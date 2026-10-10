"""Policy review statistics. Programme views overlap announcement policies."""
from .roadmap import source_events
from .supply_dashboard import inventory, quantities, block_key
from .matching_rules import catalogue, automatic_proposal, policy_members

def monitor_metrics(rows, quantity, reference, canonical_ids, notices, plans):
    selected = [row for row in rows if row["id"] in canonical_ids and row.get("planned_units") is not None]
    source_rows, _ = inventory([row for row in rows if any(e["stage"] == "SUPPLY" for e in source_events(row, reference))])
    annual = []
    annual_covered = set()
    for row in source_rows:
        if row["id"] not in canonical_ids:
            continue
        manual = [t for t in plans.get(row["id"], {}).get("targets", []) if t["year"] == reference.year and t["stage"] == "SUPPLY"]
        events = manual or [e for e in source_events(row, reference) if e["year"] == reference.year and e["stage"] == "SUPPLY"]
        if events:
            annual_covered.add(row["id"])
            annual.extend(events)
    # Manual goals on projects without a source supply schedule still count.
    for row in selected:
        if row["id"] not in annual_covered:
            targets = [t for t in plans.get(row["id"], {}).get("targets", []) if t["year"] == reference.year and t["stage"] == "SUPPLY"]
            if targets:
                annual_covered.add(row["id"])
                annual.extend(targets)
    known = [e["units"] for e in annual if e.get("units") is not None]
    goal = sum(known) if known else None
    linked = [(row, notices[row["id"]]) for row in selected if row["id"] in notices]
    observed = sum(notice["units"] for _, notice in linked) if linked else None
    year_observed = sum(notice["units"] for _, notice in linked if notice["source_date"][:4] == str(reference.year)) if linked else None
    capacity = quantity["target_units"]
    schedules = []
    scheduled_keys = set()
    capacity_by_key = {(block_key(row) or row["id"]): row["planned_units"] for row in selected}
    for row in rows:
        key = block_key(row) or row["id"]
        if "MULTI_SITE_CONTRACT" in row.get("warnings", []):
            continue
        events = [e for e in source_events(row, reference) if e["stage"] in {"MOVE_IN", "COMPLETION"}]
        dates = [e["month"] for e in events]
        if dates:
            schedules.extend(dates)
            for stage in ("MOVE_IN", "COMPLETION"):
                stage_events = [e for e in events if e["stage"] == stage]
                if stage_events and all(e.get("units") is not None for e in stage_events) and sum(e["units"] for e in stage_events) == capacity_by_key.get(key):
                    scheduled_keys.add(key)
    capacity_keys = {block_key(row) or row["id"] for row in selected}
    complete = bool(capacity_keys) and capacity_keys <= scheduled_keys and not quantity["target_missing_projects"]
    return dict(annual_goal_units=goal, annual_observed_units=year_observed,
                annual_achievement_pct=round(year_observed / goal * 100, 2) if year_observed is not None and goal else None,
                cumulative_observed_units=observed,
                cumulative_achievement_pct=round(observed / capacity * 100, 2) if observed is not None and capacity else None,
                annual_goal_missing_events=sum(e.get("units") is None for e in annual), annual_goal_project_count=len(annual_covered),
                annual_goal_basis="관리자 공급 목표가 있으면 해당 사업 원천 연간 공급 예정 대신 사용",
                expected_completion_month=max(schedules) if complete and schedules else None,
                latest_known_completion_month=max(schedules) if schedules else None,
                completion_schedule_projects=len(capacity_keys & scheduled_keys), completion_capacity_projects=len(capacity_keys),
                completion_basis="연결 사업의 준공·입주 예정 중 마지막 시점 · 일정 미확보 사업이 있으면 전체 완료 전망 미확보",
                review_count=sum(r.get("mapping", {}).get("status") == "REVIEW" for r in rows),
                confirmed_count=sum(r.get("mapping", {}).get("status") == "CONFIRMED" for r in rows),
                actual_annual_achievement_pct=None, actual_cumulative_achievement_pct=None,
                metric_basis="모집공고 확인 기준 · 검토 연결 포함 · 실제 착공·준공·입주 달성률 아님")


def build_monitor(projects, policies, goals, notices, reference, reports=(), districts=(), municipalities=(), policy_events=()):
    from .supply_dashboard import linked_notices
    rows = [r for r in projects if r.get("mapping", {}).get("status") != "RELEASED"]
    selected, _ = inventory(rows)
    canonical = {r["id"] for r in selected}
    linked = linked_notices(selected, notices, reference)
    plans = {r["project_id"]: r for r in goals}
    for index, row in enumerate(rows):
        notice = linked.get(row["id"])
        stamp = (notice or {}).get("move_in_plan_month") or ""
        if notice and notice["source_date"] < row["base_date"] and any(e["stage"] == "MOVE_IN" for e in source_events(row, reference)):
            continue
        if len(stamp) == 6 and stamp.isdigit() and "01" <= stamp[4:] <= "12":
            row = dict(row, notice_move_in_month=stamp[:4]+"-"+stamp[4:], notice_units=notice["units"], notice_evidence_url=notice.get("evidence_url"))
            rows[index] = row
    from .policy_timeline import timeline_context, build_timeline
    context = timeline_context(rows,plans,reports,districts,municipalities,reference)
    result = []
    for policy in policies:
        members = policy_members(policy, rows)
        quantity = quantities(members, plans, reference, 3, "SUPPLY", target_ids=canonical, notice_links=linked)
        metrics = monitor_metrics(members, quantity, reference, canonical, linked, plans)
        overview,timeline = build_timeline(policy,members,canonical,plans,reference,context,policy_events)
        result.append(dict(overview=overview,timeline=timeline,id=policy["policy_id"], name=policy["name"], kind=policy.get("monitor_kind", "POLICY"),
                           announced_at=policy.get("announced_at"), announced_target_units=policy.get("target_units"),
                           announced_target_scope=policy.get("target_scope"), announced_target_metric=policy.get("metric"),
                           official_target_end_year=2030 if policy["policy_id"] == "POL_2025_0907" else None,
                           evidence_url=policy.get("evidence_url"), project_ids=[r["id"] for r in members],
                           **quantity, **metrics))
    return dict(items=result, reference_date=reference.isoformat(), year=reference.year,
                project_count=len(rows), review_count=sum(r["mapping"]["status"] == "REVIEW" for r in rows),
                confirmed_count=sum(r["mapping"]["status"] == "CONFIRMED" for r in rows),
                released_count=len(projects)-len(rows),
                notice="승인 대기 사업도 검토 통계에 포함합니다. 프로그램 관점은 공급대책과 중첩되므로 항목별 물량을 합산하지 않습니다. 공식 정책 목표의 착공 지표와 공고 확인 달성률은 서로 다른 지표입니다.")
