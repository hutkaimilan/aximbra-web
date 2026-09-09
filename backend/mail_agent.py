"""E-mail rendező agent, demó módban, az AXIMBRA oldalba építve.

Szándékosan más, mint egy fiókos szolgáltatás:
  * semmit nem tárol adatbázisban - a futás a memóriában él, és lejár,
  * semmit nem ír vissza a látogató postafiókjába (nincs csillag, címke, kuka),
  * semmit nem küld el: a küldés-típusú Gmail-hívások kódszinten tiltottak,
  * a munkamenet a böngésző bezárásakor és kilépéskor is megszűnik.
"""
import asyncio
import base64
import json
import logging
import os
import re
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from cryptography.fernet import Fernet
from google_auth_oauthlib.flow import Flow
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build, Resource

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/agent/email")

GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "")
GMAIL_REDIRECT_URI = os.environ.get("AGENT_REDIRECT_URI", "")
SITE_URL = os.environ.get("FRONTEND_URL", "")

# No account outlives a visit, so a per-process key is enough. Setting
# AGENT_SESSION_KEY only matters if the service ever runs more than one replica.
_fernet = Fernet((os.environ.get("AGENT_SESSION_KEY") or Fernet.generate_key().decode()).encode())

GMAIL_SCOPES = [
    "https://www.googleapis.com/auth/gmail.modify",
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
]

SESSION_COOKIE = "aximbra_agent"
SESSION_TTL_SECONDS = 30 * 60
MAX_EMAILS = 15
MAX_SESSIONS = 40
LOOKBACK_DAYS = 30

_sessions: dict = {}
_oauth_states: dict = {}


# ---------- Never send ----------
# gmail.modify is technically enough to call messages.send, so the guarantee
# cannot rest on the scope alone. This proxy refuses every send-type call.
class SafeGmailProxy:
    def __init__(self, target):
        object.__setattr__(self, "_target", target)

    def __getattr__(self, name):
        if name == "send":
            raise PermissionError("TILTOTT Gmail művelet: az agent soha nem küld e-mailt.")
        attr = getattr(object.__getattribute__(self, "_target"), name)
        if callable(attr) and not isinstance(attr, Resource):
            def wrapped(*args, **kwargs):
                result = attr(*args, **kwargs)
                return SafeGmailProxy(result) if isinstance(result, Resource) else result
            return wrapped
        if isinstance(attr, Resource):
            return SafeGmailProxy(attr)
        return attr


# ---------- Session ----------
def _new_state() -> dict:
    return {"running": False, "total": 0, "done": 0, "errors": 0, "message": ""}


def _sweep():
    now = datetime.now(timezone.utc)
    for key, sess in list(_sessions.items()):
        if (now - sess["created_at"]).total_seconds() > SESSION_TTL_SECONDS:
            _sessions.pop(key, None)


def _read_session(request: Request):
    raw = request.cookies.get(SESSION_COOKIE)
    if not raw:
        return None
    try:
        return _fernet.decrypt(raw.encode(), ttl=SESSION_TTL_SECONDS).decode()
    except Exception:  # noqa - forged, tampered or expired
        return None


def _session(request: Request):
    _sweep()
    sid = _read_session(request)
    return _sessions.get(sid) if sid else None


def _require(request: Request) -> dict:
    sess = _session(request)
    if not sess:
        raise HTTPException(status_code=401, detail="Nincs aktív munkamenet. Csatlakozz újra.")
    return sess


def _flow():
    if not (GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET and GMAIL_REDIRECT_URI):
        raise HTTPException(status_code=503, detail="Az agent Google-hozzáférése nincs beállítva.")
    return Flow.from_client_config(
        {"web": {
            "client_id": GOOGLE_CLIENT_ID,
            "client_secret": GOOGLE_CLIENT_SECRET,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
        }},
        scopes=GMAIL_SCOPES,
        redirect_uri=GMAIL_REDIRECT_URI,
    )


# ---------- Mail parsing ----------
def _header(headers, name):
    for h in headers:
        if h.get("name", "").lower() == name.lower():
            return h.get("value", "")
    return ""


def _decode(data):
    if not data:
        return ""
    return base64.urlsafe_b64decode(data.encode("UTF-8")).decode("utf-8", errors="replace")


def _body(payload):
    plain, html = "", ""

    def walk(p):
        nonlocal plain, html
        mime, body = p.get("mimeType", ""), p.get("body", {})
        if mime == "text/plain" and body.get("data"):
            plain += _decode(body["data"])
        elif mime == "text/html" and body.get("data"):
            html += _decode(body["data"])
        for sub in p.get("parts", []) or []:
            walk(sub)

    walk(payload)
    if plain.strip():
        return plain.strip()
    if html.strip():
        t = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html, flags=re.S | re.I)
        return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", t)).strip()
    return ""


def _parse(msg):
    payload = msg.get("payload", {})
    headers = payload.get("headers", [])
    date_iso = None
    raw_date = _header(headers, "Date")
    if raw_date:
        try:
            date_iso = parsedate_to_datetime(raw_date).astimezone(timezone.utc).isoformat()
        except Exception:  # noqa
            date_iso = None
    return {
        "id": msg.get("id"),
        "sender": _header(headers, "From"),
        "subject": _header(headers, "Subject") or "(nincs tárgy)",
        "snippet": msg.get("snippet", ""),
        "date": date_iso,
        "body": _body(payload),
    }


# ---------- Routes ----------
@router.get("/status")
async def status(request: Request):
    sess = _session(request)
    return {
        "connected": bool(sess),
        "email": sess["email"] if sess else None,
        "configured": bool(GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET and GMAIL_REDIRECT_URI),
    }


@router.get("/connect")
async def connect():
    flow = _flow()
    url, state = flow.authorization_url(
        access_type="online", prompt="consent", include_granted_scopes="false"
    )
    _oauth_states[state] = {
        "code_verifier": flow.code_verifier,
        "created_at": datetime.now(timezone.utc),
    }
    for key, val in list(_oauth_states.items()):
        if (datetime.now(timezone.utc) - val["created_at"]).total_seconds() > 900:
            _oauth_states.pop(key, None)
    return {"auth_url": url}


@router.get("/callback")
async def callback(code: str = "", state: str = "", error: str = ""):
    target = f"{SITE_URL}/demo/email-agent"
    if error:
        return RedirectResponse(f"{target}?error=access_denied")
    st = _oauth_states.pop(state, None)
    if not st:
        return RedirectResponse(f"{target}?error=invalid_state")
    try:
        flow = _flow()
        flow.code_verifier = st["code_verifier"]
        flow.fetch_token(code=code)
        creds = flow.credentials
        service = SafeGmailProxy(build("gmail", "v1", credentials=creds))
        email = service.users().getProfile(userId="me").execute().get("emailAddress", "")
        if not email:
            return RedirectResponse(f"{target}?error=no_email")
        _sweep()
        if len(_sessions) >= MAX_SESSIONS:
            return RedirectResponse(f"{target}?error=busy")
        sid = os.urandom(16).hex()
        _sessions[sid] = {
            "email": email,
            "creds_json": creds.to_json(),
            "analyses": [],
            "state": _new_state(),
            "created_at": datetime.now(timezone.utc),
        }
    except Exception as e:  # noqa - never 500 into the browser
        logger.error("agent oauth failed: %s", type(e).__name__)
        return RedirectResponse(f"{target}?error=token_exchange")
    response = RedirectResponse(f"{target}?connected=1")
    # No max-age: the run ends with the browser session, never outliving the visit.
    response.set_cookie(
        SESSION_COOKIE, _fernet.encrypt(sid.encode()).decode(),
        httponly=True, secure=True, samesite="lax", path="/",
    )
    asyncio.create_task(run_agent(sid))
    return response


@router.post("/disconnect")
async def disconnect(request: Request, response: Response):
    sid = _read_session(request)
    if sid:
        _sessions.pop(sid, None)
    response.delete_cookie(SESSION_COOKIE, path="/")
    return {"ok": True}


@router.get("/progress")
async def progress(request: Request):
    return _require(request)["state"]


@router.get("/results")
async def results(request: Request):
    sess = _require(request)
    docs = sorted(
        sess["analyses"],
        key=lambda d: (-(d.get("urgency") or 0), d.get("date") or ""),
    )
    counts = {}
    for d in docs:
        counts[d["category"]] = counts.get(d["category"], 0) + 1
    return {
        "email": sess["email"],
        "analyses": docs,
        "counts": counts,
        "total": len(docs),
        "needs_reply": len([d for d in docs if d.get("needs_reply") == "igen"]),
        "top_urgent": docs[:3],
    }


async def run_agent(sid: str):
    """Read-only pass over the visitor's last 30 days. Imported lazily so the
    classifier's OpenAI client is only touched when a run actually starts."""
    from server import classify_one  # noqa: circular by design, runtime only

    sess = _sessions.get(sid)
    if not sess:
        return
    state = sess["state"]
    if state["running"]:
        return
    creds = Credentials.from_authorized_user_info(json.loads(sess["creds_json"]), GMAIL_SCOPES)
    service = SafeGmailProxy(build("gmail", "v1", credentials=creds))
    state.update({"running": True, "message": "Levelek lekérése…"})
    try:
        after = int((datetime.now(timezone.utc) - timedelta(days=LOOKBACK_DAYS)).timestamp())
        listing = service.users().messages().list(
            userId="me", maxResults=MAX_EMAILS, q=f"after:{after}"
        ).execute()
        ids = [m["id"] for m in listing.get("messages", [])]
        state["total"] = len(ids)
        state["message"] = "Feldolgozás folyamatban…"
        for mid in ids:
            if sid not in _sessions:  # visitor left mid-run
                return
            try:
                full = service.users().messages().get(userId="me", id=mid, format="full").execute()
                email = _parse(full)
                analysis = await classify_one(email)
                sess["analyses"].append({**email, **analysis})
            except Exception as e:  # noqa - one bad email must not stop the rest
                logger.warning("agent email failed: %s", type(e).__name__)
                state["errors"] += 1
            finally:
                state["done"] += 1
        state["message"] = "Kész"
    finally:
        state["running"] = False
