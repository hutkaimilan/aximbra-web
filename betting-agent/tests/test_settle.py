"""Szelvénynapló-kiértékelés: valódi ESPN-eredményen (sample/espn_scoreboard_esp1_20261019.json) és szélsőeseteken."""
import copy
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import settle  # noqa: E402
import tippmix  # noqa: E402
import web  # noqa: E402

SAMPLE = json.loads((Path(__file__).resolve().parent.parent / "sample" / "espn_scoreboard_esp1_20261019.json")
                    .read_text("utf-8"))
LEAGUES = {c.key: c.espn for c in tippmix.COMPETITIONS}
NOW = datetime(2026, 10, 21, 12, 0, tzinfo=timezone.utc)
# Getafe – Rayo Vallecano: 1–1, félidő 0–1 (Rayo 11'), 16 szöglet, 9 sárga + 1 piros
BASE = {"comp": "laliga", "home": "Getafe", "away": "Rayo Vallecano", "kickoff": "2026-10-19T19:00:00Z"}


def _day(events):
    calls = []

    def fn(league, day):
        calls.append((league, day))
        return events if league == "esp.1" else []
    return fn, calls


def _run(*legs, events=None, now=NOW):
    fn, calls = _day(SAMPLE["events"] if events is None else events)
    parsed = [settle.parse_leg({**BASE, **l}, LEAGUES) for l in legs]
    return settle.settle(parsed, fn, now=now), calls


def test_event_result_from_real_sample():
    r = settle.event_result(SAMPLE["events"][0])
    assert r["ft"] == (1, 1) and r["ht"] == (0, 1) and r["corners"] == 16 and r["cards"] == 10
    assert r["status"] == "STATUS_FULL_TIME"


@pytest.mark.parametrize("leg,status", [
    ({"mk": "1x2", "pick": "X"}, "won"),
    ({"mk": "1x2", "pick": "1"}, "lost"),
    ({"mk": "dc", "pick": "X2"}, "won"),
    ({"mk": "ou", "pick": "Kevesebb", "line": 2.5}, "won"),
    ({"mk": "btts", "pick": "Igen"}, "won"),
    ({"mk": "dnb", "pick": "1"}, "void"),
    ({"mk": "hcp", "pick": "1", "line": 1.0}, "won"),       # 1–1, hazai +1: 2–1
    ({"mk": "hcp", "pick": "X", "line": -1.0}, "lost"),     # hazai −1: 0–1
    ({"mk": "ht1x2", "pick": "2"}, "won"),
    ({"mk": "htou", "pick": "Több", "line": 0.5}, "won"),
    ({"mk": "corners", "pick": "Több", "line": 15.5}, "won"),
    ({"mk": "corners", "pick": "Több", "line": 16.5}, "lost"),
    ({"mk": "cards", "pick": "Kevesebb", "line": 10.5}, "won"),
    ({"mk": "cards", "pick": "Több", "line": 10.5}, "lost"),
])
def test_markets_settle_correctly(leg, status):
    (res,), _ = _run(leg)
    assert res["status"] == status
    assert res["score"] == "1–1" and res["ht"] == "0–1"


def test_same_match_many_legs_one_espn_request_per_day():
    out, calls = _run({"mk": "1x2", "pick": "X"}, {"mk": "btts", "pick": "Igen"}, {"mk": "corners", "pick": "Több", "line": 9.5})
    assert [r["status"] for r in out] == ["won", "won", "won"]
    assert len(calls) == len(set(calls)) <= 2


def test_tippmix_names_still_match():
    (res,), _ = _run({"home": "Getafe CF", "away": "Rayo", "mk": "1x2", "pick": "X"})
    assert res["status"] == "won"


def test_not_finished_yet_is_pending_and_not_requested():
    (res,), calls = _run({"mk": "1x2", "pick": "X"}, now=datetime(2026, 10, 19, 20, 0, tzinfo=timezone.utc))
    assert res["status"] == "pending" and calls == []


def test_missing_result_turns_unknown_after_three_days():
    (res,), _ = _run({"mk": "1x2", "pick": "X"}, events=[])
    assert res["status"] == "pending"
    (res,), _ = _run({"mk": "1x2", "pick": "X"}, events=[], now=NOW + timedelta(days=3))
    assert res["status"] == "unknown"


def test_postponed_is_void_and_extra_time_unknown():
    ev = copy.deepcopy(SAMPLE["events"][0])
    ev["competitions"][0]["status"]["type"].update(name="STATUS_POSTPONED", state="post", completed=False)
    (res,), _ = _run({"mk": "1x2", "pick": "X"}, events=[ev])
    assert res["status"] == "void"
    ev["competitions"][0]["status"]["type"].update(name="STATUS_FINAL_AET", completed=True)
    (res,), _ = _run({"mk": "1x2", "pick": "X"}, events=[ev])
    assert res["status"] == "unknown"


def test_inconsistent_goal_list_gives_no_halftime():
    ev = copy.deepcopy(SAMPLE["events"][0])
    ev["competitions"][0]["details"] = [d for d in ev["competitions"][0]["details"] if not d.get("scoringPlay")][:3]
    r = settle.event_result(ev)
    assert r["ht"] is None and r["ft"] == (1, 1)
    (res,), _ = _run({"mk": "ht1x2", "pick": "2"}, events=[ev])
    assert res["status"] == "unknown"
    (res,), _ = _run({"mk": "1x2", "pick": "X"}, events=[ev])
    assert res["status"] == "won"


@pytest.mark.parametrize("bad", [{"comp": "xx"}, {"home": ""}, {"kickoff": "tegnap"}, {"kickoff": "2026-10-19T19:00:00"},
                                 {"line": "2,5"}])
def test_parse_leg_rejects_bad_input(bad):
    with pytest.raises(ValueError):
        settle.parse_leg({**BASE, "mk": "ou", "pick": "Több", "line": 2.5, **bad}, LEAGUES)


def test_web_settle_keeps_order_and_reports_bad_legs(monkeypatch):
    monkeypatch.setattr(web, "_day_events", lambda league, day: SAMPLE["events"])
    out = web.settle_legs([{**BASE, "mk": "1x2", "pick": "1"}, {"comp": "??"}, {**BASE, "mk": "1x2", "pick": "X"}])
    assert [r["status"] for r in out["results"]] == ["lost", "unknown", "won"]
