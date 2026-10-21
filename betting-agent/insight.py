"""Meccselemzés emberi nyelven: ki nyer, hány gól várható, lő-e mindkét csapat.

Forrás: ha van éles piaci ár (Pinnacle, The Odds API), abból; ha nincs, a
TippmixPro saját szorzóiból, árrés nélkül. A gólvárható értéket a Poisson-
modell adja, a piac 1X2 és 2,5-ös gólszám esélyeihez illesztve; a „mindkét
csapat lő gólt" esélyt, ha a TippmixPro kiírja, a saját piacából vesszük.

Az illesztés meccsenként ~20 ms, ezért szorzókészletenként egyszer számoljuk
(a szorzók ritkán változnak): a gyorsítótár kulcsa a meccs és a szorzói.
"""
import threading

import fair
import poisson

_memo: dict = {}
_lock = threading.Lock()
MAX_MEMO = 2000


def _devig(outcomes, picks):
    by = {o.pick: o.odds for o in outcomes}
    if not all(p in by for p in picks):
        return None
    try:
        return dict(zip(picks, fair.devig_power([by[p] for p in picks])))
    except ValueError:
        return None


def from_tippmix(match) -> dict | None:
    """{p_home, p_draw, p_away, xg_home, xg_away, btts, over25, top_scores, source} vagy None."""
    one = [o for o in match.outcomes if o.market == "1x2"]
    ou = [o for o in match.outcomes if o.market == "ou" and o.line == 2.5]
    bt = [o for o in match.outcomes if o.market == "btts"]
    key = (match.id, tuple((o.market, o.pick, o.odds) for o in one + ou + bt))
    with _lock:
        if key in _memo:
            return _memo[key]
    p1x2 = _devig(one, ["1", "X", "2"])
    if not p1x2:
        return None
    pou = _devig(ou, ["Több", "Kevesebb"])
    pbt = _devig(bt, ["Igen", "Nem"])
    target = [p1x2["1"], p1x2["X"], p1x2["2"]]
    lh, la, _ = poisson.fit(target, {2.5: pou["Több"]} if pou else {})
    mp = poisson.outcome_probs(poisson.score_matrix(lh, la))
    res = {
        "p_home": target[0], "p_draw": target[1], "p_away": target[2],
        "xg_home": lh, "xg_away": la,
        "btts": pbt["Igen"] if pbt else mp["btts"],
        "btts_source": "piaci" if pbt else "modell",
        "over25": pou["Több"] if pou else poisson.over_prob(mp["by_total"], 2.5),
        "top_scores": poisson.top_scores(lh, la, 3),
        "source": "a TippmixPro szorzóiból",
    }
    with _lock:
        if len(_memo) >= MAX_MEMO:
            _memo.clear()
        _memo[key] = res
    return res


def from_sharp(a) -> dict:
    """markets.Analysis → ugyanaz a forma, éles piaci forrásból."""
    ph, pd, pa = a.p1x2
    over = a.totals.get(2.5, (None,))[0]
    mp = poisson.outcome_probs(poisson.score_matrix(a.lam_home, a.lam_away))
    return {"p_home": ph, "p_draw": pd, "p_away": pa, "xg_home": a.lam_home, "xg_away": a.lam_away,
            "btts": a.btts, "over25": over if over is not None else poisson.over_prob(mp["by_total"], 2.5),
            "top_scores": a.top_scores[:3], "source": ", ".join(a.sources)}
