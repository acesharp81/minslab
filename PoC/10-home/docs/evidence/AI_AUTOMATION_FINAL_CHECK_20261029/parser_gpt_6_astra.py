import re
from datetime import date

_NUMERIC = re.compile(r'([0-9]{4})([-./])([0-9]{1,2})\2([0-9]{1,2})')
_KOREAN = re.compile(r'([0-9]{4})년\s*([0-9]{1,2})월\s*([0-9]{1,2})일')


def parse_notice_date(value):
    if not isinstance(value, str):
        return None
    match = _NUMERIC.fullmatch(value)
    if match:
        parts = match.group(1, 3, 4)
    else:
        match = _KOREAN.fullmatch(value)
        if not match:
            return None
        parts = match.groups()
    try:
        return date(*map(int, parts)).isoformat()
    except ValueError:
        return None

