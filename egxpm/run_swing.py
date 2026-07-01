"""CLI entry point for the Swing Job — daily, technical-weighted, only
WATCHLIST companies whose technicals show a live setup.

Usage:
    python -m egxpm.run_swing
    python -m egxpm.run_swing --dry-run   # Score rows only, no Recommendations

Financial Engine is NOT re-collected here — FinancialStatements only change
quarterly, so this recomputes calculate_financial_metrics() over the SAME
already-collected statements Long-Term last used. Same deterministic
input, same output — functionally identical to "reading existing
FinancialMetrics from last Long-Term Job" without a separate code path to
reconstruct FinancialMetrics from a persisted breakdown.

Unlike Long-Term, Position Sizing (Stage 9) DOES run here — it's swing-only
per the canonical pipeline — and only candidates passing the filter below
reach Reasoning, to avoid spending LLM calls on setups nobody asked about.
"""

from __future__ import annotations

import argparse
import sys

from dotenv import load_dotenv

load_dotenv()  # ANTHROPIC_API_KEY must be set before the Reasoning Layer is called

from egxpm.collectors.ensure_fresh_data import ensure_fresh_prices
from egxpm.collectors.source_health_service import SourceHealthService
from egxpm.engine.position_sizing_engine import calculate_position_size
from egxpm.engine.scoring_engine import build_score
from egxpm.engine.technical_engine import TechnicalSnapshotResult
from egxpm.llm.client import ModelConfig, generate_recommendation
from egxpm.llm.context_aggregator import HistoricalSummary, build_context
from egxpm.llm.prompts import PromptRegistry
from egxpm.persistence.company_repository import CompanyRepository
from egxpm.persistence.db import init_db
from egxpm.persistence.models import (
    Job,
    JobType,
    PortfolioSnapshot,
    PortfolioSnapshotOrigin,
    Recommendation,
    RecommendationSupersession,
    RunStatus,
    TrendSignal,
    WatchlistState,
)
from egxpm.persistence.operational_repository import OperationalRepository
from egxpm.persistence.portfolio_repository import PortfolioRepository
from egxpm.persistence.recommendation_repository import RecommendationRepository
from egxpm.scoring_pipeline import (
    HISTORY_LOOKBACK_SCORES,
    active_recommendation,
    build_peer_summaries,
    compute_allocation,
    compute_company_score,
    finalize_and_checkpoint,
    historical_accuracy_summary,
    now_iso,
)
from egxpm.shared.config import build_configuration_snapshot, load_raw_config
from egxpm.shared.exceptions import BusinessDataError

DEFAULT_DB_PATH = "data/egx.db"


def passes_swing_filter(
    breakout: bool | None, unusual_volume: bool | None, trend: TrendSignal | None,
    composite_score: float | None, threshold: float,
) -> bool:
    """(breakout OR unusual_volume OR trend=BULLISH) AND composite_score >= threshold.

    CRITICAL — do not simplify this to
    `breakout or unusual_volume or (trend == BULLISH and score >= threshold)`;
    that changes AND/OR precedence and lets a breakout/unusual-volume signal
    through regardless of score. Parenthesization here matches CLAUDE.md's
    canonical filter exactly.
    """
    if composite_score is None:
        return False
    return bool(breakout or unusual_volume or trend == TrendSignal.BULLISH) and composite_score >= threshold


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="EGX Portfolio Manager — Swing Job")
    parser.add_argument("--db-path", default=DEFAULT_DB_PATH)
    parser.add_argument("--dry-run", action="store_true", help="Produce Score rows but no Recommendations")
    parser.add_argument("--config-path", default="config.yaml")
    args = parser.parse_args(argv)

    init_db(args.db_path)

    raw_config = load_raw_config(args.config_path)
    weights = build_configuration_snapshot(raw_config, weight_profile="swing_weights")

    company_repo = CompanyRepository(args.db_path)
    operational_repo = OperationalRepository(args.db_path)
    portfolio_repo = PortfolioRepository(args.db_path)
    rec_repo = RecommendationRepository(args.db_path)
    health_service = SourceHealthService(args.db_path)

    operational_repo.save_configuration_snapshot(weights)

    job = Job(job_type=JobType.SWING)
    operational_repo.save_job(job)

    watchlist_company_ids = company_repo.list_companies_in_state(WatchlistState.WATCHLIST)
    companies = [
        c for c in company_repo.list_companies(rollout_phase="phase1") if c.company_id in watchlist_company_ids
    ]

    freshness_thresholds = raw_config.get("freshness_thresholds", {})
    swing_min_score = raw_config.get("swing_min_score_threshold", 55)

    # Stages 1-6.
    succeeded: dict[str, dict] = {}
    for company in companies:
        try:
            ensure_fresh_prices(
                company_repo, operational_repo, company.company_id, freshness_thresholds.get("prices", 2),
            )
            _financial_metrics, technical_result, score_result = compute_company_score(
                company, company_repo, weights
            )
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

    # Stage 6a barrier.
    peer_summaries = build_peer_summaries(succeeded)

    # Stage 8: portfolio state.
    prices = {cid: data["technical_result"].latest_close for cid, data in succeeded.items()}
    allocation = compute_allocation(company_repo, weights, prices, cash=0.0)
    holdings = company_repo.list_holdings()

    # Stages 6b-7 + Checkpoint A, for every company scored this run
    # (candidates and non-candidates alike — the filter below only gates
    # Reasoning/Recommendations, not whether a Score gets recorded).
    final_scores: dict[str, object] = {}
    confidence_scores: dict[str, object] = {}
    for company_id, data in succeeded.items():
        company, score, technical_result = data["company"], data["score"], data["technical_result"]
        final_score, _risk_score, confidence = finalize_and_checkpoint(
            company_id, score, technical_result, peer_summaries[company.sector], weights, raw_config,
            allocation, company_repo, operational_repo, rec_repo, health_service, job.job_id,
        )
        final_scores[company_id] = final_score
        confidence_scores[company_id] = confidence

    # Candidate pre-filter — see passes_swing_filter's docstring for why
    # this precedence matters.
    candidates = [
        company_id for company_id, data in succeeded.items()
        if passes_swing_filter(
            data["technical_result"].signals.breakout, data["technical_result"].signals.unusual_volume,
            data["technical_result"].signals.trend, final_scores[company_id].composite_score, swing_min_score,
        )
    ]

    portfolio_snapshot = PortfolioSnapshot(
        holdings_snapshot=[h.model_dump() for h in holdings], cash=0.0,
        computed_allocation=allocation.model_dump(), origin=PortfolioSnapshotOrigin.SCHEDULED,
    )
    portfolio_repo.save_snapshot(portfolio_snapshot)

    if args.dry_run:
        job.status = RunStatus.COMPLETED if job.companies_failed == 0 else RunStatus.PARTIAL
        job.completed_at = now_iso()
        operational_repo.save_job(job)
        print(f"Job {job.job_id} (swing, --dry-run): {job.companies_processed} scored, "
              f"{job.companies_failed} failed, {len(candidates)} candidates, 0 recommendations (dry-run)")
        return 0 if job.companies_failed == 0 else 1

    # Stage 9 (Position Sizing) + Stages 11-13 + Checkpoint B — candidates only.
    model_config = ModelConfig(
        model=raw_config.get("swing_model", "claude-haiku-4-5"), max_tokens=raw_config.get("max_tokens", 1000),
    )
    schema = PromptRegistry.structured_recommendation_schema()
    system_prompt = PromptRegistry.swing_system_prompt()
    recommendations_created = 0

    for company_id in candidates:
        technical_result: TechnicalSnapshotResult = succeeded[company_id]["technical_result"]
        final_score = final_scores[company_id]

        try:
            sizing = calculate_position_size(technical_result, weights, allocation)
        except BusinessDataError:
            continue

        accuracy = historical_accuracy_summary(rec_repo, company_id)
        context = build_context(
            final_score, confidence_scores[company_id], allocation, sizing,
            HistoricalSummary(
                recent_composite_scores=[
                    s.composite_score for s in company_repo.list_scores(company_id)[-HISTORY_LOOKBACK_SCORES:]
                    if s.composite_score is not None
                ],
                recommendation_win_rate=accuracy.win_rate, recommendation_sample_count=accuracy.sample_count,
            ),
            None, None,  # sector/market summaries aren't recomputed for the daily swing run
        )

        try:
            structured = generate_recommendation(context, schema, model_config, system_prompt)
        except BusinessDataError:
            continue

        recommendation = Recommendation(
            company_id=company_id, action=structured.action,
            entry_price=sizing.entry_price, stop_loss=sizing.stop_loss, take_profit=sizing.take_profit,
            position_size=sizing.position_size,
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

        prior = active_recommendation(rec_repo, company_id)
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
    job.completed_at = now_iso()
    operational_repo.save_job(job)

    print(
        f"Job {job.job_id} (swing): {job.companies_processed} scored, {job.companies_failed} failed, "
        f"{len(candidates)} candidates, {recommendations_created} recommendations created"
    )
    return 0 if job.companies_failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
