from datetime import datetime, timedelta, timezone

import pytest

from egxpm.collectors.source_health_service import SourceHealthService
from egxpm.persistence.models import CollectionRun, RunStatus
from egxpm.persistence.operational_repository import OperationalRepository


def _run(data_source_id, status, days_ago):
    started_at = (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat()
    return CollectionRun(data_source_id=data_source_id, status=status, started_at=started_at)


def test_computes_success_rate_from_recent_runs(db_path):
    repo = OperationalRepository(db_path)
    for run in [
        _run("yfinance", RunStatus.COMPLETED, days_ago=1),
        _run("yfinance", RunStatus.COMPLETED, days_ago=2),
        _run("yfinance", RunStatus.FAILED, days_ago=3),
        _run("yfinance", RunStatus.COMPLETED, days_ago=4),
    ]:
        repo.save_collection_run(run)

    service = SourceHealthService(db_path)
    assert service.get_source_health("yfinance") == pytest.approx(0.75)


def test_excludes_runs_older_than_window(db_path):
    repo = OperationalRepository(db_path)
    repo.save_collection_run(_run("yfinance", RunStatus.FAILED, days_ago=45))
    repo.save_collection_run(_run("yfinance", RunStatus.COMPLETED, days_ago=1))

    service = SourceHealthService(db_path, window_days=30)
    assert service.get_source_health("yfinance") == pytest.approx(1.0)


def test_returns_none_when_no_runs_in_window(db_path):
    service = SourceHealthService(db_path)
    assert service.get_source_health("yfinance") is None


def test_caches_result_within_ttl(db_path):
    repo = OperationalRepository(db_path)
    repo.save_collection_run(_run("yfinance", RunStatus.COMPLETED, days_ago=1))

    service = SourceHealthService(db_path, ttl_seconds=3600)
    first = service.get_source_health("yfinance")
    assert first == pytest.approx(1.0)

    # New failing runs appear, but within TTL the cached value should still be returned.
    repo.save_collection_run(_run("yfinance", RunStatus.FAILED, days_ago=0))
    second = service.get_source_health("yfinance")
    assert second == pytest.approx(1.0)


def test_recomputes_after_ttl_expires(db_path, monkeypatch):
    repo = OperationalRepository(db_path)
    repo.save_collection_run(_run("yfinance", RunStatus.COMPLETED, days_ago=1))

    service = SourceHealthService(db_path, ttl_seconds=0.01)
    first = service.get_source_health("yfinance")
    assert first == pytest.approx(1.0)

    repo.save_collection_run(_run("yfinance", RunStatus.FAILED, days_ago=0))
    import time
    time.sleep(0.02)
    second = service.get_source_health("yfinance")
    assert second == pytest.approx(0.5)


def test_different_data_sources_cached_independently(db_path):
    repo = OperationalRepository(db_path)
    repo.save_collection_run(_run("yfinance", RunStatus.COMPLETED, days_ago=1))
    repo.save_collection_run(_run("mubasher", RunStatus.FAILED, days_ago=1))

    service = SourceHealthService(db_path)
    assert service.get_source_health("yfinance") == pytest.approx(1.0)
    assert service.get_source_health("mubasher") == pytest.approx(0.0)
