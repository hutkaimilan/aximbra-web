"""Backend API tests for AXIMBRA demo endpoints."""
import os
import uuid
import pytest
import requests

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://budapest-agent-demo.preview.emergentagent.com').rstrip('/')

EMAIL_ENUMS = {
    "kategoria": {"Reklamáció", "Árajánlat-kérés", "Számlázási kérdés", "Technikai támogatás", "Együttműködési ajánlat", "Egyéb"},
    "surgosseg": {"Sürgős", "Normál", "Ráér"},
    "felelos": {"Ügyfélszolgálat", "Értékesítés", "Pénzügy", "Műszaki", "Vezetőség"},
    "valaszhatarido": {"4 órán belül", "1 munkanap", "3 munkanap"},
}
LEAD_MINOSITES = {"A", "B", "C", "D"}
LEAD_DIM = {"Igazolt", "Valószínű", "Ismeretlen", "Nem illeszkedik"}


def _sid():
    return f"test-{uuid.uuid4().hex[:12]}"


def test_root():
    r = requests.get(f"{BASE_URL}/api/")
    assert r.status_code == 200
    assert r.json().get("message") == "AXIMBRA API"


def test_email_success_schema():
    sid = _sid()
    payload = {"text": "Tisztelt Ügyfélszolgálat! A tegnap rendelt termék hibásan érkezett, kérem sürgősen orvosolják a helyzetet, mert holnap utaznék. Köszönöm, Kovács Anna"}
    r = requests.post(f"{BASE_URL}/api/demo/email", json=payload, headers={"X-Session-Id": sid}, timeout=90)
    assert r.status_code == 200, r.text
    data = r.json()
    for key, allowed in EMAIL_ENUMS.items():
        assert data[key] in allowed, f"{key}={data[key]} not in {allowed}"
    assert isinstance(data["osszefoglalo"], str) and len(data["osszefoglalo"]) > 0
    assert isinstance(data["javasolt_lepes"], str) and len(data["javasolt_lepes"]) > 0


def test_lead_success_schema():
    sid = _sid()
    payload = {"text": "150 fős SaaS cég marketing igazgatója vagyok, jövő negyedévben szeretnénk AI-alapú ügyfél-minősítő rendszert bevezetni, 15-20 millió forintos kerettel."}
    r = requests.post(f"{BASE_URL}/api/demo/lead", json=payload, headers={"X-Session-Id": sid}, timeout=90)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["minosites"] in LEAD_MINOSITES
    for k in ("igeny", "koltsegvetes", "donteshozo", "hatarido"):
        assert data[k] in LEAD_DIM
    assert data["indoklas"] and data["javasolt_lepes"]


def test_email_empty_returns_422():
    r = requests.post(f"{BASE_URL}/api/demo/email", json={"text": "   "}, headers={"X-Session-Id": _sid()})
    assert r.status_code == 422


def test_email_truncates_long_input():
    # Should not error; server truncates to 4000 chars
    sid = _sid()
    long_text = "Kedves ügyfélszolgálat, van egy problémám. " + ("nagyon hosszú " * 500)
    r = requests.post(f"{BASE_URL}/api/demo/email", json={"text": long_text}, headers={"X-Session-Id": sid}, timeout=90)
    assert r.status_code in (200, 502), r.text  # either LLM valid or fallback but no crash


def test_email_rate_limit_per_session():
    """9th call with same session should return 429 after 8 successful."""
    sid = _sid()
    payload = {"text": "Rövid teszt e-mail: kérek árajánlatot 20 db termékre. Köszönöm."}
    success = 0
    for i in range(8):
        r = requests.post(f"{BASE_URL}/api/demo/email", json=payload, headers={"X-Session-Id": sid}, timeout=90)
        if r.status_code == 200:
            success += 1
        elif r.status_code == 429:
            # possibly IP hourly cap kicked in; break
            break
    # 9th call
    r = requests.post(f"{BASE_URL}/api/demo/email", json=payload, headers={"X-Session-Id": sid}, timeout=90)
    assert r.status_code == 429, f"Expected 429 after budget, got {r.status_code}: {r.text}"
    detail = r.json().get("detail", "")
    # Hungarian message
    assert any(w in detail for w in ("munkamenetben", "napi", "hálózatról")), detail
