"""CLI entry point for recording a real Holding transaction (buy/sell/add/
trim) against your actual EGX portfolio — e.g. as held in Thndr.

Usage:
    python -m egxpm.record_holding --company-id ADA --action BUY \\
        --quantity 500 --price 105.50 --category gold

    python -m egxpm.record_holding --company-id PALM --action SELL \\
        --quantity 100 --price 12.30

    # Backfilling a position you already held before using this system:
    python -m egxpm.record_holding --company-id BMM --action BUY \\
        --quantity 1000 --price 36.50 --category bmm_index \\
        --acquired-at 2025-11-01T00:00:00+00:00

--category is required only when opening a brand-new position (there's no
existing Holding to infer it from). --price is the transaction price per
share — for SELL/TRIM it doesn't change the remaining position's cost
basis (selling never changes what you paid for the shares you kept) but
ProposedAction always requires one.

Reuses PortfolioEngine.apply_action() — the one canonical implementation of
holding arithmetic (weighted-average cost on BUY/ADD, quantity reduction on
SELL/TRIM), the same one propose_rebalance and simulate_buy already use.
This CLI adds no arithmetic of its own: it loads current holdings, applies
the action, and persists the result — a new position is an insert, a
changed position is an update, a fully-sold position is a delete, all via
save_holding()'s existing upsert (holdings is a live, mutable position
record, unlike the append-only watchlist_history/company_sector_history/
recommendation_supersessions tables).

Every run also captures a PortfolioSnapshot (origin="manual") — the same
mechanism the Long-Term/Swing Jobs already use, so holdings history becomes
visible over time on the Dashboard's Historical Timeline page with no
separate "track progress" feature needed.
"""

from __future__ import annotations

import argparse
import sys

from egxpm.engine.portfolio_engine import apply_action
from egxpm.persistence.company_repository import CompanyRepository
from egxpm.persistence.db import init_db
from egxpm.persistence.models import (
    HoldingCategory,
    PortfolioSnapshot,
    PortfolioSnapshotOrigin,
    ProposedAction,
    RecommendationAction,
)
from egxpm.persistence.portfolio_repository import PortfolioRepository
from egxpm.shared.allocation_calculator import calculate as calculate_allocation
from egxpm.shared.config import load_configuration_snapshot
from egxpm.shared.exceptions import InsufficientDataError, InvalidActionError

DEFAULT_DB_PATH = "data/egx.db"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="EGX Portfolio Manager — Record a real Holding transaction")
    parser.add_argument("--company-id", required=True)
    parser.add_argument("--action", required=True, choices=[a.value for a in RecommendationAction])
    parser.add_argument("--quantity", type=float, required=True)
    parser.add_argument("--price", type=float, required=True, help="Transaction price per share (EGP)")
    parser.add_argument(
        "--category", choices=[c.value for c in HoldingCategory], default=None,
        help="Required when opening a brand-new position",
    )
    parser.add_argument(
        "--acquired-at", default=None,
        help="ISO date/time override for a brand-new position (defaults to now — use this to backfill a real acquisition date)",
    )
    parser.add_argument("--db-path", default=DEFAULT_DB_PATH)
    parser.add_argument("--config-path", default="config.yaml")
    args = parser.parse_args(argv)

    init_db(args.db_path)
    company_repo = CompanyRepository(args.db_path)
    portfolio_repo = PortfolioRepository(args.db_path)

    category = HoldingCategory(args.category) if args.category else None
    action = ProposedAction(
        company_id=args.company_id, action=RecommendationAction(args.action),
        quantity=args.quantity, price=args.price, category=category,
    )

    before = company_repo.list_holdings()
    before_ids = {h.holding_id for h in before}

    try:
        after = apply_action(before, action)
    except InvalidActionError as exc:
        print(f"Invalid holding transaction: {exc}")
        return 1

    if args.acquired_at:
        after = [
            h.model_copy(update={"acquired_at": args.acquired_at}) if h.company_id == args.company_id else h
            for h in after
        ]

    after_ids = {h.holding_id for h in after}
    for holding_id in before_ids - after_ids:
        company_repo.delete_holding(holding_id)
    for holding in after:
        company_repo.save_holding(holding)

    print(f"Recorded {args.action} {args.quantity} {args.company_id} @ {args.price:.2f} EGP.")

    final_holdings = company_repo.list_holdings()
    prices = company_repo.get_latest_prices([h.company_id for h in final_holdings])
    weights = load_configuration_snapshot(args.config_path)
    try:
        allocation = calculate_allocation(final_holdings, prices, cash=0.0, targets=weights)
        portfolio_repo.save_snapshot(PortfolioSnapshot(
            holdings_snapshot=[h.model_dump() for h in final_holdings], cash=0.0,
            computed_allocation=allocation.model_dump(), origin=PortfolioSnapshotOrigin.MANUAL,
        ))
        print(f"Portfolio total value: {allocation.total_value:,.2f} EGP")
        for company_id, pct in sorted(allocation.by_stock_pct.items(), key=lambda kv: -kv[1]):
            print(f"  {company_id}: {pct:.1%}")
    except InsufficientDataError as exc:  # a held company with no price on record yet
        print(f"(allocation/snapshot skipped — {exc})")

    return 0


if __name__ == "__main__":
    sys.exit(main())
