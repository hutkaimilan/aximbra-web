"""A videós agent beállításai: automatikus gyártás és kiposztolás.

Egyetlen JSON a köteten. Kevés érték, ritkán változik, ezért nem kell
adatbázis; az írás ideiglenes fájlon át megy, hogy egy félbeszakadt
mentés ne hagyjon csonka állományt.
"""
from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

PATH = os.environ.get("SETTINGS_PATH", "/data/settings.json")
_lock = threading.Lock()

MIN_HOURS, MAX_HOURS = 2, 48
TZ = ZoneInfo("Europe/Budapest")
# Napi módban ha egy kör elhasal (pl. a modell vagy a Make nem válaszol),
# ennyi óra múlva újra próbálja, de aznap csak egy sikeres darab megy ki.
RETRY_HOURS = 3

DEFAULTS = {
    "auto": False,            # magától gyárt-e videót
    "every_hours": 8,         # ennyi óránként egyet
    "daily_hour": -1,         # 0–23: naponta egyszer, ennyi órakor (budapesti idő); -1: ki
    "done_day": "",           # napi módban: melyik napon ment ki már sikeresen
    "autopost": False,        # a kész videó megy-e ki magától
    "targets": [],            # hova: "instagram", "linkedin"
    "aspect": "9:16",
    "form": "auto",       # videó, kép, körhinta — az "auto" a téma szövegéből dönt
    "lang": "hu",
    "voice": True,
    "male": False,
    "seconds": 30,
    "briefs": [],             # miről készüljenek; sorban haladunk rajtuk
    "next_brief": 0,
    "last_run": "",
    "last_post": "",
    "posts_today": 0,
    "posts_day": "",
    "max_posts_per_day": 3,
}


def load() -> dict:
    try:
        with open(PATH, encoding="utf-8") as f:
            saved = json.load(f)
    except (OSError, ValueError):
        saved = {}
    return {**DEFAULTS, **(saved if isinstance(saved, dict) else {})}


def save(values: dict) -> dict:
    """A megadott kulcsokat írja felül, a többit békén hagyja."""
    with _lock:
        cur = load()
        cur.update(values)
        os.makedirs(os.path.dirname(PATH) or ".", exist_ok=True)
        tmp = PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(cur, f, ensure_ascii=False)
        os.replace(tmp, PATH)
        return cur


def clean(body: dict) -> dict:
    """A felületről jövő értékek határok közé szorítva."""
    out = {}
    if "auto" in body:
        out["auto"] = bool(body["auto"])
    if "autopost" in body:
        out["autopost"] = bool(body["autopost"])
    if "targets" in body:
        want = body["targets"] if isinstance(body["targets"], list) else []
        out["targets"] = [t for t in ("instagram", "linkedin") if t in want]
    if "voice" in body:
        out["voice"] = bool(body["voice"])
    if "male" in body:
        out["male"] = bool(body["male"])
    if "every_hours" in body:
        try:
            out["every_hours"] = max(MIN_HOURS, min(MAX_HOURS, int(body["every_hours"])))
        except (TypeError, ValueError):
            pass
    if "daily_hour" in body:
        try:
            out["daily_hour"] = max(-1, min(23, int(body["daily_hour"])))
        except (TypeError, ValueError):
            pass
    if "seconds" in body:
        try:
            out["seconds"] = max(10, min(90, int(body["seconds"])))
        except (TypeError, ValueError):
            pass
    if "max_posts_per_day" in body:
        try:
            out["max_posts_per_day"] = max(1, min(10, int(body["max_posts_per_day"])))
        except (TypeError, ValueError):
            pass
    if body.get("aspect") in ("9:16", "4:5", "1:1", "16:9"):
        out["aspect"] = body["aspect"]
    if body.get("form") in ("auto", "video", "image", "carousel"):
        out["form"] = body["form"]
    if body.get("lang") in ("hu", "en"):
        out["lang"] = body["lang"]
    if "briefs" in body:
        items = body["briefs"]
        if isinstance(items, str):
            items = items.split("\n")
        out["briefs"] = [str(b).strip()[:1000] for b in (items or []) if str(b).strip()][:20]
        out["next_brief"] = 0
    return out


def due(now: datetime, s: dict) -> bool:
    """Esedékes-e az automatikus gyártás."""
    if not s.get("auto") or not s.get("briefs"):
        return False
    if int(s.get("daily_hour", -1)) >= 0:
        return _due_daily(now, s)
    last = s.get("last_run") or ""
    if not last:
        return True
    try:
        prev = datetime.fromisoformat(last)
    except ValueError:
        return True
    if prev.tzinfo is None:
        prev = prev.replace(tzinfo=timezone.utc)
    return (now - prev).total_seconds() >= s["every_hours"] * 3600


def _parse(ts: str) -> datetime | None:
    try:
        t = datetime.fromisoformat(ts)
    except (TypeError, ValueError):
        return None
    return t if t.tzinfo else t.replace(tzinfo=timezone.utc)


def _due_daily(now: datetime, s: dict) -> bool:
    """Napi mód: a beállított óra után indul, naponta egy sikeres darab.
    Ha a kör elhasal, RETRY_HOURS múlva újrapróbálja, de csak aznap."""
    local = now.astimezone(TZ)
    if s.get("done_day") == local.date().isoformat():
        return False
    if local.hour < int(s["daily_hour"]):
        return False
    prev = _parse(s.get("last_run") or "")
    return prev is None or (now - prev).total_seconds() >= RETRY_HOURS * 3600


def mark_done(now: datetime) -> dict:
    return save({"done_day": now.astimezone(TZ).date().isoformat()})


def take_brief(s: dict) -> tuple[str, int]:
    """A soron következő téma és a rá mutató index."""
    briefs = s.get("briefs") or []
    if not briefs:
        return "", 0
    i = int(s.get("next_brief") or 0) % len(briefs)
    return briefs[i], (i + 1) % len(briefs)


def post_budget(now: datetime, s: dict) -> int:
    """Hány poszt fér még bele ma."""
    today = now.astimezone(timezone.utc).date().isoformat()
    used = int(s.get("posts_today") or 0) if s.get("posts_day") == today else 0
    return max(0, int(s.get("max_posts_per_day") or 0) - used)


def count_post(now: datetime, s: dict) -> dict:
    today = now.astimezone(timezone.utc).date().isoformat()
    used = int(s.get("posts_today") or 0) if s.get("posts_day") == today else 0
    return save({"posts_day": today, "posts_today": used + 1,
                 "last_post": now.astimezone(timezone.utc).isoformat(timespec="seconds")})
