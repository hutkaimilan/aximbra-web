"""A fogadáskészítő hálózat nélkül: árrés, gólmodell, tét, TippmixPro-korlátok, táblázat."""
import csv
import json
import math
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import agent  # noqa: E402
import fair  # noqa: E402
import markets  # noqa: E402
import odds_api  # noqa: E402
import poisson  # noqa: E402
import sheet  # noqa: E402
import slip  # noqa: E402
from config import Rules, Strategy  # noqa: E402

HERE = Path(__file__).resolve().parent.parent
NOW = datetime(2026, 10, 20, 12, 0, tzinfo=timezone.utc)
R, S = Rules(), Strategy()


def leg(i, p, o, match=None, kotes=1, min_odds=0.0):
    return slip.Leg(id=f"l{i}", match_id=match or f"m{i}", match=f"Meccs {i}", label="1X2: 1",
                    prob=p, odds=o, kotes=kotes, min_odds=min_odds)


# --- árrés ---

def test_devig_sums_to_one_and_removes_margin():
    odds = [1.80, 3.80, 4.60]
    assert fair.overround(odds) > 0.03
    for f in (fair.devig_power, fair.devig_multiplicative):
        p = f(odds)
        assert math.isclose(sum(p), 1, abs_tol=1e-9)
        assert all(pi < 1 / o for pi, o in zip(p, odds)) or f is fair.devig_power


def test_power_puts_more_margin_on_longshot():
    odds = [1.25, 6.0, 12.0]
    mult, power = fair.devig_multiplicative(odds), fair.devig_power(odds)
    assert power[0] > mult[0] and power[2] < mult[2]


@pytest.mark.parametrize("bad", [[1.0, 2.0], [0.9, 3.0], ["2", 2.0], [2.0]])
def test_devig_rejects_bad_odds(bad):
    with pytest.raises(ValueError):
        fair.devig_power(bad)


def test_consensus_prefers_pinnacle_then_sharp_then_median():
    books = {"pinnacle": [0.5, 0.3, 0.2], "unibet_eu": [0.6, 0.2, 0.2]}
    assert fair.consensus(books, ("pinnacle", "betfair_ex_eu"))[1] == "magas"
    p, conf, used = fair.consensus({"betfair_ex_eu": [0.5, 0.3, 0.2], "x": [0.9, 0.05, 0.05]},
                                   ("pinnacle", "betfair_ex_eu"))
    assert conf == "közepes" and used == ["betfair_ex_eu"] and p[0] == pytest.approx(0.5)
    p, conf, _ = fair.consensus({"a": [0.5, 0.3, 0.2], "b": [0.6, 0.2, 0.2], "c": [0.4, 0.3, 0.3]}, ("pinnacle",))
    assert conf == "alacsony" and p[0] == pytest.approx(0.5 / sum([0.5, 0.3, 0.2]))


# --- gólmodell ---

def test_poisson_fit_recovers_lambdas():
    m = poisson.outcome_probs(poisson.score_matrix(1.7, 0.9))
    lh, la, err = poisson.fit([m["home"], m["draw"], m["away"]], {2.5: poisson.over_prob(m["by_total"], 2.5)})
    assert lh == pytest.approx(1.7, abs=0.01) and la == pytest.approx(0.9, abs=0.01) and err < 1e-3


def _match(h2h, totals=None):
    return odds_api.Match(id="ev1", sport="soccer_epl", kickoff=NOW + timedelta(days=1),
                          home="A", away="B", h2h=h2h, totals=totals or {})


def test_double_chance_is_exact_sum_of_1x2():
    a = markets.analyse(_match({"pinnacle": (2.0, 3.6, 3.9)}, {"pinnacle": {2.5: (1.95, 1.95)}}), S)
    sel = {(s.market, s.pick): s for s in a.selections}
    ph, pd, pa = a.p1x2
    assert sel[("Kétesély", "1X")].prob == pytest.approx(ph + pd)
    assert sel[("Gólszám 2,5", "Több")].source == "piaci"
    assert sel[("Gólszám 3,5", "Több")].source == "modell"
    assert sel[("Mindkét csapat gólt szerez", "Igen")].source == "modell"


def test_model_markets_need_more_edge_and_low_confidence_more_still():
    s_mkt = markets.Selection("1X2", "1", 0.5, "piaci", "magas")
    s_mdl = markets.Selection("Mindkét csapat gólt szerez", "Igen", 0.5, "modell", "magas")
    s_low = markets.Selection("1X2", "1", 0.5, "piaci", "alacsony")
    assert s_mkt.min_odds(S) == pytest.approx(2 * 1.03)
    assert s_mdl.min_odds(S) == pytest.approx(2 * 1.06)
    assert s_low.min_odds(S) == pytest.approx(2 * 1.05)


def test_parse_events_skips_quarter_lines_and_missing_draw():
    raw = [{"id": "x", "commence_time": "2026-10-22T19:00:00Z", "home_team": "A", "away_team": "B",
            "bookmakers": [{"key": "pinnacle", "markets": [
                {"key": "h2h", "outcomes": [{"name": "A", "price": 2.1}, {"name": "B", "price": 3.4},
                                            {"name": "Draw", "price": 3.5}]},
                {"key": "totals", "outcomes": [{"name": "Over", "price": 1.9, "point": 2.25},
                                               {"name": "Under", "price": 1.9, "point": 2.25},
                                               {"name": "Over", "price": 2.0, "point": 2.5},
                                               {"name": "Under", "price": 1.85, "point": 2.5}]}]},
                {"key": "williamhill", "markets": [
                    {"key": "h2h", "outcomes": [{"name": "A", "price": 2.0}, {"name": "B", "price": 3.3}]}]}]},
           {"id": "broken"}]
    ms = odds_api.parse_events(raw, "soccer_epl")
    assert len(ms) == 1
    assert ms[0].totals == {"pinnacle": {2.5: (2.0, 1.85)}}
    assert list(ms[0].h2h) == ["pinnacle"]


def test_fetch_uses_cache_and_does_not_pay_twice(tmp_path):
    calls = []

    def getter(url):
        calls.append(url)
        return [], {"x-requests-remaining": "490", "x-requests-last": "2"}

    _, st1 = odds_api.fetch_league("soccer_epl", "TITKOS123", "pinnacle", 3, tmp_path, now=NOW, getter=getter)
    _, st2 = odds_api.fetch_league("soccer_epl", "TITKOS123", "pinnacle", 3, tmp_path,
                                   now=NOW + timedelta(minutes=10), getter=getter)
    assert len(calls) == 1 and "490" in st1 and "gyorsítótár" in st2
    assert "TITKOS123" not in (tmp_path / "soccer_epl.json").read_text()  # a kulcs nem kerül lemezre
    odds_api.fetch_league("soccer_epl", "k", "pinnacle", 3, tmp_path, now=NOW + timedelta(minutes=40), getter=getter)
    assert len(calls) == 2


def test_get_retries_then_gives_up(monkeypatch):
    import urllib.error

    def boom(url, timeout):
        raise urllib.error.URLError("down")

    monkeypatch.setattr(odds_api.urllib.request, "urlopen", boom)
    waits = []
    with pytest.raises(odds_api.OddsApiError):
        odds_api._get("https://x", sleep=waits.append)
    assert waits == [2, 4, 8]


# --- tét és szelvény ---

def test_no_stake_without_edge():
    assert slip.stake_for(0.5, 1.9, 50_000, R, S)[0] == 0


def test_stake_respects_share_payout_and_step():
    stake, _ = slip.stake_for(0.8, 1.5, 10_000_000, R, S)
    assert stake <= R.max_stake and stake % R.stake_step == 0
    stake, _ = slip.stake_for(0.02, 80.0, 10_000_000, R, S)
    assert stake * 80 <= R.max_payout


def test_min_stake_only_when_full_kelly_allows_it():
    # Teljes Kelly 1% → 30 000 Ft-nál 300 Ft, a negyede 75: a 100 Ft-os minimum még belefér.
    stake, note = slip.stake_for(0.34, 3.0, 30_000, R, S)
    assert stake == R.min_stake and "minimális" in note
    # 5 000 Ft-nál a teljes Kelly 50 Ft: a 100 Ft túlfogadás lenne.
    assert slip.stake_for(0.34, 3.0, 5_000, R, S)[0] == 0


def test_qualifies_uses_min_odds_not_bare_ev():
    assert leg(1, 0.5, 2.04, min_odds=2.06).ev > 0
    assert not leg(1, 0.5, 2.04, min_odds=2.06).qualifies
    assert leg(1, 0.5, 2.06, min_odds=2.06).qualifies


def test_singles_skip_events_that_require_combination():
    bets, skipped = slip.singles([leg(1, 0.6, 1.9, kotes=2)], 100_000, R, S)
    assert not bets and "kötés" in skipped[0][1]


def test_combos_one_leg_per_match_and_respect_kotes():
    legs = [leg(1, 0.6, 1.9, match="m1"), leg(2, 0.55, 2.0, match="m1"),
            leg(3, 0.5, 2.2, match="m3", kotes=3), leg(4, 0.7, 1.6, match="m4")]
    for b in slip.combos(legs, 200_000, R, S, top=10):
        assert len({l.match_id for l in b.legs}) == len(b.legs)
        assert all(l.kotes <= len(b.legs) for l in b.legs)
        assert b.ev > 0


def test_two_combos_never_share_a_match():
    legs = [leg(i, 0.6, 1.9, match=f"m{i // 2}") for i in range(12)]
    bets = slip.combos(legs, 1_000_000, R, S, top=5)
    seen = [l.match_id for b in bets for l in b.legs]
    assert len(bets) >= 2 and len(seen) == len(set(seen))


def test_combos_never_include_negative_legs_unless_asked():
    legs = [leg(1, 0.6, 1.9), leg(2, 0.6, 1.9), leg(3, 0.4, 1.8)]
    assert all(l.id != "l3" for b in slip.combos(legs, 100_000, R, S) for l in b.legs)
    neg = slip.combos(legs, 100_000, R, S, target_odds=6.0, allow_negative=True)
    assert neg and neg[0].odds >= 6.0 and "NEGATÍV" in neg[0].note
    assert not slip.combos(legs, 100_000, R, S, target_odds=6.0)


def test_singles_take_one_bet_per_match():
    bets, skipped = slip.singles([leg(1, 0.6, 1.9, match="m"), leg(2, 0.5, 2.2, match="m")], 100_000, R, S)
    assert len(bets) == 1 and "meccsre" in skipped[0][1]


def test_cap_total_keeps_the_best_instead_of_dropping_everything():
    # 40 egyforma fogadás, mindegyik 300 Ft: arányosan mind 100 alá esne, a helyes eredmény ~8 marad.
    bets = [slip.Bet((leg(i, 0.6, 1.9),), 300) for i in range(40)]
    kept, dropped, _ = slip.cap_total(bets, 50_000, R, S)
    assert kept and sum(b.stake for b in kept) <= 2500 and all(b.stake >= R.min_stake for b in kept)
    assert len(kept) + len(dropped) == 40


def test_cap_total_stays_under_daily_cap_and_reports_drops():
    bets = [slip.Bet((leg(i, 0.6, 1.9),), 1000) for i in range(5)] + [slip.Bet((leg(9, 0.3, 4.0),), 200)]
    kept, dropped, note = slip.cap_total(bets, 50_000, R, S)
    assert sum(b.stake for b in kept) <= 50_000 * S.max_daily_share
    assert all(b.stake >= R.min_stake for b in kept)
    assert len(kept) + len(dropped) == len(bets) and note


# --- táblázat és teljes folyamat ---

def _analysis_sheet(tmp_path, generated=NOW):
    m = _match({"pinnacle": (2.0, 3.6, 3.9)}, {"pinnacle": {2.5: (1.95, 1.95)}})
    path = tmp_path / "t.csv"
    sheet.write(path, [markets.analyse(m, S)], {"soccer_epl": "Premier League"}, S, generated)
    return path


def _fill(path, odds_by_pick):
    with path.open(encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f, delimiter=";"))
    for r in rows:
        if (r["piac"], r["tipp"]) in odds_by_pick:
            r["tippmix_szorzo"] = odds_by_pick[(r["piac"], r["tipp"])]
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=sheet.COLUMNS, delimiter=";")
        w.writeheader()
        w.writerows(rows)


def test_sheet_roundtrip_with_decimal_comma(tmp_path):
    path = _analysis_sheet(tmp_path)
    _fill(path, {("1X2", "1"): "2,30", ("1X2", "X"): ""})
    legs, warns = sheet.read(path, now=NOW + timedelta(hours=1))
    assert len(legs) == 1 and legs[0].odds == 2.30 and legs[0].qualifies and not warns


def test_sheet_refuses_stale_analysis_unless_forced(tmp_path):
    path = _analysis_sheet(tmp_path)
    _fill(path, {("1X2", "1"): "2,30"})
    with pytest.raises(sheet.SheetError, match="--regi-is"):
        sheet.read(path, now=NOW + timedelta(hours=7))
    legs, warns = sheet.read(path, now=NOW + timedelta(hours=7), allow_stale=True)
    assert legs and warns


def test_sheet_skips_started_matches_and_rejects_garbage(tmp_path):
    path = _analysis_sheet(tmp_path)
    _fill(path, {("1X2", "1"): "2,30"})
    legs, warns = sheet.read(path, now=NOW + timedelta(days=1, minutes=1), allow_stale=True)
    assert not legs and any("elkezdődött" in w for w in warns)
    _fill(path, {("1X2", "1"): "abc"})
    with pytest.raises(sheet.SheetError, match="nem szám"):
        sheet.read(path, now=NOW)


def test_offline_end_to_end(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(agent, "OUT", tmp_path)
    table = tmp_path / "t.csv"
    assert agent.main(["elemzes", "--offline", str(HERE / "sample" / "odds_sample.json"),
                       "--tabla", str(table)]) == 0
    with table.open(encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f, delimiter=";"))
    assert len({r["meccs_id"] for r in rows}) == len(
        [e for evs in json.loads((HERE / "sample" / "odds_sample.json").read_text()).values() for e in evs])
    # Minden harmadik sorba a min. szorzónál kicsit jobb Tippmix-szorzót írunk.
    for i, r in enumerate(rows):
        if i % 3 == 0:
            r["tippmix_szorzo"] = f"{float(r['min_szorzo'].replace(',', '.')) + 0.05:.2f}".replace(".", ",")
    with table.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=sheet.COLUMNS, delimiter=";")
        w.writeheader()
        w.writerows(rows)
    assert agent.main(["szelveny", "--tabla", str(table), "--keret", "100000"]) == 0
    out = capsys.readouterr().out
    assert "A terv — egyesek" in out and "1. szelvény" in out and "1. kötés" in out
