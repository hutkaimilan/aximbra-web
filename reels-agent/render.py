"""A renderelő: a jelenettervből kész MP4, csak ffmpeg-gel.

Miért nem fej nélküli böngészővel (mint a régi agent): egy gyors montázshoz
képkockánként léptetett Chromium a legdrágább út — sok memória, lassú build,
és bármelyik képkockán el tud hasalni. Itt minden jelenet egy rövid ffmpeg-
futás, azonos formátumban, és a végén a `concat` másolással fűzi össze őket.
Ez gyors, kevés memória, és egy hibás elem csak egy jelenetet visz el.

Hang nincs benne: zenét licenc miatt nem tehetünk rá, a klipek saját hangja
pedig egy vágott montázsban csak kapkodás. A TikTokon úgyis a saját hangot
teszed alá.
"""
from __future__ import annotations

import json
import logging
import os
import re
import secrets
import shutil
import subprocess
import tempfile
from datetime import datetime, timezone

import director
import library

logger = logging.getLogger("reels.render")

VIDEO_DIR = os.environ.get("VIDEO_DIR", "/data/videos")
FPS = 30
CRF = "21"
PRESET = "veryfast"
FONT_CANDIDATES = (
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
)
# Álló videón a telefon felülete levágja a széleket: a szöveg ezeken belül marad.
SAFE = {"left": 64, "right": 100, "top": 100, "bottom_quarter": 0.25}
_ID_RE = re.compile(r"[a-z0-9]{10}")


class RenderError(RuntimeError):
    pass


def _ffmpeg(args: list[str], timeout: int = 900) -> subprocess.CompletedProcess:
    r = subprocess.run([library._ffmpeg(), "-hide_banner", "-loglevel", "error", "-y", *args],
                       capture_output=True, timeout=timeout)
    return r


def _must(args: list[str], what: str, timeout: int = 900) -> None:
    r = _ffmpeg(args, timeout)
    if r.returncode != 0:
        raise RenderError(f"{what}: {r.stderr.decode(errors='replace')[-300:]}")


def font_path() -> str | None:
    for p in FONT_CANDIDATES:
        if os.path.exists(p):
            return p
    return None


# ---- felirat képként ------------------------------------------------------
# A szöveget a Pillow rajzolja PNG-re, nem az ffmpeg drawtext: így biztosan jó
# az ékezet, tördelni is tudunk, és a biztonságos sávon belül maradunk.

def text_overlay(text: str, w: int, h: int, out: str) -> bool:
    """Felirat a biztonságos sávon belül. False, ha nincs mit kiírni."""
    text = (text or "").strip()
    if not text:
        return False
    from PIL import Image, ImageDraw, ImageFont
    fp = font_path()
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    left, right = SAFE["left"], w - SAFE["right"]
    box_w = right - left
    size = max(28, int(w * 0.072))
    font = ImageFont.truetype(fp, size) if fp else ImageFont.load_default()

    def wrap(fnt):
        lines, cur = [], ""
        for word in text.split():
            trial = (cur + " " + word).strip()
            if d.textlength(trial, font=fnt) <= box_w or not cur:
                cur = trial
            else:
                lines.append(cur)
                cur = word
        if cur:
            lines.append(cur)
        return lines

    lines = wrap(font)
    while len(lines) > 4 and size > 24 and fp:          # ne lógjon ki a képből
        size = int(size * 0.88)
        font = ImageFont.truetype(fp, size)
        lines = wrap(font)
    line_h = int(size * 1.22)
    block_h = line_h * len(lines)
    # A felső 100 px a logóé, az alsó negyed maradjon szabadon.
    top_limit = SAFE["top"] + 20
    bottom_limit = int(h * (1 - SAFE["bottom_quarter"]))
    y = max(top_limit, min(int(h * 0.60) - block_h // 2, bottom_limit - block_h))
    for n, line in enumerate(lines):
        tw = d.textlength(line, font=font)
        x = left + (box_w - tw) / 2
        ly = y + n * line_h
        for dx, dy in ((-3, 0), (3, 0), (0, -3), (0, 3), (-2, -2), (2, 2), (-2, 2), (2, -2)):
            d.text((x + dx, ly + dy), line, font=font, fill=(0, 0, 0, 215))
        d.text((x, ly), line, font=font, fill=(255, 255, 255, 255))
    img.save(out)
    return True


# ---- egy jelenet ----------------------------------------------------------

def _cover(w: int, h: int) -> str:
    """Kitöltés levágással: a kép/klip betölti a keretet, a széle lemegy."""
    return (f"scale={w}:{h}:force_original_aspect_ratio=increase:flags=lanczos,"
            f"crop={w}:{h},setsar=1")


def _zoom(effect: str, dur: float, w: int, h: int) -> str:
    """Mozgás egy állóképen. A zoompan a nagy felbontáson ugrál, ezért előtte
    felskálázunk, és utána visszaveszünk a kimeneti méretre."""
    frames = max(2, int(round(dur * FPS)))
    if effect == "punch_in":
        z = f"min(1.0+0.0022*on,1.14)"
        x, y = "iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)"
    elif effect == "punch_out":
        z = f"max(1.14-0.0022*on,1.0)"
        x, y = "iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)"
    elif effect == "pan_right":
        z = "1.10"
        x, y = f"(iw-iw/zoom)*on/{frames}", "ih/2-(ih/zoom/2)"
    elif effect == "pan_left":
        z = "1.10"
        x, y = f"(iw-iw/zoom)*(1-on/{frames})", "ih/2-(ih/zoom/2)"
    else:
        return ""
    return f",zoompan=z='{z}':x='{x}':y='{y}':d={frames}:s={w}x{h}:fps={FPS}"


def scene_segment(scene: dict, src: str, w: int, h: int, out: str, overlay: str | None) -> None:
    """Egy jelenet önálló MP4-ként, mindegyik ugyanabban a formátumban —
    így a végén másolással fűzhetők össze."""
    dur = float(scene["seconds"])
    if scene["kind"] == "clip":
        ins = ["-ss", f"{float(scene.get('start') or 0):.3f}", "-t", f"{dur:.3f}", "-i", src]
        vf = _cover(w, h) + f",fps={FPS}"
    else:
        # A zoompan bemenete legyen nagyobb a kimenetnél, különben lépcsőzik.
        ins = ["-loop", "1", "-framerate", str(FPS), "-t", f"{dur:.3f}", "-i", src]
        vf = (f"scale={w * 2}:{h * 2}:force_original_aspect_ratio=increase:flags=lanczos,"
              f"crop={w * 2}:{h * 2},setsar=1" + _zoom(scene.get("effect") or "none", dur, w, h))
        if not _zoom(scene.get("effect") or "none", dur, w, h):
            vf = _cover(w, h) + f",fps={FPS}"
    args = [*ins]
    if overlay:
        args += ["-i", overlay,
                 "-filter_complex", f"[0:v]{vf},format=yuv420p[v];[v][1:v]overlay=0:0[o]",
                 "-map", "[o]"]
    else:
        args += ["-vf", vf + ",format=yuv420p"]
    args += ["-an", "-t", f"{dur:.3f}", "-r", str(FPS), "-c:v", "libx264", "-preset", PRESET,
             "-crf", CRF, "-pix_fmt", "yuv420p", "-video_track_timescale", "90000", out]
    _must(args, f"jelenet ({scene.get('name') or scene['id']})", timeout=600)


def flash_segment(w: int, h: int, seconds: float, out: str) -> None:
    _must(["-f", "lavfi", "-i", f"color=c=white:s={w}x{h}:r={FPS}:d={seconds:.3f}",
           "-vf", "format=yuv420p", "-an", "-c:v", "libx264", "-preset", PRESET, "-crf", CRF,
           "-video_track_timescale", "90000", out], "villanás", timeout=120)


def _trim(src: str, out: str, start: float = 0.0, dur: float | None = None) -> None:
    args = ["-ss", f"{start:.3f}", "-i", src]
    if dur is not None:
        args += ["-t", f"{dur:.3f}"]
    args += ["-an", "-r", str(FPS), "-c:v", "libx264", "-preset", PRESET, "-crf", CRF,
             "-pix_fmt", "yuv420p", "-video_track_timescale", "90000", out]
    _must(args, "vágás", timeout=300)


def _crossfade(a: str, b: str, seconds: float, out: str) -> None:
    """Áttűnés: A vége és B eleje egymásba. Külön darabként készül, hogy a
    többi jelenet maradhasson másolással összefűzve."""
    _must(["-i", a, "-i", b, "-filter_complex",
           f"[0:v][1:v]xfade=transition=fade:duration={seconds:.3f}:offset=0,format=yuv420p[o]",
           "-map", "[o]", "-an", "-t", f"{seconds:.3f}", "-r", str(FPS), "-c:v", "libx264",
           "-preset", PRESET, "-crf", CRF, "-video_track_timescale", "90000", out],
          "áttűnés", timeout=300)


# ---- a teljes videó -------------------------------------------------------

def _new_id() -> str:
    return secrets.token_hex(5)


def meta_path(vid: str) -> str:
    return os.path.join(VIDEO_DIR, f"{vid}.json")


def get(vid: str) -> dict | None:
    if not _ID_RE.fullmatch(vid or ""):
        return None
    try:
        with open(meta_path(vid), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def video_path(vid: str) -> str | None:
    m = get(vid)
    if not m:
        return None
    p = os.path.join(VIDEO_DIR, f"{vid}.mp4")
    return p if os.path.exists(p) else None


def listing() -> list[dict]:
    if not os.path.isdir(VIDEO_DIR):
        return []
    out = []
    for name in os.listdir(VIDEO_DIR):
        if name.endswith(".json"):
            m = get(name[:-5])
            if m:
                out.append(m)
    return sorted(out, key=lambda m: m.get("created_at", ""), reverse=True)


def delete(vid: str) -> bool:
    if not get(vid):
        return False
    for p in (os.path.join(VIDEO_DIR, f"{vid}.mp4"), os.path.join(VIDEO_DIR, f"{vid}.jpg"),
              meta_path(vid)):
        try:
            os.remove(p)
        except OSError:
            pass
    return True


def make(plan_: dict, say=lambda m: None) -> dict:
    """A terv legyártása. Ami egy jelenetnél elhasal, azt kihagyjuk és
    megmondjuk — egy rossz elem miatt nem veszik el az egész videó."""
    os.makedirs(VIDEO_DIR, exist_ok=True)
    vid = _new_id()
    w, h = plan_["width"], plan_["height"]
    scenes = plan_["scenes"]
    say(f"Gyártás indul: {len(scenes)} jelenet, {plan_['aspect']}, kb. {plan_['seconds']:.0f} mp.")
    pieces: list[str] = []
    skipped: list[str] = []
    with tempfile.TemporaryDirectory(dir=VIDEO_DIR) as work:
        rendered: list[tuple[int, str]] = []
        for i, sc in enumerate(scenes):
            src = library.path_of(sc["id"])
            if not src:
                skipped.append(sc.get("name") or sc["id"])
                continue
            seg = os.path.join(work, f"s{i:04d}.mp4")
            ov = None
            if sc.get("text"):
                ov = os.path.join(work, f"t{i:04d}.png")
                if not text_overlay(sc["text"], w, h, ov):
                    ov = None
            try:
                scene_segment(sc, src, w, h, seg, ov)
                rendered.append((i, seg))
            except (RenderError, subprocess.SubprocessError) as e:
                skipped.append(sc.get("name") or sc["id"])
                logger.warning("jelenet kimaradt (%s): %s", sc["id"], e)
                say(f"{i + 1}/{len(scenes)} kimaradt — {sc.get('name') or sc['id']}")
                continue
            if (i + 1) % 5 == 0 or i + 1 == len(scenes):
                say(f"{i + 1}/{len(scenes)} jelenet kész")
        if not rendered:
            raise RenderError("egyetlen jelenet sem készült el")

        # Átmenetek: a villanás külön darab, az áttűnéshez a szomszédok
        # végét/elejét vágjuk vissza, és a kettő közé kerül az áttűnés.
        fade = float(plan_.get("fade_seconds") or director.FADE_SECONDS)
        flash = float(plan_.get("flash_seconds") or director.FLASH_SECONDS)
        n = len(rendered)
        for pos, (idx, seg) in enumerate(rendered):
            trans = scenes[idx].get("transition") if pos < n - 1 else "cut"
            if trans != "fade":
                pieces.append(seg)
                if trans == "flash":
                    fl = os.path.join(work, f"f{idx:04d}.mp4")
                    flash_segment(w, h, flash, fl)
                    pieces.append(fl)
                continue
            nxt = rendered[pos + 1][1]
            dur_a = max(director.MIN_SCENE, float(scenes[idx]["seconds"]))
            d = min(fade, dur_a / 2, float(scenes[rendered[pos + 1][0]]["seconds"]) / 2)
            head = os.path.join(work, f"h{idx:04d}.mp4")
            tail = os.path.join(work, f"a{idx:04d}.mp4")
            trn = os.path.join(work, f"x{idx:04d}.mp4")
            try:
                _trim(seg, head, 0.0, max(0.1, dur_a - d))
                _trim(seg, tail, max(0.0, dur_a - d), d)
                _crossfade(tail, nxt, d, trn)
                pieces += [head, trn]
                # A következő jelenet elejét az áttűnés már megmutatta.
                cut = os.path.join(work, f"c{idx:04d}.mp4")
                _trim(nxt, cut, d, None)
                rendered[pos + 1] = (rendered[pos + 1][0], cut)
            except (RenderError, subprocess.SubprocessError) as e:
                logger.warning("áttűnés kimaradt: %s", e)
                pieces.append(seg)

        listfile = os.path.join(work, "list.txt")
        with open(listfile, "w", encoding="utf-8") as f:
            for p in pieces:
                f.write(f"file '{os.path.abspath(p)}'\n")
        out = os.path.join(VIDEO_DIR, f"{vid}.mp4")
        say("Összefűzés…")
        r = _ffmpeg(["-f", "concat", "-safe", "0", "-i", listfile, "-c", "copy",
                     "-movflags", "+faststart", out], timeout=900)
        if r.returncode != 0 or not os.path.exists(out):
            # Ritka, de előfordul, hogy a darabok nem fűzhetők másolással:
            # ilyenkor újrakódolunk.
            say("Összefűzés újrakódolással…")
            _must(["-f", "concat", "-safe", "0", "-i", listfile, "-c:v", "libx264",
                   "-preset", PRESET, "-crf", CRF, "-pix_fmt", "yuv420p",
                   "-movflags", "+faststart", out], "összefűzés", timeout=1800)
        _ffmpeg(["-ss", "0.5", "-i", out, "-frames:v", "1", "-vf", "scale=540:-2", "-q:v", "4",
                 os.path.join(VIDEO_DIR, f"{vid}.jpg")], timeout=120)

    info = library.probe(out)
    meta = {"id": vid, "title": plan_.get("title", ""), "aspect": plan_["aspect"],
            "width": info.get("width"), "height": info.get("height"),
            "seconds": info.get("seconds"), "lang": plan_.get("lang", "hu"),
            "scenes": len(pieces), "used": len(rendered), "skipped": skipped,
            "bytes": os.path.getsize(out),
            "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    with open(meta_path(vid), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False)
    say(f"Kész: {meta['seconds']} mp, {meta['width']}x{meta['height']}, "
        f"{len(rendered)} elem" + (f", {len(skipped)} kimaradt." if skipped else "."))
    return meta
