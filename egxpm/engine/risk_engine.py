"""Risk Engine — Stage 6b of the canonical pipeline.

Pure function: assesses investment risk (not data reliability — that's the
Confidence Engine's job; the two are independent dimensions per the
architecture doc). Runs after the Stage 6a synchronization barrier, since
debt_peer_score needs every company's D/E ratio already aggregated into a
SectorPeerSummary.

Per the contract, missing inputs never raise — they "degrade toward
conservative mid-range": any component whose inputs are unavailable is
scored as penalty=50 (neither low- nor high-risk), rather than excluded
(which could understate risk by only averaging the components that happen
to look good) or defaulted to 0 (which would be an unjustified clean bill
of health).
"""

from __future__ import annotations

from pydantic import BaseModel

from egxpm.persistence.models import ConfigurationSnapshot, RiskScore, Score

CONSERVATIVE_DEFAULT_PENALTY = 50.0

# Component blend weights: the architecture doc names these 4 components
# but doesn't specify their relative weight in the final penalty — equal
# weighting is this system's documented v1 default.
RISK_COMPONENT_WEIGHTS = {
    "debt_peer": 0.25, "score_volatility": 0.25, "data_completeness": 0.25, "liquidity": 0.25,
}

DEBT_PEER_RATIO_CEILING = 2.0       # D/E at 2x the sector median or more -> full penalty
SCORE_VOLATILITY_CEILING = 20.0     # std_dev of last N composite scores, points
LIQUIDITY_RATIO_CEILING = 0.20      # position as a fraction of avg daily volume


class SectorPeerSummary(BaseModel):
    sector: str
    median_debt_to_equity: float | None = None
    peer_count: int = 0


class HistoricalScoreSummary(BaseModel):
    std_dev: float | None = None


class LiquiditySummary(BaseModel):
    avg_daily_volume_egp: float | None = None
    # Risk Engine runs at Stage 6b, before Position Sizing (Stage 9) exists,
    # so there is no real ATR-based position size yet. Orchestration
    # supplies a hypothetical worst case instead — typically
    # max_position_pct * portfolio_total — so liquidity risk reflects "if we
    # took the largest position our own constraints allow," not a number
    # that doesn't exist yet.
    hypothetical_position_size_egp: float | None = None


def build_sector_peer_summary(sector: str, debt_to_equity_values: list[float | None]) -> SectorPeerSummary:
    """Stage 6a: aggregates a sector's D/E ratios into the median Risk Engine compares against.

    Pure. Called once per sector after every company's Score exists for
    this run — the synchronization barrier itself. Company-level D/E
    values are read from each Score's financial_breakdown (Risk Engine
    receives a single Score, not a FinancialMetrics list, so this must be
    assembled from data already on the Score objects).
    """
    values = sorted(v for v in debt_to_equity_values if v is not None)
    if not values:
        return SectorPeerSummary(sector=sector, median_debt_to_equity=None, peer_count=0)
    n = len(values)
    mid = n // 2
    median = values[mid] if n % 2 == 1 else (values[mid - 1] + values[mid]) / 2.0
    return SectorPeerSummary(sector=sector, median_debt_to_equity=median, peer_count=n)


def _scale(value: float, low: float, high: float, max_points: float) -> float:
    fraction = 0.0 if high == low else (value - low) / (high - low)
    return max(0.0, min(1.0, fraction)) * max_points


def _debt_peer_penalty(score: Score, peer_summary: SectorPeerSummary) -> float:
    company_de = score.financial_breakdown.get("debt_to_equity", {}).get("value")
    if company_de is None or peer_summary.median_debt_to_equity is None or peer_summary.median_debt_to_equity <= 0:
        return CONSERVATIVE_DEFAULT_PENALTY
    if company_de < 0:
        return 100.0  # negative equity — a distress signal on its own, independent of peers
    ratio = company_de / peer_summary.median_debt_to_equity
    return _scale(ratio, low=1.0, high=DEBT_PEER_RATIO_CEILING, max_points=100.0)


def _score_volatility_penalty(historical_score_summary: HistoricalScoreSummary) -> float:
    std_dev = historical_score_summary.std_dev
    if std_dev is None:
        return CONSERVATIVE_DEFAULT_PENALTY
    return _scale(std_dev, low=0.0, high=SCORE_VOLATILITY_CEILING, max_points=100.0)


def _data_completeness_penalty(score: Score) -> float:
    non_null = 0
    total = 0
    for breakdown in (score.financial_breakdown, score.technical_breakdown):
        for entry in breakdown.values():
            if isinstance(entry, dict) and "value" in entry:
                total += 1
                if entry["value"] is not None:
                    non_null += 1
    # news_breakdown isn't a per-metric dict (it's aggregate stats), so its
    # presence is judged via news_score itself: either we have scored news
    # or we don't.
    total += 1
    if score.news_score is not None:
        non_null += 1

    if total == 0:
        return CONSERVATIVE_DEFAULT_PENALTY
    completeness = non_null / total
    return (1.0 - completeness) * 100.0


def _liquidity_penalty(liquidity_summary: LiquiditySummary) -> float:
    position = liquidity_summary.hypothetical_position_size_egp
    volume = liquidity_summary.avg_daily_volume_egp
    if position is None or volume is None or volume <= 0:
        return CONSERVATIVE_DEFAULT_PENALTY
    ratio = position / volume
    return _scale(ratio, low=0.0, high=LIQUIDITY_RATIO_CEILING, max_points=100.0)


def calculate_risk_score(
    score: Score,
    peer_summary: SectorPeerSummary,
    historical_score_summary: HistoricalScoreSummary,
    liquidity_summary: LiquiditySummary,
    config: ConfigurationSnapshot,
) -> RiskScore:
    """Pure. Raises: none — missing inputs degrade toward conservative mid-range.

    `config` is accepted per the engine contract but not read here: the
    component ceilings and blend weights above are fixed v1 system
    constants, not currently exposed as config.yaml keys. Kept as a
    parameter so a future config-driven version of this Engine doesn't
    need a signature change.
    """
    debt_peer = _debt_peer_penalty(score, peer_summary)
    score_volatility = _score_volatility_penalty(historical_score_summary)
    data_completeness = _data_completeness_penalty(score)
    liquidity = _liquidity_penalty(liquidity_summary)

    weighted_penalty = (
        debt_peer * RISK_COMPONENT_WEIGHTS["debt_peer"]
        + score_volatility * RISK_COMPONENT_WEIGHTS["score_volatility"]
        + data_completeness * RISK_COMPONENT_WEIGHTS["data_completeness"]
        + liquidity * RISK_COMPONENT_WEIGHTS["liquidity"]
    )
    value = max(0.0, min(100.0, 100.0 - weighted_penalty))

    return RiskScore(
        score_id=score.score_id,
        value=value,
        debt_peer_component=debt_peer,
        score_volatility_component=score_volatility,
        data_completeness_component=data_completeness,
        liquidity_component=liquidity,
        breakdown={
            "debt_peer_penalty": debt_peer, "score_volatility_penalty": score_volatility,
            "data_completeness_penalty": data_completeness, "liquidity_penalty": liquidity,
            "weighted_risk_penalty": weighted_penalty,
        },
    )
