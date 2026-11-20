from app.errors import AuditError
from app.reasons import REASONS


def appeal_balances(snapshot):
    by_key = {row['key']: row for row in snapshot['events']}
    rows = []
    for base in snapshot['penalties']['rows']:
        if base['status'] != 'VIOLATION':
            continue
        event = by_key.get(base['key'])
        reduction = event['reduction_cents'] if event else 0
        original = base['original_cents']
        if not 0 <= reduction <= original:
            raise AuditError('AMOUNT_LEDGER_MISMATCH', '异议减免金额对账失败', 500, base['key'])
        rows.append({'key': base['key'], 'original_cents': original, 'reduction_cents': reduction, 'net_cents': original - reduction,
                     'status': event['status'] if event else 'NONE', 'version': event['version'] if event else 0})
    original_cents = snapshot['settlement']['original_cents']
    reduced_cents = sum(row['reduction_cents'] for row in rows)
    net_cents = sum(row['net_cents'] for row in rows)
    if original_cents != reduced_cents + net_cents:
        raise AuditError('AMOUNT_LEDGER_MISMATCH', '净额对账失败', 500)
    return {'original_cents': original_cents, 'reduction_cents': reduced_cents, 'net_cents': net_cents,
            'balanced': True, 'rows': rows, 'events': snapshot['events']}


def with_appeals(snapshot):
    return {**snapshot, 'appeals': appeal_balances(snapshot)}


def export_evidence(snapshot):
    return {'format': 'shelf-evidence/audit-1', **with_appeals(snapshot), 'reason_dictionary': REASONS}
