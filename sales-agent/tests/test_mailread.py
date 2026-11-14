"""A csak olvasó postafiók-hozzáférés, hálózat nélkül."""
import importlib
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import mailread  # noqa: E402
from mailer import AuthError  # noqa: E402

TOKEN = "t" * 40


class FakeReader:
    opened: list[str] = []

    def __init__(self, user, pw):
        if pw == "rossz":
            raise AuthError("rossz jelszó")
        self.user = user.lower()
        FakeReader.opened.append(user)

    def search(self, key, q, limit):
        dates = {"all": "Fri, 13 Nov 2026 10:00:00 +0000", "spam": "Sat, 14 Nov 2026 10:00:00 +0000"}
        if key not in dates:
            return []
        return [{"account": self.user, "id": "1", "date": dates[key], "subject": f"{key}:{q}", "folder": key}]

    def get(self, msgid):
        return {"account": self.user, "id": msgid, "text": "szia"} if msgid == "42" else None

    def close(self):
        pass


@pytest.fixture
def accounts(monkeypatch):
    monkeypatch.setenv("GMAIL_USER", "aximbra@gmail.com")
    monkeypatch.setenv("GMAIL_APP_PASSWORD", "jo")
    monkeypatch.setenv("GMAIL_ACCOUNTS", "masik@gmail.com:rossz")
    FakeReader.opened = []


def test_search_merges_folders_newest_first_and_survives_bad_account(accounts):
    r = mailread.search("from:mailer-daemon", folders="all,spam", opener=FakeReader)
    assert [m["folder"] for m in r["results"]] == ["spam", "all"]
    assert r["results"][0]["subject"] == "spam:from:mailer-daemon"
    assert any("rossz" in e for e in r["errors"])


def test_search_rejects_unknown_account_and_long_query(accounts):
    with pytest.raises(ValueError):
        mailread.search("x", account="idegen@gmail.com", opener=FakeReader)
    with pytest.raises(ValueError):
        mailread.search("x" * 501, opener=FakeReader)


def test_query_quotes_and_newlines_are_stripped():
    assert mailread._clean_query('a"b\r\nc') == "a b  c"


def test_get_validates_id(accounts):
    with pytest.raises(ValueError):
        mailread.get("aximbra@gmail.com", "1 OR 2", opener=FakeReader)
    assert mailread.get("aximbra@gmail.com", "42", opener=FakeReader)["text"] == "szia"


def _client(tmp_path, monkeypatch, token=TOKEN):
    monkeypatch.setenv("SALES_DB_PATH", str(tmp_path / "mb.db"))
    monkeypatch.setenv("ADMIN_PASSWORD", "helyes-jelszo-123")
    if token is None:
        monkeypatch.delenv("MAILBOX_TOKEN", raising=False)
    else:
        monkeypatch.setenv("MAILBOX_TOKEN", token)
    import store as store_mod
    importlib.reload(store_mod)
    import app as app_mod
    importlib.reload(app_mod)
    from fastapi.testclient import TestClient
    return app_mod, TestClient(app_mod.app)


def test_api_requires_mailbox_token(tmp_path, monkeypatch, accounts):
    app_mod, c = _client(tmp_path, monkeypatch)
    assert c.get("/api/mailbox/accounts").status_code == 401
    # A panel jelszava nem elég.
    assert c.get("/api/mailbox/accounts", auth=("x", "helyes-jelszo-123")).status_code == 401
    r = c.get("/api/mailbox/accounts", headers={"X-Mailbox-Token": TOKEN})
    assert r.status_code == 200 and r.json()["accounts"] == ["aximbra@gmail.com", "masik@gmail.com"]


def test_api_disabled_without_long_token(tmp_path, monkeypatch, accounts):
    _, c = _client(tmp_path, monkeypatch, token="rovid")
    assert c.get("/api/mailbox/accounts", headers={"X-Mailbox-Token": "rovid"}).status_code == 503


def test_api_search_and_message(tmp_path, monkeypatch, accounts):
    app_mod, c = _client(tmp_path, monkeypatch)
    real_search, real_get = mailread.search, mailread.get
    monkeypatch.setattr(app_mod.mailread, "search", lambda *a, **k: real_search(*a, opener=FakeReader, **k))
    monkeypatch.setattr(app_mod.mailread, "get", lambda *a, **k: real_get(*a, opener=FakeReader, **k))
    h = {"X-Mailbox-Token": TOKEN}
    r = c.get("/api/mailbox/search", params={"q": "subject:teszt"}, headers=h)
    assert r.status_code == 200 and r.json()["results"]
    assert c.get("/api/mailbox/message", params={"account": "aximbra@gmail.com", "id": "42"}, headers=h).json()["text"] == "szia"
    assert c.get("/api/mailbox/message", params={"account": "aximbra@gmail.com", "id": "7"}, headers=h).status_code == 404
    assert c.get("/api/mailbox/message", params={"account": "aximbra@gmail.com", "id": "x"}, headers=h).status_code == 400


def test_api_locks_out_after_bad_tokens(tmp_path, monkeypatch, accounts):
    app_mod, c = _client(tmp_path, monkeypatch)
    monkeypatch.setattr(app_mod.time, "sleep", lambda s: None)
    for _ in range(app_mod.AUTH_FAIL_LIMIT):
        assert c.get("/api/mailbox/accounts", headers={"X-Mailbox-Token": "rossz"}).status_code == 401
    assert c.get("/api/mailbox/accounts", headers={"X-Mailbox-Token": TOKEN}).status_code == 429


def test_broken_sender_dsn_pauses_auto_sending(tmp_path):
    from datetime import datetime, timezone
    import pipeline
    from store import Store
    st = Store(str(tmp_path / "b.db"))
    log = pipeline.RunLog()
    dsn = {"subject": "Delivery Status Notification (Failure)", "date": "Fri, 13 Nov 2026 03:20:10 -0800",
           "text": "https://support.google.com/mail/?p=CustomFromDenied 502 5.7.0 Your SMTP account is not yet activated."}
    pipeline._detect_broken_sender(st, log, [{"subject": "x", "date": "", "text": "user unknown"}])
    assert st.get_setting("sender_broken_at") is None
    pipeline._detect_broken_sender(st, log, [dsn])
    assert st.get_setting("sender_broken_at") == "2026-11-13T11:20:10+00:00"
    assert pipeline.sender_blocked(st, datetime(2026, 11, 14, 10, tzinfo=timezone.utc))
    assert not pipeline.sender_blocked(st, datetime(2026, 11, 16, 10, tzinfo=timezone.utc))
    st.set_setting("auto_followup", "on")
    assert pipeline.auto_followups(st, log, now=datetime(2026, 11, 13, 13, tzinfo=timezone.utc)) == 0
    assert any("SZÜNETEL" in line for line in log.lines)
