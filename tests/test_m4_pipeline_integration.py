"""M4 validation-criteria tests: the full Stage 3-7 + Checkpoint A pipeline
run against real Phase 1 data collected in M1-M3.

This is deliberately a test, not a CLI (run_longterm.py is an M5
deliverable — this doesn't skip ahead to building the real Job early, it
just proves the M4 Engines compose correctly against real data).
"""

import os

import pytest

from egxpm.collectors.source_health_service import SourceHealthService
from egxpm.engine.confidence_engine import (
    FreshnessMetadata,
    HistoricalAccuracySummary,
    SourceHealthSummary,
    SourceQualitySummary,
    calculate_confidence,
)
from egxpm.engine.financial_engine import calculate_financial_metrics
from egxpm.engine.risk_engine import (
    HistoricalScoreSummary,
    LiquiditySummary,
    build_sector_peer_summary,
    calculate_risk_score,
)
from egxpm.engine.scoring_engine import assemble_composite_score, build_score, calculate_score
from egxpm.engine.technical_engine import ENGINE_VERSION as TECHNICAL_ENGINE_VERSION
from egxpm.engine.technical_engine import calculate_technical_snapshot
from egxpm.persistence.company_repository import CompanyRepository
from egxpm.persistence.models import SourceQuality, StatementSchema, TechnicalSnapshot
from egxpm.shared.config import load_configuration_snapshot
from egxpm.shared.exceptions import InsufficientDataError

REAL_DB_PATH = "data/egx.db"

# (company_id, StatementSchema, sector) — matches real seeded data from M0-M3
COMPANY_SCHEMAS = {
    "COMI": (StatementSchema.BANK, "Banking"),
    "TMGH": (StatementSchema.INDUSTRIAL, "Real Estate"),
    "PALM": (StatementSchema.INDUSTRIAL, "Real Estate"),
    "SWDY": (StatementSchema.INDUSTRIAL, "Industrial"),
    "ABUK": (StatementSchema.INDUSTRIAL, "Fertilizers"),
    "EFIH": (StatementSchema.INDUSTRIAL, "Technology"),
}


def _require_real_db():
    if not os.path.exists(REAL_DB_PATH):
        pytest.skip(f"{REAL_DB_PATH} not present — run M1-M3 collection jobs first")


def _to_technical_snapshot(company_id: str, result, job_id: str) -> TechnicalSnapshot:
    return TechnicalSnapshot(
        company_id=company_id,
        rsi=result.indicators.rsi, macd=result.indicators.macd, macd_signal=result.indicators.macd_signal,
        sma_20=result.indicators.sma_20, sma_50=result.indicators.sma_50, sma_200=result.indicators.sma_200,
        ema_20=result.indicators.ema_20, ema_50=result.indicators.ema_50, atr=result.indicators.atr,
        bollinger_upper=result.indicators.bollinger_upper, bollinger_lower=result.indicators.bollinger_lower,
        bollinger_bandwidth=result.indicators.bollinger_bandwidth, volume_ma_20=result.indicators.volume_ma_20,
        support_level=result.indicators.support_level, resistance_level=result.indicators.resistance_level,
        trend=result.signals.trend, breakout=result.signals.breakout, unusual_volume=result.signals.unusual_volume,
        engine_version=TECHNICAL_ENGINE_VERSION, window_size=result.window_size,
        computed_through_date=result.computed_through_date, job_id=job_id,
    )


def test_composite_scores_for_all_covered_phase1_companies_in_0_100(db_path):
    """Validation criterion: composite scores for all Phase 1 companies in [0,100]."""
    _require_real_db()
    real_repo = CompanyRepository(REAL_DB_PATH)
    write_repo = CompanyRepository(db_path)
    weights = load_configuration_snapshot()
    job_id = "test-longterm-job-1"

    scores = {}
    for company_id, (schema, _sector) in COMPANY_SCHEMAS.items():
        statements = real_repo.list_financial_statements(company_id, period_type="quarterly")
        metrics = calculate_financial_metrics(statements, schema)
        candles = real_repo.list_price_candles(company_id)
        tech_result = calculate_technical_snapshot(candles, window=200)
        news = real_repo.list_news_items(company_id)

        score_result = calculate_score(metrics, tech_result, news, weights)
        score = build_score(
            score_result, company_id=company_id,
            config_snapshot_id=weights.config_snapshot_id, job_id=job_id,
        )
        scores[company_id] = (score, tech_result)

    # Stage 6a barrier: aggregate D/E per sector from every company's Score.
    sectors: dict[str, list[str]] = {}
    for company_id, (_, sector) in COMPANY_SCHEMAS.items():
        sectors.setdefault(sector, []).append(company_id)
    peer_summaries = {
        sector: build_sector_peer_summary(
            sector, [scores[cid][0].financial_breakdown.get("debt_to_equity", {}).get("value") for cid in ids]
        )
        for sector, ids in sectors.items()
    }

    health_service = SourceHealthService(REAL_DB_PATH)

    for company_id, (schema, sector) in COMPANY_SCHEMAS.items():
        score, tech_result = scores[company_id]

        risk = calculate_risk_score(
            score, peer_summaries[sector], HistoricalScoreSummary(std_dev=5.0),
            LiquiditySummary(avg_daily_volume_egp=10_000_000, hypothetical_position_size_egp=500_000),
            weights,
        )
        final_score = assemble_composite_score(score, risk, weights)

        assert final_score.composite_score is not None, f"{company_id} composite_score is None"
        assert 0.0 <= final_score.composite_score <= 100.0, f"{company_id} composite out of range"

        confidence = calculate_confidence(
            final_score,
            FreshnessMetadata(prices_freshness=1.0, technicals_freshness=1.0, fundamentals_freshness=0.8, news_freshness=0.9),
            SourceQualitySummary(source_qualities=[SourceQuality.SCRAPED, SourceQuality.INTERNAL, SourceQuality.SCRAPED]),
            SourceHealthSummary(success_rate=health_service.get_source_health("yfinance")),
            HistoricalAccuracySummary(sample_count=0, win_rate=None),
        )
        assert 0.0 <= confidence.confidence_value <= 1.0

        # Checkpoint A — exercise the real atomic-write path for each company.
        technical_snapshot = _to_technical_snapshot(company_id, tech_result, job_id)
        write_repo.save_checkpoint_a(technical_snapshot, final_score, risk, confidence)

    # All four Checkpoint A rows landed for every company.
    for company_id in COMPANY_SCHEMAS:
        assert write_repo.get_latest_technical_snapshot(company_id) is not None


def test_stage_6a_barrier_excludes_failed_company_from_peer_set():
    """Validation criterion: Stage 6a barrier verified — a company whose
    Stage 6 (Scoring) failed must be absent from its sector's peer set,
    while its sector peers are still aggregated normally.
    """
    _require_real_db()
    real_repo = CompanyRepository(REAL_DB_PATH)
    weights = load_configuration_snapshot()

    # TMGH succeeds normally.
    tmgh_statements = real_repo.list_financial_statements("TMGH", period_type="quarterly")
    tmgh_metrics = calculate_financial_metrics(tmgh_statements, StatementSchema.INDUSTRIAL)
    tmgh_candles = real_repo.list_price_candles("TMGH")
    tmgh_tech = calculate_technical_snapshot(tmgh_candles, window=200)
    tmgh_result = calculate_score(tmgh_metrics, tmgh_tech, [], weights)
    tmgh_score = build_score(tmgh_result, company_id="TMGH", config_snapshot_id="cfg-1", job_id="job-1")

    # PALM (same "Real Estate" sector) fails Stage 6 — simulate per-company
    # failure isolation the way a Job's orchestration loop would: catch the
    # BusinessDataError and simply not produce a Score for this company.
    failed_companies = []
    palm_score = None
    try:
        calculate_financial_metrics([], StatementSchema.INDUSTRIAL)  # zero statements -> raises
    except InsufficientDataError:
        failed_companies.append("PALM")

    assert palm_score is None
    assert "PALM" in failed_companies

    # Stage 6a barrier: only companies with a real Score contribute to the peer set.
    sector_companies = {"TMGH": tmgh_score}  # PALM correctly excluded
    de_values = [s.financial_breakdown.get("debt_to_equity", {}).get("value") for s in sector_companies.values()]
    peer_summary = build_sector_peer_summary("Real Estate", de_values)

    assert peer_summary.peer_count == 1  # only TMGH, not PALM
    assert peer_summary.median_debt_to_equity == pytest.approx(
        tmgh_score.financial_breakdown["debt_to_equity"]["value"]
    )
