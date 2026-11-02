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

    def send(self, subject: str, text: str) -> None:
        body = {"from": self.sender, "to": [self.to], "subject": subject[:150], "text": text}
        try:
            r = self.client.post(RESEND_URL, headers={"Authorization": f"Bearer {self._key}"}, json=body)
        except httpx.HTTPError as e:
            raise MailError(f"a Resend nem érhető el ({type(e).__name__})") from None
        if r.status_code >= 400:
            raise MailError(f"Resend-hiba (HTTP {r.status_code}): {r.text[:200]}")
