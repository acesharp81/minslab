"""Comparable milestones only; missing actuals never become zero delivery."""
from .roadmap import source_events


def progress_metrics(selected, event_rows, plans, reference, measure, notice_links, manual_rows=None):
    cutoff = reference.strftime("%Y-%m")
    events = [(row, event) for row in event_rows for event in source_events(row, reference)
              if event["stage"] == measure]
    elapsed = [(row, event) for row, event in events if event["month"] < cutoff]
    year_elapsed = [event for _, event in elapsed if event["year"] == reference.year]
    def total(events):
        known = [event["units"] for event in events if event["units"] is not None]
        return sum(known) if known else None
    capacities = {row["id"]: row["planned_units"] for row in selected if row.get("planned_units") is not None}
    observed = [(pid, notice) for pid, notice in (notice_links or {}).items() if pid in capacities]
    observed_units = sum(notice["units"] for _, notice in observed) if observed else None
    capacity = sum(capacities.values()) if capacities else None
    # Notices prove the recruitment milestone only, not completion or move-in.
    milestone_units = observed_units if measure == "SUPPLY" else None
    late, gaps, early, on_time, pending = {}, {}, {}, set(), set()
    event_counts = {}
    for row, _ in events:
        event_counts[row["id"]] = event_counts.get(row["id"], 0) + 1
    for row, event in events:
        notice = (notice_links or {}).get(row["id"]) if measure == "SUPPLY" else None
        overdue = event["month"] < cutoff
        if not notice:
            if overdue:
                pending.add(row["id"])
            continue
        # One notice cannot establish which of several planned tranches it met.
        # Plans revised after the notice cannot establish earlier timeliness.
        if event_counts[row["id"]] > 1 or notice["source_date"] < row["base_date"]:
            if overdue:
                pending.add(row["id"])
            continue
        actual_month = notice["source_date"][:7]
        difference = (int(actual_month[:4])-event["year"])*12 + int(actual_month[5:])-int(event["month"][5:])
        if difference > 0:
            collection = late if row.get("date_precision") == "DAY" else gaps
            collection[row["id"]] = max(collection.get(row["id"], 0), difference)
        elif row.get("date_precision") == "DAY":
            if difference < 0:
                early[row["id"]] = max(early.get(row["id"], 0), -difference)
            else:
                on_time.add(row["id"])
        elif overdue:
            pending.add(row["id"])
    manual = [goal for row in (manual_rows if manual_rows is not None else selected) for goal in plans.get(row.get("master_id") or row["id"], {}).get("targets", [])
              if goal["stage"] == measure and goal["year"] == reference.year]
    return {"measure": measure, "actual_delivery_units": None, "actual_delivery_pct": None,
            "observed_units": milestone_units,
            "observed_pct": round(milestone_units/capacity*100, 2) if milestone_units is not None and capacity else None,
            "observed_projects": len(observed) if measure == "SUPPLY" else 0,
            "ratio_excluded_notice_units": sum(notice["units"] for pid,notice in (notice_links or {}).items()
                if pid in {row["id"] for row in selected} and pid not in capacities),
            "capacity_projects": len(capacities),
            "year_to_date_goal_units": total(year_elapsed),
            "cumulative_goal_units": total([event for _, event in elapsed]),
            "goal_missing_events": sum(event["units"] is None for _, event in elapsed),
            "year_to_date_goal_events": len(year_elapsed),
            "annual_manual_goal_units": total(manual),
            "early_projects": sorted(early), "early_count": len(early),
            "max_lead_months": max(early.values(), default=None),
            "on_time_projects": sorted(on_time), "on_time_count": len(on_time),
            "schedule_comparison_basis": "최초 근거 기준일 이후의 본 모집공고와 단일 예정월 비교 · 조기는 예정월보다 이전, 정상은 동월 · 연결 검토",
            "late_projects": sorted(late), "late_count": len(late),
            "max_lag_months": max(late.values(), default=None),
            "schedule_gap_project_ids": sorted(gaps), "schedule_gap_count": len(gaps),
            "max_gap_months": max(gaps.values(), default=None),
            "verification_project_ids": sorted(pending), "verification_count": len(pending),
            "goal_basis": "확보한 원천 예정월 기준 · 기준월은 일자 미확인으로 제외 · 연간 관리자 목표는 월별 배분하지 않음",
            "observed_basis": "동일 집계 대상의 LH 본 모집공고 확인 비율(하한·연결 검토) · 실제 보급률 미확보"}
