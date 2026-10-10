"""Annual milestones from evidence, without inferred dates or annual allocation."""
import re
from collections import defaultdict
from datetime import date

STAGES = {"PLANNING":"계획", "APPROVAL":"인허가", "CONSTRUCTION":"착공", "SUPPLY":"공급", "COMPLETION":"준공", "MOVE_IN":"입주"}


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
        when=month(when)
        if when:
            events.append({"year":int(when[:4]),"month":when,"stage":stage,"label":STAGES[stage]+" 예정",
                           "units":units,"basis":basis,"origin":"SOURCE","evidence_url":row.get("evidence_url"),
                           "past_due":when<as_of.strftime("%Y-%m"),"actual_verified":False})
    if row.get("rows"):
        for field,stage in (("supply_month","SUPPLY"),("move_in_month","MOVE_IN")):
            groups=defaultdict(list)
            for dimension in row["rows"]:
                when=month(dimension.get(field))
                if when:
                    groups[when].append(dimension.get("units"))
            for when,units in groups.items():
                add(stage,when,sum(units) if all(u is not None for u in units) else None,
                    "원천 면적별 공급계획" if stage=="SUPPLY" else "원천 임대 입주 예정월")
    elif row.get("source_id")=="lh_construction":
        if not row.get("start_actual_date"):
            add("CONSTRUCTION",row.get("start_plan_date"),row.get("planned_units"),"원천 계약 착공 예정일")
        add("COMPLETION",row.get("completion_plan_date"),row.get("planned_units"),"공사 계약 준공예정 · 입주일 아님")
    if row.get('source_id')=='policy_129':
        add('CONSTRUCTION',row.get('start_plan_month'),row.get('planned_units'),'1·29 공식 별첨 착공 예정월 · 준공·공급월 아님')
    notice_month=month(row.get("notice_move_in_month"))
    if notice_month:
        # A matched main notice is a more concrete move-in plan than an annual
        # supply plan. It remains a REVIEW link and never proves actual delivery.
        events=[event for event in events if event["stage"]!="MOVE_IN"]
        add("MOVE_IN",notice_month,row.get("notice_units"),"청약홈 본 모집공고 입주예정 · 사업 연결 검토")
        events[-1]["evidence_url"]=row.get("notice_evidence_url")
    return sorted(events,key=lambda event:(event["year"],event["month"],event["stage"]))


def project_roadmap(row,plan,as_of,horizon,annual_horizon=None):
    events=source_events(row,as_of)
    for goal in plan.get("targets",[]):
        events.append({"year":goal["year"],"month":None,"stage":goal["stage"],"label":STAGES[goal["stage"]]+" 목표",
                       "units":goal.get("units"),"basis":goal["basis"],"origin":"MANUAL","evidence_url":goal.get("evidence_url"),
                       "past_due":goal["year"]<as_of.year,"actual_verified":False})
    years=range(as_of.year,as_of.year+(annual_horizon if annual_horizon is not None else horizon)+1)
    annual=[{"year":year,"offset":year-as_of.year,"events":[e for e in events if e["year"]==year],
             "status":"HAS_TARGET" if any(e["year"]==year for e in events) else "NOT_SET"} for year in years]
    future=[e for e in events if as_of.year<e["year"]<=as_of.year+horizon]
    return {**{k:row.get(k) for k in ("id","name","region","source_id","program","planned_units","unit_basis",
                                    "stage","stage_label","progress_pct","base_date","date_precision","mapping")},
            "annual":annual,"has_future_target":bool(future),"has_any_target":bool(events),
            "past_due_count":sum(e["past_due"] for e in events),"earlier_events":[e for e in events if e["year"]<as_of.year],
            "goal_revision_no":plan.get("revision_no",0),"manual_count":len(plan.get("targets",[])),
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
            "notice":"원천 예정과 관리자 목표를 구분합니다. 목표 미등록은 0호가 아니며, 목표 달성과 공식 공급총량은 별도 확인합니다."}
