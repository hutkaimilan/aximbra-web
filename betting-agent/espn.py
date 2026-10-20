"""Csapatok korábbi eredményei és a meccsek ESPN-azonosítója az ESPN nyilvános JSON-végpontjairól.

Kulcs nem kell. A végpontok nem dokumentáltak, de évek óta stabilak; ha
mégis változnak, a csapatoldal hibát mutat, a szelvénykészítés működik tovább.
"""
import json
import logging
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

import names

logger = logging.getLogger(__name__)

BASE = "https://site.api.espn.com/apis/site/v2/sports/soccer"
TIMEOUT = 15


class EspnError(RuntimeError):
    pass


def _get(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise EspnError(f"ESPN HTTP {e.code}") from e
    except (urllib.error.URLError, TimeoutError, ValueError) as e:
        raise EspnError(f"ESPN nem érhető el ({type(e).__name__})") from e


def _team(c: dict) -> dict:
    t = c.get("team") or {}
    return {"id": str(t.get("id", "")), "name": t.get("displayName") or t.get("name") or "",
            "short": t.get("shortDisplayName") or "", "logo": t.get("logo") or ""}


def fixtures(league: str, now: datetime | None = None, days: int = 16) -> list[dict]:
    """A következő napok meccsei: kezdés + a két csapat ESPN-azonosítója."""
    now = now or datetime.now(timezone.utc)
    # Napos tartományt (20261020-20261030) az ESPN 400-zal elutasít, hónapot (202610) elfogad.
    months = sorted({f"{(now + timedelta(days=d)):%Y%m}" for d in (-1, days)})
    events = []
    for month in months:
        events += _get(f"{BASE}/{league}/scoreboard?dates={month}").get("events") or []
    out = []
    for ev in events:
        try:
            comp = ev["competitions"][0]
            teams = {c.get("homeAway"): _team(c) for c in comp["competitors"]}
            out.append({"kickoff": names.parse_time(ev["date"]), "home": teams["home"], "away": teams["away"]})
        except (KeyError, IndexError, TypeError, ValueError):
            continue
    return out


def teams(league: str) -> list[dict]:
    data = _get(f"{BASE}/{league}/teams")
    try:
        raw = data["sports"][0]["leagues"][0]["teams"]
    except (KeyError, IndexError, TypeError):
        return []
    return [_team(t) for t in raw]


def _score(c: dict):
    s = c.get("score")
    if isinstance(s, dict):
        s = s.get("displayValue", s.get("value"))
    try:
        return int(float(s))
    except (TypeError, ValueError):
        return None


def _results(data: dict, team_id: str) -> list[dict]:
    out = []
    for ev in data.get("events") or []:
        try:
            comp = ev["competitions"][0]
            if not comp["status"]["type"].get("completed"):
                continue
            cs = {c.get("homeAway"): c for c in comp["competitors"]}
            home, away = cs["home"], cs["away"]
        except (KeyError, IndexError, TypeError):
            continue
        hs, as_ = _score(home), _score(away)
        if hs is None or as_ is None:
            continue
        is_home = str((home.get("team") or {}).get("id")) == team_id
        mine, theirs = (hs, as_) if is_home else (as_, hs)
        res = "GY" if mine > theirs else ("V" if mine < theirs else "D")
        # Tizenegyespárbajnál a rendes játékidő döntetlen, a továbbjutó a „winner".
        if mine == theirs and (home if is_home else away).get("winner") is True:
            res = "D"
        league = ev.get("league")
        out.append({
            "date": ev.get("date"),
            "competition": (league or {}).get("name") or (league or {}).get("abbreviation") or "",
            "home": _team(home)["name"], "away": _team(away)["name"],
            "home_score": hs, "away_score": as_, "is_home": is_home, "result": res,
        })
    return out


def team_results(team_id: str, want: int = 15, now: datetime | None = None) -> dict:
    """A csapat legutóbbi lejátszott meccsei minden sorozatból (bajnokság, kupa, nemzetközi kupa)."""
    if not team_id.isdigit():
        raise ValueError("hibás csapatazonosító")
    now = now or datetime.now(timezone.utc)
    data = _get(f"{BASE}/all/teams/{team_id}/schedule")
    team = data.get("team") or {}
    res = _results(data, team_id)
    if len(res) < want:
        # Évad elején kevés a meccs: az előző évaddal egészítjük ki.
        season = (data.get("season") or {}).get("year") or now.year
        try:
            prev = _get(f"{BASE}/all/teams/{team_id}/schedule?season={int(season) - 1}")
            res += _results(prev, team_id)
        except EspnError as e:
            logger.info("előző évad nem jött le (%s): %s", team_id, e)
    seen, uniq = set(), []
    for r in sorted(res, key=lambda r: r["date"] or "", reverse=True):
        k = (r["date"], r["home"], r["away"])
        if k not in seen:
            seen.add(k)
            uniq.append(r)
    uniq = uniq[:want]
    return {"id": team_id, "name": team.get("displayName") or "", "logo": (team.get("logos") or [{}])[0].get("href", "")
            if team.get("logos") else team.get("logo", ""), "results": uniq,
            "form": "".join(r["result"][0] for r in uniq[:5])}
