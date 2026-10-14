"""A rövid videós platformok (TikTok, Instagram Reels, YouTube Shorts) aktuális
vágási, szerkesztési, sablon- és effekttrendjei.

Hetente egyszer frissül, lustán: amikor a rendező dolgozni kezd, és a tárolt
lista régebbi egy hétnél. Így nem kell hozzá ütemező, és az alvó szolgáltatást
sem kell miatta felkelteni. A panelről kézzel is frissíthető.

A trendeket webes keresésből gyűjtjük, és a modell csak a talált szövegekből
dolgozhat: minden trendhez forrás tartozik. A lista arra is kitér, hogyan
valósítható meg a sablonnal (montázs-átmenet, tempó, nyitókép, szöveg), mert a
rendező csak azt tudja használni, amit a renderelő meg tud csinálni.
"""
from __future__ import annotations

import json
import logging
import os
import threading
from datetime import datetime, timedelta, timezone

import llm
import websearch

logger = logging.getLogger(__name__)

PATH = os.environ.get("TRENDS_PATH", "/data/trends.json")
MAX_AGE = timedelta(days=7)
MAX_TRENDS = 10
_lock = threading.Lock()

# Amit a renderelő tud; a trendet ezekre fordítjuk le.
TOOLS = """What our renderer can do (map every trend onto these, nothing else):
- "montage" scene: a fast full-screen cut of the user's photos and clips; per-item time = scene seconds / items
  (0.4-0.6 s = beat-cut pace, ~1 s = calm); "transition": "cut" (hard cut), "zoom" (punch-in zoom on every
  cut), "flash" (white flash between shots), "fade" (soft crossfade).
- "clip" scene: one uploaded clip, any stretch of it, at 1x-4x speed (speed ramps = consecutive clip scenes
  at different speeds); "layout": "full" or "phone".
- "photo" scene with a slow zoom; "gallery" grid; big bold headline with 1-2 colour-highlighted words;
  kicker label; centred statement; numbered steps; before/after comparison; on-screen text-message and
  phone-call mock-ups; a closing call-to-action card.
- The first scene is the hook (max ~3 s). Narration voice-over is optional; no music, no licensed audio."""


def _queries(now: datetime) -> list[str]:
    month = now.strftime("%B %Y")
    return [f"TikTok editing trends {month} transitions cuts",
            f"Instagram Reels trends {month} templates effects editing",
            f"YouTube Shorts editing style trends {month}",
            f"short-form video hook and caption trends {month}"]


def load() -> dict:
    try:
        with open(PATH, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def fresh(data: dict, now: datetime | None = None) -> bool:
    now = now or datetime.now(timezone.utc)
    try:
        return now - datetime.fromisoformat(data.get("fetched_at", "")) < MAX_AGE
    except ValueError:
        return False


def _prompt(hits: list[dict], now: datetime) -> str:
    src = "\n\n".join(f"[{i}] {h['title']} — {h['url']}\n{h['text']}" for i, h in enumerate(hits))
    return f"""Today is {now.date()}. Below are web search results about current short-form video trends on
TikTok, Instagram Reels and YouTube Shorts. Extract the editing trends that are current now: cuts, transitions,
pacing, templates and formats, effects, text/caption styles, hook styles. Use ONLY what the sources say; skip
anything older than a few months, generic advice, and audio/song trends (we cannot use licensed audio).

{TOOLS}

Reply with a JSON object only: {{"trends": [{{"name": "short name", "platforms": ["tiktok"|"instagram"|"youtube"],
"kind": "cut|transition|pacing|template|effect|text|hook|format", "what": "what it looks like, one sentence, Hungarian",
"apply": "how to do it with our renderer, one concrete sentence in English naming the scene kind / transition / pace",
"source": index of the source}}]}} — at most {MAX_TRENDS} trends, the most widely used first.

SOURCES:
{src}"""


def refresh(say=lambda m: None) -> dict:
    """Új trendlista a webről. Hibánál a régi marad; sosem dob kivételt."""
    if not _lock.acquire(blocking=False):
        return load()
    try:
        now = datetime.now(timezone.utc)
        say("Trendfigyelés: a TikTok, Reels és Shorts aktuális vágási trendjei…")
        hits, seen = [], set()
        for q in _queries(now):
            for h in websearch.search(q, n=4):
                if h.get("url") and h["url"] not in seen:
                    seen.add(h["url"])
                    hits.append(h)
        if not hits:
            say("Trendfigyelés: most nem értem el a keresőt, a korábbi lista marad.")
            return load()
        try:
            data = llm.extract_json(llm._ask(_prompt(hits[:14], now)))
        except Exception as e:  # noqa: BLE001 — a trend csak segítség, a videó enélkül is elkészül
            logger.warning("trendösszegzés hiba: %s", e)
            return load()
        out = []
        for t in (data.get("trends") if isinstance(data, dict) else None) or []:
            if not isinstance(t, dict) or not str(t.get("name") or "").strip():
                continue
            try:
                src = hits[int(t.get("source"))]
            except (TypeError, ValueError, IndexError):
                continue          # forrás nélkül nem trend, hanem találgatás
            out.append({"name": str(t["name"]).strip()[:60],
                        "platforms": [p for p in (t.get("platforms") or []) if p in ("tiktok", "instagram", "youtube")],
                        "kind": str(t.get("kind") or "")[:20], "what": str(t.get("what") or "").strip()[:240],
                        "apply": str(t.get("apply") or "").strip()[:240],
                        "source": {"title": src["title"][:120], "url": src["url"]}})
        if not out:
            return load()
        result = {"fetched_at": now.isoformat(timespec="seconds"), "trends": out[:MAX_TRENDS]}
        os.makedirs(os.path.dirname(PATH) or ".", exist_ok=True)
        tmp = PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=1)
        os.replace(tmp, PATH)
        say(f"Trendfigyelés: {len(out)} aktuális trend.")
        return result
    finally:
        _lock.release()


def current(say=lambda m: None) -> dict:
    """A tárolt lista, ha egy hétnél frissebb; különben előbb frissít."""
    data = load()
    return data if fresh(data) else refresh(say)


def prompt_block(data: dict) -> str:
    """A rendezőnek szóló rész: mit lehet most átvenni, és hogyan."""
    items = data.get("trends") or []
    if not items:
        return ""
    lines = "\n".join(f"- {t['name']} ({', '.join(t['platforms']) or 'short video'}): {t['apply']}" for t in items)
    return f"""CURRENT SHORT-VIDEO TRENDS (collected {data.get('fetched_at', '')[:10]} from the web):
{lines}
For a TikTok / Reels / Shorts style piece, apply 1-3 of these that fit the brief and the material — unless the
brief asks for a different style. Never let a trend override the brief or the user's notes on their material."""
