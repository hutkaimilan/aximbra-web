"""Kalibráció hálózat nélkül: isotonic illesztés, mérőszámok, a korrekció csak ott, ahol javít."""
import json
import os
import random
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import builder  # noqa: E402
import calibration  # noqa: E402
import calibrate  # noqa: E402


def test_isotonic_is_monotone_and_recovers_frequencies():
    rnd = random.Random(1)
    # a becslés túl magabiztos: a valós esély p helyett 0,5 + (p − 0,5) · 0,6
    pts = []
    for _ in range(20000):
        p = rnd.random()
        pts.append((p, int(rnd.random() < 0.5 + (p - 0.5) * 0.6)))
    m = calibration.isotonic(pts)
    ys = [y for _, y in m]
    assert ys == sorted(ys)
    assert calibration.apply_map(m, 0.9) == pytest.approx(0.74, abs=0.04)
    assert calibration.apply_map(m, 0.1) == pytest.approx(0.26, abs=0.04)


def test_apply_map_interpolates_and_clamps():
    m = [(0.2, 0.1), (0.6, 0.5)]
    assert calibration.apply_map(m, 0.4) == pytest.approx(0.3)
    assert calibration.apply_map(m, 0.0) == 0.1 and calibration.apply_map(m, 0.99) == 0.5
    assert calibration.apply_map([], 0.37) == 0.37


def test_metrics_on_perfect_and_biased_forecasts():
    perfect = [(0.7, 1)] * 70 + [(0.7, 0)] * 30
    assert calibration.ece(perfect) == pytest.approx(0.0)
    biased = [(0.9, 1)] * 70 + [(0.9, 0)] * 30
    assert calibration.ece(biased) == pytest.approx(0.2)
    assert calibration.brier(perfect) < calibration.brier(biased)


def test_evaluate_uses_map_only_when_it_helps_out_of_sample():
    rnd = random.Random(2)
    good = [(p, int(rnd.random() < p)) for p in (rnd.random() for _ in range(4000))]
    test = [(p, int(rnd.random() < p)) for p in (rnd.random() for _ in range(4000))]
    res = calibration.evaluate(good, test, good + test)
    # a nyers becslés jó: a korrekció legfeljebb zajt adna, ezért a „használt" eltérés a kisebbik
    assert res["ece_used"] == min(res["ece"], res["ece_raw"])
    assert res["ok"] and res["n_test"] == 4000
    few = calibration.evaluate(good[:100], test[:100], good[:200])
    assert not few["ok"]  # kevés mérési adat: nem nevezzük kalibráltnak


def test_calibration_file_missing_changes_nothing(tmp_path):
    c = calibration.Calibration.load(tmp_path / "nincs.json")
    assert not c.available and c.apply("1x2", 0.63) == 0.63 and not c.ok("1x2")


def test_calibration_applies_only_markets_with_use_map(tmp_path):
    path = tmp_path / "c.json"
    path.write_text(json.dumps({"markets": {
        "1x2": {"use_map": True, "ok": True, "map": [[0.2, 0.1], [0.8, 0.7]]},
        "ou": {"use_map": False, "ok": True, "map": [[0.2, 0.1], [0.8, 0.7]]}}}))
    c = calibration.Calibration.load(path)
    assert c.apply("1x2", 0.5) == pytest.approx(0.4)
    assert c.apply("ou", 0.5) == 0.5 and c.ok("ou") and not c.ok("full")


def test_builder_ranked_uses_calibrated_probability():
    from test_web import _bmatch  # a webes tesztek meccsgenerátora
    state = {"competitions": [{"name": "X", "matches": [_bmatch("a", 2.2, 0.9)]}]}
    raw = builder.ranked(state, "win")[0].prob
    seen = []
    cal = builder.ranked(state, "win", cal=lambda k, p: seen.append(k) or p * 0.5)[0].prob
    assert cal == pytest.approx(raw * 0.5) and seen == ["1x2"]


def test_match_events_reproduce_live_pipeline_on_one_row():
    row = {"FTHG": "2", "FTAG": "1", "AvgCH": "1.80", "AvgCD": "3.70", "AvgCA": "4.60",
           "AvgC>2.5": "1.85", "AvgC<2.5": "2.00"}
    ev = calibrate.match_events(row)
    assert [y for _, y in ev["1x2"]] == [1, 0, 0]
    assert sum(p for p, _ in ev["1x2"]) == pytest.approx(1.0)
    assert [y for _, y in ev["ou"]] == [1, 0]
    assert {"win_goals", "goals", "full"} <= set(ev)
    assert calibrate.match_events({"FTHG": "x"}) == {}
