import json

import pytest

from egxpm.llm.context_aggregator import CuratedContext
from egxpm.llm.context_export import build_raw_context, export_context
from egxpm.persistence.company_repository import CompanyRepository
from egxpm.persistence.models import (
    ConfidenceScore,
    ConfigurationSnapshot,
    FinancialStatement,
    NewsItem,
    PeriodType,
    RiskScore,
    Score,
    SectorSummary,
    MarketSummary,
    TechnicalSnapshot,
    TrendSignal,
)
from egxpm.persistence.sector_market_repository import SectorMarketRepository

COMPANY_ID = "COMI"  # seeded by init_db via PHASE1_COMPANIES, sector "Banking"


def _curated_context():
    return CuratedContext(
        company={"company_id": COMPANY_ID}, score_summary={"composite_score": 70.0},
        confidence_summary={"confidence_value": 0.8}, portfolio_context={}, market_context={},
        position_sizing=None, historical_summary={}, data_freshness_flags=[],
    )


def test_build_raw_context_degrades_gracefully_with_no_data(db_path):
    company_repo = CompanyRepository(db_path)
    sector_repo = SectorMarketRepository(db_path)
    config = ConfigurationSnapshot()

    raw = build_raw_context(COMPANY_ID, company_repo, sector_repo, config)

    assert raw["company"]["company_id"] == COMPANY_ID
    assert raw["financial_statements"] == []
    assert raw["financial_metrics"] is None
    assert raw["technical_snapshot"] is None
    assert raw["news"] == []
    assert raw["score"] is None
    assert raw["risk_score"] is None
    assert raw["confidence_score"] is None
    assert raw["historical_scores"] == []
    assert raw["holdings"] == []
    assert raw["sector_summary"] is None
    assert raw["market_summary"] is None
    assert raw["configuration_snapshot"] == config.model_dump()


def test_build_raw_context_unknown_company_returns_none_company(db_path):
    company_repo = CompanyRepository(db_path)
    sector_repo = SectorMarketRepository(db_path)
    config = ConfigurationSnapshot()

    raw = build_raw_context("NOPE", company_repo, sector_repo, config)

    assert raw["company"] is None
    assert raw["holdings"] == []


def test_build_raw_context_includes_persisted_data(db_path):
    company_repo = CompanyRepository(db_path)
    sector_repo = SectorMarketRepository(db_path)
    config = ConfigurationSnapshot()

    stmt = FinancialStatement(
        company_id=COMPANY_ID, period_type=PeriodType.ANNUAL, period_end="2025-12-31",
        revenue=1_000_000.0, net_income=100_000.0, data_source_id="stockanalysis",
        source_version="v1", collection_run_id="run-1",
    )
    company_repo.save_financial_statement(stmt)

    snapshot = TechnicalSnapshot(
        company_id=COMPANY_ID, trend=TrendSignal.BULLISH, engine_version="v1",
        computed_through_date="2026-07-01", job_id="job-1",
    )
    company_repo.save_technical_snapshot(snapshot)

    news = NewsItem(
        company_id=COMPANY_ID, headline="CIB reports strong Q4", publisher_name="Mubasher",
        published_at="2026-07-01T00:00:00+00:00", data_source_id="mubasher",
        source_version="v1", collection_run_id="run-1",
    )
    company_repo.save_news_item(news)

    score = Score(
        company_id=COMPANY_ID, composite_score=75.0, config_snapshot_id=config.config_snapshot_id,
        job_id="job-1",
    )
    company_repo.save_score(score)
    company_repo.save_risk_score(RiskScore(score_id=score.score_id, value=80.0))
    company_repo.save_confidence_score(ConfidenceScore(score_id=score.score_id, confidence_value=0.9))

    sector_summary = SectorSummary(sector="Banking", summary_score=65.0, job_id="job-1")
    sector_repo.save_sector_summary(sector_summary)
    market_summary = MarketSummary(summary_score=60.0, job_id="job-1")
    sector_repo.save_market_summary(market_summary)

    raw = build_raw_context(COMPANY_ID, company_repo, sector_repo, config)

    assert raw["financial_statements"][0]["revenue"] == 1_000_000.0
    assert raw["technical_snapshot"]["trend"] == TrendSignal.BULLISH.value
    assert raw["news"][0]["headline"] == "CIB reports strong Q4"
    assert raw["score"]["composite_score"] == 75.0
    assert raw["risk_score"]["value"] == 80.0
    assert raw["confidence_score"]["confidence_value"] == 0.9
    assert len(raw["historical_scores"]) == 1
    assert raw["sector_summary"]["summary_score"] == 65.0
    assert raw["market_summary"]["summary_score"] == 60.0


def test_export_context_writes_json_and_markdown(db_path, tmp_path):
    company_repo = CompanyRepository(db_path)
    sector_repo = SectorMarketRepository(db_path)
    config = ConfigurationSnapshot()
    raw = build_raw_context(COMPANY_ID, company_repo, sector_repo, config)
    curated = _curated_context()

    out_dir = export_context(
        COMPANY_ID, raw, curated, prompt_version="v1", model="claude-haiku-4-5", job_id="job-1",
        export_dir=str(tmp_path / "exports"), export_date="2026-07-03",
    )

    assert out_dir == tmp_path / "exports" / "2026-07-03" / COMPANY_ID
    payload = json.loads((out_dir / "context.json").read_text())
    assert payload["company_id"] == COMPANY_ID
    assert payload["job_id"] == "job-1"
    assert payload["model"] == "claude-haiku-4-5"
    assert payload["prompt_version"] == "v1"
    assert payload["raw_context"]["company"]["company_id"] == COMPANY_ID
    assert payload["curated_context"]["score_summary"]["composite_score"] == 70.0

    markdown = (out_dir / "context.md").read_text()
    assert f"AI context — {COMPANY_ID}" in markdown
    assert "Curated context" in markdown
    assert "Raw context" in markdown


def test_export_context_defaults_to_todays_date(db_path, tmp_path):
    import datetime

    company_repo = CompanyRepository(db_path)
    sector_repo = SectorMarketRepository(db_path)
    config = ConfigurationSnapshot()
    raw = build_raw_context(COMPANY_ID, company_repo, sector_repo, config)
    curated = _curated_context()

    out_dir = export_context(
        COMPANY_ID, raw, curated, prompt_version="v1", model="claude-haiku-4-5",
        export_dir=str(tmp_path / "exports"),
    )

    today = datetime.date.today().isoformat()
    assert out_dir == tmp_path / "exports" / today / COMPANY_ID
