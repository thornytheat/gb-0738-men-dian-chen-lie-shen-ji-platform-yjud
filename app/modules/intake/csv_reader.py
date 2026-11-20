import codecs
import csv
import io

from app.errors import AuditError
from app.reasons import mark

HEADERS = {
    'stores': ('store', 'title', 'group', 'timezone'),
    'slots': ('store', 'slot', 'category'),
    'visits': ('visit', 'store', 'clock'),
    'plans': ('plan', 'category', 'start_utc', 'end_utc', 'sku', 'facings', 'price_cents'),
    'aliases': ('alias', 'sku'),
    'photos': ('photo', 'visit', 'slot', 'file', 'captured'),
    'observations': ('visit', 'slot', 'photo', 'kind', 'sku', 'facings', 'price_cents'),
}


def decode(raw, filename):
    encodings = ('utf-8-sig',) if raw.startswith(codecs.BOM_UTF8) else ('utf-8', 'gb18030')
    for coding in encodings:
        try:
            text = raw.decode(coding)
        except UnicodeDecodeError:
            continue
        if '\0' not in text:
            return text, coding
        break
    raise AuditError('BAD_ENCODING', '无法识别档件编码', evidence=filename)


def read_csv(raw, name):
    filename = name + '.csv'
    text, coding = decode(raw, filename)
    reader = csv.reader(io.StringIO(text, newline=''), strict=True)
    fields = None
    rows, quarantine = [], []
    blank = skipped = end = 0
    try:
        for values in reader:
            start, end = end + 1, reader.line_num
            if not any(value.strip() for value in values):
                blank += 1
                continue
            keys = tuple(value.strip() for value in values)
            if fields is None:
                if len(keys) != len(HEADERS[name]) or set(keys) != set(HEADERS[name]):
                    raise AuditError('BAD_HEADER', '档件字段不全或重复', evidence={'file': filename, 'line': start})
                fields = keys
            elif keys == fields:
                skipped += 1
            else:
                source = {'id': f'{filename}:{start}', 'file': filename, 'line': start, 'end_line': end, 'raw': values}
                if len(values) != len(fields):
                    hints = {key: values[fields.index(key)] for key in ('visit', 'slot', 'photo')
                             if key in fields and fields.index(key) < len(values)}
                    quarantine.append(mark(source, 'COLUMN_COUNT', **hints))
                else:
                    rows.append({'source': source, **dict(zip(fields, values))})
    except csv.Error as error:
        raise AuditError('MALFORMED_CSV', '档件引号未闭合或字段损坏',
                         evidence={'file': filename, 'line': reader.line_num}) from error
    if fields is None:
        state = 'BLANK_FILE' if blank else 'EMPTY_FILE'
    else:
        state = 'RECEIVED' if rows or quarantine else 'HEADER_ONLY'
    return {'name': filename, 'encoding': coding, 'blank': blank, 'repeated_headers': skipped, 'state': state,
            'input': len(rows) + len(quarantine), 'rows': rows, 'quarantine': quarantine}
