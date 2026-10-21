"""Visszamérés és kalibráció a football-data.co.uk ingyenes táblázataiból → calibration.json.

Minden régi meccsre ugyanazt számolja, mint élesben a weboldal: a záró piaci
átlagszorzókból (1X2, 2,5 gól) árrésmentes esély, rá illesztett gólmodell, és a
szelvénykészítő tippválasztása (builder.options). Utána összeveti a valós
eredménnyel. A korrekciót az egyik évadon illeszti, a MÁSIKON méri (különben a
saját adatán mérné magát), az élesben használt leképezés pedig mindkét évadból készül.

Futtatás (évadonként egyszer elég, az eredményt a repóba kell tenni):
    python3 calibrate.py
"""
import csv
import io
import json
import logging
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import builder
import calibration
import fair
import poisson

LEAGUES = {"E0": "Premier League", "SP1": "La Liga", "D1": "Bundesliga", "P1": "Portugál bajnokság"}
FIT, TEST = "2425", "2526"
URL = "https://www.football-data.co.uk/mmz4281/{season}/{league}.csv"
HERE = Path(__file__).resolve().parent
CACHE = HERE / "out" / "football-data"
OUT = HERE / "calibration.json"

# piac kulcsa → magyar név a „Mennyire pontos?" nézethez
NAMES = {
    "1x2": "Ki nyer? (1X2)", "dc": "Kétesély", "ou": "Gólszám 2,5", "btts": "Mindkét csapat szerez gólt",
    "win_goals": "Fogadásépítő: győztes + gólszám", "goals": "Fogadásépítő: gólszám + mindkét csapat gólja",
    "full": "Fogadásépítő: győztes + gólszám + mindkét csapat gólja",
    "hcp": "Hendikep (háromesélyes, ±1)", "ht1x2": "1X2 - 1. félidő", "htou": "Gólszám - 1. félidő (0,5 és 1,5)",
}
DEFAULT_HT_RATIO = (0.44, 0.44)

logger = logging.getLogger(__name__)


def download(season: str, league: str) -> list[dict]:
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / f"{league}_{season}.csv"
    if not path.exists():
        req = urllib.request.Request(URL.format(season=season, league=league), headers={"User-Agent": "Mozilla/5.0"})
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                path.write_bytes(r.read())
        except (urllib.error.URLError, TimeoutError) as e:
            raise RuntimeError(f"nem jött le: {league} {season} ({e})") from e
    text = path.read_bytes().decode("utf-8-sig", errors="replace")
    return list(csv.DictReader(io.StringIO(text)))


def _num(row: dict, *keys) -> float | None:
    for k in keys:
        try:
            v = float(row.get(k) or "")
        except ValueError:
            continue
        if v > 1.0:
            return v
    return None


def ht_ratio(rows: list[dict]) -> tuple[float, float]:
    """A gólok mekkora része esik az 1. félidőre, hazai és vendég oldalon külön (a félidős modellhez)."""
    tot = [0, 0, 0, 0]
    for r in rows:
        try:
            vals = [int(r["HTHG"]), int(r["FTHG"]), int(r["HTAG"]), int(r["FTAG"])]
        except (KeyError, ValueError):
            continue
        tot = [a + b for a, b in zip(tot, vals)]
    if not tot[1] or not tot[3]:
        return DEFAULT_HT_RATIO
    return tot[0] / tot[1], tot[2] / tot[3]


def match_events(row: dict, ratio: tuple = DEFAULT_HT_RATIO) -> dict:
    """Egy régi meccs → {piac kulcsa: [(becsült esély, bejött-e)]}. Hiányos sornál üres."""
    try:
        hg, ag = int(row["FTHG"]), int(row["FTAG"])
    except (KeyError, ValueError):
        return {}
    o1 = [_num(row, "AvgCH", "AvgH"), _num(row, "AvgCD", "AvgD"), _num(row, "AvgCA", "AvgA")]
    oou = [_num(row, "AvgC>2.5", "Avg>2.5"), _num(row, "AvgC<2.5", "Avg<2.5")]
    if None in o1:
        return {}
    p1, px, p2 = fair.devig_power(o1)
    p_over = fair.devig_power(oou)[0] if None not in oou else None
    lh, la, _ = poisson.fit([p1, px, p2], {2.5: p_over} if p_over is not None else {})
    mat = poisson.score_matrix(lh, la)
    mp = poisson.outcome_probs(mat)

    ev = {"1x2": [(p1, int(hg > ag)), (px, int(hg == ag)), (p2, int(hg < ag))],
          "dc": [(p1 + px, int(hg >= ag)), (px + p2, int(hg <= ag)), (p1 + p2, int(hg != ag))],
          "btts": [(mp["btts"], int(hg > 0 and ag > 0)), (1 - mp["btts"], int(hg == 0 or ag == 0))]}
    if p_over is not None:
        ev["ou"] = [(p_over, int(hg + ag > 2.5)), (1 - p_over, int(hg + ag < 2.5))]
    # Háromesélyes hendikep a TippmixPro tipikus vonalain (a hazai −1 vagy +1).
    for h in (-1.0, 1.0):
        ev.setdefault("hcp", []).extend(
            (builder.joint_prob(mat, [("hcp", pk, h)]), int(builder._cond("hcp", pk, h)(hg, ag))) for pk in ("1", "X", "2"))
    # 1. félidő: a gólvárható érték a félidős aránnyal, a valós félidős eredménnyel összevetve.
    try:
        hhg, hag = int(row["HTHG"]), int(row["HTAG"])
    except (KeyError, ValueError):
        hhg = hag = None
    if hhg is not None:
        ht = poisson.score_matrix(lh * ratio[0], la * ratio[1])
        ev["ht1x2"] = [(builder.joint_prob(ht, [("1x2", pk, None)]), int(builder._cond("1x2", pk, None)(hhg, hag)))
                       for pk in ("1", "X", "2")]
        ev["htou"] = [(builder.joint_prob(ht, [("ou", pk, ln)]), int(builder._cond("ou", pk, ln)(hhg, hag)))
                      for ln in (0.5, 1.5) for pk in ("Több", "Kevesebb")]

    # A szelvénykészítő tippválasztása ugyanazzal a kóddal, mint élesben.
    outs = [("1x2", k) for k in ("1", "X", "2")] + [("dc", k) for k in ("1X", "X2", "12")] + \
           [("btts", k) for k in ("Igen", "Nem")]
    markets = [{"key": m, "name": m, "line": None, "outcomes": [{"id": f"{m}{k}", "pick": k, "odds": 2.0}
                                                                 for mm, k in outs if mm == m]}
               for m in ("1x2", "dc", "btts")]
    if p_over is not None:
        markets.append({"key": "ou", "name": "ou", "line": 2.5, "outcomes": [
            {"id": "o", "pick": "Több", "odds": 2.0}, {"id": "u", "pick": "Kevesebb", "odds": 2.0}]})
    match = {"id": "x", "home": "H", "away": "A", "kickoff": "", "markets": markets,
             "analysis": {"p_home": p1, "p_draw": px, "p_away": p2, "xg_home": lh, "xg_away": la}}
    for kind, (picks, prob) in builder.options(match).items():
        if kind in ("win_goals", "goals", "full"):
            conds = [builder._cond(p["market"], p["pick"], p["line"]) for p in picks]
            ev.setdefault(kind, []).append((prob, int(all(c(hg, ag) for c in conds))))
    return ev


def collect(season: str, ratio: tuple) -> dict:
    out: dict = {}
    for league in LEAGUES:
        for row in download(season, league):
            for k, pts in match_events(row, ratio).items():
                out.setdefault(k, []).extend(pts)
    return out


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    # A félidős arányt csak az illesztő évadból számoljuk, hogy a mérési évad tényleg külön maradjon.
    ratio = ht_ratio([r for lg in LEAGUES for r in download(FIT, lg)])
    logger.info("félidős gólarány: hazai %.3f, vendég %.3f", *ratio)
    fit, test = collect(FIT, ratio), collect(TEST, ratio)
    markets = {}
    for key in NAMES:
        if key not in fit or key not in test:
            continue
        res = calibration.evaluate(fit[key], test[key], fit[key] + test[key])
        res["name"] = NAMES[key]
        markets[key] = res
        logger.info("%-10s n=%5d  ECE nyers %.3f, korrigált %.3f → %s  Brier %.4f (alap %.4f)  %s", key,
                    res["n_test"], res["ece_raw"], res["ece"], "korrigált" if res["use_map"] else "nyers",
                    res["brier"] if res["use_map"] else res["brier_raw"], res["brier_base"], "OK" if res["ok"] else "NEM")
    OUT.write_text(json.dumps({
        "generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": "football-data.co.uk (záró piaci átlagszorzók és eredmények)",
        "leagues": list(LEAGUES.values()), "fit_season": FIT, "test_season": TEST,
        "max_ece": calibration.MAX_ECE, "ht_ratio": [round(ratio[0], 4), round(ratio[1], 4)], "markets": markets,
    }, ensure_ascii=False, indent=1), "utf-8")
    logger.info("kiírva: %s", OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
