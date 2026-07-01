"""Financial Engine — Stage 3 of the canonical pipeline.

Pure function: accepts FinancialStatement domain objects, returns
FinancialMetrics. No I/O, no SQL. StatementSchema (not company.sector)
drives formula selection.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel

from egxpm.persistence.models import FinancialStatement, StatementSchema
from egxpm.shared.exceptions import InsufficientDataError

ENGINE_VERSION = "financial_engine_v1"

# Trend detection looks at the growth deltas between the most recent 4
# periods only (not the entire history), so a long-lived company's trend
# reflects its recent trajectory rather than being smoothed out by years
# of unrelated growth swings.
TREND_LOOKBACK_PERIODS = 4


class GrowthTrend(str, Enum):
    ACCELERATING = "accelerating"
    STABLE = "stable"
    DECELERATING = "decelerating"
    INSUFFICIENT_DATA = "insufficient_data"


class FinancialMetrics(BaseModel):
    company_id: str
    statement_schema: StatementSchema
    period_end: str
    periods_used: int

    revenue_growth: float | None = None
    net_income_growth: float | None = None
    eps_growth: float | None = None

    net_margin: float | None = None
    operating_margin: float | None = None
    return_on_equity: float | None = None
    return_on_assets: float | None = None
    debt_to_equity: float | None = None
    free_cash_flow_margin: float | None = None

    bank_schema_flag: bool = False
    growth_trend: GrowthTrend = GrowthTrend.INSUFFICIENT_DATA


def _top_line(statement: FinancialStatement, schema: StatementSchema) -> float | None:
    if schema == StatementSchema.BANK:
        return statement.net_interest_income
    return statement.revenue


def _safe_div(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator is None or denominator == 0:
        return None
    return numerator / denominator


def _growth_rate(prev: float | None, curr: float | None) -> float | None:
    if prev is None or curr is None or prev == 0:
        return None
    return (curr - prev) / abs(prev)


def calculate_financial_metrics(
    statements: list[FinancialStatement],
    statement_schema: StatementSchema,
) -> FinancialMetrics:
    """Compute financial ratios and growth trend from a company's statements.

    Raises:
        InsufficientDataError: zero statements provided.
        ValueError: statements span multiple companies or multiple period
            types (precondition — mixing quarterly and annual periods would
            make growth rates meaningless).

    Statements need not be pre-sorted; they are sorted by period_end here.
    Requires >= 2 periods for growth rates, >= 4 for trend detection;
    fields are null (not zero) when data is insufficient.
    StatementSchema.BANK: operating_margin = None, bank_schema_flag = True.
    StatementSchema.INSURANCE/HOLDING: treated like INDUSTRIAL for now — a
    documented stub, since claims/combined ratios and segment handling are
    out of scope for v1.
    """
    if not statements:
        raise InsufficientDataError("no financial statements provided")

    company_ids = {s.company_id for s in statements}
    if len(company_ids) > 1:
        raise ValueError(f"statements span multiple companies: {sorted(company_ids)}")

    period_types = {s.period_type for s in statements}
    if len(period_types) > 1:
        raise ValueError(f"statements span multiple period types: {sorted(str(p) for p in period_types)}")

    ordered = sorted(statements, key=lambda s: s.period_end)
    latest = ordered[-1]
    top_lines = [_top_line(s, statement_schema) for s in ordered]

    revenue_growth = None
    net_income_growth = None
    eps_growth = None
    if len(ordered) >= 2:
        revenue_growth = _growth_rate(top_lines[-2], top_lines[-1])
        net_income_growth = _growth_rate(ordered[-2].net_income, ordered[-1].net_income)
        prev_eps = ordered[-2].eps_diluted if ordered[-2].eps_diluted is not None else ordered[-2].eps_basic
        curr_eps = ordered[-1].eps_diluted if ordered[-1].eps_diluted is not None else ordered[-1].eps_basic
        eps_growth = _growth_rate(prev_eps, curr_eps)

    latest_top_line = top_lines[-1]
    bank_schema_flag = statement_schema == StatementSchema.BANK
    net_margin = _safe_div(latest.net_income, latest_top_line)
    operating_margin = None if bank_schema_flag else _safe_div(latest.operating_income, latest_top_line)
    return_on_equity = _safe_div(latest.net_income, latest.total_equity)
    return_on_assets = _safe_div(latest.net_income, latest.total_assets)
    debt_to_equity = _safe_div(latest.total_liabilities, latest.total_equity)
    free_cash_flow_margin = _safe_div(latest.free_cash_flow, latest_top_line)

    growth_trend = GrowthTrend.INSUFFICIENT_DATA
    if len(ordered) >= TREND_LOOKBACK_PERIODS:
        start = len(ordered) - (TREND_LOOKBACK_PERIODS - 1)
        recent_growth_rates = [
            _growth_rate(top_lines[i - 1], top_lines[i]) for i in range(start, len(ordered))
        ]
        if all(g is not None for g in recent_growth_rates):
            g1, g2, g3 = recent_growth_rates
            if g1 < g2 < g3:
                growth_trend = GrowthTrend.ACCELERATING
            elif g1 > g2 > g3:
                growth_trend = GrowthTrend.DECELERATING
            else:
                growth_trend = GrowthTrend.STABLE

    return FinancialMetrics(
        company_id=latest.company_id,
        statement_schema=statement_schema,
        period_end=latest.period_end,
        periods_used=len(ordered),
        revenue_growth=revenue_growth,
        net_income_growth=net_income_growth,
        eps_growth=eps_growth,
        net_margin=net_margin,
        operating_margin=operating_margin,
        return_on_equity=return_on_equity,
        return_on_assets=return_on_assets,
        debt_to_equity=debt_to_equity,
        free_cash_flow_margin=free_cash_flow_margin,
        bank_schema_flag=bank_schema_flag,
        growth_trend=growth_trend,
    )
