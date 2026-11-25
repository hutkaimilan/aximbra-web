"""A tárca: könyvelés, érvényesítés, előrejelzés és a bot tanácsai — hálózat nélkül."""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import strategy  # noqa: E402
from market import Candle, MarketError  # noqa: E402
from store import Store  # noqa: E402
from wallet import Wallet, WalletError  # noqa: E402

DAY = 86400 * 1000


def candles(closes, start=1_600_000_000_000):
    out, prev = [], closes[0]
    for i, c in enumerate(closes):
        out.append(Candle(start + i * DAY, prev, max(prev, c) * 1.01, min(prev, c) * 0.99, c, 1.0,
                          start + (i + 1) * DAY - 1))
        prev = c
    return out


class FakeMarket:
    def __init__(self, prices=None, series=None):
        self.prices = dict(prices or {})
        self.series = dict(series or {})

    def price(self, sym):
        if sym not in self.prices:
            raise MarketError("nincs ár")
        return self.prices[sym]

    def candles(self, sym, interval="1d", limit=400):
        if sym not in self.series:
            raise MarketError("nincs adat")
        return self.series[sym][-limit:]


def make(market=None, watch=()):
    sent = []
    clock = [1_700_000_000.0]
    w = Wallet(Store(":memory:", 0.0), market or FakeMarket({"AAPL": 100.0}),
               lambda text, kind="wallet", push=None: sent.append(text), clock=lambda: clock[0], watch=watch)
    return w, sent, clock


def test_deposit_buy_sell_moves_money_between_balance_and_holding():
    w, _, _ = make()
    w.deposit(1000)
    s = w.buy("aapl", 400)                       # 4 db 100-on
    assert s["balance"] == pytest.approx(600)
    assert s["holdings"][0]["qty"] == pytest.approx(4)
    w.market.prices["AAPL"] = 150.0
    s = w.sell("AAPL", 2)                        # 2 × 150 = 300 vissza
    assert s["balance"] == pytest.approx(900)
    assert s["holdings"][0]["qty"] == pytest.approx(2)
    assert s["realized"] == pytest.approx(100)   # 300 − 2 × 100
    assert s["total"] == pytest.approx(1200)     # 900 + 2 × 150
    assert s["pnl"] == pytest.approx(200)
    s = w.sell("AAPL")                           # a maradék
    assert s["holdings"] == [] and s["balance"] == pytest.approx(1200)


def test_withdraw_reduces_balance_and_net_deposits():
    w, _, _ = make()
    w.deposit(500)
    s = w.withdraw(200)
    assert s["balance"] == pytest.approx(300) and s["net_deposits"] == pytest.approx(300) and s["pnl"] == 0


@pytest.mark.parametrize("action", [
    lambda w: w.withdraw(1),                     # üres tárcából
    lambda w: w.buy("AAPL", 10),                 # nincs pénz
    lambda w: w.sell("AAPL"),                    # nincs tétel
    lambda w: w.deposit(-5),
    lambda w: w.deposit(float("nan")),
    lambda w: w.deposit("sok"),
    lambda w: w.buy("rossz jelölés!", 1),
    lambda w: w.buy("MSFT", 1),                  # nincs ár
])
def test_invalid_requests_raise_and_book_nothing(action):
    w, _, _ = make()
    with pytest.raises(WalletError):
        action(w)
    assert w.transactions() == []


def test_cannot_sell_more_than_held():
    w, _, _ = make()
    w.deposit(1000)
    w.buy("AAPL", 100)
    with pytest.raises(WalletError):
        w.sell("AAPL", 5)
    assert w.balance() == pytest.approx(900)


def test_buy_at_given_price_records_that_price():
    w, _, _ = make()
    w.deposit(1000)
    w.buy("AAPL", 500, price=125)
    assert w.ledger()[1]["AAPL"].qty == pytest.approx(4)


def uptrend_with_fresh_cross():
    closes = [100 + i * 0.5 for i in range(260)] + [230 - i * 1.2 for i in range(1, 31)]
    while True:
        closes.append(closes[-1] * 1.01)
        cs = candles(closes)
        sig = strategy.evaluate(cs, None, allowed={"trend_long", "pull_long"})
        if sig and sig.action == "enter":
            return cs
        assert len(closes) < 600


def test_scan_suggests_buy_amount_and_asks_for_money_when_short():
    cs = uptrend_with_fresh_cross()
    m = FakeMarket({"AAPL": cs[-1].close, "KO": 50.0}, {"AAPL": cs})
    w, sent, _ = make(m, watch=("AAPL",))
    w.deposit(1000)
    w.buy("KO", 950)                             # szinte minden pénz be van fektetve
    out = [x for x in w.scan() if "AAPL" in x]
    assert len(out) == 1 and "tegyél be" in out[0]
    assert w.scan() == []                        # ugyanarra a napra nem szól kétszer


def test_scan_on_empty_wallet_says_deposit_first():
    cs = uptrend_with_fresh_cross()
    w, _, _ = make(FakeMarket({"AAPL": cs[-1].close}, {"AAPL": cs}), watch=("AAPL",))
    out = w.scan()
    assert len(out) == 1 and "tegyél be pénzt" in out[0]


def test_scan_says_buy_with_amount_within_limits():
    cs = uptrend_with_fresh_cross()
    w, sent, _ = make(FakeMarket({"AAPL": cs[-1].close}, {"AAPL": cs}), watch=("AAPL",))
    w.deposit(10_000)
    out = w.scan()
    assert len(out) == 1 and "VEDD" in out[0]
    amount = float(out[0].split("Javasolt összeg: ")[1].split(" $")[0].replace(",", ""))
    assert 10 <= amount <= 2_500                 # legfeljebb a tárca 25%-a


def test_scan_says_sell_when_price_breaks_protective_level():
    closes = [100 + i * 0.5 for i in range(260)]
    cs = candles(closes)
    m = FakeMarket({"AAPL": closes[-1]}, {"AAPL": cs})
    w, sent, clock = make(m, watch=())
    clock[0] = cs[-1].close_time / 1000 - 5 * 86400
    w.deposit(1000)
    w.buy("AAPL", 500)
    crash = closes + [closes[-1] * 0.8]          # egy nagy esés a vétel után
    m.series["AAPL"] = candles(crash)
    m.prices["AAPL"] = crash[-1]
    out = w.scan()
    assert len(out) == 1 and "ADD EL" in out[0]


def test_scan_skips_broken_symbol_and_keeps_going():
    cs = uptrend_with_fresh_cross()
    w, _, _ = make(FakeMarket({"AAPL": cs[-1].close}, {"AAPL": cs}), watch=("NOPE", "AAPL"))
    w.deposit(10_000)
    assert len(w.scan()) == 1


def test_outlook_reports_frequencies_not_certainty():
    closes = [100 * (1.001 ** i) * (1 + 0.02 * ((i % 7) - 3) / 3) for i in range(500)]
    w, _, _ = make()
    o = w.outlook("AAPL", candles(closes))
    h20 = o["horizons"][-1]
    assert h20["days"] == 20 and h20["n"] >= 15
    assert 0 <= h20["up_pct"] <= 100 and h20["low_pct"] <= h20["median_pct"] <= h20["high_pct"]
    assert "nem garancia" in o["text"]


def test_outlook_needs_enough_data():
    w, _, _ = make()
    with pytest.raises(WalletError):
        w.outlook("AAPL", candles([100.0] * 50))


def test_drawdown_alert_once_per_peak():
    m = FakeMarket({"AAPL": 100.0})
    w, sent, _ = make(m)
    w.deposit(1000)
    w.buy("AAPL", 1000)
    w._check_drawdown(w.summary())
    m.prices["AAPL"] = 85.0
    w._check_drawdown(w.summary())
    w._check_drawdown(w.summary())
    assert len([s for s in sent if "estek" in s]) == 1


def test_watchlist_roundtrip_and_validation():
    w, _, _ = make()
    assert w.set_watchlist(["aapl", "AAPL", "btc-usd"]) == ["AAPL", "BTC-USD"]
    assert w.watchlist() == ["AAPL", "BTC-USD"]
    with pytest.raises(WalletError):
        w.set_watchlist(["bad symbol!"])
