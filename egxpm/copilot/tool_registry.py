"""Tool Registry — the Copilot's gateway to the rest of the system
(Section 15.3). 15 tools across three safety tiers:

  Read    — direct execution, no side effects.
  Propose — builds a Plan and stores it in session.pending_plans; nothing
            is applied until the user confirms it.
  Execute — the only tier allowed to write. confirm_and_apply requires an
            existing pending plan; every Execute tool still never places a
            real trade (this system is decision-support only).

Every tool method returns a plain value (or raises BusinessDataError);
execute() wraps that into a ToolResult, converting BusinessDataError into
ToolResult(success=False, error=...) rather than letting it propagate —
that's how an LLM-visible "not found" / "invalid" response differs from a
genuine bug (ValueError/AssertionError, which is NOT caught here and
surfaces loudly).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable

from egxpm.collectors.collector_service import CollectorService
from egxpm.collectors.price_collector import collect_price_candles
from egxpm.collectors.source_health_service import SourceHealthService
from egxpm.copilot.models import AnalysisSessionState, RebalancePlan, SwingPlan, ToolResult
from egxpm.engine.portfolio_engine import apply_action, calculate_allocation
from egxpm.engine.portfolio_engine import simulate as portfolio_simulate
from egxpm.engine.position_sizing_engine import calculate_position_size
from egxpm.engine.scoring_engine import build_score
from egxpm.persistence.company_repository import CompanyRepository
from egxpm.persistence.conversation_repository import ConversationRepository
from egxpm.persistence.dashboard_read_repository import DashboardReadRepository
from egxpm.persistence.models import (
    AnalysisSession,
    CollectionRun,
    Holding,
    HoldingCategory,
    ProposedAction,
    RecommendationAction,
    RunStatus,
)
from egxpm.persistence.operational_repository import OperationalRepository
from egxpm.persistence.recommendation_repository import RecommendationRepository
from egxpm.persistence.sector_market_repository import SectorMarketRepository
from egxpm.scoring_pipeline import compute_company_score
from egxpm.shared.config import build_configuration_snapshot, load_raw_config
from egxpm.shared.exceptions import BusinessDataError, InsufficientDataError

READ = "read"
PROPOSE = "propose"
EXECUTE = "execute"

TOOL_TIERS: dict[str, str] = {
    "get_company_summary": READ,
    "get_portfolio": READ,
    "get_latest_scores": READ,
    "get_recommendation_history": READ,
    "compare_companies": READ,
    "get_sector_summary": READ,
    "simulate_buy": READ,
    "get_source_health": READ,
    "search_recommendations": READ,
    "get_news": READ,
    "propose_rebalance": PROPOSE,
    "propose_swing_analysis": PROPOSE,
    "confirm_and_apply": EXECUTE,
    "trigger_collection": EXECUTE,
    "save_analysis_session": EXECUTE,
}

TOOL_SCHEMAS: dict[str, dict] = {
    "get_company_summary": {
        "description": "Get a company's identity, latest composite score, trend, and confidence.",
        "input_schema": {"type": "object", "properties": {"symbol": {"type": "string"}}, "required": ["symbol"]},
    },
    "get_portfolio": {
        "description": "Get the current portfolio allocation (holdings, category/stock percentages, total value).",
        "input_schema": {"type": "object", "properties": {}},
    },
    "get_latest_scores": {
        "description": "Get the latest Score for a list of companies (defaults to all WATCHLIST companies).",
        "input_schema": {
            "type": "object",
            "properties": {"symbols": {"type": "array", "items": {"type": "string"}}},
        },
    },
    "get_recommendation_history": {
        "description": "Get all Recommendations for a company (or every company if omitted).",
        "input_schema": {"type": "object", "properties": {"company_id": {"type": "string"}}},
    },
    "compare_companies": {
        "description": "Compare 2+ companies' latest Score breakdowns side by side.",
        "input_schema": {
            "type": "object",
            "properties": {"company_ids": {"type": "array", "items": {"type": "string"}}},
            "required": ["company_ids"],
        },
    },
    "get_sector_summary": {
        "description": "Get the latest SectorSummary (mean composite_score) for a sector.",
        "input_schema": {"type": "object", "properties": {"sector": {"type": "string"}}, "required": ["sector"]},
    },
    "simulate_buy": {
        "description": "Read-only: simulate buying shares and see the resulting AllocationReport, without writing anything.",
        "input_schema": {
            "type": "object",
            "properties": {
                "company_id": {"type": "string"}, "quantity": {"type": "number"}, "price": {"type": "number"},
            },
            "required": ["company_id", "quantity", "price"],
        },
    },
    "get_source_health": {
        "description": "Get a data source's rolling 30-day collection success rate.",
        "input_schema": {"type": "object", "properties": {"data_source_id": {"type": "string"}}, "required": ["data_source_id"]},
    },
    "search_recommendations": {
        "description": "Search Recommendations, optionally filtered by company and/or action.",
        "input_schema": {
            "type": "object",
            "properties": {"company_id": {"type": "string"}, "action": {"type": "string"}},
        },
    },
    "get_news": {
        "description": "Get recent news items for a company.",
        "input_schema": {
            "type": "object",
            "properties": {"company_id": {"type": "string"}, "limit": {"type": "integer"}},
            "required": ["company_id"],
        },
    },
    "propose_rebalance": {
        "description": "Propose a RebalancePlan deploying new_capital across top-ranked WATCHLIST candidates. "
                        "Creates a pending plan — nothing is applied until confirm_and_apply(plan_id).",
        "input_schema": {"type": "object", "properties": {"new_capital": {"type": "number"}}, "required": ["new_capital"]},
    },
    "propose_swing_analysis": {
        "description": "Propose a SwingPlan (technical-weighted score + ATR position sizing preview) for one company. "
                        "Creates a pending plan — nothing is applied until confirm_and_apply(plan_id).",
        "input_schema": {"type": "object", "properties": {"company_id": {"type": "string"}}, "required": ["company_id"]},
    },
    "confirm_and_apply": {
        "description": "Confirm a pending plan by its plan_id. This system never places real trades — "
                        "confirming records the decision and tells the user to execute manually in Thndr.",
        "input_schema": {"type": "object", "properties": {"plan_id": {"type": "string"}}, "required": ["plan_id"]},
    },
    "trigger_collection": {
        "description": "Trigger an on-demand data refresh for one company (inline — does not create a nested Job).",
        "input_schema": {
            "type": "object",
            "properties": {"data_source_type": {"type": "string"}, "company_id": {"type": "string"}},
            "required": ["data_source_type", "company_id"],
        },
    },
    "save_analysis_session": {
        "description": "Persist the current AnalysisSession workspace.",
        "input_schema": {
            "type": "object",
            "properties": {"session_id": {"type": "string"}, "conversation_id": {"type": "string"}},
            "required": ["session_id", "conversation_id"],
        },
    },
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class ToolRegistry:
    def __init__(self, db_path: str, config_path: str = "config.yaml"):
        self.db_path = db_path
        self.company_repo = CompanyRepository(db_path)
        self.recommendation_repo = RecommendationRepository(db_path)
        self.operational_repo = OperationalRepository(db_path)
        self.sector_repo = SectorMarketRepository(db_path)
        self.dashboard_repo = DashboardReadRepository(db_path)
        self.conversation_repo = ConversationRepository(db_path)
        self.health_service = SourceHealthService(db_path)
        self.raw_config = load_raw_config(config_path)
        self.weights = build_configuration_snapshot(self.raw_config, weight_profile="longterm_weights")

    # ------------------------------------------------------------
    # Dispatch
    # ------------------------------------------------------------

    def all_tools(self) -> list[dict]:
        """Anthropic tool-use schema definitions for every registered tool."""
        return [{"name": name, **schema} for name, schema in TOOL_SCHEMAS.items()]

    def execute(self, tool_name: str, arguments: dict, session: AnalysisSessionState) -> ToolResult:
        if tool_name not in TOOL_TIERS:
            return ToolResult(tool_name=tool_name, success=False, error=f"unknown tool: {tool_name!r}")
        method: Callable = getattr(self, tool_name)
        try:
            data = method(session, **arguments)
            return ToolResult(tool_name=tool_name, success=True, data=data)
        except BusinessDataError as exc:
            return ToolResult(tool_name=tool_name, success=False, error=str(exc))

    def _current_prices(self, holdings: list[Holding]) -> dict[str, float]:
        prices = {}
        for holding in holdings:
            candles = self.company_repo.list_price_candles(holding.company_id)
            if candles:
                prices[holding.company_id] = candles[-1].close
        return prices

    # ------------------------------------------------------------
    # Read tier
    # ------------------------------------------------------------

    def get_company_summary(self, session: AnalysisSessionState, symbol: str) -> dict:
        company = self.company_repo.get_company(symbol)
        if company is None:
            raise InsufficientDataError(f"unknown company: {symbol!r}")
        score = self.company_repo.get_latest_score(symbol)
        technical = self.company_repo.get_latest_technical_snapshot(symbol)
        confidence = (
            self.company_repo.get_confidence_score_by_score_id(score.score_id) if score is not None else None
        )
        return {
            "company_id": company.company_id, "name": company.name, "sector": company.sector,
            "composite_score": score.composite_score if score else None,
            "trend": technical.trend.value if technical and technical.trend else None,
            "confidence": confidence.confidence_value if confidence else None,
        }

    def get_portfolio(self, session: AnalysisSessionState) -> dict:
        holdings = self.company_repo.list_holdings()
        prices = self._current_prices(holdings)
        report = calculate_allocation(holdings, prices, cash=0.0, config=self.weights)
        return report.model_dump()

    def get_latest_scores(self, session: AnalysisSessionState, symbols: list[str] | None = None) -> dict:
        from egxpm.persistence.models import WatchlistState
        ids = symbols or self.company_repo.list_companies_in_state(WatchlistState.WATCHLIST)
        result = {}
        for company_id in ids:
            score = self.company_repo.get_latest_score(company_id)
            result[company_id] = score.model_dump() if score else None
        return result

    def get_recommendation_history(self, session: AnalysisSessionState, company_id: str | None = None) -> list[dict]:
        return [r.model_dump() for r in self.recommendation_repo.list_recommendations(company_id)]

    def compare_companies(self, session: AnalysisSessionState, company_ids: list[str]) -> dict:
        result = {}
        for company_id in company_ids:
            score = self.company_repo.get_latest_score(company_id)
            if score is None:
                raise InsufficientDataError(f"no Score on record for {company_id!r}")
            result[company_id] = {
                "composite_score": score.composite_score,
                "financial_breakdown": score.financial_breakdown,
                "technical_breakdown": score.technical_breakdown,
                "news_breakdown": score.news_breakdown,
            }
        return result

    def get_sector_summary(self, session: AnalysisSessionState, sector: str) -> dict | None:
        summary = self.sector_repo.get_latest_sector_summary(sector)
        return summary.model_dump() if summary else None

    def simulate_buy(self, session: AnalysisSessionState, company_id: str, quantity: float, price: float) -> dict:
        holdings = self.company_repo.list_holdings()
        prices = self._current_prices(holdings)
        action = ProposedAction(
            company_id=company_id, action=RecommendationAction.BUY, quantity=quantity, price=price,
            category=HoldingCategory.LONG_TERM_STOCKS,
        )
        report = portfolio_simulate(action, holdings, prices, cash=0.0, config=self.weights)
        return report.model_dump()

    def get_source_health(self, session: AnalysisSessionState, data_source_id: str) -> float | None:
        return self.health_service.get_source_health(data_source_id)

    def search_recommendations(
        self, session: AnalysisSessionState, company_id: str | None = None, action: str | None = None
    ) -> list[dict]:
        recs = self.recommendation_repo.list_recommendations(company_id)
        if action:
            recs = [r for r in recs if r.action.value == action]
        return [r.model_dump() for r in recs]

    def get_news(self, session: AnalysisSessionState, company_id: str, limit: int = 10) -> list[dict]:
        return [n.model_dump() for n in self.company_repo.list_news_items(company_id)[:limit]]

    # ------------------------------------------------------------
    # Propose tier — writes ONLY to session.pending_plans, nothing persisted
    # ------------------------------------------------------------

    def propose_rebalance(self, session: AnalysisSessionState, new_capital: float) -> dict:
        """Equal-weight allocation of new_capital across the top-ranked
        WATCHLIST candidates by composite_score, capped at
        max_per_stock_pct of portfolio value per stock. The architecture
        doc doesn't specify an exact rebalancing algorithm — this is a
        simple, deterministic, documented v1 choice (LLM narrates the
        plan; it never decides the numbers, per Principle 2.1).
        """
        rankings = self.dashboard_repo.get_longterm_rankings()
        top_n = self.raw_config.get("review_top_n_candidates", 10)
        candidates = [row for row in rankings if row["score"].composite_score is not None][:top_n]
        if not candidates:
            raise InsufficientDataError("no scored WATCHLIST candidates available to build a rebalance plan")

        holdings = self.company_repo.list_holdings()
        prices = self._current_prices(holdings)
        current_allocation = calculate_allocation(holdings, prices, cash=0.0, config=self.weights)
        max_per_stock_pct = self.weights.risk_settings.get("max_per_stock_pct", 1.0)
        per_candidate_capital = new_capital / len(candidates)

        proposed_actions: list[ProposedAction] = []
        rejected_alternatives: list[str] = []
        working_holdings = list(holdings)
        working_prices = dict(prices)

        for row in candidates:
            company_id = row["company"].company_id
            candles = self.company_repo.list_price_candles(company_id)
            if not candles:
                rejected_alternatives.append(f"{company_id}: no recent price data available, skipped")
                continue
            price = candles[-1].close
            max_egp = (
                current_allocation.total_value * max_per_stock_pct
                if current_allocation.total_value > 0 else per_candidate_capital
            )
            allocate_egp = min(per_candidate_capital, max_egp)
            if allocate_egp <= 0 or price <= 0:
                rejected_alternatives.append(f"{company_id}: no capital left to allocate after caps, skipped")
                continue
            action = ProposedAction(
                company_id=company_id, action=RecommendationAction.BUY, quantity=allocate_egp / price,
                price=price, category=HoldingCategory.LONG_TERM_STOCKS,
            )
            proposed_actions.append(action)
            working_holdings = apply_action(working_holdings, action)
            working_prices[company_id] = price

        projected = calculate_allocation(working_holdings, working_prices, cash=0.0, config=self.weights)
        plan = RebalancePlan(
            new_capital=new_capital, proposed_actions=proposed_actions, projected_allocation=projected,
            reasoning=(
                f"Equal-weight allocation of {new_capital:,.2f} EGP across the top {len(candidates)} "
                f"WATCHLIST candidates by composite_score, capped at {max_per_stock_pct:.0%} of "
                f"portfolio value per stock."
            ),
            rejected_alternatives=rejected_alternatives,
        )
        session.pending_plans[plan.plan_id] = plan.model_dump()
        return plan.model_dump()

    def propose_swing_analysis(self, session: AnalysisSessionState, company_id: str) -> dict:
        company = self.company_repo.get_company(company_id)
        if company is None:
            raise InsufficientDataError(f"unknown company: {company_id!r}")

        swing_weights = build_configuration_snapshot(self.raw_config, weight_profile="swing_weights")
        _financial_metrics, technical_result, score_result = compute_company_score(
            company, self.company_repo, swing_weights
        )
        # composite_score stays None here: assembling it requires the Stage
        # 6a sector-wide barrier (RiskScore needs SectorPeerSummary across
        # every company), which is too heavy for a single-company on-demand
        # preview. propose_swing_analysis surfaces the three sub-scores
        # instead — the full risk-adjusted composite is only ever produced
        # by the scheduled Swing Job.
        score = build_score(
            score_result, company_id=company_id,
            config_snapshot_id=swing_weights.config_snapshot_id, job_id="copilot-preview",
        )

        entry = stop = target = size = None
        note = ""
        try:
            holdings = self.company_repo.list_holdings()
            prices = self._current_prices(holdings)
            allocation = calculate_allocation(holdings, prices, cash=0.0, config=self.weights)
            sizing = calculate_position_size(technical_result, swing_weights, allocation)
            entry, stop, target, size = sizing.entry_price, sizing.stop_loss, sizing.take_profit, sizing.position_size
        except BusinessDataError as exc:
            note = f" Position sizing unavailable: {exc}"

        plan = SwingPlan(
            company_id=company_id, composite_score=score.composite_score,
            entry_price=entry, stop_loss=stop, take_profit=target, position_size=size,
            reasoning=f"Technical-weighted composite score: {score.composite_score}.{note}",
        )
        session.pending_plans[plan.plan_id] = plan.model_dump()
        return plan.model_dump()

    # ------------------------------------------------------------
    # Execute tier — the only tier allowed to write
    # ------------------------------------------------------------

    def confirm_and_apply(self, session: AnalysisSessionState, plan_id: str) -> dict:
        """Raises InsufficientDataError (-> ToolResult.error) if plan_id
        isn't in session.pending_plans — this is the exact case the M7
        acceptance test exercises."""
        if plan_id not in session.pending_plans:
            raise InsufficientDataError(f"no pending plan with plan_id={plan_id!r}")
        plan = session.pending_plans.pop(plan_id)
        session.confirmed_plan_ids.append(plan_id)
        return {
            "plan_id": plan_id, "confirmed": True, "plan": plan,
            "message": "Plan confirmed. This system never places real trades — "
                       "execute it yourself in Thndr, then record the execution.",
        }

    def trigger_collection(self, session: AnalysisSessionState, data_source_type: str, company_id: str) -> dict:
        """Calls CollectorService directly — no nested Job row, matching
        ensure_fresh_data's pattern (Business Rule, Section 13.4)."""
        if data_source_type != "price":
            raise InsufficientDataError(
                f"trigger_collection only supports data_source_type='price' in this version, got {data_source_type!r}"
            )
        run = CollectionRun(data_source_id="yfinance", company_id=company_id)
        service = CollectorService()
        candles = service.collect(lambda: collect_price_candles(company_id, run.collection_run_id, period="1mo"))
        self.company_repo.save_price_candles(candles)
        run.status = RunStatus.COMPLETED
        run.records_collected = len(candles)
        run.completed_at = _now()
        self.operational_repo.save_collection_run(run)
        return {"company_id": company_id, "records_collected": len(candles)}

    def save_analysis_session(self, session: AnalysisSessionState, session_id: str, conversation_id: str) -> dict:
        record = AnalysisSession(session_id=session_id, conversation_id=conversation_id, state=session.model_dump())
        self.conversation_repo.save_session(record)
        return {"session_id": session_id, "saved": True}
