"""Range schedules retain their source precision; plotting uses the final month."""
import re
from calendar import monthrange
from datetime import date


def schedule_period(value, year=None):
    raw=str(value or '').strip()
    if not raw or re.search(r'미정|미확정|추후|이후|이전|미수립',raw):return None
    text=re.sub(r'\s+','',raw).replace('예정','').replace('목표','').strip('()')
    text=re.sub(r"^[‘’'](\d{2})(?=년|[./-])",r'20\1',text)
    m=re.fullmatch(r'(20\d{2})[-./](\d{1,2})(?:[-./](\d{1,2}))?\.?',text)
    if not m:m=re.fullmatch(r'(20\d{2})년(\d{1,2})월(?:(\d{1,2})일)?',text)
    if m:
        y,mo=int(m[1]),int(m[2]);d=int(m[3]) if m[3] else None
        try:date(y,mo,d or 1)
        except ValueError:return None
        return dict(month=f'{y:04}-{mo:02}',due_date=f'{y:04}-{mo:02}-{d or monthrange(y,mo)[1]:02}',
                    precision='DAY' if d else 'MONTH',original=raw,conversion='EXACT' if d else 'MONTH_END')
    m=re.fullmatch(r'(?:(20\d{2})년?)?(?:제?([1-4])분기|([상하])반기|([1-4])Q)',text,re.I)
    if m:
        y=int(m[1] or year or 0);mo=int(m[2] or m[4])*3 if m[2] or m[4] else 6 if m[3]=='상' else 12
        precision='QUARTER' if m[2] or m[4] else 'HALF_YEAR'
    else:
        m=re.fullmatch(r'(20\d{2})(?:년|[./-])(\d{1,2})월?[~～〜–-](?:(20\d{2})(?:년|[./-]))?(\d{1,2})월?',text)
        if m:
            sy,sm,y,mo=int(m[1]),int(m[2]),int(m[3] or m[1]),int(m[4]);precision='MONTH_RANGE'
            if not 1<=sm<=12 or (sy,sm)>(y,mo):return None
        else:
            m=re.fullmatch(r'(20\d{2})년?(?:[~～〜–-](20\d{2})년?)?',text)
            if not m:return None
            y=int(m[2] or m[1]);mo=12;precision='YEAR_RANGE' if m[2] else 'YEAR'
            if y<int(m[1]):return None
    if not 2000<=y<=2099 or not 1<=mo<=12:return None
    return dict(month=f'{y:04}-{mo:02}',due_date=f'{y:04}-{mo:02}-{monthrange(y,mo)[1]:02}',
                precision=precision,original=raw,conversion='PERIOD_END',basis='범위 일정은 마지막 달로 집계 · 실제 사건일 아님')
