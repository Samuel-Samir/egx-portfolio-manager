"""Persistence for Copilot entities: Conversation and AnalysisSession."""

from __future__ import annotations

from typing import Optional

from egxpm.persistence import _util
from egxpm.persistence.db import connect
from egxpm.persistence.models import AnalysisSession, Conversation


class ConversationRepository:
    def __init__(self, db_path: str):
        self.db_path = db_path

    # ------------------------------------------------------------
    # Conversation
    # ------------------------------------------------------------

    def save_conversation(self, conversation: Conversation) -> None:
        with connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO conversations
                    (conversation_id, started_at, last_active_at, transcript)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(conversation_id) DO UPDATE SET
                    last_active_at = excluded.last_active_at,
                    transcript = excluded.transcript
                """,
                (
                    conversation.conversation_id, conversation.started_at,
                    conversation.last_active_at, _util.dumps(conversation.transcript),
                ),
            )

    def get_conversation(self, conversation_id: str) -> Optional[Conversation]:
        with connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT * FROM conversations WHERE conversation_id = ?", (conversation_id,)
            ).fetchone()
            if not row:
                return None
            d = _util.row_to_dict(row)
            d["transcript"] = _util.loads(d["transcript"], [])
            return Conversation(**d)

    def list_conversations(self) -> list[Conversation]:
        with connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT * FROM conversations ORDER BY started_at"
            ).fetchall()
            out = []
            for r in rows:
                d = _util.row_to_dict(r)
                d["transcript"] = _util.loads(d["transcript"], [])
                out.append(Conversation(**d))
            return out

    def delete_conversations_older_than(self, cutoff_iso: str) -> int:
        """Retention policy enforcement. Returns number of rows deleted."""
        with connect(self.db_path) as conn:
            cur = conn.execute(
                "DELETE FROM conversations WHERE last_active_at < ?", (cutoff_iso,)
            )
            return cur.rowcount

    # ------------------------------------------------------------
    # AnalysisSession
    # ------------------------------------------------------------

    def save_session(self, session: AnalysisSession) -> None:
        with connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO analysis_sessions
                    (session_id, conversation_id, created_at, state, promoted_to_recommendation_id)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(session_id) DO UPDATE SET
                    state = excluded.state,
                    promoted_to_recommendation_id = excluded.promoted_to_recommendation_id
                """,
                (
                    session.session_id, session.conversation_id, session.created_at,
                    _util.dumps(session.state), session.promoted_to_recommendation_id,
                ),
            )

    def get_session(self, session_id: str) -> Optional[AnalysisSession]:
        with connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT * FROM analysis_sessions WHERE session_id = ?", (session_id,)
            ).fetchone()
            if not row:
                return None
            d = _util.row_to_dict(row)
            d["state"] = _util.loads(d["state"], {})
            return AnalysisSession(**d)

    def list_sessions(self, conversation_id: Optional[str] = None) -> list[AnalysisSession]:
        query = "SELECT * FROM analysis_sessions WHERE 1=1"
        params: list[str] = []
        if conversation_id is not None:
            query += " AND conversation_id = ?"
            params.append(conversation_id)
        query += " ORDER BY created_at"
        with connect(self.db_path) as conn:
            rows = conn.execute(query, params).fetchall()
            out = []
            for r in rows:
                d = _util.row_to_dict(r)
                d["state"] = _util.loads(d["state"], {})
                out.append(AnalysisSession(**d))
            return out
