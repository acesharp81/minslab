import re
from datetime import date

_RE_SEP = re.compile(r'^(\d{4})([-./])(\d{1,2})\2(\d{1,2})$')
_RE_KO = re.compile(r'^\s*(\d{4})\s*년\s*(\d{1,2})\s*월\s*(\d{1,2})\s*일\s*$')


def parse_notice_date(value):
    if not isinstance(value, str):
        return None
    m = _RE_SEP.fullmatch(value)
    if not m:
        m = _RE_KO.fullmatch(value)
    if not m:
        return None
    try:
        y, mo, d = map(int, m.groups()[:3] if len(m.groups()) == 3 else (m.group(1), m.group(3), m.group(4)))
        if y < 1000 or y > 9999:
            return None
        return date(y, mo, d).isoformat()
    except Exception:
        return None

