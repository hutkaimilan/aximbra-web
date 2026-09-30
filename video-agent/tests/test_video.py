"""A videós agent hálózat nélkül: modell, felolvasó és renderelő csonkkal."""
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
    monkeypatch.setattr(videomaker.time, "sleep", lambda s: None)
    assert videomaker._tts_gemini("szia", "hu") and len(calls) == 2
