"""Persistence for operational/observability entities: Job, CollectionRun,
DataSource, and ConfigurationSnapshot (versioned scoring/risk/allocation config).
"""

from __future__ import annotations

from typing import Optional

from egxpm.persistence import _util
from egxpm.persistence.db import connect
from egxpm.persistence.models import (
    CollectionRun,
    ConfigurationSnapshot,
    DataSource,
    Job,
)


class OperationalRepository:
    def __init__(self, db_path: str):
        self.db_path = db_path

    # ------------------------------------------------------------
    # DataSource
    # ------------------------------------------------------------

    def save_data_source(self, source: DataSource) -> None:
        with connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO data_sources
                    (data_source_id, name, source_type, collection_method, source_quality,
                     is_canonical_for, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(data_source_id) DO UPDATE SET
                    name = excluded.name,
                    source_type = excluded.source_type,
                    collection_method = excluded.collection_method,
                    source_quality = excluded.source_quality,
                    is_canonical_for = excluded.is_canonical_for,
                    updated_at = excluded.updated_at
                """,
                (
                    source.data_source_id, source.name, source.source_type.value,
                    source.collection_method.value, source.source_quality.value,
                    _util.dumps(source.is_canonical_for) if source.is_canonical_for is not None else None,
                    source.created_at, source.updated_at,
                ),
            )

    def get_data_source(self, data_source_id: str) -> Optional[DataSource]:
        with connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT * FROM data_sources WHERE data_source_id = ?", (data_source_id,)
            ).fetchone()
            if not row:
                return None
            d = _util.row_to_dict(row)
            d["is_canonical_for"] = _util.loads(d["is_canonical_for"], None)
            return DataSource(**d)

    def list_data_sources(self) -> list[DataSource]:
        with connect(self.db_path) as conn:
            rows = conn.execute("SELECT * FROM data_sources ORDER BY data_source_id").fetchall()
            out = []
            for r in rows:
                d = _util.row_to_dict(r)
                d["is_canonical_for"] = _util.loads(d["is_canonical_for"], None)
                out.append(DataSource(**d))
            return out

    # ------------------------------------------------------------
    # Job (immutable execution record)
    # ------------------------------------------------------------

    def save_job(self, job: Job) -> None:
        with connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO jobs
                    (job_id, job_type, started_at, completed_at, status,
                     companies_processed, companies_failed, error_summary)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(job_id) DO UPDATE SET
                    completed_at = excluded.completed_at,
                    status = excluded.status,
                    companies_processed = excluded.companies_processed,
                    companies_failed = excluded.companies_failed,
                    error_summary = excluded.error_summary
                """,
                (
                    job.job_id, job.job_type.value, job.started_at, job.completed_at,
                    job.status.value, job.companies_processed, job.companies_failed,
                    job.error_summary,
                ),
            )

    def get_job(self, job_id: str) -> Optional[Job]:
        with connect(self.db_path) as conn:
            row = conn.execute("SELECT * FROM jobs WHERE job_id = ?", (job_id,)).fetchone()
            return Job(**_util.row_to_dict(row)) if row else None

    def list_jobs(self, job_type: Optional[str] = None) -> list[Job]:
        query = "SELECT * FROM jobs WHERE 1=1"
        params: list[str] = []
        if job_type is not None:
            query += " AND job_type = ?"
            params.append(job_type)
        query += " ORDER BY started_at DESC"
        with connect(self.db_path) as conn:
            rows = conn.execute(query, params).fetchall()
            return [Job(**_util.row_to_dict(r)) for r in rows]

    # ------------------------------------------------------------
    # CollectionRun (immutable, atomic observability unit)
    # ------------------------------------------------------------

    def save_collection_run(self, run: CollectionRun) -> None:
        with connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO collection_runs
                    (collection_run_id, job_id, data_source_id, company_id, started_at,
                     completed_at, status, records_collected, error_message)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(collection_run_id) DO UPDATE SET
                    completed_at = excluded.completed_at,
                    status = excluded.status,
                    records_collected = excluded.records_collected,
                    error_message = excluded.error_message
                """,
                (
                    run.collection_run_id, run.job_id, run.data_source_id, run.company_id,
                    run.started_at, run.completed_at, run.status.value,
                    run.records_collected, run.error_message,
                ),
            )

    def get_collection_run(self, collection_run_id: str) -> Optional[CollectionRun]:
        with connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT * FROM collection_runs WHERE collection_run_id = ?",
                (collection_run_id,),
            ).fetchone()
            return CollectionRun(**_util.row_to_dict(row)) if row else None

    def list_collection_runs(
        self, data_source_id: Optional[str] = None, job_id: Optional[str] = None
    ) -> list[CollectionRun]:
        query = "SELECT * FROM collection_runs WHERE 1=1"
        params: list[str] = []
        if data_source_id is not None:
            query += " AND data_source_id = ?"
            params.append(data_source_id)
        if job_id is not None:
            query += " AND job_id = ?"
            params.append(job_id)
        query += " ORDER BY started_at DESC"
        with connect(self.db_path) as conn:
            rows = conn.execute(query, params).fetchall()
            return [CollectionRun(**_util.row_to_dict(r)) for r in rows]

    # ------------------------------------------------------------
    # ConfigurationSnapshot (append-only, versioned)
    # ------------------------------------------------------------

    def save_configuration_snapshot(self, snapshot: ConfigurationSnapshot) -> None:
        with connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO configuration_snapshots
                    (config_snapshot_id, created_at, scoring_weights, risk_settings,
                     allocation_targets, notes)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    snapshot.config_snapshot_id, snapshot.created_at,
                    _util.dumps(snapshot.scoring_weights), _util.dumps(snapshot.risk_settings),
                    _util.dumps(snapshot.allocation_targets), snapshot.notes,
                ),
            )

    def get_configuration_snapshot(self, config_snapshot_id: str) -> Optional[ConfigurationSnapshot]:
        with connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT * FROM configuration_snapshots WHERE config_snapshot_id = ?",
                (config_snapshot_id,),
            ).fetchone()
            return self._row_to_config(row) if row else None

    def get_latest_configuration_snapshot(self) -> Optional[ConfigurationSnapshot]:
        with connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT * FROM configuration_snapshots ORDER BY created_at DESC, rowid DESC LIMIT 1"
            ).fetchone()
            return self._row_to_config(row) if row else None

    @staticmethod
    def _row_to_config(row) -> ConfigurationSnapshot:
        d = _util.row_to_dict(row)
        d["scoring_weights"] = _util.loads(d["scoring_weights"], {})
        d["risk_settings"] = _util.loads(d["risk_settings"], {})
        d["allocation_targets"] = _util.loads(d["allocation_targets"], {})
        return ConfigurationSnapshot(**d)
