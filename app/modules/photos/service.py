from collections import defaultdict

from app.modules.photos.bindings import bind_photos
from app.modules.photos.observations import read_observations, summarize_observations
from app.reasons import mark


def collect_evidence(intake, plans, bundle):
    photos, rejected, duplicates, photo_issues = bind_photos(intake, bundle)
    observations, observed, observation_issues, unreadable = read_observations(intake['tables']['observations'], photos, plans['aliases'])
    bound = defaultdict(list)
    for row in photos:
        bound[row['visit'], row['slot']].append(row)
    results, conflicting_ids = [], set()
    for visit, slot in sorted(bound.keys() | rejected.keys()):
        key = visit, slot
        accepted = bound[key]
        reasons = sorted(rejected[key])
        products, completeness, conflicts = summarize_observations(observed[key])
        for item in observed[key]:
            if item.get('sku') in conflicts:
                conflicting_ids.add(item['source']['id'])
                observation_issues.append(mark(item['source'], 'OBSERVATION_CONFLICT', visit=visit, slot=slot,
                                               photo=item['photo'], sku=item['sku']))
        if not accepted:
            reason = next((code for code in ('PHOTO_ID_CONFLICT', 'PHOTO_REUSED') if code in reasons), 'MISSING_PHOTO')
        elif conflicts or key in unreadable:
            reason = 'OBSERVATION_CONFLICT' if conflicts else 'BAD_OBSERVATION'
        elif not completeness:
            reason = 'SCAN_INCOMPLETE'
        else:
            reason = None
        results.append({'visit': visit, 'slot': slot, 'photos': accepted, 'products': products,
                        'completed_sources': completeness, 'conflicting_skus': conflicts,
                        'photo_issues': reasons, 'reason': reason})
    return {'photos': photos, 'observations': [row for row in observations if row['source']['id'] not in conflicting_ids], 'bindings': results, 'reused_groups': duplicates,
            'quarantine': photo_issues + observation_issues}
