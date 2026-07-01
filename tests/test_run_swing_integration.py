"""Synthetic integration test: proves the full candidate path (Position
Sizing -> Context Aggregation -> Reasoning -> Recommendation) works when a
company actually passes the swing filter. Real market data at the time
this was built showed zero real candidates (bearish/neutral across every
covered company) — a legitimate, verified outcome, not something to force
in the real database. This test engineers a synthetic breakout instead,
with the LLM call mocked (no network cost, fully deterministic).
"""

from datetime import date, timedelta
from unittest.mock import patch

from egxpm.llm.client import StructuredRecommendation
from egxpm.persistence.company_repository import CompanyRepository
from egxpm.persistence.db import connect
from egxpm.persistence.models import (
    FinancialStatement,
    PeriodType,
    PriceCandle,
    RecommendationAction,
    Timeframe,
)
from egxpm.run_swing import main

COMPANY_ID = "COMI"  # seeded WATCHLIST company with a real Company/schema


def _seed_synthetic_breakout_data(db_path: str) -> None:
    repo = CompanyRepository(db_path)

    # A few quarters of financial data so the Financial Engine has something.
    for i, period_end in enumerate(["2025-03-31", "2025-06-30", "2025-09-30", "2025-12-31"]):
        repo.save_financial_statement(FinancialStatement(
            company_id=COMPANY_ID, period_type=PeriodType.QUARTERLY, period_end=period_end,
            net_interest_income=100 + i * 10, net_income=50 + i * 5, total_assets=2000, total_liabilities=1800,
            total_equity=200, free_cash_flow=40, data_source_id="stockanalysis", source_version="1",
            collection_run_id="r1",
        ))

    # Flat price history, then a sharp final-day spike with a volume surge —
    # the same pattern proven to trigger breakout=True in test_technical_engine.py.
    # Anchored to end TODAY so ensure_fresh_prices sees this as fresh data and
    # doesn't overwrite the engineered spike with a real network fetch.
    prices = [100.0] * 209 + [200.0]
    volumes = [1000.0] * 209 + [5000.0]
    dates = []
    d = date.today()
    while len(dates) < len(prices):
        if d.weekday() < 5:
            dates.append(d)
        d -= timedelta(days=1)
    dates.reverse()

    candles = [
        PriceCandle(
            company_id=COMPANY_ID, timeframe=Timeframe.DAILY, candle_date=d.isoformat(),
            open=price, high=price + 0.5, low=price - 0.5, close=price, volume=volume,
            data_source_id="yfinance", source_version="1", collection_run_id="r1",
        )
        for d, price, volume in zip(dates, prices, volumes)
    ]
    repo.save_price_candles(candles)


def test_swing_candidate_gets_position_sizing_and_recommendation(db_path):
    _seed_synthetic_breakout_data(db_path)

    canned = StructuredRecommendation(
        action=RecommendationAction.BUY, reasoning="Synthetic breakout with volume confirmation.",
        key_risks=["Reversal risk after a sharp spike"],
        rejected_alternatives=["HOLD — rejected because the breakout is confirmed by volume"],
        confidence_commentary="High confidence given clean signal.",
    )

    with patch("egxpm.run_swing.generate_recommendation", return_value=canned) as mock_generate:
        exit_code = main(["--db-path", db_path])
        assert mock_generate.called

    with connect(db_path) as conn:
        recs = conn.execute(
            "SELECT * FROM recommendations WHERE company_id = ?", (COMPANY_ID,)
        ).fetchall()

    assert len(recs) == 1
    rec = recs[0]
    assert rec["action"] == "BUY"
    assert rec["entry_price"] is not None
    assert rec["stop_loss"] is not None
    assert rec["take_profit"] is not None
    assert rec["position_size"] is not None
    assert rec["stop_loss"] < rec["entry_price"] < rec["take_profit"]
