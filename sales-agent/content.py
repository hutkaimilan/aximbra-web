"""Napi tartalomtéma a videós agentnek: egy magyar (LinkedIn) és egy angol (Instagram).

A sales agent tudja, milyen fájdalmakat és jeleket talált az utóbbi hetekben a
cégeknél; ebből ír egy-egy rövid témát, és elküldi a videós agent beérkező
sorába. Cégnevet, személynevet soha nem adhat tovább: amit a modell ír, azt a
kód is átszűri a frissen talált cégek nevére és domainjére.

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
from playbook import SECTORS

logger = logging.getLogger(__name__)

ROUTES = {"hu": "linkedin", "en": "instagram"}
FORMS = ("video", "image", "carousel")
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


def _prompt(m: dict, recent: list[str], today: str) -> str:
    def block(g):
        sec = ", ".join(f"{k} ({v})" for k, v in g["sectors"].most_common(5)) or "nincs még adat"
        pains = "\n".join(f"- {p}" for p in g["pains"]) or "- nincs még adat"
        sig = "\n".join(f"- {s}" for s in g["signals"]) or "- nincs"
        return f"Iparágak: {sec}\nFájdalmak, amiket a cégeknél láttunk:\n{pains}\nFriss jelek:\n{sig}"
    best = ", ".join(m["best"]) or "még nincs elég adat"
    rec = "\n".join(f"- {r}" for r in recent) or "- nincs"
    return f"""Te az AXIMBRA értékesítési agentje vagy. Ma ({today}) két tartalomtémát írsz a videós agentnek.

AXIMBRA: egyszemélyes AI-agent stúdió (aximbra.hu). Agentek: e-mail rendező (közös postafiókot besorol, rangsorol),
telefonos AI (felveszi a hívást, rögzíti a kérést; az aximbra.hu-n 10 mp-en belül visszahív), érdeklődő-minősítő,
dokumentumelemző (számla, szállítólevél, szerződés mezői), NIS2 bizonyítékgyűjtő (támadás ellen NEM véd), értékesítő agent.
Minden agent a cég saját rendszerén fut, és semmi nem megy ki emberi jóváhagyás nélkül.

Amit az utóbbi {LOOKBACK_DAYS} napban a magyar cégeknél láttunk:
{block(m["groups"]["hu"])}

Amit a külföldi (UK, IE, FR, BE, SK, RO, HR, SI) cégeknél láttunk:
{block(m["groups"]["en"])}

Ahol eddig a legtöbb érdeklődő válasz jött: {best}

Az utóbbi napok témái (NE ismételd őket, válassz más helyzetet vagy más agentet):
{rec}

Szabályok (marketingkutatás alapján):
1. Egy téma = egy konkrét, felismerhető helyzet a vevő napjából (kategória-belépési pont), pl. "hétfő reggel 200 levél".
   Ne általános "az AI segít" üzenet.
2. Egy üzenet, egy agent. Az AXIMBRA neve az elején jelenjen meg.
3. Semmilyen számot, ügyfelet, eredményt, százalékot ne találj ki. Ami fent nincs, az nincs.
4. SOHA ne nevezz meg céget, személyt, domaint vagy várost a fenti adatokból — csak az iparágat és a helyzetet.
5. Váltogasd a formát: video, image vagy carousel. Egy magyarázó, lépésekből álló téma inkább carousel.
6. "hu": magyar nyelven, magyar kkv-vezetőknek, LinkedInre: szakmai, nyugodt, a végén kérdés az olvasónak.
   "en": angolul, nemzetközi cégtulajdonosoknak és üzemeltetési vezetőknek, Instagramra: vizuálisabb, rövidebb, erős első kép.
7. Mindkét téma 2–4 mondat, 200–600 karakter: mit mutasson, kinek, milyen hangulatban, mi a zárás.

Csak JSON-t adj vissza:
{{"hu": {{"brief": "...", "form": "video|image|carousel"}}, "en": {{"brief": "...", "form": "video|image|carousel"}}}}"""


def leaks(text: str, names: set[str]) -> list[str]:
    low = (text or "").lower()
    return sorted(n for n in names if re.search(r"(?<![\w])" + re.escape(n) + r"(?![\w])", low))


def generate(store, now: datetime) -> dict:
    m = _market(store, now)
    try:
        recent = json.loads(store.get_setting("content_recent") or "[]")
    except ValueError:
        recent = []
    data = llm.extract_json(llm._ask(_prompt(m, recent[-10:], now.date().isoformat())))
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
        form = item.get("form") if item.get("form") in FORMS else "auto"
        out[lang] = {"brief": brief, "form": form}
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
        if not all(lang in briefs for lang in ROUTES):
            briefs = generate(store, now)
            store.set_setting(f"content_briefs_{day}", json.dumps(briefs, ensure_ascii=False))
            try:
                recent = json.loads(store.get_setting("content_recent") or "[]")
            except ValueError:
                recent = []
            recent = (recent + [b["brief"][:160] for b in briefs.values()])[-20:]
            store.set_setting("content_recent", json.dumps(recent, ensure_ascii=False))
        sent = {}
        for lang, target in ROUTES.items():
            if store.get_setting(f"content_sent_{lang}") == day:
                continue
            b = briefs[lang]
            _send({"id": f"sales-{day}-{lang}", "brief": b["brief"], "lang": lang,
                   "targets": [target], "form": b["form"], "source": "sales agent"})
            store.set_setting(f"content_sent_{lang}", day)
            sent[lang] = b["brief"]
            say(f"Tartalomtéma elküldve ({lang} → {target}): {b['brief'][:80]}")
        return sent
    finally:
        _lock.release()
