"""TippmixPro-szorzók és szelvény-ellenőrzés a TippmixPro saját felületéről.

A TippmixPro weboldala (sports2.tippmixpro.hu, EveryMatrix-platform) egy
WebSocket-csatornán (WAMP protokoll) tölti a kínálatot, bejelentkezés nélkül.
Ugyanezt olvassuk, ugyanazokkal a hívásokkal, mint a böngésző:

- /sports#initialDump  tournaments/1/{ország}  → bajnokságok
- /sports#initialDump  tournament-aggregator-groups-overview/{bajnokság}/…
                                               → meccsek, piacok, szorzók
- /sports#bettingOptionsV2                     → a szelvény ellenőrzése: kötéstiltás
  (forbiddenCombinations), Fogadásépítő-szorzó egy meccsen belül (betBuilder),
  minimális tét

Ez nem dokumentált, nyilvános API: a TippmixPro bármikor megváltoztathatja.
Ha eltörik, a hívó a legutóbbi sikeres adatot mutatja „elavult" jelzéssel,
és a hibát kiírja — csendben rossz szorzót nem ad. A terhelés egy böngészőző
emberé: csak kérésre és gyorsítótárral kérdezünk.
"""
import json
import logging
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone

from websockets.exceptions import WebSocketException
from websockets.sync.client import connect

logger = logging.getLogger(__name__)

URL = "wss://sportsapi.tippmixpro.hu/v2"
ORIGIN = "https://sports2.tippmixpro.hu"
TOPIC = "/sports/2901/hu"
FOOTBALL = "1"
REGULAR_TIME = "3"  # „Rendes játékidő": a hosszabbítás nem számít
# 1X2, gólszám, mindkét csapat gólt szerez, kétesély, döntetlennél a tét visszajár
MARKET_GROUPS = "1380,1381,1382,1383,1385"
TIMEOUT = 20
HELLO = [1, "www.tippmixpro.hu", {"agent": "Wampy.js v6.2.2",
                                  "roles": {"caller": {"features": {}}, "subscriber": {"features": {}}}}]

# fogadási típus azonosító → (kulcs, név)
MARKETS = {
    "69": ("1x2", "1X2"),
    "9": ("dc", "Kétesély"),
    "47": ("ou", "Gólszám"),
    "76": ("btts", "Mindkét csapat szerez gólt"),
    "112": ("dnb", "Döntetlennél a tét visszajár"),
}
PICKS = {
    "1x2": {"home": "1", "draw": "X", "away": "2"},
    "dc": {"home_draw": "1X", "away_draw": "X2", "home_away": "12"},
    "ou": {"over": "Több", "under": "Kevesebb"},
    "btts": {"yes": "Igen", "no": "Nem"},
    "dnb": {"home": "1", "away": "2"},
}
ORDER = {"1x2": ["1", "X", "2"], "dc": ["1X", "X2", "12"], "ou": ["Több", "Kevesebb"],
         "btts": ["Igen", "Nem"], "dnb": ["1", "2"]}


@dataclass(frozen=True)
class Competition:
    key: str
    name: str
    location: str        # TippmixPro országazonosító
    pattern: str         # a bajnokság neve a TippmixPro-n, évadszám nélkül
    espn: str            # ESPN bajnokságkód (eredményekhez)
    odds_api: str        # The Odds API kulcs (valós esélyhez)


COMPETITIONS = (
    Competition("bl", "Bajnokok Ligája", "67", r"^BL \d{4}/\d{4}$", "uefa.champions", "soccer_uefa_champs_league"),
    Competition("el", "Európa-liga", "67", r"^EL \d{4}/\d{4}$", "uefa.europa", "soccer_uefa_europa_league"),
    Competition("pl", "Premier League", "77", r"^Premier Liga \d{4}/\d{4}$", "eng.1", "soccer_epl"),
    Competition("laliga", "La Liga", "65", r"^Spanyol bajnokság \d{4}/\d{4}$", "esp.1", "soccer_spain_la_liga"),
    Competition("bundesliga", "Bundesliga", "54", r"^Bundesliga 1\. \d{4}/\d{4}$", "ger.1",
                "soccer_germany_bundesliga"),
    Competition("portugal", "Portugál bajnokság", "182", r"^Portugál bajnokság \d{4}/\d{4}$", "por.1",
                "soccer_portugal_primeira_liga"),
)
BY_KEY = {c.key: c for c in COMPETITIONS}


class TippmixError(RuntimeError):
    pass


@dataclass
class Outcome:
    offer_id: str
    market: str      # 1x2 | dc | ou | btts | dnb
    pick: str        # "1", "X2", "Több", "Igen" …
    odds: float
    line: float | None = None


@dataclass
class TMMatch:
    id: str
    competition: str
    home: str
    away: str
    kickoff: datetime
    outcomes: list = field(default_factory=list)


class Session:
    """Egy WebSocket-kapcsolat. Rövid életű: lekérdezés után bezárjuk, nincs mit életben tartani."""

    def __init__(self, timeout: float = TIMEOUT):
        self.timeout = timeout
        self._id = 0
        try:
            self.ws = connect(URL, subprotocols=["wamp.2.json"], origin=ORIGIN, open_timeout=timeout,
                              close_timeout=3, max_size=64 * 1024 * 1024)
            self.ws.send(json.dumps(HELLO))
            welcome = json.loads(self.ws.recv(timeout=timeout))
        except (OSError, WebSocketException, TimeoutError, ValueError) as e:
            raise TippmixError(f"a TippmixPro nem érhető el ({type(e).__name__}: {e})") from e
        if not welcome or welcome[0] != 2:
            self.close()
            raise TippmixError(f"a TippmixPro nem fogadta a kapcsolatot: {str(welcome)[:200]}")

    def call(self, proc: str, kwargs: dict) -> dict:
        self._id += 1
        rid = self._id
        deadline = time.monotonic() + self.timeout
        try:
            self.ws.send(json.dumps([48, rid, {}, proc, [], kwargs]))
            while True:
                left = deadline - time.monotonic()
                if left <= 0:
                    raise TippmixError(f"a TippmixPro nem válaszolt ({proc})")
                msg = json.loads(self.ws.recv(timeout=left))
                if msg[0] == 50 and msg[1] == rid:      # RESULT
                    return msg[4] if len(msg) > 4 and isinstance(msg[4], dict) else {}
                if msg[0] == 8 and len(msg) > 2 and msg[2] == rid:  # ERROR
                    raise TippmixError(f"a TippmixPro hibát adott ({proc}): {str(msg[4:])[:200]}")
                # Minden más (feliratkozási események) nem nekünk szól.
        except (OSError, WebSocketException, TimeoutError, ValueError) as e:
            raise TippmixError(f"megszakadt a kapcsolat a TippmixPro-val ({type(e).__name__})") from e

    def dump(self, topic: str) -> list:
        return self.call("/sports#initialDump", {"topic": topic}).get("records") or []

    def close(self):
        try:
            self.ws.close()
        except Exception:  # noqa: BLE001 — bezáráskor már nincs mit kezdeni a hibával
            pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


def find_tournaments(session: Session, comp: Competition) -> list[str]:
    recs = session.dump(f"{TOPIC}/tournaments/{FOOTBALL}/{comp.location}")
    rx = re.compile(comp.pattern)
    return [r["id"] for r in recs if r.get("_type") == "TOURNAMENT" and rx.match(r.get("name", ""))]


def parse_matches(records: list, comp_key: str, now: datetime | None = None) -> list[TMMatch]:
    """Az aggregátor rekordjaiból meccsek. A már elkezdett meccs kimarad: élőben a szorzó percenként változik."""
    now = now or datetime.now(timezone.utc)
    by_type = {}
    for r in records:
        by_type.setdefault(r.get("_type"), []).append(r)
    markets = {m["id"]: m for m in by_type.get("MARKET", [])}
    outcomes = {o["id"]: o for o in by_type.get("OUTCOME", [])}
    market_of = {rel["outcomeId"]: rel["marketId"] for rel in by_type.get("MARKET_OUTCOME_RELATION", [])}
    matches = {}
    for m in by_type.get("MATCH", []):
        try:
            kickoff = datetime.fromtimestamp(int(m["startTime"]) / 1000, tz=timezone.utc)
            home, away = m["homeParticipantName"], m["awayParticipantName"]
        except (KeyError, TypeError, ValueError):
            continue
        if kickoff <= now or str(m.get("statusId", "1")) != "1":
            continue
        matches[m["id"]] = TMMatch(id=m["id"], competition=comp_key, home=home, away=away, kickoff=kickoff)
    for b in by_type.get("BETTING_OFFER", []):
        if b.get("isAvailable") is False or str(b.get("statusId", "1")) != "1" or b.get("isLive"):
            continue
        o = outcomes.get(b.get("outcomeId"))
        mk = markets.get(market_of.get(b.get("outcomeId"), ""))
        if not o or not mk or mk.get("eventPartId") != REGULAR_TIME:
            continue
        match = matches.get(o.get("eventId"))
        kind = MARKETS.get(str(mk.get("bettingTypeId")))
        if not match or not kind:
            continue
        pick = PICKS[kind[0]].get(o.get("headerNameKey"))
        odds = b.get("odds")
        if not pick or not isinstance(odds, (int, float)) or not 1.0 < odds < 1000:
            continue
        line = o.get("paramFloat1") if kind[0] == "ou" else None
        if kind[0] == "ou" and (not isinstance(line, (int, float)) or (line * 2) % 2 != 1):
            continue
        match.outcomes.append(Outcome(offer_id=str(b["id"]), market=kind[0], pick=pick, odds=float(odds),
                                      line=float(line) if line is not None else None))
    out = [m for m in matches.values() if m.outcomes]
    for m in out:
        m.outcomes.sort(key=lambda o: (list(MARKETS).index(_type_of(o.market)), o.line or 0,
                                       ORDER[o.market].index(o.pick)))
    return sorted(out, key=lambda m: m.kickoff)


def _type_of(market_key: str) -> str:
    return next(k for k, v in MARKETS.items() if v[0] == market_key)


def fetch_competition(session: Session, comp: Competition) -> list[TMMatch]:
    ids = find_tournaments(session, comp)
    if not ids:
        raise TippmixError(f"a „{comp.name}\" nem szerepel most a TippmixPro kínálatában")
    seen, out = set(), []
    for tid in ids:
        recs = session.dump(f"{TOPIC}/tournament-aggregator-groups-overview/{tid}/default-event-info/BOTH/{MARKET_GROUPS}")
        for m in parse_matches(recs, comp.key):
            if m.id not in seen:
                seen.add(m.id)
                out.append(m)
    return sorted(out, key=lambda m: m.kickoff)


def check_slip(session: Session, selections: list[tuple[str, float]]) -> dict:
    """A TippmixPro saját szelvény-ellenőrzése.

    selections: (betting offer id, aktuális szorzó). A szorzót a TippmixPro nem
    ellenőrzi, csak összeszorozza — ezért a hívó a friss kínálatból adja.
    Visszaad: {min_stake, forbidden: [[offer_id,…]], bet_builder: [{ids, odds}]}.
    """
    if not selections:
        raise ValueError("üres szelvény")
    res = session.call("/sports#bettingOptionsV2", {
        "terminalType": "DESKTOP", "lang": "hu", "type": "SINGLE" if len(selections) == 1 else "MULTIPLE",
        "selections": [{"bettingOfferId": i, "priceValue": p} for i, p in selections]})
    if not res.get("success"):
        raise TippmixError(f"a TippmixPro nem tudta ellenőrizni a szelvényt: {str(res)[:200]}")
    forbidden = [[s["bettingOfferId"] for s in fc.get("selections", [])] for fc in res.get("forbiddenCombinations") or []]
    builder = [{"ids": [s["bettingOfferId"] for s in bb.get("selections", [])], "odds": bb.get("betBuilderOdds")}
               for bb in res.get("betBuilder") or []]
    return {"min_stake": res.get("minStake"), "max_stake": res.get("maxStake"), "forbidden": forbidden,
            "bet_builder": builder}
