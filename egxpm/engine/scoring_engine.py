"""Scoring Engine — Stage 6 (and 6c) of the canonical pipeline, plus the
Stage 6a dashboard-facing Sector/Market aggregation.

Pure functions: financial/technical/news rubrics and weighted combination
only, no I/O. Rubric point allocations, RSI zones, and D/E ceilings below
are this system's own v1 investment-scoring judgment calls — the
architecture doc specifies the 3-component structure and one breakdown
JSON example, not exact point values, so these are documented, deterministic,
and unit-tested rather than left implicit.
"""

from __future__ import annotations

from pydantic import BaseModel

from egxpm.engine.financial_engine import FinancialMetrics, GrowthTrend
from egxpm.engine.technical_engine import TechnicalSnapshotResult
from egxpm.persistence.models import (
    ConfigurationSnapshot,
    MarketSummary,
    NewsItem,
    RiskScore,
    Score,
    SectorSummary,
    StatementSchema,
    TrendSignal,
)
from egxpm.shared.exceptions import InsufficientDataError, InvalidWeightsError

REQUIRED_WEIGHT_KEYS = ("financial", "technical", "news", "risk")

# ------------------------------------------------------------
# Financial Score rubric (0-100 total)
# ------------------------------------------------------------

# metric_name: (low, high, max_points) — linear scale, higher raw value is
# better, clamped to [0, max_points] outside [low, high].
FINANCIAL_RUBRIC: dict[str, tuple[float, float, float]] = {
    "revenue_growth": (0.0, 0.25, 15),
    "net_income_growth": (0.0, 0.25, 15),
    "eps_growth": (0.0, 0.25, 10),
    "net_margin": (0.0, 0.30, 15),
    "return_on_equity": (0.0, 0.25, 15),
    "return_on_assets": (0.0, 0.10, 10),
    "free_cash_flow_margin": (0.0, 0.20, 5),
}

# Debt/Equity is scored with schema-aware ceilings, not the shared rubric
# above: banks structurally carry much higher D/E than industrials (customer
# deposits count as liabilities), so a shared threshold would penalize every
# bank stock regardless of actual financial health — the same class of
# schema-fairness issue that already required excluding operating_margin
# for banks in the Financial Engine.
DEBT_TO_EQUITY_CEILING: dict[StatementSchema, float] = {
    StatementSchema.INDUSTRIAL: 2.0,
    StatementSchema.BANK: 12.0,
}
DEBT_TO_EQUITY_DEFAULT_CEILING = 2.0  # INSURANCE/HOLDING stubs fall back to the industrial ceiling
DEBT_TO_EQUITY_MAX_POINTS = 10.0

GROWTH_TREND_POINTS: dict[GrowthTrend, float | None] = {
    GrowthTrend.ACCELERATING: 5.0,
    GrowthTrend.STABLE: 3.0,
    GrowthTrend.DECELERATING: 1.0,
    GrowthTrend.INSUFFICIENT_DATA: None,  # no signal — excluded, not penalized
}
GROWTH_TREND_MAX_POINTS = 5.0

# ------------------------------------------------------------
# Technical Score rubric (0-100 total)
# ------------------------------------------------------------

TREND_POINTS: dict[TrendSignal, float] = {
    TrendSignal.BULLISH: 40.0, TrendSignal.NEUTRAL: 20.0, TrendSignal.BEARISH: 0.0,
}
TREND_MAX_POINTS = 40.0

RSI_HEALTHY_RANGE = (40.0, 70.0)   # full points: bullish momentum without being overbought
RSI_MODERATE_RANGE = (30.0, 80.0)  # half points: approaching either extreme
RSI_MAX_POINTS = 20.0

MACD_MAX_POINTS = 15.0
BREAKOUT_MAX_POINTS = 15.0
UNUSUAL_VOLUME_MAX_POINTS = 10.0


def _scale(value: float, low: float, high: float, max_points: float, inverse: bool = False) -> float:
    fraction = 0.0 if high == low else (value - low) / (high - low)
    fraction = max(0.0, min(1.0, fraction))
    if inverse:
        fraction = 1.0 - fraction
    return fraction * max_points


def _rsi_points(rsi: float) -> float:
    healthy_low, healthy_high = RSI_HEALTHY_RANGE
    moderate_low, moderate_high = RSI_MODERATE_RANGE
    if healthy_low <= rsi <= healthy_high:
        return RSI_MAX_POINTS
    if moderate_low <= rsi <= moderate_high:
        return RSI_MAX_POINTS / 2
    return 0.0


def _combine(
    entries: list[tuple[str, float | None, float, object]], null_handling_policy: str
) -> tuple[float | None, dict]:
    """Combines (name, points, max_points, raw_value) entries into a 0-100
    score plus a breakdown dict, per the configured null-handling policy.
    """
    breakdown: dict = {}
    if null_handling_policy == "treat_as_zero":
        total_max = sum(max_points for _, _, max_points, _ in entries)
        total_points = 0.0
        any_present = False
        for name, points, max_points, raw_value in entries:
            if points is not None:
                any_present = True
            actual = points if points is not None else 0.0
            breakdown[name] = {"value": raw_value, "points": round(actual, 4), "max": max_points}
            total_points += actual
        if not any_present or total_max == 0:
            return None, breakdown
        return (total_points / total_max) * 100.0, breakdown

    # exclude_and_renormalize (default)
    total_max = 0.0
    total_points = 0.0
    for name, points, max_points, raw_value in entries:
        if points is None:
            breakdown[name] = {"value": raw_value, "points": None, "max": max_points}
            continue
        breakdown[name] = {"value": raw_value, "points": round(points, 4), "max": max_points}
        total_points += points
        total_max += max_points
    if total_max == 0:
        return None, breakdown
    return (total_points / total_max) * 100.0, breakdown


def _score_financial(
    metrics: FinancialMetrics, null_handling_policy: str
) -> tuple[float | None, dict]:
    entries: list[tuple[str, float | None, float, object]] = []
    for name, (low, high, max_points) in FINANCIAL_RUBRIC.items():
        raw_value = getattr(metrics, name)
        points = None if raw_value is None else _scale(raw_value, low, high, max_points)
        entries.append((name, points, max_points, raw_value))

    ceiling = DEBT_TO_EQUITY_CEILING.get(metrics.statement_schema, DEBT_TO_EQUITY_DEFAULT_CEILING)
    de_value = metrics.debt_to_equity
    de_points = (
        None if de_value is None
        else _scale(de_value, 0.0, ceiling, DEBT_TO_EQUITY_MAX_POINTS, inverse=True)
    )
    entries.append(("debt_to_equity", de_points, DEBT_TO_EQUITY_MAX_POINTS, de_value))

    trend_points = GROWTH_TREND_POINTS[metrics.growth_trend]
    entries.append(("growth_trend", trend_points, GROWTH_TREND_MAX_POINTS, metrics.growth_trend.value))

    return _combine(entries, null_handling_policy)


def _score_technical(
    snapshot: TechnicalSnapshotResult, null_handling_policy: str
) -> tuple[float | None, dict]:
    indicators, signals = snapshot.indicators, snapshot.signals
    entries: list[tuple[str, float | None, float, object]] = []

    trend_points = None if signals.trend is None else TREND_POINTS[signals.trend]
    entries.append(("trend", trend_points, TREND_MAX_POINTS, signals.trend.value if signals.trend else None))

    rsi_points = None if indicators.rsi is None else _rsi_points(indicators.rsi)
    entries.append(("rsi", rsi_points, RSI_MAX_POINTS, indicators.rsi))

    macd_points = None
    if indicators.macd is not None and indicators.macd_signal is not None:
        macd_points = MACD_MAX_POINTS if indicators.macd > indicators.macd_signal else 0.0
    entries.append(("macd_crossover", macd_points, MACD_MAX_POINTS, indicators.macd))

    breakout_points = None if signals.breakout is None else (BREAKOUT_MAX_POINTS if signals.breakout else 0.0)
    entries.append(("breakout", breakout_points, BREAKOUT_MAX_POINTS, signals.breakout))

    volume_points = (
        None if signals.unusual_volume is None
        else (UNUSUAL_VOLUME_MAX_POINTS if signals.unusual_volume else 0.0)
    )
    entries.append(("unusual_volume", volume_points, UNUSUAL_VOLUME_MAX_POINTS, signals.unusual_volume))

    return _combine(entries, null_handling_policy)


def _score_news(scored_news: list[NewsItem]) -> tuple[float | None, dict]:
    if not scored_news:
        return None, {"item_count": 0}

    total_relevance = sum(item.relevance_score or 0.0 for item in scored_news)
    if total_relevance <= 0:
        weighted_sentiment = 0.0
    else:
        weighted_sentiment = sum(
            (item.sentiment_score or 0.0) * (item.relevance_score or 0.0) for item in scored_news
        ) / total_relevance

    news_score = (weighted_sentiment + 1.0) / 2.0 * 100.0
    breakdown = {
        "item_count": len(scored_news),
        "avg_sentiment": sum(item.sentiment_score or 0.0 for item in scored_news) / len(scored_news),
        "avg_relevance": total_relevance / len(scored_news),
        "weighted_sentiment": weighted_sentiment,
    }
    return news_score, breakdown


def _validate_weights(weights: ConfigurationSnapshot) -> None:
    missing = [key for key in REQUIRED_WEIGHT_KEYS if key not in weights.scoring_weights]
    if missing:
        raise InvalidWeightsError(f"scoring_weights missing required keys: {missing}")
    total = sum(weights.scoring_weights[key] for key in REQUIRED_WEIGHT_KEYS)
    if abs(total - 1.0) > 1e-6:
        raise InvalidWeightsError(f"scoring_weights must sum to 1.0, got {total}")


class ScoreResult(BaseModel):
    """Pure Engine output — company_id/config_snapshot_id/job_id are
    Orchestration metadata, attached afterward via build_score(), the same
    separation used for TechnicalSnapshotResult in the Technical Engine.
    """
    financial_score: float | None = None
    financial_breakdown: dict = {}
    technical_score: float | None = None
    technical_breakdown: dict = {}
    news_score: float | None = None
    news_breakdown: dict = {}
    composite_score: float | None = None


def calculate_score(
    financial_metrics: FinancialMetrics,
    technical_snapshot: TechnicalSnapshotResult,
    scored_news: list[NewsItem],
    weights: ConfigurationSnapshot,
) -> ScoreResult:
    """Stage 6: computes the three sub-scores. composite_score is left None
    until Stage 6c (assemble_composite_score), once RiskScore exists.

    Raises:
        InvalidWeightsError: scoring_weights is missing a required key, or
            financial+technical+news+risk don't sum to 1.0.
    """
    _validate_weights(weights)
    null_handling_policy = weights.scoring_weights.get("null_handling_policy", "exclude_and_renormalize")

    financial_score, financial_breakdown = _score_financial(financial_metrics, null_handling_policy)
    technical_score, technical_breakdown = _score_technical(technical_snapshot, null_handling_policy)
    news_score, news_breakdown = _score_news(scored_news)

    return ScoreResult(
        financial_score=financial_score, financial_breakdown=financial_breakdown,
        technical_score=technical_score, technical_breakdown=technical_breakdown,
        news_score=news_score, news_breakdown=news_breakdown, composite_score=None,
    )


def build_score(
    result: ScoreResult, company_id: str, config_snapshot_id: str, job_id: str
) -> Score:
    """Merges a pure ScoreResult with Orchestration-supplied identifiers
    into the persistable Score."""
    return Score(
        company_id=company_id,
        financial_score=result.financial_score, financial_breakdown=result.financial_breakdown,
        technical_score=result.technical_score, technical_breakdown=result.technical_breakdown,
        news_score=result.news_score, news_breakdown=result.news_breakdown,
        composite_score=result.composite_score,
        config_snapshot_id=config_snapshot_id, job_id=job_id,
    )


def _combine_weighted(
    components: list[tuple[str, float | None, float]], null_handling_policy: str
) -> float | None:
    if null_handling_policy == "treat_as_zero":
        weighted_sum = sum(w * (v if v is not None else 0.0) for _, v, w in components)
        return weighted_sum

    available = [(v, w) for _, v, w in components if v is not None]
    total_weight = sum(w for _, w in available)
    if total_weight == 0:
        return None
    return sum(v * w for v, w in available) / total_weight


def assemble_composite_score(
    score: Score, risk_score: RiskScore, weights: ConfigurationSnapshot
) -> Score:
    """Stage 6c: combines the three sub-scores with RiskScore.value into
    composite_score, using the same weight set validated at Stage 6.

    Pure. Returns a new Score (never mutates the input) — composite_score
    is finalized here, before Score is ever written (it's append-only).
    """
    null_handling_policy = weights.scoring_weights.get("null_handling_policy", "exclude_and_renormalize")
    components = [
        ("financial", score.financial_score, weights.scoring_weights["financial"]),
        ("technical", score.technical_score, weights.scoring_weights["technical"]),
        ("news", score.news_score, weights.scoring_weights["news"]),
        ("risk", risk_score.value, weights.scoring_weights["risk"]),
    ]
    composite = _combine_weighted(components, null_handling_policy)
    return score.model_copy(update={"composite_score": composite})


def aggregate_sector_summary(sector: str, scores: list[Score], job_id: str) -> SectorSummary:
    """Dashboard-facing aggregate: mean composite_score across a sector's
    companies. Computed after Stage 6c (composite must exist first) —
    distinct from Risk Engine's SectorPeerSummary (Stage 6a, D/E-only).

    Raises:
        InsufficientDataError: no company in `scores` has a composite_score yet.
    """
    scored = [s for s in scores if s.composite_score is not None]
    if not scored:
        raise InsufficientDataError(f"no composite scores available for sector={sector!r}")
    summary_score = sum(s.composite_score for s in scored) / len(scored)
    return SectorSummary(
        sector=sector, summary_score=summary_score,
        component_company_scores=[
            {"company_id": s.company_id, "composite_score": s.composite_score} for s in scored
        ],
        job_id=job_id,
    )


def aggregate_market_summary(sector_summaries: list[SectorSummary], job_id: str) -> MarketSummary:
    """Raises: InsufficientDataError if sector_summaries is empty."""
    if not sector_summaries:
        raise InsufficientDataError("no sector summaries available")
    summary_score = sum(s.summary_score for s in sector_summaries) / len(sector_summaries)
    return MarketSummary(
        summary_score=summary_score,
        component_sector_summaries=[
            {"sector": s.sector, "summary_score": s.summary_score} for s in sector_summaries
        ],
        job_id=job_id,
    )
