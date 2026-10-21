"""Az új piacok (hendikep, 1. félidő) a VALÓDI TippmixPro-mintán (sample/tippmix_ws_bundesliga.json)."""
import json
import os
import sys
from datetime import datetime
from pathlib import Path

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import builder  # noqa: E402
import labels  # noqa: E402
import poisson  # noqa: E402
import tippmix  # noqa: E402

SAMPLE = Path(__file__).resolve().parent.parent / "sample" / "tippmix_ws_bundesliga.json"


@pytest.fixture(scope="module")
def matches():
    d = json.loads(SAMPLE.read_text("utf-8"))
    return tippmix.parse_matches(d["records"], "bundesliga", now=datetime.fromisoformat(d["captured_at"]))


def _by(m):
    return {(o.market, o.pick): o for o in m.outcomes}


def test_real_sample_has_all_new_markets(matches):
    assert len(matches) == 18
    for m in matches:
        kinds = {o.market for o in m.outcomes}
        assert {"1x2", "hcp", "ht1x2"} <= kinds


def test_handicap_line_comes_from_home_outcome_not_draw(matches):
    # A mintában a döntetlen kimenetel paramétere mindig +1, a hazai vonal viszont lehet −1 vagy +1.
    lines = {o.line for m in matches for o in m.outcomes if o.market == "hcp"}
    assert lines == {-1.0, 1.0}
    for m in matches:
        hcp = [o for o in m.outcomes if o.market == "hcp"]
        assert len({o.line for o in hcp}) == 1  # mindhárom kimenetel ugyanazt a hazai vonalat kapja


def test_handicap_prices_are_consistent_with_1x2(matches):
    """−1-es hazai vonalnál a hazai győzelem (legalább 2 góllal) drágább, mint a sima hazai győzelem;
    +1-es vonalnál a „hazai nem kap ki" olcsóbb. Ha az előjel felcserélődne, ez megfordulna."""
    for m in matches:
        b = _by(m)
        h = b[("hcp", "1")]
        if h.line == -1.0:
            assert h.odds > b[("1x2", "1")].odds
        else:
            assert h.odds < b[("1x2", "1")].odds


def test_first_half_markets_parse(matches):
    m = matches[0]
    b = _by(m)
    assert b[("htou", "Több")].line == 0.5
    assert {("ht1x2", p) for p in "1X2"} <= set(b)


def test_handicap_condition():
    c = builder._cond
    # hazai −1: legalább 2 góllal kell nyerni; pontosan 1 = döntetlen; különben vendég
    assert c("hcp", "1", -1.0)(3, 1) and not c("hcp", "1", -1.0)(2, 1)
    assert c("hcp", "X", -1.0)(2, 1) and c("hcp", "2", -1.0)(1, 1)
    # hazai +1: nem kaphat ki
    assert c("hcp", "1", 1.0)(1, 1) and c("hcp", "X", 1.0)(0, 1) and c("hcp", "2", 1.0)(0, 2)


def test_handicap_probabilities_sum_to_one():
    mat = poisson.score_matrix(1.7, 1.1)
    for h in (-2.0, -1.0, 1.0, 2.0):
        assert sum(builder.joint_prob(mat, [("hcp", p, h)]) for p in "1X2") == pytest.approx(1.0)


def test_handicap_labels_match_tippmix_wording():
    assert labels.short("hcp", "1", "Como", "Manchester Utd.", -2.0) == "Como (-2)"
    assert labels.short("hcp", "X", "Como", "Manchester Utd.", -2.0) == "Döntetlen - (Manchester Utd. +2)"
    assert labels.short("hcp", "2", "Como", "Manchester Utd.", -2.0) == "Manchester Utd. (+2)"
    assert labels.sentence("hcp", "1", "Como", "MU", -1.0) == "Como legalább 2 góllal nyer"
    assert labels.sentence("hcp", "1", "Como", "MU", 1.0) == "Como nem kap ki"


def test_any_strategy_uses_half_time_matrix_and_min_odds(matches):
    m = matches[0]
    match = {"id": m.id, "home": m.home, "away": m.away, "kickoff": m.kickoff.isoformat(),
             "markets": [{"key": o.market, "name": o.market, "line": o.line,
                          "outcomes": [{"id": o.offer_id, "pick": o.pick, "odds": o.odds}]} for o in m.outcomes],
             "analysis": {"p_home": 0.7, "p_draw": 0.17, "p_away": 0.13, "xg_home": 2.6, "xg_away": 1.0,
                          "xg_ht_home": 1.25, "xg_ht_away": 0.43}}
    probs = dict(((o["market"], o["pick"], o["line"]), p) for o, p in builder.single_probs(match))
    ht = poisson.score_matrix(1.25, 0.43)
    assert probs[("htou", "Több", 0.5)] == pytest.approx(builder.joint_prob(ht, [("ou", "Több", 0.5)]))
    picks, p = builder._any_option(match, None, None)
    assert picks[0]["odds"] >= builder.ANY_MIN_ODDS
    assert all(q <= p + 1e-12 for (mk, pk, ln), q in probs.items()
               if next(o for o in builder._outcomes(match).values()
                       if (o["market"], o["pick"], o["line"]) == (mk, pk, ln))["odds"] >= builder.ANY_MIN_ODDS)
    only = builder._any_option(match, None, {"1x2"})
    assert only[0][0]["market"] == "1x2"
