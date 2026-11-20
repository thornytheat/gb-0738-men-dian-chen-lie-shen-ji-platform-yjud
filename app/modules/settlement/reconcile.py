from collections import Counter, defaultdict

from app.errors import AuditError


def ids(rows):
    return [row['source']['id'] for row in rows]


def row_ledger(table, valid, issues):
    original = Counter(ids(table['rows']) + ids(table['quarantine']))
    if original != Counter(ids(valid) + ids(issues)) or sum(original.values()) != table['input']:
        raise AuditError('SOURCE_LEDGER_MISMATCH', '原件行号对账失败', 500, table['name'])
    return {'input': table['input'], 'accepted': len(valid), 'isolated': len(issues),
            'blank': table['blank'], 'repeated_headers': table['repeated_headers']}


def reconcile(intake, plans, photos, coverage, judgments):
    files = {**{name: intake[name] for name in ('stores', 'slots', 'visits')},
             'plans': plans['plans'], 'aliases': plans['alias_rows'],
             'photos': photos['photos'], 'observations': photos['observations']}
    quarantine = sorted(intake['quarantine'] + plans['quarantine'] + photos['quarantine'],
                        key=lambda row: (row['source']['file'], row['source']['line']))
    by_file = defaultdict(list)
    for mark in quarantine:
        by_file[mark['source']['file']].append(mark)
    sources = {key: row_ledger(intake['tables'][key], valid, by_file[f'{key}.csv']) for key, valid in files.items()}
    rows = judgments['rows']
    counts = judgments['counts']
    statuses = Counter(row['status'] for row in rows)
    if (statuses != Counter(counts) or Counter(row['key'] for row in rows) != Counter(row['key'] for row in coverage['slots'])
            or len(rows) != coverage['selected'] or len(rows) != sum(counts.values())
            or coverage['selected'] + coverage['unfilled'] != coverage['target']
            or counts['COMPLIANT'] + counts['VIOLATION'] != coverage['verified']):
        raise AuditError('COVERAGE_LEDGER_MISMATCH', '柜位抽检对账失败', 500)
    strata = []
    for group in coverage['strata']:
        group_rows = [row for row in rows if row['group'] == group['code']]
        result = Counter(row['status'] for row in group_rows)
        if (len(group_rows) != group['selected'] or result['COMPLIANT'] + result['VIOLATION'] != group['verified']
                or result['PENDING'] != group['pending']
                or result['ISOLATED'] != group['isolated']):
            raise AuditError('COVERAGE_LEDGER_MISMATCH', '店组抽检对账失败', 500, group['code'])
        strata.append({'code': group['code'], 'counts': {key: result[key] for key in counts},
                       'original_cents': sum(row['original_cents'] for row in group_rows)})
    if any(row['original_cents'] != (row['applied']['cents'] if row['applied'] else 0)
           or bool(row['applied']) != (row['status'] == 'VIOLATION') for row in rows):
        raise AuditError('AMOUNT_LEDGER_MISMATCH', '柜位罚额与依据不符', 500)
    total = sum(row['original_cents'] for row in rows)
    if total != sum(item['original_cents'] for item in strata):
        raise AuditError('AMOUNT_LEDGER_MISMATCH', '罚额分组对账失败', 500)
    return {'balanced': True, 'target': coverage['target'], 'selected': len(rows), 'unfilled': coverage['unfilled'],
            'counts': counts, 'original_cents': total, 'strata': strata, 'sources': sources,
            'quarantine': quarantine, 'reason_counts': dict(sorted(Counter(row['reason'] for row in quarantine).items()))}
