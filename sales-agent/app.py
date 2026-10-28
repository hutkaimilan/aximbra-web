"""AXIMBRA értékesítő — a belső felület és az API.

Egy felhasználó, egy jelszó (ADMIN_PASSWORD, HTTP Basic). Egyszerre egy
háttérmunka futhat: keresés, küldés vagy válaszfigyelés. Magától csak
keres és vázlatot ír (ha AUTO_RESEARCH be van kapcsolva); elküldeni mindig
ember küldi, egy gombbal.
"""
import json
import logging
import os
import secrets
import threading
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi import Depends, FastAPI, File, Header, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse, Response
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from pydantic import BaseModel, Field

import advisor
import content
import demopage
import gmail_api
import llm
import outreach
import websearch
import mailer
import pipeline
import playbook
import verify
from mailer import AuthError, MailError
from playbook import COUNTRIES, SECTORS
from store import Store

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("sales")

app = FastAPI(title="AXIMBRA értékesítő", docs_url=None, redoc_url=None, openapi_url=None)
# A demóoldal az aximbra.hu-n jelenik meg, és innen kéri az adatát: csak onnan
# engedjük. Hitelesítő adatot (jelszót) böngészőből idegen oldalról nem fogadunk.
DEMO_ORIGINS = [o.strip() for o in os.environ.get(
    "DEMO_ORIGINS", "https://aximbra.hu,https://www.aximbra.hu").split(",") if o.strip()]
app.add_middleware(CORSMiddleware, allow_origins=DEMO_ORIGINS, allow_methods=["GET", "POST"],
                   allow_headers=["Content-Type"], allow_credentials=False)
security = HTTPBasic()
store = Store()


class _ApiSender:
    """A Gmail API-s küldés, ha a tulajdonos összekötötte a fiókot."""

    def available(self) -> bool:
        return gmail_api.connected(store)

    def __call__(self, msg):
        return gmail_api.send(msg, store)


mailer.set_api_sender(_ApiSender())


def _smtp_on() -> bool:
    return (os.environ.get("SMTP_ENABLED") or "").strip().lower() in ("1", "true", "yes")


def _can_send() -> bool:
    return gmail_api.connected(store) or _smtp_on()
HERE = os.path.dirname(os.path.abspath(__file__))
TZ = ZoneInfo("Europe/Budapest")


# Rossz jelszó IP-nként: 15 percen belül 5 után 429. Egy jelszó védi az összes
# leadet és demóoldalt, ezért a próbálgatást nem elég lassítani, meg kell állítani.
AUTH_FAIL_LIMIT = 5
AUTH_FAIL_WINDOW = 15 * 60
_auth_fails: dict[str, list[float]] = {}
_auth_lock = threading.Lock()


def _client_ip(request: Request) -> str:
    """A látogató IP-je a Railway proxy mögött. Az X-Forwarded-For első elemét
    a kliens maga is beírhatja, ezért a proxy által tett X-Real-IP-t, ennek
    hiányában az utolsó elemet használjuk; különben a korlát megkerülhető."""
    real = request.headers.get("x-real-ip", "").strip()
    if real:
        return real
    fwd = [x.strip() for x in request.headers.get("x-forwarded-for", "").split(",") if x.strip()]
    return (fwd[-1] if fwd else (request.client.host if request.client else "")) or "?"


def _prune(hits: dict[str, list[float]], window: float, now: float) -> None:
    """Régi IP-k kidobása, hogy a számláló ne nőjön a végtelenségig."""
    if len(hits) > 5000:
        for k in [k for k, v in hits.items() if not v or now - v[-1] > window]:
            del hits[k]


def auth(request: Request, creds: HTTPBasicCredentials = Depends(security)):
    pw = os.environ.get("ADMIN_PASSWORD", "")
    if len(pw) < 8:
        raise HTTPException(503, "Nincs beállítva elég hosszú ADMIN_PASSWORD.")
    ip, t = _client_ip(request), time.time()
    with _auth_lock:
        _prune(_auth_fails, AUTH_FAIL_WINDOW, t)
        recent = [x for x in _auth_fails.get(ip, []) if t - x < AUTH_FAIL_WINDOW]
        _auth_fails[ip] = recent
        if len(recent) >= AUTH_FAIL_LIMIT:
            raise HTTPException(429, "Túl sok hibás jelszó. Próbáld újra 15 perc múlva.")
    ok = secrets.compare_digest(creds.password.encode(), pw.encode())
    if not ok:
        with _auth_lock:
            _auth_fails.setdefault(ip, []).append(t)
        time.sleep(1)  # a jelszópróbálgatás lassítása
        raise HTTPException(401, "Hibás jelszó.", headers={"WWW-Authenticate": "Basic"})


# ---- háttérmunka --------------------------------------------------------

class Job:
    def __init__(self):
        self.lock = threading.Lock()
        self.kind = None
        self.running = False
        self.log: list[str] = []
        self.started = self.finished = None

    def start(self, kind: str, fn) -> bool:
        with self.lock:
            if self.running:
                return False
            self.kind, self.running, self.log = kind, True, []
            self.started, self.finished = datetime.now(TZ).isoformat(timespec="seconds"), None
        run = pipeline.RunLog(lines=self.log)

        def target():
            try:
                fn(run)
            except (AuthError, MailError) as e:
                run.say(f"Leálltam: {e}")
            except Exception as e:  # noqa: BLE001 — a hiba a felületen jelenjen meg, ne tűnjön el
                logger.exception("munka hiba")
                run.say(f"Váratlan hiba: {e}")
            finally:
                with self.lock:
                    self.running = False
                    self.finished = datetime.now(TZ).isoformat(timespec="seconds")

        threading.Thread(target=target, daemon=True).start()
        return True

    def state(self):
        return {"kind": self.kind, "running": self.running, "log": self.log[-200:],
                "started": self.started, "finished": self.finished}


job = Job()


def _require_start(ok: bool):
    if not ok:
        raise HTTPException(409, "Már fut egy munka, várd meg.")
    return {"ok": True}


# ---- végpontok ------------------------------------------------------------

@app.get("/health")
def health():
    return {"ok": True}


@app.get("/", dependencies=[Depends(auth)])
def index():
    # A panel egyetlen fájl, és minden deploy új változatot ad. Cache-Control
    # nélkül a böngésző a saját heurisztikája szerint tartja meg, így a friss
    # deploy után is a régit mutatja, amíg valaki erős frissítést nem nyom —
    # ez többször is úgy nézett ki, mintha ki sem ment volna a változás.
    # A "no-cache" nem tiltja a tárolást, csak használat előtt újra megkérdezi:
    # ha nem változott, 304 jön vissza, tehát nem kerül többe.
    return FileResponse(os.path.join(HERE, "static", "index.html"),
                        headers={"Cache-Control": "no-cache"})


@app.get("/api/state", dependencies=[Depends(auth)])
def state():
    demos = _demo_urls()
    return {
        "job": job.state(),
        "leads": [dict(l, mixed=bool(l["status"] == "draft" and verify.mixed_language(l)),
                       rules=verify.rule_violations(l) if l["status"] in ("draft", "failed") else [],
                       demo_url=demos.get(_lead_domain(l)))
                  for l in store.list()],
        "blocked": store.blocked_keys()[:300],
        "demo_pages": [dict(p, page_url=_demo_link(p["slug"])) for p in store.demo_list()[:200]],
        "sent_today": store.sent_today(),
        "stats": store.stats(),
        "focus": store.best_sectors(),
        "cap": pipeline.DAILY_CAP,
        "auto_send": {"on": store.get_setting("auto_send") == "on", "sent_today": store.auto_sent_today(),
                      **pipeline.readiness(store)},
        "countries": {k: v["name"] for k, v in COUNTRIES.items()},
        "sectors": {k: v["hu"] for k, v in SECTORS.items()},
        "roles": list(outreach.ROLES),
        "search_budget": {"combos": outreach.MAX_COMBOS, "per_combo": outreach.QUERIES_PER_COMBO},
        "config": {
            "gmail": bool(os.environ.get("GMAIL_USER") and os.environ.get("GMAIL_APP_PASSWORD")),
            "openai": bool(os.environ.get("OPENAI_API_KEY") or os.environ.get("GEMINI_API_KEY")),
            "auto": _auto_on(),
            "auto_times": auto_times(),
            # A Railway Hobby csomagon a kimenő SMTP le van tiltva, ezért a
            # küldés alapból a saját Gmailből, kézzel megy; a közvetlen küldés
            # csak akkor jelenik meg, ha SMTP_ENABLED be van kapcsolva.
            "smtp": _can_send(),
            "gmail_api": gmail_api.connected(store),
            "gmail_api_ready": gmail_api.configured(),
            # Ebben a Gmail-fiókban nyílik meg a kész levél (a böngészőben
            # több fiók is be lehet lépve); alapból ugyanaz, amit a válaszokhoz olvasunk.
            "gmail_user": os.environ.get("COMPOSE_ACCOUNT") or os.environ.get("GMAIL_USER", ""),
            "calendar": bool(os.environ.get("CALENDAR_ICS_URL")),
            "web_search": websearch.tavily_on(),
        },
    }


class ResearchIn(BaseModel):
    plan: dict[str, int] = Field(default_factory=dict)


@app.post("/api/research", dependencies=[Depends(auth)])
def research(body: ResearchIn):
    plan = {k.upper(): int(v) for k, v in body.plan.items() if int(v) > 0}
    if not plan:
        raise HTTPException(400, "Adj meg legalább egy országot.")
    if any(k not in COUNTRIES for k in plan) or sum(plan.values()) > pipeline.MAX_PER_RUN:
        raise HTTPException(400, f"Csak célország, és összesen legfeljebb {pipeline.MAX_PER_RUN}.")
    def run(log):
        before = {l["id"] for l in store.list("draft")}
        pipeline.research_run(store, plan, log)
        _draft_demos(before, log)
    return _require_start(job.start("keresés", run))


class SendIn(BaseModel):
    ids: list[int]


@app.post("/api/send", dependencies=[Depends(auth)])
def send(body: SendIn):
    if not _can_send():
        raise HTTPException(409, "A Gmail nincs összekötve: nyomd meg a „Gmail összekötése” gombot.")
    ids = [i for i in body.ids if isinstance(i, int)][:pipeline.DAILY_CAP]
    if not ids:
        raise HTTPException(400, "Nincs kijelölt levél.")
    return _require_start(job.start("küldés", lambda log: pipeline.send_many(store, ids, log)))


class ManualLeadIn(BaseModel):
    company: str = Field(min_length=2, max_length=200)
    email: str = Field(min_length=5, max_length=200, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    website: str = Field(default="", max_length=300)
    country: str = Field(default="HU", min_length=2, max_length=2)
    lang: str = Field(default="hu", min_length=2, max_length=2)
    town: str = Field(default="", max_length=100)
    sector: str = Field(default="", max_length=60)
    observation: str = Field(default="", max_length=1000)
    subject: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=20, max_length=5000)


@app.post("/api/manual-lead", dependencies=[Depends(auth)])
def manual_lead(body: ManualLeadIn):
    """Kézzel felvett cég, kész levéllel. Ugyanazokon a szabályokon megy át,
    mint a keresés vázlatai: célország (AT/DE soha), tiltólista, és a levél
    szabályai (ár, megnevezett munkatárs, leiratkozás) — ha bármelyik sérül,
    fel sem kerül. Küldeni utána a szokásos küldéssel lehet."""
    lead = {"company": body.company.strip(), "email": body.email.strip().lower(), "website": body.website.strip(),
            "country": body.country.upper(), "lang": body.lang.lower(), "lang2": None, "town": body.town.strip() or None,
            "sector": body.sector.strip() or None, "observation": body.observation.strip() or None,
            "pain": body.observation.strip() or "kézzel felvett", "subject": body.subject.strip(),
            "body": body.body.strip(), "score": None}
    problems = verify.rule_violations(lead)
    if problems:
        raise HTTPException(409, "Nem vehető fel: " + "; ".join(problems))
    if store.is_blocked(lead["email"]):
        raise HTTPException(409, "Ez a cím tiltólistán van.")
    lead_id = store.add_lead(lead)
    if not lead_id:
        raise HTTPException(409, "Ezzel a címmel már van levél a listában.")
    return {"id": lead_id}


class AutoSendIn(BaseModel):
    on: bool


@app.post("/api/auto-send", dependencies=[Depends(auth)])
def auto_send_toggle(body: AutoSendIn):
    # Kikapcsolni mindig lehet; bekapcsolni csak bemért pontszámmal.
    if body.on:
        r = pipeline.readiness(store)
        if not r["ready"]:
            raise HTTPException(409, "Még nem kapcsolható be: " + "; ".join(r["why"]))
        if not _can_send():
            raise HTTPException(409, "A Gmail nincs összekötve.")
    store.set_setting("auto_send", "on" if body.on else "off")
    return {"on": body.on}


class EditIn(BaseModel):
    subject: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=20, max_length=5000)


@app.post("/api/leads/{lead_id}", dependencies=[Depends(auth)])
def edit(lead_id: int, body: EditIn):
    if not store.edit(lead_id, body.subject.strip(), body.body.strip()):
        raise HTTPException(409, "Ez már nem szerkeszthető.")
    return {"ok": True}


@app.post("/api/leads/{lead_id}/mark-sent", dependencies=[Depends(auth)])
def mark_sent(lead_id: int):
    if not store.mark_sent_manual(lead_id):
        raise HTTPException(409, "Ez már nincs a vázlatok között.")
    return {"ok": True}


@app.post("/api/followups/{lead_id}/mark-sent", dependencies=[Depends(auth)])
def followup_mark_sent(lead_id: int):
    if not store.followup_sent_manual(lead_id):
        raise HTTPException(409, "Ez az utánkövetés már nincs a listán.")
    return {"ok": True}


@app.post("/api/gmail/connect", dependencies=[Depends(auth)])
def gmail_connect():
    if not gmail_api.configured():
        raise HTTPException(503, "A Google-összekötés nincs beállítva a szerveren.")
    return {"url": gmail_api.auth_url()}


@app.post("/api/gmail/disconnect", dependencies=[Depends(auth)])
def gmail_disconnect():
    gmail_api.disconnect(store)
    return {"ok": True}


# Az e-mail rendező (másik szolgáltatás) ide adja át a kör eredményét, és
# ez küldi ki e-mailben. Szándékosan csak kategórianevet és darabszámot
# fogad el: levéltartalom, feladó vagy tárgy nem juthat át ezen.
ORGANIZER_CATEGORIES = {"Ügyfél – kérdés", "Ügyfél – panasz", "Üzleti lehetőség", "Számla / pénzügy",
                        "Hatóság / hivatalos", "Szolgáltatói értesítés", "Hírlevél / marketing",
                        "Spam / kéretlen", "Egyéb"}


class OrganizerRunIn(BaseModel):
    counts: dict[str, int] = Field(default_factory=dict)
    urgent: int = Field(default=0, ge=0, le=10000)


@app.post("/internal/organizer-run")
def organizer_run(body: OrganizerRunIn, x_notify_secret: str = Header(default="")):
    secret = os.environ.get("NOTIFY_SECRET", "")
    if len(secret) < 24 or not secrets.compare_digest(x_notify_secret.encode(), secret.encode()):
        raise HTTPException(403, "tiltott")
    counts = {k: int(v) for k, v in body.counts.items() if k in ORGANIZER_CATEGORIES and 0 <= int(v) <= 10000}
    to = os.environ.get("NOTIFY_TO", "").strip()
    if not to:
        return {"ok": False, "reason": "nincs NOTIFY_TO"}
    total = sum(counts.values())
    when = datetime.now(TZ).strftime("%H:%M")
    subject = f"E-mail Rendező ({when}): {total} új levél" + (f", {body.urgent} sürgős" if body.urgent else "")
    lines = [f"Lefutott egy új frissítés ({when}).", ""]
    if total:
        lines += [f"  {n:>3}  {k}" for k, n in sorted(counts.items(), key=lambda x: -x[1]) if n]
        lines += ["", f"Összesen: {total}" + (f", ebből sürgős: {body.urgent}" if body.urgent else "")]
    else:
        lines.append("Nem jött új levél.")
    try:
        mailer.send(mailer.build_message(to, subject, "\n".join(lines)))
    except Exception as e:  # noqa: BLE001
        logger.warning("rendező-értesítés hiba: %s", e)
        raise HTTPException(502, "nem sikerült elküldeni")
    return {"ok": True}


# ---- demóoldalak ----------------------------------------------------------

class DemoIn(BaseModel):
    url: str = Field(max_length=500)
    lang: str = Field(default="", max_length=5)
    company: str = Field(default="", max_length=120)


def _demo_link(slug: str) -> str:
    return f"{demopage.PUBLIC_BASE}/{slug}"


def _demo_result(slug: str, page: dict, existing: bool) -> dict:
    return {"slug": slug, "page_url": _demo_link(slug), "agent": page["agent"]["name"],
            "observation": (page.get("observation") or {}).get("quote", ""), "generic": page["generic"],
            "existing": existing}


_demo_locks: dict[str, threading.Lock] = {}
_demo_locks_guard = threading.Lock()


def _make_demo(url: str, lang: str = "", company: str = "", lead_id: int | None = None,
               slug: str | None = None, rechoose: bool = False) -> dict:
    """Új oldal, vagy (slug-gal) a meglévő újragenerálása. Ugyanarra a domainre
    nem gyártunk másodikat: a meglévőt adjuk vissza. Domainenként egyszerre
    egy készülhet, így két gyors kattintásból sem lesz két oldal."""
    try:
        target = demopage.normalize_url(url)
    except demopage.DemoError as e:
        raise HTTPException(400, str(e))
    dom = demopage.domain_of(target)
    with _demo_locks_guard:
        lock = _demo_locks.setdefault(dom, threading.Lock())
    if not lock.acquire(timeout=240):
        raise HTTPException(409, "Ehhez a céghez már készül egy oldal, várj egy kicsit.")
    try:
        return _make_demo_locked(target, dom, lang, company, lead_id, slug, rechoose)
    finally:
        lock.release()


def _make_demo_locked(target: str, dom: str, lang: str, company: str, lead_id: int | None,
                      slug: str | None, rechoose: bool) -> dict:
    if not slug:
        old = store.demo_by_domain(dom)
        if old:
            return _demo_result(old["slug"], json.loads(old["data"]), True)
    if rechoose:
        store.demo_forget(dom)
    decision = store.demo_decision(dom)
    try:
        page = demopage.generate(target, ask=llm._ask, extract_json=llm.extract_json,
                                 lang=lang or None, company=company or None, decision=decision)
    except demopage.ModelError as e:
        raise HTTPException(503, str(e))
    except demopage.DemoError as e:
        raise HTTPException(400, str(e))
    except llm.LLMError as e:
        # A modell nem elérhető: nem gyártunk helyette általános oldalt, és a
        # meglévő jó oldalt sem írjuk felül vele.
        logger.warning("demóoldal: modellhiba: %s", e)
        raise HTTPException(503, "A nyelvi modell most nem elérhető, próbáld újra pár perc múlva.")
    if not page["generic"] and not decision:
        store.demo_decide(dom, page["agent"]["id"], [e["id"] for e in page["secondary"]])
    if slug:
        store.demo_replace(slug, page)
    else:
        slug = demopage.make_slug(page["company"], dom)
        store.demo_add(slug, page, lead_id, demopage.expires_at())
    return _demo_result(slug, page, False)


@app.post("/api/demo-pages/translate-ui", dependencies=[Depends(auth)])
def demo_translate_ui():
    """A meglévő oldalak nyelveire elkészíti a felület fordítását (nyelvenként
    egy modellhívás, egyszer); utána a régi oldalak is a saját nyelvükön jelennek meg."""
    langs = sorted({(p.get("lang") or "")[:2].lower() for p in store.demo_list()} - {"", "hu", "en"})
    done, failed = [], []
    for lang in langs:
        try:
            (done if demopage.ensure_ui(lang, llm._ask, llm.extract_json) else failed).append(lang)
        except Exception as e:  # noqa: BLE001 — egy nyelv hibája ne állítsa meg a többit
            logger.warning("ui translation %s: %s", lang, type(e).__name__)
            failed.append(lang)
    return {"translated": done, "failed": failed}


@app.post("/api/demo-pages", dependencies=[Depends(auth)])
def demo_create(body: DemoIn):
    return _make_demo(body.url, body.lang, body.company)


@app.get("/api/demo-pages", dependencies=[Depends(auth)])
def demo_list():
    return {"pages": [dict(p, page_url=_demo_link(p["slug"])) for p in store.demo_list()]}


@app.post("/api/demo-pages/{slug}/regenerate", dependencies=[Depends(auth)])
def demo_regenerate(slug: str, rechoose: bool = False):
    row = store.demo_get(slug)
    if not row:
        raise HTTPException(404, "Nincs ilyen oldal.")
    return _make_demo(row["url"], row["lang"] or "", row["company"] or "", slug=slug, rechoose=rechoose)


@app.delete("/api/demo-pages/{slug}", dependencies=[Depends(auth)])
def demo_delete(slug: str):
    if not store.demo_delete(slug):
        raise HTTPException(404, "Nincs ilyen oldal.")
    return {"ok": True}


def _lead_site(lead: dict) -> str:
    return lead.get("website") or (f"https://{lead['domain']}" if lead.get("domain") else "")


def _lead_domain(lead: dict) -> str:
    site = _lead_site(lead)
    try:
        return demopage.domain_of(demopage.normalize_url(site)) if site else ""
    except Exception:  # noqa: BLE001 — hibás webcím: nincs demó
        return ""


@app.post("/api/leads/{lead_id}/demo-page", dependencies=[Depends(auth)])
def demo_for_lead(lead_id: int):
    lead = store.get(lead_id)
    if not lead:
        raise HTTPException(404, "Nincs ilyen lead.")
    site = _lead_site(lead)
    if not site:
        raise HTTPException(400, "Ennél a leadnél nincs weboldal.")
    res = _make_demo(site, lead.get("lang") or "", lead.get("company") or "", lead_id=lead_id)
    # Ha már vár egy utánkövetés, a link bekerül; általános oldalt nem küldünk.
    res["followup_updated"] = bool(
        not res["generic"] and lead.get("followup_status") == "draft"
        and store.update_followup_draft(lead_id, pipeline.followup_body(lead, res["page_url"])))
    return res


# Egy reggeli körben legfeljebb ennyi új demóoldal készül (két modellhívás
# oldalanként az ingyenes Gemini-keretből); a többi utánkövetés link nélkül megy.
DEMO_PER_RUN = int(os.environ.get("DEMO_PER_RUN", "8"))


def _followup_demo_url(create: bool):
    """A prepare_followups-nak: a lead cégének (nem általános) demóoldala.
    create=False: csak a meglévőt adja; True: ha nincs, legfeljebb DEMO_PER_RUN
    újat készít ebben a körben."""
    made = [0]

    def get(lead: dict) -> str | None:
        site = _lead_site(lead)
        if not site:
            return None
        old = store.demo_by_domain(demopage.domain_of(demopage.normalize_url(site)))
        if old:
            return None if old["generic"] else _demo_link(old["slug"])
        if not create or made[0] >= DEMO_PER_RUN:
            return None
        made[0] += 1
        try:
            res = _make_demo(site, lead.get("lang") or "", lead.get("company") or "", lead_id=lead["id"])
        except HTTPException as e:
            logger.warning("demóoldal %s: %s", lead.get("domain"), e.detail)
            return None
        return None if res["generic"] else res["page_url"]
    return get


def _draft_demos(before: set, log) -> None:
    """Az új vázlatok cégének demóoldala már most elkészül, hogy jóváhagyáskor
    látni lehessen; az első levélbe nem kerül link, az utánkövetés ezt küldi."""
    get = _followup_demo_url(create=True)
    made = 0
    for lead in store.list("draft"):
        if lead["id"] in before:
            continue
        try:
            made += bool(get(lead))
        except Exception as e:  # noqa: BLE001 — a demó hibája ne vigye el a kört
            logger.warning("vázlat demóoldala: %s", type(e).__name__)
    if made:
        log.say(f"{made} vázlathoz elkészült a demóoldal (az utánkövetés küldi).")


def _demo_urls() -> dict[str, str]:
    """domain -> a cég (nem általános) demóoldalának linkje."""
    return {p["domain"]: _demo_link(p["slug"]) for p in store.demo_list() if not p["generic"]}


_event_hits: dict[str, list[float]] = {}
_event_lock = threading.Lock()


def _demo_notify(row: dict, event: str) -> None:
    """Első megnyitás / első „Beszéljünk” kattintás: azonnal szólunk, mert ilyenkor
    érdemes felhívni. E-mail a NOTIFY_TO címre, és ha be van állítva, webhook."""
    company = row.get("company") or row["domain"]
    lead = store.get(row["lead_id"]) if row.get("lead_id") else None
    when = datetime.now(TZ).strftime("%Y.%m.%d. %H:%M")
    if event == "first_cta":
        subject = f"Beszélni akar: {company} — rákattintott a „Beszéljünk” gombra"
    else:
        subject = f"Megnyitotta a demóoldalát: {company}"
    lines = [subject, "", f"Időpont: {when}", f"Cég: {company} ({row['domain']})",
             f"Demóoldal: {_demo_link(row['slug'])}"]
    if lead:
        lines.append(f"Lead: {lead.get('email', '')} — most érdemes felhívni vagy írni neki.")
    to = os.environ.get("NOTIFY_TO", "").strip()
    if to:
        try:
            mailer.send(mailer.build_message(to, subject, "\n".join(lines)))
        except Exception as e:  # noqa: BLE001
            logger.warning("demó-értesítés hiba: %s", e)
    hook = os.environ.get("NOTIFY_WEBHOOK_URL", "").strip()
    if hook:
        try:
            import httpx
            httpx.post(hook, json={"event": event, "slug": row["slug"], "company": company,
                                   "domain": row["domain"], "page_url": _demo_link(row["slug"]),
                                   "lead_id": row.get("lead_id"), "at": when}, timeout=10)
        except Exception as e:  # noqa: BLE001
            logger.warning("demó-webhook hiba: %s", type(e).__name__)


class DemoEventIn(BaseModel):
    type: str = Field(max_length=10)


@app.get("/public/neked/{slug}")
def demo_public(slug: str):
    row = store.demo_get(slug)
    if not row:
        raise HTTPException(404, "not_found")
    return Response(json.dumps(demopage.public_view(row), ensure_ascii=False), media_type="application/json",
                    headers={"Cache-Control": "no-store", "X-Robots-Tag": "noindex, nofollow"})


@app.post("/public/neked/{slug}/event")
def demo_event(slug: str, body: DemoEventIn, request: Request):
    if body.type not in ("open", "demo", "live", "cta"):
        raise HTTPException(400, "bad_event")
    ip, t = _client_ip(request), time.time()
    with _event_lock:
        _prune(_event_hits, 600, t)
        hits = [x for x in _event_hits.get(ip, []) if t - x < 600]
        if len(hits) >= 120:
            raise HTTPException(429, "slow_down")
        _event_hits[ip] = hits + [t]
    row = store.demo_get(slug)
    if not row:
        raise HTTPException(404, "not_found")
    first = store.demo_event(slug, body.type)
    if first:
        threading.Thread(target=_demo_notify, args=(row, first), daemon=True).start()
    return {"ok": True}


@app.get("/oauth/callback")
def oauth_callback(code: str = "", state: str = "", error: str = ""):
    # Jelszó nélkül érhető el, mert a Google irányít ide; a védelem az
    # aláírt, 15 percig érvényes állapot, és hogy csak a beállított fiók köthető be.
    if error:
        return RedirectResponse("/?gmail=elutasitva")
    if not gmail_api.configured() or not gmail_api.state_ok(state) or not code:
        return RedirectResponse("/?gmail=lejart")
    try:
        gmail_api.exchange(code, store)
    except AuthError as e:
        logger.warning("gmail összekötés: %s", e)
        return RedirectResponse("/?gmail=rossz_fiok" if "rossz fiók" in str(e) else "/?gmail=nincs_jog")
    except MailError as e:
        logger.warning("gmail összekötés: %s", e)
        return RedirectResponse("/?gmail=hiba")
    return RedirectResponse("/?gmail=ok")


@app.post("/api/leads/{lead_id}/answer", dependencies=[Depends(auth)])
def answer(lead_id: int):
    """Friss időpontok a naptárból és újraírt válasz az érdeklődőnek."""
    lead = store.get(lead_id)
    if not lead or lead["reply_kind"] != "interested":
        raise HTTPException(409, "Ez nem érdeklődő válasz.")
    try:
        return pipeline.prepare_answer(store, lead_id)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"Nem sikerült: {e}")


@app.post("/api/leads/{lead_id}/skip", dependencies=[Depends(auth)])
def skip(lead_id: int):
    if not store.skip(lead_id):
        raise HTTPException(409, "Ez már nem hagyható ki.")
    return {"ok": True}


@app.post("/api/followups/prepare", dependencies=[Depends(auth)])
def followups_prepare():
    # Kézi előkészítés: csak a már meglévő demóoldalakat linkeli, hogy a kérés
    # ne várjon percekig; új oldalt a lead „Demóoldal” gombja készít.
    return {"prepared": pipeline.prepare_followups(store, demo_url=_followup_demo_url(create=False))}


@app.post("/api/followups/{lead_id}/send", dependencies=[Depends(auth)])
def followup_send(lead_id: int):
    if job.running and job.kind == "küldés":
        raise HTTPException(409, "Épp küldés fut, várd meg.")
    try:
        ok, why = pipeline.send_followup(store, lead_id)
    except AuthError as e:
        raise HTTPException(502, str(e))
    if not ok:
        raise HTTPException(409, why)
    return {"ok": True}


@app.post("/api/followups/{lead_id}/drop", dependencies=[Depends(auth)])
def followup_drop(lead_id: int):
    store.drop_followup(lead_id)
    return {"ok": True}


@app.post("/api/replies/scan", dependencies=[Depends(auth)])
def replies_scan():
    return _require_start(job.start("válaszok", lambda log: pipeline.scan_replies(store, log)))


# ---- tanácsadó --------------------------------------------------------------

# Egyszerre egy kérdés: az ingyenes Gemini percenkénti kerete szűk, és két
# párhuzamos kérdés egymás elől enné el.
_advisor_lock = threading.Lock()


class AskIn(BaseModel):
    question: str = Field(min_length=1, max_length=12000)
    lead_id: int | None = None
    # A tanácsadóhoz csatolt fájlok azonosítói (/api/advisor/files).
    files: list[str] = Field(default_factory=list, max_length=6)


# Csatolt fájlok: a Gemini fájltárában vannak (kb. 48 óráig), itt csak a
# hivatkozásuk. Memóriában tartjuk; újraindulás után újra kell csatolni.
ADVISOR_FILE_MAX = 200 * 1024 * 1024
ADVISOR_FILE_TTL = timedelta(hours=46)
ADVISOR_FILE_TYPES = ("image/", "video/", "audio/", "application/pdf", "text/")
_advisor_files: dict = {}


def _advisor_file_list(ids: list[str]) -> list[dict]:
    now = datetime.now(TZ)
    for k in [k for k, v in _advisor_files.items() if now - v["at"] > ADVISOR_FILE_TTL]:
        _advisor_files.pop(k, None)
    missing = [i for i in ids if i not in _advisor_files]
    if missing:
        raise HTTPException(410, "Egy csatolt fájl már nem elérhető (újraindulás vagy lejárt). Csatold újra.")
    return [_advisor_files[i] for i in ids]


@app.post("/api/advisor/files", dependencies=[Depends(auth)])
def advisor_file(file: UploadFile = File(...)):
    mime = (file.content_type or "").split(";")[0].strip().lower()
    if not mime.startswith(ADVISOR_FILE_TYPES):
        raise HTTPException(400, "Kép, videó, hang, PDF vagy szöveg csatolható.")
    data = file.file.read(ADVISOR_FILE_MAX + 1)
    if not data:
        raise HTTPException(400, "Üres fájl.")
    if len(data) > ADVISOR_FILE_MAX:
        raise HTTPException(413, "Túl nagy fájl (legfeljebb 200 MB).")
    try:
        up = llm.upload_file(data, mime, file.filename or "fajl")
    except llm.LLMError as e:
        logger.warning("csatolás hiba: %s", e)
        raise HTTPException(502, f"A csatolás nem sikerült: {e}")
    fid = secrets.token_hex(8)
    _advisor_files[fid] = {**up, "name": (file.filename or "fájl")[:80], "at": datetime.now(TZ)}
    return {"id": fid, "name": _advisor_files[fid]["name"], "mime": up["mime"], "size": len(data)}


@app.get("/api/advisor", dependencies=[Depends(auth)])
def advisor_history():
    return {"messages": store.advisor_history(60), "web_search": websearch.tavily_on()}


@app.post("/api/advisor", dependencies=[Depends(auth)])
def advisor_ask(body: AskIn):
    if not _advisor_lock.acquire(blocking=False):
        raise HTTPException(409, "Még az előző kérdésen dolgozom, várd meg.")
    try:
        files = _advisor_file_list(body.files)
        return advisor.ask(store, body.question, body.lead_id, files)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except llm.LLMError as e:
        if "insufficient_quota" in str(e):
            raise HTTPException(429, "Elfogyott a mai ingyenes AI-keret, holnap újra megy.")
        logger.warning("tanácsadó hiba: %s", e)
        raise HTTPException(502, f"Nem sikerült választ kapni: {e}")
    finally:
        _advisor_lock.release()


@app.post("/api/advisor/clear", dependencies=[Depends(auth)])
def advisor_clear():
    store.advisor_clear()
    return {"ok": True}


class LinkedInSearchIn(BaseModel):
    sectors: list[str] = Field(default_factory=list, max_length=20)
    countries: list[str] = Field(default_factory=list, max_length=20)
    roles: list[str] = Field(default_factory=list, max_length=20)


@app.post("/api/linkedin/search", dependencies=[Depends(auth)])
def linkedin_search(body: LinkedInSearchIn):
    """Nyilvános profilok keresése keresőmotoron át. A linkedin.com-ot nem
    töltjük le, leadet nem ment, és nem küld semmit."""
    if not _advisor_lock.acquire(blocking=False):
        raise HTTPException(409, "Még az előző kérésen dolgozom, várd meg.")
    try:
        return outreach.search(store, sectors=body.sectors, countries=body.countries,
                               roles=body.roles)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except llm.LLMError as e:
        if "insufficient_quota" in str(e):
            raise HTTPException(429, "Elfogyott a mai ingyenes AI-keret, holnap újra megy.")
        logger.warning("linkedin keresés hiba: %s", e)
        raise HTTPException(502, f"Nem sikerült átnézni a találatokat: {e}")
    finally:
        _advisor_lock.release()


class LinkedInIn(BaseModel):
    profile: str = Field(max_length=outreach.MAX_PROFILE)
    note: str = Field(default="", max_length=500)
    lang: str = Field(default="hu", max_length=5)
    # Igaz, ha a szöveg a keresőmotor részletéből készül, nem bemásolt profilból.
    from_search: bool = False


@app.post("/api/linkedin/draft", dependencies=[Depends(auth)])
def linkedin_draft(body: LinkedInIn):
    """Bemásolt LinkedIn-profilból ítélet és megkeresés. Nem küld el semmit:
    a szöveget a panelről te másolod át, és te nyomsz küldést a LinkedInen."""
    # Ugyanaz a zár, mint a tanácsadónál: egyszerre egy modellhívás fusson,
    # különben két megnyitott fül elviszi a napi keretet.
    if not _advisor_lock.acquire(blocking=False):
        raise HTTPException(409, "Még az előző kérésen dolgozom, várd meg.")
    try:
        return outreach.draft(body.profile, body.note, body.lang, from_search=body.from_search)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except llm.LLMError as e:
        if "insufficient_quota" in str(e):
            raise HTTPException(429, "Elfogyott a mai ingyenes AI-keret, holnap újra megy.")
        logger.warning("linkedin megkeresés hiba: %s", e)
        raise HTTPException(502, f"Nem sikerült szöveget kapni: {e}")
    finally:
        _advisor_lock.release()


class BlockIn(BaseModel):
    items: str = Field(max_length=20000)
    reason: str = Field(default="kézzel felvéve", max_length=100)


@app.post("/api/block", dependencies=[Depends(auth)])
def block(body: BlockIn):
    n = 0
    for raw in body.items.replace(",", "\n").replace(";", "\n").splitlines():
        key = raw.strip().lower()
        if key and ("@" in key or "." in key) and len(key) < 200:
            store.block(key, body.reason)
            n += 1
    return {"added": n}


# ---- reggeli automatikus kör -----------------------------------------------
# Csak keres, vázlatot ír, válaszokat néz. Küldeni nem küld.

def _auto_on() -> bool:
    return (os.environ.get("AUTO_RESEARCH") or "").strip().lower() in ("1", "true", "yes")


# Minden célország egyenlő súllyal: körönként annyi ország jön sorra, amennyi
# belefér egy futás keretébe (pipeline.MAX_PER_RUN), és a következő kör ott
# folytatja, ahol ez abbahagyta. Az AUTO_PLAN csak a darabszámot írja felül
# (XX:0 kizár egy országot).
PER_COUNTRY = 2


def _auto_plan(rotate: bool = True) -> dict[str, int]:
    raw = os.environ.get("AUTO_PLAN", "")
    base = {c: PER_COUNTRY for c in COUNTRIES}
    for part in raw.split(","):
        if ":" in part:
            k, v = part.split(":", 1)
            if k.strip().upper() in COUNTRIES and v.strip().isdigit():
                base[k.strip().upper()] = int(v)
    order = [c for c in COUNTRIES if base[c] > 0 and playbook.country_ready(c)]
    plan = {c: 0 for c in COUNTRIES}
    if not order:
        return plan
    try:
        start = int(store.get_setting("plan_cursor") or 0) % len(order)
    except ValueError:
        start = 0
    total, taken = 0, 0
    for i in range(len(order)):
        c = order[(start + i) % len(order)]
        n = min(base[c], pipeline.MAX_PER_RUN)
        if total + n > pipeline.MAX_PER_RUN:
            break
        plan[c] = n
        total += n
        taken += 1
    if rotate:
        store.set_setting("plan_cursor", str((start + taken) % len(order)))
    return plan


def _morning(log):
    before = {l["id"] for l in store.list("draft")}
    replied_before = {l["id"] for l in store.list() if l["reply_kind"] != "none"}
    try:
        pipeline.scan_replies(store, log)
    except (AuthError, MailError) as e:
        log.say(f"Válaszfigyelés kimaradt: {e}")
    n = pipeline.prepare_followups(store, demo_url=_followup_demo_url(create=True))
    log.say(f"{n} utánkövetés vár jóváhagyásra.")
    auto_sent: list[dict] = []
    try:
        pipeline.research_run(store, _auto_plan(), log)
        _draft_demos(before, log)
        try:
            auto_sent = pipeline.auto_send(store, log, now=datetime.now(TZ))
        except Exception as e:  # noqa: BLE001 — a küldés hibája ne vigye el az összefoglalót
            logger.exception("magától küldés hiba")
            log.say(f"Magától küldés hiba: {e}")
    finally:
        _notify(log, before, replied_before, auto_sent)


def _notify(log, before: set, replied_before: set, auto_sent: list[dict] | None = None) -> None:
    """Összefoglaló e-mail a tulajdonosnak minden automatikus kör után."""
    to = os.environ.get("NOTIFY_TO", "").strip()
    if not to:
        return
    leads = store.list()
    new_drafts = [l for l in leads if l["status"] == "draft" and l["id"] not in before]
    new_replies = [l for l in leads if l["reply_kind"] != "none" and l["id"] not in replied_before]
    interested = [l for l in new_replies if l["reply_kind"] == "interested"]
    due = [l for l in leads if l["followup_status"] == "draft"]
    auto_sent = auto_sent or []
    new_drafts = [l for l in new_drafts if l["id"] not in {a["id"] for a in auto_sent}]
    parts = [f"{len(new_drafts)} új vázlat"]
    if auto_sent:
        parts.append(f"{len(auto_sent)} magától elküldve")
    if interested:
        parts.insert(0, f"{len(interested)} ÉRDEKLŐDŐ")
    if new_replies:
        parts.append(f"{len(new_replies)} új válasz")
    subject = "AXIMBRA értékesítő: " + ", ".join(parts)
    lines = []
    if interested:
        lines += ["ÉRDEKLŐDNEK — a válasz időpontokkal kész a Válaszok fülön:"]
        lines += [f"  • {l['company']} ({l['email']})" for l in interested] + [""]
    if new_replies and len(new_replies) > len(interested):
        lines += ["Egyéb válaszok:"]
        lines += [f"  • {l['company']}: {l['reply_kind']}" for l in new_replies if l["reply_kind"] != "interested"] + [""]
    if auto_sent:
        lines += [f"Magától elküldve ({len(auto_sent)}):"]
        lines += [f"  • {l['score']}  {l['company']} ({l['email']})" for l in auto_sent] + [""]
    stopped = [x for x in log.lines if x.startswith(("VÉSZFÉK", "Magától küldés kikapcsolva"))]
    if stopped:
        subject = "VÉSZFÉK — " + subject
        lines += stopped + [""]
    if new_drafts:
        lines += [f"Új vázlatok ({len(new_drafts)}), pontszám szerint:"]
        lines += [f"  • {l['score'] or '–'}  {l['company']} ({l['town'] or l['country']})"
                  for l in sorted(new_drafts, key=lambda x: -(x["score"] or 0))] + [""]
    if due:
        lines += [f"Utánkövetésre vár: {len(due)} cég.", ""]
    lines += [f"Ma elküldve: {store.sent_today()}/{pipeline.DAILY_CAP}", "",
              "Panel: " + os.environ.get("PANEL_URL", "https://aximbra-sales-production.up.railway.app")]
    try:
        mailer.send(mailer.build_message(to, subject, "\n".join(lines)))
        log.say(f"Értesítés elküldve: {to}")
    except Exception as e:  # noqa: BLE001 — az értesítés hibája ne rontsa el a kört
        log.say(f"Az értesítést nem tudtam elküldeni ({e}).")


def auto_times() -> list[str]:
    """AUTO_TIMES, pl. "10:00,19:00" (budapesti idő), minden nap."""
    out = []
    for part in os.environ.get("AUTO_TIMES", "10:00,19:00").replace(";", ",").split(","):
        part = part.strip()
        try:
            h, m = (int(x) for x in part.split(":"))
            if 0 <= h < 24 and 0 <= m < 60:
                out.append(f"{h:02d}:{m:02d}")
        except ValueError:
            continue
    return sorted(set(out))


# Meddig pótolja a kört az időpont után. A szolgáltatás tétlenül alszik, és
# kívülről (GitHub Actions, .github/workflows/wake.yml) ébresztjük; az ütemezett
# futás ott akár fél órát is késhet, ezért nem elég a régi 30 perc.
SLOT_GRACE_MIN = 90


def due_slot(now: datetime, times: list[str], done: set) -> str | None:
    """Az esedékes időpont, ha még nem futott le ma. SLOT_GRACE_MIN percig
    pótolja (késő ébresztés, foglalt gép); utána kihagyja."""
    for t in times:
        h, m = (int(x) for x in t.split(":"))
        start = now.replace(hour=h, minute=m, second=0, microsecond=0)
        key = f"{now.date()} {t}"
        if key not in done and start <= now < start + timedelta(minutes=SLOT_GRACE_MIN):
            return key
    return None


def _reply_watch() -> int:
    """Gyors válaszfigyelés két kör között. Csak ha jött új válasz, akkor
    szól a tulajdonosnak; a vázlatokról a kör értesítése szól."""
    log = pipeline.RunLog()
    drafts = {l["id"] for l in store.list("draft")}
    replied_before = {l["id"] for l in store.list() if l["reply_kind"] != "none"}
    pipeline.scan_replies(store, log)
    new = [l for l in store.list() if l["reply_kind"] != "none" and l["id"] not in replied_before]
    if new:
        _notify(log, drafts, replied_before)
    return len(new)


def _load_done() -> set:
    """A már lefutott körök. Az adatbázisban tartjuk, nem a memóriában: a
    szolgáltatás alszik, és minden ébredés újraindítás — memóriában tartva egy
    második ébresztés ugyanabban az ablakban újra kiküldené a kört."""
    try:
        return set(json.loads(store.get_setting("auto_done") or "[]"))
    except ValueError:
        return set()


def _scheduler():
    done: set = _load_done()
    last_watch = None
    while True:
        try:
            now = datetime.now(TZ)
            key = due_slot(now, auto_times(), done) if _auto_on() else None
            if key and job.start(f"automatikus kör ({key[-5:]})", _morning):
                done.add(key)
                done = {k for k in done if k[:10] >= (now.date() - timedelta(days=2)).isoformat()}
                store.set_setting("auto_done", json.dumps(sorted(done)))
            elif _auto_on() and not job.running and pipeline.reply_watch_due(now, last_watch):
                last_watch = now
                try:
                    _reply_watch()
                except (AuthError, MailError) as e:
                    logger.warning("válaszfigyelés kimaradt: %s", e)
            if content.enabled() and content.due(now, store):
                threading.Thread(target=_content_round, args=(now,), daemon=True).start()
        except Exception:  # noqa: BLE001
            logger.exception("ütemező hiba")
        time.sleep(30)


@app.post("/api/content/run")
def content_run(x_agent_token: str = Header(default="")):
    """A napi két téma legyártása és átadása a videós agentnek — a Make ütemezője hívja.
    Ugyanazon a napon újrahívva nem ír új témát és nem küld duplán (content.run)."""
    want = os.environ.get("AGENT_TOKEN", "")
    if len(want) < 24:
        raise HTTPException(503, "Nincs beállítva AGENT_TOKEN.")
    if not secrets.compare_digest(x_agent_token.encode(), want.encode()):
        time.sleep(1)
        raise HTTPException(401, "Hibás kulcs.")
    try:
        sent = content.run(store, datetime.now(TZ))
    except Exception as e:  # noqa: BLE001 — a Make lássa a hibát, és újrapróbálhassa
        raise HTTPException(502, f"tartalomkör hiba: {e}")
    return {"ok": True, "sent": sent}


def _content_round(now: datetime) -> None:
    """Napi két téma a videós agentnek. A hibát naplózzuk; RETRY_MIN perc múlva újra."""
    try:
        content.run(store, now)
    except Exception as e:  # noqa: BLE001
        logger.warning("tartalomtéma kimaradt: %s", e)


@app.on_event("startup")
def _startup():
    stuck = store.list("sending")
    if stuck:
        logger.warning("%d levél 'sending' állapotban maradt — kézi ellenőrzés kell", len(stuck))
    threading.Thread(target=_scheduler, daemon=True).start()
