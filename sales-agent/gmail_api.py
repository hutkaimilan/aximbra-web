"""Küldés a Gmail webes felületén (API) keresztül, Google-bejelentkezéssel.

A Railway Hobby csomagja a kimenő SMTP-t tiltja, a HTTPS-t nem. Ezért a
küldés ugyanúgy megy, ahogy az oldal e-mail agentje is dolgozik: a
tulajdonos egyszer engedélyezi a panelről, és a program a Gmail API-n
küld. Csak küldési jogot kér (gmail.send), olvasni ezzel nem tud.

A frissítő token titkosítva van a köteten (SALES_TOKEN_KEY), a panel
jelszava mögött; bármikor visszavonható a Google-fiók Biztonság oldalán.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import threading
import time
from urllib.parse import urlencode

import httpx
from cryptography.fernet import Fernet, InvalidToken

from mailer import AuthError, MailError

logger = logging.getLogger(__name__)

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
SEND_URL = "https://gmail.googleapis.com/gmail/v1/users/me/messages/send"
SCOPES = "openid email https://www.googleapis.com/auth/gmail.send"
STATE_TTL = 900
TIMEOUT = 30

_lock = threading.Lock()
_cache = {"token": None, "exp": 0.0}


def _key() -> str:
    """SALES_TOKEN_KEY, vagy ha nincs megadva, egy első induláskor
    generált kulcs a köteten (csak a tulajdonos olvashatja)."""
    env = os.environ.get("SALES_TOKEN_KEY", "").strip()
    if env:
        return env
    path = os.path.join(os.path.dirname(os.environ.get("SALES_DB_PATH", "/data/sales.db")) or ".", ".token_key")
    try:
        with open(path) as f:
            k = f.read().strip()
            if k:
                return k
    except FileNotFoundError:
        pass
    except OSError:
        return ""
    import secrets as _s
    k = _s.token_urlsafe(32)
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as f:
            f.write(k)
        return k
    except FileExistsError:  # egy párhuzamos hívás közben létrehozta
        with open(path) as f:
            return f.read().strip()
    except OSError:
        return ""


def _cfg() -> dict:
    return {
        "client_id": os.environ.get("GOOGLE_CLIENT_ID", "").strip(),
        "client_secret": os.environ.get("GOOGLE_CLIENT_SECRET", "").strip(),
        "redirect": os.environ.get("OAUTH_REDIRECT_URI", "").strip(),
        "key": _key(),
        "account": (os.environ.get("COMPOSE_ACCOUNT") or os.environ.get("GMAIL_USER", "")).strip().lower(),
    }


def configured() -> bool:
    c = _cfg()
    return all(c[k] for k in ("client_id", "client_secret", "redirect", "key", "account"))


def _fernet() -> Fernet:
    return Fernet(base64.urlsafe_b64encode(hashlib.sha256(_cfg()["key"].encode()).digest()))


def _sign(msg: str) -> str:
    return hmac.new(_cfg()["key"].encode(), msg.encode(), hashlib.sha256).hexdigest()


def auth_url() -> str:
    c = _cfg()
    ts = str(int(time.time()))
    state = f"{ts}.{_sign('oauth:' + ts)}"
    return AUTH_URL + "?" + urlencode({
        "client_id": c["client_id"], "redirect_uri": c["redirect"], "response_type": "code",
        "scope": SCOPES, "access_type": "offline", "prompt": "consent",
        "include_granted_scopes": "false", "login_hint": c["account"], "state": state,
    })


def state_ok(state: str) -> bool:
    try:
        ts, sig = state.split(".", 1)
        fresh = 0 <= time.time() - int(ts) <= STATE_TTL
    except (ValueError, AttributeError):
        return False
    return fresh and hmac.compare_digest(_sign("oauth:" + ts), sig)


def _jwt_email(id_token: str) -> str:
    # A token közvetlenül a Google token-végpontjától jött TLS-en, ezért a
    # tartalmát aláírás-ellenőrzés nélkül is olvashatjuk.
    try:
        payload = id_token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        return (json.loads(base64.urlsafe_b64decode(payload)).get("email") or "").lower()
    except (IndexError, ValueError):
        return ""


def exchange(code: str, store) -> str:
    """A visszatérő kódból frissítő token; csak a beállított fiókot fogadja el."""
    c = _cfg()
    try:
        r = httpx.post(TOKEN_URL, timeout=TIMEOUT, data={
            "code": code, "client_id": c["client_id"], "client_secret": c["client_secret"],
            "redirect_uri": c["redirect"], "grant_type": "authorization_code"})
    except httpx.HTTPError as e:
        raise MailError(f"a Google nem érhető el ({type(e).__name__})") from e
    if r.status_code != 200:
        raise MailError(f"a Google elutasította a kódot ({r.status_code})")
    data = r.json()
    email = _jwt_email(data.get("id_token", ""))
    if email != c["account"]:
        raise AuthError(f"rossz fiók: {email or '?'} — a(z) {c['account']} fiókkal lépj be")
    if "gmail.send" not in (data.get("scope") or ""):
        raise AuthError("a küldési jogot nem engedélyezted")
    refresh = data.get("refresh_token")
    if not refresh:
        raise AuthError("a Google nem adott tartós engedélyt; próbáld újra")
    store.set_setting("gmail_refresh", _fernet().encrypt(refresh.encode()).decode())
    store.set_setting("gmail_account", email)
    with _lock:
        _cache.update(token=data.get("access_token"), exp=time.time() + int(data.get("expires_in", 0)) - 60)
    return email


def connected(store) -> bool:
    return bool(store.get_setting("gmail_refresh")) and configured()


def disconnect(store) -> None:
    store.set_setting("gmail_refresh", "")
    with _lock:
        _cache.update(token=None, exp=0.0)


def _access_token(store) -> str:
    with _lock:
        if _cache["token"] and time.time() < _cache["exp"]:
            return _cache["token"]
    enc = store.get_setting("gmail_refresh")
    if not enc:
        raise AuthError("a Gmail nincs összekötve")
    try:
        refresh = _fernet().decrypt(enc.encode()).decode()
    except InvalidToken as e:
        raise AuthError("a tárolt engedély nem olvasható; kösd össze újra") from e
    c = _cfg()
    try:
        r = httpx.post(TOKEN_URL, timeout=TIMEOUT, data={
            "client_id": c["client_id"], "client_secret": c["client_secret"],
            "refresh_token": refresh, "grant_type": "refresh_token"})
    except httpx.HTTPError as e:
        raise MailError(f"a Google nem érhető el ({type(e).__name__})") from e
    if r.status_code in (400, 401):
        # invalid_grant: visszavonták, vagy lejárt. Újra kell kötni.
        disconnect(store)
        raise AuthError("a Gmail-engedély lejárt vagy visszavonták; kösd össze újra")
    if r.status_code != 200:
        raise MailError(f"tokenfrissítési hiba ({r.status_code})")
    data = r.json()
    with _lock:
        _cache.update(token=data["access_token"], exp=time.time() + int(data.get("expires_in", 3600)) - 60)
        return _cache["token"]


def send(msg, store) -> str:
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    token = _access_token(store)
    try:
        r = httpx.post(SEND_URL, timeout=TIMEOUT, headers={"Authorization": f"Bearer {token}"}, json={"raw": raw})
    except httpx.HTTPError as e:
        # Hálózati hiba: nem tudjuk, kiment-e. A hívó 'failed'-re teszi, és
        # ember dönt az újraküldésről — automatikusan nem küldjük újra.
        raise MailError(f"hálózati hiba küldés közben ({type(e).__name__}); nézd meg az Elküldött mappát") from e
    if r.status_code == 401:
        with _lock:
            _cache.update(token=None, exp=0.0)
        raise AuthError("a Gmail elutasította az engedélyt; kösd össze újra")
    if r.status_code == 429:
        raise MailError("a Gmail napi küldési korlátja; próbáld később")
    if r.status_code >= 400:
        raise MailError(f"a Gmail nem fogadta el a levelet ({r.status_code})")
    return msg["Message-ID"]
