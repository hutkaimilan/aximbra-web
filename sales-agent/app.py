"""AXIMBRA értékesítő — a belső felület és az API.

Egy felhasználó, egy jelszó (ADMIN_PASSWORD, HTTP Basic). Egyszerre egy
háttérmunka futhat: keresés, küldés vagy válaszfigyelés. Magától csak
keres és vázlatot ír (ha AUTO_RESEARCH be van kapcsolva); elküldeni mindig
ember küldi, egy gombbal.
"""
import logging
import os
import secrets
import threading
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import FileResponse, RedirectResponse, Response
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from pydantic import BaseModel, Field

import advisor
import content
import gmail_api
import llm
import websearch
import mailer
import pipeline
import verify
from mailer import AuthError, MailError
from playbook import COUNTRIES
from store import Store

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("sales")

app = FastAPI(title="AXIMBRA értékesítő", docs_url=None, redoc_url=None, openapi_url=None)
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


def auth(creds: HTTPBasicCredentials = Depends(security)):
    pw = os.environ.get("ADMIN_PASSWORD", "")
    if len(pw) < 8:
        raise HTTPException(503, "Nincs beállítva elég hosszú ADMIN_PASSWORD.")
    ok = secrets.compare_digest(creds.password.encode(), pw.encode())
    if not ok:
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
    return FileResponse(os.path.join(HERE, "static", "index.html"))


@app.get("/api/state", dependencies=[Depends(auth)])
def state():
    return {
        "job": job.state(),
        "leads": [dict(l, mixed=bool(l["status"] == "draft" and verify.mixed_language(l)),
                       rules=verify.rule_violations(l) if l["status"] in ("draft", "failed") else [])
                  for l in store.list()],
        "blocked": store.blocked_keys()[:300],
        "sent_today": store.sent_today(),
        "stats": store.stats(),
        "focus": store.best_sectors(),
        "cap": pipeline.DAILY_CAP,
        "auto_send": {"on": store.get_setting("auto_send") == "on", "sent_today": store.auto_sent_today(),
                      **pipeline.readiness(store)},
        "countries": {k: v["name"] for k, v in COUNTRIES.items()},
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
    return _require_start(job.start("keresés", lambda log: pipeline.research_run(store, plan, log)))


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
    return {"prepared": pipeline.prepare_followups(store)}


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
    question: str = Field(min_length=1, max_length=4000)
    lead_id: int | None = None


@app.get("/api/advisor", dependencies=[Depends(auth)])
def advisor_history():
    return {"messages": store.advisor_history(60), "web_search": websearch.tavily_on()}


@app.post("/api/advisor", dependencies=[Depends(auth)])
def advisor_ask(body: AskIn):
    if not _advisor_lock.acquire(blocking=False):
        raise HTTPException(409, "Még az előző kérdésen dolgozom, várd meg.")
    try:
        return advisor.ask(store, body.question, body.lead_id)
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


# Minden célországban keres; az AUTO_PLAN csak felülírja a darabszámot
# (XX:0 kizár egy országot).
DEFAULT_PLAN = {"HU": 8, "SK": 2, "RO": 2, "HR": 1, "SI": 1, "GB": 2, "IE": 1, "FR": 2, "BE": 1}


def _auto_plan() -> dict[str, int]:
    raw = os.environ.get("AUTO_PLAN", "")
    plan = {c: DEFAULT_PLAN.get(c, 1) for c in COUNTRIES}
    for part in raw.split(","):
        if ":" in part:
            k, v = part.split(":", 1)
            if k.strip().upper() in COUNTRIES and v.strip().isdigit():
                plan[k.strip().upper()] = int(v)
    return plan


def _morning(log):
    before = {l["id"] for l in store.list("draft")}
    replied_before = {l["id"] for l in store.list() if l["reply_kind"] != "none"}
    try:
        pipeline.scan_replies(store, log)
    except (AuthError, MailError) as e:
        log.say(f"Válaszfigyelés kimaradt: {e}")
    n = pipeline.prepare_followups(store)
    log.say(f"{n} utánkövetés vár jóváhagyásra.")
    auto_sent: list[dict] = []
    try:
        pipeline.research_run(store, _auto_plan(), log)
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


def due_slot(now: datetime, times: list[str], done: set) -> str | None:
    """Az esedékes időpont, ha még nem futott le ma. 30 percig pótolja,
    ha épp egy másik munka foglalta a gépet; utána kihagyja."""
    for t in times:
        h, m = (int(x) for x in t.split(":"))
        start = now.replace(hour=h, minute=m, second=0, microsecond=0)
        key = f"{now.date()} {t}"
        if key not in done and start <= now < start + timedelta(minutes=30):
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


def _scheduler():
    done: set = set()
    last_watch = None
    while True:
        try:
            now = datetime.now(TZ)
            key = due_slot(now, auto_times(), done) if _auto_on() else None
            if key and job.start(f"automatikus kör ({key[-5:]})", _morning):
                done.add(key)
                done = {k for k in done if k[:10] >= (now.date() - timedelta(days=2)).isoformat()}
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
