"""EGX Disclosure Collector — official EGX disclosures, semi-manual entry (v1).

No automated feed for official EGX disclosures has been identified (an
open item per the architecture doc — remains manual until one is found,
same as Corporate Actions). This Collector does no scraping; its only job
is to stamp a manually-entered disclosure consistently with the right
provenance fields.
"""

from __future__ import annotations

from egxpm.persistence.models import NewsItem

PUBLISHER_NAME = "Egyptian Exchange (EGX)"


def create_disclosure_news_item(
    headline: str,
    published_at: str,
    collection_run_id: str,
    company_id: str | None = None,
    sector_scope: str | None = None,
    url: str | None = None,
    source_version: str = "1",
) -> NewsItem:
    """Constructs a NewsItem for a manually-entered official EGX disclosure.

    Raises:
        ValueError: neither company_id nor sector_scope was provided — a
            disclosure must be scoped to something.
    """
    if company_id is None and sector_scope is None:
        raise ValueError("a disclosure must be scoped to a company_id or a sector_scope")

    return NewsItem(
        company_id=company_id,
        sector_scope=sector_scope,
        headline=headline,
        publisher_name=PUBLISHER_NAME,
        published_at=published_at,
        url=url,
        data_source_id="egx_official",
        source_version=source_version,
        collection_run_id=collection_run_id,
    )
