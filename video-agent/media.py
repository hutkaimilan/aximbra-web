"""A videós agent médiatára: feltöltött és generált képek, videóklipek.

Minden fájl a köteten van, mellette egy JSON a leírásával. A feltöltést
az ffmpeg normalizálja: a kép legfeljebb 1600 px széles JPEG lesz, a klip
pedig hang nélküli WebM, mert a fej nélküli Chromium azt biztosan
lejátssza (a H.264 nem mindenhol van benne), és a renderelő képkockánként
tudja léptetni.

Emberek arcának cseréje videóban szándékosan nincs benne: egy ilyen
eszköz nem tudja ellenőrizni, ki van a képen, és mire adott engedélyt.
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

logger = logging.getLogger(__name__)

MEDIA_DIR = os.environ.get("MEDIA_DIR", "/data/media")
MAX_BYTES = 60 * 1024 * 1024
IMAGE_TYPES = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}
CLIP_TYPES = {"video/mp4": ".mp4", "video/quicktime": ".mov", "video/webm": ".webm"}
MAX_IMAGE_W = 1600
MAX_CLIP_SECONDS = 20
KEEP = 60


class MediaError(RuntimeError):
    pass


def _ffmpeg() -> str:
    exe = os.environ.get("FFMPEG_PATH")
    if exe:
        return exe
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()


def _run(args: list[str], timeout: int = 180) -> subprocess.CompletedProcess:
    return subprocess.run([_ffmpeg(), "-hide_banner", "-loglevel", "error", "-y", *args],
                          capture_output=True, timeout=timeout)


def _probe(path: str) -> dict:
    """Méret és hossz az ffmpeg kimenetéből; hiba esetén üres."""
    out = subprocess.run([_ffmpeg(), "-hide_banner", "-i", path], capture_output=True, timeout=60)
    text = out.stderr.decode(errors="replace")
    info = {}
    m = re.search(r",\s(\d{2,5})x(\d{2,5})[\s,]", text)
    if m:
        info["width"], info["height"] = int(m.group(1)), int(m.group(2))
    m = re.search(r"Duration:\s(\d+):(\d+):(\d+\.?\d*)", text)
    if m:
        info["seconds"] = round(int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3)), 2)
    return info


def _new_id() -> str:
    return secrets.token_hex(6)


def _meta_path(mid: str) -> str:
    return os.path.join(MEDIA_DIR, f"{mid}.json")


def path_of(mid: str) -> str | None:
    """A médiafájl útvonala; csak a saját mappánkból, azonosító alapján."""
    if not re.fullmatch(r"[a-z0-9]{12}", mid or ""):
        return None
    m = get(mid)
    if not m:
        return None
    p = os.path.join(MEDIA_DIR, m["file"])
    return p if os.path.exists(p) else None


def get(mid: str) -> dict | None:
    if not re.fullmatch(r"[a-z0-9]{12}", mid or ""):
        return None
    try:
        with open(_meta_path(mid), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def listing() -> list[dict]:
    if not os.path.isdir(MEDIA_DIR):
        return []
    out = []
    for name in os.listdir(MEDIA_DIR):
        if name.endswith(".json"):
            m = get(name[:-5])
            if m and os.path.exists(os.path.join(MEDIA_DIR, m["file"])):
                out.append(m)
    return sorted(out, key=lambda m: m.get("created_at", ""), reverse=True)


def delete(mid: str) -> bool:
    m = get(mid)
    if not m:
        return False
    for p in (os.path.join(MEDIA_DIR, m["file"]), _meta_path(mid)):
        try:
            os.remove(p)
        except OSError:
            pass
    return True


def _prune():
    for m in listing()[KEEP:]:
        delete(m["id"])


def _save(mid: str, meta: dict) -> dict:
    os.makedirs(MEDIA_DIR, exist_ok=True)
    with open(_meta_path(mid), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False)
    _prune()
    return meta


def add_image(data: bytes, name: str, note: str = "", source: str = "upload") -> dict:
    """Kép normalizálása: legfeljebb MAX_IMAGE_W széles JPEG."""
    if not data:
        raise MediaError("üres fájl")
    if len(data) > MAX_BYTES:
        raise MediaError("túl nagy fájl")
    mid = _new_id()
    os.makedirs(MEDIA_DIR, exist_ok=True)
    out = os.path.join(MEDIA_DIR, f"{mid}.jpg")
    with tempfile.TemporaryDirectory() as d:
        src = os.path.join(d, "in")
        with open(src, "wb") as f:
            f.write(data)
        r = _run(["-i", src, "-vf", f"scale='min({MAX_IMAGE_W},iw)':-2:flags=lanczos", "-frames:v", "1",
                  "-q:v", "3", out])
        if r.returncode != 0 or not os.path.exists(out):
            raise MediaError("ezt a képet nem sikerült beolvasni")
    info = _probe(out)
    return _save(mid, {"id": mid, "kind": "image", "file": f"{mid}.jpg", "name": (name or "kép")[:80],
                       "note": note[:200], "source": source, "width": info.get("width"),
                       "height": info.get("height"),
                       "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds")})


def add_clip(data: bytes, name: str, note: str = "") -> dict:
    """Klip normalizálása: néma WebM, legfeljebb MAX_CLIP_SECONDS hosszú.

    Néma, mert a videó hangsávját a narráció adja; a klip eredeti hangja
    ütközne vele. WebM, mert a fej nélküli Chromium azt biztosan dekódolja."""
    if not data:
        raise MediaError("üres fájl")
    if len(data) > MAX_BYTES:
        raise MediaError("túl nagy fájl")
    mid = _new_id()
    os.makedirs(MEDIA_DIR, exist_ok=True)
    out = os.path.join(MEDIA_DIR, f"{mid}.webm")
    with tempfile.TemporaryDirectory() as d:
        src = os.path.join(d, "in")
        with open(src, "wb") as f:
            f.write(data)
        r = _run(["-i", src, "-t", str(MAX_CLIP_SECONDS), "-an",
                  "-vf", "scale='min(1080,iw)':-2:flags=lanczos,fps=30",
                  "-c:v", "libvpx-vp9", "-b:v", "0", "-crf", "34", "-deadline", "good",
                  "-cpu-used", "5", "-row-mt", "1", out], timeout=900)
        if r.returncode != 0 or not os.path.exists(out) or os.path.getsize(out) == 0:
            raise MediaError("ezt a videót nem sikerült beolvasni")
    info = _probe(out)
    return _save(mid, {"id": mid, "kind": "clip", "file": f"{mid}.webm", "name": (name or "klip")[:80],
                       "note": note[:200], "source": "upload", "width": info.get("width"),
                       "height": info.get("height"), "seconds": info.get("seconds"),
                       "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds")})


def store(data: bytes, content_type: str, name: str, note: str = "") -> dict:
    ct = (content_type or "").split(";")[0].strip().lower()
    if ct in IMAGE_TYPES:
        return add_image(data, name, note)
    if ct in CLIP_TYPES:
        return add_clip(data, name, note)
    raise MediaError("csak kép (JPG, PNG, WebP) vagy videó (MP4, MOV, WebM) tölthető fel")


def copy_out(mid: str, dest_dir: str) -> str | None:
    """A médiafájl másolata a renderelés melletti mappába."""
    p = path_of(mid)
    if not p:
        return None
    dest = os.path.join(dest_dir, os.path.basename(p))
    shutil.copyfile(p, dest)
    return dest
