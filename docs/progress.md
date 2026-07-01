# EGX Portfolio Manager — Development Progress

## Current Status
**Active Milestone: M2 — Fundamentals + Financial Engine**
**Last Updated: 2026-07-01**

---

## Milestone Status

| Milestone | Status | Completed Date |
|-----------|--------|----------------|
| M0 — Foundation | ✅ Done | 2026-07-01 |
| M1 — Price + Technical Engine | ✅ Done | 2026-07-01 |
| M2 — Fundamentals + Financial Engine | ⏳ Not Started | — |
| M3 — News + News Processing Engine | ⏳ Not Started | — |
| M4 — Scoring + Risk + Confidence | ⏳ Not Started | — |
| M5 — First Complete Job + Minimal Dashboard | ⏳ Not Started | — |
| M6 — Swing Job + Full Dashboard | ⏳ Not Started | — |
| M7 — Portfolio Review + Copilot | ⏳ Not Started | — |
| M8 — Hardening | ⏳ Not Started | — |
| M9 — Specification Freeze | ⏳ Not Started | — |

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

---

## Notes
- Architecture document: `docs/EGX_Investment_OS_Architecture_v1.0.docx`
- EGX tickers use `.CA` suffix in yfinance (e.g., COMI.CA)
- Mubasher XHR discovery is the highest-risk task in M3 (time-box 2 days)
- Stage 6a is a synchronization BARRIER — all companies must complete Stage 6 before ANY proceeds to Stage 6b
- Local dev environment uses a `uv`-managed Python 3.12 venv at `.venv/` (system Python is 3.9). Activate with `source .venv/bin/activate`, or invoke directly via `.venv/bin/python` / `.venv/bin/pytest`.
- Real Holding data (quantities, cost basis for ADA/BMM/CLOUD/PALM/NARE/ABR) has not been entered yet — only company + watchlist records are seeded. Needs to be entered before M5's dashboard can show real allocation.
- yfinance has no price data at all for ADA, BMM, CLOUD, NARE, ABR, EFGD (6 of 12 Phase 1 companies — mostly small funds/thin instruments). TradingView covers NARE but still misses the other 5. This is a real EGX data-coverage gap, not a code bug — M2's Fundamentals Collector (StockAnalysis.com) may or may not have better coverage for these; worth checking early in M2.
- config.yaml is not yet wired up to any runtime code (no YAML parser dependency resolved yet — see M1 session log). Jobs currently use hardcoded defaults matching its stated values.
