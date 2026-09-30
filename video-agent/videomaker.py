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
import media
import playbook
import websearch

logger = logging.getLogger(__name__)

HERE = os.path.dirname(os.path.abspath(__file__))
TEMPLATE = os.path.join(HERE, "static", "video_template.html")
VIDEO_DIR = os.environ.get("VIDEO_DIR", "/data/videos")
FPS = int(os.environ.get("VIDEO_FPS", "30"))
KEEP = 20
KINDS = ("hook", "statement", "problem", "benefit", "steps", "compare", "site", "call", "inbox",
         "agents", "number", "quote", "photo", "gallery", "clip", "cta")
VISUAL_KINDS = ("site", "call", "inbox", "photo", "gallery", "clip")
MEDIA_KINDS = ("photo", "gallery", "clip")
THEMES = ("neon", "clean", "warm", "mono")
ASPECTS = {"9:16": (540, 960), "1:1": (540, 540), "16:9": (960, 540)}
MIN_TOTAL, MAX_TOTAL = 10, 90
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

def gather(brief: str, research: bool, say=lambda m: None) -> dict:
    """A leírás linkjei (szöveg + a videóba kerülő URL-ek) és opcionális webes háttér."""
    urls = websearch.urls_in(brief)
    if not urls and re.search(r"aximbr", brief, re.I):
        urls = ["https://aximbra.hu"]
    pages = []
    for u in urls[:4]:
        p = websearch.read_page(u)
        pages.append({"url": u, "text": (p or {}).get("text", "")[:2500]})
    web = []
    if research:
        say("Webes háttérkutatás…")
        web = websearch.search(brief[:280], n=4)
    return {"urls": urls[:4], "pages": pages, "web": web, "library": media.listing()}


# ---- forgatókönyv -----------------------------------------------------------

def _lang_name(lang: str) -> str:
    return "Hungarian" if lang == "hu" else "English"


def director_prompt(brief: str, ctx: dict, seconds: int, lang: str, aspect: str, voice: bool) -> str:
    sites = "\n".join(f"  [{i}] {u}" for i, u in enumerate(ctx["urls"])) or "  (none — do not use the 'site' scene)"
    lib = ctx.get("library") or []
    shelf = "\n".join(f"  {m['id']}  {m['kind']}  {m['name']}" + (f" — {m['note']}" if m.get("note") else "")
                      for m in lib) or "  (empty — you may still ask for generated images)"
    pages = "\n\n".join(f"TEXT OF {p['url']}:\n{p['text']}" for p in ctx["pages"] if p["text"]) or "(none)"
    web = "\n\n".join(f"WEB: {w['title']} — {w['url']}\n{w['text']}" for w in ctx["web"]) or "(none)"
    return f"""You are an award-winning creative director making a short social video from a brief. No person appears on camera.
Everything is motion graphics, a real website shown on a phone, or animated UI.

THE BRIEF (this is what the client wants — follow it closely; it overrides the defaults below):
\"\"\"{brief}\"\"\"

Company facts (AXIMBRA, use when the brief is about AXIMBRA):
{playbook.AXIMBRA_FACTS}

Websites captured for the video (use their index in "shot"):
{sites}

The user's media library (put an id in "media"; clips are silent and at most 20 s):
{shelf}

Source text you may draw facts from:
{pages}

{web}

Format: {aspect} ({'vertical' if aspect == '9:16' else 'square' if aspect == '1:1' else 'landscape'}), about {seconds} seconds.
On-screen language and narration: {_lang_name(lang)}.
{'Write a spoken narration line ("voice") for every scene: natural, conversational, max ~2.3 words per second of the scene.' if voice else 'No narration: every message must be readable on screen (muted viewing). Leave "voice" empty.'}

Scene kinds (choose freely, 4–9 scenes, in the order that tells the story best):
- "hook": scroll-stopping first line, 2–3 s. Must be TRUE.
- "statement": one bold sentence (headline) + optional sub. "center": true to center it.
- "problem" / "benefit": headline + 2–4 "lines" (max 6 words each).
- "steps": headline + 2–4 "lines" = numbered process steps.
- "compare": headline + "left_title" + "lines" (before) + "right_title" + "lines2" (after), 2–3 items each.
- "site": headline + sub, shows captured website "shot" (index) scrolling on a phone. Only if a site is listed above.
- "call": a phone call answered by an AI; "lines" = 3–4 short alternating turns, AI first, no speaker labels; optional "caller", "status".
- "inbox": an inbox being sorted; "app" = inbox title; "lines" = 3–5 items formatted "subject|category tag".
- "agents": headline + 3–6 "lines" (names), optional "tile_label".
- "photo": one image with the text. Set "media" to a library id, OR set "image_prompt" to have one generated
  (describe the picture in English: subject, setting, light, mood). "layout": "full" (text over the image) or
  "side" (image beside the text). Never ask for a recognisable real person.
- "gallery": headline + "medias" = 2–4 library ids shown in a grid.
- "clip": an uploaded video clip playing behind the text. "media" must be a library id of kind "clip", and
  "seconds" must stay within that clip's length. The clip is silent; the narration carries the sound.
- "number": headline = a number FROM THE BRIEF OR SOURCES ONLY, sub = what it means.
- "quote": headline = a quote FROM THE BRIEF OR SOURCES ONLY, sub = its source.
- "cta": headline + "url" + sub + "button". Always last.
Fields: headline max 8 words, mark 1–2 key words with *asterisks*; sub max 16 words; kicker optional, max 3 words.
Use the user's own uploaded media wherever it fits the brief — that is why they uploaded it. Ask for a generated
image only where nothing uploaded fits.

Pick a visual theme that fits the brief: "neon" (futuristic, default), "clean" (light, corporate), "warm" (energetic), "mono" (minimal).

HARD RULES:
- Never invent statistics, percentages, time or money savings, customers, testimonials, awards or results.
  Numbers and quotes may appear only if they are in the brief or the source text above.
- No prices unless the brief asks for them (then only from the facts list).
- Hungarian: formal-neutral, natural, no anglicisms where a Hungarian word exists.
- Also write a social post for the video (60–120 words, strong first line, max 3 hashtags) and a first comment holding the link.

Answer ONLY with JSON:
{{"title": "", "tagline": "max 3 words", "brand": "AXIMBRA or the brand in the brief", "theme": "neon|clean|warm|mono",
"scenes": [{{"kind": "", "kicker": "", "headline": "", "sub": "", "lines": [], "lines2": [], "left_title": "", "right_title": "",
  "shot": 0, "media": "", "medias": [], "image_prompt": "", "layout": "full", "app": "", "caller": "", "status": "",
  "tile_label": "", "center": false, "url": "", "button": "", "voice": "", "seconds": 0}}],
"post": "", "first_comment": ""}}"""


def revise_prompt(script: dict, feedback: str, lang: str) -> str:
    slim = {k: script[k] for k in ("title", "tagline", "brand", "theme", "scenes", "post", "first_comment") if k in script}
    return f"""You are revising a short video script. Apply the client's feedback precisely; keep everything else as it is.
Same JSON structure, same scene kinds available (hook, statement, problem, benefit, steps, compare, site, call,
inbox, agents, number, quote, photo, gallery, clip, cta). Keep the "media" ids that are still wanted.
Language: {_lang_name(lang)}. Never invent statistics, customers, testimonials or results.

FEEDBACK: \"\"\"{feedback}\"\"\"

CURRENT SCRIPT:
{json.dumps(slim, ensure_ascii=False)}

Answer ONLY with the full revised JSON."""


def _clip(s, n: int) -> str:
    s = re.sub(r"\s+", " ", str(s or "")).strip()
    return s if len(s) <= n else s[: n - 1].rstrip() + "…"


_LABEL_RE = re.compile(r"^\s*(AI|Ügyfél|Hívó|Caller|Customer|Agent|Ügyintéző)\s*:\s*", re.I)


def _media_id(v) -> str:
    v = str(v or "").strip()
    return v if re.fullmatch(r"[a-z0-9]{12}", v) else ""


def normalize(data: dict, seconds: int, n_shots: int = 1) -> dict:
    """A modell kimenetéből érvényes, renderelhető forgatókönyv."""
    if not isinstance(data, dict):
        raise VideoError("a forgatókönyv nem JSON objektum")
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
        lines = lambda key, n: [_clip(_LABEL_RE.sub("", str(l)), 70) for l in (s.get(key) or []) if str(l).strip()][:n]
        scenes.append({
            "kind": s["kind"], "kicker": _clip(s.get("kicker"), 28), "headline": _clip(s.get("headline"), 80),
            "sub": _clip(s.get("sub"), 140), "lines": lines("lines", 6), "lines2": lines("lines2", 4),
            "left_title": _clip(s.get("left_title"), 20), "right_title": _clip(s.get("right_title"), 20),
            "media": _media_id(s.get("media")),
            "medias": [m for m in (_media_id(x) for x in (s.get("medias") or [])) if m][:4],
            "image_prompt": _clip(s.get("image_prompt"), 400),
            "layout": "side" if str(s.get("layout") or "").strip() == "side" else "full",
            "shot": shot, "app": _clip(s.get("app"), 30), "caller": _clip(s.get("caller"), 24), "status": _clip(s.get("status"), 24),
            "tile_label": _clip(s.get("tile_label"), 12), "center": bool(s.get("center")),
            "url": _clip(s.get("url") or "", 40), "button": _clip(s.get("button"), 40), "voice": _clip(s.get("voice"), 260),
            "seconds": max(2.0, min(12.0, sec)),
        })
    # Médiajelenet üres kézzel nem állja meg a helyét: szöveges lesz belőle.
    for s in scenes:
        if s["kind"] == "gallery" and not s["medias"]:
            s["kind"] = "statement"
        elif s["kind"] in ("photo", "clip") and not s["media"] and not s["image_prompt"]:
            s["kind"] = "statement"
    scenes = [s for s in scenes if s["headline"] or s["kind"] in VISUAL_KINDS][:10]
    if len(scenes) < 2:
        raise VideoError("a forgatókönyvben túl kevés használható jelenet van")
    # A klip nem lehet hosszabb, mint a felvett anyag.
    for s in scenes:
        if s["kind"] == "clip":
            m = media.get(s["media"]) or {}
            if m.get("kind") != "clip":
                s["kind"] = "photo" if m.get("kind") == "image" else "statement"
            elif m.get("seconds"):
                s["seconds"] = min(s["seconds"], float(m["seconds"]))
    ctas = [s for s in scenes if s["kind"] == "cta"]
    scenes = [s for s in scenes if s["kind"] != "cta"] + (ctas[-1:] or [{
        **scenes[-1], "kind": "cta", "headline": "Próbálja ki *élőben*", "sub": "", "lines": [], "url": "aximbra.hu",
        "button": "Élő demó · regisztráció nélkül", "voice": "", "seconds": 4.0}])
    for s in scenes:
        if s["kind"] == "cta" and not s["url"]:
            s["url"] = "aximbra.hu"
    total = sum(s["seconds"] for s in scenes)
    target = max(MIN_TOTAL, min(MAX_TOTAL, seconds))
    k = target / total if total else 1
    for s in scenes:
        s["seconds"] = round(max(2.0, min(14.0, s["seconds"] * k)), 2)
    theme = data.get("theme") if data.get("theme") in THEMES else "neon"
    return {
        "title": _clip(data.get("title") or "Videó", 80), "tagline": _clip(data.get("tagline") or "", 24).upper(),
        "brand": _clip(data.get("brand") or "AXIMBRA", 20), "theme": theme, "scenes": scenes,
        "post": str(data.get("post") or "").strip()[:3000],
        "first_comment": str(data.get("first_comment") or "Élő demók: https://aximbra.hu").strip()[:500],
    }


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
    return list(dict.fromkeys(out))


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


def write_script(brief: str, ctx: dict, seconds: int, lang: str, aspect: str, voice: bool, say=lambda m: None) -> dict:
    raw = llm._ask(director_prompt(brief, ctx, seconds, lang, aspect, voice))
    script = normalize(llm.extract_json(raw), seconds, len(ctx["urls"]))
    return check(script, brief, ctx, seconds, lang, say)


def check(script: dict, brief: str, ctx: dict, seconds: int, lang: str, say=lambda m: None) -> dict:
    sources = brief + " " + " ".join(p["text"] for p in ctx["pages"]) + " " + " ".join(w["text"] for w in ctx["web"])
    v = violations(script, sources)
    if v:
        say(f"Ellenőrzés: {len(v)} alátámasztatlan állítás, javítom…")
        fb = "Remove or rewrite these unsupported claims (numbers, guarantees, customers not in the brief):\n" + "\n".join(v)
        try:
            script = normalize(llm.extract_json(llm._ask(revise_prompt(script, fb, lang))), seconds, len(ctx["urls"]))
        except (llm.LLMError, VideoError) as e:
            logger.warning("javító kör hiba: %s", e)
        script = _strip_claims(script, sources)
        if len(script["scenes"]) < 2:
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
            time.sleep(min(60, 20 * (attempt + 1)))
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


def _tts_elevenlabs(text: str, lang: str, male: bool) -> bytes | None:
    """ElevenLabs, ha van kulcs és hang. A modell a magyart is ismeri."""
    key = os.environ.get("ELEVENLABS_API_KEY", "").strip()
    voice = (os.environ.get("ELEVENLABS_VOICE_ID_MALE") if male else None) or os.environ.get("ELEVENLABS_VOICE_ID", "")
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
    Visszaadja a teljes hangsávot (WAV) és a használt motor nevét."""
    engine, clips = "", []
    for s in script["scenes"]:
        if not s["voice"]:
            clips.append(b"")
            continue
        wav = None
        if engine in ("", "elevenlabs"):
            wav = _tts_elevenlabs(s["voice"], lang, male)
            if wav:
                engine = "elevenlabs"
        if not wav and engine in ("", "gemini"):
            wav = _tts_gemini(s["voice"], lang)
            if wav:
                engine = "gemini"
        if not wav and engine in ("", "edge"):
            wav = _tts_edge(s["voice"], lang, male)
            if wav:
                engine = "edge"
        if not wav:
            say("Hang: egyik felolvasó sem érhető el, néma videó készül felirattal.")
            return None, ""
        clips.append(_wav_pcm(wav))
    if not any(clips):
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
    """Az oldal mobilnézetben, a tetejétől legfeljebb 3200 px-ig, végiggörgetve."""
    page = browser.new_page(viewport={"width": 390, "height": 844}, device_scale_factor=2,
                            ignore_https_errors=bool(os.environ.get("CHROMIUM_PROXY")))
    try:
        page.goto(url, wait_until="networkidle", timeout=45000)
        page.wait_for_timeout(2500)
        height = min(3200, page.evaluate("document.documentElement.scrollHeight"))
        # Az oldal lejjebb lévő részei csak görgetéskor úsznak be; görgetés
        # nélkül a képen feketék maradnak. Ezért előbb végiggörgetjük.
        for y in range(0, height + 844, 350):
            page.evaluate(f"window.scrollTo(0, {y})")
            page.wait_for_timeout(220)
        page.evaluate("window.scrollTo(0, 0)")
        page.wait_for_timeout(1500)
        png = page.screenshot(clip={"x": 0, "y": 0, "width": 390, "height": height}, full_page=True)
        return {"src": "data:image/png;base64," + base64.b64encode(png).decode(), "height": round(height * phone_w / 390)}
    except Exception as e:  # noqa: BLE001 — az oldal nélkül is elkészülhet a videó
        logger.warning("képernyőkép hiba (%s): %s", url, e)
        return None
    finally:
        page.close()


PHONE_SCREEN_W = {"9:16": 258, "1:1": 184, "16:9": 198}


def render(script: dict, urls: list[str], out_path: str, aspect: str, audio: bytes | None,
           captions: bool, say=lambda m: None) -> float:
    from playwright.sync_api import sync_playwright

    w, h = ASPECTS[aspect]
    tmp = out_path + ".part.mp4"
    with tempfile.TemporaryDirectory() as work, sync_playwright() as pw:
        # A sablon és a médiafájlok egy ideiglenes mappába kerülnek, így a
        # lap saját fájlként éri el őket, adat-URL nélkül is.
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
                    shots[i] = capture_site(browser, urls[i], PHONE_SCREEN_W[aspect])
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
                                                          "shots": shots, "captions": captions, "lib": lib})
            page.evaluate("document.fonts.ready.then(() => true)")
            page.wait_for_timeout(400)
            # A klipek első képkockája legyen meg, mielőtt léptetni kezdjük.
            page.evaluate("""() => Promise.all([...document.querySelectorAll('video')].map((v) =>
                v.readyState >= 2 ? null : new Promise((r) => {
                  v.addEventListener('loadeddata', r, {once: true}); setTimeout(r, 4000); })))""")
            frames = int(total * FPS)
            say(f"Renderelés: {frames} képkocka ({total:.0f} mp, {aspect})…")
            if True:
                d = work
                inputs = ["-f", "image2pipe", "-framerate", str(FPS), "-c:v", "mjpeg", "-i", "-"]
                maps = []
                if audio:
                    apath = os.path.join(d, "a.wav")
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
                    raise
        finally:
            browser.close()
    os.replace(tmp, out_path)
    return total


# ---- tárolás ----------------------------------------------------------------

def _meta_path(vid: str) -> str:
    return os.path.join(VIDEO_DIR, f"{vid}.json")


def video_path(vid: str) -> str | None:
    if not re.fullmatch(r"[a-z0-9]{12}", vid or ""):
        return None
    p = os.path.join(VIDEO_DIR, f"{vid}.mp4")
    return p if os.path.exists(p) else None


def get_meta(vid: str) -> dict | None:
    if not video_path(vid):
        return None
    try:
        with open(_meta_path(vid), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


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


def delete(vid: str) -> bool:
    p = video_path(vid)
    if not p:
        return False
    for path in (p, _meta_path(vid)):
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
    audio, engine = (None, "")
    if opts["voice"]:
        say("Hangalámondás…")
        audio, engine = narrate(script, opts["lang"], opts.get("male", False), say)
        if engine:
            say(f"Hang kész ({ {'elevenlabs': 'ElevenLabs', 'gemini': 'Gemini'}.get(engine, 'Edge')} felolvasó).")
    vid = secrets.token_hex(6)
    started = time.time()
    total = render(script, ctx["urls"], os.path.join(VIDEO_DIR, f"{vid}.mp4"), opts["aspect"], audio,
                   captions=bool(audio), say=say)
    meta = {"id": vid, "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "parent": parent,
            "brief": opts["brief"], "opts": opts, "ctx_urls": ctx["urls"], "voice_engine": engine,
            "seconds": round(total, 1), **script}
    with open(_meta_path(vid), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False)
    _prune()
    say(f"Kész: {script['title']} — {total:.0f} mp, {time.time() - started:.0f} mp alatt renderelve.")
    return meta


def make(brief: str, seconds: int = 30, lang: str = "hu", aspect: str = "9:16", voice: bool = True,
         male: bool = False, research: bool = False, say=lambda m: None) -> dict:
    brief = (brief or "").strip()[:4000]
    if len(brief) < 8:
        raise VideoError("írd le, miről szóljon a videó")
    if aspect not in ASPECTS:
        raise VideoError("ismeretlen képarány")
    opts = {"brief": brief, "seconds": seconds, "lang": lang, "aspect": aspect, "voice": voice,
            "male": male, "research": research}
    say("Kontextus: linkek beolvasása…")
    ctx = gather(brief, research, say)
    say("Forgatókönyv írása…")
    script = write_script(brief, ctx, seconds, lang, aspect, voice, say)
    script = fill_images(script, aspect, say)
    say(f"Forgatókönyv kész: {script['title']} ({len(script['scenes'])} jelenet, {script['theme']} stílus).")
    return _finish(script, opts, ctx, say)


def revise(vid: str, feedback: str, say=lambda m: None) -> dict:
    meta = get_meta(vid)
    if not meta:
        raise VideoError("nincs ilyen videó")
    feedback = (feedback or "").strip()[:2000]
    if len(feedback) < 3:
        raise VideoError("írd le, mit változtassak")
    opts = meta.get("opts") or {"brief": meta.get("brief", ""), "seconds": 30, "lang": "hu", "aspect": "9:16",
                                "voice": False, "male": False, "research": False}
    ctx = {"urls": meta.get("ctx_urls") or [], "pages": [], "web": []}
    say("Módosítás: a forgatókönyv átírása…")
    raw = llm._ask(revise_prompt(meta, feedback, opts["lang"]))
    script = normalize(llm.extract_json(raw), opts["seconds"], len(ctx["urls"]))
    script = check(script, opts["brief"] + " " + feedback, ctx, opts["seconds"], opts["lang"], say)
    script = fill_images(script, opts["aspect"], say)
    return _finish(script, opts, ctx, say, parent=vid)
