"""Monthly construction baseline inferred from source start/end dates, never actual progress."""
from calendar import monthrange
from datetime import date, timedelta
from .input_status import input_status,input_label


def construction_plan(project, reference):
    def stamp(value, end=False):
        try:
            raw=str(value or '')
            if len(raw)==7:
                return date.fromisoformat(raw+f'-{monthrange(int(raw[:4]),int(raw[5:7]))[1] if end else 1:02d}')
            return date.fromisoformat(raw)
        except (ValueError,TypeError):return None
    start=stamp(project.get('start_plan_date') or project.get('start_actual_date'))
    end=stamp(project.get('completion_plan_date'),True)
    if not start or not end or end<=start or (end-start).days>36525:return None
    duration=(end-start).days
    def pct(day):return round(max(0,min(100,(day-start).days/duration*100)),1)
    points=[];year,month=start.year,start.month
    while (year,month)<=(end.year,end.month):
        day=min(end,date(year,month,monthrange(year,month)[1]))
        points.append(dict(month=day.strftime('%Y-%m'),date=day.isoformat(),planned_pct=pct(day)))
        year,month=(year+1,1) if month==12 else (year,month+1)
    actual_on=stamp(project.get('progress_date') or project.get('base_date'))
    actual=project.get('progress_pct')
    comparison=None
    if isinstance(actual,(int,float)) and not isinstance(actual,bool) and 0<=actual<=100 and actual_on and actual_on<=reference:
        manual=project.get('manual_fields',{}).get('progress_pct')
        comparison=dict(input_status=input_status(manual or {}),input_label=input_label(manual) if manual else '원천 공정률',date=actual_on.isoformat(),actual_pct=actual,planned_pct=pct(actual_on),
                        gap_percentage_points=round(pct(actual_on)-actual,1))
    return dict(start_date=start.isoformat(),completion_date=end.isoformat(),method='LINEAR_ESTIMATE',
                basis='착공~준공 기간에 비례한 월별 추정 계획 · 공식 중간 공정목표 아님',
                evidence_url=project.get('evidence_url'),as_of_date=reference.isoformat(),
                current_planned_pct=pct(reference),monthly=points,comparison=comparison,
                milestones=[dict(pct=n,date=(start+timedelta(days=round(duration*n/100))).isoformat()) for n in (0,25,50,75,100)])
