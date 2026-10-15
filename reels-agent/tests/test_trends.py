"""Trendfigyelő: keres, kivonatol, és csak azt tartja meg, amit meg tudunk csinálni."""
import json
import os
import sys
from datetime import datetime, timedelta, timezone

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import effects  # noqa: E402
import trends  # noqa: E402


@pytest.fixture(autouse=True)
def tmp_file(tmp_path, monkeypatch):
    monkeypatch.setattr(trends, "TRENDS_PATH", str(tmp_path / "trends.json"))


GOOD = {"trends": [
    {"name": "Velocity zoom", "what": "ütemre gyorsuló ráközelítés", "when": "nyitásnál",
     "recipe": {"motion": "punch_in", "speed": 2.5, "transition": "zoomin"},
     "source": "https://pelda.hu/a"},
    {"name": "VHS nostalgia", "what": "kazettás szemcse és színcsúszás", "when": "retró témánál",
     "recipe": {"look": "vhs"}, "source": "https://pelda.hu/b"},
]}


def _wire(monkeypatch, hits, answer):
    import llm
    import websearch
    monkeypatch.setattr(websearch, "tavily_on", lambda: True)
    monkeypatch.setattr(websearch, "search", lambda q, n=4: hits)
    monkeypatch.setattr(llm, "available", lambda: True)
    if isinstance(answer, Exception):
        def boom(_p):
            raise answer
        monkeypatch.setattr(llm, "_ask", boom)
    else:
        monkeypatch.setattr(llm, "_ask", lambda _p: json.dumps(answer))


HITS = [{"title": "What is trending", "url": "https://pelda.hu/a", "text": "velocity zoom mindenhol"}]


def test_a_refresh_stores_trends_with_sources(monkeypatch):
    _wire(monkeypatch, HITS, GOOD)
    said = []
    d = trends.refresh(said.append)
    assert [t["name"] for t in d["trends"]] == ["Velocity zoom", "VHS nostalgia"]
    assert d["trends"][0]["source"].startswith("http")
    assert trends.age_days(d) < 0.01
    assert any("Velocity zoom" in m for m in said)


def test_only_recipes_we_can_actually_render_survive(monkeypatch):
    """A modell kitalálhat effektnevet; ami nincs a készletben, az kiesik."""
    _wire(monkeypatch, HITS, {"trends": [
        {"name": "Teleport wipe", "recipe": {"transition": "teleport"}, "what": "x", "source": "https://a.hu"},
        {"name": "Fake look", "recipe": {"look": "instagram_1977"}, "what": "x", "source": "https://a.hu"},
        {"name": "Jó", "recipe": {"motion": "shake", "look": "grain"}, "what": "x", "source": "https://a.hu"},
    ]})
    names = [t["name"] for t in trends.refresh()["trends"]]
    assert names == ["Jó"]


def test_speed_is_clamped_in_a_recipe(monkeypatch):
    _wire(monkeypatch, HITS, {"trends": [
        {"name": "Hyper", "recipe": {"motion": "punch_in", "speed": 99}, "what": "x",
         "source": "https://a.hu"}]})
    assert trends.refresh()["trends"][0]["recipe"]["speed"] == 5.0


def test_a_model_failure_keeps_the_previous_research(monkeypatch):
    _wire(monkeypatch, HITS, GOOD)
    trends.refresh()
    _wire(monkeypatch, HITS, RuntimeError("elfogyott a napi keret"))
    said = []
    d = trends.refresh(said.append)
    assert [t["name"] for t in d["trends"]] == ["Velocity zoom", "VHS nostalgia"]
    assert any("korábbi" in m for m in said)


def test_no_search_results_keeps_the_previous_research(monkeypatch):
    _wire(monkeypatch, HITS, GOOD)
    trends.refresh()
    _wire(monkeypatch, [], GOOD)
    assert len(trends.refresh()["trends"]) == 2


def test_without_keys_it_steps_aside(monkeypatch):
    import llm
    import websearch
    monkeypatch.setattr(websearch, "tavily_on", lambda: False)
    monkeypatch.setattr(llm, "available", lambda: False)
    said = []
    assert trends.refresh(said.append) == {}
    assert any("kimarad" in m for m in said)


def test_weekly_refresh_only(monkeypatch):
    _wire(monkeypatch, HITS, GOOD)
    trends.refresh()
    assert trends.stale() is False
    calls = []
    monkeypatch.setattr(trends, "refresh", lambda say=None, **k: calls.append(1) or {})
    trends.ensure(lambda m: None)
    assert not calls, "friss anyagnál nem keres újra"
    # Nyolc napos anyag már elavult.
    d = trends.load()
    d["checked_at"] = (datetime.now(timezone.utc) - timedelta(days=8)).isoformat(timespec="seconds")
    trends._save(d)
    assert trends.stale() is True
    trends.ensure(lambda m: None)
    assert calls, "egy hét után magától frissít"


def test_force_refreshes_even_when_fresh(monkeypatch):
    _wire(monkeypatch, HITS, GOOD)
    trends.refresh()
    calls = []
    monkeypatch.setattr(trends, "refresh", lambda say=None, **k: calls.append(1) or {})
    trends.ensure(lambda m: None, force=True)
    assert calls


def test_the_prompt_lists_only_our_own_effects(monkeypatch):
    seen = {}
    import llm
    import websearch
    monkeypatch.setattr(websearch, "tavily_on", lambda: True)
    monkeypatch.setattr(websearch, "search", lambda q, n=4: HITS)
    monkeypatch.setattr(llm, "available", lambda: True)
    monkeypatch.setattr(llm, "_ask", lambda p: seen.update(p=p) or json.dumps(GOOD))
    trends.refresh()
    for name in ("punch_in", "vhs", "zoomin", "shake"):
        assert name in seen["p"]
    assert "velocity zoom mindenhol" in seen["p"], "a talált szöveg is menjen át"


def test_summary_is_readable_for_the_director(monkeypatch):
    _wire(monkeypatch, HITS, GOOD)
    s = trends.summary_for_prompt(trends.refresh())
    assert "Velocity zoom" in s and "punch_in" in s
    assert trends.summary_for_prompt({}) == "(no current trend research available)"


def test_broken_file_does_not_crash(monkeypatch):
    with open(trends.TRENDS_PATH, "w") as f:
        f.write("{nem json")
    assert trends.load() == {} and trends.stale() is True
