import base64
import binascii

from app.config import MAX_PHOTO_BYTES
from app.errors import AuditError
from app.manifest import now
from app.modules.appeals.service import appeal_balances, with_appeals
from app.modules.intake.clock import get_zone, utc_timestamp
from app.modules.intake.service import PHOTO_FILE
from app.modules.intake.values import InvalidRow, identifier, sku
from app.modules.penalties.rules import candidates
from app.modules.photos.fingerprints import png_hash
from app.reasons import REASONS


class InvalidSubmission(Exception):
    """补交内容未通过校验：整笔修订记为 FAILED，不改动任何柜位。"""

    def __init__(self, code, message, evidence=None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.evidence = evidence


def base_rows(snapshot):
    return {row['key']: row for row in snapshot['penalties']['rows']}


def current_states(snapshot):
    """原批次结论 + 已生效修订逐柜叠加后的当前结论（含证据）。"""
    judged = base_rows(snapshot)
    states = {}
    for row in snapshot['coverage']['slots']:
        states[row['key']] = {'status': judged[row['key']]['status'], 'reason': judged[row['key']]['reason'],
                              'original_cents': judged[row['key']]['original_cents'], 'evidence': row['evidence']}
    for revision in snapshot['revisions']:
        if revision['status'] != 'APPLIED':
            continue
        for change in revision['changes']:
            states[change['key']] = {'status': change['after']['status'], 'reason': change['after']['reason'],
                                     'original_cents': change['after']['original_cents'],
                                     'evidence': change['after']['evidence']}
    return states


def known_photos(snapshot):
    """当前生效的照片编号与摘要绑定（原批次采信件 + 已生效修订补交件）。"""
    ids, digests = set(), {}
    for row in snapshot['photos']['photos']:
        ids.add(row['photo'])
        digests.setdefault(row['sha256'], set()).add((row['visit'], row['slot']))
    for revision in snapshot['revisions']:
        if revision['status'] != 'APPLIED':
            continue
        for change in revision['changes']:
            for photo in change['after']['evidence']['photos']:
                ids.add(photo['photo'])
                digests.setdefault(photo['sha256'], set()).add((change['visit'], change['slot']))
    return ids, digests


def find_cabinet(snapshot, item):
    key = item['key']
    cabinet = next((row for row in snapshot['coverage']['slots'] if row['key'] == key), None)
    if cabinet is None:
        raise InvalidSubmission('SHELF_NOT_SAMPLED', '该柜位未在本次抽中', key)
    return cabinet


def check_supplementable(snapshot, item, cabinet, states):
    key = item['key']
    state = states[key]
    if state['status'] != 'PENDING':
        raise InvalidSubmission('CABINET_NOT_PENDING', '该柜位已有结论，不接受补交', state['status'])
    if cabinet['visit'] is None:
        raise InvalidSubmission('NO_VISIT_FOR_SUPPLEMENT', '柜位所属门店未有效到访，无法绑定补交照片', key)
    if any(event['key'] == key for event in snapshot['events']):
        raise InvalidSubmission('APPEAL_LOCKED', '该柜位已有异议记录，不能补交修订', key)


def prepare_photo(item, cabinet, visit, snapshot, number, taken_ids):
    submitted = item.get('photo')
    if submitted is None:
        return None
    key = item['key']
    try:
        photo_id = identifier(submitted['photo'])
    except InvalidRow as error:
        raise InvalidSubmission('BAD_ID', '补交照片编号无效', key) from error
    if photo_id in taken_ids:
        raise InvalidSubmission('PHOTO_ID_CONFLICT', '补交照片编号与已登记原件冲突', photo_id)
    filename = submitted['file'].strip()
    if not PHOTO_FILE.fullmatch(filename):
        raise InvalidSubmission('BAD_PHOTO_FILE', '照片文件名或内容无效', filename)
    try:
        content = base64.b64decode(submitted['content_base64'], validate=True)
    except (binascii.Error, ValueError) as error:
        raise InvalidSubmission('BAD_PHOTO_FILE', '照片文件名或内容无效', key) from error
    if len(content) > MAX_PHOTO_BYTES:
        raise InvalidSubmission('SOURCE_TOO_LARGE', '巡检档件超过容量上限', filename)
    try:
        digest = png_hash(content)
    except InvalidRow as error:
        raise InvalidSubmission('BAD_PHOTO_FILE', '照片文件名或内容无效', key) from error
    store = next(row for row in snapshot['intake']['stores'] if row['store'] == cabinet['store'])
    try:
        captured = utc_timestamp(submitted['captured'], get_zone(store['timezone']))
    except InvalidRow as error:
        raise InvalidSubmission(error.code, '拍摄时刻无法解释', key) from error
    taken_ids.add(photo_id)
    return {'photo': photo_id, 'visit': visit['visit'], 'slot': cabinet['slot'], 'file': filename,
            'captured_utc': captured.isoformat(), 'sha256': digest,
            'skew_seconds': (captured - utc_timestamp(visit['at_utc'])).total_seconds(),
            'source': {'id': f'revision-{number}:{key}'}}


def photo_issue(photo, visit, snapshot, digests):
    """复用优先于超窗；同柜同摘要只表示重复支持。"""
    if digests.get(photo['sha256'], set()) - {(visit['visit'], photo['slot'])}:
        return 'PHOTO_REUSED'
    if abs(photo['skew_seconds']) > snapshot['campaign']['max_photo_skew_min'] * 60:
        return 'PHOTO_EXPIRED'
    return None


def prepare_observations(item, snapshot, number):
    aliases = snapshot['plans']['aliases']
    entries, completed = [], []
    for index, row in enumerate(item['observations'], start=1):
        source = f"revision-{number}:{item['key']}:{index}"
        if row['kind'] == 'COMPLETE':
            completed.append(source)
            continue
        try:
            name = sku(row['sku'])
        except InvalidRow as error:
            raise InvalidSubmission('BAD_SKU', '商品编号无效', item['key']) from error
        entries.append({'sku': aliases.get(name, name), 'facings': row['facings'],
                        'price_cents': row['price_cents'], 'source': source})
    return entries, completed


def judge_after(plan, photos, prior_products, entries, completed, photo_issues, snapshot):
    groups = {}
    for name, seen in prior_products.items():
        groups.setdefault(name, {}).setdefault((seen['facings'], seen['price_cents']), []).extend(seen['sources'])
    for entry in entries:
        groups.setdefault(entry['sku'], {}).setdefault((entry['facings'], entry['price_cents']),
                                                       []).append(entry['source'])
    conflicting = sorted(name for name, values in groups.items() if len(values) > 1)
    merged = {}
    for name, values in groups.items():
        (facings, price), _ = next(iter(values.items()))
        merged[name] = {'facings': facings, 'price_cents': price,
                        'sources': [source for sources in values.values() for source in sources]}
    evidence = {'photos': photos, 'products': merged, 'completed_sources': completed,
                'conflicting_skus': conflicting, 'photo_issues': photo_issues}
    if not photos:
        reason = 'PHOTO_REUSED' if 'PHOTO_REUSED' in photo_issues else 'MISSING_PHOTO'
        status, matched = ('ISOLATED', []) if reason == 'PHOTO_REUSED' else ('PENDING', [])
    elif conflicting:
        status, reason, matched = 'ISOLATED', 'OBSERVATION_CONFLICT', []
    elif not completed:
        status, reason, matched = 'PENDING', 'SCAN_INCOMPLETE', []
    else:
        matched = candidates(plan, {'products': merged, 'completed_sources': completed},
                             snapshot['campaign']['penalty_cents'])
        status, reason = ('VIOLATION', matched[0]['code']) if matched else ('COMPLIANT', None)
    applied = matched[0] if matched else None
    return {'status': status, 'reason': reason, 'original_cents': applied['cents'] if applied else 0,
            'applied': applied, 'candidates': matched, 'evidence': evidence}


def prepare_change(snapshot, item, cabinet, photo, issue, number, states):
    key = item['key']
    state = states[key]
    entries, completed = prepare_observations(item, snapshot, number)
    prior = state['evidence']
    photos = [*prior['photos'], *([photo] if photo and issue is None else [])]
    issues = sorted({*prior['photo_issues'], *([issue] if issue else [])})
    after = judge_after(cabinet['plan'], photos, prior['products'], entries,
                        [*prior['completed_sources'], *completed], issues, snapshot)
    before = {'status': state['status'], 'reason': state['reason'], 'original_cents': state['original_cents']}
    return {'key': key, 'visit': cabinet['visit']['visit'], 'slot': cabinet['slot'], 'store': cabinet['store'],
            'before': before, 'after': after, 'delta_cents': after['original_cents'] - before['original_cents'],
            'supplement': {'photo': photo, 'issue': issue}}


def revision_ledger(snapshot, changes, states):
    """修订前后逐柜金额勾稽：修订后罚额＝修订前＋差额，净额＝修订后罚额－已裁定减免。"""
    before_cents = sum(state['original_cents'] for state in states.values())
    for change in changes:
        current = states[change['key']]
        before = change['before']
        if (current['status'], current['reason'], current['original_cents']) != \
                (before['status'], before['reason'], before['original_cents']):
            raise AuditError('AMOUNT_LEDGER_MISMATCH', '修订前柜位金额与批次不符', 500, change['key'])
    delta = sum(change['delta_cents'] for change in changes)
    reductions = appeal_balances(snapshot)['reduction_cents']
    after_cents = before_cents + delta
    if after_cents < reductions:
        raise AuditError('AMOUNT_LEDGER_MISMATCH', '修订后罚额不足以抵减已裁定减免', 500)
    return {'before_cents': before_cents, 'delta_cents': delta, 'after_cents': after_cents,
            'reduction_cents': reductions, 'net_cents': after_cents - reductions, 'balanced': True}


def apply_revision(snapshot, payload, number):
    """校验并试算一笔补交修订；任何柜位未过校验则整笔记为 FAILED，其余柜位不动。"""
    base = {'revision': number, 'request_id': payload['request_id'], 'actor': payload['actor'],
            'note': payload['note'], 'created_at': now()}

    def failed(code, message, evidence=None):
        return 'FAILED', {**base, 'status': 'FAILED', 'changes': [], 'ledger': None,
                          'error': {'code': code, 'message': message, 'evidence': evidence}}

    keys = [item['key'] for item in payload['items']]
    if len(set(keys)) != len(keys):
        return failed('DUPLICATE_ITEM_KEY', '同一柜位在一笔补交中重复出现', sorted(keys))
    states = current_states(snapshot)
    taken_ids, digests = known_photos(snapshot)
    try:
        cabinets = [find_cabinet(snapshot, item) for item in payload['items']]
        for item, cabinet in zip(payload['items'], cabinets):
            check_supplementable(snapshot, item, cabinet, states)
        photos = []
        for item, cabinet in zip(payload['items'], cabinets):
            photo = prepare_photo(item, cabinet, cabinet['visit'], snapshot, number, taken_ids)
            if photo is not None:
                digests.setdefault(photo['sha256'], set()).add((cabinet['visit']['visit'], cabinet['slot']))
            photos.append(photo)
        changes = [prepare_change(snapshot, item, cabinet, photo,
                                  photo and photo_issue(photo, cabinet['visit'], snapshot, digests),
                                  number, states)
                   for item, cabinet, photo in zip(payload['items'], cabinets, photos)]
    except InvalidSubmission as error:
        return failed(error.code, error.message, error.evidence)
    ledger = revision_ledger(snapshot, changes, states)
    return 'APPLIED', {**base, 'status': 'APPLIED', 'error': None, 'changes': changes, 'ledger': ledger}


def build_revert(snapshot, number, payload):
    revision = next(row for row in snapshot['revisions'] if row['revision'] == number)
    locked = sorted({change['key'] for change in revision['changes']
                     if any(event['key'] == change['key'] for event in snapshot['events'])})
    if locked:
        raise AuditError('APPEAL_LOCKED', '修订柜位已有异议记录，不能恢复', 409, locked)
    return {'request_id': payload['request_id'], 'actor': payload['actor'], 'note': payload['note'],
            'created_at': now()}


def revision_view(snapshot):
    """批次的修订视图：修订链、逐柜前后对照、原批次到净罚额的勾稽桥。"""
    base = base_rows(snapshot)
    current = {key: {'status': row['status'], 'reason': row['reason'], 'original_cents': row['original_cents']}
               for key, row in base.items()}
    touched = {}
    for revision in snapshot['revisions']:
        if revision['status'] != 'APPLIED':
            continue
        for change in revision['changes']:
            key = change['key']
            current[key] = {'status': change['after']['status'], 'reason': change['after']['reason'],
                            'original_cents': change['after']['original_cents']}
            touched[key] = {'key': key, 'revision': revision['revision'],
                            'original': {'status': base[key]['status'], 'reason': base[key]['reason'],
                                         'original_cents': base[key]['original_cents']},
                            'current': dict(current[key])}
    original = snapshot['settlement']['original_cents']
    revised = sum(state['original_cents'] for state in current.values())
    balances = appeal_balances(snapshot)
    net = revised - balances['reduction_cents']
    if revised != original + sum(row['current']['original_cents'] - row['original']['original_cents']
                                 for row in touched.values()) or net < 0:
        raise AuditError('AMOUNT_LEDGER_MISMATCH', '修订净额对账失败', 500)
    return {'count': len(snapshot['revisions']),
            'applied': sum(row['status'] == 'APPLIED' for row in snapshot['revisions']),
            'revisions': snapshot['revisions'], 'rows': [touched[key] for key in sorted(touched)],
            'ledger': {'original_cents': original, 'revision_delta_cents': revised - original,
                       'revised_original_cents': revised, 'reduction_cents': balances['reduction_cents'],
                       'net_cents': net, 'balanced': True}}


def with_ledger(snapshot):
    return {**with_appeals(snapshot), 'revisions': revision_view(snapshot)}


def export_revisions(snapshot):
    settlement = snapshot['settlement']
    return {'format': 'shelf-evidence/revision-1', 'generated_at': now(), 'manifest': snapshot['manifest'],
            'campaign': {key: snapshot['campaign'][key] for key in ('code', 'version', 'title')},
            'original': {key: settlement[key] for key in ('target', 'selected', 'unfilled', 'counts',
                                                          'original_cents', 'strata')},
            **revision_view(snapshot), 'appeals': appeal_balances(snapshot),
            'reason_dictionary': REASONS}
