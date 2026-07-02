from datetime import date, timedelta

from egxpm.persistence.company_repository import CompanyRepository
from egxpm.persistence.conversation_repository import ConversationRepository
from egxpm.persistence.db import connect
from egxpm.persistence.models import FinancialStatement, PeriodType, PriceCandle, Score
from egxpm.run_review import main

COMPANY_A = "TMGH"
COMPANY_B = "SWDY"


def _seed_price_candles(repo: CompanyRepository, company_id: str, close: float) -> None:
    start = date(2025, 1, 1)
    candles = [
        PriceCandle(
            company_id=company_id, candle_date=(start + timedelta(days=i)).isoformat(),
            open=close, high=close * 1.01, low=close * 0.99, close=close, volume=100000.0,
            data_source_id="yfinance", source_version="1", collection_run_id="seed-run",
        )
        for i in range(10)
    ]
    repo.save_price_candles(candles)


def _seed_financial_statement(repo: CompanyRepository, company_id: str) -> None:
    repo.save_financial_statement(FinancialStatement(
        company_id=company_id, period_type=PeriodType.QUARTERLY, period_end="2026-03-31",
        revenue=1_000_000.0, net_income=100_000.0, total_equity=500_000.0, total_liabilities=200_000.0,
        data_source_id="stockanalysis", source_version="1", collection_run_id="seed-run",
    ))


def _seed_score(repo: CompanyRepository, company_id: str, composite: float) -> None:
    repo.save_score(Score(
        company_id=company_id, financial_score=70.0, technical_score=60.0, news_score=55.0,
        composite_score=composite, config_snapshot_id="cfg-seed", job_id="seed-job",
    ))


def test_run_review_produces_rebalance_plan_and_saves_session(db_path, capsys):
    repo = CompanyRepository(db_path)
    for company_id, close, composite in [(COMPANY_A, 10.0, 80.0), (COMPANY_B, 20.0, 65.0)]:
        _seed_price_candles(repo, company_id, close)
        _seed_financial_statement(repo, company_id)
        _seed_score(repo, company_id, composite)

    exit_code = main(["--capital", "1000", "--db-path", db_path])
    assert exit_code == 0

    out = capsys.readouterr().out
    assert "RebalancePlan" in out
    assert COMPANY_A in out or COMPANY_B in out

    with connect(db_path) as conn:
        sessions = conn.execute("SELECT * FROM analysis_sessions").fetchall()
    assert len(sessions) == 1


def test_run_review_no_candidates_returns_nonzero(db_path, capsys):
    exit_code = main(["--capital", "1000", "--db-path", db_path])
    assert exit_code == 1
    out = capsys.readouterr().out
    assert "failed" in out.lower()
