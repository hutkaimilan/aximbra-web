"""Élő csapatstatisztika a szöglet- és lapmodellhez: football-data.co.uk, aktuális + előző évad.

A táblázatokat hetente frissítik; 12 órás gyorsítótárral bőven elég. Ha a letöltés
nem sikerül, nincs szöglet/lap becslés — a többi piac ettől működik tovább.
"""
import csv
import io
import logging
import urllib.error
import urllib.request
from datetime import datetime, timezone

import names
import teamstats

logger = logging.getLogger(__name__)

URL = "https://www.football-data.co.uk/mmz4281/{season}/{league}.csv"
# TippmixPro-sorozat → football-data bajnokságkód; a BL/EL csapatait mind a négy bajnokságban keressük
LEAGUE_OF = {"pl": "E0", "laliga": "SP1", "bundesliga": "D1", "portugal": "P1"}
LEAGUES = tuple(LEAGUE_OF.values())
TIMEOUT = 30


class FootballDataError(RuntimeError):
    pass


def season_codes(now: datetime | None = None) -> tuple[str, str]:
    """Az aktuális és az előző évad kódja ("2627", "2526"); az évad júliusban vált."""
    now = now or datetime.now(timezone.utc)
    start = now.year if now.month >= 7 else now.year - 1
    cur = f"{start % 100:02d}{(start + 1) % 100:02d}"
    prev = f"{(start - 1) % 100:02d}{start % 100:02d}"
    return cur, prev


def _download(season: str, league: str) -> list[dict]:
    req = urllib.request.Request(URL.format(season=season, league=league), headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            text = r.read().decode("utf-8-sig", errors="replace")
    except urllib.error.HTTPError as e:
        if e.code == 404:  # évad elején az új táblázat még nem létezik
            return []
        raise FootballDataError(f"football-data HTTP {e.code}") from e
    except (urllib.error.URLError, TimeoutError) as e:
        raise FootballDataError(f"football-data nem érhető el ({type(e).__name__})") from e
    return list(csv.DictReader(io.StringIO(text)))


def load(now: datetime | None = None) -> dict:
    """{bajnokságkód: {"corners": LeagueStats, "cards": LeagueStats}}."""
    cur, prev = season_codes(now)
    out = {}
    for lg in LEAGUES:
        out[lg] = teamstats.build(_download(cur, lg), _download(prev, lg))
    if not any(st["corners"].teams for st in out.values()):
        raise FootballDataError("üres football-data táblázatok")
    return out


# Hazai bajnokságban a csapat biztosan a táblázatban van, ott elég a lazább küszöb („Atl. Madrid" = „Ath Madrid").
# BL/EL-ben viszont a legtöbb csapat NINCS a négy bajnokságban, és laza küszöbnél a „legközelebbi" nevet
# kapná meg (Lens → Leeds, Milan → Mainz, Celtic → Celta) — ezért ott szigorú.
MIN_SCORE_DOMESTIC = 0.70
MIN_SCORE_EUROPE = 0.85


def find_team(stats: dict, name: str, comp_key: str) -> tuple[str, str] | None:
    """(bajnokságkód, football-data csapatnév) a TippmixPro-névhez, vagy None."""
    domestic = comp_key in LEAGUE_OF
    leagues = [LEAGUE_OF[comp_key]] if domestic else list(stats)
    threshold = MIN_SCORE_DOMESTIC if domestic else MIN_SCORE_EUROPE
    best = None
    for lg in leagues:
        if lg not in stats:
            continue
        hit = names.best_team(name, sorted(stats[lg]["corners"].teams), min_score=threshold)
        if hit:
            s = names.similarity(name, hit)
            if best is None or s > best[0]:
                best = (s, lg, hit)
    return (best[1], best[2]) if best else None


def expected(stats: dict, home: str, away: str, comp_key: str) -> dict | None:
    """{"corners": várható összeg, "cards": várható összeg}, ha mindkét csapat ugyanabban a bajnokságban ismert."""
    h, a = find_team(stats, home, comp_key), find_team(stats, away, comp_key)
    # Két különböző bajnokság csapatainál (BL/EL) nincs közös viszonyítási alap: nem becsülünk.
    if not h or not a or h[0] != a[0]:
        return None
    out = {}
    for key in teamstats.STATS:
        e = stats[h[0]][key].expected(h[1], a[1])
        if e:
            out[key] = e[0] + e[1]
    return out or None
