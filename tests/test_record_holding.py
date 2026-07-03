from egxpm.persistence.company_repository import CompanyRepository
from egxpm.persistence.db import connect
from egxpm.persistence.models import PriceCandle
from egxpm.persistence.portfolio_repository import PortfolioRepository
from egxpm.record_holding import main

COMPANY_A = "ADA"
COMPANY_B = "BMM"


def _seed_price(repo: CompanyRepository, company_id: str, close: float) -> None:
    repo.save_price_candles([PriceCandle(
        company_id=company_id, candle_date="2026-07-01", open=close, high=close, low=close,
        close=close, volume=1000.0, data_source_id="yfinance", source_version="1",
        collection_run_id="seed-run",
    )])


def test_opening_a_new_position_requires_category(db_path, capsys):
    exit_code = main([
        "--company-id", COMPANY_A, "--action", "BUY", "--quantity", "500", "--price", "105.50",
        "--db-path", db_path,
    ])
    assert exit_code == 1
    out = capsys.readouterr().out
    assert "without a category" in out

    company_repo = CompanyRepository(db_path)
    assert company_repo.list_holdings() == []


def test_opens_a_new_position_with_category(db_path):
    exit_code = main([
        "--company-id", COMPANY_A, "--action", "BUY", "--quantity", "500", "--price", "105.50",
        "--category", "gold", "--db-path", db_path,
    ])
    assert exit_code == 0

    company_repo = CompanyRepository(db_path)
    holdings = company_repo.list_holdings()
    assert len(holdings) == 1
    assert holdings[0].company_id == COMPANY_A
    assert holdings[0].quantity == 500
    assert holdings[0].average_cost == 105.50
    assert holdings[0].category.value == "gold"


def test_acquired_at_override_backfills_a_past_date(db_path):
    main([
        "--company-id", COMPANY_B, "--action", "BUY", "--quantity", "1000", "--price", "36.50",
        "--category", "bmm_index", "--acquired-at", "2025-11-01T00:00:00+00:00", "--db-path", db_path,
    ])
    holding = CompanyRepository(db_path).list_holdings()[0]
    assert holding.acquired_at == "2025-11-01T00:00:00+00:00"


def test_adding_to_existing_position_uses_weighted_average_cost(db_path):
    main([
        "--company-id", COMPANY_A, "--action", "BUY", "--quantity", "100", "--price", "100.0",
        "--category", "gold", "--db-path", db_path,
    ])
    exit_code = main([
        "--company-id", COMPANY_A, "--action", "ADD", "--quantity", "100", "--price", "120.0",
        "--db-path", db_path,
    ])
    assert exit_code == 0

    holdings = CompanyRepository(db_path).list_holdings()
    assert len(holdings) == 1
    assert holdings[0].quantity == 200
    assert holdings[0].average_cost == 110.0  # (100*100 + 100*120) / 200


def test_selling_entire_position_deletes_the_holding_row(db_path):
    main([
        "--company-id", COMPANY_A, "--action", "BUY", "--quantity", "500", "--price", "105.50",
        "--category", "gold", "--db-path", db_path,
    ])
    exit_code = main([
        "--company-id", COMPANY_A, "--action", "SELL", "--quantity", "500", "--price", "110.0",
        "--db-path", db_path,
    ])
    assert exit_code == 0
    assert CompanyRepository(db_path).list_holdings() == []


def test_selling_more_than_held_fails_cleanly_and_changes_nothing(db_path):
    main([
        "--company-id", COMPANY_A, "--action", "BUY", "--quantity", "100", "--price", "100.0",
        "--category", "gold", "--db-path", db_path,
    ])
    exit_code = main([
        "--company-id", COMPANY_A, "--action", "SELL", "--quantity", "9999", "--price", "100.0",
        "--db-path", db_path,
    ])
    assert exit_code == 1

    holdings = CompanyRepository(db_path).list_holdings()
    assert len(holdings) == 1
    assert holdings[0].quantity == 100  # untouched


def test_records_a_manual_portfolio_snapshot_when_prices_are_known(db_path):
    company_repo = CompanyRepository(db_path)
    _seed_price(company_repo, COMPANY_A, close=110.0)

    exit_code = main([
        "--company-id", COMPANY_A, "--action", "BUY", "--quantity", "500", "--price", "105.50",
        "--category", "gold", "--db-path", db_path,
    ])
    assert exit_code == 0

    snapshot = PortfolioRepository(db_path).get_latest_snapshot()
    assert snapshot is not None
    assert snapshot.origin.value == "manual"
    assert snapshot.computed_allocation["total_value"] == 500 * 110.0


def test_skips_snapshot_gracefully_when_no_price_known_yet(db_path, capsys):
    exit_code = main([
        "--company-id", COMPANY_A, "--action", "BUY", "--quantity", "500", "--price", "105.50",
        "--category", "gold", "--db-path", db_path,
    ])
    assert exit_code == 0
    out = capsys.readouterr().out
    assert "skipped" in out
    assert PortfolioRepository(db_path).get_latest_snapshot() is None
