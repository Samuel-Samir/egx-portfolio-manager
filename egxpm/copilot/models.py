"""Copilot value objects: Plans (ephemeral, session-scoped — never their
own SQL table, per the "AnalysisSession is Ephemeral" lifecycle already
established for the persisted AnalysisSession row), ToolResult, and the
richer in-memory AnalysisSession workspace state (Section 15.4).

Plans are NOT Recommendations: a Recommendation is immutable, permanent,
and produced by a scheduled Job; a Plan is a proposal a user must
explicitly confirm before anything happens, and expires if they don't.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

from egxpm.persistence.models import AllocationReport, ProposedAction


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _default_expiry(hours: float) -> str:
    return (datetime.now(timezone.utc) + timedelta(hours=hours)).isoformat()


class RebalancePlan(BaseModel):
    """Produced by propose_rebalance. [POLICY] Expires after a configured
    time window or upon material Portfolio change before confirmation —
    expiry is checked at confirm time, not enforced by a background job."""
    plan_id: str = Field(default_factory=_uuid)
    plan_type: Literal["rebalance"] = "rebalance"
    created_at: str = Field(default_factory=_now)
    expires_at: str = Field(default_factory=lambda: _default_expiry(24))
    new_capital: float
    proposed_actions: list[ProposedAction]
    projected_allocation: AllocationReport
    reasoning: str
    rejected_alternatives: list[str] = []


class SwingPlan(BaseModel):
    """Produced by propose_swing_analysis — a single-company swing setup
    preview, computed but not persisted (no Checkpoint A/B writes)."""
    plan_id: str = Field(default_factory=_uuid)
    plan_type: Literal["swing_analysis"] = "swing_analysis"
    created_at: str = Field(default_factory=_now)
    expires_at: str = Field(default_factory=lambda: _default_expiry(24))
    company_id: str
    composite_score: Optional[float] = None
    entry_price: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    position_size: Optional[float] = None
    reasoning: str
    rejected_alternatives: list[str] = []


class ToolResult(BaseModel):
    """What every Tool Registry call returns. success=False + error is how
    an expected business failure (wrong plan_id, insufficient data, ...)
    is communicated back to the LLM — never a raised Python exception for
    those cases. A genuine bug (ValueError/AssertionError) still raises
    and is NOT caught into a ToolResult.
    """
    tool_name: str
    success: bool
    data: Any = None
    error: Optional[str] = None


class AnalysisSessionState(BaseModel):
    """The richer workspace state (Section 15.4), serialized into/out of
    the persisted AnalysisSession.state JSON blob — that column is a
    generic dict so it can hold whatever shape each session type needs;
    this is the shape the Copilot uses.
    """
    companies_in_scope: list[str] = []
    pending_plans: dict[str, dict] = {}  # plan_id -> RebalancePlan/SwingPlan.model_dump()
    simulation_results: list[dict] = []  # AllocationReport.model_dump() entries
    draft_shortlist: list[str] = []
    notes: str = ""
    confirmed_plan_ids: list[str] = []
    promoted_to_rec_id: Optional[str] = None
