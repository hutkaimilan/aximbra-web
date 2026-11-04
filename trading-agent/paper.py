"""Papírkereskedés számításai: teljesítési ár, pozícióméret, kockázati kapu, elszámolás.

Tiszta függvények: a backtest és az élő agent ugyanezeket hívja, így a kettő
nem tud elcsúszni egymástól. A kockázati szabályok itt, kódban vannak — a
nyelvi modell ezeket nem látja és nem is tudja felülírni.
"""
from __future__ import annotations

from market import Candle

MIN_NOTIONAL = 10.0   # a Binance spot minimális kötésértéke nagyjából ennyi USDT


def entry_fill(price: float, slippage: float) -> float:
    return price * (1 + slippage)


def exit_fill(price: float, slippage: float) -> float:
    return price * (1 - slippage)


def size(equity: float, cash: float, entry: float, stop: float, risk_pct: float,
         max_open: int, fee: float) -> float:
    """Darabszám úgy, hogy a stopig `risk_pct` × tőke legyen a veszteség, de egy
    pozíció ne legyen nagyobb a tőke 1/max_open részénél és a szabad készpénznél."""
    per_unit = entry - stop
    if entry <= 0 or per_unit <= 0 or equity <= 0 or cash <= 0:
        return 0.0
    by_risk = equity * risk_pct / per_unit
    cap = min(cash, equity / max(max_open, 1)) / (1 + fee)
    return max(0.0, min(by_risk, cap / entry))


def can_open(open_count: int, max_open: int, day_realized: float, equity: float,
             daily_loss_limit: float) -> tuple[bool, str]:
    if open_count >= max_open:
        return False, f"már {open_count} pozíció nyitva (legfeljebb {max_open})"
    if equity > 0 and day_realized <= -daily_loss_limit * equity:
        return False, (f"elérte a napi veszteséglimitet ({day_realized:,.2f} USDT, "
                       f"limit {daily_loss_limit:.1%}); ma nincs több nyitás")
    return True, ""


def exit_on_bar(stop: float, target: float, bar: Candle) -> tuple[float, str] | None:
    """Stop vagy cél egy gyertyán belül. Ha mindkettő belefér, a stopot vesszük:
    a gyertyából nem tudni, melyik jött előbb, és a rosszabbat feltételezni a becsületes."""
    if bar.low <= stop:
        return min(stop, bar.open), "stop"      # ha nyitáskor már alatta volt, a nyitóáron
    if bar.high >= target:
        return max(target, bar.open), "cél"
    return None


def exit_on_price(stop: float, target: float, price: float, side: int = 1) -> tuple[float, str] | None:
    if side == 1:
        if price <= stop:
            return price, "stop"
        if price >= target:
            return price, "cél"
        return None
    if price >= stop:
        return price, "stop"
    if price <= target:
        return price, "cél"
    return None


def settle(qty: float, entry_px: float, entry_fee: float, raw_exit: float,
           fee: float, slippage: float) -> tuple[float, float, float]:
    """(kilépési ár, kilépési díj, nettó eredmény díjakkal)."""
    exit_px = exit_fill(raw_exit, slippage)
    exit_fee = qty * exit_px * fee
    pnl = qty * (exit_px - entry_px) - entry_fee - exit_fee
    return exit_px, exit_fee, pnl
