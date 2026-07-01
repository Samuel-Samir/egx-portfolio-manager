import pytest

from egxpm.engine.financial_engine import GrowthTrend, calculate_financial_metrics
from egxpm.persistence.models import FinancialStatement, PeriodType, StatementSchema
from egxpm.shared.exceptions import InsufficientDataError


def _stmt(company_id, period_end, **kwargs):
    defaults = dict(
        company_id=company_id, period_type=PeriodType.QUARTERLY, period_end=period_end,
        data_source_id="stockanalysis", source_version="1", collection_run_id="r1",
    )
    defaults.update(kwargs)
    return FinancialStatement(**defaults)


# ------------------------------------------------------------
# CIB (BANK) — hand-computed values
# ------------------------------------------------------------
# net_interest_income: 100 -> 110 -> 125 -> 145  (growth: 10%, 13.6363%, 16%: accelerating)
# net_income:           50 ->  55 ->  60 ->  70
# eps_diluted:         3.0 -> 3.3 -> 3.6 -> 4.2
# total_assets=2300, total_liabilities=2070, total_equity=230 (latest quarter)
# free_cash_flow=60 (latest quarter)

CIB_STATEMENTS = [
    _stmt("COMI", "2025-03-31", net_interest_income=100, net_income=50, eps_diluted=3.0,
          total_assets=2000, total_liabilities=1800, total_equity=200, free_cash_flow=40),
    _stmt("COMI", "2025-06-30", net_interest_income=110, net_income=55, eps_diluted=3.3,
          total_assets=2100, total_liabilities=1890, total_equity=210, free_cash_flow=45),
    _stmt("COMI", "2025-09-30", net_interest_income=125, net_income=60, eps_diluted=3.6,
          total_assets=2200, total_liabilities=1980, total_equity=220, free_cash_flow=50),
    _stmt("COMI", "2025-12-31", net_interest_income=145, net_income=70, eps_diluted=4.2,
          total_assets=2300, total_liabilities=2070, total_equity=230, free_cash_flow=60),
]


def test_cib_bank_schema_hand_verified_values():
    metrics = calculate_financial_metrics(CIB_STATEMENTS, StatementSchema.BANK)

    assert metrics.bank_schema_flag is True
    assert metrics.operating_margin is None  # BANK: always null, per contract
    assert metrics.periods_used == 4
    assert metrics.period_end == "2025-12-31"

    assert metrics.revenue_growth == pytest.approx(20 / 125)  # (145-125)/125 = 0.16
    assert metrics.net_income_growth == pytest.approx(10 / 60)
    assert metrics.eps_growth == pytest.approx(0.6 / 3.6)
    assert metrics.net_margin == pytest.approx(70 / 145)
    assert metrics.return_on_equity == pytest.approx(70 / 230)
    assert metrics.return_on_assets == pytest.approx(70 / 2300)
    assert metrics.debt_to_equity == pytest.approx(9.0)  # 2070/230
    assert metrics.free_cash_flow_margin == pytest.approx(60 / 145)
    assert metrics.growth_trend == GrowthTrend.ACCELERATING


def test_bank_operating_margin_stays_null_even_if_operating_income_present():
    # Defensive: a data anomaly shouldn't leak an operating_margin for a BANK schema.
    statements = [s.model_copy() for s in CIB_STATEMENTS]
    statements[-1] = statements[-1].model_copy(update={"operating_income": 999})
    metrics = calculate_financial_metrics(statements, StatementSchema.BANK)
    assert metrics.operating_margin is None
    assert metrics.bank_schema_flag is True


# ------------------------------------------------------------
# TMG (INDUSTRIAL) — hand-computed values
# ------------------------------------------------------------
# revenue:  200 -> 220 -> 230 -> 235  (growth: 10%, 4.5454%, 2.1739%: decelerating)
# net_income: 40 -> 42 -> 43 -> 44
# operating_income (latest): 67
# eps_diluted: 1.5 -> 1.6 (last two)
# total_assets=1000, total_liabilities=400, total_equity=600
# free_cash_flow=30

TMG_STATEMENTS = [
    _stmt("TMGH", "2025-03-31", revenue=200, net_income=40, operating_income=60, eps_diluted=1.2,
          total_assets=900, total_liabilities=380, total_equity=520, free_cash_flow=25),
    _stmt("TMGH", "2025-06-30", revenue=220, net_income=42, operating_income=65, eps_diluted=1.3,
          total_assets=950, total_liabilities=390, total_equity=560, free_cash_flow=27),
    _stmt("TMGH", "2025-09-30", revenue=230, net_income=43, operating_income=66, eps_diluted=1.5,
          total_assets=980, total_liabilities=395, total_equity=585, free_cash_flow=29),
    _stmt("TMGH", "2025-12-31", revenue=235, net_income=44, operating_income=67, eps_diluted=1.6,
          total_assets=1000, total_liabilities=400, total_equity=600, free_cash_flow=30),
]


def test_tmg_industrial_schema_hand_verified_values():
    metrics = calculate_financial_metrics(TMG_STATEMENTS, StatementSchema.INDUSTRIAL)

    assert metrics.bank_schema_flag is False
    assert metrics.periods_used == 4

    assert metrics.revenue_growth == pytest.approx(5 / 230)
    assert metrics.net_income_growth == pytest.approx(1 / 43)
    assert metrics.eps_growth == pytest.approx(0.1 / 1.5)
    assert metrics.net_margin == pytest.approx(44 / 235)
    assert metrics.operating_margin == pytest.approx(67 / 235)
    assert metrics.return_on_equity == pytest.approx(44 / 600)
    assert metrics.return_on_assets == pytest.approx(44 / 1000)
    assert metrics.debt_to_equity == pytest.approx(400 / 600)
    assert metrics.free_cash_flow_margin == pytest.approx(30 / 235)
    assert metrics.growth_trend == GrowthTrend.DECELERATING


def test_stable_trend_when_growth_rates_are_not_monotonic():
    statements = [
        _stmt("TMGH", "2025-03-31", revenue=100),
        _stmt("TMGH", "2025-06-30", revenue=105),  # +5%
        _stmt("TMGH", "2025-09-30", revenue=108.15),  # +3%
        _stmt("TMGH", "2025-12-31", revenue=112.476),  # +4%
    ]
    metrics = calculate_financial_metrics(statements, StatementSchema.INDUSTRIAL)
    assert metrics.growth_trend == GrowthTrend.STABLE


# ------------------------------------------------------------
# Insufficient data handling — nulls, not zeros
# ------------------------------------------------------------

def test_raises_insufficient_data_on_empty_list():
    with pytest.raises(InsufficientDataError):
        calculate_financial_metrics([], StatementSchema.INDUSTRIAL)


def test_single_statement_yields_null_growth_but_computed_ratios():
    statements = [_stmt("TMGH", "2025-12-31", revenue=235, net_income=44, operating_income=67,
                         total_assets=1000, total_liabilities=400, total_equity=600)]
    metrics = calculate_financial_metrics(statements, StatementSchema.INDUSTRIAL)
    assert metrics.revenue_growth is None
    assert metrics.net_income_growth is None
    assert metrics.eps_growth is None
    assert metrics.growth_trend == GrowthTrend.INSUFFICIENT_DATA
    assert metrics.net_margin == pytest.approx(44 / 235)
    assert metrics.return_on_equity == pytest.approx(44 / 600)


def test_three_periods_computes_growth_but_not_trend():
    metrics = calculate_financial_metrics(TMG_STATEMENTS[:3], StatementSchema.INDUSTRIAL)
    assert metrics.revenue_growth is not None
    assert metrics.growth_trend == GrowthTrend.INSUFFICIENT_DATA


def test_missing_denominator_yields_null_not_zero_or_crash():
    statements = [
        _stmt("TMGH", "2025-09-30", revenue=100, net_income=10, total_equity=None),
        _stmt("TMGH", "2025-12-31", revenue=110, net_income=11, total_equity=None),
    ]
    metrics = calculate_financial_metrics(statements, StatementSchema.INDUSTRIAL)
    assert metrics.return_on_equity is None
    assert metrics.debt_to_equity is None


def test_zero_denominator_yields_null_not_infinity():
    statements = [
        _stmt("TMGH", "2025-09-30", revenue=0, net_income=10),
        _stmt("TMGH", "2025-12-31", revenue=0, net_income=11),
    ]
    metrics = calculate_financial_metrics(statements, StatementSchema.INDUSTRIAL)
    assert metrics.net_margin is None
    assert metrics.revenue_growth is None  # prev top-line is 0 -> undefined growth


# ------------------------------------------------------------
# Preconditions
# ------------------------------------------------------------

def test_raises_value_error_on_mixed_companies():
    statements = TMG_STATEMENTS[:2] + [
        _stmt("COMI", "2025-09-30", net_interest_income=100, net_income=10)
    ]
    with pytest.raises(ValueError):
        calculate_financial_metrics(statements, StatementSchema.INDUSTRIAL)


def test_raises_value_error_on_mixed_period_types():
    statements = [
        _stmt("TMGH", "2024-12-31", revenue=800, period_type=PeriodType.ANNUAL),
        _stmt("TMGH", "2025-12-31", revenue=235, period_type=PeriodType.QUARTERLY),
    ]
    with pytest.raises(ValueError):
        calculate_financial_metrics(statements, StatementSchema.INDUSTRIAL)


# ------------------------------------------------------------
# Purity / determinism / unordered input
# ------------------------------------------------------------

def test_calculation_is_deterministic_and_pure():
    m1 = calculate_financial_metrics(TMG_STATEMENTS, StatementSchema.INDUSTRIAL)
    m2 = calculate_financial_metrics(TMG_STATEMENTS, StatementSchema.INDUSTRIAL)
    assert m1 == m2


def test_statements_do_not_need_to_be_pre_sorted():
    shuffled = [TMG_STATEMENTS[2], TMG_STATEMENTS[0], TMG_STATEMENTS[3], TMG_STATEMENTS[1]]
    metrics = calculate_financial_metrics(shuffled, StatementSchema.INDUSTRIAL)
    expected = calculate_financial_metrics(TMG_STATEMENTS, StatementSchema.INDUSTRIAL)
    assert metrics == expected


def test_module_has_no_io_imports():
    import egxpm.engine.financial_engine as mod
    source = open(mod.__file__).read()
    assert "sqlite3" not in source
    assert "import egxpm.persistence.db" not in source
