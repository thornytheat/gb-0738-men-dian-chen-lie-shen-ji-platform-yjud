from app.modules.penalties.rules import candidates
from conftest import locate_or_fail


def test_missing_photo_and_missing_sku_have_distinct_amounts(field):  # TRAP-28
    actual = field.penalties['rows']
    no_photo = locate_or_fail(actual, key='001:A04')
    missing = locate_or_fail(actual, key='002:A03')
    assert (no_photo['status'], no_photo['original_cents'], no_photo['reason']) == ('PENDING', 0, 'MISSING_PHOTO')
    assert (missing['status'], missing['original_cents'], missing['reason']) == ('VIOLATION', 15000, 'MISSING_SKU')
    assert missing['applied']['proof']['expected_sku'] == 'GR-211'
    assert missing['applied']['proof']['completed_sources'][0].startswith('observations.csv:')


def test_highest_applicable_rule_wins_without_summing(field):  # TRAP-19
    row = locate_or_fail(field.penalties['rows'], key='001:A03')
    assert [(rule['code'], rule['cents']) for rule in row['candidates']] == [('UNDER_FACINGS', 5500), ('PRICE_MISMATCH', 4000)]
    assert row['original_cents'] == 5500
    assert row['applied']['proof']['actual'] == 3


def test_equal_penalty_rules_use_stable_priority_not_mapping_order():  # TRAP-19
    price = {'PRICE_MISMATCH': 80, 'UNDER_FACINGS': 80}
    plan = {'sku': 'ONE', 'facings': 4, 'price_cents': 500}
    evidence = {'products': {'ONE': {'facings': 3, 'price_cents': 501, 'sources': ['line:2']}}}
    one = candidates(plan, evidence, price)
    assert one == candidates(plan, evidence, dict(reversed(tuple(price.items()))))
    assert one[0]['code'] == 'UNDER_FACINGS'


def test_wrong_sku_preserves_actual_goods_and_sources(field):
    row = locate_or_fail(field.penalties['rows'], key='005:A01')
    assert (row['reason'], row['original_cents']) == ('WRONG_SKU', 9000)
    assert row['applied']['proof']['skus'] == ['MALT-900']
    assert row['applied']['proof']['sources'][0].startswith('observations.csv:')


def test_overlapped_plan_and_conflicted_observations_cannot_be_fined(field):
    for key, reason in [('002:A04', 'PLAN_OVERLAP'), ('004:A02', 'OBSERVATION_CONFLICT'), ('001:A02', 'PHOTO_REUSED')]:
        row = locate_or_fail(field.penalties['rows'], key=key)
        assert (row['status'], row['reason'], row['original_cents'], row['candidates']) == ('ISOLATED', reason, 0, [])


def test_reference_all_compliant_at_calibrated_prices(reference):
    assert reference.penalties['counts'] == {'COMPLIANT': 18, 'VIOLATION': 0, 'PENDING': 0, 'ISOLATED': 0}
    assert all(row['original_cents'] == 0 for row in reference.penalties['rows'])


def test_complete_evidence_without_required_sku_cannot_create_under_facing():
    rules = {'MISSING_SKU': 15000, 'WRONG_SKU': 9000, 'UNDER_FACINGS': 5500, 'PRICE_MISMATCH': 4000}
    snapshot = {'products': {'OTHER': {'sources': ['obs:2']}}, 'completed_sources': ['obs:1']}
    codes = [row['code'] for row in candidates({'sku': 'A'}, snapshot, rules)]
    assert codes == ['MISSING_SKU', 'WRONG_SKU']
