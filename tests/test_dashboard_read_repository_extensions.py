import pytest

from egxpm.persistence.company_repository import CompanyRepository
from egxpm.persistence.dashboard_read_repository import DashboardReadRepository
from egxpm.persistence.models import (
    Holding,
    HoldingCategory,
    PriceCandle,
    Score,
    WatchlistHistory,
    WatchlistState,
    WatchlistTransitionType,
)
from egxpm.persistence.operational_repository import OperationalRepository

COMPANY_ID = "COMI"


# ------------------------------------------------------------
# get_holdings_detail
# ------------------------------------------------------------

def test_get_holdings_detail_joins_price_and_score(db_path):
    company_repo = CompanyRepository(db_path)
    company_repo.save_holding(Holding(
        company_id=COMPANY_ID, category=HoldingCategory.LONG_TERM_STOCKS,
        quantity=10, average_cost=50.0, acquired_at="2026-01-01",
    ))
    company_repo.save_price_candles([
        PriceCandle(
            company_id=COMPANY_ID, candle_date="2026-06-30", close=60.0,
            data_source_id="yfinance", source_version="1", collection_run_id="r1",
        )
    ])
    company_repo.save_score(Score(company_id=COMPANY_ID, composite_score=70.0, config_snapshot_id="cfg-1", job_id="job-1"))

    rows = DashboardReadRepository(db_path).get_holdings_detail()
    assert len(rows) == 1
    row = rows[0]
    assert row["latest_price"] == 60.0
    assert row["unrealized_pnl"] == pytest.approx(10 * (60.0 - 50.0))
    assert row["score"].composite_score == 70.0
    assert row["company"].company_id == COMPANY_ID


def test_get_holdings_detail_empty_when_no_holdings(db_path):
    assert DashboardReadRepository(db_path).get_holdings_detail() == []


# ------------------------------------------------------------
# get_watchlist_detail
# ------------------------------------------------------------

def test_get_watchlist_detail_includes_watchlist_and_candidate(db_path):
    company_repo = CompanyRepository(db_path)
    company_repo.append_watchlist_transition(WatchlistHistory(
        company_id="TMGH", state=WatchlistState.CANDIDATE,
        transition_type=WatchlistTransitionType.CANDIDATE_DISCOVERED,
    ))
    rows = DashboardReadRepository(db_path).get_watchlist_detail()
    company_ids = {row["company"].company_id for row in rows}
    assert COMPANY_ID in company_ids  # already WATCHLIST from seed data
    assert "TMGH" in company_ids


# ------------------------------------------------------------
# get_company_analysis
# ------------------------------------------------------------

def test_get_company_analysis_returns_all_history_types(db_path):
    company_repo = CompanyRepository(db_path)
    company_repo.save_score(Score(company_id=COMPANY_ID, composite_score=55.0, config_snapshot_id="cfg-1", job_id="job-1"))
    analysis = DashboardReadRepository(db_path).get_company_analysis(COMPANY_ID)
    assert analysis["company"].company_id == COMPANY_ID
    assert len(analysis["score_history"]) == 1
    assert analysis["financial_statements"] == []
    assert analysis["technical_snapshots"] == []
    assert analysis["news"] == []


# ------------------------------------------------------------
# Raw Database Explorer helpers
# ------------------------------------------------------------

def test_list_table_names_includes_known_tables(db_path):
    tables = OperationalRepository(db_path).list_table_names()
    assert "companies" in tables
    assert "scores" in tables
    assert not any(t.startswith("sqlite_") for t in tables)


def test_query_table_returns_rows(db_path):
    repo = OperationalRepository(db_path)
    rows = repo.query_table("companies", limit=5)
    assert len(rows) <= 5
    assert all("company_id" in row for row in rows)


def test_query_table_rejects_unknown_table(db_path):
    repo = OperationalRepository(db_path)
    with pytest.raises(ValueError):
        repo.query_table("not_a_real_table")


def test_query_table_rejects_sql_injection_attempt(db_path):
    repo = OperationalRepository(db_path)
    with pytest.raises(ValueError):
        repo.query_table("companies\"; DROP TABLE companies; --")


def test_count_table_rows(db_path):
    repo = OperationalRepository(db_path)
    count = repo.count_table_rows("companies")
    assert count == 12  # Phase 1 seed data
