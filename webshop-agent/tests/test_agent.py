import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

import agent
import connectors
from connectors import DemoShop, Shopify, WooCommerce


@pytest.fixture(autouse=True)
def no_llm(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)


def test_extract_and_language():
    e = agent.extract("Szia! Hol tart az ORL-1042 rendelésem? 2026-ban rendeltem, anna@x.hu")
    assert e["order_numbers"] == ["ORL-1042"] and e["emails"] == ["anna@x.hu"]
    assert agent.extract("Order #100234 please")["order_numbers"] == ["100234"]
    assert agent.detect_lang("Hol a csomagom? Köszönöm") == "hu"
    assert agent.detect_lang("Wo ist mein Paket? Danke") == "de"
    assert agent.detect_lang("Where is my order?") == "en"


def test_verified_customer_gets_real_tracking():
    r = agent.reply(DemoShop(), "anna.kovacs@example.com", "Rendelés", "Szia, hol tart az ORL-1042 rendelésem?")
    assert r["verified"] and r["intent"] == "order_status" and r["lang"] == "hu"
    assert "GLS38441729" in r["body"] and "feladtuk" in r["body"]
    assert "Kovács Anna" in r["body"]


def test_stranger_with_order_number_gets_no_details():
    r = agent.reply(DemoShop(), "valaki@mas.hu", "", "Hol tart az ORL-1042 rendelés?")
    assert r["order_found"] and not r["verified"] and r["order"] is None
    assert "GLS38441729" not in r["body"] and "Kovács" not in r["body"]
    assert "Adatvédelmi" in r["body"]


def test_email_only_finds_latest_order_and_unknown_asks_for_number():
    r = agent.reply(DemoShop(), "anna.kovacs@example.com", "", "Where is my parcel?")
    assert r["verified"] and r["order"]["number"] == "ORL-1042" and r["lang"] == "en"
    r = agent.reply(DemoShop(), "nobody@example.com", "", "Wo ist mein Paket?")
    assert not r["order_found"] and "Bestellnummer" in r["body"]


def test_complaint_needs_human():
    r = agent.reply(DemoShop(), "peter.nagy@example.com", "", "A ORL-1043 csomagban sérült termék jött, panaszt teszek.")
    assert r["intent"] == "complaint" and r["needs_human"]


def test_ungrounded_ai_answer_falls_back_to_template(monkeypatch):
    fake = {"intent": "order_status", "needs_human": False, "subject": "Re", "body": "Holnap 14:00-kor érkezik, csomagszám 99999999."}
    monkeypatch.setattr(agent, "_gemini", lambda p: json.dumps(fake))
    r = agent.reply(DemoShop(), "anna.kovacs@example.com", "", "Hol a ORL-1042?")
    assert r["engine"] == "template" and "99999999" not in r["body"] and "GLS38441729" in r["body"]
    good = {**fake, "body": "Kedves Kovács Anna! A rendelését feladtuk, GLS csomagszám: GLS38441729. Üdvözlettel: ŐRLŐ"}
    monkeypatch.setattr(agent, "_gemini", lambda p: json.dumps(good))
    r = agent.reply(DemoShop(), "anna.kovacs@example.com", "", "Hol a ORL-1042?")
    assert r["engine"] == "ai" and "GLS38441729" in r["body"]


def test_woocommerce_mapping():
    o = WooCommerce._order({"id": 77, "number": "1077", "status": "processing", "currency": "HUF", "total": "8900",
                            "date_created": "2026-10-01T10:00:00", "billing": {"email": "A@B.hu", "first_name": "Anna", "last_name": "Kiss"},
                            "line_items": [{"name": "Kávé", "quantity": 2}],
                            "meta_data": [{"key": "_wc_shipment_tracking_items", "value": [{"tracking_provider": "GLS", "tracking_number": "G1"}]}]})
    assert o.number == "1077" and o.status == "shipped" and o.tracking_number == "G1" and o.email == "A@B.hu"
    assert o.name == "Kiss Anna" and o.items == ["Kávé × 2"]


def test_shopify_mapping():
    o = Shopify._order({"name": "#1001", "email": "c@d.com", "fulfillment_status": "fulfilled", "created_at": "2026-10-02T09:00:00Z",
                        "total_price": "39.90", "currency": "EUR", "line_items": [{"name": "Coffee", "quantity": 1}],
                        "fulfillments": [{"tracking_company": "DHL", "tracking_number": "D9", "tracking_url": "https://t/D9",
                                          "created_at": "2026-10-03T08:00:00Z", "shipment_status": "in_transit"}]})
    assert o.number == "1001" and o.status == "shipped" and o.carrier == "DHL" and o.shipped == "2026-10-03"


def test_shop_from_env_defaults_to_demo(monkeypatch):
    monkeypatch.delenv("SHOP_KIND", raising=False)
    assert isinstance(connectors.shop_from_env(), DemoShop)
