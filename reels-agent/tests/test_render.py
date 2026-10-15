"""A renderelő: valódi ffmpeg, valódi képkockák. Nincs „úgy tesz, mintha"."""
import io
import os
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import director  # noqa: E402
import effects  # noqa: E402
import library  # noqa: E402
import render  # noqa: E402


@pytest.fixture(autouse=True)
def tmp_dirs(tmp_path, monkeypatch):
    monkeypatch.setattr(library, "MEDIA_DIR", str(tmp_path / "media"))
    monkeypatch.setattr(render, "VIDEO_DIR", str(tmp_path / "videos"))
    os.makedirs(library.MEDIA_DIR, exist_ok=True)
    os.makedirs(render.VIDEO_DIR, exist_ok=True)


def _photo(size=(1200, 1600), color=(40, 90, 180)) -> bytes:
    from PIL import Image, ImageDraw
    img = Image.new("RGB", size, color)
    ImageDraw.Draw(img).rectangle([10, 10, size[0] - 10, size[1] - 10], outline=(255, 255, 0), width=12)
    out = io.BytesIO()
    img.save(out, "JPEG", quality=85)
    return out.getvalue()


def _clip(tmp, seconds=4, w=720, h=1280) -> bytes:
    p = os.path.join(tmp, f"c{w}x{h}.mp4")
    subprocess.run([library._ffmpeg(), "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi",
                    "-i", f"testsrc2=size={w}x{h}:rate=30:duration={seconds}",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", p], check=True, timeout=180)
    with open(p, "rb") as f:
        return f.read()


def _wait(mid, timeout=180):
    import time
    t0 = time.time()
    while time.time() - t0 < timeout:
        m = library.get(mid)
        if m and m["status"] in ("ready", "failed"):
            return m
        time.sleep(0.3)
    raise AssertionError("nem készült el")


def _frame(path, at, out):
    subprocess.run([library._ffmpeg(), "-hide_banner", "-loglevel", "error", "-y", "-ss", str(at),
                    "-i", path, "-frames:v", "1", out], check=True, timeout=120)
    from PIL import Image
    return Image.open(out).convert("RGB")


# ---- felirat ---------------------------------------------------------------

def test_caption_stays_inside_the_phone_safe_area(tmp_path):
    """Álló videón a telefon levágja a széleket: balra 64, jobbra 100 px,
    fent a logónak 100 px, és az alsó negyed maradjon szabadon."""
    out = str(tmp_path / "t.png")
    assert render.text_overlay("Ez egy elég hosszú felirat, aminek tördelnie kell magát",
                               1080, 1920, out) is True
    from PIL import Image
    img = Image.open(out)
    assert img.mode == "RGBA"
    px = img.load()
    xs, ys = [], []
    for y in range(0, 1920, 2):
        for x in range(0, 1080, 2):
            if px[x, y][3] > 40:
                xs.append(x)
                ys.append(y)
    assert xs, "nem rajzolódott felirat"
    assert min(xs) >= render.SAFE["left"] - 4, f"balra kilóg: {min(xs)}"
    assert max(xs) <= 1080 - render.SAFE["right"] + 4, f"jobbra kilóg: {max(xs)}"
    assert min(ys) >= render.SAFE["top"], f"a logó sávjába ér: {min(ys)}"
    assert max(ys) <= 1920 * (1 - render.SAFE["bottom_quarter"]), f"az alsó negyedbe ér: {max(ys)}"


def test_empty_caption_draws_nothing(tmp_path):
    assert render.text_overlay("   ", 1080, 1920, str(tmp_path / "x.png")) is False


def test_a_very_long_caption_is_shrunk_not_cropped(tmp_path):
    out = str(tmp_path / "t.png")
    render.text_overlay("szó " * 60, 1080, 1920, out)
    from PIL import Image
    px = Image.open(out).load()
    ys = [y for y in range(0, 1920, 2) if any(px[x, y][3] > 40 for x in range(0, 1080, 8))]
    assert ys and max(ys) <= 1920 * (1 - render.SAFE["bottom_quarter"])


# ---- a teljes videó --------------------------------------------------------

def test_a_montage_is_made_from_photos_and_clips(tmp_path):
    ids = [library.store(_photo(color=(30 + i * 20, 80, 160)), "image/jpeg", f"p{i}.jpg")["id"]
           for i in range(5)]
    cid = library.store(_clip(str(tmp_path)), "video/quicktime", "c1.MOV")["id"]
    _wait(cid)
    items = [m for m in library.listing() if library.ready(m)]
    p = director.plan(items, seconds=8, aspect="9:16")
    meta = render.make(p)
    assert meta["width"] == 1080 and meta["height"] == 1920
    assert meta["used"] == 6 and not meta["skipped"]
    assert 5 <= meta["seconds"] <= 14, meta["seconds"]
    path = render.video_path(meta["id"])
    assert path and os.path.getsize(path) > 10000
    # Tényleg mozgókép, nem egy állókép: két távoli képkocka különbözzön.
    a = _frame(path, 0.2, str(tmp_path / "a.png"))
    b = _frame(path, meta["seconds"] - 0.5, str(tmp_path / "b.png"))
    assert a.size == (1080, 1920) and a.tobytes() != b.tobytes()
    assert os.path.exists(os.path.join(render.VIDEO_DIR, f"{meta['id']}.jpg")), "legyen előnézet"
    assert len(ids) == 5


def test_a_landscape_photo_fills_a_vertical_frame(tmp_path):
    """Fekvő fotóból se legyen fekete csík: kitölt és levág."""
    mid = library.store(_photo(size=(1600, 900), color=(200, 40, 40)), "image/jpeg", "f.jpg")["id"]
    p = director.plan([library.get(mid)], seconds=2, aspect="9:16")
    meta = render.make(p)
    img = _frame(render.video_path(meta["id"]), 0.3, str(tmp_path / "f.png"))
    w, h = img.size
    px = img.load()
    for y in (6, h // 2, h - 6):                        # a széleken se legyen fekete sáv
        r, g, b = px[w // 2, y]
        assert r + g + b > 60, f"fekete csík {y}-nál: {(r, g, b)}"


def test_the_caption_really_lands_on_the_video(tmp_path):
    mid = library.store(_photo(color=(10, 10, 10)), "image/jpeg", "p.jpg")["id"]
    library.set_note(mid, "írd rá: TESZT")
    p = director.plan([library.get(mid)], seconds=2, aspect="9:16")
    assert p["scenes"][0]["text"] == "TESZT"
    meta = render.make(p)
    img = _frame(render.video_path(meta["id"]), 0.5, str(tmp_path / "c.png"))
    px = img.load()
    bright = sum(1 for y in range(300, 1500, 3) for x in range(64, 980, 3)
                 if sum(px[x, y]) > 600)
    assert bright > 150, f"nem látszik a felirat (fehér pontok: {bright})"


def test_a_broken_item_does_not_kill_the_whole_video(tmp_path):
    good = [library.store(_photo(), "image/jpeg", f"g{i}.jpg")["id"] for i in range(3)]
    items = [library.get(i) for i in good]
    p = director.plan(items, seconds=5)
    # A középső fájlt kivesszük a lemezről: a videó a maradékból készüljön el.
    os.remove(library.path_of(good[1]))
    meta = render.make(p)
    assert meta["used"] == 2 and len(meta["skipped"]) == 1


def test_nothing_renderable_is_a_clear_error(tmp_path):
    mid = library.store(_photo(), "image/jpeg", "p.jpg")["id"]
    p = director.plan([library.get(mid)], seconds=2)
    os.remove(library.path_of(mid))
    with pytest.raises(render.RenderError, match="egyetlen jelenet"):
        render.make(p)


def test_videos_are_listed_and_deletable(tmp_path):
    mid = library.store(_photo(), "image/jpeg", "p.jpg")["id"]
    meta = render.make(director.plan([library.get(mid)], seconds=2))
    assert [v["id"] for v in render.listing()] == [meta["id"]]
    assert render.delete(meta["id"]) is True
    assert render.get(meta["id"]) is None and render.video_path(meta["id"]) is None
    assert render.delete("abcdefghij") is False
    assert render.get("../../etc") is None


def test_a_rich_ai_plan_renders_end_to_end(tmp_path):
    """Amit a modell kérhet: mozgás, színezés, sebesség, felirat, átmenet — egyben."""
    import brain
    ids = [library.store(_photo(color=(30 + i * 40, 70, 150)), "image/jpeg", f"p{i}.jpg")["id"]
           for i in range(4)]
    cid = library.store(_clip(str(tmp_path), seconds=6), "video/quicktime", "c.MOV")["id"]
    _wait(cid)
    items = [m for m in library.listing() if library.ready(m)]
    by = {m["id"]: m for m in items}
    raw = {"title": "Teszt", "trends_used": ["Velocity zoom"], "scenes": [
        {"id": ids[0], "seconds": 1.0, "motion": "punch_in", "look": "contrast_pop",
         "transition": "zoomin", "text": "Árvíztűrő", "text_style": "box", "text_anim": "pop",
         "text_position": "top"},
        {"id": cid, "seconds": 1.0, "start": 2.0, "speed": 2.0, "motion": "shake",
         "look": "vhs", "transition": "flash"},
        {"id": ids[1], "seconds": 0.8, "motion": "ken_burns", "look": "rgb_split",
         "transition": "slideleft"},
        {"id": ids[2], "seconds": 0.8, "motion": "zoom_pulse", "look": "glitch",
         "transition": "circleopen"},
        {"id": ids[3], "seconds": 1.0, "motion": "rotate_in", "look": "blur_in",
         "transition": "cut", "text": "Vége", "text_style": "bar", "text_anim": "slide_up"},
    ]}
    scenes = [brain._clean_scene(x, by, "hu") for x in raw["scenes"]]
    plan = {"aspect": "9:16", "width": 1080, "height": 1920, "lang": "hu", "title": "Teszt",
            "brief": "proba", "by": "teszt-modell", "trends_used": ["Velocity zoom"],
            "scenes": [s for s in scenes if s], "seconds": 4.6, "fade_seconds": 0.3}
    meta = render.make(plan)
    assert meta["used"] == 5 and not meta["skipped"], meta
    assert meta["trends"] == ["Velocity zoom"] and meta["by"] == "teszt-modell"
    path = render.video_path(meta["id"])
    a = _frame(path, 0.3, str(tmp_path / "x1.png"))
    b = _frame(path, meta["seconds"] - 0.3, str(tmp_path / "x2.png"))
    assert a.size == (1080, 1920) and a.tobytes() != b.tobytes()


def test_every_transition_name_renders(tmp_path):
    """Ha egy átmenet elhasalna, a vágás ne álljon meg — de ne is hasaljon el."""
    mid = library.store(_photo(), "image/jpeg", "p.jpg")["id"]
    a = str(tmp_path / "a.mp4")
    b = str(tmp_path / "b.mp4")
    base = {"id": mid, "kind": "image", "name": "p.jpg", "seconds": 0.6, "start": 0.0,
            "speed": 1.0, "motion": "none", "look": "none", "text": ""}
    render.scene_segment(base, library.path_of(mid), 540, 960, a, None)
    render.scene_segment({**base, "look": "bw"}, library.path_of(mid), 540, 960, b, None)
    bad = []
    for name in effects.XFADE:
        try:
            render.transition_segment(a, b, name, 0.2, str(tmp_path / "t.mp4"))
        except render.RenderError as e:
            bad.append((name, str(e)[-80:]))
    assert not bad, bad


def test_every_look_and_motion_renders(tmp_path):
    mid = library.store(_photo(), "image/jpeg", "p.jpg")["id"]
    base = {"id": mid, "kind": "image", "name": "p.jpg", "seconds": 0.5, "start": 0.0,
            "speed": 1.0, "motion": "none", "look": "none", "text": ""}
    bad = []
    for look in effects.LOOKS:
        try:
            render.scene_segment({**base, "look": look}, library.path_of(mid), 540, 960,
                                 str(tmp_path / "l.mp4"), None)
        except render.RenderError as e:
            bad.append(("look:" + look, str(e)[-80:]))
    for motion in effects.MOTIONS:
        try:
            render.scene_segment({**base, "motion": motion}, library.path_of(mid), 540, 960,
                                 str(tmp_path / "m.mp4"), None)
        except render.RenderError as e:
            bad.append(("motion:" + motion, str(e)[-80:]))
    assert not bad, bad


def test_square_and_landscape_outputs(tmp_path):
    mid = library.store(_photo(), "image/jpeg", "p.jpg")["id"]
    for aspect, size in (("1:1", (1080, 1080)), ("16:9", (1920, 1080))):
        meta = render.make(director.plan([library.get(mid)], seconds=2, aspect=aspect))
        assert (meta["width"], meta["height"]) == size
