import re

from app.config import DATASETS, MAX_PHOTO_BYTES, MAX_PHOTOS, MAX_TABLE_BYTES, TABLES
from app.errors import AuditError
from app.modules.intake.catalog import load_campaign
from app.modules.intake.csv_reader import read_csv
from app.modules.intake.records import slots_from, stores_from, visits_from

PHOTO_FILE = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_.-]{0,62}\.png$')


def read_limited(path, limit):
    try:
        with path.open('rb') as stream:
            content = stream.read(limit + 1)
    except OSError as error:
        raise AuditError('SOURCE_UNAVAILABLE', '巡检档件无法读取', 503, path.name) from error
    if len(content) > limit:
        raise AuditError('SOURCE_TOO_LARGE', '巡检档件超过容量上限', 413, path.name)
    return content


def acquire(root, dataset):
    if dataset not in DATASETS:
        raise AuditError('UNKNOWN_DATASET', '请选择已登记的巡检档件', 404)
    folder = root / dataset
    names = ['campaign.json', *(f'{name}.csv' for name in TABLES)]
    bundle = {name: read_limited(folder / name, MAX_TABLE_BYTES) for name in names}
    images = sorted(path for path in (folder / 'photos').glob('*.png') if PHOTO_FILE.fullmatch(path.name))
    if len(images) > MAX_PHOTOS:
        raise AuditError('SOURCE_TOO_LARGE', '照片张数超过档件上限', 413)
    bundle.update({f'photos/{path.name}': read_limited(path, MAX_PHOTO_BYTES) for path in images})
    return bundle


def receive(bundle):
    campaign = load_campaign(bundle['campaign.json'])
    tables = {name: read_csv(bundle[f'{name}.csv'], name) for name in TABLES}
    groups = {row['code'] for row in campaign['groups']}
    stores, stores_issues = stores_from(tables['stores'], groups)
    index = {row['store']: row for row in stores}
    slots, slots_issues = slots_from(tables['slots'], index)
    visits, visit_issues = visits_from(tables['visits'], index, campaign)
    quarantine = stores_issues + slots_issues + visit_issues
    return {'campaign': campaign, 'tables': tables, 'stores': stores, 'slots': slots, 'visits': visits,
            'quarantine': quarantine}
