import pytest

from egxpm.engine.risk_engine import (
    CONSERVATIVE_DEFAULT_PENALTY,
    HistoricalScoreSummary,
    LiquiditySummary,
    SectorPeerSummary,
    build_sector_peer_summary,
    calculate_risk_score,
)
from egxpm.persistence.models import ConfigurationSnapshot, Score


def _score(debt_to_equity=1.0, financial_extra=None, technical_extra=None, news_score=50.0):
    financial_breakdown = {"debt_to_equity": {"value": debt_to_equity, "points": 5, "max": 10}}
    if financial_extra:
        financial_breakdown.update(financial_extra)
    technical_breakdown = technical_extra or {"rsi": {"value": 55.0, "points": 20, "max": 20}}
    return Score(
        company_id="TMGH", financial_score=70.0, financial_breakdown=financial_breakdown,
        technical_score=60.0, technical_breakdown=technical_breakdown,
        news_score=news_score, config_snapshot_id="cfg-1", job_id="job-1",
    )


CONFIG = ConfigurationSnapshot(scoring_weights={"financial": 0.45, "technical": 0.25, "news": 0.20, "risk": 0.10})


# ------------------------------------------------------------
# build_sector_peer_summary
# ------------------------------------------------------------

def test_build_sector_peer_summary_computes_median_odd_count():
    summary = build_sector_peer_summary("Banking", [1.0, 2.0, 3.0])
    assert summary.median_debt_to_equity == pytest.approx(2.0)
    assert summary.peer_count == 3


def test_build_sector_peer_summary_computes_median_even_count():
    summary = build_sector_peer_summary("Banking", [1.0, 2.0, 3.0, 4.0])
    assert summary.median_debt_to_equity == pytest.approx(2.5)
    assert summary.peer_count == 4


def test_build_sector_peer_summary_ignores_none_values():
    summary = build_sector_peer_summary("Banking", [1.0, None, 3.0])
    assert summary.peer_count == 2
    assert summary.median_debt_to_equity == pytest.approx(2.0)


def test_build_sector_peer_summary_empty_input():
    summary = build_sector_peer_summary("Banking", [None, None])
    assert summary.peer_count == 0
    assert summary.median_debt_to_equity is None


# ------------------------------------------------------------
# calculate_risk_score — debt_peer component
# ------------------------------------------------------------

def test_debt_at_peer_median_gets_zero_penalty():
    peer_summary = SectorPeerSummary(sector="s", median_debt_to_equity=1.0, peer_count=5)
    risk = calculate_risk_score(
        _score(debt_to_equity=1.0), peer_summary,
        HistoricalScoreSummary(std_dev=0.0), LiquiditySummary(avg_daily_volume_egp=1_000_000, hypothetical_position_size_egp=0),
        CONFIG,
    )
    assert risk.debt_peer_component == pytest.approx(0.0)


def test_debt_at_double_peer_median_gets_full_penalty():
    peer_summary = SectorPeerSummary(sector="s", median_debt_to_equity=1.0, peer_count=5)
    risk = calculate_risk_score(
        _score(debt_to_equity=2.0), peer_summary,
        HistoricalScoreSummary(std_dev=0.0), LiquiditySummary(avg_daily_volume_egp=1_000_000, hypothetical_position_size_egp=0),
        CONFIG,
    )
    assert risk.debt_peer_component == pytest.approx(100.0)


def test_negative_debt_to_equity_gets_maximum_penalty():
    peer_summary = SectorPeerSummary(sector="s", median_debt_to_equity=1.0, peer_count=5)
    risk = calculate_risk_score(
        _score(debt_to_equity=-3.0), peer_summary,
        HistoricalScoreSummary(std_dev=0.0), LiquiditySummary(avg_daily_volume_egp=1_000_000, hypothetical_position_size_egp=0),
        CONFIG,
    )
    assert risk.debt_peer_component == pytest.approx(100.0)


def test_missing_peer_summary_degrades_to_conservative_default():
    peer_summary = SectorPeerSummary(sector="s", median_debt_to_equity=None, peer_count=0)
    risk = calculate_risk_score(
        _score(debt_to_equity=1.0), peer_summary,
        HistoricalScoreSummary(std_dev=0.0), LiquiditySummary(avg_daily_volume_egp=1_000_000, hypothetical_position_size_egp=0),
        CONFIG,
    )
    assert risk.debt_peer_component == pytest.approx(CONSERVATIVE_DEFAULT_PENALTY)


# ------------------------------------------------------------
# score_volatility component
# ------------------------------------------------------------

def test_zero_volatility_gets_zero_penalty():
    peer_summary = SectorPeerSummary(sector="s", median_debt_to_equity=1.0, peer_count=5)
    risk = calculate_risk_score(
        _score(), peer_summary, HistoricalScoreSummary(std_dev=0.0),
        LiquiditySummary(avg_daily_volume_egp=1_000_000, hypothetical_position_size_egp=0), CONFIG,
    )
    assert risk.score_volatility_component == pytest.approx(0.0)


def test_high_volatility_gets_full_penalty():
    peer_summary = SectorPeerSummary(sector="s", median_debt_to_equity=1.0, peer_count=5)
    risk = calculate_risk_score(
        _score(), peer_summary, HistoricalScoreSummary(std_dev=100.0),
        LiquiditySummary(avg_daily_volume_egp=1_000_000, hypothetical_position_size_egp=0), CONFIG,
    )
    assert risk.score_volatility_component == pytest.approx(100.0)


def test_missing_volatility_degrades_to_conservative_default():
    peer_summary = SectorPeerSummary(sector="s", median_debt_to_equity=1.0, peer_count=5)
    risk = calculate_risk_score(
        _score(), peer_summary, HistoricalScoreSummary(std_dev=None),
        LiquiditySummary(avg_daily_volume_egp=1_000_000, hypothetical_position_size_egp=0), CONFIG,
    )
    assert risk.score_volatility_component == pytest.approx(CONSERVATIVE_DEFAULT_PENALTY)


# ------------------------------------------------------------
# data_completeness component
# ------------------------------------------------------------

def test_fully_complete_score_gets_zero_completeness_penalty():
    score = _score(
        financial_extra={"net_margin": {"value": 0.1, "points": 5, "max": 10}},
        technical_extra={"rsi": {"value": 55.0, "points": 20, "max": 20}},
        news_score=60.0,
    )
    peer_summary = SectorPeerSummary(sector="s", median_debt_to_equity=1.0, peer_count=5)
    risk = calculate_risk_score(
        score, peer_summary, HistoricalScoreSummary(std_dev=0.0),
        LiquiditySummary(avg_daily_volume_egp=1_000_000, hypothetical_position_size_egp=0), CONFIG,
    )
    assert risk.data_completeness_component == pytest.approx(0.0)


def test_missing_metrics_and_news_increase_completeness_penalty():
    score = _score(
        financial_extra={"net_margin": {"value": None, "points": None, "max": 10}},
        news_score=None,
    )
    peer_summary = SectorPeerSummary(sector="s", median_debt_to_equity=1.0, peer_count=5)
    risk = calculate_risk_score(
        score, peer_summary, HistoricalScoreSummary(std_dev=0.0),
        LiquiditySummary(avg_daily_volume_egp=1_000_000, hypothetical_position_size_egp=0), CONFIG,
    )
    assert risk.data_completeness_component > 0.0


# ------------------------------------------------------------
# liquidity component
# ------------------------------------------------------------

def test_small_position_relative_to_volume_gets_low_penalty():
    peer_summary = SectorPeerSummary(sector="s", median_debt_to_equity=1.0, peer_count=5)
    risk = calculate_risk_score(
        _score(), peer_summary, HistoricalScoreSummary(std_dev=0.0),
        LiquiditySummary(avg_daily_volume_egp=10_000_000, hypothetical_position_size_egp=10_000), CONFIG,
    )
    assert risk.liquidity_component < 10.0


def test_large_position_relative_to_volume_gets_full_penalty():
    peer_summary = SectorPeerSummary(sector="s", median_debt_to_equity=1.0, peer_count=5)
    risk = calculate_risk_score(
        _score(), peer_summary, HistoricalScoreSummary(std_dev=0.0),
        LiquiditySummary(avg_daily_volume_egp=1_000_000, hypothetical_position_size_egp=1_000_000), CONFIG,
    )
    assert risk.liquidity_component == pytest.approx(100.0)


def test_missing_liquidity_data_degrades_to_conservative_default():
    peer_summary = SectorPeerSummary(sector="s", median_debt_to_equity=1.0, peer_count=5)
    risk = calculate_risk_score(
        _score(), peer_summary, HistoricalScoreSummary(std_dev=0.0),
        LiquiditySummary(avg_daily_volume_egp=None, hypothetical_position_size_egp=None), CONFIG,
    )
    assert risk.liquidity_component == pytest.approx(CONSERVATIVE_DEFAULT_PENALTY)


# ------------------------------------------------------------
# Overall value + never raises
# ------------------------------------------------------------

def test_risk_value_is_100_minus_weighted_penalty():
    peer_summary = SectorPeerSummary(sector="s", median_debt_to_equity=1.0, peer_count=5)
    risk = calculate_risk_score(
        _score(debt_to_equity=1.0), peer_summary, HistoricalScoreSummary(std_dev=0.0),
        LiquiditySummary(avg_daily_volume_egp=1_000_000, hypothetical_position_size_egp=0), CONFIG,
    )
    assert risk.value == pytest.approx(100.0 - risk.breakdown["weighted_risk_penalty"])


def test_risk_value_bounded_0_to_100():
    peer_summary = SectorPeerSummary(sector="s", median_debt_to_equity=1.0, peer_count=5)
    risk = calculate_risk_score(
        _score(debt_to_equity=-999), peer_summary, HistoricalScoreSummary(std_dev=1000.0),
        LiquiditySummary(avg_daily_volume_egp=1.0, hypothetical_position_size_egp=1_000_000), CONFIG,
    )
    assert 0.0 <= risk.value <= 100.0


def test_never_raises_with_all_missing_inputs():
    peer_summary = SectorPeerSummary(sector="s", median_debt_to_equity=None, peer_count=0)
    risk = calculate_risk_score(
        Score(company_id="X", config_snapshot_id="cfg-1", job_id="job-1"),
        peer_summary, HistoricalScoreSummary(std_dev=None),
        LiquiditySummary(avg_daily_volume_egp=None, hypothetical_position_size_egp=None), CONFIG,
    )
    assert 0.0 <= risk.value <= 100.0


def test_deterministic():
    peer_summary = SectorPeerSummary(sector="s", median_debt_to_equity=1.0, peer_count=5)
    args = (_score(), peer_summary, HistoricalScoreSummary(std_dev=5.0),
            LiquiditySummary(avg_daily_volume_egp=1_000_000, hypothetical_position_size_egp=10_000), CONFIG)
    r1 = calculate_risk_score(*args)
    r2 = calculate_risk_score(*args)
    assert r1.value == r2.value
    assert r1.breakdown == r2.breakdown


def test_module_has_no_io_imports():
    import egxpm.engine.risk_engine as mod
    source = open(mod.__file__).read()
    assert "sqlite3" not in source
    assert "import egxpm.persistence.db" not in source
