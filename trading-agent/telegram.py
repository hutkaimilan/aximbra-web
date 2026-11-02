"""Telegram bot: értesítés kifelé, kérdés-parancs befelé (long polling, webhook nélkül).

A token az URL-ben utazik, ezért hibaüzenetbe soha nem kerül URL, és az
app.py a httpx naplózását WARNING-ra állítja (INFO szinten kiírná a kérés URL-jét).
"""
from __future__ import annotations

import logging
import os
import time

import httpx

logger = logging.getLogger(__name__)

MAX_LEN = 4000   # a Telegram korlátja 4096 karakter üzenetenként


class TelegramError(RuntimeError):
    pass


def chunks(text: str, size: int = MAX_LEN) -> list[str]:
    text = text or ""
    out = []
    while len(text) > size:
        cut = text.rfind("\n", 0, size)
        cut = cut if cut > size // 2 else size
        out.append(text[:cut])
        text = text[cut:].lstrip("\n")
    if text:
        out.append(text)
    return out


class Telegram:
    def __init__(self, token: str, chat_id: str | None, client: httpx.Client | None = None):
        self._base = f"https://api.telegram.org/bot{token}"
        self.chat_id = chat_id
        self.client = client or httpx.Client(timeout=70)

    @classmethod
    def from_env(cls) -> "Telegram | None":
        token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
        if not token:
            return None
        return cls(token, os.environ.get("TELEGRAM_CHAT_ID", "").strip() or None)

    def _call(self, method: str, payload: dict, timeout: float = 30) -> dict:
        for attempt in range(2):
            try:
                r = self.client.post(f"{self._base}/{method}", json=payload, timeout=timeout)
            except httpx.HTTPError as e:
                raise TelegramError(f"a Telegram nem érhető el ({type(e).__name__})") from None
            try:
                data = r.json()
            except ValueError:
                raise TelegramError(f"értelmezhetetlen Telegram-válasz (HTTP {r.status_code})") from None
            if r.status_code == 429 and attempt == 0:
                wait = (data.get("parameters") or {}).get("retry_after", 5)
                time.sleep(min(float(wait), 30))
                continue
            if not data.get("ok"):
                raise TelegramError(f"Telegram-hiba (HTTP {r.status_code}): {data.get('description', '')[:200]}")
            return data
        raise TelegramError("a Telegram többször is korlátozta a küldést")

    def send(self, text: str, chat_id: str | None = None) -> None:
        target = chat_id or self.chat_id
        if not target:
            raise TelegramError("nincs beállítva a TELEGRAM_CHAT_ID")
        for part in chunks(text):
            self._call("sendMessage", {"chat_id": target, "text": part, "disable_web_page_preview": True})

    def updates(self, offset: int, timeout: int = 50) -> list[dict]:
        data = self._call("getUpdates", {"offset": offset, "timeout": timeout, "allowed_updates": ["message"]},
                          timeout=timeout + 15)
        result = data.get("result")
        return result if isinstance(result, list) else []
