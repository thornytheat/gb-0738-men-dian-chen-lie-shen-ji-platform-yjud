from app.errors import AuditError
from app.modules.intake.records import load_unique
from app.modules.intake.values import sku


def aliases_from(table):
    def convert(row):
        return {field: sku(row[field]) for field in ('alias', 'sku')}

    rows, issues = load_unique(table, convert, ('alias',))
    conflicts = [row for row in issues if row['reason'] == 'KEY_CONFLICT']
    if conflicts:
        raise AuditError('ALIAS_CONFLICT', '商品旧名有多个归属', evidence=conflicts)
    links = {item['alias']: item['sku'] for item in rows if item['alias'] != item['sku']}
    canonical = {}
    for first in links:
        current, route = first, {}
        while current in links and current not in canonical:
            if current in route:
                raise AuditError('ALIAS_CYCLE', '商品旧名出现循环', evidence=[*route, current])
            route[current] = True
            current = links[current]
        canonical.update(dict.fromkeys(route, canonical.get(current, current)))
    return rows, canonical, issues
