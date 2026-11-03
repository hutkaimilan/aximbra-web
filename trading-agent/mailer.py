"""E-mailes értesítés a Resend HTTPS API-ján.

Miért nem SMTP: a Railway a Pro csomag alatt tiltja a kimenő SMTP-portot.
Ellenőrzött domain nélkül a Resend csak a saját fiókja címére kézbesít, ezért
a címzett a NOTIFY_EMAIL (ugyanaz, amit a voice-agent is használ).
"""
from __future__ import annotations

import logging
import os

import httpx

logger = logging.getLogger(__name__)

RESEND_URL = "https://api.resend.com/emails"
DEFAULT_FROM = "Milán Trader Bot <onboarding@resend.dev>"
TIMEOUT = 15


class MailError(RuntimeError):
    pass


class Mailer:
    def __init__(self, key: str, to: str, sender: str = DEFAULT_FROM, client: httpx.Client | None = None):
        self._key = key
        self.to = to
        self.sender = sender
        self.client = client or httpx.Client(timeout=TIMEOUT)

    @classmethod
    def from_env(cls) -> "Mailer | None":
        key = os.environ.get("RESEND_API_KEY", "").strip()
        to = os.environ.get("NOTIFY_EMAIL", "").strip()
        if not (key and to and "@" in to):
            return None
        return cls(key, to, os.environ.get("TRADER_MAIL_FROM", "").strip() or DEFAULT_FROM)

    def status(self, mail_id: str) -> str:
        """A Resend szerint mi lett a levéllel (delivered, bounced, ...), diagnosztikához."""
        try:
            r = self.client.get(f"{RESEND_URL}/{mail_id}", headers={"Authorization": f"Bearer {self._key}"})
        except httpx.HTTPError as e:
            return f"lekérdezés sikertelen ({type(e).__name__})"
        if r.status_code >= 400:
            return f"lekérdezés sikertelen (HTTP {r.status_code}: {r.text[:120]})"
        data = r.json() or {}
        return f"{data.get('last_event')} (címzett: {data.get('to')}, feladó: {data.get('from')})"

    def send(self, subject: str, text: str) -> str | None:
        body = {"from": self.sender, "to": [self.to], "subject": subject[:150], "text": text}
        try:
            r = self.client.post(RESEND_URL, headers={"Authorization": f"Bearer {self._key}"}, json=body)
        except httpx.HTTPError as e:
            raise MailError(f"a Resend nem érhető el ({type(e).__name__})") from None
        if r.status_code >= 400:
            raise MailError(f"Resend-hiba (HTTP {r.status_code}): {r.text[:200]}")
        try:
            mail_id = (r.json() or {}).get("id")
        except ValueError:
            mail_id = None
        # A naplóból így visszakereshető a Resend felületén, ha egy levél nem érkezik meg.
        logger.info("e-mail elküldve (HTTP %s, Resend id: %s): %s", r.status_code, mail_id, subject[:80])
        return mail_id
