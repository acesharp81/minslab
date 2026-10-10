"""Download exactly the selected dashboard grouping, plus its block detail."""
import csv
import io


def supply_csv(data, group_by="all", group_id=None):
    fields = ["analysis_year", "reference_date", "knowledge_date", "measure", "group_type", "group_id", "name",
              "region", "coordinate_basis", "project_ids", "evidence_urls", "project_count", "target_units", "target_counted_projects",
              "target_excluded_projects", "target_missing_projects", "announced_target_units", "target_scope", "target_metric",
              "current_notice_units", "current_notice_count", "actual_delivery_units", "actual_delivery_pct",
              "observed_units", "observed_pct", "observed_projects", "ratio_excluded_notice_units", "year_to_date_goal_units", "cumulative_goal_units",
              "goal_missing_events", "annual_manual_goal_units", "early_count", "max_lead_months", "on_time_count", "schedule_comparison_basis", "late_count", "max_lag_months", "schedule_gap_count", "max_gap_months", "verification_count",
              "offset", "end_year", "source_units", "manual_units", "source_events", "manual_events", "units_missing_events",
              "projection_baseline_units", "projected_increment_units", "projected_cumulative_units", "projected_cumulative_pct",
              "projection_excluded_events", "projection_excluded_units", "projection_status", "projection_basis",
              "status", "observed_basis", "goal_basis", "future_basis"]
    entries = [(kind, row) for kind in (data["groups"] if group_by == "all" else [group_by])
               for row in data["groups"][kind] if not group_id or row["id"] == group_id]
    selected_ids = set(entries[0][1]["project_ids"]) if group_id and entries else None
    for kind,geographic_rows in (("block",data["blocks"]),("municipality",data["municipalities"])):
        for row in geographic_rows:
            quantity = row.get("group_quantities", {}).get(group_by, {}).get(group_id) if group_id else row
            if quantity:
                entries.append((kind, {**row, **quantity, "project_ids":[pid for pid in row["project_ids"]
                    if selected_ids is None or pid in selected_ids]}))
    buffer = io.StringIO()
    projects = {row["id"]:row for row in data["items"]}
    writer = csv.DictWriter(buffer, fieldnames=fields)
    writer.writeheader()
    for kind, row in entries:
        base = {field: row.get(field) for field in fields}
        base.update({field: data[field] for field in ("analysis_year", "reference_date", "knowledge_date", "measure", "future_basis")})
        base.update({field: row["progress"].get(field) for field in fields if field in row["progress"]})
        base.update(group_type=kind, group_id=row["id"], status="REVIEW_NOT_OFFICIAL_ACTUAL")
        base["project_ids"] = "|".join(row["project_ids"])
        base["evidence_urls"] = "|".join(sorted({url for pid in row["project_ids"] for url in
            (projects[pid].get("evidence_url"), (projects[pid].get("notice_evidence") or {}).get("evidence_url")) if url}))
        for future in row["future"]:
            item = {**base, **{field: future.get(field) for field in fields if field in future}}
            projected=row["projection"]["future"][future["offset"]-1]
            item.update(projection_baseline_units=row["projection"]["baseline_units"],projected_increment_units=projected["increment_units"],
                projected_cumulative_units=projected["cumulative_units"],projected_cumulative_pct=projected["cumulative_pct"],
                projection_excluded_events=projected["excluded_events"],projection_excluded_units=projected["excluded_units"],
                projection_status=projected["status"],projection_basis=row["projection"]["basis"])
            writer.writerow({field: "'"+value if isinstance(value, str) and value.startswith(("=", "+", "-", "@")) else value
                             for field, value in item.items()})
    return "\ufeff" + buffer.getvalue()
