"""Technical Reference Collector — tradingview-ta, reference only.

This is deliberately NOT the Technical Engine. It stores TradingView's own
rating and raw indicator values as-is, for comparison against the Engine's
independently computed TechnicalSnapshot. Never used as an input to scoring.
"""

from __future__ import annotations

from tradingview_ta import Interval, TA_Handler

from egxpm.persistence.db import YFINANCE_TICKERS
from egxpm.persistence.models import TechnicalReferenceSnapshot
from egxpm.shared.exceptions import InsufficientDataError

TRADINGVIEW_SYMBOLS = {
    company_id: ticker.removesuffix(".CA") for company_id, ticker in YFINANCE_TICKERS.items()
}


def fetch_analysis(symbol: str, exchange: str = "EGX", screener: str = "egypt"):
    """Thin wrapper around tradingview-ta, isolated so it can be monkeypatched in tests."""
    handler = TA_Handler(
        symbol=symbol, exchange=exchange, screener=screener, interval=Interval.INTERVAL_1_DAY
    )
    return handler.get_analysis()


def collect_technical_reference(
    company_id: str, collection_run_id: str
) -> TechnicalReferenceSnapshot:
    """Fetch TradingView's rating + raw indicators for company_id.

    Raises:
        InsufficientDataError: no symbol mapping exists for company_id.
        Exception: whatever fetch_analysis() raises (missing symbol, rate
            limit, timeout, ...) propagates unwrapped — classifying it as
            transient/structural is CollectorService's job, not this
            Collector's (Section 14.5/2.4).
    """
    symbol = TRADINGVIEW_SYMBOLS.get(company_id)
    if symbol is None:
        raise InsufficientDataError(f"no tradingview-ta symbol mapping for company_id={company_id!r}")

    analysis = fetch_analysis(symbol)

    return TechnicalReferenceSnapshot(
        company_id=company_id,
        rating=analysis.summary.get("RECOMMENDATION", "NEUTRAL"),
        raw_indicators=dict(analysis.indicators),
        data_source_id="tradingview_ta",
        collection_run_id=collection_run_id,
    )
