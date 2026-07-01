from datetime import date, timedelta

import pytest

from egxpm.collectors.ensure_fresh_data import ensure_fresh_prices, freshness_fraction
from egxpm.persistence.company_repository import CompanyRepository
from egxpm.persistence.models import PriceCandle
from egxpm.persistence.operational_repository import OperationalRepository

COMPANY_ID = "COMI"


# ------------------------------------------------------------
# freshness_fraction
# ------------------------------------------------------------

def test_freshness_fraction_fresh_data_is_1():
    today = date.today().isoformat()
    assert freshness_fraction(today, threshold_days=2) == pytest.approx(1.0)


def test_freshness_fraction_none_date_is_none():
    assert freshness_fraction(None, threshold_days=2) is None


def test_freshness_fraction_decays_linearly_past_threshold():
    stale_date = (date.today() - timedelta(days=4)).isoformat()
    assert freshness_fraction(stale_date, threshold_days=2) == pytest.approx(0.0)


def test_freshness_fraction_never_goes_negative():
    ancient_date = (date.today() - timedelta(days=365)).isoformat()
    assert freshness_fraction(ancient_date, threshold_days=2) == 0.0


def test_freshness_fraction_within_threshold_is_full():
    recent_date = (date.today() - timedelta(days=1)).isoformat()
    assert freshness_fraction(recent_date, threshold_days=2) == pytest.approx(1.0)


# ------------------------------------------------------------
# ensure_fresh_prices — no nested Job (validation criterion)
# ------------------------------------------------------------

def test_no_op_when_already_fresh(db_path):
    company_repo = CompanyRepository(db_path)
    operational_repo = OperationalRepository(db_path)
    company_repo.save_price_candles([
        PriceCandle(
            company_id=COMPANY_ID, candle_date=date.today().isoformat(), close=100.0,
            data_source_id="yfinance", source_version="1", collection_run_id="r1",
        )
    ])

    jobs_before = operational_repo.list_jobs()
    runs_before = operational_repo.list_collection_runs()

    ensure_fresh_prices(company_repo, operational_repo, COMPANY_ID, stale_after_days=2)

    assert operational_repo.list_jobs() == jobs_before  # no new Job record
    assert operational_repo.list_collection_runs() == runs_before  # no collection attempted


def test_creates_collection_run_but_no_job_when_stale(db_path):
    company_repo = CompanyRepository(db_path)
    operational_repo = OperationalRepository(db_path)
    stale_date = (date.today() - timedelta(days=10)).isoformat()
    company_repo.save_price_candles([
        PriceCandle(
            company_id=COMPANY_ID, candle_date=stale_date, close=100.0,
            data_source_id="yfinance", source_version="1", collection_run_id="r1",
        )
    ])

    jobs_before = operational_repo.list_jobs()

    ensure_fresh_prices(company_repo, operational_repo, COMPANY_ID, stale_after_days=2)

    assert operational_repo.list_jobs() == jobs_before  # still no Job record — this is the point
    runs = operational_repo.list_collection_runs(data_source_id="yfinance")
    assert len(runs) == 1
    assert runs[0].job_id is None  # not attributed to any Job — inline, ad-hoc collection
