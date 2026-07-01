"""Read-only repository for the Dashboard.

Per the Dashboard Rules (Section 16): the Dashboard never calls Engines or
the LLM, and never writes. AllocationReport is the one exception where a
pure arithmetic computation (AllocationCalculator, not an Engine) runs at
read time. Streamlit applies @st.cache_data(ttl=300) on calls into this
repository; no caching happens here.
"""

from __future__ import annotations

from typing import Optional

from egxpm.persistence.company_repository import CompanyRepository
from egxpm.persistence.models import AllocationReport, Company, ConfigurationSnapshot, WatchlistState
from egxpm.persistence.operational_repository import OperationalRepository
from egxpm.shared.allocation_calculator import calculate


class DashboardReadRepository:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.company_repo = CompanyRepository(db_path)
        self.operational_repo = OperationalRepository(db_path)

    def get_current_allocation(
        self,
        prices: dict[str, float],
        cash: float,
        fallback_config: Optional[ConfigurationSnapshot] = None,
    ) -> AllocationReport:
        holdings = self.company_repo.list_holdings()
        config = self.operational_repo.get_latest_configuration_snapshot() or fallback_config
        if config is None:
            raise ValueError("no ConfigurationSnapshot available to compute allocation")
        return calculate(holdings, prices, cash, config)

    def get_companies_overview(self) -> list[Company]:
        return self.company_repo.list_companies()

    def get_watchlist_overview(self) -> dict[str, list[str]]:
        return {
            state.value: self.company_repo.list_companies_in_state(state)
            for state in WatchlistState
        }

    def get_longterm_rankings(self) -> list[dict]:
        """WATCHLIST companies with a Score on record, ranked by
        composite_score descending (nulls last)."""
        watchlist_ids = self.company_repo.list_companies_in_state(WatchlistState.WATCHLIST)
        rows = []
        for company_id in watchlist_ids:
            score = self.company_repo.get_latest_score(company_id)
            if score is None:
                continue
            company = self.company_repo.get_company(company_id)
            rows.append({"company": company, "score": score})
        rows.sort(
            key=lambda row: (
                row["score"].composite_score is not None,
                row["score"].composite_score or 0.0,
            ),
            reverse=True,
        )
        return rows
