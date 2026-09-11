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


def test_the_boot_log_says_whether_the_form_can_send(monkeypatch, caplog):
    """A naplóból derüljön ki, mi hiányzik — a lapon szándékosan nem látszik.

    Ezt a sort egy valós hiba hívta életre: az SMTP-változók a statikus
    frontend szolgáltatására kerültek a backend helyett, és kívülről ez
    pontosan úgy nézett ki, mintha az űrlap meg sem lenne írva.
    """
    import logging

    for name in ("SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD", "LEAD_TO"):
        monkeypatch.delenv(name, raising=False)
    with caplog.at_level(logging.INFO):
        lead_intake.log_contact_config()
    assert "DISABLED" in caplog.text and "SMTP_HOST" in caplog.text

    caplog.clear()
    monkeypatch.setenv("SMTP_HOST", "smtp.example.org")
    monkeypatch.setenv("SMTP_USER", "kuldo@example.org")
    monkeypatch.setenv("SMTP_PASSWORD", "titok")
    with caplog.at_level(logging.INFO):
        lead_intake.log_contact_config()
    assert "ENABLED" in caplog.text
    assert "titok" not in caplog.text, "jelszó soha nem kerülhet a naplóba"
