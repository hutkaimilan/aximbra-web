"""A videós agent: forgatókönyvtől a kész MP4-ig, ember és kamera nélkül.

1. Forgatókönyv: a modell jelenetekre bontja a témát (horog, probléma,
   az aximbra.hu élő képe egy telefonon, egy telefonos AI-hívás, az agentek,
   felhívás), és megírja mellé a LinkedIn-posztot.
2. Felvétel: fej nélküli Chromium lefotózza az aximbra.hu-t mobilnézetben.
3. Renderelés: a jelenetek egy HTML-sablonban futnak; a program minden
   képkockánál pontosan beállítja az animációk idejét és képet készít, az
   ffmpeg pedig 1080×1920-as, 30 fps-os H.264 videót fűz belőlük.

Hang nincs benne szándékosan: a LinkedIn-videók többségét némítva nézik, és
a szöveg minden jeleneten a képen van. Zene sincs: a jogdíjas zene bajt csinál.
"""
from __future__ import annotations

import base64
import json
import logging
import os
import re
import secrets
import subprocess
import time
from datetime import datetime, timezone

import llm
import playbook

logger = logging.getLogger(__name__)

HERE = os.path.dirname(os.path.abspath(__file__))
TEMPLATE = os.path.join(HERE, "static", "video_template.html")
VIDEO_DIR = os.environ.get("VIDEO_DIR", "/data/videos")
FPS = int(os.environ.get("VIDEO_FPS", "30"))
KEEP = 12
KINDS = ("hook", "problem", "benefit", "site", "call", "agents", "cta")
MIN_TOTAL, MAX_TOTAL = 15, 60

TOPICS = {
    "altalanos": "AXIMBRA in general: custom AI agents built into a company's own systems, with live demos on aximbra.hu",
    "telefon": "the telephone AI: answers calls and calls back within 10 seconds, records the caller's request for staff",
    "email": "the email triage agent: sorts, prioritises and routes a shared inbox so staff only has to answer",
    "erdeklodo": "the lead qualifier: ranks incoming enquiries as urgent, serious or just comparing prices",
    "dokumentum": "the document analyser: reads contracts, invoices and delivery notes and extracts the fields staff re-type today",
    "nis2": "the NIS2 compliance agent: continuously collects the evidence an audit asks for (it does NOT protect against attacks)",
    "ertekesito": "the sales agent: finds fitting companies, writes each a short letter built on one real observation, follows up, sorts replies",
}


class VideoError(RuntimeError):
    pass


# ---- forgatókönyv ----------------------------------------------------------

def script_prompt(topic: str, seconds: int, lang: str, extra: str) -> str:
    language = "Hungarian" if lang == "hu" else "English"
    return f"""You are a senior B2B video marketer writing a vertical 9:16 social video (LinkedIn, Instagram Reels, TikTok) for AXIMBRA.
No person appears and there is no voice-over: every message must be readable ON SCREEN. Muted viewing is the default.

AXIMBRA facts (the only facts you may use):
{playbook.AXIMBRA_FACTS}

Topic: {topic}
{('Extra instruction from the founder: ' + extra) if extra else ''}
Total length: about {seconds} seconds. Language of ALL on-screen text and the post: {language}.

Structure it as hook → problem → proof (the live site / a call) → benefit → call to action. Pick 4–7 scenes from these kinds:
- "hook": a punchy first line that stops the scroll in 2 seconds (a sharp question or a bold claim that is TRUE). 2–3 seconds.
- "problem": headline + 2–3 "lines" (each max 6 words), the everyday pain. 4–5 s.
- "site": headline + short "sub"; the video shows aximbra.hu scrolling on a phone. 5–7 s.
- "call": the phone AI answering a call; "lines" = 3–4 very short alternating turns, AI first (max 9 words each), realistic, no invented customer names. 6–8 s.
- "benefit": headline + 2–3 "lines" (max 6 words each), what changes. 4–5 s.
- "agents": headline + 4–6 "lines" = agent names from the list. 4–5 s.
- "cta": headline + "sub" + "button" (e.g. "Élő demó · regisztráció nélkül"); url is aximbra.hu. 4–5 s. Always last.

Rules:
- headline max 7 words; mark 1–2 key words with *asterisks* for highlight. sub max 14 words. kicker (optional) max 3 words, uppercase feel.
- NEVER invent statistics, percentages, time savings, customers, testimonials or results. No prices.
- Hungarian text: natural, formal-neutral (no "tegezés" in the video), no anglicisms where a Hungarian word exists.
- Also write the LinkedIn post to go with the video (60–120 words, hook first line, no hashtag spam: max 3) and a first comment that holds the link.

Answer ONLY with JSON:
{{"title": "short internal title", "tagline": "max 3 words for the corner, e.g. AI AGENTEK",
"scenes": [{{"kind": "hook|problem|site|call|benefit|agents|cta", "kicker": "", "headline": "", "sub": "", "lines": [], "button": "", "seconds": 0}}],
"post": "the LinkedIn post", "first_comment": "e.g. Élő demók: https://aximbra.hu"}}"""


def _clip(s, n: int) -> str:
    s = re.sub(r"\s+", " ", str(s or "")).strip()
    return s if len(s) <= n else s[: n - 1].rstrip() + "…"


def normalize(data: dict, seconds: int) -> dict:
    """A modell kimenetéből érvényes, renderelhető forgatókönyv."""
    if not isinstance(data, dict):
        raise VideoError("a forgatókönyv nem JSON objektum")
    scenes = []
    for s in data.get("scenes") or []:
        if not isinstance(s, dict) or s.get("kind") not in KINDS:
            continue
        try:
            sec = float(s.get("seconds") or 4)
        except (TypeError, ValueError):
            sec = 4.0
        scenes.append({
            "kind": s["kind"],
            "kicker": _clip(s.get("kicker"), 28),
            "headline": _clip(s.get("headline"), 70),
            "sub": _clip(s.get("sub"), 120),
            "lines": [_clip(l, 60) for l in (s.get("lines") or []) if str(l).strip()][:6],
            "button": _clip(s.get("button"), 40),
            "seconds": max(2.0, min(9.0, sec)),
        })
    scenes = [s for s in scenes if s["headline"] or s["kind"] in ("site", "call")][:8]
    if len(scenes) < 2:
        raise VideoError("a forgatókönyvben túl kevés használható jelenet van")
    ctas = [s for s in scenes if s["kind"] == "cta"]
    scenes = [s for s in scenes if s["kind"] != "cta"] + (ctas[-1:] or [{
        "kind": "cta", "kicker": "", "headline": "Próbálja ki *élőben*", "sub": "", "lines": [],
        "button": "Élő demó · regisztráció nélkül", "seconds": 4.0}])
    # A teljes hosszt arányosan a kért értékhez igazítjuk, a korlátokon belül.
    total = sum(s["seconds"] for s in scenes)
    target = max(MIN_TOTAL, min(MAX_TOTAL, seconds))
    k = target / total if total else 1
    for s in scenes:
        s["seconds"] = round(max(2.0, min(10.0, s["seconds"] * k)), 2)
    return {
        "title": _clip(data.get("title") or "AXIMBRA videó", 80),
        "tagline": _clip(data.get("tagline") or "AI AGENTEK", 24).upper(),
        "scenes": scenes,
        "post": str(data.get("post") or "").strip()[:3000],
        "first_comment": str(data.get("first_comment") or "Élő demók: https://aximbra.hu").strip()[:500],
    }


def write_script(topic_key: str, seconds: int, lang: str, extra: str) -> dict:
    topic = TOPICS.get(topic_key, TOPICS["altalanos"])
    raw = llm._ask(script_prompt(topic, seconds, lang, extra.strip()[:600]))
    return normalize(llm.extract_json(raw), seconds)


# ---- renderelés -------------------------------------------------------------

def _ffmpeg() -> str:
    exe = os.environ.get("FFMPEG_PATH")
    if exe:
        return exe
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()


def _launch(pw):
    path = os.environ.get("CHROMIUM_PATH") or None
    return pw.chromium.launch(executable_path=path, args=["--no-sandbox", "--disable-dev-shm-usage"])


def capture_site(browser, url: str = "https://aximbra.hu") -> dict | None:
    """Az oldal mobilnézetben, a tetejétől legfeljebb 3200 px-ig."""
    page = browser.new_page(viewport={"width": 390, "height": 844}, device_scale_factor=2)
    try:
        page.goto(url, wait_until="networkidle", timeout=45000)
        page.wait_for_timeout(2500)
        height = min(3200, page.evaluate("document.documentElement.scrollHeight"))
        png = page.screenshot(clip={"x": 0, "y": 0, "width": 390, "height": height}, full_page=True)
        # A telefon képernyője 276 px széles: arányosan ekkora a kép magassága.
        return {"src": "data:image/png;base64," + base64.b64encode(png).decode(), "height": round(height * 276 / 390)}
    except Exception as e:  # noqa: BLE001 — az oldal nélkül is elkészülhet a videó
        logger.warning("aximbra.hu képernyőkép hiba: %s", e)
        return None
    finally:
        page.close()


def render(script: dict, out_path: str, say=lambda m: None) -> float:
    from playwright.sync_api import sync_playwright

    tmp = out_path + ".part.mp4"
    with sync_playwright() as pw:
        browser = _launch(pw)
        try:
            shot = capture_site(browser) if any(s["kind"] == "site" for s in script["scenes"]) else None
            if shot is None:
                script = {**script, "scenes": [s for s in script["scenes"] if s["kind"] != "site"] or script["scenes"]}
            page = browser.new_page(viewport={"width": 540, "height": 960}, device_scale_factor=2)
            page.goto("file://" + TEMPLATE, wait_until="networkidle", timeout=45000)
            total = page.evaluate("(cfg) => build(cfg)", {**script, "shot": shot})
            page.evaluate("document.fonts.ready.then(() => true)")
            page.wait_for_timeout(400)
            frames = int(total * FPS)
            say(f"Renderelés: {frames} képkocka ({total:.0f} mp)…")
            cmd = [_ffmpeg(), "-hide_banner", "-loglevel", "error", "-y", "-f", "image2pipe", "-framerate", str(FPS),
                   "-c:v", "mjpeg", "-i", "-", "-c:v", "libx264", "-preset", "medium", "-crf", "20",
                   "-pix_fmt", "yuv420p", "-vf", "scale=1080:1920:flags=lanczos", "-movflags", "+faststart", tmp]
            proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
            try:
                step = max(1, frames // 5)
                for f in range(frames):
                    page.evaluate("(ms) => seek(ms)", f * 1000 / FPS)
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


def list_videos() -> list[dict]:
    if not os.path.isdir(VIDEO_DIR):
        return []
    out = []
    for name in os.listdir(VIDEO_DIR):
        if name.endswith(".json"):
            try:
                with open(os.path.join(VIDEO_DIR, name), encoding="utf-8") as f:
                    m = json.load(f)
            except (OSError, ValueError):
                continue
            if video_path(m.get("id", "")):
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


def make(topic: str, seconds: int, lang: str, extra: str, say=lambda m: None) -> dict:
    os.makedirs(VIDEO_DIR, exist_ok=True)
    say("Forgatókönyv írása…")
    script = write_script(topic, seconds, lang, extra)
    say(f"Forgatókönyv kész: {script['title']} ({len(script['scenes'])} jelenet).")
    vid = secrets.token_hex(6)
    started = time.time()
    total = render(script, os.path.join(VIDEO_DIR, f"{vid}.mp4"), say)
    meta = {"id": vid, "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "topic": topic, "lang": lang, "seconds": round(total, 1), **script}
    with open(_meta_path(vid), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False)
    _prune()
    say(f"Kész: {script['title']} — {total:.0f} mp, {time.time() - started:.0f} mp alatt renderelve.")
    return meta
