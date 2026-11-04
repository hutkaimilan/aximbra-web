"""Négy fogadástípus napi gyertyákon a világpiacon (15 év, Yahoo). Díj eszközosztályonként, két időszakra bontva."""
import json, sys, statistics
from collections import defaultdict
sys.path.insert(0, "..")
import strategy
from market import Candle

raw = json.load(open(sys.argv[1]))
COST = {"forex": 0.0002, "index": 0.0004, "commodity": 0.0006, "stock": 0.0006, "crypto": 0.0014}

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

def run(c, cost):
    closes = [x.close for x in c]
    ind = strategy.compute(c); R = rsi(closes); lo, hi = bands(closes)
    f, s, r, a = ind["fast"], ind["slow"], ind["regime"], ind["atr"]
    trades = defaultdict(list); open_ = {}
    for i in range(strategy.MIN_BARS, len(c)):
        bar = c[i]
        for k, p in list(open_.items()):
            d = p["dir"]; out = None
            if d == 1 and bar.low <= p["stop"]: out = min(p["stop"], bar.open)
            elif d == -1 and bar.high >= p["stop"]: out = max(p["stop"], bar.open)
            elif p.get("tgt") and d == 1 and bar.high >= p["tgt"]: out = max(p["tgt"], bar.open)
            elif p.get("tgt") and d == -1 and bar.low <= p["tgt"]: out = min(p["tgt"], bar.open)
            elif k == "trend_long" and f[i] < s[i]: out = bar.close
            elif k == "trend_short" and f[i] > s[i]: out = bar.close
            elif k in ("dip_long", "pop_short") and (i - p["i"] >= 10 or (d == 1 and bar.close > f[i]) or (d == -1 and bar.close < f[i])): out = bar.close
            if out is not None:
                trades[k].append((c[p["i"]].close_time, (d * (out / p["e"] - 1) - 2 * cost) / p["risk"]))
                del open_[k]
        if None in (f[i], s[i], r[i], a[i], R[i], lo[i]) or a[i] <= 0: continue
        e = bar.close
        cu = f[i - 1] <= s[i - 1] and f[i] > s[i]; cd = f[i - 1] >= s[i - 1] and f[i] < s[i]
        if "trend_long" not in open_ and cu and e > r[i]:
            open_["trend_long"] = dict(dir=1, e=e, i=i, stop=e - 2 * a[i], tgt=e + 4 * a[i], risk=2 * a[i] / e)
        if "trend_short" not in open_ and cd and e < r[i]:
            open_["trend_short"] = dict(dir=-1, e=e, i=i, stop=e + 2 * a[i], tgt=e - 4 * a[i], risk=2 * a[i] / e)
        if "dip_long" not in open_ and R[i] < 30 and e < lo[i] and e > r[i]:      # visszapattanás: csak hosszú távú emelkedőben
            open_["dip_long"] = dict(dir=1, e=e, i=i, stop=e - 2 * a[i], risk=2 * a[i] / e)
        if "pop_short" not in open_ and R[i] > 70 and e > hi[i] and e < r[i]:     # visszaesés: csak hosszú távú esőben
            open_["pop_short"] = dict(dir=-1, e=e, i=i, stop=e + 2 * a[i], risk=2 * a[i] / e)
    return trades

res = defaultdict(lambda: defaultdict(list))
for sym, d in raw.items():
    cls = d["cls"]
    if cls == "macro": continue
    rows = [x for x in d["rows"] if None not in x[1:5]]
    c = [Candle(int(t) * 1000, o, h, l, cl, v or 0, int(t) * 1000 + 1) for t, o, h, l, cl, v in rows]
    for k, t in run(c, COST[cls]).items():
        res[cls][k] += t; res["MIND"][k] += t
names = {"trend_long": "Emelkedésre (trend)  ", "trend_short": "Esésre (trend)       ", "dip_long": "Visszapattanásra     ", "pop_short": "Visszaesésre         "}
def st(x):
    if not x: return "–"
    return f"{len(x):4d} db, nyerő {sum(r > 0 for _, r in x)/len(x):3.0%}, átlag {sum(r for _, r in x)/len(x):+.3f}R"
for cls in ("MIND", "stock", "commodity", "index", "forex", "crypto"):
    print(f"\n=== {cls} ===   (teljes | 2011–2018 | 2019–2026)")
    for k in names:
        t = sorted(res[cls][k]); cut = 1546300800000   # 2019-01-01
        a, b = [x for x in t if x[0] < cut], [x for x in t if x[0] >= cut]
        print(f"  {names[k]} {st(t)}  |  {st(a)}  |  {st(b)}")
