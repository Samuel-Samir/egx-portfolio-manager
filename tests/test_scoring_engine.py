import pytest

from egxpm.engine.financial_engine import FinancialMetrics, GrowthTrend
from egxpm.engine.scoring_engine import (
    aggregate_market_summary,
    aggregate_sector_summary,
    assemble_composite_score,
    build_score,
    calculate_score,
)
from egxpm.engine.technical_engine import TechnicalIndicators, TechnicalSignals, TechnicalSnapshotResult
from egxpm.persistence.models import ConfigurationSnapshot, NewsItem, RiskScore, Score, StatementSchema, TrendSignal
from egxpm.shared.exceptions import InsufficientDataError, InvalidWeightsError


def _weights(policy="exclude_and_renormalize", financial=0.45, technical=0.25, news=0.20, risk=0.10):
    return ConfigurationSnapshot(scoring_weights={
        "financial": financial, "technical": technical, "news": news, "risk": risk,
        "null_handling_policy": policy,
    })


def _financial_metrics(**overrides):
    defaults = dict(
        company_id="TMGH", statement_schema=StatementSchema.INDUSTRIAL, period_end="2026-03-31",
        periods_used=4, revenue_growth=0.10, net_income_growth=0.10, eps_growth=0.10,
        net_margin=0.15, operating_margin=0.20, return_on_equity=0.15, return_on_assets=0.08,
        debt_to_equity=0.5, free_cash_flow_margin=0.10, bank_schema_flag=False,
        growth_trend=GrowthTrend.STABLE,
    )
    defaults.update(overrides)
    return FinancialMetrics(**defaults)


def _technical_snapshot(**overrides):
    indicators_defaults = dict(rsi=55.0, macd=1.0, macd_signal=0.5)
    signals_defaults = dict(trend=TrendSignal.BULLISH, breakout=False, unusual_volume=False)
    for key in list(overrides):
        if key in indicators_defaults:
            indicators_defaults[key] = overrides.pop(key)
        elif key in signals_defaults:
            signals_defaults[key] = overrides.pop(key)
    return TechnicalSnapshotResult(
        indicators=TechnicalIndicators(**indicators_defaults),
        signals=TechnicalSignals(**signals_defaults),
        computed_through_date="2026-06-30", window_size=200,
    )


def _news_item(sentiment, relevance):
    return NewsItem(
        headline="x", publisher_name="p", published_at="2026-01-01T00:00:00+00:00",
        sentiment_score=sentiment, relevance_score=relevance,
        data_source_id="mubasher", source_version="1", collection_run_id="r1",
    )


# ------------------------------------------------------------
# calculate_score — valid outputs
# ------------------------------------------------------------

def test_financial_score_full_marks_at_thresholds():
    metrics = _financial_metrics(
        revenue_growth=0.25, net_income_growth=0.25, eps_growth=0.25, net_margin=0.30,
        return_on_equity=0.25, return_on_assets=0.10, debt_to_equity=0.0,
        free_cash_flow_margin=0.20, growth_trend=GrowthTrend.ACCELERATING,
    )
    result = calculate_score(metrics, _technical_snapshot(), [], _weights())
    assert result.financial_score == pytest.approx(100.0)


def test_financial_score_zero_at_worst_case():
    metrics = _financial_metrics(
        revenue_growth=0.0, net_income_growth=0.0, eps_growth=0.0, net_margin=0.0,
        return_on_equity=0.0, return_on_assets=0.0, debt_to_equity=2.0,
        free_cash_flow_margin=0.0, growth_trend=GrowthTrend.DECELERATING,
    )
    result = calculate_score(metrics, _technical_snapshot(), [], _weights())
    # decelerating still earns 1/5 points -> not exactly zero
    assert 0 <= result.financial_score < 5


def test_bank_debt_to_equity_uses_higher_ceiling():
    # D/E of 6.0 would score near-zero on the industrial ceiling (2.0) but
    # should score comfortably on the bank ceiling (12.0).
    bank_metrics = _financial_metrics(statement_schema=StatementSchema.BANK, debt_to_equity=6.0, bank_schema_flag=True)
    industrial_metrics = _financial_metrics(statement_schema=StatementSchema.INDUSTRIAL, debt_to_equity=6.0)
    bank_result = calculate_score(bank_metrics, _technical_snapshot(), [], _weights())
    industrial_result = calculate_score(industrial_metrics, _technical_snapshot(), [], _weights())
    assert bank_result.financial_breakdown["debt_to_equity"]["points"] > industrial_result.financial_breakdown["debt_to_equity"]["points"]


def test_technical_score_bullish_breakout_full_marks():
    snapshot = _technical_snapshot(rsi=55.0, macd=1.0, macd_signal=0.5, trend=TrendSignal.BULLISH,
                                    breakout=True, unusual_volume=True)
    metrics = _financial_metrics()
    result = calculate_score(metrics, snapshot, [], _weights())
    assert result.technical_score == pytest.approx(100.0)


def test_technical_score_bearish_no_signals_low():
    snapshot = _technical_snapshot(rsi=20.0, macd=0.1, macd_signal=0.5, trend=TrendSignal.BEARISH,
                                    breakout=False, unusual_volume=False)
    metrics = _financial_metrics()
    result = calculate_score(metrics, snapshot, [], _weights())
    assert result.technical_score == pytest.approx(0.0)


def test_news_score_positive_sentiment_scores_above_50():
    news = [_news_item(sentiment=0.8, relevance=1.0), _news_item(sentiment=0.6, relevance=0.5)]
    result = calculate_score(_financial_metrics(), _technical_snapshot(), news, _weights())
    assert result.news_score > 50.0


def test_news_score_empty_list_is_null():
    result = calculate_score(_financial_metrics(), _technical_snapshot(), [], _weights())
    assert result.news_score is None
    assert result.news_breakdown == {"item_count": 0}


def test_news_score_zero_relevance_defaults_neutral():
    news = [_news_item(sentiment=0.9, relevance=0.0)]
    result = calculate_score(_financial_metrics(), _technical_snapshot(), news, _weights())
    assert result.news_score == pytest.approx(50.0)


# ------------------------------------------------------------
# Null handling policy
# ------------------------------------------------------------

def test_exclude_and_renormalize_ignores_null_metric():
    metrics = _financial_metrics(revenue_growth=None)
    result = calculate_score(metrics, _technical_snapshot(), [], _weights(policy="exclude_and_renormalize"))
    assert result.financial_breakdown["revenue_growth"]["points"] is None
    # remaining metrics renormalized over a smaller total_max, so a partial
    # profile can still reach 100 if every present metric is at its ceiling
    full_marks = _financial_metrics(
        revenue_growth=None, net_income_growth=0.25, eps_growth=0.25, net_margin=0.30,
        return_on_equity=0.25, return_on_assets=0.10, debt_to_equity=0.0,
        free_cash_flow_margin=0.20, growth_trend=GrowthTrend.ACCELERATING,
    )
    result2 = calculate_score(full_marks, _technical_snapshot(), [], _weights(policy="exclude_and_renormalize"))
    assert result2.financial_score == pytest.approx(100.0)


def test_treat_as_zero_penalizes_null_metric():
    full_marks_missing_revenue = _financial_metrics(
        revenue_growth=None, net_income_growth=0.25, eps_growth=0.25, net_margin=0.30,
        return_on_equity=0.25, return_on_assets=0.10, debt_to_equity=0.0,
        free_cash_flow_margin=0.20, growth_trend=GrowthTrend.ACCELERATING,
    )
    result = calculate_score(full_marks_missing_revenue, _technical_snapshot(), [], _weights(policy="treat_as_zero"))
    # revenue_growth's 15 points are lost entirely under treat_as_zero
    assert result.financial_score == pytest.approx(85.0)


# ------------------------------------------------------------
# InvalidWeightsError
# ------------------------------------------------------------

def test_raises_invalid_weights_error_when_not_summing_to_one():
    bad_weights = _weights(financial=0.5, technical=0.5, news=0.5, risk=0.5)
    with pytest.raises(InvalidWeightsError):
        calculate_score(_financial_metrics(), _technical_snapshot(), [], bad_weights)


def test_raises_invalid_weights_error_when_key_missing():
    weights = ConfigurationSnapshot(scoring_weights={"financial": 0.5, "technical": 0.5})
    with pytest.raises(InvalidWeightsError):
        calculate_score(_financial_metrics(), _technical_snapshot(), [], weights)


# ------------------------------------------------------------
# assemble_composite_score (Stage 6c)
# ------------------------------------------------------------

def test_assemble_composite_score_weighted_combination():
    score = Score(
        company_id="TMGH", financial_score=80.0, technical_score=60.0, news_score=70.0,
        composite_score=None, config_snapshot_id="cfg-1", job_id="job-1",
    )
    risk_score = RiskScore(score_id=score.score_id, value=90.0)
    weights = _weights(financial=0.45, technical=0.25, news=0.20, risk=0.10)
    result = assemble_composite_score(score, risk_score, weights)
    expected = 80.0 * 0.45 + 60.0 * 0.25 + 70.0 * 0.20 + 90.0 * 0.10
    assert result.composite_score == pytest.approx(expected)
    assert result.score_id == score.score_id  # same identity, new composite only


def test_assemble_composite_score_renormalizes_around_null_subscore():
    score = Score(
        company_id="TMGH", financial_score=80.0, technical_score=60.0, news_score=None,
        composite_score=None, config_snapshot_id="cfg-1", job_id="job-1",
    )
    risk_score = RiskScore(score_id=score.score_id, value=90.0)
    weights = _weights(financial=0.45, technical=0.25, news=0.20, risk=0.10)
    result = assemble_composite_score(score, risk_score, weights)
    total_weight = 0.45 + 0.25 + 0.10
    expected = (80.0 * 0.45 + 60.0 * 0.25 + 90.0 * 0.10) / total_weight
    assert result.composite_score == pytest.approx(expected)


def test_assemble_composite_score_does_not_mutate_input():
    score = Score(
        company_id="TMGH", financial_score=80.0, technical_score=60.0, news_score=70.0,
        composite_score=None, config_snapshot_id="cfg-1", job_id="job-1",
    )
    risk_score = RiskScore(score_id=score.score_id, value=90.0)
    assemble_composite_score(score, risk_score, _weights())
    assert score.composite_score is None


# ------------------------------------------------------------
# build_score
# ------------------------------------------------------------

def test_build_score_attaches_orchestration_metadata():
    result = calculate_score(_financial_metrics(), _technical_snapshot(), [], _weights())
    score = build_score(result, company_id="TMGH", config_snapshot_id="cfg-1", job_id="job-1")
    assert score.company_id == "TMGH"
    assert score.config_snapshot_id == "cfg-1"
    assert score.job_id == "job-1"
    assert score.financial_score == result.financial_score


# ------------------------------------------------------------
# Sector / Market aggregation
# ------------------------------------------------------------

def _score_with_composite(company_id, composite):
    return Score(
        company_id=company_id, composite_score=composite, config_snapshot_id="cfg-1", job_id="job-1",
    )


def test_aggregate_sector_summary_averages_composite_scores():
    scores = [_score_with_composite("A", 80.0), _score_with_composite("B", 60.0)]
    summary = aggregate_sector_summary("Banking", scores, job_id="job-1")
    assert summary.summary_score == pytest.approx(70.0)
    assert len(summary.component_company_scores) == 2


def test_aggregate_sector_summary_excludes_null_composites():
    scores = [_score_with_composite("A", 80.0), _score_with_composite("B", None)]
    summary = aggregate_sector_summary("Banking", scores, job_id="job-1")
    assert summary.summary_score == pytest.approx(80.0)
    assert len(summary.component_company_scores) == 1


def test_aggregate_sector_summary_raises_when_no_scores_available():
    with pytest.raises(InsufficientDataError):
        aggregate_sector_summary("Banking", [_score_with_composite("A", None)], job_id="job-1")


def test_aggregate_market_summary_averages_sector_summaries():
    sector_scores = [_score_with_composite("A", 80.0)]
    banking = aggregate_sector_summary("Banking", sector_scores, job_id="job-1")
    real_estate = aggregate_sector_summary("Real Estate", [_score_with_composite("B", 60.0)], job_id="job-1")
    market = aggregate_market_summary([banking, real_estate], job_id="job-1")
    assert market.summary_score == pytest.approx(70.0)


def test_aggregate_market_summary_raises_on_empty_input():
    with pytest.raises(InsufficientDataError):
        aggregate_market_summary([], job_id="job-1")


# ------------------------------------------------------------
# Purity
# ------------------------------------------------------------

def test_calculate_score_is_deterministic():
    metrics, snapshot, news = _financial_metrics(), _technical_snapshot(), [_news_item(0.5, 0.5)]
    r1 = calculate_score(metrics, snapshot, news, _weights())
    r2 = calculate_score(metrics, snapshot, news, _weights())
    assert r1 == r2


def test_module_has_no_io_imports():
    import egxpm.engine.scoring_engine as mod
    source = open(mod.__file__).read()
    assert "sqlite3" not in source
    assert "import egxpm.persistence.db" not in source
