import pytest

from egxpm.collectors.egx_disclosure_collector import PUBLISHER_NAME, create_disclosure_news_item


def test_creates_company_scoped_disclosure():
    item = create_disclosure_news_item(
        headline="CIB announces capital increase approval",
        published_at="2026-06-01T10:00:00+02:00",
        collection_run_id="r1",
        company_id="COMI",
    )
    assert item.company_id == "COMI"
    assert item.data_source_id == "egx_official"
    assert item.publisher_name == PUBLISHER_NAME
    assert item.publisher_name != item.data_source_id


def test_creates_sector_scoped_disclosure():
    item = create_disclosure_news_item(
        headline="EGX updates listing rules for banking sector",
        published_at="2026-06-01T10:00:00+02:00",
        collection_run_id="r1",
        sector_scope="Banking",
    )
    assert item.company_id is None
    assert item.sector_scope == "Banking"


def test_raises_value_error_when_unscoped():
    with pytest.raises(ValueError):
        create_disclosure_news_item(
            headline="Some disclosure", published_at="2026-06-01T10:00:00+02:00",
            collection_run_id="r1",
        )
