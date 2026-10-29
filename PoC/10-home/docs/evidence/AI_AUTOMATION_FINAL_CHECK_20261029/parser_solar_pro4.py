import re
from datetime import date

_KR_SUFFIX_RE = re.compile(
    r'(?P<y>[12]\d{3})(?:\s)*(?:년|YEAR)(?:\s)*(?P<m>[1-9]|0[1-9]|1[0-2])(?:(?:\s)*(?:월|MONTH)(?:\s)*(?P<d>[1-9]|0[1-9]|[12]\d|3[01])(?:\s)*(?:일|DAY))?|'
    r'(?P<y2>[12]\d{3})(?:\s)*(?:년|YEAR)(?:\s)*(?P<d2>[1-9]|0[1-9]|[12]\d|3[01])(?:\s)*(?:일|DAY)$'
)
_SEPCONSIST = re.compile(r'^(?P<num>(?:1[0-9]{3}|20[0-9]{2}|2[0-9]{3}|[0-9]{4}))(?P<sep>[-.\/])(?P<m>[0-9]{1,2})(?P=sep)(?P<d>[0-9]{1,2})$')
_SURROUND = re.compile(r'^\s*(?P<core>.+?)\s*$', re.DOTALL)

def parse_notice_date(value):
    if not isinstance(value, str) or not value:
        return None
    m_surround = _SURROUND.match(value)
    if not m_surround:
        return None
    core = m_surround.group('core').strip()
    if not core:
        return None
    m_sep = _SEPCONSIST.match(core)
    if m_sep:
        try:
            y, mo, d = int(m_sep.group('num')), int(m_sep.group('m')), int(m_sep.group('d'))
            return date(y, mo, d).isoformat()
        except Exception:
            return None
    m_kr = _KR_SUFFIX_RE.match(core)
    if m_kr:
        y_str = m_kr.group('y') or m_kr.group('y2')
        if y_str is None:
            return None
        y = int(y_str)
        m = m_kr.group('m')
        d = m_kr.group('d') or m_kr.group('d2')
        if m is None or d is None:
            return None
        try:
            return date(y, int(m), int(d)).isoformat()
        except Exception:
            return None
    return None
