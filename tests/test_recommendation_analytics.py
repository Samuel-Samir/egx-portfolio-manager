from egxpm.persistence.models import Outcome
from egxpm.shared.recommendation_analytics import summarize_performance


def _outcome(is_final=True, target_hit=None, stop_hit=None, actual_return=None):
    return Outcome(
        recommendation_id="rec-1", is_final=is_final,
        target_hit=target_hit, stop_hit=stop_hit, actual_return=actual_return,
    )


def test_no_outcomes_returns_zero_count_and_none_rates():
    summary = summarize_performance([])
    assert summary.final_outcome_count == 0
    assert summary.target_hit_rate is None
    assert summary.stop_hit_rate is None
    assert summary.average_return is None


def test_only_non_final_outcomes_excluded_entirely():
    outcomes = [_outcome(is_final=False, target_hit=True, actual_return=0.5)]
    summary = summarize_performance(outcomes)
    assert summary.final_outcome_count == 0
    assert summary.target_hit_rate is None


def test_hand_computed_rates_and_average_return():
    # 5 outcomes total: 3 final, 2 non-final (must be excluded).
    # Final outcomes: 2 target_hit=True (1 stop_hit=True among them is
    # impossible in practice but the arithmetic doesn't assume mutual
    # exclusivity — each rate is independently hand-computed), 1 neither.
    outcomes = [
        _outcome(is_final=True, target_hit=True, stop_hit=False, actual_return=0.10),
        _outcome(is_final=True, target_hit=True, stop_hit=False, actual_return=-0.05),
        _outcome(is_final=True, target_hit=False, stop_hit=True, actual_return=None),
        _outcome(is_final=False, target_hit=True, actual_return=0.99),  # excluded
        _outcome(is_final=False, target_hit=False, actual_return=-0.99),  # excluded
    ]
    summary = summarize_performance(outcomes)

    # Hand-computed: final_outcome_count = 3
    assert summary.final_outcome_count == 3
    # target_hit_rate = 2 target_hit=True / 3 final = 0.6666...
    assert summary.target_hit_rate == 2 / 3
    # stop_hit_rate = 1 stop_hit=True / 3 final = 0.3333...
    assert summary.stop_hit_rate == 1 / 3
    # average_return over the 2 final outcomes with a non-null actual_return:
    # (0.10 + -0.05) / 2 = 0.025
    assert summary.average_return == 0.025


def test_final_outcomes_with_no_returns_recorded_gives_none_average():
    outcomes = [_outcome(is_final=True, target_hit=True, stop_hit=False, actual_return=None)]
    summary = summarize_performance(outcomes)
    assert summary.final_outcome_count == 1
    assert summary.target_hit_rate == 1.0
    assert summary.average_return is None
