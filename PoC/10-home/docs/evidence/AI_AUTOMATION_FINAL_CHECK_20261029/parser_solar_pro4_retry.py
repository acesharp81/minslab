import re
from datetime import date

_KR_RE = re.compile(r'(?P<y>\d{4})\s*(?:년|YEAR)\s*(?P<m>[1-9]|0[1-9]|1[0-2])\s*(?:월|MONTH)\s*(?P<d>[1-9]|0[1-9]|[12]\d|3[01])\s*(?:일|DAY)\s*$')
_SEP_RE = re.compile(r'(?P<num>\d{4})(?P<sep>[-./])(?P<m>[0-9]{1,2})(?P=sep)(?P<d>[0-9]{1,2})$')

def parse_notice_date(value):
    if not isinstance(value, str) or not value:
        return None
    core = value.strip()
    if not core:
        return None
    m_kr = _KR_RE.match(core)
    if m_kr:
        try:
            y, mo, d = int(m_kr.group('y')), int(m_kr.group('m')), int(m_kr.group('d'))
            return date(y, mo, d).isoformat()
        except Exception:
            return None
    m_sep = _SEP_RE.match(core)
    if m_sep:
        try:
            y, mo, d = int(m_sep.group('num')), int(m_sep.group('m')), int(m_sep.group('d'))
            return date(y, mo, d).isoformat()
        except Exception:
            return None
    return None
