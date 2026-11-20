from collections import defaultdict

from app.modules.intake.clock import get_zone, utc_timestamp
from app.modules.intake.records import load_unique
from app.modules.intake.service import PHOTO_FILE
from app.modules.intake.values import InvalidRow, identifier
from app.modules.photos.fingerprints import png_hash, reused_groups
from app.reasons import REASONS, mark


def bind_photos(intake, bundle):
    visits = {row['visit']: row for row in intake['visits']}
    stores = {row['store']: row for row in intake['stores']}
    slots = {(row['store'], row['slot']) for row in intake['slots']}
    limit_seconds = intake['campaign']['max_photo_skew_min'] * 60
    hashes = {}

    def convert(row):
        photo, visit, slot = (identifier(row[field]) for field in ('photo', 'visit', 'slot'))
        if visit not in visits:
            raise InvalidRow('UNKNOWN_VISIT')
        store = visits[visit]['store']
        if (store, slot) not in slots:
            raise InvalidRow('UNKNOWN_SLOT')
        filename = row['file'].strip()
        if not PHOTO_FILE.fullmatch(filename):
            raise InvalidRow('BAD_PHOTO_FILE')
        captured = utc_timestamp(row['captured'], get_zone(stores[store]['timezone']))
        skew = (captured - utc_timestamp(visits[visit]['at_utc'])).total_seconds()
        if filename not in hashes:
            hashes[filename] = png_hash(bundle.get(f'photos/{filename}'))
        return {'photo': photo, 'visit': visit, 'slot': slot, 'file': filename,
                'captured_utc': captured.isoformat(), 'skew_seconds': skew, 'sha256': hashes[filename],
                'within_capture_window': abs(skew) <= limit_seconds}

    conflicts = []
    rows, issues = load_unique(intake['tables']['photos'], convert, ('photo',), conflicting=conflicts)
    candidate_rows = rows + conflicts
    rejected, accepted = defaultdict(set), []
    decisions = {row['source']['id']: row for row in conflicts}
    for issue in issues:
        if item := decisions.get(issue['source']['id']):
            issue.update(reason='PHOTO_ID_CONFLICT', label=REASONS['PHOTO_ID_CONFLICT'],
                         visit=item['visit'], slot=item['slot'], photo=item['photo'])
            rejected[item['visit'], item['slot']].add('PHOTO_ID_CONFLICT')
    duplicate = reused_groups(candidate_rows)
    for row in rows:
        key = row['visit'], row['slot']
        if row['sha256'] in duplicate:
            group = duplicate[row['sha256']]
            reason = 'PHOTO_REUSED'
            extra = {'sha256': row['sha256'], 'related_sources': sorted(item['source']['id'] for item in group)}
        elif not row['within_capture_window']:
            reason, extra = 'PHOTO_EXPIRED', {'skew_seconds': row['skew_seconds']}
        else:
            accepted.append(row)
            continue
        rejected[key].add(reason)
        issues.append(mark(row['source'], reason, visit=row['visit'], slot=row['slot'], photo=row['photo'], **extra))
    groups = [{'sha256': digest, 'bindings': sorted({(row['visit'], row['slot']) for row in group}),
               'sources': sorted(row['source']['id'] for row in group)} for digest, group in sorted(duplicate.items())]
    return accepted, rejected, groups, issues
