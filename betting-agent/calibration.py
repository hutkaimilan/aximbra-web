"""Kalibráció: a kiírt esély legyen annyi, amennyiszer a tipp valóban bejön.

Az isotonic regresszió (pool-adjacent-violators) a becsült esélyhez a visszamért
gyakoriságot rendeli, monoton módon: ha a modell a 70%-os tippjeinél valójában
63%-ot ért el, a 70%-ból 63% lesz. A leképezést piaconként (és a Fogadásépítő-
stratégiánként) a calibrate.py illeszti a football-data.co.uk régi meccsein, és
calibration.json-ba írja; élesben ez a modul olvassa és alkalmazza.

A korrekciót csak ott használjuk, ahol a külön évadon mérve valóban javít: egy
évadnyi adatra illesztett isotonic leképezés könnyen túlillesztett, és rontana.
Egy piac akkor „ok", ha a választott változat (korrigált vagy nyers) átlagos
eltérése (ECE) a külön évadon legfeljebb 3% — különben a szelvénykészítő nem ajánlja.
"""
import json
import math
import threading
from pathlib import Path

MAX_ECE = 0.03
MIN_TEST = 300
BINS = 10


def isotonic(points: list[tuple[float, int]]) -> list[tuple[float, float]]:
    """(becsült esély, bejött-e 0/1) párokból monoton leképezés: [(blokk átlagos becslése, blokk gyakorisága)]."""
    if not points:
        return []
    pts = sorted(points)
    blocks = []  # [összes becslés, összes találat, darab]
    for p, y in pts:
        blocks.append([p, float(y), 1])
        while len(blocks) > 1 and blocks[-2][1] / blocks[-2][2] > blocks[-1][1] / blocks[-1][2]:
            s, h, n = blocks.pop()
            blocks[-1][0] += s
            blocks[-1][1] += h
            blocks[-1][2] += n
    return [(s / n, h / n) for s, h, n in blocks]


def apply_map(mapping: list, p: float) -> float:
    """Lineáris interpoláció a blokkok között; a szélein a szélső blokk értéke."""
    if not mapping:
        return p
    if p <= mapping[0][0]:
        return mapping[0][1]
    if p >= mapping[-1][0]:
        return mapping[-1][1]
    lo, hi = 0, len(mapping) - 1
    while hi - lo > 1:
        mid = (lo + hi) // 2
        if mapping[mid][0] <= p:
            lo = mid
        else:
            hi = mid
    (x0, y0), (x1, y1) = mapping[lo], mapping[hi]
    return y0 if x1 == x0 else y0 + (y1 - y0) * (p - x0) / (x1 - x0)


def curve(points: list[tuple[float, int]], bins: int = BINS) -> list[list]:
    """Megbízhatósági tábla: [alsó határ, felső határ, átlagos becslés, valós gyakoriság, darab]."""
    out = []
    for b in range(bins):
        lo, hi = b / bins, (b + 1) / bins
        sel = [(p, y) for p, y in points if lo <= p < hi or (b == bins - 1 and p == 1.0)]
        if sel:
            out.append([lo, hi, sum(p for p, _ in sel) / len(sel), sum(y for _, y in sel) / len(sel), len(sel)])
    return out


def ece(points: list[tuple[float, int]], bins: int = BINS) -> float:
    n = len(points)
    return sum(c[4] / n * abs(c[2] - c[3]) for c in curve(points, bins)) if n else 0.0


def brier(points: list[tuple[float, int]]) -> float:
    return sum((p - y) ** 2 for p, y in points) / len(points) if points else 0.0


def logloss(points: list[tuple[float, int]]) -> float:
    eps = 1e-6
    return -sum(y * math.log(max(p, eps)) + (1 - y) * math.log(max(1 - p, eps)) for p, y in points) / len(points) \
        if points else 0.0


def evaluate(fit: list, test: list, final: list) -> dict:
    """fit: illesztő évad, test: mérő évad, final: az élesben használt leképezés adatai (mindkét évad)."""
    m = isotonic(fit)
    cal_test = [(apply_map(m, p), y) for p, y in test]
    base = sum(y for _, y in fit) / len(fit) if fit else 0.5
    res = {
        "n_fit": len(fit), "n_test": len(test),
        "brier": round(brier(cal_test), 4), "brier_raw": round(brier(test), 4),
        "brier_base": round(brier([(base, y) for _, y in test]), 4),
        "logloss": round(logloss(cal_test), 4),
        "ece_raw": round(ece(test), 4), "ece": round(ece(cal_test), 4),
        "curve": [[round(x, 4) for x in c[:4]] + [c[4]] for c in curve(cal_test)],
        "curve_raw": [[round(x, 4) for x in c[:4]] + [c[4]] for c in curve(test)],
        "map": [[round(x, 4), round(y, 4)] for x, y in isotonic(final)],
    }
    # A korrekció csak akkor kell, ha a mérési évadon tényleg csökkenti az eltérést.
    res["use_map"] = res["ece"] < res["ece_raw"]
    if not res["use_map"]:
        res["curve"] = res["curve_raw"]
    res["ece_used"] = res["ece"] if res["use_map"] else res["ece_raw"]
    res["ok"] = res["n_test"] >= MIN_TEST and res["ece_used"] <= MAX_ECE
    return res


class Calibration:
    """A calibration.json élesben. Hiányzó fájlnál semmit nem korrigál, és semmit nem nevez kalibráltnak."""

    def __init__(self, data: dict | None):
        self.data = data or {}
        self.markets = self.data.get("markets", {})

    @classmethod
    def load(cls, path: Path) -> "Calibration":
        try:
            return cls(json.loads(Path(path).read_text("utf-8")))
        except (OSError, ValueError):
            return cls(None)

    def apply(self, key: str, p: float) -> float:
        m = self.markets.get(key)
        if not m or not m.get("use_map") or not m.get("map"):
            return p
        return min(0.999, max(0.001, apply_map(m["map"], p)))

    def ok(self, key: str) -> bool:
        return bool(self.markets.get(key, {}).get("ok"))

    @property
    def available(self) -> bool:
        return bool(self.markets)


_cache: dict = {}
_lock = threading.Lock()


def get(path: Path) -> Calibration:
    with _lock:
        if path not in _cache:
            _cache[path] = Calibration.load(path)
        return _cache[path]
