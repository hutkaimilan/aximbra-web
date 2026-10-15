"""AXIMBRA Reels-agent — 1. szakasz: feltöltés és médiatár.

Önálló szolgáltatás, saját kötettel és címmel; a régi aximbra-video-hoz nem
nyúl. Ebben a szakaszban egyetlen dolga van: a telefonról BÁRMENNYI fotó és
videó biztosan feljusson, és látszódjon, pontosan mi történt a telefonon.
A videógyártás a következő szakaszban épül rá.

Egy felhasználó, egy jelszó (ADMIN_PASSWORD, HTTP Basic).
"""
from __future__ import annotations

import asyncio
import logging
import os
import secrets
import threading
import time
from collections import deque
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from pydantic import BaseModel, Field

import icloud_album
import library

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("reels")

@asynccontextmanager
async def lifespan(_app: FastAPI):
    os.makedirs(library.MEDIA_DIR, exist_ok=True)
    say(f"indulás — tár: {library.MEDIA_DIR}, {library.stats()['count']} elem, "
        f"max {library.MAX_BYTES // 1048576} MB/fájl, {library.CLIP_WORKERS} párhuzamos átalakítás")
    n = library.resume_pending()
    if n:
        say(f"félbemaradt átalakítás folytatása: {n} db")
    yield


app = FastAPI(title="AXIMBRA Reels-agent", docs_url=None, redoc_url=None, openapi_url=None,
              lifespan=lifespan)
security = HTTPBasic()
HERE = os.path.dirname(os.path.abspath(__file__))
STARTED = time.time()
# Egyben csak kis fájlt veszünk át: a nagy a darabolt úton megy, különben a
# teljes videó a memóriába kerülne.
SINGLE_SHOT_MAX = 32 * 1024 * 1024


def auth(creds: HTTPBasicCredentials = Depends(security)):
    pw = os.environ.get("ADMIN_PASSWORD", "")
    if len(pw) < 8:
        raise HTTPException(503, "Nincs beállítva elég hosszú ADMIN_PASSWORD.")
    if not secrets.compare_digest(creds.password.encode(), pw.encode()):
        time.sleep(1)  # a jelszópróbálgatás lassítása
        raise HTTPException(401, "Hibás jelszó.", headers={"WWW-Authenticate": "Basic"})


# ---- napló: a telefon lépései és a szerver munkái -------------------------
# Az első perctől látni akarjuk, mit adott át a telefon, és hol akadt el.
# A felület fetch-csel küldi (nem sendBeacon: az nem viszi a Basic jelszót).

_log: deque = deque(maxlen=400)
_log_lock = threading.Lock()


def say(msg: str, who: str = "szerver") -> None:
    line = {"at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "who": who,
            "msg": str(msg)[:1000]}
    with _log_lock:
        _log.append(line)
    logger.info("[%s] %s", who, line["msg"])


def log_lines(limit: int = 200) -> list[dict]:
    with _log_lock:
        return list(_log)[-limit:]


class ClientLog(BaseModel):
    msg: str = Field(default="", max_length=2000)
    ua: str = Field(default="", max_length=300)


@app.post("/api/clientlog", dependencies=[Depends(auth)])
def client_log(body: ClientLog):
    """A telefon üzenetei: mit adott át a választó, és milyen JS-hiba történt."""
    say(body.msg.replace("\n", " ")[:1000], who="telefon")
    return {"ok": True}


# ---- album-behúzás a háttérben --------------------------------------------
# Egy 60-100 elemes album letöltése jóval több, mint a Railway 5 perces
# kéréskorlátja, ezért külön szálon fut, és a felület a naplóból követi.

class _Job:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.running = False
        self.what = ""
        self.result: dict | None = None
        self.error = ""

    def start(self, what: str, fn) -> bool:
        with self.lock:
            if self.running:
                return False
            self.running, self.what, self.result, self.error = True, what, None, ""

        def target():
            try:
                self.result = fn()
            except Exception as e:  # noqa: BLE001 — a hiba a felületen jelenjen meg
                self.error = str(e)[:400]
                say(f"Hiba: {self.error}")
                logger.exception("háttérmunka hiba")
            finally:
                with self.lock:
                    self.running = False

        threading.Thread(target=target, daemon=True).start()
        return True

    def state(self) -> dict:
        return {"running": self.running, "what": self.what, "error": self.error,
                "result": self.result}


job = _Job()


class AlbumIn(BaseModel):
    url: str = Field(max_length=500)
    note: str = Field(default="", max_length=400)


@app.post("/api/album", dependencies=[Depends(auth)])
def album_add(body: AlbumIn):
    """Megosztott iCloud-album: a szerver tölti le az összes képet és videót."""
    try:
        icloud_album.token_of(body.url)
    except icloud_album.AlbumError as e:
        raise HTTPException(400, str(e))
    tag = (body.note or "").strip() or "iCloud-album " + secrets.token_hex(3)
    if not job.start("album", lambda: icloud_album.run(body.url, tag, say)):
        raise HTTPException(409, "Már fut egy album-behúzás, várd meg.")
    return {"ok": True, "tag": tag}


# ---- feltöltés -------------------------------------------------------------

@app.post("/api/upload", dependencies=[Depends(auth)])
async def upload(file: UploadFile = File(...), note: str = Form(""), client_info: str = Form("")):
    """Egy fájl egészben (kis kép). A nagy fájl darabokban jön, lentebb."""
    cap = min(library.MAX_BYTES, SINGLE_SHOT_MAX)
    data = await file.read(cap + 1)
    if len(data) > cap:
        raise HTTPException(413, f"Ez a végpont legfeljebb {cap // 1048576} MB-ot vesz át — "
                                 "a nagyobbat darabokban kell küldeni (/api/upload/chunk).")
    say(f"feltöltés: {file.filename!r} ({file.content_type or 'típus nélkül'}, "
        f"{len(data) / 1048576:.2f} MB){(' · ' + client_info[:200]) if client_info else ''}")
    try:
        m = await asyncio.to_thread(library.store, data, file.content_type or "",
                                    file.filename or "", note.strip()[:400])
    except library.LibraryError as e:
        say(f"feltöltés ELHASALT: {file.filename!r} — {e}")
        raise HTTPException(400, str(e))
    say(f"felvéve: {m['id']} {m['kind']} ({m['status']}) — {m['name']}")
    return m


@app.post("/api/upload/chunk", dependencies=[Depends(auth)])
async def upload_chunk(file: UploadFile = File(...), upload_id: str = Form(...),
                       index: int = Form(...), total: int = Form(...)):
    data = await file.read(library.CHUNK_MAX + 1)
    try:
        out = await asyncio.to_thread(library.save_chunk, upload_id, index, total, data)
    except library.LibraryError as e:
        raise HTTPException(400, str(e))
    if index == 0 or index + 1 == total:
        say(f"darab {index + 1}/{total} megérkezett ({len(data) / 1048576:.2f} MB)")
    return out


@app.post("/api/upload/done", dependencies=[Depends(auth)])
async def upload_done(upload_id: str = Form(...), total: int = Form(...), name: str = Form(""),
                      content_type: str = Form(""), note: str = Form("")):
    say(f"darabok összerakása: {name!r} ({content_type or 'típus nélkül'}, {total} darab)")
    try:
        m = await asyncio.to_thread(library.finish_chunks, upload_id, total, content_type,
                                    name[:200], note.strip()[:400])
    except library.LibraryError as e:
        say(f"összerakás ELHASALT: {name!r} — {e}")
        raise HTTPException(400, str(e))
    say(f"felvéve: {m['id']} {m['kind']} ({m['status']}) — {m['name']}")
    return m


# ---- a tár -----------------------------------------------------------------

@app.get("/api/state", dependencies=[Depends(auth)])
def state(log: int = 120):
    return {"media": library.listing(), "stats": library.stats(), "job": job.state(),
            "log": log_lines(max(0, min(400, log))),
            "limits": {"max_mb": library.MAX_BYTES // 1048576, "chunk_mb": 4,
                       "clip_workers": library.CLIP_WORKERS, "keep": library.KEEP},
            "queue": library.queue_depth(),
            "uptime_s": round(time.time() - STARTED)}


@app.get("/api/media/{mid}", dependencies=[Depends(auth)])
def media_file(mid: str):
    path = library.path_of(mid)
    if not path:
        raise HTTPException(404, "Nincs ilyen fájl.")
    kind = "video/mp4" if path.endswith(".mp4") else "image/jpeg"
    return FileResponse(path, media_type=kind)


@app.get("/api/media/{mid}/poster.jpg", dependencies=[Depends(auth)])
def media_poster(mid: str):
    path = library.path_of(mid, "poster")
    if not path:
        raise HTTPException(404, "Nincs előnézet.")
    return FileResponse(path, media_type="image/jpeg")


class NoteIn(BaseModel):
    note: str = Field(default="", max_length=400)


@app.post("/api/media/{mid}/note", dependencies=[Depends(auth)])
def media_note(mid: str, body: NoteIn):
    """Elemhez tartozó rendezői utasítás (a következő szakasz használja)."""
    m = library.set_note(mid, body.note)
    if not m:
        raise HTTPException(404, "Nincs ilyen fájl.")
    return m


@app.post("/api/media/{mid}/retry", dependencies=[Depends(auth)])
def media_retry(mid: str):
    if not library.retry(mid):
        raise HTTPException(409, "Ezt nem lehet újraindítani (a nyers fájl már nincs meg).")
    say(f"újraindítva: {mid}")
    return {"ok": True}


@app.post("/api/media/{mid}/delete", dependencies=[Depends(auth)])
def media_delete(mid: str):
    if not library.delete(mid):
        raise HTTPException(404, "Nincs ilyen fájl.")
    say(f"törölve: {mid}")
    return {"ok": True}


@app.get("/health")
def health():
    return {"ok": True, "phase": "upload", "items": library.stats()["count"]}


@app.get("/", dependencies=[Depends(auth)])
def index():
    return FileResponse(os.path.join(HERE, "static", "index.html"))


@app.exception_handler(Exception)
async def unhandled(request: Request, exc: Exception):
    """Minden váratlan hiba a naplóba is, ne csak az 500-as válaszba."""
    logger.exception("kezeletlen hiba: %s", request.url.path)
    say(f"kezeletlen hiba {request.url.path}: {type(exc).__name__}: {str(exc)[:200]}")
    return JSONResponse({"detail": "Váratlan hiba — a naplóban megtalálod."}, status_code=500)


