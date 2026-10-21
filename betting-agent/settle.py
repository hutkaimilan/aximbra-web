"""Szelvénynapló: a mentett tippek kiértékelése a lejátszott meccsek ESPN-eredményéből.

A TippmixPro a rendes játékidőre fogad: a végeredmény, az 1. félidő (a gólok percéből),
a szögletek (wonCorners) és a lapok (sárga + piros események) mind az ESPN napi
eredménylistájából jönnek, kulcs nélkül. A meccset a kezdési idő és a két csapatnév
párosítja, mint mindenhol máshol (names.match_events).

Ahol az ESPN-adat hiányos vagy önellentmondó (pl. a gólok listája nem adja ki a
végeredményt), a tipp „ismeretlen" marad — inkább nem értékelünk, mint rosszul.
"""
import re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import builder
import names

ESPN_TZ = ZoneInfo("America/New_York")  # az ESPN napi listája a keleti parti nap szerint
VOID_STATUS = ("POSTPONED", "CANCELED", "CANCELLED", "ABANDONED", "FORFEIT", "SUSPENDED")
SETTLE_AFTER = timedelta(hours=2, minutes=15)  # ennyivel a kezdés után már vége a meccsnek
GIVE_UP_AFTER = timedelta(days=3)               # ha addig sincs eredmény: ismeretlen

_MINUTE = re.compile(r"^\s*(\d+)")


def espn_days(kickoff: datetime) -> list[str]:
    """Az ESPN-napok, amelyeken a meccs szerepelhet (keleti idő szerint, és biztonságból az UTC-nap is)."""
    days = {kickoff.astimezone(ESPN_TZ).strftime("%Y%m%d"), kickoff.astimezone(timezone.utc).strftime("%Y%m%d")}
    return sorted(days)


def _int(x):
    try:
        return int(float(x))
    except (TypeError, ValueError):
        return None


def event_result(ev: dict) -> dict | None:
    """Egy ESPN-esemény → {kickoff, home, away, state, status, ft, ht, corners, cards}; hibás rekordnál None."""
    try:
        comp = ev["competitions"][0]
        cs = {c.get("homeAway"): c for c in comp["competitors"]}
        home, away = cs["home"], cs["away"]
        st = comp["status"]["type"]
        kickoff = names.parse_time(ev["date"])
    except (KeyError, IndexError, TypeError, ValueError):
        return None
    hid = str((home.get("team") or {}).get("id", ""))
    aid = str((away.get("team") or {}).get("id", ""))
    out = {"kickoff": kickoff, "home": (home.get("team") or {}).get("displayName", ""),
           "away": (away.get("team") or {}).get("displayName", ""),
           "state": st.get("state"), "status": st.get("name") or "", "completed": bool(st.get("completed")),
           "ft": None, "ht": None, "corners": None, "cards": None}
    hs, as_ = _int((home.get("score") or {}).get("value") if isinstance(home.get("score"), dict) else home.get("score")), \
        _int((away.get("score") or {}).get("value") if isinstance(away.get("score"), dict) else away.get("score"))
    if hs is not None and as_ is not None:
        out["ft"] = (hs, as_)

    details = comp.get("details")
    if isinstance(details, list):
        goals = {hid: [0, 0], aid: [0, 0]}  # csapat → [1. félidő, összes]
        cards = 0
        ok = True
        for d in details:
            if d.get("yellowCard") or d.get("redCard"):
                cards += 1
            if not d.get("scoringPlay"):
                continue
            team = str((d.get("team") or {}).get("id", ""))
            m = _MINUTE.match(str((d.get("clock") or {}).get("displayValue", "")))
            if team not in goals or not m:
                ok = False
                continue
            goals[team][1] += 1
            if int(m.group(1)) <= 45:  # a „45'+2'" is az 1. félidő
                goals[team][0] += 1
        # A félidőt csak akkor fogadjuk el, ha a gólok listája pontosan kiadja a végeredményt
        # (öngólnál vagy hiányos listánál az ESPN csapat-hozzárendelése nem biztos).
        if ok and out["ft"] and (goals[hid][1], goals[aid][1]) == out["ft"]:
            out["ht"] = (goals[hid][0], goals[aid][0])
        if out["completed"]:
            out["cards"] = cards

    def stat(c, name):
        for s in c.get("statistics") or []:
            if s.get("name") == name:
                return _int(s.get("displayValue"))
        return None
    hc, ac = stat(home, "wonCorners"), stat(away, "wonCorners")
    if out["completed"] and hc is not None and ac is not None:
        out["corners"] = hc + ac
    return out


def evaluate(leg: dict, res: dict | None, now: datetime) -> dict:
    """Egy tipp állapota: won | lost | void | pending | unknown, és az eredmény röviden."""
    kickoff = leg["kickoff"]
    if res is None:
        if now < kickoff + SETTLE_AFTER:
            return {"status": "pending"}
        return {"status": "unknown" if now > kickoff + GIVE_UP_AFTER else "pending",
                "note": "nincs ESPN-eredmény"}
    info = {"score": "–".join(map(str, res["ft"])) if res["ft"] else None,
            "ht": "–".join(map(str, res["ht"])) if res["ht"] else None,
            "corners": res["corners"], "cards": res["cards"]}
    if any(s in res["status"].upper() for s in VOID_STATUS):
        return {"status": "void", "note": "elmaradt / félbeszakadt", **info}
    if not res["completed"]:
        return {"status": "pending", **info}
    if res["status"] != "STATUS_FULL_TIME":
        # hosszabbítás / tizenegyesek: a rendes játékidő eredménye a végeredményből nem olvasható ki
        return {"status": "unknown", "note": "hosszabbítás", **info}

    mk, pick, line = leg["mk"], leg["pick"], leg.get("line")
    if mk in ("corners", "cards"):
        total = res[mk]
        if total is None or line is None:
            return {"status": "unknown", **info}
        won = total > line if pick == "Több" else total < line
        return {"status": "won" if won else "lost", **info}
    if mk in builder.HT_MARKETS:
        score = res["ht"]
    else:
        score = res["ft"]
    if score is None:
        return {"status": "unknown", **info}
    i, j = score
    if mk == "dnb":
        if i == j:
            return {"status": "void", "note": "döntetlen: visszajár a tét", **info}
        return {"status": "won" if (i > j) == (pick == "1") else "lost", **info}
    try:
        cond = builder._cond(mk, pick, line)
    except (KeyError, ValueError):
        return {"status": "unknown", **info}
    return {"status": "won" if cond(i, j) else "lost", **info}


def parse_leg(raw: dict, leagues: dict) -> dict:
    """A kliens tippje → belső alak; hibánál ValueError (magyar üzenettel)."""
    if not isinstance(raw, dict):
        raise ValueError("hibás tipp")
    comp = raw.get("comp")
    if comp not in leagues:
        raise ValueError("ismeretlen sorozat")
    home, away = str(raw.get("home") or "")[:80], str(raw.get("away") or "")[:80]
    if not home or not away:
        raise ValueError("hiányzó csapatnév")
    try:
        kickoff = names.parse_time(str(raw.get("kickoff")))
    except ValueError:
        raise ValueError("hibás kezdési idő") from None
    if kickoff.tzinfo is None:
        raise ValueError("hibás kezdési idő")
    mk, pick = str(raw.get("mk") or ""), str(raw.get("pick") or "")
    line = raw.get("line")
    if line is not None and not isinstance(line, (int, float)):
        raise ValueError("hibás vonal")
    return {"league": leagues[comp], "home": home, "away": away, "kickoff": kickoff, "mk": mk, "pick": pick,
            "line": float(line) if line is not None else None}


def settle(legs: list[dict], day_events, now: datetime | None = None) -> list[dict]:
    """legs: parse_leg kimenetei. day_events(liga, nap) → nyers ESPN-események (gyorsítótárból).

    Csak a már lefutott meccsekhez kér eredményt; egy liga egy napját egyszer. Egy meccsre tett
    több tipp (Fogadásépítő) ugyanazt az eredményt kapja.
    """
    now = now or datetime.now(timezone.utc)
    matches: dict = {}  # (liga, kezdés, hazai, vendég) → a meccs tippjeinek indexei
    for k, leg in enumerate(legs):
        if now >= leg["kickoff"] + SETTLE_AFTER:
            matches.setdefault((leg["league"], leg["kickoff"], leg["home"], leg["away"]), []).append(k)
    found: dict = {}
    for league in {m[0] for m in matches}:
        keys = [m for m in matches if m[0] == league]
        days = sorted({d for m in keys for d in espn_days(m[1])})
        rs = [r for day in days for r in (event_result(ev) for ev in day_events(league, day)) if r]
        idx = names.match_events(keys, rs, lambda m: (m[1], m[2], m[3]),
                                 lambda r: (r["kickoff"], r["home"], r["away"]), max_minutes=30)
        for i, j in idx.items():
            found[keys[i]] = rs[j]
    out = [None] * len(legs)
    for m, ks in matches.items():
        for k in ks:
            out[k] = evaluate(legs[k], found.get(m), now)
    return [o or evaluate(leg, None, now) for o, leg in zip(out, legs)]
