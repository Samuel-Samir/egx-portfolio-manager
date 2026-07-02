"""CLI entry point for the Portfolio Review Job — deploys new capital
across the top-ranked WATCHLIST candidates as a RebalancePlan.

Usage:
    python -m egxpm.run_review --capital 50000

Unlike the Long-Term/Swing Jobs, this doesn't run Stages 1-13 or write a
Checkpoint — it reuses ToolRegistry.propose_rebalance (the one canonical
implementation of the rebalancing algorithm, invariant #10, also used by
the interactive Copilot) rather than duplicating that arithmetic here.

The resulting RebalancePlan is persisted inside a fresh AnalysisSession so
it isn't silently lost — but this Job never applies it. Plan -> Review ->
Approve -> Execute -> Audit (invariant, Section 10) still requires an
explicit user confirmation via the Copilot's confirm_and_apply, which this
CLI does not perform.
"""

from __future__ import annotations

import argparse
import sys

from egxpm.copilot.models import AnalysisSessionState
from egxpm.copilot.tool_registry import ToolRegistry
from egxpm.persistence.db import init_db
from egxpm.persistence.models import AnalysisSession, Conversation

DEFAULT_DB_PATH = "data/egx.db"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="EGX Portfolio Manager — Portfolio Review Job")
    parser.add_argument("--capital", type=float, required=True, help="New capital (EGP) to deploy")
    parser.add_argument("--db-path", default=DEFAULT_DB_PATH)
    parser.add_argument("--config-path", default="config.yaml")
    args = parser.parse_args(argv)

    init_db(args.db_path)
    registry = ToolRegistry(args.db_path, config_path=args.config_path)
    session_state = AnalysisSessionState()

    result = registry.execute("propose_rebalance", {"new_capital": args.capital}, session_state)
    if not result.success:
        print(f"Portfolio Review Job failed: {result.error}")
        return 1

    plan = result.data
    conversation = Conversation()
    registry.conversation_repo.save_conversation(conversation)
    analysis_session = AnalysisSession(
        conversation_id=conversation.conversation_id, state=session_state.model_dump()
    )
    registry.conversation_repo.save_session(analysis_session)

    print(f"RebalancePlan {plan['plan_id']} (session {analysis_session.session_id}):")
    print(f"  {plan['reasoning']}")
    for action in plan["proposed_actions"]:
        print(f"  BUY {action['quantity']:.4f} {action['company_id']} @ {action['price']:.2f} EGP")
    if plan["rejected_alternatives"]:
        print("  Skipped:")
        for note in plan["rejected_alternatives"]:
            print(f"    - {note}")
    print(f"  Projected total portfolio value: {plan['projected_allocation']['total_value']:,.2f} EGP")
    print(
        f"  Review and confirm via the Copilot (plan_id={plan['plan_id']}, "
        f"session_id={analysis_session.session_id}) before executing anything in Thndr."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
