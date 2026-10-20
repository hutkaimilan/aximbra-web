"""Valós esély és várható érték minden TippmixPro-tipphez.

A The Odds API éles irodáinak (Pinnacle, tőzsde) árrésmentesített árából
számolunk (markets.analyse), és a Tippmix-meccshez kezdési idő + csapatnevek
alapján párosítjuk. Ahol nincs pár, ott nincs valós esély — azt a tippet nem
nevezzük értékesnek, akármilyen jónak tűnik a szorzó.
"""
import names
from config import Strategy
from markets import Analysis

LINE = {1.5: "Gólszám 1,5", 2.5: "Gólszám 2,5", 3.5: "Gólszám 3,5"}
SEL_KEY = {
    ("1x2", "1"): ("1X2", "1"), ("1x2", "X"): ("1X2", "X"), ("1x2", "2"): ("1X2", "2"),
    ("dc", "1X"): ("Kétesély", "1X"), ("dc", "X2"): ("Kétesély", "X2"), ("dc", "12"): ("Kétesély", "12"),
    ("btts", "Igen"): ("Mindkét csapat gólt szerez", "Igen"), ("btts", "Nem"): ("Mindkét csapat gólt szerez", "Nem"),
}


def pair(tm_matches: list, analyses: list) -> dict:
    """Tippmix-meccs id → Analysis."""
    idx = names.match_events(tm_matches, analyses,
                             lambda m: (m.kickoff, m.home, m.away),
                             lambda a: (a.match.kickoff, a.match.home, a.match.away))
    return {tm_matches[i].id: analyses[j] for i, j in idx.items()}


def evaluate(outcome, a: Analysis, strategy: Strategy) -> dict | None:
    """{prob, fair, min_odds, ev, value, source} vagy None, ha erre a piacra nincs becslés."""
    if outcome.market == "dnb":
        ph, pd, pa = a.p1x2
        p_win, p_draw = (ph, pd) if outcome.pick == "1" else (pa, pd)
        edge = strategy.min_edge_market + (strategy.low_conf_extra_edge if a.confidence == "alacsony" else 0)
        # Döntetlennél a tét visszajár: EV = p_nyer·o + p_döntetlen − 1
        fair = (1 - p_draw) / p_win
        min_odds = (1 + edge - p_draw) / p_win
        ev = p_win * outcome.odds + p_draw - 1
        return {"prob": p_win / (p_win + (pa if outcome.pick == "1" else ph)), "fair": fair,
                "min_odds": min_odds, "ev": ev, "value": outcome.odds >= min_odds, "source": "piaci"}
    if outcome.market == "ou":
        key = (LINE.get(outcome.line), outcome.pick)
    else:
        key = SEL_KEY.get((outcome.market, outcome.pick))
    sel = next((s for s in a.selections if (s.market, s.pick) == key), None)
    if sel is None:
        return None
    min_odds = sel.min_odds(strategy)
    return {"prob": sel.prob, "fair": sel.fair_odds, "min_odds": min_odds, "ev": sel.prob * outcome.odds - 1,
            "value": outcome.odds >= min_odds, "source": sel.source}
