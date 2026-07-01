"""ensure_fresh_data — shared by every Job (Long-Term, Swing, ...).

Calls CollectorService directly, NOT a nested Job: no new Job row is
created, only the CollectionRun observability every Collector already
produces. One canonical implementation, per Business Rule #10 — Jobs must
not each reimplement their own freshness-check logic.
"""

from __future__ import annotations

from datetime import date, datetime, timezone

from egxpm.collectors.collector_service import CollectorService
from egxpm.collectors.price_collector import collect_price_candles
from egxpm.persistence.company_repository import CompanyRepository
from egxpm.persistence.models import CollectionRun, RunStatus
from egxpm.persistence.operational_repository import OperationalRepository
from egxpm.shared.exceptions import BusinessDataError


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_fresh_prices(
    company_repo: CompanyRepository,
    operational_repo: OperationalRepository,
    company_id: str,
    stale_after_days: float,
) -> None:
    """Refreshes company_id's price candles via yfinance if the latest one
    is older than stale_after_days. No-op if already fresh."""
    candles = company_repo.list_price_candles(company_id)
    latest_date = candles[-1].candle_date if candles else None
    if latest_date is not None:
        age_days = (date.today() - date.fromisoformat(latest_date)).days
        if age_days <= stale_after_days:
            return

    run = CollectionRun(data_source_id="yfinance", company_id=company_id)
    service = CollectorService()
    try:
        new_candles = service.collect(
            lambda: collect_price_candles(company_id, run.collection_run_id, period="1mo")
        )
        company_repo.save_price_candles(new_candles)
        run.status = RunStatus.COMPLETED
        run.records_collected = len(new_candles)
    except BusinessDataError as exc:
        run.status = RunStatus.FAILED
        run.error_message = str(exc)
    run.completed_at = _now()
    operational_repo.save_collection_run(run)


def freshness_fraction(latest_date: str | None, threshold_days: float) -> float | None:
    """Normalizes an artifact's age into [0,1] (1.0 = fresh) for the
    Confidence Engine's FreshnessMetadata — linear decay past the
    threshold, floored at 0.0."""
    if latest_date is None:
        return None
    try:
        latest = datetime.fromisoformat(latest_date).date()
    except ValueError:
        latest = datetime.fromisoformat(latest_date[:10]).date()
    age_days = (date.today() - latest).days
    if age_days <= threshold_days:
        return 1.0
    return max(0.0, 1.0 - (age_days - threshold_days) / threshold_days)
