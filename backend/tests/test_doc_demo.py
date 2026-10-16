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


def test_pdf_ligatures_and_typography_do_not_hide_a_real_quote(monkeypatch):
    # A PDF „ﬁ” ligatúrát és nagykötőjelet ír, a modell sima betűkkel idéz.
    monkeypatch.setattr(server, "_call_llm", _fake({
        "document_type": "contract",
        "payment_terms": {"value": "havonta előre", "source": "minden hónap 5. napjáig, előre, átutalással fizet meg"},
        "termination": {"value": "30 nap", "source": "felmondhatja - indokolás nélkül"},
        "amount": {"value": "kitalált", "source": "fizet 999 Ft-ot"},
    }))
    txt = ("Bérleti szerződés. A Bérlő minden hónap 5.\nnapjáig, előre, átutalással ﬁzet meg. "
           "A Bérbeadó felmondhatja – indokolás nélkül.")
    d = client.post("/api/demo/document", json={"filename": "c.txt", "mime": "text/plain",
                                                "data_b64": base64.b64encode(txt.encode()).decode()},
                    headers={"X-Session-Id": "t5"}).json()
    assert d["payment_terms"]["value"] == "havonta előre"
    assert d["termination"]["value"] == "30 nap"
    assert d["amount"] == {"value": "", "source": ""}  # ami nincs a papíron, továbbra is kiesik


def test_line_break_hyphens_and_joined_sentences_still_count(monkeypatch):
    # A PDF a sor végén elválaszt („webshop-⏎funkcióval”), a modell egyben idéz;
    # és két nem szomszédos mondatot „ … ” nélkül fűz össze.
    monkeypatch.setattr(server, "_call_llm", _fake({
        "document_type": "contract",
        "subject": {"value": "webshop", "source": "egy legfeljebb 12 aloldalas, webshop-funkcióval rendelkező weboldal"},
        "payment_terms": {"value": "70% előleg, 30% átadáskor",
                          "source": "A fejlesztési díj 70%-át előlegként fizeti meg. A fennmaradó 30%-a átadáskor esedékes."},
        "parties": {"value": "kitalált", "source": "A Megrendelő. A Vállalkozó. Fizet."},
        "termination": {"value": "kitalált", "source": "A fejlesztési díj 70%-át előlegként fizeti meg. Kötbért fizet 5 millió forintot."},
    }))
    txt = ("Szerződés. A Vállalkozó egy legfeljebb 12 aloldalas, webshop-\nfunkcióval rendelkező weboldalt készít. "
           "A Megrendelő a fejlesztési díj 70%-át előlegként fizeti meg. Az előleg nem jár vissza. "
           "A fennmaradó 30%-a átadáskor esedékes.")
    d = client.post("/api/demo/document", json={"filename": "c.txt", "mime": "text/plain",
                                                "data_b64": base64.b64encode(txt.encode()).decode()},
                    headers={"X-Session-Id": "t6"}).json()
    assert d["subject"]["value"] == "webshop"
    assert d["payment_terms"]["value"] == "70% előleg, 30% átadáskor"
    assert d["parties"] == {"value": "", "source": ""}      # csak apró, általános darabok
    assert d["termination"] == {"value": "", "source": ""}  # az egyik mondat kitalált


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


CONTRACT = (
    "Szolgáltatási szerződés, amely létrejött a Példa Kft. és a Minta Bt. között.\n"
    "1. A szerződés tárgya\n"
    "1.1. A Vállalkozó weboldalt készít a Megrendelőnek.\n"
    "2. Díjak\n"
    "2.1. A díj havi 100 000 Ft, amelyet a Megrendelő minden hónap\n"
    "5. napjáig fizet meg.\n"
    "2.2. Az előleg semmilyen esetben nem jár vissza.\n"
    "3. Felelősség\n"
    "3.1. A felek a titkokat kölcsönösen megőrzik.\n"
)


def test_clauses_are_split_by_number_and_headings_and_wrapped_numbers_are_ignored():
    labels = [label for label, _ in server._split_clauses(CONTRACT)]
    assert labels == ["0", "1.1", "2.1", "2.2", "3.1"]  # „2. Díjak” cím, „5. napjáig” tördelés
    body = dict(server._split_clauses(CONTRACT))["2.1"]
    assert body.startswith("2.1. A díj") and "5. napjáig fizet meg." in body


def test_unnumbered_text_is_split_into_sentence_groups():
    text = " ".join(f"Ez a(z) {i}. mondat egy számozatlan levélből, elég hosszú ahhoz, hogy számítson." for i in range(30))
    parts = server._split_clauses(text)
    assert parts[0][0] == "B1" and len(parts) > 3 and all(len(b) <= 500 for _, b in parts)


def _clause_answer():
    return {
        "clauses": [
            {"id": "0", "risk": "none", "title": "", "why": "", "party": "", "duty": ""},
            {"id": "1.1", "risk": "none", "title": "", "why": "", "party": "Vállalkozó", "duty": "elkészíti a weboldalt", "key": True},
            {"id": "[2.1]", "risk": "low", "title": "Havi díj", "why": "fix költség", "party": "Megrendelő", "duty": "havonta fizet", "key": True},
            {"id": "2.2", "risk": "high", "title": "Vissza nem járó előleg", "why": "elveszik a pénzed", "party": "", "duty": ""},
            {"id": "2.2", "risk": "none", "title": "", "why": ""},             # kétszer: az első számít
            {"id": "9.9", "risk": "high", "title": "Kitalált pont", "why": "x"},  # nincs ilyen pont
        ],
        "recommendations": ["Kérd a 2.2. pont törlését."],
    }


def test_every_flagged_clause_keeps_its_own_text_as_source(monkeypatch):
    risks, duties, recs, judged = server._from_clauses(_clause_answer(), server._split_clauses(CONTRACT))
    assert [r["value"] for r in risks] == ["Vissza nem járó előleg", "Havi díj"]  # súlyosság szerint
    assert risks[0]["source"].startswith("2.2. Az előleg semmilyen esetben") and risks[0]["severity"] == "high"
    assert [d["value"] for d in duties] == ["elkészíti a weboldalt", "havonta fizet"]
    assert recs == ["Kérd a 2.2. pont törlését."] and judged == 4


def test_clause_pass_runs_on_the_strong_model_and_falls_back(monkeypatch):
    import openai
    import httpx
    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    monkeypatch.setenv("GEMINI_API_KEY", "test")
    monkeypatch.setattr(server, "DOC_GEMINI_MODELS", ["gemini-strong", "gemini-backup"])
    calls = []

    async def fake(system, text, max_tokens=600, model=None, **kw):
        calls.append((model, "Judge EVERY clause" in system, kw.get("wait_on_limit"), kw.get("temperature")))
        if model == "gemini-strong":
            r = httpx.Response(404, request=httpx.Request("POST", "https://x"))
            raise openai.NotFoundError("no such model", response=r, body=None)
        if "Judge EVERY clause" in system:
            assert "[2.2] 2.2. Az előleg" in text  # a modell címkézett pontokat kap
            return json.dumps(_clause_answer())
        return json.dumps({"document_type": "contract", "summary": "Szerződés."})

    monkeypatch.setattr(server, "_call_llm", fake)
    txt = base64.b64encode(CONTRACT.encode()).decode()
    d = client.post("/api/demo/document", json={"filename": "c.txt", "mime": "text/plain", "data_b64": txt},
                    headers={"X-Session-Id": "t7"}).json()
    assert [r["value"] for r in d["risks_or_unusual_terms"]] == ["Vissza nem járó előleg", "Havi díj"]
    assert [c[0] for c in calls if c[1]] == ["gemini-strong", "gemini-backup"]
    assert (None, False, True, 0) in calls                       # a mezős kör az alapmodellen
    assert ("gemini-strong", True, False, None) in calls          # nem vár, alap temperature
    assert d["key_obligations"][0]["value"] == "elkészíti a weboldalt"


def test_a_paraphrased_quote_falls_back_to_the_cited_clause_but_not_for_made_up_values(monkeypatch):
    async def fake(system, text, max_tokens=600, model=None, **kw):
        if "Judge EVERY clause" in system:
            return json.dumps({"clauses": []})
        assert "In EVERY object above" in system and text.startswith("[0] ")
        return json.dumps({
            "document_type": "contract",
            # nem szó szerinti idézet, de a jó pontot jelöli meg
            "amount": {"value": "havi 100 000 Ft", "source": "A díj havonta 100 000 forint.", "clauses": ["[2.1]"]},
            # kitalált érték egy valódi ponthoz kötve: a pontban nincs ott
            "termination": {"value": "90 napos felmondás", "source": "felmondási idő 90 nap", "clauses": ["3.1"]},
            "parties": {"value": "Példa Kft. és Minta Bt.", "source": "Példa Kft. … Minta Bt.", "clauses": ["0"]},
            "key_obligations": [{"party": "Megrendelő", "value": "havonta fizet 100 000 Ft-ot",
                                 "source": "fizetni kell", "clauses": ["2.1"]}],
        })

    monkeypatch.setattr(server, "_call_llm", fake)
    txt = base64.b64encode(CONTRACT.encode()).decode()
    d = client.post("/api/demo/document", json={"filename": "c.txt", "mime": "text/plain", "data_b64": txt},
                    headers={"X-Session-Id": "t8"}).json()
    assert d["amount"] == {"value": "havi 100 000 Ft",
                           "source": "2.1. A díj havi 100 000 Ft, amelyet a Megrendelő minden hónap 5. napjáig fizet meg."}
    assert d["termination"] == {"value": "", "source": ""}
    assert d["parties"]["source"] == "Példa Kft. … Minta Bt."  # a szó szerinti idézet marad, ha jó
    assert d["key_obligations"][0]["source"].startswith("2.1. A díj havi")


def test_json_with_raw_newlines_and_trailing_commas_is_repaired():
    raw = '```json\n{"summary": "első sor\nmásodik sor", "items": [1, 2,],}\n```'
    assert server._parse_json(raw) == {"summary": "első sor\nmásodik sor", "items": [1, 2]}


def test_a_failed_field_pass_still_returns_the_clause_findings(monkeypatch):
    async def fake(system, text, max_tokens=600, model=None, **kw):
        if "Judge EVERY clause" in system:
            return json.dumps({"document_type": "contract", **_clause_answer()})
        return "{not json at all"

    monkeypatch.setattr(server, "_call_llm", fake)
    txt = base64.b64encode(CONTRACT.encode()).decode()
    r = client.post("/api/demo/document", json={"filename": "c.txt", "mime": "text/plain", "data_b64": txt},
                    headers={"X-Session-Id": "t9"})
    d = r.json()
    assert r.status_code == 200 and d["document_type"] == "contract"
    assert [x["value"] for x in d["risks_or_unusual_terms"]] == ["Vissza nem járó előleg", "Havi díj"]
    assert d["amount"] == {"value": "", "source": ""} and d["summary"] == ""
