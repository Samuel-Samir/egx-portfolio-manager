"""Shared Stage 3-7 + Checkpoint A pipeline, used by both run_longterm.py
and run_swing.py — one canonical implementation of "score a company and
persist Checkpoint A" (Business Rule #10), not duplicated per Job.

Each Job still owns its own weight profile, candidate filtering, Position
Sizing (swing only), and Reasoning/Recommendation assembly — only the
common scoring machinery lives here.
"""

from __future__ import annotations

import statistics
from datetime import datetime, timezone

from egxpm.collectors.ensure_fresh_data import freshness_fraction
from egxpm.collectors.source_health_service import SourceHealthService
from egxpm.engine.confidence_engine import (
    ConfidenceScore,
    FreshnessMetadata,
    HistoricalAccuracySummary,
    SourceHealthSummary,
    SourceQualitySummary,
    calculate_confidence,
)
from egxpm.engine.financial_engine import FinancialMetrics, calculate_financial_metrics
from egxpm.engine.risk_engine import (
    HistoricalScoreSummary,
    LiquiditySummary,
    RiskScore,
    SectorPeerSummary,
    build_sector_peer_summary,
    calculate_risk_score,
)
from egxpm.engine.scoring_engine import ScoreResult, assemble_composite_score, build_score, calculate_score
from egxpm.engine.technical_engine import ENGINE_VERSION as TECHNICAL_ENGINE_VERSION
from egxpm.engine.technical_engine import TechnicalSnapshotResult, calculate_technical_snapshot
from egxpm.persistence.company_repository import CompanyRepository
from egxpm.persistence.models import (
    AllocationReport,
    Company,
    ConfigurationSnapshot,
    Recommendation,
    Score,
    SourceQuality,
    TechnicalSnapshot,
)
from egxpm.persistence.operational_repository import OperationalRepository
from egxpm.persistence.recommendation_repository import RecommendationRepository
from egxpm.shared.allocation_calculator import calculate as calculate_allocation
from egxpm.shared.exceptions import InsufficientDataError

LIQUIDITY_LOOKBACK_DAYS = 20
HISTORY_LOOKBACK_SCORES = 8

# Which data sources' tiers feed a Score, for the Confidence Engine's
# SourceQualitySummary — fundamentals (StockAnalysis, scraped), technicals
# (pandas-ta-classic, computed internally), news (Mubasher, scraped).
SCORE_SOURCE_QUALITIES = [SourceQuality.SCRAPED, SourceQuality.INTERNAL, SourceQuality.SCRAPED]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def compute_company_score(
    company: Company, company_repo: CompanyRepository, weights: ConfigurationSnapshot,
) -> tuple[FinancialMetrics, TechnicalSnapshotResult, ScoreResult]:
    """Stages 3-6: Financial + Technical Engines, current NewsItems, Scoring
    Engine. Raises BusinessDataError on any stage's failure — the caller
    is responsible for per-company isolation.
    """
    statements = company_repo.list_financial_statements(company.company_id, period_type="quarterly")
    financial_metrics = calculate_financial_metrics(statements, company.statement_schema)

    candles = company_repo.list_price_candles(company.company_id)
    technical_result = calculate_technical_snapshot(candles, window=200)

    news = company_repo.list_news_items(company.company_id)

    score_result = calculate_score(financial_metrics, technical_result, news, weights)
    return financial_metrics, technical_result, score_result


def build_peer_summaries(succeeded: dict[str, dict]) -> dict[str, SectorPeerSummary]:
    """Stage 6a barrier: sector D/E peer aggregation from every company
    that reached Stage 6 successfully this run (`succeeded`, keyed by
    company_id, each value must have "company" and "score" keys)."""
    sectors: dict[str, list[str]] = {}
    for company_id, data in succeeded.items():
        sectors.setdefault(data["company"].sector, []).append(company_id)
    return {
        sector: build_sector_peer_summary(
            sector,
            [succeeded[cid]["score"].financial_breakdown.get("debt_to_equity", {}).get("value") for cid in ids],
        )
        for sector, ids in sectors.items()
    }


def compute_allocation(
    company_repo: CompanyRepository, weights: ConfigurationSnapshot, prices: dict[str, float], cash: float = 0.0,
) -> AllocationReport:
    """Stage 8: current portfolio allocation.

    `prices` (this run's freshly computed Technical Engine results, keyed
    by company_id) is supplemented with each held company's latest known
    price as a fallback before calling AllocationCalculator — a holding
    whose Technical Engine computation failed THIS run (e.g. a transient
    InsufficientDataError elsewhere in the pipeline) still has a real, if
    slightly stale, price on record and must not silently drop out of the
    portfolio's total_value. Only a holding with no price history at all
    still leaves AllocationCalculator.calculate() missing a price for it —
    a genuine data gap, surfaced as an empty/zero AllocationReport (not
    silently dropping that holding from the total) since no real Holding
    data exists in production yet and this path has never been exercised
    against real data.
    """
    holdings = company_repo.list_holdings()
    effective_prices = dict(prices)
    missing = [h.company_id for h in holdings if h.company_id not in effective_prices]
    if missing:
        effective_prices.update(company_repo.get_latest_prices(missing))
    try:
        return calculate_allocation(holdings, effective_prices, cash, weights)
    except InsufficientDataError:
        return AllocationReport(total_value=cash, cash=cash)


def avg_daily_volume_egp(company_repo: CompanyRepository, company_id: str) -> float | None:
    candles = company_repo.list_price_candles(company_id)[-LIQUIDITY_LOOKBACK_DAYS:]
    values = [c.volume * c.close for c in candles if c.volume is not None and c.close is not None]
    return sum(values) / len(values) if values else None


def historical_score_summary(company_repo: CompanyRepository, company_id: str) -> HistoricalScoreSummary:
    past_scores = company_repo.list_scores(company_id)[-HISTORY_LOOKBACK_SCORES:]
    composites = [s.composite_score for s in past_scores if s.composite_score is not None]
    std_dev = statistics.pstdev(composites) if len(composites) >= 2 else None
    return HistoricalScoreSummary(std_dev=std_dev)


def historical_accuracy_summary(rec_repo: RecommendationRepository, company_id: str) -> HistoricalAccuracySummary:
    recommendations = rec_repo.list_recommendations(company_id)
    outcomes = [
        outcome for rec in recommendations
        for outcome in rec_repo.list_outcomes(rec.recommendation_id)
        if outcome.is_final and outcome.target_hit is not None
    ]
    if not outcomes:
        return HistoricalAccuracySummary(sample_count=0, win_rate=None)
    win_rate = sum(1 for o in outcomes if o.target_hit) / len(outcomes)
    return HistoricalAccuracySummary(sample_count=len(outcomes), win_rate=win_rate)


def active_recommendation(rec_repo: RecommendationRepository, company_id: str) -> Recommendation | None:
    """Most recent Recommendation for company_id that hasn't already been superseded."""
    recommendations = sorted(rec_repo.list_recommendations(company_id), key=lambda r: r.created_at)
    if not recommendations:
        return None
    latest = recommendations[-1]
    return latest if not rec_repo.list_supersessions(latest.recommendation_id) else None


def build_technical_snapshot_row(
    company_id: str, technical_result: TechnicalSnapshotResult, job_id: str,
) -> TechnicalSnapshot:
    """Maps the pure Engine's TechnicalSnapshotResult onto the persisted,
    flat TechnicalSnapshot row (adds company_id/job_id/engine_version)."""
    return TechnicalSnapshot(
        company_id=company_id,
        rsi=technical_result.indicators.rsi, macd=technical_result.indicators.macd,
        macd_signal=technical_result.indicators.macd_signal, sma_20=technical_result.indicators.sma_20,
        sma_50=technical_result.indicators.sma_50, sma_200=technical_result.indicators.sma_200,
        ema_20=technical_result.indicators.ema_20, ema_50=technical_result.indicators.ema_50,
        atr=technical_result.indicators.atr, bollinger_upper=technical_result.indicators.bollinger_upper,
        bollinger_lower=technical_result.indicators.bollinger_lower,
        bollinger_bandwidth=technical_result.indicators.bollinger_bandwidth,
        volume_ma_20=technical_result.indicators.volume_ma_20, support_level=technical_result.indicators.support_level,
        resistance_level=technical_result.indicators.resistance_level, trend=technical_result.signals.trend,
        breakout=technical_result.signals.breakout, unusual_volume=technical_result.signals.unusual_volume,
        engine_version=TECHNICAL_ENGINE_VERSION, window_size=technical_result.window_size,
        computed_through_date=technical_result.computed_through_date, job_id=job_id,
    )


def finalize_and_checkpoint(
    company_id: str,
    score: Score,
    technical_result: TechnicalSnapshotResult,
    peer_summary: SectorPeerSummary,
    weights: ConfigurationSnapshot,
    raw_config: dict,
    allocation: AllocationReport,
    company_repo: CompanyRepository,
    operational_repo: OperationalRepository,
    rec_repo: RecommendationRepository,
    health_service: SourceHealthService,
    job_id: str,
) -> tuple[Score, RiskScore, ConfidenceScore]:
    """Stages 6b (Risk) - 7 (Confidence) + Checkpoint A (atomic write)."""
    freshness_thresholds = raw_config.get("freshness_thresholds", {})

    risk_score = calculate_risk_score(
        score, peer_summary, historical_score_summary(company_repo, company_id),
        LiquiditySummary(
            avg_daily_volume_egp=avg_daily_volume_egp(company_repo, company_id),
            hypothetical_position_size_egp=raw_config.get("max_position_pct", 0.0) * allocation.total_value,
        ),
        weights,
    )
    final_score = assemble_composite_score(score, risk_score, weights)

    latest_statements = company_repo.list_financial_statements(company_id, period_type="quarterly")
    latest_news = company_repo.list_news_items(company_id)
    freshness = FreshnessMetadata(
        prices_freshness=freshness_fraction(technical_result.computed_through_date, freshness_thresholds.get("prices", 2)),
        technicals_freshness=freshness_fraction(technical_result.computed_through_date, freshness_thresholds.get("technicals", 2)),
        fundamentals_freshness=freshness_fraction(
            max((s.period_end for s in latest_statements), default=None), freshness_thresholds.get("fundamentals", 92),
        ),
        news_freshness=freshness_fraction(
            max((n.published_at for n in latest_news), default=None), freshness_thresholds.get("news", 1),
        ),
    )
    confidence = calculate_confidence(
        final_score, freshness, SourceQualitySummary(source_qualities=SCORE_SOURCE_QUALITIES),
        SourceHealthSummary(success_rate=health_service.get_source_health("yfinance")),
        historical_accuracy_summary(rec_repo, company_id),
    )

    technical_snapshot = build_technical_snapshot_row(company_id, technical_result, job_id)
    company_repo.save_checkpoint_a(technical_snapshot, final_score, risk_score, confidence)

    return final_score, risk_score, confidence
