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
