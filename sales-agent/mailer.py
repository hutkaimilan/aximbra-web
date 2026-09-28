"""Küldés és olvasás a saját Gmail-fiókon, alkalmazásjelszóval.

SMTP a küldéshez, IMAP a válaszokhoz és ahhoz, hogy megnézzük: írtunk-e
már ennek a címnek bármikor, ebben a programban vagy kézzel.
"""
import email
import email.utils
import imaplib
import logging
import os
import re
import smtplib
import ssl
from email.message import EmailMessage
from email.header import decode_header, make_header

logger = logging.getLogger(__name__)

SMTP_HOST, SMTP_PORT = "smtp.gmail.com", 465
IMAP_HOST = "imap.gmail.com"
TIMEOUT = 30


class MailError(RuntimeError):
    pass


class AuthError(MailError):
    """Rossz jelszó: nincs értelme a többi levéllel próbálkozni."""


def _creds() -> tuple[str, str]:
    user = os.environ.get("GMAIL_USER", "").strip()
    pw = os.environ.get("GMAIL_APP_PASSWORD", "").replace(" ", "")
    if not user or not pw:
        raise AuthError("nincs beállítva a GMAIL_USER / GMAIL_APP_PASSWORD")
    return user, pw


def sender_name() -> str:
    return os.environ.get("SENDER_NAME", "Hutkai Milán")


def build_message(to: str, subject: str, body: str, in_reply_to: str | None = None) -> EmailMessage:
    user, _ = _creds()
    msg = EmailMessage()
    msg["From"] = email.utils.formataddr((sender_name(), user))
    msg["To"] = to
    msg["Subject"] = subject
    msg["Date"] = email.utils.formatdate(localtime=True)
    msg["Message-ID"] = email.utils.make_msgid(domain=user.split("@")[-1])
    # Egykattintásos leiratkozás: a levelezők ezt jó jelnek veszik, a
    # címzettnek pedig nem kell válaszolnia, ha nem akar.
    msg["List-Unsubscribe"] = f"<mailto:{user}?subject=nem>"
    if in_reply_to:
        msg["In-Reply-To"] = in_reply_to
        msg["References"] = in_reply_to
    msg.set_content(body)
    return msg


def send(msg: EmailMessage) -> str:
    user, pw = _creds()
    try:
        with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=TIMEOUT,
                              context=ssl.create_default_context()) as s:
            s.login(user, pw)
            refused = s.send_message(msg)
            if refused:
                raise MailError(f"a szerver visszautasította: {refused}")
    except smtplib.SMTPAuthenticationError as e:
        raise AuthError(f"Gmail belépés sikertelen: {e.smtp_code}") from e
    except (smtplib.SMTPException, OSError) as e:
        raise MailError(f"küldési hiba: {e}") from e
    return msg["Message-ID"]


class Mailbox:
    """IMAP kapcsolat egy futásra. Mindig az 'Összes levél' mappát
    választja, a nyelvtől függetlenül (a \\All jelzőből)."""

    def __init__(self):
        user, pw = _creds()
        try:
            self.imap = imaplib.IMAP4_SSL(IMAP_HOST, timeout=TIMEOUT)
            self.imap.login(user, pw)
        except imaplib.IMAP4.error as e:
            raise AuthError(f"Gmail IMAP belépés sikertelen: {e}") from e
        except OSError as e:
            raise MailError(f"IMAP hiba: {e}") from e
        self.user = user.lower()
        self._select_all_mail()

    def _select_all_mail(self):
        typ, boxes = self.imap.list()
        name = None
        for raw in boxes or []:
            line = raw.decode(errors="replace")
            if "\\All" in line:
                m = re.search(r'"([^"]+)"\s*$', line) or re.search(r"(\S+)\s*$", line)
                name = m.group(1) if m else None
                break
        if not name:
            raise MailError("nem találom az Összes levél mappát (IMAP engedélyezve van?)")
        typ, _ = self.imap.select(f'"{name}"', readonly=True)
        if typ != "OK":
            raise MailError("nem sikerült megnyitni az Összes levél mappát")

    def close(self):
        try:
            self.imap.logout()
        except Exception:  # noqa: BLE001 — a kilépés hibája nem érdekes
            pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()

    def _search(self, gmail_query: str) -> list[bytes]:
        q = gmail_query.replace('"', "")
        typ, data = self.imap.search(None, "X-GM-RAW", f'"{q}"')
        if typ != "OK" or not data or not data[0]:
            return []
        return data[0].split()

    def ever_contacted(self, address: str, domain: str | None) -> bool:
        """Írtunk-e már neki bármikor (kézzel is)."""
        q = f"to:{address}"
        if domain:
            q = f"{{to:{address} to:{domain}}}"
        return bool(self._search(f"from:me {q}"))

    def messages_from(self, address: str, since_days: int = 30) -> list[dict]:
        ids = self._search(f"from:{address} newer_than:{since_days}d")
        return [m for m in (self._fetch(i) for i in ids[-10:]) if m]

    def bounces_since(self, since_days: int = 14) -> list[dict]:
        ids = self._search(f"from:mailer-daemon newer_than:{since_days}d")
        return [m for m in (self._fetch(i) for i in ids[-50:]) if m]

    def _fetch(self, num: bytes) -> dict | None:
        typ, data = self.imap.fetch(num, "(RFC822)")
        if typ != "OK" or not data or not isinstance(data[0], tuple):
            return None
        msg = email.message_from_bytes(data[0][1])
        return {
            "from": email.utils.parseaddr(msg.get("From", ""))[1].lower(),
            "subject": str(make_header(decode_header(msg.get("Subject", "")))),
            "message_id": (msg.get("Message-ID") or "").strip(),
            "in_reply_to": (msg.get("In-Reply-To") or "").strip(),
            "references": (msg.get("References") or ""),
            "date": msg.get("Date", ""),
            "text": _plain_text(msg),
        }


def _plain_text(msg) -> str:
    parts = list(msg.walk()) if msg.is_multipart() else [msg]
    for part in parts:
        if part.get_content_type() == "text/plain" and not part.get_filename():
            try:
                return part.get_content()
            except (LookupError, AttributeError):
                payload = part.get_payload(decode=True) or b""
                return payload.decode(errors="replace")
    for part in parts:
        if part.get_content_type() == "text/html":
            payload = part.get_payload(decode=True) or b""
            return re.sub(r"<[^>]+>", " ", payload.decode(errors="replace"))
    return ""


def strip_quoted(text: str) -> str:
    """Csak az új rész a válaszból, az idézett előzmény nélkül."""
    out = []
    for line in (text or "").splitlines():
        if line.startswith(">"):
            break
        if re.match(r"^(On .+wrote:|.+ ezt írta.*:|Am .+schrieb.*:|-----Original Message-----|"
                    r"-----Ursprüngliche Nachricht-----|Dňa .+napísal.*:|În .+a scris:)", line.strip()):
            break
        out.append(line)
    return "\n".join(out).strip()
