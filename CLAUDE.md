# EGX Investment Operating System — Claude Code Master Instructions

## CRITICAL: How to Start Every Session
1. Read this file completely
2. Read `docs/progress.md` to see what is done and what is next
3. Continue from the first unchecked item in the current milestone
4. Never redo completed work
5. Never skip ahead to a future milestone

## CRITICAL: How to End Every Task
1. Run tests: `python -m pytest tests/ -v`
2. Fix any failures before moving on
3. Update `docs/progress.md` — check the completed box
4. Commit: `git add -A && git commit -m "M{N}: {description of what was done}"`
5. Move to the next unchecked item

---

## Project Overview

**What this is:** A personal AI-powered Portfolio Manager for the Egyptian Stock Exchange (EGX).
- NOT a SaaS product
- NOT a trading bot
- Single user only
- Runs locally
- Decision-support system — the AI never makes decisions, only assists

**The user:** A full-time software engineer who invests on EGX via the Thndr app. Cannot monitor markets all day. Wants disciplined, data-driven decisions.

**The goal:** Build a system that:
- Scores EGX companies using deterministic financial + technical + news analysis
- Generates explainable investment recommendations
- Tracks portfolio allocation vs targets
- Finds swing trading opportunities
- Accumulates a historical knowledge base that grows over time

---

## Architecture Principles (NEVER VIOLATE THESE)

1. **Engines are PURE functions** — no I/O, no DB access, no sqlite3 imports. Accept domain objects, return domain objects.
2. **LLM never calculates** — Python computes everything. LLM only interprets, explains, and recommends based on pre-computed numbers.
3. **Dashboard never calls Engines** — reads only precomputed data from Persistence.
4. **Collectors never call each other** — each owns exactly one data source.
5. **Jobs are thin orchestrators** — sequence calls to Engines and Repositories, contain zero business logic.
6. **All writes go through Repository layer** — nothing else writes to SQLite directly.
7. **History is append-only** — nothing is ever deleted or overwritten. Corrections are new records.
8. **Every Engine function must have unit tests** — deterministic = testable.
9. **State-changing actions require explicit user approval** — Generate Plan → User Review → Approval → Execute → Audit Log.
10. **One canonical implementation per business rule** — no duplicated logic.

---

## Project Structure

```
egx-portfolio-manager/
├── CLAUDE.md                          ← this file
├── pyproject.toml
├── config.yaml
├── .env                               ← ANTHROPIC_API_KEY (never commit)
├── .gitignore
├── docs/
│   ├── EGX_Investment_OS_Architecture_v1.0.docx
│   └── progress.md
├── data/
│   └── egx.db                         ← SQLite database
├── reports/                           ← dated Markdown reports from Jobs
├── egxpm/
│   ├── __init__.py
│   ├── shared/
│   │   ├── __init__.py
│   │   └── allocation_calculator.py   ← pure function, no layer affiliation
│   ├── collectors/
│   │   ├── __init__.py
│   │   ├── collector_service.py       ← rate limiting, retry logic
│   │   ├── price_collector.py         ← yfinance
│   │   ├── technical_reference_collector.py  ← tradingview-ta
│   │   ├── fundamentals_collector.py  ← StockAnalysis.com scraper
│   │   ├── news_collector.py          ← Mubasher + EGX disclosures
│   │   └── corporate_actions_collector.py    ← manual entry
│   ├── engine/
│   │   ├── __init__.py
│   │   ├── financial_engine.py
│   │   ├── technical_engine.py
│   │   ├── news_engine.py
│   │   ├── scoring_engine.py
│   │   ├── risk_engine.py
│   │   ├── confidence_engine.py
│   │   ├── portfolio_engine.py
│   │   └── position_sizing_engine.py
│   ├── persistence/
│   │   ├── __init__.py
│   │   ├── db.py                      ← connection, WAL, migrations
│   │   ├── models.py                  ← all Pydantic domain objects
│   │   ├── company_repository.py
│   │   ├── portfolio_repository.py
│   │   ├── recommendation_repository.py
│   │   ├── conversation_repository.py
│   │   ├── operational_repository.py
│   │   ├── sector_market_repository.py
│   │   └── dashboard_read_repository.py
│   ├── llm/
│   │   ├── __init__.py
│   │   ├── client.py                  ← Anthropic API wrapper
│   │   ├── context_aggregator.py      ← pure, builds CuratedContext
│   │   └── prompts.py                 ← PromptRegistry
│   ├── copilot/
│   │   ├── __init__.py
│   │   ├── session.py                 ← AnalysisSession + conversation loop
│   │   └── tool_registry.py           ← 15 tools with safety tiers
│   ├── run_collection.py              ← CLI entry point
│   ├── run_swing.py                   ← CLI entry point
│   ├── run_longterm.py                ← CLI entry point
│   └── run_review.py                  ← CLI entry point
├── app.py                             ← Streamlit dashboard
└── tests/
    ├── __init__.py
    ├── fixtures/                      ← test data files
    ├── test_models.py
    ├── test_financial_engine.py
    ├── test_technical_engine.py
    ├── test_news_engine.py
    ├── test_scoring_engine.py
    ├── test_risk_engine.py
    ├── test_confidence_engine.py
    ├── test_portfolio_engine.py
    ├── test_position_sizing_engine.py
    ├── test_allocation_calculator.py
    └── test_repositories.py
```

---

## pyproject.toml Content

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "egxpm"
version = "0.1.0"
description = "EGX Investment Operating System"
requires-python = ">=3.12"
dependencies = [
    "pandas>=2.2.0",
    "pandas-ta-classic>=0.0.5",
    "yfinance>=0.2.40",
    "tradingview-ta>=3.3.0",
    "anthropic>=0.40.0",
    "pydantic>=2.8.0",
    "streamlit>=1.40.0",
    "httpx>=0.27.0",
    "selectolax>=0.3.21",
    "python-dotenv>=1.0.0",
    "plotly>=5.24.0",
    "pytest>=8.3.0",
    "pytest-cov>=5.0.0",
]

[tool.pytest.ini_options]
testpaths = ["tests"]
python_files = ["test_*.py"]
python_classes = ["Test*"]
python_functions = ["test_*"]
```

---

## config.yaml Content

```yaml
# Database
db_path: "data/egx.db"

# Portfolio Target Allocation
allocation_targets:
  bmm_index: 0.25        # BMM equity index fund
  long_term_stocks: 0.40  # individual long-term picks
  swing_trading: 0.20     # swing capital
  cloud_cash: 0.10        # liquidity / cash management
  gold: 0.05              # diversification only

# Per-stock and sector constraints
max_per_stock_pct: 0.15
max_per_sector_pct: 0.35

# Scoring weights (must sum to 1.0)
longterm_weights:
  financial: 0.45
  technical: 0.25
  news: 0.20
  risk: 0.10

swing_weights:
  financial: 0.20
  technical: 0.50
  news: 0.20
  risk: 0.10

# Scoring null-handling policy
null_handling_policy: "exclude_and_renormalize"  # or "treat_as_zero"

# Swing candidate filter
swing_min_score_threshold: 55
longterm_min_score_threshold: 60

# Risk settings
risk_per_trade_pct: 0.01    # 1% of portfolio per trade
max_position_pct: 0.15      # max 15% in one position
max_portfolio_heat_pct: 0.06 # max 6% total open risk
atr_multiplier: 1.5
risk_reward_ratio: 2.0
unusual_volume_threshold: 1.5

# Recommendation validity
swing_validity_days: 1
longterm_validity_until_next_run: true

# Data freshness thresholds (days)
freshness_thresholds:
  prices: 2
  technicals: 2
  fundamentals: 92  # 1 quarter
  news: 1

# LLM settings
swing_model: "claude-haiku-4-5"
longterm_model: "claude-sonnet-4-6"
copilot_model: "claude-sonnet-4-6"
max_tokens: 1000

# Copilot limits
copilot_max_tool_rounds: 5
copilot_max_tool_calls: 15
session_ttl_hours: 24
conversation_retention_days: 30
plan_expiry_hours: 24

# Dashboard
dashboard_cache_ttl_seconds: 300

# Collector rate limiting
stockanalysis_min_delay_seconds: 2.0
mubasher_min_delay_seconds: 1.5
collector_max_retries: 3

# Source health
source_health_window_days: 30
source_health_cache_ttl_seconds: 3600

# Portfolio review
review_top_n_candidates: 10
```

---

## Complete SQLite Schema

### ALL tables must be created at Milestone 0. No exceptions.

```sql
-- ============================================================
-- PRAGMA settings (set on every connection)
-- ============================================================
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;
PRAGMA busy_timeout=5000;

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

-- Amendment 1: sector history (never overwrite sector)
CREATE TABLE IF NOT EXISTS company_sector_history (
    history_id      TEXT PRIMARY KEY,
    company_id      TEXT NOT NULL REFERENCES companies(company_id),
    sector          TEXT NOT NULL,
    effective_from  TEXT NOT NULL,
    effective_to    TEXT,
    created_at      TEXT NOT NULL
);

-- Watchlist lifecycle (append-only — current state = most recent row)
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

-- Amendment 2: supersession tracking
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
```

---

## Phase 1 Seed Data

### Data Sources (seed at M0)
```python
DATA_SOURCES = [
    {"data_source_id": "yfinance",         "name": "Yahoo Finance",       "source_type": "price",        "collection_method": "api",        "source_quality": "scraped",  "is_canonical_for": '["prices"]'},
    {"data_source_id": "pandas_ta_classic","name": "pandas-ta-classic",   "source_type": "technical",    "collection_method": "internal",   "source_quality": "internal", "is_canonical_for": '["technicals"]'},
    {"data_source_id": "tradingview_ta",   "name": "tradingview-ta",      "source_type": "technical",    "collection_method": "api",        "source_quality": "scraped",  "is_canonical_for": "null"},
    {"data_source_id": "stockanalysis",    "name": "StockAnalysis.com",   "source_type": "fundamental",  "collection_method": "scraping",   "source_quality": "scraped",  "is_canonical_for": '["fundamentals"]'},
    {"data_source_id": "mubasher",         "name": "Mubasher Info",       "source_type": "news",         "collection_method": "scraping",   "source_quality": "scraped",  "is_canonical_for": '["news"]'},
    {"data_source_id": "egx_official",    "name": "EGX Official",        "source_type": "news",         "collection_method": "manual",     "source_quality": "official", "is_canonical_for": "null"},
    {"data_source_id": "manual",           "name": "Manual Entry",        "source_type": "corporate",    "collection_method": "manual",     "source_quality": "manual",   "is_canonical_for": '["corporate_actions"]'},
]
```

### Phase 1 Companies (seed at M0)
```python
PHASE1_COMPANIES = [
    # Current Holdings
    {"company_id": "ADA",   "name": "ADA Gold Fund",              "sector": "Funds",          "statement_schema": "INDUSTRIAL", "rollout_phase": "phase1", "listing_status": "active"},
    {"company_id": "BMM",   "name": "Beltone Meya Meya Fund",     "sector": "Funds",          "statement_schema": "INDUSTRIAL", "rollout_phase": "phase1", "listing_status": "active"},
    {"company_id": "CLOUD", "name": "Cloud Invest Fund",          "sector": "Funds",          "statement_schema": "INDUSTRIAL", "rollout_phase": "phase1", "listing_status": "active"},
    {"company_id": "PALM",  "name": "Palm Hills Developments",    "sector": "Real Estate",    "statement_schema": "INDUSTRIAL", "rollout_phase": "phase1", "listing_status": "active"},
    {"company_id": "NARE",  "name": "North Africa Real Estate",   "sector": "Real Estate",    "statement_schema": "INDUSTRIAL", "rollout_phase": "phase1", "listing_status": "active"},
    {"company_id": "ABR",   "name": "Abrar Leasing",              "sector": "Financial",      "statement_schema": "BANK",       "rollout_phase": "phase1", "listing_status": "active"},
    # Watchlist Candidates
    {"company_id": "COMI",  "name": "Commercial International Bank (CIB)", "sector": "Banking",      "statement_schema": "BANK",       "rollout_phase": "phase1", "listing_status": "active"},
    {"company_id": "TMGH",  "name": "Talaat Moustafa Group",      "sector": "Real Estate",    "statement_schema": "INDUSTRIAL", "rollout_phase": "phase1", "listing_status": "active"},
    {"company_id": "SWDY",  "name": "Elsewedy Electric",          "sector": "Industrial",     "statement_schema": "INDUSTRIAL", "rollout_phase": "phase1", "listing_status": "active"},
    {"company_id": "EFGD",  "name": "EFG Holding",                "sector": "Banking",        "statement_schema": "BANK",       "rollout_phase": "phase1", "listing_status": "active"},
    {"company_id": "ABUK",  "name": "Abu Qir Fertilizers",        "sector": "Fertilizers",    "statement_schema": "INDUSTRIAL", "rollout_phase": "phase1", "listing_status": "active"},
    {"company_id": "EFIH",  "name": "eFinance",                   "sector": "Technology",     "statement_schema": "INDUSTRIAL", "rollout_phase": "phase1", "listing_status": "active"},
]

# yfinance ticker mapping (.CA suffix for EGX)
YFINANCE_TICKERS = {
    "ADA": "ADA.CA", "BMM": "BMM.CA", "CLOUD": "CLOUD.CA",
    "PALM": "PHDC.CA", "NARE": "NARE.CA", "ABR": "ABR.CA",
    "COMI": "COMI.CA", "TMGH": "TMGH.CA", "SWDY": "SWDY.CA",
    "EFGD": "EFGD.CA", "ABUK": "ABUK.CA", "EFIH": "EFIH.CA",
}
```

---

## All Engine Contracts (Section 9)

### Financial Engine
```python
def calculate_financial_metrics(
    statements: List[FinancialStatement],
    statement_schema: StatementSchema
) -> FinancialMetrics:
    """
    Pure function. No I/O.
    Raises: InsufficientDataError if zero statements provided.
    Precondition (ValueError): statements must be from same company.
    Returns null fields (not zero) when data is insufficient.
    StatementSchema.BANK: operating_margin = None with bank_schema_flag = True
    Requires >= 2 periods for growth rates. >= 4 periods for trend detection.
    """
```

### Technical Engine
```python
def calculate_technical_snapshot(
    candles: List[PriceCandle],
    window: int = 200
) -> TechnicalSnapshot:
    """
    Pure function. No I/O.
    Raises: InsufficientDataError if fewer candles than required.
    Precondition (ValueError): candles must be chronologically ordered,
        same company, same timeframe.
    Returns TechnicalSnapshot with:
        .indicators: TechnicalIndicators (raw values)
        .signals: TechnicalSignals (derived conclusions)
    Signal rules:
        trend = BULLISH if price > SMA_20 AND SMA_20 > SMA_50
        trend = BEARISH if price < SMA_20 AND SMA_20 < SMA_50
        trend = NEUTRAL otherwise
        breakout = True if price > resistance_level AND unusual_volume
        unusual_volume = True if volume > volume_ma_20 * config.unusual_volume_threshold
    """
```

### Scoring Engine
```python
def calculate_score(
    financial_metrics: FinancialMetrics,
    technical_snapshot: TechnicalSnapshot,
    scored_news: List[NewsItem],
    weights: ConfigurationSnapshot
) -> Score:
    """
    Pure function. No I/O.
    Raises: InvalidWeightsError if weights don't sum to 1.0.
    Returns Score with composite_score = None (populated at Stage 6c).
    Breakdown JSON format:
        {"revenue_growth": {"value": 18.4, "points": 15, "max": 20}, ...}
    Null metrics handled per weights.null_handling_policy:
        "exclude_and_renormalize": exclude + renormalize remaining
        "treat_as_zero": score 0 for null
    """
```

### Risk Engine
```python
def calculate_risk_score(
    score: Score,
    peer_summary: SectorPeerSummary,
    historical_score_summary: HistoricalScoreSummary,
    liquidity_summary: LiquiditySummary,
    config: ConfigurationSnapshot
) -> RiskScore:
    """
    Pure function. No I/O.
    Raises: none (missing inputs degrade toward conservative mid-range).
    Called AFTER Stage 6a barrier — requires peer_summary from sector aggregation.
    Components:
        debt_peer_score: company D/E vs sector median D/E
        score_volatility: std_dev of last N scores normalized [0,1]
        data_completeness: % of scoring metrics that were non-null
        liquidity_risk: position_size_EGP / avg_daily_volume_EGP
    RiskScore.value = 100 - weighted_risk_penalty (higher = lower risk)
    """
```

### Confidence Engine
```python
def calculate_confidence(
    score: Score,
    freshness: FreshnessMetadata,
    source_quality: SourceQualitySummary,
    source_health: SourceHealthSummary,
    historical_accuracy: HistoricalAccuracySummary
) -> ConfidenceScore:
    """
    Pure function. No I/O.
    Raises: none.
    ALL inputs supplied by Orchestration — this engine NEVER queries Persistence.
    source_health comes from SourceHealthService (1-hour TTL cache) via Orchestration.
    historical_accuracy: if < 5 samples, use 0.5 (neutral) not raw win rate.
    Source quality weights: Official=1.0, Internal=1.0, Scraped=0.7, Manual=0.8
    """
```

### Portfolio Engine
```python
def calculate_allocation(
    holdings: List[Holding],
    config: ConfigurationSnapshot
) -> AllocationReport:
    """
    Pure function. Calls AllocationCalculator.calculate() internally.
    No I/O.
    """

def simulate(
    proposed_action: ProposedAction,
    current_holdings: List[Holding],
    config: ConfigurationSnapshot
) -> AllocationReport:
    """
    Pure function. Three lines: apply_action + AllocationCalculator.calculate().
    No I/O. Raises: InvalidActionError (e.g. selling more than held).
    """
```

### AllocationCalculator (shared/)
```python
def calculate(
    holdings: List[Holding],
    prices: Dict[str, float],
    cash: float,
    targets: ConfigurationSnapshot
) -> AllocationReport:
    """
    The ONE implementation of allocation arithmetic.
    Pure function in shared/ — importable by both Engine and Persistence layers.
    PortfolioEngine passes pre-loaded domain objects.
    DashboardReadRepository passes DB-read values.
    No arithmetic duplication anywhere else.
    """
```

### Position Sizing Engine
```python
def calculate_position_size(
    technical_snapshot: TechnicalSnapshot,
    risk_config: ConfigurationSnapshot,
    portfolio: AllocationReport
) -> PositionSizing:
    """
    Pure function. No I/O.
    Raises: InsufficientVolatilityDataError (ATR unavailable/zero)
            PortfolioHeatExceededError (portfolio heat limit exceeded)
    Formula:
        stop_distance = ATR * atr_multiplier (default 1.5)
        stop_loss = entry_price - stop_distance
        take_profit = entry_price + (stop_distance * risk_reward_ratio)
        position_size = (portfolio_total * risk_per_trade_pct) / stop_distance
        position_size = min(position_size, portfolio_total * max_position_pct / entry_price)
    """
```

---

## Canonical Pipeline (Section 6)

```
Stage 1:   Collection          → raw artifacts → Persistence
Stage 2:   Domain Object Load  → Persistence → domain objects
Stage 3:   Financial Engine    → FinancialMetrics
Stage 4:   Technical Engine    → TechnicalSnapshot
Stage 5:   News Processing     → scored NewsItems
           [Stages 3, 4, 5 are INDEPENDENT — any order or parallel]
Stage 6:   Scoring Engine      → Score (3-component, composite=None)
           ── Stage 6a: Sector/Market Aggregation ──────────────────
           [SYNCHRONIZATION BARRIER: ALL companies must complete
            Stage 6 before ANY company proceeds to Stage 6b]
Stage 6b:  Risk Engine         → RiskScore
Stage 6c:  Composite Assembly  → Score.composite_score populated
Stage 7:   Confidence Engine   → ConfidenceScore
           [Score, RiskScore, ConfidenceScore all in-memory here]
Stage 8:   Portfolio Engine    → AllocationReport
Stage 9:   Position Sizing     → PositionSizing [swing only]
Stage 10:  PortfolioSnapshot   → captured by Orchestration (before_recommendation)
           ── CHECKPOINT A (atomic transaction) ─────────────────────
           [Writes: TechnicalSnapshot, Score, RiskScore, ConfidenceScore,
            PositionSizing — ALL in ONE transaction]
Stage 11:  Context Aggregation → CuratedContext
Stage 12:  Reasoning (LLM)    → StructuredRecommendation
Stage 13:  Recommendation      → assembled by Orchestration
           ── CHECKPOINT B (atomic transaction) ─────────────────────
           [Writes: Recommendation + RecommendationSupersession]
```

---

## Business Rules Summary (Section 10)

**[INVARIANT] = never changes. [POLICY] = may evolve.**

- [INVARIANT] Engines are pure functions — no exceptions ever
- [INVARIANT] Recommendations are immutable once written — corrections are new rows
- [INVARIANT] Constraint violations are surfaced, never suppressed or auto-corrected
- [INVARIANT] quality_classification on Outcome is never auto-assigned by LLM
- [INVARIANT] A Company cannot become a Holding without first existing as a WatchlistEntry
- [INVARIANT] A Recommendation's confidence_id must be from the same pipeline run
- [INVARIANT] SectorSummary and MarketSummary are always derived, never edited
- [INVARIANT] Every state-changing Tool action follows: Plan → Review → Approve → Execute → Audit
- [POLICY] Gold and Cloud allocations are not auto-rebalanced
- [POLICY] Swing recommendations expire after 1 trading day (default)
- [POLICY] No Recommendation generated for stale Score without explicit flag

---

## Watchlist States (Section 11)

States: CANDIDATE → WATCHLIST → ARCHIVED
(PORTFOLIO and SOLD are removed — ownership is derived from holdings table, not stored as state)

Valid transitions:
- (none) → CANDIDATE: candidate_discovered
- CANDIDATE → WATCHLIST: user_added_to_watchlist
- CANDIDATE → ARCHIVED: candidate_rejected
- WATCHLIST → ARCHIVED: user_archived or delisting
- ARCHIVED → WATCHLIST: user_revived

Recommendations only generated for WATCHLIST companies.

---

## Swing Job Candidate Filter (CRITICAL — correct precedence)

```python
# CORRECT (both conditions required):
swing_candidates = [
    company for company in companies
    if (
        technical_snapshot.signals.breakout
        or technical_snapshot.signals.unusual_volume
        or technical_snapshot.signals.trend == TrendSignal.BULLISH
    )
    and composite_score >= config.swing_min_score_threshold
]

# WRONG (do NOT use — AND/OR precedence bug):
# if breakout OR unusual_volume OR trend == BULLISH AND score >= threshold
```

---

## Cron Schedule (Section 13)

```bash
# Daily collection (Sun–Thu, after EGX close at 14:30 Cairo time)
30 15 * * 0-4   python -m egxpm.run_collection --type price
30 15 * * 0-4   python -m egxpm.run_collection --type technical_reference
30 15 * * 0-4   python -m egxpm.run_collection --type news

# Daily Swing Job (30-min buffer after collection)
00 16 * * 0-4   python -m egxpm.run_swing

# Weekly Fundamentals (Friday — market closed)
00 09 * * 5     python -m egxpm.run_collection --type fundamentals

# Weekly Long-Term Job (2-hour buffer after fundamentals)
00 11 * * 5     python -m egxpm.run_longterm
```

---

## Dashboard Rules (Section 16)

- Dashboard NEVER calls Engines
- Dashboard NEVER calls LLM
- Dashboard NEVER writes to Persistence
- Dashboard reads precomputed data from Persistence only
- AllocationReport on Home page is the ONE exception — computed at read time via DashboardReadRepository (which calls AllocationCalculator — pure arithmetic, not Engine)
- All write actions go through Copilot Tool Layer
- Streamlit @st.cache_data(ttl=300) on every Repository call

---

## Testing Rules

Every Engine function must have tests for:
1. Correct output for valid input
2. Correct exception for each named failure mode
3. Confirmed pure (no I/O inside the function)
4. Edge cases: null fields, insufficient data, boundary values

Repository tests must verify:
1. Domain objects round-trip (save → get → same object)
2. Append-only tables never allow updates to existing rows
3. FK constraints enforce correctly

---

## Error Handling Rules

Business/Data Errors (catchable, per-company isolation continues):
- InsufficientDataError
- InvalidWeightsError
- InsufficientVolatilityDataError
- PortfolioHeatExceededError
- ScraperSchemaChangedError (StockAnalysis schema changed)
- LLMTimeoutError
- LLMSchemaValidationError
- LLMRateLimitError

Programmer Errors (NOT catchable — must surface loudly):
- ValueError: bad input to Engine (wrong order, wrong type)
- AssertionError: invariant violated

---

## Key Reminders

1. EGX tickers in yfinance use `.CA` suffix: COMI → COMI.CA
2. EGX trades Sunday–Thursday (NOT Friday–Saturday)
3. CIB (COMI) uses StatementSchema.BANK — no operating_margin
4. Stage 6a is a BARRIER — no parallelism across it
5. PortfolioSnapshot captured BEFORE Reasoning (Stage 10), not inside Recommendation assembly
6. confirm_and_apply takes plan_id (UUID) NOT tool name
7. pending_plans keyed by plan_id — multiple plans of same type coexist
8. Checkpoint A includes ConfidenceScore (Stage 7 runs BEFORE Checkpoint A)
9. CollectorService handles rate limiting — NOT inside Collector functions
10. ensure_fresh_data calls CollectorService directly — NOT a nested Job invocation
