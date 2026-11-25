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


class FakeAccount:
    """Egy számla (agent) annyiban, amennyit a tárca használ: store + equity()."""
    def __init__(self, cash):
        self.store = Store(":memory:", cash)
        self.extra = 0.0                         # a nyitott pozíciók értékének helyettesítője

    def equity(self, prices):
        return self.store.cash() + self.extra

    def _prices(self, syms, known):
        return {}


def with_accounts(cash_crypto=5000.0, cash_world=9949.0):
    w, sent, clock = make()
    c, wd = FakeAccount(cash_crypto), FakeAccount(cash_world)
    w.accounts = {"crypto": ("Kripto", c), "world": ("Részvény", wd)}
    return w, sent, c, wd


def test_transfer_out_then_in_keeps_total_and_result():
    w, _, c, _ = with_accounts()
    r = w.transfer("crypto", "out", 2000)
    assert r == {"wallet": pytest.approx(2000), "account": pytest.approx(3000)}
    assert c.store.start_equity() == pytest.approx(3000)      # az eredmény nem torzul
    r = w.transfer("crypto", "in", 500)
    assert r["wallet"] == pytest.approx(1500) and r["account"] == pytest.approx(3500)
    assert c.equity({}) - c.store.start_equity() == pytest.approx(0)


@pytest.mark.parametrize("acc,direction,amount", [
    ("crypto", "in", 1),          # üres a tárca
    ("crypto", "out", 5001),      # több, mint a szabad készpénz
    ("nincs", "out", 1),
    ("crypto", "oldalra", 1),
    ("crypto", "out", -3),
])
def test_invalid_transfers_change_nothing(acc, direction, amount):
    w, _, c, wd = with_accounts()
    with pytest.raises(WalletError):
        w.transfer(acc, direction, amount)
    assert w.balance() == 0 and c.store.cash() == 5000 and wd.store.cash() == 9949


def test_failed_account_credit_rolls_back_wallet():
    w, _, c, _ = with_accounts()
    w.transfer("crypto", "out", 1000)
    def boom(delta):
        raise RuntimeError("lemez")
    c.store.move_capital = boom
    with pytest.raises(RuntimeError):
        w.transfer("crypto", "in", 300)
    assert w.balance() == pytest.approx(1000)


def test_return_all_puts_money_back_where_it_came_from():
    w, _, c, wd = with_accounts()
    w.transfer("crypto", "out", 3000)
    w.transfer("world", "out", 1000)
    w.deposit(500)                                # kézzel betett pénz: nem megy vissza
    w.transfer("world", "in", 400)
    r = w.return_all()
    assert r["moved"] == {"crypto": pytest.approx(3000), "world": pytest.approx(600)}
    assert c.store.cash() == pytest.approx(5000)
    assert wd.store.cash() == pytest.approx(9949)
    assert w.balance() == pytest.approx(500)
    assert c.store.start_equity() == pytest.approx(5000)
    assert w.return_all()["moved"] == {}          # másodszor már nincs mit visszatenni


def test_account_drop_alert_once_and_not_on_withdrawal():
    w, sent, c, _ = with_accounts()
    w.scan()                                     # csúcs: eredmény 0
    w.transfer("crypto", "out", 3000)            # kivét: nem esés
    assert w.scan() == []
    c.extra = -600                               # 600 $ veszteség a 2000 $-os számlán
    assert len(w.scan()) == 1 and "Kripto" in sent[-1]
    assert w.scan() == []                        # ugyanarra a csúcsra csak egyszer


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
