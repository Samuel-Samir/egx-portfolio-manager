"""Pydantic domain objects for every Section 3 entity.

These are plain data objects — no I/O, no SQL awareness. Repository
classes translate between these objects and SQLite rows; Engines accept
and return objects from this module (or engine-local value objects) and
never see a database row.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ============================================================
# ENUMS
# ============================================================

class ListingStatus(str, Enum):
    ACTIVE = "active"
    SUSPENDED = "suspended"
    DELISTED = "delisted"


class StatementSchema(str, Enum):
    INDUSTRIAL = "INDUSTRIAL"
    BANK = "BANK"


class RolloutPhase(str, Enum):
    PHASE1 = "phase1"
    PHASE2 = "phase2"


class WatchlistState(str, Enum):
    CANDIDATE = "CANDIDATE"
    WATCHLIST = "WATCHLIST"
    ARCHIVED = "ARCHIVED"


class WatchlistTransitionType(str, Enum):
    CANDIDATE_DISCOVERED = "candidate_discovered"
    USER_ADDED_TO_WATCHLIST = "user_added_to_watchlist"
    CANDIDATE_REJECTED = "candidate_rejected"
    USER_ARCHIVED = "user_archived"
    DELISTING = "delisting"
    USER_REVIVED = "user_revived"


class HoldingCategory(str, Enum):
    """Matches config.yaml allocation_targets keys exactly."""
    BMM_INDEX = "bmm_index"
    LONG_TERM_STOCKS = "long_term_stocks"
    SWING_TRADING = "swing_trading"
    CLOUD_CASH = "cloud_cash"
    GOLD = "gold"


class PeriodType(str, Enum):
    ANNUAL = "annual"
    QUARTERLY = "quarterly"


class Timeframe(str, Enum):
    DAILY = "daily"


class TrendSignal(str, Enum):
    BULLISH = "BULLISH"
    BEARISH = "BEARISH"
    NEUTRAL = "NEUTRAL"


class RecommendationAction(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"
    TRIM = "TRIM"
    ADD = "ADD"


class SourceQuality(str, Enum):
    OFFICIAL = "official"
    INTERNAL = "internal"
    SCRAPED = "scraped"
    MANUAL = "manual"


class SourceType(str, Enum):
    PRICE = "price"
    TECHNICAL = "technical"
    FUNDAMENTAL = "fundamental"
    NEWS = "news"
    CORPORATE = "corporate"


class CollectionMethod(str, Enum):
    API = "api"
    INTERNAL = "internal"
    SCRAPING = "scraping"
    MANUAL = "manual"


class RunStatus(str, Enum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    PARTIAL = "partial"


class JobType(str, Enum):
    PRICE = "price"
    TECHNICAL_REFERENCE = "technical_reference"
    TECHNICAL = "technical"
    NEWS = "news"
    FUNDAMENTALS = "fundamentals"
    SWING = "swing"
    LONGTERM = "longterm"
    REVIEW = "review"


class Agreement(str, Enum):
    AGREE = "agree"
    DISAGREE = "disagree"
    PARTIAL = "partial"


class PortfolioSnapshotOrigin(str, Enum):
    BEFORE_RECOMMENDATION = "before_recommendation"
    MANUAL = "manual"
    SCHEDULED = "scheduled"


# ============================================================
# COMPANY AGGREGATE
# ============================================================

class Company(BaseModel):
    company_id: str
    name: str
    sector: str
    industry: Optional[str] = None
    isin: Optional[str] = None
    listing_status: ListingStatus = ListingStatus.ACTIVE
    statement_schema: StatementSchema = StatementSchema.INDUSTRIAL
    rollout_phase: RolloutPhase = RolloutPhase.PHASE1
    created_at: str = Field(default_factory=_now)
    updated_at: str = Field(default_factory=_now)


class CompanySectorHistory(BaseModel):
    history_id: str = Field(default_factory=_uuid)
    company_id: str
    sector: str
    effective_from: str
    effective_to: Optional[str] = None
    created_at: str = Field(default_factory=_now)


class WatchlistHistory(BaseModel):
    history_id: str = Field(default_factory=_uuid)
    company_id: str
    state: WatchlistState
    state_changed_at: str = Field(default_factory=_now)
    transition_type: WatchlistTransitionType
    reference_type: Optional[str] = None
    reference_id: Optional[str] = None
    created_at: str = Field(default_factory=_now)


class Holding(BaseModel):
    holding_id: str = Field(default_factory=_uuid)
    company_id: str
    category: HoldingCategory
    quantity: float
    average_cost: float
    acquired_at: str
    updated_at: str = Field(default_factory=_now)


# ============================================================
# DATA SOURCES
# ============================================================

class DataSource(BaseModel):
    data_source_id: str
    name: str
    source_type: SourceType
    collection_method: CollectionMethod
    source_quality: SourceQuality
    is_canonical_for: Optional[list[str]] = None
    created_at: str = Field(default_factory=_now)
    updated_at: str = Field(default_factory=_now)


# ============================================================
# COLLECTED FACTS
# ============================================================

class FinancialStatement(BaseModel):
    statement_id: str = Field(default_factory=_uuid)
    company_id: str
    period_type: PeriodType
    period_end: str
    revenue: Optional[float] = None
    net_income: Optional[float] = None
    eps_basic: Optional[float] = None
    eps_diluted: Optional[float] = None
    total_assets: Optional[float] = None
    total_liabilities: Optional[float] = None
    total_equity: Optional[float] = None
    operating_income: Optional[float] = None
    operating_cash_flow: Optional[float] = None
    capex: Optional[float] = None
    free_cash_flow: Optional[float] = None
    net_interest_income: Optional[float] = None
    data_source_id: str
    source_version: str
    fetched_at: str = Field(default_factory=_now)
    collection_run_id: str


class PriceCandle(BaseModel):
    candle_id: str = Field(default_factory=_uuid)
    company_id: str
    timeframe: Timeframe = Timeframe.DAILY
    candle_date: str
    open: Optional[float] = None
    high: Optional[float] = None
    low: Optional[float] = None
    close: Optional[float] = None
    volume: Optional[float] = None
    adjusted_for_corporate_action: bool = False
    data_source_id: str
    source_version: str
    fetched_at: str = Field(default_factory=_now)
    collection_run_id: str


class CorporateAction(BaseModel):
    action_id: str = Field(default_factory=_uuid)
    company_id: str
    action_type: str
    action_date: str
    details: dict[str, Any] = Field(default_factory=dict)
    data_source_id: str
    entered_at: str = Field(default_factory=_now)


class NewsItem(BaseModel):
    news_id: str = Field(default_factory=_uuid)
    company_id: Optional[str] = None
    sector_scope: Optional[str] = None
    headline: str
    publisher_name: str
    published_at: str
    url: Optional[str] = None
    sentiment_score: Optional[float] = None
    relevance_score: Optional[float] = None
    data_source_id: str
    source_version: str
    fetched_at: str = Field(default_factory=_now)
    collection_run_id: str


class TechnicalReferenceSnapshot(BaseModel):
    ref_id: str = Field(default_factory=_uuid)
    company_id: str
    rating: str
    raw_indicators: dict[str, Any] = Field(default_factory=dict)
    data_source_id: str
    fetched_at: str = Field(default_factory=_now)
    collection_run_id: str


# ============================================================
# ENGINE OUTPUTS
# ============================================================

class TechnicalSnapshot(BaseModel):
    snapshot_id: str = Field(default_factory=_uuid)
    company_id: str
    computed_at: str = Field(default_factory=_now)
    rsi: Optional[float] = None
    macd: Optional[float] = None
    macd_signal: Optional[float] = None
    sma_20: Optional[float] = None
    sma_50: Optional[float] = None
    sma_200: Optional[float] = None
    ema_20: Optional[float] = None
    ema_50: Optional[float] = None
    atr: Optional[float] = None
    bollinger_upper: Optional[float] = None
    bollinger_lower: Optional[float] = None
    bollinger_bandwidth: Optional[float] = None
    volume_ma_20: Optional[float] = None
    support_level: Optional[float] = None
    resistance_level: Optional[float] = None
    trend: Optional[TrendSignal] = None
    breakout: Optional[bool] = None
    unusual_volume: Optional[bool] = None
    engine_version: str
    timeframe: Timeframe = Timeframe.DAILY
    window_size: int = 200
    computed_through_date: str
    job_id: str


class Score(BaseModel):
    score_id: str = Field(default_factory=_uuid)
    company_id: str
    computed_at: str = Field(default_factory=_now)
    financial_score: Optional[float] = None
    financial_breakdown: dict[str, Any] = Field(default_factory=dict)
    technical_score: Optional[float] = None
    technical_breakdown: dict[str, Any] = Field(default_factory=dict)
    news_score: Optional[float] = None
    news_breakdown: dict[str, Any] = Field(default_factory=dict)
    composite_score: Optional[float] = None
    config_snapshot_id: str
    job_id: str


class RiskScore(BaseModel):
    risk_score_id: str = Field(default_factory=_uuid)
    score_id: str
    value: float
    debt_peer_component: Optional[float] = None
    score_volatility_component: Optional[float] = None
    data_completeness_component: Optional[float] = None
    liquidity_component: Optional[float] = None
    breakdown: dict[str, Any] = Field(default_factory=dict)


class ConfidenceScore(BaseModel):
    confidence_id: str = Field(default_factory=_uuid)
    score_id: str
    confidence_value: float
    freshness_component: Optional[float] = None
    source_quality_component: Optional[float] = None
    source_health_component: Optional[float] = None
    historical_accuracy_component: Optional[float] = None
    breakdown: dict[str, Any] = Field(default_factory=dict)


class SectorSummary(BaseModel):
    summary_id: str = Field(default_factory=_uuid)
    sector: str
    computed_at: str = Field(default_factory=_now)
    summary_score: float
    component_company_scores: list[Any] = Field(default_factory=list)
    job_id: str


class MarketSummary(BaseModel):
    summary_id: str = Field(default_factory=_uuid)
    computed_at: str = Field(default_factory=_now)
    summary_score: float
    component_sector_summaries: list[Any] = Field(default_factory=list)
    job_id: str


# ============================================================
# CONFIGURATION
# ============================================================

class ConfigurationSnapshot(BaseModel):
    config_snapshot_id: str = Field(default_factory=_uuid)
    created_at: str = Field(default_factory=_now)
    scoring_weights: dict[str, Any] = Field(default_factory=dict)
    risk_settings: dict[str, Any] = Field(default_factory=dict)
    allocation_targets: dict[str, Any] = Field(default_factory=dict)
    notes: Optional[str] = None


# ============================================================
# PORTFOLIO AGGREGATE
# ============================================================

class PortfolioSnapshot(BaseModel):
    snapshot_id: str = Field(default_factory=_uuid)
    captured_at: str = Field(default_factory=_now)
    holdings_snapshot: list[Any] = Field(default_factory=list)
    cash: float = 0.0
    computed_allocation: dict[str, Any] = Field(default_factory=dict)
    origin: PortfolioSnapshotOrigin


# ============================================================
# RECOMMENDATION AGGREGATE
# ============================================================

class Recommendation(BaseModel):
    recommendation_id: str = Field(default_factory=_uuid)
    company_id: str
    created_at: str = Field(default_factory=_now)
    action: RecommendationAction
    entry_price: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    position_size: Optional[float] = None
    confidence_id: str
    config_snapshot_id: str
    portfolio_snapshot_id: str
    frozen_package: dict[str, Any] = Field(default_factory=dict)
    job_id: str


class RecommendationSupersession(BaseModel):
    supersession_id: str = Field(default_factory=_uuid)
    recommendation_id: str
    superseded_at: str = Field(default_factory=_now)
    superseding_event_type: str
    superseding_reference_id: Optional[str] = None


class Execution(BaseModel):
    execution_id: str = Field(default_factory=_uuid)
    recommendation_id: Optional[str] = None
    executed_at: str = Field(default_factory=_now)
    action_taken: str
    details: dict[str, Any] = Field(default_factory=dict)


class Outcome(BaseModel):
    outcome_id: str = Field(default_factory=_uuid)
    recommendation_id: str
    execution_id: Optional[str] = None
    recorded_at: str = Field(default_factory=_now)
    actual_return: Optional[float] = None
    actual_loss: Optional[float] = None
    holding_period_days: Optional[int] = None
    target_hit: Optional[bool] = None
    stop_hit: Optional[bool] = None
    quality_classification: Optional[str] = None
    is_final: bool = False


class UserFeedback(BaseModel):
    feedback_id: str = Field(default_factory=_uuid)
    recommendation_id: str
    execution_id: Optional[str] = None
    outcome_id: Optional[str] = None
    recorded_at: str = Field(default_factory=_now)
    feedback_text: str
    agreement: Optional[Agreement] = None


# ============================================================
# OPERATIONAL
# ============================================================

class Job(BaseModel):
    job_id: str = Field(default_factory=_uuid)
    job_type: JobType
    started_at: str = Field(default_factory=_now)
    completed_at: Optional[str] = None
    status: RunStatus = RunStatus.RUNNING
    companies_processed: int = 0
    companies_failed: int = 0
    error_summary: Optional[str] = None


class CollectionRun(BaseModel):
    collection_run_id: str = Field(default_factory=_uuid)
    job_id: Optional[str] = None
    data_source_id: str
    company_id: Optional[str] = None
    started_at: str = Field(default_factory=_now)
    completed_at: Optional[str] = None
    status: RunStatus = RunStatus.RUNNING
    records_collected: int = 0
    error_message: Optional[str] = None


# ============================================================
# COPILOT
# ============================================================

class Conversation(BaseModel):
    conversation_id: str = Field(default_factory=_uuid)
    started_at: str = Field(default_factory=_now)
    last_active_at: str = Field(default_factory=_now)
    transcript: list[Any] = Field(default_factory=list)


class AnalysisSession(BaseModel):
    session_id: str = Field(default_factory=_uuid)
    conversation_id: Optional[str] = None
    created_at: str = Field(default_factory=_now)
    state: dict[str, Any] = Field(default_factory=dict)
    promoted_to_recommendation_id: Optional[str] = None


# ============================================================
# SHARED / CROSS-LAYER VALUE OBJECTS
# ============================================================

class AllocationReport(BaseModel):
    """Output of shared/allocation_calculator.calculate()."""
    total_value: float
    cash: float
    by_category: dict[str, float] = Field(default_factory=dict)
    by_category_pct: dict[str, float] = Field(default_factory=dict)
    by_stock_pct: dict[str, float] = Field(default_factory=dict)
    target_deviation: dict[str, float] = Field(default_factory=dict)
    stock_constraint_violations: list[str] = Field(default_factory=list)


class ProposedAction(BaseModel):
    """Input to PortfolioEngine.simulate()."""
    company_id: str
    action: RecommendationAction
    quantity: float
    price: float
    category: Optional[HoldingCategory] = None
