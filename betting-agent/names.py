"""Csapatnevek egyeztetése a TippmixPro, az ESPN és a The Odds API között.

Ugyanaz a csapat háromféleképpen szerepel („Bayern München" / „Bayern
Munich", „E. Frankfurt" / „Eintracht Frankfurt", „FTC" / „Ferencvaros").
Név alapján önmagában ez kockázatos, ezért mérkőzést mindig a kezdési időpont
ÉS mindkét csapatnév együtt párosít: ugyanabban a bajnokságban ugyanabban a
percben két meccsnek a csapatai sosem hasonlítanak egymásra.
"""
import re
import unicodedata
from datetime import datetime
from difflib import SequenceMatcher

# Csak jelentés nélküli töltelék: a „Real", „Sporting", „United" megkülönböztet, azokat nem dobjuk el.
STOP = {"fc", "cf", "sc", "ac", "afc", "cd", "ud", "sd", "rc", "rcd", "sv", "vfb", "vfl", "tsg", "fsv",
        "club", "de", "la", "the", "and", "calcio", "1", "fk", "sk", "if", "bk", "kv", "kaa", "krc", "as",
        "ssc", "us", "ogc", "losc", "csd", "ca", "cp", "sad", "fsc", "spvgg"}

# A TippmixPro magyarított / rövidített nevei, amelyeket a betűhasonlóság nem talál meg.
ALIASES = {
    "bayern munchen": "bayern munich",
    "fc bruges": "club brugge",
    "bruges": "club brugge",
    "koln": "cologne",
    "ftc": "ferencvaros",
    "manchester utd": "manchester united",
    "man utd": "manchester united",
    "nottingham": "nottingham forest",
    "wolverhampton": "wolverhampton wanderers",
    "ath bilbao": "athletic club",
    "athletic bilbao": "athletic club",
    "atl madrid": "atletico madrid",
    "r santander": "racing santander",
    "r sociedad": "real sociedad",
    "inter": "internazionale",
    "psg": "paris saint germain",
    "paris sg": "paris saint germain",
    "e frankfurt": "eintracht frankfurt",
    "monchengladbach": "borussia monchengladbach",
    "gladbach": "borussia monchengladbach",
    "m gladbach": "borussia monchengladbach",   # football-data: „M'gladbach"
    "sp lisbon": "sporting cp",                 # football-data: „Sp Lisbon"
    "sp lisszabon": "sporting cp",
    "sporting": "sporting cp",
    "sp braga": "braga",
    "guimaraes": "vitoria guimaraes",
    "rb salzburg": "red bull salzburg",
    "crvena zvezda": "red star belgrade",
    "pao": "panathinaikos",
    "olympiakos": "olympiacos",
    "fenerbahce": "fenerbahce",
    "ru saint gilloise": "union st gilloise",
    "st pauli": "st pauli",
    "hamburg": "hamburg sv",
}


def norm(name: str) -> str:
    s = unicodedata.normalize("NFKD", name or "")
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    s = s.replace("ø", "o").replace("ß", "ss").replace("&", " ")
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    s = " ".join(s.split())
    core = " ".join(t for t in s.split() if t not in STOP) or s
    # Az alias a töltelékszavak nélküli alakra is illeszkedjen („1. FC Köln" → „koln").
    s = ALIASES.get(s) or ALIASES.get(core) or core
    return " ".join(t for t in s.split() if t not in STOP) or s


def similarity(a: str, b: str) -> float:
    """0–1: a betűsor-hasonlóság és a szavak (rövidítéssel is) egyezésének a jobbika."""
    na, nb = norm(a), norm(b)
    if not na or not nb:
        return 0.0
    if na == nb:
        return 1.0
    seq = SequenceMatcher(None, na, nb).ratio()
    ta, tb = na.split(), nb.split()
    short, long_ = (ta, tb) if len(ta) <= len(tb) else (tb, ta)
    hits = 0
    for t in short:
        # „e" ↔ „eintracht", „man" ↔ „manchester": az előtag is egyezésnek számít
        if any(u == t or (len(t) >= 1 and u.startswith(t)) or (len(u) >= 3 and t.startswith(u)) for u in long_):
            hits += 1
    tok = hits / len(short)
    # Ha csak egy rövid szó egyezik egy hosszú névből, az kevés: a hosszarány tompítja.
    tok *= 0.75 + 0.25 * (len(short) / len(long_))
    return max(seq, tok)


def pair_score(home_a: str, away_a: str, home_b: str, away_b: str) -> float:
    return min(similarity(home_a, home_b), similarity(away_a, away_b))


def match_events(items_a, items_b, key_a, key_b, max_minutes: int = 20, min_score: float = 0.5) -> dict:
    """Párosítás: a → b index. key_*(x) -> (kezdés datetime, hazai, vendég).

    Mohó, a legjobb pontszámú párokkal kezdve, így egy b-elem legfeljebb egyszer
    kel el. Időben max_minutes-on túli pár nem jöhet szóba.
    """
    cands = []
    kb = [key_b(b) for b in items_b]
    for i, a in enumerate(items_a):
        ta, ha, aa = key_a(a)
        for j, (tb, hb, ab) in enumerate(kb):
            if abs((ta - tb).total_seconds()) > max_minutes * 60:
                continue
            s = pair_score(ha, aa, hb, ab)
            if s >= min_score:
                cands.append((s, i, j))
    cands.sort(reverse=True)
    out, used_b = {}, set()
    for s, i, j in cands:
        if i in out or j in used_b:
            continue
        out[i] = j
        used_b.add(j)
    return out


def best_team(name: str, teams: list, key=lambda t: t, min_score: float = 0.6):
    """A névhez leginkább hasonló csapat a listából, vagy None."""
    best, best_s = None, 0.0
    for t in teams:
        s = similarity(name, key(t))
        if s > best_s:
            best, best_s = t, s
    return best if best_s >= min_score else None


def parse_time(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))
