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
# A keresőmotor részlete rövidebb, mint egy bemásolt profil; ennél kevesebből
# viszont már nem írunk, mert abból csak találgatás lenne.
MIN_SNIPPET = 40

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
AGENT_BY_KEY = {a["key"]: a for a in playbook.AGENTS}
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


# A nem magyar országokban angolul keresünk: a magyar iparágnév egy román vagy
# holland profilra semmit nem talál, az angol beosztás viszont szinte mindenhol
# így szerepel a LinkedInen.
SECTOR_EN = {"logistics": "logistics", "manufacturing": "manufacturing", "healthcare": "private healthcare",
             "automotive": "car dealership", "finance": "financial services", "property": "real estate",
             "ecommerce": "e-commerce", "hospitality": "hotel", "energy": "energy", "it_services": "IT services"}
COUNTRY_EN = {"HU": "Hungary", "SK": "Slovakia", "RO": "Romania", "HR": "Croatia", "SI": "Slovenia",
              "GB": "United Kingdom", "IE": "Ireland", "FR": "France", "BE": "Belgium", "NL": "Netherlands",
              "LU": "Luxembourg", "SE": "Sweden", "FI": "Finland", "PT": "Portugal", "AU": "Australia",
              "NZ": "New Zealand", "US": "United States", "CA": "Canada"}
ROLES_EN = ("Operations Manager", "Customer Service Manager", "Managing Director", "Head of Operations",
            "Finance Director", "IT Manager")


def queries(sector: str, country: str, role: str) -> list[str]:
    """Több rövid lekérdezés egy hosszú helyett: a keresők a tömör kifejezésekre
    adnak értelmes találatot, és a változatok más-más embereket hoznak fel."""
    sec = playbook.SECTORS.get(sector, {})
    if country != "HU":
        place = COUNTRY_EN.get(country, country)
        base = SECTOR_EN.get(sector, sector)
        what = (role or "").strip() or base
        out = [f"{what} {base} {place}", f"{what} {place} LinkedIn"]
        if role:
            out.append(f"{role} {base}")
        return out
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
           say=logger.info, max_combos: int = MAX_COMBOS, budgeted: bool = False) -> dict:
    """Nyilvános profilok keresése és szűrése. Nem küld és nem ment leadet."""
    sectors = _clean(sectors, playbook.SECTORS, "iparágat")
    countries = _clean(countries, playbook.COUNTRIES, "országot")
    roles = [r.strip()[:80] for r in (roles or []) if r and r.strip()][:MAX_ROLES]
    if not websearch.tavily_on():
        raise ValueError("Ehhez TAVILY_API_KEY kell: a keresőmotor indexét kérdezzük, "
                         "és enélkül nincs honnan találatot venni.")

    combos = plan(sectors, countries, roles)[:max_combos]
    # A nyilvántartásban szereplők (megkeresettek és a LinkedIn-exportból
    # ismert korábbi kapcsolatok) sem jöhetnek elő újra.
    seen, hits, keys = set(_seen_list(store)) | store.li_keys(), [], set()
    for sector, country, role in combos:
        if len(hits) >= MAX_HITS:
            break
        for q in queries(sector, country, role)[:QUERIES_PER_COMBO]:
            say(f"Keresés: {q}")
            if budgeted and not websearch.linkedin_budget(1):
                say("A mai LinkedIn-keresési keret elfogyott.")
                break
            for h in websearch.search(q, n=20, include_domains=["linkedin.com"]):
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
        # Agent a valódi névsorból, vagy sehogy. A modell korábban iparághoz
        # talált ki agentet, a szövegíró pedig ugyanazt a profilt elutasította;
        # a két lépés így mondott egymásnak ellent a felhasználó szeme előtt.
        agent = AGENT_BY_KEY.get(str(item.get("agent") or "").strip().lower())
        if not agent:
            continue
        # A pontszám a modell saját becslése, nem mérés — de a „van egy
        # beosztása egy cégnél" szintű találatokat ez tartja ki a listáról.
        score = _score(item.get("score"))
        if score < playbook.MIN_SEARCH_SCORE:
            continue
        out.append({
            "key": _profile_key(hits[i]["url"]),
            "url": hits[i]["url"],
            "name": str(item.get("name") or "").strip()[:120],
            "headline": str(item.get("headline") or "").strip()[:120],
            "summary": summary[:700],
            "agent": agent["hu"],
            "score": score,
            # A kereső nyers részlete megy vissza a panelnek, hogy a „Szöveget
            # ír" gomb ebből dolgozhasson, külön keresés nélkül. A szövegírás
            # kérésre fut profilonként: huszonnégy megkeresést előre legyártani
            # abból, amiből egyet fog elküldeni, kidobott pénz.
            "snippet": f"{hits[i]['title']}\n{hits[i]['text']}".strip()[:1200],
        })
    out.sort(key=lambda x: -x["score"])
    # A megnézetteket akkor is elkönyveljük, ha elbuktak: a következő kör ne
    # ugyanazon a huszonnégy emberen pazarolja el a keresést és a modellhívást.
    _remember(store, sorted(keys))
    return {"profiles": out, "looked_at": len(hits), "searched": len(combos),
            "note": "" if out else "A találatok egyike sem tűnt célcsoportnak."}


def draft(profile: str, note: str = "", lang: str = "hu", from_search: bool = False) -> dict:
    """Ítélet és szöveg egy profilról. ValueError, ha a bemenet kevés.

    `from_search` esetén nem bemásolt profil a forrás, hanem a keresőmotor
    részlete: rövidebb, hiányosabb, és lehet hónapokkal ezelőtti. A modell ezt
    megkapja, mert másképp kell írni abból, amiben öt sor van, mint abból, amit
    a felhasználó a saját szemével olvasott. A hivatkozott mondatot ilyenkor is
    ellenőrizzük — csak épp a részlethez mérjük, nem az élő profilhoz, és ezt a
    panel ki is írja."""
    profile = (profile or "").strip()
    floor = MIN_SNIPPET if from_search else MIN_PROFILE
    if not floor <= len(profile) <= MAX_PROFILE:
        raise ValueError(f"A szöveg {floor} és {MAX_PROFILE} karakter között legyen "
                         f"(most {len(profile)}).")
    if lang not in playbook.LANG_NAMES:
        raise ValueError(f"Ismeretlen nyelv: {lang}")

    data = llm.extract_json(llm._ask(
        playbook.linkedin_prompt(profile, (note or "").strip(), lang, from_search=from_search)))
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


# ---- napi kör: a sor feltöltése ------------------------------------------------
# Hétköznap egyszer: a következő iparág–ország párokra keres (körbeforgatva, hogy
# mind sorra kerüljön), a legjobb profiloknak megírja az üzenetet a nyelvükön,
# és a sorba teszi. Elküldeni a felhasználó küldi el, a LinkedInen; a sor arra
# való, hogy reggel kész legyen, mit kinek.

DAILY_DEFAULT = 10
DAILY_PAIRS = 6    # legfeljebb ennyi iparág–ország pár egy körben; a keresést a napi keret is korlátozza


def daily_target() -> int:
    import os
    try:
        return max(0, min(30, int(os.environ.get("LI_DAILY") or DAILY_DEFAULT)))
    except ValueError:
        return DAILY_DEFAULT


def _next_pairs(store, n: int) -> list[tuple[str, str]]:
    """A következő n iparág–ország pár. A kurzor a beállításokban él, így egy
    újraindítás után is ott folytatja, ahol abbahagyta."""
    countries = [c for c in playbook.COUNTRIES if playbook.country_ready(c)]
    sectors = list(playbook.SECTORS)
    pairs = [(sectors[i % len(sectors)], countries[i % len(countries)])
             for i in range(len(sectors) * len(countries))]
    try:
        at = int(store.get_setting("li_cursor") or 0)
    except ValueError:
        at = 0
    out = [pairs[(at + i) % len(pairs)] for i in range(n)]
    store.set_setting("li_cursor", str((at + n) % len(pairs)))
    return out


def with_offer(message: str, lang: str) -> str:
    offer = playbook.OFFER.get(lang) or playbook.OFFER["en"]
    return message if offer in message else f"{message.rstrip()}\n\n{offer}"


# Első forrás: a cégek, akiknek a sales agent már írt e-mailt. Róluk ellenőrzött
# tényünk van a saját weboldalukról, tehát illenek hozzánk; csak a döntéshozót
# kell megtalálni náluk. Ugyanazt a céget két csatornán érjük el, és az üzenet
# konkrétabb, mint egy puszta keresési találatból.
TRIED_KEY = "li_tried_leads_v2"   # v2: az első változat rossz háttérszöveggel utasított el cégeket
TRIED_KEEP = 2000


def _company_words(company: str) -> list[str]:
    """A cégnév jellemző szavai az egyezéshez (a jogi forma és a rövid szavak nélkül)."""
    stop = {"kft", "zrt", "nyrt", "bt", "kkt", "ltd", "limited", "llc", "inc", "gmbh", "sro", "s.r.o", "a.s",
            "srl", "s.a", "sa", "sas", "sarl", "bv", "b.v", "nv", "ab", "oy", "lda", "plc", "group", "the", "and"}
    words = [w.strip(".,()&-").lower() for w in re.split(r"\s+", company or "")]
    return [w for w in words if len(w) >= 3 and w not in stop]


# LinkedIn országos aldomainje (uk.linkedin.com) a célország kódjával.
_LI_SUB = {"GB": "uk"}
# Előnyben a döntéshozók: ügyvezető, üzemeltetés, ügyfélszolgálat; a HR és a
# marketing csak akkor, ha mást nem találtunk.
_ROLE_ORDER = (("ceo", "managing director", "ügyvezető", "general manager", "owner", "tulajdonos", "founder",
                "director general", "directeur général", "konateľ", "director general", "direktor"),
               ("coo", "operations", "üzemeltet", "operational", "logisti", "customer service", "ügyfélszolgálat",
                "plant manager", "site manager"),
               ("cfo", "finance", "pénzügy", "it ", "cio", "cto", "head of it"))


def _role_rank(title: str) -> int:
    t = (title or "").lower()
    for i, words in enumerate(_ROLE_ORDER):
        if any(w in t for w in words):
            return i
    return len(_ROLE_ORDER)


def _same_country(hit: dict, lead: dict, text: str) -> bool:
    host = (hit.get("url") or "").split("://")[-1].split("/")[0].lower()
    sub = host.split(".")[0] if host.count(".") >= 2 else "www"
    want = _LI_SUB.get(lead["country"], lead["country"].lower())
    if sub not in ("www", "linkedin"):
        return sub == want
    dom = (lead.get("domain") or "").split(".")[0].lower()
    town = (lead.get("town") or "").lower()
    country = COUNTRY_EN.get(lead["country"], "").lower()
    return bool((dom and dom in text) or (town and town in text) or (country and country in text))


def _tried(store) -> list[int]:
    try:
        data = json.loads(store.get_setting(TRIED_KEY) or "[]")
    except ValueError:
        return []
    return [x for x in data if isinstance(x, int)]


def _from_leads(store, want: int, say) -> int:
    tried = set(_tried(store))
    leads = [l for l in store.list("sent") if l["id"] not in tried and l["reply_kind"] in ("none", "auto")
             and not store.is_blocked(l["email"]) and l.get("company")]
    added, done = 0, []
    for lead in leads:
        if added >= want:
            break
        words = _company_words(lead["company"])
        if not words:
            done.append(lead["id"])
            continue
        if not websearch.linkedin_budget(1):
            say("A mai LinkedIn-keresési keret elfogyott.")
            break
        done.append(lead["id"])
        role = ("ügyvezető OR üzemeltetési vezető OR igazgató" if lead["country"] == "HU"
                else "CEO OR managing director OR operations director OR head of operations")
        known = store.li_keys() | set(_seen_list(store))
        pick, best = None, 99
        for h in websearch.search(f"{lead['company']} {role}", n=10, include_domains=["linkedin.com"]):
            key = _profile_key(h.get("url", ""))
            text = f"{h.get('title', '')} {h.get('text', '')}".lower()
            # Csak az, akinél a cég neve is ott van, és ugyanabban az országban:
            # különben egy névrokon cég embere lenne (egy amerikai „PPS Group”).
            if not key or key in known or not all(w in text for w in words[:2]):
                continue
            if not _same_country(h, lead, text):
                continue
            rank = _role_rank(h.get("title", ""))
            if rank < best:
                pick, best = (key, h), rank
        if not pick:
            continue
        key, h = pick
        lang = lead.get("lang") or playbook.COUNTRIES.get(lead["country"], {}).get("lang", "en")
        fact = (lead.get("observation") or "").strip()
        profile = (f"{h['title']}\n{h.get('text', '')}".strip()
                   + (f"\n\nA cég saját weboldaláról (ellenőrzött): {fact}" if fact else ""))
        note = (f"Háttér, nem kizáró ok: a cégnek ({lead['company']}) korábban már írtunk egy rövid e-mailt, "
                "erre nem jött válasz. Ezért szándékosan keressük meg a döntéshozót LinkedInen is — ez a "
                "megszokott második csatorna, írj neki nyugodtan. Az e-mailt ne említsd.")
        try:
            d = draft(profile[:MAX_PROFILE], note, lang, from_search=True)
        except (ValueError, llm.LLMError) as e:
            say(f"LinkedIn ({lead['company']}): nem lett szöveg ({e}).")
            continue
        if d["verdict"] != "ir" or not d["message"]:
            say(f"LinkedIn ({lead['company']}): a talált embernek nem érdemes írni ({d['reason']}).")
            continue
        name = re.split(r"\s[-–|]\s", h["title"])[0].strip()[:120]
        row = {"key": key, "url": h["url"].split("?")[0], "name": name, "headline": h["title"][:200],
               "company": lead["company"], "country": lead["country"], "lang": lang, "agent": lead.get("pain"),
               "score": lead.get("score"), "summary": f"E-mailben már megkerestük ({lead['email']}). {fact}"[:700],
               "message": with_offer(d["message"], lang), "note": "; ".join(d["problems"]) or None}
        if store.li_add(row):
            added += 1
            say(f"LinkedIn: sorba téve {name} ({lead['company']}, {lead['country']}).")
    store.set_setting(TRIED_KEY, json.dumps((_tried(store) + done)[-TRIED_KEEP:]))
    return added


def daily_round(store, say=logger.info) -> int:
    """Feltölti a sort legfeljebb daily_target() új profillal. Visszaadja, hányat tett be."""
    want = daily_target() - store.li_queued()
    if want <= 0:
        say("A LinkedIn-sor tele van: előbb a várakozókat küldd el vagy hagyd ki.")
        return 0
    added = _from_leads(store, want, say)
    for n, (sector, country) in enumerate(_next_pairs(store, DAILY_PAIRS)):
        if added >= want:
            break
        # Konkrét beosztással keresünk: beosztás nélkül a kifejezés csak az
        # iparág nevét ismételte, és alig hozott profilt.
        roles = ROLES if country == "HU" else ROLES_EN
        role = roles[(n + len(store.li_keys())) % len(roles)]
        try:
            found = search(store, sectors=[sector], countries=[country], roles=[role], say=say,
                           max_combos=1, budgeted=True)
        except (ValueError, llm.LLMError) as e:
            say(f"LinkedIn ({sector}, {country}): a keresés nem sikerült ({e}).")
            continue
        lang = playbook.COUNTRIES[country]["lang"]
        for p in found["profiles"]:
            if added >= want:
                break
            if not p["key"] or p["key"] in store.li_keys():
                continue
            try:
                d = draft(p["snippet"], "", lang, from_search=True)
            except (ValueError, llm.LLMError) as e:
                say(f"LinkedIn: {p['name'] or p['key']} — nem lett szöveg ({e}).")
                continue
            if d["verdict"] != "ir" or not d["message"]:
                continue
            row = {"key": p["key"], "url": p["url"], "name": p["name"], "headline": p["headline"],
                   "company": "", "country": country, "lang": lang, "agent": p["agent"], "score": p["score"],
                   "summary": p["summary"], "message": with_offer(d["message"], lang),
                   "note": "; ".join(d["problems"]) or None}
            if store.li_add(row):
                added += 1
                say(f"LinkedIn: sorba téve {p['name'] or p['key']} ({country}, {p['score']}/100).")
    say(f"LinkedIn: {added} új profil vár küldésre.")
    return added


# ---- aktív figyelő: a LinkedIn-adatexport --------------------------------------
# A LinkedIn „Adataid letöltése” csomagjából (ZIP vagy a benne lévő CSV-k)
# mindenkit kiolvasunk, akivel a sales agent előtt is volt kapcsolat: a
# kapcsolatokat, a küldött és kapott meghívókat, és akikkel üzenetet váltottál.
# Ők soha nem kerülnek a sorba; aki épp ott várt, kikerül onnan.

_IN_URL = re.compile(r"https?://(?:[a-z0-9-]+\.)*linkedin\.com/in/[^\s\",;/?#]+", re.I)


def _csv_rows(text: str) -> list[dict]:
    """A LinkedIn CSV-k elején néha megjegyzés-sorok vannak; a fejléc az első
    sor, amelyben vessző után ismert oszlopnév áll."""
    import csv
    import io
    lines = text.splitlines()
    start = 0
    for i, line in enumerate(lines[:20]):
        low = line.lower()
        if "url" in low or "first name" in low or "conversation id" in low or "from" in low:
            start = i
            break
    return list(csv.DictReader(io.StringIO("\n".join(lines[start:]))))


def parse_export(files: dict[str, bytes], own_url: str = "") -> list[dict]:
    """{fájlnév: tartalom} -> [{key, url, name, company, headline, note}]. ZIP-et is elfogad."""
    import io
    import zipfile
    texts: dict[str, str] = {}
    for name, data in files.items():
        if name.lower().endswith(".zip") or data[:2] == b"PK":
            try:
                with zipfile.ZipFile(io.BytesIO(data)) as z:
                    for info in z.infolist():
                        if info.filename.lower().endswith(".csv") and info.file_size < 50_000_000:
                            texts[info.filename] = z.read(info).decode("utf-8-sig", "replace")
            except zipfile.BadZipFile:
                raise ValueError(f"{name}: nem olvasható ZIP")
        else:
            texts[name] = data.decode("utf-8-sig", "replace")
    own = _profile_key(own_url) if own_url else ""
    found: dict[str, dict] = {}

    def add(url: str, **extra):
        key = _profile_key(url)
        if not key or key == own:
            return
        row = found.setdefault(key, {"key": key, "url": url.split("?")[0]})
        for k, v in extra.items():
            if v and not row.get(k):
                row[k] = v.strip()[:200]

    for name, text in texts.items():
        low = name.lower().rsplit("/", 1)[-1]
        if low.startswith("connections"):
            for r in _csv_rows(text):
                url = r.get("URL") or r.get("Url") or ""
                full = f"{r.get('First Name', '')} {r.get('Last Name', '')}".strip()
                add(url, name=full, company=r.get("Company", ""), headline=r.get("Position", ""),
                    note="kapcsolat (LinkedIn-export)")
        elif low.startswith("invitations"):
            for r in _csv_rows(text):
                outgoing = (r.get("Direction") or "").upper() == "OUTGOING"
                url = (r.get("inviteeProfileUrl") if outgoing else r.get("inviterProfileUrl")) or ""
                add(url, name=(r.get("To") if outgoing else r.get("From")) or "",
                    note="meghívó (LinkedIn-export)")
        elif low.startswith("messages"):
            for r in _csv_rows(text):
                for u in _IN_URL.findall((r.get("RECIPIENT PROFILE URLS") or "") + " " +
                                         (r.get("SENDER PROFILE URL") or "")):
                    add(u, note="üzenetváltás (LinkedIn-export)")
        # A többi fájlban (pl. ajánlások, követések) is lehet profillink:
        # azokat nem gyűjtjük, mert nem jelentenek megkeresést.
    return list(found.values())


def import_export(store, files: dict[str, bytes], own_url: str = "") -> dict:
    rows = parse_export(files, own_url)
    if not rows:
        raise ValueError("Nem találtam benne profilt. A LinkedIn-export ZIP-jét vagy a Connections, "
                         "Invitations, messages CSV-t töltsd fel.")
    new = dequeued = 0
    for r in rows:
        res = store.li_mark_previous(r)
        new += res == "new"
        dequeued += res == "dequeued"
    _remember(store, [r["key"] for r in rows])
    return {"found": len(rows), "new": new, "dequeued": dequeued}
