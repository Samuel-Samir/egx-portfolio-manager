import pytest

from egxpm.persistence.models import ConfigurationSnapshot, Holding, HoldingCategory
from egxpm.shared.allocation_calculator import calculate


def _holding(company_id, category, quantity, price_hint=1.0):
    return Holding(
        company_id=company_id, category=category, quantity=quantity,
        average_cost=price_hint, acquired_at="2026-01-01",
    )


def test_calculate_basic_allocation():
    holdings = [
        _holding("PALM", HoldingCategory.LONG_TERM_STOCKS, 100),
        _holding("COMI", HoldingCategory.LONG_TERM_STOCKS, 10),
    ]
    prices = {"PALM": 6.0, "COMI": 55.0}
    targets = ConfigurationSnapshot(
        allocation_targets={"long_term_stocks": 0.4, "cloud_cash": 0.1},
    )
    report = calculate(holdings, prices, cash=1000.0, targets=targets)

    assert report.total_value == pytest.approx(100 * 6.0 + 10 * 55.0 + 1000.0)
    assert report.by_category["long_term_stocks"] == pytest.approx(600.0 + 550.0)
    assert report.by_stock_pct["PALM"] == pytest.approx(600.0 / report.total_value)
    assert report.target_deviation["cloud_cash"] == pytest.approx(0.0 - 0.1)


def test_calculate_raises_on_missing_price():
    holdings = [_holding("PALM", HoldingCategory.LONG_TERM_STOCKS, 100)]
    targets = ConfigurationSnapshot(allocation_targets={"long_term_stocks": 0.4})
    with pytest.raises(ValueError):
        calculate(holdings, prices={}, cash=0.0, targets=targets)


def test_calculate_flags_stock_constraint_violation():
    holdings = [_holding("PALM", HoldingCategory.LONG_TERM_STOCKS, 1000)]
    prices = {"PALM": 10.0}
    targets = ConfigurationSnapshot(
        allocation_targets={"long_term_stocks": 0.4},
        risk_settings={"max_per_stock_pct": 0.15},
    )
    report = calculate(holdings, prices, cash=0.0, targets=targets)
    assert "PALM" in report.stock_constraint_violations


def test_calculate_no_violation_below_threshold():
    holdings = [_holding("PALM", HoldingCategory.LONG_TERM_STOCKS, 10)]
    prices = {"PALM": 10.0}
    targets = ConfigurationSnapshot(
        allocation_targets={"long_term_stocks": 0.4},
        risk_settings={"max_per_stock_pct": 0.15},
    )
    report = calculate(holdings, prices, cash=10000.0, targets=targets)
    assert report.stock_constraint_violations == []


def test_calculate_zero_total_value_does_not_divide_by_zero():
    holdings = [_holding("PALM", HoldingCategory.LONG_TERM_STOCKS, 0)]
    prices = {"PALM": 10.0}
    targets = ConfigurationSnapshot(allocation_targets={"long_term_stocks": 0.4})
    report = calculate(holdings, prices, cash=0.0, targets=targets)
    assert report.total_value == 0.0
    assert report.by_category_pct["long_term_stocks"] == 0.0
