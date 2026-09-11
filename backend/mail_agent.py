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
from email.message import EmailMessage
from email.utils import parsedate_to_datetime

from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from fastapi.responses import RedirectResponse
from cryptography.fernet import Fernet
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build, Resource

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/agent/email")

GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "")
GMAIL_REDIRECT_URI = os.environ.get("AGENT_REDIRECT_URI", "")
SITE_URL = os.environ.get("FRONTEND_URL", "")

# Whether strangers may hand this agent their mailbox.
#
# gmail.readonly is a Google *restricted* scope: offering it publicly needs a
# verified app, a published privacy notice and a named data controller the
# visitor can identify. Set AGENT_PUBLIC=false to keep the agent reachable for
# your own testing while the page tells visitors it is not open yet, instead of
# walking them into Google's "unverified app" warning.
#
# Default true so that deploying this change does not silently switch off a
# running demo; flip it deliberately.
def _env_flag(name: str, default: bool = True) -> bool:
    """Read a boolean env var. Anything unset keeps the default, so a typo turns
    into the safe value rather than silently flipping behaviour."""
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    return raw.strip().lower() not in ("false", "0", "no", "off")


AGENT_PUBLIC = _env_flag("AGENT_PUBLIC", default=True)

# No account outlives a visit, so a per-process key is enough. Setting
# AGENT_SESSION_KEY only matters if the service ever runs more than one replica.
_fernet = Fernet((os.environ.get("AGENT_SESSION_KEY") or Fernet.generate_key().decode()).encode())

# Two scope sets, chosen by the visitor at connect time.
#
# READ is the default. users.getProfile, messages.list and messages.get are all
# covered by gmail.readonly, and that is all the page asks for unless the visitor
# deliberately ticks the draft-writing box.
#
# COMPOSE adds gmail.compose, which is what Gmail requires to put a draft in
# someone's mailbox. Be clear-eyed about it: Google has no draft-only scope, so
# gmail.compose also *permits* sending, and the consent screen says so. This code
# never sends — SafeGmailProxy refuses every send-type call and a test holds that
# line — but the grant is wider than what we use, and the page states that in
# those words before the box can be ticked.
GMAIL_SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
]

COMPOSE_SCOPE = "https://www.googleapis.com/auth/gmail.compose"
GMAIL_SCOPES_COMPOSE = [*GMAIL_SCOPES, COMPOSE_SCOPE]

SESSION_HEADER = "X-Agent-Session"
SESSION_TTL_SECONDS = 30 * 60
MAX_EMAILS = 50
# How many emails are fetched and classified at once. Deliberately small: it is
# the knob that trades run time against rate limits and budget overshoot, and 5
# turns a ~50-call sequential crawl into something a visitor will wait through.
RUN_CONCURRENCY = 5
MAX_SESSIONS = 40
LOOKBACK_DAYS = 30
# Drafts are the most expensive call here (longer output than a classification),
# and they are user-triggered rather than part of the run, so they get their own
# per-session cap on top of the shared daily ceiling.
MAX_DRAFTS_PER_SESSION = 6

_sessions: dict = {}
_oauth_states: dict = {}
# asyncio only holds weak references to running tasks, so a fire-and-forget run
# can be garbage collected mid-pass. Hold it until it finishes.
_runs: set = set()


# ---------- Sending is opt-in, per call site ----------
# The scope cannot carry this guarantee: gmail.compose permits sending, so any
# code path holding the service object could send. This proxy refuses send by
# default, and the refusal travels down the chain — a Resource reached through a
# refusing proxy refuses too. Only a proxy built explicitly with allow_send=True
# can send, which is exactly one endpoint (/draft/send), reached only after the
# user confirms that specific message. Everything else — the mailbox pass, the
# draft save — holds a refusing proxy and physically cannot send.
class SafeGmailProxy:
    def __init__(self, target, allow_send: bool = False):
        object.__setattr__(self, "_target", target)
        object.__setattr__(self, "_allow_send", allow_send)

    def __getattr__(self, name):
        allow_send = object.__getattribute__(self, "_allow_send")
        if name == "send" and not allow_send:
            raise PermissionError(
                "TILTOTT Gmail művelet: ez az útvonal nem küldhet e-mailt."
            )
        attr = getattr(object.__getattribute__(self, "_target"), name)
        if callable(attr) and not isinstance(attr, Resource):
            def wrapped(*args, **kwargs):
                result = attr(*args, **kwargs)
                return SafeGmailProxy(result, allow_send) if isinstance(result, Resource) else result
            return wrapped
        if isinstance(attr, Resource):
            return SafeGmailProxy(attr, allow_send)
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
    """The site and the API sit on different hosts, so a cookie would be
    cross-site and browsers would not send it. The token travels in a header
    instead, which also keeps the run out of any long-lived browser storage."""
    raw = request.headers.get(SESSION_HEADER, "")
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


def _granted_compose(creds, requested: bool) -> bool:
    """Did Google actually grant draft-writing access?

    The consent screen lets a visitor untick individual scopes, so what we asked
    for and what we got can differ. google-auth exposes the granted list on the
    credentials when the token response carried one; when it does not, fall back
    to what was requested — the first Gmail call would fail anyway, and this keeps
    the page from offering a button that cannot work.
    """
    granted = getattr(creds, "granted_scopes", None) or getattr(creds, "scopes", None)
    if not granted:
        return requested
    return COMPOSE_SCOPE in granted


def _flow(with_compose: bool = False):
    """OAuth flow. `with_compose` is set only when the visitor asked for draft
    writing on the page — it is never the default."""
    if not AGENT_PUBLIC:
        raise HTTPException(
            status_code=503,
            detail="Az e-mail agent jelenleg nem nyilvános. Írj nekünk, és megmutatjuk élőben.",
        )
    if not (GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET and GMAIL_REDIRECT_URI):
        raise HTTPException(status_code=503, detail="Az agent Google-hozzáférése nincs beállítva.")
    return Flow.from_client_config(
        {"web": {
            "client_id": GOOGLE_CLIENT_ID,
            "client_secret": GOOGLE_CLIENT_SECRET,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
        }},
        scopes=GMAIL_SCOPES_COMPOSE if with_compose else GMAIL_SCOPES,
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
        # Kept for threading a reply draft onto the original conversation. Without
        # these, a draft lands in Gmail as a brand-new thread and reads as a
        # different message than the one it answers.
        "thread_id": msg.get("threadId"),
        "message_id": _header(headers, "Message-Id") or _header(headers, "Message-ID"),
        "references": _header(headers, "References"),
        "reply_to": _header(headers, "Reply-To"),
    }


# ---------- Routes ----------
@router.get("/status")
async def status(request: Request):
    sess = _session(request)
    return {
        "connected": bool(sess),
        "email": sess["email"] if sess else None,
        "configured": bool(GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET and GMAIL_REDIRECT_URI),
        # Distinct from `configured`: credentials can be present while the agent
        # is deliberately not offered to the public yet.
        "public": AGENT_PUBLIC,
        # Whether this session may write drafts into the mailbox. False unless the
        # visitor ticked the box *and* Google granted it.
        "can_draft": bool(sess and sess.get("can_draft")),
    }


@router.get("/connect")
async def connect(drafts: bool = False):
    """`drafts=true` asks Google for draft-writing access as well.

    It comes from a box the visitor ticks, never from a default, and it is carried
    through the OAuth state so the callback builds the flow with the same scopes —
    a mismatch there makes Google reject the exchange.
    """
    flow = _flow(with_compose=drafts)
    url, state = flow.authorization_url(
        access_type="online", prompt="consent", include_granted_scopes="false"
    )
    _oauth_states[state] = {
        "code_verifier": flow.code_verifier,
        "with_compose": drafts,
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
        flow = _flow(with_compose=bool(st.get("with_compose")))
        flow.code_verifier = st["code_verifier"]
        # google-auth-oauthlib and googleapiclient are synchronous (requests under
        # the hood). Called inline they would block the whole event loop, stalling
        # every other request on the site. Hand them to a worker thread instead.
        await asyncio.to_thread(flow.fetch_token, code=code)
        creds = flow.credentials
        service = SafeGmailProxy(await asyncio.to_thread(build, "gmail", "v1", credentials=creds))
        profile = await asyncio.to_thread(service.users().getProfile(userId="me").execute)
        email = profile.get("emailAddress", "")
        if not email:
            return RedirectResponse(f"{target}?error=no_email")
        _sweep()
        if len(_sessions) >= MAX_SESSIONS:
            return RedirectResponse(f"{target}?error=busy")
        sid = os.urandom(16).hex()
        _sessions[sid] = {
            "email": email,
            # What Google actually granted, not what we asked for. A visitor can
            # untick scopes on the consent screen, so asking is not receiving —
            # and an endpoint that trusted the request would fail later, inside a
            # Gmail call, instead of saying so up front.
            "can_draft": _granted_compose(creds, requested=bool(st.get("with_compose"))),
            # Drafts the visitor asked for, keyed by "<email id>:<tone>" so asking
            # for the same one twice is free. Dies with the session like everything
            # else here.
            "drafts": {},
            # Gmail draft ids by email id, so a second confirmation updates the
            # draft it already created instead of littering the mailbox.
            "saved": {},
            # Message ids of replies actually sent, so one email cannot be
            # answered twice by a double click or a replayed request.
            "sent": {},
            # Kept as the live object: the run is in-memory only, and an online
            # grant has no refresh token to rebuild credentials from.
            "creds": creds,
            "analyses": [],
            "state": _new_state(),
            "created_at": datetime.now(timezone.utc),
        }
    except Exception as e:  # noqa - never 500 into the browser
        logger.error("agent oauth failed: %s", type(e).__name__)
        return RedirectResponse(f"{target}?error=token_exchange")
    token = _fernet.encrypt(sid.encode()).decode()
    task = asyncio.create_task(run_agent(sid))
    _runs.add(task)
    task.add_done_callback(_runs.discard)
    return RedirectResponse(f"{target}?connected=1&s={token}")


@router.post("/disconnect")
async def disconnect(request: Request, s: str = ""):
    """Accepts the token in the header, or as ?s= for sendBeacon on page exit,
    which cannot set headers."""
    sid = _read_session(request)
    if not sid and s:
        try:
            sid = _fernet.decrypt(s.encode(), ttl=SESSION_TTL_SECONDS).decode()
        except Exception:  # noqa
            sid = None
    if sid:
        _sessions.pop(sid, None)
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


class DraftBody(BaseModel):
    id: str
    tone: Literal["hivatalos", "kozvetlen"] = "hivatalos"


@router.post("/draft")
async def draft(request: Request, body: DraftBody):
    """Write a reply draft for one email from this session's own run.

    Takes an email id, never raw text: the text comes from what this session
    already read, so the endpoint cannot be used as an open LLM proxy by anyone
    holding a session token.
    """
    from server import draft_one  # noqa: circular by design, runtime only

    sess = _require(request)
    cache_key = f"{body.id}:{body.tone}"
    cached = sess["drafts"].get(cache_key)
    if cached:
        return {**cached, "cached": True}

    email = next((d for d in sess["analyses"] if d.get("id") == body.id), None)
    if not email:
        raise HTTPException(status_code=404, detail="Ez a levél nem szerepel a futásban.")

    # Count distinct drafts, so re-reading a cached one is not charged twice.
    if len(sess["drafts"]) >= MAX_DRAFTS_PER_SESSION:
        raise HTTPException(
            status_code=429,
            detail=f"Ebben a munkamenetben {MAX_DRAFTS_PER_SESSION} fogalmazvány a keret. "
                   "Frissítsd az oldalt, vagy írj nekünk.",
        )

    result = await draft_one(email, body.tone)
    sess["drafts"][cache_key] = result
    return {**result, "cached": False}


# ---------- Writing the draft into the mailbox ----------
def _reply_recipient(email: dict) -> str:
    """Reply-To wins over From when the sender asked for it."""
    return (email.get("reply_to") or email.get("sender") or "").strip()


def _reply_subject(subject: str) -> str:
    subject = (subject or "").strip()
    if not subject or subject == "(nincs tárgy)":
        return "Re:"
    return subject if subject[:3].lower() == "re:" else f"Re: {subject}"


def _outgoing_body(text: str) -> str:
    """Strip the on-page AI-draft notice from anything that leaves for Gmail.

    The notice exists to tell the *visitor* the text was machine-written; it is
    read on the page, before they accept it. Once they have read it and chosen to
    send or save it, the message is theirs, and shipping a "this is an AI draft"
    line to their customer would be nonsense — worse, in a saved draft it would
    sit there waiting to be sent by accident.
    """
    from server import AI_NOTICE  # noqa: circular by design, runtime only

    return text.replace(AI_NOTICE, "").rstrip() + "\n"


def _build_reply_mime(email: dict, from_addr: str, subject: str, text: str) -> str:
    """RFC 2822 reply, base64url-encoded the way the Gmail API wants it.

    Threading needs In-Reply-To and References, not just Gmail's threadId: without
    the headers other mail clients show the reply as an unrelated message, and
    Gmail itself will refuse a threadId whose subject does not match.
    """
    msg = EmailMessage()
    msg["To"] = _reply_recipient(email)
    msg["From"] = from_addr
    msg["Subject"] = subject
    parent_id = (email.get("message_id") or "").strip()
    if parent_id:
        msg["In-Reply-To"] = parent_id
        existing = (email.get("references") or "").strip()
        msg["References"] = f"{existing} {parent_id}".strip() if existing else parent_id
    msg.set_content(text)
    return base64.urlsafe_b64encode(msg.as_bytes()).decode()


class SaveDraftBody(BaseModel):
    id: str
    tone: Literal["hivatalos", "kozvetlen"] = "hivatalos"
    # The explicit confirmation. Not a formality: this is the one call in the whole
    # agent that changes the visitor's mailbox, so it will not run on a stray click
    # or a replayed request that happens to hit the endpoint.
    confirm: bool = False


@router.post("/draft/save")
async def save_draft(request: Request, body: SaveDraftBody):
    """Write an already-generated reply draft into the visitor's Gmail Drafts.

    Two gates, both required:
      * the session must hold draft-writing access, which only exists if the
        visitor ticked the box and Google granted gmail.compose;
      * `confirm` must be true for this specific email.

    The draft is created, never sent — the visitor opens Gmail and presses Send
    themselves. SafeGmailProxy refuses every send-type call regardless.
    """
    sess = _require(request)
    if not sess.get("can_draft"):
        raise HTTPException(
            status_code=403,
            detail="Ehhez a munkamenethez nincs vázlatírási engedély. "
                   "Csatlakozz újra, és pipáld be a vázlatírást.",
        )
    if not body.confirm:
        raise HTTPException(status_code=400, detail="Megerősítés nélkül nem írunk a postafiókba.")

    text = sess["drafts"].get(f"{body.id}:{body.tone}")
    if not text:
        raise HTTPException(
            status_code=409,
            detail="Ehhez a levélhez még nincs fogalmazvány. Fogalmazd meg előbb.",
        )
    email = next((d for d in sess["analyses"] if d.get("id") == body.id), None)
    if not email:
        raise HTTPException(status_code=404, detail="Ez a levél nem szerepel a futásban.")
    if not _reply_recipient(email):
        raise HTTPException(status_code=422, detail="A levélnek nincs válaszolható feladója.")

    service = SafeGmailProxy(
        await asyncio.to_thread(build, "gmail", "v1", credentials=sess["creds"])
    )
    # The model writes a subject, but Gmail rejects a threadId whose subject does
    # not look like a reply to the thread, so normalise it here rather than trust it.
    subject = _reply_subject(text.get("targy") or email.get("subject"))
    raw = _build_reply_mime(email, sess["email"], subject, _outgoing_body(text["valasz"]))
    message = {"raw": raw}
    if email.get("thread_id"):
        message["threadId"] = email["thread_id"]

    existing_id = sess["saved"].get(body.id)
    try:
        if existing_id:
            # Re-confirming after a tone change updates the same draft rather than
            # leaving a pile of near-identical ones in the mailbox.
            created = await asyncio.to_thread(
                service.users().drafts().update(
                    userId="me", id=existing_id, body={"message": message}
                ).execute
            )
        else:
            created = await asyncio.to_thread(
                service.users().drafts().create(userId="me", body={"message": message}).execute
            )
    except PermissionError:
        raise
    except Exception as e:  # noqa - a Gmail refusal must not 500 into the browser
        logger.warning("draft save failed: %s", type(e).__name__)
        raise HTTPException(
            status_code=502,
            detail="A Gmail nem fogadta el a vázlatot. Próbáld újra, vagy másold ki a szöveget.",
        )

    draft_id = created.get("id") or existing_id
    sess["saved"][body.id] = draft_id
    return {
        "draft_id": draft_id,
        "updated": bool(existing_id),
        "to": _reply_recipient(email),
        "subject": subject,
        # Deep link to the draft in Gmail, so the visitor can read and send it.
        "gmail_url": f"https://mail.google.com/mail/u/0/#drafts?compose={draft_id}",
    }


class SendBody(BaseModel):
    id: str
    tone: Literal["hivatalos", "kozvetlen"] = "hivatalos"
    # The final confirmation. Sending cannot be undone, so this is never defaulted
    # and never inferred from a previous confirmation on the same email.
    confirm: bool = False


@router.post("/draft/send")
async def send_draft(request: Request, body: SendBody):
    """Send the reply the user has already read on the page.

    Deliberately built as "save, then send that draft" rather than composing a
    fresh message: what goes out is byte-for-byte the draft the user confirmed,
    and it keeps the threading the draft already has. There is no path here that
    sends text the user has not seen.
    """
    sess = _require(request)
    if not sess.get("can_draft"):
        raise HTTPException(
            status_code=403,
            detail="Ehhez a munkamenethez nincs küldési engedély. "
                   "Csatlakozz újra, és pipáld be a vázlatírást.",
        )
    if not body.confirm:
        raise HTTPException(status_code=400, detail="Megerősítés nélkül nem küldünk levelet.")

    text = sess["drafts"].get(f"{body.id}:{body.tone}")
    if not text:
        raise HTTPException(
            status_code=409,
            detail="Ehhez a levélhez még nincs fogalmazvány. Fogalmazd meg előbb.",
        )
    if sess["sent"].get(body.id):
        raise HTTPException(
            status_code=409,
            detail="Erre a levélre már küldtünk választ ebben a munkamenetben.",
        )
    email = next((d for d in sess["analyses"] if d.get("id") == body.id), None)
    if not email:
        raise HTTPException(status_code=404, detail="Ez a levél nem szerepel a futásban.")
    recipient = _reply_recipient(email)
    if not recipient:
        raise HTTPException(status_code=422, detail="A levélnek nincs válaszolható feladója.")

    # The one place in this file that may send. Everything else holds a proxy
    # that refuses.
    service = SafeGmailProxy(
        await asyncio.to_thread(build, "gmail", "v1", credentials=sess["creds"]),
        allow_send=True,
    )
    subject = _reply_subject(text.get("targy") or email.get("subject"))
    raw = _build_reply_mime(email, sess["email"], subject, _outgoing_body(text["valasz"]))
    message = {"raw": raw}
    if email.get("thread_id"):
        message["threadId"] = email["thread_id"]

    try:
        draft_id = sess["saved"].get(body.id)
        if draft_id:
            await asyncio.to_thread(
                service.users().drafts().update(
                    userId="me", id=draft_id, body={"message": message}
                ).execute
            )
        else:
            created = await asyncio.to_thread(
                service.users().drafts().create(userId="me", body={"message": message}).execute
            )
            draft_id = created.get("id")
            sess["saved"][body.id] = draft_id
        sent = await asyncio.to_thread(
            service.users().drafts().send(userId="me", body={"id": draft_id}).execute
        )
    except Exception as e:  # noqa - a Gmail refusal must not 500 into the browser
        logger.warning("send failed: %s", type(e).__name__)
        raise HTTPException(
            status_code=502,
            detail="A Gmail nem küldte el a levelet. Nézd meg a Vázlatok közt, "
                   "és onnan küldd el kézzel.",
        )

    sess["sent"][body.id] = sent.get("id")
    sess["saved"].pop(body.id, None)  # the draft became a sent message
    return {
        "message_id": sent.get("id"),
        "thread_id": sent.get("threadId"),
        "to": recipient,
        "subject": subject,
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
    state.update({"running": True, "message": "Levelek lekérése…"})
    try:
        # Every googleapiclient call is synchronous; run it in a worker thread so
        # a mailbox pass never freezes the rest of the API.
        service = SafeGmailProxy(
            await asyncio.to_thread(build, "gmail", "v1", credentials=sess["creds"])
        )
        after = int((datetime.now(timezone.utc) - timedelta(days=LOOKBACK_DAYS)).timestamp())
        listing = await asyncio.to_thread(
            service.users().messages().list(
                userId="me", maxResults=MAX_EMAILS, q=f"after:{after}"
            ).execute
        )
        ids = [m["id"] for m in listing.get("messages", [])]
        state["total"] = len(ids)
        state["message"] = "Feldolgozás folyamatban…" if ids else "Nincs feldolgozható levél az elmúlt 30 napban."
        # Fetched and classified a few at a time. Sequentially, a full mailbox
        # would be MAX_EMAILS round trips to Gmail plus MAX_EMAILS model calls,
        # one after another — minutes of staring at a progress bar. The limit is
        # small on purpose: it keeps us well inside Gmail and OpenAI rate limits,
        # and caps how far the shared daily budget can overshoot when several
        # classifications are already in flight as it runs out.
        gate = asyncio.Semaphore(RUN_CONCURRENCY)
        # Set to the budget message by whichever email hits the ceiling first;
        # the rest then stop instead of logging fifty identical failures.
        halted: dict = {"reason": None}

        async def process(mid: str):
            if halted["reason"] or sid not in _sessions:  # ceiling hit, or visitor left
                return
            async with gate:
                if halted["reason"] or sid not in _sessions:
                    return
                try:
                    full = await asyncio.to_thread(
                        service.users().messages().get(userId="me", id=mid, format="full").execute
                    )
                    email = _parse(full)
                    analysis = await classify_one(email)
                    sess["analyses"].append({**email, **analysis})
                except HTTPException as e:
                    halted["reason"] = e.detail
                except Exception as e:  # noqa - one bad email must not stop the rest
                    logger.warning("agent email failed: %s", type(e).__name__)
                    state["errors"] += 1
                finally:
                    state["done"] += 1

        # Results arrive out of order; /results sorts by urgency and date anyway.
        await asyncio.gather(*(process(mid) for mid in ids))
        if halted["reason"]:
            state["message"] = halted["reason"]
        elif ids:
            state["message"] = "Kész"
    except Exception as e:  # noqa - a dead background task would leave the page spinning
        logger.exception("agent run failed")
        state["message"] = "Az elemzés megszakadt. Próbáld újra."
        state["errors"] += 1
    finally:
        state["running"] = False
