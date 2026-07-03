"""Persistence for the Recommendation aggregate: Recommendation,
RecommendationSupersession, Execution, Outcome, UserFeedback.

Recommendations are immutable once written — corrections are new rows,
never updates (see RecommendationSupersession).
"""

from __future__ import annotations

from typing import Optional

from egxpm.persistence import _util
from egxpm.persistence.db import connect
from egxpm.persistence.models import (
    Execution,
    Outcome,
    Recommendation,
    RecommendationSupersession,
    UserFeedback,
)


class RecommendationRepository:
    def __init__(self, db_path: str):
        self.db_path = db_path

    # ------------------------------------------------------------
    # Recommendation (immutable)
    # ------------------------------------------------------------

    def save_recommendation(self, rec: Recommendation, conn=None) -> None:
        sql = """
            INSERT INTO recommendations
                (recommendation_id, company_id, created_at, action, entry_price, stop_loss,
                 take_profit, position_size, confidence_id, config_snapshot_id,
                 portfolio_snapshot_id, frozen_package, job_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        params = (
            rec.recommendation_id, rec.company_id, rec.created_at, rec.action.value,
            rec.entry_price, rec.stop_loss, rec.take_profit, rec.position_size,
            rec.confidence_id, rec.config_snapshot_id, rec.portfolio_snapshot_id,
            _util.dumps(rec.frozen_package), rec.job_id,
        )
        if conn is not None:
            conn.execute(sql, params)
        else:
            with connect(self.db_path) as c:
                c.execute(sql, params)

    def get_recommendation(self, recommendation_id: str) -> Optional[Recommendation]:
        with connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT * FROM recommendations WHERE recommendation_id = ?",
                (recommendation_id,),
            ).fetchone()
            return self._row_to_recommendation(row) if row else None

    def list_recommendations(self, company_id: Optional[str] = None) -> list[Recommendation]:
        query = "SELECT * FROM recommendations WHERE 1=1"
        params: list[str] = []
        if company_id is not None:
            query += " AND company_id = ?"
            params.append(company_id)
        query += " ORDER BY created_at"
        with connect(self.db_path) as conn:
            rows = conn.execute(query, params).fetchall()
            return [self._row_to_recommendation(r) for r in rows]

    @staticmethod
    def _row_to_recommendation(row) -> Recommendation:
        d = _util.row_to_dict(row)
        d["frozen_package"] = _util.loads(d["frozen_package"], {})
        return Recommendation(**d)

    # ------------------------------------------------------------
    # RecommendationSupersession (append-only)
    # ------------------------------------------------------------

    def save_supersession(self, supersession: RecommendationSupersession, conn=None) -> None:
        sql = """
            INSERT INTO recommendation_supersessions
                (supersession_id, recommendation_id, superseded_at,
                 superseding_event_type, superseding_reference_id)
            VALUES (?, ?, ?, ?, ?)
        """
        params = (
            supersession.supersession_id, supersession.recommendation_id,
            supersession.superseded_at, supersession.superseding_event_type,
            supersession.superseding_reference_id,
        )
        if conn is not None:
            conn.execute(sql, params)
        else:
            with connect(self.db_path) as c:
                c.execute(sql, params)

    def save_checkpoint_b(
        self, recommendation: Recommendation, supersession: RecommendationSupersession | None = None
    ) -> None:
        """Checkpoint B (Stage 13): Recommendation + (optional) RecommendationSupersession,
        one atomic transaction."""
        with connect(self.db_path) as conn:
            self.save_recommendation(recommendation, conn=conn)
            if supersession is not None:
                self.save_supersession(supersession, conn=conn)

    def list_supersessions(self, recommendation_id: str) -> list[RecommendationSupersession]:
        with connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT * FROM recommendation_supersessions WHERE recommendation_id = ? ORDER BY superseded_at",
                (recommendation_id,),
            ).fetchall()
            return [RecommendationSupersession(**_util.row_to_dict(r)) for r in rows]

    # ------------------------------------------------------------
    # Execution (append-only)
    # ------------------------------------------------------------

    def save_execution(self, execution: Execution) -> None:
        with connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO executions
                    (execution_id, recommendation_id, executed_at, action_taken, details)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    execution.execution_id, execution.recommendation_id, execution.executed_at,
                    execution.action_taken, _util.dumps(execution.details),
                ),
            )

    def get_execution(self, execution_id: str) -> Optional[Execution]:
        with connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT * FROM executions WHERE execution_id = ?", (execution_id,)
            ).fetchone()
            if not row:
                return None
            d = _util.row_to_dict(row)
            d["details"] = _util.loads(d["details"], {})
            return Execution(**d)

    def list_executions(self, recommendation_id: str) -> list[Execution]:
        with connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT * FROM executions WHERE recommendation_id = ? ORDER BY executed_at",
                (recommendation_id,),
            ).fetchall()
            out = []
            for r in rows:
                d = _util.row_to_dict(r)
                d["details"] = _util.loads(d["details"], {})
                out.append(Execution(**d))
            return out

    def list_all_executions(self) -> list[Execution]:
        """Every Execution on record, most recent first — the full
        transaction history (an Execution may exist without a prior
        Recommendation, invariant Section 10.4, e.g. a manually-recorded
        real holding transaction not following any system recommendation)."""
        with connect(self.db_path) as conn:
            rows = conn.execute("SELECT * FROM executions ORDER BY executed_at DESC").fetchall()
            out = []
            for r in rows:
                d = _util.row_to_dict(r)
                d["details"] = _util.loads(d["details"], {})
                out.append(Execution(**d))
            return out

    # ------------------------------------------------------------
    # Outcome (append-only)
    # ------------------------------------------------------------

    def save_outcome(self, outcome: Outcome) -> None:
        with connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO outcomes
                    (outcome_id, recommendation_id, execution_id, recorded_at, actual_return,
                     actual_loss, holding_period_days, target_hit, stop_hit,
                     quality_classification, is_final)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    outcome.outcome_id, outcome.recommendation_id, outcome.execution_id,
                    outcome.recorded_at, outcome.actual_return, outcome.actual_loss,
                    outcome.holding_period_days,
                    None if outcome.target_hit is None else int(outcome.target_hit),
                    None if outcome.stop_hit is None else int(outcome.stop_hit),
                    outcome.quality_classification, int(outcome.is_final),
                ),
            )

    def list_outcomes(self, recommendation_id: str) -> list[Outcome]:
        with connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT * FROM outcomes WHERE recommendation_id = ? ORDER BY recorded_at",
                (recommendation_id,),
            ).fetchall()
            return [self._row_to_outcome(r) for r in rows]

    @staticmethod
    def _row_to_outcome(row) -> Outcome:
        d = _util.row_to_dict(row)
        d["target_hit"] = None if d["target_hit"] is None else bool(d["target_hit"])
        d["stop_hit"] = None if d["stop_hit"] is None else bool(d["stop_hit"])
        d["is_final"] = bool(d["is_final"])
        return Outcome(**d)

    # ------------------------------------------------------------
    # UserFeedback (append-only)
    # ------------------------------------------------------------

    def save_user_feedback(self, feedback: UserFeedback) -> None:
        with connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO user_feedback
                    (feedback_id, recommendation_id, execution_id, outcome_id, recorded_at,
                     feedback_text, agreement)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    feedback.feedback_id, feedback.recommendation_id, feedback.execution_id,
                    feedback.outcome_id, feedback.recorded_at, feedback.feedback_text,
                    feedback.agreement.value if feedback.agreement else None,
                ),
            )

    def list_user_feedback(self, recommendation_id: str) -> list[UserFeedback]:
        with connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT * FROM user_feedback WHERE recommendation_id = ? ORDER BY recorded_at",
                (recommendation_id,),
            ).fetchall()
            return [UserFeedback(**_util.row_to_dict(r)) for r in rows]
