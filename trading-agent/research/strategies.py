"""Négy fogadástípus visszatesztje 10 kriptón, 4 órás gyertyákon, határidős díjjal, két külön időszakon."""
import sys, statistics
sys.path.insert(0, "..")
import strategy
from market import Market

SYMS = "BTC ETH SOL BNB XRP DOGE ADA AVAX LINK TRX".split()
FEE, SLIP = 0.0005, 0.0002          # Binance USDⓈ-M taker díj + csúszás oldalanként
COST = 2 * (FEE + SLIP)

def rsi(closes, n=14):
    out = [None] * len(closes); up = dn = 0.0
    for i in range(1, len(closes)):
        d = closes[i] - closes[i - 1]; u, w = max(d, 0), max(-d, 0)
        if i <= n: up += u / n; dn += w / n
        else: up = (up * (n - 1) + u) / n; dn = (dn * (n - 1) + w) / n
        if i >= n: out[i] = 100 - 100 / (1 + up / dn) if dn else 100
    return out

def bands(closes, n=20, k=2.0):
    lo, hi = [None] * len(closes), [None] * len(closes)
    for i in range(n - 1, len(closes)):
        w = closes[i - n + 1:i + 1]; m = sum(w) / n; sd = statistics.pstdev(w)
        lo[i], hi[i] = m - k * sd, m + k * sd
    return lo, hi

def run(c):
    closes = [x.close for x in c]
    ind = strategy.compute(c); R = rsi(closes); lo, hi = bands(closes)
    f, s, r, a = ind["fast"], ind["slow"], ind["regime"], ind["atr"]
    trades = {k: [] for k in ("trend_long", "trend_short", "dip_long", "pop_short")}
    open_ = {}
    for i in range(strategy.MIN_BARS, len(c)):
        bar = c[i]
        for k, p in list(open_.items()):          # kilépések
            d = p["dir"]; out = None
            if d == 1 and bar.low <= p["stop"]: out = min(p["stop"], bar.open)
            elif d == -1 and bar.high >= p["stop"]: out = max(p["stop"], bar.open)
            elif d == 1 and p.get("tgt") and bar.high >= p["tgt"]: out = max(p["tgt"], bar.open)
            elif d == -1 and p.get("tgt") and bar.low <= p["tgt"]: out = min(p["tgt"], bar.open)
            elif k == "trend_long" and f[i] < s[i]: out = bar.close
            elif k == "trend_short" and f[i] > s[i]: out = bar.close
            elif k in ("dip_long", "pop_short") and (i - p["i"] >= 12 or (d == 1 and bar.close > f[i]) or (d == -1 and bar.close < f[i])): out = bar.close
            if out is not None:
                ret = d * (out / p["e"] - 1) - COST
                trades[k].append((c[p["i"]].close_time, ret / p["risk"]))
                del open_[k]
        if None in (f[i], s[i], r[i], a[i], R[i], lo[i]): continue
        e = bar.close
        cu = f[i - 1] <= s[i - 1] and f[i] > s[i]; cd = f[i - 1] >= s[i - 1] and f[i] < s[i]
        if "trend_long" not in open_ and cu and e > r[i]:
            open_["trend_long"] = {"dir": 1, "e": e, "i": i, "stop": e - 2 * a[i], "tgt": e + 4 * a[i], "risk": 2 * a[i] / e}
        if "trend_short" not in open_ and cd and e < r[i]:
            open_["trend_short"] = {"dir": -1, "e": e, "i": i, "stop": e + 2 * a[i], "tgt": e - 4 * a[i], "risk": 2 * a[i] / e}
        if "dip_long" not in open_ and R[i] < 25 and e < lo[i]:
            open_["dip_long"] = {"dir": 1, "e": e, "i": i, "stop": e - 2 * a[i], "risk": 2 * a[i] / e}
        if "pop_short" not in open_ and R[i] > 75 and e > hi[i]:
            open_["pop_short"] = {"dir": -1, "e": e, "i": i, "stop": e + 2 * a[i], "risk": 2 * a[i] / e}
    return trades

m = Market(); allt = {k: [] for k in ("trend_long", "trend_short", "dip_long", "pop_short")}
for s in SYMS:
    c = m.history(s + "USDT", "4h", 6000)
    for k, v in run(c).items(): allt[k] += v
    print(f"{s}: {len(c)} gyertya ({len(c)*4/24/365:.1f} év)", file=sys.stderr)
names = {"trend_long": "Emelkedésre (trend)", "trend_short": "Esésre (trend)", "dip_long": "Visszapattanásra (túladott)", "pop_short": "Visszaesésre (túlvett)"}
for k, t in allt.items():
    t.sort(); half = len(t) // 2
    def st(x):
        if not x: return "nincs kötés"
        w = [r for _, r in x if r > 0]
        return f"{len(x):4d} kötés | nyerő {len(w)/len(x):.0%} | átlag {sum(r for _, r in x)/len(x):+.3f}R | össz {sum(r for _, r in x):+.1f}R"
    print(f"\n{names[k]}\n  teljes:    {st(t)}\n  1. fele:   {st(t[:half])}\n  2. fele:   {st(t[half:])}")
