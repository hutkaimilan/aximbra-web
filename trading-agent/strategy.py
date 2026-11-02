"""Alapstratégia: trendkövetés mozgóátlagokkal.

Ez szándékosan nem „a világ legjobb stratégiája”, hanem egy átlátható, jól
ismert kiindulópont, amin a teljes lánc — adat, jelzés, kockázat, napló,
értesítés — élesben letesztelhető. Hogy van-e benne valódi előny, azt a
backtest és a papírkereskedés számai döntik el, nem ez a leírás.

Szabályok (csak long, spot):
- belépés: az EMA20 felfelé keresztezi az EMA50-et, és a záróár az EMA200 fölött van;
- stop: belépés − 2 × ATR14;   cél: belépés + 2 × (belépés − stop), azaz 2R;
- kilépés jelzésre: az EMA20 lefelé keresztezi az EMA50-et.
"""
from __future__ import annotations

from dataclasses import dataclass

from market import Candle

NAME = "EMA20/50 keresztezés, EMA200 trendszűrő, 2×ATR stop, 2R cél"
FAST, SLOW, REGIME, ATR_N = 20, 50, 200, 14
STOP_ATR = 2.0
TARGET_R = 2.0
MIN_BARS = REGIME + 2


@dataclass(frozen=True)
class Signal:
    action: str                 # "enter" | "exit"
    price: float                # a jelzést adó gyertya záróára
    reason: str
    stop: float | None = None
    atr: float | None = None


def ema(values: list[float], n: int) -> list[float | None]:
    out: list[float | None] = [None] * len(values)
    if n <= 0 or len(values) < n:
        return out
    k = 2 / (n + 1)
    prev = sum(values[:n]) / n
    out[n - 1] = prev
    for i in range(n, len(values)):
        prev = values[i] * k + prev * (1 - k)
        out[i] = prev
    return out


def atr(candles: list[Candle], n: int) -> list[float | None]:
    """Wilder-féle átlagos valódi tartomány."""
    out: list[float | None] = [None] * len(candles)
    if n <= 0 or len(candles) <= n:
        return out
    trs = [candles[0].high - candles[0].low]
    for i in range(1, len(candles)):
        c, prev_close = candles[i], candles[i - 1].close
        trs.append(max(c.high - c.low, abs(c.high - prev_close), abs(c.low - prev_close)))
    prev = sum(trs[1:n + 1]) / n
    out[n] = prev
    for i in range(n + 1, len(candles)):
        prev = (prev * (n - 1) + trs[i]) / n
        out[i] = prev
    return out


def compute(candles: list[Candle]) -> dict:
    closes = [c.close for c in candles]
    return {"close": closes, "fast": ema(closes, FAST), "slow": ema(closes, SLOW),
            "regime": ema(closes, REGIME), "atr": atr(candles, ATR_N)}


def signal_at(ind: dict, i: int, in_position: bool) -> Signal | None:
    """Jelzés az i-edik (lezárt) gyertyán. A backtest és az élő futás ugyanezt hívja."""
    if i < 1:
        return None
    f, s, r, a, close = ind["fast"], ind["slow"], ind["regime"], ind["atr"], ind["close"]
    if any(v is None for v in (f[i], s[i], f[i - 1], s[i - 1], r[i], a[i])):
        return None
    if in_position:
        if f[i - 1] >= s[i - 1] and f[i] < s[i]:
            return Signal("exit", close[i], "az EMA20 lefelé keresztezte az EMA50-et: a felfelé tartó trend megtört")
        return None
    if f[i - 1] <= s[i - 1] and f[i] > s[i] and close[i] > r[i] and a[i] > 0:
        return Signal("enter", close[i],
                      "az EMA20 felfelé keresztezte az EMA50-et, és az ár az EMA200 fölött van (emelkedő trend)",
                      stop=close[i] - STOP_ATR * a[i], atr=a[i])
    return None


def latest(candles: list[Candle], in_position: bool) -> Signal | None:
    if len(candles) < MIN_BARS:
        return None
    return signal_at(compute(candles), len(candles) - 1, in_position)


def target_for(entry: float, stop: float) -> float:
    return entry + TARGET_R * (entry - stop)
