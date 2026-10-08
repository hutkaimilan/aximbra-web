"""A videós agent hálózat nélkül: modell, felolvasó és renderelő csonkkal."""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import llm  # noqa: E402


# ---- videós agent ----

import videomaker  # noqa: E402


def test_video_script_is_normalized_and_ends_with_cta():
    raw = {"title": "T", "scenes": [
        {"kind": "cta", "headline": "Korai CTA", "seconds": 4},
        {"kind": "hook", "headline": "Ki veszi fel?", "seconds": 3},
        {"kind": "call", "headline": "", "lines": ["AI: Jó napot!", "Ügyfél: Ajánlatot kérnék."], "seconds": 6},
        {"kind": "bogus", "headline": "x"},
        {"kind": "problem", "headline": "Ismerős?", "lines": ["a", "b", "c", "d", "e", "f", "g"], "seconds": 99},
    ]}
    s = videomaker.normalize(raw, 30)
    assert [x["kind"] for x in s["scenes"]] == ["hook", "call", "problem", "cta"]
    assert s["scenes"][1]["lines"] == ["Jó napot!", "Ajánlatot kérnék."]
    assert len(s["scenes"][2]["lines"]) == 6
    assert all(2 <= x["seconds"] <= 14 for x in s["scenes"])
    assert s["first_comment"]


def test_video_script_without_usable_scenes_fails():
    with pytest.raises(videomaker.VideoError):
        videomaker.normalize({"scenes": [{"kind": "hook", "headline": ""}]}, 30)


def test_video_ids_cannot_escape_the_folder():
    assert videomaker.video_path("../../etc/passwd") is None
    assert videomaker.video_path("abc") is None


def test_video_served_in_byte_ranges(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    import app as app_mod
    monkeypatch.setenv("ADMIN_PASSWORD", "jelszo1234")
    monkeypatch.setattr(videomaker, "VIDEO_DIR", str(tmp_path))
    (tmp_path / "abcdef012345.mp4").write_bytes(bytes(range(100)))
    c = TestClient(app_mod.app)
    r = c.get("/api/videos/abcdef012345.mp4", headers={"Range": "bytes=10-19"}, auth=("a", "jelszo1234"))
    assert r.status_code == 206 and r.content == bytes(range(10, 20))
    assert r.headers["content-range"] == "bytes 10-19/100"
    assert c.get("/api/videos/abcdef012345.mp4", auth=("a", "rossz")).status_code == 401




def test_video_claims_need_a_source():
    s = videomaker.normalize({"scenes": [
        {"kind": "hook", "headline": "40%-kal kevesebb elveszett hívás", "voice": "Garantáltan"},
        {"kind": "benefit", "headline": "Mi változik?", "lines": ["Nulla elveszett ügyfél", "Rendezett postafiók"]},
        {"kind": "statement", "headline": "10 másodpercen belül visszahív"},
    ]}, 20)
    v = videomaker.violations(s, "")
    assert any("40%" in x for x in v) and any("Nulla" in x for x in v) and any("Garantáltan" in x for x in v)
    assert not any("10 másodperc" in x for x in v)  # az AXIMBRA-tényekben szerepel
    assert not videomaker.violations(s, "A brief szerint 40%-kal kevesebb, garantáltan, nulla veszteség, ügyfeleink")[:0]
    cleaned = videomaker._strip_claims(s, "")
    heads = [x["headline"] for x in cleaned["scenes"]]
    assert "40%-kal kevesebb elveszett hívás" not in heads
    assert cleaned["scenes"][0]["lines"] == ["Rendezett postafiók"]


def test_video_narration_stretches_scenes(monkeypatch):
    import math, struct
    tone = b"".join(struct.pack("<h", int(3000 * math.sin(i / 20))) for i in range(videomaker.SAMPLE_RATE * 3))
    monkeypatch.setattr(videomaker, "_tts_gemini", lambda text, lang: videomaker._pcm_to_wav(tone))
    s = videomaker.normalize({"scenes": [
        {"kind": "hook", "headline": "Első", "voice": "Hosszú mondat", "seconds": 2},
        {"kind": "statement", "headline": "Második", "voice": "", "seconds": 3},
    ]}, 10)
    s["scenes"][0]["seconds"] = 2.0
    wav, engine = videomaker.narrate(s, "hu", False)
    assert engine == "gemini" and s["scenes"][0]["seconds"] >= 3.7
    total = sum(x["seconds"] for x in s["scenes"])
    with __import__("wave").open(__import__("io").BytesIO(wav)) as w:
        assert abs(w.getnframes() / w.getframerate() - total) < 0.05


def test_video_narration_falls_back_to_silent(monkeypatch):
    monkeypatch.setattr(videomaker, "_tts_gemini", lambda text, lang: None)
    monkeypatch.setattr(videomaker, "_tts_edge", lambda text, lang, male: None)
    s = videomaker.normalize({"scenes": [{"kind": "hook", "headline": "A", "voice": "szia"},
                                         {"kind": "statement", "headline": "B"}]}, 10)
    assert videomaker.narrate(s, "hu", False) == (None, "")


def test_video_revise_keeps_options_and_links_parent(tmp_path, monkeypatch):
    import json as _json
    monkeypatch.setattr(videomaker, "VIDEO_DIR", str(tmp_path))
    (tmp_path / "abcdef012345.mp4").write_bytes(b"x")
    (tmp_path / "abcdef012345.json").write_text(_json.dumps({
        "id": "abcdef012345", "title": "T", "scenes": [{"kind": "hook", "headline": "Régi"}],
        "opts": {"brief": "E-mail rendező videó", "seconds": 20, "lang": "hu", "aspect": "1:1", "voice": False,
                 "male": False, "research": False}, "ctx_urls": []}), encoding="utf-8")
    monkeypatch.setattr(llm, "_ask", lambda p, **k: _json.dumps({"title": "Új", "scenes": [
        {"kind": "hook", "headline": "Új nyitás"}, {"kind": "cta", "headline": "Próbálja ki"}]}))
    seen = {}

    def fake_render(script, urls, out, aspect, audio, captions, say):
        seen["aspect"] = aspect
        open(out, "wb").write(b"mp4")
        return 20.0

    monkeypatch.setattr(videomaker, "render", fake_render)
    m = videomaker.revise("abcdef012345", "rövidebb nyitás")
    assert m["parent"] == "abcdef012345" and m["title"] == "Új" and seen["aspect"] == "1:1"
    assert videomaker.get_meta(m["id"])["scenes"][0]["headline"] == "Új nyitás"


def test_gemini_tts_waits_out_the_minute_limit(monkeypatch):
    import base64 as b64
    calls = []

    class R:
        def __init__(self, code, data=None, text=""):
            self.status_code, self._d, self.text = code, data, text

        def json(self):
            return self._d

    ok = {"candidates": [{"content": {"parts": [{"inlineData": {"data": b64.b64encode(b"\x00\x00" * 100).decode()}}]}}]}
    seq = iter([R(429, text="rate"), R(200, ok)])
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    monkeypatch.setattr(videomaker.httpx, "post", lambda *a, **k: calls.append(1) or next(seq))
    monkeypatch.setattr(videomaker.stop, "sleep", lambda s: None)
    assert videomaker._tts_gemini("szia", "hu") and len(calls) == 2


# ---- médiatár ----

import media  # noqa: E402


def _png(w=40, h=30, c=(10, 120, 200)):
    import struct, zlib
    raw = b"".join(b"\x00" + bytes(c) * w for _ in range(h))

    def ch(t, d):
        x = t + d
        return struct.pack(">I", len(d)) + x + struct.pack(">I", zlib.crc32(x))

    return (b"\x89PNG\r\n\x1a\n" + ch(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
            + ch(b"IDAT", zlib.compress(raw)) + ch(b"IEND", b""))


@pytest.fixture
def lib(tmp_path, monkeypatch):
    monkeypatch.setattr(media, "MEDIA_DIR", str(tmp_path))
    return media


def test_upload_normalizes_an_image_and_lists_it(lib):
    m = lib.store(_png(), "image/png", "logo.png", "az AXIMBRA logó")
    assert m["kind"] == "image" and m["file"].endswith(".jpg") and m["width"] == 40
    assert lib.path_of(m["id"]) and [x["id"] for x in lib.listing()] == [m["id"]]
    assert lib.delete(m["id"]) and lib.listing() == []


def test_upload_rejects_other_file_types(lib):
    with pytest.raises(lib.MediaError):
        lib.store(b"MZ...", "application/x-msdownload", "a.exe")
    with pytest.raises(lib.MediaError):
        lib.store(b"", "image/png", "ures.png")


def test_media_ids_cannot_escape_the_folder(lib):
    assert lib.path_of("../../etc/passwd") is None and lib.path_of("abc") is None


def test_scenes_without_usable_media_fall_back_to_text(lib, monkeypatch):
    monkeypatch.setattr(videomaker.media, "MEDIA_DIR", lib.MEDIA_DIR)
    img = lib.store(_png(), "image/png", "kep.png")
    s = videomaker.normalize({"scenes": [
        {"kind": "photo", "headline": "Kép nélkül", "seconds": 4},
        {"kind": "gallery", "headline": "Üres galéria", "medias": [], "seconds": 4},
        {"kind": "clip", "headline": "Kép klipként", "media": img["id"], "seconds": 9},
        {"kind": "photo", "headline": "Jó kép", "media": img["id"], "seconds": 4},
    ]}, 20)
    kinds = [x["kind"] for x in s["scenes"]]
    assert kinds[:4] == ["statement", "statement", "photo", "photo"]
    assert s["scenes"][3]["media"] == img["id"]


def test_generated_images_only_when_the_model_answers(lib, monkeypatch):
    monkeypatch.setattr(videomaker.media, "MEDIA_DIR", lib.MEDIA_DIR)
    monkeypatch.setattr(videomaker.imagegen, "MEDIA_DIR", lib.MEDIA_DIR, raising=False)
    monkeypatch.setattr(videomaker.imagegen, "available", lambda: True)
    monkeypatch.setattr(videomaker.imagegen, "generate_into_library",
                        lambda prompt, aspect, name: {"id": "aaaaaaaaaaaa"} if "jo" in prompt else None)
    s = videomaker.normalize({"scenes": [
        {"kind": "photo", "headline": "A", "image_prompt": "jo kep", "seconds": 4},
        {"kind": "photo", "headline": "B", "image_prompt": "rossz", "seconds": 4},
    ]}, 12)
    out = videomaker.fill_images(s, "9:16")
    assert out["scenes"][0]["kind"] == "photo" and out["scenes"][0]["media"] == "aaaaaaaaaaaa"
    assert out["scenes"][1]["kind"] == "statement"

    monkeypatch.setattr(videomaker.imagegen, "available", lambda: False)
    s2 = videomaker.normalize({"scenes": [{"kind": "photo", "headline": "C", "image_prompt": "jo", "seconds": 4},
                                          {"kind": "cta", "headline": "D", "seconds": 4}]}, 12)
    assert videomaker.fill_images(s2, "9:16")["scenes"][0]["kind"] == "statement"


# ---- automatika és kiposztolás ----

import publisher  # noqa: E402
import settings as st  # noqa: E402
from datetime import datetime, timedelta, timezone  # noqa: E402


@pytest.fixture
def cfg(tmp_path, monkeypatch):
    monkeypatch.setattr(st, "PATH", str(tmp_path / "s.json"))
    return st


def test_settings_round_trip_and_limits(cfg):
    saved = cfg.save(cfg.clean({"every_hours": 99, "seconds": 5, "aspect": "kacsa", "lang": "de",
                                "briefs": "egy\n\n  kettő  \n", "targets": ["instagram", "tiktok"],
                                "max_posts_per_day": 99}))
    assert saved["every_hours"] == cfg.MAX_HOURS and saved["seconds"] == 10
    assert saved["aspect"] == "9:16" and saved["lang"] == "hu"      # érvénytelen érték nem megy át
    assert saved["briefs"] == ["egy", "kettő"] and saved["targets"] == ["instagram"]
    assert saved["max_posts_per_day"] == 10
    assert cfg.load()["briefs"] == ["egy", "kettő"]


def test_due_only_when_on_with_topics_and_time_passed(cfg):
    now = datetime(2026, 10, 1, 12, tzinfo=timezone.utc)
    assert not cfg.due(now, {**cfg.DEFAULTS, "auto": True, "briefs": []})
    assert not cfg.due(now, {**cfg.DEFAULTS, "auto": False, "briefs": ["a"]})
    on = {**cfg.DEFAULTS, "auto": True, "briefs": ["a"], "every_hours": 8}
    assert cfg.due(now, on)                                           # még sosem futott
    assert not cfg.due(now, {**on, "last_run": (now - timedelta(hours=7)).isoformat()})
    assert cfg.due(now, {**on, "last_run": (now - timedelta(hours=9)).isoformat()})


def test_briefs_are_taken_in_turn(cfg):
    s = {**cfg.DEFAULTS, "briefs": ["a", "b", "c"], "next_brief": 2}
    assert cfg.take_brief(s) == ("c", 0)
    assert cfg.take_brief({**s, "next_brief": 0}) == ("a", 1)
    assert cfg.take_brief({**cfg.DEFAULTS, "briefs": []}) == ("", 0)


def test_daily_post_budget_resets_on_a_new_day(cfg):
    now = datetime(2026, 10, 1, 12, tzinfo=timezone.utc)
    s = {**cfg.DEFAULTS, "max_posts_per_day": 2}
    assert cfg.post_budget(now, s) == 2
    s = {**s, "posts_day": "2026-10-01", "posts_today": 2}
    assert cfg.post_budget(now, s) == 0
    assert cfg.post_budget(now + timedelta(days=1), s) == 2


def test_publisher_reports_what_is_missing(monkeypatch):
    for v in ("IG_USER_ID", "IG_ACCESS_TOKEN", "PUBLIC_BASE_URL", "LI_ACCESS_TOKEN", "LI_AUTHOR_URN", "LI_WEBHOOK_URL"):
        monkeypatch.delenv(v, raising=False)
    assert not publisher.ig_ready() and not publisher.li_ready()
    assert publisher.enabled_targets() == []
    assert len(publisher.ig_missing()) == 3 and len(publisher.li_missing()) == 1
    monkeypatch.setenv("LI_ACCESS_TOKEN", "t")
    monkeypatch.setenv("LI_AUTHOR_URN", "urn:li:person:abc")
    assert publisher.enabled_targets() == ["linkedin"]


def test_linkedin_refuses_a_bad_author_urn(monkeypatch):
    monkeypatch.setenv("LI_ACCESS_TOKEN", "t")
    monkeypatch.setenv("LI_AUTHOR_URN", "abc123")
    with pytest.raises(publisher.PublishError):
        publisher.li_publish("/dev/null", "szöveg")


def test_instagram_needs_an_https_url(monkeypatch):
    monkeypatch.setenv("IG_USER_ID", "1")
    monkeypatch.setenv("IG_ACCESS_TOKEN", "t")
    with pytest.raises(publisher.PublishError):
        publisher.ig_publish("http://nem-biztonsagos/v.mp4", "szöveg")


def test_public_link_needs_the_right_ticket(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    import app as app_mod
    monkeypatch.setenv("ADMIN_PASSWORD", "jelszo1234")
    monkeypatch.setenv("PUBLIC_LINK_SECRET", "titok")
    monkeypatch.setattr(videomaker, "VIDEO_DIR", str(tmp_path))
    (tmp_path / "abcdef012345.mp4").write_bytes(b"mp4")
    c = TestClient(app_mod.app)
    good = app_mod.public_ticket("abcdef012345")
    assert c.get(f"/p/abcdef012345/{good}.mp4").status_code == 200        # jegy nélkül nyilvános
    assert c.get("/p/abcdef012345/rosszjegy.mp4").status_code == 404
    assert c.get(f"/p/masikvideo00/{good}.mp4").status_code == 404


# ---- kép és körhinta --------------------------------------------------------

def test_form_is_guessed_from_the_brief():
    assert videomaker.pick_form("Csinálj egy körhintát 5 képben az agentekről") == "carousel"
    assert videomaker.pick_form("Kérek egy képet a telefonos AI-ról") == "image"
    assert videomaker.pick_form("30 mp-es videó az e-mail rendezőről") == "video"
    assert videomaker.pick_form("Mutasd be az AXIMBRA-t") == "video"
    assert videomaker.pick_form("5 tipp, hogyan rendezze a céges postafiókot") == "carousel"
    assert videomaker.pick_form("Videó: 3 lépés az e-mail rendezéshez") == "video"


def test_still_scripts_drop_the_moving_scenes_and_the_voice():
    raw = {"title": "T", "scenes": [
        {"kind": "hook", "headline": "Ki veszi fel?", "voice": "narráció", "seconds": 3},
        {"kind": "call", "headline": "Hívás", "lines": ["AI: Jó napot!"], "seconds": 6},
        {"kind": "benefit", "headline": "Miért jó", "lines": ["a", "b"], "seconds": 5},
    ]}
    s = videomaker.normalize(raw, 30, 1, "carousel")
    assert all(x["kind"] not in ("call", "site", "inbox", "clip") for x in s["scenes"])
    assert all(not x.get("voice") for x in s["scenes"])
    assert all(x["seconds"] == 5.0 for x in s["scenes"])


def test_a_single_image_keeps_one_scene_and_needs_no_cta():
    s = videomaker.normalize({"title": "T", "scenes": [
        {"kind": "hook", "headline": "Egy mondat", "seconds": 3},
        {"kind": "benefit", "headline": "Másik", "lines": ["a"], "seconds": 5},
    ]}, 30, 1, "image")
    assert len(s["scenes"]) == 1 and s["scenes"][0]["kind"] != "cta"


def test_carousel_is_capped_at_eight_slides():
    scenes = [{"kind": "benefit", "headline": f"H{i}", "lines": ["a"], "seconds": 4} for i in range(12)]
    s = videomaker.normalize({"title": "T", "scenes": scenes}, 30, 1, "carousel")
    assert len(s["scenes"]) <= videomaker.MAX_SLIDES


def test_slides_are_served_and_publicly_linked(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    import app as app_mod
    monkeypatch.setenv("ADMIN_PASSWORD", "jelszo1234")
    monkeypatch.setenv("PUBLIC_LINK_SECRET", "titok")
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://pelda.hu")
    monkeypatch.setattr(videomaker, "VIDEO_DIR", str(tmp_path))
    vid = "abcdef012345"
    for n in (1, 2):
        (tmp_path / f"{vid}-{n}.jpg").write_bytes(b"jpg%d" % n)
    meta = {"id": vid, "form": "carousel", "files": [f"{vid}-1.jpg", f"{vid}-2.jpg"],
            "title": "T", "created_at": "2026-01-01T00:00:00"}
    (tmp_path / f"{vid}.json").write_text(json.dumps(meta), encoding="utf-8")

    c = TestClient(app_mod.app)
    assert c.get(f"/api/videos/{vid}/2.jpg", auth=("a", "jelszo1234")).content == b"jpg2"
    assert c.get(f"/api/videos/{vid}/3.jpg", auth=("a", "jelszo1234")).status_code == 404
    assert c.get(f"/api/videos/{vid}.mp4", auth=("a", "jelszo1234")).status_code == 404

    tick = app_mod.public_ticket(vid)
    assert c.get(f"/p/{vid}/{tick}/1.jpg").status_code == 200
    assert c.get(f"/p/{vid}/rosszjegy/1.jpg").status_code == 404
    assert app_mod.public_urls(videomaker.get_meta(vid)) == [
        f"https://pelda.hu/p/{vid}/{tick}/1.jpg", f"https://pelda.hu/p/{vid}/{tick}/2.jpg"]


def test_a_carousel_of_one_image_goes_out_as_a_plain_image(monkeypatch):
    calls = []
    monkeypatch.setattr(publisher, "ig_publish_image", lambda url, cap: calls.append(url) or "1")
    assert publisher.ig_publish_carousel(["https://pelda.hu/a.jpg"], "szöveg") == "1"
    assert calls == ["https://pelda.hu/a.jpg"]


def test_publish_picks_the_route_from_the_form(monkeypatch):
    seen = {}
    monkeypatch.setattr(publisher, "ig_direct", lambda: True)   # a Graph API-út
    monkeypatch.setattr(publisher, "ig_publish", lambda u, c: seen.setdefault("video", u) or "v")
    monkeypatch.setattr(publisher, "ig_publish_carousel", lambda u, c: seen.setdefault("slides", u) or "k")
    publisher.publish("instagram", paths=["/a.mp4"], urls=["https://x/a.mp4"], caption="c", form="video")
    publisher.publish("instagram", paths=["/a.jpg", "/b.jpg"],
                      urls=["https://x/a.jpg", "https://x/b.jpg"], caption="c", form="carousel")
    assert seen == {"video": "https://x/a.mp4", "slides": ["https://x/a.jpg", "https://x/b.jpg"]}
    with pytest.raises(publisher.PublishError):
        publisher.publish("instagram", paths=["/a.jpg"], urls=[], caption="c", form="image")


def test_slide_numbers_are_dropped_from_the_kicker():
    s = videomaker.normalize({"title": "T", "scenes": [
        {"kind": "hook", "kicker": "1. SLIDE", "headline": "Első", "seconds": 4},
        {"kind": "benefit", "kicker": "Dia 2", "headline": "Második", "lines": ["a"], "seconds": 4},
        {"kind": "statement", "kicker": "AXIMBRA", "headline": "Harmadik", "seconds": 4},
    ]}, 30, 1, "carousel")
    assert [x["kicker"] for x in s["scenes"]][:3] == ["", "", "AXIMBRA"]


# ---- Claude -----------------------------------------------------------------

class _Resp:
    def __init__(self, code, body=None, text="", headers=None):
        self.status_code, self._body, self.text, self.headers = code, body or {}, text, headers or {}

    def json(self):
        return self._body


def test_claude_is_used_when_its_key_is_set(monkeypatch):
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    sent = {}

    def post(url, headers, json, timeout):
        sent.update(url=url, model=json["model"], key=headers["x-api-key"])
        return _Resp(200, {"content": [{"type": "text", "text": '{"ok": 1}'}], "stop_reason": "end_turn"})
    monkeypatch.setattr(llm.httpx, "post", post)
    assert llm.provider() == "anthropic"
    assert llm.extract_json(llm._ask("x")) == {"ok": 1}
    assert sent["url"] == llm.ANTHROPIC_URL and sent["model"] == llm.ANTHROPIC_MODEL and sent["key"] == "k"


def test_claude_out_of_credit_falls_back_to_gemini(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    monkeypatch.setenv("GEMINI_API_KEY", "g")
    monkeypatch.setattr(llm.httpx, "post", lambda *a, **k: _Resp(
        400, text='{"error":{"message":"Your credit balance is too low"}}'))
    monkeypatch.setattr(llm, "_gemini", lambda p: "gemini válasz")
    assert llm._ask("x") == "gemini válasz"


def test_claude_error_without_gemini_is_raised(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setattr(llm.httpx, "post", lambda *a, **k: _Resp(401, text="invalid x-api-key"))
    with pytest.raises(llm.LLMError):
        llm._ask("x")


def test_claude_bad_request_is_not_hidden_by_the_fallback(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    monkeypatch.setenv("GEMINI_API_KEY", "g")
    monkeypatch.setattr(llm.httpx, "post", lambda *a, **k: _Resp(400, text="max_tokens: too large"))
    monkeypatch.setattr(llm, "_gemini", lambda p: pytest.fail("nem eshet vissza programhibán"))
    with pytest.raises(llm.LLMError):
        llm._ask("x")


# ---- leállítás --------------------------------------------------------------

def test_stop_ends_a_running_job(monkeypatch):
    import threading
    import time
    import app as app_mod
    import stop
    j = app_mod.Job()
    started, done = threading.Event(), threading.Event()

    def work(say):
        started.set()
        try:
            while True:
                say("dolgozom")
                stop.sleep(0.05)
        finally:
            done.set()
    assert j.start(work)
    assert started.wait(2)
    assert j.stop()
    assert done.wait(2)
    for _ in range(50):
        if not j.running:
            break
        time.sleep(0.02)
    st = j.state()
    assert not st["running"] and st["cancelled"] and not st["error"]
    assert not j.stop()          # ami nem fut, azt nem lehet leállítani
    stop.reset()


def test_a_stopped_render_leaves_no_files(tmp_path, monkeypatch):
    import stop
    monkeypatch.setattr(videomaker, "VIDEO_DIR", str(tmp_path))

    def half(script, urls, out_dir, vid, aspect, say):
        (tmp_path / f"{vid}-1.jpg").write_bytes(b"x")
        raise stop.Cancelled("leállítva")
    monkeypatch.setattr(videomaker, "render_stills", half)
    script = videomaker.normalize({"title": "T", "scenes": [
        {"kind": "hook", "headline": "Egy", "seconds": 3},
        {"kind": "statement", "headline": "Kettő", "seconds": 3}]}, 30, 0, "carousel")
    opts = {"brief": "b", "seconds": 30, "lang": "hu", "aspect": "4:5", "voice": False, "form": "carousel"}
    with pytest.raises(stop.Cancelled):
        videomaker._finish(script, opts, {"urls": []}, lambda m: None)
    assert list(tmp_path.iterdir()) == []


# ---- logó -------------------------------------------------------------------

import logomaker  # noqa: E402

_EVIL = """<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" viewBox="0 0 1080 1080" onload="alert(1)">
<script>alert(1)</script><style>@import url(http://rossz.hu/x.css);</style>
<image href="file:///etc/passwd" width="10" height="10"/>
<foreignObject><div>x</div></foreignObject>
<defs><linearGradient id="g"><stop offset="0" stop-color="#0ff"/></linearGradient></defs>
<rect width="1080" height="1080" fill="#04040C" class="x" style="fill:red"/>
<circle cx="540" cy="540" r="300" fill="url(#g)" onclick="x()"/>
<path d="M0 0L10 10" fill="url(http://rossz.hu/a.svg#g)"/>
<use href="#g"/><use xlink:href="http://rossz.hu/a.svg#x"/>
</svg>"""


def test_logo_svg_is_stripped_to_drawing_only():
    out = logomaker.sanitize(_EVIL)
    low = out.lower()
    for bad in ("script", "onload", "onclick", "<style", "@import", "<image", "foreignobject",
                "passwd", "rossz.hu", "class=", "style="):
        assert bad not in low, bad
    assert 'fill="url(#g)"' in out and 'href="#g"' in out and "<circle" in out
    assert 'width="1080"' in out and 'viewBox="0 0 1080 1080"' in out


def test_logo_svg_with_a_dtd_or_nothing_to_draw_is_rejected():
    with pytest.raises(logomaker.LogoError):
        logomaker.sanitize('<!DOCTYPE svg [<!ENTITY x SYSTEM "file:///etc/passwd">]><svg>&x;</svg>')
    with pytest.raises(logomaker.LogoError):
        logomaker.sanitize('<svg xmlns="http://www.w3.org/2000/svg"><script>x</script></svg>')
    with pytest.raises(logomaker.LogoError):
        logomaker.sanitize("<svg><rect")


def test_logo_answer_is_parsed_into_variants():
    text = """TITLE: AXIMBRA profilkép
=== VARIANT: Gyűrűs jel
<svg xmlns="http://www.w3.org/2000/svg"><rect width="1" height="1"/></svg>
=== VARIANT: Sima jel
```xml
<svg xmlns="http://www.w3.org/2000/svg"><circle r="1"/></svg>
```"""
    out = logomaker.parse(text)
    assert out["title"] == "AXIMBRA profilkép"
    assert [v["idea"] for v in out["variants"]] == ["Gyűrűs jel", "Sima jel"]
    assert out["variants"][1]["svg"].startswith("<svg") and out["variants"][1]["svg"].endswith("</svg>")


def test_logo_words_win_over_image_words():
    assert videomaker.pick_form("készíts egy kör alakú kép logót a profilképhez") == "logo"
    assert videomaker.pick_form("új profilkép az AXIMBRA oldalaknak") == "logo"
    assert videomaker.pick_form("egy kép a telefonos agentről") == "image"


def test_a_bad_variant_is_dropped_and_the_rest_kept(monkeypatch):
    good = '<svg xmlns="http://www.w3.org/2000/svg"><circle cx="1" cy="1" r="1"/></svg>'
    monkeypatch.setattr(llm, "_ask", lambda p: f"TITLE: T\n=== VARIANT: jó\n{good}\n=== VARIANT: rossz\n<svg><g/></svg>")
    d = videomaker.design_logos("AXIMBRA logó", {"pages": []}, "hu")
    assert [v["idea"] for v in d["variants"]] == ["jó"]


def test_logo_files_are_served_and_never_posted(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    import app as app_mod
    monkeypatch.setenv("ADMIN_PASSWORD", "jelszo1234")
    monkeypatch.setattr(videomaker, "VIDEO_DIR", str(tmp_path))
    vid = "abcdef012345"
    (tmp_path / f"{vid}-1.png").write_bytes(b"\\x89PNG")
    (tmp_path / f"{vid}-1.svg").write_text("<svg/>", encoding="utf-8")
    meta = {"id": vid, "form": "logo", "files": [f"{vid}-1.png"], "vectors": [f"{vid}-1.svg"],
            "title": "T", "created_at": "2026-01-01T00:00:00"}
    (tmp_path / f"{vid}.json").write_text(json.dumps(meta), encoding="utf-8")
    c, A = TestClient(app_mod.app), ("a", "jelszo1234")
    assert c.get(f"/api/videos/{vid}/1.png", auth=A).headers["content-type"] == "image/png"
    assert c.get(f"/api/videos/{vid}/1.jpg", auth=A).status_code == 404
    r = c.get(f"/api/videos/{vid}/1.svg", auth=A)
    assert r.status_code == 200 and "attachment" in r.headers["content-disposition"]
    assert "default-src 'none'" in r.headers["content-security-policy"]
    assert c.get(f"/api/videos/{vid}/2.svg", auth=A).status_code == 404
    assert c.post(f"/api/videos/{vid}/publish", json={"targets": ["instagram"]}, auth=A).status_code == 409
    assert videomaker.delete(vid) and list(tmp_path.iterdir()) == []


def test_logo_filters_get_a_region_wide_enough_for_the_blur():
    out = logomaker.sanitize('<svg xmlns="http://www.w3.org/2000/svg"><defs><filter id="f" x="0" y="0" '
                             'width="100%" height="100%" filterUnits="userSpaceOnUse"><feGaussianBlur '
                             'stdDeviation="40"/></filter></defs><circle r="5" filter="url(#f)"/></svg>')
    assert 'x="-75%"' in out and 'width="250%"' in out and "userSpaceOnUse" not in out


def test_linkedin_version_trails_the_calendar():
    from datetime import date
    assert publisher.li_version(date(2026, 9, 30)) == "202607"
    assert publisher.li_version(date(2027, 1, 5)) == "202611"
    assert publisher.li_version(date(2026, 2, 1)) == "202512"


def test_linkedin_goes_through_the_webhook_without_its_own_app(monkeypatch):
    for k in ("LI_ACCESS_TOKEN", "LI_AUTHOR_URN"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("LI_WEBHOOK_URL", "https://hook.eu2.make.com/abc")
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://pelda.hu")
    sent = []
    monkeypatch.setattr(publisher.httpx, "post", lambda url, json, timeout: sent.append((url, json)) or _Resp(200))
    assert publisher.li_ready() and publisher.li_missing() == []
    out = publisher.publish("linkedin", paths=["/a.jpg", "/b.jpg"], urls=["https://x/1.jpg", "https://x/2.jpg"],
                            caption="szöveg", title="T", form="carousel")
    assert out and len(sent) == 1
    url, body = sent[0]
    assert url == "https://hook.eu2.make.com/abc"
    assert body["image_urls"] == ["https://x/1.jpg", "https://x/2.jpg"] and body["first_image_url"] == "https://x/1.jpg"
    assert body["caption"] == "szöveg" and body["video_url"] == ""


def test_a_plain_http_webhook_is_not_trusted(monkeypatch):
    for k in ("LI_ACCESS_TOKEN", "LI_AUTHOR_URN"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("LI_WEBHOOK_URL", "http://hook.pelda.hu/abc")
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://pelda.hu")
    assert not publisher.li_ready()


def test_linkedin_text_carries_the_link_it_cannot_comment(tmp_path, monkeypatch):
    import app as app_mod
    monkeypatch.setattr(videomaker, "VIDEO_DIR", str(tmp_path))
    vid = "abcdef012345"
    (tmp_path / f"{vid}-1.jpg").write_bytes(b"x")
    meta = {"id": vid, "form": "image", "files": [f"{vid}-1.jpg"], "title": "T",
            "first_comment": "Élő demó: https://aximbra.hu", "created_at": "2026-01-01T00:00:00"}
    (tmp_path / f"{vid}.json").write_text(json.dumps(meta), encoding="utf-8")
    seen = {}
    monkeypatch.setattr(publisher, "publish", lambda t, **k: seen.setdefault(t, k["caption"]) and "ok")
    app_mod._post_video(vid, ["linkedin", "instagram"], "Poszt szöveg", lambda m: None)
    assert seen["linkedin"] == "Poszt szöveg\n\nÉlő demó: https://aximbra.hu"
    assert seen["instagram"] == "Poszt szöveg"


def test_a_voice_that_runs_out_midway_is_replaced_for_the_whole_video(monkeypatch):
    import io, wave as wv

    def tone():
        buf = io.BytesIO()
        with wv.open(buf, "wb") as w:
            w.setnchannels(1); w.setsampwidth(2); w.setframerate(videomaker.SAMPLE_RATE)
            w.writeframes(b"\x01\x00" * videomaker.SAMPLE_RATE)
        return buf.getvalue()
    calls = {"gemini": 0}

    def gemini(t, lang):
        calls["gemini"] += 1
        return tone() if calls["gemini"] == 1 else None      # a napi keret az 1. jelenet után elfogy
    monkeypatch.setattr(videomaker, "_tts_elevenlabs", lambda t, l, m: None)
    monkeypatch.setattr(videomaker, "_tts_gemini", gemini)
    monkeypatch.setattr(videomaker, "_tts_edge", lambda t, l, m: tone())
    script = {"scenes": [{"voice": "egy", "seconds": 3.0}, {"voice": "kettő", "seconds": 3.0}]}
    audio, engine = videomaker.narrate(script, "hu", False)
    assert audio and engine == "edge"


def test_the_post_text_is_checked_for_invented_claims_too():
    script = videomaker.normalize({"title": "T", "scenes": [
        {"kind": "hook", "headline": "Ki veszi fel?", "seconds": 3},
        {"kind": "statement", "headline": "Az agent felveszi", "seconds": 3}],
        "post": "Azonnali válasz és nulla elvesztett érdeklődő. Próbálja ki élőben!\n\nhttps://aximbra.hu"}, 30)
    v = videomaker.violations(script, "")
    assert any("nulla" in x for x in v)
    out = videomaker._strip_claims(script, "")
    assert "nulla" not in out["post"] and "Próbálja ki élőben!" in out["post"] and "https://aximbra.hu" in out["post"]


def test_call_lines_lose_trailing_speaker_labels_and_urls_their_protocol():
    s = videomaker.normalize({"title": "T", "scenes": [
        {"kind": "call", "headline": "Hívás", "lines": ["Jó napot, miben segíthetek? |AI agent",
                                                         "Ajánlatot kérnék.| Érdeklődő"], "seconds": 5},
        {"kind": "inbox", "headline": "Posta", "lines": ["Árajánlat|Értékesítés"], "seconds": 5},
        {"kind": "cta", "headline": "Próbálja ki", "url": "https://www.aximbra.hu/", "seconds": 4}]}, 30)
    assert s["scenes"][0]["lines"] == ["Jó napot, miben segíthetek?", "Ajánlatot kérnék."]
    assert s["scenes"][1]["lines"] == ["Árajánlat|Értékesítés"]      # a postafiók címkéje marad
    assert s["scenes"][-1]["url"] == "aximbra.hu"


def test_english_words_are_respelled_for_the_hungarian_voice_only():
    say = videomaker.spoken
    assert say("A telefonos AI agent azonnal fogadja a hívást.", "hu") == "A telefonos éjáj édzsent azonnal fogadja a hívást."
    assert say("Az e-mail rendező agentje rendezi az inboxot.", "hu") == "Az ímél rendező édzsentje rendezi az inbokszot."
    assert say("Próbálja ki: aximbra.hu, AXIMBRA agentek kkv-knak.", "hu") == \
        "Próbálja ki: akszimbra pont hu, Akszimbra édzsentek kákávé-knak."
    assert say("Our AI agent", "en") == "Our AI agent"


# ---- kutatott marketingszabályok ----

def _craft_script(**kw):
    raw = {"title": "T", "brand": "AXIMBRA", "scenes": [
        {"kind": "hook", "headline": "Ki veszi fel a telefont?", "seconds": 6},
        {"kind": "statement", "headline": "Az AXIMBRA agentje felveszi", "voice": "Ezt mondja.", "seconds": 5},
        {"kind": "benefit", "headline": "Mit kap?", "lines": ["Kevesebb elveszett hívás"], "seconds": 5},
        {"kind": "cta", "headline": "Próbálja ki", "url": "aximbra.hu", "seconds": 4},
    ], "post": "Ki veszi fel a telefont este?\n\nSzöveg. #ai #kkv #agent #automatizalas #magyar"}
    raw.update(kw)
    return videomaker.normalize(raw, 30)


def test_hook_is_short_and_hashtags_capped():
    s = _craft_script()
    assert s["scenes"][0]["seconds"] <= videomaker.HOOK_MAX
    assert s["post"].count("#") == 3 and "#automatizalas" not in s["post"]
    assert videomaker.craft_issues(s) == []


def test_craft_issues_catch_broken_rules():
    s = _craft_script(post="x" * 200)
    s["scenes"][0]["kind"] = "agents"
    s["scenes"][1]["headline"] = "Egy nagyon hosszú címsor ami bőven több mint nyolc szóból áll"
    s["scenes"][2]["headline"], s["scenes"][2]["sub"], s["scenes"][2]["lines"] = "", "", []
    s["scenes"][2]["voice"] = "Csak hangban mondjuk el."
    issues = " | ".join(videomaker.craft_issues(s))
    assert "első jelenet" in issues and "8 szónál" in issues and "hang nélkül" in issues and "első sora" in issues


def test_brand_must_appear_before_the_close():
    s = _craft_script()
    s["scenes"][1]["headline"] = "Az agent felveszi"
    s["post"] = "Ki veszi fel?"
    assert any("márkanév" in x for x in videomaker.craft_issues(s))


def test_check_sends_craft_problems_to_one_revision(monkeypatch):
    s = _craft_script(post="y" * 200)
    asked = []
    fixed = {"title": "T", "brand": "AXIMBRA", "scenes": [
        {"kind": "hook", "headline": "Ki veszi fel?", "seconds": 3},
        {"kind": "statement", "headline": "Az AXIMBRA felveszi", "seconds": 5},
        {"kind": "cta", "headline": "Próbálja ki", "url": "aximbra.hu", "seconds": 4}], "post": "Ki veszi fel este?"}
    monkeypatch.setattr(llm, "_ask", lambda p, **k: asked.append(p) or json.dumps(fixed))
    out = videomaker.check(s, "brief", {"urls": [], "pages": [], "web": []}, 30, "hu")
    assert len(asked) == 1 and "első sora" in asked[0] and "PROVEN CRAFT RULES" in asked[0]
    assert out["post"] == "Ki veszi fel este?"


def test_daily_mode_runs_once_after_the_hour_and_retries_a_failed_day(cfg):
    # 2026-10-05 06:30 UTC = 08:30 Budapest (nyári idő, UTC+2)
    now = datetime(2026, 10, 5, 6, 30, tzinfo=timezone.utc)
    on = {**cfg.DEFAULTS, "auto": True, "briefs": ["a"], "daily_hour": 8}
    assert cfg.due(now, on)
    assert not cfg.due(now, {**on, "daily_hour": 9})                     # még nincs itt az idő
    assert not cfg.due(now, {**on, "done_day": "2026-10-05"})            # ma már kiment
    assert cfg.due(now, {**on, "done_day": "2026-10-04"})
    failed = {**on, "last_run": (now - timedelta(hours=1)).isoformat()}
    assert not cfg.due(now, failed)                                      # elhasalt: vár
    assert cfg.due(now + timedelta(hours=cfg.RETRY_HOURS), failed)       # aztán újra próbál
    assert cfg.clean({"daily_hour": 99})["daily_hour"] == 23
    assert cfg.clean({"daily_hour": -5})["daily_hour"] == -1
    cfg.mark_done(now)
    assert cfg.load()["done_day"] == "2026-10-05"


def test_instagram_via_its_own_webhook(monkeypatch):
    for v in ("IG_USER_ID", "IG_ACCESS_TOKEN", "LI_ACCESS_TOKEN", "LI_AUTHOR_URN"):
        monkeypatch.delenv(v, raising=False)
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://x.example")
    monkeypatch.setenv("IG_WEBHOOK_URL", "https://hook.example/ig")
    monkeypatch.setenv("LI_WEBHOOK_URL", "https://hook.example/li")
    assert publisher.ig_ready() and publisher.ig_missing() == []
    sent = []

    class R:
        status_code = 200
        text = "Accepted"

    monkeypatch.setattr(publisher.httpx, "post", lambda url, json, timeout: sent.append((url, json)) or R())
    publisher.publish("instagram", paths=["/a.mp4"], urls=["https://x.example/p/1.mp4"],
                      caption="x" * 3000, form="video")
    url, body = sent[0]
    assert url == "https://hook.example/ig" and body["platform"] == "instagram"   # nem a LinkedIn-útra megy
    assert len(body["caption"]) == 2200 and body["video_url"].endswith(".mp4")


def test_inbox_dedupes_validates_and_retries(tmp_path, monkeypatch):
    import inbox
    monkeypatch.setattr(inbox, "PATH", str(tmp_path / "inbox.json"))
    now = datetime(2026, 10, 5, 6, tzinfo=timezone.utc)
    body = {"id": "sales-2026-10-05-hu", "brief": "Álló videó a közös postafiókról, kkv-vezetőknek.",
            "lang": "hu", "targets": ["linkedin", "tiktok"]}
    it, new = inbox.add(body, now)
    assert new and it["targets"] == ["linkedin"] and it["form"] == "auto"
    assert inbox.add(body, now) == (it, False)                         # újraküldés: nincs dupla
    for bad in ({**body, "id": "x"}, {**body, "brief": "rövid"}, {**body, "lang": "de"}, {**body, "targets": []}):
        with pytest.raises(inbox.InboxError):
            inbox.add({**bad, "id": bad["id"] if bad["id"] == "x" else "id-" + bad["lang"] + str(len(bad["targets"]))}, now)
    assert inbox.next_due(now)["id"] == it["id"]
    inbox.update(it["id"], tries=1, last_try=now.isoformat())
    assert inbox.next_due(now) is None                                  # elhasalt: vár egy órát
    assert inbox.next_due(now + inbox.RETRY_AFTER)["id"] == it["id"]
    assert inbox.update(it["id"], tries=2)["status"] == "failed"        # két próba után feladja
    assert inbox.next_due(now + timedelta(days=1)) is None


def test_elevenlabs_voice_per_language(monkeypatch):
    for v in ("ELEVENLABS_VOICE_ID", "ELEVENLABS_VOICE_ID_HU", "ELEVENLABS_VOICE_ID_EN", "ELEVENLABS_VOICE_ID_MALE"):
        monkeypatch.delenv(v, raising=False)
    assert videomaker.elevenlabs_voice("hu") == "FGY2WhTYpPnrIDTdsKH5"      # Laura
    assert videomaker.elevenlabs_voice("en") == "hpp4J3VqNfWAUOO0d1Us"      # Bella
    monkeypatch.setenv("ELEVENLABS_VOICE_ID_EN", "x1")
    monkeypatch.setenv("ELEVENLABS_VOICE_ID_MALE", "m1")
    assert videomaker.elevenlabs_voice("en") == "x1"
    assert videomaker.elevenlabs_voice("hu", male=True) == "m1"


def test_inbox_can_hold_a_long_video_for_approval(tmp_path, monkeypatch):
    """Egy összefoglaló videó 90 mp, és nem posztolódik magától: a panelen
    vár jóváhagyásra. Cél nélkül csak így fogadható el."""
    import inbox
    monkeypatch.setattr(inbox, "PATH", str(tmp_path / "inbox.json"))
    now = datetime(2026, 10, 8, 9, tzinfo=timezone.utc)
    body = {"id": "sales-summary-1", "brief": "Összefoglaló videó az aximbra.hu oldalról, végig az oldallal.",
            "lang": "hu", "targets": [], "hold": True, "seconds": 150, "form": "video"}
    it, new = inbox.add(body, now)
    assert new and it["hold"] is True and it["seconds"] == 120 and it["targets"] == []
    with pytest.raises(inbox.InboxError):
        inbox.add({**body, "id": "sales-summary-2", "hold": False}, now)    # cél és jóváhagyás nélkül nem
    plain, _ = inbox.add({**body, "id": "sales-daily", "hold": False, "targets": ["linkedin"],
                          "seconds": None}, now)
    assert plain["seconds"] is None and plain["hold"] is False           # a napi témák úgy futnak, mint eddig


def test_a_held_item_is_rendered_but_never_posted(tmp_path, monkeypatch):
    import app as video_app
    import inbox
    monkeypatch.setattr(inbox, "PATH", str(tmp_path / "inbox.json"))
    it, _ = inbox.add({"id": "sales-summary-3", "brief": "Összefoglaló videó az aximbra.hu oldalról, 90 mp.",
                       "lang": "hu", "targets": ["linkedin"], "hold": True, "seconds": 90, "form": "video"})
    made = {}

    def make(brief, seconds, *a, **k):
        made["seconds"] = seconds
        return {"id": "v1", "post": ""}
    monkeypatch.setattr(video_app.videomaker, "make", make)
    monkeypatch.setattr(video_app, "_post_video", lambda *a, **k: pytest.fail("jóváhagyás nélkül posztolt"))
    said = []
    video_app._inbox_round(inbox.next_due())(said.append)
    assert made["seconds"] == 90
    assert inbox._load()[0]["status"] == "done" and inbox._load()[0]["video"] == "v1"
    assert any("jóváhagyásra vár" in m for m in said)


def test_up_to_six_site_sections_are_captured_and_read_once(monkeypatch):
    import websearch
    reads = []
    monkeypatch.setattr(websearch, "read_page", lambda u: reads.append(u) or {"text": "x" * 100})
    monkeypatch.setattr(videomaker.media, "listing", lambda: [])
    brief = ("Végig az oldallal: https://aximbra.hu https://aximbra.hu/#agentek https://aximbra.hu/#folyamat "
             "https://aximbra.hu/#megterules https://aximbra.hu/#eset https://epistemebudapest.up.railway.app "
             "https://hetedik.example.com")
    ctx = videomaker.gather(brief, research=False)
    assert len(ctx["urls"]) == 6 and ctx["urls"][1] == "https://aximbra.hu/#agentek"
    assert reads == ["https://aximbra.hu", "https://epistemebudapest.up.railway.app"]


def test_no_url_or_scene_number_reaches_the_screen():
    """Élesben a rendező a briefből a „2. jelenet" címkét és a
    https://aximbra.hu/#agentek címet tette a képernyőre, levágva."""
    data = {"scenes": [
        {"kind": "site", "kicker": "2. jelenet", "headline": "https://aximbra.hu/#agentek",
         "sub": "15 agent-típus — https://aximbra.hu/#agentek", "shot": 1,
         "voice": "Nézze meg: https://aximbra.hu", "seconds": 8},
        {"kind": "statement", "kicker": "Jelenet 3", "headline": "Élő *demók* regisztráció nélkül", "seconds": 6},
        {"kind": "cta", "headline": "Próbálja ki", "url": "https://aximbra.hu/", "seconds": 4}]}
    out = videomaker.normalize(data, 30, n_shots=2)
    site, stmt, cta = out["scenes"]
    assert site["kicker"] == "" and stmt["kicker"] == ""
    assert "http" not in site["headline"] and "aximbra.hu" not in site["sub"]
    assert site["sub"] == "15 agent-típus"
    assert "http" not in site["voice"] and "aximbra.hu" in site["voice"]       # a narráció a domaint kimondhatja
    assert cta["url"] == "aximbra.hu"                                          # a záróképen marad a cím


def test_the_same_page_is_never_shown_twice():
    """Kétszer ugyanaz az oldalrész, csak más narrációval: a második egy még
    nem használt felvételre vált, vagy szöveges jelenet lesz."""
    scene = lambda shot, h: {"kind": "site", "headline": h, "shot": shot, "seconds": 6}
    data = {"scenes": [scene(0, "Egy"), scene(0, "Kettő"), scene(0, "Három"),
                       {"kind": "cta", "headline": "Vége", "seconds": 4}]}
    out = videomaker.normalize(data, 30, n_shots=2)
    shots = [(s["kind"], s["shot"]) for s in out["scenes"][:3]]
    assert shots[0] == ("site", 0) and shots[1] == ("site", 1) and shots[2][0] == "statement"


def test_a_two_minute_video_keeps_its_length_and_more_scenes():
    data = {"scenes": [{"kind": "statement", "headline": f"Jelenet szöveg {i}", "seconds": 9} for i in range(14)]
            + [{"kind": "cta", "headline": "Vége", "seconds": 5}]}
    out = videomaker.normalize(data, 120, n_shots=0)
    assert len(out["scenes"]) == 15
    assert abs(sum(s["seconds"] for s in out["scenes"]) - 120) < 1.5
    short = videomaker.normalize(data, 60, n_shots=0)
    assert len(short["scenes"]) == videomaker.MAX_SCENES + 1                  # 10 + záró


def test_an_sms_confirmation_scene_survives_in_a_video_but_not_on_a_still():
    data = {"scenes": [{"kind": "sms", "headline": "A *visszaigazolás* azonnal megy", "caller": "EPISTEME",
                        "lines": ["Foglalását rögzítettük: péntek 19:00, 2 fő."], "seconds": 6},
                       {"kind": "cta", "headline": "Vége", "seconds": 4}]}
    vid = videomaker.normalize(data, 20, n_shots=0)
    assert vid["scenes"][0]["kind"] == "sms" and vid["scenes"][0]["caller"] == "EPISTEME"
    still = videomaker.normalize(data, 20, n_shots=0, form="carousel")
    assert still["scenes"][0]["kind"] == "statement"
    assert '"sms"' in videomaker.director_prompt("x", {"urls": [], "pages": [], "web": [], "library": []}, 30, "hu", "9:16", True)


def test_a_long_recording_is_cut_into_stretches_with_speed(monkeypatch):
    """Egy 75 mp-es felvétel több jelenetre bontva: a várakozás gyorsítva, az
    eredmény 1×. Ami nem fér a felvétel végéig, gyorsul vagy rövidül."""
    clip = {"id": "c" * 12, "kind": "clip", "seconds": 75.0, "width": 720, "height": 1560, "name": "rec"}
    monkeypatch.setattr(videomaker.media, "get", lambda mid: clip if mid == clip["id"] else None)
    data = {"scenes": [
        {"kind": "clip", "media": clip["id"], "from": 0, "speed": 3, "seconds": 5, "layout": "phone", "headline": "Beérkezik"},
        {"kind": "clip", "media": clip["id"], "from": 15, "speed": 1, "seconds": 6, "layout": "phone", "headline": "Kész"},
        {"kind": "clip", "media": clip["id"], "from": 70, "speed": 1, "seconds": 9, "layout": "phone", "headline": "Vége"},
        {"kind": "cta", "headline": "Próbálja ki", "seconds": 4}]}
    out = videomaker.normalize(data, 24, n_shots=0)
    a, b, c = out["scenes"][:3]
    assert (a["from"], a["speed"], a["layout"]) == (0.0, 3.0, "phone")
    assert (b["from"], b["speed"]) == (15.0, 1.0)
    assert c["from"] == 70.0 and c["seconds"] * c["speed"] <= 5.0 + 1e-6      # a felvétel végéig fér
    for s in (a, b, c):
        assert s["from"] + s["seconds"] * s["speed"] <= 75.0 + 1e-6


def test_the_director_sees_clip_segments_and_must_use_attachments(monkeypatch):
    clip = {"id": "d" * 12, "kind": "clip", "seconds": 75.0, "width": 720, "height": 1560, "name": "email-agent",
            "segments": [{"from": 0, "to": 12, "what": "bejelentkezés, töltés", "pace": "wait"},
                         {"from": 12, "to": 20, "what": "a levelek kategóriát kapnak", "pace": "result"}]}
    monkeypatch.setattr(videomaker.media, "get", lambda mid: clip if mid == clip["id"] else None)
    ctx = {"urls": [], "pages": [], "web": [], "library": [clip], "attached": [clip["id"]]}
    p = videomaker.director_prompt("Összefoglaló", ctx, 120, "hu", "9:16", True)
    assert "75 s, tall/phone recording" in p and "0–12 s  wait: bejelentkezés, töltés" in p
    assert "THE USER ATTACHED THESE" in p and p.count(clip["id"]) >= 2
    assert '"from": 0, "speed": 1' in p and "4×" in p


def test_clip_segments_are_cleaned_and_a_failed_analysis_keeps_the_clip(monkeypatch):
    import media
    segs = media._clean_segments([{"from": 0, "to": 6, "what": "töltés", "pace": "wait"},
                                  {"from": 6, "to": 6.2, "what": "túl rövid", "pace": "result"},
                                  {"from": "x", "to": 9}, {"from": 9, "to": 99, "what": "lista", "pace": "?"}], 75)
    assert [(s["from"], s["to"], s["pace"]) for s in segs] == [(0.0, 6.0, "wait"), (9.0, 75.0, "action")]

    class R:
        returncode = 1
    monkeypatch.setattr(media, "_run", lambda *a, **k: R())
    assert media.analyse_clip("/nincs.webm", 75) == []


def test_attached_media_reaches_the_director(monkeypatch):
    seen = {}
    img = {"id": "e" * 12, "kind": "image", "name": "kep"}
    monkeypatch.setattr(videomaker.media, "get", lambda mid: img if mid == img["id"] else None)
    monkeypatch.setattr(videomaker, "gather", lambda brief, research, say: {"urls": [], "pages": [], "web": [], "library": [img]})

    def write(brief, ctx, *a, **k):
        seen["attached"] = ctx.get("attached")
        raise videomaker.VideoError("eddig kellett")
    monkeypatch.setattr(videomaker, "write_script", write)
    with pytest.raises(videomaker.VideoError):
        videomaker.make("Összefoglaló videó", 60, form="video", attach=[img["id"], "nincsilyen123"])
    assert seen["attached"] == [img["id"]]


# ---- személyes adatok elmosása ------------------------------------------------

def test_redaction_follows_a_scrolling_line_between_samples():
    """Görgetésnél a sor két minta között is takarva marad: a helyét
    arányosan számoljuk, és ami csak az egyik mintán van, azt a görgetés
    irányában toljuk."""
    import redact
    samples = [{"t": 0.0, "lines": [{"text": "Kovács Anna", "box": [10, 300, 200, 330]},
                                    {"text": "Beérkezett levelek", "box": [10, 20, 300, 50]}]},
               {"t": 1.0, "lines": [{"text": "Kovács Anna", "box": [10, 100, 200, 130]},
                                    {"text": "Szabó Péter", "box": [10, 600, 200, 630]}]}]
    steps = redact.plan(samples, {"kovács anna", "szabó péter"}, 1.0)
    mid = redact.boxes_at(steps, 0.5)
    covers = lambda want: any(b[0] <= want[0] and b[1] <= want[1] and b[2] >= want[2] and b[3] >= want[3] for b in mid)
    assert covers([10, 200, 200, 230])                     # félúton a két hely között
    assert covers([10, 700, 200, 730])                     # a később bejövő sor, visszafelé tolva (t=0-kor 800-on)
    assert not any(b[1] <= 20 <= b[3] and b[1] > -50 for b in mid if b[3] < 100)  # a felület szövege nem takart
    still = redact.plan([{"t": 0.0, "lines": [{"text": "Kovács Anna", "box": [10, 300, 200, 330]}]},
                         {"t": 1.0, "lines": [{"text": "Kovács Anna", "box": [10, 300, 200, 330]}]}], {"kovács anna"}, 1.0)
    assert redact.boxes_at(still, 0.5) == [[10, 300, 200, 330]]   # állóképen nem nő a takarás


def test_rules_catch_emails_and_phones_and_the_model_names(monkeypatch):
    import redact
    monkeypatch.setattr(redact.llm if hasattr(redact, "llm") else __import__("llm"), "_ask",
                        lambda prompt: '{"ids": [0]}')
    hit = redact.classify(["Kovács Anna", "kovacs.anna@fenyves.hu", "+36 30 123 4567", "Beérkezett", "AXIMBRA"])
    assert "kovacs.anna@fenyves.hu" in hit and "+36 30 123 4567" in hit
    assert "kovács anna" in hit and "beérkezett" not in hit and "aximbra" not in hit


def test_without_the_model_capitalised_name_pairs_are_still_blurred(monkeypatch):
    import llm as video_llm
    import redact

    def boom(prompt):
        raise video_llm.LLMError("nincs modell")
    monkeypatch.setattr(video_llm, "_ask", boom)
    hit = redact.classify(["Kovács Anna", "Számla korrekció", "toth@ceg.hu"])
    assert hit == {"kovács anna", "toth@ceg.hu"}


def test_a_clip_is_unusable_until_redacted_and_stays_out_if_it_fails(tmp_path, monkeypatch):
    import media
    import redact
    monkeypatch.setattr(media, "MEDIA_DIR", str(tmp_path))
    monkeypatch.setattr(media, "_start_processing", lambda mid: None)       # kézzel futtatjuk
    monkeypatch.setattr(media, "analyse_clip", lambda path, secs: [])

    class R:
        returncode = 0
    def fake_run(args, timeout=180):
        open(args[-1], "wb").write(b"webm")
        return R()
    monkeypatch.setattr(media, "_run", fake_run)
    monkeypatch.setattr(media, "_probe", lambda p: {"width": 720, "height": 1560, "seconds": 75.0})
    m = media.add_clip(b"x" * 10, "felvetel.mp4")
    assert m["status"] == "processing" and not media.ready(media.get(m["id"]))
    monkeypatch.setattr(redact, "redact_clip", lambda path, say=None: 12)
    media._process_clip(m["id"])
    assert media.ready(media.get(m["id"])) and media.get(m["id"])["redacted"] == 12

    m2 = media.add_clip(b"y" * 10, "masik.mp4")
    def fail(path, say=None):
        raise redact.RedactError("nincs szövegfelismerő")
    monkeypatch.setattr(redact, "redact_clip", fail)
    media._process_clip(m2["id"])
    assert media.get(m2["id"])["status"] == "failed" and not media.ready(media.get(m2["id"]))
    # a hibás klip a videóból is kimarad
    data = {"scenes": [{"kind": "clip", "media": m2["id"], "headline": "Felvétel", "seconds": 5},
                       {"kind": "cta", "headline": "Vége", "seconds": 4}]}
    out = videomaker.normalize(data, 10, n_shots=0)
    assert out["scenes"][0]["kind"] == "statement"


@pytest.mark.skipif(not __import__("redact").available(), reason="nincs tesseract")
def test_a_screenshot_loses_its_names_and_emails(tmp_path, monkeypatch):
    """Valódi szövegfelismeréssel: a képen a név és az e-mail-cím elmosódik,
    a felület szövege olvasható marad."""
    import llm as video_llm
    import redact
    from PIL import Image, ImageDraw, ImageFont
    monkeypatch.setattr(video_llm, "_ask", lambda prompt: (_ for _ in ()).throw(video_llm.LLMError("x")))
    font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 26)
    img = Image.new("RGB", (720, 400), (12, 15, 26))
    d = ImageDraw.Draw(img)
    d.text((30, 40), "Beérkezett levelek", font=font, fill=(230, 236, 250))
    d.text((30, 140), "Kovács Anna", font=font, fill=(235, 240, 255))
    d.text((30, 200), "kovacs.anna@fenyvesbutor.hu", font=font, fill=(160, 175, 210))
    p = str(tmp_path / "s.jpg")
    img.save(p, quality=95)
    assert redact.redact_image(p) >= 2
    text = " ".join(l["text"] for l in redact.ocr_lines(p))
    assert "Kovács" not in text and "@" not in text and "Beérkezett" in text


def test_only_the_own_account_stays_readable_and_email_content_is_blurred(monkeypatch):
    """A fiókválasztóban csak az aximbra-s fiók látszik; az agent futásakor a
    küldő, a tárgy és az összefoglaló is elmosódik, a felület felirata nem."""
    import llm as video_llm
    import redact
    seen = {}

    def ask(prompt):
        seen["prompt"] = prompt
        lines = dict(l.split(": ", 1) for l in prompt.split("LINES (id: text):\n")[1].split("\n\nAnswer")[0].splitlines())
        return '{"blur": [%s]}' % ",".join(i for i, t in lines.items()
                                          if t in ("kovács anna", "elmaradt szállítás – 3. nap", "a feladó panaszkodik a késésre"))
    monkeypatch.setattr(video_llm, "_ask", ask)
    hit = redact.classify(["Válasszon fiókot", "aximbra@gmail.com", "AXIMBRA", "kovacs.anna@gmail.com", "Kovács Anna",
                           "Elmaradt szállítás – 3. nap", "A feladó panaszkodik a késésre", "Ügyfél – panasz", "Sürgős"])
    assert "aximbra@gmail.com" not in hit and "aximbra" not in hit                  # a saját fiók látszik
    assert {"kovacs.anna@gmail.com", "kovács anna", "elmaradt szállítás – 3. nap", "a feladó panaszkodik a késésre"} <= hit
    assert not {"válasszon fiókot", "ügyfél – panasz", "sürgős"} & hit             # a felület olvasható
    assert "aximbra" not in seen["prompt"].split("LINES (id: text):")[1]          # a sajátot meg sem kérdezzük


def test_without_the_model_long_lines_count_as_content(monkeypatch):
    import llm as video_llm
    import redact
    monkeypatch.setattr(video_llm, "_ask", lambda p: (_ for _ in ()).throw(video_llm.LLMError("x")))
    hit = redact.classify(["Beérkezett levelek", "Árajánlatkérés 250 db éves keretszerződésre", "Válasz szükséges",
                           "A szállítás három napja késik, kérem segítsenek"])
    assert hit == {"árajánlatkérés 250 db éves keretszerződésre", "a szállítás három napja késik, kérem segítsenek"}


def test_uploads_from_before_the_redaction_are_reprocessed(tmp_path, monkeypatch):
    import json
    import media
    import redact
    monkeypatch.setattr(media, "MEDIA_DIR", str(tmp_path))
    started = []
    monkeypatch.setattr(media, "_start_processing", lambda mid: started.append(mid))
    monkeypatch.setattr(media.threading, "Thread", lambda target, args, daemon: type("T", (), {"start": lambda self: started.append(args[0])})())
    def put(mid, **meta):
        open(tmp_path / f"{mid}.webm", "wb").write(b"x")
        json.dump({"id": mid, "file": f"{mid}.webm", "created_at": "2026-10-08", **meta}, open(tmp_path / f"{mid}.json", "w"))
    put("a" * 12, kind="clip", source="upload")                                           # elmosás előtti feltöltés
    put("b" * 12, kind="clip", source="upload", redact=True, redact_v=1, status="ready")  # enyhébb szabály
    put("c" * 12, kind="clip", source="upload", redact=True, redact_v=redact.POLICY_VERSION, status="ready")
    put("d" * 12, kind="clip", source="upload", redact=False, status="ready")             # a feltöltő kikapcsolta
    put("e" * 12, kind="image", source="generated")                                       # AI-kép
    assert media.resume_pending() == 2
    assert sorted(started) == ["a" * 12, "b" * 12]
    assert not media.ready(media.get("a" * 12)) and media.ready(media.get("c" * 12))


def test_the_director_gets_the_on_screen_text_to_translate(monkeypatch):
    clip = {"id": "f" * 12, "kind": "clip", "seconds": 60.0, "width": 720, "height": 1560, "name": "en-felvetel",
            "segments": [{"from": 5, "to": 12, "what": "Google figyelmeztetés", "pace": "action",
                          "screen_text": "A Google nem ellenőrizte ezt az alkalmazást", "screen_lang": "hu"}]}
    p = videomaker.director_prompt("English summary", {"urls": [], "pages": [], "web": [], "library": [clip]},
                                   60, "en", "9:16", True)
    assert 'on screen (hu): "A Google nem ellenőrizte ezt az alkalmazást"' in p and "SUBTITLES" in p


@pytest.mark.skipif(not __import__("redact").available(), reason="nincs tesseract")
def test_account_chooser_shows_only_the_aximbra_account(tmp_path, monkeypatch):
    import llm as video_llm
    import redact
    from PIL import Image, ImageDraw, ImageFont
    monkeypatch.setattr(video_llm, "_ask", lambda p: (_ for _ in ()).throw(video_llm.LLMError("x")))
    f = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 26)
    img = Image.new("RGB", (720, 520), (255, 255, 255))
    d = ImageDraw.Draw(img)
    d.text((30, 30), "Válasszon fiókot", font=f, fill=(30, 30, 30))
    d.text((30, 140), "aximbra@gmail.com", font=f, fill=(60, 60, 60))
    d.text((30, 260), "Kovács Anna", font=f, fill=(30, 30, 30))
    d.text((30, 310), "kovacs.anna@gmail.com", font=f, fill=(60, 60, 60))
    p = str(tmp_path / "chooser.jpg")
    img.save(p, quality=95)
    redact.redact_image(p)
    text = " ".join(l["text"] for l in redact.ocr_lines(p))
    assert "aximbra@gmail.com" in text and "Válasszon" in text
    assert "Kovács" not in text and "kovacs" not in text


@pytest.mark.skipif(not __import__("redact").available(), reason="nincs tesseract")
def test_dim_secondary_text_is_found_and_blurred(tmp_path, monkeypatch):
    """Élesben a halványszürke összefoglaló sor („Zoltán Fábián sent a message
    on LinkedIn.") kimaradt: a sima és a megfordított kép nem elég hozzá."""
    import llm as video_llm
    import redact
    from PIL import Image, ImageDraw, ImageFont
    monkeypatch.setattr(video_llm, "_ask", lambda p: (_ for _ in ()).throw(video_llm.LLMError("x")))
    f = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 30)
    img = Image.new("RGB", (900, 260), (11, 15, 26))
    ImageDraw.Draw(img).text((40, 100), "Zoltán Fábián sent a message on", font=f, fill=(74, 85, 120))
    p = str(tmp_path / "dim.png")
    img.save(p)
    assert redact.redact_image(p) >= 1
    assert "Fábián" not in " ".join(l["text"] for l in redact.ocr_lines(p))


def test_the_redacted_clip_is_written_next_to_the_original(tmp_path, monkeypatch):
    """Élesben a kész elmosás a /tmp → /data átnevezésen hasalt el (két külön
    lemez). A kész fájl most a végleges mellé készül, és onnan cserél."""
    import redact
    src = open(redact.__file__, encoding="utf-8").read()
    assert 'out = path + ".redacting.webm"' in src
    assert 'os.path.join(d, "out.webm")' not in src


def test_upload_returns_at_once_and_conversion_runs_in_the_background(tmp_path, monkeypatch):
    """Élesben egy 75 mp-es felvétel „Load failed"-del elhasalt: a feltöltés
    megvárta az átalakítást. Most a kérés a mentés után visszatér."""
    import media
    monkeypatch.setattr(media, "MEDIA_DIR", str(tmp_path))
    started = []
    monkeypatch.setattr(media, "_start_processing", lambda mid: started.append(mid))
    monkeypatch.setattr(media, "_run", lambda *a, **k: pytest.fail("a feltöltés nem alakíthat át"))
    m = media.add_clip(b"raw-mov-bytes", "felvetel.mov")
    assert started == [m["id"]] and m["status"] == "processing"
    assert (tmp_path / m["raw"]).exists() and media.get(m["id"])["id"] == m["id"]
    assert [x["id"] for x in media.listing()] == [m["id"]]        # látszik a tárban, amíg dolgozik

    class R:
        returncode = 0
    monkeypatch.setattr(media, "_run", lambda args, timeout=180: open(args[-1], "wb").write(b"webm") and R())
    monkeypatch.setattr(media, "_probe", lambda p: {"width": 720, "height": 1560, "seconds": 75.4})
    monkeypatch.setattr(media, "analyse_clip", lambda p, s: [])
    import redact
    monkeypatch.setattr(redact, "redact_clip", lambda p, say=None: 9)
    media._process_clip(m["id"])
    done = media.get(m["id"])
    assert done["status"] == "ready" and done["seconds"] == 75.4 and "raw" not in done
    assert not (tmp_path / m["raw"]).exists()                     # az elmosatlan eredeti nem marad meg


def test_caption_requests_are_recognised():
    off = ["vedd ki a feliratot", "Ne legyen felirat a videón", "felirat nélkül", "remove the subtitles",
           "Rövidebb nyitás. Vegye ki a feliratokat!"]
    assert all(videomaker.wants_captions(t) is False for t in off)
    assert videomaker.wants_captions("kapcsold be a feliratot") is True
    assert videomaker.wants_captions("legyen rajta felirat") is True
    # Nem a narráció felirata: a méretre vagy a fordító feliratra vonatkozó kérés.
    for t in ("rövidebb nyitás", "a feliratok legyenek nagyobbak", "A Google-képernyőkhöz angol feliratot tegyen."):
        assert videomaker.wants_captions(t) is None


def test_revise_turns_captions_off_without_rewriting_the_script(tmp_path, monkeypatch):
    import json as _json
    monkeypatch.setattr(videomaker, "VIDEO_DIR", str(tmp_path))
    (tmp_path / "abcdef012345.mp4").write_bytes(b"x")
    scenes = [{"kind": "hook", "headline": "Hány órát?", "voice": "Hány órát veszít a csapatod?", "seconds": 3}]
    (tmp_path / "abcdef012345.json").write_text(_json.dumps({
        "id": "abcdef012345", "title": "T", "theme": "clean", "scenes": scenes,
        "opts": {"brief": "E-mail rendező videó", "seconds": 20, "lang": "hu", "aspect": "9:16", "voice": False,
                 "male": False, "research": False, "form": "video"}, "ctx_urls": []}), encoding="utf-8")

    def no_llm(*a, **k):
        raise AssertionError("a felirat kikapcsolásához nem kell új forgatókönyv")

    monkeypatch.setattr(llm, "_ask", no_llm)
    seen = {}

    def fake_render(script, urls, out, aspect, audio, captions, say):
        seen["captions"] = captions
        seen["headline"] = script["scenes"][0]["headline"]
        open(out, "wb").write(b"mp4")
        return 20.0

    monkeypatch.setattr(videomaker, "render", fake_render)
    m = videomaker.revise("abcdef012345", "Vedd ki a feliratot!")
    assert seen == {"captions": False, "headline": "Hány órát?"}
    assert m["opts"]["captions"] is False and m["parent"] == "abcdef012345"
    # A következő módosítás is felirat nélkül marad, amíg vissza nem kéred.
    monkeypatch.setattr(llm, "_ask", lambda p, **k: _json.dumps({"title": "Új", "scenes": [
        {"kind": "hook", "headline": "Új nyitás", "voice": "Rövid nyitás."}, {"kind": "cta", "headline": "Próbálja ki"}]}))
    videomaker.revise(m["id"], "rövidebb nyitás")
    assert seen["captions"] is False


def test_edge_female_voice_gets_a_spelling_it_can_say(monkeypatch):
    import sys, types
    said = {}

    class Comm:
        def __init__(self, text, voice):
            said[voice] = text

        async def save(self, path):
            open(path, "wb").write(b"")

    monkeypatch.setitem(sys.modules, "edge_tts", types.SimpleNamespace(Communicate=Comm))
    text = videomaker.spoken("Az AI agent beolvassa a leveleket.", "hu")
    videomaker._tts_edge(text, "hu", male=False)
    videomaker._tts_edge(text, "hu", male=True)
    assert "écsent" in said["hu-HU-NoemiNeural"] and "dzs" not in said["hu-HU-NoemiNeural"]
    assert "édzsent" in said["hu-HU-TamasNeural"]


def test_foreign_screens_get_timed_subtitles_once(tmp_path, monkeypatch):
    import json as _json
    monkeypatch.setattr(media, "MEDIA_DIR", str(tmp_path))
    segs = [{"from": 0, "to": 4, "what": "fiókválasztó", "pace": "action", "screen_text": "Válasszon fiókot", "screen_lang": "hu"},
            {"from": 4, "to": 8, "what": "levelek", "pace": "result", "screen_text": "Számla március", "screen_lang": "hu"},
            {"from": 8, "to": 20, "what": "agent fut", "pace": "result", "screen_text": "Sorting your inbox", "screen_lang": "en"}]
    media._save("c0ffee000001", {"id": "c0ffee000001", "kind": "clip", "file": "x.webm", "seconds": 20, "segments": segs})
    calls = []

    def fake(prompt, **k):
        calls.append(prompt)
        return _json.dumps({"subs": [{"i": 0, "text": "Google sign-in: choose account"}, {"i": 1, "text": ""}]})

    monkeypatch.setattr(llm, "_ask", fake)
    cues = videomaker.clip_cues("c0ffee000001", "en")
    assert cues == [{"from": 0, "to": 4, "text": "Google sign-in: choose account"}]
    assert "Sorting your inbox" not in calls[0]          # az angol képernyő nem kap feliratot
    assert videomaker.clip_cues("c0ffee000001", "en") == cues and len(calls) == 1   # tárolva
    script = {"scenes": [{"kind": "clip", "media": "c0ffee000001", "from": 0, "speed": 2, "seconds": 3},
                         {"kind": "clip", "media": "c0ffee000001", "from": 10, "speed": 1, "seconds": 4}]}
    videomaker._attach_cues(script, "en", lambda m: None)
    assert script["scenes"][0]["cues"] == cues and "cues" not in script["scenes"][1]
    # magyar videóban a magyar képernyőhöz nem kell felirat
    monkeypatch.setattr(llm, "_ask", lambda p, **k: _json.dumps({"subs": []}))
    assert videomaker.clip_cues("c0ffee000001", "hu") == []
