from datetime import datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.modules.intake.values import InvalidRow, clean


def get_zone(value):
    try:
        return ZoneInfo(clean(value))
    except (ZoneInfoNotFoundError, ValueError) as error:
        raise InvalidRow('BAD_ZONE') from error


def utc_timestamp(value, zone=None):
    value = clean(value)
    if 'T' not in value and ' ' not in value:
        raise InvalidRow('BAD_CLOCK')
    try:
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is not None:
            return parsed.astimezone(timezone.utc)
        if zone is None:
            raise InvalidRow('BAD_CLOCK')
        candidates = {moment for fold in (0, 1)
                      if (moment := parsed.replace(tzinfo=zone, fold=fold).astimezone(timezone.utc))
                      .astimezone(zone).replace(tzinfo=None) == parsed}
    except (ValueError, OverflowError) as error:
        if isinstance(error, InvalidRow):
            raise
        raise InvalidRow('BAD_CLOCK') from error
    if len(candidates) == 2:
        raise InvalidRow('AMBIGUOUS_CLOCK')
    if not candidates:
        raise InvalidRow('NONEXISTENT_CLOCK')
    return candidates.pop()
