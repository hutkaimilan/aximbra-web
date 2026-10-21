"""Szöglet és lap: TippmixPro-meccsoldal (valódi minta), csapatmodell, névegyeztetés, szelvény-esély."""
import json
import math
import os
import sys
from datetime import datetime
from pathlib import Path

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import builder  # noqa: E402
import footballdata  # noqa: E402
import labels  # noqa: E402
import teamstats  # noqa: E402
import tippmix  # noqa: E402

SAMPLE = Path(__file__).resolve().parent.parent / "sample"


class FakeSession:
    """A mintafájl válaszait adja vissza a meccsoldal két lépésére."""

    def __init__(self, path):
        self.d = json.loads(path.read_text("utf-8"))
        self.topics = []

    def dump(self, topic):
        self.topics.append(topic)
        if topic.endswith("/market-groups"):
            return self.d["market_groups"]
        return self.d["groups"].get(topic.rsplit("/", 1)[1], [])


def _extras(name):
    s = FakeSession(SAMPLE / name)
    now = datetime.fromisoformat(s.d["captured_at"])
    return tippmix.fetch_extras(s, s.d["match_id"], now=now), s


def test_matchday_sample_has_corners_and_cards():
    outs, s = _extras("tippmix_ws_match_bl.json")
    corners = sorted({o.line for o in outs if o.market == "corners"})
    cards = sorted({o.line for o in outs if o.market == "cards"})
    assert corners and min(corners) <= 8.5 and max(corners) >= 11.5
    assert cards and min(cards) <= 3.5 and max(cards) >= 5.5
    # minden vonal x,5, és minden vonalon van Több és Kevesebb is
    for key in ("corners", "cards"):
        by_line = {}
        for o in outs:
            if o.market == key:
                assert o.line % 1 == 0.5
                by_line.setdefault(o.line, set()).add(o.pick)
        assert all(p == {"Több", "Kevesebb"} for p in by_line.values())
    # csak a két extra csoportot kérte le (a többi piaccsoportot nem)
    assert all("Szogletek" in t or "Lapok" in t or t.endswith("/market-groups") for t in s.topics)


def test_corner_prices_fall_as_line_rises():
    outs, _ = _extras("tippmix_ws_match_bl.json")
    over = sorted((o.line, o.odds) for o in outs if o.market == "corners" and o.pick == "Több")
    assert all(a[1] <= b[1] for a, b in zip(over, over[1:]))


def test_two_days_before_no_total_corners():
    outs, _ = _extras("tippmix_ws_match_groups.json")
    assert not [o for o in outs if o.market == "corners"]


def test_fetch_extras_rejects_bad_id():
    with pytest.raises(ValueError):
        tippmix.fetch_extras(FakeSession(SAMPLE / "tippmix_ws_match_bl.json"), "../x")


# --- csapatmodell -------------------------------------------------------------------------------

def _row(h, a, hc, ac, hy=1, ay=2, hr=0, ar=0):
    return {"HomeTeam": h, "AwayTeam": a, "HC": str(hc), "AC": str(ac), "HY": str(hy), "AY": str(ay),
            "HR": str(hr), "AR": str(ar)}


def test_team_model_strong_corner_team_gets_more():
    rows = []
    for _ in range(10):
        rows += [_row("Big", "Small", 9, 2), _row("Small", "Big", 3, 8), _row("Mid", "Mid2", 5, 5),
                 _row("Mid2", "Mid", 5, 5)]
    st = teamstats.build(rows, [])
    eh, ea = st["corners"].expected("Big", "Small")
    assert eh > ea
    assert eh > st["corners"].expected("Mid", "Mid2")[0]
    assert teamstats.build(rows, [])["cards"].expected("Big", "Small") is not None


def test_red_card_counts_as_one_card():
    assert teamstats.actual(_row("A", "B", 1, 1, hy=2, ay=1, hr=1, ar=0), "cards") == 4


def test_missing_columns_are_skipped():
    st = teamstats.build([{"HomeTeam": "A", "AwayTeam": "B", "HC": "", "AC": "3"}], [])
    assert not st["corners"].teams


def test_negative_binomial_sums_to_one_and_matches_poisson_limit():
    for r in (2.0, 18.3, 59.7, 1e7):
        assert math.isclose(sum(teamstats.nb_pmf(k, 10.0, r) for k in range(200)), 1.0, rel_tol=1e-6)
    pois = 1 - sum(math.exp(-10) * 10 ** k / math.factorial(k) for k in range(10))
    assert math.isclose(teamstats.over_prob(10.0, 1e7, 9.5), pois, rel_tol=1e-6)
    # nagyobb szóródás (kisebb r) mellett a várható érték fölötti vonal valószínűbb
    assert teamstats.over_prob(10.0, 5.0, 13.5) > teamstats.over_prob(10.0, 1e7, 13.5)


# --- football-data névegyeztetés -------------------------------------------------------------------

@pytest.fixture()
def fd_stats():
    def lg(teams):
        rows = [_row(h, a, 5, 4) for h in teams for a in teams if h != a]
        return teamstats.build(rows, [])
    return {"E0": lg(["Man United", "Leeds", "Liverpool", "Nott'm Forest"]),
            "SP1": lg(["Ath Madrid", "Celta", "Real Madrid", "Sociedad"]),
            "D1": lg(["Bayern Munich", "Mainz", "M'gladbach", "Ein Frankfurt"]),
            "P1": lg(["Sp Lisbon", "Benfica", "Porto", "Sp Braga"])}


def test_domestic_names_match(fd_stats):
    assert footballdata.find_team(fd_stats, "Manchester Utd.", "pl") == ("E0", "Man United")
    assert footballdata.find_team(fd_stats, "Atl. Madrid", "laliga") == ("SP1", "Ath Madrid")
    assert footballdata.find_team(fd_stats, "Mönchengladbach", "bundesliga") == ("D1", "M'gladbach")
    assert footballdata.find_team(fd_stats, "Sporting", "portugal") == ("P1", "Sp Lisbon")


def test_european_cup_rejects_lookalikes(fd_stats):
    # BL/EL: a négy bajnokságon kívüli csapat nem kaphatja meg a „legközelebbi" nevet
    for name in ("Lens", "Milan", "Celtic"):
        assert footballdata.find_team(fd_stats, name, "cl") is None
    assert footballdata.find_team(fd_stats, "Liverpool", "cl") == ("E0", "Liverpool")


def test_expected_needs_both_teams_from_same_league(fd_stats):
    assert footballdata.expected(fd_stats, "Liverpool", "Benfica", "cl") is None
    assert footballdata.expected(fd_stats, "Celtic", "Liverpool", "cl") is None
    e = footballdata.expected(fd_stats, "Liverpool", "Leeds", "pl")
    assert e and 8 < e["corners"] < 10 and e["cards"] > 0


def test_season_codes_switch_in_july():
    assert footballdata.season_codes(datetime(2026, 10, 21)) == ("2627", "2526")
    assert footballdata.season_codes(datetime(2027, 3, 1)) == ("2627", "2526")
    assert footballdata.season_codes(datetime(2027, 7, 1)) == ("2728", "2627")


# --- szelvény ------------------------------------------------------------------------------------

def _match(analysis, lines=(8.5, 9.5, 10.5)):
    outs = []
    for ln in lines:
        outs.append({"key": "corners", "name": f"Szögletszám {ln}", "line": ln, "outcomes": [
            {"id": f"o{ln}", "pick": "Több", "odds": 1.5}, {"id": f"u{ln}", "pick": "Kevesebb", "odds": 2.4}]})
    return {"id": "1", "home": "A", "away": "B", "kickoff": "2026-10-21T19:00:00+00:00",
            "markets": [{"key": "1x2", "name": "1X2", "line": None, "outcomes": [
                {"id": "h", "pick": "1", "odds": 1.8}, {"id": "d", "pick": "X", "odds": 3.6},
                {"id": "a", "pick": "2", "odds": 4.5}]}] + outs,
            "analysis": analysis}


BASE = {"xg_home": 1.6, "xg_away": 1.0, "p_home": 0.5, "p_draw": 0.25, "p_away": 0.25}


def test_single_probs_include_corners_only_with_estimate():
    without = builder.single_probs(_match(dict(BASE)))
    assert not [o for o, _ in without if o["market"] == "corners"]
    with_mu = builder.single_probs(_match({**BASE, "corners_mu": 10.0, "disp_corners": 59.7}))
    corners = {(o["pick"], o["line"]): p for o, p in with_mu if o["market"] == "corners"}
    assert len(corners) == 6
    for ln in (8.5, 9.5, 10.5):
        assert math.isclose(corners[("Több", ln)] + corners[("Kevesebb", ln)], 1.0)
    assert corners[("Több", 8.5)] > corners[("Több", 9.5)] > corners[("Több", 10.5)]


def test_any_strategy_can_pick_corners():
    m = _match({**BASE, "corners_mu": 13.0, "disp_corners": 59.7})
    picks, p = builder._any_option(m, None, None)
    assert picks[0]["market"] == "corners" and picks[0]["pick"] == "Több" and picks[0]["line"] == 8.5
    assert p > 0.85
    # ha a visszamérés nem engedi a szögletet, nem választja
    picks, _ = builder._any_option(m, None, {"1x2"})
    assert picks[0]["market"] == "1x2"


def test_labels_for_corners_and_cards():
    assert labels.short("corners", "Több", "A", "B", 9.5) == "Több, mint 9,5"
    assert labels.sentence("corners", "Több", "A", "B", 9.5) == "Legalább 10 szöglet lesz a meccsen"
    assert labels.sentence("cards", "Kevesebb", "A", "B", 4.5) == "Legfeljebb 4 lap lesz a meccsen"


# --- webréteg ------------------------------------------------------------------------------------

import web  # noqa: E402


def _o(market, line, pick="Több"):
    return tippmix.Outcome(offer_id=f"{market}{line}{pick}", market=market, pick=pick, odds=1.9, line=line)


def test_stat_lines_keep_only_lines_near_expectation():
    outs = [_o("corners", ln) for ln in (5.5, 7.5, 8.5, 9.5, 10.5, 11.5, 14.5)] + \
           [_o("cards", ln) for ln in (1.5, 2.5, 3.5, 4.5, 5.5, 6.5)]
    kept = web._stat_lines(outs, {"corners": 10.0, "cards": 4.0})
    assert sorted(o.line for o in kept if o.market == "corners") == [7.5, 8.5, 9.5, 10.5, 11.5]
    assert sorted(o.line for o in kept if o.market == "cards") == [2.5, 3.5, 4.5, 5.5]
    # becslés nélkül a kínálat középső vonala körül
    kept = web._stat_lines(outs, None)
    assert sorted(o.line for o in kept if o.market == "corners") == [7.5, 8.5, 9.5, 10.5, 11.5]


def test_load_extras_skips_failing_match_and_raises_when_all_fail(monkeypatch):
    class S:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def fetch(_s, mid):
        if mid == "2":
            raise tippmix.TippmixError("hiba")
        return [_o("corners", 9.5)]

    monkeypatch.setattr(tippmix, "Session", S)
    monkeypatch.setattr(tippmix, "fetch_extras", fetch)
    out = web._load_extras(("1", "2", "3"))
    assert set(out) == {"1", "3"}
    with pytest.raises(tippmix.TippmixError):
        web._load_extras(("2",))


def test_extras_only_for_matches_starting_soon(monkeypatch):
    from datetime import timedelta, timezone
    now = datetime.now(timezone.utc)
    mk = lambda i, h: tippmix.TMMatch(id=i, competition="pl", home="A", away="B",  # noqa: E731
                                      kickoff=now + timedelta(hours=h), outcomes=[])
    seen = {}
    monkeypatch.setattr(web, "_load_extras", lambda ids: seen.setdefault("ids", ids) and {"1": [], "9": []})
    monkeypatch.setattr(web, "_background", lambda key, ttl, loader: loader())
    out = web._extras_for({"matches": {"pl": [mk("1", 5), mk("2", 60)]}})
    assert seen["ids"] == ("1",)
    assert set(out) == {"1"}  # a régi listából maradt meccs nem kerül vissza


def test_background_returns_cached_and_loads_once(monkeypatch):
    import threading
    calls, gate = [], threading.Event()

    def loader():
        calls.append(1)
        gate.wait(2)
        return "kész"

    key = ("teszt", "background")
    web.CACHE.drop(key)
    assert web._background(key, 60, loader) is None      # nincs még érték: nem vár
    assert web._background(key, 60, loader) is None      # második kérés nem indít újabb töltést
    gate.set()
    for _ in range(100):
        if web.CACHE.peek(key):
            break
        threading.Event().wait(0.01)
    assert web._background(key, 60, loader) == "kész"
    assert len(calls) == 1
