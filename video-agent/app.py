"""AXIMBRA videós agent — önálló szolgáltatás, saját felülettel.

Egy felhasználó, egy jelszó (ADMIN_PASSWORD, HTTP Basic). Egyszerre egy
videó készül: a renderelés sok processzort visz, két párhuzamos munka
mindkettőt lelassítaná.
"""
import hashlib
import hmac
import logging
import os
import re
import secrets
import threading
import time
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from pydantic import BaseModel, Field

import imagegen
import llm
import media
import publisher
import settings as settings_store
import stop
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
        self.cancelled = False
        self.started = self.finished = None

    def start(self, fn) -> bool:
        with self.lock:
            if self.running:
                return False
            stop.reset()
            self.running, self.log, self.error, self.cancelled = True, [], "", False
            self.started, self.finished = datetime.now(TZ).isoformat(timespec="seconds"), None

        def say(msg: str):
            # Minden naplósor egyben megállási pont is.
            stop.check()
            logger.info(msg)
            self.log.append(msg)

        def target():
            try:
                fn(say)
            except stop.Cancelled:
                self.cancelled = True
                self.log.append("Leállítva. A félkész darabot töröltem.")
                logger.info("a gyártást leállították")
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

    def stop(self) -> bool:
        with self.lock:
            if not self.running:
                return False
            stop.request()
            self.log.append("Leállítás kérve — az éppen futó lépés végén megáll…")
            return True

    def state(self):
        return {"running": self.running, "log": self.log[-50:], "error": self.error,
                "started": self.started, "finished": self.finished,
                "stopping": self.running and stop.requested(), "cancelled": self.cancelled}


job = Job()


@app.post("/api/job/stop", dependencies=[Depends(auth)])
def job_stop():
    if not job.stop():
        raise HTTPException(409, "Nem fut semmi.")
    return {"ok": True}


def _start(fn):
    if not job.start(fn):
        raise HTTPException(409, "Már készül egy videó, várd meg.")
    return {"ok": True}


# ---- nyilvános videócím -----------------------------------------------------
# Az Instagram a saját szerverével tölti le a videót, ezért ez az egy útvonal
# jelszó nélkül elérhető. Aláírt, kitalálhatatlan jegy védi, és csak a kész
# videófájlt adja ki.

def _link_secret() -> str:
    return os.environ.get("PUBLIC_LINK_SECRET", "") or os.environ.get("ADMIN_PASSWORD", "")


def public_ticket(vid: str) -> str:
    return hmac.new(_link_secret().encode(), f"video:{vid}".encode(), hashlib.sha256).hexdigest()[:32]


def public_urls(meta: dict) -> list[str]:
    """A darab fájljainak nyilvános címe, sorrendben. Üres lista, ha nincs
    beállítva nyilvános cím — akkor Instagramra nem tudunk posztolni."""
    base = os.environ.get("PUBLIC_BASE_URL", "").strip().rstrip("/")
    vid = meta.get("id") or ""
    if not base or not vid:
        return []
    tick = public_ticket(vid)
    if (meta.get("form") or "video") == "video":
        return [f"{base}/p/{vid}/{tick}.mp4"]
    return [f"{base}/p/{vid}/{tick}/{n}.jpg" for n in range(1, len(meta.get("files") or []) + 1)]


def _public_ok(vid: str, ticket: str) -> bool:
    return bool(_link_secret()) and hmac.compare_digest(ticket, public_ticket(vid))


@app.get("/p/{vid}/{ticket}.mp4")
def public_video(vid: str, ticket: str):
    path = videomaker.video_path(vid)
    if not path or not _public_ok(vid, ticket):
        raise HTTPException(404, "Nincs ilyen videó.")
    return FileResponse(path, media_type="video/mp4")


@app.get("/p/{vid}/{ticket}/{n}.jpg")
def public_slide(vid: str, ticket: str, n: int):
    path = videomaker.asset_path(vid, n)
    if not path or not path.endswith(".jpg") or not _public_ok(vid, ticket):
        raise HTTPException(404, "Nincs ilyen kép.")
    return FileResponse(path, media_type="image/jpeg")


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
        "settings": settings_store.load(),
        "publish": publisher.status(),
        "config": {
            "ai": llm.available(),
            "ai_engine": llm.engine_name(),
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


class SettingsIn(BaseModel):
    auto: bool | None = None
    autopost: bool | None = None
    every_hours: int | None = None
    seconds: int | None = None
    max_posts_per_day: int | None = None
    aspect: str | None = None
    form: str | None = None
    lang: str | None = None
    voice: bool | None = None
    male: bool | None = None
    targets: list[str] | None = None
    briefs: list[str] | str | None = None


@app.post("/api/settings", dependencies=[Depends(auth)])
def settings_save(body: SettingsIn):
    values = settings_store.clean({k: v for k, v in body.model_dump().items() if v is not None})
    if values.get("autopost"):
        s = {**settings_store.load(), **values}
        live = publisher.enabled_targets()
        chosen = [t for t in (s.get("targets") or []) if t in live]
        if not chosen:
            raise HTTPException(409, "Előbb kösd be az Instagramot vagy a LinkedInt, és jelöld be, hova posztoljon.")
    return settings_store.save(values)


class PublishIn(BaseModel):
    targets: list[str] = Field(default_factory=list)
    caption: str = Field(default="", max_length=2900)


@app.post("/api/videos/{vid}/publish", dependencies=[Depends(auth)])
def video_publish(vid: str, body: PublishIn):
    meta = videomaker.get_meta(vid)
    if not meta:
        raise HTTPException(404, "Nincs ilyen videó.")
    if meta.get("form") == "logo":
        raise HTTPException(409, "A logóváltozatokat nem posztolom: töltsd le a kiválasztottat, és állítsd be profilképnek.")
    targets = [t for t in body.targets if t in publisher.enabled_targets()]
    if not targets:
        raise HTTPException(409, "Nincs bekötve platform. " + "; ".join(
            publisher.ig_missing() + publisher.li_missing()))
    return _start(lambda say: _post_video(vid, targets, body.caption or meta.get("post", ""), say))


# ---- automatika -------------------------------------------------------------

def _auto_round(say) -> dict:
    """Egy automatikus kör: a soron következő téma legyártása, és ha kérted,
    kiposztolása. A napi posztkeret és a bekötött platformok korlátoznak."""
    now = datetime.now(timezone.utc)
    s = settings_store.load()
    brief, nxt = settings_store.take_brief(s)
    if not brief:
        say("Automatika: nincs téma megadva.")
        return {}
    settings_store.save({"next_brief": nxt, "last_run": now.isoformat(timespec="seconds")})
    say(f"Automatika: {brief[:90]}")
    meta = videomaker.make(brief, s["seconds"], s["lang"], s["aspect"], s["voice"], s["male"],
                           research=False, form=s.get("form") or "auto", say=say)
    if not s.get("autopost"):
        say("Kész, de kiposztolni te posztolod ki.")
        return meta
    targets = [t for t in (s.get("targets") or []) if t in publisher.enabled_targets()]
    if not targets:
        say("Magától posztolás: nincs bekötve platform, a kész darab a listában marad.")
        return meta
    if settings_store.post_budget(now, s) <= 0:
        say("Magától posztolás: a mai keret betelt.")
        return meta
    _post_video(meta["id"], targets, meta.get("post", ""), say)
    settings_store.count_post(now, settings_store.load())
    return meta


def _scheduler():
    while True:
        try:
            s = settings_store.load()
            if settings_store.due(datetime.now(timezone.utc), s) and not job.running:
                job.start(_auto_round)
        except Exception:  # noqa: BLE001 — az ütemező sosem állhat le egy hibán
            logger.exception("ütemező hiba")
        time.sleep(60)


@app.on_event("startup")
def _startup():
    threading.Thread(target=_scheduler, daemon=True).start()


class VideoIn(BaseModel):
    brief: str = Field(min_length=8, max_length=4000)
    seconds: int = Field(default=30, ge=10, le=90)
    lang: str = Field(default="hu", pattern="^(hu|en)$")
    aspect: str = Field(default="9:16", pattern="^(9:16|4:5|1:1|16:9)$")
    voice: bool = True
    male: bool = False
    research: bool = False
    form: str = Field(default="auto", pattern="^(auto|video|image|carousel|logo)$")


class ReviseIn(BaseModel):
    feedback: str = Field(min_length=3, max_length=2000)


@app.post("/api/videos", dependencies=[Depends(auth)])
def video_make(body: VideoIn):
    return _start(lambda say: videomaker.make(body.brief, body.seconds, body.lang, body.aspect, body.voice,
                                              body.male, body.research, body.form, say=say))


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


def _post_video(vid: str, targets: list[str], caption: str, say) -> dict:
    """Egy kész videó kiposztolása a megadott helyekre. Ami elhasal, azt
    naplózzuk, de a többi platform attól még mehet."""
    meta = videomaker.get_meta(vid) or {}
    form = meta.get("form") or "video"
    n = len(meta.get("files") or []) or 1
    paths = [p for p in (videomaker.asset_path(vid, i) for i in range(1, n + 1)) if p]
    if not paths:
        raise RuntimeError("a fájl nem található")
    urls = public_urls(meta)
    out = {}
    try:
        for t in targets:
            try:
                say(f"{t}: feltöltés…")
                pid = publisher.publish(t, paths=paths, urls=urls, caption=caption,
                                        title=meta.get("title", ""), form=form)
                out[t] = pid
                say(f"{t}: kiposztolva ({pid}).")
            except publisher.PublishError as e:
                out[t] = f"hiba: {e}"
                say(f"{t}: nem sikerült — {e}")
    finally:
        # Leállításkor is rögzítjük, ami már kiment: különben újra kiposztolnád.
        if out:
            videomaker.mark_posted(vid, out)
    return out


def _slide(vid: str, n: int, ext: str, download: int):
    path = videomaker.asset_path(vid, n)
    if not path or not path.endswith("." + ext):
        raise HTTPException(404, "Nincs ilyen kép.")
    return FileResponse(path, media_type="image/png" if ext == "png" else "image/jpeg",
                        filename=f"aximbra-{vid}-{n}.{ext}" if download else None)


@app.get("/api/videos/{vid}/{n}.jpg", dependencies=[Depends(auth)])
def video_slide(vid: str, n: int, download: int = 0):
    return _slide(vid, n, "jpg", download)


@app.get("/api/videos/{vid}/{n}.png", dependencies=[Depends(auth)])
def video_slide_png(vid: str, n: int, download: int = 0):
    return _slide(vid, n, "png", download)


@app.get("/api/videos/{vid}/{n}.svg", dependencies=[Depends(auth)])
def video_vector(vid: str, n: int):
    # Az SVG a modell kódja (megtisztítva). Csak letöltésként adjuk ki, és
    # a CSP akkor se engedjen benne semmit futni, ha valaki megnyitja.
    path = videomaker.vector_path(vid, n)
    if not path:
        raise HTTPException(404, "Nincs ilyen logó.")
    return FileResponse(path, media_type="image/svg+xml", filename=f"aximbra-logo-{vid}-{n}.svg",
                        headers={"Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'",
                                 "X-Content-Type-Options": "nosniff"})


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
