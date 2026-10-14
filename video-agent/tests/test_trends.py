"""Trendfigyelő: csak forrással igazolt trend kerül a listára, és hetente frissül."""
import json
import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import trends  # noqa: E402
import videomaker  # noqa: E402


def test_refresh_keeps_only_sourced_trends(monkeypatch, tmp_path):
    monkeypatch.setattr(trends, "PATH", str(tmp_path / "t.json"))
    monkeypatch.setattr(trends.websearch, "search", lambda q, n=4: [
        {"title": "Reels trends", "url": "https://example.com/" + q[:5].replace(" ", ""), "text": "punch-in zoom cuts"}])
    monkeypatch.setattr(trends.llm, "_ask", lambda p: json.dumps({"trends": [
        {"name": "Punch-in zoom", "platforms": ["instagram", "myspace"], "kind": "transition",
         "what": "Minden vágásnál ráközelít.", "apply": "montage with transition zoom", "source": 0},
        {"name": "Kitalált", "what": "x", "apply": "y", "source": 99}]}))
    d = trends.refresh()
    assert [t["name"] for t in d["trends"]] == ["Punch-in zoom"]
    assert d["trends"][0]["platforms"] == ["instagram"] and d["trends"][0]["source"]["url"].startswith("https://")
    assert trends.fresh(trends.load())
    assert "Punch-in zoom" in trends.prompt_block(d)


def test_stale_list_is_refreshed_and_search_failure_keeps_old(monkeypatch, tmp_path):
    p = tmp_path / "t.json"
    old = {"fetched_at": (datetime.now(timezone.utc) - timedelta(days=8)).isoformat(), "trends": [{"name": "Régi"}]}
    p.write_text(json.dumps(old))
    monkeypatch.setattr(trends, "PATH", str(p))
    monkeypatch.setattr(trends.websearch, "search", lambda q, n=4: [])
    assert not trends.fresh(trends.load())
    assert trends.current()["trends"][0]["name"] == "Régi"


def test_user_notes_reach_the_director(monkeypatch):
    item = {"id": "img000000001", "kind": "image", "name": "nyito.jpg", "note": ""}
    monkeypatch.setattr(videomaker.media, "get", lambda i: item if i == item["id"] else None)
    ctx = {"urls": [], "pages": [], "web": [], "library": [], "attached": [item["id"]],
           "media_notes": {item["id"]: "ez legyen a nyitókép"}, "trends": {}}
    p = videomaker.director_prompt("Reel a nyárról", ctx, 30, "hu", "9:16", True, "video")
    assert 'INSTRUCTION FOR THIS ONE: "ez legyen a nyitókép"' in p
