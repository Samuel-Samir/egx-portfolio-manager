"""SourceHealthService — rolling 30-day CollectionRun success rate, 1-hour
TTL cached (architecture doc Section 7.4/14.3).

Not a separate collection job and no new table: derived on demand from
CollectionRun history already written by every Collector. Feeds the
Confidence Engine's SourceHealthSummary input; Orchestration calls this
service and hands the result to the Engine — the Engine itself never
touches Persistence or a cache.
"""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone

from egxpm.persistence.models import RunStatus
from egxpm.persistence.operational_repository import OperationalRepository

CACHE_TTL_SECONDS = 3600
SOURCE_HEALTH_WINDOW_DAYS = 30


class SourceHealthService:
    def __init__(
        self,
        db_path: str,
        ttl_seconds: float = CACHE_TTL_SECONDS,
        window_days: int = SOURCE_HEALTH_WINDOW_DAYS,
    ):
        self.db_path = db_path
        self.ttl_seconds = ttl_seconds
        self.window_days = window_days
        self._cache: dict[str, tuple[float, float | None]] = {}

    def get_source_health(self, data_source_id: str) -> float | None:
        """Rolling `window_days` CollectionRun success rate for data_source_id.

        Returns None if there are no CollectionRuns in the window at all
        (unknown, not assumed healthy) — the Confidence Engine's neutral
        (0.5) default applies from there, same as its other missing-data cases.
        """
        now = time.monotonic()
        cached = self._cache.get(data_source_id)
        if cached is not None and (now - cached[0]) < self.ttl_seconds:
            return cached[1]

        success_rate = self._compute_success_rate(data_source_id)
        self._cache[data_source_id] = (now, success_rate)
        return success_rate

    def _compute_success_rate(self, data_source_id: str) -> float | None:
        repo = OperationalRepository(self.db_path)
        cutoff = (datetime.now(timezone.utc) - timedelta(days=self.window_days)).isoformat()
        runs = [
            run for run in repo.list_collection_runs(data_source_id=data_source_id)
            if run.started_at >= cutoff
        ]
        if not runs:
            return None
        successes = sum(1 for run in runs if run.status == RunStatus.COMPLETED)
        return successes / len(runs)
