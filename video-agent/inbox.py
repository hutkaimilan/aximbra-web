"""Beérkező témák más agentektől (pl. a sales agent napi két témája).

Egy JSON-fájl a köteten. Minden tétel egyszer megy le: az azonosítón
szűrünk, így ha a küldő újrapróbálja (mert nem kapta meg a választ),
abból nem lesz dupla videó. Egy tétel legfeljebb MAX_TRIES-szor fut;
utána "failed", és a panelen látszik.
"""
from __future__ import annotations

import json
import os
import re
import threading
from datetime import datetime, timedelta, timezone

PATH = os.environ.get("INBOX_PATH", os.path.join(os.path.dirname(os.environ.get("SETTINGS_PATH", "/data/settings.json")), "inbox.json"))
MAX_TRIES = 2
RETRY_AFTER = timedelta(hours=1)
KEEP_DAYS = 30
TARGETS = ("instagram", "linkedin")
FORMS = ("auto", "video", "image", "carousel")
_lock = threading.Lock()


class InboxError(ValueError):
    pass


def _load() -> list[dict]:
    try:
        with open(PATH, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return []
    return data if isinstance(data, list) else []


def _save(items: list[dict]) -> None:
    os.makedirs(os.path.dirname(PATH) or ".", exist_ok=True)
    tmp = PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False)
    os.replace(tmp, PATH)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def add(body: dict, now: datetime | None = None) -> tuple[dict, bool]:
    """Új tétel felvétele. Visszaadja a tételt, és hogy új volt-e."""
    now = now or _now()
    tid = str(body.get("id") or "").strip()
    if not re.fullmatch(r"[A-Za-z0-9_.:-]{3,80}", tid):
        raise InboxError("hiányzó vagy hibás azonosító")
    brief = str(body.get("brief") or "").strip()
    if not 20 <= len(brief) <= 2000:
        raise InboxError("a téma 20 és 2000 karakter között legyen")
    lang = body.get("lang")
    if lang not in ("hu", "en"):
        raise InboxError("nyelv: hu vagy en")
    targets = [t for t in (body.get("targets") or []) if t in TARGETS]
    if not targets:
        raise InboxError("legalább egy cél kell: instagram vagy linkedin")
    form = body.get("form") if body.get("form") in FORMS else "auto"
    with _lock:
        items = _load()
        for it in items:
            if it["id"] == tid:
                return it, False
        it = {"id": tid, "brief": brief, "lang": lang, "targets": targets, "form": form,
              "source": str(body.get("source") or "")[:40], "status": "pending", "tries": 0,
              "created_at": now.isoformat(timespec="seconds"), "last_try": "", "result": {}, "error": ""}
        cutoff = (now - timedelta(days=KEEP_DAYS)).isoformat()
        items = [x for x in items if x.get("created_at", "") >= cutoff] + [it]
        _save(items)
        return it, True


def next_due(now: datetime | None = None) -> dict | None:
    """A legrégebbi futtatható tétel: még nem kész, és ha már elhasalt,
    akkor eltelt RETRY_AFTER."""
    now = now or _now()
    for it in _load():
        if it["status"] != "pending" or it["tries"] >= MAX_TRIES:
            continue
        if it["last_try"]:
            try:
                if now - datetime.fromisoformat(it["last_try"]) < RETRY_AFTER:
                    continue
            except ValueError:
                pass
        return it
    return None


def update(tid: str, **fields) -> dict | None:
    with _lock:
        items = _load()
        for it in items:
            if it["id"] == tid:
                it.update(fields)
                if it["status"] == "pending" and it["tries"] >= MAX_TRIES:
                    it["status"] = "failed"
                _save(items)
                return it
    return None


def recent(n: int = 10) -> list[dict]:
    return list(reversed(_load()))[:n]
