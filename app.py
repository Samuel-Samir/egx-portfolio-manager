"""Minimal Dashboard — Home, Long-Term Rankings, Job Status, Collector Status.

Per the Dashboard Rules (Section 16): never calls Engines or the LLM, never
writes to Persistence. AllocationReport on Home is the one exception —
computed at read time via DashboardReadRepository (pure arithmetic, not an
Engine). Every Repository call is wrapped in @st.cache_data(ttl=300).
"""

from __future__ import annotations

import streamlit as st

from egxpm.persistence.company_repository import CompanyRepository
from egxpm.persistence.dashboard_read_repository import DashboardReadRepository
from egxpm.persistence.db import init_db
from egxpm.persistence.models import RunStatus
from egxpm.persistence.operational_repository import OperationalRepository
from egxpm.persistence.recommendation_repository import RecommendationRepository
from egxpm.shared.config import load_configuration_snapshot

DB_PATH = "data/egx.db"
CACHE_TTL_SECONDS = 300

init_db(DB_PATH)  # idempotent — safe to call on every page load
st.set_page_config(page_title="EGX Portfolio Manager", layout="wide")


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
    from egxpm.persistence.portfolio_repository import PortfolioRepository
    return PortfolioRepository(DB_PATH).get_latest_snapshot()


@st.cache_data(ttl=CACHE_TTL_SECONDS)
def load_longterm_rankings():
    return DashboardReadRepository(DB_PATH).get_longterm_rankings()


@st.cache_data(ttl=CACHE_TTL_SECONDS)
def load_recent_jobs(limit: int = 20):
    jobs = OperationalRepository(DB_PATH).list_jobs()
    return jobs[:limit]


@st.cache_data(ttl=CACHE_TTL_SECONDS)
def load_recent_collection_runs(limit: int = 50):
    runs = OperationalRepository(DB_PATH).list_collection_runs()
    return runs[:limit]


@st.cache_data(ttl=CACHE_TTL_SECONDS)
def load_recent_recommendations(limit: int = 20):
    recs = RecommendationRepository(DB_PATH).list_recommendations()
    return sorted(recs, key=lambda r: r.created_at, reverse=True)[:limit]


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


PAGES = {
    "Home": render_home,
    "Long-Term Rankings": render_longterm_rankings,
    "Job Status": render_job_status,
    "Collector Status": render_collector_status,
}

page_name = st.sidebar.radio("Page", list(PAGES.keys()))
PAGES[page_name]()
