"""A trading agent hálózat nélkül: piac, Telegram és modell csonkkal."""
import math
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import backtest  # noqa: E402
import config  # noqa: E402
import paper  # noqa: E402
import strategy  # noqa: E402
from agent import Agent  # noqa: E402
from llm import LLMError  # noqa: E402
from market import Candle, MarketError  # noqa: E402
from store import Store  # noqa: E402

H4 = 4 * 3600 * 1000


def make_candles(closes, start=1_700_000_000_000, step=H4, spread=0.01):
    out, prev = [], closes[0]
    for i, c in enumerate(closes):
        o = prev
        out.append(Candle(start + i * step, o, max(o, c) * (1 + spread), min(o, c) * (1 - spread), c, 1.0,
                          start + (i + 1) * step - 1))
        prev = c
    return out


def crossover_series():
    """Hosszú emelkedés (ár az EMA200 fölött), rövid visszaesés, majd újra fel:
    a végén az EMA20 felfelé keresztezi az EMA50-et."""
    up = [100 + i * 0.5 for i in range(260)]
    dip = [up[-1] - i * 1.2 for i in range(1, 31)]
    closes = up + dip
    while True:
        closes.append(closes[-1] * 1.01)
        if strategy.latest(make_candles(closes), False) is not None:
            return closes
        assert len(closes) < 500, "a teszt-sorozatban nem jött létre keresztezés"


CFG = config.Config(symbols=("BTCUSDT",), db_path=":memory:")


# --- indikátorok, stratégia ---------------------------------------------------
def test_ema_matches_definition():
    vals = [1, 2, 3, 4, 5, 6]
    out = strategy.ema(vals, 3)
    assert out[:2] == [None, None]
    assert out[2] == pytest.approx(2.0)
    assert out[3] == pytest.approx(4 * 0.5 + 2.0 * 0.5)
    assert strategy.ema([1, 2], 3) == [None, None]


def test_signal_needs_crossover_and_regime():
    ind = {"close": [10, 11], "fast": [9, 11], "slow": [10, 10], "regime": [8, 8], "atr": [1, 1]}
    sig = strategy.signal_at(ind, 1, False)
    assert sig.action == "enter" and sig.stop == pytest.approx(11 - 2 * 1)
    ind["regime"] = [12, 12]   # ár az EMA200 alatt: csökkenő trendben nem veszünk
    assert strategy.signal_at(ind, 1, False) is None
    ind = {"close": [10, 9], "fast": [11, 9], "slow": [10, 10], "regime": [8, 8], "atr": [1, 1]}
    assert strategy.signal_at(ind, 1, True).action == "exit"
    assert strategy.signal_at(ind, 1, False) is None


def test_crossover_series_produces_entry():
    sig = strategy.latest(make_candles(crossover_series()), False)
    assert sig.action == "enter" and sig.stop < sig.price


# --- kockázat, elszámolás -------------------------------------------------------
def test_size_respects_risk_and_cap():
    qty = paper.size(10_000, 10_000, entry=100, stop=98, risk_pct=0.01, max_open=2, fee=0.001)
    assert qty * (100 - 98) <= 100 + 1e-9          # legfeljebb 1% kockázat
    assert qty * 100 <= 5_000                       # legfeljebb a tőke fele (2 pozíció)
    assert paper.size(10_000, 10_000, 100, 101, 0.01, 2, 0.001) == 0.0   # stop a belépés fölött


def test_daily_loss_limit_blocks():
    assert paper.can_open(0, 2, -301, 10_000, 0.03)[0] is False
    assert paper.can_open(0, 2, -299, 10_000, 0.03)[0] is True
    assert paper.can_open(2, 2, 0, 10_000, 0.03)[0] is False


def test_bar_exit_assumes_stop_first_and_gaps():
    bar = Candle(0, 100, 120, 80, 100, 1, 1)
    assert paper.exit_on_bar(90, 110, bar) == (90, "stop")
    gap = Candle(0, 85, 86, 84, 85, 1, 1)
    assert paper.exit_on_bar(90, 110, gap) == (85, "stop")   # nyitáskor már a stop alatt
    assert paper.exit_on_bar(90, 110, Candle(0, 100, 111, 99, 105, 1, 1)) == (110, "cél")


def test_settle_includes_fees_both_sides():
    _, _, pnl = paper.settle(1.0, 100.0, 0.1, 100.0, fee=0.001, slippage=0.0)
    assert pnl == pytest.approx(-0.2)


# --- napló ------------------------------------------------------------------------
def test_store_idempotent_signal_and_single_open_position():
    s = Store(":memory:", 1000)
    assert s.record_signal("BTCUSDT", 1, "enter", 10, "x") is True
    assert s.record_signal("BTCUSDT", 1, "enter", 10, "x") is False
    pid = s.open_position("BTCUSDT", 1, 100, 0.1, 95, 110, 1)
    assert pid and s.cash() == pytest.approx(1000 - 100.1)
    assert s.open_position("BTCUSDT", 1, 100, 0.1, 95, 110, 2) is None   # második nyitott nem lehet
    assert s.close_position(pid, 110, 0.11, "cél", 9.79) is True
    assert s.close_position(pid, 110, 0.11, "cél", 9.79) is False       # kétszer nem zár
    assert s.cash() == pytest.approx(1000 - 100.1 + 110 - 0.11)
    assert s.open_position("BTCUSDT", 100, 100, 0.1, 95, 110, 3) is None  # nincs rá fedezet


def test_store_keeps_account_across_restart(tmp_path):
    path = str(tmp_path / "t.db")
    s = Store(path, 1000)
    s.open_position("BTCUSDT", 1, 100, 0, 95, 110, 1)
    s2 = Store(path, 5000)  # újraindítás más kezdőtőke-beállítással
    assert s2.cash() == pytest.approx(900) and s2.start_equity() == 1000
    assert len(s2.open_positions()) == 1


# --- backtest ---------------------------------------------------------------------
def test_backtest_runs_and_fees_cost_money():
    closes = [100 * (1 + 0.002 * i) * (1 + 0.08 * math.sin(i / 15)) for i in range(1500)]
    candles = make_candles(closes)
    res = backtest.run("BTCUSDT", candles, CFG)
    assert res["trades"] > 0
    assert 0 <= res["max_drawdown"] < 1
    free = backtest.run("BTCUSDT", candles, config.Config(symbols=("BTCUSDT",), fee=0, slippage=0))
    assert free["final_equity"] > res["final_equity"]
    assert "Backtest" in backtest.summary(res)
    with pytest.raises(ValueError):
        backtest.run("BTCUSDT", candles[:50], CFG)


# --- agent ------------------------------------------------------------------------
class FakeMarket:
    def __init__(self, candles, price):
        self.candles_ = candles
        self.price_ = price
        self.fail = False

    def candles(self, symbol, interval, limit=300, **_):
        if self.fail:
            raise MarketError("hálózati hiba (ConnectError)")
        return self.candles_[-limit:]

    def price(self, symbol):
        if self.fail:
            raise MarketError("hálózati hiba (ConnectError)")
        return self.price_


class FakeBot:
    chat_id = "42"

    def __init__(self):
        self.sent = []

    def send(self, text, chat_id=None):
        self.sent.append(text)


class FakeLLM:
    provider = "fake"

    def __init__(self, fail=False):
        self.fail = fail

    def ask(self, prompt):
        if self.fail:
            raise LLMError("leállt")
        return "Magyarázat."


def make_agent(llm=None):
    candles = make_candles(crossover_series())
    clock = lambda: (candles[-1].close_time + 60_000) / 1000  # noqa: E731
    cfg = config.Config(symbols=("BTCUSDT",), db_path=":memory:", report_hour=23)
    market = FakeMarket(candles, candles[-1].close)
    bot = FakeBot()
    return Agent(cfg, Store(":memory:", 10_000), market, bot, llm, clock=clock), market, bot


def test_agent_opens_once_and_notifies():
    ag, _, bot = make_agent(FakeLLM())
    ag.tick()
    assert len(ag.store.open_positions()) == 1
    assert any("VÉTEL" in m and "Magyarázat" in m for m in bot.sent)
    ag.tick()
    ag.store.delete("last_candle:BTCUSDT")   # mintha újraindulás után újra látná ugyanazt a gyertyát
    ag.tick()
    assert len(ag.store.open_positions()) == 1
    assert sum("VÉTEL" in m for m in bot.sent) == 1


def test_agent_still_alerts_when_llm_down():
    ag, _, bot = make_agent(FakeLLM(fail=True))
    ag.tick()
    msg = [m for m in bot.sent if "VÉTEL" in m]
    assert msg and "🧠" not in msg[0]


def test_agent_stop_hit_closes_position():
    ag, market, bot = make_agent()
    ag.tick()
    pos = ag.store.open_positions()[0]
    market.price_ = pos.stop
    ag.tick()
    assert not ag.store.open_positions()
    closed = ag.store.closed_positions()[0]
    assert closed.exit_reason == "stop" and closed.pnl < 0
    # Pontosan a stopon: 1R, plusz a díjak és a csúszás — de nem több ennél.
    assert -1.2 < closed.r_multiple < -1.0
    assert any("ZÁRÁS" in m for m in bot.sent)


def test_agent_data_outage_alerts_once_and_recovers():
    ag, market, bot = make_agent()
    market.fail = True
    ag.tick()
    ag.tick()
    assert sum("nincs megbízható piaci adat" in m for m in bot.sent) == 1
    market.fail = False
    ag.tick()
    assert any("újra rendben" in m for m in bot.sent)


def test_agent_refuses_stale_data():
    ag, market, bot = make_agent()
    ag.clock = lambda: (market.candles_[-1].close_time + 3 * H4) / 1000
    ag.tick()
    assert not ag.store.open_positions()
    assert any("elavult" in m for m in bot.sent)


def test_messages_only_from_owner():
    ag, _, _ = make_agent()
    assert ag.handle_message(99, "/status") is None
    assert "Állapot" in ag.handle_message(42, "/status")
    assert "Parancsok" in ag.handle_message("42", "/help")
    assert "Szabad kérdésre" in ag.handle_message(42, "mit csinál a BTC?")
    ag.bot.chat_id = None
    assert "chat-azonosítód: 7" in ag.handle_message(7, "szia")


def test_config_rejects_dangerous_values(monkeypatch):
    monkeypatch.setenv("RISK_PER_TRADE", "1")
    with pytest.raises(config.ConfigError):
        config.load()
    monkeypatch.setenv("RISK_PER_TRADE", "0.01")
    monkeypatch.setenv("TRADING_SYMBOLS", "btc/usdt")
    with pytest.raises(config.ConfigError):
        config.load()


class FakeMailer:
    def __init__(self, fail=False):
        self.sent = []
        self.fail = fail

    def send(self, subject, text):
        from mailer import MailError
        if self.fail:
            raise MailError("leállt")
        self.sent.append((subject, text))


def test_email_channel_gets_alerts_without_telegram():
    ag, _, _ = make_agent()
    ag.bot = None
    ag.mailer = FakeMailer()
    ag.tick()
    subjects = [s for s, _ in ag.mailer.sent]
    assert any("VÉTEL" in s for s in subjects)
    assert all("PAPÍRKERESKEDÉS" not in s for s in subjects)   # a tárgy az érdemi sor


def test_email_failure_does_not_block_telegram():
    ag, _, bot = make_agent()
    ag.mailer = FakeMailer(fail=True)
    ag.tick()
    assert any("VÉTEL" in m for m in bot.sent)


# --- tőzsdei végrehajtás (Binance-csonk) -----------------------------------------------
from exchange import BinanceClient, ExchangeError, Fill  # noqa: E402


class FakeLiveExecutor:
    live = True
    name = "Binance demó"

    def __init__(self):
        self.stops = {}          # cid -> "open" | "filled" | "gone"
        self.orders = {}         # cid -> Fill
        self.fail_protect = False
        self.buy_uncertain = False
        self.sells = []

    def round_qty(self, symbol, qty):
        return round(qty, 5)

    def min_notional(self, symbol):
        return 5.0

    def buy(self, symbol, qty, price, cid):
        fill = Fill(qty * 0.999, price, qty * price * 0.001)
        self.orders[cid] = fill
        if self.buy_uncertain:
            raise ExchangeError("időtúllépés", uncertain=True)
        return fill

    def sell(self, symbol, qty, price, cid):
        self.sells.append(cid)
        return Fill(qty, price, qty * price * 0.001)

    def protect(self, symbol, qty, stop, cid):
        if self.fail_protect:
            raise ExchangeError("STOP_LOSS_LIMIT elutasítva")
        self.stops[cid] = "open"

    def unprotect(self, symbol, cid):
        if self.stops.get(cid) == "open":
            self.stops[cid] = "gone"

    def stop_state(self, symbol, cid):
        st = self.stops.get(cid)
        if st == "open":
            return None
        if st == "filled":
            return ("filled", Fill(1.0, 90.0, 0.09))
        return ("gone", None)

    def lookup(self, symbol, cid):
        return self.orders.get(cid)


def make_live_agent():
    ag, market, bot = make_agent()
    ag.executor = FakeLiveExecutor()
    ag.label = "🧪 BINANCE DEMÓ — játékpénz"
    return ag, market, bot


def test_live_entry_places_exchange_stop():
    ag, _, bot = make_live_agent()
    ag.tick()
    pos = ag.store.open_positions()[0]
    assert pos.stop_cid and ag.executor.stops[pos.stop_cid] == "open"
    assert any("VÉTEL" in m and "BINANCE DEMÓ" in m for m in bot.sent)


def test_live_stop_failure_exits_immediately():
    ag, _, bot = make_live_agent()
    ag.executor.fail_protect = True
    ag.tick()
    assert not ag.store.open_positions()
    assert ag.store.closed_positions()[0].exit_reason == "biztonsági zárás"
    assert ag.executor.sells


def test_live_exchange_stop_fill_is_booked():
    ag, _, bot = make_live_agent()
    ag.tick()
    pos = ag.store.open_positions()[0]
    ag.executor.stops[pos.stop_cid] = "filled"
    ag.tick()
    closed = ag.store.closed_positions()[0]
    assert closed.exit_reason == "stop (tőzsdei)" and not ag.executor.sells


def test_live_uncertain_buy_is_reconciled_not_repeated():
    ag, _, bot = make_live_agent()
    ag.executor.buy_uncertain = True
    ag.tick()
    assert not ag.store.open_positions() and ag.store.get("pending_entry:BTCUSDT")
    ag.executor.buy_uncertain = False
    ag.tick()   # a következő ciklus a tőzsdei adatból könyvel, nem vesz újra
    assert len(ag.store.open_positions()) == 1
    assert len(ag.executor.orders) == 1
    assert ag.store.get("pending_entry:BTCUSDT") is None


def test_binance_signature_is_valid_ed25519():
    import base64
    import urllib.parse

    import httpx
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    priv = Ed25519PrivateKey.generate()
    pem = priv.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                             serialization.NoEncryption()).decode()
    seen = {}

    def handler(request):
        seen["url"] = str(request.url)
        seen["key"] = request.headers.get("X-MBX-APIKEY")
        return httpx.Response(200, json={"balances": [{"asset": "USDT", "free": "5000"}]})

    client = BinanceClient("k", pem, client=httpx.Client(transport=httpx.MockTransport(handler)))
    assert client.free("USDT") == 5000
    query = seen["url"].split("?", 1)[1]
    payload, sig = query.rsplit("&signature=", 1)
    priv.public_key().verify(base64.b64decode(urllib.parse.unquote(sig)), payload.encode())
    assert seen["key"] == "k" and "timestamp=" in payload


def test_binance_place_queries_before_resending(monkeypatch):
    import httpx
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    pem = Ed25519PrivateKey.generate().private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()).decode()
    calls = []

    def handler(request):
        calls.append(request.method)
        if request.method == "POST":
            raise httpx.ReadTimeout("lassú")
        return httpx.Response(200, json={"status": "FILLED", "executedQty": "0.001",
                                         "cummulativeQuoteQty": "77"})

    import exchange
    monkeypatch.setattr(exchange.time, "sleep", lambda s: None)
    client = BinanceClient("k", pem, client=httpx.Client(transport=httpx.MockTransport(handler)))
    order = client.place({"symbol": "BTCUSDT", "side": "BUY", "type": "MARKET", "quantity": "0.001",
                          "newClientOrderId": "mtb-x"})
    assert order["status"] == "FILLED"
    assert calls.count("POST") == 1   # nem küldte újra, mert a lekérdezés megtalálta


def test_forced_entry_runs_once_through_risk_gate(monkeypatch):
    ag, _, bot = make_live_agent()
    ag.store.set("last_candle:BTCUSDT", 10**15)       # a stratégia ebben a ciklusban ne jelezzen
    monkeypatch.setenv("FORCE_ENTRY", "BTCUSDT")
    ag.tick()
    pos = ag.store.open_positions()
    assert len(pos) == 1 and pos[0].stop_cid and ag.executor.stops[pos[0].stop_cid] == "open"
    assert pos[0].risk_amount <= 10_000 * 0.01 * 1.05           # a kockázati határon belül
    assert any("KÉZI INDÍTÁS" in m for m in bot.sent)
    ag.store.close_position(pos[0].id, pos[0].entry_price, 0, "teszt", 0.0)
    ag.tick()                                                   # nem indul újra
    assert not ag.store.open_positions()


# --- radar, védekező mód, webes felület ---------------------------------------------------
import json as _json  # noqa: E402
import math  # noqa: E402

import radar  # noqa: E402


def _series(n=40, day_move=0.0, base=100.0, noise=0.004):
    out, px = [], base
    for i in range(n - 1):
        px *= 1 + noise * (1 if i % 2 else -1)
        out.append((1_700_000_000 + i * 86400, px))
    out.append((1_700_000_000 + (n - 1) * 86400, px * (1 + day_move)))
    return out


def test_measure_flags_unusual_move_not_normal_one():
    calm = radar.measure("EURUSD=X", _series(day_move=0.004))
    big = radar.measure("^GSPC", _series(day_move=-0.035))
    assert not radar.is_notable(calm)
    assert radar.is_notable(big) and big.z < -2.5 and big.day_pct == pytest.approx(-3.5, abs=0.2)
    assert radar.measure("X", _series(n=10)) is None


def test_risk_off_conditions_are_narrow():
    m = lambda sym, pct, price=100: radar.Move(sym, sym, "macro", price, pct, 0, -3, "2026-11-03")  # noqa: E731
    assert radar.risk_off_reason({"^VIX": m("^VIX", 30, 30)})
    assert radar.risk_off_reason({"^VIX": m("^VIX", 30, 15)}) is None      # alacsony szintről ugrás nem pánik
    assert radar.risk_off_reason({"^GSPC": m("^GSPC", -3.4)})
    assert radar.risk_off_reason({"^GSPC": m("^GSPC", -1.0), "BTC-USD": m("BTC-USD", -4)}) is None


def test_parse_rss_and_heuristic():
    xml = ("<rss><channel><item><title>Markets  PLUNGE as bank run fears grow</title>"
           "<link>https://x.test/a</link><pubDate>Mon, 03 Nov 2026 10:00:00 GMT</pubDate></item>"
           "<item><title>no link</title></item></channel></rss>")
    items = radar.parse_rss(xml, "T")
    assert len(items) == 1 and items[0]["title"] == "Markets PLUNGE as bank run fears grow"
    assert radar.heuristic(items[0]["title"])["sev"] == 4 and radar.heuristic("Company opens new office")["sev"] == 2
    assert radar.parse_rss("<<not xml", "T") == []


def test_news_scan_alerts_only_new_severe_and_not_on_first_run():
    import httpx
    xml = ("<rss><channel><item><title>Global markets crash as default looms</title><link>https://x.test/1</link></item>"
           "</channel></rss>")
    client = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, text=xml)))
    st = Store(":memory:", 1000)
    events = []
    r = radar.Radar(st, None, emit=lambda *a: events.append(a), client=client)
    r.scan_news()
    assert events == []                       # az első körben a régi hírek nem riasztanak
    xml2 = xml.replace("https://x.test/1", "https://x.test/2")
    client2 = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, text=xml2)))
    r.client = client2
    r.scan_news()
    assert len(events) >= 1 and events[0][0] == "news"
    n = len(events)
    r.scan_news()
    assert len(events) == n                   # ugyanazt a hírt nem riasztja újra


def test_risk_off_closes_positions_and_pauses_entries():
    ag, market, bot = make_live_agent()
    ag.tick()
    assert ag.store.open_positions()
    ag.risk_off("teszt: pánik")
    assert not ag.store.open_positions()
    assert ag.store.closed_positions()[0].exit_reason == "védekező mód"
    assert ag.entries_paused()
    ag.store.delete("last_candle:BTCUSDT")
    ag.tick()                                  # a stratégia jelezne, de a védekező mód tiltja
    assert not ag.store.open_positions()
    assert "feloldva" in ag.respond("/folytat") and not ag.entries_paused()


def test_web_requires_login_and_serves_state(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from web import make_router
    ag, _, _ = make_agent()
    ag.radar = radar.Radar(ag.store, None)
    monkeypatch.setenv("WEB_PASSWORD", "titok-jelszo")
    app = FastAPI()
    app.include_router(make_router(ag, {"last_tick": None}))
    c = TestClient(app, base_url="https://testserver")
    assert c.get("/api/state").status_code == 401
    assert c.post("/api/login", json={"password": "rossz"}).status_code == 401
    assert c.post("/api/login", json={"password": "titok-jelszo"}).status_code == 200
    s = c.get("/api/state").json()
    assert s["equity"] == pytest.approx(10_000) and s["positions"] == []
    ag.notify("🕐 Teszt esemény\nrészlet", kind="pulse", push=None)
    ev = c.get("/api/events").json()["events"]
    assert any(e["title"] == "🕐 Teszt esemény" for e in ev)
    assert "Parancsok" in c.post("/api/chat", json={"text": "/help"}).json()["reply"]
    monkeypatch.delenv("WEB_PASSWORD")
    assert c.get("/api/state").status_code == 404      # jelszó nélkül a felület ki van kapcsolva


def test_web_login_rate_limit(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from web import make_router
    ag, _, _ = make_agent()
    monkeypatch.setenv("WEB_PASSWORD", "jo")
    app = FastAPI()
    app.include_router(make_router(ag, {}))
    c = TestClient(app, base_url="https://testserver")
    codes = [c.post("/api/login", json={"password": "x"}).status_code for _ in range(10)]
    assert codes[:8] == [401] * 8 and codes[8] == 429
    assert c.post("/api/login", json={"password": "jo"}).status_code == 429   # zárolás alatt a jó jelszó sem jó


def test_llm_falls_back_to_second_provider():
    import httpx

    from llm import LLM
    calls = []

    def gem(request):
        calls.append("gemini")
        return httpx.Response(503, json={"error": "overloaded"})

    def oai(request):
        calls.append("openai")
        return httpx.Response(200, json={"choices": [{"message": {"content": "válasz"}}]})

    import llm as llm_mod
    llm_mod.time.sleep = lambda s: None
    primary = LLM("gemini", "k", client=httpx.Client(transport=httpx.MockTransport(gem)),
                  fallback=LLM("openai", "k", client=httpx.Client(transport=httpx.MockTransport(oai))))
    assert primary.ask("hello") == "válasz"
    assert calls.count("gemini") == 2 and calls[-1] == "openai"


def test_secret_link_logs_in_without_password(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from web import make_router
    ag, _, _ = make_agent()
    monkeypatch.setenv("WEB_PASSWORD", "jelszo")
    monkeypatch.setenv("WEB_LINK_KEY", "k" * 32)
    app = FastAPI()
    app.include_router(make_router(ag, {}))
    c = TestClient(app, base_url="https://testserver")
    assert c.get("/?k=rossz", follow_redirects=False).status_code == 401
    r = c.get("/?k=" + "k" * 32, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/"
    assert c.get("/api/state").status_code == 200


def test_equity_is_logged_and_served():
    ag, market, _ = make_agent()
    ag.tick()
    hist = ag.store.equity_history(0)
    assert len(hist) == 1 and hist[0][1] == pytest.approx(ag.equity({"BTCUSDT": market.price_}), rel=1e-6)
    ag.tick()                                   # 5 percen belül nem ír új pontot
    assert len(ag.store.equity_history(0)) == 1


# --- irány, fogadástípus, világpiaci számla -----------------------------------------------
def test_short_paper_accounting_and_exit():
    st = Store(":memory:", 10_000)
    pid = st.open_position("BTC-USD", 1.0, 100.0, 0.1, 104.0, 92.0, 1, side=-1, kind="trend")
    assert st.cash() == pytest.approx(10_000 + 100 - 0.1)            # az eladás bevétele bejön
    p = st.get_position(pid)
    assert p.side == -1 and p.risk_amount == pytest.approx(4.0)
    assert paper.exit_on_price(p.stop, p.target, 105, -1) == (105, "stop")
    assert paper.exit_on_price(p.stop, p.target, 91, -1) == (91, "cél")
    assert paper.exit_on_price(p.stop, p.target, 100, -1) is None
    pnl = -1 * 1.0 * (92 - 100) - 0.1 - 0.09
    assert st.close_position(pid, 92.0, 0.09, "cél", pnl)
    assert st.cash() == pytest.approx(10_000 + 100 - 0.1 - 92 - 0.09)
    assert st.cash() - 10_000 == pytest.approx(pnl)                    # a számla pont a nyereséggel nőtt


def _mk(closes):
    return make_candles(closes)


def test_evaluate_short_and_dip_signals():
    down = [200 - i * 0.5 for i in range(260)]                         # hosszú esés: EMA200 felett az ár
    bounce = [down[-1] + i * 1.0 for i in range(1, 25)]
    closes = down + bounce
    while strategy.evaluate(_mk(closes), None, {"trend_short"}) is None:
        closes.append(closes[-1] * 0.985)
        assert len(closes) < 400
    sig = strategy.evaluate(_mk(closes), None, {"trend_short"})
    assert sig.side == -1 and sig.stop > sig.price
    assert strategy.evaluate(_mk(closes), None, {"trend_long"}) is None   # nem engedélyezett típus nem jelez
    up = [100 + i * 0.6 for i in range(260)]
    dip = up + [up[-1] * (1 - 0.02 * k) for k in range(1, 8)]
    sig = strategy.evaluate(_mk(dip), None, {"dip_long"})
    assert sig is not None and sig.kind == "dip" and sig.side == 1


def test_news_block_on_opposite_severe_news():
    st = Store(":memory:", 1000)
    nid = st.add_news("https://x/1", "T", "Tesla recalls million cars", None)
    st.set_news_analysis(nid, _json.dumps({"sev": 5, "dir": "down", "assets": ["TSLA"], "hu": "Tesla visszahívás"}))
    assert radar.news_conflict(st, "TSLA", 1)                  # emelkedésre nem fogad
    assert radar.news_conflict(st, "TSLA", -1) is None         # esésre igen
    assert radar.news_conflict(st, "AAPL", 1) is None


def test_world_market_drops_forming_daily_bar():
    import httpx

    from world import YahooMarket
    now = 1_800_000_000
    ts = [now - 86400 * (40 - i) for i in range(40)] + [now - 3600]    # utolsó: ma nyílt
    data = {"chart": {"result": [{"timestamp": ts, "meta": {"regularMarketPrice": 123.4},
                                   "indicators": {"quote": [{"open": [1.0] * 41, "high": [2.0] * 41, "low": [0.5] * 41,
                                                              "close": [1.5] * 41, "volume": [10] * 41}]}}]}}
    m = YahooMarket(client=httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, json=data))),
                    clock=lambda: now)
    c = m.candles("TSLA", "1d")
    assert len(c) == 40 and all(x.close_time < now * 1000 for x in c)
    assert m.price("TSLA") == 123.4


def test_pullback_entry_in_running_uptrend():
    up = [100 * (1.004 ** i) for i in range(300)]
    closes = up + [up[-1] * 0.995]            # kis visszalépés az EMA20 közelébe
    sig = strategy.evaluate(_mk(closes), None, {"pull_long"})
    ind = strategy.compute(_mk(closes))
    if sig is None:                           # ha még túl messze van az EMA20-tól, tovább lépünk vissza
        while sig is None and closes[-1] > ind["fast"][-1]:
            closes.append(closes[-1] * 0.997)
            sig = strategy.evaluate(_mk(closes), None, {"pull_long"})
            ind = strategy.compute(_mk(closes))
    assert sig is not None and sig.kind == "pull" and sig.side == 1
