"""Napi tartalomtéma a videós agentnek: egy magyar (LinkedIn) és egy angol (Instagram).

A sales agent tudja, milyen fájdalmakat és jeleket talált az utóbbi hetekben a
cégeknél; ebből ír egy-egy rövid témát, és elküldi a videós agent beérkező
sorába. Cégnevet, személynevet soha nem adhat tovább: amit a modell ír, azt a
kód is átszűri a frissen talált cégek nevére és domainjére.

Naponta egy agent kerül sorra, és a nap mindkét témája (LinkedIn és Instagram)
ugyanarról az egyről szól. Hogy melyik, azt a KÓD dönti el, nem a modell:
a legrégebben szerepelt agent jön, így mind sorra kerül, mielőtt bármelyik
másodszor jönne. Amíg a választás a modellre volt bízva, mindig a
legkézenfekvőbbre (e-mail rendező) esett, a lista vége pedig soha nem került
elő — a posztok eloszlása ezért nem a modell ízlésén múlik.

Ugyanígy a kód adja:
- az iparágat (a legrégebben szerepelt jön) — magára hagyva a modell minden
  nap „gyártó cégről" írt, mert a piaci jelek között az volt a leggyakoribb;
- a formát (videó vagy kép/körhinta) — magára hagyva LinkedInre mindig képet,
  Instagramra mindig videót kért. A dátumból számoljuk, platformonként
  felváltva, és egy napon az egyik platform videót, a másik állóképet kap;
- a nap nevét, mert a modell a dátumból rosszul számolta ki.

Hibatűrés:
- a napi témát egyszer generálja és elmenti; ha a küldés elhasal, ugyanazt a
  szöveget ugyanazzal az azonosítóval küldi újra, a videós agent pedig az
  azonosítón szűr, így nem lesz dupla videó;
- RETRY_MIN percenként újrapróbálja, LAST_HOUR óráig; utána aznapra feladja.
"""
from __future__ import annotations

import json
import logging
import os
import re
import threading
from collections import Counter
from datetime import datetime, timedelta

import httpx

import llm
from playbook import AGENTS, SECTORS, VOICE_AGENT

logger = logging.getLogger(__name__)

ROUTES = {"hu": "linkedin", "en": "instagram"}
LOOKBACK_DAYS = 21
RETRY_MIN = 30
LAST_HOUR = 21
DEFAULT_URL = "https://aximbra-video-production.up.railway.app/api/inbox"
_lock = threading.Lock()


def enabled() -> bool:
    return (os.environ.get("CONTENT_DAILY") or "").strip().lower() in ("1", "true", "yes") \
        and len(os.environ.get("AGENT_TOKEN", "")) >= 24


def start_time() -> tuple[int, int]:
    raw = (os.environ.get("CONTENT_TIME") or "07:30").strip()
    try:
        h, m = (int(x) for x in raw.split(":"))
        if 0 <= h < 24 and 0 <= m < 60:
            return h, m
    except ValueError:
        pass
    return 7, 30


def due(now: datetime, store) -> bool:
    """Ma még nem ment ki mindkét téma, elmúlt a kezdés, és az utolsó
    próbálkozás óta eltelt RETRY_MIN perc."""
    h, m = start_time()
    if now < now.replace(hour=h, minute=m, second=0, microsecond=0) or now.hour >= LAST_HOUR:
        return False
    day = now.date().isoformat()
    if all(store.get_setting(f"content_sent_{lang}") == day for lang in ROUTES):
        return False
    last = store.get_setting("content_last_try") or ""
    try:
        return now - datetime.fromisoformat(last) >= timedelta(minutes=RETRY_MIN)
    except ValueError:
        return True


# ---- mit tudunk a piacról ---------------------------------------------------

def _market(store, now: datetime) -> dict:
    """Az utóbbi hetek leadjeiből: iparágak, fájdalmak, jelek — nevek nélkül
    a promptban, de a nevek listája megmarad a szűréshez."""
    since = (now - timedelta(days=LOOKBACK_DAYS)).isoformat()
    leads = [l for l in store.list() if (l.get("created_at") or "") >= since]
    names: set[str] = set()
    out = {"hu": {"sectors": Counter(), "pains": [], "signals": []},
           "en": {"sectors": Counter(), "pains": [], "signals": []}}
    for l in leads:
        g = out["hu" if l.get("country") == "HU" else "en"]
        sec = l.get("sector") or ""
        if sec in SECTORS:
            g["sectors"][SECTORS[sec].get("hu", sec) if g is out["hu"] else sec] += 1
        if l.get("pain") and len(g["pains"]) < 12:
            g["pains"].append(l["pain"][:220])
        if l.get("signal_note") and len(g["signals"]) < 8:
            g["signals"].append(l["signal_note"][:160])
        for n in (l.get("company"), (l.get("domain") or "").split(".")[0]):
            n = (n or "").strip()
            if len(n) >= 4:
                names.add(n.lower())
    best = store.best_sectors()
    return {"groups": out, "names": names, "best": best}


# ---- melyik agent kerül ma sorra --------------------------------------------

# A tizenöt kártya és a telefonos agent. A telefonos a második: az első
# napon (2026-10-08) az e-mail rendező már kiment, így ő jön utána.
ROTATION = (AGENTS[0], VOICE_AGENT, *AGENTS[1:])
AGENT_KEYS = tuple(a["key"] for a in ROTATION)
HISTORY_KEEP = 2 * len(ROTATION)
SECTOR_KEYS = tuple(SECTORS)

# Platformonként felváltva videó és állókép; a körhinta minden második
# állókép helyén jön. Az Instagram egy lépéssel el van tolva, így egy napon
# az egyik platform videót, a másik állóképet kap.
FORM_CYCLE = ("video", "image", "video", "carousel")
FORM_OFFSET = {"hu": 0, "en": 1}

HU_DAYS = ("hétfő", "kedd", "szerda", "csütörtök", "péntek", "szombat", "vasárnap")
EN_DAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")


def _history(store, setting: str = "content_agents", keys=AGENT_KEYS) -> list[str]:
    try:
        hist = json.loads(store.get_setting(setting) or "[]")
    except ValueError:
        return []
    if not isinstance(hist, list):
        return []
    return [k for k in hist if isinstance(k, str) and k in keys]


def pick_agent(store) -> dict:
    """A legrégebben szerepelt agent jön. Aki még sosem volt, az előre kerül, a
    holtversenyt pedig a névsor sorrendje dönti el — a választás így
    determinisztikus és visszanézhető. Ebből következik, amit kértünk: mind
    sorra kerül, mielőtt bármelyik másodszor jönne."""
    last = {k: i for i, k in enumerate(_history(store))}
    return min(ROTATION, key=lambda a: last.get(a["key"], -1))


def pick_sector(store) -> str:
    """Ugyanaz a szabály az iparágra: a legrégebben szerepelt jön."""
    last = {k: i for i, k in enumerate(_history(store, "content_sectors", SECTOR_KEYS))}
    return min(SECTOR_KEYS, key=lambda k: last.get(k, -1))


def pick_form(lang: str, day) -> str:
    """A dátumból, nem tárolt számlálóból: egy újrafutás vagy egy kimaradt nap
    nem csúsztatja el, és bármelyik napra visszanézhető."""
    return FORM_CYCLE[(day.toordinal() + FORM_OFFSET.get(lang, 0)) % len(FORM_CYCLE)]


FORM_HU = {"video": "rövid videó", "image": "egyetlen kép", "carousel": "képes körhinta (több kép egymás után)"}


def _prompt(m: dict, recent: list[str], today: str, agent: dict, sector: str = "",
            weekday: tuple = ("", ""), forms: dict | None = None) -> str:
    forms = forms or {}
    sec = SECTORS.get(sector) or {}
    def block(g):
        sec = ", ".join(f"{k} ({v})" for k, v in g["sectors"].most_common(5)) or "nincs még adat"
        pains = "\n".join(f"- {p}" for p in g["pains"]) or "- nincs még adat"
        sig = "\n".join(f"- {s}" for s in g["signals"]) or "- nincs"
        return f"Iparágak: {sec}\nFájdalmak, amiket a cégeknél láttunk:\n{pains}\nFriss jelek:\n{sig}"
    best = ", ".join(m["best"]) or "még nincs elég adat"
    rec = "\n".join(f"- {r}" for r in recent) or "- nincs"
    return f"""Te az AXIMBRA értékesítési agentje vagy. Ma ({today}, {weekday[0]} / {weekday[1]}) két tartalomtémát írsz a videós agentnek.
Ha a témában napot említesz, az csak a mai nap lehet ({weekday[0]} / {weekday[1]}) — vagy ne említs napot.

AXIMBRA: egyszemélyes AI-agent stúdió (aximbra.hu). Minden agent a cég saját rendszerén fut, és semmi nem megy ki
emberi jóváhagyás nélkül. Az oldalon élő demók vannak regisztráció nélkül.

A MAI AGENT — mindkét téma erről szól, másikról ma nem írsz:
  magyarul: {agent["hu"]} — {agent["hu_what"]}
  angolul: {agent["en"]} — {agent["en_what"]}
A sorrendet nem te döntöd el: minden agent sorra kerül, ma ez következik. Ha ez a mai agent nem illik a lenti
piaci jelekhez, akkor sem váltasz agentet — olyan helyzetet keresel, ahol ennek az agentnek van dolga.
Nem kötelező kimondani az agent nevét: elég, ha a téma az ő helyzetéről szól, és abból látszik, mit old meg.

A MAI IPARÁG — mindkét téma ebben játszódik, másik iparágat ma nem hozol:
  {sec.get("hu", sector)} ({sector})
  Jellemző gond ott: {sec.get("pain", "")}
Ezt is a kód választja, körbe: ha a lenti piaci jelek más iparágról szólnak, akkor is ebben maradsz, és olyan
szerepet, helyzetet keresel benne, ahol a mai agentnek van dolga.

A MAI FORMA — ezt is a kód adja, nem választasz:
  "hu" (LinkedIn): {FORM_HU.get(forms.get("hu", ""), "")}
  "en" (Instagram): {FORM_HU.get(forms.get("en", ""), "")}
A témát úgy írd, hogy ebben a formában működjön (videónál mozgás és hang, képnél egy erős jelenet, körhintánál lépések).

Amit az utóbbi {LOOKBACK_DAYS} napban a magyar cégeknél láttunk:
{block(m["groups"]["hu"])}

Amit a külföldi (UK, IE, FR, BE, SK, RO, HR, SI) cégeknél láttunk:
{block(m["groups"]["en"])}

Ahol eddig a legtöbb érdeklődő válasz jött: {best}

Az utóbbi napok témái (NE ismételd őket — a mai agent adott, tehát MÁS HELYZETET válassz, ne másik agentet):
{rec}

Szabályok (marketingkutatás alapján):
1. Egy téma = egy konkrét, felismerhető helyzet a vevő napjából (kategória-belépési pont), pl. "hétfő reggel 200 levél".
   Ne általános "az AI segít" üzenet.
2. Egy üzenet, egy agent — a mai. Az AXIMBRA neve az elején jelenjen meg.
3. Semmilyen számot, ügyfelet, eredményt, százalékot ne találj ki. Ami fent nincs, az nincs.
4. SOHA ne nevezz meg céget, személyt, domaint vagy várost a fenti adatokból — csak az iparágat és a helyzetet.
   Egyedi, egy céghez köthető részletet (postafiók-nevek, termékek, rendszerek neve) se vegyél át: általánosíts.
   Ne írd bele, hogy "az értékesítő agent mutatja be" — a téma a nézőnek szól, nem rólad.
5. A formát fent megkaptad; ne írj mást.
6. "hu": magyar nyelven, magyar kkv-vezetőknek, LinkedInre: szakmai, nyugodt, a végén kérdés az olvasónak.
   "en": angolul, nemzetközi cégtulajdonosoknak és üzemeltetési vezetőknek, Instagramra: vizuálisabb, rövidebb, erős első kép.
7. Mindkét téma 2–4 mondat, 200–600 karakter: mit mutasson, kinek, milyen hangulatban, mi a zárás.

Csak JSON-t adj vissza:
{{"hu": {{"brief": "..."}}, "en": {{"brief": "..."}}}}"""


def leaks(text: str, names: set[str]) -> list[str]:
    low = (text or "").lower()
    return sorted(n for n in names if re.search(r"(?<![\w])" + re.escape(n) + r"(?![\w])", low))


def generate(store, now: datetime, agent: dict, sector: str = "") -> dict:
    m = _market(store, now)
    try:
        recent = json.loads(store.get_setting("content_recent") or "[]")
    except ValueError:
        recent = []
    day = now.date()
    forms = {lang: pick_form(lang, day) for lang in ROUTES}
    weekday = (HU_DAYS[day.weekday()], EN_DAYS[day.weekday()])
    data = llm.extract_json(llm._ask(_prompt(m, recent[-10:], day.isoformat(), agent,
                                             sector, weekday, forms)))
    if not isinstance(data, dict):
        raise llm.LLMError("a témaíró nem objektumot adott")
    out = {}
    for lang in ROUTES:
        item = data.get(lang) or {}
        brief = (item.get("brief") or "").strip() if isinstance(item, dict) else ""
        if not 40 <= len(brief) <= 1500:
            raise llm.LLMError(f"{lang}: hiányzó vagy rossz hosszú téma")
        bad = leaks(brief, m["names"])
        if bad:
            raise llm.LLMError(f"{lang}: cégnevet tartalmazna ({len(bad)} db), eldobtam")
        # A forma a kódé: amit a modell esetleg mégis visszaír, nem számít.
        out[lang] = {"brief": brief, "form": forms[lang]}
    return out


def _send(item: dict) -> None:
    url = (os.environ.get("VIDEO_INBOX_URL") or DEFAULT_URL).strip()
    try:
        r = httpx.post(url, json=item, headers={"X-Agent-Token": os.environ.get("AGENT_TOKEN", "")}, timeout=30)
    except httpx.HTTPError as e:
        raise RuntimeError(f"a videós agent nem érhető el ({type(e).__name__})") from e
    if r.status_code >= 400:
        raise RuntimeError(f"a videós agent elutasította: HTTP {r.status_code} {r.text[:120]}")


def run(store, now: datetime, say=logger.info) -> dict:
    """A napi kör. Egyszerre csak egy fut."""
    if not _lock.acquire(blocking=False):
        return {}
    try:
        store.set_setting("content_last_try", now.isoformat(timespec="seconds"))
        day = now.date().isoformat()
        try:
            briefs = json.loads(store.get_setting(f"content_briefs_{day}") or "{}")
        except ValueError:
            briefs = {}
        if not isinstance(briefs, dict):
            briefs = {}
        if not all(lang in briefs for lang in ROUTES):
            # A mai agentet a kód választja, és a nap témáival EGYÜTT mentjük:
            # egy sikertelen küldés utáni újrafutás ugyanazt a napot folytatja,
            # nem lép tovább a névsorban és nem ír át egy már kiküldött témát.
            agent = pick_agent(store)
            sector = pick_sector(store)
            briefs = generate(store, now, agent, sector)
            briefs["agent"] = agent["key"]
            briefs["sector"] = sector
            store.set_setting(f"content_briefs_{day}", json.dumps(briefs, ensure_ascii=False))
            # A névsor csak akkor lép, ha a témák tényleg megvannak — egy
            # elhasalt modellhívás nem égethet el egy agentet.
            store.set_setting("content_agents",
                              json.dumps((_history(store) + [agent["key"]])[-HISTORY_KEEP:]))
            store.set_setting("content_sectors", json.dumps(
                (_history(store, "content_sectors", SECTOR_KEYS) + [sector])[-2 * len(SECTOR_KEYS):]))
            try:
                recent = json.loads(store.get_setting("content_recent") or "[]")
            except ValueError:
                recent = []
            recent = (recent + [briefs[lang]["brief"][:160] for lang in ROUTES])[-20:]
            store.set_setting("content_recent", json.dumps(recent, ensure_ascii=False))
        # A mai agent a küldő nevében is látszik, hogy a videós agent paneljén
        # végig lehessen nézni, melyikről ment már poszt.
        key = briefs.get("agent") or ""
        source = f"sales agent · {key}" if key else "sales agent"
        sent = {}
        for lang, target in ROUTES.items():
            if store.get_setting(f"content_sent_{lang}") == day:
                continue
            b = briefs[lang]
            _send({"id": f"sales-{day}-{lang}", "brief": b["brief"], "lang": lang,
                   "targets": [target], "form": b["form"], "source": source})
            store.set_setting(f"content_sent_{lang}", day)
            sent[lang] = b["brief"]
            say(f"Tartalomtéma elküldve ({lang} → {target}, {key or 'agent'}, "
                f"{briefs.get('sector') or '-'}, {b['form']}): {b['brief'][:80]}")
        return sent
    finally:
        _lock.release()
