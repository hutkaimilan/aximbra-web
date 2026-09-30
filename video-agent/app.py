"""AXIMBRA videós agent — önálló szolgáltatás, saját felülettel.

Egy felhasználó, egy jelszó (ADMIN_PASSWORD, HTTP Basic). Egyszerre egy
videó készül: a renderelés sok processzort visz, két párhuzamos munka
mindkettőt lelassítaná.
"""
import logging
import os
import re
import secrets
import threading
import time
from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from pydantic import BaseModel, Field

import imagegen
import media
import videomaker
import websearch

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("video")

app = FastAPI(title="AXIMBRA videós agent", docs_url=None, redoc_url=None, openapi_url=None)
security = HTTPBasic()
HERE = os.path.dirname(os.path.abspath(__file__))
TZ = ZoneInfo("Europe/Budapest")


def auth(creds: HTTPBasicCredentials = Depends(security)):
    pw = os.environ.get("ADMIN_PASSWORD", "")
    if len(pw) < 8:
        raise HTTPException(503, "Nincs beállítva elég hosszú ADMIN_PASSWORD.")
    if not secrets.compare_digest(creds.password.encode(), pw.encode()):
        time.sleep(1)  # a jelszópróbálgatás lassítása
        raise HTTPException(401, "Hibás jelszó.", headers={"WWW-Authenticate": "Basic"})


class Job:
    def __init__(self):
        self.lock = threading.Lock()
        self.running = False
        self.log: list[str] = []
        self.error = ""
        self.started = self.finished = None

    def start(self, fn) -> bool:
        with self.lock:
            if self.running:
                return False
            self.running, self.log, self.error = True, [], ""
            self.started, self.finished = datetime.now(TZ).isoformat(timespec="seconds"), None

        def say(msg: str):
            logger.info(msg)
            self.log.append(msg)

        def target():
            try:
                fn(say)
            except Exception as e:  # noqa: BLE001 — a hiba a felületen jelenjen meg, ne tűnjön el
                logger.exception("videó hiba")
                msg = "Elfogyott a mai ingyenes AI-keret, holnap újra megy." if "insufficient_quota" in str(e) else str(e)
                self.error = msg
                say(f"Hiba: {msg}")
            finally:
                with self.lock:
                    self.running = False
                    self.finished = datetime.now(TZ).isoformat(timespec="seconds")

        threading.Thread(target=target, daemon=True).start()
        return True

    def state(self):
        return {"running": self.running, "log": self.log[-50:], "error": self.error,
                "started": self.started, "finished": self.finished}


job = Job()


def _start(fn):
    if not job.start(fn):
        raise HTTPException(409, "Már készül egy videó, várd meg.")
    return {"ok": True}


@app.get("/health")
def health():
    return {"ok": True}


@app.get("/", dependencies=[Depends(auth)])
def index():
    return FileResponse(os.path.join(HERE, "static", "index.html"))


@app.get("/api/state", dependencies=[Depends(auth)])
def state():
    return {
        "job": job.state(),
        "videos": videomaker.list_videos(),
        "media": media.listing(),
        "topics": videomaker.TOPICS,
        "config": {
            "ai": bool(os.environ.get("GEMINI_API_KEY") or os.environ.get("OPENAI_API_KEY")),
            "web_search": websearch.tavily_on(),
            "elevenlabs": bool(os.environ.get("ELEVENLABS_API_KEY") and os.environ.get("ELEVENLABS_VOICE_ID")),
            "imagegen": imagegen.available(),
            "imagegen_engine": imagegen.engine(),
        },
    }


@app.post("/api/media", dependencies=[Depends(auth)])
async def media_add(file: UploadFile = File(...), note: str = Form("")):
    data = await file.read(media.MAX_BYTES + 1)
    if len(data) > media.MAX_BYTES:
        raise HTTPException(413, "Túl nagy fájl (legfeljebb 60 MB).")
    try:
        return media.store(data, file.content_type or "", file.filename or "", note.strip()[:200])
    except media.MediaError as e:
        raise HTTPException(400, str(e))


@app.get("/api/media/{mid}", dependencies=[Depends(auth)])
def media_file(mid: str):
    path = media.path_of(mid)
    if not path:
        raise HTTPException(404, "Nincs ilyen fájl.")
    kind = "video/webm" if path.endswith(".webm") else "image/jpeg"
    return FileResponse(path, media_type=kind)


@app.post("/api/media/{mid}/delete", dependencies=[Depends(auth)])
def media_delete(mid: str):
    if not media.delete(mid):
        raise HTTPException(404, "Nincs ilyen fájl.")
    return {"ok": True}


class VideoIn(BaseModel):
    brief: str = Field(min_length=8, max_length=4000)
    seconds: int = Field(default=30, ge=10, le=90)
    lang: str = Field(default="hu", pattern="^(hu|en)$")
    aspect: str = Field(default="9:16", pattern="^(9:16|1:1|16:9)$")
    voice: bool = True
    male: bool = False
    research: bool = False


class ReviseIn(BaseModel):
    feedback: str = Field(min_length=3, max_length=2000)


@app.post("/api/videos", dependencies=[Depends(auth)])
def video_make(body: VideoIn):
    return _start(lambda say: videomaker.make(body.brief, body.seconds, body.lang, body.aspect, body.voice,
                                              body.male, body.research, say=say))


@app.post("/api/videos/{vid}/revise", dependencies=[Depends(auth)])
def video_revise(vid: str, body: ReviseIn):
    if not videomaker.get_meta(vid):
        raise HTTPException(404, "Nincs ilyen videó.")
    return _start(lambda say: videomaker.revise(vid, body.feedback, say=say))


@app.post("/api/videos/{vid}/delete", dependencies=[Depends(auth)])
def video_delete(vid: str):
    if not videomaker.delete(vid):
        raise HTTPException(404, "Nincs ilyen videó.")
    return {"ok": True}


@app.get("/api/videos/{vid}.mp4", dependencies=[Depends(auth)])
def video_file(vid: str, download: int = 0, range: str = Header(default="")):
    path = videomaker.video_path(vid)
    if not path:
        raise HTTPException(404, "Nincs ilyen videó.")
    if download:
        return FileResponse(path, media_type="video/mp4", filename=f"aximbra-{vid}.mp4")
    # Az iPhone Safari csak bájttartomány-kéréssel játszik le videót.
    size = os.path.getsize(path)
    m = re.fullmatch(r"bytes=(\d*)-(\d*)", range.strip())
    if not m or (not m.group(1) and not m.group(2)):
        return FileResponse(path, media_type="video/mp4", headers={"Accept-Ranges": "bytes"})
    if m.group(1):
        start, end = int(m.group(1)), int(m.group(2)) if m.group(2) else size - 1
    else:
        start, end = max(0, size - int(m.group(2))), size - 1
    end = min(end, size - 1, start + 8 * 1024 * 1024 - 1)
    if start > end:
        raise HTTPException(416, "Érvénytelen tartomány.", headers={"Content-Range": f"bytes */{size}"})
    with open(path, "rb") as f:
        f.seek(start)
        data = f.read(end - start + 1)
    return Response(data, status_code=206, media_type="video/mp4",
                    headers={"Content-Range": f"bytes {start}-{end}/{size}", "Accept-Ranges": "bytes"})
