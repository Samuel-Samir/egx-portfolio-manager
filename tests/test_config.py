import pytest

from egxpm.shared.config import build_configuration_snapshot, load_configuration_snapshot


def test_load_configuration_snapshot_from_real_config_yaml():
    snapshot = load_configuration_snapshot()
    assert snapshot.scoring_weights["financial"] == pytest.approx(0.45)
    assert snapshot.scoring_weights["technical"] == pytest.approx(0.25)
    assert snapshot.scoring_weights["news"] == pytest.approx(0.20)
    assert snapshot.scoring_weights["risk"] == pytest.approx(0.10)
    assert snapshot.risk_settings["max_per_stock_pct"] == pytest.approx(0.15)
    assert snapshot.allocation_targets["long_term_stocks"] == pytest.approx(0.40)


def test_swing_weight_profile_differs_from_longterm():
    longterm = load_configuration_snapshot(weight_profile="longterm_weights")
    swing = load_configuration_snapshot(weight_profile="swing_weights")
    assert longterm.scoring_weights["technical"] != swing.scoring_weights["technical"]
    assert swing.scoring_weights["technical"] == pytest.approx(0.50)


def test_build_configuration_snapshot_resolves_one_profile():
    raw = {
        "longterm_weights": {"financial": 0.45, "technical": 0.25, "news": 0.20, "risk": 0.10},
        "swing_weights": {"financial": 0.20, "technical": 0.50, "news": 0.20, "risk": 0.10},
        "null_handling_policy": "treat_as_zero",
        "max_per_stock_pct": 0.15,
        "allocation_targets": {"long_term_stocks": 0.4},
    }
    snapshot = build_configuration_snapshot(raw, weight_profile="swing_weights")
    assert snapshot.scoring_weights["financial"] == pytest.approx(0.20)
    assert snapshot.scoring_weights["null_handling_policy"] == "treat_as_zero"
    assert snapshot.risk_settings == {"max_per_stock_pct": 0.15}
