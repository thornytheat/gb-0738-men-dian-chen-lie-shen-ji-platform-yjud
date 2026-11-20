from hashlib import sha256


def apportion(groups, target):
    """按权重最大余数法分配目标柜数，余数并列时按店组编号顺序。"""
    total = sum(group['weight'] for group in groups)
    quotas, remainders = {}, []
    for group in groups:
        exact = target * group['weight']
        quota, remainder = divmod(exact, total)
        quotas[group['code']] = quota
        remainders.append((-remainder, group['code']))
    remainders.sort()
    for _, code in remainders[:target - sum(quotas.values())]:
        quotas[code] += 1
    return quotas


def draw_score(seed, store, slot):
    return sha256(b'\0'.join((seed.encode(), store.encode(), slot.encode()))).hexdigest()


def choose_slots(intake, sample_size):
    """按店组分层确定性抽签，返回抽中柜位行与各店组配额，结果与输入行序无关。"""
    campaign = intake['campaign']
    groups = {row['store']: row['group'] for row in intake['stores']}
    quotas = apportion(campaign['groups'], sample_size)
    rows, strata = [], []
    for group in campaign['groups']:
        code = group['code']
        pool = sorted(
            ({'key': f"{slot['store']}:{slot['slot']}", 'store': slot['store'], 'slot': slot['slot'],
              'group': code, 'category': slot['category'], 'source': slot['source'],
              'score': draw_score(campaign['seed'], slot['store'], slot['slot'])}
             for slot in intake['slots'] if groups.get(slot['store']) == code),
            key=lambda row: (row['score'], row['key']))
        target = quotas[code]
        chosen = pool[:target]
        rows.extend({**row, 'rank': rank} for rank, row in enumerate(chosen, start=1))
        strata.append({'code': code, 'title': group['title'], 'weight': group['weight'], 'target': target,
                       'pool': len(pool), 'selected': len(chosen), 'unfilled': target - len(chosen),
                       'ranked_candidates': pool})
    return rows, strata
