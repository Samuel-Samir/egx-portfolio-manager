import pytest

from egxpm.persistence.db import init_db


@pytest.fixture
def db_path(tmp_path):
    path = tmp_path / "egx_test.db"
    init_db(path)
    return str(path)
