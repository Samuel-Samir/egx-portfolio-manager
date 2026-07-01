import sqlite3

import pytest

from egxpm.persistence.company_repository import CompanyRepository
from egxpm.persistence.conversation_repository import ConversationRepository
from egxpm.persistence.dashboard_read_repository import DashboardReadRepository
from egxpm.persistence.models import (
    AnalysisSession,
    CollectionRun,
    ConfidenceScore,
    ConfigurationSnapshot,
    Conversation,
    CorporateAction,
    Execution,
    FinancialStatement,
    Holding,
    HoldingCategory,
    Job,
    JobType,
    NewsItem,
    Outcome,
    PeriodType,
    PortfolioSnapshot,
    PortfolioSnapshotOrigin,
    PriceCandle,
    Recommendation,
    RecommendationAction,
    RecommendationSupersession,
    RiskScore,
    RunStatus,
    Score,
    SectorSummary,
    MarketSummary,
    TechnicalReferenceSnapshot,
    TechnicalSnapshot,
    UserFeedback,
    WatchlistHistory,
    WatchlistState,
    WatchlistTransitionType,
)
from egxpm.persistence.operational_repository import OperationalRepository
from egxpm.persistence.portfolio_repository import PortfolioRepository
from egxpm.persistence.recommendation_repository import RecommendationRepository
from egxpm.persistence.sector_market_repository import SectorMarketRepository

COMPANY_ID = "COMI"  # seeded by init_db via PHASE1_COMPANIES


# ------------------------------------------------------------
# CompanyRepository
# ------------------------------------------------------------

def test_company_round_trips(db_path):
    repo = CompanyRepository(db_path)
    company = repo.get_company(COMPANY_ID)
    assert company is not None
    assert company.company_id == COMPANY_ID
    assert company.name == "Commercial International Bank (CIB)"


def test_phase1_companies_seeded_into_watchlist(db_path):
    repo = CompanyRepository(db_path)
    for company_id in ["ADA", "BMM", "CLOUD", "PALM", "NARE", "ABR",
                        "COMI", "TMGH", "SWDY", "EFGD", "ABUK", "EFIH"]:
        assert repo.get_watchlist_state(company_id) == WatchlistState.WATCHLIST
        history = repo.get_watchlist_history(company_id)
        assert [h.transition_type for h in history] == [
            WatchlistTransitionType.CANDIDATE_DISCOVERED,
            WatchlistTransitionType.USER_ADDED_TO_WATCHLIST,
        ]


def test_company_sector_change_never_overwrites_history(db_path):
    repo = CompanyRepository(db_path)
    initial_history = repo.get_sector_history(COMPANY_ID)
    assert len(initial_history) == 1
    assert initial_history[0].effective_to is None

    repo.change_sector(COMPANY_ID, "Financial Services", "2026-08-01T00:00:00+00:00")

    history = repo.get_sector_history(COMPANY_ID)
    assert len(history) == 2
    assert history[0].effective_to == "2026-08-01T00:00:00+00:00"
    assert history[1].sector == "Financial Services"
    assert history[1].effective_to is None
    assert repo.get_company(COMPANY_ID).sector == "Financial Services"


def test_watchlist_history_is_append_only(db_path):
    repo = CompanyRepository(db_path)
    entry = WatchlistHistory(
        company_id=COMPANY_ID, state=WatchlistState.CANDIDATE,
        transition_type=WatchlistTransitionType.CANDIDATE_DISCOVERED,
    )
    repo.append_watchlist_transition(entry)
    with pytest.raises(sqlite3.IntegrityError):
        repo.append_watchlist_transition(entry)  # duplicate history_id


def test_watchlist_state_tracks_latest_transition(db_path):
    repo = CompanyRepository(db_path)
    repo.append_watchlist_transition(WatchlistHistory(
        company_id=COMPANY_ID, state=WatchlistState.CANDIDATE,
        state_changed_at="2026-01-01T00:00:00+00:00",
        transition_type=WatchlistTransitionType.CANDIDATE_DISCOVERED,
    ))
    repo.append_watchlist_transition(WatchlistHistory(
        company_id=COMPANY_ID, state=WatchlistState.WATCHLIST,
        state_changed_at="2026-02-01T00:00:00+00:00",
        transition_type=WatchlistTransitionType.USER_ADDED_TO_WATCHLIST,
    ))
    assert repo.get_watchlist_state(COMPANY_ID) == WatchlistState.WATCHLIST
    # All Phase 1 companies are seeded into WATCHLIST already (init_db);
    # COMPANY_ID's additional transitions must not remove it from that set.
    assert COMPANY_ID in repo.list_companies_in_state(WatchlistState.WATCHLIST)


def test_holding_round_trip_and_mutable_update(db_path):
    repo = CompanyRepository(db_path)
    holding = Holding(
        company_id=COMPANY_ID, category=HoldingCategory.LONG_TERM_STOCKS,
        quantity=10, average_cost=50.0, acquired_at="2026-01-01",
    )
    repo.save_holding(holding)
    fetched = repo.get_holding(holding.holding_id)
    assert fetched == holding

    holding.quantity = 20
    repo.save_holding(holding)  # holdings are Mutable — update allowed
    assert repo.get_holding(holding.holding_id).quantity == 20

    repo.delete_holding(holding.holding_id)
    assert repo.get_holding(holding.holding_id) is None


def test_financial_statement_fk_enforced(db_path):
    repo = CompanyRepository(db_path)
    stmt = FinancialStatement(
        company_id="NONEXISTENT", period_type=PeriodType.ANNUAL, period_end="2025-12-31",
        revenue=100.0, data_source_id="stockanalysis", source_version="v1",
        collection_run_id="run-1",
    )
    with pytest.raises(sqlite3.IntegrityError):
        repo.save_financial_statement(stmt)


def test_financial_statement_round_trip_and_append_only(db_path):
    repo = CompanyRepository(db_path)
    stmt = FinancialStatement(
        company_id=COMPANY_ID, period_type=PeriodType.ANNUAL, period_end="2025-12-31",
        revenue=100.0, net_income=20.0, data_source_id="stockanalysis",
        source_version="v1", collection_run_id="run-1",
    )
    repo.save_financial_statement(stmt)
    fetched = repo.list_financial_statements(COMPANY_ID)
    assert len(fetched) == 1
    assert fetched[0] == stmt
    with pytest.raises(sqlite3.IntegrityError):
        repo.save_financial_statement(stmt)  # duplicate statement_id


def test_price_candles_round_trip(db_path):
    repo = CompanyRepository(db_path)
    candles = [
        PriceCandle(
            company_id=COMPANY_ID, candle_date="2026-06-01", open=10, high=11,
            low=9, close=10.5, volume=1000, data_source_id="yfinance",
            source_version="v1", collection_run_id="run-1",
        ),
        PriceCandle(
            company_id=COMPANY_ID, candle_date="2026-06-02", open=10.5, high=12,
            low=10, close=11.5, volume=1500, data_source_id="yfinance",
            source_version="v1", collection_run_id="run-1",
        ),
    ]
    repo.save_price_candles(candles)
    fetched = repo.list_price_candles(COMPANY_ID)
    assert [c.candle_date for c in fetched] == ["2026-06-01", "2026-06-02"]
    assert fetched[0].close == 10.5


def test_corporate_action_round_trip(db_path):
    repo = CompanyRepository(db_path)
    action = CorporateAction(
        company_id=COMPANY_ID, action_type="dividend", action_date="2026-06-01",
        details={"amount_per_share": 1.5}, data_source_id="manual",
    )
    repo.save_corporate_action(action)
    fetched = repo.list_corporate_actions(COMPANY_ID)
    assert fetched[0].details == {"amount_per_share": 1.5}


def test_news_item_round_trip(db_path):
    repo = CompanyRepository(db_path)
    item = NewsItem(
        company_id=COMPANY_ID, headline="CIB reports strong Q2",
        publisher_name="Mubasher", published_at="2026-06-01T09:00:00+00:00",
        sentiment_score=0.6, relevance_score=0.9, data_source_id="mubasher",
        source_version="v1", collection_run_id="run-1",
    )
    repo.save_news_item(item)
    fetched = repo.list_news_items(COMPANY_ID)
    assert fetched[0] == item


def test_technical_reference_snapshot_round_trip(db_path):
    repo = CompanyRepository(db_path)
    snap = TechnicalReferenceSnapshot(
        company_id=COMPANY_ID, rating="BUY", raw_indicators={"RSI": 55.2},
        data_source_id="tradingview_ta", collection_run_id="run-1",
    )
    repo.save_technical_reference_snapshot(snap)
    fetched = repo.get_latest_technical_reference_snapshot(COMPANY_ID)
    assert fetched.raw_indicators == {"RSI": 55.2}


def test_technical_snapshot_round_trip_and_append_only(db_path):
    repo = CompanyRepository(db_path)
    snap = TechnicalSnapshot(
        company_id=COMPANY_ID, rsi=55.0, trend="BULLISH", breakout=True,
        unusual_volume=False, engine_version="v1", computed_through_date="2026-06-01",
        job_id="job-1",
    )
    repo.save_technical_snapshot(snap)
    fetched = repo.get_latest_technical_snapshot(COMPANY_ID)
    assert fetched.rsi == 55.0
    assert fetched.breakout is True
    assert fetched.unusual_volume is False
    with pytest.raises(sqlite3.IntegrityError):
        repo.save_technical_snapshot(snap)


def test_score_round_trip_and_append_only(db_path):
    repo = CompanyRepository(db_path)
    score = Score(
        company_id=COMPANY_ID, financial_score=80.0,
        financial_breakdown={"revenue_growth": {"value": 18.4, "points": 15, "max": 20}},
        composite_score=75.0, config_snapshot_id="cfg-1", job_id="job-1",
    )
    repo.save_score(score)
    fetched = repo.get_score(score.score_id)
    assert fetched.financial_breakdown["revenue_growth"]["points"] == 15
    assert repo.get_latest_score(COMPANY_ID).score_id == score.score_id
    with pytest.raises(sqlite3.IntegrityError):
        repo.save_score(score)


def test_risk_and_confidence_score_round_trip(db_path):
    repo = CompanyRepository(db_path)
    score = Score(company_id=COMPANY_ID, config_snapshot_id="cfg-1", job_id="job-1")
    repo.save_score(score)

    risk = RiskScore(score_id=score.score_id, value=72.5, breakdown={"debt": "low"})
    repo.save_risk_score(risk)
    fetched_risk = repo.get_risk_score_by_score_id(score.score_id)
    assert fetched_risk.value == 72.5

    confidence = ConfidenceScore(score_id=score.score_id, confidence_value=0.85)
    repo.save_confidence_score(confidence)
    fetched_conf = repo.get_confidence_score_by_score_id(score.score_id)
    assert fetched_conf.confidence_value == 0.85


# ------------------------------------------------------------
# PortfolioRepository
# ------------------------------------------------------------

def test_portfolio_snapshot_round_trip(db_path):
    repo = PortfolioRepository(db_path)
    snap = PortfolioSnapshot(
        holdings_snapshot=[{"company_id": COMPANY_ID, "quantity": 10}],
        cash=500.0, computed_allocation={"long_term_stocks": 0.5},
        origin=PortfolioSnapshotOrigin.BEFORE_RECOMMENDATION,
    )
    repo.save_snapshot(snap)
    fetched = repo.get_snapshot(snap.snapshot_id)
    assert fetched == snap
    assert repo.get_latest_snapshot().snapshot_id == snap.snapshot_id


# ------------------------------------------------------------
# RecommendationRepository (exercises FK chain: score -> confidence,
# configuration_snapshot, portfolio_snapshot -> recommendation)
# ------------------------------------------------------------

def _build_recommendation_dependencies(db_path):
    company_repo = CompanyRepository(db_path)
    operational_repo = OperationalRepository(db_path)
    portfolio_repo = PortfolioRepository(db_path)

    score = Score(company_id=COMPANY_ID, config_snapshot_id="cfg-1", job_id="job-1")
    company_repo.save_score(score)
    confidence = ConfidenceScore(score_id=score.score_id, confidence_value=0.8)
    company_repo.save_confidence_score(confidence)

    config_snapshot = ConfigurationSnapshot(allocation_targets={"long_term_stocks": 0.4})
    operational_repo.save_configuration_snapshot(config_snapshot)

    portfolio_snapshot = PortfolioSnapshot(origin=PortfolioSnapshotOrigin.BEFORE_RECOMMENDATION)
    portfolio_repo.save_snapshot(portfolio_snapshot)

    return confidence, config_snapshot, portfolio_snapshot


def test_recommendation_round_trip_and_fk_enforced(db_path):
    repo = RecommendationRepository(db_path)
    confidence, config_snapshot, portfolio_snapshot = _build_recommendation_dependencies(db_path)

    rec = Recommendation(
        company_id=COMPANY_ID, action=RecommendationAction.BUY, entry_price=50.0,
        stop_loss=45.0, take_profit=60.0, position_size=1000.0,
        confidence_id=confidence.confidence_id,
        config_snapshot_id=config_snapshot.config_snapshot_id,
        portfolio_snapshot_id=portfolio_snapshot.snapshot_id,
        frozen_package={"reasoning": "strong fundamentals"}, job_id="job-1",
    )
    repo.save_recommendation(rec)
    fetched = repo.get_recommendation(rec.recommendation_id)
    assert fetched == rec

    bad_rec = rec.model_copy(update={
        "recommendation_id": "rec-bad", "confidence_id": "nonexistent-confidence",
    })
    with pytest.raises(sqlite3.IntegrityError):
        repo.save_recommendation(bad_rec)


def test_recommendation_supersession_round_trip(db_path):
    repo = RecommendationRepository(db_path)
    confidence, config_snapshot, portfolio_snapshot = _build_recommendation_dependencies(db_path)
    rec = Recommendation(
        company_id=COMPANY_ID, action=RecommendationAction.BUY,
        confidence_id=confidence.confidence_id,
        config_snapshot_id=config_snapshot.config_snapshot_id,
        portfolio_snapshot_id=portfolio_snapshot.snapshot_id, job_id="job-1",
    )
    repo.save_recommendation(rec)

    supersession = RecommendationSupersession(
        recommendation_id=rec.recommendation_id,
        superseding_event_type="new_score_computed",
    )
    repo.save_supersession(supersession)
    fetched = repo.list_supersessions(rec.recommendation_id)
    assert fetched[0] == supersession


def test_execution_outcome_feedback_round_trip(db_path):
    repo = RecommendationRepository(db_path)
    confidence, config_snapshot, portfolio_snapshot = _build_recommendation_dependencies(db_path)
    rec = Recommendation(
        company_id=COMPANY_ID, action=RecommendationAction.BUY,
        confidence_id=confidence.confidence_id,
        config_snapshot_id=config_snapshot.config_snapshot_id,
        portfolio_snapshot_id=portfolio_snapshot.snapshot_id, job_id="job-1",
    )
    repo.save_recommendation(rec)

    execution = Execution(
        recommendation_id=rec.recommendation_id, action_taken="bought",
        details={"quantity": 10, "price": 50.0},
    )
    repo.save_execution(execution)
    assert repo.get_execution(execution.execution_id) == execution

    outcome = Outcome(
        recommendation_id=rec.recommendation_id, execution_id=execution.execution_id,
        actual_return=0.12, target_hit=True, stop_hit=False, is_final=True,
    )
    repo.save_outcome(outcome)
    assert repo.list_outcomes(rec.recommendation_id)[0] == outcome

    feedback = UserFeedback(
        recommendation_id=rec.recommendation_id, execution_id=execution.execution_id,
        outcome_id=outcome.outcome_id, feedback_text="Good call", agreement="agree",
    )
    repo.save_user_feedback(feedback)
    assert repo.list_user_feedback(rec.recommendation_id)[0] == feedback


# ------------------------------------------------------------
# ConversationRepository
# ------------------------------------------------------------

def test_conversation_round_trip_and_mutable_update(db_path):
    repo = ConversationRepository(db_path)
    conv = Conversation(transcript=[{"role": "user", "text": "hi"}])
    repo.save_conversation(conv)
    assert repo.get_conversation(conv.conversation_id).transcript == conv.transcript

    conv.transcript.append({"role": "assistant", "text": "hello"})
    repo.save_conversation(conv)  # Conversation is Ephemeral/mutable
    assert len(repo.get_conversation(conv.conversation_id).transcript) == 2


def test_analysis_session_round_trip(db_path):
    conv_repo = ConversationRepository(db_path)
    conv = Conversation()
    conv_repo.save_conversation(conv)

    session = AnalysisSession(conversation_id=conv.conversation_id, state={"step": 1})
    conv_repo.save_session(session)
    fetched = conv_repo.get_session(session.session_id)
    assert fetched.state == {"step": 1}


# ------------------------------------------------------------
# OperationalRepository
# ------------------------------------------------------------

def test_data_source_round_trip(db_path):
    repo = OperationalRepository(db_path)
    source = repo.get_data_source("yfinance")
    assert source is not None
    assert source.is_canonical_for == ["prices"]


def test_job_and_collection_run_round_trip(db_path):
    repo = OperationalRepository(db_path)
    job = Job(job_type=JobType.PRICE)
    repo.save_job(job)
    assert repo.get_job(job.job_id).status.value == "running"

    job.status = RunStatus.COMPLETED
    job.completed_at = "2026-06-01T00:00:00+00:00"
    repo.save_job(job)  # Job record mutated to reflect completion — same row
    assert repo.get_job(job.job_id).status.value == "completed"

    run = CollectionRun(job_id=job.job_id, data_source_id="yfinance", company_id=COMPANY_ID)
    repo.save_collection_run(run)
    assert repo.get_collection_run(run.collection_run_id).records_collected == 0


def test_configuration_snapshot_round_trip_and_append_only(db_path):
    repo = OperationalRepository(db_path)
    snapshot = ConfigurationSnapshot(
        scoring_weights={"financial": 0.45}, risk_settings={"max_per_stock_pct": 0.15},
        allocation_targets={"long_term_stocks": 0.4},
    )
    repo.save_configuration_snapshot(snapshot)
    fetched = repo.get_configuration_snapshot(snapshot.config_snapshot_id)
    assert fetched == snapshot
    assert repo.get_latest_configuration_snapshot().config_snapshot_id == snapshot.config_snapshot_id
    with pytest.raises(sqlite3.IntegrityError):
        repo.save_configuration_snapshot(snapshot)


# ------------------------------------------------------------
# SectorMarketRepository
# ------------------------------------------------------------

def test_sector_and_market_summary_round_trip(db_path):
    repo = SectorMarketRepository(db_path)
    sector_summary = SectorSummary(
        sector="Banking", summary_score=70.0,
        component_company_scores=[{"company_id": COMPANY_ID, "score": 70.0}],
        job_id="job-1",
    )
    repo.save_sector_summary(sector_summary)
    assert repo.get_latest_sector_summary("Banking").summary_score == 70.0

    market_summary = MarketSummary(
        summary_score=65.0, component_sector_summaries=[{"sector": "Banking", "score": 70.0}],
        job_id="job-1",
    )
    repo.save_market_summary(market_summary)
    assert repo.get_latest_market_summary().summary_score == 65.0


# ------------------------------------------------------------
# DashboardReadRepository (the one Dashboard read-time computation)
# ------------------------------------------------------------

def test_dashboard_read_repository_computes_allocation(db_path):
    company_repo = CompanyRepository(db_path)
    holding = Holding(
        company_id=COMPANY_ID, category=HoldingCategory.LONG_TERM_STOCKS,
        quantity=10, average_cost=50.0, acquired_at="2026-01-01",
    )
    company_repo.save_holding(holding)

    dashboard_repo = DashboardReadRepository(db_path)
    fallback_config = ConfigurationSnapshot(allocation_targets={"long_term_stocks": 0.4})
    report = dashboard_repo.get_current_allocation(
        prices={COMPANY_ID: 55.0}, cash=1000.0, fallback_config=fallback_config,
    )
    assert report.total_value == pytest.approx(10 * 55.0 + 1000.0)
    assert COMPANY_ID in report.by_stock_pct


def test_dashboard_read_repository_watchlist_overview(db_path):
    company_repo = CompanyRepository(db_path)
    company_repo.append_watchlist_transition(WatchlistHistory(
        company_id=COMPANY_ID, state=WatchlistState.WATCHLIST,
        transition_type=WatchlistTransitionType.USER_ADDED_TO_WATCHLIST,
    ))
    dashboard_repo = DashboardReadRepository(db_path)
    overview = dashboard_repo.get_watchlist_overview()
    assert COMPANY_ID in overview[WatchlistState.WATCHLIST.value]
