"""Az AI-rendező: a modell tervét megszűrjük, és ha nincs modell, van tartalék."""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import brain  # noqa: E402
import director  # noqa: E402
import effects  # noqa: E402


def item(i, kind="image", note="", seconds=None, hot=None):
    return {"id": f"{i:012x}", "kind": kind, "name": f"IMG_{i}.jpg", "note": note,
            "seconds": seconds, "hot": hot, "width": 1080, "height": 1920,
            "created_at": f"2026-10-15T08:00:{i:02d}.000+00:00", "status": "ready"}


ITEMS = [item(1), item(2), item(3, kind="clip", seconds=12, hot=7.0), item(4)]
BY = {m["id"]: m for m in ITEMS}


def _plan_json(scenes, title="Teszt", used=("Velocity zoom",)):
    return {"title": title, "trends_used": list(used), "scenes": scenes}


def _fake_llm(monkeypatch, answer, engine="teszt-modell", available=True):
    import llm
    monkeypatch.setattr(llm, "available", lambda: available)
    monkeypatch.setattr(llm, "engine_name", lambda: engine)
    if isinstance(answer, Exception):
        def boom(_p):
            raise answer
        monkeypatch.setattr(llm, "_ask", boom)
    else:
        import json as _j
        monkeypatch.setattr(llm, "_ask", lambda _p: _j.dumps(answer))


# ---- a terv megszűrése ----------------------------------------------------

def test_the_model_can_only_use_effects_we_have(monkeypatch):
    """Kitalált effektnév ne hasaltassa el a renderelést: csendben "none" lesz."""
    _fake_llm(monkeypatch, _plan_json([
        {"id": ITEMS[0]["id"], "seconds": 1.0, "motion": "hyperspace_warp",
         "look": "instagram_1977", "transition": "teleport"},
        {"id": ITEMS[1]["id"], "seconds": 1.0, "motion": "punch_in", "look": "vhs",
         "transition": "zoomin"},
        {"id": ITEMS[2]["id"], "seconds": 1.0},
        {"id": ITEMS[3]["id"], "seconds": 1.0},
    ]))
    p = brain.plan(ITEMS, "valami")
    at = {s["id"]: s for s in p["scenes"]}
    a, b = at[ITEMS[0]["id"]], at[ITEMS[1]["id"]]
    assert a["motion"] == "none" and a["look"] == "none" and a["transition"] == "cut"
    assert b["motion"] == "punch_in" and b["look"] == "vhs" and b["transition"] == "zoomin"


def test_unknown_media_ids_are_dropped(monkeypatch):
    _fake_llm(monkeypatch, _plan_json([
        {"id": "nincs-ilyen", "seconds": 1.0},
        {"id": ITEMS[0]["id"], "seconds": 1.0},
        {"id": ITEMS[1]["id"], "seconds": 1.0},
    ]))
    p = brain.plan(ITEMS, "x")
    assert all(s["id"] in BY for s in p["scenes"])


def test_scene_lengths_and_clip_starts_are_clamped(monkeypatch):
    _fake_llm(monkeypatch, _plan_json([
        {"id": ITEMS[0]["id"], "seconds": 99},
        {"id": ITEMS[1]["id"], "seconds": 0.01},
        # klip: a kezdet nem lóghat túl a végén, gyorsítással együtt sem
        {"id": ITEMS[2]["id"], "seconds": 5, "start": 11.9, "speed": 3.0},
    ]))
    p = brain.plan(ITEMS, "x")
    s0, s1, s2 = p["scenes"][:3]
    assert s0["seconds"] <= director.MAX_SCENE and s1["seconds"] >= director.MIN_SCENE
    assert s2["start"] + s2["seconds"] * s2["speed"] <= 12.0 + 0.01


def test_speed_is_clamped_and_photos_stay_at_one(monkeypatch):
    _fake_llm(monkeypatch, _plan_json([
        {"id": ITEMS[0]["id"], "seconds": 1, "speed": 99},
        {"id": ITEMS[2]["id"], "seconds": 1, "speed": 99},
    ]))
    at = {s["id"]: s for s in brain.plan(ITEMS, "x")["scenes"]}
    assert at[ITEMS[0]["id"]]["speed"] == 1.0, "fotónak nincs sebessége"
    assert at[ITEMS[2]["id"]]["speed"] == 5.0, "a klip sebessége a felső korlátra megy"


def test_items_left_out_by_the_model_are_added_back(monkeypatch):
    _fake_llm(monkeypatch, _plan_json([{"id": ITEMS[0]["id"], "seconds": 1},
                                       {"id": ITEMS[1]["id"], "seconds": 1}]))
    p = brain.plan(ITEMS, "x")
    assert {s["id"] for s in p["scenes"]} == {m["id"] for m in ITEMS}, "minden elem kerüljön bele"


def test_skipped_items_never_reach_the_model_or_the_plan(monkeypatch):
    items = ITEMS + [item(9, note="hagyd ki")]
    seen = {}

    import llm, json as _j
    monkeypatch.setattr(llm, "available", lambda: True)
    monkeypatch.setattr(llm, "engine_name", lambda: "teszt")
    monkeypatch.setattr(llm, "_ask", lambda p: seen.update(prompt=p) or _j.dumps(
        _plan_json([{"id": m["id"], "seconds": 1} for m in ITEMS])))
    p = brain.plan(items, "x")
    assert f"{9:012x}" not in seen["prompt"]
    assert all(s["id"] != f"{9:012x}" for s in p["scenes"])


def test_the_last_scene_never_has_a_transition(monkeypatch):
    _fake_llm(monkeypatch, _plan_json([{"id": m["id"], "seconds": 1, "transition": "zoomin"}
                                       for m in ITEMS]))
    assert brain.plan(ITEMS, "x")["scenes"][-1]["transition"] == "cut"


# ---- amit a modellnek átadunk ---------------------------------------------

def test_the_prompt_carries_your_words_the_trends_and_the_toolbox(monkeypatch):
    seen = {}
    import llm, json as _j
    monkeypatch.setattr(llm, "available", lambda: True)
    monkeypatch.setattr(llm, "engine_name", lambda: "teszt")
    monkeypatch.setattr(llm, "_ask", lambda p: seen.update(prompt=p) or _j.dumps(
        _plan_json([{"id": m["id"], "seconds": 1} for m in ITEMS])))
    td = {"trends": [{"name": "Velocity zoom", "what": "gyors ráközelítés ütemre",
                      "when": "nyitásnál", "recipe": {"motion": "punch_in", "speed": 2.0},
                      "source": "https://pelda.hu"}]}
    brain.plan(ITEMS, "pörgős bemutató a hétvégéről", 30, "9:16", "hu", td)
    p = seen["prompt"]
    assert "pörgős bemutató a hétvégéről" in p
    assert "Velocity zoom" in p
    assert "punch_in" in p and "zoomin" in p, "a készlet nevei is menjenek át"
    assert "strongest_moment=7.0s" in p, "a klip legjobb pillanata is"


def test_aximbra_branding_only_when_it_is_about_aximbra(monkeypatch):
    seen = []
    import llm, json as _j
    monkeypatch.setattr(llm, "available", lambda: True)
    monkeypatch.setattr(llm, "engine_name", lambda: "teszt")
    monkeypatch.setattr(llm, "_ask", lambda p: seen.append(p) or _j.dumps(
        _plan_json([{"id": m["id"], "seconds": 1} for m in ITEMS])))
    brain.plan(ITEMS, "a kutyám a parkban")
    assert "NOT about AXIMBRA" in seen[-1]
    brain.plan(ITEMS, "az AXIMBRA új szolgáltatása")
    assert "is about AXIMBRA" in seen[-1]


# ---- tartalék -------------------------------------------------------------

def test_without_a_model_the_built_in_editor_takes_over(monkeypatch):
    import llm
    monkeypatch.setattr(llm, "available", lambda: False)
    said = []
    p = brain.plan(ITEMS, "akármi", say=said.append)
    assert p["by"] == "beépített vágó" and len(p["scenes"]) == len(ITEMS)
    assert any("beépített" in m for m in said), "mondja ki, hogy tartalékkal ment"


def test_a_failing_model_does_not_stop_the_video(monkeypatch):
    _fake_llm(monkeypatch, RuntimeError("insufficient_quota: elfogyott a napi keret"))
    said = []
    p = brain.plan(ITEMS, "akármi", say=said.append)
    assert p["by"] == "beépített vágó" and p["scenes"]
    assert any("keret" in m for m in said)


def test_a_garbage_answer_falls_back_too(monkeypatch):
    _fake_llm(monkeypatch, {"scenes": [{"id": "nincs"}]})
    p = brain.plan(ITEMS, "x")
    assert p["by"] == "beépített vágó"


def test_nothing_usable_is_an_error():
    with pytest.raises(ValueError):
        brain.plan([item(1, note="hagyd ki")], "x")


def test_every_scene_field_is_something_the_renderer_knows(monkeypatch):
    _fake_llm(monkeypatch, _plan_json([{"id": m["id"], "seconds": 1, "motion": "shake",
                                        "look": "glitch", "transition": "pixelize"}
                                       for m in ITEMS]))
    for s in brain.plan(ITEMS, "x")["scenes"]:
        assert effects.is_motion(s["motion"]) and effects.is_look(s["look"])
        assert effects.is_transition(s["transition"])


def test_a_caption_from_the_model_is_thrown_away(monkeypatch):
    """Feliratot nem kérsz: ha a modell mégis küld, nem kerül a tervbe."""
    _fake_llm(monkeypatch, _plan_json([{"id": m["id"], "seconds": 1, "text": "NE LÁTSZÓDJON"}
                                       for m in ITEMS]))
    for s in brain.plan(ITEMS, "x")["scenes"]:
        assert "text" not in s


def test_the_model_is_told_not_to_write_on_screen(monkeypatch):
    seen = {}
    import llm, json as _j
    monkeypatch.setattr(llm, "available", lambda: True)
    monkeypatch.setattr(llm, "engine_name", lambda: "teszt")
    monkeypatch.setattr(llm, "_ask", lambda p: seen.update(p=p) or _j.dumps(
        _plan_json([{"id": m["id"], "seconds": 1} for m in ITEMS])))
    brain.plan(ITEMS, "x")
    assert "NO on-screen text" in seen["p"]
