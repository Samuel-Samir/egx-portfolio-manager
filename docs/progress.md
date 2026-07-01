# EGX Portfolio Manager — Development Progress

## Current Status
**Active Milestone: M1 — Price + Technical Engine**
**Last Updated: 2026-07-01**

---

## Milestone Status

| Milestone | Status | Completed Date |
|-----------|--------|----------------|
| M0 — Foundation | ✅ Done | 2026-07-01 |
| M1 — Price + Technical Engine | 🔄 In Progress | — |
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

- [ ] shared/exceptions.py (business/data + programmer error taxonomy)
- [ ] collectors/collector_service.py (retry policy: transient 3x exponential backoff 2/4/8s; structural no retry)
- [ ] collectors/price_collector.py (yfinance, .CA tickers)
- [ ] collectors/technical_reference_collector.py (tradingview-ta, reference only)
- [ ] engine/technical_engine.py (pandas-ta-classic, all indicators + signals)
- [ ] Unit tests for all Technical Engine contracts
- [ ] run_collection.py entry point (--type price / technical_reference / technical)
- [ ] 5 years OHLCV collected for all Phase 1 companies (best effort — see coverage note)
- [ ] TechnicalSnapshot rows written to DB
- [ ] Per-company failure isolation verified

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

---

## Notes
- Architecture document: `docs/EGX_Investment_OS_Architecture_v1.0.docx`
- EGX tickers use `.CA` suffix in yfinance (e.g., COMI.CA)
- Mubasher XHR discovery is the highest-risk task in M3 (time-box 2 days)
- Stage 6a is a synchronization BARRIER — all companies must complete Stage 6 before ANY proceeds to Stage 6b
- Local dev environment uses a `uv`-managed Python 3.12 venv at `.venv/` (system Python is 3.9). Activate with `source .venv/bin/activate`, or invoke directly via `.venv/bin/python` / `.venv/bin/pytest`.
- Real Holding data (quantities, cost basis for ADA/BMM/CLOUD/PALM/NARE/ABR) has not been entered yet — only company + watchlist records are seeded. Needs to be entered before M5's dashboard can show real allocation.
