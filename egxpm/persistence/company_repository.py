"""All persistence for the Company aggregate root.

Per the architecture's aggregate-root principle, everything that attaches
to a Company — financials, prices, technicals, news, scores — is owned by
this repository. Engines and Jobs never write SQL directly; they call
these methods.
"""

from __future__ import annotations

from typing import Optional

from egxpm.persistence import _util
from egxpm.persistence.db import connect
from egxpm.persistence.models import (
    Company,
    CompanySectorHistory,
    ConfidenceScore,
    CorporateAction,
    FinancialStatement,
    Holding,
    NewsItem,
    PriceCandle,
    RiskScore,
    Score,
    TechnicalReferenceSnapshot,
    TechnicalSnapshot,
    Timeframe,
    WatchlistHistory,
    WatchlistState,
)


class CompanyRepository:
    def __init__(self, db_path: str):
        self.db_path = db_path

    # ------------------------------------------------------------
    # Company
    # ------------------------------------------------------------

    def create_company(self, company: Company) -> None:
        with connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO companies
                    (company_id, name, sector, industry, isin, listing_status,
                     statement_schema, rollout_phase, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    company.company_id, company.name, company.sector, company.industry,
                    company.isin, company.listing_status.value, company.statement_schema.value,
                    company.rollout_phase.value, company.created_at, company.updated_at,
                ),
            )
            conn.execute(
                """
                INSERT INTO company_sector_history
                    (history_id, company_id, sector, effective_from, effective_to, created_at)
                VALUES (?, ?, ?, ?, NULL, ?)
                """,
                (
                    f"{company.company_id}-sector-{company.created_at}",
                    company.company_id, company.sector, company.created_at, company.created_at,
                ),
            )

    def get_company(self, company_id: str) -> Optional[Company]:
        with connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT * FROM companies WHERE company_id = ?", (company_id,)
            ).fetchone()
            return Company(**_util.row_to_dict(row)) if row else None

    def list_companies(
        self, rollout_phase: Optional[str] = None, listing_status: Optional[str] = None
    ) -> list[Company]:
        query = "SELECT * FROM companies WHERE 1=1"
        params: list[str] = []
        if rollout_phase is not None:
            query += " AND rollout_phase = ?"
            params.append(rollout_phase)
        if listing_status is not None:
            query += " AND listing_status = ?"
            params.append(listing_status)
        query += " ORDER BY company_id"
        with connect(self.db_path) as conn:
            rows = conn.execute(query, params).fetchall()
            return [Company(**_util.row_to_dict(r)) for r in rows]

    def change_sector(self, company_id: str, new_sector: str, effective_from: str) -> None:
        """Records a sector change. Never overwrites prior history (Amendment 1)."""
        with connect(self.db_path) as conn:
            conn.execute(
                """
                UPDATE company_sector_history
                SET effective_to = ?
                WHERE company_id = ? AND effective_to IS NULL
                """,
                (effective_from, company_id),
            )
            conn.execute(
                """
                INSERT INTO company_sector_history
                    (history_id, company_id, sector, effective_from, effective_to, created_at)
                VALUES (?, ?, ?, ?, NULL, ?)
                """,
                (f"{company_id}-sector-{effective_from}", company_id, new_sector, effective_from, effective_from),
            )
            conn.execute(
                "UPDATE companies SET sector = ?, updated_at = ? WHERE company_id = ?",
                (new_sector, effective_from, company_id),
            )

    def get_sector_history(self, company_id: str) -> list[CompanySectorHistory]:
        with connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT * FROM company_sector_history WHERE company_id = ? ORDER BY effective_from",
                (company_id,),
            ).fetchall()
            return [CompanySectorHistory(**_util.row_to_dict(r)) for r in rows]

    # ------------------------------------------------------------
    # Watchlist (append-only state machine)
    # ------------------------------------------------------------

    def append_watchlist_transition(self, entry: WatchlistHistory) -> None:
        with connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO watchlist_history
                    (history_id, company_id, state, state_changed_at,
                     transition_type, reference_type, reference_id, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    entry.history_id, entry.company_id, entry.state.value,
                    entry.state_changed_at, entry.transition_type.value,
                    entry.reference_type, entry.reference_id, entry.created_at,
                ),
            )

    def get_watchlist_state(self, company_id: str) -> Optional[WatchlistState]:
        with connect(self.db_path) as conn:
            row = conn.execute(
                """
                SELECT state FROM watchlist_history
                WHERE company_id = ?
                ORDER BY state_changed_at DESC, rowid DESC
                LIMIT 1
                """,
                (company_id,),
            ).fetchone()
            return WatchlistState(row["state"]) if row else None

    def get_watchlist_history(self, company_id: str) -> list[WatchlistHistory]:
        with connect(self.db_path) as conn:
            rows = conn.execute(
                """
                SELECT * FROM watchlist_history WHERE company_id = ?
                ORDER BY state_changed_at ASC, rowid ASC
                """,
                (company_id,),
            ).fetchall()
            return [WatchlistHistory(**_util.row_to_dict(r)) for r in rows]

    def list_companies_in_state(self, state: WatchlistState) -> list[str]:
        with connect(self.db_path) as conn:
            rows = conn.execute(
                """
                SELECT company_id, state FROM watchlist_history w
                WHERE w.rowid = (
                    SELECT rowid FROM watchlist_history
                    WHERE company_id = w.company_id
                    ORDER BY state_changed_at DESC, rowid DESC
                    LIMIT 1
                )
                """
            ).fetchall()
            return [r["company_id"] for r in rows if r["state"] == state.value]

    # ------------------------------------------------------------
    # Holdings
    # ------------------------------------------------------------

    def save_holding(self, holding: Holding) -> None:
        with connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO holdings
                    (holding_id, company_id, category, quantity, average_cost, acquired_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(holding_id) DO UPDATE SET
                    category = excluded.category,
                    quantity = excluded.quantity,
                    average_cost = excluded.average_cost,
                    updated_at = excluded.updated_at
                """,
                (
                    holding.holding_id, holding.company_id, holding.category.value,
                    holding.quantity, holding.average_cost, holding.acquired_at, holding.updated_at,
                ),
            )

    def get_holding(self, holding_id: str) -> Optional[Holding]:
        with connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT * FROM holdings WHERE holding_id = ?", (holding_id,)
            ).fetchone()
            return Holding(**_util.row_to_dict(row)) if row else None

    def list_holdings(
        self, company_id: Optional[str] = None, category: Optional[str] = None
    ) -> list[Holding]:
        query = "SELECT * FROM holdings WHERE 1=1"
        params: list[str] = []
        if company_id is not None:
            query += " AND company_id = ?"
            params.append(company_id)
        if category is not None:
            query += " AND category = ?"
            params.append(category)
        with connect(self.db_path) as conn:
            rows = conn.execute(query, params).fetchall()
            return [Holding(**_util.row_to_dict(r)) for r in rows]

    def delete_holding(self, holding_id: str) -> None:
        with connect(self.db_path) as conn:
            conn.execute("DELETE FROM holdings WHERE holding_id = ?", (holding_id,))

    # ------------------------------------------------------------
    # FinancialStatement (append-only)
    # ------------------------------------------------------------

    def save_financial_statement(self, stmt: FinancialStatement) -> None:
        with connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO financial_statements
                    (statement_id, company_id, period_type, period_end, revenue, net_income,
                     eps_basic, eps_diluted, total_assets, total_liabilities, total_equity,
                     operating_income, operating_cash_flow, capex, free_cash_flow,
                     net_interest_income, data_source_id, source_version, fetched_at,
                     collection_run_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    stmt.statement_id, stmt.company_id, stmt.period_type.value, stmt.period_end,
                    stmt.revenue, stmt.net_income, stmt.eps_basic, stmt.eps_diluted,
                    stmt.total_assets, stmt.total_liabilities, stmt.total_equity,
                    stmt.operating_income, stmt.operating_cash_flow, stmt.capex,
                    stmt.free_cash_flow, stmt.net_interest_income, stmt.data_source_id,
                    stmt.source_version, stmt.fetched_at, stmt.collection_run_id,
                ),
            )

    def list_financial_statements(
        self, company_id: str, period_type: Optional[str] = None
    ) -> list[FinancialStatement]:
        query = "SELECT * FROM financial_statements WHERE company_id = ?"
        params: list[str] = [company_id]
        if period_type is not None:
            query += " AND period_type = ?"
            params.append(period_type)
        query += " ORDER BY period_end"
        with connect(self.db_path) as conn:
            rows = conn.execute(query, params).fetchall()
            return [FinancialStatement(**_util.row_to_dict(r)) for r in rows]

    # ------------------------------------------------------------
    # PriceCandle (append-only)
    # ------------------------------------------------------------

    def save_price_candles(self, candles: list[PriceCandle]) -> None:
        with connect(self.db_path) as conn:
            conn.executemany(
                """
                INSERT INTO price_candles
                    (candle_id, company_id, timeframe, candle_date, open, high, low, close,
                     volume, adjusted_for_corporate_action, data_source_id, source_version,
                     fetched_at, collection_run_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        c.candle_id, c.company_id, c.timeframe.value, c.candle_date, c.open,
                        c.high, c.low, c.close, c.volume, int(c.adjusted_for_corporate_action),
                        c.data_source_id, c.source_version, c.fetched_at, c.collection_run_id,
                    )
                    for c in candles
                ],
            )

    def list_price_candles(
        self,
        company_id: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        timeframe: Timeframe = Timeframe.DAILY,
    ) -> list[PriceCandle]:
        query = "SELECT * FROM price_candles WHERE company_id = ? AND timeframe = ?"
        params: list[str] = [company_id, timeframe.value]
        if start_date is not None:
            query += " AND candle_date >= ?"
            params.append(start_date)
        if end_date is not None:
            query += " AND candle_date <= ?"
            params.append(end_date)
        query += " ORDER BY candle_date"
        with connect(self.db_path) as conn:
            rows = conn.execute(query, params).fetchall()
            return [
                PriceCandle(**{**_util.row_to_dict(r), "adjusted_for_corporate_action": bool(r["adjusted_for_corporate_action"])})
                for r in rows
            ]

    # ------------------------------------------------------------
    # CorporateAction (append-only, manual entry)
    # ------------------------------------------------------------

    def save_corporate_action(self, action: CorporateAction) -> None:
        with connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO corporate_actions
                    (action_id, company_id, action_type, action_date, details,
                     data_source_id, entered_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    action.action_id, action.company_id, action.action_type, action.action_date,
                    _util.dumps(action.details), action.data_source_id, action.entered_at,
                ),
            )

    def list_corporate_actions(self, company_id: str) -> list[CorporateAction]:
        with connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT * FROM corporate_actions WHERE company_id = ? ORDER BY action_date",
                (company_id,),
            ).fetchall()
            return [
                CorporateAction(**{**_util.row_to_dict(r), "details": _util.loads(r["details"], {})})
                for r in rows
            ]

    # ------------------------------------------------------------
    # NewsItem (append-only)
    # ------------------------------------------------------------

    def save_news_item(self, item: NewsItem) -> None:
        with connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO news_items
                    (news_id, company_id, sector_scope, headline, publisher_name,
                     published_at, url, sentiment_score, relevance_score, lexicon_version,
                     data_source_id, source_version, fetched_at, collection_run_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    item.news_id, item.company_id, item.sector_scope, item.headline,
                    item.publisher_name, item.published_at, item.url, item.sentiment_score,
                    item.relevance_score, item.lexicon_version, item.data_source_id,
                    item.source_version, item.fetched_at, item.collection_run_id,
                ),
            )

    def list_news_items(
        self, company_id: Optional[str] = None, since: Optional[str] = None
    ) -> list[NewsItem]:
        query = "SELECT * FROM news_items WHERE 1=1"
        params: list[str] = []
        if company_id is not None:
            query += " AND company_id = ?"
            params.append(company_id)
        if since is not None:
            query += " AND published_at >= ?"
            params.append(since)
        query += " ORDER BY published_at DESC"
        with connect(self.db_path) as conn:
            rows = conn.execute(query, params).fetchall()
            return [NewsItem(**_util.row_to_dict(r)) for r in rows]

    # ------------------------------------------------------------
    # TechnicalReferenceSnapshot (append-only, reference only)
    # ------------------------------------------------------------

    def save_technical_reference_snapshot(self, snap: TechnicalReferenceSnapshot) -> None:
        with connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO technical_reference_snapshots
                    (ref_id, company_id, rating, raw_indicators, data_source_id,
                     fetched_at, collection_run_id)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    snap.ref_id, snap.company_id, snap.rating, _util.dumps(snap.raw_indicators),
                    snap.data_source_id, snap.fetched_at, snap.collection_run_id,
                ),
            )

    def get_latest_technical_reference_snapshot(
        self, company_id: str
    ) -> Optional[TechnicalReferenceSnapshot]:
        with connect(self.db_path) as conn:
            row = conn.execute(
                """
                SELECT * FROM technical_reference_snapshots WHERE company_id = ?
                ORDER BY fetched_at DESC, rowid DESC LIMIT 1
                """,
                (company_id,),
            ).fetchone()
            if not row:
                return None
            return TechnicalReferenceSnapshot(
                **{**_util.row_to_dict(row), "raw_indicators": _util.loads(row["raw_indicators"], {})}
            )

    # ------------------------------------------------------------
    # TechnicalSnapshot (append-only, engine output — Checkpoint A)
    # ------------------------------------------------------------

    def save_technical_snapshot(self, snap: TechnicalSnapshot, conn=None) -> None:
        sql = """
            INSERT INTO technical_snapshots
                (snapshot_id, company_id, computed_at, rsi, macd, macd_signal, sma_20,
                 sma_50, sma_200, ema_20, ema_50, atr, bollinger_upper, bollinger_lower,
                 bollinger_bandwidth, volume_ma_20, support_level, resistance_level, trend,
                 breakout, unusual_volume, engine_version, timeframe, window_size,
                 computed_through_date, job_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        params = (
            snap.snapshot_id, snap.company_id, snap.computed_at, snap.rsi, snap.macd,
            snap.macd_signal, snap.sma_20, snap.sma_50, snap.sma_200, snap.ema_20,
            snap.ema_50, snap.atr, snap.bollinger_upper, snap.bollinger_lower,
            snap.bollinger_bandwidth, snap.volume_ma_20, snap.support_level,
            snap.resistance_level, snap.trend.value if snap.trend else None,
            None if snap.breakout is None else int(snap.breakout),
            None if snap.unusual_volume is None else int(snap.unusual_volume),
            snap.engine_version, snap.timeframe.value, snap.window_size,
            snap.computed_through_date, snap.job_id,
        )
        if conn is not None:
            conn.execute(sql, params)
        else:
            with connect(self.db_path) as c:
                c.execute(sql, params)

    def get_latest_technical_snapshot(self, company_id: str) -> Optional[TechnicalSnapshot]:
        with connect(self.db_path) as conn:
            row = conn.execute(
                """
                SELECT * FROM technical_snapshots WHERE company_id = ?
                ORDER BY computed_at DESC, rowid DESC LIMIT 1
                """,
                (company_id,),
            ).fetchone()
            return self._row_to_technical_snapshot(row) if row else None

    def list_technical_snapshots(self, company_id: str) -> list[TechnicalSnapshot]:
        with connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT * FROM technical_snapshots WHERE company_id = ? ORDER BY computed_at",
                (company_id,),
            ).fetchall()
            return [self._row_to_technical_snapshot(r) for r in rows]

    @staticmethod
    def _row_to_technical_snapshot(row) -> TechnicalSnapshot:
        d = _util.row_to_dict(row)
        d["breakout"] = None if d["breakout"] is None else bool(d["breakout"])
        d["unusual_volume"] = None if d["unusual_volume"] is None else bool(d["unusual_volume"])
        return TechnicalSnapshot(**d)

    # ------------------------------------------------------------
    # Score (append-only, engine output — Checkpoint A)
    # ------------------------------------------------------------

    def save_score(self, score: Score, conn=None) -> None:
        sql = """
            INSERT INTO scores
                (score_id, company_id, computed_at, financial_score, financial_breakdown,
                 technical_score, technical_breakdown, news_score, news_breakdown,
                 composite_score, config_snapshot_id, job_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        params = (
            score.score_id, score.company_id, score.computed_at, score.financial_score,
            _util.dumps(score.financial_breakdown), score.technical_score,
            _util.dumps(score.technical_breakdown), score.news_score,
            _util.dumps(score.news_breakdown), score.composite_score,
            score.config_snapshot_id, score.job_id,
        )
        if conn is not None:
            conn.execute(sql, params)
        else:
            with connect(self.db_path) as c:
                c.execute(sql, params)

    def get_score(self, score_id: str) -> Optional[Score]:
        with connect(self.db_path) as conn:
            row = conn.execute("SELECT * FROM scores WHERE score_id = ?", (score_id,)).fetchone()
            return self._row_to_score(row) if row else None

    def get_latest_score(self, company_id: str) -> Optional[Score]:
        with connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT * FROM scores WHERE company_id = ? ORDER BY computed_at DESC, rowid DESC LIMIT 1",
                (company_id,),
            ).fetchone()
            return self._row_to_score(row) if row else None

    def list_scores(self, company_id: str) -> list[Score]:
        with connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT * FROM scores WHERE company_id = ? ORDER BY computed_at", (company_id,)
            ).fetchall()
            return [self._row_to_score(r) for r in rows]

    @staticmethod
    def _row_to_score(row) -> Score:
        d = _util.row_to_dict(row)
        d["financial_breakdown"] = _util.loads(d["financial_breakdown"], {})
        d["technical_breakdown"] = _util.loads(d["technical_breakdown"], {})
        d["news_breakdown"] = _util.loads(d["news_breakdown"], {})
        return Score(**d)

    # ------------------------------------------------------------
    # RiskScore (append-only, engine output — Checkpoint A)
    # ------------------------------------------------------------

    def save_risk_score(self, risk_score: RiskScore, conn=None) -> None:
        sql = """
            INSERT INTO risk_scores
                (risk_score_id, score_id, value, debt_peer_component,
                 score_volatility_component, data_completeness_component,
                 liquidity_component, breakdown)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """
        params = (
            risk_score.risk_score_id, risk_score.score_id, risk_score.value,
            risk_score.debt_peer_component, risk_score.score_volatility_component,
            risk_score.data_completeness_component, risk_score.liquidity_component,
            _util.dumps(risk_score.breakdown),
        )
        if conn is not None:
            conn.execute(sql, params)
        else:
            with connect(self.db_path) as c:
                c.execute(sql, params)

    def get_risk_score_by_score_id(self, score_id: str) -> Optional[RiskScore]:
        with connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT * FROM risk_scores WHERE score_id = ?", (score_id,)
            ).fetchone()
            if not row:
                return None
            d = _util.row_to_dict(row)
            d["breakdown"] = _util.loads(d["breakdown"], {})
            return RiskScore(**d)

    # ------------------------------------------------------------
    # ConfidenceScore (append-only, engine output — Checkpoint A)
    # ------------------------------------------------------------

    def save_confidence_score(self, confidence: ConfidenceScore, conn=None) -> None:
        sql = """
            INSERT INTO confidence_scores
                (confidence_id, score_id, confidence_value, freshness_component,
                 source_quality_component, source_health_component,
                 historical_accuracy_component, breakdown)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """
        params = (
            confidence.confidence_id, confidence.score_id, confidence.confidence_value,
            confidence.freshness_component, confidence.source_quality_component,
            confidence.source_health_component, confidence.historical_accuracy_component,
            _util.dumps(confidence.breakdown),
        )
        if conn is not None:
            conn.execute(sql, params)
        else:
            with connect(self.db_path) as c:
                c.execute(sql, params)

    def get_confidence_score_by_score_id(self, score_id: str) -> Optional[ConfidenceScore]:
        with connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT * FROM confidence_scores WHERE score_id = ?", (score_id,)
            ).fetchone()
            if not row:
                return None
            d = _util.row_to_dict(row)
            d["breakdown"] = _util.loads(d["breakdown"], {})
            return ConfidenceScore(**d)

    # ------------------------------------------------------------
    # Checkpoint A (Stage 10) — one atomic transaction across all four
    # Stage 6-7 artifacts. Either all four rows land, or none do.
    # ------------------------------------------------------------

    def save_checkpoint_a(
        self,
        technical_snapshot: TechnicalSnapshot,
        score: Score,
        risk_score: RiskScore,
        confidence_score: ConfidenceScore,
    ) -> None:
        with connect(self.db_path) as conn:
            self.save_technical_snapshot(technical_snapshot, conn=conn)
            self.save_score(score, conn=conn)
            self.save_risk_score(risk_score, conn=conn)
            self.save_confidence_score(confidence_score, conn=conn)
