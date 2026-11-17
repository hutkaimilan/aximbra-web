"""Tőzsdei hibák: egy instrumentum 502-je nem állíthatja meg a kört, a GET-et újrapróbáljuk."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import json  # noqa: E402

from exchange import BinanceClient, ExchangeError  # noqa: E402
from test_trading import make_live_agent  # noqa: E402


def test_pending_lookup_502_does_not_abort_tick():
    ag, market, bot = make_live_agent()
    ag.store.set("pending_entry:BTCUSDT", json.dumps({"cid": "mtb-x", "stop": 1.0, "candle": 1}))

    def boom(sym, cid):
        raise ExchangeError("Binance-szerverhiba (HTTP 502)")

    ag.executor.lookup = boom
    ag.tick()                                    # nem dob kivételt
    assert ag.store.get("pending_entry:BTCUSDT")  # a függő vétel megmarad a következő körre
    assert ag.store.get("pending_fail_since:BTCUSDT")


def test_exchange_error_on_one_symbol_keeps_others_running():
    ag, market, bot = make_live_agent()
    ag.tick()
    pos = ag.store.open_positions()[0]

    def boom(sym, cid):
        raise ExchangeError("Binance-szerverhiba (HTTP 502)")

    ag.executor.stop_state = boom
    ag.tick()                                    # a stop lekérdezése hibázik: nem zár vakon, nem omlik össze
    assert ag.store.get_position(pos.id).status == "open"


def test_get_requests_retry_transient_errors(monkeypatch):
    import httpx
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    import exchange
    monkeypatch.setattr(exchange.time, "sleep", lambda s: None)
    pem = Ed25519PrivateKey.generate().private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()).decode()
    calls = []

    def handler(request):
        calls.append(1)
        if len(calls) < 3:
            return httpx.Response(502, text="bad gateway")
        return httpx.Response(200, json={"balances": [{"asset": "USDT", "free": "10"}]})

    c = BinanceClient("k", pem, client=httpx.Client(transport=httpx.MockTransport(handler)))
    assert c.free("USDT") == 10 and len(calls) == 3
