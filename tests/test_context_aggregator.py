import pytest

from egxpm.engine.position_sizing_engine import PositionSizing
from egxpm.llm.context_aggregator import HistoricalSummary, build_context
from egxpm.persistence.models import AllocationReport, ConfidenceScore, MarketSummary, Score, SectorSummary


def _score(**overrides):
    defaults = dict(
        company_id="TMGH", composite_score=70.0, financial_score=60.0, technical_score=80.0, news_score=50.0,
        financial_breakdown={
            "revenue_growth": {"value": 0.2, "points": 15, "max": 15},
            "net_margin": {"value": 0.0, "points": 0, "max": 15},
        },
        technical_breakdown={"trend": {"value": "BULLISH", "points": 40, "max": 40}},
        config_snapshot_id="cfg-1", job_id="job-1",
    )
    defaults.update(overrides)
    return Score(**defaults)


def _confidence(**overrides):
    defaults = dict(
        score_id="s-1", confidence_value=0.8, freshness_component=0.9,
        source_quality_component=0.7, source_health_component=0.95, historical_accuracy_component=0.5,
    )
    defaults.update(overrides)
    return ConfidenceScore(**defaults)


def _portfolio():
    return AllocationReport(
        total_value=100_000.0, cash=1000.0, by_stock_pct={"TMGH": 0.12},
        target_deviation={"long_term_stocks": 0.05}, stock_constraint_violations=[],
    )


def _sizing():
    return PositionSizing(
        entry_price=100.0, stop_loss=95.0, take_profit=110.0,
        stop_distance=5.0, position_size=100.0, risk_reward_ratio=2.0, new_risk_egp=500.0,
    )


def test_build_context_basic_shape():
    context = build_context(
        _score(), _confidence(), _portfolio(), _sizing(), HistoricalSummary(),
        SectorSummary(sector="Real Estate", summary_score=55.0, job_id="job-1"),
        MarketSummary(summary_score=50.0, job_id="job-1"),
    )
    assert context.company["company_id"] == "TMGH"
    assert context.score_summary["composite"] == 70.0
    assert context.portfolio_context["current_pct"] == pytest.approx(0.12)
    assert context.market_context["sector_score"] == 55.0
    assert context.market_context["market_score"] == 50.0
    assert context.position_sizing["entry"] == 100.0


def test_key_strengths_and_weaknesses_ranked_by_points_ratio():
    context = build_context(
        _score(), _confidence(), _portfolio(), None, HistoricalSummary(), None, None,
    )
    # revenue_growth (15/15=1.0) and trend (40/40=1.0) are full marks;
    # net_margin (0/15=0.0) is the clear weakness.
    assert "net_margin" in context.score_summary["key_weaknesses"]
    assert "revenue_growth" in context.score_summary["key_strengths"] or "trend" in context.score_summary["key_strengths"]


def test_score_trend_improving():
    context = build_context(
        _score(), _confidence(), _portfolio(), None,
        HistoricalSummary(recent_composite_scores=[50.0, 60.0, 70.0]), None, None,
    )
    assert context.score_summary["score_trend"] == "improving"
    assert context.historical_summary["score_trend_narrative"] == "improving"


def test_score_trend_declining():
    context = build_context(
        _score(), _confidence(), _portfolio(), None,
        HistoricalSummary(recent_composite_scores=[70.0, 60.0, 50.0]), None, None,
    )
    assert context.score_summary["score_trend"] == "declining"


def test_score_trend_insufficient_data_with_fewer_than_two_points():
    context = build_context(
        _score(), _confidence(), _portfolio(), None, HistoricalSummary(recent_composite_scores=[70.0]), None, None,
    )
    assert context.score_summary["score_trend"] == "insufficient_data"


def test_lowest_confidence_component_identified():
    confidence = _confidence(
        freshness_component=0.9, source_quality_component=0.3,
        source_health_component=0.95, historical_accuracy_component=0.5,
    )
    context = build_context(_score(), confidence, _portfolio(), None, HistoricalSummary(), None, None)
    assert context.confidence_summary["lowest_component"] == "source_quality"


def test_missing_sector_and_market_summary_degrades_gracefully():
    context = build_context(_score(), _confidence(), _portfolio(), None, HistoricalSummary(), None, None)
    assert context.market_context["sector_score"] is None
    assert context.market_context["market_score"] is None


def test_missing_position_sizing_is_none():
    context = build_context(_score(), _confidence(), _portfolio(), None, HistoricalSummary(), None, None)
    assert context.position_sizing is None


def test_never_raises_with_minimal_score():
    minimal = Score(company_id="X", config_snapshot_id="cfg-1", job_id="job-1")
    context = build_context(minimal, _confidence(), _portfolio(), None, HistoricalSummary(), None, None)
    assert context.score_summary["key_strengths"] == []
    assert context.score_summary["key_weaknesses"] == []


def test_deterministic():
    args = (_score(), _confidence(), _portfolio(), _sizing(), HistoricalSummary(), None, None)
    c1 = build_context(*args)
    c2 = build_context(*args)
    assert c1 == c2


def test_module_has_no_io_imports():
    import egxpm.llm.context_aggregator as mod
    source = open(mod.__file__).read()
    assert "sqlite3" not in source
    assert "import egxpm.persistence.db" not in source
