"""A webes réteg hálózat nélkül: TippmixPro-rekordok, névegyeztetés, valós esély, munkamenet, gyorsítótár."""
import os
import sys
import time
from datetime import datetime, timedelta, timezone

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import espn  # noqa: E402
import markets  # noqa: E402
import names  # noqa: E402
import odds_api  # noqa: E402
import tippmix  # noqa: E402
import value  # noqa: E402
import web  # noqa: E402
from config import Strategy  # noqa: E402

NOW = datetime(2026, 10, 20, 12, 0, tzinfo=timezone.utc)
KICK = NOW + timedelta(days=2)


def _records(start=KICK, live=False):
    ms = int(start.timestamp() * 1000)
    recs = [{"_type": "MATCH", "id": "M1", "startTime": ms, "statusId": "1",
             "homeParticipantName": "Bayern München", "awayParticipantName": "E. Frankfurt"}]
    offers = [("69", "home", None, 1.40), ("69", "draw", None, 5.0), ("69", "away", None, 7.0),
              ("47", "over", 2.5, 1.5), ("47", "under", 2.5, 2.5), ("47", "over", 2.25, 1.6),
              ("112", "home", None, 1.1), ("76", "yes", None, 1.6)]
    for n, (bt, key, line, odds) in enumerate(offers):
        mid, oid, bid = f"MK{bt}", f"O{n}", f"{900 + n}"
        if not any(r.get("id") == mid for r in recs):
            recs.append({"_type": "MARKET", "id": mid, "eventId": "M1", "bettingTypeId": bt, "eventPartId": "3"})
        recs.append({"_type": "OUTCOME", "id": oid, "eventId": "M1", "headerNameKey": key, "paramFloat1": line})
        recs.append({"_type": "MARKET_OUTCOME_RELATION", "id": f"R{n}", "marketId": mid, "outcomeId": oid})
        recs.append({"_type": "BETTING_OFFER", "id": bid, "outcomeId": oid, "odds": odds, "statusId": "1",
                     "isAvailable": True, "isLive": live})
    # félidős 1X2: nem rendes játékidő, ki kell maradnia
    recs.append({"_type": "MARKET", "id": "HT", "eventId": "M1", "bettingTypeId": "69", "eventPartId": "1"})
    recs.append({"_type": "OUTCOME", "id": "OHT", "eventId": "M1", "headerNameKey": "home"})
    recs.append({"_type": "MARKET_OUTCOME_RELATION", "id": "RHT", "marketId": "HT", "outcomeId": "OHT"})
    recs.append({"_type": "BETTING_OFFER", "id": "999", "outcomeId": "OHT", "odds": 1.9, "statusId": "1"})
    return recs


def test_parse_matches_keeps_regular_time_and_half_lines_only():
    [m] = tippmix.parse_matches(_records(), "bundesliga", now=NOW)
    picks = [(o.market, o.pick, o.line) for o in m.outcomes]
    assert picks == [("1x2", "1", None), ("1x2", "X", None), ("1x2", "2", None), ("ou", "Több", 2.5),
                     ("ou", "Kevesebb", 2.5), ("btts", "Igen", None), ("dnb", "1", None)]
    assert all(o.offer_id != "999" for o in m.outcomes)


def test_parse_matches_drops_started_and_live():
    assert tippmix.parse_matches(_records(start=NOW - timedelta(minutes=1)), "x", now=NOW) == []
    assert tippmix.parse_matches(_records(live=True), "x", now=NOW) == []


def test_find_tournaments_uses_season_agnostic_pattern():
    class FakeSession:
        def dump(self, topic):
            return [{"_type": "TOURNAMENT", "id": "1", "name": "BL 2027/2028"},
                    {"_type": "TOURNAMENT", "id": "2", "name": "BL (speciális) 2027"},
                    {"_type": "TOURNAMENT", "id": "3", "name": "BL, női 2027/2028"}]
    assert tippmix.find_tournaments(FakeSession(), tippmix.BY_KEY["bl"]) == ["1"]


def test_check_slip_parses_forbidden_and_bet_builder():
    class FakeSession:
        def call(self, proc, kw):
            assert kw["type"] == "MULTIPLE"
            return {"success": True, "minStake": 100.0,
                    "forbiddenCombinations": [{"selections": [{"bettingOfferId": "1"}, {"bettingOfferId": "2"}]}],
                    "betBuilder": [{"selections": [{"bettingOfferId": "3"}, {"bettingOfferId": "4"}], "betBuilderOdds": 1.65}]}
    r = tippmix.check_slip(FakeSession(), [("1", 1.5), ("2", 1.2)])
    assert r["forbidden"] == [["1", "2"]] and r["bet_builder"] == [{"ids": ["3", "4"], "odds": 1.65}]
    assert r["min_stake"] == 100.0


# --- nevek ---

@pytest.mark.parametrize("a,b", [("Bayern München", "Bayern Munich"), ("E. Frankfurt", "Eintracht Frankfurt"),
                                 ("1. FC Köln", "FC Cologne"), ("Manchester Utd.", "Manchester United"),
                                 ("Atl. Madrid", "Atlético Madrid"), ("FTC", "Ferencvaros"),
                                 ("Mönchengladbach", "Borussia Mönchengladbach"), ("Olympiakosz", "Olympiacos")])
def test_similar_names(a, b):
    assert names.similarity(a, b) >= 0.6


@pytest.mark.parametrize("a,b", [("Manchester City", "Manchester United"), ("Real Madrid", "Atlético Madrid"),
                                 ("Sporting CP", "Sporting Gijon")])
def test_different_teams_score_lower_than_same(a, b):
    assert names.similarity(a, b) < names.similarity(a, a)


def test_match_events_needs_time_and_both_names():
    t = KICK
    tm = [(t, "Bayern München", "E. Frankfurt"), (t, "Mainz", "Bremen")]
    other = [(t, "Mainz", "Werder Bremen"), (t, "Bayern Munich", "Eintracht Frankfurt"),
             (t + timedelta(hours=3), "Mainz", "Werder Bremen")]
    got = names.match_events(tm, other, lambda x: x, lambda x: x)
    assert got == {0: 1, 1: 0}
    assert names.match_events(tm, [(t + timedelta(hours=1), "Mainz", "Bremen")], lambda x: x, lambda x: x) == {}


# --- valós esély ---

def _analysis():
    m = odds_api.Match(id="x", sport="soccer_germany_bundesliga", kickoff=KICK, home="Bayern Munich",
                       away="Eintracht Frankfurt", h2h={"pinnacle": (1.45, 5.2, 6.8)},
                       totals={"pinnacle": {2.5: (1.55, 2.5)}})
    return markets.analyse(m, Strategy())


def test_pair_and_evaluate_markets():
    [tm] = tippmix.parse_matches(_records(), "bundesliga", now=NOW)
    a = _analysis()
    assert value.pair([tm], [a]) == {"M1": a}
    by = {(o.market, o.pick): o for o in tm.outcomes}
    home = value.evaluate(by[("1x2", "1")], a, Strategy())
    assert home["prob"] == pytest.approx(a.p1x2[0]) and home["source"] == "piaci"
    assert home["ev"] == pytest.approx(a.p1x2[0] * 1.40 - 1)
    assert value.evaluate(by[("btts", "Igen")], a, Strategy())["source"] == "modell"
    dnb = value.evaluate(by[("dnb", "1")], a, Strategy())
    ph, pd, _ = a.p1x2
    assert dnb["ev"] == pytest.approx(ph * 1.1 + pd - 1)
    assert dnb["fair"] == pytest.approx((1 - pd) / ph)


# --- munkamenet, gyorsítótár ---

def test_token_roundtrip_and_password_change(monkeypatch):
    monkeypatch.setenv("APP_PASSWORD", "egy")
    monkeypatch.delenv("APP_SECRET", raising=False)
    tok = web.make_token()
    assert web.valid_token(tok)
    assert not web.valid_token(tok, now=time.time() + 31 * 86400)
    assert not web.valid_token(tok.replace(tok[-1], "0" if tok[-1] != "0" else "1"))
    assert not web.valid_token("szemét")
    monkeypatch.setenv("APP_PASSWORD", "kettő")
    assert not web.valid_token(tok)


def test_cache_single_flight_and_stale_on_error():
    c = web.Cache()
    calls = []

    def ok():
        calls.append(1)
        return "adat"

    assert c.get("k", 60, ok)[0] == "adat"
    assert c.get("k", 60, ok)[0] == "adat" and len(calls) == 1

    def boom():
        raise RuntimeError("le")

    val, _, err = c.get("k", 0, boom)
    assert val == "adat" and isinstance(err, RuntimeError)
    with pytest.raises(RuntimeError):
        c.get("új", 60, boom)


def test_limiter():
    lim = web.Limiter(2, 60)
    assert lim.allow("a") and lim.allow("a") and not lim.allow("a") and lim.allow("b")


def test_espn_results_from_team_perspective():
    data = {"events": [
        {"date": "2026-10-18T13:30Z", "league": {"name": "Bundesliga"}, "competitions": [{
            "status": {"type": {"completed": True}},
            "competitors": [{"homeAway": "home", "team": {"id": "1", "displayName": "A"}, "score": {"displayValue": "0"}},
                            {"homeAway": "away", "team": {"id": "2", "displayName": "B"}, "score": {"displayValue": "2"}}]}]},
        {"date": "2026-10-25T13:30Z", "competitions": [{"status": {"type": {"completed": False}}, "competitors": []}]}]}
    [r] = espn._results(data, "2")
    assert r["result"] == "GY" and not r["is_home"] and r["competition"] == "Bundesliga"
    [r] = espn._results(data, "1")
    assert r["result"] == "V"


def test_open_mode_without_password(monkeypatch):
    monkeypatch.delenv("APP_PASSWORD", raising=False)
    h = web.Handler.__new__(web.Handler)
    h.headers = {}
    assert h._authed()
    monkeypatch.setenv("APP_PASSWORD", "titok")
    assert not h._authed()


def test_forced_refresh_is_throttled():
    lim = web.Limiter(1, 30)
    assert lim.allow("all") and not lim.allow("all")


# --- Fogadásépítős szelvények ---

import builder  # noqa: E402
import poisson  # noqa: E402


def _bmatch(mid, xh, xa, with_btts=True):
    m = poisson.outcome_probs(poisson.score_matrix(xh, xa))
    mk = [{"key": "1x2", "name": "1X2", "line": None, "outcomes": [
        {"id": f"{mid}1", "pick": "1", "odds": 1.5, "label": "Hazai"},
        {"id": f"{mid}X", "pick": "X", "odds": 4.0, "label": "Döntetlen"},
        {"id": f"{mid}2", "pick": "2", "odds": 6.0, "label": "Vendég"}]},
        {"key": "ou", "name": "Gólszám 2,5", "line": 2.5, "outcomes": [
            {"id": f"{mid}o", "pick": "Több", "odds": 1.7, "label": "Több, mint 2,5"},
            {"id": f"{mid}u", "pick": "Kevesebb", "odds": 2.1, "label": "Kevesebb, mint 2,5"}]}]
    if with_btts:
        mk.append({"key": "btts", "name": "Mindkét csapat szerez gólt", "line": None, "outcomes": [
            {"id": f"{mid}y", "pick": "Igen", "odds": 1.8, "label": "Igen"},
            {"id": f"{mid}n", "pick": "Nem", "odds": 1.9, "label": "Nem"}]})
    return {"id": mid, "home": f"H{mid}", "away": f"A{mid}", "kickoff": "2026-10-24T13:30:00+00:00", "markets": mk,
            "analysis": {"p_home": m["home"], "p_draw": m["draw"], "p_away": m["away"], "xg_home": xh, "xg_away": xa}}


def test_joint_prob_matches_marginals_and_is_never_larger():
    mat = poisson.score_matrix(1.8, 0.9)
    m = poisson.outcome_probs(mat)
    assert builder.joint_prob(mat, [("1x2", "1", None)]) == pytest.approx(m["home"])
    both = builder.joint_prob(mat, [("1x2", "1", None), ("ou", "Több", 2.5)])
    assert both <= m["home"] and both <= poisson.over_prob(m["by_total"], 2.5)
    assert builder.joint_prob(mat, [("1x2", "1", None), ("1x2", "2", None)]) == 0


def test_options_pick_favourite_then_most_likely_companions():
    opts = builder.options(_bmatch("a", 2.6, 0.7))
    picks1, p1 = opts["win"]
    assert [p["pick"] for p in picks1] == ["1"]
    picks3, p3 = opts["full"]
    assert [p["market"] for p in picks3] == ["1x2", "ou", "btts"]
    assert p3 <= opts["win_goals"][1] <= p1
    # a harmadik tipp az, amelyik az első kettővel EGYÜTT a legvalószínűbb
    mat = poisson.score_matrix(2.6, 0.7)
    base = [("1x2", "1", None), ("ou", picks3[1]["pick"], 2.5)]
    want = max(("Igen", "Nem"), key=lambda b: builder.joint_prob(mat, base + [("btts", b, None)]))
    assert picks3[2]["pick"] == want
    no_btts = builder.options(_bmatch("b", 1.5, 1.2, with_btts=False))
    assert "full" not in no_btts and "goals" not in no_btts and "win_goals" in no_btts


def test_ranked_and_assemble_respect_target_and_skip_unpriced():
    state = {"competitions": [{"name": "X", "matches": [_bmatch(str(i), 1.5 + i * 0.2, 0.9) for i in range(5)]}]}
    groups = builder.ranked(state, "win_goals")
    assert [g.prob for g in groups] == sorted((g.prob for g in groups), reverse=True)
    for g in groups:
        g.odds = 1.6
    groups[0].odds = None  # a TippmixPro nem árazta
    v = builder.assemble("x", "", groups, 2, None)
    assert len(v.groups) == 2 and groups[0] not in v.groups
    v = builder.assemble("x", "", groups, 2, 4.0)
    assert v.odds >= 4.0 and len(v.groups) == 3
    assert builder.assemble("x", "", groups, 2, 1000.0) is None


def test_assemble_never_uses_the_same_team_twice():
    a = _bmatch("a", 2.4, 0.8)
    b = _bmatch("b", 2.2, 0.8)
    b["home"] = a["home"]  # ugyanaz a csapat egy másik fordulóban
    c = _bmatch("c", 2.0, 0.8)
    state = {"competitions": [{"name": "X", "matches": [a, b, c]}]}
    groups = builder.ranked(state, "win")
    v = builder.assemble("x", "", groups, 3, None)
    teams = [t for g in v.groups for t in g.teams]
    assert len(teams) == len(set(teams)) and len(v.groups) == 2


def test_window_uses_budapest_days():
    def m(mid, iso):
        return {"id": mid, "kickoff": iso}
    state = {"competitions": [{"name": "X", "matches": [
        m("a", "2026-10-21T16:45:00+00:00"),   # szerda 18:45
        m("b", "2026-10-21T22:30:00+00:00"),   # Budapesten már csütörtök 00:30
        m("c", "2026-10-22T19:00:00+00:00"),   # csütörtök
        m("d", "2026-10-24T13:30:00+00:00")]}]}  # szombat
    from datetime import date as d
    one, start, days = web.window(state, None, 1)
    assert start == d(2026, 10, 21) and [x["id"] for x in one["competitions"][0]["matches"]] == ["a"]
    assert days == [d(2026, 10, 21), d(2026, 10, 22), d(2026, 10, 24)]
    two, _, _ = web.window(state, d(2026, 10, 21), 2)
    assert [x["id"] for x in two["competitions"][0]["matches"]] == ["a", "b", "c"]
    sat, _, _ = web.window(state, d(2026, 10, 24), 1)
    assert [x["id"] for x in sat["competitions"][0]["matches"]] == ["d"]
    empty, _, _ = web.window(state, d(2026, 10, 23), 1)
    assert empty["competitions"][0]["matches"] == []


def test_goals_strategy_picks_the_most_likely_pair_without_a_winner():
    match = _bmatch("g", 1.6, 1.4)
    picks, prob = builder.options(match)["goals"]
    assert [p["market"] for p in picks] == ["ou", "btts"]
    mat = poisson.score_matrix(1.6, 1.4)
    best = max(((s, b) for s in ("Több", "Kevesebb") for b in ("Igen", "Nem")),
               key=lambda sb: builder.joint_prob(mat, [("ou", sb[0], 2.5), ("btts", sb[1], None)]))
    assert (picks[0]["pick"], picks[1]["pick"]) == best
    assert prob == pytest.approx(builder.joint_prob(mat, [("ou", best[0], 2.5), ("btts", best[1], None)]))


def test_assemble_skips_near_certain_groups_that_add_no_odds():
    state = {"competitions": [{"name": "X", "matches": [_bmatch(str(i), 1.5 + i * 0.2, 0.9) for i in range(4)]}]}
    groups = builder.ranked(state, "win")
    for g in groups:
        g.odds = 1.5
    groups[0].odds = 1.03
    v = builder.assemble("x", "", groups, 3, None)
    assert groups[0] not in v.groups and all(g.odds >= builder.MIN_GROUP_ODDS for g in v.groups)
