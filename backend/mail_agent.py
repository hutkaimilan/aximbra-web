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
import secrets
import string
from datetime import datetime, timezone, timedelta
from email.message import EmailMessage
from email.utils import parsedate_to_datetime

from typing import Literal

import httplib2
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from fastapi.responses import RedirectResponse
from cryptography.fernet import Fernet
from google_auth_httplib2 import AuthorizedHttp
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build, Resource

from attachments import MAX_ATTACHMENT_BYTES, extract_text, list_candidates

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/agent/email")

GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "").strip()
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "").strip()
GMAIL_REDIRECT_URI = os.environ.get("AGENT_REDIRECT_URI", "").strip()
SITE_URL = os.environ.get("FRONTEND_URL", "").strip()


def _log_agent_config():
    """Say at boot which agent settings are missing, and how.

    "Az agent Google-hozzáférése nincs beállítva" on the page cannot say which of
    the four is wrong — it is public, and naming the gaps to strangers is not its
    job. Without this, a variable that exists but holds an empty string looks
    identical to one that was never set, and both look like a code fault. The
    deploy log is private, so the detail belongs here.

    Values are never logged, only whether each is present — a client secret must
    not end up in a log line.
    """
    required = {
        "GOOGLE_CLIENT_ID": GOOGLE_CLIENT_ID,
        "GOOGLE_CLIENT_SECRET": GOOGLE_CLIENT_SECRET,
        "AGENT_REDIRECT_URI": GMAIL_REDIRECT_URI,
    }
    missing = [name for name, value in required.items() if not value]
    # Set-but-empty is the case that reads as "configured" in a dashboard and as
    # "not configured" here, so it is called out separately.
    blank = [n for n in missing if os.environ.get(n) is not None]
    if missing:
        logger.warning(
            "email agent NOT configured - missing: %s%s",
            ", ".join(missing),
            f" (set but empty: {', '.join(blank)})" if blank else " (not set at all)",
        )
    else:
        logger.info("email agent configured (redirect URI: %s)", GMAIL_REDIRECT_URI)
    if not SITE_URL:
        logger.warning(
            "FRONTEND_URL is empty - the OAuth callback will redirect to '/demo/email-agent' "
            "with no host, which sends the visitor nowhere useful."
        )


_log_agent_config()

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
# gmail.compose also permits sending, and the consent screen says so. Sending
# happens in exactly one place — /draft/send, on a draft the visitor confirmed
# for that one email — and every other Gmail call goes through a proxy that
# refuses send outright. The page states this before the box can be ticked.
GMAIL_SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
]

COMPOSE_SCOPE = "https://www.googleapis.com/auth/gmail.compose"
GMAIL_SCOPES_COMPOSE = [*GMAIL_SCOPES, COMPOSE_SCOPE]

# Moving mail to Trash needs more than reading: gmail.compose cannot touch an
# existing message's labels. Asked for only when the visitor ticks the cleanup
# box, and separate from drafting - someone may want one without the other.
MODIFY_SCOPE = "https://www.googleapis.com/auth/gmail.modify"

# Only these two categories may ever be trashed. Anything the classifier put
# elsewhere stays out of reach of the button, whatever the browser asks for.
#
# These are the classifier's keys (server.AGENT_CATEGORIES), not the labels the
# page shows. The first version listed the Hungarian labels, which no analysis
# ever carries, so the trashable list was always empty and the cleanup button
# never appeared - on a real mailbox with five newsletters and three spam mails.
TRASHABLE_CATEGORIES = {"newsletter", "spam"}


def _scopes_for(with_compose: bool, with_modify: bool) -> list:
    scopes = list(GMAIL_SCOPES)
    if with_compose:
        scopes.append(COMPOSE_SCOPE)
    if with_modify:
        scopes.append(MODIFY_SCOPE)
    return scopes


def _is_trashable(doc: dict) -> bool:
    return doc.get("category") in TRASHABLE_CATEGORIES

SESSION_HEADER = "X-Agent-Session"
SESSION_TTL_SECONDS = 30 * 60
MAX_EMAILS = 50
# How many emails are fetched and classified at once. Deliberately small: it is
# the knob that trades run time against rate limits and budget overshoot, and 5
# turns a ~50-call sequential crawl into something a visitor will wait through.
RUN_CONCURRENCY = 5
# A példa-postafiók tíz levele egyszerre mehet: fix darabszám, nincs mellette
# Gmail-kérés, és ez az első, amit a látogató lát a rendszerből.
SAMPLE_CONCURRENCY = 10
MAX_SESSIONS = 40
LOOKBACK_DAYS = 30
# Drafts are the most expensive call here (longer output than a classification),
# and they are user-triggered rather than part of the run, so they get their own
# per-session cap on top of the shared daily ceiling.
MAX_DRAFTS_PER_SESSION = 6

_sessions: dict = {}
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


HTTP_TIMEOUT_SECONDS = 30


OAUTH_STATE_TTL_SECONDS = 15 * 60


# Az oldal kilenc nyelven fut, és a futás kimenete a felület nyelvén készül.
# A kliens küldi, tehát ellenőrizni kell: ismeretlen kód esetén magyar, nem hiba
# — egy elgépelt nyelvkód miatt nem áll meg egy demó.
AGENT_LANGS = ("hu", "en", "de", "es", "fr", "it", "ro", "sk", "zh")


def _safe_lang(value) -> str:
    return value if value in AGENT_LANGS else "hu"


def _pack_state(code_verifier: str, with_compose: bool, lang: str = "hu",
                with_modify: bool = False) -> str:
    """Carry the OAuth handoff in the state parameter instead of server memory.

    It used to live in a module-level dict, which meant any restart between
    clicking connect and coming back from Google — a deploy, a crash, Railway
    moving the container — lost it, and the visitor got "Lejárt a folyamat" for
    something that had not expired at all.

    Encrypted, not merely signed: the PKCE verifier is in here and travels
    through the visitor's browser. Fernet gives confidentiality, authenticity and
    the expiry in one, keyed by AGENT_SESSION_KEY, so it survives restarts
    without anything being stored.
    """
    payload = json.dumps(
        {"v": code_verifier, "c": bool(with_compose), "m": bool(with_modify),
         "l": _safe_lang(lang)},
        separators=(",", ":"),
    )
    return _fernet.encrypt(payload.encode()).decode()


def _unpack_state(state: str):
    """The handoff, or None if it is forged, tampered with, or genuinely old."""
    if not state:
        return None
    try:
        raw = _fernet.decrypt(state.encode(), ttl=OAUTH_STATE_TTL_SECONDS)
        data = json.loads(raw.decode())
        verifier = data.get("v")
        if not isinstance(verifier, str) or not verifier:
            return None
        return {"verifier": verifier, "with_compose": bool(data.get("c")),
                "with_modify": bool(data.get("m")),
                "lang": _safe_lang(data.get("l"))}
    except Exception:  # noqa - forged, tampered or expired
        return None


def _new_code_verifier() -> str:
    """Same shape the library would generate. Made here so it can be sealed into
    the state before the authorization URL is built."""
    alphabet = string.ascii_letters + string.digits + "-._~"
    return "".join(secrets.choice(alphabet) for _ in range(128))


def _fresh_http(creds):
    """A private HTTP connection for one Gmail call.

    google-api-python-client is built on httplib2, which is **not thread-safe**:
    the `http` object a service is built with owns a connection, and two threads
    using it at once corrupt its state. Not an exception — a hard crash of the
    whole process, which takes every in-memory session with it and drops the
    visitor back on the connect screen with no explanation.

    The service object itself is fine to share; only the transport is not. So the
    Gmail calls that run in worker threads pass their own http to execute(),
    which is the documented way to use this client from more than one thread.
    """
    return AuthorizedHttp(creds, http=httplib2.Http(timeout=HTTP_TIMEOUT_SECONDS))


def _granted_compose(creds, requested: bool) -> bool:
    """Did Google actually grant draft-writing access?

    The consent screen lets a visitor untick individual scopes, so what we asked
    for and what we got can differ. google-auth exposes the granted list on the
    credentials when the token response carried one; when it does not, fall back
    to what was requested — the first Gmail call would fail anyway, and this keeps
    the page from offering a button that cannot work.
    """
    return _granted_scope(creds, COMPOSE_SCOPE, requested)


def _granted_scope(creds, scope: str, requested: bool) -> bool:
    """Whether Google actually granted one scope, not whether we asked for it."""
    granted = getattr(creds, "granted_scopes", None) or getattr(creds, "scopes", None)
    if not granted:
        return requested
    return scope in granted


def _flow(with_compose: bool = False, with_modify: bool = False):
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
        scopes=_scopes_for(with_compose, with_modify),
        redirect_uri=GMAIL_REDIRECT_URI,
    )


# ---------- Mail parsing ----------
def _header(headers, name):
    for h in headers:
        if h.get("name", "").lower() == name.lower():
            return h.get("value", "")
    return ""


def _decode(data):
    """base64url from Gmail, tolerant of what Gmail actually sends.

    Gmail omits the '=' padding often enough that a strict decode raises
    binascii.Error — and raising here used to take the whole email out of the
    run, counted as an unexplained error. Pad it, and never raise: a body we
    cannot read is an empty body, not a lost email.
    """
    if not data:
        return ""
    try:
        raw = data.encode("UTF-8")
        raw += b"=" * (-len(raw) % 4)
        return base64.urlsafe_b64decode(raw).decode("utf-8", errors="replace")
    except Exception as e:  # noqa - malformed part must not sink the message
        logger.warning("could not decode a message part: %s", type(e).__name__)
        return ""


def _html_to_text(html: str) -> str:
    t = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html, flags=re.S | re.I)
    t = re.sub(r"<br\s*/?>|</p>|</div>|</tr>", "\n", t, flags=re.I)
    return re.sub(r"[ \t]+", " ", re.sub(r"<[^>]+>", " ", t)).strip()


def _body(payload):
    """Text of the message, plus a structure summary for when there is none.

    The summary carries mime types and whether each part had inline data — never
    content. It is the only way to tell, from a log, the difference between an
    email that is genuinely empty and one whose body we failed to find.
    """
    plain, html, other = "", "", ""
    shape = []

    def walk(p, depth=0):
        nonlocal plain, html, other
        # Gmail usually sends a bare "text/plain", but a mimeType carrying
        # parameters ("text/plain; charset=UTF-8") is valid and used to miss the
        # equality check entirely, losing the body with no trace.
        mime = (p.get("mimeType") or "").split(";")[0].strip().lower()
        body = p.get("body") or {}
        data = body.get("data")
        shape.append(
            f"{'  ' * depth}{mime or '?'}"
            f"[{'data' if data else ('attachment' if body.get('attachmentId') else 'none')}"
            f" {body.get('size', 0)}b]"
        )
        if data:
            if mime == "text/plain":
                plain += _decode(data)
            elif mime == "text/html":
                html += _decode(data)
            elif mime.startswith("text/"):
                # text/* we do not specifically know (amp-html and friends):
                # better a last resort than silently nothing.
                other += _decode(data)
        for sub in p.get("parts") or []:
            walk(sub, depth + 1)

    walk(payload or {})
    if plain.strip():
        return plain.strip(), shape
    if html.strip():
        return _html_to_text(html), shape
    if other.strip():
        return _html_to_text(other) if "<" in other else other.strip(), shape
    return "", shape


def _parse(msg):
    payload = msg.get("payload", {})
    headers = payload.get("headers", [])
    body, shape = _body(payload)
    snippet = msg.get("snippet", "") or ""
    if not body.strip() and not snippet.strip():
        # Both empty is the case worth investigating: Gmail shows a snippet for
        # anything with content, so this is either a genuinely empty message or a
        # payload shape the walk did not understand. Structure only, no content.
        logger.warning(
            "empty body and snippet for message %s - payload shape: %s",
            msg.get("id"), " | ".join(shape) or "(no payload)",
        )
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
        # Üresen hagyjuk: a feliratot a lap adja hozzá a saját nyelvén.
        "subject": _header(headers, "Subject"),
        "snippet": snippet,
        "date": date_iso,
        "body": body,
        # Kept for threading a reply draft onto the original conversation. Without
        # these, a draft lands in Gmail as a brand-new thread and reads as a
        # different message than the one it answers.
        "thread_id": msg.get("threadId"),
        "message_id": _header(headers, "Message-Id") or _header(headers, "Message-ID"),
        "references": _header(headers, "References"),
        "reply_to": _header(headers, "Reply-To"),
        # Csak a jelöltek listája, tartalom nélkül: a letöltés külön lépés, és
        # csak akkor történik meg, ha a törzs önmagában kevés.
        "attachments": list_candidates(payload),
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
        # Whether this session may move unimportant mail to Trash.
        "can_trash": bool(sess and sess.get("can_trash")),
        # A run over the example inbox rather than someone's Gmail. The page says
        # so rather than letting the results pass for the visitor's own mail.
        "sample": bool(sess and sess.get("sample")),
    }


@router.get("/connect")
async def connect(drafts: bool = False, cleanup: bool = False, lang: str = "hu"):
    """`drafts=true` asks Google for draft-writing access as well.

    It comes from a box the visitor ticks, never from a default, and it is carried
    through the OAuth state so the callback builds the flow with the same scopes —
    a mismatch there makes Google reject the exchange.
    """
    flow = _flow(with_compose=drafts, with_modify=cleanup)
    # Set before authorization_url, which only generates one when it is still
    # None — so the verifier can be sealed into the state we hand Google.
    flow.code_verifier = _new_code_verifier()
    url, _ = flow.authorization_url(
        access_type="online",
        prompt="consent",
        include_granted_scopes="false",
        state=_pack_state(flow.code_verifier, drafts, lang, with_modify=cleanup),
    )
    return {"auth_url": url}


@router.get("/callback")
async def callback(code: str = "", state: str = "", error: str = ""):
    # A nyelvi előtag az OAuth-állapotból jön vissza. Enélkül a látogató a
    # magyar lapon köt ki, akármelyik nyelven indult — és onnantól magyar
    # felületen nézi a saját postafiókját.
    lang_prefix = ""
    st_early = _unpack_state(state)
    if st_early and st_early["lang"] != "hu":
        lang_prefix = f"/{st_early['lang']}"
    target = f"{SITE_URL}{lang_prefix}/demo/email-agent"
    if error:
        return RedirectResponse(f"{target}?error=access_denied")
    st = _unpack_state(state)
    if not st:
        logger.warning("agent oauth: unusable state (forged, tampered or expired)")
        return RedirectResponse(f"{target}?error=invalid_state")
    try:
        flow = _flow(with_compose=st["with_compose"], with_modify=st["with_modify"])
        flow.code_verifier = st["verifier"]
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
            # A felület nyelve, az OAuth-körön keresztül hozva: az összefoglalók
            # és a sürgősség-indoklás ezen a nyelven készülnek.
            "lang": st["lang"],
            # What Google actually granted, not what we asked for. A visitor can
            # untick scopes on the consent screen, so asking is not receiving —
            # and an endpoint that trusted the request would fail later, inside a
            # Gmail call, instead of saying so up front.
            "can_draft": _granted_compose(creds, requested=st["with_compose"]),
            # Whether this session may move mail to Trash. Same rule as drafting:
            # the visitor ticked the box and Google actually granted it.
            "can_trash": _granted_scope(creds, MODIFY_SCOPE, requested=st["with_modify"]),
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


# ---------------------------------------------------------------- keresés ---
# A futás az elmúlt 30 nap ötven levelét nézi. A keresés ennél többet lát: a
# Gmail saját keresőjét kérdezi, tehát bármilyen régi levél előkerül — ugyanaz,
# mintha a Gmailbe írnád be a szót. Osztályozás nincs rajta: az modellhívás
# levelenként, és egy keresés nem éri meg ennyit; a találat fejléce és a
# részlete elég ahhoz, hogy megtaláld, amit keresel.
SEARCH_MAX_RESULTS = 25
MAX_SEARCHES_PER_SESSION = 30
SEARCH_MIN_CHARS = 2
SEARCH_MAX_CHARS = 120


def _sample_search(emails: list, query: str) -> list:
    """Keresés a példa postafiókban. Ugyanazok a mezők, csak hálózat nélkül."""
    words = [w for w in query.lower().split() if w]
    hits = []
    for e in emails:
        haystack = " ".join([
            e.get("sender", ""), e.get("subject", ""), e.get("body", ""), e.get("snippet", ""),
        ]).lower()
        if all(w in haystack for w in words):
            hits.append(e)
    return hits[:SEARCH_MAX_RESULTS]


@router.get("/search")
async def search(request: Request, q: str = ""):
    """Levélkeresés kulcsszóra, a teljes postafiókban."""
    sess = _require(request)
    query = (q or "").strip()[:SEARCH_MAX_CHARS]
    if len(query) < SEARCH_MIN_CHARS:
        raise HTTPException(status_code=400, detail={"code": "search_too_short"})

    if sess.get("sample"):
        from sample_inbox import sample_emails  # noqa: runtime only

        hits = _sample_search(sample_emails(datetime.now(timezone.utc)), query)
        return {"query": query, "total": len(hits), "results": hits}

    # A keresés Gmail-hívásokba kerül, tehát munkamenetenként korlátos.
    sess["searches"] = sess.get("searches", 0) + 1
    if sess["searches"] > MAX_SEARCHES_PER_SESSION:
        raise HTTPException(status_code=429, detail={"code": "search_limit"})

    service = SafeGmailProxy(
        await asyncio.to_thread(build, "gmail", "v1", credentials=sess["creds"])
    )
    try:
        listing = await asyncio.to_thread(
            service.users().messages().list(
                userId="me", maxResults=SEARCH_MAX_RESULTS, q=query
            ).execute,
            http=_fresh_http(sess["creds"]),
        )
    except Exception as e:  # noqa - a rossz kereső-kifejezés is ide fut be
        logger.info("search failed: %s", type(e).__name__)
        raise HTTPException(status_code=502, detail={"code": "search_failed"})

    ids = [m["id"] for m in listing.get("messages", [])]
    if not ids:
        return {"query": query, "total": 0, "results": []}

    # Fejléc és részlet elég; a teljes törzs letöltése huszonöt levélre lassú
    # lenne, és a keresésnél nem is ez a kérdés.
    gate = asyncio.Semaphore(RUN_CONCURRENCY)
    found: dict = {}

    async def fetch(mid: str):
        async with gate:
            try:
                msg = await asyncio.to_thread(
                    service.users().messages().get(
                        userId="me", id=mid, format="metadata",
                        metadataHeaders=["From", "Subject", "Date"],
                    ).execute,
                    http=_fresh_http(sess["creds"]),
                )
                found[mid] = _parse(msg)
            except Exception as e:  # noqa - egy hibás találat ne vigye el a többit
                logger.info("search hit unreadable: %s", type(e).__name__)

    await asyncio.gather(*(fetch(mid) for mid in ids))
    # A Gmail sorrendjét tartjuk: az a relevancia, amit a kereső adott.
    results = [found[mid] for mid in ids if mid in found]
    return {"query": query, "total": len(results), "results": results}


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
    # Trashed mail is gone from the mailbox, so it leaves the lists too - keeping
    # it would offer actions on something that is no longer in the inbox. The
    # breakdown follows the list for the same reason: a bar counting mail that
    # is no longer there would contradict what sits underneath it.
    live = [d for d in docs if not d.get("trashed")]
    counts = {}
    for d in live:
        counts[d["category"]] = counts.get(d["category"], 0) + 1
    return {
        "email": sess["email"],
        "analyses": live,
        "counts": counts,
        "total": len(docs),
        "needs_reply": len([d for d in live if d.get("needs_reply") == "igen"]),
        # The urgent list is what still needs attention, never junk.
        "top_urgent": [d for d in live if not _is_trashable(d)][:3],
        "trashable": [d["id"] for d in live if _is_trashable(d)],
        "trashed": len([d for d in docs if d.get("trashed")]),
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

    result = await draft_one(email, body.tone, sess.get("lang", "hu"))
    sess["drafts"][cache_key] = result
    return {**result, "cached": False}


# ---------- Writing the draft into the mailbox ----------
def _reply_recipient(email: dict) -> str:
    """Reply-To wins over From when the sender asked for it."""
    return (email.get("reply_to") or email.get("sender") or "").strip()


def _reply_subject(subject: str) -> str:
    subject = (subject or "").strip()
    if not subject:
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
    from server import AI_NOTICES  # noqa: circular by design, runtime only

    # Minden nyelvi változatot: a futás nyelve és a fogalmazvány nyelve nem
    # feltétlenül ugyanaz, és egy bent felejtett „AI draft" sor pont az ügyfél
    # postafiókjában derülne ki.
    for notice in AI_NOTICES.values():
        text = text.replace(notice, "")
    return text.rstrip() + "\n"


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

    This endpoint only creates the draft; the visitor opens Gmail and presses
    Send, or confirms it separately at /draft/send. The proxy built here refuses
    every send-type call, so nothing leaves the mailbox on this path.
    """
    sess = _require(request)
    if sess.get("sample"):
        raise HTTPException(
            status_code=409,
            detail="Ez egy példa postafiók — nincs hova menteni. "
                   "Csatlakoztasd a sajátodat, ha a Gmailedbe szeretnél vázlatot.",
        )
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
    if sess.get("sample"):
        raise HTTPException(
            status_code=409,
            detail="Ez egy példa postafiók — a címzettek kitaláltak, nincs kinek küldeni.",
        )
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


class TrashBody(BaseModel):
    ids: list[str]
    confirm: bool = False


@router.post("/trash")
async def trash(request: Request, body: TrashBody):
    """Move unimportant mail to Gmail's Trash.

    Three gates, all required:
      * the session must hold cleanup access, which only exists if the visitor
        ticked the box and Google granted gmail.modify;
      * `confirm` must be true;
      * every id must belong to this session's run AND sit in a trashable
        category. The browser proposes; this decides. A crafted request naming
        an invoice or a client question is refused, not obeyed.

    Trash only - recoverable in Gmail for about 30 days. A permanent delete is
    never called anywhere in this file.
    """
    sess = _require(request)
    if not body.ids:
        raise HTTPException(status_code=400, detail="Nincs megadva törlendő levél.")
    if not body.confirm:
        raise HTTPException(status_code=400, detail="Megerősítés nélkül nem törlünk.")

    wanted = set(body.ids)
    allowed = [
        d for d in sess["analyses"]
        if d.get("id") in wanted and _is_trashable(d) and not d.get("trashed")
    ]
    refused = len(wanted) - len(allowed)

    # The example mailbox has no Gmail behind it: mark them and return, so the
    # flow can be tried without connecting an account.
    if sess.get("sample"):
        for doc in allowed:
            doc["trashed"] = True
        return {"ok": True, "trashed": len(allowed), "failed": 0, "refused": refused}

    if not sess.get("can_trash"):
        raise HTTPException(
            status_code=403,
            detail="Ehhez a munkamenethez nincs takarítási engedély. "
                   "Csatlakozz újra, és pipáld be a takarítást.",
        )
    if not allowed:
        return {"ok": True, "trashed": 0, "failed": 0, "refused": refused}

    service = SafeGmailProxy(
        await asyncio.to_thread(build, "gmail", "v1", credentials=sess["creds"])
    )
    done, failed = 0, 0
    for doc in allowed:
        try:
            await asyncio.to_thread(
                service.users().messages().trash(userId="me", id=doc["id"]).execute
            )
            doc["trashed"] = True
            done += 1
        except Exception as e:  # noqa - one failure must not stop the rest
            logger.warning("trash failed: %s", type(e).__name__)
            failed += 1
    return {"ok": True, "trashed": done, "failed": failed, "refused": refused}


@router.post("/sample")
async def start_sample(request: Request, lang: str = "hu"):
    """Start a run over the example inbox — no Google account involved.

    The real Gmail path works, but it puts Google's red "unverified app" screen
    in front of every visitor (unavoidable for a restricted scope until the app
    passes a security assessment), and a stranger will not hand over their
    mailbox to an agency they met a minute ago anyway. This shows what the agent
    does, which is the part worth showing, with the same classifier and the same
    drafter running live.

    Public and it spends model credits, so it carries the same per-IP limit as
    the other demos.
    """
    from server import _check_limits  # noqa: circular by design, runtime only

    ip = request.client.host if request.client else "unknown"
    _check_limits(request, f"sample:{ip}")

    _sweep()
    if len(_sessions) >= MAX_SESSIONS:
        raise HTTPException(status_code=429, detail="Most sokan próbálják egyszerre. Nézz vissza pár perc múlva.")

    sid = os.urandom(16).hex()
    _sessions[sid] = {
        "email": "példa@postafiók.hu",
        "lang": _safe_lang(lang),
        # No credentials at all. Not "unused" — absent, so no code path here can
        # reach a real mailbox even by mistake.
        "creds": None,
        "sample": True,
        "can_draft": False,
        "drafts": {},
        "saved": {},
        "sent": {},
        "analyses": [],
        "state": _new_state(),
        "created_at": datetime.now(timezone.utc),
    }
    task = asyncio.create_task(run_sample(sid))
    _runs.add(task)
    task.add_done_callback(_runs.discard)
    return {"session": _fernet.encrypt(sid.encode()).decode()}


async def run_sample(sid: str):
    """Classify the example inbox. Same classifier, same limits, no Gmail."""
    from server import classify_one  # noqa: circular by design, runtime only
    from sample_inbox import sample_emails

    sess = _sessions.get(sid)
    if not sess:
        return
    state = sess["state"]
    if state["running"]:
        return
    emails = sample_emails(datetime.now(timezone.utc))
    state.update({"running": True, "total": len(emails), "message": "running"})

    # A példa-postafiók tíz levél, fix, és nincs mellette Gmail-hívás: itt az
    # egész futás elfér egy hullámban. Az éles postafiók marad az öt szálon —
    # ott ötven levél is lehet, és egy ötvenes löket az OpenAI és a Gmail
    # oldalán is kockázat. Egy első benyomásnál viszont a húsz másodpercnyi
    # várakozás maga a hiba.
    gate = asyncio.Semaphore(min(len(emails), SAMPLE_CONCURRENCY))
    halted: dict = {"reason": None}

    async def process(email):
        if halted["reason"] or sid not in _sessions:
            return
        async with gate:
            if halted["reason"] or sid not in _sessions:
                return
            try:
                analysis = await classify_one(email, sess.get("lang", "hu"))
                sess["analyses"].append({**email, **analysis})
            except HTTPException:
                # A megállás oka egységesen a napi keret; a szöveget a lap adja
                # a saját nyelvén, nem a kiszolgáló.
                halted["reason"] = "budget"
            except Exception as e:  # noqa - one bad email must not stop the rest
                logger.warning("sample email failed: %s", type(e).__name__)
                state["errors"] += 1
            finally:
                state["done"] += 1

    try:
        await asyncio.gather(*(process(e) for e in emails))
        state["message"] = halted["reason"] or "done"
    except Exception:  # noqa - a dead task would leave the page spinning
        logger.exception("sample run failed")
        state["message"] = "interrupted"
        state["errors"] += 1
    finally:
        state["running"] = False


# A törzs alatta számít "üresnek". Egy „Küldöm az anyagot, részletek csatolva”
# levél pont ennyi, és pont az a levél, aminél a melléklet a lényeg.
THIN_BODY_CHARS = 400


async def _add_attachment_text(service, sess, email: dict) -> None:
    """A melléklet szövegét hozzáfűzi a levél törzséhez, ha van értelme.

    Csak akkor tölt le, ha a törzs önmagában kevés — egy rendes levélnél a
    melléklet letöltése felesleges idő és sávszélesség. Soha nem dob kivételt:
    egy olvashatatlan csatolmány nem indokolja, hogy a levél kiessen a futásból.
    """
    candidates = email.get("attachments") or []
    if not candidates or len((email.get("body") or "").strip()) >= THIN_BODY_CHARS:
        return

    pieces = []
    for att in candidates:
        try:
            got = await asyncio.to_thread(
                service.users().messages().attachments().get(
                    userId="me", messageId=email["id"], id=att["attachment_id"]
                ).execute,
                http=_fresh_http(sess["creds"]),
            )
            raw = _decode_attachment(got.get("data", ""))
            if not raw or len(raw) > MAX_ATTACHMENT_BYTES:
                continue
            text = extract_text(att["filename"], att["mime"], raw)
            if text:
                pieces.append(f"--- Melléklet: {att['filename']} ---\n{text}")
            else:
                # Kimondva, hogy a modell ne tényként kezelje az üres törzset:
                # a különbség „nincs benne semmi” és „nem tudtuk elolvasni” közt
                # a javasolt lépést is megváltoztatja.
                pieces.append(
                    f"--- Melléklet: {att['filename']} "
                    f"(a tartalmát nem sikerült szöveggé alakítani) ---"
                )
        except Exception as e:  # noqa - egy rossz melléklet ne vigye el a levelet
            logger.info("attachment fetch failed: %s", type(e).__name__)

    if pieces:
        body = (email.get("body") or "").strip()
        email["body"] = (body + "\n\n" + "\n\n".join(pieces)).strip()


def _decode_attachment(data: str) -> bytes:
    if not data:
        return b""
    try:
        raw = data.encode("UTF-8")
        raw += b"=" * (-len(raw) % 4)
        return base64.urlsafe_b64decode(raw)
    except Exception:  # noqa
        return b""


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
    state.update({"running": True, "message": "fetching"})
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
            ).execute,
            http=_fresh_http(sess["creds"]),
        )
        ids = [m["id"] for m in listing.get("messages", [])]
        state["total"] = len(ids)
        state["message"] = "running" if ids else "empty"
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
                    # Its own connection: this runs in a worker thread alongside
                    # RUN_CONCURRENCY - 1 others, and httplib2 cannot be shared.
                    full = await asyncio.to_thread(
                        service.users().messages().get(userId="me", id=mid, format="full").execute,
                        http=_fresh_http(sess["creds"]),
                    )
                    email = _parse(full)
                    await _add_attachment_text(service, sess, email)
                    analysis = await classify_one(email, sess.get("lang", "hu"))
                    sess["analyses"].append({**email, **analysis})
                except HTTPException:
                    # A megállás oka egységesen a napi keret; a szöveget a lap adja
                    # a saját nyelvén, nem a kiszolgáló.
                    halted["reason"] = "budget"
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
            state["message"] = "done"
    except Exception as e:  # noqa - a dead background task would leave the page spinning
        logger.exception("agent run failed")
        state["message"] = "interrupted"
        state["errors"] += 1
    finally:
        state["running"] = False
