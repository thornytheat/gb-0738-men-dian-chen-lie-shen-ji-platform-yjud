from collections import defaultdict

from app.modules.intake.clock import utc_timestamp
from app.modules.intake.records import load_unique
from app.modules.intake.values import InvalidRow, identifier, integer, sku


def plan_versions(table, aliases):
    def convert(row):
        start, end = (utc_timestamp(row[key]) for key in ('start_utc', 'end_utc'))
        if start >= end:
            raise InvalidRow('BAD_INTERVAL')
        name = sku(row['sku'])
        return {'plan': identifier(row['plan']), 'category': identifier(row['category']),
                'start_utc': start.isoformat(), 'end_utc': end.isoformat(), 'sku': aliases.get(name, name),
                'facings': integer(row['facings'], 1, 999), 'price_cents': integer(row['price_cents'], 1, 10_000_000)}

    conflicts = []
    rows, issues = load_unique(table, convert, ('plan',), conflicting=conflicts)
    return rows, conflicts, issues


def latest_visits(rows):
    visits = defaultdict(list)
    for visit in rows:
        visits[visit['store']].append(visit)
    active, replaced = {}, []
    for store, records in sorted(visits.items()):
        records.sort(key=lambda visit: (utc_timestamp(visit['at_utc']), visit['visit']), reverse=True)
        active[store], *rest = records
        replaced.extend({'store': store, 'inactive_visit': row['visit'], 'active_visit': active[store]['visit'],
                         'source': row['source']} for row in rest)
    return active, replaced


class PlanIndex:
    def __init__(self, rows, conflicts):
        self.by_category = defaultdict(list)
        for row in [*rows, *conflicts]:
            self.by_category[row['category']].append((utc_timestamp(row['start_utc']), utc_timestamp(row['end_utc']), row))
        self.conflicts = {row['source']['id'] for row in conflicts}

    def at(self, category, instant):
        stamp = utc_timestamp(instant)
        active = [row for start, end, row in self.by_category[category] if start <= stamp < end]
        active.sort(key=lambda row: (row['plan'], row['source']['line']))
        if not active:
            return {'plan': None, 'reason': 'PLAN_MISSING', 'candidates': []}
        if len(active) > 1 or active[0]['source']['id'] in self.conflicts:
            return {'plan': None, 'reason': 'PLAN_OVERLAP', 'candidates': active}
        return {'plan': active[0], 'reason': None, 'candidates': []}
