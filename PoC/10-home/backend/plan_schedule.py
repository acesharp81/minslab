"""Preserve an explicit undecided schedule separately from absent/empty fields."""
import re
from .roadmap import month
from .schedule_period import schedule_period


def plan_schedule(row, field, source_id):
    value=row.get(field+'_raw') or row.get(field+'_month')
    period=schedule_period(value)
    if period:
        return dict(status='DATED',label=str(value),date=period['month'],period=period)
    present=row.get(field+'_field_present')
    # The nine-column LH sale-plan schema has no move-in column, including legacy rows.
    if present is False or present is None and field=='move_in' and source_id in ('lh_sale','lh_incheon_sale'):
        return dict(status='NOT_PROVIDED',label='원천 항목 미제공',date=None)
    raw=row.get(field+'_raw')
    if raw is None:
        return dict(status='UNVERIFIED',label='원문 일정 미확인',date=None)
    raw=str(raw).strip()
    if not raw or raw in ('-','—','–'):
        return dict(status='EMPTY',label='원천 공란',date=None)
    return dict(status='UNDETERMINED' if re.search(r'미정|미확정|추후|미수립',raw) else 'TEXT',label=raw,date=None)
