import os

import pytest
from streamlit.testing.v1 import AppTest

PAGES = ["Home", "Long-Term Rankings", "Job Status", "Collector Status"]


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
