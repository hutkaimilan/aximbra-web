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
import threading
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

MEDIA_DIR = os.environ.get("MEDIA_DIR", "/data/media")
# Egy telefonos képernyőfelvétel egy-két perc alatt is 100 MB fölé megy.
MAX_BYTES = 250 * 1024 * 1024
IMAGE_TYPES = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}
CLIP_TYPES = {"video/mp4": ".mp4", "video/quicktime": ".mov", "video/webm": ".webm"}
MAX_IMAGE_W = 1600
# Hosszabb felvétel is mehet (pl. egy agent végigkattintva): a rendező darabolja
# és gyorsítja, lásd a jelenetek "from" és "speed" mezőjét.
MAX_CLIP_SECONDS = 180
# Az elemzéshez kis másolat kell: a modell úgyis kb. másodpercenként egy
# képkockát néz, és a kérésben utazó fájl legfeljebb ~20 MB lehet.
ANALYSIS_MAX_BYTES = 18 * 1024 * 1024
PACES = ("wait", "action", "result")
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
            if m and (os.path.exists(os.path.join(MEDIA_DIR, m["file"]))
                      or (m.get("raw") and os.path.exists(os.path.join(MEDIA_DIR, m["raw"])))):
                out.append(m)
    return sorted(out, key=lambda m: m.get("created_at", ""), reverse=True)


def delete(mid: str) -> bool:
    m = get(mid)
    if not m:
        return False
    for p in (os.path.join(MEDIA_DIR, m["file"]), _meta_path(mid),
              *([os.path.join(MEDIA_DIR, m["raw"])] if m.get("raw") else [])):
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


def ready(m: dict | None) -> bool:
    """Használható-e videóban: a feltöltött klip csak az elmosás után az."""
    return bool(m) and m.get("status", "ready") == "ready"


def add_image(data: bytes, name: str, note: str = "", source: str = "upload", redact_pii: bool = False) -> dict:
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
    redacted, redact_v = None, None
    if redact_pii:
        import redact
        try:
            redacted = redact.redact_image(out)
            redact_v = redact.POLICY_VERSION
        except Exception as e:  # noqa: BLE001 — elmosás nélkül nem kerülhet a tárba
            os.remove(out)
            logger.warning("képelmosás hiba: %s", e)
            raise MediaError("a személyes adatok elmosása nem sikerült, a kép nem került a tárba") from e
    info = _probe(out)
    return _save(mid, {"id": mid, "kind": "image", "file": f"{mid}.jpg", "name": (name or "kép")[:80],
                       "note": note[:200], "source": source, "width": info.get("width"),
                       "height": info.get("height"), "redacted": redacted, "redact": bool(redact_pii),
                       "redact_v": redact_v,
                       "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds")})


def add_clip(data: bytes, name: str, note: str = "", redact_pii: bool = True) -> dict:
    """A feltöltött videó mentése; a többi a háttérben fut.

    Az átalakítás (néma, 720 px-es WebM), az elmosás és az elemzés egy hosszabb
    felvételnél perceket vesz igénybe. Ha a feltöltés erre várna, az iPhone
    böngészője kb. egy perc csend után „Load failed"-del feladja — élesben egy
    75 mp-es felvétel így nem jutott át. Ezért a kérés a fájl mentése után
    azonnal visszatér, és a klip „processing", amíg el nem készül."""
    if not data:
        raise MediaError("üres fájl")
    if len(data) > MAX_BYTES:
        raise MediaError("túl nagy fájl")
    mid = _new_id()
    os.makedirs(MEDIA_DIR, exist_ok=True)
    raw = f"{mid}.upload"
    with open(os.path.join(MEDIA_DIR, raw), "wb") as f:
        f.write(data)
    meta = {"id": mid, "kind": "clip", "file": f"{mid}.webm", "raw": raw, "name": (name or "klip")[:80],
            "note": note[:200], "source": "upload", "width": None, "height": None, "seconds": None,
            "segments": [], "status": "processing", "redact": bool(redact_pii), "redacted": None,
            "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    _save(mid, meta)
    _start_processing(mid)
    return meta


def _normalize_clip(mid: str, m: dict) -> dict:
    """A nyers feltöltésből néma WebM. Néma, mert a videó hangsávját a narráció
    adja; WebM, mert a fej nélküli Chromium azt biztosan dekódolja. 720 px elég:
    a videóban egy telefon képernyőjén vagy 540 px szélesen jelenik meg."""
    src = os.path.join(MEDIA_DIR, m["raw"])
    out = os.path.join(MEDIA_DIR, m["file"])
    r = _run(["-i", src, "-t", str(MAX_CLIP_SECONDS), "-an",
              "-vf", "scale='min(720,iw)':-2:flags=lanczos,fps=30",
              "-c:v", "libvpx-vp9", "-b:v", "0", "-crf", "36", "-deadline", "realtime",
              "-cpu-used", "8", "-row-mt", "1", out], timeout=900)
    if r.returncode != 0 or not os.path.exists(out) or os.path.getsize(out) == 0:
        raise MediaError("ezt a videót nem sikerült beolvasni")
    try:
        os.remove(src)          # az eredeti (elmosatlan) feltöltés nem marad meg
    except OSError:
        pass
    info = _probe(out)
    m = {**m, "width": info.get("width"), "height": info.get("height"), "seconds": info.get("seconds")}
    m.pop("raw", None)
    return _save(mid, m)


_busy: set = set()
_busy_lock = threading.Lock()


def _start_processing(mid: str) -> None:
    with _busy_lock:
        if mid in _busy:
            return
        _busy.add(mid)
    threading.Thread(target=_process_clip, args=(mid,), daemon=True).start()


def _process_clip(mid: str) -> None:
    """Elmosás (ha kérték), aztán a részek elemzése — az elmosott változaton,
    így a modell sem látja a személyes adatokat."""
    try:
        m = get(mid)
        if not m:
            return
        if m.get("raw"):
            try:
                m = _normalize_clip(mid, m)
            except Exception as e:  # noqa: BLE001
                logger.warning("klip-átalakítás hiba (%s): %s", mid, e)
                _save(mid, {**m, "status": "failed", "error": "Ezt a videót nem sikerült beolvasni."})
                return
        path = path_of(mid)
        if not path:
            return
        if m.get("redact"):
            import redact
            import time as _t
            t0 = _t.time()
            logger.info("klip elmosása indul: %s (%s mp)", mid, m.get("seconds"))
            try:
                m["redacted"] = redact.redact_clip(path)
                m["redact_v"] = redact.POLICY_VERSION
                logger.info("klip elmosva: %s — %s szöveg, %.0f mp alatt", mid, m["redacted"], _t.time() - t0)
            except Exception as e:  # noqa: BLE001 — elmosás nélkül nem használható
                logger.warning("klipelmosás hiba (%s): %s", mid, e)
                _save(mid, {**m, "status": "failed", "error": "A személyes adatok elmosása nem sikerült."})
                return
        m["segments"] = analyse_clip(path, m.get("seconds") or 0)
        _save(mid, {**m, "status": "ready"})
    finally:
        with _busy_lock:
            _busy.discard(mid)


def _needs_redaction(m: dict) -> bool:
    """Feltöltött anyag, ami nincs a mostani szabállyal elmosva: az elmosás
    előtt feltöltött (nincs "redact" mezője), vagy egy enyhébb szabállyal
    elmosott. Akinél a feltöltő kikapcsolta az elmosást, azt nem bántjuk."""
    import redact
    if m.get("source") != "upload":
        return False
    if "redact" not in m:
        return True
    return bool(m.get("redact")) and (m.get("redact_v") or 0) < redact.POLICY_VERSION


def _process_image(mid: str) -> None:
    try:
        m, path = get(mid), path_of(mid)
        if not m or not path:
            return
        import redact
        try:
            m["redacted"] = redact.redact_image(path)
            _save(mid, {**m, "redact": True, "redact_v": redact.POLICY_VERSION, "status": "ready"})
        except Exception as e:  # noqa: BLE001
            logger.warning("képelmosás hiba (%s): %s", mid, e)
            _save(mid, {**m, "redact": True, "status": "failed", "error": "A személyes adatok elmosása nem sikerült."})
    finally:
        with _busy_lock:
            _busy.discard(mid)


def resume_pending() -> int:
    """Újraindulás után: a félbemaradt feldolgozások folytatása, és a még nem
    (vagy enyhébb szabállyal) elmosott feltöltések újra átnézése. Addig ezek
    sem kerülhetnek videóba ("processing")."""
    todo = []
    for m in listing():
        if m.get("status") == "processing" or _needs_redaction(m):
            _save(m["id"], {**m, "status": "processing", "redact": True})
            todo.append(m)
    for m in todo:
        if m.get("kind") == "clip":
            _start_processing(m["id"])
        else:
            with _busy_lock:
                if m["id"] in _busy:
                    continue
                _busy.add(m["id"])
            threading.Thread(target=_process_image, args=(m["id"],), daemon=True).start()
    return len(todo)


ANALYSIS_PROMPT = """This is a screen recording ({seconds:.0f} s) that will be edited into a short social video.
Split it into consecutive segments covering the whole recording, in order, and for each say what is on screen
and its pace:
- "wait": loading, a spinner, an empty or unchanged screen, a consent or login screen, the user hesitating;
- "action": typing, scrolling, tapping, moving between screens — something happens but nothing to read yet;
- "result": the moment something worth reading appears or changes (a sorted list, a label, an answer, a
  confirmation) — the viewer must be able to read it.
A Google sign-in, account-chooser or "unverified app" warning screen is "action" (it shows the demo is real), not "wait".
Segments are 1–15 s long; "from" and "to" are seconds from the start. Describe in Hungarian, max 12 words each.
"screen_text": the main interface text the viewer would need to read in that segment (a warning, a button, a
heading), copied in its original language, max 15 words, or "" if none; "screen_lang": its language code (hu, en…).
Some parts are already blurred; never write down personal data (names, email addresses, phone numbers).
Answer ONLY with JSON: {{"segments": [{{"from": 0, "to": 6, "what": "...", "pace": "wait|action|result",
"screen_text": "", "screen_lang": ""}}]}}"""


def _clean_segments(raw, total: float) -> list[dict]:
    segs = []
    for x in raw if isinstance(raw, list) else []:
        if not isinstance(x, dict):
            continue
        try:
            a, b = float(x.get("from")), float(x.get("to"))
        except (TypeError, ValueError):
            continue
        a, b = max(0.0, a), min(total or b, b)
        if b - a < 0.5:
            continue
        pace = x.get("pace") if x.get("pace") in PACES else "action"
        lang = str(x.get("screen_lang") or "").strip().lower()[:5]
        segs.append({"from": round(a, 1), "to": round(b, 1), "what": str(x.get("what") or "")[:90], "pace": pace,
                     "screen_text": str(x.get("screen_text") or "")[:140], "screen_lang": lang})
    segs.sort(key=lambda s: s["from"])
    return segs[:40]


def analyse_clip(path: str, seconds: float) -> list[dict]:
    """A felvétel részei időbélyeggel: mi látszik, és várakozás, mozgás vagy
    eredmény-e. Ebből tudja a rendező, hol gyorsítson és hol ne. Ha az
    elemzés nem sikerül, üres lista: a klip attól még használható."""
    import llm
    try:
        with tempfile.TemporaryDirectory() as d:
            small = os.path.join(d, "a.webm")
            r = _run(["-i", path, "-an", "-vf", "scale=360:-2,fps=2", "-c:v", "libvpx-vp9", "-b:v", "0",
                      "-crf", "45", "-deadline", "realtime", "-cpu-used", "8", small], timeout=300)
            if r.returncode != 0 or not os.path.exists(small) or os.path.getsize(small) > ANALYSIS_MAX_BYTES:
                return []
            with open(small, "rb") as f:
                data = f.read()
        raw = llm.extract_json(llm.ask_about_media(ANALYSIS_PROMPT.format(seconds=seconds or 0), data, "video/webm"))
        return _clean_segments((raw or {}).get("segments") if isinstance(raw, dict) else raw, seconds or 0)
    except Exception as e:  # noqa: BLE001 — az elemzés nélkül is megmarad a klip
        logger.warning("klipelemzés kimaradt: %s", e)
        return []


def store(data: bytes, content_type: str, name: str, note: str = "", redact_pii: bool = True) -> dict:
    ct = (content_type or "").split(";")[0].strip().lower()
    if ct in IMAGE_TYPES:
        return add_image(data, name, note, redact_pii=redact_pii)
    if ct in CLIP_TYPES:
        return add_clip(data, name, note, redact_pii=redact_pii)
    raise MediaError("csak kép (JPG, PNG, WebP) vagy videó (MP4, MOV, WebM) tölthető fel")


def copy_out(mid: str, dest_dir: str) -> str | None:
    """A médiafájl másolata a renderelés melletti mappába."""
    p = path_of(mid)
    if not p:
        return None
    dest = os.path.join(dest_dir, os.path.basename(p))
    shutil.copyfile(p, dest)
    return dest
