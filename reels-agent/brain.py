"""Az AI-rendező: a te leírásodból + a mostani trendekből jelenetterv.

Bemenet: amit beírtál (mit akarsz), a friss trendek, és a tárban lévő elemek
(mi ez, milyen hosszú, hol a legmozgalmasabb része, és mit írtál rá).
Kimenet: jelenetenként melyik elem, meddig, milyen mozgás, színezés,
sebesség, felirat és utána milyen átmenet — kizárólag az effects.py neveiből.

Ha a modell nem elérhető (nincs kulcs, elfogyott a napi keret, hibás válasz),
a determinista rendező (director.py) veszi át: videó akkor is lesz. Ezt a
napló kimondja, nem csendben történik.
"""
from __future__ import annotations

import json
import logging

import director
import effects

logger = logging.getLogger("reels.brain")

MAX_SCENES = 80

PROMPT = """You are the editor of a short-form vertical video (TikTok / Reels / Shorts).

WHAT THE USER ASKED FOR:
{brief}

TARGET: about {seconds} seconds, aspect {aspect}, on-screen language: {lang}.

CURRENT TRENDS (researched on the web in the last days — use 1 to 3 of these if they fit
the material; ignore the rest):
{trends}

YOUR TOOLBOX — you may ONLY use these exact names:
  motion (camera move on a shot): {motion}
  look (colour / image treatment): {look}
  transition (what happens AFTER this shot): {transition}
  speed: a number 0.2–5.0, clips only (1.0 = normal)
  text_position: {text_position}
  text_style: {text_style}
  text_anim: {text_anim}

THE MATERIAL (use the id exactly as given):
{media}

RULES
- Use every item at least once unless its note says to skip it. Obey every note:
  an item marked as the opening shot goes first, one marked last goes last,
  "from N seconds" sets that clip's start, "write on it: X" must appear as text.
- Mix photos and clips; do not put all the clips at the end.
- Scene length {min_scene}–{max_scene} seconds. Fast cuts carry energy; let a shot breathe
  only when something must be read.
- For a clip, "start" is where to cut in. The strongest moment of each clip is given below;
  use it unless the note says otherwise.
- Keep on-screen text short (max ~8 words), in {lang}, and only where it adds something.
- The last scene's transition must be "cut".
- {brand}

Answer ONLY with JSON:
{{"title": "short title, max 60 chars",
  "trends_used": ["name of each trend you actually used"],
  "scenes": [{{"id": "<media id>", "seconds": 0.8, "start": 0.0, "motion": "punch_in",
               "look": "none", "speed": 1.0, "transition": "cut",
               "text": "", "text_position": "lower", "text_style": "outline",
               "text_anim": "none"}}]}}"""

BRAND_ON = ("This IS about AXIMBRA, so an AXIMBRA word mark may appear in the text of the "
            "first or last scene.")
BRAND_OFF = ("This is NOT about AXIMBRA: never put the word AXIMBRA, any logo, link or "
             "sign-off anywhere in the video.")


def media_lines(items: list[dict]) -> str:
    out = []
    for m in items:
        bits = [f"id={m['id']}", "photo" if m.get("kind") != "clip" else "clip"]
        if m.get("kind") == "clip":
            bits.append(f"length={m.get('seconds')}s")
            if m.get("hot") is not None:
                bits.append(f"strongest_moment={m['hot']}s")
        if m.get("width"):
            bits.append(f"{m['width']}x{m['height']}")
        if (m.get("note") or "").strip():
            bits.append(f'note="{m["note"].strip()[:160]}"')
        out.append("- " + ", ".join(bits))
    return "\n".join(out)


def _is_aximbra(brief: str) -> bool:
    return "aximbra" in (brief or "").lower()


def _clean_scene(raw: dict, by_id: dict, lang: str) -> dict | None:
    if not isinstance(raw, dict):
        return None
    m = by_id.get(str(raw.get("id") or ""))
    if not m:
        return None
    try:
        secs = float(raw.get("seconds") or 0)
    except (TypeError, ValueError):
        secs = 0
    secs = max(director.MIN_SCENE, min(director.MAX_SCENE, secs or 1.0))
    is_clip = m.get("kind") == "clip"
    speed = effects.clamp_speed(raw.get("speed", 1.0)) if is_clip else 1.0
    start = 0.0
    if is_clip:
        dur = float(m.get("seconds") or 0)
        try:
            start = float(raw.get("start") or 0)
        except (TypeError, ValueError):
            start = 0.0
        if dur > 0:
            # A jelenet nem lóghat túl a klip végén — gyorsításnál több nyersanyag kell.
            secs = min(secs, dur / max(0.2, speed))
            start = max(0.0, min(start, max(0.0, dur - secs * speed)))
    motion = raw.get("motion") if effects.is_motion(str(raw.get("motion") or "")) else "none"
    look = raw.get("look") if effects.is_look(str(raw.get("look") or "")) else "none"
    trans = raw.get("transition") if effects.is_transition(str(raw.get("transition") or "")) else "cut"
    text = str(raw.get("text") or "").strip()[:120]
    pos = raw.get("text_position") if raw.get("text_position") in effects.TEXT_POSITIONS else "lower"
    style = raw.get("text_style") if raw.get("text_style") in effects.TEXT_STYLES else "outline"
    anim = raw.get("text_anim") if raw.get("text_anim") in effects.TEXT_ANIMS else "none"
    return {"id": m["id"], "kind": m.get("kind"), "name": m.get("name", ""),
            "seconds": round(secs, 3), "start": round(start, 3), "speed": speed,
            "motion": motion, "look": look, "transition": trans,
            "text": text, "text_position": pos, "text_style": style, "text_anim": anim,
            "source_seconds": m.get("seconds")}


def plan(items: list[dict], brief: str, seconds: float = 25.0, aspect: str = "9:16",
         lang: str = "hu", trend_data: dict | None = None, say=lambda m: None) -> dict:
    """Terv a modelltől; ha nem megy, a determinista rendezőtől."""
    import llm
    import trends as trends_mod

    usable = [m for m in items if not director.read_note(m.get("note", ""))["skip"]]
    if not usable:
        raise ValueError("nincs használható elem")
    if aspect not in director.ASPECTS:
        aspect = "9:16"
    w, h = director.ASPECTS[aspect]
    td = trend_data or {}

    def fallback(why: str) -> dict:
        say(f"Rendező: {why} — a beépített vágóval dolgozom (a leírásod szövegként nem "
            "kerül bele, de az elemenkénti utasításaid igen).")
        p = director.plan(items, seconds, aspect, "", lang)
        p["brief"] = brief
        p["by"] = "beépített vágó"
        p["trends_used"] = []
        return p

    if not llm.available():
        return fallback("nincs beállítva modellkulcs")

    cat = effects.catalogue()
    prompt = PROMPT.format(
        brief=(brief or "").strip()[:4000] or "(no description given — make a clean, fast montage)",
        seconds=int(seconds), aspect=aspect, lang="Hungarian" if lang == "hu" else "English",
        trends=trends_mod.summary_for_prompt(td),
        media=media_lines(usable)[:12000],
        min_scene=director.MIN_SCENE, max_scene=director.MAX_SCENE,
        brand=BRAND_ON if _is_aximbra(brief) else BRAND_OFF,
        **{k: ", ".join(v) for k, v in cat.items() if isinstance(v, list)})
    say(f"Rendező ({llm.engine_name()}): a leírásod + {len(td.get('trends') or [])} trend "
        f"+ {len(usable)} elem…")
    try:
        raw = llm.extract_json(llm._ask(prompt))
    except Exception as e:  # noqa: BLE001 — a videó nem maradhat el egy modellhiba miatt
        logger.warning("rendező hiba: %s", e)
        return fallback(f"a modell nem válaszolt ({str(e)[:120]})")

    by_id = {m["id"]: m for m in usable}
    scenes = [s for s in ((_clean_scene(x, by_id, lang)) for x in
                          ((raw or {}).get("scenes") if isinstance(raw, dict) else raw) or []) if s]
    if len(scenes) < 2:
        return fallback("a modell nem adott értelmezhető jelenetsort")
    scenes = scenes[:MAX_SCENES]
    scenes[-1]["transition"] = "cut"

    missing = [m for m in usable if m["id"] not in {s["id"] for s in scenes}]
    if missing:
        say(f"Rendező: {len(missing)} elem kimaradt a tervből, a végére teszem.")
        for m in missing:
            extra = _clean_scene({"id": m["id"], "seconds": 0.8, "motion": "punch_in"}, by_id, lang)
            if extra:
                scenes.insert(len(scenes) - 1, extra)

    used = [str(t)[:60] for t in ((raw or {}).get("trends_used") or []) if str(t).strip()][:4]
    total = sum(s["seconds"] for s in scenes)
    title = str((raw or {}).get("title") or "")[:60]
    say(f"Rendező kész: {len(scenes)} jelenet, kb. {total:.0f} mp"
        + (f" — trendek: {', '.join(used)}" if used else ""))
    return {"aspect": aspect, "width": w, "height": h, "lang": lang, "title": title,
            "brief": brief, "by": llm.engine_name(), "trends_used": used,
            "scenes": scenes, "seconds": round(total, 2), "fade_seconds": 0.3}
