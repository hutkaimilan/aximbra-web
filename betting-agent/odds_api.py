"""Szorzók a The Odds API-ból (the-odds-api.com), lemezes gyorsítótárral.

A kvóta pénz: egy hívás ára piacok × régiók, tíz iroda egy régiónak számít.
Öt bajnokság × két piac (1X2, gólszám) = 10 kredit futásonként, az ingyenes
havi 500 kreditből ez ~50 futás. A gyorsítótár miatt egy újrafuttatás (hiba,
elgépelt kapcsoló) nem fizet újra.

Egy bajnokság hibája nem állítja meg a többit: a hívó a hibalistát a
jelentésbe írja. Rossz kulcsnál viszont nincs értelme folytatni.
"""
import json
import logging
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

BASE = "https://api.the-odds-api.com/v4/sports/{sport}/odds/"
TIMEOUT = 30
RETRY_WAITS = (2, 4, 8)


class OddsApiError(RuntimeError):
    pass


class AuthError(OddsApiError):
    pass


@dataclass
class Match:
    id: str
    sport: str
    kickoff: datetime
    home: str
    away: str
    # iroda -> (hazai, döntetlen, vendég) szorzó
    h2h: dict = field(default_factory=dict)
    # iroda -> {vonal: (felett, alatt)}; csak x,5-ös vonal: a negyedes ázsiai vonalnak nincs Tippmix-megfelelője
    totals: dict = field(default_factory=dict)


def _get(url: str, sleep=time.sleep) -> tuple[list, dict]:
    last = None
    for attempt in range(len(RETRY_WAITS) + 1):
        try:
            with urllib.request.urlopen(url, timeout=TIMEOUT) as r:
                return json.loads(r.read().decode("utf-8")), dict(r.headers)
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", "replace")[:300]
            if e.code == 401:
                raise AuthError("a The Odds API elutasította a kulcsot (401) — ODDS_API_KEY") from e
            if e.code == 429 or e.code >= 500:
                last = OddsApiError(f"HTTP {e.code}: {body}")
            else:
                # 404 ismeretlen bajnokság, 422 hibás paraméter: újrapróbálni felesleges.
                raise OddsApiError(f"HTTP {e.code}: {body}") from e
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
            last = OddsApiError(f"hálózati hiba: {type(e).__name__}: {e}")
        if attempt < len(RETRY_WAITS):
            sleep(RETRY_WAITS[attempt])
    raise last


def fetch_league(sport: str, api_key: str, bookmakers: str, days_ahead: int,
                 cache_dir: Path, cache_minutes: int = 30, now: datetime | None = None,
                 getter=_get) -> tuple[list, str]:
    """Nyers eseménylista egy bajnokságra és egy sor a kvótáról (vagy hogy gyorsítótárból jött)."""
    now = now or datetime.now(timezone.utc)
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache = cache_dir / f"{sport}.json"
    if cache.exists():
        try:
            saved = json.loads(cache.read_text("utf-8"))
            age = now - datetime.fromisoformat(saved["fetched_at"])
            if age < timedelta(minutes=cache_minutes) and saved.get("bookmakers") == bookmakers:
                return saved["data"], f"gyorsítótár ({int(age.total_seconds() // 60)} perces)"
        except (OSError, ValueError, KeyError) as e:
            logger.warning("sérült gyorsítótár, újratöltöm: %s (%s)", cache, e)
    params = {
        "apiKey": api_key,
        "markets": "h2h,totals",
        "bookmakers": bookmakers,
        "oddsFormat": "decimal",
        "commenceTimeFrom": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "commenceTimeTo": (now + timedelta(days=days_ahead)).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    data, headers = getter(BASE.format(sport=sport) + "?" + urllib.parse.urlencode(params))
    if not isinstance(data, list):
        raise OddsApiError(f"váratlan válasz: {str(data)[:200]}")
    tmp = cache.with_suffix(".tmp")
    tmp.write_text(json.dumps({"fetched_at": now.isoformat(), "bookmakers": bookmakers, "data": data}), "utf-8")
    os.replace(tmp, cache)  # atomi csere: egy félbeszakadt írás nem hagy sérült fájlt
    h = {k.lower(): v for k, v in headers.items()}
    return data, f"kvóta: {h.get('x-requests-remaining', '?')} maradt, ez {h.get('x-requests-last', '?')} volt"


def _price(x):
    return x if isinstance(x, (int, float)) and 1.0 < x < 10_000 else None


def parse_events(raw: list, sport: str) -> list[Match]:
    out = []
    for ev in raw:
        try:
            m = Match(id=str(ev["id"]), sport=sport,
                      kickoff=datetime.fromisoformat(ev["commence_time"].replace("Z", "+00:00")),
                      home=ev["home_team"], away=ev["away_team"])
        except (KeyError, TypeError, ValueError) as e:
            logger.warning("kihagyott esemény (%s): %s", e, str(ev)[:120])
            continue
        for bk in ev.get("bookmakers") or []:
            key = bk.get("key")
            for mk in bk.get("markets") or []:
                outs = mk.get("outcomes") or []
                if mk.get("key") == "h2h":
                    by = {o.get("name"): _price(o.get("price")) for o in outs}
                    trio = (by.get(m.home), by.get("Draw"), by.get(m.away))
                    if all(trio):
                        m.h2h[key] = trio
                elif mk.get("key") == "totals":
                    lines = {}
                    for o in outs:
                        pt, pr = o.get("point"), _price(o.get("price"))
                        if not isinstance(pt, (int, float)) or pr is None or (pt * 2) % 2 != 1:
                            continue
                        lines.setdefault(float(pt), {})[o.get("name")] = pr
                    for pt, d in lines.items():
                        if d.get("Over") and d.get("Under"):
                            m.totals.setdefault(key, {})[pt] = (d["Over"], d["Under"])
        if m.h2h:
            out.append(m)
        else:
            logger.info("nincs 1X2 szorzó, kihagyva: %s – %s", m.home, m.away)
    return out
