#!/usr/bin/env python3
"""Read a frozen HOME JSON export and write housing-wave v1.4 CSVs.

This module uses only the Python standard library. It never opens the HOME DB or
calls a collector. The eight CSV headers are read from docs/common_form.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import re
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


HOME = next(parent for parent in Path(__file__).resolve().parents if (parent / "docs/common_form").is_dir())
DEFAULT_INPUT = HOME / "data/exports/home-20261010-live-v3"
DEFAULT_OUTPUT = HOME / "exports/housing_wave_common_v1_4"
FORM = HOME / "docs/common_form"
FILES = (
    "정책_policies.csv", "프로그램_programs.csv", "사업_projects.csv",
    "정책사업연결_links.csv", "사업식별자_identifiers.csv",
    "진행이력_events.csv", "공급물량_units.csv", "원천_sources.csv",
)
REVIEW_COLUMNS = ("item_type", "local_project_id", "source_id", "source_record_key", "reason", "evidence", "proposed_action")
SENSITIVE_QUERY = {"servicekey", "apikey", "api_key", "authkey", "access_token", "token", "password", "secret", "consumer_key"}
DATE_RE = re.compile(r"^\d{4}-(?:0[1-9]|1[0-2])-(?:0[1-9]|[12]\d|3[01])$")
MONTH_RE = re.compile(r"^\d{4}-(?:0[1-9]|1[0-2])$")
BAD_UNIT_WARNINGS = {"MULTI_SITE_CONTRACT", "TOTAL_CONFLICT", "JOINT_QUANTITY_UNALLOCATED"}


def json_rows(path: Path):
    """Stream export arrays, which have one JSON object per line."""
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8") as stream:
        for line in stream:
            value = line.strip().rstrip(",")
            if value.startswith("{"):
                yield json.loads(value)


def load_rows(path: Path):
    return list(json_rows(path))


def day(value):
    if value is None:
        return ""
    value = str(value).strip()
    if re.fullmatch(r"\d{8}", value):
        value = f"{value[:4]}-{value[4:6]}-{value[6:]}"
    if DATE_RE.fullmatch(value):
        try:
            datetime.strptime(value, "%Y-%m-%d")
            return value
        except ValueError:
            return ""
    return ""


def month(value):
    if value is None:
        return ""
    value = str(value).strip()
    if re.fullmatch(r"\d{6}", value):
        value = f"{value[:4]}-{value[4:]}"
    return value if MONTH_RE.fullmatch(value) else ""


def period(value):
    return day(value) or month(value)


def as_int(value):
    if isinstance(value, bool) or value is None or value == "":
        return None
    try:
        number = int(str(value).replace(",", ""))
        return number if str(value).replace(",", "").strip() == str(number) and number >= 0 else None
    except ValueError:
        return None


def safe_url(value):
    if not isinstance(value, str) or not value.startswith(("https://", "http://")):
        return ""
    parts = urlsplit(value)
    query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if k.lower() not in SENSITIVE_QUERY]
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), ""))


def clean(value):
    if value is None:
        return ""
    value = str(value).strip()
    return "" if value in {"시행기관 확인 필요", "지역 상세 확인 필요", "유형 확인 필요", "None"} else value


def district_name(payload):
    raw = clean(payload.get("district") or payload.get("district_name"))
    return raw.rstrip(" (")


def malformed_district(payload):
    raw = clean(payload.get("district") or payload.get("district_name"))
    return bool(raw and raw.count("(") != raw.count(")"))


def block_key(payload):
    district = district_name(payload)
    block = clean(payload.get("block"))
    region = clean(payload.get("region"))
    if not (region and district and block):
        return None
    normalize = lambda s: re.sub(r"[\s\-]", "", s).upper()
    return region, normalize(district), normalize(block)


def stable_id(prefix, value):
    return prefix + hashlib.sha256(value.encode("utf-8")).hexdigest()[:18].upper()


class Converter:
    def __init__(self, input_dir: Path, sample: int | None):
        self.root = input_dir
        self.sample = sample
        self.manifest = json.loads((input_dir / "manifest.json").read_text(encoding="utf-8"))
        self.registry = {r["id"]: r for r in json.loads((input_dir / "source_registry.json").read_text(encoding="utf-8"))}
        self.headers = self.read_headers()
        self.rows = {name: [] for name in FILES}
        self.sources = {}
        self.projects = {}
        self.event_keys = set()
        self.review = []
        self.excluded = Counter()
        self.included = Counter()
        self.used_source_counts = Counter()
        self.batches = {}
        for row in json_rows(input_dir / "collection_batches.json.gz"):
            files = [item.get("file", "") for item in row.get("manifest", []) if isinstance(item, dict)]
            self.batches[row["id"]] = (day(str(row.get("started_at", ""))[:10]), files[0] if len(files) == 1 else "")

    @staticmethod
    def read_headers():
        result = {}
        for name in FILES:
            with (FORM / name).open("r", encoding="utf-8-sig", newline="") as stream:
                result[name] = tuple(next(csv.reader(stream)))
        return result

    def add(self, filename, **fields):
        unknown = set(fields) - set(self.headers[filename])
        if unknown:
            raise ValueError(f"Unknown columns in {filename}: {unknown}")
        self.rows[filename].append({name: fields.get(name, "") for name in self.headers[filename]})

    def flag(self, item_type, project_id, source_id, record_key, reason, evidence="", action="원천 확인"):
        self.review.append(dict(zip(REVIEW_COLUMNS, (item_type, project_id or "", source_id or "", record_key or "", reason, clean(evidence), action))))

    def source(self, record, kind=None):
        source_id = record["source_id"]
        payload = record["payload"]
        key = record["entity_id"]
        ref = stable_id("HOME-SRC-", record["id"])
        if ref in self.sources:
            return ref
        info = self.registry.get(source_id, {})
        batch_date, original = self.batches.get(record.get("batch_id"), ("", ""))
        label = payload.get("source_date_label", "")
        as_of = ""
        if "기준일" in label or "데이터 확인일" in label:
            as_of = period(payload.get("source_date"))
        if not as_of:
            as_of = period(payload.get("dataset_version"))
        if not as_of and source_id.startswith(("policy_", "urban_930", "gh_supply_plan", "lh_sale", "lh_rent", "lh_construction", "lh_progress", "sh_inventory")):
            as_of = period(payload.get("base_date") or payload.get("report_date"))
        self.used_source_counts[source_id] += 1
        self.sources[ref] = {
            "source_ref": ref, "source_owner": "HOME", "provider": clean(info.get("org")),
            "dataset_name": clean(info.get("name") or source_id),
            "source_url": safe_url(payload.get("evidence_url")) or safe_url(info.get("url")),
            "source_record_key": clean(payload.get("source_object_id") or key),
            "data_as_of": as_of, "collected_at": batch_date,
            "original_filename": original,
            "notes": f"source_id={source_id}; HOME entity_id={key}; revision_no={record.get('revision_no')}; recorded_at={record.get('recorded_at')}; source_date_label={label}"[:800],
        }
        return ref

    def mapping_source(self, table, row):
        ref = stable_id("HOME-SRC-", f"{table}:{row['id']}")
        if ref not in self.sources:
            self.used_source_counts["HOME:" + table] += 1
            self.sources[ref] = {
                "source_ref": ref, "source_owner": "HOME", "provider": "HOME",
                "dataset_name": table, "source_url": safe_url(row.get("evidence_url")),
                "source_record_key": row["id"], "data_as_of": "", "collected_at": "",
                "original_filename": table + ".json.gz",
                "notes": f"HOME 연결 상태={row.get('status', row.get('relation_status', ''))}; 스냅샷={self.manifest['snapshot_at']}",
            }
        return ref

    def revisions(self, kind):
        path = self.root / "revisions" / (kind + ".json.gz")
        return (r for r in json_rows(path) if r.get("superseded_at") is None) if path.exists() else iter(())

    def demo(self, record):
        payload = record["payload"]
        return any(str(payload.get(key, "")).upper() == "DEMO" for key in ("sample_mode", "availability", "data_type")) or payload.get("is_demo") is True

    def project(self, project_id, payload, source_ref, organization="", scope="PUBLIC"):
        if project_id in self.projects:
            return
        key = block_key(payload)
        row = {
            "local_project_id": project_id, "project_name": clean(payload.get("name")),
            "project_unit": "BLOCK" if key else "AREA_UNKNOWN",
            "parent_area_name": district_name(payload),
            "block_name": clean(payload.get("block")),
            "region": clean(payload.get("region")), "sigungu": clean(payload.get("municipality")),
            "organization": clean(payload.get("developer") or payload.get("agency") or organization),
            "public_scope": scope, "project_status": clean(payload.get("stage_label") or payload.get("source_stage")),
            "is_demo": "false", "source_ref": source_ref,
        }
        self.projects[project_id] = row
        self.add("사업_projects.csv", **row)

    def identifier(self, project_id, id_type, value, issuer, source_ref, status="CONFIRMED"):
        value = clean(value)
        if value:
            self.add("사업식별자_identifiers.csv", local_project_id=project_id, id_type=id_type,
                     id_value=value, id_issuer=issuer, source_ref=source_ref, match_status=status)

    def event(self, project_id, event_type, date_type, date_value, detail, source_ref, status="CONFIRMED", progress=""):
        date_value = clean(date_value)
        exact = day(date_value)
        monthly = month(date_value) if not exact else ""
        if date_value and not (exact or monthly):
            self.flag("event", project_id, "", "", "INVALID_DATE", date_value, "원천 날짜 형식 확인")
            return
        event_key = (project_id, event_type, date_type, exact, monthly, str(progress))
        if event_key in self.event_keys:
            self.excluded["DUPLICATE_BLOCK_EVENT:events"] += 1
            return
        self.event_keys.add(event_key)
        self.add("진행이력_events.csv", local_project_id=project_id, event_type=event_type,
                 date_type=date_type, event_date=exact, event_month=monthly, progress_pct=progress,
                 event_detail=clean(detail), source_ref=source_ref, review_status=status)

    def unit(self, project_id, quantity_type, value, housing_type, reference_period, scope, source_ref, status="CONFIRMED"):
        number = as_int(value)
        if number is None or number == 0:
            return
        self.add("공급물량_units.csv", local_project_id=project_id, quantity_type=quantity_type,
                 housing_type=clean(housing_type), unit_count=str(number),
                 reference_period=period(reference_period), unit_scope=scope,
                 source_ref=source_ref, review_status=status)

    def policies(self):
        for record in self.revisions("policy"):
            if self.demo(record):
                self.excluded["DEMO:policy"] += 1
                continue
            data = record["payload"]
            ref = self.source(record)
            self.add("정책_policies.csv", local_policy_id=data.get("id", ""), policy_name=data.get("name", ""),
                     announcement_date=day(data.get("announced_at")), scope_region=data.get("target_scope", ""),
                     source_ref=ref, review_status="REVIEW_REQUIRED" if data.get("lifecycle_status") != "CONFIRMED" else "CONFIRMED")
            self.included["policy"] += 1

    def core_projects(self):
        all_rows = sorted(self.revisions("project"), key=lambda r: (r["source_id"], r["entity_id"]))
        if self.sample:
            eligible = [r for r in all_rows if not self.demo(r)
                        and "MULTI_SITE_CONTRACT" not in r["payload"].get("warnings", [])
                        and not (r["source_id"] == "sh_inventory" and r["payload"].get("program") != "토지임대부")]
            by_source = defaultdict(list)
            for record in eligible:
                by_source[record["source_id"]].append(record)
            chosen = [rows[0] for _, rows in sorted(by_source.items())]
            all_rows = chosen[:self.sample] + [r for r in eligible if r not in chosen][:max(0, self.sample - len(chosen))]
        self.core_ids = set()
        self.block_index = defaultdict(list)
        self.sh_landlease = {}
        for record in all_rows:
            data = record["payload"]
            key = record["entity_id"]
            if self.demo(record):
                self.excluded["DEMO:project"] += 1
                continue
            if record["source_id"] == "sh_inventory" and data.get("program") != "토지임대부":
                self.excluded["PUBLIC_PART_UNVERIFIED:project"] += 1
                self.flag("project", key, record["source_id"], key, "PUBLIC_PART_UNVERIFIED", data.get("name"), "공공주택 부분 검증")
                continue
            if "MULTI_SITE_CONTRACT" in data.get("warnings", []):
                self.excluded["MULTI_SITE_CONTRACT:project"] += 1
                self.flag("project", key, record["source_id"], key, "MULTI_SITE_CONTRACT", data.get("name"), "현장별 사업 범위 확인")
                continue
            ref = self.source(record)
            scope = "PUBLIC"
            self.project(key, data, ref, scope=scope)
            self.core_ids.add(key)
            self.included["project"] += 1
            if malformed_district(data):
                self.projects[key]["project_unit"] = "AREA_UNKNOWN"
                self.rows["사업_projects.csv"][-1]["project_unit"] = "AREA_UNKNOWN"
                self.flag("project", key, record["source_id"], key, "MALFORMED_DISTRICT_LABEL", data.get("district"), "지구명 원문 검증")
            self.identifier(key, "HOME_ENTITY_ID", key, "HOME", ref)
            self.identifier(key, "SOURCE_OBJECT_ID", data.get("source_object_id"), clean(self.registry.get(record["source_id"], {}).get("org")), ref)
            if block_key(data):
                self.block_index[block_key(data)].append(key)
                self.identifier(key, "DISTRICT_BLOCK", f"{district_name(data)}|{data['block']}", "HOME 원천", ref,
                                "REVIEW_REQUIRED" if malformed_district(data) else "CONFIRMED")
            if record["source_id"] == "sh_inventory" and data.get("program") == "토지임대부":
                self.sh_landlease[(data.get("region"), data.get("name"))] = key
            warnings = set(data.get("warnings", []))
            if warnings & BAD_UNIT_WARNINGS:
                self.excluded["CONFLICT_OR_UNALLOCATED:units"] += 1
                self.flag("unit", key, record["source_id"], key, ",".join(sorted(warnings & BAD_UNIT_WARNINGS)), data.get("unit_basis"), "물량 범위 확인")
            elif record["source_id"] == "sh_inventory" and data.get("program") == "토지임대부":
                pass  # Latest SH subtype rows below replace the HOME aggregate.
            elif data.get("supply_units") is not None:
                self.unit(key, "SUPPLY_PLAN", data.get("supply_units"), data.get("tenure"), data.get("base_date"), "SUBTYPE", ref, "REVIEW_REQUIRED")
            elif data.get("planned_units") is not None:
                self.unit(key, "PROJECT_PLAN", data.get("planned_units"), data.get("tenure"), data.get("base_date"), "PROJECT_TOTAL", ref,
                          "REVIEW_REQUIRED" if scope == "" or malformed_district(data) else "CONFIRMED")
            for field, typ, date_type, detail in (
                ("start_actual_date", "CONSTRUCTION_START", "ACTUAL", "원천 착공일"),
                ("start_plan_date", "CONSTRUCTION_START", "PLANNED", "원천 착공예정일"),
                ("completion_plan_date", "COMPLETION", "PLANNED", "공사 준공예정일; 입주일 아님"),
            ):
                if data.get(field):
                    self.event(key, typ, date_type, data[field], detail, ref)
            if data.get("progress_pct") is not None:
                self.event(key, "CONSTRUCTION_PROGRESS", "ACTUAL", "", "원천 공정률; 측정일 미제공 시 source_ref의 기준일 확인", ref,
                           progress=str(data["progress_pct"]))
            if data.get("schedule_month") and not data.get("completion_plan_date"):
                basis = clean(data.get("schedule_basis"))
                kind = "SUPPLY" if record["source_id"] in {"lh_sale", "lh_rent", "sh_inventory"} else "BUSINESS"
                self.event(key, kind, "PLANNED", data["schedule_month"], basis or "원천 예정월", ref, "REVIEW_REQUIRED")

    def external_lh(self):
        new_blocks = {}
        for kind in ("lh_supply", "lh_movein_plan", "lh_completion_plan"):
            for record in sorted(self.revisions(kind), key=lambda r: r["entity_id"]):
                data = record["payload"]
                if self.demo(record):
                    self.excluded[f"DEMO:{kind}"] += 1
                    continue
                key = block_key(data)
                if key is None:
                    self.excluded[f"NO_BLOCK:{kind}"] += 1
                    self.flag(kind, "", record["source_id"], record["entity_id"], "NO_BLOCK", data.get("name"), "사업 단위 확인")
                    continue
                core = self.block_index.get(key, [])
                if len(core) > 1:
                    self.excluded[f"MULTIPLE_BLOCK_MATCH:{kind}"] += 1
                    self.flag(kind, "", record["source_id"], record["entity_id"], "MULTIPLE_BLOCK_MATCH", data.get("name"), "동일 블록 사업 검토")
                    continue
                if self.sample and not core:
                    continue
                ref = self.source(record)
                if core:
                    project_id = core[0]
                    status = "REVIEW_REQUIRED"
                    self.flag(kind, project_id, record["source_id"], record["entity_id"], "BLOCK_MATCH_REVIEW", data.get("name"), "지구·블록 동일성 확인")
                else:
                    project_id = new_blocks.setdefault(key, stable_id("HOME-LH-BLOCK-", "|".join(key)))
                    status = "CONFIRMED"
                    if project_id not in self.projects:
                        project_data = dict(data, name=f"{data.get('district') or data.get('district_name')} {data.get('block')}",
                                            district=data.get("district") or data.get("district_name"), municipality=data.get("municipality"))
                        self.project(project_id, project_data, ref, organization="LH")
                        self.included["lh_block_project"] += 1
                self.identifier(project_id, "HOME_ENTITY_ID", record["entity_id"], "HOME", ref, status)
                self.identifier(project_id, "SOURCE_OBJECT_ID", data.get("source_object_id"), "LH", ref, status)
                self.identifier(project_id, "DISTRICT_BLOCK", f"{data.get('district') or data.get('district_name')}|{data.get('block')}", "LH", ref, status)
                self.included[kind] += 1
                if kind == "lh_supply":
                    self.unit(project_id, "NOTICE", data.get("units"), data.get("housing_type"), data.get("source_date"), "SUBTYPE", ref, status)
                    self.event(project_id, "SUPPLY_NOTICE", "ACTUAL", data.get("source_date"), "LH 공공분양 모집공고일; 입주실적 아님", ref, status)
                    if data.get("move_in_plan_month"):
                        self.event(project_id, "MOVE_IN", "PLANNED", data.get("move_in_plan_month"), "원천 최초입주시기; 예정 포함, 실제 입주 아님", ref, "REVIEW_REQUIRED")
                elif kind == "lh_movein_plan":
                    self.event(project_id, "MOVE_IN", "PLANNED", data.get("move_in_plan_month") or data.get("schedule_month"), "LH 공개본 입주예정월; 실제 입주 아님", ref, status)
                    if as_int(data.get("units")):
                        self.excluded["UNSUPPORTED_MOVE_IN_PLAN_QUANTITY:units"] += 1
                elif kind == "lh_completion_plan":
                    self.event(project_id, "COMPLETION", "PLANNED", data.get("completion_plan_date"), "LH 블록 준공예정일; 실제 준공·입주 아님", ref, status)
                    if as_int(data.get("units")):
                        self.excluded["UNSUPPORTED_COMPLETION_PLAN_QUANTITY:units"] += 1

    def sh_subtypes(self):
        for record in self.revisions("sh_plan"):
            data = record["payload"]
            if self.demo(record):
                self.excluded["DEMO:sh_plan"] += 1
                continue
            if not data.get("is_latest_dataset"):
                self.excluded["OLD_SH_DATASET:sh_plan"] += 1
                continue
            key = (data.get("region"), data.get("name"))
            project_id = self.sh_landlease.get(key)
            if not project_id:
                self.excluded["UNLINKED_SH_PLAN:sh_plan"] += 1
                self.flag("sh_plan", "", record["source_id"], record["entity_id"], "UNLINKED_SH_PLAN", data.get("name"), "사업 연결 확인")
                continue
            ref = self.source(record)
            self.identifier(project_id, "HOME_ENTITY_ID", record["entity_id"], "HOME", ref)
            self.identifier(project_id, "SOURCE_OBJECT_ID", data.get("source_object_id"), "SH", ref)
            housing_type = str(data.get("housing_type") or "") + "㎡" if data.get("housing_type") else ""
            self.unit(project_id, "SUPPLY_PLAN", data.get("units"), housing_type, data.get("dataset_version"), "SUBTYPE", ref)
            self.included["sh_plan_subtype"] += 1

    def links(self):
        policy_ids = {r["local_policy_id"] for r in self.rows["정책_policies.csv"]}
        program_rows = sorted(load_rows(self.root / "program_policy_links.json.gz"), key=lambda r: r["id"])
        for row in program_rows:
            if row.get("status") == "RELEASED":
                self.excluded["RELEASED:program_policy"] += 1
                continue
            ref = self.mapping_source("program_policy_links", row)
            self.add("프로그램_programs.csv", local_program_id=row["id"], program_name=row["name"],
                     program_definition="", source_ref=ref,
                     review_status="CONFIRMED" if row.get("status") == "CONFIRMED" else "REVIEW_REQUIRED")
            policy_id = row.get("policy_id")
            if policy_id in policy_ids:
                self.add("정책사업연결_links.csv", link_type="POLICY_PROGRAM", from_local_id=policy_id,
                         to_local_id=row["id"], evidence=clean(row.get("basis")),
                         review_status="CONFIRMED" if row.get("status") == "CONFIRMED" else "REVIEW_REQUIRED", source_ref=ref)
            elif policy_id not in (None, "", "UNASSIGNED"):
                self.flag("program_policy_link", "", "HOME", row["id"], "MISSING_POLICY", policy_id, "정책 원천 확인")
        program_ids = {r["local_program_id"] for r in self.rows["프로그램_programs.csv"]}
        for row in sorted(load_rows(self.root / "project_program_links.json.gz"), key=lambda r: r["project_id"]):
            if row.get("status") == "RELEASED":
                self.excluded["RELEASED:project_program"] += 1
                continue
            if row.get("project_id") not in self.projects:
                self.excluded["EXCLUDED_PROJECT:project_program"] += 1
                continue
            if row.get("program_id") not in program_ids:
                self.flag("project_program_link", row.get("project_id"), "HOME", row["id"], "MISSING_PROGRAM", row.get("program_id"), "프로그램 원천 확인")
                continue
            ref = self.mapping_source("project_program_links", row)
            self.add("정책사업연결_links.csv", link_type="PROGRAM_PROJECT", from_local_id=row["program_id"],
                     to_local_id=row["project_id"], evidence=clean(row.get("basis")),
                     review_status="CONFIRMED" if row.get("status") == "CONFIRMED" else "REVIEW_REQUIRED", source_ref=ref)

    def audits(self):
        for row in load_rows(self.root / "identity_aliases.json.gz"):
            if row.get("match_rule") == "SOURCE_ANCHOR" and row.get("source_entity_id") in self.projects:
                ref = self.mapping_source("identity_aliases", row)
                self.identifier(row["source_entity_id"], "HOME_PROJECT_ID", row.get("project_id"), "HOME", ref, "REVIEW_REQUIRED")
            elif row.get("match_rule") != "SOURCE_ANCHOR" and row.get("relation_status") != "CONFIRMED":
                self.flag("identity_alias", "", row.get("source_id"), row.get("source_entity_id"),
                          "IDENTITY_ALIAS_REVIEW", row.get("basis"), "동일 사업 근거 검증")
        for kind in ("sh_project", "renewal_inventory", "notice", "lh_notice", "gh_notice", "permit", "register", "agency_stock", "lh_stock", "project_report", "plan_notice"):
            count = self.manifest.get("kind_counts", {}).get(kind, {}).get("current", 0)
            if kind == "sh_project":
                self.excluded["SH_PUBLIC_PART_REVIEW:sh_project"] = count
                for row in self.revisions(kind):
                    data = row["payload"]
                    self.flag(kind, "", row["source_id"], row["entity_id"], "SH_PUBLIC_PART_REVIEW", data.get("name"), "공공임대 부분과 HOME 사업 연결 검증")
            elif kind == "notice":
                self.excluded["PUBLIC_SCOPE_OR_LINK_UNVERIFIED:notice"] = count
                for row in self.revisions(kind):
                    name = row["payload"].get("name", "")
                    if any(word in name for word in ("공공분양", "공공임대", "행복주택", "국민임대")):
                        self.flag(kind, "", row["source_id"], row["entity_id"], "PUBLIC_NOTICE_MATCH_REVIEW", name, "공공 부분과 사업 연결 확인")
            else:
                self.excluded[f"NO_CONFIRMED_PUBLIC_PROJECT_LINK:{kind}"] = count

    def run(self):
        self.policies()
        self.core_projects()
        self.external_lh()
        self.sh_subtypes()
        self.links()
        if not self.sample:
            self.audits()
        self.rows["원천_sources.csv"] = list(self.sources.values())
        self.validate()

    def validate(self):
        problems = []
        source_ids = set(self.sources)
        project_ids = [r["local_project_id"] for r in self.rows["사업_projects.csv"]]
        policy_ids = {r["local_policy_id"] for r in self.rows["정책_policies.csv"]}
        program_ids = {r["local_program_id"] for r in self.rows["프로그램_programs.csv"]}
        if len(project_ids) != len(set(project_ids)):
            problems.append("Duplicate local_project_id")
        if len(policy_ids) != len(self.rows["정책_policies.csv"]):
            problems.append("Duplicate local_policy_id")
        if len(program_ids) != len(self.rows["프로그램_programs.csv"]):
            problems.append("Duplicate local_program_id")
        for filename, rows in self.rows.items():
            if any(set(r) != set(self.headers[filename]) for r in rows):
                problems.append(f"Header mismatch: {filename}")
            for n, row in enumerate(rows, 1):
                if filename != "원천_sources.csv" and row.get("source_ref") not in source_ids:
                    problems.append(f"Missing source_ref: {filename}:{n}")
                for field in ("announcement_date", "event_date", "data_as_of", "collected_at"):
                    if field in row and row[field] and not day(row[field]):
                        problems.append(f"Invalid date: {filename}:{n}:{field}")
                for field in ("event_month", "reference_period"):
                    if field in row and row[field] and not period(row[field]):
                        problems.append(f"Invalid period: {filename}:{n}:{field}")
                if filename in {"사업식별자_identifiers.csv", "진행이력_events.csv", "공급물량_units.csv"} and row["local_project_id"] not in project_ids:
                    problems.append(f"Missing project FK: {filename}:{n}")
                if filename == "공급물량_units.csv" and as_int(row["unit_count"]) is None:
                    problems.append(f"Invalid unit_count: {n}")
                if filename == "진행이력_events.csv" and row["progress_pct"]:
                    try:
                        pct = float(row["progress_pct"])
                        if not 0 <= pct <= 100:
                            raise ValueError
                    except ValueError:
                        problems.append(f"Invalid progress_pct: {n}")
                if filename == "정책사업연결_links.csv":
                    if row["link_type"] == "POLICY_PROGRAM" and not (row["from_local_id"] in policy_ids and row["to_local_id"] in program_ids):
                        problems.append(f"Invalid policy-program FK: {n}")
                    if row["link_type"] == "PROGRAM_PROJECT" and not (row["from_local_id"] in program_ids and row["to_local_id"] in project_ids):
                        problems.append(f"Invalid program-project FK: {n}")
                if any("[REDACTED]" in str(v) or re.search(r"(?:servicekey|api_key|access_token)=", str(v), re.I) for v in row.values()):
                    problems.append(f"Potential secret in {filename}:{n}")
        if problems:
            raise ValueError("Validation failed:\n" + "\n".join(problems[:50]))
        return {name: len(rows) for name, rows in self.rows.items()}

    def write(self, output: Path):
        output.mkdir(parents=True, exist_ok=True)
        for filename in FILES:
            with (output / filename).open("w", encoding="utf-8-sig", newline="") as stream:
                writer = csv.DictWriter(stream, self.headers[filename], lineterminator="\r\n")
                writer.writeheader()
                writer.writerows(sorted(self.rows[filename], key=lambda r: tuple(str(r[k]) for k in self.headers[filename])))
        with (output / "review_required.csv").open("w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.DictWriter(stream, REVIEW_COLUMNS, lineterminator="\r\n")
            writer.writeheader()
            writer.writerows(sorted(self.review, key=lambda r: tuple(str(r[k]) for k in REVIEW_COLUMNS)))
        counts = self.validate()
        report = ["# HOME → 주택파동 공통규격 v1.4 변환 보고서", "",
                  f"입력: `{self.root}`", f"스냅샷: `{self.manifest['snapshot_at']}`", "",
                  "## 파일별 레코드 건수", "", "| 파일 | 행 수 |", "|---|---:|"]
        report += [f"| {name} | {counts[name]:,} |" for name in FILES]
        report += [f"| review_required.csv | {len(self.review):,} |", "", "## 변환 원천 건수", "", "| 원천 유형 | 변환 행 |", "|---|---:|"]
        report += [f"| {key} | {value:,} |" for key, value in sorted(self.included.items())]
        report += ["", "## 원천 ID별 현재 판본과 사용 행", "", "사용 행은 해당 원천 revision 또는 HOME 연결 행을 한 번 이상 출력에 인용한 수다.", "", "| source_id | 현재 판본 | 사용 행 |", "|---|---:|---:|"]
        for source_id in sorted(self.registry):
            current = self.manifest.get("source_counts", {}).get(source_id, {}).get("current", 0)
            report.append(f"| {source_id} | {current:,} | {self.used_source_counts[source_id]:,} |")
        for source_id in ("HOME:program_policy_links", "HOME:project_program_links", "HOME:identity_aliases"):
            report.append(f"| {source_id} | — | {self.used_source_counts[source_id]:,} |")
        as_of_count = sum(bool(row["data_as_of"]) for row in self.sources.values())
        collected_count = sum(bool(row["collected_at"]) for row in self.sources.values())
        report += ["", f"원천 기준일 확보: {as_of_count:,}/{len(self.sources):,}행; 실제 수집 배치일 확보: {collected_count:,}/{len(self.sources):,}행.",
                   "HOME 내부 연결·식별자 매핑 행에는 원천 수집 배치가 없어 collected_at을 공란으로 둔다. 공고일·입주예정월도 별도 자료 기준일로 오인하지 않는다.",
                   "", "## 제외·보류 건수", "", "원천 행과 물량 행의 기준이 섞여 있으므로 서로 더하지 않는다.", "", "| 사유:유형 | 건수 |", "|---|---:|"]
        report += [f"| {key} | {value:,} |" for key, value in sorted(self.excluded.items())]
        report += ["", "## 검토 필요 사유", "", "| 사유 | 항목 수 |", "|---|---:|"]
        report += [f"| {reason} | {count:,} |" for reason, count in sorted(Counter(row["reason"] for row in self.review).items())]
        report += ["", "## 검증", "", "CSV 8종의 헤더·UTF-8 BOM, 날짜·숫자 형식, 로컬 ID 중복, 모든 source_ref 및 정책·프로그램·사업 참조 무결성 통과.",
                   "DEMO 표기 행은 제출 파일에서 제외; 이번 스냅샷에서 해당 행 0건. 공공 여부·사업 동일성이 불확실한 자료는 검토 대장에 기록.",
                   "준공예정·입주예정 호수는 v1.4 물량 유형에 없으므로 물량 CSV에 강제로 넣지 않았다. 실제 입주 호수는 미확보.",
                   "정책·프로그램 링크는 HOME의 원천 상태대로 REVIEW_REQUIRED이며 공식 정책 귀속 확정으로 해석하면 안 된다.",
                   "주택인허가·건축물대장·재고·일반 민간 분양은 공공주택 사업의 확정 연결이 없어 사업·물량으로 전환하지 않았다.",
                   "", "## 오류", "", "형식·참조 검증 오류 0건. 의미 검토 필요 항목은 review_required.csv 참조.", ""]
        (output / "conversion_report.md").write_text("\n".join(report), encoding="utf-8")
        readme = f"""# HOME 주택파동 공통규격 v1.4 제출본

입력은 HOME 운영 DB의 읽기 전용 공유 스냅샷 `{self.root.name}`이다. DB·API·화면을 변경하거나 외부에서 재수집하지 않는다. CSV 8종의 헤더는 `docs/common_form` 원본을 읽어 쓴다.

## 재생성

`PoC/10-home`에서 실행:

```bash
python exports/housing_wave_common_v1_4/program/convert.py --input data/exports/home-20261010-live-v3 --output exports/housing_wave_common_v1_4
python exports/housing_wave_common_v1_4/program/validate.py exports/housing_wave_common_v1_4
```

같은 입력으로 다시 실행하면 같은 CSV·보고서가 생성된다. `--sample 8 --output /tmp/home-common-sample`은 실제 사업 8건의 시험 변환이다.

`review_required.csv`는 공통규격 8종에 포함되지 않는 검토 대장이다. `HOME-LH-BLOCK-*`는 HOME 내부 임시 블록 ID이며 팀 최종 통합 ID가 아니다. `TEST_SAMPLE`은 공식 자료의 부분 수집이고 DEMO가 아니다. 물량 유형 간 단순 합산은 금지한다. 공공 여부·지구/블록 일치가 검토 중인 행은 `REVIEW_REQUIRED`로 표시했다.
"""
        (output / "README.md").write_text(readme, encoding="utf-8")
        mapping = FORM / "HOME_v1_4_1단계_분석_매핑안.md"
        (output / "field_mapping.md").write_text(mapping.read_text(encoding="utf-8") + "\n## 실행 매핑 보충\n\n사용자가 ZIP을 압축 해제해 `docs/common_form`에 배치한 README와 CSV 8종을 기준으로 삼았다. HOME `project`를 기본 사업 목록으로 사용하고, LH의 명시적 지구·블록은 사업당 한 행으로 묶었다. HOME 기존 블록과 정확히 겹치는 LH 원천은 `REVIEW_REQUIRED`로 표시했다. SH 토지임대부 최신 주택형별 계획 물량 4행은 HOME 집계 물량을 대체하며 중복 기록하지 않았다. SH 정비사업 16건은 공공주택 부분 미확인으로 사업 CSV에서 제외하고 검토 대장에 남겼다. HOME `HPR_` 후보 ID는 확정 사업번호로 승격하지 않고 `HOME_PROJECT_ID` 식별자로 `REVIEW_REQUIRED` 상태로 보존했다.\n", encoding="utf-8")
        program = output / "program"
        program.mkdir(exist_ok=True)
        for name in ("convert.py", "validate.py"):
            (program / name).write_bytes((Path(__file__).resolve().parent / name).read_bytes())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--sample", type=int, choices=range(5, 11), metavar="5-10")
    args = parser.parse_args()
    converter = Converter(args.input.resolve(), args.sample)
    converter.run()
    converter.write(args.output.resolve())
    print(json.dumps({"counts": converter.validate(), "review_required": len(converter.review), "output": str(args.output.resolve())}, ensure_ascii=False))


if __name__ == "__main__":
    main()
