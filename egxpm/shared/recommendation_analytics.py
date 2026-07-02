"""Recommendation performance analytics — pure arithmetic over already-loaded
Outcome records, the same category as AllocationCalculator (Section 12.6):
importable by both the Dashboard (read time) and anywhere else that needs
it, with exactly one implementation rather than duplicating the arithmetic
inline in a Streamlit page function.

quality_classification on Outcome is never auto-assigned here or anywhere
(invariant, Section 10.4) — this module only aggregates rates/averages
over fields a Job or the user has already recorded.
"""

from __future__ import annotations

from egxpm.persistence.models import Outcome, RecommendationPerformanceSummary


def summarize_performance(outcomes: list[Outcome]) -> RecommendationPerformanceSummary:
    """Pure. Computes target-hit rate, stop-hit rate, and average return
    over FINAL outcomes only (Outcome.is_final=True) — a still-open
    position's target_hit/stop_hit/actual_return aren't yet meaningful and
    would bias the rates if included.

    Rates and the average are None (not 0.0) when there's no final outcome
    (or, for average_return, no final outcome with a non-null actual_return)
    to compute them from — an honestly-absent number, not a misleading zero.
    """
    final_outcomes = [o for o in outcomes if o.is_final]
    if not final_outcomes:
        return RecommendationPerformanceSummary(final_outcome_count=0)

    target_hits = sum(1 for o in final_outcomes if o.target_hit)
    stop_hits = sum(1 for o in final_outcomes if o.stop_hit)
    returns = [o.actual_return for o in final_outcomes if o.actual_return is not None]

    return RecommendationPerformanceSummary(
        final_outcome_count=len(final_outcomes),
        target_hit_rate=target_hits / len(final_outcomes),
        stop_hit_rate=stop_hits / len(final_outcomes),
        average_return=(sum(returns) / len(returns)) if returns else None,
    )
