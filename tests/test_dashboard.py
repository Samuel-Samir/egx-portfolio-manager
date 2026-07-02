import os

import pytest
from streamlit.testing.v1 import AppTest

# All 14 pages per the architecture doc's Page Inventory. "Reports" (the
# 15th page listed there) is out of scope — no Job writes dated Markdown
# files to reports/ yet.
PAGES = [
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


def _require_real_db():
    if not os.path.exists("data/egx.db"):
        pytest.skip("data/egx.db not present — run collection + Long-Term Job first")


@pytest.mark.parametrize("page", PAGES)
def test_page_renders_without_exception(page):
    _require_real_db()
    at = AppTest.from_file("app.py")
    at.run(timeout=30)
    at.sidebar.radio[0].set_value(page).run(timeout=30)
    assert list(at.exception) == []


def test_all_14_pages_registered():
    at = AppTest.from_file("app.py")
    at.run(timeout=30)
    assert set(at.sidebar.radio[0].options) == set(PAGES)
    assert len(PAGES) == 14
