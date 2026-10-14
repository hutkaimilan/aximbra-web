"""A dokumentum-elemző demó: csak a dokumentumban szó szerint meglévő adatot adja vissza."""
import base64
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("OPENAI_API_KEY", "sk-test")

from fastapi.testclient import TestClient
import server

client = TestClient(server.app)


def _fake(answer):
    async def call(system, text, max_tokens=600, **kw):
        return json.dumps(answer)
    return call


def test_fields_without_a_real_source_are_dropped(monkeypatch):
    monkeypatch.setattr(server, "_call_llm", _fake({
        "document_type": "invoice",
        "amount": {"value": "EUR 2,800.00", "source": "Total due: EUR 2,800.00"},
        "date": {"value": "1 January 2020", "source": "Dated 1 January 2020"},          # nincs a szövegben
        "parties": {"value": "Northwind … Duna", "source": "Seller: Northwind Supplies Ltd. … Buyer: Duna Logisztika Kft."},
        "due_date_or_deadline": {"value": "", "source": ""},
        "key_obligations": [{"value": "pay in 30 days", "source": "within 30 days of the invoice date"}],
        "risks_or_unusual_terms": [{"value": "made up", "source": "a clause that does not exist"}],
    }))
    d = client.post("/api/demo/document", json={"sample": "invoice_en", "lang": "en"},
                    headers={"X-Session-Id": "t1"}).json()
    assert d["amount"]["value"] == "EUR 2,800.00"
    assert d["date"] == {"value": "", "source": ""}
    assert d["parties"]["value"] == "Northwind, Duna"
    assert d["key_obligations"] and d["risks_or_unusual_terms"] == []


def test_unknown_type_and_bad_inputs(monkeypatch):
    monkeypatch.setattr(server, "_call_llm", _fake({"document_type": "poem"}))
    d = client.post("/api/demo/document", json={"sample": "quote_hu"}, headers={"X-Session-Id": "t2"}).json()
    assert d["document_type"] == "other"
    assert client.post("/api/demo/document", json={"sample": "nope"}).status_code == 400
    png = base64.b64encode(b"x" * 50).decode()
    assert client.post("/api/demo/document", json={"filename": "a.png", "mime": "image/png", "data_b64": png}).status_code == 415
    big = base64.b64encode(b"x" * (5 * 1024 * 1024 + 1)).decode()
    assert client.post("/api/demo/document", json={"filename": "a.txt", "mime": "text/plain", "data_b64": big}).status_code == 413


def test_uploaded_text_file_is_analysed(monkeypatch):
    monkeypatch.setattr(server, "_call_llm", _fake({
        "document_type": "contract", "amount": {"value": "100 EUR", "source": "The fee is 100 EUR per month."}}))
    txt = base64.b64encode("Service agreement. The fee is 100 EUR per month. Either party may terminate.".encode()).decode()
    d = client.post("/api/demo/document", json={"filename": "c.txt", "mime": "text/plain", "data_b64": txt},
                    headers={"X-Session-Id": "t3"}).json()
    assert d["document_type"] == "contract" and d["amount"]["value"] == "100 EUR"


def test_detailed_contract_analysis(monkeypatch):
    monkeypatch.setattr(server, "_call_llm", _fake({
        "document_type": "contract",
        "summary": "IT-üzemeltetési szerződés havi díjjal.",
        "duration": {"value": "határozatlan idő", "source": "határozatlan időre szól"},
        "termination": {"value": "90 nap", "source": "90 napos felmondási idővel mondhatja fel"},
        "key_obligations": [{"party": "Szolgáltató", "value": "4 órás reakcióidő",
                             "source": "a hibabejelentésekre munkanapokon 4 órán belül reagál"}],
        "risks_or_unusual_terms": [
            {"value": "díjemelés", "why": "évente drágulhat", "severity": "medium",
             "source": "legfeljebb 15%-kal emelni"},
            {"value": "24 hónapos kötöttség", "why": "kilépéskor a teljes hátralévő díj jár", "severity": "high",
             "source": "a hátralévő időszak teljes díját egy összegben köteles megfizetni"},
            {"value": "kitalált", "why": "x", "severity": "high", "source": "ilyen mondat nincs a szerződésben"}],
        "recommendations": ["Kérd a 24 hónapos kötöttség rövidítését.", 5],
    }))
    d = client.post("/api/demo/document", json={"sample": "contract_hu"}, headers={"X-Session-Id": "t4"}).json()
    assert d["summary"].startswith("IT-üzemeltetési")
    assert d["duration"]["value"] == "határozatlan idő" and d["termination"]["value"] == "90 nap"
    assert d["subject"] == {"value": "", "source": ""}
    assert d["key_obligations"][0]["party"] == "Szolgáltató"
    assert [r["severity"] for r in d["risks_or_unusual_terms"]] == ["high", "medium"]
    assert d["risks_or_unusual_terms"][0]["why"].startswith("kilépéskor")
    assert d["recommendations"] == ["Kérd a 24 hónapos kötöttség rövidítését."]
    assert d["truncated"] is False
