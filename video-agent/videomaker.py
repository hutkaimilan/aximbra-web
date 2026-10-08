"""A videós agent: egy szabad szöveges leírásból kész MP4, ember és kamera nélkül.

A leírás („brief”) a fő bemenet: miről szóljon, kinek, milyen hangulatban,
milyen linkek szerepeljenek. Innen:

1. Kontextus: a leírásban szereplő linkeket beolvassa (szöveg a tényekhez,
   mobil képernyőkép a videóba), kérésre a weben is utánanéz.
2. Rendező: a modell megírja a forgatókönyvet a jelenettárból (horog,
   kijelentés, probléma, előny, lépések, előtte/utána, weboldal a telefonon,
   telefonhívás, beérkező levelek, agentek, szám, idézet, felhívás), a
   narrációt és a posztot.
3. Ellenőrzés: szám, százalék, ügyfél, referencia csak akkor maradhat, ha a
   leírásban vagy a beolvasott oldalakon szerepel; egyébként egy javító kör,
   és ami utána is szabálysértő, az kimarad.
4. Hang: jelenetenként felolvasás (ElevenLabs, ha van kulcs; utána Gemini TTS, majd Edge TTS; ha egyik
   sem megy, néma videó felirattal). A jelenet legalább olyan hosszú, mint a
   narrációja.
5. Renderelés: HTML-sablon, képkockánként léptetett animációk, ffmpeg.

Módosítás: egy kész videóhoz írt visszajelzésből a modell átírja a
forgatókönyvet, és új változat készül.
"""
from __future__ import annotations

import asyncio
import base64
import contextlib
import io
import json
import logging
import os
import re
import secrets
import shutil
import subprocess
import tempfile
import time
import wave
from datetime import datetime, timezone

import httpx

import imagegen
import llm
import logomaker
import media
import playbook
import stop
import websearch

logger = logging.getLogger(__name__)

HERE = os.path.dirname(os.path.abspath(__file__))
TEMPLATE = os.path.join(HERE, "static", "video_template.html")
VIDEO_DIR = os.environ.get("VIDEO_DIR", "/data/videos")
FPS = int(os.environ.get("VIDEO_FPS", "30"))
KEEP = 20
KINDS = ("hook", "statement", "problem", "benefit", "steps", "compare", "site", "call", "inbox", "sms",
         "agents", "number", "quote", "photo", "gallery", "clip", "cta")
VISUAL_KINDS = ("site", "call", "inbox", "sms", "photo", "gallery", "clip")
# Mozgó jelenetek: álló diában szöveges dia lesz belőlük.
MOTION_KINDS = ("site", "call", "inbox", "sms", "clip")
MEDIA_KINDS = ("photo", "gallery", "clip")
THEMES = ("neon", "clean", "warm", "mono")
ASPECTS = {"9:16": (540, 960), "4:5": (540, 675), "1:1": (540, 540), "16:9": (960, 540)}
FORMS = ("auto", "video", "image", "carousel", "logo")
MAX_SLIDES = 8
MIN_TOTAL, MAX_TOTAL = 10, 120
# Egy hosszabb (90 mp fölötti) videó több jelenetet bír el.
MAX_SCENES, MAX_SCENES_LONG = 10, 15
SAMPLE_RATE = 24000

# Gyors kiindulópontok a felületen; a leírás mindig felülírja.
TOPICS = {
    "altalanos": "Az AXIMBRA általában: egyedi AI agentek a cégek saját rendszereibe, élő demókkal az aximbra.hu-n.",
    "telefon": "A telefonos AI: felveszi a hívást, rögzíti a hívó kérését a munkatársaknak; az aximbra.hu-n 10 másodpercen belül visszahív.",
    "email": "Az e-mail rendező: a közös postafiókot reggelre besorolja, rangsorolja és továbbítja, a munkatársnak csak válaszolnia kell.",
    "erdeklodo": "Az érdeklődő-minősítő: a beérkező ajánlatkéréseket sürgős, komoly és csak árat hasonlító csoportba sorolja.",
    "dokumentum": "A dokumentumelemző: szerződésekből, számlákból, szállítólevelekből kiolvassa a mezőket, amiket ma kézzel gépelnek át.",
    "nis2": "A NIS2 megfelelőségi agent: folyamatosan gyűjti az audithoz kért bizonyítékokat. Támadás ellen NEM véd.",
    "ertekesito": "Az értékesítő agent: illő cégeket talál, mindegyiknek egy valós megfigyelésre épülő levelet ír, utánkövet, és rendezi a válaszokat.",
}

VOICES = {
    "hu": {"gemini": "Kore", "edge": "hu-HU-NoemiNeural", "edge_male": "hu-HU-TamasNeural"},
    "en": {"gemini": "Kore", "edge": "en-US-AvaNeural", "edge_male": "en-US-AndrewNeural"},
}


class VideoError(RuntimeError):
    pass


# ---- kontextus ----------------------------------------------------------------

# Ennyi oldalról (vagy oldalszakaszról, pl. https://aximbra.hu/#agentek) készül
# képernyőkép. Egy összefoglaló videónak több szakasz kell, mint egy napi posztnak.
MAX_SITES = 6


def gather(brief: str, research: bool, say=lambda m: None) -> dict:
    """A leírás linkjei (szöveg + a videóba kerülő URL-ek) és opcionális webes háttér."""
    urls = websearch.urls_in(brief, MAX_SITES)
    if not urls and re.search(r"aximbr", brief, re.I):
        urls = ["https://aximbra.hu"]
    pages, read = [], set()
    for u in urls[:MAX_SITES]:
        # Ugyanannak az oldalnak a szakaszai (#agentek, #eset) egy szöveg:
        # egyszer olvassuk be, ne töltse meg ötször ugyanazzal a promptot.
        base = u.split("#", 1)[0].rstrip("/")
        if base in read:
            continue
        read.add(base)
        p = websearch.read_page(base or u)
        pages.append({"url": base or u, "text": (p or {}).get("text", "")[:2500]})
    web = []
    if research:
        say("Webes háttérkutatás…")
        web = websearch.search(brief[:280], n=4)
    return {"urls": urls[:MAX_SITES], "pages": pages, "web": web,
            "library": [m for m in media.listing() if media.ready(m)]}


# ---- forgatókönyv -----------------------------------------------------------

def _lang_name(lang: str) -> str:
    return "Hungarian" if lang == "hu" else "English"


FORM_RULES = {
    "video": "Make a VIDEO: 4–9 scenes that play one after another.",
    "image": """Make ONE SINGLE IMAGE, not a video: exactly one scene. It has to stand alone and be readable at a
glance — a strong headline and a sub that completes the thought. No narration; leave "voice" empty.""",
    "carousel": """Make a CAROUSEL of still slides, not a video: 3–6 scenes, each one a slide the reader swipes to.
Slide 1 must stop the scroll on its own, and the last slide is the call to action. Every slide has to make sense
alone, and in order they must tell one argument. No narration; leave "voice" empty.""",
}


def _shelf_line(m: dict) -> str:
    line = f"  {m['id']}  {m['kind']}  {m['name']}" + (f" — {m['note']}" if m.get("note") else "")
    if m.get("kind") == "clip":
        shape = "tall/phone recording" if (m.get("height") or 0) > (m.get("width") or 0) else "landscape"
        line += f"  [{float(m.get('seconds') or 0):.0f} s, {shape}]"
        for g in m.get("segments") or []:
            line += f"\n      {g['from']:.0f}–{g['to']:.0f} s  {g['pace']}: {g['what']}"
            if g.get("screen_text"):
                line += '  | on screen (%s): "%s"' % (g.get("screen_lang") or "?", g["screen_text"])
    return line


def director_prompt(brief: str, ctx: dict, seconds: int, lang: str, aspect: str, voice: bool,
                    form: str = "video") -> str:
    still = form in ("image", "carousel")
    sites = "\n".join(f"  [{i}] {u}" for i, u in enumerate(ctx["urls"])) or "  (none — do not use the 'site' scene)"
    lib = ctx.get("library") or []
    shelf = "\n".join(_shelf_line(m) for m in lib) or "  (empty — you may still ask for generated images)"
    attached = [m for m in (media.get(x) for x in ctx.get("attached") or []) if m]
    must = ("THE USER ATTACHED THESE FOR THIS VIDEO — use every one of them (each at least once), they are the\n"
            "point of the brief:\n" + "\n".join(_shelf_line(m) for m in attached)) if attached else ""
    pages = "\n\n".join(f"TEXT OF {p['url']}:\n{p['text']}" for p in ctx["pages"] if p["text"]) or "(none)"
    web = "\n\n".join(f"WEB: {w['title']} — {w['url']}\n{w['text']}" for w in ctx["web"]) or "(none)"
    return f"""You are an award-winning creative director making social content from a brief. No person appears on camera.
Everything is graphics, a real website shown on a phone, or UI.

THE BRIEF (this is what the client wants — follow it closely; it overrides the defaults below):
\"\"\"{brief}\"\"\"

Company facts (AXIMBRA, use when the brief is about AXIMBRA):
{playbook.AXIMBRA_FACTS}

Websites captured for the video (use their index in "shot"):
{sites}

The user's media library (put an id in "media"; clips are silent):
{shelf}
{must}

Source text you may draw facts from:
{pages}

{web}

{playbook.MARKETING_RULES}

{FORM_RULES.get(form, FORM_RULES["video"])}
Format: {aspect}{"" if still else f", about {seconds} seconds"}.
On-screen language: {_lang_name(lang)}.
{'Write a spoken narration line ("voice") for every scene: natural, conversational, max ~2.3 words per second of the scene.' if voice and not still else 'No narration: every message must be readable on screen. Leave "voice" empty.'}

Scene kinds (pick what fits the brief; a still slide reads best as statement, number, quote, photo, compare, steps,
problem, benefit, agents or cta — "site", "call" and "inbox" animate, so they belong in a video):
- "hook": scroll-stopping first line, 2–3 s. Must be TRUE.
- "statement": one bold sentence (headline) + optional sub. "center": true to center it.
- "problem" / "benefit": headline + 2–4 "lines" (max 6 words each).
- "steps": headline + 2–4 "lines" = numbered process steps.
- "compare": headline + "left_title" + "lines" (before) + "right_title" + "lines2" (after), 2–3 items each.
- "site": headline + sub, shows captured website "shot" (index) scrolling on a phone. Only if a site is listed above.
- "call": a phone call answered by an AI; "lines" = 3–4 short alternating turns, AI first, no speaker labels; optional "caller", "status".
- "inbox": an inbox being sorted; "app" = inbox title; "lines" = 3–5 items formatted "subject|category tag".
- "sms": a text message arriving on a phone, e.g. a booking confirmation; "caller" = sender name, "lines" = 1–3
  messages exactly as the customer receives them.
- "agents": headline + 3–6 "lines" (names), optional "tile_label".
- "photo": one image with the text. Set "media" to a library id, OR set "image_prompt" to have one generated
  (describe the picture in English: subject, setting, light, mood). "layout": "full" (text over the image) or
  "side" (image beside the text). Never ask for a recognisable real person.
- "gallery": headline + "medias" = 2–4 library ids shown in a grid.
- "clip": an uploaded video clip. "media" = a library id of kind "clip". A long recording is used in several
  consecutive "clip" scenes, each one a stretch of it: "from" = where the stretch starts (seconds into the
  clip), "speed" = playback speed (1, 1.5, 2, 3 or 4), "seconds" = screen time; the stretch covers
  seconds × speed of the recording, which must fit before the clip ends. "layout": "phone" shows it inside a
  phone frame (use this for a phone screen recording, i.e. a tall clip), "full" plays it behind the text.
  The clip is silent; the narration carries the sound.
  EDITING A SCREEN RECORDING (follow the clip's segments listed in the library):
  * "wait" (loading, spinner, login or consent screens, hesitation): skip it with "from", or play it at 4×.
  * "action" (typing, scrolling, tapping between screens): 2–3×, so it reads as momentum, not waiting.
  * "result" (the list sorts itself, a label or answer appears, a confirmation arrives): 1×, at least 2.5 s
    on screen, and the narration names what the viewer sees right then.
  * Keep the recording's order; never speed through text the narration talks about; a stretch of 1× after
    a fast one is what makes the result land.
  * Sign-in, account-chooser and consent screens prove the demo is real: keep them at 2–3×, do not cut them.
  * SUBTITLES: when the on-screen text of a stretch (listed as "on screen (xx)") is in another language than
    this video, put a short translation of it into that scene's "sub", in the video's language — e.g. Google's
    Hungarian "unverified app" warning gets an English sub in an English video. The viewer must understand
    every screen.
- "number": headline = a number FROM THE BRIEF OR SOURCES ONLY, sub = what it means.
- "quote": headline = a quote FROM THE BRIEF OR SOURCES ONLY, sub = its source.
- "cta": headline + "url" + sub + "button". Always last.
{'A still slide has no motion, so favour the kinds that hold up frozen, and let each carry more text than a video scene would. Never number the slides — no "slide 2", no "2/5"; the kicker is a real label or empty.' if still else ''}
Fields: headline max 8 words, mark 1–2 key words with *asterisks*; sub max 16 words; kicker optional, max 3 words.
Use the user's own uploaded media wherever it fits the brief — that is why they uploaded it. Ask for a generated
image only where nothing uploaded fits.

Pick a visual theme that fits the brief: "neon" (futuristic, default), "clean" (light, corporate), "warm" (energetic), "mono" (minimal).

HARD RULES:
- Never invent statistics, percentages, time or money savings, customers, testimonials, awards or results.
  Numbers and quotes may appear only if they are in the brief or the source text above.
- No prices unless the brief asks for them (then only from the facts list).
- Hungarian: formal-neutral, natural, no anglicisms where a Hungarian word exists.
- Also write the social post that goes with it (120–250 words in short paragraphs, a first line under 140
  characters that works alone, one genuine question to the reader at the end, max 3 hashtags) and a first
  comment holding the link. The post must stand on its own on any platform: do not tell the reader to swipe,
  and do not point to a comment or to a "link below" — some platforms show only the first slide and no comment.

Answer ONLY with JSON:
{{"title": "", "tagline": "max 3 words", "brand": "AXIMBRA or the brand in the brief", "theme": "neon|clean|warm|mono",
"scenes": [{{"kind": "", "kicker": "", "headline": "", "sub": "", "lines": [], "lines2": [], "left_title": "", "right_title": "",
  "shot": 0, "media": "", "from": 0, "speed": 1, "medias": [], "image_prompt": "", "layout": "full", "app": "", "caller": "", "status": "",
  "tile_label": "", "center": false, "url": "", "button": "", "voice": "", "seconds": 0}}],
"post": "", "first_comment": ""}}"""


WHAT = {"video": "short video script", "image": "single still image", "carousel": "carousel of still slides"}


def revise_prompt(script: dict, feedback: str, lang: str, form: str = "video") -> str:
    slim = {k: script[k] for k in ("title", "tagline", "brand", "theme", "scenes", "post", "first_comment") if k in script}
    still = form in ("image", "carousel")
    return f"""You are revising a {WHAT.get(form, WHAT["video"])}. Apply the client's feedback precisely; keep everything else as it is.
Same JSON structure, same scene kinds available (hook, statement, problem, benefit, steps, compare, site, call,
inbox, agents, number, quote, photo, gallery, clip, cta). Keep the "media" ids that are still wanted.
{'Keep it still: the same number of slides as now, no narration, leave "voice" empty.' if still else ''}
Language: {_lang_name(lang)}. Never invent statistics, customers, testimonials or results.
While fixing, keep to these rules:
{playbook.MARKETING_RULES}

FEEDBACK: \"\"\"{feedback}\"\"\"

CURRENT SCRIPT:
{json.dumps(slim, ensure_ascii=False)}

Answer ONLY with the full revised JSON."""


def _clip(s, n: int) -> str:
    s = re.sub(r"\s+", " ", str(s or "")).strip()
    return s if len(s) <= n else s[: n - 1].rstrip() + "…"


_TAIL_LABEL_RE = re.compile(r"\s*[|:–-]\s*(AI(\s+agent)?|Ügyfél|Hívó|Érdeklődő|Caller|Customer|Agent|Ügyintéző)\s*$", re.I)
_LABEL_RE = re.compile(r"^\s*(AI|Ügyfél|Hívó|Caller|Customer|Agent|Ügyintéző)\s*:\s*", re.I)
# A modell szeret diaszámot írni a kickerbe („3. SLIDE”). Az olvasónak semmit
# nem mond, a körhinta amúgy is számozza magát, ezért kiszedjük.
_SLIDENO_RE = re.compile(r"^\s*(?:\d+\s*[.)]?\s*(?:slide|dia|kép|oldal|jelenet|scene)|(?:slide|dia|kép|oldal|jelenet|scene)\s*[.:#]?\s*\d+)\s*$", re.I)
# Ha a brief címekkel jelöli a jeleneteket („2. jelenet: https://aximbra.hu/#agentek"),
# a rendező ezt egyszer szó szerint a képernyőre tette, levágva. Képernyőre URL
# csak a záróképen kerülhet (az a "url" mező), máshol kiszedjük.
_URL_RE = re.compile(r"\bhttps?://\S+|\bwww\.\S+|\b[a-z0-9-]+\.(?:hu|com|app|io|eu)(?:/\S*)?", re.I)


def _no_url(text) -> str:
    return re.sub(r"\s{2,}", " ", _URL_RE.sub("", str(text or ""))).strip(" -–—:|·")


SPEEDS = (1.0, 1.5, 2.0, 3.0, 4.0)


def _num(v, default: float, lo: float, hi: float) -> float:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, x))


def _fit_clip(s: dict, length: float) -> None:
    """A jelenet a felvétel egy szakasza: from-tól seconds × speed hosszan.
    Ha nem fér a felvétel végéig, előbb gyorsít (legfeljebb 4×), aztán rövidít."""
    if not length:
        return
    s["from"] = min(s.get("from") or 0.0, max(0.0, length - 1.0))
    avail = length - s["from"]
    if s["seconds"] * s["speed"] > avail:
        need = next((v for v in SPEEDS if v >= s["speed"] and s["seconds"] * v <= avail), None)
        if need:
            s["speed"] = need
        else:
            s["seconds"] = max(1.0, round(avail / s["speed"], 2))


def _media_id(v) -> str:
    v = str(v or "").strip()
    return v if re.fullmatch(r"[a-z0-9]{12}", v) else ""


def normalize(data: dict, seconds: int, n_shots: int = 1, form: str = "video") -> dict:
    """A modell kimenetéből érvényes, renderelhető forgatókönyv.

    Álló kép és körhinta ugyanebből készül: ott a jelenet egy dia, az idő
    csak a kirajzoláshoz kell, a kész fájlban nem jelenik meg."""
    if not isinstance(data, dict):
        raise VideoError("a forgatókönyv nem JSON objektum")
    still = form in ("image", "carousel")
    scenes = []
    for s in data.get("scenes") or []:
        if not isinstance(s, dict) or s.get("kind") not in KINDS:
            continue
        if s["kind"] == "site" and n_shots == 0:
            s = {**s, "kind": "statement"}
        try:
            sec = float(s.get("seconds") or 4)
        except (TypeError, ValueError):
            sec = 4.0
        try:
            shot = max(0, min(max(0, n_shots - 1), int(s.get("shot") or 0)))
        except (TypeError, ValueError):
            shot = 0
        lines = lambda key, n: [_clip(_LABEL_RE.sub("", l), 70) for l in
                                (_no_url(x) for x in (s.get(key) or [])) if l.strip()][:n]
        kicker = _no_url(s.get("kicker"))
        scenes.append({
            "kind": s["kind"], "kicker": "" if _SLIDENO_RE.match(kicker) else _clip(kicker, 28),
            "headline": _clip(_no_url(s.get("headline")), 80),
            "sub": _clip(_no_url(s.get("sub")), 140), "lines": lines("lines", 6), "lines2": lines("lines2", 4),
            "left_title": _clip(s.get("left_title"), 20), "right_title": _clip(s.get("right_title"), 20),
            "media": _media_id(s.get("media")),
            "medias": [m for m in (_media_id(x) for x in (s.get("medias") or [])) if m][:4],
            "image_prompt": _clip(s.get("image_prompt"), 400),
            "layout": (str(s.get("layout") or "").strip() if str(s.get("layout") or "").strip() in ("side", "phone")
                       else "full"),
            "from": _num(s.get("from"), 0.0, 0.0, 600.0),
            "speed": min(SPEEDS, key=lambda v: abs(v - _num(s.get("speed"), 1.0, 0.25, 8.0))),
            "shot": shot, "app": _clip(s.get("app"), 30), "caller": _clip(s.get("caller"), 24), "status": _clip(s.get("status"), 24),
            "tile_label": _clip(s.get("tile_label"), 12), "center": bool(s.get("center")),
            "url": _clip(re.sub(r"^https?://(www\.)?|/+$", "", str(s.get("url") or "").strip()), 40), "button": _clip(s.get("button"), 40),
            # Felolvasva a „https://" sem jó; a domain marad.
            "voice": _clip(re.sub(r"https?://(www\.)?", "", str(s.get("voice") or "")), 260),
            "seconds": max(2.0, min(12.0, sec)),
        })
    # A hívásbuborékba nem kell, ki beszél: az elején és a végén is levágjuk.
    for s in scenes:
        if s["kind"] == "call":
            s["lines"] = [l for l in (_TAIL_LABEL_RE.sub("", l).strip() for l in s["lines"]) if l]
    # Médiajelenet üres kézzel nem állja meg a helyét: szöveges lesz belőle.
    for s in scenes:
        if s["kind"] == "gallery" and not s["medias"]:
            s["kind"] = "statement"
        elif s["kind"] in ("photo", "clip") and not s["media"] and not s["image_prompt"]:
            s["kind"] = "statement"
    # Álló diához a mozgó jelenetek nem valók: azokból szöveges dia lesz.
    if still:
        for s in scenes:
            if s["kind"] in MOTION_KINDS:
                s["kind"] = "statement"
    # Ugyanaz az oldalrész kétszer: a néző ugyanazt látja kétszer, csak más
    # narrációval. Egy felvétel egyszer megy; a második egy még nem használtra
    # vált, ha van, különben szöveges jelenet lesz belőle.
    used: set = set()
    for s in scenes:
        if s["kind"] != "site":
            continue
        if s["shot"] in used:
            free = [i for i in range(n_shots) if i not in used]
            if not free:
                s["kind"] = "statement"
                continue
            s["shot"] = free[0]
        used.add(s["shot"])
    # A körhinta záró diával együtt fér bele a felső korlátba.
    cap = MAX_SLIDES - 1 if still else (MAX_SCENES_LONG if seconds > 90 else MAX_SCENES)
    scenes = [s for s in scenes if s["headline"] or s["kind"] in VISUAL_KINDS][:cap]
    if not scenes or (len(scenes) < 2 and form != "image"):
        raise VideoError("a forgatókönyvben túl kevés használható jelenet van")
    if form == "image":
        scenes = scenes[:1]
    # A klip nem lehet hosszabb, mint a felvett anyag.
    for s in scenes:
        if s["kind"] == "clip":
            m = media.get(s["media"]) or {}
            if m.get("kind") == "clip" and not media.ready(m):
                s["kind"] = "statement"      # még elmosás alatt, vagy elhasalt: nem mehet ki
            elif m.get("kind") != "clip":
                s["kind"] = "photo" if m.get("kind") == "image" else "statement"
            elif m.get("seconds"):
                _fit_clip(s, float(m["seconds"]))
    # Egyetlen kép magában áll, nem kell rá külön záró dia.
    if form != "image":
        ctas = [s for s in scenes if s["kind"] == "cta"]
        scenes = [s for s in scenes if s["kind"] != "cta"] + (ctas[-1:] or [{
            **scenes[-1], "kind": "cta", "headline": "Próbálja ki *élőben*", "sub": "", "lines": [], "url": "aximbra.hu",
            "button": "Élő demó · regisztráció nélkül", "voice": "", "seconds": 4.0}])
    for s in scenes:
        if s["kind"] == "cta" and not s["url"]:
            s["url"] = "aximbra.hu"
    if still:
        # A diákat a belépő mozgás vége után fotózzuk, ezért mindegyik egyforma hosszú.
        for s in scenes:
            s["seconds"] = 5.0
            s["voice"] = ""
    else:
        total = sum(s["seconds"] for s in scenes)
        target = max(MIN_TOTAL, min(MAX_TOTAL, seconds))
        k = target / total if total else 1
        for s in scenes:
            s["seconds"] = round(max(2.0, min(14.0, s["seconds"] * k)), 2)
            if s["kind"] == "clip":
                _fit_clip(s, float((media.get(s["media"]) or {}).get("seconds") or 0))
    # Az első másodpercek döntenek: a nyitókép rövid, hogy gyorsan jöjjön a lényeg.
    if not still and scenes[0]["kind"] == "hook":
        scenes[0]["seconds"] = min(scenes[0]["seconds"], HOOK_MAX)
    theme = data.get("theme") if data.get("theme") in THEMES else "neon"
    return {
        "title": _clip(data.get("title") or "Videó", 80), "tagline": _clip(data.get("tagline") or "", 24).upper(),
        "brand": _clip(data.get("brand") or "AXIMBRA", 20), "theme": theme, "scenes": scenes,
        "post": _cap_hashtags(str(data.get("post") or "").strip()[:3000]),
        "first_comment": str(data.get("first_comment") or "Élő demók: https://aximbra.hu").strip()[:500],
    }


HOOK_MAX = 3.5        # mp: a nyitókép eddig tart, a többi jelenet viszi a mondanivalót
MAX_HASHTAGS = 3
FIRST_LINE_MAX = 140  # karakter: a LinkedIn mobilon ennyi után vágja le a posztot
_HASHTAG_RE = re.compile(r"(?<![\w&])#\w+")


def _cap_hashtags(post: str) -> str:
    """Legfeljebb három hashtag; a többit kivesszük, a szöveg marad."""
    n = 0

    def keep(m):
        nonlocal n
        n += 1
        return m.group(0) if n <= MAX_HASHTAGS else ""
    out = _HASHTAG_RE.sub(keep, post)
    return re.sub(r"[ \t]{2,}", " ", out).strip() if n > MAX_HASHTAGS else post


def craft_issues(script: dict, form: str = "video") -> list[str]:
    """A kutatott marketingszabályok gépileg mérhető része (playbook.MARKETING_RULES).
    Ami itt akad, azt a modell egy javítókörben átírja."""
    out = []
    scenes = script["scenes"]
    for i, s in enumerate(scenes):
        if len(s["headline"].replace("*", "").split()) > 8:
            out.append(f"{i + 1}. jelenet: a címsor 8 szónál hosszabb, rövidítsd")
        if s["voice"] and not (s["headline"] or s["sub"] or s["lines"]) and s["kind"] not in VISUAL_KINDS:
            out.append(f"{i + 1}. jelenet: csak a hang mondja el, hang nélkül érthetetlen — tedd ki szövegként is")
    if form == "video" and scenes and scenes[0]["kind"] not in ("hook", "statement", "problem", "number", "photo", "clip", "call"):
        out.append("az első jelenet nem ragadja meg a figyelmet: nyiss a néző problémájával, nagy címsorral")
    brand = (script.get("brand") or "").lower()
    if form != "image" and brand and len(scenes) > 2:
        said = " ".join(t for s in scenes if s["kind"] != "cta" for t in _scene_texts(s)).lower()
        if brand not in said and brand not in script.get("post", "").lower():
            out.append(f"a márkanév ({script['brand']}) nem hangzik el és nincs leírva a záró kép előtt")
    first = next((l for l in (script.get("post") or "").splitlines() if l.strip()), "")
    if len(first) > FIRST_LINE_MAX:
        out.append(f"a poszt első sora {len(first)} karakter: {FIRST_LINE_MAX} alatt kell megfognia, a hírfolyam ott vágja")
    return out


# ---- ellenőrzés -------------------------------------------------------------

_CLAIM_RE = re.compile(r"\d+(?:[.,]\d+)?|\bszázalék|\bpercent|\bügyfel(ünk|eink)|\breferenci|\besettanulmány|\bgarant|\bnulla\b|"
                       r"\bsoha\s+többé|\bminden\s+(hívás|levél|ügyfél)|\bzero\b|\bnever\s+again|\bguarante|\bour\s+clients", re.I)


def _allowed_numbers(*texts: str) -> set[str]:
    return set(re.findall(r"\d+(?:[.,]\d+)?", " ".join(texts)))


def _unsupported(text: str, ok_nums: set[str]) -> bool:
    """Igaz, ha a szövegben olyan szám vagy állítás van, ami nincs a forrásokban."""
    for m in _CLAIM_RE.finditer(text or ""):
        if m.group(0)[0].isdigit() and m.group(0) in ok_nums:
            continue
        return True
    return False


def _scene_texts(s: dict) -> list[str]:
    return [s["headline"], s["sub"], s["voice"], s["kicker"], *s["lines"], *s["lines2"]]


def violations(script: dict, sources: str) -> list[str]:
    """Alátámasztatlan állítások: szám a forrásokon kívülről, ügyfélre vagy
    referenciára hivatkozás, garancia."""
    ok = _allowed_numbers(sources, playbook.AXIMBRA_FACTS)
    out = []
    for i, s in enumerate(script["scenes"]):
        out += [f"{i + 1}. jelenet: „{t}”" for t in _scene_texts(s) if _unsupported(t, ok)]
    # A poszt szövege ugyanúgy nyilvános, mint a videó: ott sem lehet kitalált állítás.
    out += [f"poszt: „{t}”" for t in _sentences(script.get("post", "")) if _unsupported(t, ok)]
    return list(dict.fromkeys(out))


def _sentences(text: str) -> list[str]:
    """Mondatok; a linket és a hashtageket nem vágjuk szét."""
    return [t for t in re.split(r"(?<=[.!?])\s+|\n+", text or "") if t.strip()]


def _strip_claims(script: dict, sources: str) -> dict:
    """Ami a javítás után is alátámasztatlan, az kimarad."""
    ok = _allowed_numbers(sources, playbook.AXIMBRA_FACTS)
    for s in script["scenes"]:
        for key in ("sub", "voice", "kicker"):
            if _unsupported(s[key], ok):
                s[key] = ""
        s["lines"] = [l for l in s["lines"] if not _unsupported(l, ok)]
        s["lines2"] = [l for l in s["lines2"] if not _unsupported(l, ok)]
    script["scenes"] = [s for s in script["scenes"] if s["kind"] == "cta" or not _unsupported(s["headline"], ok)]
    if script.get("post"):
        kept = [t for t in re.split(r"(?<=[.!?])[ \t]+", script["post"])
                if not _unsupported(t, ok) or t.strip().startswith("http")]
        script["post"] = " ".join(kept).strip()
    return script


def fill_images(script: dict, aspect: str, say=lambda m: None) -> dict:
    """A kért, de még nem létező képek legenerálása. Ha a képgenerálás nem
    elérhető, a jelenet szöveges marad — a videó ettől még elkészül."""
    wanted = [s for s in script["scenes"] if s["kind"] == "photo" and not s["media"] and s["image_prompt"]]
    if not wanted:
        return script
    if not imagegen.available():
        for s in wanted:
            s["kind"] = "statement"
        return script
    say(f"Képgenerálás: {len(wanted)} kép…")
    made = 0
    for s in wanted[:4]:
        stop.check()
        m = imagegen.generate_into_library(s["image_prompt"], aspect, name=s["headline"] or "jelenetkép")
        if m:
            s["media"], made = m["id"], made + 1
        else:
            s["kind"] = "statement"
    for s in wanted[4:]:
        s["kind"] = "statement"
    if not made:
        say("Képgenerálás: most nem elérhető, szöveges jelenet lesz.")
    else:
        free = sum(1 for s in wanted if (media.get(s["media"]) or {}).get("source") == "generated-free")
        say(f"Képgenerálás: {made} kép készült." + (f" Ebből {free} az ingyenes forrásból, vízjellel." if free else ""))
    return script


def write_script(brief: str, ctx: dict, seconds: int, lang: str, aspect: str, voice: bool,
                 say=lambda m: None, form: str = "video") -> dict:
    raw = llm._ask(director_prompt(brief, ctx, seconds, lang, aspect, voice, form))
    script = normalize(llm.extract_json(raw), seconds, len(ctx["urls"]), form)
    return check(script, brief, ctx, seconds, lang, say, form)


def check(script: dict, brief: str, ctx: dict, seconds: int, lang: str, say=lambda m: None,
          form: str = "video") -> dict:
    sources = brief + " " + " ".join(p["text"] for p in ctx["pages"]) + " " + " ".join(w["text"] for w in ctx["web"])
    v = violations(script, sources)
    craft = craft_issues(script, form)
    if v or craft:
        say("Ellenőrzés: " + ", ".join(x for x in (f"{len(v)} alátámasztatlan állítás" if v else "",
                                                   f"{len(craft)} marketinghiba" if craft else "") if x) + ", javítom…")
        fb = ""
        if v:
            fb += "Remove or rewrite these unsupported claims (numbers, guarantees, customers not in the brief):\n" + "\n".join(v) + "\n"
        if craft:
            fb += "Fix these craft problems (they break the proven rules):\n" + "\n".join(craft)
        try:
            script = normalize(llm.extract_json(llm._ask(revise_prompt(script, fb, lang, form))),
                               seconds, len(ctx["urls"]), form)
        except (llm.LLMError, VideoError) as e:
            logger.warning("javító kör hiba: %s", e)
        script = _strip_claims(script, sources)
        if len(script["scenes"]) < (1 if form == "image" else 2):
            raise VideoError("az ellenőrzés után túl kevés jelenet maradt")
    return script


# ---- hang ---------------------------------------------------------------------

def _pcm_to_wav(pcm: bytes, rate: int = SAMPLE_RATE) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm)
    return buf.getvalue()


# A magyar felolvasó az angol szavakat magyarul ejti ("a-gent"). Ezért a
# hangnak kiejtés szerint írjuk át őket; a felirat helyesírva marad.
# A toldalék megmarad: agentje → édzsentje, agenteket → édzsenteket.
SAY_HU = [
    (r"\baximbra\.hu\b", "akszimbra pont hu"),
    (r"\bAXIMBRA\b|\bAximbra\b", "Akszimbra"),
    (r"\bAI[- ]?agent", "éjáj édzsent"),
    (r"\bagent", "édzsent"),
    (r"\bAgent", "Édzsent"),
    (r"\bAI\b", "éjáj"),
    (r"\be-mail", "ímél"),
    (r"\bE-mail", "Ímél"),
    (r"\binbox", "inboksz"),
    (r"\bkkv", "kákávé"),
    (r"\bKKV", "kákávé"),
    (r"\bonline\b", "onlájn"),
    (r"\bchatbot", "csetbot"),
    (r"\bNIS2\b", "nisz kettő"),
]


def spoken(text: str, lang: str) -> str:
    """A felolvasónak átadott szöveg: magyarnál kiejtés szerint átírva."""
    if lang != "hu":
        return text
    for pat, rep_ in SAY_HU:
        text = re.sub(pat, rep_, text)
    return text


def _tts_gemini(text: str, lang: str) -> bytes | None:
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not key:
        return None
    model = os.environ.get("GEMINI_TTS_MODEL", "gemini-2.5-flash-preview-tts")
    body = {"contents": [{"parts": [{"text": text}]}],
            "generationConfig": {"responseModalities": ["AUDIO"], "speechConfig": {
                "voiceConfig": {"prebuiltVoiceConfig": {"voiceName": VOICES[lang]["gemini"]}}}}}
    # Az ingyenes szint percenként csak néhány felolvasást enged: ilyenkor
    # kivárjuk, különben a videó közepén elnémulna. A napi keretnél feladjuk.
    for attempt in range(5):
        try:
            r = httpx.post(llm.GEMINI_URL.format(model=model), headers={"x-goog-api-key": key}, json=body, timeout=90)
        except httpx.HTTPError:
            return None
        if r.status_code == 429 and "per day" not in r.text.lower() and "perday" not in r.text.lower():
            stop.sleep(min(60, 20 * (attempt + 1)))
            continue
        break
    if r.status_code >= 400:
        logger.info("gemini tts nem elérhető: %s", r.status_code)
        return None
    try:
        data = r.json()["candidates"][0]["content"]["parts"][0]["inlineData"]["data"]
    except (KeyError, IndexError, ValueError):
        return None
    return _pcm_to_wav(base64.b64decode(data))


# Nyelvenkénti alapértelmezett hang (a meglévő videók hangjával egyezik):
# magyar: Laura, angol: Bella. Környezeti változóval felülírható.
ELEVEN_VOICES = {"hu": "FGY2WhTYpPnrIDTdsKH5", "en": "hpp4J3VqNfWAUOO0d1Us"}


def elevenlabs_voice(lang: str, male: bool = False) -> str:
    """Sorrend: férfihang (ha kérték) → ELEVENLABS_VOICE_ID_<NYELV> → nyelvi alapértelmezés → ELEVENLABS_VOICE_ID."""
    env = os.environ.get
    if male and (env("ELEVENLABS_VOICE_ID_MALE") or "").strip():
        return env("ELEVENLABS_VOICE_ID_MALE").strip()
    return ((env(f"ELEVENLABS_VOICE_ID_{lang.upper()}") or "").strip()
            or ELEVEN_VOICES.get(lang, "")
            or (env("ELEVENLABS_VOICE_ID") or "").strip())


def _tts_elevenlabs(text: str, lang: str, male: bool) -> bytes | None:
    """ElevenLabs, ha van kulcs és hang. A modell a magyart is ismeri."""
    key = os.environ.get("ELEVENLABS_API_KEY", "").strip()
    voice = elevenlabs_voice(lang, male)
    if not key or not voice.strip():
        return None
    model = os.environ.get("ELEVENLABS_MODEL", "eleven_flash_v2_5")
    try:
        r = httpx.post(f"https://api.elevenlabs.io/v1/text-to-speech/{voice.strip()}",
                       params={"output_format": f"pcm_{SAMPLE_RATE}"}, headers={"xi-api-key": key},
                       json={"text": text, "model_id": model, "language_code": lang}, timeout=90)
    except httpx.HTTPError:
        return None
    if r.status_code >= 400 or not r.content:
        logger.info("elevenlabs tts hiba: %s %s", r.status_code, r.text[:200])
        return None
    return _pcm_to_wav(r.content)


def _tts_edge(text: str, lang: str, male: bool) -> bytes | None:
    try:
        import edge_tts
    except ImportError:
        return None
    voice = VOICES[lang]["edge_male" if male else "edge"]
    try:
        with tempfile.TemporaryDirectory() as d:
            mp3 = os.path.join(d, "v.mp3")
            asyncio.run(edge_tts.Communicate(text, voice).save(mp3))
            out = subprocess.run([_ffmpeg(), "-hide_banner", "-loglevel", "error", "-i", mp3, "-f", "wav",
                                  "-ac", "1", "-ar", str(SAMPLE_RATE), "-"], capture_output=True, timeout=60)
            return out.stdout if out.returncode == 0 and out.stdout else None
    except Exception as e:  # noqa: BLE001 — nem hivatalos szolgáltatás; ha nem megy, néma videó lesz
        logger.info("edge tts hiba: %s", e)
        return None


def _wav_pcm(wav_bytes: bytes) -> bytes:
    with wave.open(io.BytesIO(wav_bytes)) as w:
        if w.getframerate() != SAMPLE_RATE or w.getnchannels() != 1 or w.getsampwidth() != 2:
            raise VideoError("váratlan hangformátum")
        return w.readframes(w.getnframes())


def narrate(script: dict, lang: str, male: bool, say=lambda m: None) -> tuple[bytes | None, str]:
    """Jelenetenkénti felolvasás; a jelenetet a narrációhoz nyújtja.
    Visszaadja a teljes hangsávot (WAV) és a használt motor nevét.

    Egy videón belül egy hang szól. Ha a választott felolvasó menet közben
    akad el (pl. a napi ingyenes keret az első jelenet után fogy el), a
    narrációt elölről kezdjük a következővel, nem keverjük a két hangot."""
    engines = (("elevenlabs", lambda t: _tts_elevenlabs(t, lang, male)),
               ("gemini", lambda t: _tts_gemini(t, lang)),
               ("edge", lambda t: _tts_edge(t, lang, male)))
    names = {"elevenlabs": "ElevenLabs", "gemini": "Gemini", "edge": "Edge"}
    if not any(s["voice"] for s in script["scenes"]):
        return None, ""
    clips, engine = None, ""
    for name, speak in engines:
        got = []
        for s in script["scenes"]:
            stop.check()
            if not s["voice"]:
                got.append(b"")
                continue
            wav = speak(spoken(s["voice"], lang))
            if not wav:
                got = None
                break
            got.append(_wav_pcm(wav))
        if got is not None:
            clips, engine = got, name
            break
        if name != "elevenlabs" or os.environ.get("ELEVENLABS_API_KEY"):
            say(f"Hang: a(z) {names[name]} felolvasó elakadt, a következővel próbálom.")
    if clips is None:
        say("Hang: egyik felolvasó sem érhető el, néma videó készül felirattal.")
        return None, ""
    track = bytearray()
    for s, pcm in zip(script["scenes"], clips):
        dur = len(pcm) / 2 / SAMPLE_RATE
        s["seconds"] = round(max(s["seconds"], dur + 0.7), 2)
        lead = int(0.25 * SAMPLE_RATE) * 2
        room = int(s["seconds"] * SAMPLE_RATE) * 2
        seg = (b"\x00" * lead + pcm)[:room]
        track += seg + b"\x00" * (room - len(seg))
    return _pcm_to_wav(bytes(track)), engine


# ---- renderelés -------------------------------------------------------------

def _ffmpeg() -> str:
    exe = os.environ.get("FFMPEG_PATH")
    if exe:
        return exe
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()


def _launch(pw):
    path = os.environ.get("CHROMIUM_PATH") or None
    proxy = {"server": os.environ["CHROMIUM_PROXY"]} if os.environ.get("CHROMIUM_PROXY") else None
    return pw.chromium.launch(executable_path=path, proxy=proxy, args=["--no-sandbox", "--disable-dev-shm-usage"])


def capture_site(browser, url: str, phone_w: int) -> dict | None:
    """Az oldal mobilnézetben, legfeljebb 3200 px, végiggörgetve. Ha a címben
    szakasz van (https://aximbra.hu/#agentek), attól a szakasztól indul — így
    egy hosszú oldal lejjebb lévő részei is bekerülhetnek a videóba."""
    page = browser.new_page(viewport={"width": 390, "height": 844}, device_scale_factor=2,
                            ignore_https_errors=bool(os.environ.get("CHROMIUM_PROXY")))
    try:
        base, _, frag = url.partition("#")
        page.goto(base or url, wait_until="networkidle", timeout=45000)
        page.wait_for_timeout(2500)
        total = page.evaluate("document.documentElement.scrollHeight")
        top = 0
        if frag and re.fullmatch(r"[A-Za-z][\w-]{0,60}", frag):
            top = int(page.evaluate(
                "(id) => { const el = document.getElementById(id);"
                " return el ? el.getBoundingClientRect().top + window.scrollY : 0; }", frag) or 0)
        top = max(0, min(top, max(0, total - 844)))
        height = max(844, min(3200, total - top))
        # Az oldal lejjebb lévő részei csak görgetéskor úsznak be; görgetés
        # nélkül a képen feketék maradnak. Ezért előbb végiggörgetjük.
        for y in range(0, top + height + 844, 350):
            page.evaluate(f"window.scrollTo(0, {y})")
            page.wait_for_timeout(220)
        page.evaluate(f"window.scrollTo(0, {top})")
        page.wait_for_timeout(1500)
        png = page.screenshot(clip={"x": 0, "y": top, "width": 390, "height": height}, full_page=True)
        return {"src": "data:image/png;base64," + base64.b64encode(png).decode(), "height": round(height * phone_w / 390)}
    except Exception as e:  # noqa: BLE001 — az oldal nélkül is elkészülhet a videó
        logger.warning("képernyőkép hiba (%s): %s", url, e)
        return None
    finally:
        page.close()


PHONE_SCREEN_W = {"9:16": 258, "4:5": 192, "1:1": 184, "16:9": 198}
# Álló videóban a telefon kisebb (a platformok alsó sávja fölé kell férnie,
# lásd body.vid a sablonban): 212 px széles, 9 px kerettel. A felvétel ehhez
# méretezett magasságából számolja a sablon a görgetést; a régi szélességgel
# túlfutott az oldal végén, és fekete rész látszott.
PHONE_SCREEN_W_VIDEO = 194


@contextlib.contextmanager
def _staged(script: dict, urls: list[str], aspect: str, captions: bool, stills: bool, say):
    """A kirajzolt lap, felkészítve a léptetésre. A sablon és a médiafájlok
    egy ideiglenes mappába kerülnek, így a lap saját fájlként éri el őket."""
    from playwright.sync_api import sync_playwright

    w, h = ASPECTS[aspect]
    with tempfile.TemporaryDirectory() as work, sync_playwright() as pw:
        shutil.copyfile(TEMPLATE, os.path.join(work, "index.html"))
        lib = {}
        for sc in script["scenes"]:
            for mid in ([sc.get("media")] if sc.get("media") else []) + (sc.get("medias") or []):
                if mid and mid not in lib:
                    m = media.get(mid)
                    if m and media.copy_out(mid, work):
                        lib[mid] = {"src": m["file"], "kind": m["kind"], "width": m.get("width"),
                                    "height": m.get("height"), "seconds": m.get("seconds")}
        browser = _launch(pw)
        try:
            used = sorted({s["shot"] for s in script["scenes"] if s["kind"] == "site"})
            shots = [None] * len(urls)
            for i in used:
                if i < len(urls):
                    say(f"Weboldal felvétele: {urls[i]}")
                    shots[i] = capture_site(browser, urls[i], PHONE_SCREEN_W_VIDEO if aspect == "9:16" and not stills
                                            else PHONE_SCREEN_W[aspect])
            scenes = []
            for sc in script["scenes"]:
                if sc["kind"] == "site" and not (sc["shot"] < len(shots) and shots[sc["shot"]]):
                    sc = {**sc, "kind": "statement"}
                elif sc["kind"] in MEDIA_KINDS:
                    have = [m for m in ([sc.get("media")] if sc.get("media") else []) + (sc.get("medias") or []) if m in lib]
                    if not have:
                        sc = {**sc, "kind": "statement"}
                scenes.append(sc)
            page = browser.new_page(viewport={"width": w, "height": h}, device_scale_factor=2)
            page.goto("file://" + os.path.join(work, "index.html"), wait_until="networkidle", timeout=45000)
            total = page.evaluate("(cfg) => build(cfg)", {**script, "scenes": scenes, "aspect": aspect,
                                                          "shots": shots, "captions": captions,
                                                          "lib": lib, "stills": stills})
            page.evaluate("document.fonts.ready.then(() => true)")
            page.wait_for_timeout(400)
            # A klipek első képkockája legyen meg, mielőtt léptetni kezdjük.
            page.evaluate("""() => Promise.all([...document.querySelectorAll('video')].map((v) =>
                v.readyState >= 2 ? null : new Promise((r) => {
                  v.addEventListener('loadeddata', r, {once: true}); setTimeout(r, 4000); })))""")
            yield page, total, scenes, work
        finally:
            browser.close()


def render(script: dict, urls: list[str], out_path: str, aspect: str, audio: bytes | None,
           captions: bool, say=lambda m: None) -> float:
    w, h = ASPECTS[aspect]
    tmp = out_path + ".part.mp4"
    with _staged(script, urls, aspect, captions, False, say) as (page, total, _scenes, work):
        frames = int(total * FPS)
        say(f"Renderelés: {frames} képkocka ({total:.0f} mp, {aspect})…")
        inputs = ["-f", "image2pipe", "-framerate", str(FPS), "-c:v", "mjpeg", "-i", "-"]
        maps = []
        if audio:
            apath = os.path.join(work, "a.wav")
            with open(apath, "wb") as f:
                f.write(audio)
            inputs += ["-i", apath]
            maps = ["-map", "0:v", "-map", "1:a", "-c:a", "aac", "-b:a", "160k", "-shortest"]
        cmd = [_ffmpeg(), "-hide_banner", "-loglevel", "error", "-y", *inputs, *maps,
               "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
               "-vf", f"scale={w * 2}:{h * 2}:flags=lanczos", "-movflags", "+faststart", tmp]
        proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            step = max(1, frames // 5)
            for f in range(frames):
                stop.check()
                page.evaluate("(ms) => seek(ms)", f * 1000 / FPS)  # a klipeket is idejére állítja
                proc.stdin.write(page.screenshot(type="jpeg", quality=92))
                if f and f % step == 0:
                    say(f"Renderelés: {round(100 * f / frames)}%")
            proc.stdin.close()
            err = proc.stderr.read().decode(errors="replace")
            if proc.wait(timeout=300) != 0:
                raise VideoError(f"az ffmpeg hibát jelzett: {err[:300]}")
        except BaseException:
            proc.kill()
            proc.wait()
            try:
                os.remove(tmp)
            except OSError:
                pass
            raise
    os.replace(tmp, out_path)
    return total


def render_stills(script: dict, urls: list[str], out_dir: str, vid: str, aspect: str,
                  say=lambda m: None) -> list[str]:
    """Diánként egy JPEG. A képet a jelenet legvégén fotózzuk: ott már minden
    belépő mozgás lefutott, és álló képnél nincs kimenő halványítás."""
    files = []
    with _staged(script, urls, aspect, False, True, say) as (page, _total, scenes, _work):
        say(f"Képek rajzolása: {len(scenes)} dia ({aspect})…")
        for i in range(len(scenes)):
            stop.check()
            page.evaluate("(i) => slide(i)", i)
            name = f"{vid}-{i + 1}.jpg"
            page.screenshot(path=os.path.join(out_dir, name), type="jpeg", quality=94)
            files.append(name)
    return files


def design_logos(brief: str, ctx: dict, lang: str, say=lambda m: None, feedback: str = "",
                 previous: list[str] | None = None) -> dict:
    """A modell SVG-változatai, megtisztítva. Egy újrapróbálás jár, ha
    egyetlen használható változat sem jött."""
    pages = "\n\n".join(f"{p['url']}:\n{p['text'][:1500]}" for p in ctx.get("pages") or [] if p.get("text"))
    prompt = logomaker.logo_prompt(brief, pages, lang, feedback, previous)
    for attempt in range(2):
        stop.check()
        out = logomaker.parse(llm._ask(prompt))
        good = []
        for v in out["variants"]:
            try:
                good.append({"idea": v["idea"], "svg": logomaker.sanitize(v["svg"])})
            except logomaker.LogoError as e:
                logger.info("logóváltozat elvetve: %s", e)
        if good:
            if len(good) < len(out["variants"]):
                say(f"{len(out['variants']) - len(good)} hibás változatot elvetettem.")
            return {"title": out["title"], "variants": good}
        say("A modell nem adott használható SVG-t, újrapróbálom…")
    raise VideoError("a modell nem adott használható logót")


def render_logos(variants: list[dict], out_dir: str, vid: str, say=lambda m: None) -> tuple[list[str], list[str]]:
    """Változatonként egy 1080×1080-as PNG, mellé a vektoros SVG."""
    from playwright.sync_api import sync_playwright

    files, vectors = [], []
    say(f"Logók rajzolása: {len(variants)} változat…")
    with sync_playwright() as pw:
        browser = _launch(pw)
        try:
            page = browser.new_page(viewport={"width": logomaker.SIZE, "height": logomaker.SIZE})
            for i, v in enumerate(variants, 1):
                stop.check()
                page.set_content(f'<!doctype html><body style="margin:0;background:#04040C">{v["svg"]}</body>')
                page.wait_for_timeout(150)
                name = f"{vid}-{i}.png"
                page.screenshot(path=os.path.join(out_dir, name), type="png",
                                clip={"x": 0, "y": 0, "width": logomaker.SIZE, "height": logomaker.SIZE})
                with open(os.path.join(out_dir, f"{vid}-{i}.svg"), "w", encoding="utf-8") as f:
                    f.write(v["svg"])
                files.append(name)
                vectors.append(f"{vid}-{i}.svg")
        finally:
            browser.close()
    return files, vectors


def vector_path(vid: str, n: int) -> str | None:
    """A logó n-edik változatának SVG-je."""
    meta = get_meta(vid)
    vectors = (meta or {}).get("vectors") or []
    if not 1 <= n <= len(vectors):
        return None
    p = os.path.join(VIDEO_DIR, vectors[n - 1])
    return p if os.path.exists(p) else None


# ---- tárolás ----------------------------------------------------------------

def _meta_path(vid: str) -> str:
    return os.path.join(VIDEO_DIR, f"{vid}.json")


def _valid_id(vid: str) -> bool:
    return bool(re.fullmatch(r"[a-z0-9]{12}", vid or ""))


def video_path(vid: str) -> str | None:
    """A videófájl, ha ez a darab videó."""
    if not _valid_id(vid):
        return None
    p = os.path.join(VIDEO_DIR, f"{vid}.mp4")
    return p if os.path.exists(p) else None


def asset_path(vid: str, n: int | None = None) -> str | None:
    """A videó, vagy képes darabnál az n-edik dia (1-től)."""
    if not _valid_id(vid):
        return None
    meta = _read_meta(vid)
    files = (meta or {}).get("files") or []
    if not files:
        return video_path(vid)
    idx = 0 if n is None else n - 1
    if not 0 <= idx < len(files):
        return None
    p = os.path.join(VIDEO_DIR, files[idx])
    return p if os.path.exists(p) else None


def _read_meta(vid: str) -> dict | None:
    if not _valid_id(vid):
        return None
    try:
        with open(_meta_path(vid), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def get_meta(vid: str) -> dict | None:
    """A leírás, ha a hozzá tartozó fájlok tényleg megvannak."""
    meta = _read_meta(vid)
    if not meta:
        return None
    files = meta.get("files") or []
    if files:
        return meta if all(os.path.exists(os.path.join(VIDEO_DIR, f)) for f in files) else None
    return meta if video_path(vid) else None


def list_videos() -> list[dict]:
    if not os.path.isdir(VIDEO_DIR):
        return []
    out = []
    for name in os.listdir(VIDEO_DIR):
        if name.endswith(".json"):
            m = get_meta(name[:-5])
            if m:
                out.append(m)
    return sorted(out, key=lambda m: m.get("created_at", ""), reverse=True)


def mark_posted(vid: str, results: dict) -> dict | None:
    """Hova és mikor ment ki a videó; a felület ezt mutatja."""
    meta = get_meta(vid)
    if not meta:
        return None
    posted = dict(meta.get("posted") or {})
    posted.update({k: {"id": v, "at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
                   for k, v in results.items()})
    meta["posted"] = posted
    with open(_meta_path(vid), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False)
    return meta


def delete(vid: str) -> bool:
    meta = _read_meta(vid)
    files = ((meta or {}).get("files") or []) + ((meta or {}).get("vectors") or [])
    paths = [os.path.join(VIDEO_DIR, f) for f in files] or ([video_path(vid)] if video_path(vid) else [])
    if not paths:
        return False
    for path in paths + [_meta_path(vid)]:
        try:
            os.remove(path)
        except OSError:
            pass
    return True


def _prune():
    for m in list_videos()[KEEP:]:
        delete(m["id"])


def _finish(script: dict, opts: dict, ctx: dict, say, parent: str | None = None) -> dict:
    os.makedirs(VIDEO_DIR, exist_ok=True)
    form = opts.get("form") or "video"
    vid = secrets.token_hex(6)
    try:
        return _produce(script, opts, ctx, say, parent, form, vid)
    except BaseException:
        # Leállítás vagy hiba: a félkész fájlok ne maradjanak a mappában.
        for name in os.listdir(VIDEO_DIR):
            if name.startswith(vid):
                try:
                    os.remove(os.path.join(VIDEO_DIR, name))
                except OSError:
                    pass
        raise


def _produce(script: dict, opts: dict, ctx: dict, say, parent: str | None, form: str, vid: str) -> dict:
    started = time.time()
    audio, engine, total, files, vectors = None, "", 0.0, [], []
    if form == "logo":
        files, vectors = render_logos(script.pop("logo_variants"), VIDEO_DIR, vid, say)
        done = f"{len(files)} logóváltozat"
    elif form in ("image", "carousel"):
        files = render_stills(script, ctx["urls"], VIDEO_DIR, vid, opts["aspect"], say)
        done = f"{len(files)} kép"
    else:
        if opts["voice"]:
            say("Hangalámondás…")
            audio, engine = narrate(script, opts["lang"], opts.get("male", False), say)
            if engine:
                say(f"Hang kész ({ {'elevenlabs': 'ElevenLabs', 'gemini': 'Gemini'}.get(engine, 'Edge')} felolvasó).")
        total = render(script, ctx["urls"], os.path.join(VIDEO_DIR, f"{vid}.mp4"), opts["aspect"], audio,
                       captions=any(sc["voice"] for sc in script["scenes"]), say=say)
        files = [f"{vid}.mp4"]
        done = f"{total:.0f} mp"
    meta = {"id": vid, "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "parent": parent,
            "form": form, "files": files, "vectors": vectors, "slides": len(files) if form != "video" else 0,
            "brief": opts["brief"], "opts": opts, "ctx_urls": ctx["urls"], "voice_engine": engine,
            "seconds": round(total, 1), **script}
    # Az utolsó pont, ahol még megállhatunk: a leírás kiírása után már kész darab van.
    stop.check()
    with open(_meta_path(vid), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False)
    _prune()
    say(f"Kész: {script['title']} — {done}, {time.time() - started:.0f} mp alatt.")
    return meta


# A magyar szavak toldalékolódnak, ezért a szótőre keresünk: a „körhintát”
# és a „képeket” ugyanúgy megtaláljuk, mint az alapalakot.
FORM_WORDS = {
    "image": ("kép", "kep", "image", "poszter"),
    "carousel": ("körhint", "korhint", "carousel", "diasor", "több kép", "tobb kep", "slide", "diasor"),
    "video": ("videó", "video", "reels", "reel", "tiktok"),
}
# Magyarázó tartalom, ha a formát nem nevezted meg: a körhinta a LinkedInen
# 2–3-szor tovább tartja az olvasót, mint egy kép (playbook, 15. szabály).
EXPLAINER_WORDS = ("tipp", "lépés", "lepes", "hogyan", "útmutató", "utmutato", "checklist", "ellenőrzőlist",
                   "ellenorzolist", "how to")
# A logó szavai megelőznek mindent: a „kör alakú kép logó” logó, nem kép.
LOGO_WORDS = ("logó", "logo", "profilkép", "profilkep", "embléma", "emblema", "arculati jel")


def pick_form(brief: str) -> str:
    """Ha nem mondtad meg, a leírás szavaiból találjuk ki, mit kérsz."""
    text = (brief or "").lower()
    if any(w in text for w in LOGO_WORDS):
        return "logo"
    hits = {f: min((text.find(w) for w in words if w in text), default=-1) for f, words in FORM_WORDS.items()}
    named = {f: i for f, i in hits.items() if i >= 0}
    if named:
        return min(named, key=named.get)
    return "carousel" if any(w in text for w in EXPLAINER_WORDS) else "video"


FORM_NAMES = {"video": "videó", "image": "kép", "carousel": "körhinta", "logo": "logó"}


def make(brief: str, seconds: int = 30, lang: str = "hu", aspect: str = "9:16", voice: bool = True,
         male: bool = False, research: bool = False, form: str = "auto", say=lambda m: None,
         attach: list | None = None) -> dict:
    brief = (brief or "").strip()[:4000]
    if len(brief) < 8:
        raise VideoError("írd le, mit készítsek")
    if aspect not in ASPECTS:
        raise VideoError("ismeretlen képarány")
    if form not in FORMS:
        raise VideoError("ismeretlen formátum")
    if form == "auto":
        form = pick_form(brief)
        say(f"Formátum a leírás alapján: {FORM_NAMES[form]}.")
    attach = _wait_ready([m for m in (attach or []) if media.get(m)][:8], say)
    opts = {"brief": brief, "seconds": seconds, "lang": lang, "aspect": aspect, "voice": voice,
            "male": male, "research": research, "form": form, "attach": attach}
    say("Kontextus: linkek beolvasása…")
    ctx = gather(brief, research, say)
    ctx["attached"] = attach
    if attach:
        say(f"Csatolt média: {len(attach)} db — a rendező mindet felhasználja.")
    if form == "logo":
        opts["aspect"] = "1:1"
        say("Logótervezés…")
        return _finish(_logo_script(design_logos(brief, ctx, lang, say)), opts, ctx, say)
    say("Forgatókönyv írása…")
    script = write_script(brief, ctx, seconds, lang, aspect, voice, say, form)
    script = fill_images(script, aspect, say)
    say(f"Forgatókönyv kész: {script['title']} ({len(script['scenes'])} "
        f"{'dia' if form != 'video' else 'jelenet'}, {script['theme']} stílus).")
    return _finish(script, opts, ctx, say)


ATTACH_WAIT_SECONDS = 20 * 60


def _wait_ready(ids: list, say=lambda m: None) -> list:
    """A csatolt klipek közül amelyik még elmosás alatt van, azt megvárjuk
    (legfeljebb ATTACH_WAIT_SECONDS-ig). Ami elhasalt, az kimarad: elmosás
    nélkül nem mehet ki."""
    deadline = time.time() + ATTACH_WAIT_SECONDS
    told = False
    while True:
        metas = [media.get(i) for i in ids]
        busy = [m for m in metas if m and m.get("status") == "processing"]
        if not busy or time.time() > deadline:
            break
        if not told:
            say(f"Várom a csatolt felvétel elmosását és elemzését ({len(busy)} db)…")
            told = True
        stop.sleep(5)
    ok = [m["id"] for m in (media.get(i) for i in ids) if media.ready(m)]
    if len(ok) < len(ids):
        say(f"{len(ids) - len(ok)} csatolt fájl kimarad: az elmosása nem sikerült vagy nem ért véget.")
    return ok


def _logo_script(d: dict) -> dict:
    """A logó a videókkal közös listába kerül, ezért ugyanazokat a mezőket kapja."""
    return {"title": d["title"], "tagline": "", "brand": "", "theme": "", "scenes": [],
            "post": "", "first_comment": "", "ideas": [v["idea"] for v in d["variants"]],
            "logo_variants": d["variants"]}


def revise(vid: str, feedback: str, say=lambda m: None) -> dict:
    meta = get_meta(vid)
    if not meta:
        raise VideoError("nincs ilyen videó")
    feedback = (feedback or "").strip()[:2000]
    if len(feedback) < 3:
        raise VideoError("írd le, mit változtassak")
    opts = meta.get("opts") or {"brief": meta.get("brief", ""), "seconds": 30, "lang": "hu", "aspect": "9:16",
                                "voice": False, "male": False, "research": False}
    # A módosítás nem vált formátumot: amit videónak kértél, videó marad.
    form = opts.get("form") or meta.get("form") or "video"
    opts = {**opts, "form": form}
    ctx = {"urls": meta.get("ctx_urls") or [], "pages": [], "web": []}
    if form == "logo":
        previous = []
        for n in range(1, len(meta.get("vectors") or []) + 1):
            p = vector_path(vid, n)
            if p:
                with open(p, encoding="utf-8") as f:
                    previous.append(f.read())
        say("Módosítás: a logók újratervezése…")
        d = design_logos(opts["brief"], ctx, opts["lang"], say, feedback, previous)
        return _finish(_logo_script(d), opts, ctx, say, parent=vid)
    say("Módosítás: a forgatókönyv átírása…")
    raw = llm._ask(revise_prompt(meta, feedback, opts["lang"], form))
    script = normalize(llm.extract_json(raw), opts["seconds"], len(ctx["urls"]), form)
    script = check(script, opts["brief"] + " " + feedback, ctx, opts["seconds"], opts["lang"], say, form)
    script = fill_images(script, opts["aspect"], say)
    return _finish(script, opts, ctx, say, parent=vid)
