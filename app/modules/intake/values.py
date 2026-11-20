import re
import unicodedata

ID = re.compile(r'^[A-Z0-9][A-Z0-9_-]{0,31}$')
INTEGER = re.compile(r'^(?:[0-9]+|[0-9]{1,3}(?:,[0-9]{3})+)$')


class InvalidRow(ValueError):
    def __init__(self, code):
        super().__init__(code)
        self.code = code


def clean(value):
    return unicodedata.normalize('NFKC', value).strip()


def identifier(value, code='BAD_ID'):
    value = clean(value).upper()
    if not ID.fullmatch(value):
        raise InvalidRow(code)
    return value


def sku(value):
    value = clean(value).casefold().upper()
    if not value or len(value) > 48 or any(unicodedata.category(piece).startswith('C') for piece in value):
        raise InvalidRow('BAD_SKU')
    return value


def integer(value, minimum, maximum):
    value = clean(value)
    if len(value) > 15 or not INTEGER.fullmatch(value):
        raise InvalidRow('BAD_NUMBER')
    number = int(value.replace(',', ''))
    if not minimum <= number <= maximum:
        raise InvalidRow('BAD_NUMBER')
    return number
