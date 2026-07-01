import sqlite3

import pytest

from egxpm.persistence.company_repository import CompanyRepository
from egxpm.persistence.models import (
    ConfidenceScore,
    ConfigurationSnapshot,
    PortfolioSnapshot,
    PortfolioSnapshotOrigin,
    Recommendation,
    RecommendationAction,
    RecommendationSupersession,
    RiskScore,
    Score,
)
from egxpm.persistence.operational_repository import OperationalRepository
from egxpm.persistence.portfolio_repository import PortfolioRepository
from egxpm.persistence.recommendation_repository import RecommendationRepository

COMPANY_ID = "COMI"


def _recommendation_dependencies(db_path):
    company_repo = CompanyRepository(db_path)
    operational_repo = OperationalRepository(db_path)
    portfolio_repo = PortfolioRepository(db_path)

    score = Score(company_id=COMPANY_ID, config_snapshot_id="cfg-1", job_id="job-1")
    company_repo.save_score(score)
    confidence = ConfidenceScore(score_id=score.score_id, confidence_value=0.8)
    company_repo.save_confidence_score(confidence)
    config_snapshot = ConfigurationSnapshot(allocation_targets={"long_term_stocks": 0.4})
    operational_repo.save_configuration_snapshot(config_snapshot)
    portfolio_snapshot = PortfolioSnapshot(origin=PortfolioSnapshotOrigin.BEFORE_RECOMMENDATION)
    portfolio_repo.save_snapshot(portfolio_snapshot)
    return confidence, config_snapshot, portfolio_snapshot


def _recommendation(confidence, config_snapshot, portfolio_snapshot):
    return Recommendation(
        company_id=COMPANY_ID, action=RecommendationAction.BUY,
        confidence_id=confidence.confidence_id, config_snapshot_id=config_snapshot.config_snapshot_id,
        portfolio_snapshot_id=portfolio_snapshot.snapshot_id, job_id="job-1",
    )


def test_checkpoint_b_writes_recommendation_and_supersession_atomically(db_path):
    confidence, config_snapshot, portfolio_snapshot = _recommendation_dependencies(db_path)
    rec_repo = RecommendationRepository(db_path)
    old_rec = _recommendation(confidence, config_snapshot, portfolio_snapshot)
    rec_repo.save_recommendation(old_rec)

    new_rec = _recommendation(confidence, config_snapshot, portfolio_snapshot)
    supersession = RecommendationSupersession(
        recommendation_id=old_rec.recommendation_id, superseding_event_type="new_score_computed",
        superseding_reference_id=new_rec.recommendation_id,
    )
    rec_repo.save_checkpoint_b(new_rec, supersession)

    assert rec_repo.get_recommendation(new_rec.recommendation_id) is not None
    assert rec_repo.list_supersessions(old_rec.recommendation_id)[0].supersession_id == supersession.supersession_id


def test_checkpoint_b_without_supersession(db_path):
    confidence, config_snapshot, portfolio_snapshot = _recommendation_dependencies(db_path)
    rec_repo = RecommendationRepository(db_path)
    rec = _recommendation(confidence, config_snapshot, portfolio_snapshot)
    rec_repo.save_checkpoint_b(rec, supersession=None)
    assert rec_repo.get_recommendation(rec.recommendation_id) is not None


def test_checkpoint_b_rolls_back_both_on_simulated_crash(db_path):
    confidence, config_snapshot, portfolio_snapshot = _recommendation_dependencies(db_path)
    rec_repo = RecommendationRepository(db_path)
    rec = _recommendation(confidence, config_snapshot, portfolio_snapshot)
    broken_supersession = RecommendationSupersession(
        recommendation_id="does-not-exist", superseding_event_type="new_score_computed",
    )

    with pytest.raises(sqlite3.IntegrityError):
        rec_repo.save_checkpoint_b(rec, broken_supersession)

    assert rec_repo.get_recommendation(rec.recommendation_id) is None
