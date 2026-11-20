from fastapi.testclient import TestClient

from app.main import create_app
from conftest import appeal_payload


def test_home_and_seven_action_entries(client, run):
    page = client.get('/')
    assert page.status_code == 200
    assert all(word in page.text for word in ('证据严重度矩阵', '分层样本缺口', '运行审计', '导出证据'))
    for stage, key in [('intake', 'stores'), ('plans', 'decisions'), ('photos', 'bindings'), ('coverage', 'strata'),
                       ('penalties', 'rows'), ('settlement', 'original_cents'), (f"appeals/{run['manifest']['run_id']}", 'net_cents')]:
        result = client.get(f'/api/{stage}')
        assert result.status_code == 200 and key in result.json()


def test_api_contract_returns_explicit_errors(client):
    invalid = client.get('/api/coverage?sample_size=0')
    assert (invalid.status_code, invalid.json()['detail']['code']) == (422, 'INVALID_INPUT')
    missing = client.get('/api/appeals/' + '0' * 64)
    assert (missing.status_code, missing.json()['detail']['code']) == (404, 'RUN_NOT_FOUND')


def test_persistent_snapshot_and_event_survive_application_restart(settings):
    with TestClient(create_app(settings)) as initial:
        run = initial.post('/api/settlement/runs', json={}).json()
        run_id = run['manifest']['run_id']
        assert initial.post(f'/api/appeals/{run_id}/events', json=appeal_payload()).status_code == 200
    with TestClient(create_app(settings)) as restored:
        result = restored.get(f'/api/settlement/runs/{run_id}').json()
        assert result['events'][0]['status'] == 'OPEN'
        assert result['appeals']['net_cents'] == 29500
