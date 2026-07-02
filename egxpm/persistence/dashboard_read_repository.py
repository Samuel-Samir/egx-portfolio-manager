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

    def get_holdings_detail(self) -> list[dict]:
        """Each Holding joined with its Company, latest Score, latest
        ConfidenceScore, and latest PriceCandle (current price)."""
        rows = []
        for holding in self.company_repo.list_holdings():
            company = self.company_repo.get_company(holding.company_id)
            score = self.company_repo.get_latest_score(holding.company_id)
            confidence = (
                self.company_repo.get_confidence_score_by_score_id(score.score_id)
                if score is not None else None
            )
            candles = self.company_repo.list_price_candles(holding.company_id)
            latest_price = candles[-1].close if candles else None
            unrealized_pnl = (
                holding.quantity * (latest_price - holding.average_cost)
                if latest_price is not None else None
            )
            rows.append({
                "holding": holding, "company": company, "score": score, "confidence": confidence,
                "latest_price": latest_price, "unrealized_pnl": unrealized_pnl,
            })
        return rows

    def get_watchlist_detail(self) -> list[dict]:
        """WATCHLIST + CANDIDATE companies with their latest Score and
        latest TechnicalSnapshot."""
        rows = []
        for state in (WatchlistState.WATCHLIST, WatchlistState.CANDIDATE):
            for company_id in self.company_repo.list_companies_in_state(state):
                company = self.company_repo.get_company(company_id)
                rows.append({
                    "company": company, "state": state,
                    "score": self.company_repo.get_latest_score(company_id),
                    "technical_snapshot": self.company_repo.get_latest_technical_snapshot(company_id),
                })
        return rows

    def get_company_analysis(self, company_id: str) -> dict:
        """Single-company deep dive: Score history, FinancialStatement
        history, TechnicalSnapshot history, and recent news."""
        return {
            "company": self.company_repo.get_company(company_id),
            "score_history": self.company_repo.list_scores(company_id),
            "financial_statements": self.company_repo.list_financial_statements(company_id),
            "technical_snapshots": self.company_repo.list_technical_snapshots(company_id),
            "news": self.company_repo.list_news_items(company_id),
        }
