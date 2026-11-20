from collections import Counter

from app.modules.penalties.rules import candidates


def judge(coverage, campaign):
    rows, counts = [], Counter()
    for entry in coverage['slots']:
        state = entry['evidence_status']
        matched = candidates(entry['plan'], entry['evidence'], campaign['penalty_cents']) if state == 'VERIFIED' else []
        if state == 'VERIFIED':
            status = 'VIOLATION' if matched else 'COMPLIANT'
        else:
            status = state
        applied = matched[0] if matched else None
        reason = applied['code'] if applied else entry['reason']
        rows.append({'key': entry['key'], 'store': entry['store'], 'slot': entry['slot'], 'group': entry['group'],
                     'category': entry['category'], 'status': status, 'reason': reason, 'candidates': matched,
                     'applied': applied, 'original_cents': applied['cents'] if applied else 0,
                     'visit': entry['visit'], 'plan': entry['plan'], 'plan_candidates': entry['plan_candidates'],
                     'evidence': entry['evidence'], 'roster_source': entry['source']})
        counts[status] += 1
    return {'rows': rows, 'counts': {key: counts[key] for key in ('COMPLIANT', 'VIOLATION', 'PENDING', 'ISOLATED')}}
