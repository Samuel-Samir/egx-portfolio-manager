from datetime import date, timedelta

from egxpm.persistence.company_repository import CompanyRepository
from egxpm.persistence.db import connect
from egxpm.persistence.models import (
    ConfidenceScore,
    ConfigurationSnapshot,
    PortfolioSnapshot,
    PortfolioSnapshotOrigin,
    PriceCandle,
    Recommendation,
    RecommendationAction,
    Score,
)
from egxpm.persistence.operational_repository import OperationalRepository
from egxpm.persistence.portfolio_repository import PortfolioRepository
from egxpm.persistence.recommendation_repository import RecommendationRepository
from egxpm.record_corporate_action import main

COMPANY_ID = "TMGH"  # seeded Phase 1 company


def _seed_price_candles(repo: CompanyRepository, action_date: date, close_before: float, close_after: float):
    start = action_date - timedelta(days=250)
    candles = []
    for i in range(260):
        d = start + timedelta(days=i)
        close = close_before if d < action_date else close_after
        candles.append(PriceCandle(
            company_id=COMPANY_ID, candle_date=d.isoformat(),
            open=close, high=close * 1.01, low=close * 0.99, close=close, volume=1000.0,
            data_source_id="yfinance", source_version="1", collection_run_id="seed-run",
        ))
    repo.save_price_candles(candles)


def _seed_active_recommendation(db_path) -> Recommendation:
    company_repo = CompanyRepository(db_path)
    operational_repo = OperationalRepository(db_path)
    portfolio_repo = PortfolioRepository(db_path)
    rec_repo = RecommendationRepository(db_path)

    score = Score(company_id=COMPANY_ID, config_snapshot_id="cfg-1", job_id="job-1", composite_score=60.0)
    company_repo.save_score(score)
    confidence = ConfidenceScore(score_id=score.score_id, confidence_value=0.8)
    company_repo.save_confidence_score(confidence)
    config_snapshot = ConfigurationSnapshot(allocation_targets={"long_term_stocks": 0.4})
    operational_repo.save_configuration_snapshot(config_snapshot)
    portfolio_snapshot = PortfolioSnapshot(origin=PortfolioSnapshotOrigin.BEFORE_RECOMMENDATION)
    portfolio_repo.save_snapshot(portfolio_snapshot)

    rec = Recommendation(
        company_id=COMPANY_ID, action=RecommendationAction.BUY, entry_price=50.0,
        confidence_id=confidence.confidence_id, config_snapshot_id=config_snapshot.config_snapshot_id,
        portfolio_snapshot_id=portfolio_snapshot.snapshot_id, frozen_package={}, job_id="job-1",
    )
    rec_repo.save_recommendation(rec)
    return rec


def test_dividend_records_action_and_supersedes_recommendation_without_touching_prices(db_path):
    company_repo = CompanyRepository(db_path)
    action_date = date(2026, 6, 1)
    _seed_price_candles(company_repo, action_date, close_before=10.0, close_after=10.0)
    prior_candles = company_repo.list_price_candles(COMPANY_ID)
    rec = _seed_active_recommendation(db_path)

    exit_code = main([
        "--company-id", COMPANY_ID, "--action-type", "dividend",
        "--action-date", action_date.isoformat(), "--details", '{"amount_per_share": 1.5}',
        "--db-path", db_path,
    ])
    assert exit_code == 0

    with connect(db_path) as conn:
        actions = conn.execute("SELECT * FROM corporate_actions WHERE company_id = ?", (COMPANY_ID,)).fetchall()
    assert len(actions) == 1
    assert actions[0]["action_type"] == "dividend"
    assert actions[0]["data_source_id"] == "manual"

    # Not a price-adjusting action type — candles are untouched.
    after_candles = company_repo.list_price_candles(COMPANY_ID)
    assert after_candles == prior_candles

    rec_repo = RecommendationRepository(db_path)
    supersessions = rec_repo.list_supersessions(rec.recommendation_id)
    assert len(supersessions) == 1
    assert supersessions[0].superseding_event_type == "corporate_action"

    with connect(db_path) as conn:
        jobs = conn.execute("SELECT * FROM jobs WHERE job_type = 'corporate_action'").fetchall()
    assert len(jobs) == 1
    assert jobs[0]["status"] == "completed"


def test_split_adjusts_prices_before_action_date_and_recomputes_technical_snapshot(db_path):
    company_repo = CompanyRepository(db_path)
    action_date = date(2026, 6, 1)
    _seed_price_candles(company_repo, action_date, close_before=100.0, close_after=50.0)

    exit_code = main([
        "--company-id", COMPANY_ID, "--action-type", "split",
        "--action-date", action_date.isoformat(), "--ratio", "2.0",
        "--db-path", db_path,
    ])
    assert exit_code == 0

    candles = company_repo.list_price_candles(COMPANY_ID)
    before = [c for c in candles if c.candle_date < action_date.isoformat()]
    after = [c for c in candles if c.candle_date >= action_date.isoformat()]

    assert all(c.close == 50.0 for c in before)  # 100 / ratio(2.0)
    assert all(c.adjusted_for_corporate_action for c in before)
    assert all(c.close == 50.0 for c in after)  # already post-split scale, untouched
    assert all(not c.adjusted_for_corporate_action for c in after)

    snapshots = company_repo.list_technical_snapshots(COMPANY_ID)
    assert len(snapshots) == 1  # freshly recomputed over the adjusted series


def test_price_adjusting_action_without_ratio_fails_cleanly(db_path):
    exit_code = main([
        "--company-id", COMPANY_ID, "--action-type", "split",
        "--action-date", "2026-06-01", "--db-path", db_path,
    ])
    assert exit_code == 1

    with connect(db_path) as conn:
        actions = conn.execute("SELECT * FROM corporate_actions").fetchall()
    assert len(actions) == 0
