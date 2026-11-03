"""Azonnali telefonértesítés az ntfy.sh-n (ingyenes, regisztráció nélkül).

A téma neve a jelszó: aki ismeri, olvashatja az értesítéseket. Ezért hosszú,
véletlen név kell (NTFY_TOPIC), és az értesítés nem tartalmaz számlaadatot,
csak a riasztás lényegét.
"""
from __future__ import annotations

import logging
import os

import httpx

logger = logging.getLogger(__name__)
SERVER = os.environ.get("NTFY_SERVER", "https://ntfy.sh").rstrip("/")


class Push:
    def __init__(self, topic: str, client: httpx.Client | None = None):
        self.topic = topic
        self.client = client or httpx.Client(timeout=10)

    @classmethod
    def from_env(cls) -> "Push | None":
        topic = os.environ.get("NTFY_TOPIC", "").strip()
        return cls(topic) if len(topic) >= 12 else None

    def send(self, title: str, text: str, priority: int = 3, click: str | None = None) -> None:
        # A fejlécek latin-1-ek: az ékezetes cím UTF-8 bájtként, RFC 2047 nélkül nem menne át,
        # ezért JSON-ként küldünk (az ntfy ezt támogatja).
        body = {"topic": self.topic, "title": title[:120], "message": (text or " ")[:900], "priority": priority}
        if click:
            body["click"] = click
        try:
            r = self.client.post(SERVER, json=body)
        except httpx.HTTPError as e:
            logger.warning("az ntfy nem érhető el (%s)", type(e).__name__)
            return
        if r.status_code >= 400:
            logger.warning("ntfy-hiba (HTTP %s): %s", r.status_code, r.text[:120])
