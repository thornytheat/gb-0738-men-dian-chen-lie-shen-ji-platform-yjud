from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import shutil
import sqlite3

import pytest

from app.config import Options
from app.errors import AuditError
from app.modules.settlement.reconcile import reconcile
from app.modules.settlement.service import run_audit
from app.store import Store


def test_field_settlement_matches_source_shelf_and_amount_ledgers(field):
    sheet = field.settlement
    assert sheet['balanced'] is True and sheet['original_cents'] == 29500
    assert sheet['counts'] == {'COMPLIANT': 8, 'VIOLATION': 3, 'PENDING': 3, 'ISOLATED': 3}
    assert sheet['sources']['observations'] == {'input': 50, 'accepted': 40, 'isolated': 10, 'blank': 0, 'repeated_headers': 0}
    assert sum(row['isolated'] for row in sheet['sources'].values()) == len(sheet['quarantine']) == 22


def test_substituted_source_same_row_count_fails(field):
    photos = deepcopy(field.photos)
    photos['observations'][1] = photos['observations'][0]
    with pytest.raises(AuditError) as error:
        reconcile(field.intake, field.plans, photos, field.coverage, field.penalties)
    assert (error.value.code, error.value.evidence) == ('SOURCE_LEDGER_MISMATCH', 'observations.csv')


def test_incorrect_penalty_amount_fails_per_slot_reconciliation(field):
    adjusted = deepcopy(field.penalties)
    next(row for row in adjusted['rows'] if row['status'] == 'VIOLATION')['original_cents'] += 1
    with pytest.raises(AuditError) as error:
        reconcile(field.intake, field.plans, field.photos, field.coverage, adjusted)
    assert error.value.code == 'AMOUNT_LEDGER_MISMATCH'


def test_same_effective_parameters_reuse_absolute_snapshot(client, run):
    again = client.post('/api/settlement/runs', json={'dataset': 'field', 'sample_size': 18}).json()
    assert again.pop('reused') is True and run.pop('reused') is False
    assert again == run
    changed = client.post('/api/settlement/runs', json={'sample_size': 17}).json()
    assert changed['reused'] is False and changed['manifest']['run_id'] != again['manifest']['run_id']


def test_concurrent_runs_publish_only_one_complete_snapshot(settings):
    store = Store(settings.database)
    store.initialize()
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: run_audit(settings, store, Options()), range(4)))
    assert sum(not reused for _, reused in results) == 1
    assert {snapshot['settlement']['original_cents'] for snapshot, _ in results} == {29500}
    with sqlite3.connect(settings.database) as connection:
        assert connection.execute('SELECT COUNT(*) FROM runs').fetchone() == (1,)


def test_parse_error_rolls_back_entire_batch_and_restoring_original_allows_retry(settings, tmp_path):  # TRAP-16
    duplicate = tmp_path / 'data'
    shutil.copytree(settings.sample_root, duplicate)
    settings.sample_root = duplicate
    name = duplicate / 'field' / 'observations.csv'
    baseline = name.read_bytes()
    name.write_bytes(baseline + b'V001,A01,"cut')
    store = Store(settings.database)
    store.initialize()
    with pytest.raises(AuditError) as error:
        run_audit(settings, store, Options())
    assert error.value.code == 'MALFORMED_CSV'
    with sqlite3.connect(settings.database) as connection:
        assert connection.execute('SELECT COUNT(*) FROM runs').fetchone() == (0,)
    name.write_bytes(baseline)
    result, reused = run_audit(settings, store, Options())
    assert result['settlement']['balanced'] and not reused


def test_hash_changes_when_only_photo_bytes_change(settings, tmp_path):
    duplicate = tmp_path / 'data'
    shutil.copytree(settings.sample_root, duplicate)
    settings.sample_root = duplicate
    store = Store(settings.database)
    store.initialize()
    first, _ = run_audit(settings, store, Options())
    target = duplicate / 'field' / 'photos' / 'P001.png'
    target.write_bytes(target.read_bytes() + b'\0')
    second, reused = run_audit(settings, store, Options())
    assert not reused and second['manifest']['run_id'] != first['manifest']['run_id']
    assert second['manifest']['inputs']['photos/P001.png'] != first['manifest']['inputs']['photos/P001.png']
    assert second['settlement']['reason_counts']['BAD_PHOTO_FILE'] == 2
