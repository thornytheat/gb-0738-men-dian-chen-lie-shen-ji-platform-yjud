from hashlib import sha256

import pytest

from app.modules.intake.values import InvalidRow
from app.modules.photos.fingerprints import png_hash
from conftest import locate_or_fail


def test_different_file_names_with_equal_bytes_flag_both_bindings(field):  # TRAP-27
    duplicate, = field.photos['reused_groups']
    assert duplicate['bindings'] == [('V001', 'A02'), ('V003', 'A02')]
    assert duplicate['sha256'] == sha256(field.bundle['photos/P002.png']).hexdigest()
    rows = [row for row in field.photos['quarantine'] if row['reason'] == 'PHOTO_REUSED']
    assert {row['source']['raw'][3] for row in rows} == {'P002.png', 'P010.png'}


def test_same_bytes_with_multiple_ids_on_same_binding_remains_eligible(reference):
    reference.bundle['photos.csv'] += b'P-MORE,V001,A01,P001.png,2026-11-07T09:02:00+08:00\r\n'
    row = locate_or_fail(reference.photos['bindings'], visit='V001', slot='A01')
    assert len(row['photos']) == 2 and row['reason'] is None
    assert reference.photos['reused_groups'] == []


def test_expired_capture_and_unsafe_file_keep_separate_reasons(field):
    expired = locate_or_fail(field.photos['quarantine'], reason='PHOTO_EXPIRED')
    bad = locate_or_fail(field.photos['quarantine'], reason='BAD_PHOTO_FILE')
    assert (expired['visit'], expired['slot'], expired['skew_seconds']) == ('V006', 'A02', 1860)
    assert bad['source']['raw'][3] == '../other.png'


def test_missing_completion_is_distinct_from_conflicting_counts(field):
    incomplete = locate_or_fail(field.photos['bindings'], visit='V005', slot='A03')
    conflict = locate_or_fail(field.photos['bindings'], visit='V004', slot='A02')
    assert (incomplete['reason'], conflict['reason']) == ('SCAN_INCOMPLETE', 'OBSERVATION_CONFLICT')
    assert conflict['conflicting_skus'] == ['GR-211']
    assert len([row for row in field.photos['quarantine'] if row['reason'] == 'OBSERVATION_CONFLICT']) == 2


def test_alias_and_fullwidth_price_reconcile_to_integer_evidence(field):  # TRAP-06
    item = locate_or_fail(field.photos['bindings'], visit='V006', slot='A01')['products']['GR-209']
    assert item['price_cents'] == 13800 and item['facings'] == 4
    assert item['sources'] and item['sources'][0].startswith('observations.csv:')


def test_bad_png_chunks_are_rejected(field):
    raw = field.bundle['photos/P001.png']
    assert png_hash(raw) == sha256(raw).hexdigest()
    for invalid in (raw[:-1], raw + b'X', raw[:33] + b'dummy'):
        with pytest.raises(InvalidRow) as error:
            png_hash(invalid)
        assert error.value.code == 'BAD_PHOTO_FILE'


def test_photo_read_preserves_snapshot_digest_and_detects_changed_digest(client, field):
    row = locate_or_fail(field.photos['photos'], photo='P001')
    path = '/api/photos/original/field/P001.png/'
    response = client.get(path + row['sha256'])
    assert response.headers['content-type'] == 'image/png' and sha256(response.content).hexdigest() == row['sha256']
    wrong = client.get(path + '0' * 64)
    assert (wrong.status_code, wrong.json()['detail']['code']) == (409, 'PHOTO_CHANGED')


def test_capture_at_exact_window_end_is_valid(reference):
    reference.bundle['photos.csv'] = reference.bundle['photos.csv'].replace(b'2026-11-07T09:02:00+08:00', b'2026-11-07T09:30:00+08:00')
    row = locate_or_fail(reference.photos['photos'], photo='P001')
    assert row['skew_seconds'] == 1800
