import sys, warnings
import numpy as np, pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import roc_auc_score
warnings.filterwarnings("ignore")
sys.argv = [sys.argv[0], sys.argv[1], "5"]
exec(open("study.py").read().split("years = sorted")[0])    # ugyanaz az adat és jellemzők

# cél: a következő 5 napban az eszköz legalább 1,5 szórásnyit (5 napos skálán) esik
rows["crash"] = (rows["fwd"] < -1.5 * rows["vol21"] * np.sqrt(H)).astype(int)
print(f"zuhanások aránya: {rows['crash'].mean():.3f}")
res = []
for yr in sorted(set(rows.index.year)):
    if yr < 2017: continue
    tr = rows[rows.index < pd.Timestamp(f"{yr}-01-01") - pd.Timedelta(days=H + 2)]
    te = rows[rows.index.year == yr]
    m = HistGradientBoostingClassifier(max_depth=3, learning_rate=0.05, max_iter=150, l2_regularization=5.0, min_samples_leaf=200, random_state=0)
    m.fit(tr[F], tr["crash"])
    t = te.copy(); t["pc"] = m.predict_proba(te[F])[:, 1]; res.append(t)
oos = pd.concat(res)
print(f"OOS AUC (zuhanás-előrejelzés): {roc_auc_score(oos['crash'], oos['pc']):.4f}")
# az egyszerű alapvonal: csak a mostani volatilitás-arány
print(f"alapvonal AUC (csak vol_ratio): {roc_auc_score(oos['crash'], oos['vol_ratio']):.4f}")
top = oos["pc"] > oos["pc"].quantile(0.9)
print(f"a legkockázatosabb 10% napon a zuhanás aránya: {oos.loc[top,'crash'].mean():.3f}  vs. átlag {oos['crash'].mean():.3f}")
print(f"a legkockázatosabb 10% napon az átlagos 5 napos hozam: {oos.loc[top,'fwd'].mean()*100:+.2f}%  vs. a többi napon {oos.loc[~top,'fwd'].mean()*100:+.2f}%")

# védelem: long kosár, de a modell szerinti kockázatos napokon kiszállunk
for cl_name, mask in (("összes", oos["cls"].notna()), ("forex", oos["cls"]=="forex"), ("index", oos["cls"]=="index"), ("részvény", oos["cls"]=="stock"), ("kripto", oos["cls"]=="crypto"), ("nyersanyag", oos["cls"]=="commodity")):
    o = oos[mask]
    out = {}
    for name, q in (("tartás", None), ("védett q80", 0.8), ("védett q90", 0.9)):
        pnl = []
        for s, g in o.groupby("sym"):
            g = g.sort_index()
            pos = pd.Series(1.0, index=g.index) if q is None else (g["pc"] < g["pc"].expanding(250).quantile(q).shift(1).fillna(1)).astype(float)
            turn = pos.diff().abs().fillna(1.0)
            pnl.append((pos * g["fwd1"] - turn * COST[g["cls"].iloc[0]]).rename(s))
        r = pd.concat(pnl, axis=1).mean(axis=1).dropna()
        eq = (1 + r).cumprod(); dd = (eq / eq.cummax() - 1).min(); ann = r.mean() * 252; sd = r.std() * np.sqrt(252)
        out[name] = f"hozam {ann*100:+5.1f}%  Sharpe {ann/sd:4.2f}  max esés {dd*100:6.1f}%"
    print(f"\n[{cl_name}]")
    for k, v in out.items(): print(f"  {k:12s} {v}")
oos.to_pickle(sys.argv[1].replace(".json", "_crash.pkl"))
