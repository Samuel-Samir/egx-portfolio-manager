"""CLI entry point for Collection Jobs.

Usage:
    python -m egxpm.run_collection --type price
    python -m egxpm.run_collection --type technical_reference
    python -m egxpm.run_collection --type technical
    python -m egxpm.run_collection --type fundamentals

A thin orchestrator: sequences calls to Collectors/Engine and Repositories.
Contains zero business logic of its own. Each company is isolated — one
company's failure is recorded on its CollectionRun and does not stop the
rest of the Job.
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone

from egxpm.collectors.collector_service import CollectorService
from egxpm.collectors.fundamentals_collector import collect_fundamentals
from egxpm.collectors.price_collector import collect_price_candles
from egxpm.collectors.technical_reference_collector import collect_technical_reference
from egxpm.engine.technical_engine import ENGINE_VERSION, calculate_technical_snapshot
from egxpm.persistence.company_repository import CompanyRepository
from egxpm.persistence.db import init_db
from egxpm.persistence.models import CollectionRun, Job, JobType, RunStatus, TechnicalSnapshot
from egxpm.persistence.operational_repository import OperationalRepository
from egxpm.shared.exceptions import BusinessDataError

DEFAULT_DB_PATH = "data/egx.db"
TRADINGVIEW_MIN_DELAY_SECONDS = 1.5
STOCKANALYSIS_MIN_DELAY_SECONDS = 2.0


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _run_price(
    company_repo: CompanyRepository, operational_repo: OperationalRepository, job: Job, period: str
) -> None:
    service = CollectorService()
    for company in company_repo.list_companies(rollout_phase="phase1"):
        run = CollectionRun(job_id=job.job_id, data_source_id="yfinance", company_id=company.company_id)
        try:
            candles = service.collect(
                lambda cid=company.company_id, rid=run.collection_run_id: collect_price_candles(
                    cid, rid, period=period
                )
            )
            company_repo.save_price_candles(candles)
            run.status = RunStatus.COMPLETED
            run.records_collected = len(candles)
            job.companies_processed += 1
        except BusinessDataError as exc:
            run.status = RunStatus.FAILED
            run.error_message = str(exc)
            job.companies_failed += 1
        run.completed_at = _now()
        operational_repo.save_collection_run(run)


def _run_technical_reference(
    company_repo: CompanyRepository, operational_repo: OperationalRepository, job: Job
) -> None:
    service = CollectorService()
    for company in company_repo.list_companies(rollout_phase="phase1"):
        run = CollectionRun(
            job_id=job.job_id, data_source_id="tradingview_ta", company_id=company.company_id
        )
        try:
            snapshot = service.collect(
                lambda cid=company.company_id, rid=run.collection_run_id: collect_technical_reference(
                    cid, rid
                ),
                min_delay_seconds=TRADINGVIEW_MIN_DELAY_SECONDS,
            )
            company_repo.save_technical_reference_snapshot(snapshot)
            run.status = RunStatus.COMPLETED
            run.records_collected = 1
            job.companies_processed += 1
        except BusinessDataError as exc:
            run.status = RunStatus.FAILED
            run.error_message = str(exc)
            job.companies_failed += 1
        run.completed_at = _now()
        operational_repo.save_collection_run(run)


def _run_technical(
    company_repo: CompanyRepository, operational_repo: OperationalRepository, job: Job, window: int
) -> None:
    for company in company_repo.list_companies(rollout_phase="phase1"):
        run = CollectionRun(
            job_id=job.job_id, data_source_id="pandas_ta_classic", company_id=company.company_id
        )
        try:
            candles = company_repo.list_price_candles(company.company_id)
            result = calculate_technical_snapshot(candles, window=window)
            snapshot = TechnicalSnapshot(
                company_id=company.company_id,
                rsi=result.indicators.rsi,
                macd=result.indicators.macd,
                macd_signal=result.indicators.macd_signal,
                sma_20=result.indicators.sma_20,
                sma_50=result.indicators.sma_50,
                sma_200=result.indicators.sma_200,
                ema_20=result.indicators.ema_20,
                ema_50=result.indicators.ema_50,
                atr=result.indicators.atr,
                bollinger_upper=result.indicators.bollinger_upper,
                bollinger_lower=result.indicators.bollinger_lower,
                bollinger_bandwidth=result.indicators.bollinger_bandwidth,
                volume_ma_20=result.indicators.volume_ma_20,
                support_level=result.indicators.support_level,
                resistance_level=result.indicators.resistance_level,
                trend=result.signals.trend,
                breakout=result.signals.breakout,
                unusual_volume=result.signals.unusual_volume,
                engine_version=ENGINE_VERSION,
                window_size=result.window_size,
                computed_through_date=result.computed_through_date,
                job_id=job.job_id,
            )
            company_repo.save_technical_snapshot(snapshot)
            run.status = RunStatus.COMPLETED
            run.records_collected = 1
            job.companies_processed += 1
        except BusinessDataError as exc:
            run.status = RunStatus.FAILED
            run.error_message = str(exc)
            job.companies_failed += 1
        run.completed_at = _now()
        operational_repo.save_collection_run(run)


def _run_fundamentals(
    company_repo: CompanyRepository, operational_repo: OperationalRepository, job: Job
) -> None:
    service = CollectorService()
    for company in company_repo.list_companies(rollout_phase="phase1"):
        run = CollectionRun(
            job_id=job.job_id, data_source_id="stockanalysis", company_id=company.company_id
        )
        try:
            statements = service.collect(
                lambda cid=company.company_id, rid=run.collection_run_id: collect_fundamentals(
                    cid, rid
                ),
                min_delay_seconds=STOCKANALYSIS_MIN_DELAY_SECONDS,
            )
            for statement in statements:
                company_repo.save_financial_statement(statement)
            run.status = RunStatus.COMPLETED
            run.records_collected = len(statements)
            job.companies_processed += 1
        except BusinessDataError as exc:
            run.status = RunStatus.FAILED
            run.error_message = str(exc)
            job.companies_failed += 1
        run.completed_at = _now()
        operational_repo.save_collection_run(run)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="EGX Portfolio Manager collection jobs")
    parser.add_argument(
        "--type", required=True,
        choices=["price", "technical_reference", "technical", "fundamentals"],
    )
    parser.add_argument("--db-path", default=DEFAULT_DB_PATH)
    parser.add_argument("--period", default="5y", help="yfinance history period (--type price only)")
    parser.add_argument("--window", type=int, default=200, help="Technical Engine window (--type technical only)")
    args = parser.parse_args(argv)

    init_db(args.db_path)  # idempotent: creates schema/seeds on first run, applies migrations after

    job_type_by_arg = {
        "price": JobType.PRICE,
        "technical_reference": JobType.TECHNICAL_REFERENCE,
        "technical": JobType.TECHNICAL,
        "fundamentals": JobType.FUNDAMENTALS,
    }

    company_repo = CompanyRepository(args.db_path)
    operational_repo = OperationalRepository(args.db_path)

    job = Job(job_type=job_type_by_arg[args.type])
    operational_repo.save_job(job)

    if args.type == "price":
        _run_price(company_repo, operational_repo, job, args.period)
    elif args.type == "technical_reference":
        _run_technical_reference(company_repo, operational_repo, job)
    elif args.type == "technical":
        _run_technical(company_repo, operational_repo, job, args.window)
    elif args.type == "fundamentals":
        _run_fundamentals(company_repo, operational_repo, job)

    job.status = RunStatus.COMPLETED if job.companies_failed == 0 else RunStatus.PARTIAL
    job.completed_at = _now()
    operational_repo.save_job(job)

    print(
        f"Job {job.job_id} ({args.type}): "
        f"{job.companies_processed} succeeded, {job.companies_failed} failed"
    )
    return 0 if job.companies_failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
