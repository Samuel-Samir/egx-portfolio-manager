"""Connection management, schema creation, and seed data.

This is the only module in the codebase allowed to import sqlite3 and
issue raw SQL DDL. All other persistence code goes through the
Repository classes.
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

SCHEMA_SQL = """
-- ============================================================
-- COMPANY AGGREGATE
-- ============================================================
CREATE TABLE IF NOT EXISTS companies (
    company_id        TEXT PRIMARY KEY,
    name              TEXT NOT NULL,
    sector            TEXT NOT NULL,
    industry          TEXT,
    isin              TEXT,
    listing_status    TEXT NOT NULL DEFAULT 'active',
    statement_schema  TEXT NOT NULL DEFAULT 'INDUSTRIAL',
    rollout_phase     TEXT NOT NULL DEFAULT 'phase1',
    created_at        TEXT NOT NULL,
    updated_at        TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS company_sector_history (
    history_id      TEXT PRIMARY KEY,
    company_id      TEXT NOT NULL REFERENCES companies(company_id),
    sector          TEXT NOT NULL,
    effective_from  TEXT NOT NULL,
    effective_to    TEXT,
    created_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS watchlist_history (
    history_id        TEXT PRIMARY KEY,
    company_id        TEXT NOT NULL REFERENCES companies(company_id),
    state             TEXT NOT NULL,
    state_changed_at  TEXT NOT NULL,
    transition_type   TEXT NOT NULL,
    reference_type    TEXT,
    reference_id      TEXT,
    created_at        TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS holdings (
    holding_id    TEXT PRIMARY KEY,
    company_id    TEXT NOT NULL REFERENCES companies(company_id),
    category      TEXT NOT NULL,
    quantity      REAL NOT NULL,
    average_cost  REAL NOT NULL,
    acquired_at   TEXT NOT NULL,
    updated_at    TEXT NOT NULL
);

-- ============================================================
-- DATA SOURCES
-- ============================================================
CREATE TABLE IF NOT EXISTS data_sources (
    data_source_id      TEXT PRIMARY KEY,
    name                TEXT NOT NULL,
    source_type         TEXT NOT NULL,
    collection_method   TEXT NOT NULL,
    source_quality      TEXT NOT NULL,
    is_canonical_for    TEXT,
    created_at          TEXT NOT NULL,
    updated_at          TEXT NOT NULL
);

-- ============================================================
-- COLLECTED FACTS (all carry provenance columns)
-- ============================================================
CREATE TABLE IF NOT EXISTS financial_statements (
    statement_id        TEXT PRIMARY KEY,
    company_id          TEXT NOT NULL REFERENCES companies(company_id),
    period_type         TEXT NOT NULL,
    period_end          TEXT NOT NULL,
    revenue             REAL,
    net_income          REAL,
    eps_basic           REAL,
    eps_diluted         REAL,
    total_assets        REAL,
    total_liabilities   REAL,
    total_equity        REAL,
    operating_income    REAL,
    operating_cash_flow REAL,
    capex               REAL,
    free_cash_flow      REAL,
    net_interest_income REAL,
    data_source_id      TEXT NOT NULL REFERENCES data_sources(data_source_id),
    source_version      TEXT NOT NULL,
    fetched_at          TEXT NOT NULL,
    collection_run_id   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS price_candles (
    candle_id                     TEXT PRIMARY KEY,
    company_id                    TEXT NOT NULL REFERENCES companies(company_id),
    timeframe                     TEXT NOT NULL DEFAULT 'daily',
    candle_date                   TEXT NOT NULL,
    open                          REAL,
    high                          REAL,
    low                           REAL,
    close                         REAL,
    volume                        REAL,
    adjusted_for_corporate_action INTEGER NOT NULL DEFAULT 0,
    data_source_id                TEXT NOT NULL REFERENCES data_sources(data_source_id),
    source_version                TEXT NOT NULL,
    fetched_at                    TEXT NOT NULL,
    collection_run_id             TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS corporate_actions (
    action_id       TEXT PRIMARY KEY,
    company_id      TEXT NOT NULL REFERENCES companies(company_id),
    action_type     TEXT NOT NULL,
    action_date     TEXT NOT NULL,
    details         TEXT NOT NULL,
    data_source_id  TEXT NOT NULL REFERENCES data_sources(data_source_id),
    entered_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS news_items (
    news_id           TEXT PRIMARY KEY,
    company_id        TEXT REFERENCES companies(company_id),
    sector_scope      TEXT,
    headline          TEXT NOT NULL,
    publisher_name    TEXT NOT NULL,
    published_at      TEXT NOT NULL,
    url               TEXT,
    sentiment_score   REAL,
    relevance_score   REAL,
    data_source_id    TEXT NOT NULL REFERENCES data_sources(data_source_id),
    source_version    TEXT NOT NULL,
    fetched_at        TEXT NOT NULL,
    collection_run_id TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS technical_reference_snapshots (
    ref_id            TEXT PRIMARY KEY,
    company_id        TEXT NOT NULL REFERENCES companies(company_id),
    rating            TEXT NOT NULL,
    raw_indicators    TEXT NOT NULL,
    data_source_id    TEXT NOT NULL REFERENCES data_sources(data_source_id),
    fetched_at        TEXT NOT NULL,
    collection_run_id TEXT NOT NULL
);

-- ============================================================
-- ENGINE OUTPUTS (Checkpoint A artifacts)
-- ============================================================
CREATE TABLE IF NOT EXISTS technical_snapshots (
    snapshot_id          TEXT PRIMARY KEY,
    company_id           TEXT NOT NULL REFERENCES companies(company_id),
    computed_at          TEXT NOT NULL,
    rsi                  REAL,
    macd                 REAL,
    macd_signal          REAL,
    sma_20               REAL,
    sma_50               REAL,
    sma_200              REAL,
    ema_20               REAL,
    ema_50               REAL,
    atr                  REAL,
    bollinger_upper      REAL,
    bollinger_lower      REAL,
    bollinger_bandwidth  REAL,
    volume_ma_20         REAL,
    support_level        REAL,
    resistance_level     REAL,
    trend                TEXT,
    breakout             INTEGER,
    unusual_volume       INTEGER,
    engine_version       TEXT NOT NULL,
    timeframe            TEXT NOT NULL DEFAULT 'daily',
    window_size          INTEGER NOT NULL DEFAULT 200,
    computed_through_date TEXT NOT NULL,
    job_id               TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS scores (
    score_id              TEXT PRIMARY KEY,
    company_id            TEXT NOT NULL REFERENCES companies(company_id),
    computed_at           TEXT NOT NULL,
    financial_score       REAL,
    financial_breakdown   TEXT NOT NULL DEFAULT '{}',
    technical_score       REAL,
    technical_breakdown   TEXT NOT NULL DEFAULT '{}',
    news_score            REAL,
    news_breakdown        TEXT NOT NULL DEFAULT '{}',
    composite_score       REAL,
    config_snapshot_id    TEXT NOT NULL,
    job_id                TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS risk_scores (
    risk_score_id               TEXT PRIMARY KEY,
    score_id                    TEXT NOT NULL REFERENCES scores(score_id),
    value                       REAL NOT NULL,
    debt_peer_component         REAL,
    score_volatility_component  REAL,
    data_completeness_component REAL,
    liquidity_component         REAL,
    breakdown                   TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS confidence_scores (
    confidence_id                    TEXT PRIMARY KEY,
    score_id                         TEXT NOT NULL REFERENCES scores(score_id),
    confidence_value                 REAL NOT NULL,
    freshness_component              REAL,
    source_quality_component         REAL,
    source_health_component          REAL,
    historical_accuracy_component    REAL,
    breakdown                        TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS sector_summaries (
    summary_id               TEXT PRIMARY KEY,
    sector                   TEXT NOT NULL,
    computed_at              TEXT NOT NULL,
    summary_score            REAL NOT NULL,
    component_company_scores TEXT NOT NULL DEFAULT '[]',
    job_id                   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS market_summaries (
    summary_id                   TEXT PRIMARY KEY,
    computed_at                  TEXT NOT NULL,
    summary_score                REAL NOT NULL,
    component_sector_summaries   TEXT NOT NULL DEFAULT '[]',
    job_id                       TEXT NOT NULL
);

-- ============================================================
-- CONFIGURATION
-- ============================================================
CREATE TABLE IF NOT EXISTS configuration_snapshots (
    config_snapshot_id  TEXT PRIMARY KEY,
    created_at          TEXT NOT NULL,
    scoring_weights     TEXT NOT NULL DEFAULT '{}',
    risk_settings       TEXT NOT NULL DEFAULT '{}',
    allocation_targets  TEXT NOT NULL DEFAULT '{}',
    notes               TEXT
);

-- ============================================================
-- PORTFOLIO AGGREGATE
-- ============================================================
CREATE TABLE IF NOT EXISTS portfolio_snapshots (
    snapshot_id          TEXT PRIMARY KEY,
    captured_at          TEXT NOT NULL,
    holdings_snapshot    TEXT NOT NULL DEFAULT '[]',
    cash                 REAL NOT NULL DEFAULT 0,
    computed_allocation  TEXT NOT NULL DEFAULT '{}',
    origin               TEXT NOT NULL
);

-- ============================================================
-- RECOMMENDATION AGGREGATE
-- ============================================================
CREATE TABLE IF NOT EXISTS recommendations (
    recommendation_id     TEXT PRIMARY KEY,
    company_id            TEXT NOT NULL REFERENCES companies(company_id),
    created_at            TEXT NOT NULL,
    action                TEXT NOT NULL,
    entry_price           REAL,
    stop_loss             REAL,
    take_profit           REAL,
    position_size         REAL,
    confidence_id         TEXT NOT NULL REFERENCES confidence_scores(confidence_id),
    config_snapshot_id    TEXT NOT NULL REFERENCES configuration_snapshots(config_snapshot_id),
    portfolio_snapshot_id TEXT NOT NULL REFERENCES portfolio_snapshots(snapshot_id),
    frozen_package        TEXT NOT NULL DEFAULT '{}',
    job_id                TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS recommendation_supersessions (
    supersession_id           TEXT PRIMARY KEY,
    recommendation_id         TEXT NOT NULL REFERENCES recommendations(recommendation_id),
    superseded_at             TEXT NOT NULL,
    superseding_event_type    TEXT NOT NULL,
    superseding_reference_id  TEXT
);

CREATE TABLE IF NOT EXISTS executions (
    execution_id        TEXT PRIMARY KEY,
    recommendation_id   TEXT REFERENCES recommendations(recommendation_id),
    executed_at         TEXT NOT NULL,
    action_taken        TEXT NOT NULL,
    details             TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS outcomes (
    outcome_id               TEXT PRIMARY KEY,
    recommendation_id        TEXT NOT NULL REFERENCES recommendations(recommendation_id),
    execution_id             TEXT REFERENCES executions(execution_id),
    recorded_at              TEXT NOT NULL,
    actual_return            REAL,
    actual_loss              REAL,
    holding_period_days      INTEGER,
    target_hit               INTEGER,
    stop_hit                 INTEGER,
    quality_classification   TEXT,
    is_final                 INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS user_feedback (
    feedback_id         TEXT PRIMARY KEY,
    recommendation_id   TEXT NOT NULL REFERENCES recommendations(recommendation_id),
    execution_id        TEXT REFERENCES executions(execution_id),
    outcome_id          TEXT REFERENCES outcomes(outcome_id),
    recorded_at         TEXT NOT NULL,
    feedback_text       TEXT NOT NULL,
    agreement           TEXT
);

-- ============================================================
-- OPERATIONAL
-- ============================================================
CREATE TABLE IF NOT EXISTS jobs (
    job_id               TEXT PRIMARY KEY,
    job_type             TEXT NOT NULL,
    started_at           TEXT NOT NULL,
    completed_at         TEXT,
    status               TEXT NOT NULL DEFAULT 'running',
    companies_processed  INTEGER DEFAULT 0,
    companies_failed     INTEGER DEFAULT 0,
    error_summary        TEXT
);

CREATE TABLE IF NOT EXISTS collection_runs (
    collection_run_id   TEXT PRIMARY KEY,
    job_id              TEXT REFERENCES jobs(job_id),
    data_source_id      TEXT NOT NULL REFERENCES data_sources(data_source_id),
    company_id          TEXT REFERENCES companies(company_id),
    started_at          TEXT NOT NULL,
    completed_at        TEXT,
    status              TEXT NOT NULL DEFAULT 'running',
    records_collected   INTEGER DEFAULT 0,
    error_message       TEXT
);

-- ============================================================
-- COPILOT
-- ============================================================
CREATE TABLE IF NOT EXISTS conversations (
    conversation_id TEXT PRIMARY KEY,
    started_at      TEXT NOT NULL,
    last_active_at  TEXT NOT NULL,
    transcript      TEXT NOT NULL DEFAULT '[]'
);

CREATE TABLE IF NOT EXISTS analysis_sessions (
    session_id                      TEXT PRIMARY KEY,
    conversation_id                 TEXT REFERENCES conversations(conversation_id),
    created_at                      TEXT NOT NULL,
    state                           TEXT NOT NULL DEFAULT '{}',
    promoted_to_recommendation_id   TEXT REFERENCES recommendations(recommendation_id)
);

-- ============================================================
-- INDEXES
-- ============================================================
CREATE INDEX IF NOT EXISTS idx_price_candles_company_date
    ON price_candles(company_id, candle_date);
CREATE INDEX IF NOT EXISTS idx_scores_company_time
    ON scores(company_id, computed_at);
CREATE INDEX IF NOT EXISTS idx_financial_statements_company_period
    ON financial_statements(company_id, period_end);
CREATE INDEX IF NOT EXISTS idx_watchlist_company_changed
    ON watchlist_history(company_id, state_changed_at DESC);
CREATE INDEX IF NOT EXISTS idx_recommendations_company_time
    ON recommendations(company_id, created_at);
CREATE INDEX IF NOT EXISTS idx_collection_runs_source_time
    ON collection_runs(data_source_id, started_at DESC);
CREATE INDEX IF NOT EXISTS idx_jobs_type_time
    ON jobs(job_type, started_at DESC);
CREATE INDEX IF NOT EXISTS idx_portfolio_snapshots_time
    ON portfolio_snapshots(captured_at DESC);
"""

DATA_SOURCES = [
    {"data_source_id": "yfinance", "name": "Yahoo Finance", "source_type": "price", "collection_method": "api", "source_quality": "scraped", "is_canonical_for": '["prices"]'},
    {"data_source_id": "pandas_ta_classic", "name": "pandas-ta-classic", "source_type": "technical", "collection_method": "internal", "source_quality": "internal", "is_canonical_for": '["technicals"]'},
    {"data_source_id": "tradingview_ta", "name": "tradingview-ta", "source_type": "technical", "collection_method": "api", "source_quality": "scraped", "is_canonical_for": None},
    {"data_source_id": "stockanalysis", "name": "StockAnalysis.com", "source_type": "fundamental", "collection_method": "scraping", "source_quality": "scraped", "is_canonical_for": '["fundamentals"]'},
    {"data_source_id": "mubasher", "name": "Mubasher Info", "source_type": "news", "collection_method": "scraping", "source_quality": "scraped", "is_canonical_for": '["news"]'},
    {"data_source_id": "egx_official", "name": "EGX Official", "source_type": "news", "collection_method": "manual", "source_quality": "official", "is_canonical_for": None},
    {"data_source_id": "manual", "name": "Manual Entry", "source_type": "corporate", "collection_method": "manual", "source_quality": "manual", "is_canonical_for": '["corporate_actions"]'},
]

PHASE1_COMPANIES = [
    # Current Holdings
    {"company_id": "ADA", "name": "ADA Gold Fund", "sector": "Funds", "statement_schema": "INDUSTRIAL", "rollout_phase": "phase1", "listing_status": "active"},
    {"company_id": "BMM", "name": "Beltone Meya Meya Fund", "sector": "Funds", "statement_schema": "INDUSTRIAL", "rollout_phase": "phase1", "listing_status": "active"},
    {"company_id": "CLOUD", "name": "Cloud Invest Fund", "sector": "Funds", "statement_schema": "INDUSTRIAL", "rollout_phase": "phase1", "listing_status": "active"},
    {"company_id": "PALM", "name": "Palm Hills Developments", "sector": "Real Estate", "statement_schema": "INDUSTRIAL", "rollout_phase": "phase1", "listing_status": "active"},
    {"company_id": "NARE", "name": "North Africa Real Estate", "sector": "Real Estate", "statement_schema": "INDUSTRIAL", "rollout_phase": "phase1", "listing_status": "active"},
    {"company_id": "ABR", "name": "Abrar Leasing", "sector": "Financial", "statement_schema": "BANK", "rollout_phase": "phase1", "listing_status": "active"},
    # Watchlist Candidates
    {"company_id": "COMI", "name": "Commercial International Bank (CIB)", "sector": "Banking", "statement_schema": "BANK", "rollout_phase": "phase1", "listing_status": "active"},
    {"company_id": "TMGH", "name": "Talaat Moustafa Group", "sector": "Real Estate", "statement_schema": "INDUSTRIAL", "rollout_phase": "phase1", "listing_status": "active"},
    {"company_id": "SWDY", "name": "Elsewedy Electric", "sector": "Industrial", "statement_schema": "INDUSTRIAL", "rollout_phase": "phase1", "listing_status": "active"},
    {"company_id": "EFGD", "name": "EFG Holding", "sector": "Banking", "statement_schema": "BANK", "rollout_phase": "phase1", "listing_status": "active"},
    {"company_id": "ABUK", "name": "Abu Qir Fertilizers", "sector": "Fertilizers", "statement_schema": "INDUSTRIAL", "rollout_phase": "phase1", "listing_status": "active"},
    {"company_id": "EFIH", "name": "eFinance", "sector": "Technology", "statement_schema": "INDUSTRIAL", "rollout_phase": "phase1", "listing_status": "active"},
]

YFINANCE_TICKERS = {
    "ADA": "ADA.CA", "BMM": "BMM.CA", "CLOUD": "CLOUD.CA",
    "PALM": "PHDC.CA", "NARE": "NARE.CA", "ABR": "ABR.CA",
    "COMI": "COMI.CA", "TMGH": "TMGH.CA", "SWDY": "SWDY.CA",
    "EFGD": "EFGD.CA", "ABUK": "ABUK.CA", "EFIH": "EFIH.CA",
}


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_connection(db_path: str | Path) -> sqlite3.Connection:
    """Open a SQLite connection with the required PRAGMAs set."""
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


@contextmanager
def connect(db_path: str | Path) -> Iterator[sqlite3.Connection]:
    """Context manager yielding a connection; commits on success, rolls back on error."""
    conn = get_connection(db_path)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def create_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA_SQL)


def seed_data_sources(conn: sqlite3.Connection) -> None:
    now = _utcnow()
    for ds in DATA_SOURCES:
        conn.execute(
            """
            INSERT INTO data_sources
                (data_source_id, name, source_type, collection_method,
                 source_quality, is_canonical_for, created_at, updated_at)
            VALUES (:data_source_id, :name, :source_type, :collection_method,
                    :source_quality, :is_canonical_for, :created_at, :updated_at)
            ON CONFLICT(data_source_id) DO NOTHING
            """,
            {**ds, "created_at": now, "updated_at": now},
        )


def seed_phase1_companies(conn: sqlite3.Connection) -> None:
    now = _utcnow()
    for company in PHASE1_COMPANIES:
        conn.execute(
            """
            INSERT INTO companies
                (company_id, name, sector, industry, isin, listing_status,
                 statement_schema, rollout_phase, created_at, updated_at)
            VALUES (:company_id, :name, :sector, :industry, :isin, :listing_status,
                    :statement_schema, :rollout_phase, :created_at, :updated_at)
            ON CONFLICT(company_id) DO NOTHING
            """,
            {
                **company,
                "industry": company.get("industry"),
                "isin": company.get("isin"),
                "created_at": now,
                "updated_at": now,
            },
        )
        conn.execute(
            """
            INSERT INTO company_sector_history
                (history_id, company_id, sector, effective_from, effective_to, created_at)
            SELECT :history_id, :company_id, :sector, :effective_from, NULL, :created_at
            WHERE NOT EXISTS (
                SELECT 1 FROM company_sector_history WHERE company_id = :company_id
            )
            """,
            {
                "history_id": f"{company['company_id']}-sector-seed",
                "company_id": company["company_id"],
                "sector": company["sector"],
                "effective_from": now,
                "created_at": now,
            },
        )


def init_db(db_path: str | Path) -> None:
    """Create schema and seed reference data. Idempotent."""
    with connect(db_path) as conn:
        create_schema(conn)
        seed_data_sources(conn)
        seed_phase1_companies(conn)
