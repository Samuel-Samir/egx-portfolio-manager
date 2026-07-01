"""News Collector — Mubasher Info (primary news source).

Discovery finding (2-day time-box, resolved on day 1): no XHR/API
reverse-engineering or Playwright was needed. A company's stock page
(/markets/EGX/stocks/{ticker}) is plain server-rendered HTML containing a
".stock-overview-media-block" list of its most recent headlines+links, and
each article page cleanly exposes its own publish date and source label —
both static HTML, scrapable with httpx + selectolax like every other
collector in this codebase.
"""

from __future__ import annotations

import httpx
from selectolax.parser import HTMLParser

from egxpm.persistence.db import YFINANCE_TICKERS
from egxpm.persistence.models import NewsItem
from egxpm.shared.exceptions import InsufficientDataError, ScraperSchemaChangedError

MUBASHER_SYMBOLS = {
    company_id: ticker.removesuffix(".CA") for company_id, ticker in YFINANCE_TICKERS.items()
}

BASE_URL = "https://www.mubasher.info"

_ARABIC_MONTHS = {
    "يناير": 1, "فبراير": 2, "مارس": 3, "أبريل": 4, "مايو": 5, "يونيو": 6,
    "يوليو": 7, "أغسطس": 8, "سبتمبر": 9, "أكتوبر": 10, "نوفمبر": 11, "ديسمبر": 12,
}


def fetch_overview_page(ticker: str) -> str:
    """Thin wrapper around httpx, isolated so it can be monkeypatched in tests."""
    response = httpx.get(
        f"{BASE_URL}/markets/EGX/stocks/{ticker}",
        headers={"User-Agent": "Mozilla/5.0"}, timeout=30, follow_redirects=True,
    )
    response.raise_for_status()
    return response.text


def fetch_article_page(path: str) -> str:
    """Thin wrapper around httpx, isolated so it can be monkeypatched in tests."""
    response = httpx.get(
        f"{BASE_URL}{path}", headers={"User-Agent": "Mozilla/5.0"},
        timeout=30, follow_redirects=True,
    )
    response.raise_for_status()
    return response.text


def _parse_mubasher_datetime(raw: str) -> str:
    """Parses '14 يونيو 2026 04:16 م' into an ISO8601 string.

    Assumes Egypt Standard Time (UTC+2, fixed year-round since Egypt
    dropped DST in 2023) since Mubasher displays local Cairo time with no
    explicit offset.
    """
    day_str, month_name, year_str, time_str, meridiem = raw.strip().split()
    day = int(day_str)
    month = _ARABIC_MONTHS[month_name]
    year = int(year_str)
    hour, minute = (int(part) for part in time_str.split(":"))
    if meridiem == "م" and hour != 12:
        hour += 12
    elif meridiem == "ص" and hour == 12:
        hour = 0
    return f"{year:04d}-{month:02d}-{day:02d}T{hour:02d}:{minute:02d}:00+02:00"


def parse_overview(html: str) -> list[dict]:
    """Extracts (headline, url) pairs from a company's stock overview page.

    Raises:
        ScraperSchemaChangedError: the news-list container itself is
            missing (a real layout change, not just "no recent news").
    """
    doc = HTMLParser(html)
    container = doc.css_first(".stock-overview__media-blocks")
    if container is None:
        raise ScraperSchemaChangedError("stock-overview__media-blocks container not found")

    entries = []
    for block in container.css(".stock-overview-media-block"):
        title_link = block.css_first("a.mi-home-media-block__title")
        if title_link is None:
            continue
        href = title_link.attributes.get("href")
        headline = title_link.text(strip=True)
        if href and headline:
            entries.append({"headline": headline, "url": href})
    return entries


def parse_article(html: str) -> dict:
    """Extracts published_at (ISO8601) and publisher_name from an article page.

    The page ships both server-rendered values and unrendered Angular
    template placeholders side by side; this picks the first element whose
    text doesn't still contain a literal "{{" binding.

    Raises:
        ScraperSchemaChangedError: neither the date nor the source label
            could be found in rendered form.
    """
    doc = HTMLParser(html)

    published_at_raw = next(
        (el.text(strip=True) for el in doc.css(".mi-article__published-at")
         if el.text(strip=True) and "{{" not in el.text(strip=True)),
        None,
    )
    source_raw = next(
        (el.text(strip=True) for el in doc.css(".mi-article__source")
         if el.text(strip=True) and "{{" not in el.text(strip=True)),
        None,
    )
    if published_at_raw is None or source_raw is None:
        raise ScraperSchemaChangedError("could not find rendered published_at/source on article page")

    publisher_name = source_raw.split(":", 1)[-1].strip() if ":" in source_raw else source_raw
    return {
        "published_at": _parse_mubasher_datetime(published_at_raw),
        "publisher_name": publisher_name,
    }


def collect_news(
    company_id: str, collection_run_id: str, source_version: str = "1"
) -> list[NewsItem]:
    """Fetch recent news for company_id via Mubasher.

    Raises:
        InsufficientDataError: no ticker mapping exists, or the company
            currently has no news entries on its overview page.
        ScraperSchemaChangedError: propagated from parse_overview/parse_article.
        Exception: whatever fetch_overview_page()/fetch_article_page() raise
            (missing ticker, rate limit, timeout, ...) propagates unwrapped —
            CollectorService, not this Collector, decides transient vs.
            structural.
    """
    ticker = MUBASHER_SYMBOLS.get(company_id)
    if ticker is None:
        raise InsufficientDataError(f"no Mubasher symbol mapping for company_id={company_id!r}")

    entries = parse_overview(fetch_overview_page(ticker))
    if not entries:
        raise InsufficientDataError(f"no news entries found for ticker={ticker!r}")

    items = []
    for entry in entries:
        details = parse_article(fetch_article_page(entry["url"]))
        items.append(
            NewsItem(
                company_id=company_id,
                headline=entry["headline"],
                publisher_name=details["publisher_name"],
                published_at=details["published_at"],
                url=f"{BASE_URL}{entry['url']}",
                data_source_id="mubasher",
                source_version=source_version,
                collection_run_id=collection_run_id,
            )
        )
    return items
