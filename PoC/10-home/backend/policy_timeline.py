"""Current policy membership with evidence-dated block plans and report snapshots.

No interpolated planned percentages, historic policy attribution or progress averages.
"""
from collections import defaultdict
from datetime import date

from .roadmap import source_events, month, STAGES
from .supply_dashboard import inventory, block_key
from .supply_geography import municipal_membership

PROFILES = {
    "POL_2025_0907": {
        "purpose": "공공택지의 공급 속도를 높이고 도심 유휴부지·정비사업을 활용해 수도권 주택공급을 확대합니다.",
        "location": "수도권 · 인천 포함 / HOME 조회 범위는 서울·경기",
        "period": "2026~2030년 신규 착공 목표 · 2025.09.07 발표",
        "details": ["공공택지 LH 직접 시행", "노후 임대주택·공공청사·미사용 학교용지 활용", "재건축·재개발 촉진"],
        "url": "https://www.molit.go.kr/USR/NEWS/m_71/dtl.jsp?id=95091185",
        "annual_official": {year:270000 for year in range(2026,2031)},
    },
    "POL_2026_0129": {
        "purpose": "도심의 유휴부지와 노후 청사를 활용해 청년·신혼부부 등의 주거 수요에 대응합니다.",
        "location": "서울 용산·태릉, 경기 과천 등 수도권 / HOME 조회 범위는 서울·경기",
        "period": "2026.01.29 발표 · 개별 사업 일정으로 추진",
        "details": ["도심 부지·노후 청사 활용", "청년·신혼부부 중점 공급", "기존 용산 계획을 포함한 공급계획"],
        "url": "https://www.korea.kr/briefing/policyBriefingView.do?newsId=156742030",
    },
    "POL_2026_0813": {
        "purpose": "기존 공급대책의 이행 속도를 높이고 추가 공급과 주거 선택지를 확대해 전월세·매매시장 안정을 추진합니다.",
        "location": "수도권 공공택지·도심 / HOME 조회 범위는 서울·경기",
        "period": "2026.08.13 발표 · 개별 사업 일정으로 추진",
        "details": ["택지 조성·인허가 절차 병행", "기존 택지 조기 착공", "수도권 추가 공급"],
        "url": "https://www.korea.kr/briefing/policyBriefingView.do?newsId=156774369",
    },
    "MON_THIRD_NEW_TOWN": {
        "purpose": "서울 인근 공공택지에 주택을 공급하고 광역교통망·일자리·생활 기반을 함께 조성합니다.",
        "location": "남양주·하남·고양·부천 등 / HOME 조회 범위는 서울·경기",
        "period": "2018.12.19 최초 입지 발표부터 · 지구·블록별 일정으로 추진",
        "details": ["공공택지 주택공급", "광역교통망 연계", "일자리·생활 기반 조성"],
        "url": "https://www.korea.kr/news/policyNewsView.do?newsId=148856563",
    },
    "MON_URBAN_COMPLEX": {
        "purpose": "공공 주도로 역세권·준공업지역·저층주거지를 복합 개발해 도심 주택공급을 확대합니다.",
        "location": "서울 등 대도시 도심 / HOME 조회 범위는 서울·경기",
        "period": "2021.02.04 도입 방안 발표부터 · 사업별 일정으로 추진",
        "details": ["역세권 주거·상업 복합 개발", "준공업지역 주거·산업 복합 개발", "저층주거지 주거환경 개선"],
        "url": "https://www.korea.kr/news/policyNewsView.do?newsId=148883564",
    },
}


def known_sum(values):
    values = [v for v in values if v is not None]
    return sum(values) if values else None


def timeline_context(rows, plans, reports, districts, municipalities, reference):
    eligible = [r for r in rows if "MULTI_SITE_CONTRACT" not in r.get("warnings", [])]
    source_ids, manual_ids = {}, {}
    for stage in STAGES:
        chosen,_ = inventory([r for r in eligible if any(e["stage"] == stage for e in source_events(r,reference))])
        source_ids[stage] = {r["id"] for r in chosen}
        chosen,_ = inventory([r for r in eligible if any(e["stage"] == stage for e in plans.get(r["id"],{}).get("targets",[]))])
        manual_ids[stage] = {r["id"] for r in chosen}
    annual_reports = defaultdict(list)
    ids = {r["id"] for r in eligible}
    for report in reports:
        pid = report.get("current_project_id")
        stamp = report.get("report_date") or report.get("base_date") or ""
        if pid in ids and stamp <= reference.isoformat() and month(stamp) and report.get("progress_pct") is not None:
            annual_reports[pid].append(report)
    resolved = municipal_membership(rows,municipalities,districts,block_key)
    return dict(source_ids=source_ids,manual_ids=manual_ids,reports=annual_reports,resolved=resolved,
                municipalities={m["id"]:m for m in municipalities})


def build_timeline(policy, members, canonical, plans, reference, context, policy_events=()):
    profile = PROFILES.get(policy["policy_id"],{})
    groups = defaultdict(list)
    for row in members:
        groups[block_key(row) or (row["region"],"",row["id"])].append(row)
    blocks, sources = [], {}
    def evidence(url,label,kind):
        if url: sources.setdefault(url,dict(url=url,label=label,kind=kind))
    evidence(policy.get("evidence_url"),policy["name"],"정책 원문")
    evidence(profile.get("url"),policy["name"]+" · 개요 근거","정책 개요")
    origin = policy["policy_id"].removeprefix("MON_")
    for event in policy_events:
        if event.get("origin_id") == origin:
            evidence(event.get("evidence_url"),event["name"],"정책 흐름")
    start_year = (min(int(row['base_date'][:4]) for row in members) if members and policy.get('monitor_kind') == 'UNMAPPED'
                  else int((policy.get("announced_at") or str(reference.year))[:4]))
    for key, rows in sorted(groups.items()):
        block_id = "|".join(key)
        name = key[1]+" "+key[2] if key[1] else rows[0]["name"]
        areas = {context["resolved"][r["id"]] for r in rows if r["id"] in context["resolved"]}
        area = context["municipalities"].get(next(iter(areas))) if len(areas)==1 else None
        events, manual, intervals, actuals = [], [], [], []
        for row in rows:
            evidence(row.get("evidence_url"),row["name"],"사업 계획·현황")
            if "MULTI_SITE_CONTRACT" in row.get("warnings",[]): continue
            for event in source_events(row,reference):
                if row["id"] in context["source_ids"][event["stage"]]:
                    events.append(dict(event,project_id=row["id"]))
                    evidence(event.get("evidence_url"),row["name"]+" · "+event["label"],"사업 계획·현황")
            for goal in plans.get(row["id"],{}).get("targets",[]):
                if row["id"] in context["manual_ids"].get(goal["stage"],set()):
                    manual.append(dict(goal,month=None,label=STAGES[goal["stage"]]+" 목표",origin="MANUAL",project_id=row["id"]))
                    evidence(goal.get("evidence_url"),row["name"]+" · 관리자 목표","관리자 근거")
            start,end = row.get("start_plan_date"),row.get("completion_plan_date")
            if month(start) and month(end) and start <= end:
                intervals.append(dict(start=start,end=end,name=row["name"],evidence_url=row.get("evidence_url")))
            snapshots = list(context["reports"].get(row["id"],[]))
            if row.get("progress_pct") is not None and month(row.get("base_date")) and row["base_date"] <= reference.isoformat():
                snapshots.append(dict(row,report_date=row.get('progress_date') or row["base_date"],
                    evidence_url=row.get('progress_evidence_url') or row.get('evidence_url')))
            yearly = {}
            for snapshot in sorted(snapshots,key=lambda r:r["report_date"]):
                # No carry-forward to missing years; no averaging several contracts.
                year = int(snapshot["report_date"][:4])
                yearly[year] = snapshot
            for year,snapshot in sorted(yearly.items()):
                if year<start_year: continue
                actuals.append(dict(year=year,date=snapshot["report_date"],pct=snapshot["progress_pct"],
                                    project_id=row["id"],name=row["name"],evidence_url=snapshot.get("evidence_url")))
                evidence(snapshot.get("evidence_url"),snapshot["report_date"]+" · 공사 현황","공정률 보고서")
        overridden = {(g["year"],g["stage"]) for g in manual}
        events = [e for e in events if (e["year"],e["stage"]) not in overridden] + manual
        events = [e for e in events if e["year"]>=start_year]
        capacity = known_sum(r.get("planned_units") for r in rows if r["id"] in canonical)
        blocks.append(dict(id=block_id,name=name,block=key[2] if key[1] else None,region=key[0],
                           municipality=area["name"] if area else None,municipality_id=area["id"] if area else None,
                           project_ids=[r["id"] for r in rows],target_units=capacity,
                           review_count=sum(r.get("mapping",{}).get("status")=="REVIEW" for r in rows),
                           events=events,intervals=intervals,actuals=actuals))
    end_year = max([reference.year+3,2030 if policy["policy_id"]=="POL_2025_0907" else reference.year]+[
        e["year"] for b in blocks for e in b["events"]])
    years = list(range(start_year,end_year+1))
    annual = []
    for year in years:
        quantities = {}
        for stage in ("SUPPLY","COMPLETION","MOVE_IN","CONSTRUCTION"):
            events = [e for b in blocks for e in b["events"] if e["year"]==year and e["stage"]==stage]
            quantities[stage] = dict(units=known_sum(e.get("units") for e in events),
                                     source_units=known_sum(e.get("units") for e in events if e["origin"]=="SOURCE"),
                                     manual_units=known_sum(e.get("units") for e in events if e["origin"]=="MANUAL"),
                                     missing_events=sum(e.get("units") is None for e in events))
        annual.append(dict(year=year,**quantities,official_start_units=profile.get("annual_official",{}).get(year)))
    regions = []
    for region in sorted({b["region"] for b in blocks}):
        regional = [b for b in blocks if b["region"]==region]
        cities = []
        for city in sorted({b["municipality"] or "시군구 연결 검토" for b in regional}):
            children = [b for b in regional if (b["municipality"] or "시군구 연결 검토")==city]
            cities.append(dict(id=region+"|"+city,name=city,blocks=children,target_units=known_sum(b["target_units"] for b in children)))
        regions.append(dict(id=region,name=region,cities=cities,target_units=known_sum(b["target_units"] for b in regional)))
    by_program = defaultdict(list)
    for row in members:
        if row["id"] in canonical: by_program[row.get("program") or "연결 사업"].append(row.get("planned_units"))
    overview = dict(purpose=profile.get("purpose"),location=profile.get("location") or policy.get("target_scope"),
                    period=profile.get("period") or policy.get("announced_at"),details=profile.get("details",[]),
                    breakdown=[dict(name=k,units=known_sum(v)) for k,v in sorted(by_program.items())])
    return overview,dict(years=years,annual=annual,regions=regions,block_count=len(blocks),evidence=list(sources.values()),
                         basis="현재 정책 연결 사업의 과거 보고 이력입니다. 과거 연도의 정책 귀속·실제 공급량을 의미하지 않습니다. 상단은 예정 기간·물량, 하단은 해당 연도 마지막 확보 보고 공정률이며 미확보 연도를 보간하지 않습니다.")
