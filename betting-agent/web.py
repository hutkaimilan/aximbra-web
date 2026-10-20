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
import markets
import names
import odds_api
import builder
import insight
import labels
import slip
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
SESSION_DAYS = 30
MAX_BODY = 64 * 1024
MAX_SLIP = 20
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

    def drop(self, key):
        with self._guard:
            self._data.pop(key, None)


CACHE = Cache()
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
    base = {v[0]: v[1] for v in tippmix.MARKETS.values()}[market]
    return f"{base} {str(line).replace('.', ',')}" if line is not None else base


def build_state() -> dict:
    tm, ts, err = CACHE.get("tippmix", TIPPMIX_TTL, _load_tippmix)
    has_key = bool(os.environ.get("ODDS_API_KEY", "").strip())
    fair_status, errors = [], []
    if err:
        errors.append(f"A TippmixPro-adat nem frissült ({err}); a legutóbbi sikeres lekérdezést látod.")
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
            mk = []
            for g in _group(m.outcomes):
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
        if i in idx:
            legs.append(idx[i])
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
                groups = builder.ranked(state, kind)[:builder.CANDIDATES]
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
                        "builder": len(ids) > 1, "odds": round(g.odds, 4), "prob": round(g.prob, 4),
                        "picks": [{"id": p["id"], "label": p["label"], "market": p["market_name"], "odds": p["odds"]}
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


# --- HTTP ----------------------------------------------------------------------------------------

STATIC_FILES = {"/": "index.html", "/app.js": "app.js", "/app.css": "app.css", "/icon.svg": "icon.svg"}
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
        self.send_header("Content-Security-Policy", CSP)
        for k, v in (extra or {}).items():
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
        return self._err(404, "nincs ilyen végpont")

    def _static(self, name):
        path = STATIC / name
        try:
            data = path.read_bytes()
        except OSError:
            return self._err(404, "nincs ilyen fájl")
        ctype = mimetypes.guess_type(name)[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype in ("application/javascript", "image/svg+xml"):
            ctype += "; charset=utf-8"
        headers = {"Cache-Control": "no-cache"}
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
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()


if __name__ == "__main__":
    main()
