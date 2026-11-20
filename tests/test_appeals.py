from hashlib import sha256

from conftest import appeal_payload, locate_or_fail


def path(run):
    return f"/api/appeals/{run['manifest']['run_id']}"


def open_and_reduce(client, run):
    url = path(run) + '/events'
    initial = client.post(url, json=appeal_payload())
    assert initial.status_code == 200
    final = client.post(url, json=appeal_payload(request_id='A-REDUCE-202611', expected_version=1, action='REDUCED',
                                               reduction_cents=6000, note='部分补证确实', evidence_ref='回查票-27'))
    assert final.status_code == 200
    return initial.json()['event'], final.json()['event']


def test_appeal_adjusts_net_and_retains_original_penalty_and_sources(client, run):
    events = open_and_reduce(client, run)
    result = client.get(path(run)).json()
    assert (result['original_cents'], result['reduction_cents'], result['net_cents']) == (29500, 6000, 23500)
    assert result['events'] == list(events)
    assert events[1]['original_rule'] == 'MISSING_SKU' and events[1]['plan_source'] == 'plans.csv:3'
    assert locate_or_fail(result['rows'], key='002:A03')['net_cents'] == 9000


def test_reused_request_replays_record_and_changed_payload_conflicts(client, run):
    url = path(run) + '/events'
    original = client.post(url, json=appeal_payload()).json()
    replay = client.post(url, json=appeal_payload()).json()
    assert replay == {**original, 'reused': True}
    changed = client.post(url, json=appeal_payload(note='更改说明'))
    assert (changed.status_code, changed.json()['detail']['code']) == (409, 'REQUEST_CONFLICT')


def test_stale_appeal_version_cannot_override_current_stage(client, run):  # TRAP-26
    url = path(run) + '/events'
    client.post(url, json=appeal_payload())
    stale = client.post(url, json=appeal_payload(request_id='A-STALE-202611', action='UPHELD'))
    assert (stale.status_code, stale.json()['detail']['code'], stale.json()['detail']['evidence']) == (409, 'STALE_APPEAL', 1)
    assert len(client.get(path(run)).json()['events']) == 1


def test_invalid_transition_and_non_violation_cannot_be_reviewed(client, run):
    url = path(run) + '/events'
    skipped = client.post(url, json=appeal_payload(action='UPHELD'))
    assert (skipped.status_code, skipped.json()['detail']['code']) == (409, 'INVALID_TRANSITION')
    prevented = client.post(url, json=appeal_payload(key='001:A04'))
    assert (prevented.status_code, prevented.json()['detail']['code']) == (409, 'NO_PENALTY')


def test_reduction_must_be_strictly_less_than_penalty(client, run):
    url = path(run) + '/events'
    client.post(url, json=appeal_payload())
    invalid = client.post(url, json=appeal_payload(request_id='A-FULL-202611', expected_version=1, action='REDUCED', reduction_cents=15000))
    assert (invalid.status_code, invalid.json()['detail']['code']) == (422, 'BAD_REDUCTION')
    waived = client.post(url, json=appeal_payload(request_id='A-FULL-202611', expected_version=1, action='WAIVED'))
    assert waived.json()['event']['reduction_cents'] == 15000


def test_single_export_contains_hashes_events_and_original_evidence(client, run, field):
    open_and_reduce(client, run)
    response = client.get(path(run) + '/export')
    assert response.headers['content-disposition'].startswith('attachment; filename="shelf-audit-')
    exported = response.json()
    assert exported['format'] == 'shelf-evidence/audit-1'
    assert exported['manifest']['inputs']['photos/P001.png'] == sha256(field.bundle['photos/P001.png']).hexdigest()
    assert exported['appeals']['net_cents'] == 23500
    assert exported['events'][1]['evidence_ref'] == '回查票-27'
    assert 'PHOTO_REUSED' in exported['reason_dictionary']


def test_new_run_reuses_stored_clearance_and_preserves_event_order(client, run):
    initial, final = open_and_reduce(client, run)
    restored = client.post('/api/settlement/runs', json={}).json()
    assert restored['reused'] is True
    assert restored['events'] == [initial, final]
    assert restored['settlement']['original_cents'] == 29500


def test_concurrent_decisions_enforce_one_terminal_event(client, run):
    from concurrent.futures import ThreadPoolExecutor

    url = path(run) + '/events'
    assert client.post(url, json=appeal_payload()).status_code == 200
    alternatives = [appeal_payload(request_id=f'TERMINAL-{i}', expected_version=1, action=action)
                    for i, action in enumerate(('UPHELD', 'WAIVED'))]
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda body: client.post(url, json=body), alternatives))
    assert sorted(response.status_code for response in results) == [200, 409]
    ledger = client.get(path(run)).json()
    assert [event['version'] for event in ledger['events']] == [1, 2]
    assert ledger['net_cents'] in {14500, 29500}
    assert ledger['net_cents'] + ledger['reduction_cents'] == 29500
