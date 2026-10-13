"""Read PoC 10 public APIs and write a traceable PoC 12 HOME data snapshot.

The import is deliberately read-only. Source project IDs, nulls, provenance and
review states survive conversion; no PoC 12 registry IDs or map coordinates are
invented. The API is read over a time window, not as a database transaction.
"""
from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin
from urllib.request import urlopen

BASE = "http://127.0.0.1:18100/poc/home/api/"
ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "data" / "home10" / "converted.json"
REPORT = ROOT / "docs" / "POLICY_907_DATA_GAPS.md"
MAP_OUTPUT = ROOT / "data" / "home10" / "map.json"
# This is a navigation aid, not a claim of official approval or completion.
STAGE = {
    "CANDIDATE": "02", "PROPOSED_DISTRICT": "02", "DESIGNATED": "02",
    "PLANNING": "02", "PLANNED_SUPPLY": "02", "APPROVAL": "03",
    "CONSTRUCTION": "04",
}
MUNICIPALITY_UNKNOWN = {"지역 상세 확인 필요", "서울 (구 확인 필요)", ""}


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def get(base: str, route: str):
    with urlopen(urljoin(base, route), timeout=60) as response:
        return json.load(response)


def all_pages(base: str, route: str):
    rows = []
    page = 1
    while True:
        body = get(base, f"{route}?page={page}&page_size=200")
        rows.extend(body["items"])
        if len(rows) >= body["total"]:
            if len(rows) != body["total"]:
                raise ValueError(f"{route}: pagination count changed during import")
            return rows
        if not body["items"]:
            raise ValueError(f"{route}: empty page before expected total")
        page += 1


def known(value):
    return value if value is not None and value != "" else None


def location_key(region, district, block):
    if not region or not district or not block:
        return None
    area = re.sub(r"\s*\([^)]*\)\s*$", "", str(district)).replace("국제화계획", "")
    area = re.sub(r"[^가-힣a-z0-9]", "", area.lower())
    for suffix in ("공공주택지구", "택지개발사업", "택지개발지구", "도시개발사업", "공급촉진지구", "지구"):
        if area.endswith(suffix):
            area = area[:-len(suffix)]
            break
    lot = re.fullmatch(r"([a-z]{1,3})\s*-?\s*0*(\d+)(?:bl)?", str(block).lower(), re.I)
    return (region, area, lot[1] + str(int(lot[2]))) if area and lot else None


def project_site(row):
    district, block = known(row.get("district")), known(row.get("block"))
    if district and block:
        return district, block, "SOURCE_FIELDS"
    if row.get("source_id") not in {"lh_sale", "lh_rent"}:
        return district, block, None
    match = re.fullmatch(r"(.+?)\s+([a-z]{1,3}-?\d+(?:-\d+)?(?:bl)?)", row.get("name") or "", re.I)
    return (match[1], match[2], "LH_PLAN_NAME_SINGLE_BLOCK") if match else (district, block, None)


def normalize_project(row, identity, source_names, location=None, location_gap_reason=None):
    mapping = row.get("mapping") or {}
    move_in = row.get("move_in_start") or {}
    data_status = row.get("data_status") or {}
    aliases = identity[1] if identity else []
    municipality = known(row.get("municipality"))
    if municipality in MUNICIPALITY_UNKNOWN:
        municipality = None
    district, block, location_match_rule = project_site(row)
    address = known(row.get("address"))
    location_level = ("BLOCK" if district and block else "ADDRESS" if address else
                      "MUNICIPALITY" if municipality else "REGION")
    return {
        "id": row["id"], "name": row["name"], "region": known(row.get("region")),
        "municipality": municipality, "district": district, "block": block,
        "address": address, "locationLevel": location_level,
        "sourceId": row["source_id"], "sourceName": source_names.get(row["source_id"], row["source_id"]),
        "revisionNo": row.get("revision_no"), "recordedAt": known(row.get("recorded_at")),
        "baseDate": known(row.get("base_date")), "evidenceUrl": known(row.get("evidence_url")),
        "rawStage": known(row.get("stage")), "stageLabel": known(row.get("stage_label")),
        "stageCode": STAGE.get(row.get("stage")),
        "plannedUnits": row.get("planned_units"), "unitBasis": known(row.get("unit_basis")),
        "supplyUnits": row.get("supply_units"), "actualDeliveryUnits": row.get("actual_delivery_units"),
        "progressPct": row.get("progress_pct"),
        "progressDate": known(row.get("progress_date")),
        "progressEvidenceUrl": known(row.get("progress_evidence_url")),
        "progressDateBasis": known(row.get("progress_date_basis")),
        "scheduleMonth": known(row.get("schedule_month")),
        "scheduleBasis": known(row.get("schedule_basis")),
        "startActualDate": known(row.get("start_actual_date")),
        "completionPlanDate": known(row.get("completion_plan_date")),
        "moveInStartDate": known(move_in.get("date")),
        "moveInStartStatus": known(move_in.get("status")),
        "moveInStartBasis": known(move_in.get("basis")),
        "moveInStartEvidenceUrl": known(move_in.get("evidence_url")),
        "dataPhase": known(data_status.get("phase")),
        "completionDateStatus": known(data_status.get("completion_date")),
        "inLatestSource": row.get("in_latest_source"),
        "longitude": location["longitude"] if location else row.get("longitude"),
        "latitude": location["latitude"] if location else row.get("latitude"),
        "locationRole": location["geometry_role"] if location else None,
        "locationJoinStatus": "NAME_MATCH_REVIEW" if location else None,
        "locationEvidenceUrl": location.get("location_evidence_url") if location else None,
        "locationAnchorId": location["id"] if location else None,
        "locationMatchRule": location_match_rule if location else None,
        "locationGapReason": location_gap_reason,
        "developer": known(row.get("developer")), "contractor": known(row.get("contractor")),
        "programName": known(mapping.get("program_name") or row.get("program")),
        "programId": known(mapping.get("program_id")),
        "policyId": known(mapping.get("policy_id")),
        "projectProgramStatus": known(mapping.get("status")),
        "programPolicyStatus": known(mapping.get("policy_status")),
        "mappingBasis": known(mapping.get("basis") or row.get("mapping_basis")),
        "identityId": identity[0] if identity else None,
        "identityStatus": identity[2] if identity else None,
        "forecastLinkCount": len(aliases),
        "forecastLinkStatus": (aliases[0].get("status") if len({a.get("status") for a in aliases}) == 1 else "MIXED") if aliases else None,
        "forecastUnitComparison": (aliases[0].get("unit_comparison") if len({a.get("unit_comparison") for a in aliases}) == 1 else "MIXED") if aliases else None,
        "warnings": row.get("warnings") or [],
    }


def convert(base: str):
    started = now()
    projects = all_pages(base, "projects")
    identities = all_pages(base, "identities")
    policies = get(base, "policies")["items"]
    programs = get(base, "programs")["items"]
    plans = get(base, "plans")["items"]
    sources = get(base, "sources")["items"]
    coverage = get(base, "coverage")["items"]
    geometry = get(base, "policy-geo/geometry")
    annual_supply = get(base, "annual-supply")
    roadmap = get(base, "roadmap")
    policy_monitor = get(base, "policy-monitor")
    ended = now()

    if len({p["id"] for p in projects}) != len(projects):
        raise ValueError("duplicate PoC 10 project ID")
    if len({p["id"] for p in identities}) != len(identities):
        raise ValueError("duplicate PoC 10 identity ID")
    if roadmap["total"] != len(projects) or {p["id"] for p in roadmap["items"]} != {p["id"] for p in projects}:
        raise ValueError("roadmap and project candidate IDs differ")
    source_names = {s["id"]: s["name"] for s in sources}
    anchors = {}
    forecast_by_identity = {}
    alias_status = Counter()
    alias_comparison = Counter()
    for entry in identities:
        for alias in entry.get("aliases") or []:
            alias_status[alias.get("status") or "UNKNOWN"] += 1
            if alias.get("match_rule") == "SOURCE_ANCHOR":
                anchors[alias["source_entity_id"]] = (entry["id"], [], entry.get("identity_status"))
            elif alias.get("match_rule") == "REGION_DISTRICT_BLOCK":
                forecast_by_identity.setdefault(entry["id"], []).append(alias)
                alias_comparison[alias.get("unit_comparison") or "UNKNOWN"] += 1
    for entity, (identity_id, _, status) in list(anchors.items()):
        anchors[entity] = (identity_id, forecast_by_identity.get(identity_id, []), status)
    projects_by_location = defaultdict(lambda: defaultdict(list))
    for row in projects:
        district, block, _ = project_site(row)
        key = location_key(row.get("region"), district, block)
        if key and row.get("source_id") in {"lh_construction", "lh_progress", "lh_sale", "lh_rent"}:
            group = "WORK" if row["source_id"] in {"lh_construction", "lh_progress"} else "PLAN"
            projects_by_location[key][group].append(row)
    labels_by_location = defaultdict(list)
    for anchor in geometry.get("block_anchors") or []:
        if (anchor.get("geometry_role") != "LH_PUBLIC_BLOCK_LABEL_POINT"
                or not anchor.get("location_evidence_url")):
            continue
        lon, lat = anchor.get("longitude"), anchor.get("latitude")
        if not isinstance(lon, (int, float)) or not isinstance(lat, (int, float)) or not (120 <= lon <= 135 and 30 <= lat <= 45):
            continue
        key = location_key(anchor.get("region"), anchor.get("district_name"), anchor.get("block"))
        if key:
            labels_by_location[key].append(anchor)
    matched_locations = {}
    for key, groups in projects_by_location.items():
        if len(labels_by_location[key]) != 1:
            continue
        for members in groups.values():
            # The same block may occur once in construction and once in a supply plan.
            # Keep their business identities separate; reject ambiguity within a cohort.
            if len(members) == 1:
                matched_locations[members[0]["id"]] = labels_by_location[key][0]
    gap_reasons = {}
    for row in projects:
        if row["id"] in matched_locations:
            continue
        source = row.get("source_id")
        if source not in {"lh_construction", "lh_progress", "lh_sale", "lh_rent"}:
            reason = "SITE_EVIDENCE_REQUIRED"
        else:
            district, block, _ = project_site(row)
            key = location_key(row.get("region"), district, block)
            group = "WORK" if source in {"lh_construction", "lh_progress"} else "PLAN"
            reason = ("NO_SINGLE_BLOCK_CODE" if not key else
                      "NO_PUBLIC_BLOCK_LABEL" if not labels_by_location[key] else
                      "AMBIGUOUS_BLOCK_LABEL" if len(labels_by_location[key]) > 1 else
                      "AMBIGUOUS_SOURCE_BLOCK" if len(projects_by_location[key][group]) > 1 else
                      "LOCATION_REVIEW_REQUIRED")
        gap_reasons[row["id"]] = reason
    converted = [normalize_project(p, anchors.get(p["id"]), source_names,
                                   matched_locations.get(p["id"]), gap_reasons.get(p["id"])) for p in projects]
    converted.sort(key=lambda p: (p["region"] or "", p["name"], p["id"]))
    if any(p["stageCode"] in {"05", "06"} for p in converted):
        raise ValueError("planned HOME records must not be labelled actual supply/move-in")
    if any(p["supplyUnits"] is None and p["plannedUnits"] is None and p["progressPct"] == 0 for p in converted):
        raise ValueError("missing progress must remain null")
    if len(anchors) != len(projects):
        raise ValueError(f"missing source identity anchors: {len(anchors)}/{len(projects)}")

    output = {
        "format": "poc12-home10-converted/1", "source": "PoC 10 HOME read-only public API",
        "readStartedAt": started, "readFinishedAt": ended,
        "scope": "서울특별시·경기도 HOME 사업후보와 정책·원천·커버리지",
        "notes": ["API 여러 경로를 순서대로 읽었으므로 단일 DB 트랜잭션 스냅샷은 아닙니다.",
                  "PRO_/HPR_ 식별자는 PoC 10 원본이며 PoC 12 PRJ 레지스트리와 동일 사업으로 자동 병합하지 않았습니다.",
                  "계획호수, 공급계획호수, 현장 공정률과 실제 준공·입주 호수는 서로 다른 지표입니다.",
                  "일부 좌표는 PoC 10 LH 블록 라벨점과 지역·지구·블록이 유일하게 일치한 탐색용 위치입니다. 사업 경계나 동일성 승인으로 사용하지 않습니다."],
        "projects": converted,
        "annualSupply": annual_supply,
        "roadmap": roadmap,
        "policyMonitor": policy_monitor,
        "policies": [{"id": p.get("policy_id") or p.get("id"), "name": p.get("name"),
                      "metric": p.get("metric"), "targetUnits": p.get("target_units"),
                      "targetScope": p.get("target_scope"), "status": p.get("lifecycle_status"),
                      "announcedAt": p.get("announced_at"), "evidenceUrl": p.get("evidence_url")}
                     for p in policies],
        "programs": [{"id": p["id"], "name": p["name"], "policyId": p.get("policy_id"),
                       "status": p.get("status"), "projectCount": p.get("project_count"),
                       "basis": p.get("basis"), "evidenceUrl": p.get("evidence_url")}
                      for p in programs],
        "plans": [{"id": p["id"], "name": p.get("name"), "region": p.get("region"),
                   "legalStatus": p.get("legal_status"),
                   "events": [{"noticeNo": e.get("notice_no"), "noticeDate": e.get("notice_date"),
                               "evidenceUrl": e.get("evidence_url")}
                              for e in p.get("events") or []],
                   "projectLinks": len(p.get("project_links") or [])} for p in plans],
        "sources": [{"id": s["id"], "name": s.get("name"), "org": s.get("org"),
                     "url": s.get("url"), "type": s.get("type"),
                     "status": s.get("status"), "lastSuccess": s.get("last_success"),
                     "recordCount": s.get("record_count")}
                    for s in sources],
        "coverage": [{"sourceId": c.get("source_id"), "endpoint": c.get("endpoint"),
                      "region": c.get("region"), "areaCode": c.get("area_code"),
                      "sourcePeriod": c.get("source_period"),
                      "expectedCount": c.get("expected_count"), "fetchedCount": c.get("fetched_count"),
                      "queryStatus": c.get("query_status"), "populationStatus": c.get("population_status"),
                      "scopeNote": c.get("scope_note"), "recordedAt": c.get("recorded_at")}
                     for c in coverage],
        "identitySummary": {"identities": len(identities), "anchors": len(anchors),
                            "forecastReviewCount": sum(len(items) for items in forecast_by_identity.values()),
                            "forecastProjects": len(forecast_by_identity),
                            "aliasStatuses": dict(alias_status),
                            "forecastUnitComparison": dict(alias_comparison)},
        "locationSummary": {"blockLabelAnchors": len(geometry.get("block_anchors") or []),
                            "usableBlockLabels": sum(map(len, labels_by_location.values())),
                            "uniqueProjectMatchesForReview": len(matched_locations),
                            "distinctLinkedBlocks": len({a["id"] for a in matched_locations.values()}),
                            "matchedBySource": dict(Counter(p["source_id"] for p in projects if p["id"] in matched_locations)),
                            "unresolvedBySource": dict(Counter(p["source_id"] for p in projects if p["id"] in gap_reasons)),
                            "unresolvedByReason": dict(Counter(gap_reasons.values()))},
    }
    map_output = {
        "format": "poc12-home10-map/1", "readFinishedAt": ended,
        "scope": geometry.get("scope"), "geometryNote": geometry.get("geometry_note"),
        "regions": geometry["regions"], "municipalities": geometry["municipalities"],
        "housingLands": {"type": "FeatureCollection", "features": []},  # unrelated land polygons are not 9·7 projects
        "projects": [{key: p.get(key) for key in (
            "id", "name", "region", "municipality", "district", "block", "stageCode",
            "stageLabel", "plannedUnits", "progressPct", "sourceName", "evidenceUrl",
            "policyId", "projectProgramStatus",
            "longitude", "latitude", "locationRole", "locationJoinStatus", "locationEvidenceUrl",
            "locationAnchorId", "locationMatchRule", "locationGapReason")}
                     for p in converted if p["policyId"] == "POL_2025_0907"],
    }
    return output, map_output


def gap_counts(data):
    rows = data["projects"]
    checks = {
        "계획호수": lambda p: p["plannedUnits"] is not None,
        "공급계획호수": lambda p: p["supplyUnits"] is not None,
        "원천 공정률": lambda p: p["progressPct"] is not None,
        "일정 월": lambda p: p["scheduleMonth"] is not None,
        "구체 시군구": lambda p: p["municipality"] is not None,
        "지구·블록": lambda p: p["district"] is not None and p["block"] is not None,
        "주소": lambda p: p["address"] is not None,
        "공사 시작 실적일": lambda p: p["startActualDate"] is not None,
        "준공 예정일": lambda p: p["completionPlanDate"] is not None,
        "입주 시작 예정일": lambda p: p["moveInStartDate"] is not None,
        "실제 준공·입주 호수": lambda p: p["actualDeliveryUnits"] is not None,
        "사업 API 직접 좌표": lambda p: p["locationRole"] is None and p["longitude"] is not None and p["latitude"] is not None,
        "LH 블록 라벨점 연결": lambda p: p["locationRole"] == "LH_PUBLIC_BLOCK_LABEL_POINT",
        "원문 URL": lambda p: p["evidenceUrl"] is not None,
    }
    return {name: {"present": sum(bool(fn(p)) for p in rows), "missing": sum(not fn(p) for p in rows)}
            for name, fn in checks.items()}


POLICY_907 = "POL_2025_0907"


def policy_907_snapshot(full):
    """Keep only source records used by the public 9·7 proof of concept."""
    projects = [row for row in full["projects"] if row["policyId"] == POLICY_907]
    policies = [row for row in full["policies"] if row["id"] == POLICY_907]
    if not projects or len(policies) != 1:
        raise ValueError("9·7 policy or candidates missing from PoC 10")
    program_ids = {row["programId"] for row in projects}
    source_ids = {row["sourceId"] for row in projects}
    programs = [row for row in full["programs"] if row["id"] in program_ids and row["policyId"] == POLICY_907]
    sources = [row for row in full["sources"] if row["id"] in source_ids]
    if {row["id"] for row in programs} != program_ids or {row["id"] for row in sources} != source_ids:
        raise ValueError("9·7 candidate has an unresolved program or source")
    monitor_items = [row for row in full["policyMonitor"]["items"] if row["id"] == POLICY_907]
    if len(monitor_items) != 1:
        raise ValueError("9·7 policy monitor missing from PoC 10")
    return {
        "format": full["format"], "source": full["source"],
        "readStartedAt": full["readStartedAt"], "readFinishedAt": full["readFinishedAt"],
        "scope": "9·7 주택공급 확대방안 정책의 서울·경기 사업후보와 관련 원천",
        "notes": full["notes"],
        "projects": projects, "policies": policies, "programs": programs,
        "sources": sources,
        "coverage": [row for row in full["coverage"] if row["sourceId"] in source_ids],
        "policyMonitor": {"items": monitor_items},
    }


def policy_907_report(data):
    rows = data["projects"]
    gaps = gap_counts(data)
    linked = [row for row in rows if row["locationRole"] == "LH_PUBLIC_BLOCK_LABEL_POINT"]
    source_counts = Counter(row["sourceId"] for row in rows)
    lines = [
        "# 9·7 정책 PoC 자료 범위와 결측", "",
        f"PoC 10 읽기 종료: {data['readFinishedAt']}. 사업후보 {len(rows)}건. "
        "정책 귀속은 모두 REVIEW이며 확정 사업 목록이 아닙니다.", "",
        "| 항목 | 확보 | 미확보 |", "| --- | ---: | ---: |",
    ]
    for label, key in [("계획 규모", "계획호수"), ("원천 공정률", "원천 공정률"),
                       ("원천 준공 예정일", "준공 예정일"), ("입주 시작 예정일", "입주 시작 예정일"),
                       ("시군구", "구체 시군구"), ("실제 준공·입주 호수", "실제 준공·입주 호수"),
                       ("LH 블록 라벨점 연결", "LH 블록 라벨점 연결")]:
        values = gaps[key]
        lines.append(f"| {label} | {values['present']} | {values['missing']} |")
    lines += ["", "## 해석", "",
              "- 발표 목표 135만 호는 수도권(인천 포함) 2026~2030년 착공 목표입니다. 수집 후보는 서울·경기만 포함하며 인천 후보는 없습니다.",
              f"- 9·7 연결 후보 {len(rows)}건은 원천 기록입니다. 동일 사업 여부와 정책 귀속이 승인되지 않아 계획 규모·예정 호수를 서로 더하지 않습니다.",
              f"- 연결된 위치 {len(linked)}건은 {len({row['locationAnchorId'] for row in linked})}개 LH 블록 라벨점 이름 대조 결과입니다. 위치가 없는 {len(rows)-len(linked)}건을 지도에 임의로 배치하지 않았습니다.",
              "- 실제 준공·입주 호수는 0건 확인입니다. 이는 실제 물량이 0호라는 뜻이 아니라 이 원천에서 검증된 값이 없다는 뜻입니다.",
              f"- 사용 원천 {len(data['sources'])}종과 직접 연결된 모집단 조회 범위 기록은 {len(data['coverage'])}건입니다. 수집 성공이 전체 목록 완결을 보증하지 않습니다.",
              "- 3D는 공식 건물 형상과 가상 아파트 모형을 구분합니다. 가상 동수·층수·배치는 실제 설계가 아니며, 위치 미확보 후보는 배경지도 없는 개별 미리보기에서만 표시합니다. [형상 수집 결과](HOME10_3D.md)를 참고하세요.",
              "", "## 원천별 후보 행", "", "| 원천 ID | 후보 행 |", "| --- | ---: |"]
    lines.extend(f"| {source_id} | {count} |" for source_id, count in sorted(source_counts.items()))
    lines.append("")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api", default=BASE, help="PoC 10 public read-only API base")
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--report", type=Path, default=REPORT)
    parser.add_argument("--map-output", type=Path, default=MAP_OUTPUT)
    args = parser.parse_args()
    full_data, map_data = convert(args.api.rstrip("/") + "/")
    data = policy_907_snapshot(full_data)
    if {row["id"] for row in data["projects"]} != {row["id"] for row in map_data["projects"]}:
        raise ValueError("9·7 snapshot and map candidate IDs differ")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temp = args.output.with_suffix(args.output.suffix + ".tmp")
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    temp.replace(args.output)
    args.map_output.parent.mkdir(parents=True, exist_ok=True)
    map_temp = args.map_output.with_suffix(args.map_output.suffix + ".tmp")
    map_temp.write_text(json.dumps(map_data, ensure_ascii=False, separators=(",", ":")) + "\n")
    map_temp.replace(args.map_output)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(policy_907_report(data))
    print(f"converted 9·7 only: {len(data['projects'])} projects, {len(data['policies'])} policies, "
          f"{len(data['programs'])} programs, {len(data['sources'])} sources → {args.output}")
    print(f"HOME map → {args.map_output}")
    print(f"data gaps → {args.report}")


if __name__ == "__main__":
    main()
