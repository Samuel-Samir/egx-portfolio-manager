"""CLI entry point for the Long-Term Job — the full 14-stage canonical
pipeline (Section 6), run weekly against every WATCHLIST company.

Usage:
    python -m egxpm.run_longterm
    python -m egxpm.run_longterm --dry-run   # Score rows only, no Recommendations

A thin orchestrator: sequences calls to Collectors, Engines, the Reasoning
Layer, and Repositories. Per-company failure isolation is mandatory —
BusinessDataError is caught and logged per company; ValueError surfaces
loudly as a bug, per the architecture doc's Job Design Principles.
"""

from __future__ import annotations

import argparse
import statistics
import sys
from datetime import datetime, timezone

from dotenv import load_dotenv

load_dotenv()  # ANTHROPIC_API_KEY must be set before the Reasoning Layer is called

from egxpm.collectors.ensure_fresh_data import ensure_fresh_prices, freshness_fraction
from egxpm.collectors.source_health_service import SourceHealthService
from egxpm.engine.confidence_engine import (
    FreshnessMetadata,
    HistoricalAccuracySummary,
    SourceHealthSummary,
    SourceQualitySummary,
    calculate_confidence,
)
from egxpm.engine.financial_engine import calculate_financial_metrics
from egxpm.engine.risk_engine import (
    HistoricalScoreSummary,
    LiquiditySummary,
    build_sector_peer_summary,
    calculate_risk_score,
)
from egxpm.engine.scoring_engine import (
    aggregate_market_summary,
    aggregate_sector_summary,
    assemble_composite_score,
    build_score,
    calculate_score,
)
from egxpm.engine.technical_engine import ENGINE_VERSION as TECHNICAL_ENGINE_VERSION
from egxpm.engine.technical_engine import calculate_technical_snapshot
from egxpm.llm.client import ModelConfig, generate_recommendation
from egxpm.llm.context_aggregator import HistoricalSummary, build_context
from egxpm.llm.prompts import PromptRegistry
from egxpm.persistence.company_repository import CompanyRepository
from egxpm.persistence.db import init_db
from egxpm.persistence.models import (
    AllocationReport,
    Job,
    JobType,
    PortfolioSnapshot,
    PortfolioSnapshotOrigin,
    Recommendation,
    RecommendationSupersession,
    RunStatus,
    SourceQuality,
    TechnicalSnapshot,
    WatchlistState,
)
from egxpm.persistence.operational_repository import OperationalRepository
from egxpm.persistence.portfolio_repository import PortfolioRepository
from egxpm.persistence.recommendation_repository import RecommendationRepository
from egxpm.shared.allocation_calculator import calculate as calculate_allocation
from egxpm.shared.config import build_configuration_snapshot, load_raw_config
from egxpm.shared.exceptions import BusinessDataError

DEFAULT_DB_PATH = "data/egx.db"
LIQUIDITY_LOOKBACK_DAYS = 20
HISTORY_LOOKBACK_SCORES = 8

# Position Sizing (Stage 9) is explicitly swing-only in the canonical
# pipeline; the Long-Term Job never invokes it. Long-term Recommendations
# carry an entry_price for reference but no ATR-based stop/target/size —
# the architecture doesn't specify a long-term position-sizing formula
# (only the swing ATR-based one), so this deliberately isn't fabricated.


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _avg_daily_volume_egp(company_repo: CompanyRepository, company_id: str) -> float | None:
    candles = company_repo.list_price_candles(company_id)[-LIQUIDITY_LOOKBACK_DAYS:]
    values = [c.volume * c.close for c in candles if c.volume is not None and c.close is not None]
    return sum(values) / len(values) if values else None


def _historical_score_summary(company_repo: CompanyRepository, company_id: str) -> HistoricalScoreSummary:
    past_scores = company_repo.list_scores(company_id)[-HISTORY_LOOKBACK_SCORES:]
    composites = [s.composite_score for s in past_scores if s.composite_score is not None]
    std_dev = statistics.pstdev(composites) if len(composites) >= 2 else None
    return HistoricalScoreSummary(std_dev=std_dev)


def _historical_accuracy_summary(rec_repo: RecommendationRepository, company_id: str) -> HistoricalAccuracySummary:
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


def _active_recommendation(rec_repo: RecommendationRepository, company_id: str) -> Recommendation | None:
    """Most recent Recommendation for company_id that hasn't already been superseded."""
    recommendations = sorted(rec_repo.list_recommendations(company_id), key=lambda r: r.created_at)
    if not recommendations:
        return None
    latest = recommendations[-1]
    return latest if not rec_repo.list_supersessions(latest.recommendation_id) else None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="EGX Portfolio Manager — Long-Term Job")
    parser.add_argument("--db-path", default=DEFAULT_DB_PATH)
    parser.add_argument("--dry-run", action="store_true", help="Produce Score rows but no Recommendations")
    parser.add_argument("--config-path", default="config.yaml")
    args = parser.parse_args(argv)

    init_db(args.db_path)

    raw_config = load_raw_config(args.config_path)
    weights = build_configuration_snapshot(raw_config, weight_profile="longterm_weights")

    company_repo = CompanyRepository(args.db_path)
    operational_repo = OperationalRepository(args.db_path)
    portfolio_repo = PortfolioRepository(args.db_path)
    rec_repo = RecommendationRepository(args.db_path)
    health_service = SourceHealthService(args.db_path)

    operational_repo.save_configuration_snapshot(weights)

    job = Job(job_type=JobType.LONGTERM)
    operational_repo.save_job(job)

    watchlist_company_ids = company_repo.list_companies_in_state(WatchlistState.WATCHLIST)
    companies = [
        c for c in company_repo.list_companies(rollout_phase="phase1") if c.company_id in watchlist_company_ids
    ]

    freshness_thresholds = raw_config.get("freshness_thresholds", {})
    longterm_min_score = raw_config.get("longterm_min_score_threshold", 60)

    # ------------------------------------------------------------
    # Stages 1-6: per-company Collection freshness + Financial/Technical/
    # News Engines + Scoring Engine. Each company is fully isolated.
    # ------------------------------------------------------------
    succeeded: dict[str, dict] = {}
    for company in companies:
        try:
            ensure_fresh_prices(
                company_repo, operational_repo, company.company_id,
                freshness_thresholds.get("prices", 2),
            )
            statements = company_repo.list_financial_statements(company.company_id, period_type="quarterly")
            financial_metrics = calculate_financial_metrics(statements, company.statement_schema)

            candles = company_repo.list_price_candles(company.company_id)
            technical_result = calculate_technical_snapshot(candles, window=200)

            news = company_repo.list_news_items(company.company_id)

            score_result = calculate_score(financial_metrics, technical_result, news, weights)
            score = build_score(
                score_result, company_id=company.company_id,
                config_snapshot_id=weights.config_snapshot_id, job_id=job.job_id,
            )
            succeeded[company.company_id] = {
                "company": company, "score": score, "technical_result": technical_result,
            }
            job.companies_processed += 1
        except BusinessDataError:
            job.companies_failed += 1

    # ------------------------------------------------------------
    # Stage 6a: synchronization barrier — sector D/E peer aggregation.
    # A company absent from `succeeded` is absent from every peer set.
    # ------------------------------------------------------------
    sectors: dict[str, list[str]] = {}
    for company_id, data in succeeded.items():
        sectors.setdefault(data["company"].sector, []).append(company_id)
    peer_summaries = {
        sector: build_sector_peer_summary(
            sector,
            [succeeded[cid]["score"].financial_breakdown.get("debt_to_equity", {}).get("value") for cid in ids],
        )
        for sector, ids in sectors.items()
    }

    # ------------------------------------------------------------
    # Portfolio state (Stage 8), computed once, shared by every company
    # this run. No real Holding data has been entered yet (known
    # limitation) — an empty portfolio is a valid, honest state, not a bug.
    # ------------------------------------------------------------
    holdings = company_repo.list_holdings()
    prices = {cid: data["technical_result"].latest_close for cid, data in succeeded.items()}
    cash = 0.0
    try:
        allocation = calculate_allocation(holdings, prices, cash, weights)
    except ValueError:
        allocation = AllocationReport(total_value=cash, cash=cash)

    final_scores: dict[str, object] = {}
    confidence_scores: dict[str, object] = {}

    # ------------------------------------------------------------
    # Stages 6b-7 + Checkpoint A: Risk Engine, composite assembly,
    # Confidence Engine, then the atomic 4-table write.
    # ------------------------------------------------------------
    for company_id, data in succeeded.items():
        company, score, technical_result = data["company"], data["score"], data["technical_result"]

        risk_score = calculate_risk_score(
            score, peer_summaries[company.sector], _historical_score_summary(company_repo, company_id),
            LiquiditySummary(
                avg_daily_volume_egp=_avg_daily_volume_egp(company_repo, company_id),
                hypothetical_position_size_egp=(
                    raw_config.get("max_position_pct", 0.0) * allocation.total_value
                ),
            ),
            weights,
        )
        final_score = assemble_composite_score(score, risk_score, weights)

        latest_statement = company_repo.list_financial_statements(company_id, period_type="quarterly")
        latest_news = company_repo.list_news_items(company_id)
        freshness = FreshnessMetadata(
            prices_freshness=freshness_fraction(technical_result.computed_through_date, freshness_thresholds.get("prices", 2)),
            technicals_freshness=freshness_fraction(technical_result.computed_through_date, freshness_thresholds.get("technicals", 2)),
            fundamentals_freshness=freshness_fraction(
                max((s.period_end for s in latest_statement), default=None), freshness_thresholds.get("fundamentals", 92),
            ),
            news_freshness=freshness_fraction(
                max((n.published_at for n in latest_news), default=None), freshness_thresholds.get("news", 1),
            ),
        )
        confidence = calculate_confidence(
            final_score, freshness,
            SourceQualitySummary(source_qualities=[SourceQuality.SCRAPED, SourceQuality.INTERNAL, SourceQuality.SCRAPED]),
            SourceHealthSummary(success_rate=health_service.get_source_health("yfinance")),
            _historical_accuracy_summary(rec_repo, company_id),
        )

        technical_snapshot = TechnicalSnapshot(
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
            computed_through_date=technical_result.computed_through_date, job_id=job.job_id,
        )
        company_repo.save_checkpoint_a(technical_snapshot, final_score, risk_score, confidence)

        final_scores[company_id] = final_score
        confidence_scores[company_id] = confidence

    # ------------------------------------------------------------
    # Dashboard-facing Sector/Market aggregation (post-composite).
    # ------------------------------------------------------------
    sector_summaries = {}
    for sector, ids in sectors.items():
        try:
            sector_summaries[sector] = aggregate_sector_summary(
                sector, [final_scores[cid] for cid in ids], job_id=job.job_id
            )
        except BusinessDataError:
            continue
    if sector_summaries:
        market_summary = aggregate_market_summary(list(sector_summaries.values()), job_id=job.job_id)
    else:
        market_summary = None

    # ------------------------------------------------------------
    # Stage 10: PortfolioSnapshot, captured before Recommendation
    # assembly — origin="scheduled" for a cron-triggered Long-Term run.
    # ------------------------------------------------------------
    portfolio_snapshot = PortfolioSnapshot(
        holdings_snapshot=[h.model_dump() for h in holdings], cash=cash,
        computed_allocation=allocation.model_dump(), origin=PortfolioSnapshotOrigin.SCHEDULED,
    )
    portfolio_repo.save_snapshot(portfolio_snapshot)

    if args.dry_run:
        job.status = RunStatus.COMPLETED if job.companies_failed == 0 else RunStatus.PARTIAL
        job.completed_at = _now()
        operational_repo.save_job(job)
        print(f"Job {job.job_id} (longterm, --dry-run): {job.companies_processed} scored, "
              f"{job.companies_failed} failed, 0 recommendations (dry-run)")
        return 0 if job.companies_failed == 0 else 1

    # ------------------------------------------------------------
    # Stages 11-13 + Checkpoint B: Context Aggregation, Reasoning,
    # Recommendation assembly, RecommendationSupersession.
    # ------------------------------------------------------------
    model_config = ModelConfig(
        model=raw_config.get("longterm_model", "claude-haiku-4-5"),
        max_tokens=raw_config.get("max_tokens", 1000),
    )
    schema = PromptRegistry.structured_recommendation_schema()
    system_prompt = PromptRegistry.longterm_system_prompt()
    recommendations_created = 0

    for company_id, final_score in final_scores.items():
        if final_score.composite_score is None or final_score.composite_score < longterm_min_score:
            continue

        context = build_context(
            final_score, confidence_scores[company_id], allocation, None,
            HistoricalSummary(
                recent_composite_scores=[
                    s.composite_score for s in company_repo.list_scores(company_id)[-HISTORY_LOOKBACK_SCORES:]
                    if s.composite_score is not None
                ],
                recommendation_win_rate=_historical_accuracy_summary(rec_repo, company_id).win_rate,
                recommendation_sample_count=_historical_accuracy_summary(rec_repo, company_id).sample_count,
            ),
            sector_summaries.get(succeeded[company_id]["company"].sector), market_summary,
        )

        try:
            structured = generate_recommendation(context, schema, model_config, system_prompt)
        except BusinessDataError:
            continue

        recommendation = Recommendation(
            company_id=company_id, action=structured.action,
            entry_price=succeeded[company_id]["technical_result"].latest_close,
            confidence_id=confidence_scores[company_id].confidence_id,
            config_snapshot_id=weights.config_snapshot_id,
            portfolio_snapshot_id=portfolio_snapshot.snapshot_id,
            frozen_package={
                "reasoning": structured.reasoning, "key_risks": structured.key_risks,
                "rejected_alternatives": structured.rejected_alternatives,
                "confidence_commentary": structured.confidence_commentary,
                "curated_context": context.model_dump(),
                "prompt_version": PromptRegistry.version(), "model": model_config.model,
            },
            job_id=job.job_id,
        )

        prior = _active_recommendation(rec_repo, company_id)
        supersession = (
            RecommendationSupersession(
                recommendation_id=prior.recommendation_id, superseding_event_type="new_score_computed",
                superseding_reference_id=recommendation.recommendation_id,
            )
            if prior is not None else None
        )
        rec_repo.save_checkpoint_b(recommendation, supersession)
        recommendations_created += 1

    job.status = RunStatus.COMPLETED if job.companies_failed == 0 else RunStatus.PARTIAL
    job.completed_at = _now()
    operational_repo.save_job(job)

    print(
        f"Job {job.job_id} (longterm): {job.companies_processed} scored, {job.companies_failed} failed, "
        f"{recommendations_created} recommendations created"
    )
    return 0 if job.companies_failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
