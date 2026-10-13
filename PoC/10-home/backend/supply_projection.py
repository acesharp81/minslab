"""Stack a single milestone's unfulfilled, non-overlapping plans on its baseline."""
from .roadmap import source_events


def projections(selected, event_rows, reference, horizon, measure, links, key_for):
    if measure=="MOVE_IN":
        return {"baseline_units":None,"baseline_pct":None,"future":[
            {"offset":offset,"end_year":reference.year+offset,"increment_units":None,
             "cumulative_units":None,"cumulative_pct":None,"eligible_events":0,
             "excluded_events":0,"excluded_units":0,"excluded_reasons":[],"status":"DATE_ONLY"}
            for offset in range(1,horizon+1)],"basis":"입주는 시작 예정월만 관리 · 물량·달성률 집계 제외"}
    capacities={row["id"]:row["planned_units"] for row in selected if row.get("planned_units") is not None}
    owners={key_for(row):row["id"] for row in selected if key_for(row) and row["id"] in capacities}
    baseline=sum(notice["units"] for pid,notice in (links or {}).items() if pid in capacities) if measure=="SUPPLY" else None
    has_baseline=measure=="SUPPLY" and any(pid in capacities for pid in (links or {}))
    baseline=baseline if has_baseline else None
    scheduled={}
    excluded=[]
    for row in event_rows:
        events=[event for event in source_events(row,reference) if event["stage"]==measure and event["month"]>reference.strftime("%Y-%m")]
        if not events:continue
        owner=row["id"] if row["id"] in capacities else owners.get(key_for(row))
        reason=None
        if owner is None:reason="CAPACITY_UNLINKED"
        elif measure=="SUPPLY" and owner in (links or {}):reason="NOTICE_COHORT_OVERLAP"
        elif any(event["units"] is None for event in events):reason="EVENT_UNITS_MISSING"
        elif sum(event["units"] for event in events)>capacities[owner]:reason="CAPACITY_CONFLICT"
        if reason:
            excluded.extend(dict(event,project_id=row["id"],reason=reason) for event in events)
        else:
            scheduled.setdefault(owner,[]).extend(events)
    eligible=[event for events in scheduled.values() for event in events]
    total=sum(capacities.values()) if capacities else None
    result=[]
    for offset in range(1,horizon+1):
        events=[event for event in eligible if event["year"]<=reference.year+offset]
        excluded_events=[event for event in excluded if event["year"]<=reference.year+offset]
        # Zero is known only within a collected schedule set; no schedule is
        # unknown. This never substitutes zero for a missing actual baseline.
        increment=sum(event["units"] for event in events) if eligible else None
        cumulative=baseline+increment if baseline is not None and increment is not None else None
        result.append({"offset":offset,"end_year":reference.year+offset,"increment_units":increment,
            "cumulative_units":cumulative,"cumulative_pct":round(cumulative/total*100,2) if cumulative is not None and total else None,
            "eligible_events":len(events),"excluded_events":len(excluded_events),
            "excluded_units":sum(event["units"] for event in excluded_events if event["units"] is not None),
            "excluded_reasons":sorted({event["reason"] for event in excluded_events}),
            "status":"REVIEW_PROJECTION" if cumulative is not None else "BASELINE_OR_SCHEDULE_UNKNOWN"})
    return {"baseline_units":baseline,"baseline_pct":round(baseline/total*100,2) if baseline is not None and total else None,
            "future":result,"basis":"동일 단계의 현재 확인량 + 중복 없는 미이행 원천 예정량 · 연도 말 누적 · 관리자 목표 별도 · 검토 전망"}
