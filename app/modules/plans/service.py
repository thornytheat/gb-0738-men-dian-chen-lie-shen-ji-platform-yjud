from app.modules.plans.aliases import aliases_from
from app.modules.plans.windows import PlanIndex, latest_visits, plan_versions


def plan_shelf(intake):
    tables = intake['tables']
    alias_rows, aliases, alias_issues = aliases_from(tables['aliases'])
    plans, conflicting, plan_issues = plan_versions(tables['plans'], aliases)
    selected, replaced = latest_visits(intake['visits'])
    index = PlanIndex(plans, conflicting)
    decisions = []
    for slot in intake['slots']:
        visit = selected.get(slot['store'])
        result = (index.at(slot['category'], visit['at_utc']) if visit else
                  {'plan': None, 'reason': 'VISIT_MISSING', 'candidates': []})
        decisions.append({'store': slot['store'], 'slot': slot['slot'], 'category': slot['category'],
                          'roster_source': slot['source'], 'visit': visit, **result})
    return {'decisions': decisions, 'plans': plans, 'alias_rows': alias_rows, 'aliases': aliases,
            'replaced_visits': replaced, 'quarantine': alias_issues + plan_issues}
