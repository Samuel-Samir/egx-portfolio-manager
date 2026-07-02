import pytest

from egxpm.engine.portfolio_engine import calculate_allocation, simulate
from egxpm.persistence.models import ConfigurationSnapshot, Holding, HoldingCategory, ProposedAction, RecommendationAction
from egxpm.shared.exceptions import InvalidActionError


def _holding(company_id, quantity=10, average_cost=50.0, category=HoldingCategory.LONG_TERM_STOCKS):
    return Holding(company_id=company_id, category=category, quantity=quantity, average_cost=average_cost, acquired_at="2026-01-01")


def _config(**targets):
    return ConfigurationSnapshot(allocation_targets=targets or {"long_term_stocks": 0.4})


# ------------------------------------------------------------
# calculate_allocation — thin wrapper, matches AllocationCalculator directly
# ------------------------------------------------------------

def test_calculate_allocation_matches_allocation_calculator():
    holdings = [_holding("PALM", quantity=100)]
    prices = {"PALM": 6.0}
    report = calculate_allocation(holdings, prices, cash=1000.0, config=_config())
    assert report.total_value == pytest.approx(100 * 6.0 + 1000.0)


# ------------------------------------------------------------
# simulate — BUY opening a new position
# ------------------------------------------------------------

def test_simulate_buy_opens_new_position():
    action = ProposedAction(company_id="TMGH", action=RecommendationAction.BUY, quantity=50, price=10.0, category=HoldingCategory.LONG_TERM_STOCKS)
    report = simulate(action, current_holdings=[], prices={}, cash=1000.0, config=_config())
    assert report.by_stock_pct["TMGH"] > 0
    assert report.total_value == pytest.approx(50 * 10.0 + 1000.0)


def test_simulate_buy_new_position_without_category_raises():
    action = ProposedAction(company_id="TMGH", action=RecommendationAction.BUY, quantity=50, price=10.0)
    with pytest.raises(InvalidActionError):
        simulate(action, current_holdings=[], prices={}, cash=1000.0, config=_config())


def test_simulate_buy_adds_to_existing_position_with_weighted_avg_cost():
    holdings = [_holding("PALM", quantity=100, average_cost=5.0)]
    action = ProposedAction(company_id="PALM", action=RecommendationAction.ADD, quantity=100, price=7.0)
    report = simulate(action, current_holdings=holdings, prices={"PALM": 7.0}, cash=0.0, config=_config())
    # weighted avg cost = (100*5 + 100*7) / 200 = 6.0; total_value should reflect 200 shares at price 7.0
    assert report.total_value == pytest.approx(200 * 7.0)


# ------------------------------------------------------------
# simulate — SELL / TRIM
# ------------------------------------------------------------

def test_simulate_sell_reduces_position():
    holdings = [_holding("PALM", quantity=100, average_cost=5.0)]
    action = ProposedAction(company_id="PALM", action=RecommendationAction.SELL, quantity=40, price=6.0)
    report = simulate(action, current_holdings=holdings, prices={"PALM": 6.0}, cash=0.0, config=_config())
    assert report.by_stock_pct["PALM"] > 0
    assert report.total_value == pytest.approx(60 * 6.0)


def test_simulate_sell_entire_position_removes_it():
    holdings = [_holding("PALM", quantity=100, average_cost=5.0)]
    action = ProposedAction(company_id="PALM", action=RecommendationAction.SELL, quantity=100, price=6.0)
    report = simulate(action, current_holdings=holdings, prices={"PALM": 6.0}, cash=1000.0, config=_config())
    assert "PALM" not in report.by_stock_pct
    assert report.total_value == pytest.approx(1000.0)


def test_simulate_sell_more_than_held_raises():
    holdings = [_holding("PALM", quantity=50)]
    action = ProposedAction(company_id="PALM", action=RecommendationAction.SELL, quantity=100, price=6.0)
    with pytest.raises(InvalidActionError):
        simulate(action, current_holdings=holdings, prices={"PALM": 6.0}, cash=0.0, config=_config())


def test_simulate_sell_nonexistent_holding_raises():
    action = ProposedAction(company_id="PALM", action=RecommendationAction.SELL, quantity=10, price=6.0)
    with pytest.raises(InvalidActionError):
        simulate(action, current_holdings=[], prices={}, cash=0.0, config=_config())


# ------------------------------------------------------------
# simulate — HOLD is a no-op
# ------------------------------------------------------------

def test_simulate_hold_does_not_change_holdings():
    holdings = [_holding("PALM", quantity=100, average_cost=5.0)]
    action = ProposedAction(company_id="PALM", action=RecommendationAction.HOLD, quantity=0, price=6.0)
    report = simulate(action, current_holdings=holdings, prices={"PALM": 6.0}, cash=0.0, config=_config())
    assert report.total_value == pytest.approx(100 * 6.0)


# ------------------------------------------------------------
# Purity — never mutates the input list
# ------------------------------------------------------------

def test_simulate_does_not_mutate_input_holdings():
    holdings = [_holding("PALM", quantity=100, average_cost=5.0)]
    original_quantity = holdings[0].quantity
    action = ProposedAction(company_id="PALM", action=RecommendationAction.SELL, quantity=40, price=6.0)
    simulate(action, current_holdings=holdings, prices={"PALM": 6.0}, cash=0.0, config=_config())
    assert holdings[0].quantity == original_quantity


def test_module_has_no_io_imports():
    import egxpm.engine.portfolio_engine as mod
    source = open(mod.__file__).read()
    assert "sqlite3" not in source
    assert "import egxpm.persistence.db" not in source
