"""A rendező: az elemenkénti utasításaidat követi, és ütemre vág."""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import director  # noqa: E402


def item(i, kind="image", note="", seconds=None, hot=None):
    return {"id": f"{i:012x}", "kind": kind, "name": f"IMG_{i}.jpg", "note": note,
            "seconds": seconds, "hot": hot, "created_at": f"2026-10-15T08:00:{i:02d}.000+00:00",
            "status": "ready"}


# ---- az utasítások olvasása -----------------------------------------------

@pytest.mark.parametrize("note", ["ez legyen a nyitókép", "Nyitokep", "legyen az elso",
                                  "opening shot", "first frame"])
def test_opening_is_understood(note):
    assert director.read_note(note)["first"] is True


@pytest.mark.parametrize("note,want", [
    ("csak a 3. mp-től", 3.0), ("3 mp-tol", 3.0), ("a 12. másodperctől", 12.0),
    ("from 4s", 4.0), ("0:15-től", 15.0), ("1:05-től", 65.0)])
def test_start_time_is_understood(note, want):
    assert director.read_note(note)["start"] == want


@pytest.mark.parametrize("note,want", [
    ("írd rá: AXIMBRA", "AXIMBRA"), ("ird ra: hajra", "hajra"),
    ("felirat: Így csináld", "Így csináld"), ("text: Do it", "Do it"),
    ('írd rá: "idézőjelben"', "idézőjelben")])
def test_text_is_understood(note, want):
    assert director.read_note(note)["text"] == want


def test_an_instruction_can_hold_several_things():
    n = director.read_note("ez legyen a nyitókép, írd rá: AXIMBRA")
    assert n["first"] and n["text"] == "AXIMBRA"


def test_plain_notes_change_nothing():
    n = director.read_note("a kutya a parkban")
    assert not any([n["first"], n["last"], n["skip"], n["text"]]) and n["start"] is None


# ---- sorrend ---------------------------------------------------------------

def test_opening_and_closing_go_where_you_said():
    items = [item(1), item(2, note="legyen az utolsó"), item(3, note="ez legyen a nyitókép"),
             item(4)]
    names = [m["name"] for m in director.order(items)]
    assert names[0] == "IMG_3.jpg" and names[-1] == "IMG_2.jpg"


def test_skipped_items_are_left_out():
    items = [item(1), item(2, note="hagyd ki"), item(3)]
    assert [m["name"] for m in director.order(items)] == ["IMG_1.jpg", "IMG_3.jpg"]


def test_clips_are_spread_among_the_photos():
    """Montázs: ne legyen minden klip egy kupacban a végén."""
    items = [item(i) for i in range(1, 10)] + \
            [item(20 + i, kind="clip", seconds=8) for i in range(3)]
    kinds = [m["kind"] for m in director.order(items)]
    spots = [i for i, k in enumerate(kinds) if k == "clip"]
    assert len(spots) == 3
    assert max(spots) - min(spots) >= 4, f"a klipek egy helyen vannak: {spots}"


def test_order_is_the_upload_order():
    items = [item(3), item(1), item(2)]            # a tár fordítva adja
    assert [m["name"] for m in director.order(items)] == ["IMG_1.jpg", "IMG_2.jpg", "IMG_3.jpg"]


# ---- a terv ----------------------------------------------------------------

def test_plan_uses_every_item_and_respects_instructions():
    items = [item(1, note="ez legyen a nyitókép, írd rá: AXIMBRA"),
             item(2, kind="clip", seconds=20, hot=12.0, note="csak a 3. mp-től"),
             item(3, kind="clip", seconds=20, hot=12.0),
             item(4, note="hagyd ki"), item(5)]
    p = director.plan(items, seconds=20, aspect="9:16")
    assert len(p["scenes"]) == 4, "a kihagyott elem nem kerül bele"
    assert all("text" not in s for s in p["scenes"]), "feliratot nem teszünk ki"
    starts = {s["name"]: s["start"] for s in p["scenes"]}
    assert starts["IMG_2.jpg"] == 3.0, "amit mondtál, az számít"
    assert starts["IMG_3.jpg"] == 12.0, "egyébként a legjobb pillanat"


def test_clip_start_never_runs_past_the_end():
    p = director.plan([item(1, kind="clip", seconds=2.0, hot=1.9)], seconds=10)
    s = p["scenes"][0]
    assert s["start"] + s["seconds"] <= 2.0 + 0.001


def test_scene_lengths_stay_inside_the_limits():
    for n, target in ((3, 60), (60, 15), (22, 25)):
        p = director.plan([item(i) for i in range(n)], seconds=target)
        lens = [s["seconds"] for s in p["scenes"]]
        assert min(lens) >= director.MIN_SCENE - 1e-6
        assert max(lens) <= director.MAX_SCENE + 1e-6
        assert len(set(lens)) > 1 or n == 1, "legyen ritmusa, ne egyforma kockák"


def test_a_long_video_is_close_to_the_asked_length():
    p = director.plan([item(i) for i in range(22)], seconds=30)
    assert 26 <= p["seconds"] <= 36, p["seconds"]


def test_transitions_are_mixed_and_the_last_one_is_a_cut():
    p = director.plan([item(i) for i in range(20)], seconds=30)
    kinds = {s["transition"] for s in p["scenes"]}
    assert {"cut", "flash", "fade"} <= kinds
    assert p["scenes"][-1]["transition"] == "cut"


def test_photos_move_and_clips_do_not():
    p = director.plan([item(1), item(2, kind="clip", seconds=9)], seconds=10)
    by = {s["kind"]: s["motion"] for s in p["scenes"]}
    assert by["image"] != "none" and by["clip"] == "none"


def test_aspects_and_an_empty_selection():
    assert director.plan([item(1)], aspect="1:1")["width"] == 1080
    assert director.plan([item(1)], aspect="16:9")["width"] == 1920
    assert director.plan([item(1)], aspect="hoppa")["aspect"] == "9:16"
    with pytest.raises(ValueError):
        director.plan([item(1, note="hagyd ki")])
    with pytest.raises(ValueError):
        director.plan([])
