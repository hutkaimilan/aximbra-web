"""A Reels-agent médiatára: a telefonról feltöltött fotók és videók.

Minden elem a köteten van, mellette egy JSON a leírásával. A feltöltés
azonnal visszatér (a telefon böngészője kb. egy perc csend után feladja),
az átalakítás a háttérben fut:

  * kép  → legfeljebb MAX_IMAGE_W széles JPEG (HEIC/HEIF/AVIF/TIFF is, Pillow-val)
  * klip → H.264/AAC MP4, a hosszabb oldalon legfeljebb MAX_CLIP_W px,
           plusz egy borítókép (poster.jpg)

Amit a telefon küld, de nem mond meg (típus nélküli fájl), azt a tartalmából
döntjük el. A tár magától NEM töröl friss elemet: csak a KEEP-en túli, legalább
KEEP_MIN_AGE óránál régebbieket, hogy egy 60–100 elemes feltöltés ne tolja ki
önmagát.
"""
from __future__ import annotations

import io
import json
import logging
import os
import re
import secrets
import shutil
import subprocess
import tempfile
import threading
import time
from datetime import datetime, timezone

logger = logging.getLogger("reels.library")

MEDIA_DIR = os.environ.get("MEDIA_DIR", "/data/media")
# Egy 4K-s iPhone-felvétel 2-3 perce is belefér.
MAX_BYTES = int(os.environ.get("MAX_UPLOAD_MB", "600")) * 1024 * 1024
MAX_IMAGE_W = 1920
MAX_CLIP_W = 1920
MAX_CLIP_SECONDS = 300
# Ennyi elem fölött a legrégebbiek törlődnek — de csak ha ennél régebbiek.
KEEP = int(os.environ.get("LIBRARY_KEEP", "500"))
KEEP_MIN_AGE_H = 48
# Egyszerre ennyi videót alakítunk át: párhuzamos ffmpeg-ek kifutnának a memóriából.
CLIP_WORKERS = max(1, int(os.environ.get("CLIP_WORKERS", "2")))

IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}
CLIP_TYPES = {"video/mp4", "video/quicktime", "video/webm"}
CLIP_ALIASES = {"video/x-m4v": "video/mp4", "video/3gpp": "video/mp4", "video/3gpp2": "video/mp4",
                "video/mpeg": "video/mp4", "video/x-matroska": "video/webm", "video/avi": "video/mp4",
                "video/x-msvideo": "video/mp4", "video/hevc": "video/quicktime"}
EXT_TYPES = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp",
             ".gif": "image/gif", ".heic": "image/heic", ".heif": "image/heif", ".avif": "image/avif",
             ".tif": "image/tiff", ".tiff": "image/tiff", ".bmp": "image/bmp", ".dng": "image/dng",
             ".mp4": "video/mp4", ".m4v": "video/mp4", ".mov": "video/quicktime", ".qt": "video/quicktime",
             ".webm": "video/webm", ".3gp": "video/mp4", ".mkv": "video/webm", ".avi": "video/mp4"}

_ID_RE = re.compile(r"[a-z0-9]{12}")


class LibraryError(RuntimeError):
    pass


# ---- ffmpeg ----------------------------------------------------------------

def _ffmpeg() -> str:
    exe = os.environ.get("FFMPEG_PATH")
    if exe:
        return exe
    if shutil.which("ffmpeg"):
        return "ffmpeg"
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()


def _run(args: list[str], timeout: int = 600) -> subprocess.CompletedProcess:
    return subprocess.run([_ffmpeg(), "-hide_banner", "-loglevel", "error", "-y", *args],
                          capture_output=True, timeout=timeout)


def probe(path: str) -> dict:
    """Méret, hossz, képkockasebesség az ffmpeg kimenetéből; hiba esetén üres."""
    try:
        out = subprocess.run([_ffmpeg(), "-hide_banner", "-i", path], capture_output=True, timeout=120)
    except (OSError, subprocess.SubprocessError):
        return {}
    text = out.stderr.decode(errors="replace")
    info: dict = {}
    m = re.search(r",\s(\d{2,5})x(\d{2,5})[\s,\[]", text)
    if m:
        info["width"], info["height"] = int(m.group(1)), int(m.group(2))
    m = re.search(r"Duration:\s(\d+):(\d+):(\d+\.?\d*)", text)
    if m:
        info["seconds"] = round(int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3)), 2)
    m = re.search(r"(\d+(?:\.\d+)?)\sfps", text)
    if m:
        info["fps"] = float(m.group(1))
    m = re.search(r"rotation of\s(-?\d+)", text)
    if m:
        info["rotation"] = int(float(m.group(1)))
    return info


# ---- a tár fájljai ---------------------------------------------------------

def _new_id() -> str:
    return secrets.token_hex(6)


def _meta_path(mid: str) -> str:
    return os.path.join(MEDIA_DIR, f"{mid}.json")


def get(mid: str) -> dict | None:
    if not _ID_RE.fullmatch(mid or ""):
        return None
    try:
        with open(_meta_path(mid), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def path_of(mid: str, which: str = "file") -> str | None:
    """A médiafájl útvonala; csak a saját mappánkból, azonosító alapján.
    which: "file" (a használható változat), "poster", "raw" (nyers feltöltés)."""
    m = get(mid)
    if not m or which not in ("file", "poster", "raw"):
        return None
    name = m.get(which)
    if not name or "/" in name or "\\" in name:
        return None
    p = os.path.join(MEDIA_DIR, name)
    return p if os.path.exists(p) else None


def listing() -> list[dict]:
    """Minden elem, a legújabb elöl."""
    if not os.path.isdir(MEDIA_DIR):
        return []
    out = []
    for name in os.listdir(MEDIA_DIR):
        if not name.endswith(".json"):
            continue
        m = get(name[:-5])
        if m:
            out.append(m)
    return sorted(out, key=lambda m: m.get("created_at", ""), reverse=True)


def stats() -> dict:
    items = listing()
    return {"count": len(items),
            "images": sum(1 for m in items if m.get("kind") == "image"),
            "clips": sum(1 for m in items if m.get("kind") == "clip"),
            "pending": sum(1 for m in items if m.get("status") == "processing"),
            "failed": sum(1 for m in items if m.get("status") == "failed"),
            "bytes": _dir_bytes()}


def _dir_bytes() -> int:
    total = 0
    for root, _dirs, files in os.walk(MEDIA_DIR) if os.path.isdir(MEDIA_DIR) else []:
        for f in files:
            try:
                total += os.path.getsize(os.path.join(root, f))
            except OSError:
                pass
    return total


def delete(mid: str) -> bool:
    m = get(mid)
    if not m:
        return False
    for key in ("file", "poster", "raw"):
        name = m.get(key)
        if name and "/" not in name and "\\" not in name:
            try:
                os.remove(os.path.join(MEDIA_DIR, name))
            except OSError:
                pass
    try:
        os.remove(_meta_path(mid))
    except OSError:
        pass
    return True


def _prune() -> None:
    """A KEEP-en túli elemek törlése — de csak a legalább KEEP_MIN_AGE_H órával
    korábban feltöltöttek. Egy nagy, friss feltöltés így nem törli ki magát.

    A sorrendet a leíró fájl módosítási ideje adja, nem a created_at: egy
    60-100 elemes feltöltésnél a feltöltési időpontok egybeesnek."""
    items = []
    for m in listing():
        try:
            items.append((os.path.getmtime(_meta_path(m["id"])), m["id"]))
        except OSError:
            pass
    items.sort(reverse=True)                      # legfrissebb elöl
    cutoff = time.time() - KEEP_MIN_AGE_H * 3600
    for mtime, mid in items[KEEP:]:
        if mtime < cutoff:
            delete(mid)


def _save(mid: str, meta: dict) -> dict:
    os.makedirs(MEDIA_DIR, exist_ok=True)
    tmp = _meta_path(mid) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False)
    os.replace(tmp, _meta_path(mid))
    return meta


def set_note(mid: str, note: str) -> dict | None:
    """Az elemhez tartozó rendezői utasítás („ez legyen a nyitókép…")."""
    m = get(mid)
    if not m:
        return None
    return _save(mid, {**m, "note": (note or "")[:400]})


def ready(m: dict | None) -> bool:
    return bool(m) and m.get("status") == "ready"


# ---- típusfelismerés -------------------------------------------------------

def _pillow():
    from PIL import Image
    try:
        import pillow_heif
        pillow_heif.register_heif_opener()
    except Exception as e:  # noqa: BLE001 — HEIC nélkül a többi formátum megy
        logger.warning("pillow-heif nem tölthető be: %s", e)
    return Image


# A típus eldöntéséhez a fájl eleje elég (a fejléc); egy 600 MB-os videót
# nem olvasunk be csak azért, hogy megnézzük, kép-e.
SNIFF_BYTES = 256 * 1024


def _is_image(data: bytes) -> bool:
    """Kép-e: a Pillow (HEIC-kel együtt) felismeri-e a fejlécét."""
    try:
        Image = _pillow()
        return bool(Image.open(io.BytesIO(data)).format)
    except Exception:  # noqa: BLE001
        return False


def _to_jpeg(data: bytes) -> bytes:
    """Bármilyen Pillow által ismert kép (HEIC, AVIF, GIF, TIFF, BMP…) → JPEG."""
    try:
        Image = _pillow()
        img = Image.open(io.BytesIO(data))
        img = getattr(img, "convert")("RGB")
        out = io.BytesIO()
        img.save(out, "JPEG", quality=92, optimize=True)
        return out.getvalue()
    except Exception as e:  # noqa: BLE001
        raise LibraryError(f"ezt a képet nem tudtam beolvasni ({type(e).__name__})") from e


def decide_type(content_type: str, name: str, data: bytes) -> str:
    """Mi ez: kép vagy videó? A böngésző típusa, a kiterjesztés, végül a tartalom."""
    ct = (content_type or "").split(";")[0].strip().lower()
    ct = CLIP_ALIASES.get(ct, ct)
    ext = os.path.splitext(name or "")[1].lower()
    if ct.split("/")[0] in ("application", "text", "font", "model", "audio") \
            and ct != "application/octet-stream" and ext not in EXT_TYPES:
        raise LibraryError("ez nem kép vagy videó")
    if not (ct.startswith("image/") or ct.startswith("video/")):
        ct = EXT_TYPES.get(ext, "")
    if not ct:
        ct = "image/unknown" if _is_image(data) else "video/unknown"
    return ct


# ---- felvétel a tárba ------------------------------------------------------

def store(data: bytes, content_type: str, name: str, note: str = "", source: str = "upload") -> dict:
    """Egy feltöltött fájl a tárba. Azonnal visszatér; a nehéz munka a háttérben."""
    if not data:
        raise LibraryError("üres fájl")
    if len(data) > MAX_BYTES:
        raise LibraryError(f"túl nagy fájl (legfeljebb {MAX_BYTES // (1024 * 1024)} MB)")
    ct = decide_type(content_type, name, data)
    if ct.startswith("image/"):
        return _add_image(data, ct, name, note, source)
    return _add_clip(data, ct, name, note, source)


def store_file(path: str, content_type: str, name: str, note: str = "",
               source: str = "upload") -> dict:
    """Egy már lemezen lévő fájl a tárba. Ezt használja a darabolt feltöltés:
    egy 600 MB-os videót nem viszünk át a memórián (a beolvasás + a másolat
    több mint egy gigabájt lenne, két futó ffmpeg mellett)."""
    size = os.path.getsize(path)
    if size == 0:
        raise LibraryError("üres fájl")
    if size > MAX_BYTES:
        raise LibraryError(f"túl nagy fájl (legfeljebb {MAX_BYTES // (1024 * 1024)} MB)")
    with open(path, "rb") as f:
        head = f.read(SNIFF_BYTES)
    ct = decide_type(content_type, name, head)
    if ct.startswith("image/"):
        with open(path, "rb") as f:          # kép: néhány tíz MB, elfér
            return _add_image(f.read(), ct, name, note, source)
    mid = _new_id()
    os.makedirs(MEDIA_DIR, exist_ok=True)
    raw = f"{mid}.upload"
    dest = os.path.join(MEDIA_DIR, raw)
    try:
        os.replace(path, dest)               # ugyanazon a köteten: átnevezés, másolás nélkül
    except OSError:
        shutil.move(path, dest)
    meta = _save(mid, {**_base_meta(mid, "clip", name, note, source, size),
                       "file": f"{mid}.mp4", "raw": raw, "status": "processing", "src_type": ct})
    _start_clip(mid)
    return meta


def _base_meta(mid: str, kind: str, name: str, note: str, source: str, size: int) -> dict:
    return {"id": mid, "kind": kind, "name": (name or ("kép" if kind == "image" else "klip"))[:120],
            "note": (note or "")[:400], "source": source, "bytes": size,
            "width": None, "height": None, "seconds": None, "poster": None, "error": "",
            "created_at": datetime.now(timezone.utc).isoformat(timespec="milliseconds")}


def _add_image(data: bytes, ct: str, name: str, note: str, source: str) -> dict:
    """A kép átalakítása azonnal: egy fotó ezredmásodpercek kérdése."""
    mid = _new_id()
    os.makedirs(MEDIA_DIR, exist_ok=True)
    meta = _base_meta(mid, "image", name, note, source, len(data))
    if ct not in IMAGE_TYPES:
        data = _to_jpeg(data)
    out = os.path.join(MEDIA_DIR, f"{mid}.jpg")
    with tempfile.TemporaryDirectory() as d:
        src = os.path.join(d, "in")
        with open(src, "wb") as f:
            f.write(data)
        r = _run(["-i", src, "-vf", f"scale='min({MAX_IMAGE_W},iw)':-2:flags=lanczos",
                  "-frames:v", "1", "-q:v", "3", out], timeout=180)
        if r.returncode != 0 or not os.path.exists(out):
            # Az ffmpeg elhasalt (pl. ritka színprofil): essünk vissza a Pillow-ra.
            try:
                Image = _pillow()
                img = Image.open(io.BytesIO(data)).convert("RGB")
                if img.width > MAX_IMAGE_W:
                    img = img.resize((MAX_IMAGE_W, max(1, round(img.height * MAX_IMAGE_W / img.width))))
                img.save(out, "JPEG", quality=90)
            except Exception as e:  # noqa: BLE001
                raise LibraryError("ezt a képet nem sikerült beolvasni") from e
    info = probe(out)
    return _save(mid, {**meta, "file": f"{mid}.jpg", "poster": f"{mid}.jpg", "status": "ready",
                       "width": info.get("width"), "height": info.get("height")})


def _add_clip(data: bytes, ct: str, name: str, note: str, source: str) -> dict:
    """A videó mentése nyersen; az átalakítás a háttérben, legfeljebb
    CLIP_WORKERS párhuzamosan. A kérés nem várja meg: egy 75 mp-es felvételen
    az iPhone böngészője korábban „Load failed"-del feladta."""
    mid = _new_id()
    os.makedirs(MEDIA_DIR, exist_ok=True)
    raw = f"{mid}.upload"
    tmp = os.path.join(MEDIA_DIR, raw + ".tmp")
    with open(tmp, "wb") as f:
        f.write(data)
    os.replace(tmp, os.path.join(MEDIA_DIR, raw))
    meta = _save(mid, {**_base_meta(mid, "clip", name, note, source, len(data)),
                       "file": f"{mid}.mp4", "raw": raw, "status": "processing", "src_type": ct})
    _start_clip(mid)
    return meta


_busy: set[str] = set()
_busy_lock = threading.Lock()
_sem = threading.BoundedSemaphore(CLIP_WORKERS)


def queue_depth() -> int:
    with _busy_lock:
        return len(_busy)


def _start_clip(mid: str) -> None:
    with _busy_lock:
        if mid in _busy:
            return
        _busy.add(mid)
    threading.Thread(target=_clip_worker, args=(mid,), daemon=True).start()


def _clip_worker(mid: str) -> None:
    try:
        with _sem:
            _convert_clip(mid)
    except Exception:  # noqa: BLE001 — a szál sosem viheti magával a szolgáltatást
        logger.exception("klip-átalakítás összeomlott: %s", mid)
        m = get(mid)
        if m:
            _save(mid, {**m, "status": "failed", "error": "Ezt a videót nem sikerült átalakítani."})
    finally:
        with _busy_lock:
            _busy.discard(mid)


def _convert_clip(mid: str) -> None:
    m = get(mid)
    if not m or not m.get("raw"):
        return
    src = os.path.join(MEDIA_DIR, m["raw"])
    if not os.path.exists(src):
        _save(mid, {**m, "status": "failed", "error": "A nyers feltöltés eltűnt."})
        return
    out = os.path.join(MEDIA_DIR, m["file"])
    t0 = time.time()
    info = probe(src)
    logger.info("klip átalakítás indul: %s (%s, %.1f MB, %s mp)", mid, m.get("name"),
                os.path.getsize(src) / 1048576, info.get("seconds"))
    # H.264/AAC MP4: a Safari is lejátssza (előnézet a telefonon), és az
    # ffmpeg-es vágáshoz is ez a legegyszerűbb. A hosszabb oldal max MAX_CLIP_W.
    vf = (f"scale='if(gt(iw,ih),min({MAX_CLIP_W},iw),-2)':'if(gt(iw,ih),-2,min({MAX_CLIP_W},ih))'"
          ":flags=lanczos,format=yuv420p")
    r = _run(["-i", src, "-t", str(MAX_CLIP_SECONDS), "-vf", vf, "-c:v", "libx264", "-preset", "veryfast",
              "-crf", "25", "-movflags", "+faststart", "-c:a", "aac", "-b:a", "96k", "-ac", "2",
              "-max_muxing_queue_size", "1024", out], timeout=1800)
    if r.returncode != 0 or not os.path.exists(out) or os.path.getsize(out) == 0:
        err = r.stderr.decode(errors="replace")[-300:]
        logger.warning("klip-átalakítás hiba (%s): %s", mid, err)
        _save(mid, {**m, "status": "failed", "error": "Ezt a videót nem sikerült beolvasni."})
        return
    poster = f"{mid}.poster.jpg"
    pinfo = probe(out)
    at = min(1.0, max(0.0, (pinfo.get("seconds") or 1) / 3))
    _run(["-ss", f"{at:.2f}", "-i", out, "-frames:v", "1", "-vf", "scale='min(640,iw)':-2",
          "-q:v", "4", os.path.join(MEDIA_DIR, poster)], timeout=120)
    try:
        os.remove(src)
    except OSError:
        pass
    m = {**m, "width": pinfo.get("width"), "height": pinfo.get("height"),
         "seconds": pinfo.get("seconds"), "fps": pinfo.get("fps"),
         "poster": poster if os.path.exists(os.path.join(MEDIA_DIR, poster)) else None,
         "status": "ready", "error": ""}
    m.pop("raw", None)
    _save(mid, m)
    logger.info("klip kész: %s — %sx%s, %s mp, %.0f mp alatt", mid, m["width"], m["height"],
                m["seconds"], time.time() - t0)
    _prune()


def retry(mid: str) -> bool:
    """Félbemaradt vagy elhasalt átalakítás újraindítása (ha a nyers fájl megvan)."""
    m = get(mid)
    if not m or m.get("kind") != "clip" or not m.get("raw"):
        return False
    if not os.path.exists(os.path.join(MEDIA_DIR, m["raw"])):
        return False
    _save(mid, {**m, "status": "processing", "error": ""})
    _start_clip(mid)
    return True


def resume_pending() -> int:
    """Újraindulás után: a félbemaradt átalakítások folytatása."""
    n = 0
    for m in listing():
        if m.get("status") == "processing" and m.get("kind") == "clip":
            if retry(m["id"]):
                n += 1
            else:
                _save(m["id"], {**m, "status": "failed",
                                "error": "Az átalakítás újraindulás közben megszakadt."})
    return n


# ---- darabolt feltöltés ----------------------------------------------------
# A Railway egy kérést legfeljebb 5 percig enged, és egy telefonos felvétel
# gyenge neten ennyi idő alatt nem ér fel egyben. A felület darabokban küldi,
# darabonként újrapróbálva; itt rakjuk össze.

CHUNK_MAX = 8 * 1024 * 1024
UPLOAD_TTL = 24 * 3600
_UPLOAD_ID_RE = re.compile(r"[a-f0-9]{16,40}")


def scratch_dir() -> str:
    """Átmeneti mappa a köteten: ide stream-el, ami még nem a tár része."""
    d = os.path.join(MEDIA_DIR, ".uploads", "scratch")
    os.makedirs(d, exist_ok=True)
    return d


def _upload_dir(upload_id: str) -> str:
    if not _UPLOAD_ID_RE.fullmatch(upload_id or ""):
        raise LibraryError("hibás feltöltés-azonosító")
    return os.path.join(MEDIA_DIR, ".uploads", upload_id)


def _prune_uploads() -> None:
    root = os.path.join(MEDIA_DIR, ".uploads")
    if not os.path.isdir(root):
        return
    for name in os.listdir(root):
        d = os.path.join(root, name)
        try:
            if time.time() - os.path.getmtime(d) > UPLOAD_TTL:
                shutil.rmtree(d, ignore_errors=True)
        except OSError:
            pass


def save_chunk(upload_id: str, index: int, total: int, data: bytes) -> dict:
    """Egy darab mentése. Ugyanazt a darabot újra küldve felülírja (újrapróbálás)."""
    max_parts = MAX_BYTES // (1024 * 1024) + 2      # 1 MB-os darabnál is elég
    if not (0 < total <= max_parts) or not (0 <= index < total):
        raise LibraryError("hibás darabszám")
    if not data or len(data) > CHUNK_MAX:
        raise LibraryError("hibás darabméret")
    d = _upload_dir(upload_id)
    if index == 0:
        _prune_uploads()
    os.makedirs(d, exist_ok=True)
    tmp = os.path.join(d, f"{index:05d}.part")
    with open(tmp, "wb") as f:
        f.write(data)
    os.replace(tmp, os.path.join(d, f"{index:05d}"))
    have = len([n for n in os.listdir(d) if n.isdigit()])
    return {"ok": True, "index": index, "have": have, "total": total}


def finish_chunks(upload_id: str, total: int, content_type: str, name: str, note: str = "") -> dict:
    """A darabok összerakása és a szokásos feldolgozás."""
    d = _upload_dir(upload_id)
    parts = [os.path.join(d, f"{i:05d}") for i in range(total)]
    missing = [i for i, p in enumerate(parts) if not os.path.exists(p)]
    if total <= 0 or missing:
        raise LibraryError(f"hiányzó darab: {missing[:5]}")
    size = sum(os.path.getsize(p) for p in parts)
    if size > MAX_BYTES:
        shutil.rmtree(d, ignore_errors=True)
        raise LibraryError(f"túl nagy fájl (legfeljebb {MAX_BYTES // (1024 * 1024)} MB)")
    joined = os.path.join(d, "joined")
    try:
        with open(joined, "wb") as out:      # darabonként fűzzük össze, a lemezen
            for p in parts:
                with open(p, "rb") as f:
                    shutil.copyfileobj(f, out, 1024 * 1024)
        return store_file(joined, content_type, name, note)
    finally:
        shutil.rmtree(d, ignore_errors=True)
