# EGX Portfolio Manager — Development Progress

## Current Status
**All 9 milestones complete — tagged v1.0 / architecture-v1.0**
**Last Updated: 2026-07-03**

---

## Milestone Status

| Milestone | Status | Completed Date |
|-----------|--------|----------------|
| M0 — Foundation | ✅ Done | 2026-07-01 |
| M1 — Price + Technical Engine | ✅ Done | 2026-07-01 |
| M2 — Fundamentals + Financial Engine | ✅ Done | 2026-07-01 |
| M3 — News + News Processing Engine | ✅ Done | 2026-07-01 |
| M4 — Scoring + Risk + Confidence | ✅ Done | 2026-07-02 |
| M5 — First Complete Job + Minimal Dashboard | ✅ Done | 2026-07-02 |
| M6 — Swing Job + Full Dashboard | ✅ Done | 2026-07-02 |
| M7 — Portfolio Review + Copilot | ✅ Done | 2026-07-02 |
| M8 — Hardening | ✅ Done | 2026-07-03 |
| M9 — Specification Freeze | ✅ Done | 2026-07-03 |

---

## M0 — Foundation Checklist

- [x] Project folder structure created
- [x] pyproject.toml with all dependencies
- [x] config.yaml with defaults
- [x] SQLite schema (ALL tables including 3 amendments)
- [x] Domain objects — Pydantic models (all Section 3 entities)
- [x] Company Master seed data (Phase 1: holdings + watchlist)
- [x] db.py — WAL connection setup
- [x] company_repository.py
- [x] portfolio_repository.py
- [x] recommendation_repository.py
- [x] conversation_repository.py
- [x] operational_repository.py
- [x] sector_market_repository.py
- [x] dashboard_read_repository.py (stubs)
- [x] AllocationCalculator in shared/
- [x] Unit tests — domain objects round-trip through Repository (43 tests passing)

---

## M1 — Price + Technical Engine Checklist

- [x] shared/exceptions.py (business/data + programmer error taxonomy)
- [x] collectors/collector_service.py (retry policy: transient 3x exponential backoff 2/4/8s; structural no retry)
- [x] collectors/price_collector.py (yfinance, .CA tickers)
- [x] collectors/technical_reference_collector.py (tradingview-ta, reference only)
- [x] engine/technical_engine.py (pandas-ta-classic, all indicators + signals)
- [x] Unit tests for all Technical Engine contracts (16 tests, 100% passing)
- [x] run_collection.py entry point (--type price / technical_reference / technical)
- [x] 5 years OHLCV collected for all Phase 1 companies — **partial by necessity, not a bug: 6/12 (see coverage note below)**
- [x] TechnicalSnapshot rows written to DB (for the 6 companies with candle data)
- [x] Per-company failure isolation verified (live: yfinance 6/12 failures didn't stop the job; TradingView 5/12 failures likewise isolated)

---

## M2 — Fundamentals + Financial Engine Checklist

- [x] engine/financial_engine.py (StatementSchema branching: INDUSTRIAL + BANK; INSURANCE/HOLDING stubs)
- [x] Growth trend detection (accelerating/stable/decelerating/insufficient_data, >=4 periods)
- [x] Unit tests hand-verified against CIB (BANK) and TMG (INDUSTRIAL) values (14 tests, 100% passing)
- [x] collectors/fundamentals_collector.py (StockAnalysis.com, 2s rate limit, retry, ScraperSchemaChangedError)
- [x] run_collection.py --type fundamentals
- [x] FinancialStatements for all Phase 1 companies (>= 4 quarters) — **7/12 companies, 19-20 quarters each (same coverage gap as M1)**
- [x] Bank schema produces operating_margin=null with flag, not wrong number (verified against real CIB data: `operating_margin=None`, `bank_schema_flag=True`, vs. TMG's real `operating_margin=0.363`)

---

## M3 — News + News Processing Engine Checklist

- [x] Mubasher discovery (2-day time-box: XHR vs Playwright) — **resolved on day 1, no XHR/Playwright needed at all (see notes)**
- [x] collectors/news_collector.py (Mubasher)
- [x] EGX Disclosure Collector (semi-manual v1)
- [x] News Processing Engine (lexicon-based, English + Arabic)
- [x] run_collection.py --type news
- [x] News items for all Phase 1 companies (>= 2 weeks) — **7/12 companies, real dates spanning weeks to ~4 months each (same coverage gap as M1/M2)**
- [x] Sentiment correct for 10 manually-labeled test headlines (5 English + 5 Arabic, 21 tests total)
- [x] publisher_name distinct from data_source_id (verified against real data: "مباشر"/"خاص مباشر" vs. "mubasher")
- [x] Lexicon version recorded per item (verified: 42/42 real collected items have lexicon_version set)

---

## M4 — Scoring + Risk + Confidence Engines Checklist

- [x] Scoring Engine (3-component, full breakdown JSON)
- [x] Sector/Market Aggregation (Stage 6a synchronization barrier — plus a separate Stage-6a-only SectorPeerSummary for the Risk Engine's D/E comparison, computed earlier than the dashboard-facing SectorSummary/MarketSummary, see session log)
- [x] Risk Engine (Stage 6b, all 4 components)
- [x] Confidence Engine (5 inputs, SourceHealthService with 1-hr TTL)
- [x] AllocationCalculator unit tests (already written in M0 — reverified still passing, not duplicated)
- [x] Checkpoint A transaction (atomic: TechnicalSnapshot + Score + RiskScore + ConfidenceScore)
- [x] Composite scores for all Phase 1 companies in [0,100] (verified against real data: 42.6-68.0 across the 6 covered companies)
- [x] Score breakdown JSON complete
- [x] Stage 6a barrier verified (failing company absent from peer set — verified with a real InsufficientDataError)
- [x] Checkpoint A atomic transaction verified via simulated crash (two real FK-violation crash simulations)
- [x] Resolved the open config.yaml/pyyaml question (added pyyaml — see session log)

---

## M5 — First Complete Job + Minimal Dashboard Checklist

- [x] Position Sizing Engine (ATR-based stop/target/size, portfolio heat check) — built and tested, but NOT invoked by the Long-Term Job (Stage 9 is explicitly swing-only; will be used starting M6)
- [x] Reasoning Layer (Claude API, Structured Outputs, prompt caching) — real ANTHROPIC_API_KEY added to .env, verified live
- [x] Context Aggregator
- [x] run_longterm.py — the full 14-stage Long-Term Job pipeline (first real Job entry point; run_collection.py's 4 --type modes were always Collection-only, not the full pipeline)
- [x] RecommendationSupersession (implemented; verified on second run — real second run superseded the first ABUK recommendation)
- [x] PortfolioSnapshot scheduled capture (origin="scheduled" at end of each Long-Term run)
- [x] Minimal Dashboard: Home, Long-Term Rankings, Job Status, Collector Status pages
- [x] Long-Term Job completes for all Phase 1 companies (6/12 with data — same coverage gap applies, verified live)
- [x] >= 1 Recommendation with valid frozen_package and rejected_alternatives field (real: ABUK, HOLD, with a genuine 3-item rejected_alternatives list)
- [x] portfolio_snapshot_id on Recommendation references existing snapshot captured before Checkpoint B (verified: snapshot captured_at 25s before recommendation created_at)
- [x] --dry-run produces Score rows but no Recommendation rows (verified live, delta-based check)
- [x] Minimal Dashboard renders without error (verified via Streamlit's AppTest, all 4 pages, zero exceptions)

---

## M6 — Swing Job + Full Dashboard Checklist

- [x] Swing Job (run_swing.py) — candidate filter with CORRECT AND/OR precedence: `(breakout OR unusual_volume OR trend=BULLISH) AND score >= threshold`, NOT the buggy `breakout OR unusual_volume OR (trend=BULLISH AND score>=threshold)`
- [x] ensure_fresh_data calls CollectorService directly (not nested Job) — extracted into a shared module (`egxpm/collectors/ensure_fresh_data.py`), reused by both Jobs
- [x] cron configuration with DST note (`deploy/crontab`)
- [x] All 14 Dashboard pages using DashboardReadRepository or a designated single-owner Repository
- [x] Swing candidate filter verified: breakout=True + score=15 -> BLOCKED; breakout=True + score=75 -> PASSES (exact validation-criteria cases, plus 7 more precedence-regression tests)
- [x] ensure_fresh_data verified: no nested Job record created for inline collection (verified live: 7 total Job rows across all M1-M6 runs, zero of them spurious; CollectionRuns from inline freshness checks correctly have job_id=NULL)
- [x] All 14 pages render against real DB data (Streamlit AppTest, zero exceptions, plus a real manually-started server confirming HTTP 200)
- [x] Position Sizing Engine (built in M5) gets its first real caller here — Stage 9 is swing-only (verified via a synthetic breakout integration test, since real market data currently shows zero candidates)

---

## M7 — Portfolio Review + Copilot Checklist

- [x] Portfolio Review Job (produces RebalancePlan) — run_review.py
- [x] Tool Registry (15 tools, safety tiers: Read/Propose/Execute, plan_id-keyed pending_plans — NOT keyed by tool name, multiple plans of same type can coexist)
- [x] Conversation loop (max_rounds=5, max_tool_calls=15, typed tool_result blocks — provider-protocol adapter, not plain text serialization)
- [x] AnalysisSession workspace (companies_in_scope, pending_plans, simulation_results, draft_shortlist, notes, promoted_to_rec_id)
- [x] Streamlit Copilot UI
- [x] `run_review.py --capital 50000` produces a RebalancePlan
- [x] Scripted acceptance test: compare 2 companies -> simulate -> propose 2 plans -> confirm one (other stays intact) -> confirm wrong plan_id -> ToolResult.error
- [x] session.pending_plans has 2 entries with distinct plan_ids after two propose calls
- [x] Every state-changing Tool action follows Plan -> Review -> Approve -> Execute -> Audit (INVARIANT, never skip)

---

## M8 — Hardening + Consolidation Checklist

- [x] Section 8 schema validation with real data (company_sector_history, recommendation_supersessions, watchlist_history transitions)
- [x] Corporate Actions manual entry CLI/tool
- [x] Recommendation quality analytics
- [x] Error handling consolidation
- [x] Document consolidation — cross-references, terminology, pipeline diagram
- [x] All three Section 8 amendments validated with real operational data
- [x] Corporate action correctly invalidates and recomputes affected TechnicalSnapshots
- [x] Recommendation performance analytics verified against manually computed reference values
- [x] Zero open TODO/required-follow-up flags in document
- [x] Terminology audit complete

---

## M9 — Specification Freeze Checklist

- [x] Remove all pending-amendment and TODO flags (codebase side — the .docx itself is left untouched, see Notes)
- [x] Update Section 6 pipeline diagram (verify "as built" matches the documented Stages 1-13 + 6a/6b/6c + Checkpoints A/B)
- [x] Terminology audit pass (re-confirm M8's audit still holds)
- [x] Cross-reference verification
- [x] Tag git commit architecture-v1.0
- [x] Tag codebase v1.0
- [x] Zero open flags (codebase)
- [x] Zero terminology inconsistencies (codebase)
- [x] Section 6 diagram matches Section 12 pipeline as built
- [x] A new developer can understand every system behavior from CLAUDE.md + progress.md + the codebase itself (the .docx was left untouched — see Notes)

---

## Session Log

### Session 1 — 2026-07-01
- Created CLAUDE.md and progress.md
- Architecture document finalized (v1.0)
- Repository initialized
- **Next:** Start M0 — project structure and schema

### Session 2 — 2026-07-01
- Completed M0 — Foundation in full:
  - Local Python 3.12 environment set up via `uv` (system Python was 3.9; project requires >=3.12). `.venv` created, all pyproject dependencies installed cleanly.
  - Full project structure, `pyproject.toml`, `config.yaml`, `.gitignore`, `.env.example`.
  - `egxpm/persistence/db.py`: complete SQLite schema (26 tables incl. all 3 amendments — company_sector_history, watchlist_history, recommendation_supersessions), WAL/foreign_keys/busy_timeout PRAGMAs, seed data for 7 DataSources and 12 Phase 1 companies.
  - Phase 1 companies are also seeded through the watchlist state machine (CANDIDATE → WATCHLIST) since a Company cannot become a Holding without first existing as a WatchlistEntry. Actual Holding rows (real quantities/cost basis) are NOT fabricated — that's the user's real financial data and must be entered separately.
  - `egxpm/persistence/models.py`: Pydantic domain objects for every Section 3 entity, plus `AllocationReport`/`ProposedAction` shared value objects. `HoldingCategory` enum values are deliberately identical to `config.yaml`'s `allocation_targets` keys so AllocationCalculator can match them directly.
  - `egxpm/shared/allocation_calculator.py`: pure `calculate()` function. Note — the engine contract signature (`holdings, prices, cash, targets`) has no sector data available, so sector-level constraint checking (`max_per_sector_pct`) could not be implemented here; only stock-level (`max_per_stock_pct`, read from `ConfigurationSnapshot.risk_settings`) and category-level allocation are computed. Revisit if sector constraints are needed later — would require passing sector info in explicitly.
  - All 7 Repository classes implemented. Per the architecture's aggregate-root principle ("Company: financials, prices, technicals, news, scores all attach here"), `company_repository.py` owns 13 tables; the other 6 repositories map one-to-one to their listed table groups.
  - Fixed a real ordering bug found via tests: several "get latest by timestamp" queries (`get_watchlist_state`, `list_companies_in_state`, `get_latest_score`, etc.) broke ties non-deterministically when two rows shared an identical timestamp (which happens whenever a job computes one `now()` and reuses it across multiple inserts). Fixed by adding `rowid` as an explicit tiebreaker everywhere latest-row selection happens.
  - 43 tests passing (`test_models.py`, `test_allocation_calculator.py`, `test_repositories.py`) covering round-trips, append-only enforcement (duplicate PK → `IntegrityError`), and FK enforcement.
- **Next:** Start M1 — Price + Technical Engine

### Session 3 — 2026-07-01
- Completed M1 — Price + Technical Engine in full:
  - `egxpm/shared/exceptions.py`: the full Business/Data error taxonomy from CLAUDE.md's Error Handling Rules (`InsufficientDataError`, `InvalidWeightsError`, `InsufficientVolatilityDataError`, `PortfolioHeatExceededError`, `ScraperSchemaChangedError`, `LLMTimeoutError`, `LLMSchemaValidationError`, `LLMRateLimitError`), all under a `BusinessDataError` base. Programmer errors (`ValueError`, `AssertionError`) are deliberately NOT part of this taxonomy — they're meant to surface loudly, never be caught by a Job loop.
  - `egxpm/collectors/collector_service.py`: rate-limit delay + retry policy (transient: 3 attempts, exponential backoff 2/4/8s; structural: immediate `BusinessDataError`, no retry). Classifies transient vs. structural from HTTP status codes when available, falling back to a text heuristic (`429`/`503`/`timeout`/`connection` in the message) since not every library (e.g. `tradingview-ta`) exposes a structured status code.
  - **Important layering fix caught via live testing**: `technical_reference_collector.py` originally caught-and-wrapped `tradingview-ta`'s raw exception into `InsufficientDataError` *inside the Collector*, which would have permanently hidden retry-relevant signals (like a `429` in the message) from `CollectorService` — meaning a genuinely transient rate-limit would never get retried. Fixed by letting Collectors raise unwrapped exceptions and leaving classification entirely to `CollectorService`, per architecture Section 14.5/2.4 ("retry logic lives in CollectorService, never inside a Collector function"). Verified live: a real TradingView 429 was retried 3x with backoff before failing, as designed.
  - `egxpm/collectors/price_collector.py`: yfinance-backed, using the canonical `YFINANCE_TICKERS` mapping from `db.py` (no duplicated ticker list).
  - `egxpm/collectors/technical_reference_collector.py`: tradingview-ta-backed (`exchange='EGX', screener='egypt'`), reference-only — never used as a scoring input. Symbol mapping is derived from `YFINANCE_TICKERS` by stripping `.CA`, not a separately hardcoded dict.
  - `egxpm/engine/technical_engine.py`: pure `calculate_technical_snapshot(candles, window=200, unusual_volume_threshold=1.5)`. Note — the CLAUDE.md contract signature didn't include a config parameter even though the signal rules reference `config.unusual_volume_threshold`; resolved the same way as `AllocationCalculator` in M0, by adding it as an explicit keyword argument defaulting to config.yaml's stated value, keeping the engine free of any hidden config-file access. Support/resistance levels use a 20-day rolling high/low of the *prior* days (excluding today), so breakout is always measured against a level set before today's move — not implied anywhere in the docx, but necessary for the breakout signal to be non-circular.
  - 16 Technical Engine unit tests covering valid-output cases (deterministic monotonic up/down trends, flat/neutral, breakout, unusual volume), every named exception, purity/determinism, and boundary values (exactly `window` candles). Caught and fixed one real bug this way: the ValueError message for mixed timeframes crashed with an `AttributeError` when a non-enum value slipped through model-attribute assignment (Pydantic v2 doesn't validate on assignment by default).
  - `egxpm/run_collection.py`: CLI entry point, `--type {price, technical_reference, technical}`. Thin orchestrator — creates a `Job` + one `CollectionRun` per company, isolates each company's failure (catches only `BusinessDataError`, lets `ValueError`/`AssertionError` crash loudly as programmer errors should), and reports `N succeeded, M failed` with a non-zero exit code if any company failed.
  - **Real yfinance coverage gap found (not a bug — a genuine EGX data-coverage limitation)**: only 6 of 12 Phase 1 tickers resolve on Yahoo Finance — `PALM`(`PHDC.CA`), `COMI`, `TMGH`, `SWDY`, `ABUK`, `EFIH`. The other 6 — `ADA`, `BMM`, `CLOUD`, `NARE`, `ABR`, `EFGD` (mostly small funds/thin instruments) — return no data at all from Yahoo. TradingView (`tradingview-ta`) has slightly better coverage (also covers `NARE`, still misses `ADA`/`BMM`/`CLOUD`/`ABR`/`EFGD`). Verified per-company failure isolation live against this real gap: the Job completed with partial success both times rather than crashing.
  - `data/egx.db` populated with real data: 5 years of daily OHLCV (2021-07-04 through 2026-06-30) for the 6 covered companies, `TechnicalSnapshot` rows computed for all 6, and `TechnicalReferenceSnapshot` rows for the 7 companies TradingView covers.
  - Added `JobType.TECHNICAL` (engine-computation step) to `persistence/models.py` — wasn't in the original enum, which only had `TECHNICAL_REFERENCE` for the collector.
  - 59 tests passing total (43 from M0 + 16 new).
- **Open question, not yet resolved**: `config.yaml` needs a YAML parser at runtime (job scripts need `db_path`, thresholds, model names, etc.) but `pyyaml` isn't in CLAUDE.md's specified `pyproject.toml` dependency list. Asked the user how to proceed (add pyyaml / convert to TOML+tomllib / hardcode as Python constants) — question was dismissed without an answer. `run_collection.py` currently sidesteps this entirely with hardcoded defaults matching config.yaml's stated values (e.g. `db_path="data/egx.db"`, `window=200`). **This needs to be resolved before any Job reads tunable config (scoring weights, thresholds, model names) — will come up again by M4 (Scoring) at the latest.**
- **Next:** Start M2 — Fundamentals + Financial Engine

### Session 4 — 2026-07-01
- Completed M2 — Fundamentals + Financial Engine in full:
  - `egxpm/engine/financial_engine.py`: pure `calculate_financial_metrics(statements, statement_schema)`. Unlike the Technical Engine, statements do NOT need to be pre-sorted by caller — sorted internally by `period_end` — since CLAUDE.md's Financial Engine contract (unlike the Technical Engine's) doesn't list chronological order as a stated precondition.
  - Growth trend detection (`accelerating`/`stable`/`decelerating`/`insufficient_data`) looks only at the most recent 4 periods' growth deltas, not the entire multi-year history, so a long-lived company's classification reflects recent trajectory rather than being smoothed out by unrelated years-old swings. This wasn't specified in the docx beyond ">= 4 periods" — a reasonable, documented design choice.
  - **CAR/NPL ratios were explicitly listed in the architecture doc as a BANK schema deliverable ("CAR/NPL ratios added"), but were deliberately NOT implemented.** The `financial_statements` table (fixed at M0, not modified) has no fields for regulatory capital, risk-weighted assets, or non-performing loan balances — and live inspection of StockAnalysis.com's actual balance sheet page (the M2 data source) confirmed it doesn't expose those either (only "Gross Loans" and "Allowance for Loan Losses", which is a reserve, not an NPL balance). Rather than inventing a schema migration for data no available source actually provides, or fabricating an approximation, `FinancialMetrics` simply omits CAR/NPL fields for now. `operating_margin=None` + `bank_schema_flag=True` — the one thing the M2 validation criteria actually require — is fully implemented and verified against real data.
  - 14 Financial Engine unit tests, hand-computed against synthetic-but-structurally-realistic CIB (BANK) and TMG (INDUSTRIAL) fixtures — every ratio value in the tests was computed by hand and matched exactly (e.g. `debt_to_equity == 2070/230 == 9.0`).
  - `egxpm/collectors/fundamentals_collector.py`: scrapes StockAnalysis.com's income statement, balance sheet, and cash flow pages (`?p=quarterly`). Extracts `period_end` directly from each header cell's `id="YYYY-MM-DD"` attribute rather than parsing display text like `"Mar '26Mar 31, 2026"` — much more robust than text parsing. Deliberately ignores the site's own precomputed growth-%/margin rows; the Financial Engine always computes ratios from raw figures itself (one canonical implementation, never trusting a second source's precomputed number).
  - **Real bug caught via live testing**: the original missing-field check raised `ScraperSchemaChangedError` if *any* whitelisted field wasn't found anywhere on a page — but BANK income statements genuinely have no "Operating Income" row at all (confirmed live against COMI's real page), which is an expected schema difference, not a broken scrape. Fixed to only raise when *none* of the whitelisted fields matched anything, which is the actual signal of a real layout change.
  - `egxpm/run_collection.py --type fundamentals`: 2s StockAnalysis.com rate limit applied once per company (matching the docx's literal wording "between company requests", not between the 3 sub-page requests within one company).
  - **StockAnalysis.com coverage gap confirmed to match M1's exactly**: same 7/12 companies work (`PALM`→`PHDC`, `COMI`, `TMGH`, `SWDY`, `ABUK`, `EFIH`, plus `NARE` — StockAnalysis and TradingView both cover NARE; only Yahoo Finance doesn't), same 5 (`ADA`, `BMM`, `CLOUD`, `ABR`, `EFGD`) return 404 everywhere. This is very likely a structural fact about these 5 tickers (thin/inactive instruments), not a per-source quirk — worth treating as a known, permanent Phase 1 data gap rather than re-investigating in future milestones.
  - `data/egx.db` populated with real data: 19-20 quarters (~5 years) of `FinancialStatement` rows for the 7 covered companies. Verified the Financial Engine end-to-end against this real data: CIB (BANK) → `operating_margin=None`, TMG (INDUSTRIAL) → `operating_margin=0.363`.
  - 73 tests passing total (59 from M0+M1 + 14 new).
- **Next:** Start M3 — News + News Processing Engine. Mubasher discovery (XHR vs Playwright) is explicitly flagged as the highest-risk task in the architecture doc — time-box it to 2 days before falling back to a heavier approach.

### Session 5 — 2026-07-01
- Completed M3 — News + News Processing Engine in full:
  - **Mubasher discovery resolved on day 1 of the 2-day time-box** — no XHR reverse-engineering or Playwright was needed at all. A company's stock page (`/markets/EGX/stocks/{ticker}`) is plain server-rendered HTML: a `.stock-overview-media-block` list gives the 6 most recent headlines + links, and each article page cleanly exposes its own published date and source label in rendered HTML (sitting alongside unrendered Angular template placeholders like `{{details.article.source}}` — picked the first element whose text doesn't still contain a literal `{{`). Same ticker convention as M1/M2 (base symbol, `.CA` stripped).
  - **Schema gap, deliberately fixed this time (unlike CAR/NPL in M2)**: `news_items` had no column to record which lexicon version scored an item, but "lexicon version recorded per item" is an explicit M3 validation criterion we fully own (unlike CAR/NPL, which depends on data no source provides). Added `lexicon_version TEXT` via an idempotent additive migration in `db.py`, applied automatically by `init_db()` — verified live against the existing `data/egx.db` (with real M1/M2 data already in it) that no existing data was touched. Also switched `run_collection.py` to call `init_db()` unconditionally every run (it's fully idempotent) instead of only when the db file is missing, since that's how future migrations reach an existing database.
  - `egxpm/engine/news_engine.py`: pure `score_news_item(item) -> NewsItem`. Lexicon-based sentiment `[-1,1]` + relevance `[0,1]`, versioned (`news_lexicon_v1`), English + Arabic terms.
  - **Real bug caught while writing hand-labeled tests**: having both a singular and inflected form of the same word in one lexicon set (e.g. `"increase"` and `"increases"`) double-counted a single headline mention, because substring matching means the shorter form already matches inside the longer one. Fixed by keeping exactly one form per word family and adding a small script to verify programmatically that no lexicon entry is a substring of another in the same set.
  - **Deliberate design choice, verified against real Arabic text before committing to it**: matching is plain substring search, not word-boundary regex. Arabic attaches grammatical suffixes directly onto word roots with no separator (e.g. "أرباحاً" = "أرباح" + accusative tanween), so a strict `\b` boundary would miss almost every real inflected Arabic form — confirmed live that `\b`-bounded matching failed on a real headline while substring matching succeeded. This does trade away some English precision (e.g. "fall" could match inside an unrelated word), but that's the documented v1 tradeoff — Arabic stemming/normalization is explicitly a "future seam, not v1" per the architecture doc.
  - 21 News Engine tests, including the 10 hand-labeled headlines required by the validation criteria (5 English + 5 Arabic: positive/negative/neutral/tied cases).
  - `egxpm/collectors/news_collector.py` (Mubasher) and `egxpm/collectors/egx_disclosure_collector.py` (EGX official disclosures — semi-manual v1, no automated feed exists, so this Collector just stamps consistent provenance on user-entered disclosures; no scraping).
  - `egxpm/run_collection.py --type news`: 1.5s Mubasher rate limit. Scoring happens between collection and the single INSERT (not a later UPDATE) since `news_items` is append-only — the Job runs `score_news_item()` on each raw item before `save_news_item()`.
  - `data/egx.db` populated with real data: 42 news items (6 per company) across the 7 covered companies, dates spanning weeks to ~4 months, confirmed `publisher_name` ("مباشر"/"خاص مباشر") always distinct from `data_source_id` ("mubasher"), confirmed `lexicon_version` set on all 42 rows.
  - Same 5-company coverage gap (`ADA`, `BMM`, `CLOUD`, `ABR`, `EFGD`) held for Mubasher too — now confirmed across all 4 sources checked (yfinance, TradingView, StockAnalysis.com, Mubasher). This is very likely a hard, permanent Phase 1 data limitation for these 5 companies.
  - 97 tests passing total (73 from M0-M2 + 24 new: 21 News Engine + 3 EGX Disclosure Collector).
- **Next:** Start M4 — Scoring + Risk + Confidence Engines. The open `config.yaml`/`pyyaml` question (unresolved since M1) needs an answer before this milestone can read real scoring weights instead of hardcoded defaults — flag it to the user again if it comes up.

### Session 6 — 2026-07-02
- Completed M4 — Scoring + Risk + Confidence Engines in full. This was the largest milestone by far — it's the first one combining outputs from all three prior Engines (Financial, Technical, News) plus a cross-company synchronization barrier and an atomic 4-table transaction. Several genuine spec gaps needed documented v1 judgment calls (below), all deliberately conservative and testable rather than guessed silently.
  - **Resolved the config.yaml/pyyaml question** (open since M1): added `pyyaml` as a dependency. `egxpm/shared/config.py` is the one place that reads `config.yaml`; `build_configuration_snapshot()` resolves it into a `ConfigurationSnapshot` with ONE active weight profile (`longterm_weights` or `swing_weights`) per snapshot, since a `ConfigurationSnapshot` represents one resolved policy for one Job run, not both profiles at once.
  - `egxpm/engine/scoring_engine.py`: `calculate_score()` computes financial/technical/news sub-scores (composite left `None` until Stage 6c); `assemble_composite_score()` is Stage 6c. Returns `ScoreResult` (not `Score`) for the same reason `TechnicalSnapshotResult` exists — `company_id`/`config_snapshot_id`/`job_id` are Orchestration metadata, attached afterward via `build_score()`.
    - **Rubric point allocations are this system's own v1 judgment calls** (documented inline) — the architecture doc gives the 3-component structure and one breakdown JSON example, not exact point values. Financial: revenue/net-income/EPS growth, net margin, ROE, ROA, D/E, FCF margin, growth-trend bonus, summing to 100. Technical: trend (40), RSI zone (20), MACD crossover (15), breakout (15), unusual volume (10).
    - **Debt/Equity scoring is schema-aware** (bank ceiling 12.0x vs industrial 2.0x) — banks are structurally far more leveraged since customer deposits count as liabilities. Verified against real data: COMI's real D/E of 6.25 scores reasonably on the bank scale instead of being punished as if it were an over-leveraged industrial company.
    - Sector/Market aggregation for the *dashboard* (`aggregate_sector_summary`/`aggregate_market_summary`, averaging `composite_score`) is intentionally a different, later computation than the Risk Engine's `SectorPeerSummary` (Stage 6a, D/E-only) — composite doesn't exist until Stage 6c, so the dashboard aggregate can't be computed at the actual Stage 6a barrier point; only the D/E peer comparison can.
  - `egxpm/engine/risk_engine.py`: 4 components (debt_peer, score_volatility, data_completeness, liquidity). **Missing inputs degrade to penalty=50 (conservative mid-range)** per the explicit contract wording — deliberately different from the Scoring Engine's exclude-and-renormalize/treat-as-zero policy, since excluding a risk component that would've looked bad could understate overall risk.
    - `build_sector_peer_summary()` reads each company's D/E straight from `Score.financial_breakdown` (not a separate `FinancialMetrics` list) — matches the actual contract signature (`calculate_risk_score` only receives a `Score`).
    - `LiquiditySummary.hypothetical_position_size_egp` is a genuine spec gap: liquidity_risk needs a position size, but Position Sizing (Stage 9) hasn't run yet at Stage 6b. Resolved by using a hypothetical worst case (e.g. `max_position_pct * portfolio_total`) rather than a number that doesn't exist yet — documented inline.
    - Component blend weights (equal 0.25 each) and ceilings (D/E 2x peer median, score std_dev 20pts, liquidity 20% of daily volume) are documented v1 defaults — the doc names the components without specifying relative weight.
  - `egxpm/engine/confidence_engine.py`: 5 inputs (Score + Freshness/SourceQuality/SourceHealth/HistoricalAccuracy summaries). `RiskScore` is deliberately NOT an input (Risk = investment quality, Confidence = data reliability — independent dimensions per the doc; verified with a test that inspects the function signature). Source quality tier weights (Official/Internal=1.0, Scraped=0.7, Manual=0.8) are fixed system constants straight from the doc's table; the 4 components' blend weight isn't specified there either, so equal weighting again.
  - `egxpm/collectors/source_health_service.py`: 1-hour TTL cache over a rolling 30-day `CollectionRun` success rate. No new table, per the doc's "derived on demand" rule. Returns `None` (not an optimistic 1.0) when there's no run history at all, so the Confidence Engine's neutral-0.5 default applies consistently.
  - **Checkpoint A**: `CompanyRepository.save_checkpoint_a()` — turned out to need almost no new code, since all four `save_*` methods already accepted an optional external `conn` parameter from M0/M1's design. Verified atomicity with two real crash simulations (FK violations on `RiskScore` and, separately, on the last-written `ConfidenceScore`) — confirmed none of the four rows survive either way, not just the row that actually failed.
  - **Deliberately did NOT build `run_longterm.py` this milestone** — it's explicitly an M5 deliverable. Instead wrote an integration test (`tests/test_m4_pipeline_integration.py`) that runs the real Stage 3-7 + Checkpoint A pipeline against real M1-M3 data, verifying both remaining validation criteria: composite scores for all 6 covered companies land in [0,100] with real differentiation (COMI=42.6, TMGH=41.7, PALM=48.0, SWDY=36.4, ABUK=68.0, EFIH=58.4), and the Stage 6a barrier correctly excludes a company that failed Stage 6 (a real `InsufficientDataError`) from its sector's peer D/E set.
  - 168 tests passing total (97 from M0-M3 + 71 new: 3 config + 23 Scoring Engine + 21 Risk Engine + 13 Confidence Engine + 6 SourceHealthService + 3 Checkpoint A + 2 M4 integration).
- **Next:** Start M5 — First Complete Job + Minimal Dashboard. Will need `ANTHROPIC_API_KEY` set in `.env` for the Reasoning Layer, and will need to ask the user for real Holding data (quantities/cost basis) before the dashboard can show real allocation — both flagged as open items since earlier milestones.

### Session 7 — 2026-07-02
- Completed M5 — First Complete Job + Minimal Dashboard in full. This is the first milestone that produces a real, LLM-reasoned Recommendation end-to-end — asked the user for an `ANTHROPIC_API_KEY` before starting (they provided one; saved directly to `.env`, confirmed gitignored, verified with a real API call before building anything against it).
  - `egxpm/engine/position_sizing_engine.py`: ATR-based stop/target/size + portfolio-heat guard, 9 tests. Two real gaps resolved: (1) `entry_price` isn't in the contract signature, so added `latest_close` to `TechnicalSnapshotResult` (the Technical Engine already computes it internally, just didn't expose it); (2) the portfolio-heat check's "open_risk" has no natural source (`AllocationCalculator` can't see stop losses on active Recommendations), so added `open_risk_egp` to `AllocationReport`, defaulting to 0.0. Used CLAUDE.md's complete formula (which divides the position cap by `entry_price`, keeping units in shares throughout) over the architecture doc's shorter version, which drops that division and would mix EGP/share-count units.
  - **Position Sizing Engine is built but NOT called by the Long-Term Job** — Stage 9 is explicitly annotated "[swing only]" in the canonical pipeline. Long-term Recommendations carry `entry_price` for reference but no stop/target/size; the architecture doesn't specify a long-term position-sizing formula, so none was fabricated. It gets its first real caller in M6's Swing Job.
  - `egxpm/llm/context_aggregator.py`: Stage 11, `build_context()` produces `CuratedContext`, 11 tests.
  - `egxpm/llm/client.py` + `egxpm/llm/prompts.py`: the Reasoning Layer. Structured Outputs via Claude's forced tool-use (not a JSON-mode flag), prompt caching on the system prompt. **Two real bugs caught via live testing against the actual API** (not assumed from docs):
    1. *Hallucination*: since `CuratedContext` only carries `company_id` (the `build_context` contract has no separate `company` parameter), Claude invented a plausible-but-wrong full company name ("Tamer Group Holding" for TMGH — actually Talaat Moustafa Group). Fixed with an explicit identity-guard instruction in both system prompts rather than expanding the function signature; verified live that the model now correctly refers to the company only by its ticker.
    2. *Schema drift*: Claude (Haiku) intermittently emitted `key_risks`/`rejected_alternatives` as a markdown string or malformed pseudo-tool-call text instead of a JSON array, despite the schema declaring them as arrays — correctly caught as `LLMSchemaValidationError`. Fixed with explicit Field descriptions ("never a single string") plus bumping retries from 1 to 3 attempts, which took a small live sample from failing ~40% of calls to 5/5 successful.
  - **Checkpoint B**: `RecommendationRepository.save_checkpoint_b()` (Recommendation + optional RecommendationSupersession), same conn-threading pattern as Checkpoint A, verified via a real FK-violation crash simulation.
  - `egxpm/run_longterm.py`: the full 14-stage Long-Term Job. Sequences `ensure_fresh_data` (calls `CollectorService` directly, no nested Job row, per the architecture doc), Financial/Technical/News Engines, Scoring Engine, the Stage 6a sector D/E barrier, Risk + Confidence Engines, Checkpoint A, Portfolio Engine, `PortfolioSnapshot` (origin=scheduled), Context Aggregation, the Reasoning Layer, and Checkpoint B with `RecommendationSupersession`.
  - **Verified live end-to-end, not just unit tested**: `--dry-run` produced 6 Score+Risk+Confidence rows and 0 new Recommendations; a real run produced 1 real Recommendation (ABUK, HOLD) with a genuine `rejected_alternatives` list reasoning through BUY/ADD/SELL and citing the real 0.0 technical score and 0.75 confidence as reasons; `portfolio_snapshot_id` correctly references a snapshot captured ~25s before the recommendation; running the Job a second time correctly superseded the first ABUK recommendation via `RecommendationSupersession`.
  - Caught a real test-design bug of my own while verifying: after populating the real `data/egx.db` with an actual recommendation, `tests/test_run_longterm.py`'s dry-run test (which copies that real db) started failing because it asserted an absolute `rec_count == 0` instead of checking the delta introduced by the test's own dry-run call. Fixed to compare before/after counts.
  - `app.py`: Minimal Dashboard — Home (allocation, latest PortfolioSnapshot, recent Recommendations with reasoning/risks/rejected-alternatives), Long-Term Rankings (WATCHLIST companies ranked by composite_score with full breakdown), Job Status, Collector Status. Added `DashboardReadRepository.get_longterm_rankings()`.
  - **Tooling note**: the interactive preview tool couldn't attach to this project's `uv`-managed venv — `PermissionError` reading `.venv/pyvenv.cfg`, traced to a `com.apple.provenance` extended attribute the sandboxed preview process can't read past. Not a bug in the app. Verified dashboard correctness instead via Streamlit's built-in `AppTest` (in-process headless testing, now `tests/test_dashboard.py`) and a manually-started real server (`curl` HTTP 200, clean startup log, no errors).
  - 209 tests passing total (168 from M0-M4 + 41 new: 9 Position Sizing + 11 Context Aggregator + 8 LLM client + 3 Checkpoint B + 6 run_longterm + 4 dashboard).
- **Next:** Start M6 — Swing Job + Full Dashboard. The Swing candidate filter's AND/OR precedence bug is explicitly called out in CLAUDE.md as a named pitfall to avoid — double-check the implementation against the two given test cases before considering it done. Position Sizing Engine (built in M5, unused until now) gets its first real caller.

### Session 8 — 2026-07-02
- Completed M6 — Swing Job + Full Dashboard in full.
  - **Refactored before adding new code**: extracted `egxpm/collectors/ensure_fresh_data.py` (shared by both Jobs) and `egxpm/scoring_pipeline.py` (the common Stage 3-7 + Checkpoint A machinery), pulling this logic out of `run_longterm.py` first rather than copy-pasting it into `run_swing.py`. `run_longterm.py` shrank from ~384 to ~250 lines with verified-identical behavior (reran `--dry-run` against a scratch copy of real data: same 6 scored/6 failed/0 recommendations as before the refactor).
  - `egxpm/run_swing.py`: the Swing Job. `passes_swing_filter()` implements `(breakout OR unusual_volume OR trend=BULLISH) AND composite_score >= threshold` — the exact precedence CLAUDE.md calls out by name as a pitfall. 9 tests, including the two literal validation-criteria cases (breakout=True+score=15 blocked, breakout=True+score=75 passes) plus regression coverage proving the buggy alternate parenthesization would have let unusual_volume/breakout bypass the score gate entirely.
  - **Financial Engine "skip" resolved pragmatically**: the architecture doc says the Swing Job reads "existing FinancialMetrics from last Long-Term Job," but there's no `financial_metrics` table — only the Score computed from it is persisted. Rather than reconstructing a `FinancialMetrics` object from a persisted Score's breakdown JSON (fragile, an inversion of the normal data flow), Swing recomputes `calculate_financial_metrics()` over the SAME already-collected `FinancialStatement` rows Long-Term used. Since Financial Engine is pure and those statements only change quarterly, this produces an identical result with zero extra I/O — functionally the same outcome the spec describes, without a separate code path.
  - Position Sizing Engine (built in M5, unused until now) gets its first real caller — Stage 9 is swing-only. Verified live: real market data at the time showed **zero real swing candidates** across all 6 covered companies (bearish/neutral trend, no breakout/unusual volume anywhere) — a genuine, verified market condition, not a bug. Added a synthetic integration test (mocked LLM, no network cost) engineering a breakout via the same flat-then-spike candle pattern already proven in `test_technical_engine.py`, confirming the full pipeline (Position Sizing -> Context -> Reasoning -> Recommendation) produces a Recommendation with correctly-ordered `stop_loss < entry_price < take_profit` when a candidate does pass.
  - **ensure_fresh_data validation criterion verified live**: across 2 full Swing Job runs plus all of M1-M5's runs, only 7 total `Job` rows exist in the database — all legitimate (5 Collection + 1 Long-Term + 1 Swing) — with zero spurious nested Job rows from inline freshness checks. Those checks instead produced `CollectionRun` rows with `job_id=NULL`, exactly as designed.
  - `deploy/crontab`: the cron schedule with a DST note — Egypt abolished DST in 2023 (permanent fixed UTC+2), so there's no seasonal transition logic needed; the note explains `TZ=Africa/Cairo` as the simplest way to deploy correctly on a non-Cairo server.
  - Extended `DashboardReadRepository` (`get_holdings_detail`, `get_watchlist_detail`, `get_company_analysis`) and `OperationalRepository` (`list_table_names`/`query_table`/`count_table_rows` for the Raw Database Explorer — table name validated against a live `sqlite_master` whitelist before being interpolated into a query, since SQLite can't parameterize identifiers; verified against a real injection-attempt string).
  - Built all 14 Dashboard pages (10 new: Portfolio Holdings Detail, Watchlist, Swing Trading, Recommendations History, Recommendation Performance, Company Analysis, Financial Statements, News Feed, Historical Timeline, Raw Database Explorer; Collector Status enhanced with `SourceHealthService`). All 14 rendered with **zero exceptions on the first attempt** (Streamlit's `AppTest`, parametrized one-test-per-page), reconfirmed with a real manually-started server (curl HTTP 200, clean log).
  - Swing Trading page identifies swing-originated Recommendations via `stop_loss IS NOT NULL` rather than joining to the `jobs` table — only swing Recommendations carry ATR-based stop/target/size (Position Sizing is swing-only), so this is a reliable, join-free signal.
  - 241 tests passing total (211 from M0-M5 + 30 new: 7 ensure_fresh_data + 9 run_swing filter + 1 run_swing synthetic integration + 9 dashboard-repository extensions + 15 dashboard (14 pages + registration check) — note some M5 tests were consolidated/moved during the refactor, not simply added).
- **Next:** Start M7 — Portfolio Review + Copilot. This introduces the first user-facing write path (propose/confirm plans through a Tool Registry) — read the Plan -> Review -> Approve -> Execute -> Audit invariant carefully, since it's explicitly never to be skipped for any state-changing Tool action.

### Session 9 — 2026-07-02
- Completed M7 — Portfolio Review + Copilot in full. This is the first milestone with a user-facing write path.
  - **`egxpm/engine/portfolio_engine.py` built for the first time this milestone** — it was in CLAUDE.md's file listing since M0 but M4-M6's Jobs had all been calling `shared/allocation_calculator.calculate()` directly. M7 needed `PortfolioEngine.simulate()` explicitly, so it was built now: `apply_action()` (public — the Tool Registry needs it directly for `propose_rebalance`'s chained simulation) plus thin `calculate_allocation()`/`simulate()` wrappers. Same signature gap as always with this contract (missing `prices`/`cash`), resolved the same way as M5's Position Sizing Engine — explicit added parameters, documented inline. 11 tests.
  - **Where do Plans live? Resolved as: nowhere in SQL.** No `rebalance_plans`/`swing_plans` table exists in the M0 schema, and adding one now would violate "ALL tables must be created at Milestone 0" far more than earlier judgment calls (like M3's `lexicon_version` column, which the system fully owns). `egxpm/copilot/models.py`'s `RebalancePlan`/`SwingPlan` are ephemeral, session-scoped Pydantic objects that live only inside `AnalysisSessionState.pending_plans`, serialized into the already-existing generic `AnalysisSession.state` JSON column only when a session is explicitly saved.
  - `egxpm/copilot/tool_registry.py`: all 15 tools (10 Read, 2 Propose, 3 Execute) as one `ToolRegistry` class. `execute(tool_name, arguments, session)` dispatches by tier and converts `BusinessDataError` into `ToolResult(success=False, error=...)` — never a raised exception for an expected failure like a wrong `plan_id` or missing data; `ValueError`/`AssertionError` still propagate as genuine bugs.
    - `propose_rebalance` computes the exact allocation in Python — equal-weight capital split across the top-N WATCHLIST candidates by `composite_score`, capped at `max_per_stock_pct` of portfolio value per stock — the LLM only narrates the resulting plan, never decides the numbers, per "LLM never calculates."
    - `propose_swing_analysis` intentionally does NOT assemble a risk-adjusted composite score (that requires the Stage 6a sector-wide barrier across every company, too heavy for a single on-demand preview) — it surfaces the three raw sub-scores instead; only the scheduled Swing Job produces the real composite.
    - `confirm_and_apply` never places a real trade (Section 15.6) — it pops the plan from `pending_plans`, records it in `confirmed_plan_ids`, and returns a message instructing the user to execute manually in Thndr.
  - `egxpm/copilot/session.py`: `CopilotSession` — the conversation loop. Loops Claude <-> tools up to `copilot_max_tool_rounds` (5), capping total tool calls at `copilot_max_tool_calls` (15) per user turn; forces a text-only final answer (`tool_choice: none`) if the round budget is exhausted with tool calls still pending. `messages` carries typed content blocks (SDK `ContentBlock` objects for assistant turns, hand-built `tool_result` dicts for tool responses), never a flattened plain-text transcript. 8 tests against a fake registry/client covering the round loop, the forced-final-call path, the per-round tool-call budget, and the typed `tool_result` block shape.
  - `egxpm/run_review.py`: thin CLI wrapper around `ToolRegistry.propose_rebalance` — reuses the one canonical rebalancing implementation rather than duplicating it (invariant #10). Persists the resulting plan inside a fresh `AnalysisSession` so a CLI-produced plan isn't silently lost, but never applies it — confirmation still requires the Copilot's `confirm_and_apply`.
  - **Verified live end-to-end against real production data** (`data/egx.db`, real scores from M4-M6's real runs): `python -m egxpm.run_review --capital 50000` produced a real 6-company equal-weight plan (ABUK/EFIH/PALM/COMI/TMGH/SWDY) and persisted a real `AnalysisSession` row. Since no real Holding data has been entered yet (flagged since M5), the per-stock cap degrades to an unconstrained equal split — a correctly-documented consequence of the known data gap, not a bug.
  - `app.py`: added the Copilot as the dashboard's 15th page — the one deliberate exception to "Dashboard never calls LLM / never writes," since it *is* the Copilot Tool Layer's UI. Chat interface backed by `CopilotSession` in `st.session_state` (per-browser-session, not `@st.cache_data`); pending plans render as expanders with a Confirm button (the explicit user-approval step); a Save session button persists the `AnalysisSession`.
  - **Verified live end-to-end via Streamlit's `AppTest`** (same sandbox limitation as M5 — the interactive preview still can't attach to this venv): a real chat question about TMGH correctly called `get_company_summary` and returned its real composite score (41.72) with correct sector/trend/confidence; `propose_rebalance` via chat produced a real pending plan; clicking Confirm correctly moved it into `confirmed_plan_ids` and removed it from `pending_plans` (checked directly against `session.state`, not just the rendered UI); Save session persisted a real `AnalysisSession` row.
  - Scripted acceptance test (`tests/test_tool_registry.py::test_full_acceptance_scenario`) covers the exact M7 validation criterion: compare 2 companies -> simulate -> propose 2 plans (distinct `plan_id`s) -> confirm one (the other stays in `pending_plans`) -> confirm a nonexistent `plan_id` -> `ToolResult.error`.
  - 274 tests passing total (241 from M0-M6 + 33 new: 11 Portfolio Engine + 11 Tool Registry + 8 Copilot session + 2 run_review + 1 Copilot dashboard page, with the old "14 pages registered" test replaced by a "15 pages registered" test).
- **Next:** Start M8 — Hardening. No specific scope has been read from CLAUDE.md yet for M8/M9 beyond their milestone-table names ("Hardening" / "Specification Freeze") — read the architecture doc's M8/M9 sections at the start of that session before assuming scope.

### Session 10 — 2026-07-03
- Completed M8 — Hardening + Consolidation in full. Read Section 17.1 (M8/M9 deliverables + validation criteria) and Appendix A.1 (terminology audit reference) directly from the architecture docx, since CLAUDE.md's milestone table only names M8/M9 without detail.
  - **Fixed a latent price_candles duplicate-date bug before touching corporate actions**: `CompanyRepository.list_price_candles` returned every physical row with no dedup by (company_id, candle_date, timeframe), even though price_candles is append-only by design (corrections are new rows, never UPDATEs). A corporate-action price adjustment (needed this milestone) or `ensure_fresh_prices`' period="1mo" refresh overlapping already-stored history would have silently handed every downstream consumer duplicate dates. Fixed with the same "latest row wins" pattern already used for `get_latest_score` — a correlated subquery picking the max (fetched_at, rowid) per date. No real duplicates existed yet in data/egx.db (all successful yfinance runs so far are from the single M1 bulk fetch), so this was a latent-bug fix, not a data repair.
  - `egxpm/collectors/corporate_actions_collector.py` + `egxpm/record_corporate_action.py`: manual-entry CLI. Records the CorporateAction; for price-adjusting types ("split"/"bonus_issue", requiring `details["ratio"]`), inserts new (never UPDATEd) PriceCandle rows for every date before the action, scaled by ratio, then recomputes and saves a fresh TechnicalSnapshot over the adjusted series. Every action type also supersedes any currently active Recommendation via `RecommendationSupersession` (`superseding_event_type="corporate_action"`, Section 10.3) — implemented for the first time; only `new_score_computed` existed before. Also noticed and fixed a related gap while here: `run_review.py` never created a `Job` row despite `JobType.REVIEW` already existing in the enum since M0 — fixed for observability consistency with every other Job.
  - **Section 8 amendments validated against real operational data**: ran a second real Long-Term Job against `data/egx.db` (not a scratch copy) to produce the first genuine `recommendation_supersessions` row in the production database (ABUK HOLD → BUY). `tests/test_section8_amendments_live.py` reads the real database directly and asserts the actual invariants each amendment guarantees. Corporate-action price adjustment and company-sector/watchlist amendment mechanisms were validated via dedicated tests rather than fabricated in production data — no real split/sector-change/archival has ever happened for any Phase 1 company, and inventing one in `data/egx.db` would mean inventing business data no real event justifies.
  - `egxpm/shared/recommendation_analytics.py`: extracted `summarize_performance()` (target-hit rate, stop-hit rate, average return over FINAL outcomes only) out of `app.py`'s Recommendation Performance page, where the arithmetic previously lived inline — same category as `AllocationCalculator` (pure, importable, one canonical implementation). Hand-computed test fixture verifies the exact rates/average against manually worked-out reference values, per M8's validation criterion.
  - **Error handling consolidation found 3 real bugs**: (1) `CollectorService.collect()`'s bare `except Exception` would have silently retried-then-wrapped a genuine `ValueError`/`AssertionError` from inside a Collector into a `BusinessDataError`, hiding a real programmer bug behind per-company isolation — fixed by re-raising `ValueError`/`AssertionError` first; added `tests/test_collector_service.py` (8 tests — this module had zero dedicated tests despite being core shared infrastructure since M1). (2) `AllocationCalculator.calculate()`'s bare `ValueError` for a held company missing from `prices`, silently caught by `scoring_pipeline.compute_allocation()` into a fabricated empty `AllocationReport` — except `prices` there was only ever built from companies that succeeded Stage 3-6 *this run*, so a held company whose Technical Engine merely failed this run (transient) would silently vanish from `total_value` with no error anywhere. Currently unreachable (no real Holding data exists yet) but a real landmine. Fixed: the exception is now `InsufficientDataError` (a real data-completeness gap per the taxonomy, not a caller-precondition `ValueError`), and a new `CompanyRepository.get_latest_prices()` — the one canonical "current price" lookup — supplies each holding's last known price as a fallback before that exception can even fire. (3) That same "latest known price per holding" loop was independently duplicated three times (`app.py`, `ToolRegistry._current_prices`, and the gap in `compute_allocation`) — consolidated onto `get_latest_prices()`.
  - **Terminology audit against Appendix A.1**: found one genuine drift (`technical_engine.py`'s docstring said "indicators + derived signals" instead of naming `TechnicalSnapshot.indicators`/`TechnicalSnapshot.signals` explicitly — fixed). Everything else checked either had zero matches or was CLAUDE.md's own literal wording (CLAUDE.md quotes "allocation arithmetic" verbatim in its own AllocationCalculator contract) or a genuinely different concept (`technical_reference_collector.py`'s "raw indicators" refers to the real `raw_indicators` column on `technical_reference_snapshots`, a different table). Deliberately did NOT rename `WatchlistState`/`watchlist_history` to "MonitoringIntent" per the appendix's forbidden-alias entry for that concept — CLAUDE.md (the higher-priority, explicitly overriding document) names this concept `WatchlistState` throughout its own "Watchlist States" section; the full doc's Section 11 uses "Monitoring Intent" as the abstract dimension's name in prose while still persisting it through `watchlist_history` — a documentation-terminology distinction, not an instruction to rename the schema this codebase is built around.
  - 298 tests passing total (274 from M0-M7 + 24 new: 1 dedup regression + 4 corporate-actions-collector + 3 record-corporate-action + 3 Section 8 live validation + 4 recommendation analytics + 8 CollectorService + 1 get_latest_prices).
- **Next:** Start M9 — Specification Freeze (per Section 17.1: remove pending-amendment/TODO flags, verify Section 6 pipeline diagram matches implementation, a final cross-reference/terminology pass, tag `architecture-v1.0` and `v1.0`). This is the last milestone — after it, the system is v1.0 per the doc's own definition, though real Holding data still needs to be entered by the user before the dashboard/Portfolio Review reflect actual positions (flagged since M5, still open).

### Session 11 — 2026-07-03
- Completed M9 — Specification Freeze in full. This is the last milestone; the codebase is now tagged `v1.0` and the architecture reference is tagged `architecture-v1.0`.
  - **Asked the user how to handle the .docx itself** before doing anything else: M9's "remove pending-amendment/TODO flags" and "update Section 6 diagram" deliverables literally target `docs/EGX_Investment_OS_Architecture_v1.0.docx`, but there's no reliable tooling here to safely edit an embedded Word diagram, and even a text-only edit risks corrupting a binary file I can't visually re-verify afterward. The user chose to leave the .docx untouched entirely — it remains exactly as provided, and the items below are documented here instead of edited into it.
  - **Codebase-side "remove TODO flags"**: grepped the full codebase (`egxpm/`, `app.py`, `tests/`) for `TODO`/`FIXME`/`XXX:`/`HACK:` — zero matches. Nothing to remove.
  - **Section 6 pipeline cross-reference verification**: re-read `run_longterm.py` and `run_swing.py` stage-by-stage against the canonical Stages 1-13 + 6a/6b/6c + Checkpoints A/B. Both Jobs implement every stage in the documented order, including one already-resolved, deliberate ordering nuance from M4: Stage 8 (Portfolio Engine/AllocationReport) is actually computed *before* Stage 6b (Risk Engine) in both Jobs, not after as the stage numbering alone would suggest — because Risk Engine's liquidity component needs a `hypothetical_position_size_egp` derived from the portfolio total, a genuine cross-stage input dependency documented back in M4's session log, not a new finding or a bug.
  - **Terminology re-check**: re-ran M8's full forbidden-alias grep across the codebase — zero matches, confirming M8's audit still holds and nothing introduced during M8's own fixes regressed it.
  - **Docx staleness noted, not edited**: the architecture doc's own text still contains at least one now-resolved placeholder — a "Scraping / XHR (TBD)" note for the Mubasher News Collector in the Section 6 data-source table, even though M3 resolved this on day one via plain server-rendered HTML (no XHR/Playwright needed). This and Section 7.6's "Open Items for Discovery" list (Mubasher XHR, corporate-actions automation, symbol normalization) are stale relative to what was actually built — Appendix A.3's "Open Items Resolved" table already captures most of these; the doc simply wasn't hand-edited to remove the earlier forward-looking markers. Left as-is per the user's decision above.
  - Tagged the current commit `v1.0` (codebase) and `architecture-v1.0` (the frozen architecture reference, unedited) — both local tags, no remote configured.
  - 298 tests passing (no new tests this session — M9 was verification/consolidation, not new functionality).
- **What "v1.0" means in practice**: the system fully implements CLAUDE.md's architecture end-to-end — all 10 architectural invariants, the 13-stage pipeline with both checkpoints, the 15-tool Copilot with Plan→Review→Approve→Execute→Audit, and Corporate Actions. It has NOT yet been used with real financial data: no real Holding (quantities/cost basis) has been entered for any of the 6 currently-held positions (ADA/BMM/CLOUD/PALM/NARE/ABR), and 5 of the 12 Phase 1 companies (ADA/BMM/CLOUD/ABR/EFGD) have zero data available from any of the 4 sources checked (a real, permanent EGX coverage gap, not a bug). Both are pre-existing, previously-flagged, user-actionable items — not defects introduced by this build.

---

## Notes
- Architecture document: `docs/EGX_Investment_OS_Architecture_v1.0.docx`
- EGX tickers use `.CA` suffix in yfinance (e.g., COMI.CA)
- Mubasher XHR discovery is the highest-risk task in M3 (time-box 2 days)
- Stage 6a is a synchronization BARRIER — all companies must complete Stage 6 before ANY proceeds to Stage 6b
- Local dev environment uses a `uv`-managed Python 3.12 venv at `.venv/` (system Python is 3.9). Activate with `source .venv/bin/activate`, or invoke directly via `.venv/bin/python` / `.venv/bin/pytest`.
- Real Holding data (quantities, cost basis for ADA/BMM/CLOUD/PALM/NARE/ABR) has not been entered yet — only company + watchlist records are seeded. Needs to be entered before M5's dashboard can show real allocation.
- yfinance has no price data at all for ADA, BMM, CLOUD, NARE, ABR, EFGD (6 of 12 Phase 1 companies — mostly small funds/thin instruments). TradingView covers NARE but still misses the other 5. This is a real EGX data-coverage gap, not a code bug — M2's Fundamentals Collector (StockAnalysis.com) may or may not have better coverage for these; worth checking early in M2.
- **Update (M2)**: confirmed — StockAnalysis.com also 404s on ADA, BMM, CLOUD, ABR, EFGD, and also covers NARE (like TradingView). So the real, permanent Phase 1 coverage gap across all 3 sources checked so far is: **ADA, BMM, CLOUD, ABR, EFGD (5 of 12) have no data anywhere.** Treat this as a known data limitation going forward rather than re-investigating per milestone — these likely need a different/manual data source (e.g. EGX's own disclosure site) if they're ever to be scored.
- **Update (M3)**: confirmed a 4th time — Mubasher also has zero news coverage for ADA, BMM, CLOUD, ABR, EFGD. This gap is now consistent across every data source checked (yfinance, TradingView, StockAnalysis.com, Mubasher). Treat as settled: these 5 companies cannot be scored with any automated source currently in this codebase. If they ever need to be, the EGX Disclosure Collector's manual-entry path is the only route.
- config.yaml is not yet wired up to any runtime code (no YAML parser dependency resolved yet — see M1 session log). Jobs currently use hardcoded defaults matching its stated values.
- CAR/NPL ratios (mentioned in the architecture doc as a BANK-schema deliverable) are NOT implemented — `financial_statements` schema has no fields for regulatory capital/RWA/NPL balances, and StockAnalysis.com's balance sheet page doesn't expose them either (only "Gross Loans" and a loan-loss reserve, not an NPL figure). `FinancialMetrics` simply omits these fields for now.
