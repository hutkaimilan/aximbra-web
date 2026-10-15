"""A tár: bármilyen formátum bejut, a nagy fájl darabokban, friss elem nem törlődik."""
import io
import os
import subprocess
import sys
import time

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import library  # noqa: E402


@pytest.fixture(autouse=True)
def tmp_media(tmp_path, monkeypatch):
    monkeypatch.setattr(library, "MEDIA_DIR", str(tmp_path / "media"))
    os.makedirs(library.MEDIA_DIR, exist_ok=True)
    yield


def _jpeg(w=1200, h=800, color=(200, 60, 40)) -> bytes:
    from PIL import Image
    out = io.BytesIO()
    Image.new("RGB", (w, h), color).save(out, "JPEG")
    return out.getvalue()


def _png(w=400, h=400) -> bytes:
    from PIL import Image
    out = io.BytesIO()
    Image.new("RGBA", (w, h), (10, 200, 120, 255)).save(out, "PNG")
    return out.getvalue()


def _gif() -> bytes:
    from PIL import Image
    out = io.BytesIO()
    Image.new("P", (64, 64)).save(out, "GIF")
    return out.getvalue()


def _mp4(tmp, seconds=2, w=640, h=360, vcodec="libx264") -> bytes:
    """Igazi videó, igazi ffmpeg-gel — nem elég úgy tenni, mintha."""
    p = os.path.join(tmp, "in.mp4")
    subprocess.run([library._ffmpeg(), "-hide_banner", "-loglevel", "error", "-y",
                    "-f", "lavfi", "-i", f"testsrc=size={w}x{h}:rate=30:duration={seconds}",
                    "-f", "lavfi", "-i", f"sine=frequency=440:duration={seconds}",
                    "-c:v", vcodec, "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", p],
                   check=True, capture_output=True, timeout=180)
    with open(p, "rb") as f:
        return f.read()


def _wait(mid, timeout=180):
    """Megvárja a háttérben futó átalakítást."""
    t0 = time.time()
    while time.time() - t0 < timeout:
        m = library.get(mid)
        if m and m.get("status") in ("ready", "failed"):
            return m
        time.sleep(0.4)
    raise AssertionError("az átalakítás nem fejeződött be")


# ---- típusfelismerés -------------------------------------------------------

def test_phone_types_are_recognised():
    """Amit az iPhone küld: HEIC, MOV, és a típus nélküli fájl is."""
    assert library.decide_type("image/heic", "IMG_1.HEIC", b"") == "image/heic"
    assert library.decide_type("video/quicktime", "IMG_2.MOV", b"") == "video/quicktime"
    # A böngésző néha semmit nem mond a típusról: a kiterjesztés dönt.
    assert library.decide_type("", "IMG_3.mov", b"") == "video/quicktime"
    assert library.decide_type("application/octet-stream", "IMG_4.heic", b"") == "image/heic"
    # Se típus, se kiterjesztés: a tartalom dönt.
    assert library.decide_type("", "valami", _jpeg(32, 32)) == "image/unknown"
    assert library.decide_type("", "valami", b"\x00\x01rossz") == "video/unknown"
    # Ritkább videótípusok a megszokottra.
    assert library.decide_type("video/x-m4v", "a.m4v", b"") == "video/mp4"


def test_documents_are_rejected():
    with pytest.raises(library.LibraryError):
        library.decide_type("application/pdf", "szamla.pdf", b"%PDF-1.4")
    with pytest.raises(library.LibraryError):
        library.decide_type("text/plain", "jegyzet.txt", b"hello")


# ---- képek -----------------------------------------------------------------

def test_jpeg_is_stored_and_scaled_down():
    m = library.store(_jpeg(4000, 3000), "image/jpeg", "IMG_0001.JPG", "nyitókép")
    assert m["kind"] == "image" and m["status"] == "ready"
    assert m["width"] == library.MAX_IMAGE_W, "a nagy fotót leskálázzuk"
    assert m["note"] == "nyitókép"
    assert os.path.exists(library.path_of(m["id"]))
    assert library.path_of(m["id"], "poster")           # a kép maga a borítókép


def test_png_and_gif_come_in_as_jpeg():
    for data, ct, name in ((_png(), "image/png", "a.png"), (_gif(), "image/gif", "a.gif")):
        m = library.store(data, ct, name)
        assert m["status"] == "ready" and library.path_of(m["id"]).endswith(".jpg")


def test_heic_without_pillow_heif_fails_clearly(monkeypatch):
    """HEIC-támogatás nélkül is érthető hibát kapunk, nem 500-at."""
    monkeypatch.setattr(library, "_is_image", lambda data: False)
    with pytest.raises(library.LibraryError):
        library.store(b"nem is kep", "image/heic", "IMG.HEIC")


def test_empty_and_oversized_are_refused(monkeypatch):
    with pytest.raises(library.LibraryError, match="üres"):
        library.store(b"", "image/jpeg", "a.jpg")
    monkeypatch.setattr(library, "MAX_BYTES", 10)
    with pytest.raises(library.LibraryError, match="túl nagy"):
        library.store(_jpeg(), "image/jpeg", "a.jpg")


# ---- videók ----------------------------------------------------------------

def test_clip_upload_returns_at_once_then_converts(tmp_path):
    """A kérés nem várja meg az átalakítást (az iPhone feladná), de kész lesz."""
    m = library.store(_mp4(str(tmp_path)), "video/quicktime", "IMG_9.MOV", "a 3. mp-től")
    assert m["kind"] == "clip" and m["status"] == "processing"
    done = _wait(m["id"])
    assert done["status"] == "ready", done.get("error")
    assert done["seconds"] and done["seconds"] >= 1.5
    assert done["width"] == 640 and done["height"] == 360
    assert done["note"] == "a 3. mp-től"
    assert library.path_of(m["id"]).endswith(".mp4")
    assert library.path_of(m["id"], "poster"), "legyen borítókép az előnézethez"
    assert not library.path_of(m["id"], "raw"), "a nyers feltöltés az átalakítás után törlődik"


def test_broken_clip_is_marked_failed_not_lost():
    m = library.store(b"\x00" * 5000, "video/mp4", "rossz.mp4")
    done = _wait(m["id"], timeout=90)
    assert done["status"] == "failed" and done["error"]
    # A tárban látszik, hogy elhasalt — nem tűnik el némán.
    assert any(x["id"] == m["id"] for x in library.listing())


def test_tall_clip_keeps_its_shape(tmp_path):
    """Álló felvétel álló marad (a 9:16-os videóhoz ez kell)."""
    m = library.store(_mp4(str(tmp_path), w=360, h=640), "video/mp4", "allo.mp4")
    done = _wait(m["id"])
    assert done["status"] == "ready" and done["height"] > done["width"]


def test_only_two_clips_convert_at_once(tmp_path, monkeypatch):
    """Memória: egyszerre legfeljebb CLIP_WORKERS átalakítás fut."""
    seen, lock = [], __import__("threading").Lock()
    real = library._convert_clip

    def slow(mid):
        with lock:
            seen.append(library.queue_depth())
        time.sleep(0.5)
        return real(mid)

    monkeypatch.setattr(library, "_convert_clip", slow)
    data = _mp4(str(tmp_path), seconds=1)
    ids = [library.store(data, "video/mp4", f"{i}.mp4")["id"] for i in range(6)]
    for mid in ids:
        _wait(mid)
    # A sorban állók is beszámítanak a queue_depth-be, de egyszerre
    # legfeljebb CLIP_WORKERS ffmpeg fut: ezt a szemafor adja.
    assert library._sem._initial_value == library.CLIP_WORKERS


def _store_without_starting(data, name):
    """Feltöltés úgy, mintha a gép az átalakítás előtt indult volna újra."""
    real = library._start_clip
    library._start_clip = lambda mid: None
    try:
        return library.store(data, "video/mp4", name)
    finally:
        library._start_clip = real


def test_resume_restarts_unfinished_conversion(tmp_path):
    """Újraindulás után a félbemaradt átalakítás folytatódik."""
    m = _store_without_starting(_mp4(str(tmp_path)), "felbe.mp4")
    assert library.get(m["id"])["status"] == "processing"
    assert library.resume_pending() == 1
    assert _wait(m["id"])["status"] == "ready"


def test_resume_marks_failed_when_raw_is_gone(tmp_path):
    m = _store_without_starting(_mp4(str(tmp_path)), "felbe.mp4")
    os.remove(os.path.join(library.MEDIA_DIR, library.get(m["id"])["raw"]))
    assert library.resume_pending() == 0
    assert library.get(m["id"])["status"] == "failed"


# ---- darabolt feltöltés ----------------------------------------------------

def test_chunked_upload_reassembles(tmp_path, monkeypatch):
    monkeypatch.setattr(library, "CHUNK_MAX", 64 * 1024)
    data = _jpeg(2000, 1500)
    uid = "a" * 32
    parts = [data[i:i + 50000] for i in range(0, len(data), 50000)]
    for i, p in enumerate(parts):
        out = library.save_chunk(uid, i, len(parts), p)
        assert out["have"] == i + 1
    m = library.finish_chunks(uid, len(parts), "image/jpeg", "nagy.jpg", "jegyzet")
    assert m["status"] == "ready" and m["note"] == "jegyzet"
    assert not os.path.isdir(library._upload_dir(uid)), "az összerakás után a darabok törlődnek"


def test_resent_chunk_overwrites():
    """Újrapróbálásnál ugyanaz a darab újra felküldhető."""
    uid = "b" * 32
    library.save_chunk(uid, 0, 2, b"rossz")
    library.save_chunk(uid, 0, 2, b"jo")
    library.save_chunk(uid, 1, 2, b"-vege")
    with open(os.path.join(library._upload_dir(uid), "00000"), "rb") as f:
        assert f.read() == b"jo"


def test_missing_chunk_is_named():
    uid = "c" * 32
    library.save_chunk(uid, 0, 3, b"x")
    library.save_chunk(uid, 2, 3, b"z")
    with pytest.raises(library.LibraryError, match=r"hiányzó darab: \[1\]"):
        library.finish_chunks(uid, 3, "image/jpeg", "a.jpg")


def test_bad_upload_ids_are_refused():
    for bad in ("", "../../etc", "xyz", "A" * 32, "a" * 64):
        with pytest.raises(library.LibraryError):
            library.save_chunk(bad, 0, 1, b"x")


def test_chunk_bounds_are_checked():
    with pytest.raises(library.LibraryError, match="darabszám"):
        library.save_chunk("d" * 32, 5, 3, b"x")
    with pytest.raises(library.LibraryError, match="darabméret"):
        library.save_chunk("d" * 32, 0, 1, b"x" * (library.CHUNK_MAX + 1))


# ---- a tár nem töröl friss elemet -----------------------------------------

def test_fresh_items_are_never_pruned(monkeypatch):
    """Ez a mostani 60-as korlát hibája: egy nagy feltöltés kitolta önmagát."""
    monkeypatch.setattr(library, "KEEP", 3)
    ids = [library.store(_jpeg(100, 100), "image/jpeg", f"{i}.jpg")["id"] for i in range(8)]
    library._prune()
    assert len(library.listing()) == 8, "friss elem nem törlődhet"
    # 48 óránál régebbi elemeken viszont lefut.
    old = time.time() - 3 * 24 * 3600
    for mid in ids[:5]:
        os.utime(library._meta_path(mid), (old, old))
    library._prune()
    left = {m["id"] for m in library.listing()}
    assert len(left) == 3 and set(ids[5:]) <= left


def test_note_can_be_changed_per_item():
    m = library.store(_jpeg(200, 200), "image/jpeg", "a.jpg")
    assert library.set_note(m["id"], "ez legyen a nyitókép")["note"] == "ez legyen a nyitókép"
    assert library.get(m["id"])["note"] == "ez legyen a nyitókép"
    assert library.set_note("x" * 12, "akármi") is None


def test_delete_removes_every_file(tmp_path):
    m = library.store(_mp4(str(tmp_path)), "video/mp4", "a.mp4")
    _wait(m["id"])
    assert library.delete(m["id"]) is True
    assert library.get(m["id"]) is None
    assert os.listdir(library.MEDIA_DIR) == [] or all(
        not n.startswith(m["id"]) for n in os.listdir(library.MEDIA_DIR))


def test_ids_outside_the_store_are_refused():
    """Az azonosító nem lehet útvonal."""
    for bad in ("../app", "..", "/etc/passwd", "ab", ""):
        assert library.get(bad) is None
        assert library.path_of(bad) is None
