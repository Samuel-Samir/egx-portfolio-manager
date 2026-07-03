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

Arabic support: a sidebar language toggle translates fixed UI chrome
(titles, labels, captions, column headers) via egxpm/shared/i18n.t() —
data itself (company names, tickers, numbers, JSON breakdown keys) is
never translated. This is a separate concern from the language the
Reasoning Layer writes recommendations in (see llm/prompts.py) or the
language the Copilot replies in (which follows the user's own language).
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
from egxpm.shared.i18n import is_rtl, t
from egxpm.shared.recommendation_analytics import summarize_performance

DB_PATH = "data/egx.db"
CACHE_TTL_SECONDS = 300

init_db(DB_PATH)  # idempotent — safe to call on every page load
st.set_page_config(page_title="EGX Portfolio Manager", layout="wide")


def _lang() -> str:
    return st.session_state.get("language", "en")


# ------------------------------------------------------------
# Cached data loaders — one per Repository call, per the Dashboard Rules
# ------------------------------------------------------------

@st.cache_data(ttl=CACHE_TTL_SECONDS)
def load_allocation():
    """Returns (AllocationReport, missing_price_company_ids).

    A held company with literally no price on record (e.g. ADA — no
    collector currently covers it) must not crash the whole Home page.
    It's excluded from the arithmetic here and its exclusion is surfaced
    to the caller so the page can show a visible warning — the Dashboard
    boundary is the right place for this tolerance, not
    AllocationCalculator.calculate() itself, which must keep raising for
    every other caller (e.g. the real Job pipeline) where a silent gap
    would be a genuine bug rather than an expected, permanent one.
    """
    dashboard_repo = DashboardReadRepository(DB_PATH)
    company_repo = CompanyRepository(DB_PATH)
    holdings = company_repo.list_holdings()
    prices = company_repo.get_latest_prices([h.company_id for h in holdings])
    missing = sorted({h.company_id for h in holdings if h.company_id not in prices})
    priced_holdings = [h for h in holdings if h.company_id in prices]
    fallback_config = load_configuration_snapshot()
    allocation = dashboard_repo.get_current_allocation(
        prices=prices, cash=0.0, fallback_config=fallback_config, holdings_override=priced_holdings,
    )
    return allocation, missing


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
def load_all_executions():
    return RecommendationRepository(DB_PATH).list_all_executions()


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
    lang = _lang()
    st.title(t("Home — Portfolio Summary", lang))

    allocation, missing_price_company_ids = load_allocation()
    col1, col2, col3 = st.columns(3)
    col1.metric(t("Total Portfolio Value (EGP)", lang), f"{allocation.total_value:,.2f}")
    col2.metric(t("Cash (EGP)", lang), f"{allocation.cash:,.2f}")
    col3.metric(t("Holdings Count", lang), len(allocation.by_stock_pct))

    if missing_price_company_ids:
        st.warning(
            f"{t('Price data unavailable — excluded from allocation below', lang)}: "
            f"{', '.join(missing_price_company_ids)}"
        )

    if allocation.total_value == 0:
        st.info(t(
            "No real Holding data has been entered yet — this shows an empty portfolio, "
            "not an error. Enter your actual EGX positions to see real allocation here.",
            lang,
        ))

    if allocation.by_category_pct:
        st.subheader(t("Allocation by Category", lang))
        st.bar_chart(allocation.by_category_pct)

    if allocation.stock_constraint_violations:
        st.warning(f"{t('Stock constraint violations', lang)}: {', '.join(allocation.stock_constraint_violations)}")

    snapshot = load_latest_portfolio_snapshot()
    if snapshot:
        st.caption(f"{t('Last PortfolioSnapshot', lang)}: {snapshot.captured_at} ({t('origin', lang)}={snapshot.origin.value})")
    else:
        st.caption(t("No PortfolioSnapshot captured yet — run the Long-Term Job.", lang))

    st.subheader(t("Recent Recommendations", lang))
    recommendations = load_recent_recommendations(limit=5)
    if not recommendations:
        st.write(t("No Recommendations yet.", lang))
    else:
        for rec in recommendations:
            with st.expander(f"{rec.company_id} — {rec.action.value} ({rec.created_at})"):
                st.write(rec.frozen_package.get("reasoning", ""))
                risks = rec.frozen_package.get("key_risks", [])
                if risks:
                    st.write(f"**{t('Key risks:', lang)}**")
                    for risk in risks:
                        st.write(f"- {risk}")
                alternatives = rec.frozen_package.get("rejected_alternatives", [])
                if alternatives:
                    st.write(f"**{t('Rejected alternatives:', lang)}**")
                    for alt in alternatives:
                        st.write(f"- {alt}")


def render_portfolio_holdings():
    lang = _lang()
    st.title(t("Portfolio — Holdings Detail", lang))
    rows = load_holdings_detail()
    if not rows:
        st.write(t("No Holdings on record. This is expected until real positions are entered.", lang))
    else:
        table = []
        for row in rows:
            holding, company, score = row["holding"], row["company"], row["score"]
            table.append({
                t("Company", lang): holding.company_id, t("Name", lang): company.name if company else None,
                t("Category", lang): holding.category.value, t("Quantity", lang): holding.quantity,
                t("Avg Cost", lang): holding.average_cost, t("Latest Price", lang): row["latest_price"],
                t("Unrealized P&L", lang): row["unrealized_pnl"],
                t("Composite Score", lang): score.composite_score if score else None,
                t("Confidence", lang): row["confidence"].confidence_value if row["confidence"] else None,
            })
        st.dataframe(table, width="stretch")

    st.subheader(t("Add Transaction", lang))
    st.caption(t(
        "Records a real transaction you made (or are about to make) in Thndr — this "
        "system never places real trades itself. Updates your Holdings and adds it "
        "to the transaction history below.",
        lang,
    ))

    companies = load_companies_overview()
    session = _get_copilot_session()

    col1, col2 = st.columns(2)
    company_id = col1.selectbox(t("Company", lang), [c.company_id for c in companies], key="txn_company")
    action = col2.selectbox(t("Action", lang), ["BUY", "ADD", "SELL", "TRIM"], key="txn_action")
    col3, col4 = st.columns(2)
    quantity = col3.number_input(t("Quantity", lang), min_value=0.0, step=1.0, key="txn_quantity")
    price = col4.number_input(t("Price", lang), min_value=0.0, step=0.01, format="%.2f", key="txn_price")
    category = st.selectbox(
        f"{t('Category', lang)} ({t('required for a new position', lang)})",
        ["", "bmm_index", "long_term_stocks", "swing_trading", "cloud_cash", "gold"],
        key="txn_category",
    )
    related_recs = [r for r in load_all_recommendations() if r.company_id == company_id][:10]
    rec_none_label = f"({t('none', lang)})"
    rec_options = [rec_none_label] + [f"{r.action.value} @ {r.created_at}" for r in related_recs]
    rec_choice = st.selectbox(t("Link to a Recommendation (optional)", lang), rec_options, key="txn_rec")

    if st.button(t("Add", lang)):
        recommendation_id = None
        if rec_choice != rec_none_label:
            recommendation_id = related_recs[rec_options.index(rec_choice) - 1].recommendation_id
        result = session.registry.execute("record_holding_transaction", {
            "company_id": company_id, "action": action, "quantity": quantity, "price": price,
            "category": category or None, "recommendation_id": recommendation_id,
        }, session.state)
        if result.success:
            st.success(f"{action} {quantity} {company_id} @ {price:.2f} EGP — {t('recorded', lang)}.")
            load_holdings_detail.clear()
            load_allocation.clear()
            load_portfolio_snapshot_history.clear()
            load_all_executions.clear()
            st.rerun()
        else:
            st.error(result.error)

    st.subheader(t("Transaction History", lang))
    executions = load_all_executions()
    if not executions:
        st.write(t("No transactions recorded yet.", lang))
    else:
        exec_table = [
            {
                t("Executed At", lang): e.executed_at, t("Action", lang): e.details.get("action"),
                t("Company", lang): e.details.get("company_id"), t("Quantity", lang): e.details.get("quantity"),
                t("Price", lang): e.details.get("price"),
                t("Recommendation", lang): e.recommendation_id[:8] if e.recommendation_id else None,
            }
            for e in executions
        ]
        st.dataframe(exec_table, width="stretch")


def render_watchlist():
    lang = _lang()
    st.title(t("Watchlist", lang))
    rows = load_watchlist_detail()
    if not rows:
        st.write(t("No WATCHLIST or CANDIDATE companies found.", lang))
        return

    table = [
        {
            t("Company", lang): row["company"].company_id, t("Name", lang): row["company"].name,
            t("State", lang): row["state"].value, t("Sector", lang): row["company"].sector,
            t("Composite Score", lang): row["score"].composite_score if row["score"] else None,
            t("Trend", lang): row["technical_snapshot"].trend.value if row["technical_snapshot"] and row["technical_snapshot"].trend else None,
        }
        for row in rows
    ]
    st.dataframe(table, width="stretch")


def render_swing_trading():
    lang = _lang()
    st.title(t("Swing Trading", lang))
    st.caption(t(
        "Today's swing Recommendations. Identified by having a stop_loss set — "
        "only swing Recommendations carry ATR-based stop/target/size; "
        "long-term Recommendations don't (Position Sizing is swing-only).",
        lang,
    ))
    today = date.today().isoformat()
    swing_today = [
        rec for rec in load_all_recommendations()
        if rec.stop_loss is not None and rec.created_at[:10] == today
    ]
    if not swing_today:
        st.write(t("No swing Recommendations today.", lang))
        return

    for rec in swing_today:
        events = load_recommendation_events(rec.recommendation_id)
        superseded = len(events["supersessions"]) > 0
        with st.expander(f"{rec.company_id} — {rec.action.value} {t('(superseded)', lang) if superseded else ''}"):
            st.write(f"Entry: {rec.entry_price} | Stop: {rec.stop_loss} | Target: {rec.take_profit} | Size: {rec.position_size}")
            st.write(rec.frozen_package.get("reasoning", ""))


def render_recommendations_history():
    lang = _lang()
    st.title(t("Recommendations History", lang))
    recommendations = load_all_recommendations()
    if not recommendations:
        st.write(t("No Recommendations yet.", lang))
        return

    page_size = 20
    total_pages = max(1, (len(recommendations) + page_size - 1) // page_size)
    page = st.number_input(t("Page", lang), min_value=1, max_value=total_pages, value=1)
    start = (page - 1) * page_size
    page_items = recommendations[start:start + page_size]

    table = []
    for rec in page_items:
        events = load_recommendation_events(rec.recommendation_id)
        table.append({
            t("Company", lang): rec.company_id, t("Action", lang): rec.action.value, t("Created", lang): rec.created_at,
            t("Superseded", lang): len(events["supersessions"]) > 0,
            t("Executions", lang): len(events["executions"]), t("Outcomes", lang): len(events["outcomes"]),
        })
    st.dataframe(table, width="stretch")
    st.caption(f"{t('Page', lang)} {page} {t('of', lang)} {total_pages} ({len(recommendations)} {t('total', lang)})")


def render_recommendation_performance():
    lang = _lang()
    st.title(t("Recommendation Performance", lang))
    recommendations = load_all_recommendations()
    all_outcomes = []
    all_feedback = []
    for rec in recommendations:
        events = load_recommendation_events(rec.recommendation_id)
        all_outcomes.extend(events["outcomes"])
        all_feedback.extend(events["feedback"])

    if not all_outcomes:
        st.write(t(
            "No Outcomes recorded yet — Performance analytics will populate once trades "
            "are executed and outcomes tracked.",
            lang,
        ))
        return

    summary = summarize_performance(all_outcomes)

    col1, col2, col3 = st.columns(3)
    col1.metric(t("Final Outcomes", lang), summary.final_outcome_count)
    col2.metric(t("Target Hit Rate", lang), f"{summary.target_hit_rate * 100:.1f}%" if summary.target_hit_rate is not None else "n/a")
    col3.metric(t("Stop Hit Rate", lang), f"{summary.stop_hit_rate * 100:.1f}%" if summary.stop_hit_rate is not None else "n/a")
    if summary.average_return is not None:
        st.metric(t("Average Return", lang), f"{summary.average_return * 100:.2f}%")

    st.subheader(t("User Feedback", lang))
    if not all_feedback:
        st.write(t("No UserFeedback recorded yet.", lang))
    else:
        st.dataframe(
            [{t("Agreement", lang): f.agreement.value if f.agreement else None, t("Text", lang): f.feedback_text} for f in all_feedback],
            width="stretch",
        )


def render_company_analysis():
    lang = _lang()
    st.title(t("Company Analysis", lang))
    companies = load_companies_overview()
    if not companies:
        st.write(t("No companies on record.", lang))
        return
    selected = st.selectbox(t("Company", lang), [c.company_id for c in companies])
    analysis = load_company_analysis(selected)

    st.subheader(t("Score History", lang))
    if analysis["score_history"]:
        st.dataframe(
            [{t("Computed At", lang): s.computed_at, t("Composite Score", lang): s.composite_score, t("Financial", lang): s.financial_score,
              t("Technical", lang): s.technical_score, t("News", lang): s.news_score} for s in analysis["score_history"]],
            width="stretch",
        )
    else:
        st.write(t("No Score history yet.", lang))

    st.subheader(t("Financial Statements", lang))
    if analysis["financial_statements"]:
        st.dataframe(
            [{t("Period", lang): s.period_end, t("Revenue", lang): s.revenue, t("Net Income", lang): s.net_income,
              t("Total Assets", lang): s.total_assets} for s in analysis["financial_statements"]],
            width="stretch",
        )
    else:
        st.write(t("No FinancialStatements yet.", lang))

    st.subheader(t("Technical Snapshots", lang))
    if analysis["technical_snapshots"]:
        st.dataframe(
            [{t("Computed At", lang): t2.computed_at, t("Trend", lang): t2.trend.value if t2.trend else None,
              "RSI": t2.rsi, t("Breakout", lang): t2.breakout} for t2 in analysis["technical_snapshots"]],
            width="stretch",
        )
    else:
        st.write(t("No TechnicalSnapshots yet.", lang))

    st.subheader(t("Recent News", lang))
    if analysis["news"]:
        for item in analysis["news"][:10]:
            st.write(f"- **{item.published_at}** ({item.publisher_name}): {item.headline} "
                      f"[sentiment={item.sentiment_score}, relevance={item.relevance_score}]")
    else:
        st.write(t("No news yet.", lang))


def render_financial_statements():
    lang = _lang()
    st.title(t("Financial Statements", lang))
    companies = load_companies_overview()
    if not companies:
        st.write(t("No companies on record.", lang))
        return
    selected = st.selectbox(t("Company", lang), [c.company_id for c in companies], key="fs_company")
    statements = load_financial_statements(selected)
    if not statements:
        st.write(t("No FinancialStatements for this company yet.", lang))
        return
    table = [
        {
            t("Period", lang): s.period_end, t("Type", lang): s.period_type.value, t("Revenue", lang): s.revenue,
            t("Net Interest Income", lang): s.net_interest_income, t("Net Income", lang): s.net_income,
            t("EPS (Diluted)", lang): s.eps_diluted, t("Total Assets", lang): s.total_assets,
            t("Total Liabilities", lang): s.total_liabilities, t("Total Equity", lang): s.total_equity,
            t("Operating CF", lang): s.operating_cash_flow, t("Free Cash Flow", lang): s.free_cash_flow,
        }
        for s in statements
    ]
    st.dataframe(table, width="stretch")

    latest_score = CompanyRepository(DB_PATH).get_latest_score(selected)
    if latest_score and latest_score.financial_breakdown:
        st.subheader(t("Latest Financial Score Breakdown", lang))
        st.json(latest_score.financial_breakdown)


def render_news_feed():
    lang = _lang()
    st.title(t("News Feed", lang))
    companies = load_companies_overview()
    options = [t("All companies", lang)] + [c.company_id for c in companies]
    selected = st.selectbox(t("Filter by company", lang), options)
    company_id = None if selected == t("All companies", lang) else selected
    news = load_news_items(company_id)
    if not news:
        st.write(t("No news items found.", lang))
        return
    table = [
        {
            t("Published", lang): n.published_at, t("Company", lang): n.company_id, t("Publisher", lang): n.publisher_name,
            t("Headline", lang): n.headline, t("Sentiment", lang): n.sentiment_score, t("Relevance", lang): n.relevance_score,
        }
        for n in news
    ]
    st.dataframe(table, width="stretch")


def render_historical_timeline():
    lang = _lang()
    st.title(t("Historical Timeline", lang))
    snapshots = load_portfolio_snapshot_history()
    if not snapshots:
        st.write(t("No PortfolioSnapshots yet — run a Long-Term or Swing Job.", lang))
        return
    table = [
        {t("Captured At", lang): s.captured_at, t("Origin", lang): s.origin.value, t("Cash", lang): s.cash,
         t("Total Value", lang): s.computed_allocation.get("total_value")}
        for s in snapshots
    ]
    st.dataframe(table, width="stretch")


def render_longterm_rankings():
    lang = _lang()
    st.title(t("Long-Term Rankings", lang))
    rankings = load_longterm_rankings()
    if not rankings:
        st.write(t("No scored WATCHLIST companies yet — run `python -m egxpm.run_longterm`.", lang))
        return

    table = [
        {
            t("Company", lang): row["company"].company_id, t("Name", lang): row["company"].name,
            t("Sector", lang): row["company"].sector, "Composite": row["score"].composite_score,
            t("Financial", lang): row["score"].financial_score, t("Technical", lang): row["score"].technical_score,
            t("News", lang): row["score"].news_score,
        }
        for row in rankings
    ]
    st.dataframe(table, width="stretch")

    st.subheader(t("Score Breakdown", lang))
    selected = st.selectbox(t("Company", lang), [row["company"].company_id for row in rankings])
    selected_row = next(row for row in rankings if row["company"].company_id == selected)
    col1, col2 = st.columns(2)
    col1.write(f"**{t('Financial breakdown', lang)}**")
    col1.json(selected_row["score"].financial_breakdown)
    col2.write(f"**{t('Technical breakdown', lang)}**")
    col2.json(selected_row["score"].technical_breakdown)
    st.write(f"**{t('News breakdown', lang)}**")
    st.json(selected_row["score"].news_breakdown)


def render_job_status():
    lang = _lang()
    st.title(t("Job Status", lang))
    jobs = load_recent_jobs()
    if not jobs:
        st.write(t("No Jobs recorded yet.", lang))
        return
    table = [
        {
            t("Job ID", lang): job.job_id[:8], t("Type", lang): job.job_type.value, t("Status", lang): job.status.value,
            t("Started", lang): job.started_at, t("Completed", lang): job.completed_at,
            t("Processed", lang): job.companies_processed, t("Failed", lang): job.companies_failed,
        }
        for job in jobs
    ]
    st.dataframe(table, width="stretch")


def render_collector_status():
    lang = _lang()
    st.title(t("Collector Status", lang))
    runs = load_recent_collection_runs()
    if not runs:
        st.write(t("No CollectionRuns recorded yet.", lang))
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

    st.subheader(t("Source Health (rolling 30-day success rate, 1-hr cache)", lang))
    health = load_source_health(tuple(sorted(by_source.keys())))
    st.dataframe(
        [{t("Source", lang): source, t("Rolling Success Rate", lang): f"{rate:.0%}" if rate is not None else "n/a"}
         for source, rate in health.items()],
        width="stretch",
    )

    st.subheader(t("Success rate by source (most recent runs shown)", lang))
    st.dataframe(
        [{t("Source", lang): source, **stats} for source, stats in by_source.items()],
        width="stretch",
    )

    st.subheader(t("Recent runs", lang))
    table = [
        {
            t("Source", lang): run.data_source_id, t("Company", lang): run.company_id, t("Status", lang): run.status.value,
            t("Started", lang): run.started_at, t("Records", lang): run.records_collected, t("Error", lang): run.error_message,
        }
        for run in runs
    ]
    st.dataframe(table, width="stretch")


def render_raw_database_explorer():
    lang = _lang()
    st.title(t("Raw Database Explorer", lang))
    st.caption(t("Read-only. Any table, paginated.", lang))
    tables = load_table_names()
    selected = st.selectbox(t("Table", lang), tables)
    page_size = st.number_input(t("Rows per page", lang), min_value=10, max_value=500, value=50, step=10)
    page = st.number_input(t("Page", lang), min_value=1, value=1)
    rows, total = load_table_page(selected, limit=page_size, offset=(page - 1) * page_size)
    st.caption(f"{total} {t('total rows', lang)}")
    if rows:
        st.dataframe(rows, width="stretch")
    else:
        st.write(t("No rows on this page.", lang))


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
    lang = _lang()
    st.title(t("Copilot", lang))
    st.caption(t(
        "Conversational analysis assistant — read-only tools run immediately; "
        "propose_rebalance and propose_swing_analysis create a pending plan below "
        "that you must explicitly confirm. This system never places real trades: "
        "confirming a plan only records the decision — you still execute it "
        "yourself in Thndr.",
        lang,
    ))
    session = _get_copilot_session()

    for role, text in st.session_state.copilot_display_history:
        with st.chat_message(role):
            st.markdown(text)

    user_text = st.chat_input(t("Ask about a company, your portfolio, or propose a plan...", lang))
    if user_text:
        st.session_state.copilot_display_history.append(("user", user_text))
        with st.chat_message("user"):
            st.markdown(user_text)
        with st.chat_message("assistant"):
            with st.spinner(t("Thinking...", lang)):
                try:
                    reply = session.send_message(user_text)
                except BusinessDataError as exc:
                    reply = f"(the LLM call failed: {exc})"
            st.markdown(reply)
        st.session_state.copilot_display_history.append(("assistant", reply))

    pending = session.state.pending_plans
    if pending:
        st.subheader(t("Pending Plans", lang))
        st.caption(t("Clicking Confirm is the explicit approval step — nothing is applied without it.", lang))
        for plan_id, plan in list(pending.items()):
            with st.expander(f"{plan.get('plan_type', 'plan')} — {plan_id}"):
                st.json(plan)
                if st.button(t("Confirm", lang), key=f"confirm-{plan_id}"):
                    result = session.registry.execute(
                        "confirm_and_apply", {"plan_id": plan_id}, session.state
                    )
                    if result.success:
                        st.success(result.data["message"])
                    else:
                        st.error(result.error)
                    st.rerun()

    if session.state.confirmed_plan_ids:
        st.caption(f"{t('Confirmed this session', lang)}: {', '.join(session.state.confirmed_plan_ids)}")

    if st.session_state.copilot_display_history and st.button(t("Save session", lang)):
        conversation_id = _ensure_conversation(session)
        result = session.registry.execute(
            "save_analysis_session",
            {"session_id": session.session_id, "conversation_id": conversation_id},
            session.state,
        )
        if result.success:
            st.success(f"{t('Session saved', lang)} (session_id={session.session_id}).")
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

st.sidebar.selectbox(
    "Language / اللغة", ["en", "ar"], format_func=lambda l: "English" if l == "en" else "العربية",
    key="language",
)
_active_lang = _lang()
if is_rtl(_active_lang):
    st.markdown(
        """<style>
        .stApp, [data-testid="stSidebar"] { direction: rtl; text-align: right; }
        [data-testid="stMetricValue"], [data-testid="stMetricLabel"] { text-align: right; }
        </style>""",
        unsafe_allow_html=True,
    )

page_name = st.sidebar.radio(t("Page", _active_lang), list(PAGES.keys()), format_func=lambda k: t(k, _active_lang))
PAGES[page_name]()
