import pytest

from egxpm.persistence.models import TrendSignal
from egxpm.run_swing import passes_swing_filter

THRESHOLD = 55


# ------------------------------------------------------------
# The two explicit M6 validation-criteria cases
# ------------------------------------------------------------

def test_breakout_true_low_score_is_blocked():
    assert passes_swing_filter(
        breakout=True, unusual_volume=False, trend=TrendSignal.NEUTRAL,
        composite_score=15, threshold=THRESHOLD,
    ) is False


def test_breakout_true_high_score_passes():
    assert passes_swing_filter(
        breakout=True, unusual_volume=False, trend=TrendSignal.NEUTRAL,
        composite_score=75, threshold=THRESHOLD,
    ) is True


# ------------------------------------------------------------
# Precedence regression coverage: the WRONG implementation
# (`breakout or unusual_volume or (trend == BULLISH and score >= threshold)`)
# would pass this case since breakout=True short-circuits the OR chain
# regardless of score. The CORRECT implementation requires score >=
# threshold unconditionally.
# ------------------------------------------------------------

def test_unusual_volume_true_low_score_is_blocked():
    assert passes_swing_filter(
        breakout=False, unusual_volume=True, trend=TrendSignal.BEARISH,
        composite_score=10, threshold=THRESHOLD,
    ) is False


def test_bullish_trend_low_score_is_blocked():
    assert passes_swing_filter(
        breakout=False, unusual_volume=False, trend=TrendSignal.BULLISH,
        composite_score=10, threshold=THRESHOLD,
    ) is False


def test_bullish_trend_high_score_passes():
    assert passes_swing_filter(
        breakout=False, unusual_volume=False, trend=TrendSignal.BULLISH,
        composite_score=75, threshold=THRESHOLD,
    ) is True


def test_no_technical_signal_at_all_blocked_regardless_of_score():
    assert passes_swing_filter(
        breakout=False, unusual_volume=False, trend=TrendSignal.NEUTRAL,
        composite_score=100, threshold=THRESHOLD,
    ) is False


def test_score_exactly_at_threshold_passes():
    assert passes_swing_filter(
        breakout=True, unusual_volume=False, trend=TrendSignal.NEUTRAL,
        composite_score=THRESHOLD, threshold=THRESHOLD,
    ) is True


def test_none_composite_score_is_blocked():
    assert passes_swing_filter(
        breakout=True, unusual_volume=True, trend=TrendSignal.BULLISH,
        composite_score=None, threshold=THRESHOLD,
    ) is False


def test_none_signals_treated_as_falsy():
    assert passes_swing_filter(
        breakout=None, unusual_volume=None, trend=None,
        composite_score=90, threshold=THRESHOLD,
    ) is False
