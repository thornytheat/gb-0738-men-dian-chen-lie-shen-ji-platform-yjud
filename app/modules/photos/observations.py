from collections import defaultdict

from app.modules.intake.values import InvalidRow, clean, identifier, integer, sku
from app.reasons import mark


def read_observations(table, photos, aliases):
    by_photo = {row['photo']: row for row in photos}
    by_binding = defaultdict(list)
    accepted, issues = [], list(table['quarantine'])
    unreadable = set()
    for row in table['rows']:
        visit = slot = None
        try:
            visit, slot, photo = (identifier(row[field]) for field in ('visit', 'slot', 'photo'))
            matched = by_photo.get(photo)
            if not matched or (visit, slot) != (matched['visit'], matched['slot']):
                raise InvalidRow('PHOTO_UNAVAILABLE')
            kind = clean(row['kind']).upper()
            if kind == 'COMPLETE' and not any(clean(row[field]) for field in ('sku', 'facings', 'price_cents')):
                values = {}
            elif kind == 'ITEM':
                name = sku(row['sku'])
                values = {'sku': aliases.get(name, name), 'facings': integer(row['facings'], 1, 999),
                          'price_cents': integer(row['price_cents'], 1, 10_000_000)}
            else:
                raise InvalidRow('BAD_OBSERVATION')
        except InvalidRow as error:
            issues.append(mark(row['source'], error.code, visit=visit, slot=slot, photo=row['photo']))
            if visit and slot and error.code != 'PHOTO_UNAVAILABLE':
                unreadable.add((visit, slot))
            continue
        item = {'source': row['source'], 'visit': visit, 'slot': slot, 'photo': photo, 'kind': kind, **values}
        accepted.append(item)
        by_binding[visit, slot].append(item)

    for mark_item in table['quarantine']:
        try:
            visit, slot, photo = (identifier(mark_item[key]) for key in ('visit', 'slot', 'photo'))
        except (KeyError, InvalidRow):
            continue
        if photo in by_photo and (visit, slot) == (by_photo[photo]['visit'], by_photo[photo]['slot']):
            unreadable.add((visit, slot))
    return accepted, by_binding, issues, unreadable


def summarize_observations(rows):
    products, completeness, conflicts = {}, [], set()
    for item in rows:
        if item['kind'] == 'COMPLETE':
            completeness.append(item['source']['id'])
        else:
            code = item['sku']
            prior = products.setdefault(code, {'facings': item['facings'], 'price_cents': item['price_cents'], 'sources': []})
            if (prior['facings'], prior['price_cents']) != (item['facings'], item['price_cents']):
                conflicts.add(code)
            prior['sources'].append(item['source']['id'])
    return products, completeness, sorted(conflicts)
