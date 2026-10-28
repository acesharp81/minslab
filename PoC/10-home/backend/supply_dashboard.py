"""Evidence-year map projections. Knowledge dates and supply measures stay separate."""
import re
from collections import defaultdict
import pickle
from datetime import date

from .map_data import district_term, same_district
from .roadmap import project_roadmap, source_events
from .supply_progress import progress_metrics
from .supply_projection import projections
from .supply_geography import municipal_membership, block_milestones
from .matching_rules import policy_members
from .block_identity import normalize_block, title_blocks

MEASURES = {"SUPPLY": "모집·공급", "MOVE_IN": "입주 시작일", "COMPLETION": "준공"}
SOURCE_ALIASES = {"lh_incheon_sale": "lh_sale", "lh_incheon_rent": "lh_rent",
                  "lh_incheon_construction": "lh_construction"}


def marker_view(dashboard):
    """Same quantities, provenance and points; omit unused polygon coordinates."""
    return {**dashboard, **{key: [{k: v for k, v in row.items() if k != 'geometry'}
                                for row in dashboard[key]]
                           for key in ('municipalities', 'districts')}}


def block_key(row):
    if not row.get('region'):return None
    term = district_term(row)
    block = row.get("block")
    block_code = normalize_block(block)
    explicit=title_blocks(row.get('name',''))
    if len(explicit)==1 and (not block_code or '-' in block_code):
        # A construction contract's site code is not necessarily its housing
        # block. The one explicit housing block in its title takes precedence.
        block_code=next(iter(explicit))
    if not block_code:
        # Contract site codes can differ from the one explicit housing block in
        # the title. Derive the display key without rewriting the source field.
        if len(explicit)==1:
            block_code=next(iter(explicit))
    if not term:
        return None
    if not block_code:
        # Some LH blocks have a letter only (e.g. 인천부평 A). Supply
        # plans put it at the end of the title; construction/progress rows
        # supply a separate district and block. Preserve the district rather
        # than treating those sources as independent housing inventories.
        suffix = re.fullmatch(r"(.+?)\s+([A-Za-z])(?:BL|블록)?", term, re.I)
        letter = re.fullmatch(r"[A-Za-z]", str(block or ""))
        if letter:
            block_code = letter[0].upper()
            if suffix and suffix[2].upper() != block_code:
                return None
        elif not block and suffix:
            block_code = suffix[2].upper()
        else:
            return None
        if suffix:
            term = suffix[1]
    term = re.sub(r"\s+", "", term).replace("국제화계획", "")
    term = re.sub(r"(?:공공주택지구|택지개발사업|택지개발지구|지구)+$", "", term)
    return (row["region"], term, block_code)


def inventory(rows):
    """Exclude ambiguous contracts; count an exact land/block once across sources.

    This is a REVIEW subtotal, not an approved canonical housing inventory.
    Different supply-plan totals at a shared block are excluded, not guessed.
    """
    grouped = defaultdict(list)
    excluded = []
    for row in rows:
        if "MULTI_SITE_CONTRACT" in row.get("warnings", []):
            excluded.append(row["id"])
            continue
        key = block_key(row)
        if row["source_id"] == "lh_construction" and key is None:
            excluded.append(row["id"])
            continue
        grouped[key or (row["source_id"], row["id"])].append(row)
    selected = []
    for group in grouped.values():
        plans = [row for row in group if row["source_id"] in {"lh_sale", "lh_rent"}]
        # Distinct named rental cohorts are disjoint, not duplicate snapshots.
        rental_types={'국민임대','영구임대','행복주택','통합공공임대'}
        tenures=[r.get('tenure') for r in plans]
        if len(plans)>1 and len(set(tenures))==len(plans) and all(t in rental_types for t in tenures):
            selected.extend(plans)
            excluded.extend(r['id'] for r in group if r not in plans)
            continue
        if len(plans) > 1 or (not plans and len(group) > 1):
            excluded.extend(row["id"] for row in group)
            continue
        winner = plans[0] if plans else group[0]
        if winner.get('planned_units') is None:
            capacities = {r['planned_units'] for r in group if r.get('planned_units') is not None and r['planned_units'] > 0}
            if len(capacities) == 1:
                winner = dict(winner, planned_units=capacities.pop(), quantity_basis='SAME_BLOCK_SOURCE',
                              quantity_source_ids=[r['id'] for r in group if r.get('planned_units') is not None])
        selected.append(winner)
        excluded.extend(row["id"] for row in group if row["id"] != winner["id"])
    return selected, excluded


def linked_notices(rows,notices,reference):
    """Conservative REVIEW links, never verified move-in or official policy output."""
    matched={}
    candidates=[]
    for row in rows:
        key=block_key(row)
        if key:
            block=re.fullmatch(r"([A-Z]+)(\d+)(?:-(\d+))?",key[2])
            # Letter-only blocks are deduplicated above, but a notice title
            # needs a separately reviewed link rather than a loose letter match.
            if block is None:
                continue
            pattern=re.compile(re.escape(key[1])+r"(?:공공주택지구|택지개발지구|지구)?"+
                re.escape(block[1])+r"[-－]?0*"+block[2]+
                (r'[-－]0*'+block[3] if block[3] else '')+r"(?:BL|블록)?(?![A-Z0-9－-])")
            candidates.append((row,pattern))
    for notice in sorted(notices,key=lambda row:(row.get("source_date") or "",row["id"])):
        if not notice.get("source_date") or notice["source_date"]>reference.isoformat():continue
        if "한국토지주택공사" not in re.sub(r"\s+","",notice.get("developer", "")):continue
        name=re.sub(r"\s+","",notice["name"]).replace("국제화계획", "").upper()
        if any(word in name for word in ("사전","잔여","추가","취소","무순위","정정")):continue
        if len(title_blocks(name))>1:continue
        if notice.get("units") is None or notice["units"]<=0:continue
        owners=[]
        for row,pattern in candidates:
            if row["region"]!=notice["region"] or not pattern.search(name):continue
            if row["source_id"]=="lh_rent" and "임대" not in name:continue
            if row["source_id"]=="lh_sale" and "분양" not in name:continue
            if row.get("planned_units") is not None and notice["units"]>row["planned_units"]:continue
            owners.append(row)
        if len(owners)==1:
            matched[owners[0]["id"]]=notice
    # A single notice cannot count against two supply cohorts, even if names
    # happen to match. Keep such multi-owner links unallocated.
    repeats=defaultdict(list)
    for project_id,notice in matched.items():repeats[notice.get("house_manage_no") or notice["id"]].append(project_id)
    for owners in repeats.values():
        if len(owners)>1:
            for project_id in owners:matched.pop(project_id)
    return matched


def quantities(rows, plans, reference, horizon, measure, target_ids=None,event_ids=None,manual_ids=None,notice_links=None):
    selected, excluded = inventory(rows)
    if target_ids is not None:
        selected=[row for row in rows if row["id"] in target_ids]
        excluded=[row["id"] for row in rows if row["id"] not in target_ids]
    known = [row["planned_units"] for row in selected if row.get("planned_units") is not None]
    future = []
    # Aggregate each metric independently. A construction record at a matched
    # block can contribute a completion schedule, but never a second plan total.
    event_rows, event_excluded = inventory([row for row in rows if any(
        event["stage"] == measure for event in source_events(row, reference))])
    if event_ids is not None:
        event_rows=[row for row in rows if row["id"] in event_ids]
    events = [event for row in event_rows for event in source_events(row, reference)
              if event["stage"] == measure and event["month"] > reference.strftime("%Y-%m")]
    manual_rows,_=inventory([row for row in rows if any(goal["stage"]==measure for goal in
        plans.get(row.get("master_id") or row["id"], {}).get("targets", []))])
    if manual_ids is not None:
        manual_rows=[row for row in rows if row["id"] in manual_ids]
    manual = [] if measure=="MOVE_IN" else [goal for row in manual_rows for goal in plans.get(row.get("master_id") or row["id"], {}).get("targets", [])
              if goal["stage"] == measure and goal["year"] > reference.year]
    for offset in range(1, horizon+1):
        end_year = reference.year+offset
        source = [event for event in events if event["year"] <= end_year]
        goals = [goal for goal in manual if goal["year"] <= end_year]
        source_known = [event["units"] for event in source if event["units"] is not None]
        manual_known = [goal["units"] for goal in goals if goal.get("units") is not None]
        future.append({"offset": offset, "end_year": end_year,
                       "start_date":min((event["month"] for event in source),default=None) if measure=="MOVE_IN" else None,
                       "source_units": None if measure=="MOVE_IN" else sum(source_known) if source_known else None,
                       "manual_units": None if measure=="MOVE_IN" else sum(manual_known) if manual_known else None,
                       "source_events": len(source), "manual_events": 0 if measure=="MOVE_IN" else len(goals),
                       "units_missing_events": 0 if measure=="MOVE_IN" else len(source)-len(source_known),
                       "excluded_source_rows": len(event_excluded)})
    linked=[notice_links[row["id"]] for row in rows if notice_links and row["id"] in notice_links]
    return {"project_count": len(rows), "target_units": sum(known) if known else None,
            "move_in_start":min((event["month"] for event in events),default=None) if measure=="MOVE_IN" else None,
            "target_counted_projects": len(known), "target_excluded_projects": len(excluded),
            "target_missing_projects": len(selected)-len(known), "current_units": None,
            "current_status": "ACTUAL_NOT_COLLECTED", "current_notice_units":sum(row["units"] for row in linked) if linked else None,
            "current_notice_count":len(linked),"current_notice_status":"CONFIRMED" if linked and all(n.get('review_status')=='CONFIRMED' for n in linked) else "REVIEW", "future": future,
            "chart_target_ids": [row["id"] for row in selected],
            "chart_schedule_ids": [row["id"] for row in event_rows],
            "chart_manual_ids": [row["id"] for row in manual_rows],
            "progress": progress_metrics(selected,event_rows,plans,reference,measure,notice_links,manual_rows),
            "projection": projections(selected,event_rows,reference,horizon,measure,notice_links,block_key)}


def market_notices(notices, reference, horizon, region=None):
    # A house-management ID can have amended/repeated notices. Use its latest
    # notice known at the reference date, not the sum of its revisions.
    latest = {}
    for row in sorted(notices, key=lambda row: (row.get("source_date") or "", row["id"])):
        if (region and row["region"] != region) or not row.get("source_date") or row["source_date"] > reference.isoformat():
            continue
        latest[row.get("house_manage_no") or row["id"]] = row
    units = [row["units"] for row in latest.values() if row.get("units") is not None]
    future = []
    for offset in range(1, horizon+1):
        matched = [row for row in latest.values() if re.fullmatch(r"20\d{2}(0[1-9]|1[0-2])", row.get("move_in_plan_month") or "")
                   and reference.strftime("%Y%m") < row["move_in_plan_month"] <= f"{reference.year+offset}12"]
        future.append({"offset": offset, "start_date":min((row["move_in_plan_month"][:4]+"-"+row["move_in_plan_month"][4:] for row in matched),default=None), "notice_count": len(matched)})
    return {"notice_count": len(latest), "announced_units": sum(units) if units else None,
            "missing_units_count": len(latest)-len(units), "future_move_in": future,
            "basis": "서울·인천·경기 청약 모집공고 · 민간 포함 · 정부정책 미연결 · 실입주량 아님"}


def build_dashboard(projects, reports, districts, policies, goals, notices, events, knowledge_date,
                    start_year, analysis_year=None, horizon=10, measure="SUPPLY", permits=None, municipalities=None, annual_permit_count=None, block_locations=None, stored_supply_links=None, stage_events=None, **filters):
    analysis_year = analysis_year or knowledge_date.year
    reference = min(date(analysis_year, 12, 31), knowledge_date)
    if analysis_year > knowledge_date.year:
        raise ValueError("자료 연도는 조회 기준연도 이하여야 합니다")
    projects = [dict(row, source_id=SOURCE_ALIASES.get(row["source_id"], row["source_id"]),
                     origin_source_id=row.get("origin_source_id", row["source_id"]))
                for row in projects if row.get("mapping", {}).get("status") != "RELEASED"]
    masters = {row["id"]: row for row in projects}
    rows = [dict(row, master_id=row["id"]) for row in projects
            if row["source_id"] not in {"lh_construction","lh_progress"} and row["base_date"] <= reference.isoformat()]
    if analysis_year == knowledge_date.year:
        rows.extend(dict(row, master_id=row["id"]) for row in projects if row["source_id"] in {"lh_construction","lh_progress"})
    else:
        latest = {}
        for report in sorted(reports, key=lambda row: row["report_date"]):
            if report["report_date"] <= reference.isoformat():
                latest[report.get('current_project_id') or (report['source_id'],report["source_object_id"])] = report
        for report in latest.values():
            master = masters.get(report.get("current_project_id"))
            # Old reports never inherit the later policy attribution.
            rows.append(dict(report, id=report.get("current_project_id") or report["id"], master_id=report.get("current_project_id"),
                             source_id="lh_progress" if report['source_id']=='lh_progress' else "lh_construction", mapping={"policy_id": None, "status": "REVIEW"},
                             historical_report=True, current_mapping=master.get("mapping") if master else None))
    for field in ("region", "source_id", "stage"):
        if filters.get(field):
            rows = [row for row in rows if (row.get("origin_source_id", row.get(field)) if field == "source_id" else row.get(field)) == filters[field]]
    if filters.get("q"):
        needle = filters["q"].casefold()
        rows = [row for row in rows if needle in " ".join(str(row.get(key, "")) for key in ("name", "district", "program", "municipality")).casefold()]
    if filters.get("policy_id"):
        selected_policy = next((p for p in policies if p["policy_id"] == filters["policy_id"]), {"policy_id":filters["policy_id"]})
        rows = policy_members(selected_policy, rows)
    if filters.get("mapping_status"):
        rows = [row for row in rows if row.get("mapping", {}).get("status") == filters["mapping_status"]]
    resolved_inventory = {r['id']: r for r in inventory(rows)[0]}
    rows = [resolved_inventory.get(r['id'], r) for r in rows]
    # Historical scenarios use only goals already established at the reference
    # date, preventing a goal entered today from appearing in a 2025 snapshot.
    plans = {row["project_id"]: row for row in goals if row["base_date"] <= reference.isoformat()}
    initial_targets,_=inventory(rows)
    initial_links=linked_notices(initial_targets,notices,reference)
    eligible={r['id']:r for r in initial_targets}
    for pid,notice in (stored_supply_links or {}).items():
        if pid in eligible and notice['source_date']<=reference.isoformat() and notice['units']<=(eligible[pid].get('planned_units') or 0):
            initial_links[pid]=notice
    for row in rows:
        notice=initial_links.get(row["id"])
        if notice and re.fullmatch(r"20\d{2}(0[1-9]|1[0-2])",notice.get("move_in_plan_month") or ""):
            if notice["source_date"]<row["base_date"] and any(event["stage"]=="MOVE_IN" for event in source_events(row,reference)):
                continue
            stamp=notice["move_in_plan_month"]
            row.update(notice_move_in_month=stamp[:4]+"-"+stamp[4:],notice_units=notice["units"],
                       notice_evidence_url=notice.get("evidence_url"))
    items = []
    for row in rows:
        item = project_roadmap(row, plans.get(row.get("master_id") or row["id"], {}), reference, horizon, annual_horizon=max(horizon, 5))
        item.update(master_id=row.get("master_id"), historical_report=row.get("historical_report", False), municipality=row.get("municipality"),
                    report_date=row.get("report_date"), evidence_url=row.get("evidence_url"))
        item["map_quantities"] = quantities([row], plans, reference, horizon, measure, notice_links=initial_links)
        items.append(item)
    condition=filters.get("schedule_status","all")
    if condition!="all":
        items=[item for item in items if (
            item["has_future_target"] if condition=="future" else not item["has_any_target"] if condition=="missing" else
            item["past_due_count"] if condition=="past" else item["manual_count"] if condition=="manual" else True)]
        visible_ids={item["id"] for item in items}
        rows=[row for row in rows if row["id"] in visible_ids]
    target_rows,_=inventory(rows)
    schedule_rows,_=inventory([row for row in rows if any(event["stage"]==measure for event in source_events(row,reference))])
    manual_rows,_=inventory([row for row in rows if any(goal["stage"]==measure for goal in
        plans.get(row.get("master_id") or row["id"],{}).get("targets",[]))])
    canonical=({row["id"] for row in target_rows},{row["id"] for row in schedule_rows},{row["id"] for row in manual_rows})
    selected_ids={row["id"] for row in rows}
    notice_links={pid:notice for pid,notice in initial_links.items() if pid in selected_ids}
    from .map_stage_state import cohort_parts, aggregate as aggregate_stages
    stage_parts = cohort_parts(target_rows, rows, notice_links, stage_events or {}, reference, block_key)
    for item in items:
        notice=notice_links.get(item["id"])
        item["notice_evidence"]={key:notice.get(key) for key in ("id","name","units","source_date","evidence_url")} if notice else None
    calculated = {}
    def calculate(members):
        key=tuple(r['id'] for r in members)
        if key in calculated:return pickle.loads(calculated[key])
        amount = quantities(members,plans,reference,horizon,measure,*canonical,notice_links=notice_links)
        amount['stage_distribution'] = aggregate_stages([r for r in members if r['id'] in canonical[0]], stage_parts)
        # Only bytes produced in this build are decoded. Isolate nested results
        # without walking the same large dictionaries in Python for every group.
        calculated[key]=pickle.dumps(amount,protocol=5)
        return amount
    def display_amount(members):
        amount=calculate(members)
        # A valid individual target must stay visible even when that contract
        # cannot be added to the deduplicated portfolio (e.g. multi-site scope).
        if amount['target_units'] is None and len(members)==1 and members[0].get('planned_units') is not None:
            amount=dict(amount,aggregate_target_units=None,target_units=members[0]['planned_units'],
                        quantity_basis='PROJECT_REFERENCE',quantity_note='사업 목표 표시 · 중복·복합공사 범위로 전체 합계 별도')
        return amount
    active_policies = [policy for policy in policies if policy["announced_at"] <= reference.isoformat()
                       and (not filters.get("policy_id") or policy["policy_id"] == filters["policy_id"])]
    groups = {"policy": [], "program": [], "region": []}
    def group(key, label, members, **extra):
        return dict(id=key, name=label, project_ids=[row["id"] for row in members],
                    **calculate(members), **extra)
    for policy in active_policies:
        members = policy_members(policy, rows)
        groups["policy"].append(group(policy["policy_id"], policy["name"], members,
            announced_target_units=policy.get("target_units"), target_scope=policy.get("target_scope"), target_metric=policy.get("metric"), monitor_kind=policy.get("monitor_kind","POLICY")))
    active_policy_ids = {policy["policy_id"] for policy in active_policies}
    unmapped = [row for row in rows if row.get("mapping", {}).get("policy_id") not in active_policy_ids]
    if unmapped:
        groups["policy"].append(group("UNMAPPED", "정책 귀속 미확인 · 과거 보고서", unmapped))
    for program in sorted({row.get("program") or "미분류" for row in rows}):
        groups["program"].append(group(program, program, [row for row in rows if (row.get("program") or "미분류") == program]))
    show_market = not any(filters.get(key) for key in ("policy_id", "source_id", "stage", "mapping_status", "q"))
    market_rows = notices if show_market else []
    for region in ("서울특별시", "인천광역시", "경기도"):
        if filters.get("region") and filters["region"] != region:
            continue
        members = [row for row in rows if row["region"] == region]
        groups["region"].append(group(region, region, members,
            market=market_notices(market_rows, reference, horizon, region)))
    for grouping in groups.values():
        for aggregate in grouping:
            members=[row for row in rows if row["id"] in aggregate["project_ids"]]
            aggregate["group_quantities"]={kind:{item["id"]:calculate(
                [row for row in members if row["id"] in item["project_ids"]]) for item in target_groups}
                for kind,target_groups in groups.items()}
    mapped = []
    located = set()
    for district in districts:
        members = [row for row in rows if row["id"] in district.get("project_ids", [])
                   or (row.get("historical_report") and district_term(row) and same_district(district_term(row), district["name"]))]
        if members:
            member_ids={row["id"] for row in members}
            grouped_quantities={kind:{group["id"]:calculate(
                [row for row in members if row["id"] in group["project_ids"]])
                for group in grouping if member_ids.intersection(group["project_ids"])} for kind,grouping in groups.items()}
            mapped.append(dict(district, project_ids=[row["id"] for row in members],group_quantities=grouped_quantities,
                               quantities=calculate(members)))
            located.update(row["id"] for row in members)
    # Blocks use the same global inventory decisions as every aggregate. The
    # district anchor is explicitly representative, never a block coordinate.
    block_members = defaultdict(list)
    for row in rows:
        key = block_key(row)
        if key:
            block_members[key].append(row)
    locations = {(row["region"], row["district_key"], row["block"]): row for row in (block_locations or [])}
    blocks = []
    for key, members in sorted(block_members.items()):
        ids = {row["id"] for row in members}
        anchors = [district for district in mapped if ids.intersection(district["project_ids"])]
        anchor = anchors[0] if len(anchors) == 1 else None
        location = locations.get(key)
        if not location and not anchor:
            points={(r.get('latitude'),r.get('longitude')) for r in members if r.get('latitude') is not None and r.get('longitude') is not None}
            if len(points)==1:
                source=next(r for r in members if r.get('latitude') is not None)
                location=dict(latitude=source['latitude'],longitude=source['longitude'],coordinate_basis=source.get('coordinate_basis'),evidence_url=source.get('location_evidence_url'))
        block=group("|".join(key), key[1]+" "+key[2], members, region=key[0], block=key[2],
            district_name=anchor["name"] if anchor else key[1],
            latitude=location["latitude"] if location else anchor["latitude"] if anchor else None,
            longitude=location["longitude"] if location else anchor["longitude"] if anchor else None,
            coordinate_basis=location["coordinate_basis"] if location else "DISTRICT_REPRESENTATIVE" if anchor else "UNLOCATED",
            location_evidence_url=location.get("evidence_url") if location else None,
            group_quantities={kind:{item["id"]:display_amount([row for row in members if row["id"] in item["project_ids"]])
                for item in grouping if ids.intersection(item["project_ids"])} for kind,grouping in groups.items()})
        block.update(display_amount(members))
        block["milestones"]=block_milestones(members,notice_links,reference)
        blocks.append(block)
    # Named Seoul projects and area-only locations were excluded by block syntax.
    # Stored anchors are explicitly approximate; no network work occurs on reads.
    represented={pid for b in blocks if b.get('latitude') is not None for pid in b['project_ids']}
    for row in rows:
        if row['id'] in represented or row.get('latitude') is None or row.get('longitude') is None:continue
        name=row['name'];members=[row];ids={row['id']}
        scopes={kind:{g['id']:display_amount(members) for g in grouping if ids.intersection(g['project_ids'])} for kind,grouping in groups.items()}
        anchor=dict(id='location:'+row['id'],name=name,project_ids=[row['id']],regions=[row['region']],
            latitude=row['latitude'],longitude=row['longitude'],coordinate_basis=row.get('coordinate_basis'),
            location_label=row.get('location_label'),link_status='REVIEW',geometry=None,
            quantities=calculate(members),group_quantities=scopes,base_date=row['base_date'])
        mapped.append(anchor);located.add(row['id'])
        b=group(anchor['id'],name,members,region=row['region'],block='대표 위치',district_name=name,
            latitude=row['latitude'],longitude=row['longitude'],coordinate_basis=row.get('coordinate_basis'),
            location_label=row.get('location_label'),location_evidence_url=row.get('location_evidence_url'),group_quantities=scopes)
        b.update(display_amount(members))
        b['milestones']=block_milestones(members,notice_links,reference);blocks.append(b)
    municipality_groups=[]
    resolved=municipal_membership(rows,municipalities or [],mapped,block_key)
    boundary_names={area['id']:area['name'] for area in municipalities or []}
    for row in rows:
        if row['region']=='인천광역시':
            row['municipality']=boundary_names.get(resolved.get(row['id']),'지역 상세 확인 필요')
    for boundary in municipalities or []:
        members=[row for row in rows if resolved.get(row["id"])==boundary["id"]]
        member_ids={row["id"] for row in members}
        municipality_groups.append(dict(boundary,**{key:value for key,value in group(boundary["id"],boundary["name"],members).items() if key not in {"id","name"}},
            group_quantities={kind:{item["id"]:calculate([row for row in members if row["id"] in item["project_ids"]])
                for item in grouping if member_ids.intersection(item["project_ids"])} for kind,grouping in groups.items()}))
    flow = [row for row in events if not filters.get("policy_id") and (row.get("event_date") or "")[:4] == str(analysis_year)
            and row["event_date"] <= reference.isoformat()]
    flow.extend(dict(policy, event_date=policy["announced_at"], basis=policy.get("metric")) for policy in active_policies
                if policy["announced_at"][:4] == str(analysis_year))
    flow.sort(key=lambda row:row["event_date"])
    annual_notices = [row for row in notices if (row.get("source_date") or "")[:4] == str(analysis_year)
                      and row["source_date"] <= reference.isoformat() and (not filters.get("region") or row["region"] == filters["region"])] if show_market else []
    annual_permits=[row for row in (permits or []) if (
        row.get("dates",{}).get("원천 허가일 (apprvDay)") or row.get("source_date") or "")[:4]==str(analysis_year)
        and (row.get("dates",{}).get("원천 허가일 (apprvDay)") or row.get("source_date") or "9999")<=reference.isoformat()
        and (not filters.get("region") or row["region"]==filters["region"])] if show_market else []
    annual_reports = [row for row in reports if row["report_date"][:4] == str(analysis_year)
                      and row["report_date"] <= reference.isoformat() and (not filters.get("region") or row["region"] == filters["region"])
                      and (not filters.get("q") or filters["q"].casefold() in (row["name"]+" "+row.get("district", "")).casefold())]
    if any(filters.get(key) for key in ("policy_id","source_id","stage","mapping_status")):
        ids={row["id"] for row in rows}
        annual_reports=[row for row in annual_reports if (row.get("current_project_id") or row["id"]) in ids]
    return {"analysis_year": analysis_year, "reference_date": reference.isoformat(), "knowledge_date": knowledge_date.isoformat(),
            "start_year": start_year, "current_year": knowledge_date.year, "horizon": horizon, "measure": measure,
            "measure_label": MEASURES[measure], "items": items, "groups": groups, "districts": mapped, "blocks": blocks,
            "municipalities":municipality_groups,"municipality_unlinked_ids":sorted(row["id"] for row in rows if row["id"] not in resolved),
            "summary": calculate(rows),
            "unlocated_project_ids": sorted(row["id"] for row in rows if row["id"] not in located),
            "history": {"events": flow, "report_rows": len(annual_reports),
                        "report_dates": sorted({row["report_date"] for row in annual_reports}), "notice_count": len(annual_notices),
                        "permit_count":len(annual_permits) if annual_permit_count is None else annual_permit_count},
            "notice": "계획량·공고 연결은 검토 합계입니다. 승인 대기 포함·연결 해제 제외. 프로그램 정책과 공급대책은 중첩되므로 정책별 항목을 합산하지 않습니다. 현재 공고량은 LH·지구·블록 일치의 본 모집공고만 집계하며 사전·잔여·추가 공고는 제외합니다. 실입주·정책 실적은 미확보입니다.",
            "future_basis": "기준월 이후부터 각 미래 연도 말까지 누적 · 기준월 예정과 당해연도 관리자 목표 제외 · 원천과 관리자 목표 별도",
            "geometry_basis": "조회 기준일에 확보한 공식 지구 경계를 과거 자료 위치의 참고 경계로 사용 · 과거 경계 복원 아님"}
