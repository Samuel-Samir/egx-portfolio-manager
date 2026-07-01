"""Persistence for SectorSummary and MarketSummary — derived, append-only
aggregations produced at the Stage 6a synchronization barrier. Never edited.
"""

from __future__ import annotations

from typing import Optional

from egxpm.persistence import _util
from egxpm.persistence.db import connect
from egxpm.persistence.models import MarketSummary, SectorSummary


class SectorMarketRepository:
    def __init__(self, db_path: str):
        self.db_path = db_path

    # ------------------------------------------------------------
    # SectorSummary
    # ------------------------------------------------------------

    def save_sector_summary(self, summary: SectorSummary, conn=None) -> None:
        sql = """
            INSERT INTO sector_summaries
                (summary_id, sector, computed_at, summary_score, component_company_scores, job_id)
            VALUES (?, ?, ?, ?, ?, ?)
        """
        params = (
            summary.summary_id, summary.sector, summary.computed_at, summary.summary_score,
            _util.dumps(summary.component_company_scores), summary.job_id,
        )
        if conn is not None:
            conn.execute(sql, params)
        else:
            with connect(self.db_path) as c:
                c.execute(sql, params)

    def get_latest_sector_summary(self, sector: str) -> Optional[SectorSummary]:
        with connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT * FROM sector_summaries WHERE sector = ? ORDER BY computed_at DESC LIMIT 1",
                (sector,),
            ).fetchone()
            return self._row_to_sector_summary(row) if row else None

    def list_sector_summaries(self, sector: Optional[str] = None) -> list[SectorSummary]:
        query = "SELECT * FROM sector_summaries WHERE 1=1"
        params: list[str] = []
        if sector is not None:
            query += " AND sector = ?"
            params.append(sector)
        query += " ORDER BY computed_at"
        with connect(self.db_path) as conn:
            rows = conn.execute(query, params).fetchall()
            return [self._row_to_sector_summary(r) for r in rows]

    @staticmethod
    def _row_to_sector_summary(row) -> SectorSummary:
        d = _util.row_to_dict(row)
        d["component_company_scores"] = _util.loads(d["component_company_scores"], [])
        return SectorSummary(**d)

    # ------------------------------------------------------------
    # MarketSummary
    # ------------------------------------------------------------

    def save_market_summary(self, summary: MarketSummary, conn=None) -> None:
        sql = """
            INSERT INTO market_summaries
                (summary_id, computed_at, summary_score, component_sector_summaries, job_id)
            VALUES (?, ?, ?, ?, ?)
        """
        params = (
            summary.summary_id, summary.computed_at, summary.summary_score,
            _util.dumps(summary.component_sector_summaries), summary.job_id,
        )
        if conn is not None:
            conn.execute(sql, params)
        else:
            with connect(self.db_path) as c:
                c.execute(sql, params)

    def get_latest_market_summary(self) -> Optional[MarketSummary]:
        with connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT * FROM market_summaries ORDER BY computed_at DESC LIMIT 1"
            ).fetchone()
            return self._row_to_market_summary(row) if row else None

    def list_market_summaries(self) -> list[MarketSummary]:
        with connect(self.db_path) as conn:
            rows = conn.execute("SELECT * FROM market_summaries ORDER BY computed_at").fetchall()
            return [self._row_to_market_summary(r) for r in rows]

    @staticmethod
    def _row_to_market_summary(row) -> MarketSummary:
        d = _util.row_to_dict(row)
        d["component_sector_summaries"] = _util.loads(d["component_sector_summaries"], [])
        return MarketSummary(**d)
