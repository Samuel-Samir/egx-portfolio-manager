"""Full Dashboard — 14 read-only pages plus the Copilot (Section 16): no
Engine calls, no LLM calls, no writes on the read-only pages. AllocationReport
on Home is the one exception — computed at read time via
DashboardReadRepository (pure arithmetic, not an Engine). Every Repository
call on the read-only pages is wrapped in @st.cache_data(ttl=300).

The Copilot page is the one deliberate exception to "Dashboard never calls
LLM / never writes" — per the Dashboard Rules, ALL write actions go through
the Copilot Tool Layer, and this page is that layer's UI (Section 16, M7).
It talks to ToolRegistry/CopilotSession directly, not through a cached
read-only Repository call.

"Reports" (the 15th page in the architecture doc's inventory) is out of
scope: no Job in this codebase writes dated Markdown files to reports/ yet.
"""

from __future__ import annotations

from datetime import date

import streamlit as st
from dotenv import load_dotenv

load_dotenv()  # ANTHROPIC_API_KEY must be set before the Copilot page is used

from egxpm.collectors.source_health_service import SourceHealthService
from egxpm.copilot.session import CopilotSession
from egxpm.copilot.tool_registry import ToolRegistry
from egxpm.persistence.company_repository import CompanyRepository
from egxpm.persistence.dashboard_read_repository import DashboardReadRepository
from egxpm.persistence.db import init_db
from egxpm.persistence.models import Conversation, RunStatus
from egxpm.persistence.operational_repository import OperationalRepository
from egxpm.persistence.portfolio_repository import PortfolioRepository
from egxpm.persistence.recommendation_repository import RecommendationRepository
from egxpm.shared.config import load_configuration_snapshot
from egxpm.shared.exceptions import BusinessDataError

DB_PATH = "data/egx.db"
CACHE_TTL_SECONDS = 300

init_db(DB_PATH)  # idempotent — safe to call on every page load
st.set_page_config(page_title="EGX Portfolio Manager", layout="wide")


# ------------------------------------------------------------
# Cached data loaders — one per Repository call, per the Dashboard Rules
# ------------------------------------------------------------

@st.cache_data(ttl=CACHE_TTL_SECONDS)
def load_allocation():
    dashboard_repo = DashboardReadRepository(DB_PATH)
    company_repo = CompanyRepository(DB_PATH)
    holdings = company_repo.list_holdings()
    prices = {}
    for holding in holdings:
        candles = company_repo.list_price_candles(holding.company_id)
        if candles:
            prices[holding.company_id] = candles[-1].close
    fallback_config = load_configuration_snapshot()
    return dashboard_repo.get_current_allocation(prices=prices, cash=0.0, fallback_config=fallback_config)


@st.cache_data(ttl=CACHE_TTL_SECONDS)
def load_latest_portfolio_snapshot():
    return PortfolioRepository(DB_PATH).get_latest_snapshot()


@st.cache_data(ttl=CACHE_TTL_SECONDS)
def load_portfolio_snapshot_history():
    return PortfolioRepository(DB_PATH).list_snapshots()


@st.cache_data(ttl=CACHE_TTL_SECONDS)
def load_longterm_rankings():
    return DashboardReadRepository(DB_PATH).get_longterm_rankings()


@st.cache_data(ttl=CACHE_TTL_SECONDS)
def load_holdings_detail():
    return DashboardReadRepository(DB_PATH).get_holdings_detail()


@st.cache_data(ttl=CACHE_TTL_SECONDS)
def load_watchlist_detail():
    return DashboardReadRepository(DB_PATH).get_watchlist_detail()


@st.cache_data(ttl=CACHE_TTL_SECONDS)
def load_company_analysis(company_id: str):
    return DashboardReadRepository(DB_PATH).get_company_analysis(company_id)


@st.cache_data(ttl=CACHE_TTL_SECONDS)
def load_companies_overview():
    return DashboardReadRepository(DB_PATH).get_companies_overview()


@st.cache_data(ttl=CACHE_TTL_SECONDS)
def load_financial_statements(company_id: str):
    return CompanyRepository(DB_PATH).list_financial_statements(company_id)


@st.cache_data(ttl=CACHE_TTL_SECONDS)
def load_news_items(company_id: str | None):
    return CompanyRepository(DB_PATH).list_news_items(company_id)


@st.cache_data(ttl=CACHE_TTL_SECONDS)
def load_recent_jobs(limit: int = 20):
    jobs = OperationalRepository(DB_PATH).list_jobs()
    return jobs[:limit]


@st.cache_data(ttl=CACHE_TTL_SECONDS)
def load_recent_collection_runs(limit: int = 50):
    runs = OperationalRepository(DB_PATH).list_collection_runs()
    return runs[:limit]


@st.cache_data(ttl=CACHE_TTL_SECONDS)
def load_source_health(data_source_ids: tuple[str, ...]):
    service = SourceHealthService(DB_PATH)
    return {source_id: service.get_source_health(source_id) for source_id in data_source_ids}


@st.cache_data(ttl=CACHE_TTL_SECONDS)
def load_all_recommendations():
    recs = RecommendationRepository(DB_PATH).list_recommendations()
    return sorted(recs, key=lambda r: r.created_at, reverse=True)


@st.cache_data(ttl=CACHE_TTL_SECONDS)
def load_recent_recommendations(limit: int = 20):
    return load_all_recommendations()[:limit]


@st.cache_data(ttl=CACHE_TTL_SECONDS)
def load_recommendation_events(recommendation_id: str):
    rec_repo = RecommendationRepository(DB_PATH)
    return {
        "supersessions": rec_repo.list_supersessions(recommendation_id),
        "executions": rec_repo.list_executions(recommendation_id),
        "outcomes": rec_repo.list_outcomes(recommendation_id),
        "feedback": rec_repo.list_user_feedback(recommendation_id),
    }


@st.cache_data(ttl=CACHE_TTL_SECONDS)
def load_table_names():
    return OperationalRepository(DB_PATH).list_table_names()


@st.cache_data(ttl=CACHE_TTL_SECONDS)
def load_table_page(table_name: str, limit: int, offset: int):
    repo = OperationalRepository(DB_PATH)
    return repo.query_table(table_name, limit=limit, offset=offset), repo.count_table_rows(table_name)


# ------------------------------------------------------------
# Pages
# ------------------------------------------------------------

def render_home():
    st.title("Home — Portfolio Summary")

    allocation = load_allocation()
    col1, col2, col3 = st.columns(3)
    col1.metric("Total Portfolio Value (EGP)", f"{allocation.total_value:,.2f}")
    col2.metric("Cash (EGP)", f"{allocation.cash:,.2f}")
    col3.metric("Holdings Count", len(allocation.by_stock_pct))

    if allocation.total_value == 0:
        st.info(
            "No real Holding data has been entered yet — this shows an empty portfolio, "
            "not an error. Enter your actual EGX positions to see real allocation here."
        )

    if allocation.by_category_pct:
        st.subheader("Allocation by Category")
        st.bar_chart(allocation.by_category_pct)

    if allocation.stock_constraint_violations:
        st.warning(f"Stock constraint violations: {', '.join(allocation.stock_constraint_violations)}")

    snapshot = load_latest_portfolio_snapshot()
    if snapshot:
        st.caption(f"Last PortfolioSnapshot: {snapshot.captured_at} (origin={snapshot.origin.value})")
    else:
        st.caption("No PortfolioSnapshot captured yet — run the Long-Term Job.")

    st.subheader("Recent Recommendations")
    recommendations = load_recent_recommendations(limit=5)
    if not recommendations:
        st.write("No Recommendations yet.")
    else:
        for rec in recommendations:
            with st.expander(f"{rec.company_id} — {rec.action.value} ({rec.created_at})"):
                st.write(rec.frozen_package.get("reasoning", ""))
                risks = rec.frozen_package.get("key_risks", [])
                if risks:
                    st.write("**Key risks:**")
                    for risk in risks:
                        st.write(f"- {risk}")
                alternatives = rec.frozen_package.get("rejected_alternatives", [])
                if alternatives:
                    st.write("**Rejected alternatives:**")
                    for alt in alternatives:
                        st.write(f"- {alt}")


def render_portfolio_holdings():
    st.title("Portfolio — Holdings Detail")
    rows = load_holdings_detail()
    if not rows:
        st.write("No Holdings on record. This is expected until real positions are entered.")
        return

    table = []
    for row in rows:
        holding, company, score = row["holding"], row["company"], row["score"]
        table.append({
            "Company": holding.company_id, "Name": company.name if company else None,
            "Category": holding.category.value, "Quantity": holding.quantity,
            "Avg Cost": holding.average_cost, "Latest Price": row["latest_price"],
            "Unrealized P&L": row["unrealized_pnl"],
            "Composite Score": score.composite_score if score else None,
            "Confidence": row["confidence"].confidence_value if row["confidence"] else None,
        })
    st.dataframe(table, width="stretch")


def render_watchlist():
    st.title("Watchlist")
    rows = load_watchlist_detail()
    if not rows:
        st.write("No WATCHLIST or CANDIDATE companies found.")
        return

    table = [
        {
            "Company": row["company"].company_id, "Name": row["company"].name,
            "State": row["state"].value, "Sector": row["company"].sector,
            "Composite Score": row["score"].composite_score if row["score"] else None,
            "Trend": row["technical_snapshot"].trend.value if row["technical_snapshot"] and row["technical_snapshot"].trend else None,
        }
        for row in rows
    ]
    st.dataframe(table, width="stretch")


def render_swing_trading():
    st.title("Swing Trading")
    st.caption(
        "Today's swing Recommendations. Identified by having a stop_loss set — "
        "only swing Recommendations carry ATR-based stop/target/size; "
        "long-term Recommendations don't (Position Sizing is swing-only)."
    )
    today = date.today().isoformat()
    swing_today = [
        rec for rec in load_all_recommendations()
        if rec.stop_loss is not None and rec.created_at[:10] == today
    ]
    if not swing_today:
        st.write("No swing Recommendations today.")
        return

    for rec in swing_today:
        events = load_recommendation_events(rec.recommendation_id)
        superseded = len(events["supersessions"]) > 0
        with st.expander(f"{rec.company_id} — {rec.action.value} {'(superseded)' if superseded else ''}"):
            st.write(f"Entry: {rec.entry_price} | Stop: {rec.stop_loss} | Target: {rec.take_profit} | Size: {rec.position_size}")
            st.write(rec.frozen_package.get("reasoning", ""))


def render_recommendations_history():
    st.title("Recommendations History")
    recommendations = load_all_recommendations()
    if not recommendations:
        st.write("No Recommendations yet.")
        return

    page_size = 20
    total_pages = max(1, (len(recommendations) + page_size - 1) // page_size)
    page = st.number_input("Page", min_value=1, max_value=total_pages, value=1)
    start = (page - 1) * page_size
    page_items = recommendations[start:start + page_size]

    table = []
    for rec in page_items:
        events = load_recommendation_events(rec.recommendation_id)
        table.append({
            "Company": rec.company_id, "Action": rec.action.value, "Created": rec.created_at,
            "Superseded": len(events["supersessions"]) > 0,
            "Executions": len(events["executions"]), "Outcomes": len(events["outcomes"]),
        })
    st.dataframe(table, width="stretch")
    st.caption(f"Page {page} of {total_pages} ({len(recommendations)} total)")


def render_recommendation_performance():
    st.title("Recommendation Performance")
    recommendations = load_all_recommendations()
    all_outcomes = []
    all_feedback = []
    for rec in recommendations:
        events = load_recommendation_events(rec.recommendation_id)
        all_outcomes.extend(events["outcomes"])
        all_feedback.extend(events["feedback"])

    if not all_outcomes:
        st.write("No Outcomes recorded yet — Performance analytics will populate once trades are executed and outcomes tracked.")
        return

    final_outcomes = [o for o in all_outcomes if o.is_final]
    target_hits = sum(1 for o in final_outcomes if o.target_hit)
    stop_hits = sum(1 for o in final_outcomes if o.stop_hit)
    returns = [o.actual_return for o in final_outcomes if o.actual_return is not None]

    col1, col2, col3 = st.columns(3)
    col1.metric("Final Outcomes", len(final_outcomes))
    col2.metric("Target Hit Rate", f"{target_hits / len(final_outcomes) * 100:.1f}%" if final_outcomes else "n/a")
    col3.metric("Stop Hit Rate", f"{stop_hits / len(final_outcomes) * 100:.1f}%" if final_outcomes else "n/a")
    if returns:
        st.metric("Average Return", f"{sum(returns) / len(returns) * 100:.2f}%")

    st.subheader("User Feedback")
    if not all_feedback:
        st.write("No UserFeedback recorded yet.")
    else:
        st.dataframe(
            [{"Agreement": f.agreement.value if f.agreement else None, "Text": f.feedback_text} for f in all_feedback],
            width="stretch",
        )


def render_company_analysis():
    st.title("Company Analysis")
    companies = load_companies_overview()
    if not companies:
        st.write("No companies on record.")
        return
    selected = st.selectbox("Company", [c.company_id for c in companies])
    analysis = load_company_analysis(selected)

    st.subheader("Score History")
    if analysis["score_history"]:
        st.dataframe(
            [{"Computed At": s.computed_at, "Composite": s.composite_score, "Financial": s.financial_score,
              "Technical": s.technical_score, "News": s.news_score} for s in analysis["score_history"]],
            width="stretch",
        )
    else:
        st.write("No Score history yet.")

    st.subheader("Financial Statements")
    if analysis["financial_statements"]:
        st.dataframe(
            [{"Period": s.period_end, "Revenue": s.revenue, "Net Income": s.net_income,
              "Total Assets": s.total_assets} for s in analysis["financial_statements"]],
            width="stretch",
        )
    else:
        st.write("No FinancialStatements yet.")

    st.subheader("Technical Snapshots")
    if analysis["technical_snapshots"]:
        st.dataframe(
            [{"Computed At": t.computed_at, "Trend": t.trend.value if t.trend else None,
              "RSI": t.rsi, "Breakout": t.breakout} for t in analysis["technical_snapshots"]],
            width="stretch",
        )
    else:
        st.write("No TechnicalSnapshots yet.")

    st.subheader("Recent News")
    if analysis["news"]:
        for item in analysis["news"][:10]:
            st.write(f"- **{item.published_at}** ({item.publisher_name}): {item.headline} "
                      f"[sentiment={item.sentiment_score}, relevance={item.relevance_score}]")
    else:
        st.write("No news yet.")


def render_financial_statements():
    st.title("Financial Statements")
    companies = load_companies_overview()
    if not companies:
        st.write("No companies on record.")
        return
    selected = st.selectbox("Company", [c.company_id for c in companies], key="fs_company")
    statements = load_financial_statements(selected)
    if not statements:
        st.write("No FinancialStatements for this company yet.")
        return
    table = [
        {
            "Period": s.period_end, "Type": s.period_type.value, "Revenue": s.revenue,
            "Net Interest Income": s.net_interest_income, "Net Income": s.net_income,
            "EPS (Diluted)": s.eps_diluted, "Total Assets": s.total_assets,
            "Total Liabilities": s.total_liabilities, "Total Equity": s.total_equity,
            "Operating CF": s.operating_cash_flow, "Free Cash Flow": s.free_cash_flow,
        }
        for s in statements
    ]
    st.dataframe(table, width="stretch")

    latest_score = CompanyRepository(DB_PATH).get_latest_score(selected)
    if latest_score and latest_score.financial_breakdown:
        st.subheader("Latest Financial Score Breakdown")
        st.json(latest_score.financial_breakdown)


def render_news_feed():
    st.title("News Feed")
    companies = load_companies_overview()
    options = ["All companies"] + [c.company_id for c in companies]
    selected = st.selectbox("Filter by company", options)
    company_id = None if selected == "All companies" else selected
    news = load_news_items(company_id)
    if not news:
        st.write("No news items found.")
        return
    table = [
        {
            "Published": n.published_at, "Company": n.company_id, "Publisher": n.publisher_name,
            "Headline": n.headline, "Sentiment": n.sentiment_score, "Relevance": n.relevance_score,
        }
        for n in news
    ]
    st.dataframe(table, width="stretch")


def render_historical_timeline():
    st.title("Historical Timeline")
    snapshots = load_portfolio_snapshot_history()
    if not snapshots:
        st.write("No PortfolioSnapshots yet — run a Long-Term or Swing Job.")
        return
    table = [
        {"Captured At": s.captured_at, "Origin": s.origin.value, "Cash": s.cash,
         "Total Value": s.computed_allocation.get("total_value")}
        for s in snapshots
    ]
    st.dataframe(table, width="stretch")


def render_longterm_rankings():
    st.title("Long-Term Rankings")
    rankings = load_longterm_rankings()
    if not rankings:
        st.write("No scored WATCHLIST companies yet — run `python -m egxpm.run_longterm`.")
        return

    table = [
        {
            "Company": row["company"].company_id, "Name": row["company"].name,
            "Sector": row["company"].sector, "Composite": row["score"].composite_score,
            "Financial": row["score"].financial_score, "Technical": row["score"].technical_score,
            "News": row["score"].news_score,
        }
        for row in rankings
    ]
    st.dataframe(table, width="stretch")

    st.subheader("Score Breakdown")
    selected = st.selectbox("Company", [row["company"].company_id for row in rankings])
    selected_row = next(row for row in rankings if row["company"].company_id == selected)
    col1, col2 = st.columns(2)
    col1.write("**Financial breakdown**")
    col1.json(selected_row["score"].financial_breakdown)
    col2.write("**Technical breakdown**")
    col2.json(selected_row["score"].technical_breakdown)
    st.write("**News breakdown**")
    st.json(selected_row["score"].news_breakdown)


def render_job_status():
    st.title("Job Status")
    jobs = load_recent_jobs()
    if not jobs:
        st.write("No Jobs recorded yet.")
        return
    table = [
        {
            "Job ID": job.job_id[:8], "Type": job.job_type.value, "Status": job.status.value,
            "Started": job.started_at, "Completed": job.completed_at,
            "Processed": job.companies_processed, "Failed": job.companies_failed,
        }
        for job in jobs
    ]
    st.dataframe(table, width="stretch")


def render_collector_status():
    st.title("Collector Status")
    runs = load_recent_collection_runs()
    if not runs:
        st.write("No CollectionRuns recorded yet.")
        return

    by_source: dict[str, dict[str, int]] = {}
    for run in runs:
        stats = by_source.setdefault(run.data_source_id, {"completed": 0, "failed": 0, "other": 0})
        if run.status == RunStatus.COMPLETED:
            stats["completed"] += 1
        elif run.status == RunStatus.FAILED:
            stats["failed"] += 1
        else:
            stats["other"] += 1

    st.subheader("Source Health (rolling 30-day success rate, 1-hr cache)")
    health = load_source_health(tuple(sorted(by_source.keys())))
    st.dataframe(
        [{"Source": source, "Rolling Success Rate": f"{rate:.0%}" if rate is not None else "n/a"}
         for source, rate in health.items()],
        width="stretch",
    )

    st.subheader("Success rate by source (most recent runs shown)")
    st.dataframe(
        [{"Source": source, **stats} for source, stats in by_source.items()],
        width="stretch",
    )

    st.subheader("Recent runs")
    table = [
        {
            "Source": run.data_source_id, "Company": run.company_id, "Status": run.status.value,
            "Started": run.started_at, "Records": run.records_collected, "Error": run.error_message,
        }
        for run in runs
    ]
    st.dataframe(table, width="stretch")


def render_raw_database_explorer():
    st.title("Raw Database Explorer")
    st.caption("Read-only. Any table, paginated.")
    tables = load_table_names()
    selected = st.selectbox("Table", tables)
    page_size = st.number_input("Rows per page", min_value=10, max_value=500, value=50, step=10)
    page = st.number_input("Page", min_value=1, value=1)
    rows, total = load_table_page(selected, limit=page_size, offset=(page - 1) * page_size)
    st.caption(f"{total} total rows")
    if rows:
        st.dataframe(rows, width="stretch")
    else:
        st.write("No rows on this page.")


def _get_copilot_session() -> CopilotSession:
    """Session state, not @st.cache_data — this is stateful conversation,
    not a cached read-only Repository lookup, and belongs to one browser
    session, not shared across users the way a cached page load is."""
    if "copilot_session" not in st.session_state:
        registry = ToolRegistry(DB_PATH)
        st.session_state.copilot_session = CopilotSession(registry)
        st.session_state.copilot_display_history = []
    return st.session_state.copilot_session


def _ensure_conversation(session: CopilotSession) -> str:
    if session.conversation_id is None:
        conversation = Conversation()
        session.registry.conversation_repo.save_conversation(conversation)
        session.conversation_id = conversation.conversation_id
    return session.conversation_id


def render_copilot():
    st.title("Copilot")
    st.caption(
        "Conversational analysis assistant — read-only tools run immediately; "
        "propose_rebalance and propose_swing_analysis create a pending plan below "
        "that you must explicitly confirm. This system never places real trades: "
        "confirming a plan only records the decision — you still execute it "
        "yourself in Thndr."
    )
    session = _get_copilot_session()

    for role, text in st.session_state.copilot_display_history:
        with st.chat_message(role):
            st.markdown(text)

    user_text = st.chat_input("Ask about a company, your portfolio, or propose a plan...")
    if user_text:
        st.session_state.copilot_display_history.append(("user", user_text))
        with st.chat_message("user"):
            st.markdown(user_text)
        with st.chat_message("assistant"):
            with st.spinner("Thinking..."):
                try:
                    reply = session.send_message(user_text)
                except BusinessDataError as exc:
                    reply = f"(the LLM call failed: {exc})"
            st.markdown(reply)
        st.session_state.copilot_display_history.append(("assistant", reply))

    pending = session.state.pending_plans
    if pending:
        st.subheader("Pending Plans")
        st.caption("Clicking Confirm is the explicit approval step — nothing is applied without it.")
        for plan_id, plan in list(pending.items()):
            with st.expander(f"{plan.get('plan_type', 'plan')} — {plan_id}"):
                st.json(plan)
                if st.button("Confirm", key=f"confirm-{plan_id}"):
                    result = session.registry.execute(
                        "confirm_and_apply", {"plan_id": plan_id}, session.state
                    )
                    if result.success:
                        st.success(result.data["message"])
                    else:
                        st.error(result.error)
                    st.rerun()

    if session.state.confirmed_plan_ids:
        st.caption(f"Confirmed this session: {', '.join(session.state.confirmed_plan_ids)}")

    if st.session_state.copilot_display_history and st.button("Save session"):
        conversation_id = _ensure_conversation(session)
        result = session.registry.execute(
            "save_analysis_session",
            {"session_id": session.session_id, "conversation_id": conversation_id},
            session.state,
        )
        if result.success:
            st.success(f"Session saved (session_id={session.session_id}).")
        else:
            st.error(result.error)


PAGES = {
    "Home": render_home,
    "Portfolio — Holdings Detail": render_portfolio_holdings,
    "Watchlist": render_watchlist,
    "Swing Trading": render_swing_trading,
    "Long-Term Rankings": render_longterm_rankings,
    "Recommendations History": render_recommendations_history,
    "Recommendation Performance": render_recommendation_performance,
    "Company Analysis": render_company_analysis,
    "Financial Statements": render_financial_statements,
    "News Feed": render_news_feed,
    "Historical Timeline": render_historical_timeline,
    "Collector Status": render_collector_status,
    "Job Status": render_job_status,
    "Raw Database Explorer": render_raw_database_explorer,
    "Copilot": render_copilot,
}

page_name = st.sidebar.radio("Page", list(PAGES.keys()))
PAGES[page_name]()
