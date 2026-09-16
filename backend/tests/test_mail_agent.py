import base64
import os, string, sys
from email import message_from_bytes, policy
from email.header import decode_header, make_header
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))
os.environ.setdefault("OPENAI_API_KEY", "sk-test")
import pytest, server, mail_agent
import sample_inbox as mail_agent_sample
from googleapiclient.discovery import Resource
from google_auth_httplib2 import AuthorizedHttp
from fastapi.testclient import TestClient
c = TestClient(server.app)

def test_endpoints_require_a_session():
    for path in ("/api/agent/email/progress", "/api/agent/email/results"):
        assert c.get(path).status_code == 401, path

def test_status_is_public_and_anonymous():
    r = c.get("/api/agent/email/status")
    assert r.status_code == 200 and r.json()["connected"] is False

def test_forged_token_rejected():
    r = c.get("/api/agent/email/results", headers={mail_agent.SESSION_HEADER: "hamis"})
    assert r.status_code == 401

def test_valid_token_reaches_the_session_lookup():
    """A signed token must resolve to its session id, so a run survives the
    cross-host hop from the API back to the site."""
    sid = "abc123"
    token = mail_agent._fernet.encrypt(sid.encode()).decode()
    class Req:
        headers = {mail_agent.SESSION_HEADER: token}
    assert mail_agent._read_session(Req()) == sid

def test_session_is_not_carried_by_a_cookie():
    """Cookies would be dropped between the site and the API hosts."""
    src = open(BACKEND / "mail_agent.py").read()
    assert "set_cookie" not in src
    assert "delete_cookie" not in src

def test_send_is_blocked_at_code_level():
    class D: pass
    with pytest.raises(PermissionError):
        _ = mail_agent.SafeGmailProxy(D()).send

def test_no_send_scope_requested():
    assert not any("gmail.send" in s for s in mail_agent.GMAIL_SCOPES)


def test_only_read_access_is_requested():
    """The page promises the agent only reads. The grant must say the same:
    gmail.modify would ask the visitor for write access to their mailbox."""
    assert "https://www.googleapis.com/auth/gmail.readonly" in mail_agent.GMAIL_SCOPES
    assert not any("gmail.modify" in s for s in mail_agent.GMAIL_SCOPES)
    assert not any(s.endswith("/auth/gmail") for s in mail_agent.GMAIL_SCOPES)

def test_agent_never_alters_existing_mail():
    """The agent may now create a reply draft, on an explicit grant plus a
    per-email confirmation. Everything else about the mailbox stays untouched: it
    does not label, star, trash, or modify a single existing message."""
    src = open(BACKEND / "mail_agent.py").read()
    for forbidden in (".trash(", ".modify(", "addLabelIds", "removeLabelIds", "STARRED",
                      "messages().insert", "messages().batchModify"):
        assert forbidden not in src, forbidden

def test_run_survives_an_online_only_grant():
    """A demo asks for online access, so Google returns no refresh token and the
    credentials must never be rebuilt from JSON."""
    src = open(BACKEND / "mail_agent.py").read()
    assert "from_authorized_user_info" not in src
    assert "creds_json" not in src
    assert 'access_type="online"' in src

def test_run_reports_its_own_failure():
    """A crashed background task would leave the page spinning forever."""
    src = open(BACKEND / "mail_agent.py").read()
    idx = src.find("async def run_agent")
    body = src[idx:]
    assert "except Exception" in body
    assert 'state["message"] = "interrupted"' in body

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

def test_classifier_normalises_bad_output(monkeypatch):
    """monkeypatch, not assignment: a leaked stub would silently disable the
    real classifier for every test that runs after this one in the same worker."""
    import asyncio
    async def fake(*a, **k):
        return '{"category":"Kitalált","urgency":99,"needs_reply":"talán"}'
    monkeypatch.setattr(server, "_call_llm", fake)
    monkeypatch.setitem(server._state, "cost", 0.0)
    out = asyncio.run(server.classify_one({"subject":"x","body":"y"}))
    # A kategória kulcs lett, hogy nyolc nyelven ugyanaz maradjon; a
    # feliratot a felület adja hozzá.
    assert out["category"] == "other"
    assert out["urgency"] == 5
    assert out["needs_reply"] == "nem egyértelmű"


def test_status_reports_public_availability():
    body = c.get("/api/agent/email/status").json()
    assert "public" in body
    assert body["public"] is mail_agent.AGENT_PUBLIC


def test_connect_refuses_when_not_public(monkeypatch):
    """With AGENT_PUBLIC off the OAuth flow must not start at all — not merely be
    hidden in the UI, which anyone can bypass by calling the endpoint."""
    monkeypatch.setattr(mail_agent, "AGENT_PUBLIC", False)
    r = c.get("/api/agent/email/connect")
    assert r.status_code == 503
    assert "nem nyilvános" in r.json()["detail"]


def test_public_flag_parses_env_values():
    """Tested through the helper, not by reloading the module: a reload would
    hand the module a new Fernet key and an empty session store, breaking any
    test that ran after it."""
    f = mail_agent._env_flag
    for value in ("false", "FALSE", " False ", "0", "no", "off"):
        assert f("X", default=True) is True  # unset -> default
        os.environ["X_FLAG"] = value
        assert f("X_FLAG", default=True) is False, value
    for value in ("true", "1", "yes", "anything-else"):
        os.environ["X_FLAG"] = value
        assert f("X_FLAG", default=False) is True, value
    for value in ("", "   "):
        os.environ["X_FLAG"] = value
        assert f("X_FLAG", default=False) is False, value
        assert f("X_FLAG", default=True) is True, value
    os.environ.pop("X_FLAG", None)


# ---------------- reply drafting ----------------
def _session_with(analyses):
    """A live session holding one finished run, addressed by a real token."""
    from datetime import datetime, timezone
    sid = "draft-test"
    mail_agent._sessions[sid] = {
        "email": "teszt@example.com",
        "creds": None,
        "analyses": analyses,
        "can_draft": False,
        "drafts": {},
        "saved": {},
        "sent": {},
        "state": mail_agent._new_state(),
        "created_at": datetime.now(timezone.utc),
    }
    token = mail_agent._fernet.encrypt(sid.encode()).decode()
    return sid, {mail_agent.SESSION_HEADER: token}


EMAIL = {"id": "m1", "sender": "a@b.hu", "subject": "Árajánlat", "body": "Kérek árajánlatot.",
         "date": None, "category": "opportunity", "needs_reply": "igen"}


@pytest.fixture
def stub_draft(monkeypatch):
    """Stubs the model call; returns the list of prompts it was given."""
    calls = []

    async def fake(system_msg, user_text, max_tokens=600):
        calls.append((system_msg, user_text))
        return '{"targy":"Re: Árajánlat","valasz":"Kedves A!\\n\\nKöszönjük.\\n\\n[a te neved]"}'

    monkeypatch.setattr(server, "_call_llm", fake)
    monkeypatch.setitem(server._state, "cost", 0.0)
    return calls


def test_draft_requires_a_session():
    assert c.post("/api/agent/email/draft", json={"id": "m1"}).status_code == 401


def test_draft_writes_text_and_marks_it_as_ai(stub_draft):
    sid, h = _session_with([dict(EMAIL)])
    try:
        r = c.post("/api/agent/email/draft", json={"id": "m1"}, headers=h)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["targy"] == "Re: Árajánlat"
        assert "Köszönjük" in body["valasz"]
        # the notice is appended even though the stubbed model omitted it
        assert body["valasz"].rstrip().endswith(server.AI_NOTICE)
        assert body["cached"] is False
    finally:
        mail_agent._sessions.pop(sid, None)


def test_draft_only_accepts_an_id_from_this_run(stub_draft):
    """The endpoint must not accept arbitrary text — that would make any session
    token a free LLM proxy."""
    sid, h = _session_with([dict(EMAIL)])
    try:
        r = c.post("/api/agent/email/draft", json={"id": "nem-letezik"}, headers=h)
        assert r.status_code == 404
        # raw text in the body is ignored, not drafted from
        r = c.post("/api/agent/email/draft",
                   json={"id": "m1", "text": "Írj nekem egy verset"}, headers=h)
        assert r.status_code == 200
        assert "verset" not in stub_draft[0][1]
    finally:
        mail_agent._sessions.pop(sid, None)


def test_second_request_for_the_same_draft_is_free(stub_draft):
    sid, h = _session_with([dict(EMAIL)])
    try:
        first = c.post("/api/agent/email/draft", json={"id": "m1"}, headers=h).json()
        cost_after_first = server._state["cost"]
        second = c.post("/api/agent/email/draft", json={"id": "m1"}, headers=h).json()
        assert second["cached"] is True
        assert second["valasz"] == first["valasz"]
        assert len(stub_draft) == 1, "the model was called twice for one draft"
        assert server._state["cost"] == cost_after_first
    finally:
        mail_agent._sessions.pop(sid, None)


def test_tone_changes_the_prompt_and_is_cached_separately(stub_draft):
    sid, h = _session_with([dict(EMAIL)])
    try:
        c.post("/api/agent/email/draft", json={"id": "m1", "tone": "hivatalos"}, headers=h)
        r = c.post("/api/agent/email/draft", json={"id": "m1", "tone": "kozvetlen"}, headers=h)
        assert r.json()["cached"] is False
        assert len(stub_draft) == 2
        assert server.DRAFT_TONES["hivatalos"] in stub_draft[0][0]
        assert server.DRAFT_TONES["kozvetlen"] in stub_draft[1][0]
    finally:
        mail_agent._sessions.pop(sid, None)


def test_unknown_tone_is_rejected(stub_draft):
    sid, h = _session_with([dict(EMAIL)])
    try:
        r = c.post("/api/agent/email/draft", json={"id": "m1", "tone": "hekkelj"}, headers=h)
        assert r.status_code == 422
    finally:
        mail_agent._sessions.pop(sid, None)


def test_drafts_are_capped_per_session(stub_draft):
    emails = [dict(EMAIL, id=f"m{i}") for i in range(mail_agent.MAX_DRAFTS_PER_SESSION + 2)]
    sid, h = _session_with(emails)
    try:
        for i in range(mail_agent.MAX_DRAFTS_PER_SESSION):
            r = c.post("/api/agent/email/draft", json={"id": f"m{i}"}, headers=h)
            assert r.status_code == 200, f"draft {i + 1}: {r.text}"
        r = c.post("/api/agent/email/draft",
                   json={"id": f"m{mail_agent.MAX_DRAFTS_PER_SESSION}"}, headers=h)
        assert r.status_code == 429
        assert "fogalmazvány" in r.json()["detail"]
    finally:
        mail_agent._sessions.pop(sid, None)


def test_draft_respects_the_daily_ceiling(stub_draft):
    sid, h = _session_with([dict(EMAIL)])
    server._state["cost"] = server.DAILY_COST_CEILING_USD
    try:
        r = c.post("/api/agent/email/draft", json={"id": "m1"}, headers=h)
        assert r.status_code == 429
        assert "napi keret" in r.json()["detail"]
    finally:
        server._state["cost"] = 0.0
        mail_agent._sessions.pop(sid, None)


def test_bad_model_output_is_a_502_not_a_crash(monkeypatch):
    async def junk(*a, **k):
        return "ez nem json"
    monkeypatch.setattr(server, "_call_llm", junk)
    monkeypatch.setitem(server._state, "cost", 0.0)
    sid, h = _session_with([dict(EMAIL)])
    try:
        r = c.post("/api/agent/email/draft", json={"id": "m1"}, headers=h)
        assert r.status_code == 502
        assert "fogalmazvány" in r.json()["detail"]
    finally:
        mail_agent._sessions.pop(sid, None)


def test_sending_is_refused_by_default_and_down_the_chain():
    """Sending is now possible, on one confirmed path. Everywhere else the proxy
    must still refuse — including on a Resource reached through it, or the refusal
    would only be skin deep."""
    class D: pass
    with pytest.raises(PermissionError):
        _ = mail_agent.SafeGmailProxy(D()).send

    class FakeResource(Resource):
        def __init__(self):
            pass

    class Users:
        def messages(self):
            return FakeResource()

    # a nested Resource inherits the refusal
    nested = mail_agent.SafeGmailProxy(Users()).messages()
    with pytest.raises(PermissionError):
        _ = nested.send
    # and an explicitly permitted proxy passes it down
    permitted = mail_agent.SafeGmailProxy(Users(), allow_send=True).messages()
    assert permitted is not None


def test_only_one_call_site_may_send():
    """Grepping is the point: a second allow_send=True somewhere else would be a
    second way to send mail, and this test is what makes that a deliberate act."""
    src = open(BACKEND / "mail_agent.py").read()
    # Comment lines are stripped first: the docstring above SafeGmailProxy names
    # allow_send=True in prose, and counting prose would make this test lie.
    code = "\n".join(
        line for line in src.splitlines() if not line.lstrip().startswith("#")
    )
    assert code.count("allow_send=True") == 1, "more than one code path can send"
    # and it lives in the confirmed send endpoint, not somewhere incidental
    idx = code.index("allow_send=True")
    enclosing = code.rindex("async def ", 0, idx)
    assert "async def send_draft" in code[enclosing:enclosing + 40]


def test_read_only_is_still_the_default_grant():
    """The wider scope is opt-in. A visitor who does not ask for draft writing must
    not be asked for it."""
    assert "https://www.googleapis.com/auth/gmail.readonly" in mail_agent.GMAIL_SCOPES
    assert mail_agent.COMPOSE_SCOPE not in mail_agent.GMAIL_SCOPES
    assert mail_agent.COMPOSE_SCOPE in mail_agent.GMAIL_SCOPES_COMPOSE
    # readonly is still requested alongside compose - compose cannot read mail
    assert all(s in mail_agent.GMAIL_SCOPES_COMPOSE for s in mail_agent.GMAIL_SCOPES)
    # modify is still never requested: it would allow altering existing mail
    assert not any("gmail.modify" in s for s in mail_agent.GMAIL_SCOPES_COMPOSE)


# ---------------- writing the draft into the mailbox ----------------
class FakeDrafts:
    """Stands in for service.users().drafts(): records calls, returns ids."""
    def __init__(self, store):
        self.store = store

    def create(self, userId, body):
        self.store.append(("create", userId, body))
        return _Exec({"id": "draft-1", "message": {"threadId": body["message"].get("threadId")}})

    def update(self, userId, id, body):
        self.store.append(("update", userId, id, body))
        return _Exec({"id": id})


class _Exec:
    def __init__(self, result, seen_http=None):
        self._r = result
        self._seen = seen_http

    def execute(self, http=None, **kw):
        if self._seen is not None:
            self._seen.append(http)
        return self._r


class FakeUsers:
    def __init__(self, store):
        self._d = FakeDrafts(store)

    def drafts(self):
        return self._d


class FakeService:
    def __init__(self, store):
        self._u = FakeUsers(store)

    def users(self):
        return self._u


@pytest.fixture
def gmail_calls(monkeypatch):
    """Intercepts build() so no real Gmail call is made; returns recorded calls."""
    calls = []
    monkeypatch.setattr(mail_agent, "build", lambda *a, **k: FakeService(calls))
    monkeypatch.setattr(mail_agent, "SafeGmailProxy", lambda target: target)
    return calls


THREADED = dict(
    EMAIL, thread_id="t99", message_id="<orig@pelda.hu>",
    references="<older@pelda.hu>", reply_to="",
)


def _session_ready_to_save(can_draft=True, email=None):
    """A session that already holds a generated draft for EMAIL m1."""
    sid, h = _session_with([dict(email or THREADED)])
    s = mail_agent._sessions[sid]
    s["can_draft"] = can_draft
    s["drafts"]["m1:hivatalos"] = {
        "tone": "hivatalos", "targy": "Árajánlat", "valasz": "Kedves A!\n\nKöszönjük.",
    }
    return sid, h


def test_saving_a_draft_requires_a_session():
    r = c.post("/api/agent/email/draft/save", json={"id": "m1", "confirm": True})
    assert r.status_code == 401


def test_saving_is_refused_without_the_grant(gmail_calls):
    sid, h = _session_ready_to_save(can_draft=False)
    try:
        r = c.post("/api/agent/email/draft/save",
                   json={"id": "m1", "confirm": True}, headers=h)
        assert r.status_code == 403
        assert "vázlatírási engedély" in r.json()["detail"]
        assert gmail_calls == [], "Gmail was touched without the grant"
    finally:
        mail_agent._sessions.pop(sid, None)


def test_saving_is_refused_without_confirmation(gmail_calls):
    """The mailbox is never written on an unconfirmed request, grant or no grant."""
    sid, h = _session_ready_to_save()
    try:
        for payload in ({"id": "m1"}, {"id": "m1", "confirm": False}):
            r = c.post("/api/agent/email/draft/save", json=payload, headers=h)
            assert r.status_code == 400, payload
            assert "Megerősítés nélkül" in r.json()["detail"]
        assert gmail_calls == [], "Gmail was touched without confirmation"
    finally:
        mail_agent._sessions.pop(sid, None)


def test_saving_needs_an_existing_draft(gmail_calls):
    sid, h = _session_with([dict(THREADED)])
    mail_agent._sessions[sid]["can_draft"] = True
    try:
        r = c.post("/api/agent/email/draft/save",
                   json={"id": "m1", "confirm": True}, headers=h)
        assert r.status_code == 409
        assert gmail_calls == []
    finally:
        mail_agent._sessions.pop(sid, None)


def test_confirmed_save_creates_a_threaded_reply_draft(gmail_calls):
    sid, h = _session_ready_to_save()
    try:
        r = c.post("/api/agent/email/draft/save",
                   json={"id": "m1", "confirm": True}, headers=h)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["draft_id"] == "draft-1"
        assert body["updated"] is False
        assert body["to"] == "a@b.hu"
        assert body["subject"] == "Re: Árajánlat"
        assert "draft-1" in body["gmail_url"]

        assert len(gmail_calls) == 1
        op, user, payload = gmail_calls[0]
        assert (op, user) == ("create", "me")
        assert payload["message"]["threadId"] == "t99"

        # Parsed, not string-matched: a Hungarian subject is RFC 2047 encoded
        # (=?utf-8?q?...?=), so asserting on the raw bytes would either fail on
        # correct output or pass on mojibake.
        msg = message_from_bytes(
            base64.urlsafe_b64decode(payload["message"]["raw"]), policy=policy.default
        )
        assert msg["To"] == "a@b.hu"
        assert msg["From"] == "teszt@example.com"
        assert str(make_header(decode_header(msg["Subject"]))) == "Re: Árajánlat"
        # threading headers, not just Gmail's threadId
        assert msg["In-Reply-To"] == "<orig@pelda.hu>"
        assert msg["References"] == "<older@pelda.hu> <orig@pelda.hu>"
        assert "Köszönjük" in msg.get_content()
    finally:
        mail_agent._sessions.pop(sid, None)


def test_reply_to_wins_over_from(gmail_calls):
    sid, h = _session_ready_to_save(email=dict(THREADED, reply_to="ugyfelszolgalat@b.hu"))
    try:
        r = c.post("/api/agent/email/draft/save",
                   json={"id": "m1", "confirm": True}, headers=h)
        assert r.json()["to"] == "ugyfelszolgalat@b.hu"
        msg = message_from_bytes(base64.urlsafe_b64decode(gmail_calls[0][2]["message"]["raw"]))
        assert msg["To"] == "ugyfelszolgalat@b.hu"
    finally:
        mail_agent._sessions.pop(sid, None)


def test_reconfirming_updates_the_same_draft(gmail_calls):
    """A second confirmation must not leave a pile of near-identical drafts."""
    sid, h = _session_ready_to_save()
    try:
        c.post("/api/agent/email/draft/save", json={"id": "m1", "confirm": True}, headers=h)
        r = c.post("/api/agent/email/draft/save", json={"id": "m1", "confirm": True}, headers=h)
        assert r.status_code == 200
        assert r.json()["updated"] is True
        assert r.json()["draft_id"] == "draft-1"
        assert [call[0] for call in gmail_calls] == ["create", "update"]
    finally:
        mail_agent._sessions.pop(sid, None)


def test_unanswerable_sender_is_refused(gmail_calls):
    sid, h = _session_ready_to_save(email=dict(THREADED, sender="", reply_to=""))
    try:
        r = c.post("/api/agent/email/draft/save",
                   json={"id": "m1", "confirm": True}, headers=h)
        assert r.status_code == 422
        assert gmail_calls == []
    finally:
        mail_agent._sessions.pop(sid, None)


def test_gmail_refusal_is_a_502_not_a_crash(monkeypatch):
    class Boom:
        def users(self):
            raise RuntimeError("gmail said no")
    monkeypatch.setattr(mail_agent, "build", lambda *a, **k: Boom())
    monkeypatch.setattr(mail_agent, "SafeGmailProxy", lambda t: t)
    sid, h = _session_ready_to_save()
    try:
        r = c.post("/api/agent/email/draft/save",
                   json={"id": "m1", "confirm": True}, headers=h)
        assert r.status_code == 502
        assert "nem fogadta el" in r.json()["detail"]
    finally:
        mail_agent._sessions.pop(sid, None)


def test_subject_is_normalised_to_a_reply():
    f = mail_agent._reply_subject
    assert f("Árajánlat") == "Re: Árajánlat"
    assert f("Re: Árajánlat") == "Re: Árajánlat"
    assert f("RE: Árajánlat") == "RE: Árajánlat"
    assert f("") == "Re:"
    # A „nincs tárgy" feliratot már nem a kiszolgáló teszi a levélre, hanem a
    # lap írja ki a saját nyelvén, tehát ide sosem jut el.


def test_status_reports_draft_permission():
    body = c.get("/api/agent/email/status").json()
    assert body["can_draft"] is False, "no session means no draft permission"


def test_granted_scopes_decide_not_what_was_requested():
    """A visitor can untick a scope on Google's consent screen. Asking is not
    receiving, and the page must not offer a button that cannot work."""
    class Creds:
        def __init__(self, scopes):
            self.granted_scopes = scopes
    g = mail_agent._granted_compose
    assert g(Creds([mail_agent.COMPOSE_SCOPE]), requested=True) is True
    assert g(Creds(["https://www.googleapis.com/auth/gmail.readonly"]), requested=True) is False
    assert g(Creds([]), requested=True) is True, "no list reported -> fall back to request"
    assert g(Creds([]), requested=False) is False


def test_connect_carries_the_draft_choice_into_the_oauth_state(monkeypatch):
    """The callback must rebuild the flow with the same scopes, or Google rejects
    the exchange."""
    seen = {}

    class FakeFlow:
        code_verifier = None

        def authorization_url(self, **kw):
            seen["state"] = kw.get("state")
            return ("https://accounts.google.com/fake", kw.get("state"))

    def fake_flow(with_compose=False):
        seen["with_compose"] = with_compose
        return FakeFlow()

    monkeypatch.setattr(mail_agent, "_flow", fake_flow)

    c.get("/api/agent/email/connect")
    assert seen["with_compose"] is False
    # the choice rides in the state itself, so a restart cannot lose it
    assert mail_agent._unpack_state(seen["state"])["with_compose"] is False

    c.get("/api/agent/email/connect?drafts=true")
    assert seen["with_compose"] is True
    assert mail_agent._unpack_state(seen["state"])["with_compose"] is True


def test_the_oauth_handoff_survives_a_restart():
    """It used to live in a module-level dict, so a deploy between clicking
    connect and returning from Google produced "Lejárt a folyamat" for a flow
    that was seconds old."""
    verifier = mail_agent._new_code_verifier()
    state = mail_agent._pack_state(verifier, with_compose=True)
    # a restart clears every in-memory store; the state must still resolve
    mail_agent._sessions.clear()
    out = mail_agent._unpack_state(state)
    assert out == {"verifier": verifier, "with_compose": True, "lang": "hu"}


def test_a_forged_or_tampered_state_is_refused():
    verifier = mail_agent._new_code_verifier()
    state = mail_agent._pack_state(verifier, with_compose=False)
    assert mail_agent._unpack_state("") is None
    assert mail_agent._unpack_state("hamisitvany") is None
    assert mail_agent._unpack_state(state[:-4] + "AAAA") is None, "tampering must not verify"
    assert mail_agent._unpack_state(state) is not None


def test_an_expired_state_is_refused(monkeypatch):
    verifier = mail_agent._new_code_verifier()
    state = mail_agent._pack_state(verifier, with_compose=False)
    monkeypatch.setattr(mail_agent, "OAUTH_STATE_TTL_SECONDS", 0)
    import time
    time.sleep(1.1)
    assert mail_agent._unpack_state(state) is None


def test_the_state_does_not_expose_the_verifier():
    """It travels through the visitor's browser and Google's servers."""
    verifier = mail_agent._new_code_verifier()
    state = mail_agent._pack_state(verifier, with_compose=True)
    assert verifier not in state
    assert "with_compose" not in state


def test_code_verifier_shape_matches_what_google_expects():
    v = mail_agent._new_code_verifier()
    assert len(v) == 128
    allowed = set(string.ascii_letters + string.digits + "-._~")
    assert set(v) <= allowed
    assert mail_agent._new_code_verifier() != v, "must not be predictable"


def test_connect_seals_the_generated_verifier_into_the_state(monkeypatch):
    """authorization_url only generates a verifier when it is still None, so the
    one sealed into the state must be the one actually used."""
    captured = {}

    class FakeFlow:
        code_verifier = None

        def authorization_url(self, **kw):
            captured["verifier_at_call"] = self.code_verifier
            captured["state"] = kw.get("state")
            return ("https://accounts.google.com/fake", kw.get("state"))

    monkeypatch.setattr(mail_agent, "_flow", lambda with_compose=False: FakeFlow())
    c.get("/api/agent/email/connect?drafts=true")
    assert captured["verifier_at_call"], "no verifier was set before the URL was built"
    assert mail_agent._unpack_state(captured["state"])["verifier"] == captured["verifier_at_call"]


# ---------------- sending ----------------
class FakeDraftsSend(FakeDrafts):
    def send(self, userId, body):
        self.store.append(("send", userId, body["id"]))
        return _Exec({"id": "sent-1", "threadId": "t99"})


class FakeUsersSend(FakeUsers):
    def __init__(self, store):
        self._d = FakeDraftsSend(store)


class FakeServiceSend(FakeService):
    def __init__(self, store):
        self._u = FakeUsersSend(store)


@pytest.fixture
def gmail_send_calls(monkeypatch):
    calls = []
    monkeypatch.setattr(mail_agent, "build", lambda *a, **k: FakeServiceSend(calls))
    monkeypatch.setattr(mail_agent, "SafeGmailProxy", lambda target, allow_send=False: target)
    return calls


def test_send_requires_a_session():
    r = c.post("/api/agent/email/draft/send", json={"id": "m1", "confirm": True})
    assert r.status_code == 401


def test_send_is_refused_without_the_grant(gmail_send_calls):
    sid, h = _session_ready_to_save(can_draft=False)
    try:
        r = c.post("/api/agent/email/draft/send",
                   json={"id": "m1", "confirm": True}, headers=h)
        assert r.status_code == 403
        assert gmail_send_calls == [], "Gmail was touched without the grant"
    finally:
        mail_agent._sessions.pop(sid, None)


def test_send_is_refused_without_confirmation(gmail_send_calls):
    """Sending cannot be undone; an unconfirmed request must never reach Gmail."""
    sid, h = _session_ready_to_save()
    try:
        for payload in ({"id": "m1"}, {"id": "m1", "confirm": False}):
            r = c.post("/api/agent/email/draft/send", json=payload, headers=h)
            assert r.status_code == 400, payload
            assert "Megerősítés nélkül nem küldünk" in r.json()["detail"]
        assert gmail_send_calls == []
    finally:
        mail_agent._sessions.pop(sid, None)


def test_send_needs_an_existing_draft(gmail_send_calls):
    """Nothing is ever sent that the user has not read on the page."""
    sid, h = _session_with([dict(THREADED)])
    mail_agent._sessions[sid]["can_draft"] = True
    try:
        r = c.post("/api/agent/email/draft/send",
                   json={"id": "m1", "confirm": True}, headers=h)
        assert r.status_code == 409
        assert gmail_send_calls == []
    finally:
        mail_agent._sessions.pop(sid, None)


def test_confirmed_send_creates_then_sends_that_draft(gmail_send_calls):
    sid, h = _session_ready_to_save()
    try:
        r = c.post("/api/agent/email/draft/send",
                   json={"id": "m1", "confirm": True}, headers=h)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["message_id"] == "sent-1"
        assert body["to"] == "a@b.hu"
        assert body["subject"] == "Re: Árajánlat"

        ops = [call[0] for call in gmail_send_calls]
        assert ops == ["create", "send"], ops
        # what is sent is the draft that was built, by id — not a second compose
        assert gmail_send_calls[1][2] == "draft-1"
        msg = message_from_bytes(
            base64.urlsafe_b64decode(gmail_send_calls[0][2]["message"]["raw"]),
            policy=policy.default,
        )
        assert msg["To"] == "a@b.hu"
        assert msg["In-Reply-To"] == "<orig@pelda.hu>"
    finally:
        mail_agent._sessions.pop(sid, None)


def test_send_reuses_an_already_saved_draft(gmail_send_calls):
    """If the user saved first and then sent, the saved draft is updated and sent,
    not duplicated."""
    sid, h = _session_ready_to_save()
    mail_agent._sessions[sid]["saved"]["m1"] = "draft-existing"
    try:
        c.post("/api/agent/email/draft/send", json={"id": "m1", "confirm": True}, headers=h)
        ops = [call[0] for call in gmail_send_calls]
        assert ops == ["update", "send"], ops
        assert gmail_send_calls[1][2] == "draft-existing"
    finally:
        mail_agent._sessions.pop(sid, None)


def test_one_email_cannot_be_answered_twice(gmail_send_calls):
    """A double click or a replayed request must not send a second reply."""
    sid, h = _session_ready_to_save()
    try:
        first = c.post("/api/agent/email/draft/send",
                       json={"id": "m1", "confirm": True}, headers=h)
        assert first.status_code == 200
        second = c.post("/api/agent/email/draft/send",
                        json={"id": "m1", "confirm": True}, headers=h)
        assert second.status_code == 409
        assert "már küldtünk választ" in second.json()["detail"]
        assert [call[0] for call in gmail_send_calls].count("send") == 1
    finally:
        mail_agent._sessions.pop(sid, None)


def test_sent_message_carries_no_ai_draft_notice(gmail_send_calls):
    """The notice is for the reader of the page, not for the recipient: shipping
    'this is an AI draft' to a customer would be nonsense."""
    sid, h = _session_ready_to_save()
    mail_agent._sessions[sid]["drafts"]["m1:hivatalos"] = {
        "tone": "hivatalos", "targy": "Árajánlat",
        "valasz": f"Kedves A!\n\nKöszönjük.\n\n{server.AI_NOTICE}",
    }
    try:
        c.post("/api/agent/email/draft/send", json={"id": "m1", "confirm": True}, headers=h)
        msg = message_from_bytes(
            base64.urlsafe_b64decode(gmail_send_calls[0][2]["message"]["raw"]),
            policy=policy.default,
        )
        content = msg.get_content()
        assert server.AI_NOTICE not in content
        assert "Köszönjük" in content
    finally:
        mail_agent._sessions.pop(sid, None)


def test_saved_draft_carries_no_ai_draft_notice_either(gmail_calls):
    """A saved draft is one click from going out, so it must not carry it either."""
    sid, h = _session_ready_to_save()
    mail_agent._sessions[sid]["drafts"]["m1:hivatalos"] = {
        "tone": "hivatalos", "targy": "Árajánlat",
        "valasz": f"Kedves A!\n\nKöszönjük.\n\n{server.AI_NOTICE}",
    }
    try:
        c.post("/api/agent/email/draft/save", json={"id": "m1", "confirm": True}, headers=h)
        msg = message_from_bytes(
            base64.urlsafe_b64decode(gmail_calls[0][2]["message"]["raw"]),
            policy=policy.default,
        )
        assert server.AI_NOTICE not in msg.get_content()
    finally:
        mail_agent._sessions.pop(sid, None)


def test_send_failure_is_a_502_and_does_not_mark_it_sent(monkeypatch):
    class Boom:
        def users(self):
            raise RuntimeError("gmail said no")
    monkeypatch.setattr(mail_agent, "build", lambda *a, **k: Boom())
    monkeypatch.setattr(mail_agent, "SafeGmailProxy", lambda t, allow_send=False: t)
    sid, h = _session_ready_to_save()
    try:
        r = c.post("/api/agent/email/draft/send",
                   json={"id": "m1", "confirm": True}, headers=h)
        assert r.status_code == 502
        assert "Vázlatok" in r.json()["detail"], "a failed send should point somewhere useful"
        assert mail_agent._sessions[sid]["sent"] == {}, "a failed send must not block a retry"
    finally:
        mail_agent._sessions.pop(sid, None)


# ---------------- the run itself ----------------
def test_reads_fifty_emails():
    assert mail_agent.MAX_EMAILS == 50
    src = open(BACKEND / "mail_agent.py").read()
    assert "maxResults=MAX_EMAILS" in src, "the Gmail query must follow the constant"


def _run_session(ids):
    from datetime import datetime, timezone
    sid = "run-test"
    mail_agent._sessions[sid] = {
        "email": "teszt@example.com", "creds": None, "analyses": [],
        "can_draft": False, "drafts": {}, "saved": {}, "sent": {},
        "state": mail_agent._new_state(), "created_at": datetime.now(timezone.utc),
    }
    return sid


class RunFakeService:
    """Gmail stub for a whole run: lists ids, returns a message per id."""
    def __init__(self, ids, tracker):
        self._ids, self._t = ids, tracker

    def users(self):
        return self

    def messages(self):
        return self

    def list(self, userId, maxResults, q):
        self._t["max_results"] = maxResults
        return _Exec({"messages": [{"id": i} for i in self._ids[:maxResults]]},
                     self._t.setdefault("https", []))

    def get(self, userId, id, format):
        return _Exec({
            "id": id, "threadId": f"t{id}", "snippet": "s",
            "payload": {"headers": [{"name": "From", "value": f"{id}@x.hu"},
                                    {"name": "Subject", "value": f"Tárgy {id}"}],
                        "mimeType": "text/plain", "body": {}},
        }, self._t.setdefault("https", []))


def _install_run_stubs(monkeypatch, ids, classify):
    tracker = {"max_results": None, "peak": 0, "live": 0}
    monkeypatch.setattr(mail_agent, "build", lambda *a, **k: RunFakeService(ids, tracker))
    monkeypatch.setattr(mail_agent, "SafeGmailProxy", lambda t, allow_send=False: t)

    async def wrapped(email, lang="hu"):
        tracker["live"] += 1
        tracker["peak"] = max(tracker["peak"], tracker["live"])
        try:
            return await classify(email, lang)
        finally:
            tracker["live"] -= 1

    monkeypatch.setattr(server, "classify_one", wrapped)
    return tracker


def test_a_full_run_classifies_every_email(monkeypatch):
    import asyncio
    ids = [f"m{i}" for i in range(50)]

    async def classify(email, lang='hu'):
        await asyncio.sleep(0)
        return {"category": "other", "urgency": 1, "needs_reply": "nem",
                "urgency_reason": "", "deadline": "", "summary": "", "next_step": ""}

    tracker = _install_run_stubs(monkeypatch, ids, classify)
    sid = _run_session(ids)
    try:
        asyncio.run(mail_agent.run_agent(sid))
        sess = mail_agent._sessions[sid]
        assert tracker["max_results"] == 50
        assert sess["state"]["total"] == 50
        assert sess["state"]["done"] == 50
        assert sess["state"]["errors"] == 0
        assert len(sess["analyses"]) == 50
        assert sess["state"]["message"] == "done"
        assert sess["state"]["running"] is False
    finally:
        mail_agent._sessions.pop(sid, None)


def test_the_run_is_concurrent_but_bounded(monkeypatch):
    """Sequentially this would be 50 round trips end to end. Concurrency is the
    point — but unbounded it would hammer Gmail and OpenAI at once."""
    import asyncio
    ids = [f"m{i}" for i in range(50)]

    async def classify(email, lang='hu'):
        await asyncio.sleep(0.01)  # long enough for overlap to show
        return {"category": "other", "urgency": 1, "needs_reply": "nem",
                "urgency_reason": "", "deadline": "", "summary": "", "next_step": ""}

    tracker = _install_run_stubs(monkeypatch, ids, classify)
    sid = _run_session(ids)
    try:
        asyncio.run(mail_agent.run_agent(sid))
        assert tracker["peak"] > 1, "the run never overlapped — it is still sequential"
        assert tracker["peak"] <= mail_agent.RUN_CONCURRENCY, tracker["peak"]
    finally:
        mail_agent._sessions.pop(sid, None)


def test_one_bad_email_does_not_stop_the_rest(monkeypatch):
    import asyncio
    ids = [f"m{i}" for i in range(10)]

    async def classify(email, lang='hu'):
        if email["sender"].startswith("m3"):
            raise RuntimeError("boom")
        return {"category": "other", "urgency": 1, "needs_reply": "nem",
                "urgency_reason": "", "deadline": "", "summary": "", "next_step": ""}

    _install_run_stubs(monkeypatch, ids, classify)
    sid = _run_session(ids)
    try:
        asyncio.run(mail_agent.run_agent(sid))
        sess = mail_agent._sessions[sid]
        assert sess["state"]["errors"] == 1
        assert len(sess["analyses"]) == 9
        assert sess["state"]["message"] == "done"
    finally:
        mail_agent._sessions.pop(sid, None)


def test_hitting_the_budget_halts_the_run_once(monkeypatch):
    """Fifty emails must not produce fifty identical budget failures; the run
    stops and says why, and the count of attempts stays bounded."""
    import asyncio
    from fastapi import HTTPException
    ids = [f"m{i}" for i in range(50)]
    attempts = {"n": 0}

    async def classify(email, lang='hu'):
        attempts["n"] += 1
        if attempts["n"] > 3:
            raise HTTPException(status_code=429, detail="Az agent mára elérte a napi keretét.")
        return {"category": "other", "urgency": 1, "needs_reply": "nem",
                "urgency_reason": "", "deadline": "", "summary": "", "next_step": ""}

    _install_run_stubs(monkeypatch, ids, classify)
    sid = _run_session(ids)
    try:
        asyncio.run(mail_agent.run_agent(sid))
        sess = mail_agent._sessions[sid]
        assert sess["state"]["message"] == "budget"
        assert sess["state"]["errors"] == 0, "a budget stop is not a per-email error"
        # at most one extra batch gets through before the halt is seen
        assert attempts["n"] <= 3 + mail_agent.RUN_CONCURRENCY, attempts["n"]
        assert sess["state"]["running"] is False
    finally:
        mail_agent._sessions.pop(sid, None)


def test_a_visitor_leaving_mid_run_stops_the_work(monkeypatch):
    import asyncio
    ids = [f"m{i}" for i in range(50)]
    sid = _run_session(ids)

    async def classify(email, lang='hu'):
        # drop the session as soon as the first email is classified
        mail_agent._sessions.pop(sid, None)
        return {"category": "other", "urgency": 1, "needs_reply": "nem",
                "urgency_reason": "", "deadline": "", "summary": "", "next_step": ""}

    tracker = _install_run_stubs(monkeypatch, ids, classify)
    # held directly: the run removes it from _sessions, and the point is what it
    # stopped doing, not the size of a global dict other tests also write to
    sess = mail_agent._sessions[sid]
    try:
        asyncio.run(mail_agent.run_agent(sid))
        assert tracker["live"] == 0, "work was still in flight when the run returned"
        assert sid not in mail_agent._sessions
        assert len(sess["analyses"]) < len(ids), "the run kept going after the visitor left"
        assert sess["state"]["running"] is False
    finally:
        mail_agent._sessions.pop(sid, None)


def test_cost_knobs_are_env_tunable(monkeypatch):
    """A 50-email run costs ~50x a single call, so the ceiling has to be
    changeable on the service without a code deploy."""
    f = server._env_float
    monkeypatch.setenv("X_CEIL", "12.5")
    assert f("X_CEIL", 4.0) == 12.5
    monkeypatch.setenv("X_CEIL", "")
    assert f("X_CEIL", 4.0) == 4.0
    monkeypatch.setenv("X_CEIL", "nem szám")
    assert f("X_CEIL", 4.0) == 4.0, "a typo must not take the API down on boot"
    monkeypatch.delenv("X_CEIL", raising=False)
    assert f("X_CEIL", 4.0) == 4.0


def test_config_check_names_the_gap_without_leaking_values(monkeypatch, caplog):
    """A missing setting must be diagnosable from the deploy log — but a client
    secret must never appear in one."""
    import logging
    monkeypatch.setattr(mail_agent, "GOOGLE_CLIENT_ID", "")
    monkeypatch.setattr(mail_agent, "GOOGLE_CLIENT_SECRET", "titkos-ertek-123")
    monkeypatch.setattr(mail_agent, "GMAIL_REDIRECT_URI", "https://x/cb")
    monkeypatch.setattr(mail_agent, "SITE_URL", "https://x")
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "")  # set but empty
    with caplog.at_level(logging.WARNING, logger="mail_agent"):
        mail_agent._log_agent_config()
    text = caplog.text
    assert "GOOGLE_CLIENT_ID" in text
    assert "set but empty" in text
    assert "GOOGLE_CLIENT_SECRET" not in text, "a present setting should not be reported missing"
    assert "titkos-ertek-123" not in text, "a secret value reached the log"


def test_config_values_are_stripped():
    """A trailing newline in a dashboard variable is invisible and would break the
    redirect URI match at Google rather than here."""
    src = open(BACKEND / "mail_agent.py").read()
    for name in ("GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET", "AGENT_REDIRECT_URI", "FRONTEND_URL"):
        line = next(l for l in src.splitlines() if f'os.environ.get("{name}", "")' in l)
        assert line.rstrip().endswith('.strip()'), name


# ---------------- message body extraction ----------------
def _b64(text):
    """Gmail-style base64url, padding stripped the way Gmail often sends it."""
    return base64.urlsafe_b64encode(text.encode()).decode().rstrip("=")


def _part(mime, text=None, parts=None, attachment=False):
    body = {}
    if text is not None:
        body["data"] = _b64(text)
        body["size"] = len(text)
    if attachment:
        body = {"attachmentId": "att1", "size": 999}
    p = {"mimeType": mime, "body": body}
    if parts:
        p["parts"] = parts
    return p


BODY_TEXT = "Azonnali felszólítás!\n\nTelefonszámla befizetés!"


def test_plain_text_body_is_read():
    text, _ = mail_agent._body(_part("text/plain", BODY_TEXT))
    assert text == BODY_TEXT


def test_unpadded_base64_is_still_decoded():
    """Gmail routinely omits the '=' padding. Strict decoding raised, which took
    the whole email out of the run as an unexplained error."""
    # both padding lengths Gmail can drop: one '=' and two
    for original in ("Azonnali felszolitas", "Telefonszamla"):
        data = _b64(original)
        assert len(data) % 4 != 0, f"{original!r} does not exercise padding"
        text, _ = mail_agent._body({"mimeType": "text/plain", "body": {"data": data}})
        assert text == original


def test_mime_type_with_parameters_is_not_missed():
    """'text/plain; charset=UTF-8' is valid and used to fail an equality check,
    losing the body silently."""
    text, _ = mail_agent._body(_part('text/plain; charset="UTF-8"', BODY_TEXT))
    assert text == BODY_TEXT
    text, _ = mail_agent._body(_part("TEXT/PLAIN", BODY_TEXT))
    assert text == BODY_TEXT


def test_multipart_alternative_prefers_plain_text():
    payload = _part("multipart/alternative", parts=[
        _part("text/plain", BODY_TEXT),
        _part("text/html", f"<p>{BODY_TEXT}</p>"),
    ])
    text, _ = mail_agent._body(payload)
    assert text == BODY_TEXT


def test_html_only_message_falls_back_to_stripped_html():
    payload = _part("multipart/alternative", parts=[
        _part("text/html", "<div>Azonnali<br>felszólítás</div><script>x=1</script>"),
    ])
    text, _ = mail_agent._body(payload)
    assert "Azonnali" in text and "felszólítás" in text
    assert "<div>" not in text
    assert "x=1" not in text, "script contents must not land in the body"


def test_nested_multipart_is_walked():
    payload = _part("multipart/mixed", parts=[
        _part("multipart/related", parts=[
            _part("multipart/alternative", parts=[_part("text/plain", BODY_TEXT)]),
        ]),
        _part("application/pdf", attachment=True),
    ])
    text, _ = mail_agent._body(payload)
    assert text == BODY_TEXT


def test_unknown_text_subtype_is_a_last_resort():
    payload = _part("multipart/alternative", parts=[_part("text/x-amp-html", "<p>Szia</p>")])
    text, _ = mail_agent._body(payload)
    assert "Szia" in text


def test_a_broken_part_yields_an_empty_body_not_a_lost_email():
    payload = {"mimeType": "text/plain", "body": {"data": "!!! nem base64 !!!"}}
    text, _ = mail_agent._body(payload)
    assert text == ""  # and crucially: no exception


def test_parse_survives_a_body_it_cannot_read():
    """_parse raising would drop the email from the run entirely."""
    msg = {"id": "m1", "threadId": "t1", "snippet": "elonezet",
           "payload": {"mimeType": "text/plain", "body": {"data": "***"},
                       "headers": [{"name": "From", "value": "a@b.hu"}]}}
    out = mail_agent._parse(msg)
    assert out["body"] == ""
    assert out["snippet"] == "elonezet"
    assert out["sender"] == "a@b.hu"


def test_empty_body_and_snippet_logs_the_payload_shape(caplog):
    """The case that sent me looking in the wrong place: no way to tell a
    genuinely empty email from one we failed to parse."""
    import logging
    msg = {"id": "m9", "snippet": "  ", "payload": _part("multipart/alternative", parts=[
        _part("text/plain", attachment=True),
        _part("text/html", attachment=True),
    ])}
    with caplog.at_level(logging.WARNING, logger="mail_agent"):
        out = mail_agent._parse(msg)
    assert out["body"] == ""
    assert "m9" in caplog.text
    assert "multipart/alternative" in caplog.text
    assert "attachment" in caplog.text, "the shape must say why there was no text"


def test_the_shape_log_never_carries_content(caplog):
    import logging
    secret = "SZIGORUAN-TITKOS-TARTALOM"
    msg = {"id": "m10", "snippet": "", "payload": _part("text/plain", secret)}
    with caplog.at_level(logging.WARNING, logger="mail_agent"):
        mail_agent._parse(msg)
    assert secret not in caplog.text


def test_every_threaded_gmail_call_gets_its_own_connection(monkeypatch):
    """httplib2 is not thread-safe. Sharing one connection across the run's worker
    threads does not raise — it crashes the interpreter, taking every in-memory
    session with it, which looks to the visitor like being dumped back on the
    connect screen for no reason."""
    import asyncio
    ids = [f"m{i}" for i in range(12)]

    async def classify(email, lang='hu'):
        await asyncio.sleep(0)
        return {"category": "other", "urgency": 1, "needs_reply": "nem",
                "urgency_reason": "", "deadline": "", "summary": "", "next_step": ""}

    tracker = _install_run_stubs(monkeypatch, ids, classify)
    sid = _run_session(ids)
    try:
        asyncio.run(mail_agent.run_agent(sid))
        seen = tracker["https"]
        assert len(seen) == len(ids) + 1, "list + one get per email"
        assert all(h is not None for h in seen), "a call reused the service's shared http"
        assert len({id(h) for h in seen}) == len(seen), "two calls shared one connection"
    finally:
        mail_agent._sessions.pop(sid, None)


def test_fresh_http_is_authorised_and_has_a_timeout():
    class Creds: pass
    http = mail_agent._fresh_http(Creds())
    assert isinstance(http, AuthorizedHttp)
    assert http.http.timeout == mail_agent.HTTP_TIMEOUT_SECONDS, "a hung call would wedge a worker"


# ---------------- sample inbox (no Google account) ----------------
@pytest.fixture
def stub_classifier(monkeypatch):
    seen = []

    async def fake(email, lang="hu"):
        seen.append(email)
        return {"category": "other", "urgency": 3, "needs_reply": "igen",
                "urgency_reason": "ok", "deadline": "", "summary": "ossz", "next_step": "lepes"}

    monkeypatch.setattr(server, "classify_one", fake)
    monkeypatch.setitem(server._state, "cost", 0.0)
    server._ip_hits.clear()
    return seen


def _sample_session():
    """Start a sample run and return (sid, headers)."""
    r = c.post("/api/agent/email/sample")
    assert r.status_code == 200, r.text
    token = r.json()["session"]
    sid = mail_agent._fernet.decrypt(token.encode()).decode()
    return sid, {mail_agent.SESSION_HEADER: token}


def test_sample_needs_no_google_account(stub_classifier):
    """The whole point: a visitor sees what the agent does without Google's
    unverified-app screen, and without handing anyone their mailbox."""
    sid, h = _sample_session()
    try:
        results = c.get("/api/agent/email/results", headers=h).json()
        assert results["total"] == len(mail_agent_sample.SAMPLE_EMAILS)
        assert len(stub_classifier) == results["total"], "every sample email was classified"
        status = c.get("/api/agent/email/status", headers=h).json()
        assert status["connected"] is True
        assert status["sample"] is True
        assert status["can_draft"] is False
    finally:
        mail_agent._sessions.pop(sid, None)


def test_a_sample_session_holds_no_credentials(stub_classifier):
    """Absent, not merely unused: no code path can reach a real mailbox from here
    even by mistake."""
    sid, _ = _sample_session()
    try:
        assert mail_agent._sessions[sid]["creds"] is None
        assert mail_agent._sessions[sid]["sample"] is True
    finally:
        mail_agent._sessions.pop(sid, None)


def test_sample_can_still_write_the_reply_text(stub_classifier, stub_draft):
    """The drafting is real — same model call as on a live mailbox."""
    sid, h = _sample_session()
    try:
        first = c.get("/api/agent/email/results", headers=h).json()["analyses"][0]
        r = c.post("/api/agent/email/draft", json={"id": first["id"]}, headers=h)
        assert r.status_code == 200, r.text
        assert r.json()["valasz"]
    finally:
        mail_agent._sessions.pop(sid, None)


def test_sample_refuses_to_save_or_send(stub_classifier, stub_draft, gmail_send_calls):
    """There is no mailbox and the recipients are invented. Both must say so
    plainly rather than sending the visitor off to reconnect."""
    sid, h = _sample_session()
    try:
        first = c.get("/api/agent/email/results", headers=h).json()["analyses"][0]
        c.post("/api/agent/email/draft", json={"id": first["id"]}, headers=h)
        for path in ("/api/agent/email/draft/save", "/api/agent/email/draft/send"):
            r = c.post(path, json={"id": first["id"], "confirm": True}, headers=h)
            assert r.status_code == 409, path
            assert "példa postafiók" in r.json()["detail"], path
        assert gmail_send_calls == [], "a sample run touched Gmail"
    finally:
        mail_agent._sessions.pop(sid, None)


def test_sample_dates_are_relative_to_now():
    """A demo where everything arrived six months ago gives itself away, and
    urgency is judged on the date."""
    from datetime import datetime, timezone
    from sample_inbox import sample_emails
    now = datetime.now(timezone.utc)
    emails = sample_emails(now)
    newest = max(datetime.fromisoformat(e["date"]) for e in emails)
    oldest = min(datetime.fromisoformat(e["date"]) for e in emails)
    assert (now - newest).total_seconds() < 60 * 60 * 24
    assert (now - oldest).days <= mail_agent.LOOKBACK_DAYS


def test_the_sample_inbox_is_not_all_urgent():
    """An inbox where everything matters proves nothing about triage."""
    from sample_inbox import SAMPLE_EMAILS
    assert len(SAMPLE_EMAILS) >= 8
    joined = " ".join(e["body"] for e in SAMPLE_EMAILS).lower()
    for expected in ("leiratkozás", "automatikus", "ne válaszoljon"):
        assert expected in joined, f"no low-priority mail in the sample: {expected}"
    assert any(e.get("attachments") for e in SAMPLE_EMAILS), "no attachment-only case"
    assert any(not e["subject"] for e in SAMPLE_EMAILS), "no missing-subject case"


def test_the_classifier_is_told_how_to_recognise_phishing():
    """Live, the sample's scam mail came out as the most urgent customer
    complaint. The rules that prevent that must stay in every language."""
    for lang in server.AGENT_LANG_NAMES:
        prompt = server.agent_sys(lang).lower()
        assert "phishing" in prompt, lang
        assert "not how loudly" in prompt, lang
        assert "never a customer complaint" in prompt, lang


def test_spam_is_never_urgent_and_never_needs_a_reply(monkeypatch):
    """Even when the model gets the category right but scores urgency by how
    loud the email is."""
    import asyncio

    async def fake_llm(system, text, max_tokens=0):
        return '{"category": "spam", "urgency": 5, "needs_reply": "igen"}'

    monkeypatch.setattr(server, "_call_llm", fake_llm)
    out = asyncio.run(server.classify_one({"subject": "AZONNALI", "body": "fizess"}))
    assert out["category"] == "spam"
    assert out["urgency"] == 1
    assert out["needs_reply"] == "nem"


def test_sample_is_rate_limited_per_ip(stub_classifier, monkeypatch):
    """Public and it spends model credits on every call."""
    monkeypatch.setattr(server, "MAX_REQ_PER_IP_HOUR", 3)
    server._ip_hits.clear()
    made = []
    try:
        for _ in range(3):
            r = c.post("/api/agent/email/sample")
            assert r.status_code == 200
            made.append(mail_agent._fernet.decrypt(r.json()["session"].encode()).decode())
        r = c.post("/api/agent/email/sample")
        assert r.status_code == 429
    finally:
        for sid in made:
            mail_agent._sessions.pop(sid, None)
        server._ip_hits.clear()


def test_sample_run_uses_one_wave(monkeypatch):
    """A példa-postafiók tíz levele egyszerre fusson.

    Öt szálon két hullám lesz belőle, és a látogató első benyomása a
    kétszeres várakozás. Az éles postafiók ettől külön marad (RUN_CONCURRENCY),
    mert ott ötven levél is lehet — ezt is állítja a teszt.
    """
    import asyncio
    from datetime import datetime, timezone

    assert mail_agent.SAMPLE_CONCURRENCY >= 10
    assert mail_agent.RUN_CONCURRENCY == 5, "az éles futás maradjon óvatos"

    peak = {"now": 0, "max": 0}

    async def slow_classify(email, lang='hu'):
        peak["now"] += 1
        peak["max"] = max(peak["max"], peak["now"])
        await asyncio.sleep(0.02)
        peak["now"] -= 1
        return {"category": "other", "urgency": 1, "needs_reply": "nem", "summary": "x"}

    import server
    monkeypatch.setattr(server, "classify_one", slow_classify)

    sid = "sample-wave"
    mail_agent._sessions[sid] = {
        "creds": None, "email": "peldа@example.com", "analyses": [], "drafts": {},
        "saved": {}, "sent": {}, "created_at": datetime.now(timezone.utc),
        "state": {"running": False, "done": 0, "total": 0, "errors": 0, "message": ""},
        "sample": True, "can_draft": False,
    }
    try:
        asyncio.run(mail_agent.run_sample(sid))
        assert peak["max"] == 10, f"egy hullám helyett {peak['max']} párhuzamos hívás"
        assert len(mail_agent._sessions[sid]["analyses"]) == 10
    finally:
        mail_agent._sessions.pop(sid, None)


# ---------------------------------------------------------------- nyelvek ---
# Az oldal nyolc nyelven fut. A futás kimenete — összefoglaló, indoklás,
# javasolt lépés — a felület nyelvén kell hogy készüljön, különben a német
# látogató magyar mondatokat kap a saját postafiókjáról.


def test_the_run_language_reaches_the_classifier(monkeypatch):
    import asyncio
    from datetime import datetime, timezone
    seen = {}

    async def fake(email, lang="hu"):
        seen["lang"] = lang
        return {"category": "other", "urgency": 1, "needs_reply": "nem",
                "urgency_reason": "", "deadline": "", "summary": "", "next_step": ""}

    monkeypatch.setattr(server, "classify_one", fake)
    sid = "lang-run"
    mail_agent._sessions[sid] = {
        "creds": None, "email": "p@example.com", "analyses": [], "drafts": {}, "saved": {},
        "sent": {}, "created_at": datetime.now(timezone.utc), "state": mail_agent._new_state(),
        "sample": True, "can_draft": False, "lang": "de",
    }
    try:
        asyncio.run(mail_agent.run_sample(sid))
        assert seen["lang"] == "de"
    finally:
        mail_agent._sessions.pop(sid, None)


def test_an_unknown_language_falls_back_instead_of_failing():
    """Egy elgépelt nyelvkód nem indok arra, hogy egy demó megálljon."""
    assert mail_agent._safe_lang("de") == "de"
    assert mail_agent._safe_lang("klingon") == "hu"
    assert mail_agent._safe_lang(None) == "hu"
    assert mail_agent._safe_lang("") == "hu"


def test_the_language_survives_the_oauth_round_trip():
    state = mail_agent._pack_state("verifier-123", True, "fr")
    assert mail_agent._unpack_state(state)["lang"] == "fr"
    # Ismeretlen kód a csomagolásnál is magyarra esik vissza.
    state = mail_agent._pack_state("verifier-123", False, "xx")
    assert mail_agent._unpack_state(state)["lang"] == "hu"


def test_every_language_of_the_ai_notice_is_stripped_before_sending():
    """A fogalmazvány nyelve és a felületé nem feltétlenül ugyanaz.

    Egy bent felejtett „AI draft" sor az ügyfél postafiókjában derülne ki, ezért
    a kimenő szövegből mindegyik nyelvi változatot ki kell szedni, nem csak az
    aktuálisat.
    """
    for lang, notice in server.AI_NOTICES.items():
        body = mail_agent._outgoing_body(f"Kedves A!\n\nKöszönjük.\n\n{notice}")
        assert notice not in body, lang
        assert "Köszönjük." in body


def test_the_draft_notice_is_written_in_the_interface_language(monkeypatch):
    import asyncio

    async def fake_llm(system_msg, user_text, max_tokens=600):
        assert server.AI_NOTICES["es"] in system_msg, "a promptba a felület nyelve kerüljön"
        return '{"targy":"Asunto","valasz":"Hola,\\n\\nGracias."}'

    monkeypatch.setattr(server, "_call_llm", fake_llm)
    monkeypatch.setitem(server._state, "cost", 0.0)
    out = asyncio.run(server.draft_one({"subject": "x", "body": "Hola"}, "hivatalos", "es"))
    assert out["valasz"].rstrip().endswith(server.AI_NOTICES["es"])


def test_the_classifier_prompt_names_the_language(monkeypatch):
    import asyncio
    seen = {}

    async def fake_llm(system_msg, user_text, max_tokens=600):
        seen["sys"] = system_msg
        return '{"category":"other","urgency":1,"needs_reply":"nem"}'

    monkeypatch.setattr(server, "_call_llm", fake_llm)
    monkeypatch.setitem(server._state, "cost", 0.0)
    asyncio.run(server.classify_one({"subject": "x", "body": "y"}, "sk"))
    assert "po slovensky" in seen["sys"]


def test_the_callback_returns_to_the_page_in_the_visitor_s_language():
    """A Google-kör után ne a magyar lapon kössön ki, aki angolul indult.

    Ez volt az a hiba, amitől a látogató angolról indult, végigment a
    beleegyezésen, és magyar felületen találta magát a saját postafiókjával.
    """
    import mail_agent
    from fastapi.testclient import TestClient
    from fastapi import FastAPI

    app = FastAPI()
    app.include_router(mail_agent.router)
    client = TestClient(app, follow_redirects=False)

    for lang, expected in (("en", "/en/demo/email-agent"), ("de", "/de/demo/email-agent"),
                           ("hu", "/demo/email-agent")):
        state = mail_agent._pack_state("verifier", False, lang)
        r = client.get(f"/api/agent/email/callback?error=access_denied&state={state}")
        assert r.status_code in (302, 307), r.status_code
        assert expected in r.headers["location"], (lang, r.headers["location"])
        assert "error=access_denied" in r.headers["location"]


def test_the_run_state_speaks_in_keys_not_hungarian():
    """A futás állapotát a lap fordítja; a kiszolgáló kulcsot ad.

    Amíg magyar mondat volt, egy angol lapon is magyarul állt ott, hogy
    „Feldolgozás folyamatban…".
    """
    import pathlib as _pathlib

    import mail_agent

    source = _pathlib.Path(mail_agent.__file__).read_text(encoding="utf-8")
    body = "\n".join(l for l in source.split("\n")
                     if 'state["message"]' in l or '"message":' in l)
    for hungarian in ("Feldolgozás", "Levelek lekérése", "Kész", "megszakadt", "Nincs feldolgozható"):
        assert hungarian not in body, f"a kiszolgáló magyar állapotüzenetet küld: {hungarian}"


# ------------------------------------------------------------------ keresés ---
# A futás az elmúlt 30 nap ötven levelét nézi. A keresés a Gmail saját
# keresőjét kérdezi, tehát régebbi levél is előkerül — ez a különbség a kettő
# között, és ezt a tesztek is így nézik.


class SearchFakeService:
    """Gmail-csonk kereséshez: rögzíti a lekérdezést, id-ket ad vissza."""

    def __init__(self, ids, tracker):
        self._ids, self._t = ids, tracker

    def users(self):
        return self

    def messages(self):
        return self

    def list(self, userId, maxResults, q):
        self._t["q"] = q
        self._t["max_results"] = maxResults
        return _Exec({"messages": [{"id": i} for i in self._ids[:maxResults]]},
                     self._t.setdefault("https", []))

    def get(self, userId, id, format, metadataHeaders=None):
        self._t.setdefault("formats", []).append(format)
        return _Exec({
            "id": id, "threadId": f"t{id}", "snippet": f"részlet {id}",
            "payload": {"headers": [{"name": "From", "value": f"{id}@pelda.hu"},
                                    {"name": "Subject", "value": f"Neptun {id}"}],
                        "mimeType": "text/plain", "body": {}},
        }, self._t.setdefault("https", []))


def _search_session(monkeypatch, ids):
    tracker = {}
    monkeypatch.setattr(mail_agent, "build", lambda *a, **k: SearchFakeService(ids, tracker))
    monkeypatch.setattr(mail_agent, "SafeGmailProxy", lambda t, allow_send=False: t)
    sid, headers = _session_with([])
    mail_agent._sessions[sid]["creds"] = object()
    return sid, headers, tracker


def test_search_asks_gmail_and_keeps_its_order(monkeypatch):
    ids = ["b", "a", "c"]
    sid, headers, tracker = _search_session(monkeypatch, ids)
    client = c
    try:
        r = client.get("/api/agent/email/search?q=neptun", headers=headers)
        assert r.status_code == 200, r.text
        body = r.json()
        assert tracker["q"] == "neptun", "a beírt szó megy a Gmail keresőjébe"
        assert [e["id"] for e in body["results"]] == ids, "a Gmail sorrendje a relevancia"
        assert body["total"] == 3
        # Fejléc és részlet elég; a teljes törzs huszonöt levélre lassú lenne.
        assert set(tracker["formats"]) == {"metadata"}
    finally:
        mail_agent._sessions.pop(sid, None)


def test_search_needs_at_least_two_characters(monkeypatch):
    sid, headers, _ = _search_session(monkeypatch, ["a"])
    client = c
    try:
        for q in ("", " ", "a"):
            r = client.get(f"/api/agent/email/search?q={q}", headers=headers)
            assert r.status_code == 400, q
            assert r.json()["detail"]["code"] == "search_too_short"
    finally:
        mail_agent._sessions.pop(sid, None)


def test_search_is_capped_per_session(monkeypatch):
    sid, headers, _ = _search_session(monkeypatch, ["a"])
    client = c
    try:
        for _ in range(mail_agent.MAX_SEARCHES_PER_SESSION):
            assert client.get("/api/agent/email/search?q=szamla", headers=headers).status_code == 200
        r = client.get("/api/agent/email/search?q=szamla", headers=headers)
        assert r.status_code == 429
        assert r.json()["detail"]["code"] == "search_limit"
    finally:
        mail_agent._sessions.pop(sid, None)


def test_search_without_a_session_is_refused():
    client = c
    assert client.get("/api/agent/email/search?q=neptun").status_code == 401


def test_the_sample_inbox_is_searchable_without_google():
    """Belépés nélkül is ki lehessen próbálni — ez a demó fő útja."""
    from datetime import datetime, timezone

    emails = mail_agent_sample.sample_emails(datetime.now(timezone.utc))
    one = emails[0]
    word = one["subject"].split()[0].lower()
    hits = mail_agent._sample_search(emails, word)
    assert hits, f"a(z) {word!r} szóra legyen találat"
    assert all(word in " ".join([e["sender"], e["subject"], e["body"]]).lower() for e in hits)
    # Két szó: mindkettőnek szerepelnie kell, nem elég az egyik.
    assert mail_agent._sample_search(emails, "neptun kaposzta") == []
