import pytest

from egxpm.collectors.corporate_actions_collector import create_corporate_action


def test_creates_dividend_action_no_ratio_required():
    action = create_corporate_action(
        company_id="COMI", action_type="dividend", action_date="2026-06-01",
        details={"amount_per_share": 1.5},
    )
    assert action.company_id == "COMI"
    assert action.action_type == "dividend"
    assert action.data_source_id == "manual"
    assert action.details == {"amount_per_share": 1.5}


def test_creates_split_action_with_ratio():
    action = create_corporate_action(
        company_id="COMI", action_type="split", action_date="2026-06-01", details={"ratio": 2.0},
    )
    assert action.details["ratio"] == 2.0


def test_split_without_ratio_raises():
    with pytest.raises(ValueError):
        create_corporate_action(
            company_id="COMI", action_type="split", action_date="2026-06-01", details={},
        )


def test_bonus_issue_without_positive_ratio_raises():
    with pytest.raises(ValueError):
        create_corporate_action(
            company_id="COMI", action_type="bonus_issue", action_date="2026-06-01",
            details={"ratio": -1.0},
        )
