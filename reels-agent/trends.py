"""Trendfigyelő: mik most a TikTok/Reels/Shorts vágási és effekt-trendjei.

Webes keresés (Tavily, havi 1000 ingyenes keresés), majd a modell kivonatolja
belőle, amit a rendező használni tud: az effekt neve, mit csinál, és hogy a
mi készletünkből (effects.py) mivel rakható ki. Forrással együtt, hogy
ellenőrizhető legyen.

A találat a köteten marad és egy hétig érvényes: nem égetjük a keretet minden
gyártásnál, és ha épp nincs net vagy kulcs, a legutóbbi anyag akkor is megvan.
"""
from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime, timezone

import effects

logger = logging.getLogger("reels.trends")

TRENDS_PATH = os.environ.get("TRENDS_PATH", "/data/trends.json")
MAX_AGE_DAYS = 7
QUERIES = (
    "TikTok editing trends this month transitions effects",
    "Instagram Reels trending edit style velocity zoom transition",
    "YouTube Shorts viral editing techniques trending effects",
    "trending CapCut template effect style short form video",
)

PROMPT = """You are briefing a video editor on what is trending RIGHT NOW in short-form video
(TikTok, Instagram Reels, YouTube Shorts).

Below are web search results from the last days. Use ONLY what they say; do not invent trends.

{research}

The editor's toolbox can do exactly these, and nothing else:
  camera motion: {motion}
  colour/image looks: {look}
  transitions between shots: {transition}
  clip speed: 0.2 – 5.0
There is NO on-screen text: ignore any trend that is only about captions or titles.

Pick the 6 most useful, concrete, CURRENT editing trends. For each give:
  "name": short name of the trend, as editors call it
  "what": one sentence, what it looks like on screen (max 20 words)
  "recipe": how to build it from the toolbox above — ONLY names from the lists,
            e.g. {{"motion": "punch_in", "look": "contrast_pop", "transition": "zoomin", "speed": 1.6}}
  "when": one short sentence on when to use it in a montage (max 15 words)
  "source": the URL from the research that mentions it

Answer ONLY with JSON: {{"trends": [{{"name": "...", "what": "...", "recipe": {{...}},
"when": "...", "source": "https://..."}}]}}"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def load() -> dict:
    try:
        with open(TRENDS_PATH, encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def _save(d: dict) -> dict:
    os.makedirs(os.path.dirname(TRENDS_PATH) or ".", exist_ok=True)
    tmp = TRENDS_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False)
    os.replace(tmp, TRENDS_PATH)
    return d


def age_days(d: dict | None = None) -> float | None:
    d = load() if d is None else d
    ts = d.get("checked_at")
    if not ts:
        return None
    try:
        then = datetime.fromisoformat(ts)
    except ValueError:
        return None
    return (datetime.now(timezone.utc) - then).total_seconds() / 86400


def stale() -> bool:
    a = age_days()
    return a is None or a > MAX_AGE_DAYS


def _clean(raw) -> list[dict]:
    """Csak az marad, ami a mi készletünkből tényleg kirakható."""
    out = []
    for x in (raw if isinstance(raw, list) else []):
        if not isinstance(x, dict):
            continue
        r = x.get("recipe") if isinstance(x.get("recipe"), dict) else {}
        recipe = {}
        if effects.is_motion(str(r.get("motion") or "")):
            recipe["motion"] = r["motion"]
        if effects.is_look(str(r.get("look") or "")):
            recipe["look"] = r["look"]
        if effects.is_transition(str(r.get("transition") or "")):
            recipe["transition"] = r["transition"]
        if r.get("speed") is not None:
            recipe["speed"] = effects.clamp_speed(r.get("speed"))
        name = str(x.get("name") or "").strip()[:60]
        if not name or not recipe:
            continue
        src = str(x.get("source") or "").strip()
        out.append({"name": name, "what": str(x.get("what") or "")[:160],
                    "when": str(x.get("when") or "")[:120], "recipe": recipe,
                    "source": src if src.startswith("http") else ""})
    return out[:8]


def refresh(say=lambda m: None) -> dict:
    """Friss keresés + kivonat. Hiba esetén a régi anyag marad meg."""
    import llm
    import websearch
    old = load()
    if not websearch.tavily_on() and not llm.available():
        say("Trendfigyelő: nincs se keresőkulcs, se modell — kimarad.")
        return old
    say("Trendfigyelő: keresés a mostani TikTok/Reels/Shorts vágási trendekre…")
    hits = []
    for q in QUERIES:
        try:
            hits += websearch.search(q, 4)
        except Exception as e:  # noqa: BLE001 — egy rossz kérés ne vigye el az egészet
            logger.warning("keresés hiba (%s): %s", q, e)
    seen, research = set(), []
    for hit in hits:
        u = hit.get("url") or ""
        if u in seen:
            continue
        seen.add(u)
        research.append(f"- {hit.get('title', '')} ({u})\n  {hit.get('text', '')[:900]}")
    if not research:
        say("Trendfigyelő: a keresés nem hozott semmit — a korábbi anyaggal dolgozom.")
        return old
    cat = effects.catalogue()
    prompt = PROMPT.format(research="\n".join(research)[:18000], **{k: ", ".join(v)
                                                                   for k, v in cat.items()
                                                                   if isinstance(v, list)})
    try:
        raw = llm.extract_json(llm._ask(prompt))
    except Exception as e:  # noqa: BLE001
        logger.warning("trendkivonat hiba: %s", e)
        say(f"Trendfigyelő: a modell nem adott használható választ ({type(e).__name__}) — "
            "a korábbi anyaggal dolgozom.")
        return old
    items = _clean((raw or {}).get("trends") if isinstance(raw, dict) else raw)
    if not items:
        say("Trendfigyelő: nem jött ki belőle használható recept — marad a korábbi.")
        return old
    say(f"Trendfigyelő: {len(items)} mostani trend — " + ", ".join(t["name"] for t in items[:6]))
    return _save({"checked_at": _now(), "trends": items,
                  "sources": [h.get("url") for h in hits if h.get("url")][:12]})


def ensure(say=lambda m: None, force: bool = False) -> dict:
    """Egy hétnél régebbi anyagot frissít; egyébként a meglévőt adja."""
    if force or stale():
        return refresh(say)
    d = load()
    a = age_days(d)
    if d.get("trends"):
        say(f"Trendfigyelő: {len(d['trends'])} trend, {a:.0f} napja frissítve.")
    return d


def summary_for_prompt(d: dict, limit: int = 6) -> str:
    items = (d.get("trends") or [])[:limit]
    if not items:
        return "(no current trend research available)"
    lines = []
    for t in items:
        lines.append(f"- {t['name']}: {t['what']} | recipe: {json.dumps(t['recipe'])} | use: {t['when']}")
    return "\n".join(lines)
