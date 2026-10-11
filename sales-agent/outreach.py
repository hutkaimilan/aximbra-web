"""LinkedIn-megkeresés: a profilt te másolod be, a szöveget az agent írja, elküldeni te küldöd el.

Miért kézi bemásolás, és nem összekötés: a LinkedIn nem ad hozzáférést más
emberek profiljának olvasásához. Önkiszolgálóan a saját profil, a saját e-mail
cím és a posztolás kérhető; a profilolvasás partnerprogramhoz kötött. A
lekaparás pedig a felhasználási feltételekbe ütközik (fiókzárolás), és mivel
nem az érintettől gyűjtené az adatot, a GDPR 14. cikke szerint értesítési
kötelezettséggel is jár. Amit viszont a böngésződben jogosultan elolvasol, azt
be is másolhatod: ugyanaz az információ, csak nem automatizáltan szerezve.

Két dolgot ad vissza, és az első a fontosabb: egy ítéletet arról, hogy érdemes-e
egyáltalán írni, és csak utána a szöveget. A félresikerült megkeresések nem
attól lettek rosszak, hogy kevés volt bennük a személyre szabás, hanem attól,
hogy olyannak mentek, aki maga építi ugyanezt.

Amit a modell állít, azt a kód ellenőrzi: a hivatkozott mondatnak tényleg a
bemásolt szövegben kell lennie (ugyanaz az egyezésvizsgálat, mint a leveleknél),
és ár nem kerülhet bele. Ami nem áll, az a panelen figyelmeztetésként látszik —
nem némán javítjuk, mert a szöveget te küldöd el, és neked kell látnod, mi
gyanús benne.
"""
from __future__ import annotations

import json
import logging
import re
from itertools import zip_longest

import llm
import playbook
import verify
import websearch

logger = logging.getLogger(__name__)

VERDICTS = ("ir", "ne_irj")
MIN_PROFILE = 80
MAX_PROFILE = 12000
MIN_MESSAGE = 80

# ---- kereső ------------------------------------------------------------------
# A keresést NEM a LinkedInen futtatjuk: egy keresőmotor indexét kérdezzük
# (Tavily), és csak azt használjuk, amit az már nyilvánosan indexelt. A
# linkedin.com-ot magát soha nem töltjük le — az automatizált lekérés ütközne a
# felhasználási feltételekkel, és bejelentkezés nélkül úgyis belépőfalat adna.
# Ezért a találat annyit tud, amennyit a kereső tud róla: egy fejléc és egy
# részlet, ami lehet hónapokkal ezelőtti. A lista tehát kiindulópont, nem
# adatlap — a valódi szöveget a profil bemásolása után a draft() ellenőrzi.
PROFILE_RE = re.compile(r"^https?://([a-z0-9-]+\.)*linkedin\.com/in/[^/?#]+", re.I)
JUDGEMENTS = ("ir", "ne_irj", "keves_adat")
MAX_HITS = 24
SEEN_KEY = "linkedin_seen"
SEEN_KEEP = 600
# A keresés pénzbe kerül: a Tavily ingyenes szintje havi 1000 lekérdezés. Egy
# kör ezért legfeljebb MAX_COMBOS × QUERIES_PER_COMBO keresést költ, akárhány
# szűrőt pipálnak ki — a szűrők a mintavétel szélességét állítják, nem a
# számlát. A panel előre kiírja, hány keresés lesz belőle.
MAX_COMBOS = 6
QUERIES_PER_COMBO = 2
MAX_ROLES = 6

# Szerepkörök, akikhez a legtöbb agentünknek van köze. A panelen ezek a
# pipálható sorok; a lista szándékosan rövid, mert minden bepipált szerepkör
# szorozza a kombinációkat.
ROLES = (
    "ügyfélszolgálati vezető", "üzemeltetési vezető", "logisztikai vezető",
    "pénzügyi vezető", "IT-vezető", "HR-vezető", "ügyvezető",
)


def _profile_key(url: str) -> str:
    """A profil azonosítója a slug: ugyanaz az ember több alakban is bejöhet
    (nyelvi aldomain, követő paraméterek), és kétszer ne kerüljön a listára."""
    m = PROFILE_RE.match((url or "").strip())
    if not m:
        return ""
    return m.group(0).split("/in/", 1)[1].rstrip("/").lower()


def _seen_list(store) -> list[str]:
    try:
        data = json.loads(store.get_setting(SEEN_KEY) or "[]")
    except ValueError:
        return []
    return [x for x in data if isinstance(x, str)] if isinstance(data, list) else []


def _remember(store, keys: list[str]) -> None:
    """Csak a profil azonosítóját tartjuk meg, nevet és szöveget nem: ennyi kell
    ahhoz, hogy ugyanaz az ember ne jöjjön elő minden héten, és nem több."""
    old = _seen_list(store)
    known = set(old)
    store.set_setting(SEEN_KEY, json.dumps((old + [k for k in keys if k not in known])[-SEEN_KEEP:]))


def _score(v) -> int:
    try:
        return max(0, min(100, int(float(v))))
    except (TypeError, ValueError):
        return 0


def queries(sector: str, country: str, role: str) -> list[str]:
    """Több rövid lekérdezés egy hosszú helyett: a keresők a tömör kifejezésekre
    adnak értelmes találatot, és a változatok más-más embereket hoznak fel."""
    sec = playbook.SECTORS.get(sector, {})
    place = playbook.COUNTRIES.get(country, {}).get("name", country)
    what = (role or "").strip() or sec.get("hu", sector)
    base = sec.get("hu", sector)
    out = [f"{what} {base} {place}", f"{what} {place} LinkedIn"]
    if role:
        out.append(f"{role} {base}")
    return out


def plan(sectors: list[str], countries: list[str], roles: list[str]) -> list[tuple[str, str, str]]:
    """A bepipált szűrők szorzata, körbeforgatva, MAX_COMBOS-ig vágva.

    Tíz iparág, kilenc ország és néhány szerepkör szorzata több száz
    kombináció; mindet lefuttatni egyetlen gombnyomásra elvinné a havi
    keresési keretet. A sorrend ezért kör-körben megy: előbb minden bepipált
    iparágból egy, aztán a másodikok. Így egy széles pipálás mintát vesz
    mindenből, nem pedig az első iparágat meríti ki."""
    rows: dict[str, list[tuple[str, str, str]]] = {}
    for s in sectors:
        for c in countries:
            for r in (roles or [""]):
                rows.setdefault(s, []).append((s, c, r))
    out: list[tuple[str, str, str]] = []
    for group in zip_longest(*rows.values()):
        out.extend(x for x in group if x)
    return out[:MAX_COMBOS]


def _clean(values, allowed, what: str) -> list[str]:
    out = [v for v in dict.fromkeys(values or []) if v in allowed]
    if not out:
        raise ValueError(f"Pipálj ki legalább egy {what}.")
    return out


def search(store, *, sectors: list[str], countries: list[str], roles: list[str] | None = None,
           say=logger.info) -> dict:
    """Nyilvános profilok keresése és szűrése. Nem küld és nem ment leadet."""
    sectors = _clean(sectors, playbook.SECTORS, "iparágat")
    countries = _clean(countries, playbook.COUNTRIES, "országot")
    roles = [r.strip()[:80] for r in (roles or []) if r and r.strip()][:MAX_ROLES]
    if not websearch.tavily_on():
        raise ValueError("Ehhez TAVILY_API_KEY kell: a keresőmotor indexét kérdezzük, "
                         "és enélkül nincs honnan találatot venni.")

    combos = plan(sectors, countries, roles)
    seen, hits, keys = set(_seen_list(store)), [], set()
    for sector, country, role in combos:
        if len(hits) >= MAX_HITS:
            break
        for q in queries(sector, country, role)[:QUERIES_PER_COMBO]:
            say(f"Keresés: {q}")
            for h in websearch.search(q, n=10, include_domains=["linkedin.com"]):
                key = _profile_key(h.get("url", ""))
                if not key or key in keys or key in seen:
                    continue
                keys.add(key)
                hits.append({"title": h["title"][:200], "url": h["url"],
                             "text": (h.get("text") or "")[:900]})
            if len(hits) >= MAX_HITS:
                break
    hits = hits[:MAX_HITS]
    if not hits:
        return {"profiles": [], "looked_at": 0, "searched": len(combos),
                "note": "Nem jött új nyilvános profil erre a szűrésre. Pipálj ki több iparágat vagy "
                        "országot, vagy nézd meg később — a már látottakat kihagyjuk."}

    say(f"{len(hits)} új profil, egy hívásban átnézem őket.")
    data = llm.extract_json(llm._ask(playbook.linkedin_judge_prompt(hits, sectors, countries, roles)))
    if not isinstance(data, list):
        raise llm.LLMError("a profilszűrő nem listát adott")

    out = []
    for item in data:
        if not isinstance(item, dict):
            continue
        i = item.get("i")
        if not isinstance(i, int) or not 0 <= i < len(hits):
            continue
        if item.get("verdict") != "ir":
            continue
        summary = str(item.get("summary") or "").strip()
        if not summary:
            continue
        out.append({
            "url": hits[i]["url"],
            "name": str(item.get("name") or "").strip()[:120],
            "headline": str(item.get("headline") or "").strip()[:120],
            "summary": summary[:700],
            "agent": str(item.get("agent") or "").strip()[:60],
            "score": _score(item.get("score")),
        })
    out.sort(key=lambda x: -x["score"])
    # A megnézetteket akkor is elkönyveljük, ha elbuktak: a következő kör ne
    # ugyanazon a huszonnégy emberen pazarolja el a keresést és a modellhívást.
    _remember(store, sorted(keys))
    return {"profiles": out, "looked_at": len(hits), "searched": len(combos),
            "note": "" if out else "A találatok egyike sem tűnt célcsoportnak."}


def draft(profile: str, note: str = "", lang: str = "hu") -> dict:
    """Ítélet és szöveg a bemásolt profilra. ValueError, ha a bemenet kevés."""
    profile = (profile or "").strip()
    if not MIN_PROFILE <= len(profile) <= MAX_PROFILE:
        raise ValueError(f"A bemásolt profil {MIN_PROFILE} és {MAX_PROFILE} karakter között legyen "
                         f"(most {len(profile)}).")
    if lang not in playbook.LANG_NAMES:
        raise ValueError(f"Ismeretlen nyelv: {lang}")

    data = llm.extract_json(llm._ask(playbook.linkedin_prompt(profile, (note or "").strip(), lang)))
    if not isinstance(data, dict):
        raise llm.LLMError("a megkeresés-író nem objektumot adott")

    verdict = data.get("verdict")
    if verdict not in VERDICTS:
        raise llm.LLMError(f"ismeretlen ítélet: {verdict!r}")
    reason = str(data.get("reason") or "").strip()[:300]

    if verdict == "ne_irj":
        # Szöveget ilyenkor szándékosan nem adunk vissza, akkor sem, ha a modell
        # írt egyet: ha ott van a mezőben, előbb-utóbb valaki kimásolja.
        return {"verdict": verdict, "reason": reason or "Nem célcsoport.",
                "quote": "", "message": "", "problems": []}

    quote = str(data.get("quote") or "").strip()
    message = str(data.get("message") or "").strip()
    if len(message) < MIN_MESSAGE:
        raise llm.LLMError("a megkeresés-író üres vagy túl rövid szöveget adott")

    problems = []
    if not quote:
        problems.append("Nem jelölte meg, melyik mondatra hivatkozik a profilból.")
    elif not verify.quote_on_page(quote, profile):
        problems.append("A hivatkozott mondat nincs benne a bemásolt szövegben — ellenőrizd, "
                        "mielőtt elküldöd.")
    if verify.has_price(message):
        problems.append("Árat említ. A megkeresésben nem árazunk.")
    if len(message) > playbook.LINKEDIN_MAX_CHARS:
        problems.append(f"Hosszabb {playbook.LINKEDIN_MAX_CHARS} karakternél "
                        f"({len(message)}) — LinkedInen ennyit nem olvasnak el.")
    return {"verdict": verdict, "reason": reason, "quote": quote,
            "message": message, "problems": problems}
