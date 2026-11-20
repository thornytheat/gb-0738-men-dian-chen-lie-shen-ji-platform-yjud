from app.modules.coverage.sampling import choose_slots

# 证据不足、可补证 → 待证；证据冲突或不可用 → 隔离
PENDING_REASONS = {'VISIT_MISSING', 'MISSING_PHOTO', 'SCAN_INCOMPLETE'}


def empty_evidence(visit, slot):
    return {'visit': visit, 'slot': slot, 'photos': [], 'products': {}, 'completed_sources': [],
            'conflicting_skus': [], 'photo_issues': [], 'reason': 'MISSING_PHOTO'}


def classify(decision, binding):
    """按生效陈列图与图证结论判定柜位证据状态。"""
    reason = decision['reason']
    if reason in ('PLAN_MISSING', 'PLAN_OVERLAP'):
        return 'ISOLATED', reason
    if reason == 'VISIT_MISSING':
        return 'PENDING', reason
    reason = binding['reason']
    if reason is None:
        return 'VERIFIED', None
    return ('PENDING', reason) if reason in PENDING_REASONS else ('ISOLATED', reason)


def coverage(intake, plans, photos, sample_size):
    rows, strata = choose_slots(intake, sample_size)
    decisions = {(row['store'], row['slot']): row for row in plans['decisions']}
    bindings = {(row['visit'], row['slot']): row for row in photos['bindings']}
    slots = []
    for row in rows:
        decision = decisions[row['store'], row['slot']]
        visit = decision['visit']
        binding = (bindings.get((visit['visit'], row['slot'])) if visit else None) \
            or empty_evidence(visit['visit'] if visit else None, row['slot'])
        status, reason = classify(decision, binding)
        slots.append({**row, 'evidence_status': status, 'reason': reason, 'visit': visit,
                      'plan': decision['plan'], 'plan_candidates': decision['candidates'],
                      'evidence': binding})
    verified = sum(row['evidence_status'] == 'VERIFIED' for row in slots)
    for group in strata:
        members = [row for row in slots if row['group'] == group['code']]
        group['verified'] = sum(row['evidence_status'] == 'VERIFIED' for row in members)
        group['pending'] = sum(row['evidence_status'] == 'PENDING' for row in members)
        group['isolated'] = sum(row['evidence_status'] == 'ISOLATED' for row in members)
        group['gap'] = group['target'] - group['verified']
    return {'target': sample_size, 'selected': len(slots), 'unfilled': sample_size - len(slots),
            'verified': verified, 'strata': strata, 'slots': slots}
