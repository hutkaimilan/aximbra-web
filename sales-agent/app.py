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
from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from pydantic import BaseModel, Field

import pipeline
from mailer import AuthError, MailError
from playbook import COUNTRIES
from store import Store

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("sales")

app = FastAPI(title="AXIMBRA értékesítő", docs_url=None, redoc_url=None, openapi_url=None)
security = HTTPBasic()
store = Store()
HERE = os.path.dirname(os.path.abspath(__file__))
TZ = ZoneInfo("Europe/Budapest")


def auth(creds: HTTPBasicCredentials = Depends(security)):
    pw = os.environ.get("ADMIN_PASSWORD", "")
    if len(pw) < 10:
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
        "leads": store.list(),
        "blocked": store.blocked_keys()[:300],
        "sent_today": store.sent_today(),
        "cap": pipeline.DAILY_CAP,
        "countries": {k: v["name"] for k, v in COUNTRIES.items()},
        "config": {
            "gmail": bool(os.environ.get("GMAIL_USER") and os.environ.get("GMAIL_APP_PASSWORD")),
            "openai": bool(os.environ.get("OPENAI_API_KEY")),
            "auto": _auto_on(),
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
    ids = [i for i in body.ids if isinstance(i, int)][:pipeline.DAILY_CAP]
    if not ids:
        raise HTTPException(400, "Nincs kijelölt levél.")
    return _require_start(job.start("küldés", lambda log: pipeline.send_many(store, ids, log)))


class EditIn(BaseModel):
    subject: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=20, max_length=5000)


@app.post("/api/leads/{lead_id}", dependencies=[Depends(auth)])
def edit(lead_id: int, body: EditIn):
    if not store.edit(lead_id, body.subject.strip(), body.body.strip()):
        raise HTTPException(409, "Ez már nem szerkeszthető.")
    return {"ok": True}


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


def _auto_plan() -> dict[str, int]:
    raw = os.environ.get("AUTO_PLAN", "HU:10,SK:2,RO:2,HR:1")
    plan = {}
    for part in raw.split(","):
        if ":" in part:
            k, v = part.split(":", 1)
            if k.strip().upper() in COUNTRIES and v.strip().isdigit():
                plan[k.strip().upper()] = int(v)
    return plan


def _morning(log):
    try:
        pipeline.scan_replies(store, log)
    except (AuthError, MailError) as e:
        log.say(f"Válaszfigyelés kimaradt: {e}")
    n = pipeline.prepare_followups(store)
    log.say(f"{n} utánkövetés vár jóváhagyásra.")
    pipeline.research_run(store, _auto_plan(), log)


def _scheduler():
    last = None
    while True:
        try:
            now = datetime.now(TZ)
            if _auto_on() and now.weekday() < 5 and now.hour == 7 and last != now.date():
                if job.start("reggeli kör", _morning):
                    last = now.date()
        except Exception:  # noqa: BLE001
            logger.exception("ütemező hiba")
        time.sleep(60)


@app.on_event("startup")
def _startup():
    stuck = store.list("sending")
    if stuck:
        logger.warning("%d levél 'sending' állapotban maradt — kézi ellenőrzés kell", len(stuck))
    threading.Thread(target=_scheduler, daemon=True).start()
