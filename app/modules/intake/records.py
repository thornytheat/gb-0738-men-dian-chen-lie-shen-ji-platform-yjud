from collections import defaultdict

from app.modules.intake.clock import get_zone, utc_timestamp
from app.modules.intake.values import InvalidRow, clean, identifier
from app.reasons import mark


def load_unique(table, convert, primary, conflicting=None):
    groups = defaultdict(list)
    accepted, issues = [], list(table['quarantine'])
    for row in table['rows']:
        source = row['source']
        try:
            spec = convert(row)
            groups[tuple(spec[column] for column in primary)].append((source, spec))
        except InvalidRow as error:
            issues.append(mark(source, error.code, row_key=[row[column] for column in primary]))
    for key, entries in sorted(groups.items()):
        source, spec = entries[0]
        if any(other != spec for _, other in entries[1:]):
            if conflicting is not None:
                conflicting.extend({'source': row, **value} for row, value in entries)
            issues.extend(mark(row, 'KEY_CONFLICT', row_key=key, conflicts=[s['id'] for s, _ in entries])
                          for row, _ in entries)
            continue
        accepted.append({'source': source, **spec})
        issues.extend(mark(row, 'DUPLICATE_ROW', row_key=key, kept=source['id']) for row, _ in entries[1:])
    return accepted, issues


def stores_from(table, groups):
    def convert(row):
        group = identifier(row['group'])
        if group not in groups:
            raise InvalidRow('UNKNOWN_GROUP')
        return {'store': identifier(row['store']), 'title': clean(row['title']) or identifier(row['store']),
                'group': group, 'timezone': get_zone(row['timezone']).key}

    return load_unique(table, convert, ('store',))


def slots_from(table, store_map):
    def convert(row):
        store = identifier(row['store'])
        if store not in store_map:
            raise InvalidRow('UNKNOWN_STORE')
        return {'store': store, 'slot': identifier(row['slot']), 'category': identifier(row['category'])}

    return load_unique(table, convert, ('store', 'slot'))


def visits_from(table, store_map, campaign):
    start, end = [utc_timestamp(campaign[key]) for key in ('start_utc', 'end_utc')]

    def convert(row):
        store = identifier(row['store'])
        if store not in store_map:
            raise InvalidRow('UNKNOWN_STORE')
        moment = utc_timestamp(row['clock'], get_zone(store_map[store]['timezone']))
        if not start <= moment < end:
            raise InvalidRow('OUTSIDE_CAMPAIGN')
        return {'store': store, 'visit': identifier(row['visit']), 'at_utc': moment.isoformat()}

    return load_unique(table, convert, ('visit',))
