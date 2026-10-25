"""Webes felület: TippmixPro-kínálat, szelvény a TippmixPro saját ellenőrzésével, értékkereső, csapatoldal.

Erőforrás: egy Python-folyamat, a standard könyvtár HTTP-szervere és egy
WebSocket-kliens — nincs böngésző, nincs adatbázis, nincs nyelvi modell. A
Railway alvó módjában forgalom nélkül nem fut, és nem is fizetsz érte.

Minden külső adat gyorsítótárból jön, és egy kulcsot egyszerre csak egy
kérés tölt (a többi megvárja): két gyors kattintás nem kérdez kétszer, és
egy újrafuttatás nem költ újabb The Odds API-kreditet.

Környezeti változók:
  APP_PASSWORD      opcionális belépési jelszó; üresen vagy hiányában az oldal jelszó nélkül nyitott
  APP_SECRET        a munkamenet aláírókulcsa (alapból a jelszóból származik)
  ODDS_API_KEY      opcionális: valós esély és értékkereső (the-odds-api.com)
  EMERGENT_URL      az Emergentben készült Szelvénymodell szervere (a /emergent/ oldal adatforrása)
  PORT              a Railway adja
"""
import concurrent.futures
import gzip
import hashlib
import hmac
import json
import logging
import mimetypes
import os
import threading
import time
from collections import deque
from datetime import date, datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from zoneinfo import ZoneInfo

import espn
import footballdata
import markets
import names
import odds_api
import re
import urllib.error
import urllib.request
import settle
import builder
import calibration
import insight
import labels
import slip
import teamstats
import tippmix
import value
from config import DEFAULT_BOOKMAKERS, load_rules, load_strategy

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("web")

HERE = Path(__file__).resolve().parent
STATIC = HERE / "static"
TIPPMIX_TTL = int(os.environ.get("TIPPMIX_CACHE_SECONDS", "180"))
ODDS_TTL = int(os.environ.get("ODDS_CACHE_MINUTES", "120")) * 60
FIXTURES_TTL = 30 * 60
TEAM_TTL = 6 * 3600
EXTRAS_TTL = 10 * 60          # szöglet/lap szorzók: a meccsnapon mozognak, de nem percenként
EXTRAS_HOURS = 36             # a TippmixPro csak a meccsnap körül írja ki őket; korábban fölösleges kérdezni
FD_TTL = 12 * 3600            # football-data: hetente frissül
STAT_SPAN = {"corners": 2.5, "cards": 2.0}  # a kártyán csak a várható érték ± ennyi körüli vonalak
SESSION_DAYS = 30
MAX_BODY = 64 * 1024
MAX_SLIP = 20
MAX_SETTLE = 200              # egy kiértékelő kérésben ennyi tipp (a kliens kötegel)
BUDAPEST = ZoneInfo("Europe/Budapest")
MAX_DAYS = 7
MIN_SLIP_PROB = 0.60  # automatikus mód: célszorzó nélkül a szelvény becsült esélye legalább ennyi (≥ 60%)


class Cache:
    """TTL-gyorsítótár kulcsonkénti zárral; töltési hibánál a régi értéket adja vissza (elavultként)."""

    def __init__(self, max_items: int = 400):
        self._data: dict = {}
        self._locks: dict = {}
        self._guard = threading.Lock()
        self.max_items = max_items

    def _lock(self, key):
        with self._guard:
            return self._locks.setdefault(key, threading.Lock())

    def get(self, key, ttl: float, loader):
        """(érték, időbélyeg, hiba vagy None)."""
        hit = self._data.get(key)
        if hit and time.time() - hit[0] < ttl:
            return hit[1], hit[0], None
        with self._lock(key):
            hit = self._data.get(key)
            if hit and time.time() - hit[0] < ttl:
                return hit[1], hit[0], None
            try:
                val = loader()
            except Exception as e:  # noqa: BLE001 — a hívó dönti el, mutatható-e a régi érték
                if hit:
                    logger.warning("frissítés sikertelen, régi adat marad (%s): %s", key, e)
                    return hit[1], hit[0], e
                raise
            with self._guard:
                if len(self._data) >= self.max_items:
                    oldest = min(self._data, key=lambda k: self._data[k][0])
                    self._data.pop(oldest, None)
                self._data[key] = (time.time(), val)
            return val, self._data[key][0], None

    def peek(self, key):
        """(érték, időbélyeg) töltés nélkül, akár elavultan is; vagy None."""
        hit = self._data.get(key)
        return (hit[1], hit[0]) if hit else None

    def drop(self, key):
        with self._guard:
            self._data.pop(key, None)


CACHE = Cache()
CAL = calibration.get(HERE / "calibration.json")
RULES = load_rules()
STRATEGY = load_strategy()


# --- adatok --------------------------------------------------------------------------------------

def _load_tippmix() -> dict:
    """Mind a hat sorozat, párhuzamosan (sorozatonként külön kapcsolat, ~1–2 s összesen)."""
    def one(comp):
        with tippmix.Session() as s:
            return tippmix.fetch_competition(s, comp)

    out, errors = {}, {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as ex:
        futs = {ex.submit(one, c): c for c in tippmix.COMPETITIONS}
        for f in concurrent.futures.as_completed(futs):
            c = futs[f]
            try:
                out[c.key] = f.result()
            except tippmix.TippmixError as e:
                errors[c.key] = str(e)
    if not out:
        raise tippmix.TippmixError("; ".join(errors.values()) or "a TippmixPro nem adott adatot")
    return {"matches": out, "errors": errors}


def _load_fixtures(league: str) -> list:
    return espn.fixtures(league)


def _load_sharp(comp: tippmix.Competition) -> tuple[list, str]:
    key = os.environ.get("ODDS_API_KEY", "").strip()
    raw, status = odds_api.fetch_league(comp.odds_api, key, os.environ.get("ODDS_BOOKMAKERS", DEFAULT_BOOKMAKERS),
                                        STRATEGY.days_ahead + 10, Path("/tmp/odds-cache"),
                                        cache_minutes=ODDS_TTL // 60)
    analyses = []
    for m in odds_api.parse_events(raw, comp.odds_api):
        try:
            analyses.append(markets.analyse(m, STRATEGY))
        except ValueError as e:
            logger.info("kihagyott meccs (%s – %s): %s", m.home, m.away, e)
    return analyses, status


def _load_extras(match_ids: tuple) -> dict:
    """{meccsazonosító: [Outcome]} a szöglet- és lappiacokkal, 3 szálon, szálanként egy kapcsolattal.

    Egy-egy meccs hibája csak azt a meccset hagyja ki; ha mind hibás, kivétel — a gyorsítótár
    ilyenkor a legutóbbi sikeres eredményt adja vissza.
    """
    chunks = [match_ids[i::3] for i in range(3)]

    def run(ids):
        res, errs = {}, 0
        with tippmix.Session() as s:
            for mid in ids:
                try:
                    res[mid] = tippmix.fetch_extras(s, mid)
                except (tippmix.TippmixError, ValueError) as e:
                    errs += 1
                    logger.info("szöglet/lap (%s): %s", mid, e)
        return res, errs

    out, errors = {}, 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as ex:
        for f in [ex.submit(run, c) for c in chunks if c]:
            try:
                res, errs = f.result()
            except tippmix.TippmixError as e:  # a kapcsolat sem jött létre
                logger.info("szöglet/lap kapcsolat: %s", e)
                errors += 1
                continue
            out.update(res)
            errors += errs
    if match_ids and not out and errors:
        raise tippmix.TippmixError("a szöglet/lap piacok nem tölthetők")
    return out


_BG_LOADING: set = set()
_BG_GUARD = threading.Lock()


def _background(key, ttl: float, loader):
    """A gyorsítótárazott érték (akár elavultan) várakozás nélkül; ha nincs vagy lejárt, a háttérben tölti.

    A szöglet/lap kiegészítők lassúak (meccsenként 2–3 lekérés, football-data ~10 s), és nélkülük is
    teljes az oldal: ébredés utáni első kérésnél így nem vár a felhasználó, a következő frissítéstől látszanak.
    """
    hit = CACHE.peek(key)
    if hit is None or time.time() - hit[1] >= ttl:
        with _BG_GUARD:
            start = key not in _BG_LOADING
            _BG_LOADING.add(key)
        if start:
            def run():
                try:
                    CACHE.get(key, ttl, loader)
                except Exception as e:  # noqa: BLE001 — háttérszál: a hiba csak naplóba megy, a kiegészítő kimarad
                    logger.info("háttérbetöltés (%s): %s", key, e)
                finally:
                    with _BG_GUARD:
                        _BG_LOADING.discard(key)
            threading.Thread(target=run, daemon=True).start()
    return hit[0] if hit else None


def _extras_for(tm: dict) -> dict:
    """A következő EXTRAS_HOURS órában kezdődő meccsek szöglet/lap piacai."""
    now = datetime.now(timezone.utc)
    ids = tuple(sorted(m.id for ms in tm["matches"].values() for m in ms
                       if now - timedelta(hours=2) <= m.kickoff <= now + timedelta(hours=EXTRAS_HOURS)))
    if not ids:
        return {}
    # Egy kulcs a teljes listára: új meccs belépésekor (ritka) az egész újratölt, közben a régi lista szolgál.
    val = _background("extras", EXTRAS_TTL, lambda: _load_extras(ids))
    return {k: v for k, v in (val or {}).items() if k in ids}


def _football_data():
    return _background("fd", FD_TTL, footballdata.load)


def _stat_lines(outcomes: list, mu: dict | None) -> list:
    """Szöglet/lap: csak a várható érték körüli vonalak (becslés nélkül a kínálat középső vonalai)."""
    out = []
    for key, span in STAT_SPAN.items():
        os_ = [o for o in outcomes if o.market == key]
        if not os_:
            continue
        center = (mu or {}).get(key)
        if center is None:
            lines = sorted({o.line for o in os_})
            center = lines[len(lines) // 2]
        out += [o for o in os_ if abs(o.line - center) <= span]
    return out


def _group(outcomes) -> list:
    groups = []
    for o in outcomes:
        key = (o.market, o.line)
        if not groups or groups[-1]["_k"] != key:
            groups.append({"_k": key, "key": o.market, "name": _market_name(o.market, o.line), "line": o.line,
                           "outcomes": []})
        groups[-1]["outcomes"].append(o)
    return groups


def _market_name(market: str, line) -> str:
    """A TippmixPro piacneve: „Gólszám 2,5", „Hendikep -1", „Gólszám 0,5 - 1. félidő"."""
    base = {v[0]: v[1] for v in tippmix.MARKETS.values()}[market]
    if line is None:
        return base
    ln = f"{line:g}".replace(".", ",")
    if market == "htou":
        return f"Gólszám {ln} - 1. félidő"
    if market == "2hou":
        return f"Gólszám {ln} - 2. félidő"
    if market == "hcp":
        return f"{base} {line:+g}"  # a hazai csapat vonala előjellel: „Hendikep -1", „Hendikep +1"
    return f"{base} {ln}"


def _calibrated(an: dict) -> dict:
    """A meccskártya esélyei a visszamérés szerint (calibration.json); ahol nincs javító leképezés, változatlan."""
    ps = [CAL.apply("1x2", an["p_home"]), CAL.apply("1x2", an["p_draw"]), CAL.apply("1x2", an["p_away"])]
    tot = sum(ps)  # a három kimenetel külön-külön korrigált: újra 100%-ra kell hozni
    rh, ra = (CAL.data.get("ht_ratio") or [0.44, 0.44])[:2]
    out = {**an, "p_home": ps[0] / tot, "p_draw": ps[1] / tot, "p_away": ps[2] / tot,
           "over25": CAL.apply("ou", an["over25"]),
           # az 1. félidő gólvárható értéke a visszamért félidős aránnyal (a félidős piacokhoz)
           "xg_ht_home": an["xg_home"] * rh, "xg_ht_away": an["xg_away"] * ra}
    if an.get("btts_source") != "piaci":
        out["btts"] = CAL.apply("btts", an["btts"])
    return out


def build_state() -> dict:
    tm, ts, err = CACHE.get("tippmix", TIPPMIX_TTL, _load_tippmix)
    has_key = bool(os.environ.get("ODDS_API_KEY", "").strip())
    fair_status, errors = [], []
    if err:
        errors.append(f"A TippmixPro-adat nem frissült ({err}); a legutóbbi sikeres lekérdezést látod.")
    extras = _extras_for(tm)
    fd = _football_data() if extras else None  # szöglet/lap modell csak akkor kell, ha van ilyen piac
    disp = CAL.data.get("dispersion") or {}
    comps = []
    for comp in tippmix.COMPETITIONS:
        ms = tm["matches"].get(comp.key, [])
        entry = {"key": comp.key, "name": comp.name, "error": tm["errors"].get(comp.key), "matches": []}
        espn_map, fair_map = {}, {}
        if ms:
            try:
                fx, _, _ = CACHE.get(f"fx:{comp.espn}", FIXTURES_TTL, lambda l=comp.espn: _load_fixtures(l))
                idx = names.match_events(ms, fx, lambda m: (m.kickoff, m.home, m.away),
                                         lambda f: (f["kickoff"], f["home"]["name"], f["away"]["name"]))
                espn_map = {ms[i].id: fx[j] for i, j in idx.items()}
            except espn.EspnError as e:
                logger.info("ESPN-meccslista (%s): %s", comp.espn, e)
            if has_key:
                try:
                    (analyses, status), _, serr = CACHE.get(f"sharp:{comp.key}", ODDS_TTL, lambda c=comp: _load_sharp(c))
                    fair_map = value.pair(ms, analyses)
                    fair_status.append(f"{comp.name}: {len(fair_map)}/{len(ms)} meccshez van valós esély ({status})")
                    if serr:
                        fair_status.append(f"{comp.name}: a valós esély nem frissült ({serr})")
                except odds_api.AuthError as e:
                    fair_status.append(str(e))
                    has_key = False
                except odds_api.OddsApiError as e:
                    fair_status.append(f"{comp.name}: nincs valós esély ({e})")
        for m in ms:
            fx = espn_map.get(m.id)
            a = fair_map.get(m.id)
            mu = footballdata.expected(fd, m.home, m.away, comp.key) if fd and m.id in extras else None
            mk = []
            for g in _group(list(m.outcomes) + _stat_lines(extras.get(m.id, []), mu)):
                outs = []
                for o in g["outcomes"]:
                    item = {"id": o.offer_id, "pick": o.pick, "odds": o.odds,
                            "label": labels.short(o.market, o.pick, m.home, m.away, o.line),
                            "text": labels.sentence(o.market, o.pick, m.home, m.away, o.line)}
                    if a:
                        ev = value.evaluate(o, a, STRATEGY)
                        if ev:
                            item.update({k: (round(v, 4) if isinstance(v, float) else v) for k, v in ev.items()})
                    outs.append(item)
                mk.append({"key": g["key"], "name": g["name"], "line": g["line"], "outcomes": outs})
            one_x_two = [o.odds for o in m.outcomes if o.market == "1x2"]
            an = insight.from_sharp(a) if a else insight.from_tippmix(m)
            if an:
                an = _calibrated(an)
                for key in teamstats.STATS:
                    if mu and mu.get(key):
                        an[f"{key}_mu"] = mu[key]
                        an[f"disp_{key}"] = float(disp.get(key) or 1e6)
            entry["matches"].append({
                "id": m.id, "home": m.home, "away": m.away, "kickoff": m.kickoff.isoformat(),
                "margin": round(sum(1 / x for x in one_x_two) - 1, 4) if len(one_x_two) == 3 else None,
                "espn": {"league": comp.espn, "home": fx["home"]["id"] if fx else None,
                         "away": fx["away"]["id"] if fx else None,
                         "home_logo": fx["home"]["logo"] if fx else "", "away_logo": fx["away"]["logo"] if fx else ""},
                "markets": mk,
                "analysis": {k: (round(v, 4) if isinstance(v, float) else v) for k, v in an.items()} if an else None,
                "sharp": {"sources": a.sources, "confidence": a.confidence, "xg": [round(a.lam_home, 2), round(a.lam_away, 2)],
                          "top_scores": [[s, round(p, 4)] for s, p in a.top_scores[:3]]} if a else None,
            })
        comps.append(entry)
    return {
        "generated": datetime.fromtimestamp(ts, tz=timezone.utc).isoformat(), "age": int(time.time() - ts),
        "stale": bool(err), "errors": errors, "competitions": comps,
        "fair": {"enabled": has_key, "status": fair_status},
        "rules": {"min_stake": RULES.min_stake, "max_payout": RULES.max_payout, "max_events": RULES.max_events},
        "strategy": {"min_edge_market": STRATEGY.min_edge_market, "min_edge_model": STRATEGY.min_edge_model},
    }


MATCH_TTL = 10 * 60
MAX_EXTRA_OFFERS = 20000
_EXTRA_OFFERS: dict = {}   # a meccsoldalról lekért ajánlatok: id → (meccs, piac, kimenetel, sorozat), a check()-hez
_EXTRA_GUARD = threading.Lock()


def _load_match_markets(match_id: str) -> list:
    with tippmix.Session() as s:
        return tippmix.fetch_extras(s, match_id, groups_wanted=tippmix.MATCH_GROUPS, markets=tippmix.MATCH_MARKETS)


def match_markets(match_id: str) -> dict:
    """/api/match-markets: egy meccs saját oldalának gól-, félidős, szöglet- és lappiacai, minden vonallal.

    Az áttekintő csak a 2,5-ös gólvonalat adja; a szelvényépítéshez (pl. „több mint 3,5", „2. félidőben
    legalább 2 gól") a meccsoldal kell. Az ajánlatok ezután a /api/check-ben is ismertek.
    """
    state = build_state()
    hit = next(((m, c) for c in state["competitions"] for m in c["matches"] if m["id"] == match_id), None)
    if not hit:
        raise KeyError(match_id)
    m, c = hit
    outs, _, _ = CACHE.get(("mm", match_id), MATCH_TTL, lambda: _load_match_markets(match_id))
    mk = []
    for g in _group(outs):
        items = [{"id": o.offer_id, "pick": o.pick, "odds": o.odds,
                  "label": labels.short(o.market, o.pick, m["home"], m["away"], o.line),
                  "text": labels.sentence(o.market, o.pick, m["home"], m["away"], o.line)} for o in g["outcomes"]]
        mk.append({"key": g["key"], "name": g["name"], "line": g["line"], "outcomes": items})
    with _EXTRA_GUARD:
        if len(_EXTRA_OFFERS) > MAX_EXTRA_OFFERS:
            _EXTRA_OFFERS.clear()
        for g in mk:
            for o in g["outcomes"]:
                _EXTRA_OFFERS[o["id"]] = (m, g, o, c)
    return {"id": m["id"], "home": m["home"], "away": m["away"], "kickoff": m["kickoff"], "competition": c["key"],
            "markets": mk}


def _index(state: dict) -> dict:
    """Ajánlat id → (meccs, piac, kimenetel, sorozat)."""
    out = {}
    for c in state["competitions"]:
        for m in c["matches"]:
            for mk in m["markets"]:
                for o in mk["outcomes"]:
                    out[o["id"]] = (m, mk, o, c)
    return out


def check(ids: list, stake: int) -> dict:
    state = build_state()
    idx = _index(state)
    legs, missing = [], []
    for i in ids:
        hit = idx.get(i) or _EXTRA_OFFERS.get(i)
        if hit:
            legs.append(hit)
        else:
            missing.append(i)
    res = {"missing": missing, "legs": [], "forbidden": [], "bet_builder": [], "warnings": [],
           "min_stake": RULES.min_stake, "ok": False}
    if missing:
        res["warnings"].append("Néhány tipp már nincs a kínálatban (elkezdődött vagy levették): kivettem.")
    if not legs:
        return res
    for m, mk, o, c in legs:
        res["legs"].append({"id": o["id"], "match": f"{m['home']} – {m['away']}", "kickoff": m["kickoff"],
                            "label": o.get("label"), "text": o.get("text"),
                            "competition": c["name"], "market": mk["name"], "pick": o["pick"], "odds": o["odds"],
                            "prob": o.get("prob"), "ev": o.get("ev"), "fair": o.get("fair"), "match_id": m["id"],
                            "market_key": mk["key"]})
    try:
        with tippmix.Session() as s:
            chk = tippmix.check_slip(s, [(l["id"], l["odds"]) for l in res["legs"]])
    except (tippmix.TippmixError, ValueError) as e:
        res["warnings"].append(f"A TippmixPro ellenőrzése most nem elérhető: {e}")
        return res
    res["forbidden"] = chk["forbidden"]
    res["bet_builder"] = chk["bet_builder"]
    if chk.get("min_stake"):
        res["min_stake"] = int(chk["min_stake"])
    in_builder = {i for bb in chk["bet_builder"] for i in bb["ids"]}
    odds = 1.0
    for l in res["legs"]:
        if l["id"] not in in_builder:
            odds *= l["odds"]
    for bb in chk["bet_builder"]:
        odds *= bb["odds"] or 1.0
    res["odds"] = round(odds, 4)
    res["stake"] = stake
    res["payout"] = int(stake * odds)
    # Valós esély csak független lábakra számolható: a Fogadásépítő lábai korreláltak, a DNB-nél visszajár a tét.
    if not chk["bet_builder"] and all(l["prob"] for l in res["legs"]) and not any(l["market_key"] == "dnb" for l in res["legs"]):
        p = 1.0
        for l in res["legs"]:
            p *= l["prob"]
        res["prob"] = round(p, 4)
        res["ev"] = round(p * odds - 1, 4)
    if len(res["legs"]) > RULES.max_events:
        res["warnings"].append(f"Egy szelvényen legfeljebb {RULES.max_events} esemény lehet.")
    if stake and stake < res["min_stake"]:
        res["warnings"].append(f"A minimális tét {res['min_stake']} Ft.")
    if res["payout"] > RULES.max_payout:
        res["warnings"].append(f"A lehetséges nyeremény a szabályzat szerinti {RULES.max_payout:,} Ft-os plafon fölött van."
                               .replace(",", " "))
    res["ok"] = not res["forbidden"] and not missing and len(res["legs"]) <= RULES.max_events and stake >= res["min_stake"]
    return res


def _bb_odds(session, picks: list) -> float | None:
    """A TippmixPro Fogadásépítő-szorzója egy meccs tippjeire (None, ha nem köthetők)."""
    ids = tuple(p["id"] for p in picks)

    def load():
        chk = tippmix.check_slip(session, [(p["id"], p["odds"]) for p in picks])
        if chk["forbidden"] or not chk["bet_builder"]:
            return 0.0
        return float(chk["bet_builder"][0]["odds"] or 0.0)

    val, _, _ = CACHE.get(("bb",) + ids, TIPPMIX_TTL, load)
    return val or None


def _versions(state: dict, stake: int, target: float | None, notes: list, min_prob: float | None = None) -> list:
    """A három változat (builder.VERSIONS), a TippmixPro Fogadásépítő-szorzóival és végső ellenőrzésével."""
    out = []
    try:
        with tippmix.Session() as s:
            for name, kind, n_default, desc in builder.VERSIONS:
                key = builder.CAL_KEY[kind]
                if key is not None and CAL.available and not CAL.ok(key):
                    notes.append(f"A „{name}” változat ki van kapcsolva: a visszamérés szerint nem elég pontos.")
                    continue
                # Az „any" csak a visszamérés szerint pontos piacokból választhat; visszamérés nélkül bármiből.
                allowed = {k for k in CAL.markets if CAL.ok(k)} if CAL.available else None
                groups = builder.ranked(state, kind, cal=CAL.apply, allowed=allowed)[:builder.CANDIDATES]
                for g in groups:
                    if len(g.picks) > 1:
                        g.odds = _bb_odds(s, g.picks)
                excluded, v, chk = set(), None, None
                for _ in range(4):
                    v = builder.assemble(name, desc, [g for g in groups if g.match_id not in excluded],
                                         n_default, target, min_prob)
                    if not v:
                        break
                    # Végső ellenőrzés a teljes szelvényre: kötéstiltás és a TippmixPro saját csoportszorzói.
                    legs = [p for g in v.groups for p in g.picks]
                    chk = tippmix.check_slip(s, [(p["id"], p["odds"]) for p in legs])
                    if not chk["forbidden"]:
                        break
                    # Tiltott pár: a gyengébb csoportot kivesszük, a helyére a következő legesélyesebb jön.
                    owner = {p["id"]: g for g in v.groups for p in g.picks}
                    bad = [owner[i] for pair in chk["forbidden"] for i in pair if i in owner]
                    excluded.add(min(bad, key=lambda g: g.prob).match_id if bad else v.groups[-1].match_id)
                    v = None
                if not v:
                    priced = [g for g in groups if g.odds and g.odds >= builder.MIN_GROUP_ODDS]
                    if min_prob is not None and (not priced or priced[0].prob < min_prob):
                        top = (f" (a legesélyesebb meccsé is csak {priced[0].prob * 100:.1f}%)".replace(".", ",")
                               if priced else "")
                        notes.append(f"A „{name}” változatból most nincs legalább {min_prob:.0%}-os szelvény{top}.")
                    elif target and min_prob is not None:
                        notes.append(f"A „{name}” változattal a {str(target).replace('.', ',')}-es célszorzó és a "
                                     f"{min_prob:.0%}-os minimum esély együtt nem teljesíthető.")
                    elif target:
                        notes.append(f"A „{name}” változat legfeljebb {builder.MAX_MATCHES} meccsel sem éri el "
                                     f"a {str(target).replace('.', ',')}-es célszorzót.")
                    continue
                bb = {tuple(b["ids"]): b["odds"] for b in chk["bet_builder"]}
                groups_json = []
                for g in v.groups:
                    ids = tuple(p["id"] for p in g.picks)
                    if len(ids) > 1:
                        g.odds = bb.get(ids, g.odds)
                    groups_json.append({
                        "match": g.match, "competition": g.competition, "kickoff": g.kickoff,
                        "comp": g.comp_key, "home": g.home, "away": g.away,
                        "builder": len(ids) > 1, "odds": round(g.odds, 4), "prob": round(g.prob, 4),
                        "picks": [{"id": p["id"], "label": p["label"], "market": p["market_name"], "odds": p["odds"],
                                   "mk": p["market"], "pick": p["pick"], "line": p["line"]}
                                  for p in g.picks]})
                st = max(stake, int(chk.get("min_stake") or RULES.min_stake))
                out.append({"name": v.name, "desc": v.desc, "groups": groups_json, "odds": round(v.odds, 4),
                            "prob": round(v.prob, 4), "ev": round(v.prob * v.odds - 1, 4), "stake": st,
                            "payout": int(st * v.odds)})
    except tippmix.TippmixError as e:
        notes.append(f"A TippmixPro most nem tudta beárazni a szelvényeket: {e}")
    if not out:
        notes.append("Nem találtam szelvényt" + (f" {str(target).replace('.', ',')}-es célszorzóra." if target else "."))
    return out


def resolve_min_prob(mode: str, target: float | None) -> float | None:
    """Az esélyküszöb a választott módból.

    „auto" (alap): célszorzó nélkül legalább 60%, célszorzóval nincs küszöb — a célszorzót
    éri el a lehető legnagyobb eséllyel. „0": nincs alsó határ. 60–95: szigorú küszöb,
    célszorzóval együtt is. Hibás érték: ValueError.
    """
    if mode == "auto":
        return None if target else MIN_SLIP_PROB
    if mode == "0":
        return None
    try:
        p = int(mode) / 100
    except ValueError:
        p = -1.0  # ugyanaz az érthető üzenet, mint a tartományon kívüli számra
    if not MIN_SLIP_PROB <= p <= 0.95:
        raise ValueError(f"A minimum esély {MIN_SLIP_PROB:.0%} és 95% között legyen.")
    return p


def local_day(kickoff_iso: str) -> date:
    return datetime.fromisoformat(kickoff_iso).astimezone(BUDAPEST).date()


def window(state: dict, start: date | None, days: int) -> tuple[dict, date | None, list]:
    """Csak a [start, start+days) budapesti napokra eső meccsek. Kezdőnap nélkül az első meccsnap.

    Visszaad: (szűrt állapot, a ténylegesen használt kezdőnap, az összes meccsnap).
    """
    match_days = sorted({local_day(m["kickoff"]) for c in state["competitions"] for m in c["matches"]})
    if not match_days:
        return state, None, []
    start = start or match_days[0]
    end = start + timedelta(days=days)
    comps = [{**c, "matches": [m for m in c["matches"] if start <= local_day(m["kickoff"]) < end]}
             for c in state["competitions"]]
    return {**state, "competitions": comps}, start, match_days


def best(bankroll: int, target: float | None, stake: int = 1000, start: date | None = None, days: int = 1,
         comps: list | None = None, min_prob: float | None = MIN_SLIP_PROB) -> dict:
    full = build_state()
    if comps:
        full = {**full, "competitions": [c for c in full["competitions"] if c["key"] in comps]}
    state, start, match_days = window(full, start, days)
    out = {"enabled": state["fair"]["enabled"], "picks": [], "singles": [], "combos": [], "low_margin": [],
           "notes": list(state["fair"]["status"]), "versions": [],
           "window": {"start": start.isoformat() if start else None, "days": days,
                      "matches": sum(len(c["matches"]) for c in state["competitions"]),
                      "match_days": [d.isoformat() for d in match_days]}}
    rows = []
    for c in state["competitions"]:
        for m in c["matches"]:
            if m["margin"] is not None:
                out["low_margin"].append({"competition": c["name"], "match": f"{m['home']} – {m['away']}",
                                          "kickoff": m["kickoff"], "margin": m["margin"], "id": m["id"]})
            for mk in m["markets"]:
                for o in mk["outcomes"]:
                    if o.get("value"):
                        rows.append((c, m, mk, o))
    out["low_margin"].sort(key=lambda r: r["margin"])
    out["low_margin"] = out["low_margin"][:15]
    rows.sort(key=lambda r: -r[3]["ev"])
    for c, m, mk, o in rows:
        out["picks"].append({"id": o["id"], "competition": c["name"], "match": f"{m['home']} – {m['away']}",
                             "kickoff": m["kickoff"], "market": mk["name"], "pick": o["pick"], "odds": o["odds"],
                             "label": o.get("text"),
                             "fair": o["fair"], "prob": o["prob"], "ev": o["ev"], "min_odds": o["min_odds"],
                             "source": o["source"]})
    if not out["window"]["matches"]:
        out["notes"].append("A kiválasztott napokon nincs meccs a kiválasztott sorozatokban. Válassz másik napot.")
        return out
    out["versions"] = _versions(state, stake, target, out["notes"], min_prob)
    if target and min_prob is None and any(v["prob"] < MIN_SLIP_PROB for v in out["versions"]):
        out["notes"].append(f"A {str(target).replace('.', ',')}-es célszorzó miatt néhány szelvény esélye "
                            f"{MIN_SLIP_PROB:.0%} alatt van (narancssárga címke). Kisebb célszorzóval nő az esély.")
    if not out["enabled"] or not rows:
        return out
    legs = [slip.Leg(id=o["id"], match_id=m["id"], match=f"{m['home']} – {m['away']}",
                     label=o.get("text") or f"{mk['name']}: {o['pick']}", prob=o["prob"], odds=o["odds"], source=o["source"],
                     min_odds=o["min_odds"])
            for c, m, mk, o in rows if mk["key"] != "dnb"]
    singles, _ = slip.singles(legs, bankroll, RULES, STRATEGY)
    singles, _, _ = slip.cap_total(singles, bankroll, RULES, STRATEGY)
    combos = slip.combos(legs, bankroll, RULES, STRATEGY, target_odds=target, top=5)
    combos, _, _ = slip.cap_total(combos, bankroll, RULES, STRATEGY)

    def bet_json(b):
        return {"legs": [{"id": l.id, "match": l.match, "label": l.label, "odds": l.odds, "prob": l.prob, "ev": l.ev}
                         for l in b.legs],
                "odds": round(b.odds, 4), "prob": round(b.prob, 4), "ev": round(b.ev, 4), "stake": b.stake,
                "payout": b.payout, "note": b.note}

    out["singles"] = [bet_json(b) for b in singles]
    # Minden ajánlott kötést a TippmixPro maga is ellenőriz: tiltott párosítás nem kerülhet ki.
    if combos:
        try:
            with tippmix.Session() as s:
                for b in combos:
                    chk = tippmix.check_slip(s, [(l.id, l.odds) for l in b.legs])
                    if chk["forbidden"] or chk["bet_builder"]:
                        continue
                    out["combos"].append(bet_json(b))
                    if len(out["combos"]) >= 3:
                        break
        except tippmix.TippmixError as e:
            out["notes"].append(f"A kötéseket a TippmixPro most nem tudta ellenőrizni, ezért nem ajánlok kötést: {e}")
    return out


LEAGUES = {c.key: c.espn for c in tippmix.COMPETITIONS}


def _day_events(league: str, day: str) -> list:
    """Egy liga egy napjának ESPN-eredményei: lezárt napnál 24 órás, különben 10 perces gyorsítótárral."""
    key = ("espn-day", league, day)
    hit = CACHE.peek(key)
    done = bool(hit) and all(((ev.get("status") or {}).get("type") or {}).get("completed")
                             for ev in hit[0]) and bool(hit[0])
    try:
        val, _, _ = CACHE.get(key, 24 * 3600 if done else 600, lambda: espn.scoreboard_day(league, day))
        return val
    except espn.EspnError as e:
        logger.info("ESPN-eredmények (%s %s): %s", league, day, e)
        return []


def settle_legs(raw: list) -> dict:
    """/api/settle: a mentett tippek állapota (won/lost/void/pending/unknown) a sorrendjükben."""
    legs, out = [], []
    for r in raw:
        try:
            legs.append(settle.parse_leg(r, LEAGUES))
            out.append(None)
        except ValueError as e:
            out.append({"status": "unknown", "note": str(e)})
    res = iter(settle.settle(legs, _day_events))
    return {"results": [o or next(res) for o in out]}


def team(team_id: str | None, name: str | None, league: str | None) -> dict:
    if not team_id and name and league:
        if league not in {c.espn for c in tippmix.COMPETITIONS}:
            raise ValueError("ismeretlen bajnokság")
        ts, _, _ = CACHE.get(f"teams:{league}", 24 * 3600, lambda: espn.teams(league))
        hit = names.best_team(name, ts, key=lambda t: t["name"]) or names.best_team(name, ts, key=lambda t: t["short"])
        if not hit:
            raise LookupError(f"„{name}” nem található az ESPN-en")
        team_id = hit["id"]
    if not team_id or not team_id.isdigit():
        raise ValueError("hibás csapatazonosító")
    data, _, _ = CACHE.get(f"team:{team_id}", TEAM_TTL, lambda: espn.team_results(team_id))
    return data


# --- munkamenet és korlátok ---------------------------------------------------------------------

def _secret() -> bytes:
    s = os.environ.get("APP_SECRET", "").strip()
    if s:
        return s.encode()
    # A jelszóból származtatva: újraindulás (alvó mód) után is érvényes marad a belépés,
    # jelszócsere után viszont minden régi munkamenet érvénytelen.
    return hashlib.sha256(("tippmix-web|" + os.environ.get("APP_PASSWORD", "")).encode()).digest()


def make_token(now: float | None = None) -> str:
    exp = int((now or time.time()) + SESSION_DAYS * 86400)
    sig = hmac.new(_secret(), f"v1|{exp}".encode(), hashlib.sha256).hexdigest()
    return f"{exp}.{sig}"


def valid_token(tok: str, now: float | None = None) -> bool:
    try:
        exp_s, sig = tok.split(".", 1)
        exp = int(exp_s)
    except (ValueError, AttributeError):
        return False
    good = hmac.new(_secret(), f"v1|{exp}".encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(good, sig) and exp > (now or time.time())


class Limiter:
    def __init__(self, n: int, seconds: float):
        self.n, self.seconds = n, seconds
        self.hits: dict = {}
        self.lock = threading.Lock()

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        with self.lock:
            q = self.hits.setdefault(key, deque())
            while q and now - q[0] > self.seconds:
                q.popleft()
            if len(q) >= self.n:
                return False
            q.append(now)
            if len(self.hits) > 5000:  # elhagyott kulcsok takarítása
                for k in [k for k, v in self.hits.items() if not v]:
                    self.hits.pop(k, None)
            return True


LOGIN_LIMIT = Limiter(8, 15 * 60)
LOGIN_GLOBAL = Limiter(40, 15 * 60)
CHECK_LIMIT = Limiter(40, 60)
REFRESH_LIMIT = Limiter(1, 30)
SETTLE_LIMIT = Limiter(20, 60)
MATCH_LIMIT = Limiter(120, 60)


# --- HTTP ----------------------------------------------------------------------------------------

STATIC_FILES = {"/": "index.html", "/app.js": "app.js", "/app.css": "app.css", "/icon.svg": "icon.svg"}
# Az Emergentben készült Szelvénymodell: a felülete itt van (static/emergent, az emergent-ui/ buildje),
# az adatait az Emergent-szerver adja; a böngésző csak ezt az oldalt látja, a kéréseket mi továbbítjuk.
EMERGENT_URL = os.environ.get("EMERGENT_URL", "https://elo-szorzo-tipp.preview.emergentagent.com").rstrip("/")
EMERGENT_DIR = STATIC / "emergent"
EMERGENT_TIMEOUT = 150  # az előnézet alvásból 1–2 perc alatt ébred
EMERGENT_API = re.compile(r"^/emergent/api/(state|slips|check|accuracy|log|health|team/[A-Za-z0-9._-]{1,40})$")
EMERGENT_ASSET = re.compile(r"^/emergent/assets/[A-Za-z0-9._-]{1,80}$")
EMERGENT_LIMIT = Limiter(120, 60)
CSP_EMERGENT = ("default-src 'self'; img-src 'self' data: https:; style-src 'self' 'unsafe-inline' "
                "https://fonts.googleapis.com; font-src https://fonts.gstatic.com; script-src 'self'; "
                "connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
# Ébren tartás: az Emergent-előnézet használat nélkül elalszik, és csak a tulajdonos ébresztheti fel. Amíg
# ébren van, ennyi másodpercenként rákérdezünk, hogy ne aludjon el (0 = kikapcsolva). Ha háromszor
# egymás után alszik, abbahagyjuk (úgysem ébreszti fel), és a Railway is elaltathatja ezt a szervert;
# a következő sikeres kérés újraindítja.
KEEPALIVE_SECONDS = int(os.environ.get("EMERGENT_KEEPALIVE_SECONDS", "240"))
KEEPALIVE_MAX_FAILS = 3


def _emergent_alive() -> bool:
    req = urllib.request.Request(f"{EMERGENT_URL}/api/health", headers={"User-Agent": "aximbra-tippmix-keepalive"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return "json" in r.headers.get("Content-Type", "") and bool(json.loads(r.read(64 * 1024)).get("ok"))
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        return False


class EmergentKeepAlive:
    """Egyetlen háttérszál, ami amíg az Emergent ébren van, rendszeresen rákérdez."""

    def __init__(self):
        self._lock = threading.Lock()
        self._running = False

    def kick(self):
        if KEEPALIVE_SECONDS <= 0:
            return
        with self._lock:
            if self._running:
                return
            self._running = True
        threading.Thread(target=self._loop, daemon=True, name="emergent-keepalive").start()

    def _loop(self):
        fails = 0
        try:
            while fails < KEEPALIVE_MAX_FAILS:
                time.sleep(KEEPALIVE_SECONDS)
                if _emergent_alive():
                    fails = 0
                else:
                    fails += 1
            logger.info("az Emergent-szerver alszik: az ébren tartás szünetel a következő sikeres kérésig")
        except Exception:  # noqa: BLE001 — háttérszál: csak napló, a következő kérés újraindítja
            logger.exception("ébren tartás hiba")
        finally:
            with self._lock:
                self._running = False


KEEPALIVE = EmergentKeepAlive()

# Az alvó előnézetet csak a tulajdonos ébresztheti fel, bejelentkezve az Emergentbe: ez az ő ébresztő-oldala.
EMERGENT_WAKE = ("https://app.emergent.sh/loading-preview?host="
                 + urlparse(EMERGENT_URL).netloc + "&wake=1")
CSP = ("default-src 'self'; img-src 'self' https://a.espncdn.com data:; style-src 'self'; script-src 'self'; "
       "connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")


class Handler(BaseHTTPRequestHandler):
    server_version = "tippmix-web"
    sys_version = ""

    def log_message(self, fmt, *args):
        logger.info("%s %s", self.address_string(), fmt % args)

    def address_string(self):
        fwd = self.headers.get("X-Forwarded-For", "")
        return fwd.split(",")[0].strip() if fwd else self.client_address[0]

    # válaszok
    def _headers(self, status, ctype, length, extra=None):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(length))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Frame-Options", "DENY")
        extra = dict(extra or {})
        self.send_header("Content-Security-Policy", extra.pop("Content-Security-Policy", CSP))
        for k, v in extra.items():
            self.send_header(k, v)
        self.end_headers()

    def _json(self, status, obj, extra=None):
        body = json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        headers = {"Cache-Control": "no-store", **(extra or {})}
        if len(body) > 1024 and "gzip" in self.headers.get("Accept-Encoding", ""):
            body = gzip.compress(body, 6)
            headers["Content-Encoding"] = "gzip"
            headers["Vary"] = "Accept-Encoding"
        self._headers(status, "application/json; charset=utf-8", len(body), headers)
        if self.command != "HEAD":
            self.wfile.write(body)

    def _err(self, status, msg):
        self._json(status, {"error": msg})

    def _authed(self) -> bool:
        if not os.environ.get("APP_PASSWORD"):
            return True  # nyitott mód: nincs jelszó beállítva
        for part in self.headers.get("Cookie", "").split(";"):
            k, _, v = part.strip().partition("=")
            if k == "sess" and valid_token(v):
                return True
        return False

    def _body(self):
        try:
            n = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            n = -1
        if n < 0 or n > MAX_BODY:
            raise ValueError("túl nagy kérés")
        raw = self.rfile.read(n) if n else b"{}"
        data = json.loads(raw.decode("utf-8") or "{}")
        if not isinstance(data, dict):
            raise ValueError("JSON objektum kell")
        return data

    def _cookie(self, value, max_age):
        secure = "; Secure" if self.headers.get("X-Forwarded-Proto", "") == "https" else ""
        return f"sess={value}; Path=/; HttpOnly; SameSite=Strict; Max-Age={max_age}{secure}"

    # útvonalak
    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        url = urlparse(self.path)
        if url.path == "/health":
            return self._json(200, {"ok": True})
        if url.path in STATIC_FILES:
            return self._static(STATIC_FILES[url.path])
        if url.path.startswith("/emergent"):
            return self._emergent(url)
        if not url.path.startswith("/api/"):
            return self._err(404, "nincs ilyen oldal")
        if url.path == "/api/me":
            return self._json(200, {"authed": self._authed(), "open": not os.environ.get("APP_PASSWORD")})
        if not self._authed():
            return self._err(401, "Jelentkezz be.")
        q = {k: v[0] for k, v in parse_qs(url.query).items()}
        try:
            if url.path == "/api/state":
                # Jelszó nélkül bárki nyomhat frissítést: 30 másodpercenként legfeljebb egy éri el a TippmixPro-t.
                if q.get("refresh") == "1" and REFRESH_LIMIT.allow("all"):
                    CACHE.drop("tippmix")
                return self._json(200, build_state())
            if url.path == "/api/match-markets":
                mid = q.get("id", "")
                if not (mid.isdigit() and len(mid) < 30):
                    return self._err(400, "Hibás meccsazonosító.")
                if not MATCH_LIMIT.allow(self.address_string()):
                    return self._err(429, "Lassíts egy kicsit: percenként legfeljebb 120 meccsoldal.")
                try:
                    return self._json(200, match_markets(mid))
                except KeyError:
                    return self._err(404, "Ez a meccs most nincs a kínálatban.")
            if url.path == "/api/best":
                bankroll = int(q.get("keret", "50000"))
                if not 1000 <= bankroll <= 100_000_000:
                    return self._err(400, "A keret 1 000 és 100 000 000 Ft között legyen.")
                target = float(q["cel"].replace(",", ".")) if q.get("cel") else None
                if target is not None and not 1.01 < target <= 1000:
                    return self._err(400, "A célszorzó 1,01 és 1000 között legyen.")
                stake = int(q.get("tet", "1000"))
                if not 0 < stake <= 10_000_000:
                    return self._err(400, "Hibás tét.")
                days = int(q.get("napok", "1"))
                if not 1 <= days <= MAX_DAYS:
                    return self._err(400, f"A napok száma 1 és {MAX_DAYS} között legyen.")
                try:
                    start = date.fromisoformat(q["kezd"]) if q.get("kezd") else None
                except ValueError:
                    return self._err(400, "Hibás dátum (ÉÉÉÉ-HH-NN formában kell).")
                comps = [k for k in q.get("sorozat", "").split(",") if k]
                if any(k not in tippmix.BY_KEY for k in comps):
                    return self._err(400, "Ismeretlen sorozat.")
                min_prob = resolve_min_prob(q.get("esely", "auto"), target)
                return self._json(200, best(bankroll, target, stake, start, days, comps or None, min_prob))
            if url.path == "/api/accuracy":
                return self._json(200, CAL.data or {"markets": {}})
            if url.path == "/api/team":
                return self._json(200, team(q.get("id"), q.get("name"), q.get("league")))
        except (ValueError, LookupError) as e:
            return self._err(400, str(e))
        except tippmix.TippmixError as e:
            return self._err(502, f"TippmixPro: {e}")
        except espn.EspnError as e:
            return self._err(502, f"Eredmények: {e}")
        except Exception:  # noqa: BLE001 — a részletek a naplóba mennek, a böngészőbe nem
            logger.exception("váratlan hiba: %s", url.path)
            return self._err(500, "Váratlan hiba történt.")
        return self._err(404, "nincs ilyen végpont")

    def do_POST(self):
        url = urlparse(self.path)
        # Csak azonos eredetű kérés: a SameSite=Strict mellé második védvonal a CSRF ellen.
        origin = self.headers.get("Origin")
        if origin and urlparse(origin).netloc != self.headers.get("Host"):
            return self._err(403, "Idegen eredetű kérés.")
        try:
            body = self._body()
        except (ValueError, UnicodeDecodeError) as e:
            return self._err(400, f"Hibás kérés: {e}")
        if url.path == "/api/login":
            ip = self.address_string()
            if not LOGIN_LIMIT.allow(ip) or not LOGIN_GLOBAL.allow("all"):
                return self._err(429, "Túl sok próbálkozás. Próbáld újra 15 perc múlva.")
            pw = str(body.get("password", ""))
            if not hmac.compare_digest(pw.encode(), os.environ.get("APP_PASSWORD", "").encode()):
                return self._err(401, "Hibás jelszó.")
            return self._json(200, {"ok": True}, {"Set-Cookie": self._cookie(make_token(), SESSION_DAYS * 86400)})
        if url.path.startswith("/emergent/api/"):
            return self._emergent(url, body)
        if url.path == "/api/logout":
            return self._json(200, {"ok": True}, {"Set-Cookie": self._cookie("", 0)})
        if not self._authed():
            return self._err(401, "Jelentkezz be.")
        if url.path == "/api/check":
            if not CHECK_LIMIT.allow(self.address_string()):
                return self._err(429, "Lassíts egy kicsit: percenként legfeljebb 40 ellenőrzés.")
            ids = body.get("ids")
            if not isinstance(ids, list) or not all(isinstance(i, str) and i.isdigit() and len(i) < 30 for i in ids):
                return self._err(400, "Hibás tipplista.")
            ids = list(dict.fromkeys(ids))[:MAX_SLIP + 5]
            try:
                stake = int(body.get("stake") or 0)
            except (TypeError, ValueError):
                return self._err(400, "A tét egész szám legyen.")
            if not 0 <= stake <= 10_000_000:
                return self._err(400, "Hibás tét.")
            try:
                return self._json(200, check(ids, stake))
            except tippmix.TippmixError as e:
                return self._err(502, f"TippmixPro: {e}")
            except Exception:  # noqa: BLE001
                logger.exception("váratlan hiba: check")
                return self._err(500, "Váratlan hiba történt.")
        if url.path == "/api/settle":
            if not SETTLE_LIMIT.allow(self.address_string()):
                return self._err(429, "Lassíts egy kicsit: percenként legfeljebb 20 kiértékelés.")
            legs = body.get("legs")
            if not isinstance(legs, list) or len(legs) > MAX_SETTLE:
                return self._err(400, f"Hibás tipplista (legfeljebb {MAX_SETTLE} tipp egyszerre).")
            try:
                return self._json(200, settle_legs(legs))
            except Exception:  # noqa: BLE001
                logger.exception("váratlan hiba: settle")
                return self._err(500, "Váratlan hiba történt.")
        return self._err(404, "nincs ilyen végpont")

    def _emergent(self, url, body=None):
        """Az Emergent-féle Szelvénymodell: felület a static/emergent-ből, /emergent/api/* továbbítva."""
        if url.path in ("/emergent", "/emergent/"):
            return self._static("emergent/index.html", csp=CSP_EMERGENT)
        if EMERGENT_ASSET.match(url.path):
            # a fájlnév a tartalom hash-e: nyugodtan gyorsítótárazható
            return self._static("emergent/" + url.path[len("/emergent/"):], csp=CSP_EMERGENT,
                                cache="public, max-age=31536000, immutable")
        m = EMERGENT_API.match(url.path)
        if not m:
            return self._err(404, "nincs ilyen oldal")
        if not self._authed():
            return self._json(401, {"detail": "Jelentkezz be."})
        if not EMERGENT_LIMIT.allow(self.address_string()):
            return self._json(429, {"detail": "Lassíts egy kicsit, percenként legfeljebb 120 kérés."})
        if body is not None and m.group(1) != "check":
            return self._json(405, {"detail": "Ez a végpont csak olvasható."})
        target = f"{EMERGENT_URL}/api/{m.group(1)}" + (f"?{url.query}" if url.query else "")
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(target, data=data, method="POST" if data is not None else "GET",
                                     headers={"Content-Type": "application/json", "Accept": "application/json",
                                              "User-Agent": "aximbra-tippmix"})
        try:
            with urllib.request.urlopen(req, timeout=EMERGENT_TIMEOUT) as r:
                status, ctype, raw = r.status, r.headers.get("Content-Type", ""), r.read(8 * 1024 * 1024)
        except urllib.error.HTTPError as e:
            status, ctype, raw = e.code, e.headers.get("Content-Type", ""), e.read(64 * 1024)
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            logger.info("Emergent-szerver nem érhető el: %s", e)
            return self._json(502, {"detail": "Az Emergent-szerver most nem érhető el. Próbáld újra 1–2 perc múlva."})
        if "json" not in ctype:
            # alvó előnézetnél HTML vagy szöveg jön: a felület ébresztő gombot mutat (wake_url), és vár
            return self._json(503, {"detail": "Az Emergent-szerver alszik.", "wake_url": EMERGENT_WAKE})
        if status < 500:
            KEEPALIVE.kick()  # ébren van: tartsuk is ébren
        headers = {"Cache-Control": "no-store"}
        if "gzip" in self.headers.get("Accept-Encoding", "") and len(raw) > 1024:
            raw = gzip.compress(raw, 6)
            headers["Content-Encoding"] = "gzip"
            headers["Vary"] = "Accept-Encoding"
        self._headers(status, "application/json; charset=utf-8", len(raw), headers)
        self.wfile.write(raw)

    def _static(self, name, csp=None, cache="no-cache"):
        path = STATIC / name
        try:
            data = path.read_bytes()
        except OSError:
            return self._err(404, "nincs ilyen fájl")
        ctype = mimetypes.guess_type(name)[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype in ("application/javascript", "image/svg+xml"):
            ctype += "; charset=utf-8"
        headers = {"Cache-Control": cache}
        if csp:
            headers["Content-Security-Policy"] = csp
        if "gzip" in self.headers.get("Accept-Encoding", "") and len(data) > 1024:
            data = gzip.compress(data, 6)
            headers["Content-Encoding"] = "gzip"
            headers["Vary"] = "Accept-Encoding"
        self._headers(200, ctype, len(data), headers)
        if self.command != "HEAD":
            self.wfile.write(data)


def main():
    if not os.environ.get("APP_PASSWORD"):
        logger.warning("Az APP_PASSWORD nincs beállítva: az oldal jelszó nélkül, bárki számára nyitott.")
    port = int(os.environ.get("PORT", "8080"))
    srv = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    srv.daemon_threads = True
    logger.info("fut: http://0.0.0.0:%d", port)
    KEEPALIVE.kick()  # ha az Emergent épp ébren van, maradjon is
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()


if __name__ == "__main__":
    main()
