from app.errors import AuditError
from app.manifest import now

FINAL = {'UPHELD', 'WAIVED', 'REDUCED'}


def next_event(snapshot, payload):
    key = payload['key']
    base = next((row for row in snapshot['penalties']['rows'] if row['key'] == key), None)
    if not base:
        raise AuditError('SHELF_NOT_FOUND', '该柜位未在本次抽中', 404)
    if base['status'] != 'VIOLATION':
        raise AuditError('NO_PENALTY', '该柜位没有可复核罚额', 409, base['status'])
    history = [item for item in snapshot['events'] if item['key'] == key]
    last = history[-1] if history else None
    previous_version = last['version'] if last else 0
    if payload['expected_version'] != previous_version:
        raise AuditError('STALE_APPEAL', '异议版本已变化，请刷新', 409, previous_version)
    action = payload['action']
    previous_status = last['status'] if last else None
    if not ((previous_status is None and action == 'OPEN') or (previous_status == 'OPEN' and action in FINAL)):
        raise AuditError('INVALID_TRANSITION', '当前异议状态不允许该动作', 409, previous_status)
    old = base['original_cents']
    requested = payload.get('reduction_cents')
    if action == 'REDUCED':
        if requested is None or not 0 < requested < old:
            raise AuditError('BAD_REDUCTION', '减免须小于原罚额且大于零', evidence=old)
        delta = requested
    elif requested is not None:
        raise AuditError('BAD_REDUCTION', '该异议动作无需减免金额')
    else:
        delta = old if action == 'WAIVED' else 0
    return {'key': key, 'status': action, 'version': previous_version + 1, 'request_id': payload['request_id'],
            'actor': payload['actor'], 'note': payload['note'], 'evidence_ref': payload['evidence_ref'],
            'created_at': now(), 'original_cents': old, 'reduction_cents': delta,
            'original_rule': base['applied']['code'], 'plan_source': base['plan']['source']['id']}
