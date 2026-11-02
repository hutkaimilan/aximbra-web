"""Beállítások környezeti változókból, induláskor ellenőrizve.

Hibás érték esetén a szolgáltatás el sem indul: egy rosszul beírt kockázati
limit (pl. RISK_PER_TRADE=1 az 0.01 helyett) csendben a számla 100%-át
kockáztatná kötésenként.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

INTERVALS = {"15m": 900, "30m": 1800, "1h": 3600, "2h": 7200, "4h": 14400,
             "6h": 21600, "12h": 43200, "1d": 86400}
_SYMBOL = re.compile(r"^[A-Z0-9]{5,20}$")


class ConfigError(ValueError):
    pass


def _num(name: str, default: float, lo: float, hi: float) -> float:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        value = float(raw)
    except ValueError:
        raise ConfigError(f"{name}: nem szám ({raw!r})") from None
    if not lo <= value <= hi:
        raise ConfigError(f"{name}: {lo} és {hi} között kell lennie (most {value})")
    return value


@dataclass(frozen=True)
class Config:
    symbols: tuple[str, ...] = ("BTCUSDT", "ETHUSDT")
    interval: str = "4h"
    start_equity: float = 10_000.0
    risk_per_trade: float = 0.01      # a tőke hány százalékát kockáztatja egy kötés (stopig)
    max_open: int = 2                 # egyszerre nyitott pozíciók
    daily_loss_limit: float = 0.03    # ennyi napi realizált veszteség után aznap nincs új nyitás
    fee: float = 0.001                # Binance spot taker díj oldalanként
    slippage: float = 0.0005
    poll_seconds: int = 60
    report_hour: int = 8
    timezone: str = "Europe/Budapest"
    db_path: str = "/data/trading.db"

    @property
    def interval_seconds(self) -> int:
        return INTERVALS[self.interval]

    @property
    def tz(self) -> ZoneInfo:
        return ZoneInfo(self.timezone)


def load() -> Config:
    raw_symbols = os.environ.get("TRADING_SYMBOLS", "BTCUSDT,ETHUSDT")
    symbols = tuple(dict.fromkeys(s.strip().upper() for s in raw_symbols.split(",") if s.strip()))
    if not symbols:
        raise ConfigError("TRADING_SYMBOLS: legalább egy instrumentum kell (pl. BTCUSDT)")
    bad = [s for s in symbols if not _SYMBOL.match(s)]
    if bad:
        raise ConfigError(f"TRADING_SYMBOLS: érvénytelen név: {', '.join(bad)}")

    interval = os.environ.get("TRADING_INTERVAL", "4h").strip()
    if interval not in INTERVALS:
        raise ConfigError(f"TRADING_INTERVAL: ezek egyike kell: {', '.join(INTERVALS)}")

    tz = os.environ.get("TRADING_TZ", "Europe/Budapest").strip()
    try:
        ZoneInfo(tz)
    except (ZoneInfoNotFoundError, ValueError):
        raise ConfigError(f"TRADING_TZ: ismeretlen időzóna ({tz})") from None

    return Config(
        symbols=symbols,
        interval=interval,
        start_equity=_num("PAPER_START_EQUITY", 10_000, 100, 1e9),
        risk_per_trade=_num("RISK_PER_TRADE", 0.01, 0.001, 0.05),
        max_open=int(_num("MAX_OPEN_POSITIONS", 2, 1, 10)),
        daily_loss_limit=_num("DAILY_LOSS_LIMIT", 0.03, 0.005, 0.2),
        fee=_num("FEE_RATE", 0.001, 0, 0.01),
        slippage=_num("SLIPPAGE_RATE", 0.0005, 0, 0.01),
        poll_seconds=int(_num("POLL_SECONDS", 60, 15, 3600)),
        report_hour=int(_num("REPORT_HOUR", 8, 0, 23)),
        timezone=tz,
        db_path=os.environ.get("TRADING_DB_PATH", "/data/trading.db"),
    )
