from copy import deepcopy

import pytest

from app.errors import AuditError
from app.modules.plans.aliases import aliases_from
from app.modules.plans.windows import PlanIndex, latest_visits
from conftest import locate_or_fail


def test_exact_rollover_takes_new_plan_only(field):  # TRAP-23
    row = locate_or_fail(field.plans['decisions'], store='002', slot='A03')
    assert row['visit']['at_utc'] == '2026-11-09T00:00:00+00:00'
    assert row['plan']['plan'] == 'NEW-212' and row['candidates'] == []
    before = locate_or_fail(field.plans['decisions'], store='001', slot='A01')
    assert before['plan']['plan'] == 'OLD-210'


def test_overlap_is_isolated_with_both_plan_versions(field):  # TRAP-25
    row = locate_or_fail(field.plans['decisions'], store='002', slot='A04')
    assert row['plan'] is None and row['reason'] == 'PLAN_OVERLAP'
    assert [item['plan'] for item in row['candidates']] == ['HOL-801', 'HOL-802']
    assert [item['source']['id'] for item in row['candidates']] == ['plans.csv:4', 'plans.csv:5']


def test_conflicting_plan_id_never_silently_falls_back(field):  # TRAP-14
    field.bundle['plans.csv'] += b'NEW-212,SPIRIT,2026-11-20T00:00:00Z,2026-12-01T00:00:00Z,GR-211,9,15800\r\n'
    row = locate_or_fail(field.plans['decisions'], store='002', slot='A03')
    assert row['reason'] == 'PLAN_OVERLAP'
    assert [item['facings'] for item in row['candidates']] == [3]
    assert len([item for item in field.plans['quarantine'] if item['reason'] == 'KEY_CONFLICT']) == 2


def test_older_visit_is_retained_but_not_selected_when_input_is_out_of_order(field):  # TRAP-13
    result, replaced = latest_visits(list(reversed(field.intake['visits'])))
    assert result['001']['visit'] == 'V001'
    assert [(row['inactive_visit'], row['active_visit']) for row in replaced] == [('V000', 'V001')]


def test_alias_chain_is_order_independent(field):  # TRAP-22
    table = deepcopy(field.intake['tables']['aliases'])
    table['rows'].reverse()
    _, alias, _ = aliases_from(table)
    assert alias == field.plans['aliases']
    assert alias == {'新谷陈酿': 'GR-211', '谷雨旧装': 'GR-209', '谷雨陈酿': 'GR-209'}


def test_alias_cycle_returns_route(field):  # TRAP-20
    field.bundle['aliases.csv'] += 'GR-209,谷雨陈酿\r\n'.encode()
    with pytest.raises(AuditError) as failure:
        _ = field.plans
    assert failure.value.code == 'ALIAS_CYCLE'
    assert failure.value.evidence == ['GR-209', '谷雨陈酿', '谷雨旧装', 'GR-209']


def test_missing_category_and_bad_intervals_remain_distinct(field):
    missing = PlanIndex(field.plans['plans'], []).at('OTHER','2026-11-09T00:00:00Z')
    assert missing == {'plan': None, 'reason': 'PLAN_MISSING', 'candidates': []}
    broken = locate_or_fail(field.plans['quarantine'], reason='BAD_INTERVAL')
    assert broken['source']['raw'][0] == 'BROKEN-901'
