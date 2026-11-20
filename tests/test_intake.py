import pytest

from app.errors import AuditError
from app.modules.intake.clock import get_zone, utc_timestamp
from app.modules.intake.csv_reader import read_csv
from app.modules.intake.values import InvalidRow, integer
from conftest import locate_or_fail


def test_encoded_archive_preserves_multiline_chinese_source(field):  # TRAP-01 TRAP-03
    table = field.intake['tables']['stores']
    assert table['encoding'] == 'gb18030'
    source = locate_or_fail(table['rows'], store='088')['source']
    assert (source['line'], source['end_line'], source['raw'][1]) == (8, 9, '卷宗\n空址 ')
    assert locate_or_fail(field.intake['quarantine'], reason='BAD_ZONE')['source'] == source


def test_bom_segment_headers_and_extra_columns(field):  # TRAP-02 TRAP-04 TRAP-05
    table = field.intake['tables']['slots']
    assert (table['encoding'], table['blank'], table['repeated_headers'], table['input']) == ('utf-8-sig', 1, 1, 28)
    broken, = table['quarantine']
    assert broken['reason'] == 'COLUMN_COUNT'
    assert broken['source']['raw'] == ['002', 'A08', 'SPIRIT', '多列']


def test_store_codes_keep_leading_zero(field):  # TRAP-08
    assert [row['store'] for row in field.intake['stores']] == ['001', '002', '003', '004', '005', '006']
    assert locate_or_fail(field.intake['quarantine'], reason='UNKNOWN_STORE')['source']['raw'][0] == '099'


def test_offsets_and_naive_store_timezone_resolve_to_same_visit(field):  # TRAP-11
    current = locate_or_fail(field.intake['visits'], visit='V002')
    assert current['at_utc'] == '2026-11-09T00:00:00+00:00'
    assert locate_or_fail(field.intake['quarantine'], reason='DUPLICATE_ROW', kept='visits.csv:3')['source']['raw'][2] == '2026-11-09T00:00:00Z'


def test_dst_ambiguity_gap_and_explicit_offsets(field):  # TRAP-12
    bad = locate_or_fail(field.intake['quarantine'], reason='AMBIGUOUS_CLOCK')
    assert bad['source']['raw'][0] == 'V777'
    with pytest.raises(InvalidRow) as gap:
        utc_timestamp('2026-03-08T02:10:00', get_zone('America/New_York'))
    assert gap.value.code == 'NONEXISTENT_CLOCK'
    left = utc_timestamp('2026-11-01T01:25:00-04:00')
    right = utc_timestamp('2026-11-01T01:25:00-05:00')
    assert (right - left).total_seconds() == 3600


def test_campaign_upper_boundary_is_exclusive(field):  # TRAP-23
    outside = locate_or_fail(field.intake['quarantine'], reason='OUTSIDE_CAMPAIGN')
    assert outside['source']['raw'] == ['V999', '005', '2026-12-01T00:00:00Z']
    assert 'V999' not in {row['visit'] for row in field.intake['visits']}


def test_table_rejects_unclosed_quote_and_distinguishes_empty_states(field):  # TRAP-16 TRAP-18
    data = field.bundle['visits.csv']
    with pytest.raises(AuditError) as error:
        read_csv(data + b'V888,001,"', 'visits')
    assert (error.value.code, error.value.evidence['line']) == ('MALFORMED_CSV', 12)
    states = [read_csv(raw, 'visits')['state'] for raw in (b'', b'\n, ,\n', b'visit,store,clock\n')]
    assert states == ['EMPTY_FILE', 'BLANK_FILE', 'HEADER_ONLY']


def test_integer_rules_keep_fullwidth_amount_exact():  # TRAP-06
    assert integer(' １３，８００ ', 0, 15000) == 13800
    with pytest.raises(InvalidRow) as error:
        integer('138,00', 0, 15000)
    assert error.value.code == 'BAD_NUMBER'
