"""Technical Engine — Stage 4 of the canonical pipeline.

Pure function: accepts PriceCandle domain objects, returns a
TechnicalSnapshotResult (indicators + derived signals). No I/O, no SQL,
no awareness of Persistence. Orchestration is responsible for merging the
result with company_id/job_id/engine_version and saving it through
CompanyRepository.save_technical_snapshot().
"""

from __future__ import annotations

import pandas as pd
import pandas_ta_classic as ta
from pydantic import BaseModel

from egxpm.persistence.models import PriceCandle, TrendSignal
from egxpm.shared.exceptions import InsufficientDataError

ENGINE_VERSION = "technical_engine_v1"

# Resistance/support are the rolling high/low of the SUPPORT_RESISTANCE_LOOKBACK
# periods *before* today, so a breakout is measured against a level the price
# had not yet touched — not today's own high/low.
SUPPORT_RESISTANCE_LOOKBACK = 20


class TechnicalIndicators(BaseModel):
    rsi: float | None = None
    macd: float | None = None
    macd_signal: float | None = None
    sma_20: float | None = None
    sma_50: float | None = None
    sma_200: float | None = None
    ema_20: float | None = None
    ema_50: float | None = None
    atr: float | None = None
    bollinger_upper: float | None = None
    bollinger_lower: float | None = None
    bollinger_bandwidth: float | None = None
    volume_ma_20: float | None = None
    support_level: float | None = None
    resistance_level: float | None = None


class TechnicalSignals(BaseModel):
    trend: TrendSignal
    breakout: bool
    unusual_volume: bool


class TechnicalSnapshotResult(BaseModel):
    indicators: TechnicalIndicators
    signals: TechnicalSignals
    computed_through_date: str
    window_size: int
    # The Position Sizing Engine needs an entry price (Stage 9), but neither
    # its contract signature nor the persisted TechnicalSnapshot row carries
    # one. Rather than a schema change for a single derived value, the
    # Technical Engine exposes the close price it already computes
    # internally — Position Sizing consumes the same in-memory
    # TechnicalSnapshotResult produced earlier in the same Job run.
    latest_close: float


def _last(series: pd.Series | None) -> float | None:
    if series is None or series.empty:
        return None
    value = series.iloc[-1]
    return None if pd.isna(value) else float(value)


def calculate_technical_snapshot(
    candles: list[PriceCandle],
    window: int = 200,
    unusual_volume_threshold: float = 1.5,
) -> TechnicalSnapshotResult:
    """Compute indicators + signals from the trailing `window` candles.

    Raises:
        InsufficientDataError: fewer than `window` candles provided, or the
            most recent candle has no close price.
        ValueError: candles span multiple companies/timeframes, or are not
            in chronological order (precondition, not a data-quality issue).
    """
    if not candles:
        raise InsufficientDataError("no candles provided")

    company_ids = {c.company_id for c in candles}
    if len(company_ids) > 1:
        raise ValueError(f"candles span multiple companies: {sorted(company_ids)}")

    timeframes = {c.timeframe for c in candles}
    if len(timeframes) > 1:
        raise ValueError(f"candles span multiple timeframes: {sorted(str(t) for t in timeframes)}")

    for prev, curr in zip(candles, candles[1:]):
        if curr.candle_date <= prev.candle_date:
            raise ValueError("candles must be in strictly ascending chronological order")

    if len(candles) < window:
        raise InsufficientDataError(f"need at least {window} candles, got {len(candles)}")

    window_candles = candles[-window:]
    dates = [c.candle_date for c in window_candles]
    close = pd.Series([c.close for c in window_candles], index=dates, dtype=float)
    high = pd.Series([c.high for c in window_candles], index=dates, dtype=float)
    low = pd.Series([c.low for c in window_candles], index=dates, dtype=float)
    volume = pd.Series([c.volume for c in window_candles], index=dates, dtype=float)

    price = close.iloc[-1]
    if pd.isna(price):
        raise InsufficientDataError("most recent candle has no close price")

    rsi = ta.rsi(close, length=14)
    macd_df = ta.macd(close)
    sma_20 = ta.sma(close, length=20)
    sma_50 = ta.sma(close, length=50)
    sma_200 = ta.sma(close, length=200)
    ema_20 = ta.ema(close, length=20)
    ema_50 = ta.ema(close, length=50)
    atr = ta.atr(high, low, close, length=14)
    bbands = ta.bbands(close, length=20)
    volume_ma_20 = ta.sma(volume, length=20)
    resistance = high.shift(1).rolling(SUPPORT_RESISTANCE_LOOKBACK).max()
    support = low.shift(1).rolling(SUPPORT_RESISTANCE_LOOKBACK).min()

    indicators = TechnicalIndicators(
        rsi=_last(rsi),
        macd=_last(macd_df["MACD_12_26_9"]) if macd_df is not None else None,
        macd_signal=_last(macd_df["MACDs_12_26_9"]) if macd_df is not None else None,
        sma_20=_last(sma_20),
        sma_50=_last(sma_50),
        sma_200=_last(sma_200),
        ema_20=_last(ema_20),
        ema_50=_last(ema_50),
        atr=_last(atr),
        bollinger_upper=_last(bbands["BBU_20_2.0"]) if bbands is not None else None,
        bollinger_lower=_last(bbands["BBL_20_2.0"]) if bbands is not None else None,
        bollinger_bandwidth=_last(bbands["BBB_20_2.0"]) if bbands is not None else None,
        volume_ma_20=_last(volume_ma_20),
        support_level=_last(support),
        resistance_level=_last(resistance),
    )

    if (
        indicators.sma_20 is not None
        and indicators.sma_50 is not None
        and price > indicators.sma_20 > indicators.sma_50
    ):
        trend = TrendSignal.BULLISH
    elif (
        indicators.sma_20 is not None
        and indicators.sma_50 is not None
        and price < indicators.sma_20 < indicators.sma_50
    ):
        trend = TrendSignal.BEARISH
    else:
        trend = TrendSignal.NEUTRAL

    latest_volume = volume.iloc[-1]
    unusual_volume = bool(
        indicators.volume_ma_20 is not None
        and not pd.isna(latest_volume)
        and latest_volume > indicators.volume_ma_20 * unusual_volume_threshold
    )
    breakout = bool(
        indicators.resistance_level is not None
        and price > indicators.resistance_level
        and unusual_volume
    )

    return TechnicalSnapshotResult(
        indicators=indicators,
        signals=TechnicalSignals(trend=trend, breakout=breakout, unusual_volume=unusual_volume),
        computed_through_date=window_candles[-1].candle_date,
        window_size=window,
        latest_close=float(price),
    )
