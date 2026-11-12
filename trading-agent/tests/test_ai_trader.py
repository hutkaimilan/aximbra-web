"""Az AI-kereskedő: döntés végrehajtása, eladás, hibás válasz kezelése."""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import ai_trader  # noqa: E402
from test_trading import make_agent  # noqa: E402


class AILLM:
    provider = "fake"

    def __init__(self, reply):
        self.reply = reply

    def ask(self, prompt, system=None, models=None, timeout=None):
        return self.reply


def test_ai_trader_buys_sells_and_survives_bad_reply():
    ag, market, bot = make_agent()
    ag.llm = AILLM('{"lépések":[{"lépés":"vesz","jel":"BTCUSDT","összeg_százalék":25,"stop_százalék":4,"ok":"erős"}],'
                   '"összefoglaló":"Veszek."}')
    assert ai_trader.run_once(ag, lambda s: "crypto", lambda: []) == "Veszek."
    pos = ag.store.open_positions()
    assert len(pos) == 1 and pos[0].kind == "ai"
    assert pos[0].qty * pos[0].entry_price == pytest.approx(10_000 * 0.25, rel=0.02)
    assert pos[0].stop == pytest.approx(market.price_ * 0.96, rel=1e-6)

    ag.llm = AILLM('{"lépések":[{"lépés":"elad","jel":"BTCUSDT","ok":"célt ért"}],"összefoglaló":"Eladok."}')
    ai_trader.run_once(ag, lambda s: "crypto", lambda: [])
    assert not ag.store.open_positions()
    assert ag.store.closed_positions()[0].exit_reason == "AI-eladás"

    ag.llm = AILLM("nem json")
    assert ai_trader.run_once(ag, lambda s: "crypto", lambda: []) == ""


def test_ai_trader_ignores_unknown_symbols_and_closed_markets():
    ag, market, bot = make_agent()
    ag.llm = AILLM('{"lépések":[{"lépés":"vesz","jel":"NEMLÉTEZŐ","összeg_százalék":50,"stop_százalék":5}],'
                   '"összefoglaló":"x"}')
    ai_trader.run_once(ag, lambda s: "crypto", lambda: [])
    assert not ag.store.open_positions()
    ag.llm = AILLM('{"lépések":[{"lépés":"vesz","jel":"BTCUSDT","összeg_százalék":50,"stop_százalék":5}],'
                   '"összefoglaló":"x"}')
    ai_trader.market_open = lambda cls, now: False
    try:
        ai_trader.run_once(ag, lambda s: "stock", lambda: [])
    finally:
        import importlib
        importlib.reload(ai_trader)
    assert not ag.store.open_positions()


def test_install_files_are_public_and_health_not_shadowed(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from web import make_router
    ag, _, _ = make_agent()
    monkeypatch.setenv("WEB_PASSWORD", "x")
    app = FastAPI()
    app.include_router(make_router(ag, {}))

    @app.get("/health")
    def health():
        return {"ok": True}

    c = TestClient(app, base_url="https://testserver")
    assert c.get("/manifest.json").json()["display"] == "standalone"
    assert c.get("/sw.js").status_code == 200 and c.get("/icon-512.png").status_code == 200
    assert c.get("/health").json() == {"ok": True}
    assert c.get("/titkos.db").status_code == 404
