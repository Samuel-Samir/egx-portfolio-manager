import os

import pytest
from streamlit.testing.v1 import AppTest

# All 14 read-only pages per the architecture doc's Page Inventory, plus
# the Copilot (M7) — the one page that isn't read-only, per the Dashboard
# Rules exception for the Copilot Tool Layer. "Reports" (the 15th page
# listed in the doc's read-only inventory) is out of scope — no Job writes
# dated Markdown files to reports/ yet.
READ_ONLY_PAGES = [
    "Home",
    "Portfolio — Holdings Detail",
    "Watchlist",
    "Swing Trading",
    "Long-Term Rankings",
    "Recommendations History",
    "Recommendation Performance",
    "Company Analysis",
    "Financial Statements",
    "News Feed",
    "Historical Timeline",
    "Collector Status",
    "Job Status",
    "Raw Database Explorer",
]
PAGES = READ_ONLY_PAGES + ["Copilot"]


def _require_real_db():
    if not os.path.exists("data/egx.db"):
        pytest.skip("data/egx.db not present — run collection + Long-Term Job first")


@pytest.mark.parametrize("page", READ_ONLY_PAGES)
def test_page_renders_without_exception(page):
    _require_real_db()
    at = AppTest.from_file("app.py")
    at.run(timeout=30)
    at.sidebar.radio[0].set_value(page).run(timeout=30)
    assert list(at.exception) == []


def test_copilot_page_renders_without_exception():
    # Only requires ANTHROPIC_API_KEY to construct the client, not a network
    # call — the page renders its empty chat + pending-plans UI on load.
    _require_real_db()
    if not os.environ.get("ANTHROPIC_API_KEY"):
        pytest.skip("ANTHROPIC_API_KEY not set")
    at = AppTest.from_file("app.py")
    at.run(timeout=30)
    at.sidebar.radio[0].set_value("Copilot").run(timeout=30)
    assert list(at.exception) == []


def test_all_15_pages_registered():
    at = AppTest.from_file("app.py")
    at.run(timeout=30)
    assert set(at.sidebar.radio[0].options) == set(PAGES)
    assert len(PAGES) == 15


@pytest.mark.parametrize("page", READ_ONLY_PAGES)
def test_page_renders_without_exception_in_arabic(page):
    # format_func translates the displayed label only — the underlying
    # radio value (and PAGES dict key) stays the stable English string,
    # so routing is unaffected by the language toggle.
    _require_real_db()
    at = AppTest.from_file("app.py")
    at.run(timeout=30)
    at.sidebar.selectbox[0].set_value("ar").run(timeout=30)
    at.sidebar.radio[0].set_value(page).run(timeout=30)
    assert list(at.exception) == []
