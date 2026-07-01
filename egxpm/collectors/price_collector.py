"""Price Collector — the one Collector that owns yfinance."""

from __future__ import annotations

import pandas as pd
import yfinance as yf

from egxpm.persistence.db import YFINANCE_TICKERS
from egxpm.persistence.models import PriceCandle, Timeframe
from egxpm.shared.exceptions import InsufficientDataError


def fetch_candles(ticker: str, period: str = "5y") -> pd.DataFrame:
    """Thin wrapper around yfinance, isolated so it can be monkeypatched in tests."""
    return yf.Ticker(ticker).history(period=period)


def collect_price_candles(
    company_id: str,
    collection_run_id: str,
    period: str = "5y",
    source_version: str = "1",
) -> list[PriceCandle]:
    """Fetch OHLCV for company_id via yfinance and return PriceCandle domain objects.

    Raises:
        InsufficientDataError: no yfinance ticker mapping exists for company_id,
            or yfinance returned no rows (e.g. delisted/unlisted on Yahoo Finance).
    """
    ticker = YFINANCE_TICKERS.get(company_id)
    if ticker is None:
        raise InsufficientDataError(f"no yfinance ticker mapping for company_id={company_id!r}")

    df = fetch_candles(ticker, period=period)
    if df.empty:
        raise InsufficientDataError(f"yfinance returned no price data for ticker={ticker!r}")

    candles = []
    for date, row in df.iterrows():
        candles.append(
            PriceCandle(
                company_id=company_id,
                timeframe=Timeframe.DAILY,
                candle_date=date.strftime("%Y-%m-%d"),
                open=_clean(row.get("Open")),
                high=_clean(row.get("High")),
                low=_clean(row.get("Low")),
                close=_clean(row.get("Close")),
                volume=_clean(row.get("Volume")),
                data_source_id="yfinance",
                source_version=source_version,
                collection_run_id=collection_run_id,
            )
        )
    return candles


def _clean(value) -> float | None:
    if value is None or pd.isna(value):
        return None
    return float(value)
