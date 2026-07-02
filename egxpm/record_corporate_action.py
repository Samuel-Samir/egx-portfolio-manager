"""CLI entry point for manually recording a Corporate Action — the one
explicitly manual-entry data source in this codebase (no automated EGX
corporate-action feed exists; Section 7.6 open item).

Usage:
    python -m egxpm.record_corporate_action --company-id COMI \\
        --action-type dividend --action-date 2026-06-01 \\
        --details '{"amount_per_share": 1.5}'

    python -m egxpm.record_corporate_action --company-id COMI \\
        --action-type split --action-date 2026-06-01 --ratio 2.0

For a price-adjusting action_type ("split" or "bonus_issue" — see
corporate_actions_collector.PRICE_ADJUSTING_ACTION_TYPES), this:
  1. Records the CorporateAction (append-only, provenance="manual").
  2. Inserts adjusted PriceCandle rows for every date strictly before the
     action_date (open/high/low/close divided by ratio, volume multiplied
     by ratio, adjusted_for_corporate_action=True) — these are NEW rows,
     never an UPDATE of history (Business Rule #7); list_price_candles'
     latest-wins dedup means callers now see the adjusted series.
  3. Recomputes and saves a fresh TechnicalSnapshot over the now-adjusted
     series (the old snapshot, computed over pre-adjustment prices, no
     longer reflects reality — e.g. every SMA/support/resistance level was
     computed on a price scale that no longer matches today's).
Every action_type (price-adjusting or not) also supersedes any currently
active Recommendation for the company via RecommendationSupersession
(superseding_event_type="corporate_action", Section 10.3) — a corporate
action invalidates the assumptions any existing Recommendation was made
under, regardless of whether it moves the price scale.

This CLI is a thin orchestrator (invariant #5): it sequences Collector,
Engine, and Repository calls and contains no business logic of its own.
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from datetime import datetime, timezone

from egxpm.collectors.corporate_actions_collector import (
    PRICE_ADJUSTING_ACTION_TYPES,
    create_corporate_action,
)
from egxpm.engine.technical_engine import calculate_technical_snapshot
from egxpm.persistence.company_repository import CompanyRepository
from egxpm.persistence.db import init_db
from egxpm.persistence.models import Job, JobType, RecommendationSupersession, RunStatus
from egxpm.persistence.operational_repository import OperationalRepository
from egxpm.persistence.recommendation_repository import RecommendationRepository
from egxpm.scoring_pipeline import active_recommendation, build_technical_snapshot_row
from egxpm.shared.exceptions import BusinessDataError

DEFAULT_DB_PATH = "data/egx.db"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _adjust_candles_before(candles, action_date: str, ratio: float, collection_run_id: str):
    adjusted = []
    for c in candles:
        if c.candle_date >= action_date:
            continue
        adjusted.append(c.model_copy(update={
            "candle_id": str(uuid.uuid4()),
            "open": c.open / ratio if c.open is not None else None,
            "high": c.high / ratio if c.high is not None else None,
            "low": c.low / ratio if c.low is not None else None,
            "close": c.close / ratio if c.close is not None else None,
            "volume": c.volume * ratio if c.volume is not None else None,
            "adjusted_for_corporate_action": True,
            "data_source_id": "manual",
            "source_version": "1",
            "fetched_at": _now(),
            "collection_run_id": collection_run_id,
        }))
    return adjusted


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="EGX Portfolio Manager — Record Corporate Action")
    parser.add_argument("--company-id", required=True)
    parser.add_argument("--action-type", required=True, help="e.g. dividend, split, bonus_issue, rights_issue")
    parser.add_argument("--action-date", required=True, help="YYYY-MM-DD")
    parser.add_argument("--ratio", type=float, default=None, help="Required for split/bonus_issue")
    parser.add_argument("--details", default="{}", help="Extra JSON details, e.g. '{\"amount_per_share\": 1.5}'")
    parser.add_argument("--db-path", default=DEFAULT_DB_PATH)
    args = parser.parse_args(argv)

    init_db(args.db_path)
    company_repo = CompanyRepository(args.db_path)
    operational_repo = OperationalRepository(args.db_path)
    rec_repo = RecommendationRepository(args.db_path)

    details = json.loads(args.details)
    if args.ratio is not None:
        details["ratio"] = args.ratio

    try:
        action = create_corporate_action(
            company_id=args.company_id, action_type=args.action_type,
            action_date=args.action_date, details=details,
        )
    except ValueError as exc:
        print(f"Invalid corporate action: {exc}")
        return 1

    job = Job(job_type=JobType.CORPORATE_ACTION)
    operational_repo.save_job(job)

    company_repo.save_corporate_action(action)
    print(f"Recorded CorporateAction {action.action_id} ({action.action_type}) for {action.company_id}.")

    if action.action_type in PRICE_ADJUSTING_ACTION_TYPES:
        candles = company_repo.list_price_candles(args.company_id)
        adjusted = _adjust_candles_before(candles, args.action_date, details["ratio"], job.job_id)
        if adjusted:
            company_repo.save_price_candles(adjusted)
            print(f"Adjusted {len(adjusted)} PriceCandle rows before {args.action_date} by ratio {details['ratio']}.")

        try:
            full_series = company_repo.list_price_candles(args.company_id)
            technical_result = calculate_technical_snapshot(full_series, window=200)
            snapshot = build_technical_snapshot_row(args.company_id, technical_result, job.job_id)
            company_repo.save_technical_snapshot(snapshot)
            print(f"Recomputed TechnicalSnapshot {snapshot.snapshot_id} over the adjusted series.")
        except BusinessDataError as exc:
            print(f"TechnicalSnapshot recompute skipped: {exc}")

    prior = active_recommendation(rec_repo, args.company_id)
    if prior is not None:
        rec_repo.save_supersession(RecommendationSupersession(
            recommendation_id=prior.recommendation_id, superseding_event_type="corporate_action",
            superseding_reference_id=action.action_id,
        ))
        print(f"Superseded active Recommendation {prior.recommendation_id} (corporate_action).")

    job.status = RunStatus.COMPLETED
    job.companies_processed = 1
    job.completed_at = _now()
    operational_repo.save_job(job)
    return 0


if __name__ == "__main__":
    sys.exit(main())
