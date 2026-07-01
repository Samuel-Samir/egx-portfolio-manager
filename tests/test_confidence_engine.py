import pytest

from egxpm.engine.confidence_engine import (
    HISTORICAL_ACCURACY_NEUTRAL,
    FreshnessMetadata,
    HistoricalAccuracySummary,
    SourceHealthSummary,
    SourceQualitySummary,
    calculate_confidence,
)
from egxpm.persistence.models import Score, SourceQuality


def _score():
    return Score(company_id="TMGH", config_snapshot_id="cfg-1", job_id="job-1")


FULL_FRESHNESS = FreshnessMetadata(
    prices_freshness=1.0, technicals_freshness=1.0, fundamentals_freshness=1.0, news_freshness=1.0,
)
NO_FRESHNESS = FreshnessMetadata()
OFFICIAL_QUALITY = SourceQualitySummary(source_qualities=[SourceQuality.OFFICIAL, SourceQuality.INTERNAL])
SCRAPED_QUALITY = SourceQualitySummary(source_qualities=[SourceQuality.SCRAPED])
HEALTHY_SOURCE = SourceHealthSummary(success_rate=1.0)
UNHEALTHY_SOURCE = SourceHealthSummary(success_rate=0.2)


def test_fully_fresh_official_healthy_high_accuracy_yields_high_confidence():
    result = calculate_confidence(
        _score(), FULL_FRESHNESS, OFFICIAL_QUALITY, HEALTHY_SOURCE,
        HistoricalAccuracySummary(sample_count=20, win_rate=0.9),
    )
    assert result.confidence_value > 0.9


def test_stale_scraped_unhealthy_low_accuracy_yields_low_confidence():
    result = calculate_confidence(
        _score(), NO_FRESHNESS, SCRAPED_QUALITY, UNHEALTHY_SOURCE,
        HistoricalAccuracySummary(sample_count=20, win_rate=0.1),
    )
    assert result.confidence_value < 0.5


def test_historical_accuracy_below_min_samples_uses_neutral():
    result = calculate_confidence(
        _score(), FULL_FRESHNESS, OFFICIAL_QUALITY, HEALTHY_SOURCE,
        HistoricalAccuracySummary(sample_count=2, win_rate=0.95),
    )
    assert result.historical_accuracy_component == pytest.approx(HISTORICAL_ACCURACY_NEUTRAL)


def test_historical_accuracy_at_min_samples_uses_real_win_rate():
    result = calculate_confidence(
        _score(), FULL_FRESHNESS, OFFICIAL_QUALITY, HEALTHY_SOURCE,
        HistoricalAccuracySummary(sample_count=5, win_rate=0.8),
    )
    assert result.historical_accuracy_component == pytest.approx(0.8)


def test_source_quality_weights_match_architecture_doc():
    official = calculate_confidence(
        _score(), FULL_FRESHNESS, SourceQualitySummary(source_qualities=[SourceQuality.OFFICIAL]),
        HEALTHY_SOURCE, HistoricalAccuracySummary(sample_count=5, win_rate=0.5),
    )
    scraped = calculate_confidence(
        _score(), FULL_FRESHNESS, SourceQualitySummary(source_qualities=[SourceQuality.SCRAPED]),
        HEALTHY_SOURCE, HistoricalAccuracySummary(sample_count=5, win_rate=0.5),
    )
    manual = calculate_confidence(
        _score(), FULL_FRESHNESS, SourceQualitySummary(source_qualities=[SourceQuality.MANUAL]),
        HEALTHY_SOURCE, HistoricalAccuracySummary(sample_count=5, win_rate=0.5),
    )
    assert official.source_quality_component == pytest.approx(1.0)
    assert scraped.source_quality_component == pytest.approx(0.7)
    assert manual.source_quality_component == pytest.approx(0.8)
    assert official.confidence_value > manual.confidence_value > scraped.confidence_value


def test_missing_freshness_defaults_neutral_not_fresh():
    result = calculate_confidence(
        _score(), NO_FRESHNESS, OFFICIAL_QUALITY, HEALTHY_SOURCE,
        HistoricalAccuracySummary(sample_count=5, win_rate=0.5),
    )
    assert result.freshness_component == pytest.approx(0.5)


def test_missing_source_health_defaults_neutral():
    result = calculate_confidence(
        _score(), FULL_FRESHNESS, OFFICIAL_QUALITY, SourceHealthSummary(success_rate=None),
        HistoricalAccuracySummary(sample_count=5, win_rate=0.5),
    )
    assert result.source_health_component == pytest.approx(0.5)


def test_partial_freshness_averages_available_artifacts():
    partial = FreshnessMetadata(prices_freshness=1.0, technicals_freshness=0.0)
    result = calculate_confidence(
        _score(), partial, OFFICIAL_QUALITY, HEALTHY_SOURCE,
        HistoricalAccuracySummary(sample_count=5, win_rate=0.5),
    )
    assert result.freshness_component == pytest.approx(0.5)


def test_never_raises_on_all_missing_inputs():
    result = calculate_confidence(
        _score(), FreshnessMetadata(), SourceQualitySummary(), SourceHealthSummary(),
        HistoricalAccuracySummary(),
    )
    assert 0.0 <= result.confidence_value <= 1.0


def test_confidence_value_bounded_0_to_1():
    result = calculate_confidence(
        _score(), FULL_FRESHNESS, OFFICIAL_QUALITY, HEALTHY_SOURCE,
        HistoricalAccuracySummary(sample_count=100, win_rate=1.0),
    )
    assert 0.0 <= result.confidence_value <= 1.0


def test_risk_score_is_not_an_input():
    import inspect
    from egxpm.engine.confidence_engine import calculate_confidence as fn
    params = list(inspect.signature(fn).parameters)
    assert "risk_score" not in params
    assert "risk" not in params


def test_deterministic():
    args = (
        _score(), FULL_FRESHNESS, OFFICIAL_QUALITY, HEALTHY_SOURCE,
        HistoricalAccuracySummary(sample_count=10, win_rate=0.6),
    )
    r1 = calculate_confidence(*args)
    r2 = calculate_confidence(*args)
    assert r1.confidence_value == r2.confidence_value
    assert r1.breakdown == r2.breakdown


def test_module_has_no_io_imports():
    import egxpm.engine.confidence_engine as mod
    source = open(mod.__file__).read()
    assert "sqlite3" not in source
    assert "import egxpm.persistence.db" not in source
