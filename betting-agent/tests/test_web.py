"""A webes réteg hálózat nélkül: TippmixPro-rekordok, névegyeztetés, valós esély, munkamenet, gyorsítótár."""
import math
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


# --- célszorzós szelvény valós esély nélkül ---

import target as target_mod  # noqa: E402


def _state(matches):
    return {"competitions": [{"key": "x", "name": "X", "matches": matches}]}


def _m(mid, o1, ox, o2, over=None, under=None):
    mk = [{"key": "1x2", "name": "1X2", "line": None, "outcomes": [
        {"id": f"{mid}1", "pick": "1", "odds": o1}, {"id": f"{mid}X", "pick": "X", "odds": ox},
        {"id": f"{mid}2", "pick": "2", "odds": o2}]},
        {"key": "dc", "name": "Kétesély", "line": None, "outcomes": [{"id": f"{mid}d", "pick": "1X", "odds": 1.2}]},
        {"key": "dnb", "name": "DNB", "line": None, "outcomes": [{"id": f"{mid}n", "pick": "1", "odds": 1.3}]}]
    if over:
        mk.append({"key": "ou", "name": "Gólszám 2,5", "line": 2.5, "outcomes": [
            {"id": f"{mid}o", "pick": "Több", "odds": over}, {"id": f"{mid}u", "pick": "Kevesebb", "odds": under}]})
    return {"id": mid, "home": f"H{mid}", "away": f"A{mid}", "markets": mk}


def test_candidates_devig_own_odds_skip_dnb_and_derive_double_chance():
    cands = target_mod.candidates(_state([_m("a", 2.0, 3.4, 3.8, 1.9, 1.9)]), max_odds=10)
    ids = {c.id for c in cands}
    assert "an" not in ids                      # DNB kimarad
    assert all(c.ratio <= 1.0 + 1e-9 for c in cands)
    assert len([c for c in cands if c.match_id == "a"]) <= target_mod.PER_MATCH


def test_search_hits_target_window_one_leg_per_match():
    ms = [_m(str(i), 1.9 + i * 0.05, 3.5, 4.0, 1.85, 1.95) for i in range(8)]
    cands = target_mod.candidates(_state(ms), max_odds=8 * 1.35)
    found = target_mod.search(cands, 8.0)
    assert found
    for ratio, _, odds, legs in found:
        assert 8.0 <= odds <= 8.0 * 1.35 + 1e-9
        assert len({l.match_id for l in legs}) == len(legs)
        assert ratio == pytest.approx(math.prod(l.ratio for l in legs))
    # a legjobb elöl
    assert found[0][0] == max(f[0] for f in found)
    picked = target_mod.pick_disjoint(found, 3)
    seen = [l.match_id for f in picked for l in f[3]]
    assert len(seen) == len(set(seen))


def test_search_returns_nothing_for_unreachable_target():
    cands = target_mod.candidates(_state([_m("a", 1.5, 4.0, 6.0)]), max_odds=1000)
    assert target_mod.search(cands, 500.0) == []
