"""Visszatesztelés valódi múltbeli gyertyákon, díjjal és csúszással.

Ugyanazt a stratégiát (strategy.signal_at) és ugyanazokat a kockázati
szabályokat (paper.*) futtatja, mint az élő agent. Instrumentumonként külön
számlán fut, így az eredmény az adott piacon mért teljesítmény.

Parancssorból:  python backtest.py BTCUSDT ETHUSDT --bars 3000
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone

import config
import paper
import strategy
from market import Candle, Market, MarketError


def _day(ms: int, tz) -> str:
    return datetime.fromtimestamp(ms / 1000, tz).date().isoformat()


def run(symbol: str, candles: list[Candle], cfg: config.Config) -> dict:
    if len(candles) < strategy.MIN_BARS + 10:
        raise ValueError(f"legalább {strategy.MIN_BARS + 10} gyertya kell a teszthez (most {len(candles)})")
    ind = strategy.compute(candles)
    first = strategy.MIN_BARS - 1
    cash = cfg.start_equity
    pos: dict | None = None
    trades: list[dict] = []
    fees = 0.0
    peak = cash
    max_dd = 0.0
    day_pnl: dict[str, float] = {}

    def close(i: int, raw_price: float, reason: str) -> None:
        nonlocal cash, pos, fees
        exit_px, exit_fee, pnl = paper.settle(pos["qty"], pos["entry"], pos["entry_fee"], raw_price,
                                              cfg.fee, cfg.slippage)
        cash += pos["qty"] * exit_px - exit_fee
        fees += exit_fee
        day = _day(candles[i].close_time, cfg.tz)
        day_pnl[day] = day_pnl.get(day, 0.0) + pnl
        trades.append({"entry_time": candles[pos["i"]].close_time, "exit_time": candles[i].close_time,
                       "entry": pos["entry"], "exit": exit_px, "reason": reason, "pnl": pnl,
                       "r": pnl / pos["risk"] if pos["risk"] > 0 else 0.0})
        pos = None

    for i in range(first, len(candles)):
        bar = candles[i]
        if pos is not None and i > pos["i"]:
            hit = paper.exit_on_bar(pos["stop"], pos["target"], bar)
            if hit:
                close(i, *hit)
        sig = strategy.signal_at(ind, i, pos is not None)
        if sig and sig.action == "exit" and pos is not None:
            close(i, bar.close, "jelzés")
        elif sig and sig.action == "enter" and pos is None:
            ok, _ = paper.can_open(0, cfg.max_open, day_pnl.get(_day(bar.close_time, cfg.tz), 0.0), cash,
                                   cfg.daily_loss_limit)
            fill = paper.entry_fill(bar.close, cfg.slippage)
            if ok and fill > sig.stop:
                qty = paper.size(cash, cash, fill, sig.stop, cfg.risk_per_trade, cfg.max_open, cfg.fee)
                if qty * fill >= paper.MIN_NOTIONAL:
                    entry_fee = qty * fill * cfg.fee
                    cash -= qty * fill + entry_fee
                    fees += entry_fee
                    pos = {"i": i, "qty": qty, "entry": fill, "entry_fee": entry_fee, "stop": sig.stop,
                           "target": strategy.target_for(fill, sig.stop), "risk": qty * (fill - sig.stop)}
        equity = cash + (pos["qty"] * bar.close if pos else 0.0)
        peak = max(peak, equity)
        max_dd = max(max_dd, (peak - equity) / peak if peak > 0 else 0.0)

    if pos is not None:  # a végén nyitva maradt pozíciót az utolsó záróáron számoljuk el
        close(len(candles) - 1, candles[-1].close, "teszt vége")

    wins = [t for t in trades if t["pnl"] > 0]
    gross_win = sum(t["pnl"] for t in wins)
    gross_loss = -sum(t["pnl"] for t in trades if t["pnl"] <= 0)
    return {
        "symbol": symbol,
        "interval": cfg.interval,
        "from": candles[first].close_time,
        "to": candles[-1].close_time,
        "bars": len(candles) - first,
        "trades": len(trades),
        "win_rate": len(wins) / len(trades) if trades else 0.0,
        "avg_r": sum(t["r"] for t in trades) / len(trades) if trades else 0.0,
        "profit_factor": gross_win / gross_loss if gross_loss > 0 else None,
        "return": cash / cfg.start_equity - 1,
        "buy_hold": candles[-1].close / candles[first].close - 1,
        "max_drawdown": max_dd,
        "fees": fees,
        "final_equity": cash,
        "trade_list": trades,
    }


def summary(res: dict) -> str:
    fmt = lambda ms: datetime.fromtimestamp(ms / 1000, timezone.utc).strftime("%Y-%m-%d")  # noqa: E731
    pf = "—" if res["profit_factor"] is None else f"{res['profit_factor']:.2f}"
    # Csökkenő piacon a kisebb veszteség is "veri" a tartást — az mégsem nyereséges stratégia.
    if res["trades"] == 0:
        verdict = "⚪ nem volt kötés: ebből nem lehet ítéletet mondani"
    elif res["return"] > 0 and res["avg_r"] > 0 and res["return"] > res["buy_hold"]:
        verdict = "✅ díjakkal együtt nyereséges, és jobb a „vedd meg és tartsd”-nál"
    elif res["return"] > res["buy_hold"]:
        verdict = "🟡 kevesebbet veszített, mint a tartás, de önmagában nem nyereséges"
    else:
        verdict = "❌ díjakkal együtt rosszabb, mint a „vedd meg és tartsd”"
    if 0 < res["trades"] < 30:
        verdict += f"\n⚠️ {res['trades']} kötés kevés: statisztikailag ez még nem bizonyíték"
    return (f"📊 Backtest — {res['symbol']} ({res['interval']}), {fmt(res['from'])} → {fmt(res['to'])}\n"
            f"Kötések: {res['trades']} | találati arány: {res['win_rate']:.0%} | átlag: {res['avg_r']:+.2f}R | "
            f"profit faktor: {pf}\n"
            f"Hozam: {res['return']:+.1%} | vedd-meg-és-tartsd: {res['buy_hold']:+.1%} | "
            f"max. visszaesés: {res['max_drawdown']:.1%} | díjak: {res['fees']:,.0f} USDT\n"
            f"{verdict}\n"
            f"Stratégia: {strategy.NAME}")


def run_symbol(market: Market, symbol: str, cfg: config.Config, bars: int = 3000) -> dict:
    candles = market.history(symbol, cfg.interval, bars)
    return run(symbol, candles, cfg)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Backtest valódi Binance-adatokon")
    parser.add_argument("symbols", nargs="*", help="pl. BTCUSDT ETHUSDT (alapértelmezés: TRADING_SYMBOLS)")
    parser.add_argument("--bars", type=int, default=3000, help="gyertyák száma (alapértelmezés: 3000)")
    args = parser.parse_args(argv)
    cfg = config.load()
    market = Market()
    status = 0
    for sym in [s.upper() for s in args.symbols] or list(cfg.symbols):
        try:
            print(summary(run_symbol(market, sym, cfg, args.bars)), end="\n\n")
        except (MarketError, ValueError) as e:
            print(f"{sym}: {e}", file=sys.stderr)
            status = 1
    return status


if __name__ == "__main__":
    sys.exit(main())
