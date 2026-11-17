import asyncio
import json

import pytest
from cryptography.fernet import Fernet
from fastapi import FastAPI
from fastapi.testclient import TestClient

import owner_inbox


@pytest.fixture()
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("OWNER_INBOX_KEY", "s3cret-key")
    monkeypatch.setenv("OWNER_INBOX_EMAILS", "a@example.com, B@example.com")
    monkeypatch.setenv("CONTINUOUS_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("CONTINUOUS_DB_PATH", str(tmp_path / "db.sqlite3"))
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "cid")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "csecret")
    monkeypatch.setenv("AGENT_REDIRECT_URI", "https://api.example.com/api/agent/email/callback")
    monkeypatch.setattr(owner_inbox, "_store", None)
    owner_inbox._used_links.clear()
    app = FastAPI()
    app.include_router(owner_inbox.router)
    return TestClient(app)


AUTH = {"Authorization": "Bearer s3cret-key"}


def test_unconfigured_is_503(monkeypatch):
    monkeypatch.delenv("OWNER_INBOX_KEY", raising=False)
    app = FastAPI(); app.include_router(owner_inbox.router)
    r = TestClient(app).get("/api/owner/inbox/accounts", headers=AUTH)
    assert r.status_code == 503


def test_requires_bearer(client):
    assert client.get("/api/owner/inbox/accounts").status_code == 401
    assert client.get("/api/owner/inbox/accounts", headers={"Authorization": "Bearer nope"}).status_code == 401
    assert client.get("/api/owner/inbox/accounts", headers=AUTH).status_code == 200


def test_connect_link_single_use_and_offline(client):
    url = client.post("/api/owner/inbox/connect-link", headers=AUTH).json()["url"]
    assert url.startswith("https://api.example.com/api/owner/inbox/connect?t=")
    assert "s3cret-key" not in url
    path = url.replace("https://api.example.com", "")
    r = client.get(path, follow_redirects=False)
    assert r.status_code in (302, 307)
    loc = r.headers["location"]
    assert "access_type=offline" in loc and "gmail.readonly" in loc
    assert "state=owner." in loc
    assert "gmail.compose" not in loc and "gmail.modify" not in loc
    again = client.get(path, follow_redirects=False)
    assert again.status_code == 400


def test_bad_link_rejected(client):
    assert client.get("/api/owner/inbox/connect?t=garbage").status_code == 400


def test_messages_unknown_and_unconnected(client):
    assert client.get("/api/owner/inbox/messages?account=x@example.com", headers=AUTH).status_code == 404
    assert client.get("/api/owner/inbox/messages?account=a@example.com", headers=AUTH).status_code == 404


def test_messages_reads_with_stored_token(client, monkeypatch):
    owner_inbox._get_store().add_account("a@example.com", "a@example.com", "rt-1")
    seen = {}

    def fake(token, q, limit):
        seen.update(token=token, q=q, limit=limit)
        return [{"id": "m1", "subject": "Hi"}]

    monkeypatch.setattr(owner_inbox, "_list_messages", fake)
    r = client.get("/api/owner/inbox/messages?account=A@example.com&limit=999", headers=AUTH)
    assert r.status_code == 200 and r.json()["count"] == 1
    assert seen == {"token": "rt-1", "q": owner_inbox.DEFAULT_QUERY, "limit": owner_inbox.MAX_RESULTS}


def test_callback_rejects_foreign_state(client):
    r = asyncio.run(owner_inbox.handle_callback("c", "owner.garbage", ""))
    assert r.status_code == 400


def test_is_owner_state():
    assert owner_inbox.is_owner_state("owner.abc")
    assert not owner_inbox.is_owner_state("gAAAA")
    assert not owner_inbox.is_owner_state("")
