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
