"""A végpontok: jelszó, feltöltés (egyben és darabokban), HEIC, telefonos napló."""
import io
import os
import subprocess
import sys
import time

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import library  # noqa: E402

PW = "nagyon-hosszu-jelszo"
AUTH = ("admin", PW)


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("ADMIN_PASSWORD", PW)
    monkeypatch.setattr(library, "MEDIA_DIR", str(tmp_path / "media"))
    import app as app_module
    with TestClient(app_module.app, raise_server_exceptions=False) as c:
        yield c


def _jpeg(w=800, h=600, noisy=False) -> bytes:
    from PIL import Image
    out = io.BytesIO()
    if noisy:   # zajos kép: nem tömörödik pár kB-ra, így valóban több darab lesz
        img = Image.frombytes("RGB", (w, h), os.urandom(w * h * 3))
    else:
        img = Image.new("RGB", (w, h), (30, 90, 200))
    img.save(out, "JPEG", quality=95)
    return out.getvalue()


def _heic(w=800, h=600) -> bytes:
    """Igazi HEIC — ezt küldi az iPhone, és eddig ez nem volt feltölthető."""
    from PIL import Image
    import pillow_heif
    pillow_heif.register_heif_opener()
    out = io.BytesIO()
    Image.new("RGB", (w, h), (200, 120, 40)).save(out, "HEIF", quality=70)
    return out.getvalue()


def _mov(tmp, seconds=2) -> bytes:
    p = os.path.join(tmp, "in.mov")
    subprocess.run([library._ffmpeg(), "-hide_banner", "-loglevel", "error", "-y",
                    "-f", "lavfi", "-i", f"testsrc=size=720x1280:rate=30:duration={seconds}",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", p],
                   check=True, capture_output=True, timeout=180)
    with open(p, "rb") as f:
        return f.read()


def _wait_ready(client, mid, timeout=180):
    t0 = time.time()
    while time.time() - t0 < timeout:
        m = library.get(mid)
        if m and m["status"] in ("ready", "failed"):
            return m
        time.sleep(0.4)
    raise AssertionError("nem készült el")


# ---- jelszó ----------------------------------------------------------------

def test_health_needs_no_password(client):
    r = client.get("/health")
    assert r.status_code == 200 and r.json()["ok"] is True


def test_panel_and_api_need_the_password(client):
    assert client.get("/").status_code == 401
    assert client.get("/api/state").status_code == 401
    assert client.post("/api/clientlog", json={"msg": "x"}).status_code == 401
    assert client.get("/", auth=("a", "rossz")).status_code == 401
    assert client.get("/", auth=AUTH).status_code == 200


def test_panel_leads_with_the_photo_picker(client):
    """Amit kértél: egy gomb → Fotótár → kijelölés. Nem album-behúzogatás."""
    html = client.get("/", auth=AUTH).text
    assert "Fotó feltöltése" in html
    # Az albumos út csak vészkijárat, összecsukva a lap alján.
    assert html.index("Fotó feltöltése") < html.index("Vészkijárat")


def test_panel_has_no_accept_on_the_file_inputs(client):
    """iPhone-on a pontos accept lista kiszürkíti a HEIC-et és a videókat."""
    html = client.get("/", auth=AUTH).text
    inputs = [ln for ln in html.splitlines() if 'type="file"' in ln]
    assert len(inputs) == 2, inputs
    assert not any("accept" in ln for ln in inputs)
    # A naplózás fetch-csel megy, nem beacon-nel (az nem viszi a jelszót).
    assert "navigator.sendBeacon" not in html and "/api/clientlog" in html


# ---- feltöltés egyben ------------------------------------------------------

def test_jpeg_upload(client):
    r = client.post("/api/upload", auth=AUTH, files={"file": ("IMG_1.jpg", _jpeg(), "image/jpeg")},
                    data={"note": "nyitókép"})
    assert r.status_code == 200, r.text
    m = r.json()
    assert m["kind"] == "image" and m["status"] == "ready" and m["note"] == "nyitókép"
    assert client.get(f"/api/media/{m['id']}", auth=AUTH).status_code == 200
    assert client.get(f"/api/media/{m['id']}/poster.jpg", auth=AUTH).status_code == 200


def test_heic_upload_from_iphone(client):
    """A HEIC-fotót a szerver alakítja át — a telefonnak nem kell."""
    r = client.post("/api/upload", auth=AUTH,
                    files={"file": ("IMG_2.HEIC", _heic(), "image/heic")})
    assert r.status_code == 200, r.text
    m = r.json()
    assert m["status"] == "ready" and m["width"] == 800
    assert library.path_of(m["id"]).endswith(".jpg")


def test_upload_with_no_content_type_still_works(client):
    """A böngésző néha semmit nem mond a típusról."""
    r = client.post("/api/upload", auth=AUTH,
                    files={"file": ("IMG_3", _jpeg(), "application/octet-stream")})
    assert r.status_code == 200 and r.json()["kind"] == "image"


def test_mov_upload_returns_at_once(client, tmp_path):
    r = client.post("/api/upload", auth=AUTH,
                    files={"file": ("IMG_4.MOV", _mov(str(tmp_path)), "video/quicktime")})
    assert r.status_code == 200, r.text
    m = r.json()
    assert m["kind"] == "clip" and m["status"] == "processing", "a kérés nem várja meg az átalakítást"
    done = _wait_ready(client, m["id"])
    assert done["status"] == "ready" and done["height"] > done["width"]
    assert client.get(f"/api/media/{m['id']}/poster.jpg", auth=AUTH).status_code == 200


def test_a_document_is_refused_with_a_clear_message(client):
    r = client.post("/api/upload", auth=AUTH,
                    files={"file": ("szamla.pdf", b"%PDF-1.4 x", "application/pdf")})
    assert r.status_code == 400 and "nem kép vagy videó" in r.json()["detail"]


def test_oversized_upload_is_refused(client, monkeypatch):
    monkeypatch.setattr(library, "MAX_BYTES", 1024)
    r = client.post("/api/upload", auth=AUTH, files={"file": ("a.jpg", _jpeg(), "image/jpeg")})
    assert r.status_code == 413


# ---- feltöltés darabokban --------------------------------------------------

def test_chunked_upload_through_http(client):
    data = _jpeg(900, 700, noisy=True)
    uid = "f" * 32
    parts = [data[i:i + 40000] for i in range(0, len(data), 40000)]
    assert len(parts) > 2
    for i, p in enumerate(parts):
        r = client.post("/api/upload/chunk", auth=AUTH, files={"file": ("part", p)},
                        data={"upload_id": uid, "index": i, "total": len(parts)})
        assert r.status_code == 200 and r.json()["have"] == i + 1
    r = client.post("/api/upload/done", auth=AUTH,
                    data={"upload_id": uid, "total": len(parts), "name": "nagy.jpg",
                          "content_type": "image/jpeg", "note": "darabolva"})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "ready" and r.json()["note"] == "darabolva"


def test_missing_chunk_is_a_400_not_a_500(client):
    uid = "e" * 32
    client.post("/api/upload/chunk", auth=AUTH, files={"file": ("part", b"x")},
                data={"upload_id": uid, "index": 0, "total": 2})
    r = client.post("/api/upload/done", auth=AUTH,
                    data={"upload_id": uid, "total": 2, "name": "a.jpg", "content_type": "image/jpeg"})
    assert r.status_code == 400 and "hiányzó darab" in r.json()["detail"]


# ---- napló, állapot, tár ---------------------------------------------------

def test_phone_log_lands_in_the_state(client):
    client.post("/api/clientlog", auth=AUTH,
                json={"msg": "VÁLASZTÓ (fotóválasztó): 22 fájl átadva"})
    s = client.get("/api/state", auth=AUTH).json()
    line = [l for l in s["log"] if l["who"] == "telefon"]
    assert line and "22 fájl" in line[-1]["msg"]


def test_upload_steps_are_logged(client):
    client.post("/api/upload", auth=AUTH, files={"file": ("IMG_7.jpg", _jpeg(), "image/jpeg")})
    msgs = " | ".join(l["msg"] for l in client.get("/api/state", auth=AUTH).json()["log"])
    assert "IMG_7.jpg" in msgs and "felvéve" in msgs


def test_state_reports_the_library(client):
    client.post("/api/upload", auth=AUTH, files={"file": ("a.jpg", _jpeg(), "image/jpeg")})
    s = client.get("/api/state", auth=AUTH).json()
    assert s["stats"]["count"] == 1 and s["stats"]["images"] == 1
    assert s["limits"]["clip_workers"] == library.CLIP_WORKERS
    assert len(s["media"]) == 1


def test_note_and_delete(client):
    mid = client.post("/api/upload", auth=AUTH,
                      files={"file": ("a.jpg", _jpeg(), "image/jpeg")}).json()["id"]
    r = client.post(f"/api/media/{mid}/note", auth=AUTH, json={"note": "csak a 3. mp-től"})
    assert r.status_code == 200 and r.json()["note"] == "csak a 3. mp-től"
    assert client.post(f"/api/media/{mid}/delete", auth=AUTH).status_code == 200
    assert client.get(f"/api/media/{mid}", auth=AUTH).status_code == 404
    assert client.post(f"/api/media/{mid}/note", auth=AUTH, json={"note": "x"}).status_code == 404


def test_album_rejects_a_wrong_link(client):
    r = client.post("/api/album", auth=AUTH, json={"url": "https://example.com/x"})
    assert r.status_code == 400 and "megosztott iCloud-album" in r.json()["detail"]


def test_album_starts_in_the_background(client, monkeypatch):
    import icloud_album
    seen = {}
    monkeypatch.setattr(icloud_album, "run",
                        lambda url, tag, say, **kw: seen.update(url=url, tag=tag) or {"album": "x",
                                                                                      "ids": [], "failed": [],
                                                                                      "total": 0})
    r = client.post("/api/album", auth=AUTH,
                    json={"url": "https://www.icloud.com/sharedalbum/#B0abcdefghij"})
    assert r.status_code == 200 and r.json()["tag"]
    for _ in range(50):
        if seen:
            break
        time.sleep(0.05)
    assert seen["url"].endswith("B0abcdefghij")


def test_path_traversal_on_media_ids(client):
    for bad in ("..", "%2e%2e", "ab"):
        assert client.get(f"/api/media/{bad}", auth=AUTH).status_code in (404, 400)
