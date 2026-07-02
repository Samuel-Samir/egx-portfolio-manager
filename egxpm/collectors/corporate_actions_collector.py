"""Corporate Actions Collector — manual entry (v1). No automated feed for
EGX corporate actions has been identified (an open item per the
architecture doc — remains manual until one is found, same as EGX
Disclosures). This Collector does no scraping; its only job is to stamp a
manually-entered corporate action consistently with the right provenance.

action_type is a free-form label recorded verbatim (not an enum in the
schema — corporate_actions.action_type is a plain TEXT column). Only
"split" and "bonus_issue" are structurally price-adjusting (they change
what a historical price means relative to today's share count) and are
the two types record_corporate_action.py's price-adjustment logic acts
on; other types (e.g. "dividend", "rights_issue") are recorded for the
audit trail and RecommendationSupersession trigger but don't rewrite
price history.
"""

from __future__ import annotations

from egxpm.persistence.models import CorporateAction

PRICE_ADJUSTING_ACTION_TYPES = {"split", "bonus_issue"}


def create_corporate_action(
    company_id: str,
    action_type: str,
    action_date: str,
    details: dict,
) -> CorporateAction:
    """Constructs a CorporateAction for a manually-entered event.

    For a price-adjusting action_type ("split" or "bonus_issue"), details
    must include a "ratio" (float > 0): the multiplier applied to a share
    count, e.g. a 2-for-1 split is ratio=2.0 (old_close / ratio = adjusted
    close; old_volume * ratio = adjusted volume).

    Raises:
        ValueError: action_type is price-adjusting and details["ratio"]
            is missing or not a positive number.
    """
    if action_type in PRICE_ADJUSTING_ACTION_TYPES:
        ratio = details.get("ratio")
        if not isinstance(ratio, (int, float)) or ratio <= 0:
            raise ValueError(
                f"action_type={action_type!r} requires a positive numeric details['ratio']"
            )

    return CorporateAction(
        company_id=company_id, action_type=action_type, action_date=action_date,
        details=details, data_source_id="manual",
    )
