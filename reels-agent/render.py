"""A renderelő: a jelenettervből kész MP4, csak ffmpeg-gel.

Miért nem fej nélküli böngészővel (mint a régi agent): egy gyors montázshoz
képkockánként léptetett Chromium a legdrágább út — sok memória, lassú build,
és bármelyik képkockán el tud hasalni. Itt minden jelenet egy rövid ffmpeg-
futás, azonos formátumban, és a végén a `concat` másolással fűzi össze őket.
Ez gyors, kevés memória, és egy hibás elem csak egy jelenetet visz el.

Amit egy jelenet kaphat, azt az effects.py sorolja fel: mozgás, színezés/képi
hatás, sebesség, felirat (hely, stílus, animáció) és az utána jövő átmenet.

Hang nincs benne — nem is kérted; a TikTokon a saját hangot teszed alá.
"""
from __future__ import annotations

import json
import logging
import os
import re
import secrets
import subprocess
import tempfile
from datetime import datetime, timezone

import effects
import library

logger = logging.getLogger("reels.render")

VIDEO_DIR = os.environ.get("VIDEO_DIR", "/data/videos")
FPS = effects.FPS
CRF = "21"
PRESET = "veryfast"
FONT_CANDIDATES = (
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
)
# Álló videón a telefon felülete levágja a széleket: a szöveg ezeken belül marad.
SAFE = {"left": 64, "right": 100, "top": 100, "bottom_quarter": 0.25}
# A felirat függőleges helye a kereten belül (a doboz közepe).
TEXT_Y = {"top": 0.17, "middle": 0.50, "lower": 0.63, "bottom": 0.72}
FLASH_SECONDS = 0.07
_ID_RE = re.compile(r"[a-z0-9]{10}")


class RenderError(RuntimeError):
    pass


def _ffmpeg(args: list[str], timeout: int = 900) -> subprocess.CompletedProcess:
    return subprocess.run([library._ffmpeg(), "-hide_banner", "-loglevel", "error", "-y", *args],
                          capture_output=True, timeout=timeout)


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

def text_overlay(text: str, w: int, h: int, out: str, position: str = "lower",
                 style: str = "outline") -> bool:
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
    size = max(26, int(w * (0.052 if style == "caption" else 0.072)))
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
    while len(lines) > 4 and size > 22 and fp:          # ne lógjon ki a képből
        size = int(size * 0.88)
        font = ImageFont.truetype(fp, size)
        lines = wrap(font)
    line_h = int(size * 1.24)
    block_h = line_h * len(lines)
    top_limit = SAFE["top"] + 16
    bottom_limit = int(h * (1 - SAFE["bottom_quarter"]))
    centre = TEXT_Y.get(position, TEXT_Y["lower"]) * h
    y = int(max(top_limit, min(centre - block_h / 2, bottom_limit - block_h)))

    pad = int(size * 0.42)
    if style == "bar":
        d.rectangle([0, y - pad, w, y + block_h + pad], fill=(0, 0, 0, 170))
    elif style == "box":
        widest = max(d.textlength(l, font=font) for l in lines)
        bx = left + (box_w - widest) / 2
        d.rounded_rectangle([bx - pad, y - pad, bx + widest + pad, y + block_h + pad],
                            radius=int(pad * 0.9), fill=(0, 0, 0, 180))

    for n, line in enumerate(lines):
        tw = d.textlength(line, font=font)
        x = left + (box_w - tw) / 2
        ly = y + n * line_h
        if style in ("outline", "caption"):
            for dx, dy in ((-3, 0), (3, 0), (0, -3), (0, 3), (-2, -2), (2, 2), (-2, 2), (2, -2)):
                d.text((x + dx, ly + dy), line, font=font, fill=(0, 0, 0, 220))
        d.text((x, ly), line, font=font, fill=(255, 255, 255, 255))
    img.save(out)
    return True


def _text_chain(anim: str, d: float, w: int, h: int) -> tuple[str, str]:
    """(a felirat-réteg szűrője, az overlay x:y kifejezése)."""
    anim = anim if anim in effects.TEXT_ANIMS else "none"
    pre = "format=rgba"
    if anim in ("fade", "pop"):
        pre += f",fade=t=in:st=0:d={min(0.35, max(0.1, d * 0.3)):.3f}:alpha=1"
    if anim == "slide_up" or anim == "pop":
        rise = int(h * 0.05)
        return pre, f"0:'if(lt(t,0.3),{rise}*(1-t/0.3),0)'"
    if anim == "shake":
        return pre, f"'{max(3, int(w * 0.006))}*sin(t*28)':'{max(2, int(h * 0.003))}*cos(t*33)'"
    return pre, "0:0"


# ---- egy jelenet ----------------------------------------------------------

def _cover(w: int, h: int) -> str:
    """Kitöltés levágással: a kép/klip betölti a keretet, a széle lemegy."""
    return (f"scale={w}:{h}:force_original_aspect_ratio=increase:flags=lanczos,"
            f"crop={w}:{h},setsar=1")


def _scene_chain(scene: dict, w: int, h: int) -> tuple[str, bool]:
    """A jelenet képi lánca a nyers bemenettől a kész kockáig."""
    d = float(scene["seconds"])
    motion = scene.get("motion") if effects.is_motion(scene.get("motion") or "") else "none"
    look = scene.get("look") if effects.is_look(scene.get("look") or "") else "none"
    is_clip = scene.get("kind") == "clip"
    parts: list[str] = []
    if is_clip:
        speed = effects.clamp_speed(scene.get("speed", 1.0))
        parts.append(_cover(w, h))
        if abs(speed - 1.0) > 0.01:
            parts.append(f"setpts={1 / speed:.4f}*PTS")
        parts.append(f"fps={FPS}")
        mf = effects.motion_filter(motion, d, w, h) if motion in ("shake", "zoom_pulse") else ""
        if mf:
            parts.append(mf)
    else:
        mf = effects.motion_filter(motion, d, w, h)
        if mf:
            # A zoompan bemenete legyen nagyobb a kimenetnél, különben lépcsőzik.
            parts.append(f"scale={w * 2}:{h * 2}:force_original_aspect_ratio=increase:flags=lanczos,"
                         f"crop={w * 2}:{h * 2},setsar=1")
            parts.append(mf)
        else:
            parts.append(_cover(w, h))
            parts.append(f"fps={FPS}")
    after = effects.after_motion(motion, d)
    if after:
        parts.append(after)
    lf = effects.look_filter(look, d, w, h)
    complex_look = bool(lf) and effects.needs_complex(look)
    if lf and not complex_look:
        parts.append(lf)
    chain = ",".join(p for p in parts if p)
    if complex_look:
        chain = f"{chain},{lf}" if chain else lf
    return chain, complex_look


def scene_segment(scene: dict, src: str, w: int, h: int, out: str, overlay: str | None) -> None:
    """Egy jelenet önálló MP4-ként, mindegyik ugyanabban a formátumban —
    így a végén másolással fűzhetők össze."""
    d = float(scene["seconds"])
    if scene.get("kind") == "clip":
        speed = effects.clamp_speed(scene.get("speed", 1.0))
        src_len = d * speed                       # gyorsításnál több nyersanyag kell
        ins = ["-ss", f"{float(scene.get('start') or 0):.3f}", "-t", f"{src_len:.3f}", "-i", src]
    else:
        ins = ["-loop", "1", "-framerate", str(FPS), "-t", f"{d:.3f}", "-i", src]
    chain, _complex = _scene_chain(scene, w, h)
    args = [*ins]
    if overlay:
        pre, xy = _text_chain(scene.get("text_anim") or "none", d, w, h)
        # A feliratot képkockákká kell tenni, különben az áttűnése egyetlen
        # (nulla átlátszóságú) kockán ragadna, és a felirat sosem jelenne meg.
        args += ["-loop", "1", "-framerate", str(FPS), "-t", f"{d:.3f}", "-i", overlay,
                 "-filter_complex",
                 f"[0:v]{chain},format=yuv420p[v];[1:v]{pre}[t];[v][t]overlay={xy}:format=auto[o]",
                 "-map", "[o]"]
    else:
        args += ["-filter_complex", f"[0:v]{chain},format=yuv420p[o]", "-map", "[o]"]
    args += ["-an", "-t", f"{d:.3f}", "-r", str(FPS), "-c:v", "libx264", "-preset", PRESET,
             "-crf", CRF, "-pix_fmt", "yuv420p", "-video_track_timescale", "90000", out]
    _must(args, f"jelenet ({scene.get('name') or scene['id']})", timeout=600)


def colour_segment(w: int, h: int, seconds: float, out: str, colour: str = "white") -> None:
    _must(["-f", "lavfi", "-i", f"color=c={colour}:s={w}x{h}:r={FPS}:d={seconds:.3f}",
           "-vf", "format=yuv420p", "-an", "-c:v", "libx264", "-preset", PRESET, "-crf", CRF,
           "-video_track_timescale", "90000", out], "villanás", timeout=120)


def _trim(src: str, out: str, start: float = 0.0, dur: float | None = None) -> None:
    args = ["-ss", f"{start:.3f}", "-i", src]
    if dur is not None:
        args += ["-t", f"{dur:.3f}"]
    args += ["-an", "-r", str(FPS), "-c:v", "libx264", "-preset", PRESET, "-crf", CRF,
             "-pix_fmt", "yuv420p", "-video_track_timescale", "90000", out]
    _must(args, "vágás", timeout=300)


def transition_segment(a: str, b: str, kind: str, seconds: float, out: str) -> None:
    """Átmenet A vége és B eleje között — az ffmpeg xfade egész készletéből."""
    name = kind if kind in effects.XFADE else "fade"
    _must(["-i", a, "-i", b, "-filter_complex",
           f"[0:v][1:v]xfade=transition={name}:duration={seconds:.3f}:offset=0,format=yuv420p[o]",
           "-map", "[o]", "-an", "-t", f"{seconds:.3f}", "-r", str(FPS), "-c:v", "libx264",
           "-preset", PRESET, "-crf", CRF, "-video_track_timescale", "90000", out],
          f"átmenet ({name})", timeout=300)


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
    if not get(vid):
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
                if not text_overlay(sc["text"], w, h, ov, sc.get("text_position") or "lower",
                                    sc.get("text_style") or "outline"):
                    ov = None
            try:
                scene_segment(sc, src, w, h, seg, ov)
            except (RenderError, subprocess.SubprocessError) as e:
                logger.warning("jelenet hiba (%s): %s", sc["id"], e)
                # Egy merészebb hatás néha nem jön össze: essünk vissza a
                # csupasz kockára, hogy az elem azért bekerüljön.
                try:
                    plain = {**sc, "motion": "none", "look": "none", "speed": 1.0}
                    scene_segment(plain, src, w, h, seg, ov)
                    say(f"{i + 1}/{len(scenes)} effekt nélkül — {sc.get('name') or sc['id']}")
                except (RenderError, subprocess.SubprocessError) as e2:
                    skipped.append(sc.get("name") or sc["id"])
                    logger.warning("jelenet kimaradt (%s): %s", sc["id"], e2)
                    say(f"{i + 1}/{len(scenes)} kimaradt — {sc.get('name') or sc['id']}")
                    continue
            rendered.append((i, seg))
            if (i + 1) % 5 == 0 or i + 1 == len(scenes):
                say(f"{i + 1}/{len(scenes)} jelenet kész")
        if not rendered:
            raise RenderError("egyetlen jelenet sem készült el")

        n = len(rendered)
        for pos, (idx, seg) in enumerate(rendered):
            kind = (scenes[idx].get("transition") or "cut") if pos < n - 1 else "cut"
            if kind in ("cut", "flash", "blackout"):
                pieces.append(seg)
                if kind in ("flash", "blackout"):
                    fl = os.path.join(work, f"f{idx:04d}.mp4")
                    try:
                        colour_segment(w, h, FLASH_SECONDS, fl,
                                       "white" if kind == "flash" else "black")
                        pieces.append(fl)
                    except RenderError as e:
                        logger.warning("villanás kimaradt: %s", e)
                continue
            # xfade: a két szomszéd végét/elejét visszavágjuk, közéjük kerül az átmenet
            nxt = rendered[pos + 1][1]
            dur_a = max(0.3, float(scenes[idx]["seconds"]))
            dur_b = max(0.3, float(scenes[rendered[pos + 1][0]]["seconds"]))
            d = min(float(plan_.get("fade_seconds") or 0.3), dur_a / 2, dur_b / 2)
            head = os.path.join(work, f"h{idx:04d}.mp4")
            tail = os.path.join(work, f"a{idx:04d}.mp4")
            trn = os.path.join(work, f"x{idx:04d}.mp4")
            cut = os.path.join(work, f"c{idx:04d}.mp4")
            try:
                _trim(seg, head, 0.0, max(0.1, dur_a - d))
                _trim(seg, tail, max(0.0, dur_a - d), d)
                transition_segment(tail, nxt, kind, d, trn)
                _trim(nxt, cut, d, None)
                pieces += [head, trn]
                rendered[pos + 1] = (rendered[pos + 1][0], cut)
            except (RenderError, subprocess.SubprocessError) as e:
                logger.warning("átmenet kimaradt (%s): %s", kind, e)
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
            say("Összefűzés újrakódolással…")
            _must(["-f", "concat", "-safe", "0", "-i", listfile, "-c:v", "libx264",
                   "-preset", PRESET, "-crf", CRF, "-pix_fmt", "yuv420p",
                   "-movflags", "+faststart", out], "összefűzés", timeout=1800)
        _ffmpeg(["-ss", "0.5", "-i", out, "-frames:v", "1", "-vf", "scale=540:-2", "-q:v", "4",
                 os.path.join(VIDEO_DIR, f"{vid}.jpg")], timeout=120)

    info = library.probe(out)
    meta = {"id": vid, "title": plan_.get("title", ""), "brief": plan_.get("brief", "")[:300],
            "aspect": plan_["aspect"], "width": info.get("width"), "height": info.get("height"),
            "seconds": info.get("seconds"), "lang": plan_.get("lang", "hu"),
            "by": plan_.get("by", "rendező"), "trends": plan_.get("trends_used", []),
            "scenes": len(pieces), "used": len(rendered), "skipped": skipped,
            "bytes": os.path.getsize(out),
            "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    with open(meta_path(vid), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False)
    say(f"Kész: {meta['seconds']} mp, {meta['width']}x{meta['height']}, "
        f"{len(rendered)} elem" + (f", {len(skipped)} kimaradt." if skipped else "."))
    return meta
