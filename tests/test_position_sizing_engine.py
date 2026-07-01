import pytest

from egxpm.engine.position_sizing_engine import calculate_position_size
from egxpm.engine.technical_engine import TechnicalIndicators, TechnicalSignals, TechnicalSnapshotResult
from egxpm.persistence.models import AllocationReport, ConfigurationSnapshot, TrendSignal
from egxpm.shared.exceptions import InsufficientVolatilityDataError, PortfolioHeatExceededError


def _snapshot(atr=2.0, latest_close=100.0):
    return TechnicalSnapshotResult(
        indicators=TechnicalIndicators(atr=atr),
        signals=TechnicalSignals(trend=TrendSignal.BULLISH, breakout=False, unusual_volume=False),
        computed_through_date="2026-06-30", window_size=200, latest_close=latest_close,
    )


def _risk_config(**overrides):
    settings = dict(
        atr_multiplier=1.5, risk_reward_ratio=2.0, risk_per_trade_pct=0.01,
        max_position_pct=0.15, max_portfolio_heat_pct=0.06,
    )
    settings.update(overrides)
    return ConfigurationSnapshot(risk_settings=settings)


def _portfolio(total_value=1_000_000.0, open_risk_egp=0.0):
    return AllocationReport(total_value=total_value, cash=0.0, open_risk_egp=open_risk_egp)


# ------------------------------------------------------------
# Hand-verified formula
# ------------------------------------------------------------

def test_hand_verified_formula():
    # ATR=2.0, atr_multiplier=1.5 -> stop_distance=3.0
    # entry=100 -> stop_loss=97, take_profit=100+3*2=106
    # risk_based_size = (1_000_000 * 0.01) / 3.0 = 3333.33...
    # cap_based_size = (1_000_000 * 0.15) / 100 = 1500.0 -> binding cap
    result = calculate_position_size(_snapshot(atr=2.0, latest_close=100.0), _risk_config(), _portfolio())
    assert result.stop_distance == pytest.approx(3.0)
    assert result.stop_loss == pytest.approx(97.0)
    assert result.take_profit == pytest.approx(106.0)
    assert result.position_size == pytest.approx(1500.0)
    assert result.new_risk_egp == pytest.approx(1500.0 * 3.0)


def test_risk_based_size_binds_when_cap_is_generous():
    # A wide-open max_position_pct means risk-based sizing is the binding constraint.
    config = _risk_config(max_position_pct=0.99)
    result = calculate_position_size(_snapshot(atr=2.0, latest_close=100.0), config, _portfolio(total_value=10_000.0))
    risk_based = (10_000.0 * 0.01) / 3.0
    cap_based = (10_000.0 * 0.99) / 100.0
    assert risk_based < cap_based
    assert result.position_size == pytest.approx(risk_based)


# ------------------------------------------------------------
# Exceptions
# ------------------------------------------------------------

def test_raises_insufficient_volatility_when_atr_is_none():
    with pytest.raises(InsufficientVolatilityDataError):
        calculate_position_size(_snapshot(atr=None), _risk_config(), _portfolio())


def test_raises_insufficient_volatility_when_atr_is_zero():
    with pytest.raises(InsufficientVolatilityDataError):
        calculate_position_size(_snapshot(atr=0.0), _risk_config(), _portfolio())


def test_raises_portfolio_heat_exceeded_when_over_limit():
    # max_portfolio_heat_pct=0.06 of 1,000,000 = 60,000; open_risk already at 59,000
    # new_risk = 1500 * 3.0 = 4500 -> 59,000 + 4,500 = 63,500 > 60,000
    with pytest.raises(PortfolioHeatExceededError):
        calculate_position_size(
            _snapshot(atr=2.0, latest_close=100.0), _risk_config(),
            _portfolio(total_value=1_000_000.0, open_risk_egp=59_000.0),
        )


def test_does_not_raise_when_under_heat_limit():
    result = calculate_position_size(
        _snapshot(atr=2.0, latest_close=100.0), _risk_config(),
        _portfolio(total_value=1_000_000.0, open_risk_egp=1000.0),
    )
    assert result.position_size > 0


def test_missing_max_portfolio_heat_pct_skips_check():
    config = _risk_config()
    config.risk_settings.pop("max_portfolio_heat_pct")
    result = calculate_position_size(
        _snapshot(atr=2.0, latest_close=100.0), config,
        _portfolio(total_value=1_000_000.0, open_risk_egp=10_000_000.0),  # would fail if checked
    )
    assert result.position_size > 0


# ------------------------------------------------------------
# Purity / determinism
# ------------------------------------------------------------

def test_deterministic():
    args = (_snapshot(), _risk_config(), _portfolio())
    r1 = calculate_position_size(*args)
    r2 = calculate_position_size(*args)
    assert r1 == r2


def test_module_has_no_io_imports():
    import egxpm.engine.position_sizing_engine as mod
    source = open(mod.__file__).read()
    assert "sqlite3" not in source
    assert "import egxpm.persistence.db" not in source
