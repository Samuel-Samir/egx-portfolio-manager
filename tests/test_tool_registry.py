import pytest

from egxpm.copilot.models import AnalysisSessionState
from egxpm.copilot.tool_registry import TOOL_SCHEMAS, TOOL_TIERS, ToolRegistry
from egxpm.persistence.company_repository import CompanyRepository
from egxpm.persistence.models import (
    FinancialStatement,
    Holding,
    HoldingCategory,
    PeriodType,
    PriceCandle,
    Score,
)

# Phase 1 companies are seeded WATCHLIST by init_db (see seed_phase1_watchlist).
COMPANY_A = "TMGH"
COMPANY_B = "SWDY"


def _seed_price_candles(company_repo: CompanyRepository, company_id: str, close: float) -> None:
    # calculate_technical_snapshot requires >= window (default 200) candles.
    from datetime import date, timedelta

    start = date(2025, 1, 1)
    candles = [
        PriceCandle(
            company_id=company_id, candle_date=(start + timedelta(days=i)).isoformat(),
            open=close, high=close * 1.01, low=close * 0.99, close=close, volume=100000.0,
            data_source_id="yfinance", source_version="1", collection_run_id="seed-run",
        )
        for i in range(220)
    ]
    company_repo.save_price_candles(candles)


def _seed_financial_statement(company_repo: CompanyRepository, company_id: str) -> None:
    company_repo.save_financial_statement(FinancialStatement(
        company_id=company_id, period_type=PeriodType.QUARTERLY, period_end="2026-03-31",
        revenue=1_000_000.0, net_income=100_000.0, total_equity=500_000.0, total_liabilities=200_000.0,
        data_source_id="stockanalysis", source_version="1", collection_run_id="seed-run",
    ))


def _seed_score(company_repo: CompanyRepository, company_id: str, composite: float) -> None:
    score = Score(
        company_id=company_id, financial_score=70.0, technical_score=60.0, news_score=55.0,
        composite_score=composite, config_snapshot_id="cfg-seed", job_id="seed-job",
    )
    company_repo.save_score(score)


@pytest.fixture
def registry(db_path):
    return ToolRegistry(db_path, config_path="config.yaml")


@pytest.fixture
def session():
    return AnalysisSessionState()


@pytest.fixture
def seeded(db_path):
    company_repo = CompanyRepository(db_path)
    _seed_price_candles(company_repo, COMPANY_A, close=10.0)
    _seed_price_candles(company_repo, COMPANY_B, close=20.0)
    _seed_financial_statement(company_repo, COMPANY_A)
    _seed_financial_statement(company_repo, COMPANY_B)
    _seed_score(company_repo, COMPANY_A, composite=80.0)
    _seed_score(company_repo, COMPANY_B, composite=65.0)
    company_repo.save_holding(Holding(
        company_id=COMPANY_A, category=HoldingCategory.LONG_TERM_STOCKS,
        quantity=10, average_cost=9.0, acquired_at="2026-01-01",
    ))
    return company_repo


# ------------------------------------------------------------
# Tier registration
# ------------------------------------------------------------

def test_all_16_tools_registered():
    assert len(TOOL_TIERS) == 16
    assert set(TOOL_TIERS) == set(TOOL_SCHEMAS)


def test_tier_counts_match_spec():
    tiers = list(TOOL_TIERS.values())
    assert tiers.count("read") == 10
    assert tiers.count("propose") == 2
    assert tiers.count("execute") == 4


# ------------------------------------------------------------
# Read tier
# ------------------------------------------------------------

def test_get_company_summary_unknown_company_is_tool_result_error(registry, session):
    result = registry.execute("get_company_summary", {"symbol": "NOPE"}, session)
    assert result.success is False
    assert "NOPE" in result.error


def test_compare_companies(registry, session, seeded):
    result = registry.execute("compare_companies", {"company_ids": [COMPANY_A, COMPANY_B]}, session)
    assert result.success is True
    assert result.data[COMPANY_A]["composite_score"] == 80.0
    assert result.data[COMPANY_B]["composite_score"] == 65.0


def test_simulate_buy_does_not_touch_real_holdings(registry, session, seeded):
    before = seeded.list_holdings()
    result = registry.execute(
        "simulate_buy", {"company_id": COMPANY_B, "quantity": 5, "price": 20.0}, session
    )
    assert result.success is True
    assert result.data["by_stock_pct"].get(COMPANY_B, 0) > 0
    after = seeded.list_holdings()
    assert before == after  # simulate_buy is read-tier: no persistence side effect


# ------------------------------------------------------------
# Acceptance scenario (M7 validation criterion):
# compare 2 companies -> simulate -> propose 2 plans -> confirm one
# (other stays intact) -> confirm wrong plan_id -> ToolResult.error
# ------------------------------------------------------------

def test_full_acceptance_scenario(registry, session, seeded):
    compare = registry.execute("compare_companies", {"company_ids": [COMPANY_A, COMPANY_B]}, session)
    assert compare.success is True

    sim = registry.execute(
        "simulate_buy", {"company_id": COMPANY_B, "quantity": 5, "price": 20.0}, session
    )
    assert sim.success is True

    plan_1 = registry.execute("propose_rebalance", {"new_capital": 1000.0}, session)
    assert plan_1.success is True
    plan_2 = registry.execute("propose_swing_analysis", {"company_id": COMPANY_B}, session)
    assert plan_2.success is True

    assert len(session.pending_plans) == 2
    plan_ids = list(session.pending_plans.keys())
    assert len(set(plan_ids)) == 2  # distinct plan_ids

    confirm = registry.execute("confirm_and_apply", {"plan_id": plan_ids[0]}, session)
    assert confirm.success is True
    assert plan_ids[0] not in session.pending_plans
    assert plan_ids[1] in session.pending_plans  # the other plan stays intact
    assert plan_ids[0] in session.confirmed_plan_ids

    wrong = registry.execute("confirm_and_apply", {"plan_id": "not-a-real-plan-id"}, session)
    assert wrong.success is False
    assert wrong.error is not None
    assert "not-a-real-plan-id" in wrong.error


# ------------------------------------------------------------
# Propose tier — LLM never calculates: numbers come from Python
# ------------------------------------------------------------

def test_propose_rebalance_caps_per_stock_and_is_deterministic(registry, session, seeded):
    result_1 = registry.execute("propose_rebalance", {"new_capital": 500.0}, session)
    result_2 = registry.execute("propose_rebalance", {"new_capital": 500.0}, session)
    assert result_1.success is True and result_2.success is True
    amounts_1 = sorted((a["company_id"], a["quantity"]) for a in result_1.data["proposed_actions"])
    amounts_2 = sorted((a["company_id"], a["quantity"]) for a in result_2.data["proposed_actions"])
    assert amounts_1 == amounts_2  # same inputs -> same deterministic plan


def test_propose_rebalance_no_candidates_raises_business_error(registry, session, db_path):
    # Fresh DB fixture with no scores at all -> ToolResult.error, not a crash.
    empty_registry = ToolRegistry(db_path, config_path="config.yaml")
    result = empty_registry.execute("propose_rebalance", {"new_capital": 100.0}, AnalysisSessionState())
    assert result.success is False


# ------------------------------------------------------------
# Execute tier
# ------------------------------------------------------------

def test_confirm_and_apply_never_touches_real_holdings(registry, session, seeded):
    before = seeded.list_holdings()
    plan = registry.execute("propose_rebalance", {"new_capital": 500.0}, session)
    plan_id = plan.data["plan_id"]
    confirm = registry.execute("confirm_and_apply", {"plan_id": plan_id}, session)
    assert confirm.success is True
    assert "Thndr" in confirm.data["message"]
    after = seeded.list_holdings()
    assert before == after  # never places real trades


def test_save_analysis_session_round_trips(registry, session, seeded):
    from egxpm.persistence.conversation_repository import ConversationRepository
    from egxpm.persistence.models import Conversation

    conv_repo = ConversationRepository(registry.db_path)
    conv_repo.save_conversation(Conversation(conversation_id="conv-1"))

    session.notes = "test note"
    result = registry.execute(
        "save_analysis_session", {"session_id": "sess-1", "conversation_id": "conv-1"}, session
    )
    assert result.success is True
    saved = conv_repo.get_session("sess-1")
    assert saved is not None
    assert saved.state["notes"] == "test note"


def test_dispatch_unknown_tool_is_tool_result_error(registry, session):
    result = registry.execute("delete_everything", {}, session)
    assert result.success is False
    assert "delete_everything" in result.error


# ------------------------------------------------------------
# record_holding_transaction
# ------------------------------------------------------------

def test_record_holding_transaction_opens_new_position(registry, session, seeded):
    # COMPANY_B has no pre-seeded holding, unlike COMPANY_A (see `seeded`).
    result = registry.execute("record_holding_transaction", {
        "company_id": COMPANY_B, "action": "BUY", "quantity": 100, "price": 20.0,
        "category": "long_term_stocks",
    }, session)
    assert result.success is True
    assert result.data["portfolio_snapshot_captured"] is True

    holding = next(h for h in seeded.list_holdings() if h.company_id == COMPANY_B)
    assert holding.quantity == 100
    assert holding.average_cost == 20.0


def test_record_holding_transaction_requires_category_for_new_position(registry, session, seeded):
    result = registry.execute("record_holding_transaction", {
        "company_id": COMPANY_B, "action": "BUY", "quantity": 100, "price": 20.0,
    }, session)
    assert result.success is False
    assert "without a category" in result.error


def test_record_holding_transaction_selling_more_than_held_is_tool_result_error(registry, session, seeded):
    # COMPANY_A already has a seeded holding of 10 shares (see `seeded`).
    result = registry.execute("record_holding_transaction", {
        "company_id": COMPANY_A, "action": "SELL", "quantity": 9999, "price": 10.0,
    }, session)
    assert result.success is False
    holding = next(h for h in seeded.list_holdings() if h.company_id == COMPANY_A)
    assert holding.quantity == 10  # untouched


def test_record_holding_transaction_creates_a_standalone_execution(registry, session, seeded):
    result = registry.execute("record_holding_transaction", {
        "company_id": COMPANY_B, "action": "BUY", "quantity": 100, "price": 20.0,
        "category": "long_term_stocks",
    }, session)
    execution = registry.recommendation_repo.get_execution(result.data["execution_id"])
    assert execution is not None
    assert execution.recommendation_id is None


def test_record_holding_transaction_links_to_a_recommendation(registry, session, seeded):
    from egxpm.persistence.models import (
        ConfidenceScore,
        ConfigurationSnapshot,
        PortfolioSnapshot,
        PortfolioSnapshotOrigin,
        Recommendation,
        RecommendationAction,
    )

    score = registry.company_repo.get_latest_score(COMPANY_B)
    confidence = ConfidenceScore(score_id=score.score_id, confidence_value=0.8)
    registry.company_repo.save_confidence_score(confidence)
    config_snapshot = ConfigurationSnapshot(allocation_targets={"long_term_stocks": 0.4})
    registry.operational_repo.save_configuration_snapshot(config_snapshot)
    portfolio_snapshot = PortfolioSnapshot(origin=PortfolioSnapshotOrigin.BEFORE_RECOMMENDATION)
    registry.portfolio_repo.save_snapshot(portfolio_snapshot)
    rec = Recommendation(
        company_id=COMPANY_B, action=RecommendationAction.BUY,
        confidence_id=confidence.confidence_id, config_snapshot_id=config_snapshot.config_snapshot_id,
        portfolio_snapshot_id=portfolio_snapshot.snapshot_id, job_id="job-1",
    )
    registry.recommendation_repo.save_recommendation(rec)

    result = registry.execute("record_holding_transaction", {
        "company_id": COMPANY_B, "action": "BUY", "quantity": 100, "price": 20.0,
        "category": "long_term_stocks", "recommendation_id": rec.recommendation_id,
    }, session)
    assert result.success is True

    linked_executions = registry.recommendation_repo.list_executions(rec.recommendation_id)
    assert len(linked_executions) == 1
    assert linked_executions[0].execution_id == result.data["execution_id"]

    all_executions = registry.recommendation_repo.list_all_executions()
    assert any(e.execution_id == result.data["execution_id"] for e in all_executions)


def test_record_holding_transaction_backfills_acquired_at(registry, session, seeded):
    registry.execute("record_holding_transaction", {
        "company_id": COMPANY_B, "action": "BUY", "quantity": 100, "price": 20.0,
        "category": "long_term_stocks", "acquired_at": "2025-01-15T00:00:00+00:00",
    }, session)
    holding = next(h for h in seeded.list_holdings() if h.company_id == COMPANY_B)
    assert holding.acquired_at == "2025-01-15T00:00:00+00:00"
