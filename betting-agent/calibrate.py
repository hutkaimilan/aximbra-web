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
}

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


def match_events(row: dict) -> dict:
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


def collect(season: str) -> dict:
    out: dict = {}
    for league in LEAGUES:
        for row in download(season, league):
            for k, pts in match_events(row).items():
                out.setdefault(k, []).extend(pts)
    return out


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    fit, test = collect(FIT), collect(TEST)
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
        "max_ece": calibration.MAX_ECE, "markets": markets,
    }, ensure_ascii=False, indent=1), "utf-8")
    logger.info("kiírva: %s", OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
