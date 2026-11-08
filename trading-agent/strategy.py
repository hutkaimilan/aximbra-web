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
    side: int = 1               # 1: emelkedésre (long), -1: esésre (short)
    kind: str = "trend"         # "trend" | "dip"


KINDS = {
    "trend_long": "emelkedésre (trendkövetés)",
    "trend_short": "esésre (trendkövetés)",
    "dip_long": "visszapattanásra (túladott, de hosszú távon emelkedő)",
    "pull_long": "emelkedésre (futó trendbe, visszalépésnél)",
}
TARGET_R_BY_KIND = {"trend": TARGET_R, "dip": 3.0}   # a dip fő kilépése az EMA20 visszaérése, a cél csak vészfék
DIP_MAX_BARS = 10
TRAIL_KINDS = {"trend", "pull", "ai"}      # emelkedésre ezeknél követő stop van, fix cél nélkül
TRAIL_ATR = 3.0


def trail_stop(pos, candles, atr_now: float) -> float | None:
    """Új (magasabb) stop a követő szabály szerint, vagy None. +1R után nullszaldó, utána a pozíció óta
    látott legmagasabb záró alatt 3 ATR-rel. A stop soha nem megy lefelé."""
    if pos.side != 1 or pos.kind not in TRAIL_KINDS or not atr_now or pos.qty <= 0:
        return None
    r0 = pos.risk_amount / pos.qty
    closes = [c.close for c in candles if c.open_time > pos.entry_candle]
    if not closes or r0 <= 0:
        return None
    hi = max(closes)
    if hi - pos.entry_price < r0:
        return None
    new = max(pos.stop, pos.entry_price, hi - TRAIL_ATR * atr_now)
    return new if new > pos.stop + 0.1 * atr_now else None


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


def rsi(closes: list[float], n: int = 14) -> list[float | None]:
    out: list[float | None] = [None] * len(closes)
    up = dn = 0.0
    for i in range(1, len(closes)):
        d = closes[i] - closes[i - 1]
        u, w = max(d, 0.0), max(-d, 0.0)
        if i <= n:
            up += u / n
            dn += w / n
        else:
            up = (up * (n - 1) + u) / n
            dn = (dn * (n - 1) + w) / n
        if i >= n:
            out[i] = 100 - 100 / (1 + up / dn) if dn else 100.0
    return out


def lower_band(closes: list[float], n: int = 20, k: float = 2.0) -> list[float | None]:
    out: list[float | None] = [None] * len(closes)
    for i in range(n - 1, len(closes)):
        w = closes[i - n + 1:i + 1]
        m = sum(w) / n
        sd = (sum((x - m) ** 2 for x in w) / n) ** 0.5
        out[i] = m - k * sd
    return out


def compute(candles: list[Candle]) -> dict:
    closes = [c.close for c in candles]
    return {"close": closes, "fast": ema(closes, FAST), "slow": ema(closes, SLOW),
            "regime": ema(closes, REGIME), "atr": atr(candles, ATR_N),
            "rsi": rsi(closes), "lower": lower_band(closes)}


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


def evaluate(candles: list[Candle], pos=None, allowed: set[str] | frozenset = frozenset({"trend_long"})) -> Signal | None:
    """Döntés az utolsó lezárt gyertyán. pos: nyitott pozíció (side, kind, entry_candle) vagy None.
    Belépés sorrendje: trend emelkedésre, trend esésre, visszapattanás. Kilépés a pozíció típusa szerint."""
    if len(candles) < MIN_BARS:
        return None
    ind = compute(candles)
    i = len(candles) - 1
    f, s, r, a, c = ind["fast"], ind["slow"], ind["regime"], ind["atr"], ind["close"]
    if any(v is None for v in (f[i], s[i], f[i - 1], s[i - 1], r[i], a[i])) or a[i] <= 0:
        return None
    if pos is not None:
        side, kind = getattr(pos, "side", 1) or 1, getattr(pos, "kind", "trend") or "trend"
        if kind == "ai":
            return None   # az AI-kereskedő pozícióiról az AI dönt (és a stop véd)
        if kind == "dip":
            age = sum(1 for x in candles if x.open_time > pos.entry_candle)
            if c[i] > f[i]:
                return Signal("exit", c[i], "visszapattant: az ár visszaért a rövid távú átlag (EMA20) fölé")
            if age >= DIP_MAX_BARS:
                return Signal("exit", c[i], f"{DIP_MAX_BARS} gyertya alatt sem pattant vissza: időkorlát")
            return None
        if side == 1 and kind in TRAIL_KINDS:
            return None   # a kilépést a követő stop végzi (research: +0,14R → +0,28R)
        if side == 1 and f[i] < s[i]:
            return Signal("exit", c[i], "az EMA20 az EMA50 alá került: az emelkedő lendület elfogyott")
        if side == -1 and f[i] > s[i]:
            return Signal("exit", c[i], "az EMA20 az EMA50 fölé került: az eső lendület elfogyott")
        return None
    up = f[i - 1] <= s[i - 1] and f[i] > s[i]
    down = f[i - 1] >= s[i - 1] and f[i] < s[i]
    if "trend_long" in allowed and up and c[i] > r[i]:
        return Signal("enter", c[i], "emelkedésre: az EMA20 felfelé keresztezte az EMA50-et, és a hosszú trend is emelkedő",
                      stop=c[i] - STOP_ATR * a[i], atr=a[i], side=1, kind="trend")
    if "trend_short" in allowed and down and c[i] < r[i]:
        return Signal("enter", c[i], "esésre: az EMA20 lefelé keresztezte az EMA50-et, és a hosszú trend is eső",
                      stop=c[i] + STOP_ATR * a[i], atr=a[i], side=-1, kind="trend")
    if ("pull_long" in allowed and f[i] > s[i] and c[i] > r[i] and 0 <= c[i] - f[i] <= 0.5 * a[i]
            and c[i - 1] > f[i - 1]):
        return Signal("enter", c[i], "emelkedésre: futó emelkedő trendben az ár visszalépett a rövid távú átlaghoz "
                      "(EMA20), és ott megtartotta", stop=c[i] - STOP_ATR * a[i], atr=a[i], side=1, kind="pull")
    rs, lo = ind["rsi"][i], ind["lower"][i]
    if "dip_long" in allowed and rs is not None and lo is not None and rs < 30 and c[i] < lo and c[i] > r[i]:
        return Signal("enter", c[i], f"visszapattanásra: túladott (RSI {rs:.0f}), az ár a szokásos sáv alá esett, "
                      "de a hosszú trend emelkedő", stop=c[i] - STOP_ATR * a[i], atr=a[i], side=1, kind="dip")
    return None


def target_for_side(entry: float, stop: float, side: int, kind: str) -> float:
    return entry + side * TARGET_R_BY_KIND.get(kind, TARGET_R) * abs(entry - stop)


def latest(candles: list[Candle], in_position: bool) -> Signal | None:
    if len(candles) < MIN_BARS:
        return None
    return signal_at(compute(candles), len(candles) - 1, in_position)


def target_for(entry: float, stop: float) -> float:
    return entry + TARGET_R * (entry - stop)
