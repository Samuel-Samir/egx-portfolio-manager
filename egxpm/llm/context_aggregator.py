"""Context Aggregator — Stage 11 of the canonical pipeline.

Pure function: receives already-loaded domain objects from Orchestration
and produces a token-budget-constrained CuratedContext for the Reasoning
Layer. No Persistence access — everything here is data already in memory
from earlier pipeline stages.

The contract signature (score, confidence, portfolio, sizing,
historical_summary, sector_summary, market_summary) has no separate
`company` parameter, so the `company` field below is limited to what's
derivable from `score.company_id` — full name/sector would need a Company
object the contract doesn't pass in.
"""

from __future__ import annotations

from pydantic import BaseModel

from egxpm.engine.position_sizing_engine import PositionSizing
from egxpm.persistence.models import AllocationReport, ConfidenceScore, MarketSummary, Score, SectorSummary

TOP_N = 3


class HistoricalSummary(BaseModel):
    recent_composite_scores: list[float] = []
    recommendation_win_rate: float | None = None
    recommendation_sample_count: int = 0


class CuratedContext(BaseModel):
    company: dict
    score_summary: dict
    confidence_summary: dict
    portfolio_context: dict
    market_context: dict
    position_sizing: dict | None
    historical_summary: dict
    data_freshness_flags: list[dict]


def _metric_ratios(breakdown: dict) -> list[tuple[str, float]]:
    ratios = []
    for name, entry in breakdown.items():
        if not isinstance(entry, dict):
            continue
        points, max_points = entry.get("points"), entry.get("max")
        if points is None or not max_points:
            continue
        ratios.append((name, points / max_points))
    return ratios


def _strengths_and_weaknesses(score: Score, top_n: int = TOP_N) -> tuple[list[str], list[str]]:
    ratios = _metric_ratios(score.financial_breakdown) + _metric_ratios(score.technical_breakdown)
    ratios.sort(key=lambda pair: pair[1], reverse=True)
    strengths = [name for name, _ in ratios[:top_n]]
    weaknesses = [name for name, _ in reversed(ratios[-top_n:])] if ratios else []
    return strengths, weaknesses


def _score_trend_narrative(recent_scores: list[float]) -> str:
    if len(recent_scores) < 2:
        return "insufficient_data"
    if all(b > a for a, b in zip(recent_scores, recent_scores[1:])):
        return "improving"
    if all(b < a for a, b in zip(recent_scores, recent_scores[1:])):
        return "declining"
    return "stable"


def _lowest_confidence_component(confidence: ConfidenceScore) -> str | None:
    components = {
        "freshness": confidence.freshness_component,
        "source_quality": confidence.source_quality_component,
        "source_health": confidence.source_health_component,
        "historical_accuracy": confidence.historical_accuracy_component,
    }
    available = {name: value for name, value in components.items() if value is not None}
    if not available:
        return None
    return min(available, key=available.get)


def build_context(
    score: Score,
    confidence: ConfidenceScore,
    portfolio: AllocationReport,
    sizing: PositionSizing | None,
    historical_summary: HistoricalSummary,
    sector_summary: SectorSummary | None,
    market_summary: MarketSummary | None,
) -> CuratedContext:
    """Pure. No exceptions — every field degrades gracefully when its
    source data is missing (None sizing for the long-term pipeline,
    missing sector/market summaries, etc.)."""
    strengths, weaknesses = _strengths_and_weaknesses(score)

    return CuratedContext(
        company={"company_id": score.company_id},
        score_summary={
            "composite": score.composite_score,
            "financial": score.financial_score,
            "technical": score.technical_score,
            "news": score.news_score,
            "key_strengths": strengths,
            "key_weaknesses": weaknesses,
            "score_trend": _score_trend_narrative(historical_summary.recent_composite_scores),
        },
        confidence_summary={
            "value": confidence.confidence_value,
            "lowest_component": _lowest_confidence_component(confidence),
        },
        portfolio_context={
            "current_pct": portfolio.by_stock_pct.get(score.company_id, 0.0),
            "target_deviation": portfolio.target_deviation,
            "violations": portfolio.stock_constraint_violations,
        },
        market_context={
            "sector_score": sector_summary.summary_score if sector_summary else None,
            "sector": sector_summary.sector if sector_summary else None,
            "market_score": market_summary.summary_score if market_summary else None,
        },
        position_sizing=(
            {
                "entry": sizing.entry_price, "stop_loss": sizing.stop_loss,
                "take_profit": sizing.take_profit, "size": sizing.position_size,
                "rr_ratio": sizing.risk_reward_ratio,
            }
            if sizing is not None else None
        ),
        historical_summary={
            "score_trend_narrative": _score_trend_narrative(historical_summary.recent_composite_scores),
            "recommendation_success_rate": historical_summary.recommendation_win_rate,
            "sample_count": historical_summary.recommendation_sample_count,
        },
        data_freshness_flags=[
            {"aspect": "overall_freshness", "value": confidence.freshness_component},
        ],
    )
