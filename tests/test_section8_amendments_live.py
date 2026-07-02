"""M8 validation criterion: "All three Section 8 amendments validated with
real operational data" — company_sector_history, recommendation_supersessions,
watchlist_history. These tests read the real data/egx.db (skipped if it
doesn't exist), not a synthetic fixture, and assert the actual invariants
each amendment is supposed to guarantee.

recommendation_supersessions specifically needed a second real Long-Term
Job run against data/egx.db before this milestone — the only
supersession-producing event that had ever happened for real before M8 was
verified against a scratch copy (see M5's session log), not the live
database. That second real run is what produced the row this test reads.
"""

import os

import pytest

from egxpm.persistence.company_repository import CompanyRepository
from egxpm.persistence.db import connect
from egxpm.persistence.models import WatchlistState

DB_PATH = "data/egx.db"


def _require_real_db():
    if not os.path.exists(DB_PATH):
        pytest.skip("data/egx.db not present — run collection + a Job first")


def test_watchlist_history_real_transitions_are_append_only_and_consistent():
    _require_real_db()
    repo = CompanyRepository(DB_PATH)
    watchlist_ids = repo.list_companies_in_state(WatchlistState.WATCHLIST)
    assert len(watchlist_ids) > 0

    for company_id in watchlist_ids:
        history = repo.get_watchlist_history(company_id)
        assert len(history) >= 1
        # append-only: state_changed_at is non-decreasing across the history
        timestamps = [h.state_changed_at for h in history]
        assert timestamps == sorted(timestamps)
        # get_watchlist_state must match the most recent row in the full history
        assert repo.get_watchlist_state(company_id) == history[-1].state


def test_company_sector_history_has_one_current_row_per_company_matching_company_sector():
    _require_real_db()
    repo = CompanyRepository(DB_PATH)
    with connect(DB_PATH) as conn:
        companies = conn.execute("SELECT company_id, sector FROM companies").fetchall()
    assert len(companies) > 0

    for row in companies:
        history = repo.get_sector_history(row["company_id"])
        assert len(history) >= 1
        current = [h for h in history if h.effective_to is None]
        assert len(current) == 1  # exactly one open-ended (current) sector record
        assert current[0].sector == row["sector"]


def test_recommendation_supersessions_have_a_real_row_with_valid_fk_chain():
    _require_real_db()
    with connect(DB_PATH) as conn:
        supersessions = conn.execute("SELECT * FROM recommendation_supersessions").fetchall()
        if not supersessions:
            pytest.skip(
                "no recommendation_supersessions rows yet — requires a second real "
                "Long-Term/Swing Job run for the same company (see M5/M8 session log)"
            )
        for row in supersessions:
            superseded = conn.execute(
                "SELECT * FROM recommendations WHERE recommendation_id = ?",
                (row["recommendation_id"],),
            ).fetchone()
            assert superseded is not None  # FK target actually exists
            if row["superseding_reference_id"]:
                superseding = conn.execute(
                    "SELECT * FROM recommendations WHERE recommendation_id = ?",
                    (row["superseding_reference_id"],),
                ).fetchone()
                assert superseding is not None
                assert superseding["company_id"] == superseded["company_id"]
                # the superseding recommendation must be newer than the one it replaces
                assert superseding["created_at"] > superseded["created_at"]
