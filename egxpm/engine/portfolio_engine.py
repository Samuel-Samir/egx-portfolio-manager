"""Portfolio Engine — allocation and simulation.

Pure functions wrapping shared/allocation_calculator.calculate(), the one
implementation of allocation arithmetic (Section 12.6). No arithmetic
duplication here — this module only prepares inputs (applying a
hypothetical action for simulate()) and delegates the actual math.

Note on the contract signature: CLAUDE.md's calculate_allocation(holdings,
config) and simulate(proposed_action, current_holdings, config) omit
`prices` and `cash`, but AllocationCalculator.calculate() cannot run
without them (there's no other source for either — Holding doesn't carry
a live price, and cash isn't part of ConfigurationSnapshot). Both are
added as explicit parameters here rather than inventing a non-persisted
"holding with attached price" wrapper type.
"""

from __future__ import annotations

from datetime import datetime, timezone

from egxpm.persistence.models import ConfigurationSnapshot, Holding, ProposedAction, RecommendationAction
from egxpm.shared.allocation_calculator import calculate as calculate_allocation_arithmetic
from egxpm.shared.exceptions import InvalidActionError


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _apply_action(holdings: list[Holding], action: ProposedAction) -> list[Holding]:
    """Applies one ProposedAction to a holdings list, returning a new list
    (never mutates the input). Raises InvalidActionError for an impossible
    action (selling/trimming more than held, or opening a new BUY/ADD
    position with no category to file it under).
    """
    updated = [h.model_copy() for h in holdings]
    existing_index = next((i for i, h in enumerate(updated) if h.company_id == action.company_id), None)
    existing = updated[existing_index] if existing_index is not None else None

    if action.action in (RecommendationAction.BUY, RecommendationAction.ADD):
        if existing is not None:
            total_qty = existing.quantity + action.quantity
            new_avg_cost = (
                existing.quantity * existing.average_cost + action.quantity * action.price
            ) / total_qty
            updated[existing_index] = existing.model_copy(
                update={"quantity": total_qty, "average_cost": new_avg_cost, "updated_at": _now()}
            )
        else:
            if action.category is None:
                raise InvalidActionError(
                    f"cannot open a new position in {action.company_id!r} without a category"
                )
            updated.append(Holding(
                company_id=action.company_id, category=action.category,
                quantity=action.quantity, average_cost=action.price, acquired_at=_now(),
            ))

    elif action.action in (RecommendationAction.SELL, RecommendationAction.TRIM):
        if existing is None or existing.quantity < action.quantity:
            held = existing.quantity if existing is not None else 0.0
            raise InvalidActionError(
                f"cannot sell {action.quantity} shares of {action.company_id!r}; only {held} held"
            )
        remaining = existing.quantity - action.quantity
        if remaining == 0:
            updated.pop(existing_index)
        else:
            updated[existing_index] = existing.model_copy(update={"quantity": remaining, "updated_at": _now()})

    # HOLD: no change.

    return updated


def calculate_allocation(holdings: list[Holding], prices: dict[str, float], cash: float, config: ConfigurationSnapshot):
    """Pure. Calls AllocationCalculator.calculate() internally. No I/O."""
    return calculate_allocation_arithmetic(holdings, prices, cash, config)


def simulate(
    proposed_action: ProposedAction, current_holdings: list[Holding],
    prices: dict[str, float], cash: float, config: ConfigurationSnapshot,
):
    """Pure. Applies proposed_action to current_holdings, then
    AllocationCalculator.calculate(). No I/O.

    Raises:
        InvalidActionError: selling/trimming more than held, or opening a
            new position with no category.
    """
    hypothetical_holdings = _apply_action(current_holdings, proposed_action)
    hypothetical_prices = dict(prices)
    hypothetical_prices.setdefault(proposed_action.company_id, proposed_action.price)
    return calculate_allocation_arithmetic(hypothetical_holdings, hypothetical_prices, cash, config)
