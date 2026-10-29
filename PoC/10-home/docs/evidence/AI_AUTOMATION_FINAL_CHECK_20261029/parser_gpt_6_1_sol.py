import re
from datetime import date


def parse_notice_date(value):
    if not isinstance(value, str):
        return None

    match = re.fullmatch(
        r'([0-9]{4})([-./])([0-9]{1,2})\2([0-9]{1,2})', value
    )
    if match:
        year, month, day = match.group(1, 3, 4)
    else:
        match = re.fullmatch(
            r'([0-9]{4})\s*년\s*([0-9]{1,2})\s*월\s*([0-9]{1,2})\s*일',
            value,
        )
        if not match:
            return None
        year, month, day = match.groups()

    try:
        return date(int(year), int(month), int(day)).isoformat()
    except ValueError:
        return None

