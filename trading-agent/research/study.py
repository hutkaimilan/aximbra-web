import json, sys, warnings
import numpy as np, pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
warnings.filterwarnings("ignore")

raw = json.load(open(sys.argv[1]))
H = int(sys.argv[2]) if len(sys.argv) > 2 else 5
COST = {"forex": 0.0001, "index": 0.0002, "commodity": 0.0003, "stock": 0.0003, "crypto": 0.001, "macro": 0}

def frame(sym):
    d = pd.DataFrame(raw[sym]["rows"], columns=["t","o","h","l","c","v"])
    d["date"] = pd.to_datetime(d["t"], unit="s").dt.normalize()
    return d.drop_duplicates("date").set_index("date")

px = {s: frame(s) for s in raw}
idx = pd.DatetimeIndex(sorted(set().union(*[set(p.index) for p in px.values()])))
close = pd.DataFrame({s: p["c"] for s, p in px.items()}).reindex(idx).ffill(limit=5)

def ctx():
    out = pd.DataFrame(index=idx)
    out["vix"] = np.log(close["^VIX"])
    out["vix_d5"] = out["vix"].diff(5)
    out["dxy_r5"] = np.log(close["DX-Y.NYB"]).diff(5)
    out["tnx_d5"] = close["^TNX"].diff(5)
    out["spx_r5"] = np.log(close["^GSPC"]).diff(5)
    out["spx_r21"] = np.log(close["^GSPC"]).diff(21)
    return out
C = ctx()

def feats(s):
    p = px[s].reindex(idx).ffill(limit=5)
    c = p["c"]; r = np.log(c).diff()
    vol = r.rolling(21).std()
    f = pd.DataFrame(index=idx)
    for n in (1, 2, 3, 5, 10, 21, 63, 126):
        f[f"r{n}"] = np.log(c).diff(n) / (vol * np.sqrt(n))
    for n in (20, 50, 200):
        f[f"ema{n}"] = (c / c.ewm(span=n, adjust=False).mean() - 1) / vol
    delta = c.diff(); up = delta.clip(lower=0).ewm(alpha=1/14, adjust=False).mean(); dn = (-delta.clip(upper=0)).ewm(alpha=1/14, adjust=False).mean()
    f["rsi"] = 100 - 100 / (1 + up / dn)
    f["vol_ratio"] = r.rolling(10).std() / r.rolling(63).std()
    f["rngpos"] = (c - p["l"].rolling(20).min()) / (p["h"].rolling(20).max() - p["l"].rolling(20).min())
    f["gap"] = (p["o"] / c.shift() - 1) / vol
    f["dow"] = idx.dayofweek
    f = f.join(C)
    f["vol21"] = vol
    f["fwd"] = np.log(c).shift(-H) - np.log(c)          # a jövő: csak célváltozó
    f["fwd1"] = r.shift(-1)                              # következő napi hozam: csak a szimulációhoz
    f["sym"] = s; f["cls"] = raw[s]["cls"]
    return f

rows = pd.concat([feats(s) for s in raw if raw[s]["cls"] != "macro"])
rows = rows.replace([np.inf, -np.inf], np.nan).dropna(subset=["r126", "ema200", "rsi", "vol_ratio", "rngpos", "vix", "spx_r21", "fwd", "fwd1"])
rows = rows[rows.index >= "2012-01-01"]
rows["y"] = (rows["fwd"] > 0).astype(int)
F = [c for c in rows.columns if c not in ("fwd", "fwd1", "sym", "cls", "y", "vol21")]
print(f"minták: {len(rows):,} | eszközök: {rows.sym.nunique()} | horizont: {H} nap | jellemzők: {len(F)}")

years = sorted(set(rows.index.year))
res = []
for yr in years:
    if yr < 2017: continue
    tr = rows[rows.index < f"{yr}-01-01"]
    tr = tr[tr.index < pd.Timestamp(f"{yr}-01-01") - pd.Timedelta(days=H + 2)]   # a célváltozó átlóg a teszt évébe: levágjuk
    te = rows[rows.index.year == yr]
    if len(te) == 0: continue
    m = HistGradientBoostingClassifier(max_depth=3, learning_rate=0.05, max_iter=150, l2_regularization=5.0, min_samples_leaf=200, random_state=0)
    m.fit(tr[F], tr["y"])
    p = m.predict_proba(te[F])[:, 1]
    t = te.copy(); t["p"] = p
    res.append(t)
oos = pd.concat(res)
print(f"kiértékelt (soha nem látott) minták: {len(oos):,}  ({oos.index.min().date()} → {oos.index.max().date()})")
print(f"OOS AUC összesen: {roc_auc_score(oos['y'], oos['p']):.4f}  (0.5 = véletlen)")
print(f"OOS találati arány (p>0.5 → fel): {((oos['p']>0.5)==(oos['y']==1)).mean():.4f} | alaparány (fel napok): {oos['y'].mean():.4f}")
print("\nÉvenként AUC:")
for yr, g in oos.groupby(oos.index.year):
    print(f"  {yr}: {roc_auc_score(g['y'], g['p']):.4f}")
print("\nOsztályonként AUC:")
for cl, g in oos.groupby("cls"):
    print(f"  {cl:10s} {roc_auc_score(g['y'], g['p']):.4f}  (n={len(g):,})")

# szimuláció: minden nap minden eszközre pozíció a jelzés szerint, díjjal; egyenlő súly
def sim(thr, long_short):
    pnl = []
    for s, g in oos.groupby("sym"):
        g = g.sort_index()
        pos = np.where(g["p"] > 0.5 + thr, 1.0, np.where(long_short & (g["p"] < 0.5 - thr), -1.0, 0.0))
        pos = pd.Series(pos, index=g.index)
        turn = pos.diff().abs().fillna(abs(pos.iloc[0]))
        ret = pos * g["fwd1"] - turn * COST[g["cls"].iloc[0]]
        pnl.append(ret.rename(s))
    P = pd.concat(pnl, axis=1)
    return P.mean(axis=1)            # egyenlő súlyú portfólió, aktív eszközök közt
bh = oos.groupby(oos.index)["fwd1"].mean()
def stats(r):
    r = r.dropna(); ann = r.mean() * 252; sd = r.std() * np.sqrt(252)
    eq = (1 + r).cumprod(); dd = (eq / eq.cummax() - 1).min()
    return f"éves hozam {ann*100:+.1f}% | szórás {sd*100:.1f}% | Sharpe {ann/sd if sd else 0:.2f} | max esés {dd*100:.1f}% | összesen {(eq.iloc[-1]-1)*100:+.0f}%"
print("\nSzimuláció (díjakkal, egyenlő súlyú kosár, OOS időszak):")
print("  vedd-meg-és-tartsd :", stats(bh))
for thr in (0.0, 0.03, 0.06):
    print(f"  csak long,  küszöb {thr:.2f}:", stats(sim(thr, False)))
    print(f"  long/short, küszöb {thr:.2f}:", stats(sim(thr, True)))
oos.to_pickle(sys.argv[1].replace(".json", f"_oos{H}.pkl"))
