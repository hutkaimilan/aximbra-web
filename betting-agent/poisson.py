"""Poisson-gólmodell a piac esélyeihez illesztve.

Nem saját csapaterősséget becslünk — egy góladatokból épített modell a
Pinnacle záró szorzóit hosszú távon nem veri. Ehelyett megkeressük azt a
két gólvárható értéket (hazai λ, vendég λ), amely a piac 1X2 és gólszám
esélyeit a legjobban visszaadja, és ebből számolunk olyan piacokat, amelyeket
nem kértünk le (mindkét csapat gólt szerez, 1,5 / 3,5 gól, pontos eredmény).

Ismert korlát: a független Poisson a 0-0 és 1-1 eredményt kissé alulbecsüli.
Ezért a modellből számolt tippekhez a config nagyobb előnyt követel meg.
"""
import math

MAX_GOALS = 10


def pmf(lam: float) -> list[float]:
    out = [math.exp(-lam)]
    for k in range(1, MAX_GOALS + 1):
        out.append(out[-1] * lam / k)
    return out


def score_matrix(lh: float, la: float) -> list[list[float]]:
    ph, pa = pmf(lh), pmf(la)
    return [[ph[i] * pa[j] for j in range(MAX_GOALS + 1)] for i in range(MAX_GOALS + 1)]


def outcome_probs(m) -> dict:
    n = len(m)
    home = sum(m[i][j] for i in range(n) for j in range(n) if i > j)
    draw = sum(m[i][i] for i in range(n))
    away = sum(m[i][j] for i in range(n) for j in range(n) if i < j)
    btts = sum(m[i][j] for i in range(1, n) for j in range(1, n))
    total = home + draw + away  # a 10 gól fölötti farok miatt kicsit kevesebb 1-nél
    by_total = [0.0] * (2 * n - 1)
    for i in range(n):
        for j in range(n):
            by_total[i + j] += m[i][j]
    return {"home": home / total, "draw": draw / total, "away": away / total,
            "btts": btts / total, "by_total": [x / total for x in by_total]}


def over_prob(by_total: list[float], line: float) -> float:
    return sum(p for g, p in enumerate(by_total) if g > line)


def _loss(lh, la, target_1x2, target_overs):
    # Ugyanaz, mint outcome_probs + over_prob, de a 11×11-es mátrix helyett kumulált összegekkel:
    # az illesztés ezt ezerszer hívja, így tízszer gyorsabb.
    ph, pa = pmf(lh), pmf(la)
    cum_a, acc = [], 0.0
    for x in pa:
        acc += x
        cum_a.append(acc)
    home = sum(ph[i] * cum_a[i - 1] for i in range(1, len(ph)))
    draw = sum(ph[i] * pa[i] for i in range(len(ph)))
    total = sum(ph) * cum_a[-1]
    away = total - home - draw
    err = ((home / total - target_1x2[0]) ** 2 + (draw / total - target_1x2[1]) ** 2
           + (away / total - target_1x2[2]) ** 2)
    for line, p in target_overs.items():
        upto = sum(ph[i] * pa[k - i] for k in range(int(line) + 1) for i in range(k + 1))
        err += ((total - upto) / total - p) ** 2
    return err


def fit(target_1x2, target_overs: dict | None = None) -> tuple[float, float, float]:
    """(hazai λ, vendég λ, legnagyobb eltérés a piactól): durva rács, majd kétszer tízszer finomabb."""
    target_overs = target_overs or {}
    best = None
    lo_h = lo_a = 0.1
    hi_h = hi_a = 4.5
    for step in (0.2, 0.02, 0.002):
        h = lo_h
        while h <= hi_h + 1e-9:
            a = lo_a
            while a <= hi_a + 1e-9:
                e = _loss(h, a, target_1x2, target_overs)
                if best is None or e < best[0]:
                    best = (e, h, a)
                a += step
            h += step
        _, bh, ba = best
        lo_h, hi_h = max(0.05, bh - step), bh + step
        lo_a, hi_a = max(0.05, ba - step), ba + step
    _, lh, la = best
    m = outcome_probs(score_matrix(lh, la))
    diffs = [abs(m["home"] - target_1x2[0]), abs(m["draw"] - target_1x2[1]), abs(m["away"] - target_1x2[2])]
    diffs += [abs(over_prob(m["by_total"], line) - p) for line, p in target_overs.items()]
    return lh, la, max(diffs)


def top_scores(lh: float, la: float, n: int = 5) -> list[tuple[str, float]]:
    m = score_matrix(lh, la)
    cells = [(f"{i}-{j}", m[i][j]) for i in range(len(m)) for j in range(len(m))]
    return sorted(cells, key=lambda c: -c[1])[:n]
