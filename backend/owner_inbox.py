"""A tulajdonos saját postafiókjai, tartós, csak olvasó hozzáféréssel.

Nem a nyilvános demó, és nem is ügyfélszolgáltatás: kizárólag az
`OWNER_INBOX_EMAILS`-ben felsorolt fiókok csatlakozhatnak, és a leveleket csak az
`OWNER_INBOX_KEY` birtokosa kérdezheti le (Bearer fejléc). Kulcs nélkül az egész
modul 503-at ad, tehát beállítás nélkül semmit nem nyit meg.

Folyamat:
  1. `POST /api/owner/inbox/connect-link` (Bearer) → egyórás, egyszer használatos
     csatlakozó link. A mesterkulcs így soha nem kerül URL-be, böngésző-előzménybe.
  2. A link a Google-hoz visz: `gmail.readonly`, `access_type=offline`, tehát
     refresh tokent kapunk. A visszahívás a már regisztrált
     `/api/agent/email/callback` címre jön — a Google Console-ban nem kell semmit
     átírni —, onnan az `owner.` előtagú állapot alapján ide kerül.
  3. A refresh token titkosítva a `continuous.store` SQLite-tárába kerül
     (`CONTINUOUS_KEY`, `CONTINUOUS_DB_PATH` — tartós volume-on).
  4. `GET /api/owner/inbox/messages?account=…&q=…` (Bearer) → fejlécek és
     részlet, élőben a Gmailből. Levéltörzset nem adunk ki és nem tárolunk.

Írási hatókört ez a modul nem kér; a Google oldalán sem tudna írni.
"""
import asyncio
import hmac
import json
import logging
import os
import secrets
import threading

import httplib2
from cryptography.fernet import Fernet, InvalidToken
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse
from google_auth_httplib2 import AuthorizedHttp
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/owner/inbox")

STATE_PREFIX = "owner."
STATE_TTL_SECONDS = 15 * 60
LINK_TTL_SECONDS = 60 * 60
MAX_RESULTS = 50
DEFAULT_QUERY = "in:inbox newer_than:2h"
HTTP_TIMEOUT_SECONDS = 30
SCOPES = ["openid", "https://www.googleapis.com/auth/userinfo.email",
          "https://www.googleapis.com/auth/gmail.readonly"]

# Egyszer használatos linkek azonosítói. Memóriában: újraindításkor elvesznek,
# ami csak annyit jelent, hogy új linket kell kérni — biztonsági rést nem nyit.
_used_links: set = set()
_used_lock = threading.Lock()
_store = None
_store_lock = threading.Lock()


def _owner_key() -> str:
    return (os.environ.get("OWNER_INBOX_KEY") or "").strip()


def _allowed_emails() -> set:
    raw = os.environ.get("OWNER_INBOX_EMAILS") or ""
    return {e.strip().lower() for e in raw.split(",") if e.strip()}


def _fernet() -> Fernet:
    """Az állapot és a link titkosítása. A CONTINUOUS_KEY-t használjuk: ugyanaz a
    kulcs védi a tokeneket, külön kulcs csak egy újabb elveszíthető titok lenne."""
    key = (os.environ.get("CONTINUOUS_KEY") or "").strip()
    if not key:
        raise HTTPException(status_code=503, detail="owner inbox not configured")
    return Fernet(key.encode())


def _configured() -> None:
    if not _owner_key() or not _allowed_emails():
        raise HTTPException(status_code=503, detail="owner inbox not configured")
    for name in ("GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET", "AGENT_REDIRECT_URI"):
        if not (os.environ.get(name) or "").strip():
            raise HTTPException(status_code=503, detail="owner inbox not configured")
    _fernet()


def _require_owner(request: Request) -> None:
    """Bearer-kulcs, állandó idejű összehasonlítással."""
    _configured()
    header = request.headers.get("authorization") or ""
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(status_code=401, detail="unauthorized")
    if not hmac.compare_digest(token.strip().encode(), _owner_key().encode()):
        raise HTTPException(status_code=401, detail="unauthorized")


def _get_store():
    global _store
    with _store_lock:
        if _store is None:
            from continuous.store import Store  # noqa: csak beállított rendszerben

            _store = Store()
        return _store


def _flow() -> Flow:
    return Flow.from_client_config(
        {"web": {
            "client_id": os.environ["GOOGLE_CLIENT_ID"].strip(),
            "client_secret": os.environ["GOOGLE_CLIENT_SECRET"].strip(),
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
        }},
        scopes=SCOPES,
        redirect_uri=os.environ["AGENT_REDIRECT_URI"].strip(),
    )


def is_owner_state(state: str) -> bool:
    return bool(state) and state.startswith(STATE_PREFIX)


def _page(title: str, text: str, status: int = 200) -> HTMLResponse:
    from html import escape

    body = (f"<!doctype html><meta charset=utf-8><meta name=viewport content='width=device-width'>"
            f"<title>{escape(title)}</title><body style='font-family:system-ui;padding:24px;max-width:520px'>"
            f"<h2>{escape(title)}</h2><p>{escape(text)}</p></body>")
    return HTMLResponse(body, status_code=status)


# ---------------------------------------------------------------- routes ---
@router.post("/connect-link")
async def connect_link(request: Request):
    """Egyórás, egyszer használatos link a fiók csatlakoztatásához."""
    _require_owner(request)
    link_id = secrets.token_urlsafe(16)
    token = _fernet().encrypt(json.dumps({"k": "link", "id": link_id}).encode()).decode()
    base = os.environ["AGENT_REDIRECT_URI"].strip().split("/api/")[0]
    return {"url": f"{base}/api/owner/inbox/connect?t={token}", "expires_in": LINK_TTL_SECONDS}


@router.get("/connect")
async def connect(t: str = ""):
    try:
        _configured()
    except HTTPException:
        return _page("Nincs beállítva", "A tulajdonosi postafiók-hozzáférés nincs bekapcsolva.", 503)
    try:
        data = json.loads(_fernet().decrypt(t.encode(), ttl=LINK_TTL_SECONDS).decode())
        if data.get("k") != "link" or not data.get("id"):
            raise ValueError
    except (InvalidToken, ValueError, json.JSONDecodeError):
        return _page("Érvénytelen link", "A link lejárt vagy hibás. Kérj újat.", 400)
    with _used_lock:
        if data["id"] in _used_links:
            return _page("Már felhasznált link", "Ezt a linket már használták. Kérj újat.", 400)
        _used_links.add(data["id"])

    flow = _flow()
    flow.code_verifier = secrets.token_urlsafe(64)[:128]
    state = STATE_PREFIX + _fernet().encrypt(
        json.dumps({"k": "state", "v": flow.code_verifier}).encode()).decode()
    url, _ = flow.authorization_url(
        access_type="offline",
        # consent: enélkül a Google második csatlakozáskor nem ad új refresh tokent.
        prompt="select_account consent",
        include_granted_scopes="false",
        state=state,
    )
    from fastapi.responses import RedirectResponse

    return RedirectResponse(url)


async def handle_callback(code: str, state: str, error: str):
    """A /api/agent/email/callback ide adja át az `owner.` állapotú kéréseket."""
    if error:
        return _page("Megszakítva", "A Google-hozzáférést nem adtad meg.", 400)
    try:
        _configured()
        raw = _fernet().decrypt(state[len(STATE_PREFIX):].encode(), ttl=STATE_TTL_SECONDS)
        st = json.loads(raw.decode())
        if st.get("k") != "state" or not st.get("v"):
            raise ValueError
    except HTTPException:
        return _page("Nincs beállítva", "A tulajdonosi postafiók-hozzáférés nincs bekapcsolva.", 503)
    except (InvalidToken, ValueError, json.JSONDecodeError):
        return _page("Lejárt", "A folyamat lejárt vagy hibás. Kérj új linket.", 400)

    try:
        flow = _flow()
        flow.code_verifier = st["v"]
        await asyncio.to_thread(flow.fetch_token, code=code)
        creds = flow.credentials
        svc = await asyncio.to_thread(build, "gmail", "v1", credentials=creds, cache_discovery=False)
        profile = await asyncio.to_thread(svc.users().getProfile(userId="me").execute)
    except Exception as e:  # noqa - soha ne 500 a böngészőbe
        logger.error("owner inbox oauth failed: %s", type(e).__name__)
        return _page("Hiba", "A Google-csatlakozás nem sikerült. Próbáld újra új linkkel.", 502)

    email = (profile.get("emailAddress") or "").lower()
    if email not in _allowed_emails():
        logger.warning("owner inbox: refused account not on the allowlist")
        return _page("Nem engedélyezett fiók", f"A(z) {email} fiók nincs a listán.", 403)
    if not creds.refresh_token:
        return _page("Nincs tartós hozzáférés",
                     "A Google nem adott tartós hozzáférést. Próbáld újra új linkkel.", 502)
    try:
        await asyncio.to_thread(_get_store().add_account, email, email, creds.refresh_token)
    except Exception as e:  # noqa
        logger.error("owner inbox store failed: %s", type(e).__name__)
        return _page("Hiba", "A hozzáférést nem sikerült elmenteni.", 500)
    logger.info("owner inbox: account connected")
    return _page("Kész", f"A(z) {email} fiók csatlakoztatva. Ezt az ablakot bezárhatod.")


@router.get("/accounts")
async def accounts(request: Request):
    _require_owner(request)
    rows = await asyncio.to_thread(_get_store().accounts)
    return {"accounts": [{"email": r["email"], "connected_at": r.get("created_at"),
                          "last_error": r.get("last_error")} for r in rows]}


def _header(headers, name):
    for h in headers or []:
        if (h.get("name") or "").lower() == name.lower():
            return h.get("value") or ""
    return ""


def _list_messages(refresh_token: str, query: str, limit: int) -> list:
    from continuous.gmail import credentials_from_refresh_token

    creds = credentials_from_refresh_token(refresh_token)
    svc = build("gmail", "v1", credentials=creds, cache_discovery=False)

    def http():
        return AuthorizedHttp(creds, http=httplib2.Http(timeout=HTTP_TIMEOUT_SECONDS))

    listing = svc.users().messages().list(userId="me", q=query, maxResults=limit).execute(http=http())
    out = []
    for m in listing.get("messages", []) or []:
        msg = svc.users().messages().get(
            userId="me", id=m["id"], format="metadata",
            metadataHeaders=["From", "To", "Cc", "Subject", "Date"],
        ).execute(http=http())
        headers = (msg.get("payload") or {}).get("headers")
        out.append({
            "id": msg.get("id"),
            "thread_id": msg.get("threadId"),
            "from": _header(headers, "From"),
            "to": _header(headers, "To"),
            "cc": _header(headers, "Cc"),
            "subject": _header(headers, "Subject"),
            "date": _header(headers, "Date"),
            "internal_date": msg.get("internalDate"),
            "labels": msg.get("labelIds") or [],
            "snippet": msg.get("snippet") or "",
        })
    return out


@router.get("/messages")
async def messages(request: Request, account: str = "", q: str = DEFAULT_QUERY, limit: int = 25):
    _require_owner(request)
    account = account.strip().lower()
    if account not in _allowed_emails():
        raise HTTPException(status_code=404, detail="unknown account")
    limit = max(1, min(int(limit), MAX_RESULTS))
    query = (q or DEFAULT_QUERY).strip()[:300]
    store = _get_store()
    try:
        token = await asyncio.to_thread(store.refresh_token, account)
    except RuntimeError:
        raise HTTPException(status_code=500, detail="token unreadable with current key")
    if not token:
        raise HTTPException(status_code=404, detail="account not connected")
    try:
        items = await asyncio.to_thread(_list_messages, token, query, limit)
    except Exception as e:  # noqa
        name = type(e).__name__
        logger.warning("owner inbox read failed for an account: %s", name)
        await asyncio.to_thread(store.mark_run, account, name)
        # RefreshError: visszavont vagy lejárt hozzáférés → újra kell csatlakozni.
        status = 409 if name == "RefreshError" else 502
        raise HTTPException(status_code=status, detail={"error": name, "reconnect": status == 409})
    await asyncio.to_thread(store.mark_run, account, None)
    return {"account": account, "query": query, "count": len(items), "messages": items}
