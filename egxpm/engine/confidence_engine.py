"""Confidence Engine — Stage 7 of the canonical pipeline.

Pure function: assesses data reliability (not investment risk — that's the
Risk Engine's job; the two are independent dimensions per the architecture
doc. RiskScore is deliberately NOT an input here). All 5 inputs are
pre-loaded and supplied by Orchestration; this Engine never queries
Persistence, and never computes a source-health rolling window itself
(that's SourceHealthService's job, cached for 1 hour, called by
Orchestration before this Engine runs).
"""

from __future__ import annotations

from pydantic import BaseModel

from egxpm.persistence.models import ConfidenceScore, Score, SourceQuality

# Fixed system constants (per the architecture doc's Source Quality Tiers
# table) — not user-configurable, unlike scoring weights.
SOURCE_QUALITY_WEIGHTS: dict[SourceQuality, float] = {
    SourceQuality.OFFICIAL: 1.0,
    SourceQuality.INTERNAL: 1.0,
    SourceQuality.SCRAPED: 0.7,
    SourceQuality.MANUAL: 0.8,
}

# Confidence blends 4 components (freshness, source quality, source health,
# historical accuracy) — the doc names them and gives per-tier weights for
# source quality specifically, but not the 4 components' relative share of
# the final blend. Equal weighting is this system's documented v1 default.
CONFIDENCE_COMPONENT_WEIGHTS = {
    "freshness": 0.25, "source_quality": 0.25, "source_health": 0.25, "historical_accuracy": 0.25,
}

# Below this many sample recommendations, a raw win rate is too noisy to
# trust — use a neutral 0.5 instead, per the contract.
HISTORICAL_ACCURACY_MIN_SAMPLES = 5
HISTORICAL_ACCURACY_NEUTRAL = 0.5


class FreshnessMetadata(BaseModel):
    """Per-artifact freshness, already normalized to [0,1] (1.0 = fresh) by
    Orchestration comparing fetched_at against config.yaml's
    freshness_thresholds — this Engine takes no config and does no date math.
    """
    prices_freshness: float | None = None
    technicals_freshness: float | None = None
    fundamentals_freshness: float | None = None
    news_freshness: float | None = None


class SourceQualitySummary(BaseModel):
    """One SourceQuality tier per artifact that contributed to this Score
    (e.g. [SCRAPED, INTERNAL, SCRAPED] for fundamentals/technicals/news)."""
    source_qualities: list[SourceQuality] = []


class SourceHealthSummary(BaseModel):
    """success_rate: rolling 30-day CollectionRun success rate [0,1],
    computed by SourceHealthService (1-hour TTL cache)."""
    success_rate: float | None = None


class HistoricalAccuracySummary(BaseModel):
    sample_count: int = 0
    win_rate: float | None = None


def _freshness_component(freshness: FreshnessMetadata) -> float:
    values = [
        v for v in (
            freshness.prices_freshness, freshness.technicals_freshness,
            freshness.fundamentals_freshness, freshness.news_freshness,
        ) if v is not None
    ]
    if not values:
        return 0.5  # unknown freshness — neutral, not assumed fresh
    return sum(values) / len(values)


def _source_quality_component(source_quality: SourceQualitySummary) -> float:
    if not source_quality.source_qualities:
        return 0.5
    weights = [SOURCE_QUALITY_WEIGHTS[tier] for tier in source_quality.source_qualities]
    return sum(weights) / len(weights)


def _source_health_component(source_health: SourceHealthSummary) -> float:
    return source_health.success_rate if source_health.success_rate is not None else 0.5


def _historical_accuracy_component(historical_accuracy: HistoricalAccuracySummary) -> float:
    if historical_accuracy.sample_count < HISTORICAL_ACCURACY_MIN_SAMPLES or historical_accuracy.win_rate is None:
        return HISTORICAL_ACCURACY_NEUTRAL
    return historical_accuracy.win_rate


def calculate_confidence(
    score: Score,
    freshness: FreshnessMetadata,
    source_quality: SourceQualitySummary,
    source_health: SourceHealthSummary,
    historical_accuracy: HistoricalAccuracySummary,
) -> ConfidenceScore:
    """Pure. Raises: none."""
    freshness_component = _freshness_component(freshness)
    source_quality_component = _source_quality_component(source_quality)
    source_health_component = _source_health_component(source_health)
    historical_accuracy_component = _historical_accuracy_component(historical_accuracy)

    confidence_value = (
        freshness_component * CONFIDENCE_COMPONENT_WEIGHTS["freshness"]
        + source_quality_component * CONFIDENCE_COMPONENT_WEIGHTS["source_quality"]
        + source_health_component * CONFIDENCE_COMPONENT_WEIGHTS["source_health"]
        + historical_accuracy_component * CONFIDENCE_COMPONENT_WEIGHTS["historical_accuracy"]
    )

    return ConfidenceScore(
        score_id=score.score_id,
        confidence_value=confidence_value,
        freshness_component=freshness_component,
        source_quality_component=source_quality_component,
        source_health_component=source_health_component,
        historical_accuracy_component=historical_accuracy_component,
        breakdown={
            "freshness": freshness_component, "source_quality": source_quality_component,
            "source_health": source_health_component, "historical_accuracy": historical_accuracy_component,
        },
    )
