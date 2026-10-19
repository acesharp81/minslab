"""Annual milestones from evidence, without inferred dates or annual allocation."""
import re
from collections import defaultdict
from datetime import date
from .schedule_period import schedule_period

STAGES = {"PLANNING":"계획", "APPROVAL":"인허가", "CONSTRUCTION":"착공", "SUPPLY":"공급", "COMPLETION":"준공", "MOVE_IN":"입주 시작"}


def month(value):
    if not value or not re.fullmatch(r"20\d{2}-\d{2}(?:-\d{2})?",str(value)):
        return None
    try:
        date.fromisoformat(str(value)[:7]+"-01")
        return str(value)[:7]
    except ValueError:
        return None


def source_events(row, as_of):
    events=[]
    def add(stage,when,units,basis):
        raw_when=str(when or "")
        period=schedule_period(when)
        when=period['month'] if period else None
        if when:
            events.append({"year":int(when[:4]),"month":when,"stage":stage,"label":STAGES[stage]+" 예정",
                           "due_date":period["due_date"],"precision":period["precision"],"source_date_label":raw_when,"date_conversion":period["conversion"],
                           "units":None if stage=="MOVE_IN" else units,"basis":basis,"origin":"SOURCE","evidence_url":row.get("evidence_url"),
                           "past_due":when<as_of.strftime("%Y-%m"),"actual_verified":False})
    if row.get("rows"):
        for field,stage in (("supply_month","SUPPLY"),("move_in_month","MOVE_IN")):
            groups=defaultdict(list);periods={}
            for dimension in row["rows"]:
                period=schedule_period(dimension.get(field.replace('_month','_raw')) or dimension.get(field))
                when=period['month'] if period else None
                if when:
                    groups[when].append(dimension.get("units"))
                    periods.setdefault(when,[]).append(period)
            for when,units in ([(min(groups), groups[min(groups)])] if stage=="MOVE_IN" and groups else groups.items()):
                add(stage,when,sum(units) if all(u is not None for u in units) else None,
                    "원천 면적별 공급계획" if stage=="SUPPLY" else "원천 임대 입주 시작 예정월")
                originals=periods[when]
                events[-1]['source_date_label']=' / '.join(dict.fromkeys(p['original'] for p in originals))
                if any(p['conversion']=='PERIOD_END' for p in originals):
                    events[-1].update(date_conversion='PERIOD_END',precision='PERIOD',basis=events[-1]['basis']+' · 범위 마지막 달 기준')
    elif row.get("source_id") in ("lh_construction","lh_incheon_construction","lh_progress"):
        if not row.get("start_actual_date"):
            add("CONSTRUCTION",row.get("start_plan_date"),row.get("planned_units"),"원천 계약 착공 예정일")
        add("COMPLETION",row.get("completion_plan_date"),row.get("planned_units"),"공사 계약 준공예정 · 입주일 아님")
    if row.get('source_id')=='lh_policy_followup':
        add('CONSTRUCTION',row.get('start_plan_month'),row.get('planned_units'),'LH 정책 후속 개별 공모 착공 목표월')
    if row.get('start_plan_year') and not row.get('start_actual_date') and not row.get('start_plan_date'):
        add('CONSTRUCTION',str(row['start_plan_year'])+'년',row.get('planned_units'),row.get('schedule_basis') or '공식 착공 예정연도 · 연말 표기')
    if row.get('source_id')=='policy_129':
        add('CONSTRUCTION',row.get('start_plan_month'),row.get('planned_units'),'1·29 공식 별첨 착공 예정월 · 준공·공급월 아님')
    for field,stage in (('source_supply_label','SUPPLY'),('source_move_in_label','MOVE_IN')):
        period=schedule_period(row.get(field))
        if period:
            events=[e for e in events if e['stage']!=stage]
            add(stage,row[field],row.get('planned_units'),'원천 예정 범위 · 마지막 달 기준 집계')
            if stage=='MOVE_IN' and row.get('move_in_evidence_url'):
                for event in events:
                    if event['stage']=='MOVE_IN':event['evidence_url']=row['move_in_evidence_url']
    notice_month=month(row.get("notice_move_in_month"))
    if notice_month:
        # A matched main notice is a more concrete move-in plan than an annual
        # supply plan. It remains a REVIEW link and never proves actual delivery.
        events=[event for event in events if event["stage"]!="MOVE_IN"]
        add("MOVE_IN",notice_month,None,"청약홈 본 모집공고 입주 시작 예정월 · 사업 연결 검토")
        events[-1]["evidence_url"]=row.get("notice_evidence_url")
    return sorted(events,key=lambda event:(event["year"],event["month"],event["stage"]))


def milestone_state(row, as_of, events=None):
    """Date-only occupancy start and source-reported pre-completion percentage."""
    events=events if events is not None else source_events(row,as_of)
    move_in=next((event for event in events if event["stage"]=="MOVE_IN" and event["origin"]=="SOURCE"),None)
    move_in_start={"date":move_in["month"],"precision":"MONTH","status":"PLANNED",
                   "basis":move_in["basis"],"evidence_url":move_in["evidence_url"]} if move_in else None
    value=row.get("progress_pct")
    pct=value if isinstance(value,(int,float)) and not isinstance(value,bool) and 0<=value<=100 else None
    construction_progress={"pct":pct,
                           "as_of_date":row.get("progress_date") or (row.get("base_date") if pct is not None else None),
                           "evidence_url":row.get("progress_evidence_url") or (row.get("evidence_url") if pct is not None else None),
                           "status":"SOURCE_REPORTED" if pct is not None else "NOT_ACQUIRED"}
    return {"move_in_start":move_in_start,"construction_progress":construction_progress}


def project_roadmap(row,plan,as_of,horizon,annual_horizon=None):
    events=source_events(row,as_of)
    for goal in plan.get("targets",[]):
        if goal["stage"] == "MOVE_IN":
            continue  # Legacy annual unit targets are not an occupancy start date.
        events.append({"year":goal["year"],"month":None,"stage":goal["stage"],"label":STAGES[goal["stage"]]+" 목표",
                       "units":goal.get("units"),"basis":goal["basis"],"origin":"MANUAL","evidence_url":goal.get("evidence_url"),
                       "past_due":goal["year"]<as_of.year,"actual_verified":False})
    years=range(as_of.year,as_of.year+(annual_horizon if annual_horizon is not None else horizon)+1)
    annual=[{"year":year,"offset":year-as_of.year,"events":[e for e in events if e["year"]==year],
             "status":"HAS_TARGET" if any(e["year"]==year for e in events) else "NOT_SET"} for year in years]
    future=[e for e in events if as_of.year<e["year"]<=as_of.year+horizon]
    state=milestone_state(row,as_of,events)
    return {**{k:row.get(k) for k in ("id","name","region","source_id","program","planned_units","unit_basis",
                                    "stage","stage_label","progress_pct","base_date","date_precision","mapping")},
            **state,
            "annual":annual,"has_future_target":bool(future),"has_any_target":bool(events),
            "past_due_count":sum(e["past_due"] for e in events),"earlier_events":[e for e in events if e["year"]<as_of.year],
            "goal_revision_no":plan.get("revision_no",0),"manual_count":sum(goal["stage"]!="MOVE_IN" for goal in plan.get("targets",[])),
            "supply_year_range": row.get("supply_year_range")}


def build_roadmap(projects,plans,as_of,horizon):
    rows=[project_roadmap(row,plans.get(row["id"],{}),as_of,horizon) for row in projects]
    rows.sort(key=lambda row:(not row["has_future_target"],row["region"],row["name"]))
    summaries=[]
    for year in range(as_of.year+1,as_of.year+horizon+1):
        events=[e for row in rows for annual in row["annual"] if annual["year"]==year for e in annual["events"]]
        summaries.append({"year":year,"offset":year-as_of.year,
                          "project_count":sum(any(a["year"]==year and a["events"] for a in row["annual"]) for row in rows),
                          "source_event_count":sum(e["origin"]=="SOURCE" for e in events),
                          "manual_event_count":sum(e["origin"]=="MANUAL" for e in events),
                          "stages":{stage:sum(e["stage"]==stage for e in events) for stage in STAGES},
                          "status":"HAS_TARGET" if events else "NOT_SET"})
    return {"items":rows,"total":len(rows),"as_of_date":as_of.isoformat(),"current_year":as_of.year,"horizon":horizon,
            "years":summaries,"future_target_count":sum(r["has_future_target"] for r in rows),
            "no_schedule_count":sum(not r["has_any_target"] for r in rows),"manual_project_count":sum(bool(r["manual_count"]) for r in rows),
            "past_due_project_count":sum(bool(r["past_due_count"]) for r in rows),
            "notice":"원천 예정과 관리자 목표를 구분합니다. 입주는 시작 예정월만 관리하며 호수·달성률로 집계하지 않습니다. 준공 전 공정률은 원천 보고값만 표시합니다. 목표 미등록은 0호가 아닙니다."}
