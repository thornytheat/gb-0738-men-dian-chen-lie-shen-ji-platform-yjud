import pytest
from fastapi.testclient import TestClient

from app.config import ROOT, Options, Settings
from app.main import create_app
from app.pipeline import Audit


@pytest.fixture
def settings(tmp_path):
    return Settings(ROOT / 'sample_data', tmp_path / 'audit.sqlite3')


@pytest.fixture
def field(settings):
    return Audit(settings, Options())


@pytest.fixture
def reference(settings):
    return Audit(settings, Options(dataset='reference'))


@pytest.fixture
def client(settings):
    with TestClient(create_app(settings)) as session:
        yield session


@pytest.fixture
def run(client):
    return client.post('/api/settlement/runs', json={}).json()


def locate_or_fail(rows, **fields):
    return next(row for row in rows if all(row[key] == value for key, value in fields.items()))


def appeal_payload(**changes):
    return {'key': '002:A03', 'request_id': 'A-OPEN-202611', 'expected_version': 0, 'action': 'OPEN', 'actor': '黄稽核',
            'note': '提交原件复核', 'evidence_ref': '复核簿-21', **changes}
