import sqlite3

import pytest

from egxpm.persistence.company_repository import CompanyRepository
from egxpm.persistence.models import ConfidenceScore, RiskScore, Score, TechnicalSnapshot

COMPANY_ID = "COMI"  # seeded by init_db


def _artifacts():
    snapshot = TechnicalSnapshot(
        company_id=COMPANY_ID, rsi=55.0, engine_version="v1",
        computed_through_date="2026-06-30", job_id="job-1",
    )
    score = Score(company_id=COMPANY_ID, composite_score=70.0, config_snapshot_id="cfg-1", job_id="job-1")
    risk = RiskScore(score_id=score.score_id, value=80.0)
    confidence = ConfidenceScore(score_id=score.score_id, confidence_value=0.9)
    return snapshot, score, risk, confidence


def test_checkpoint_a_writes_all_four_rows_atomically(db_path):
    repo = CompanyRepository(db_path)
    snapshot, score, risk, confidence = _artifacts()

    repo.save_checkpoint_a(snapshot, score, risk, confidence)

    assert repo.get_latest_technical_snapshot(COMPANY_ID) is not None
    assert repo.get_score(score.score_id) is not None
    assert repo.get_risk_score_by_score_id(score.score_id) is not None
    assert repo.get_confidence_score_by_score_id(score.score_id) is not None


def test_checkpoint_a_rolls_back_all_four_on_simulated_crash(db_path):
    """Crash simulation: RiskScore has a bad FK (score_id pointing nowhere),
    which SQLite rejects (foreign_keys=ON). The TechnicalSnapshot and Score
    writes that happened earlier in the same call must not survive either.
    """
    repo = CompanyRepository(db_path)
    snapshot, score, risk, confidence = _artifacts()
    broken_risk = risk.model_copy(update={"score_id": "does-not-exist"})

    with pytest.raises(sqlite3.IntegrityError):
        repo.save_checkpoint_a(snapshot, score, broken_risk, confidence)

    assert repo.get_latest_technical_snapshot(COMPANY_ID) is None
    assert repo.get_score(score.score_id) is None
    assert repo.get_risk_score_by_score_id(score.score_id) is None
    assert repo.get_confidence_score_by_score_id(score.score_id) is None


def test_checkpoint_a_rolls_back_when_last_artifact_fails(db_path):
    """Crash simulation targeting the LAST of the four writes: proves the
    transaction isn't accidentally committed early (e.g. by a stray
    intermediate connection)."""
    repo = CompanyRepository(db_path)
    snapshot, score, risk, confidence = _artifacts()
    broken_confidence = confidence.model_copy(update={"score_id": "does-not-exist"})

    with pytest.raises(sqlite3.IntegrityError):
        repo.save_checkpoint_a(snapshot, score, risk, broken_confidence)

    assert repo.get_latest_technical_snapshot(COMPANY_ID) is None
    assert repo.get_score(score.score_id) is None
    assert repo.get_risk_score_by_score_id(score.score_id) is None
