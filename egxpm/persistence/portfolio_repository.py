"""Persistence for PortfolioSnapshot — the immutable, timestamped capture
of full Portfolio state."""

from __future__ import annotations

from typing import Optional

from egxpm.persistence import _util
from egxpm.persistence.db import connect
from egxpm.persistence.models import PortfolioSnapshot


class PortfolioRepository:
    def __init__(self, db_path: str):
        self.db_path = db_path

    def save_snapshot(self, snapshot: PortfolioSnapshot, conn=None) -> None:
        sql = """
            INSERT INTO portfolio_snapshots
                (snapshot_id, captured_at, holdings_snapshot, cash, computed_allocation, origin)
            VALUES (?, ?, ?, ?, ?, ?)
        """
        params = (
            snapshot.snapshot_id, snapshot.captured_at, _util.dumps(snapshot.holdings_snapshot),
            snapshot.cash, _util.dumps(snapshot.computed_allocation), snapshot.origin.value,
        )
        if conn is not None:
            conn.execute(sql, params)
        else:
            with connect(self.db_path) as c:
                c.execute(sql, params)

    def get_snapshot(self, snapshot_id: str) -> Optional[PortfolioSnapshot]:
        with connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT * FROM portfolio_snapshots WHERE snapshot_id = ?", (snapshot_id,)
            ).fetchone()
            return self._row_to_snapshot(row) if row else None

    def get_latest_snapshot(self) -> Optional[PortfolioSnapshot]:
        with connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT * FROM portfolio_snapshots ORDER BY captured_at DESC, rowid DESC LIMIT 1"
            ).fetchone()
            return self._row_to_snapshot(row) if row else None

    def list_snapshots(self) -> list[PortfolioSnapshot]:
        with connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT * FROM portfolio_snapshots ORDER BY captured_at"
            ).fetchall()
            return [self._row_to_snapshot(r) for r in rows]

    @staticmethod
    def _row_to_snapshot(row) -> PortfolioSnapshot:
        d = _util.row_to_dict(row)
        d["holdings_snapshot"] = _util.loads(d["holdings_snapshot"], [])
        d["computed_allocation"] = _util.loads(d["computed_allocation"], {})
        return PortfolioSnapshot(**d)
