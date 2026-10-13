#!/usr/bin/env python3
"""Validate an already generated housing-wave v1.4 CSV package."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

from convert import Converter, FILES, FORM, as_int, day, month, period


def check(root: Path):
    headers = Converter.read_headers()
    rows = {}
    errors = []
    for name in FILES:
        path = root / name
        if not path.exists():
            errors.append(f"Missing file: {name}")
            continue
        if not path.read_bytes().startswith(b"\xef\xbb\xbf"):
            errors.append(f"Missing UTF-8 BOM: {name}")
        with path.open("r", encoding="utf-8-sig", newline="") as stream:
            reader = csv.DictReader(stream)
            if tuple(reader.fieldnames or ()) != headers[name]:
                errors.append(f"Header mismatch: {name}")
            rows[name] = list(reader)
    if errors:
        return errors
    projects = [r["local_project_id"] for r in rows["사업_projects.csv"]]
    policies = [r["local_policy_id"] for r in rows["정책_policies.csv"]]
    programs = [r["local_program_id"] for r in rows["프로그램_programs.csv"]]
    sources = [r["source_ref"] for r in rows["원천_sources.csv"]]
    for name, ids in (("local_project_id", projects), ("local_policy_id", policies), ("local_program_id", programs), ("source_ref", sources)):
        if len(ids) != len(set(ids)) or any(not value for value in ids):
            errors.append(f"Duplicate or empty {name}")
    project_set, policy_set, program_set, source_set = map(set, (projects, policies, programs, sources))
    for filename, data in rows.items():
        for n, row in enumerate(data, 2):
            if filename != "원천_sources.csv" and row.get("source_ref") not in source_set:
                errors.append(f"Invalid source_ref: {filename}:{n}")
            if filename in ("사업식별자_identifiers.csv", "진행이력_events.csv", "공급물량_units.csv") and row["local_project_id"] not in project_set:
                errors.append(f"Invalid project reference: {filename}:{n}")
            for field in ("announcement_date", "event_date", "data_as_of", "collected_at"):
                if row.get(field) and not day(row[field]):
                    errors.append(f"Invalid date: {filename}:{n}:{field}")
            for field in ("event_month", "reference_period"):
                if row.get(field) and not period(row[field]):
                    errors.append(f"Invalid period: {filename}:{n}:{field}")
            if filename == "공급물량_units.csv":
                if as_int(row["unit_count"]) is None:
                    errors.append(f"Invalid unit_count: {n}")
                if row["quantity_type"] not in {"PROJECT_PLAN", "PUBLIC_PLAN", "SUPPLY_PLAN", "NOTICE", "MOVE_IN_ACTUAL"}:
                    errors.append(f"Invalid quantity_type: {n}")
            if filename == "진행이력_events.csv" and row["progress_pct"]:
                try:
                    if not 0 <= float(row["progress_pct"]) <= 100:
                        errors.append(f"Invalid progress_pct: {n}")
                except ValueError:
                    errors.append(f"Invalid progress_pct: {n}")
            if filename == "정책사업연결_links.csv":
                if row["link_type"] == "POLICY_PROGRAM" and not (row["from_local_id"] in policy_set and row["to_local_id"] in program_set):
                    errors.append(f"Invalid policy-program reference: {n}")
                elif row["link_type"] == "PROGRAM_PROJECT" and not (row["from_local_id"] in program_set and row["to_local_id"] in project_set):
                    errors.append(f"Invalid program-project reference: {n}")
                elif row["link_type"] not in {"POLICY_PROGRAM", "PROGRAM_PROJECT"}:
                    errors.append(f"Invalid link_type: {n}")
            if "review_status" in row and row["review_status"] not in {"CONFIRMED", "REVIEW_REQUIRED"}:
                errors.append(f"Invalid review_status: {filename}:{n}")
    return errors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    errors = check(args.directory)
    if errors:
        raise SystemExit("\n".join(errors[:100]))
    print("PASS: 8 CSV headers, BOM, dates, numbers, IDs, and references")


if __name__ == "__main__":
    main()
