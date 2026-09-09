import os, sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))
os.environ.setdefault("OPENAI_API_KEY", "sk-test")
import pytest, server, mail_agent
from fastapi.testclient import TestClient
c = TestClient(server.app)

def test_endpoints_require_a_session():
    for path in ("/api/agent/email/progress", "/api/agent/email/results"):
        assert c.get(path).status_code == 401, path

def test_status_is_public_and_anonymous():
    r = c.get("/api/agent/email/status")
    assert r.status_code == 200 and r.json()["connected"] is False

def test_forged_cookie_rejected():
    c.cookies.set(mail_agent.SESSION_COOKIE, "hamis")
    assert c.get("/api/agent/email/results").status_code == 401
    c.cookies.clear()

def test_send_is_blocked_at_code_level():
    class D: pass
    with pytest.raises(PermissionError):
        _ = mail_agent.SafeGmailProxy(D()).send

def test_no_send_scope_requested():
    assert not any("gmail.send" in s for s in mail_agent.GMAIL_SCOPES)

def test_agent_never_writes_to_the_mailbox():
    src = open(BACKEND / "mail_agent.py").read()
    for forbidden in (".trash(", ".modify(", "addLabelIds", "STARRED", "drafts()"):
        assert forbidden not in src, forbidden

def test_agent_stores_nothing_persistent():
    src = open(BACKEND / "mail_agent.py").read()
    for forbidden in ("mongo", "sqlite", "open(", "psycopg"):
        assert forbidden not in src.lower(), forbidden

def test_expired_sessions_swept():
    from datetime import datetime, timezone, timedelta
    mail_agent._sessions.clear()
    mail_agent._sessions["old"] = {"created_at": datetime.now(timezone.utc) - timedelta(seconds=mail_agent.SESSION_TTL_SECONDS + 5)}
    mail_agent._sessions["new"] = {"created_at": datetime.now(timezone.utc)}
    mail_agent._sweep()
    assert "old" not in mail_agent._sessions and "new" in mail_agent._sessions

def test_classifier_normalises_bad_output():
    import asyncio
    async def fake(*a, **k):
        return '{"category":"Kitalált","urgency":99,"needs_reply":"talán"}'
    server._call_llm = fake
    out = asyncio.get_event_loop().run_until_complete(server.classify_one({"subject":"x","body":"y"}))
    assert out["category"] == "Egyéb"
    assert out["urgency"] == 5
    assert out["needs_reply"] == "nem egyértelmű"
