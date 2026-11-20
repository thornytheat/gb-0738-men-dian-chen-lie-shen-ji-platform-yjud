import base64
import struct
import zlib

from conftest import appeal_payload, locate_or_fail


def make_png(tag=b'\x01\x02\x03'):
    def chunk(kind, data):
        return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data))

    ihdr = struct.pack('>IIBBBBB', 1, 1, 8, 2, 0, 0, 0)
    idat = zlib.compress(b'\x00' + tag)
    return b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', ihdr) + chunk(b'IDAT', idat) + chunk(b'IEND', b'')


def photo(photo_id, captured, tag=b'\x11\x22\x33'):
    return {'photo': photo_id, 'file': f'{photo_id}.png', 'captured': captured,
            'content_base64': base64.b64encode(make_png(tag)).decode()}


def item(key, photo_arg=None, observations=()):
    return {'key': key, 'photo': photo_arg, 'observations': list(observations)}


COMPLETE = {'kind': 'COMPLETE'}
GOODS_209 = {'kind': 'ITEM', 'sku': 'GR-209', 'facings': 4, 'price_cents': 13800}


def supplement(client, run, items, request_id='REV-20261120-01', actor='林复核', note='门店补交漏拍照片'):
    return client.post(f"/api/revisions/{run['manifest']['run_id']}",
                       json={'request_id': request_id, 'actor': actor, 'note': note, 'items': items})


def two_cabinet_items():
    return [item('001:A04', photo('P026', '2026-11-07T09:05:00+08:00'), [COMPLETE, GOODS_209]),
            item('006:A02', photo('P027', '2026-11-08T23:57:00', tag=b'\x44\x55\x66'), [COMPLETE])]


def test_supplement_two_cabinets_scoped_balanced_and_exportable(client, run):
    run_id = run['manifest']['run_id']
    before = client.get(f'/api/settlement/runs/{run_id}').json()
    response = supplement(client, run, two_cabinet_items())
    assert response.status_code == 200
    revision = response.json()['revision']
    assert revision['status'] == 'APPLIED' and revision['revision'] == 1
    changes = {row['key']: row for row in revision['changes']}
    assert changes['001:A04']['before']['status'] == 'PENDING'
    assert (changes['001:A04']['after']['status'], changes['001:A04']['delta_cents']) == ('COMPLIANT', 0)
    assert (changes['006:A02']['after']['status'], changes['006:A02']['after']['reason']) == ('VIOLATION', 'MISSING_SKU')
    assert changes['006:A02']['delta_cents'] == 15000
    assert revision['ledger'] == {'before_cents': 29500, 'delta_cents': 15000, 'after_cents': 44500,
                                  'reduction_cents': 0, 'net_cents': 44500, 'balanced': True}
    after = client.get(f'/api/settlement/runs/{run_id}').json()
    # 原批次与依据保持原样可回查
    assert after['settlement'] == before['settlement'] and after['penalties'] == before['penalties']
    untouched = [row for row in after['revisions']['rows'] if row['key'] not in ('001:A04', '006:A02')]
    assert untouched == []
    ledger = after['revisions']['ledger']
    assert (ledger['original_cents'], ledger['revision_delta_cents'], ledger['revised_original_cents'],
            ledger['net_cents']) == (29500, 15000, 44500, 44500)
    # 异议减免与修订增减共同勾稽净罚额
    client.post(f'/api/appeals/{run_id}/events', json=appeal_payload())
    client.post(f'/api/appeals/{run_id}/events',
                json=appeal_payload(request_id='A-REDUCE-202611', expected_version=1, action='REDUCED',
                                    reduction_cents=6000, note='部分补证确实', evidence_ref='回查票-27'))
    view = client.get(f'/api/revisions/{run_id}').json()
    assert (view['ledger']['reduction_cents'], view['ledger']['net_cents']) == (6000, 38500)
    exported = client.get(f'/api/revisions/{run_id}/export').json()
    assert exported['format'] == 'shelf-evidence/revision-1'
    assert exported['original']['original_cents'] == 29500
    assert [row['revision'] for row in exported['revisions']] == [1]
    assert exported['ledger']['net_cents'] == 38500 and exported['appeals']['net_cents'] == 23500


def test_same_submission_replay_does_not_penalize_twice(client, run):
    run_id = run['manifest']['run_id']
    first = supplement(client, run, two_cabinet_items()).json()
    replay = supplement(client, run, two_cabinet_items()).json()
    assert replay['reused'] is True and replay['revision'] == first['revision']
    again = supplement(client, run, two_cabinet_items(), request_id='REV-20261120-99')
    assert again.status_code == 422 and again.json()['detail']['code'] == 'CABINET_NOT_PENDING'
    view = client.get(f'/api/revisions/{run_id}').json()
    assert (view['count'], view['applied']) == (2, 1)
    assert view['ledger']['revised_original_cents'] == 44500  # 同一补交重跑不重复计罚


def test_conflicting_request_id_is_rejected(client, run):
    run_id = run['manifest']['run_id']
    supplement(client, run, two_cabinet_items())
    changed = supplement(client, run, [item('005:A03', None, [COMPLETE])], request_id='REV-20261120-01')
    assert (changed.status_code, changed.json()['detail']['code']) == (409, 'REQUEST_CONFLICT')


def test_failed_revision_keeps_original_and_allows_retry(client, run):
    run_id = run['manifest']['run_id']
    broken = item('001:A04', {'photo': 'P026', 'file': 'P026.png', 'captured': '2026-11-07T09:05:00+08:00',
                              'content_base64': base64.b64encode(b'not-a-png').decode()}, [COMPLETE, GOODS_209])
    failed = supplement(client, run, [broken])
    assert (failed.status_code, failed.json()['detail']['code']) == (422, 'BAD_PHOTO_FILE')
    assert failed.json()['detail']['evidence']['revision'] == 1
    restored = client.get(f'/api/settlement/runs/{run_id}').json()
    assert restored['settlement']['original_cents'] == 29500
    assert locate_or_fail(restored['penalties']['rows'], key='001:A04')['status'] == 'PENDING'
    assert (restored['revisions']['count'], restored['revisions']['applied']) == (1, 0)
    revert = client.post(f'/api/revisions/{run_id}/1/revert',
                         json={'request_id': 'REVERT-0001', 'actor': '林复核', 'note': '恢复'})
    assert (revert.status_code, revert.json()['detail']['code']) == (409, 'REVISION_NOT_APPLIED')
    retry = supplement(client, run, two_cabinet_items(), request_id='REV-20261120-02')
    assert retry.status_code == 200 and retry.json()['revision']['revision'] == 2
    assert client.get(f'/api/revisions/{run_id}').json()['ledger']['revised_original_cents'] == 44500


def test_revert_restores_original_batch_and_is_idempotent(client, run):
    run_id = run['manifest']['run_id']
    supplement(client, run, two_cabinet_items())
    body = {'request_id': 'REVERT-0001', 'actor': '林复核', 'note': '门店撤回补交'}
    reverted = client.post(f'/api/revisions/{run_id}/1/revert', json=body).json()
    assert reverted['revision']['status'] == 'REVERTED'
    replay = client.post(f'/api/revisions/{run_id}/1/revert', json=body).json()
    assert replay['reused'] is True and replay['revision']['revert']['request_id'] == 'REVERT-0001'
    conflict = client.post(f'/api/revisions/{run_id}/1/revert', json={**body, 'request_id': 'REVERT-0002'})
    assert (conflict.status_code, conflict.json()['detail']['code']) == (409, 'REQUEST_CONFLICT')
    view = client.get(f'/api/revisions/{run_id}').json()
    assert view['applied'] == 0 and view['rows'] == []
    assert (view['ledger']['revised_original_cents'], view['ledger']['net_cents']) == (29500, 29500)


def test_reused_photo_bytes_isolate_and_expired_photo_stays_pending(client, run):
    run_id = run['manifest']['run_id']
    reused = client.get('/api/photos/original/field/P001.png/' +
                        locate_or_fail(client.get('/api/photos').json()['photos'], photo='P001')['sha256']).content
    items = [item('001:A04', {'photo': 'P026', 'file': 'P026.png', 'captured': '2026-11-07T09:05:00+08:00',
                              'content_base64': base64.b64encode(reused).decode()}, [COMPLETE, GOODS_209])]
    revision = supplement(client, run, items).json()['revision']
    change = revision['changes'][0]
    assert (change['after']['status'], change['after']['reason']) == ('ISOLATED', 'PHOTO_REUSED')
    assert change['supplement']['issue'] == 'PHOTO_REUSED'
    late = item('006:A02', photo('P027', '2026-11-09T02:00:00'), [COMPLETE, GOODS_209])
    second = supplement(client, run, [late], request_id='REV-20261120-02').json()['revision']
    change = second['changes'][0]
    assert (change['after']['status'], change['after']['reason']) == ('PENDING', 'MISSING_PHOTO')
    assert change['after']['evidence']['photo_issues'] == ['PHOTO_EXPIRED']
    # 待证柜位可再次补交，证据链累计
    better = item('006:A02', photo('P028', '2026-11-08T23:57:00', tag=b'\x77\x88\x99'), [COMPLETE])
    third = supplement(client, run, [better], request_id='REV-20261120-03').json()['revision']
    assert third['changes'][0]['after']['status'] == 'COMPLIANT'


def test_scan_completion_uses_existing_photo_and_counts(client, run):
    run_id = run['manifest']['run_id']
    response = supplement(client, run, [item('005:A03', None, [COMPLETE])])
    change = response.json()['revision']['changes'][0]
    assert change['before']['reason'] == 'SCAN_INCOMPLETE'
    assert (change['after']['status'], change['after']['original_cents']) == ('COMPLIANT', 0)
    assert len(change['after']['evidence']['photos']) == 1  # 沿用原批已采信照片


def test_non_pending_unknown_and_conflict_guards(client, run):
    run_id = run['manifest']['run_id']
    violating = supplement(client, run, [item('002:A03', None, [COMPLETE])])
    assert (violating.status_code, violating.json()['detail']['code']) == (422, 'CABINET_NOT_PENDING')
    missing = supplement(client, run, [item('009:A99', None, [COMPLETE])], request_id='REV-20261120-02')
    assert (missing.status_code, missing.json()['detail']['code']) == (422, 'SHELF_NOT_SAMPLED')
    conflicting = supplement(client, run, [item('005:A03', None, [COMPLETE, {'kind': 'ITEM', 'sku': 'GR-211',
                                                                 'facings': 4, 'price_cents': 15800}])],
                           request_id='REV-20261120-03')
    change = conflicting.json()['revision']['changes'][0]
    assert (change['after']['status'], change['after']['reason']) == ('ISOLATED', 'OBSERVATION_CONFLICT')
    assert change['after']['evidence']['conflicting_skus'] == ['GR-211']


def test_supplemented_photo_original_is_servable(client, run):
    run_id = run['manifest']['run_id']
    supplement(client, run, two_cabinet_items())
    response = client.get(f'/api/revisions/{run_id}/1/photos/P026')
    assert response.status_code == 200 and response.headers['content-type'] == 'image/png'
    assert response.content == make_png(b'\x11\x22\x33')
    missing = client.get(f'/api/revisions/{run_id}/1/photos/P999')
    assert (missing.status_code, missing.json()['detail']['code']) == (404, 'PHOTO_NOT_FOUND')


def test_concurrent_supplements_apply_exactly_once(client, run):
    from concurrent.futures import ThreadPoolExecutor

    run_id = run['manifest']['run_id']
    bodies = [{'request_id': f'REV-RACE-{i:02d}', 'actor': '林复核', 'note': '并发补交',
               'items': [item('001:A04', photo('P026', '2026-11-07T09:05:00+08:00',
                                             tag=bytes([i, i, i])), [COMPLETE, GOODS_209])]}
              for i in range(1, 5)]
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda body: client.post(f'/api/revisions/{run_id}', json=body), bodies))
    assert sorted(response.status_code for response in results) == [200, 422, 422, 422]
    view = client.get(f'/api/revisions/{run_id}').json()
    assert (view['count'], view['applied']) == (4, 1)
    assert view['ledger']['revised_original_cents'] == 29500  # 并发同一柜位只生效一笔
