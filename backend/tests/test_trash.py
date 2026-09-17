"""A takarítás határai: csak a nem lényeges levél, csak Kukába, csak engedéllyel."""
import os, sys, datetime
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))
os.environ.setdefault("OPENAI_API_KEY", "sk-test")
os.environ.setdefault("AGENT_PUBLIC", "1")

import mail_agent
from fastapi.testclient import TestClient
import server
c = TestClient(server.app)


def _session(docs, can_trash=True, sample=False):
    sid = "trash-" + os.urandom(4).hex()
    mail_agent._sessions[sid] = {
        "email": "x@y.hu", "creds": None, "analyses": docs, "can_trash": can_trash,
        "sample": sample, "lang": "hu", "drafts": {}, "saved": {}, "sent": {},
        "state": mail_agent._new_state(),
        "created_at": datetime.datetime.now(datetime.timezone.utc),
    }
    return sid, {mail_agent.SESSION_HEADER: mail_agent._fernet.encrypt(sid.encode()).decode()}


def test_only_newsletter_and_spam_count_as_unimportant():
    assert mail_agent._is_trashable({"category": "newsletter"})
    assert mail_agent._is_trashable({"category": "spam"})
    for keep in ("customer_question", "invoice", "opportunity",
                 "authority", "provider_notice", "other"):
        assert not mail_agent._is_trashable({"category": keep}), keep


def test_a_crafted_request_cannot_trash_important_mail():
    sid, h = _session([
        {"id": "invoice", "category": "invoice"},
        {"id": "junk", "category": "newsletter"},
    ], sample=True)
    r = c.post("/api/agent/email/trash", json={"ids": ["invoice"], "confirm": True}, headers=h)
    assert r.status_code == 200
    assert r.json()["trashed"] == 0 and r.json()["refused"] == 1
    assert mail_agent._sessions[sid]["analyses"][0].get("trashed") is None
    mail_agent._sessions.pop(sid, None)


def test_ids_outside_the_run_are_refused():
    sid, h = _session([{"id": "mine", "category": "spam"}], sample=True)
    r = c.post("/api/agent/email/trash", json={"ids": ["not-mine"], "confirm": True}, headers=h)
    assert r.json()["trashed"] == 0 and r.json()["refused"] == 1
    mail_agent._sessions.pop(sid, None)


def test_without_confirmation_nothing_is_trashed():
    sid, h = _session([{"id": "j", "category": "spam"}], sample=True)
    assert c.post("/api/agent/email/trash", json={"ids": ["j"]}, headers=h).status_code == 400
    assert mail_agent._sessions[sid]["analyses"][0].get("trashed") is None
    mail_agent._sessions.pop(sid, None)


def test_without_the_grant_a_real_mailbox_is_refused():
    sid, h = _session([{"id": "j", "category": "spam"}], can_trash=False)
    r = c.post("/api/agent/email/trash", json={"ids": ["j"], "confirm": True}, headers=h)
    assert r.status_code == 403
    mail_agent._sessions.pop(sid, None)


def test_trash_needs_a_session():
    assert c.post("/api/agent/email/trash", json={"ids": ["x"], "confirm": True}).status_code == 401


def test_the_sample_mailbox_can_be_tidied_without_gmail():
    sid, h = _session([{"id": "j", "category": "newsletter"}], sample=True)
    r = c.post("/api/agent/email/trash", json={"ids": ["j"], "confirm": True}, headers=h)
    assert r.json()["trashed"] == 1
    assert mail_agent._sessions[sid]["analyses"][0]["trashed"] is True
    mail_agent._sessions.pop(sid, None)


def test_trashed_mail_leaves_the_results():
    sid, h = _session([
        {"id": "gone", "category": "spam", "trashed": True},
        {"id": "here", "category": "customer_question", "needs_reply": "igen"},
    ], sample=True)
    body = c.get("/api/agent/email/results", headers=h).json()
    assert [d["id"] for d in body["analyses"]] == ["here"]
    assert body["trashed"] == 1 and body["total"] == 2
    # A kategória-diagram is a listát követi: egy oszlop, ami alatta már nem
    # látható levelet számol, csak ellentmondana annak, ami a lapon van.
    assert body["counts"] == {"customer_question": 1}
    mail_agent._sessions.pop(sid, None)


def test_cleanup_scope_is_asked_for_only_when_ticked():
    assert mail_agent.MODIFY_SCOPE not in mail_agent._scopes_for(False, False)
    assert mail_agent.MODIFY_SCOPE in mail_agent._scopes_for(False, True)
    assert mail_agent.COMPOSE_SCOPE not in mail_agent._scopes_for(False, True)


def test_the_opt_in_survives_the_oauth_round_trip():
    packed = mail_agent._pack_state("v" * 128, False, "hu", with_modify=True)
    assert mail_agent._unpack_state(packed)["with_modify"] is True


def test_a_scope_google_refused_is_not_believed():
    class Creds:
        granted_scopes = [mail_agent.GMAIL_SCOPES[0]]
    assert mail_agent._granted_scope(Creds(), mail_agent.MODIFY_SCOPE, requested=True) is False


def test_nothing_is_ever_deleted_permanently():
    src = (BACKEND / "mail_agent.py").read_text(encoding="utf-8")
    assert "batchDelete" not in src
    assert ".delete(" not in src
    assert ".trash(" in src


def test_trashable_categories_are_keys_the_classifier_actually_returns():
    """Élesben üres volt a kidobható lista: a halmaz a magyar feliratokat
    sorolta, az osztályozó viszont kulcsot ad vissza. Ez a teszt a kettőt köti össze."""
    assert mail_agent.TRASHABLE_CATEGORIES <= server.AGENT_CATEGORIES
    assert mail_agent.TRASHABLE_CATEGORIES == {"newsletter", "spam"}
