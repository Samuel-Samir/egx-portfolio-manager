import os
from datetime import date, timedelta

import pytest

from egxpm.persistence.db import connect
from egxpm.run_longterm import _freshness_fraction, main

REAL_DB_PATH = "data/egx.db"


def _require_real_db():
    if not os.path.exists(REAL_DB_PATH):
        pytest.skip(f"{REAL_DB_PATH} not present — run M1-M3 collection jobs first")


# ------------------------------------------------------------
# _freshness_fraction
# ------------------------------------------------------------

def test_freshness_fraction_fresh_data_is_1():
    today = date.today().isoformat()
    assert _freshness_fraction(today, threshold_days=2) == pytest.approx(1.0)


def test_freshness_fraction_none_date_is_none():
    assert _freshness_fraction(None, threshold_days=2) is None


def test_freshness_fraction_decays_linearly_past_threshold():
    stale_date = (date.today() - timedelta(days=4)).isoformat()
    # threshold=2, age=4 -> 2 days past threshold, decay window = threshold (2) -> 1.0 - 2/2 = 0.0
    assert _freshness_fraction(stale_date, threshold_days=2) == pytest.approx(0.0)


def test_freshness_fraction_never_goes_negative():
    ancient_date = (date.today() - timedelta(days=365)).isoformat()
    assert _freshness_fraction(ancient_date, threshold_days=2) == 0.0


def test_freshness_fraction_within_threshold_is_full():
    recent_date = (date.today() - timedelta(days=1)).isoformat()
    assert _freshness_fraction(recent_date, threshold_days=2) == pytest.approx(1.0)


# ------------------------------------------------------------
# Full --dry-run against real collected data
# ------------------------------------------------------------

def test_dry_run_produces_scores_but_no_recommendations(tmp_path):
    _require_real_db()
    import shutil
    scratch_db = str(tmp_path / "egx_scratch.db")
    shutil.copy(REAL_DB_PATH, scratch_db)

    exit_code = main(["--dry-run", "--db-path", scratch_db])

    with connect(scratch_db) as conn:
        score_count = conn.execute("SELECT COUNT(*) c FROM scores").fetchone()["c"]
        rec_count = conn.execute("SELECT COUNT(*) c FROM recommendations").fetchone()["c"]
        risk_count = conn.execute("SELECT COUNT(*) c FROM risk_scores").fetchone()["c"]
        confidence_count = conn.execute("SELECT COUNT(*) c FROM confidence_scores").fetchone()["c"]
        snapshot_count = conn.execute("SELECT COUNT(*) c FROM portfolio_snapshots").fetchone()["c"]

    assert score_count > 0
    assert risk_count == score_count
    assert confidence_count == score_count
    assert rec_count == 0
    assert snapshot_count == 1
    assert exit_code in (0, 1)  # 1 because the known 6-company coverage gap fails those companies
