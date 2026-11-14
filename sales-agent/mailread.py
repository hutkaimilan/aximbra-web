"""Csak olvasó hozzáférés a beállított Gmail-postafiókokhoz (a tulajdonos kérése,
2026-11-15: "MINDEN EMAILRE RA KELL LATNOD").

Ugyanazokat a fiókokat használja, mint a válaszfigyelés (GMAIL_USER +
GMAIL_ACCOUNTS, alkalmazásjelszóval, IMAP). Az "Összes levél" mellett a Spam
és a Kuka mappában is keres, mert a visszapattanás és a válasz oda is kerülhet.

Mindig readonly módban nyit: semmit nem jelöl olvasottnak, nem töröl, nem küld.
"""
from __future__ import annotations

import email
import email.utils
import imaplib
import re
import threading
from email.header import decode_header, make_header

from mailer import IMAP_HOST, TIMEOUT, AuthError, MailError, _accounts, _plain_text

MAX_LIMIT = 50
MAX_TEXT = 20000
SNIPPET = 300
# Ennél több egyidejű IMAP-belépés a Gmailnél korlátozást okozhat.
_imap_slots = threading.BoundedSemaphore(2)

# Gmail IMAP jelzők -> rövid név, amit a hívó is megadhat.
FOLDER_FLAGS = {"all": "\\All", "spam": "\\Junk", "trash": "\\Trash"}


def _hdr(value: str | None) -> str:
    try:
        return str(make_header(decode_header(value or "")))
    except (LookupError, ValueError, UnicodeError):
        return value or ""


def _folders(imap) -> dict[str, str]:
    typ, boxes = imap.list()
    out: dict[str, str] = {}
    for raw in boxes or []:
        line = raw.decode(errors="replace")
        for key, flag in FOLDER_FLAGS.items():
            if flag in line and key not in out:
                m = re.search(r'"([^"]+)"\s*$', line) or re.search(r"(\S+)\s*$", line)
                if m:
                    out[key] = m.group(1)
    return out


def _clean_query(q: str) -> str:
    q = (q or "").replace('"', " ").replace("\r", " ").replace("\n", " ").strip()
    if len(q) > 500:
        raise ValueError("túl hosszú keresés (max 500 karakter)")
    return q


class _Reader:
    def __init__(self, user: str, pw: str):
        try:
            self.imap = imaplib.IMAP4_SSL(IMAP_HOST, timeout=TIMEOUT)
            self.imap.login(user, pw)
        except imaplib.IMAP4.error as e:
            raise AuthError(f"IMAP belépés sikertelen ({user}): {e}") from e
        except OSError as e:
            raise MailError(f"IMAP hiba ({user}): {e}") from e
        self.user = user.lower()
        self.folders = _folders(self.imap)

    def close(self):
        try:
            self.imap.logout()
        except Exception:  # noqa: BLE001 — a kilépés hibája nem érdekes
            pass

    def _select(self, key: str) -> bool:
        name = self.folders.get(key)
        if not name:
            return False
        typ, _ = self.imap.select(f'"{name}"', readonly=True)
        return typ == "OK"

    def search(self, key: str, q: str, limit: int) -> list[dict]:
        if not self._select(key):
            return []
        crit = ("X-GM-RAW", f'"{q}"') if q else ("ALL",)
        typ, data = self.imap.search(None, *crit)
        if typ != "OK" or not data or not data[0]:
            return []
        nums = data[0].split()[-limit:]
        out = []
        for num in reversed(nums):  # legújabb elöl
            m = self._fetch(num, full=False)
            if m:
                m["folder"] = key
                out.append(m)
        return out

    def get(self, msgid: str) -> dict | None:
        for key in ("all", "spam", "trash"):
            if not self._select(key):
                continue
            typ, data = self.imap.search(None, "X-GM-MSGID", msgid)
            if typ == "OK" and data and data[0]:
                m = self._fetch(data[0].split()[0], full=True)
                if m:
                    m["folder"] = key
                    return m
        return None

    def _fetch(self, num: bytes, full: bool) -> dict | None:
        typ, data = self.imap.fetch(num, "(X-GM-MSGID X-GM-LABELS BODY.PEEK[])")
        if typ != "OK" or not data:
            return None
        meta, raw = b"", None
        for part in data:
            if isinstance(part, tuple):
                meta, raw = part[0], part[1]
                break
        if raw is None:
            return None
        meta_s = meta.decode(errors="replace")
        mid = re.search(r"X-GM-MSGID (\d+)", meta_s)
        labels = re.search(r"X-GM-LABELS \(([^)]*)\)", meta_s)
        msg = email.message_from_bytes(raw)
        text = _plain_text(msg) or ""
        out = {
            "account": self.user,
            "id": mid.group(1) if mid else "",
            "date": msg.get("Date", ""),
            "from": _hdr(msg.get("From")),
            "to": _hdr(msg.get("To")),
            "subject": _hdr(msg.get("Subject")),
            "labels": labels.group(1) if labels else "",
        }
        if full:
            out.update({
                "cc": _hdr(msg.get("Cc")),
                "message_id": (msg.get("Message-ID") or "").strip(),
                "in_reply_to": (msg.get("In-Reply-To") or "").strip(),
                "attachments": [p.get_filename() for p in msg.walk() if p.get_filename()],
                "text": text[:MAX_TEXT],
                "truncated": len(text) > MAX_TEXT,
            })
        else:
            out["snippet"] = re.sub(r"\s+", " ", text).strip()[:SNIPPET]
        return out


def accounts() -> list[str]:
    return [u.lower() for u, _ in _accounts()]


def _pick(account: str | None) -> list[tuple[str, str]]:
    accs = _accounts()
    if not accs:
        raise AuthError("nincs beállított postafiók")
    if account:
        accs = [a for a in accs if a[0].lower() == account.strip().lower()]
        if not accs:
            raise ValueError("ismeretlen postafiók")
    return accs


def _when(m: dict) -> float:
    try:
        return email.utils.parsedate_to_datetime(m.get("date") or "").timestamp()
    except (TypeError, ValueError, IndexError):
        return 0.0


def search(q: str = "", account: str | None = None, folders: str = "all,spam,trash",
           limit: int = 20, opener=_Reader) -> dict:
    """Keresés Gmail-szintaxissal (from:, subject:, newer_than:...) minden fiókban."""
    q = _clean_query(q)
    limit = max(1, min(int(limit), MAX_LIMIT))
    keys = [k for k in (f.strip() for f in (folders or "").split(",")) if k in FOLDER_FLAGS] or ["all"]
    results, errors = [], []
    with _imap_slots:
        for user, pw in _pick(account):
            try:
                r = opener(user, pw)
            except (AuthError, MailError) as e:
                errors.append(str(e))
                continue
            try:
                for k in keys:
                    results.extend(r.search(k, q, limit))
            except (imaplib.IMAP4.error, OSError) as e:
                errors.append(f"{user}: {e}")
            finally:
                r.close()
    results.sort(key=_when, reverse=True)
    return {"results": results[:limit], "errors": errors}


def get(account: str, msgid: str, opener=_Reader) -> dict | None:
    if not re.fullmatch(r"\d{1,25}", msgid or ""):
        raise ValueError("hibás üzenetazonosító")
    with _imap_slots:
        for user, pw in _pick(account):
            r = opener(user, pw)
            try:
                return r.get(msgid)
            except (imaplib.IMAP4.error, OSError) as e:
                raise MailError(f"{user}: {e}") from e
            finally:
                r.close()
    return None
