import pytest
from pydantic import ValidationError

from egxpm.persistence.models import (
    Company,
    ConfidenceScore,
    Holding,
    HoldingCategory,
    Job,
    JobType,
    PortfolioSnapshot,
    PortfolioSnapshotOrigin,
    Recommendation,
    RecommendationAction,
    RiskScore,
    Score,
    StatementSchema,
    WatchlistHistory,
    WatchlistState,
    WatchlistTransitionType,
)


def test_company_defaults():
    company = Company(company_id="COMI", name="CIB", sector="Banking")
    assert company.statement_schema == StatementSchema.INDUSTRIAL
    assert company.listing_status.value == "active"
    assert company.created_at and company.updated_at


def test_company_bank_schema():
    company = Company(
        company_id="COMI", name="CIB", sector="Banking",
        statement_schema=StatementSchema.BANK,
    )
    assert company.statement_schema == StatementSchema.BANK


def test_holding_category_matches_config_keys():
    holding = Holding(
        company_id="PALM", category=HoldingCategory.LONG_TERM_STOCKS,
        quantity=100, average_cost=5.5, acquired_at="2026-01-01",
    )
    assert holding.category.value == "long_term_stocks"
    assert holding.holding_id


def test_holding_rejects_invalid_category():
    with pytest.raises(ValidationError):
        Holding(
            company_id="PALM", category="not_a_category",
            quantity=100, average_cost=5.5, acquired_at="2026-01-01",
        )


def test_watchlist_history_requires_valid_state():
    entry = WatchlistHistory(
        company_id="TMGH", state=WatchlistState.CANDIDATE,
        transition_type=WatchlistTransitionType.CANDIDATE_DISCOVERED,
    )
    assert entry.state == WatchlistState.CANDIDATE
    with pytest.raises(ValidationError):
        WatchlistHistory(
            company_id="TMGH", state="NOT_A_STATE",
            transition_type=WatchlistTransitionType.CANDIDATE_DISCOVERED,
        )


def test_score_defaults_composite_none():
    score = Score(company_id="COMI", config_snapshot_id="cfg-1", job_id="job-1")
    assert score.composite_score is None
    assert score.financial_breakdown == {}


def test_risk_score_requires_value():
    with pytest.raises(ValidationError):
        RiskScore(score_id="s-1")


def test_confidence_score_requires_value():
    with pytest.raises(ValidationError):
        ConfidenceScore(score_id="s-1")


def test_portfolio_snapshot_requires_origin():
    with pytest.raises(ValidationError):
        PortfolioSnapshot()
    snap = PortfolioSnapshot(origin=PortfolioSnapshotOrigin.BEFORE_RECOMMENDATION)
    assert snap.cash == 0.0
    assert snap.holdings_snapshot == []


def test_recommendation_requires_linked_ids():
    with pytest.raises(ValidationError):
        Recommendation(company_id="COMI", action=RecommendationAction.BUY)
    rec = Recommendation(
        company_id="COMI", action=RecommendationAction.BUY,
        confidence_id="c-1", config_snapshot_id="cfg-1",
        portfolio_snapshot_id="p-1", job_id="job-1",
    )
    assert rec.recommendation_id


def test_job_defaults():
    job = Job(job_type=JobType.SWING)
    assert job.status.value == "running"
    assert job.companies_processed == 0
