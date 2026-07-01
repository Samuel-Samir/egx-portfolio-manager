"""The ONE implementation of portfolio allocation arithmetic.

Pure function, importable by any layer (Engine, Persistence). No arithmetic
duplication anywhere else in the codebase.
"""

from __future__ import annotations

from egxpm.persistence.models import AllocationReport, ConfigurationSnapshot, Holding


def calculate(
    holdings: list[Holding],
    prices: dict[str, float],
    cash: float,
    targets: ConfigurationSnapshot,
) -> AllocationReport:
    """Compute current allocation, deviation from targets, and constraint violations.

    Raises:
        ValueError: a holding references a company_id missing from `prices`.
    """
    stock_values: dict[str, float] = {}
    category_values: dict[str, float] = {}

    for holding in holdings:
        if holding.company_id not in prices:
            raise ValueError(f"missing price for company_id={holding.company_id!r}")
        value = holding.quantity * prices[holding.company_id]
        stock_values[holding.company_id] = stock_values.get(holding.company_id, 0.0) + value
        category_values[holding.category.value] = (
            category_values.get(holding.category.value, 0.0) + value
        )

    total_value = sum(stock_values.values()) + cash

    by_category_pct = (
        {cat: value / total_value for cat, value in category_values.items()}
        if total_value > 0
        else {cat: 0.0 for cat in category_values}
    )
    by_stock_pct = (
        {company_id: value / total_value for company_id, value in stock_values.items()}
        if total_value > 0
        else {company_id: 0.0 for company_id in stock_values}
    )

    target_deviation = {
        category: by_category_pct.get(category, 0.0) - target_pct
        for category, target_pct in targets.allocation_targets.items()
    }

    max_per_stock_pct = targets.risk_settings.get("max_per_stock_pct")
    stock_constraint_violations = (
        [
            company_id
            for company_id, pct in by_stock_pct.items()
            if pct > max_per_stock_pct
        ]
        if max_per_stock_pct is not None
        else []
    )

    return AllocationReport(
        total_value=total_value,
        cash=cash,
        by_category=category_values,
        by_category_pct=by_category_pct,
        by_stock_pct=by_stock_pct,
        target_deviation=target_deviation,
        stock_constraint_violations=stock_constraint_violations,
    )
