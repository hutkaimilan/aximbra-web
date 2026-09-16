"""Az ajánlatkérő űrlap kiszolgálói oldala.

A hangsúly azon van, ami pénzbe kerül, ha elromlik: hogy soha ne mondjon
sikert, ha a levél nem ment el, és hogy amit a látogató beír, ne válhasson
levélfejléccé.
"""
import smtplib

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import lead_intake


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("SMTP_HOST", "smtp.example.org")
    monkeypatch.setenv("SMTP_USER", "kuldo@example.org")
    monkeypatch.setenv("SMTP_PASSWORD", "titok")
    monkeypatch.setenv("LEAD_TO", "cel@example.org")
    for name in ("RESEND_API_KEY", "RESEND_FROM"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setitem(lead_intake._smtp_reachable, "value", None)
    lead_intake._ip_hits.clear()
    lead_intake._day_state["count"] = 0
    app = FastAPI()
    app.include_router(lead_intake.router)
    return TestClient(app)


VALID = {
    "name": "Kovács Anna",
    "email": "anna@pelda.hu",
    "message": "Három webshopunk van, és a beérkező leveleket szeretnénk rendezni.",
    "company": "Példa Kft.",
    "consent": True,
    "elapsed_ms": 30000,
}


def _capture(monkeypatch):
    sent = []
    monkeypatch.setattr(lead_intake, "_send_sync", lambda cfg, msg: sent.append((cfg, msg)))
    return sent


def test_status_reports_configured(client):
    assert client.get("/api/contact/status").json() == {"configured": True}


def test_status_false_without_password(client, monkeypatch):
    monkeypatch.delenv("SMTP_PASSWORD")
    assert client.get("/api/contact/status").json() == {"configured": False}


def test_unconfigured_refuses_instead_of_pretending(client, monkeypatch):
    """Ez a lényeg: beállítás nélkül NEM 200, hogy a lap a levelezőprogramos
    utat kínálhassa fel ahelyett, hogy sikert hazudna."""
    monkeypatch.delenv("SMTP_HOST")
    r = client.post("/api/contact", json=VALID)
    assert r.status_code == 503


def test_valid_submission_is_sent(client, monkeypatch):
    sent = _capture(monkeypatch)
    r = client.post("/api/contact", json=VALID)
    assert r.status_code == 200 and r.json() == {"ok": True}
    cfg, msg = sent[0]
    assert msg["To"] == "cel@example.org"
    assert msg["Reply-To"] == "anna@pelda.hu"
    assert "Három webshopunk" in msg.get_content()
    assert "Példa Kft." in msg.get_content()


def test_header_injection_in_the_name_cannot_add_a_header(client, monkeypatch):
    sent = _capture(monkeypatch)
    evil = dict(VALID, name="Anna\nBcc: mindenki@example.net")
    assert client.post("/api/contact", json=evil).status_code == 200
    _, msg = sent[0]
    assert msg["Bcc"] is None
    assert "\n" not in msg["Subject"]


def test_consent_is_required(client, monkeypatch):
    _capture(monkeypatch)
    r = client.post("/api/contact", json=dict(VALID, consent=False))
    assert r.status_code == 400


def test_bad_email_is_rejected(client, monkeypatch):
    _capture(monkeypatch)
    for bad in ("nincs-kukac", "a@b", "a@@b.hu", "", "a b@c.hu"):
        assert client.post("/api/contact", json=dict(VALID, email=bad)).status_code == 400, bad


def test_short_message_is_rejected(client, monkeypatch):
    _capture(monkeypatch)
    assert client.post("/api/contact", json=dict(VALID, message="szia")).status_code == 400


def test_honeypot_is_silently_accepted_but_not_sent(client, monkeypatch):
    sent = _capture(monkeypatch)
    r = client.post("/api/contact", json=dict(VALID, website="http://spam.example"))
    assert r.status_code == 200        # a robot ne tanuljon belőle
    assert sent == []                  # de levél nem megy


def test_instant_submission_is_rejected(client, monkeypatch):
    _capture(monkeypatch)
    assert client.post("/api/contact", json=dict(VALID, elapsed_ms=300)).status_code == 400


def test_smtp_failure_is_reported_not_swallowed(client, monkeypatch):
    def boom(cfg, msg):
        raise smtplib.SMTPAuthenticationError(535, b"nope")
    monkeypatch.setattr(lead_intake, "_send_sync", boom)
    r = client.post("/api/contact", json=VALID)
    assert r.status_code == 502


def test_rate_limit_per_ip(client, monkeypatch):
    _capture(monkeypatch)
    for _ in range(lead_intake.MAX_PER_IP_HOUR):
        assert client.post("/api/contact", json=VALID).status_code == 200
    assert client.post("/api/contact", json=VALID).status_code == 429


def test_password_never_appears_in_the_message(client, monkeypatch):
    sent = _capture(monkeypatch)
    client.post("/api/contact", json=VALID)
    _, msg = sent[0]
    assert "titok" not in msg.get_content()


def _capture_resend(monkeypatch):
    sent = []

    async def fake(cfg, payload):
        sent.append((cfg, payload))

    monkeypatch.setattr(lead_intake, "_send_resend", fake)
    return sent


def test_resend_is_preferred_over_smtp(client, monkeypatch):
    """Élesben a Railway letiltja az SMTP-t; ha van Resend-kulcs, azon menjen."""
    monkeypatch.setenv("RESEND_API_KEY", "re_teszt")
    smtp_sent = _capture(monkeypatch)
    sent = _capture_resend(monkeypatch)
    r = client.post("/api/contact", json=VALID)
    assert r.status_code == 200
    assert smtp_sent == []
    cfg, payload = sent[0]
    assert payload["to"] == ["cel@example.org"]
    assert payload["reply_to"] == "anna@pelda.hu"
    assert "Három webshopunk" in payload["text"] and "Példa Kft." in payload["text"]
    assert payload["from"] == lead_intake.RESEND_DEFAULT_FROM


def test_resend_alone_is_enough(client, monkeypatch):
    for name in ("SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD"):
        monkeypatch.delenv(name)
    monkeypatch.setenv("RESEND_API_KEY", "re_teszt")
    assert client.get("/api/contact/status").json() == {"configured": True}


def test_resend_needs_a_recipient(client, monkeypatch):
    for name in ("SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD", "LEAD_TO"):
        monkeypatch.delenv(name)
    monkeypatch.setenv("RESEND_API_KEY", "re_teszt")
    assert client.get("/api/contact/status").json() == {"configured": False}


def test_resend_rejection_is_reported_not_swallowed(client, monkeypatch):
    monkeypatch.setenv("RESEND_API_KEY", "re_teszt")

    async def boom(cfg, payload):
        raise lead_intake.ResendError("HTTP 403 validation_error: only your own address")

    monkeypatch.setattr(lead_intake, "_send_resend", boom)
    assert client.post("/api/contact", json=VALID).status_code == 502


def test_header_injection_cannot_reach_the_resend_reply_to(client, monkeypatch):
    monkeypatch.setenv("RESEND_API_KEY", "re_teszt")
    sent = _capture_resend(monkeypatch)
    evil = dict(VALID, name="Anna\nBcc: mindenki@example.net")
    assert client.post("/api/contact", json=evil).status_code == 200
    _, payload = sent[0]
    assert "\n" not in payload["subject"]


def _fake_resend_api(monkeypatch, status, body):
    import httpx

    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(status, json=body)

    real = httpx.AsyncClient

    class Client(real):
        def __init__(self, *a, **kw):
            super().__init__(*a, transport=httpx.MockTransport(handler), **kw)

    monkeypatch.setattr(lead_intake.httpx, "AsyncClient", Client)
    return seen


def test_send_resend_calls_the_api_with_the_key(monkeypatch):
    import asyncio
    import json

    seen = _fake_resend_api(monkeypatch, 200, {"id": "abc"})
    cfg = {"key": "re_teszt"}
    asyncio.run(lead_intake._send_resend(cfg, {"to": ["cel@example.org"], "text": "szia"}))
    req = seen[0]
    assert str(req.url) == lead_intake.RESEND_URL
    assert req.headers["Authorization"] == "Bearer re_teszt"
    assert json.loads(req.content)["to"] == ["cel@example.org"]


def test_send_resend_turns_a_refusal_into_an_error(monkeypatch):
    import asyncio

    _fake_resend_api(monkeypatch, 403, {"name": "validation_error", "message": "own address only"})
    with pytest.raises(lead_intake.ResendError) as e:
        asyncio.run(lead_intake._send_resend({"key": "re_teszt"}, {"text": "titkos tartalom"}))
    assert "403" in str(e.value) and "validation_error" in str(e.value)
    assert "titkos tartalom" not in str(e.value)


def test_unreachable_smtp_port_hides_the_form(client, monkeypatch):
    """Ez történt élesben: minden beállítás megvolt, a port zárva volt, és az
    űrlap megjelent — minden beküldés hibára futott."""
    monkeypatch.setitem(lead_intake._smtp_reachable, "value", False)
    assert client.get("/api/contact/status").json() == {"configured": False}
    assert client.post("/api/contact", json=VALID).status_code == 503


def test_a_network_error_hides_the_form_for_the_next_visitor(client, monkeypatch):
    def unreachable(cfg, msg):
        raise OSError("Network is unreachable")

    monkeypatch.setattr(lead_intake, "_send_sync", unreachable)
    assert client.post("/api/contact", json=VALID).status_code == 502
    assert client.get("/api/contact/status").json() == {"configured": False}


def test_a_wrong_password_does_not_hide_the_form(client, monkeypatch):
    """A rossz jelszó beállítási hiba, nem zárt port: a naplóból kell kiderülnie,
    nem attól, hogy az űrlap eltűnik."""
    def denied(cfg, msg):
        raise smtplib.SMTPAuthenticationError(535, b"nope")

    monkeypatch.setattr(lead_intake, "_send_sync", denied)
    assert client.post("/api/contact", json=VALID).status_code == 502
    assert client.get("/api/contact/status").json() == {"configured": True}


def test_probe_reports_a_closed_port():
    import socket

    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    # A socket bezárva: a port szabad, senki nem figyel rajta.
    assert lead_intake.probe_smtp({"host": "127.0.0.1", "port": port}) is False


def test_the_boot_log_says_whether_the_form_can_send(monkeypatch, caplog):
    """A naplóból derüljön ki, mi hiányzik — a lapon szándékosan nem látszik.

    Ezt a sort egy valós hiba hívta életre: az SMTP-változók a statikus
    frontend szolgáltatására kerültek a backend helyett, és kívülről ez
    pontosan úgy nézett ki, mintha az űrlap meg sem lenne írva.
    """
    import logging

    for name in ("SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD", "LEAD_TO", "RESEND_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    with caplog.at_level(logging.INFO):
        lead_intake.log_contact_config()
    assert "DISABLED" in caplog.text and "SMTP_HOST" in caplog.text
    assert "RESEND_API_KEY" in caplog.text, "a napló mondja meg a másik utat is"

    caplog.clear()
    monkeypatch.setenv("RESEND_API_KEY", "re_titkos")
    monkeypatch.setenv("LEAD_TO", "cel@example.org")
    with caplog.at_level(logging.INFO):
        lead_intake.log_contact_config()
    assert "via Resend" in caplog.text
    assert "re_titkos" not in caplog.text, "kulcs soha nem kerülhet a naplóba"
    monkeypatch.delenv("RESEND_API_KEY")
    monkeypatch.delenv("LEAD_TO")

    caplog.clear()
    monkeypatch.setenv("SMTP_HOST", "smtp.example.org")
    monkeypatch.setenv("SMTP_USER", "kuldo@example.org")
    monkeypatch.setenv("SMTP_PASSWORD", "titok")
    with caplog.at_level(logging.INFO):
        lead_intake.log_contact_config()
    assert "ENABLED" in caplog.text
    assert "titok" not in caplog.text, "jelszó soha nem kerülhet a naplóba"
