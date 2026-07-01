"""Fundamentals Collector — StockAnalysis.com scrape.

StockAnalysis.com identifies each column by a `id="YYYY-MM-DD"` attribute
on the header cell, which gives an exact period_end without any date-string
parsing. Row labels are matched against a small whitelist per statement;
anything not in the whitelist (including the site's own precomputed growth
%/margin rows) is ignored — this Engine's job is to compute ratios from raw
figures itself, never to trust a pre-computed number from the source.
"""

from __future__ import annotations

import httpx
from selectolax.parser import HTMLParser

from egxpm.persistence.db import YFINANCE_TICKERS
from egxpm.persistence.models import FinancialStatement, PeriodType
from egxpm.shared.exceptions import InsufficientDataError, ScraperSchemaChangedError

STOCKANALYSIS_SYMBOLS = {
    company_id: ticker.removesuffix(".CA") for company_id, ticker in YFINANCE_TICKERS.items()
}

_PAGE_SLUGS = {
    "income-statement": "",
    "balance-sheet": "balance-sheet/",
    "cash-flow-statement": "cash-flow-statement/",
}

_INCOME_FIELDS = {
    "Revenue": "revenue",
    "Net Interest Income": "net_interest_income",
    "Net Income": "net_income",
    "EPS (Basic)": "eps_basic",
    "EPS (Diluted)": "eps_diluted",
    "Operating Income": "operating_income",
}
_BALANCE_FIELDS = {
    "Total Assets": "total_assets",
    "Total Liabilities": "total_liabilities",
    "Shareholders' Equity": "total_equity",
}
_CASH_FLOW_FIELDS = {
    "Operating Cash Flow": "operating_cash_flow",
    "Capital Expenditures": "capex",
    "Free Cash Flow": "free_cash_flow",
}


def fetch_page(ticker: str, statement: str) -> str:
    """Thin wrapper around httpx, isolated so it can be monkeypatched in tests."""
    slug = _PAGE_SLUGS[statement]
    url = f"https://stockanalysis.com/quote/egx/{ticker}/financials/{slug}"
    response = httpx.get(
        url, params={"p": "quarterly"}, headers={"User-Agent": "Mozilla/5.0"},
        timeout=15, follow_redirects=True,
    )
    response.raise_for_status()
    return response.text


def _parse_number(raw: str) -> float | None:
    raw = raw.strip()
    if raw in ("", "-", "—", "N/A"):
        return None
    return float(raw.replace(",", ""))


def _parse_table(html: str, field_map: dict[str, str]) -> dict[str, dict[str, float | None]]:
    """Returns {period_end_iso: {field_name: value}}."""
    doc = HTMLParser(html)
    tables = doc.css("table")
    if not tables:
        raise ScraperSchemaChangedError("no financial table found on page")

    rows = tables[0].css("tr")
    if len(rows) < 2:
        raise ScraperSchemaChangedError("financial table has no data rows")

    header_cells = rows[0].css("th,td")
    period_ends = [cell.attributes.get("id") for cell in header_cells]
    if not any(pid and pid[:4].isdigit() for pid in period_ends[1:]):
        raise ScraperSchemaChangedError("could not find period_end ids in header row")

    by_period: dict[str, dict[str, float | None]] = {}
    for row in rows[1:]:
        cells = row.css("td,th")
        if not cells:
            continue
        field_name = field_map.get(cells[0].text(strip=True))
        if field_name is None:
            continue
        for period_end, cell in zip(period_ends[1:], cells[1:]):
            if not period_end:
                continue
            by_period.setdefault(period_end, {})[field_name] = _parse_number(cell.text(strip=True))

    # Not every field in field_map exists for every StatementSchema (e.g. banks
    # have no "Operating Income" row) — that's an expected schema difference,
    # not a broken scrape. Only raise if NONE of the whitelisted fields matched
    # anything, which means the site's row labels changed out from under us.
    found_fields = {name for period in by_period.values() for name in period}
    if not found_fields:
        raise ScraperSchemaChangedError(
            f"none of the expected fields were found on page: {sorted(field_map.values())}"
        )

    return by_period


def collect_fundamentals(
    company_id: str, collection_run_id: str, source_version: str = "1"
) -> list[FinancialStatement]:
    """Fetch quarterly financial statements for company_id via StockAnalysis.com.

    Raises:
        InsufficientDataError: no ticker mapping exists, or no reporting
            period appears in all three statements.
        ScraperSchemaChangedError: an expected table/field is missing
            (site layout changed).
        Exception: whatever fetch_page() raises (missing symbol, rate
            limit, timeout, ...) propagates unwrapped — CollectorService,
            not this Collector, decides transient vs. structural.
    """
    ticker = STOCKANALYSIS_SYMBOLS.get(company_id)
    if ticker is None:
        raise InsufficientDataError(f"no StockAnalysis.com symbol mapping for company_id={company_id!r}")

    income = _parse_table(fetch_page(ticker, "income-statement"), _INCOME_FIELDS)
    balance = _parse_table(fetch_page(ticker, "balance-sheet"), _BALANCE_FIELDS)
    cash_flow = _parse_table(fetch_page(ticker, "cash-flow-statement"), _CASH_FLOW_FIELDS)

    period_ends = set(income) & set(balance) & set(cash_flow)
    if not period_ends:
        raise InsufficientDataError(f"no overlapping reporting periods found for ticker={ticker!r}")

    statements = []
    for period_end in sorted(period_ends):
        merged = {**income[period_end], **balance[period_end], **cash_flow[period_end]}
        statements.append(
            FinancialStatement(
                company_id=company_id,
                period_type=PeriodType.QUARTERLY,
                period_end=period_end,
                revenue=merged.get("revenue"),
                net_income=merged.get("net_income"),
                eps_basic=merged.get("eps_basic"),
                eps_diluted=merged.get("eps_diluted"),
                total_assets=merged.get("total_assets"),
                total_liabilities=merged.get("total_liabilities"),
                total_equity=merged.get("total_equity"),
                operating_income=merged.get("operating_income"),
                operating_cash_flow=merged.get("operating_cash_flow"),
                capex=merged.get("capex"),
                free_cash_flow=merged.get("free_cash_flow"),
                net_interest_income=merged.get("net_interest_income"),
                data_source_id="stockanalysis",
                source_version=source_version,
                collection_run_id=collection_run_id,
            )
        )
    return statements
