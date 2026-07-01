from datetime import date, timedelta

import pytest

from egxpm.engine.technical_engine import calculate_technical_snapshot
from egxpm.persistence.models import PriceCandle, TrendSignal, Timeframe
from egxpm.shared.exceptions import InsufficientDataError


def _make_candles(prices, volumes=None, company_id="COMI", timeframe=Timeframe.DAILY,
                   start=date(2024, 1, 1)):
    candles = []
    d = start
    i = 0
    while i < len(prices):
        if d.weekday() < 5:  # business days only, EGX trades Sun-Thu but weekday spacing doesn't matter here
            p = prices[i]
            v = volumes[i] if volumes is not None else 1000.0
            close = None if p is None else p
            candles.append(PriceCandle(
                company_id=company_id, timeframe=timeframe, candle_date=d.isoformat(),
                open=close, high=None if close is None else close + 0.5,
                low=None if close is None else close - 0.5, close=close, volume=v,
                data_source_id="yfinance", source_version="1", collection_run_id="r1",
            ))
            i += 1
        d += timedelta(days=1)
    return candles


# ------------------------------------------------------------
# Correct output for valid input
# ------------------------------------------------------------

def test_monotonic_uptrend_yields_bullish():
    prices = [50 + i * 0.5 for i in range(210)]  # strictly increasing
    candles = _make_candles(prices)
    result = calculate_technical_snapshot(candles, window=200)
    assert result.signals.trend == TrendSignal.BULLISH
    assert result.indicators.sma_20 > result.indicators.sma_50
    assert result.window_size == 200
    assert result.computed_through_date == candles[-1].candle_date


def test_monotonic_downtrend_yields_bearish():
    prices = [200 - i * 0.5 for i in range(210)]  # strictly decreasing
    candles = _make_candles(prices)
    result = calculate_technical_snapshot(candles, window=200)
    assert result.signals.trend == TrendSignal.BEARISH
    assert result.indicators.sma_20 < result.indicators.sma_50


def test_flat_series_yields_neutral_and_no_breakout():
    prices = [100.0] * 210
    candles = _make_candles(prices)
    result = calculate_technical_snapshot(candles, window=200)
    assert result.signals.trend == TrendSignal.NEUTRAL
    assert result.signals.breakout is False
    assert result.signals.unusual_volume is False


def test_price_spike_with_volume_spike_triggers_breakout():
    prices = [100.0] * 209 + [200.0]  # flat history, then a sharp final-day spike
    volumes = [1000.0] * 209 + [5000.0]  # far above volume_ma_20 * 1.5
    candles = _make_candles(prices, volumes=volumes)
    result = calculate_technical_snapshot(candles, window=200)
    assert result.signals.unusual_volume is True
    assert result.indicators.resistance_level == pytest.approx(100.5)
    assert result.signals.breakout is True


def test_unusual_volume_without_breakout():
    prices = [100.0] * 210  # flat — no resistance to break
    volumes = [1000.0] * 209 + [5000.0]
    candles = _make_candles(prices, volumes=volumes)
    result = calculate_technical_snapshot(candles, window=200)
    assert result.signals.unusual_volume is True
    assert result.signals.breakout is False  # price never exceeds resistance


# ------------------------------------------------------------
# Exceptions
# ------------------------------------------------------------

def test_raises_insufficient_data_on_empty_list():
    with pytest.raises(InsufficientDataError):
        calculate_technical_snapshot([], window=200)


def test_raises_insufficient_data_when_fewer_than_window():
    candles = _make_candles([100.0] * 50)
    with pytest.raises(InsufficientDataError):
        calculate_technical_snapshot(candles, window=200)


def test_raises_insufficient_data_when_latest_close_missing():
    candles = _make_candles([100.0] * 209 + [None])
    with pytest.raises(InsufficientDataError):
        calculate_technical_snapshot(candles, window=200)


def test_raises_value_error_on_mixed_companies():
    candles = _make_candles([100.0] * 210)
    candles[-1] = candles[-1].model_copy(update={"company_id": "TMGH"})
    with pytest.raises(ValueError):
        calculate_technical_snapshot(candles, window=200)


def test_raises_value_error_on_mixed_timeframes():
    candles = _make_candles([100.0] * 210)
    # Timeframe only has DAILY today, so simulate a foreign value bypassing validation
    candles[-1].timeframe = "weekly"
    with pytest.raises(ValueError):
        calculate_technical_snapshot(candles, window=200)


def test_raises_value_error_on_non_chronological_order():
    candles = _make_candles([100.0] * 210)
    candles[0], candles[1] = candles[1], candles[0]
    with pytest.raises(ValueError):
        calculate_technical_snapshot(candles, window=200)


def test_raises_value_error_on_duplicate_dates():
    candles = _make_candles([100.0] * 210)
    candles[-1] = candles[-1].model_copy(update={"candle_date": candles[-2].candle_date})
    with pytest.raises(ValueError):
        calculate_technical_snapshot(candles, window=200)


# ------------------------------------------------------------
# Purity / determinism
# ------------------------------------------------------------

def test_calculation_is_deterministic_and_pure():
    candles = _make_candles([100 + (i % 7) for i in range(210)])
    result1 = calculate_technical_snapshot(candles, window=200)
    result2 = calculate_technical_snapshot(candles, window=200)
    assert result1 == result2


def test_module_has_no_io_imports():
    import egxpm.engine.technical_engine as mod
    source = open(mod.__file__).read()
    assert "sqlite3" not in source
    assert "import egxpm.persistence.db" not in source


# ------------------------------------------------------------
# Boundary values
# ------------------------------------------------------------

def test_exactly_window_candles_is_sufficient():
    candles = _make_candles([100 + i * 0.1 for i in range(200)])
    result = calculate_technical_snapshot(candles, window=200)
    assert result.indicators.sma_200 is not None


def test_custom_unusual_volume_threshold():
    prices = [100.0] * 210
    volumes = [1000.0] * 209 + [1600.0]  # 1.6x average — above 1.5x, below 2.0x
    candles = _make_candles(prices, volumes=volumes)
    lenient = calculate_technical_snapshot(candles, window=200, unusual_volume_threshold=2.0)
    strict = calculate_technical_snapshot(candles, window=200, unusual_volume_threshold=1.5)
    assert lenient.signals.unusual_volume is False
    assert strict.signals.unusual_volume is True
