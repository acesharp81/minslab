"""SH official file-converted APIs; versioned plans never imply delivery actuals."""
import hashlib
import json
import re
from datetime import date

from .api_samples import base, day, key_for, response_json, today
from .collectors import clean, integer

METADATA_URL = "https://infuser.odcloud.kr/oas/docs"
PAGE_SIZE = 100


def versions(data, dataset_id):
    if data.get("host") != "api.odcloud.kr" or data.get("basePath") != "/api" or not isinstance(data.get("paths"), dict):
        raise ValueError("SH Open API 메타데이터 schema 변경")
    result = []
    for path, definition in data["paths"].items():
        if not re.fullmatch(r"/" + dataset_id + r"/v1/uddi:[a-zA-Z0-9_-]+", path):
            raise ValueError("SH Open API 경로 변경")
        match = re.search(r"_(\d{8})$", definition.get("get", {}).get("summary", ""))
        published = day(match[1]) if match else None
        if not published:
            raise ValueError("SH 공개본 기준일 미확인")
        if published <= today().isoformat():
            result.append((published, path))
    if not result or len({d for d, _ in result}) != len(result):
        raise ValueError("SH 공개본 기준일 누락·중복")
    return sorted(result)


def scheduled_month(row):
    if "공급시기 예정 년도" in row:
        year, month = integer(row.get("공급시기 예정 년도")), integer(row.get("공급시기 예정월"))
        if year is None and month is None:
            return None
        if year is None or month is None or not 1900 <= year <= 2100 or not 1 <= month <= 12:
            raise ValueError("SH 공급 예정 연월 형식 변경")
        return f"{year:04d}-{month:02d}"
    value = clean(row.get("공급시기(예정)") or row.get("분양예정시기"))
    if not value:
        return None
    match = re.fullmatch(r"(20\d{2})[-./](\d{1,2})", value)
    if not match or not 1 <= int(match[2]) <= 12:
        raise ValueError("SH 공급 예정 연월 형식 변경")
    return f"{match[1]}-{int(match[2]):02d}"


def parse_rows(rows, source, version, latest):
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise ValueError("SH 행 schema 변경")
    records, seen = [], set()
    plan = source["id"] == "sh_supply_plan"
    for row in rows:
        name = clean(row.get("단지명" if plan else "구역명"))
        total_field = ("합계" if "합계" in row else "계") if plan else "전체 세대수"
        if not name or total_field not in row:
            raise ValueError("SH 사업명·계획 세대수 컬럼 누락")
        district = clean(row.get("지구" if plan else "자치구"))
        business = clean(row.get("사업유형" if plan else "구분"))
        housing_type = row.get("주택형") if plan else None
        identity = json.dumps([version, district, name, business, housing_type], ensure_ascii=False, separators=(",", ":"))
        identifier = hashlib.sha256(identity.encode()).hexdigest()
        if identifier in seen:
            raise ValueError("SH 공개본 내 사업·주택형 중복")
        seen.add(identifier)
        if plan and district:
            name = district + " " + name
        address = "" if plan else "서울특별시 " + clean(row.get("위치"))
        kind = "sh_plan" if plan else "sh_project"
        payload = base(source, kind, name, "서울특별시", address, version)
        payload.update(source_object_id=identifier, dataset_version=version, latest_dataset_version=latest,
                       is_latest_dataset=version == latest, source_date_label="공개본 자료 기준일",
                       business_type=business, units=integer(row.get(total_field)), native_fields=row,
                       unit_basis="해당 공개본의 계획 세대수 · 공급 실적 아님 · 공개본 간 합산 금지",
                       warnings=["SH_PLAN_NOT_ACTUAL"], stage_label="SH 계획·과거 현황 · 정책 연결 검토 전")
        if version != latest:
            payload["warnings"].append("SH_HISTORY_SNAPSHOT")
        if plan:
            payload.update(schedule_month=scheduled_month(row), housing_type=housing_type,
                           pre_subscription_units=integer(row.get("사전청약 공급세대수")),
                           main_subscription_units=integer(row.get("본청약 공급세대수")))
            if payload["schedule_month"]:
                payload["warnings"].append("SH_SCHEDULE_NOT_ACTUAL")
            pre, main = payload["pre_subscription_units"], payload["main_subscription_units"]
            if pre is not None and main is not None and payload["units"] != pre + main:
                raise ValueError("SH 사전·본청약 합계 불일치")
        else:
            if not district or not clean(row.get("위치")) or "추진현황" not in row or "임대 세대수" not in row:
                raise ValueError("SH 사업 위치·현황 컬럼 누락")
            payload.update(municipality=district, rental_units=integer(row.get("임대 세대수")), source_stage=clean(row.get("추진현황")))
            if payload["rental_units"] is not None and payload["units"] is not None and payload["rental_units"] > payload["units"]:
                raise ValueError("SH 임대 세대수가 전체 세대수 초과")
            if (today() - date.fromisoformat(version)).days > 365:
                payload["warnings"].append("SH_OLD_STATUS")
        records.append((kind, identifier, payload))
    return records


def collect_sh(source, fetcher):
    metadata = response_json(fetcher.get(METADATA_URL, "json", params={"namespace": source["dataset_id"] + "/v1"}))
    published = versions(metadata, source["dataset_id"])
    latest = published[-1][0]
    records, counts = [], []
    for version, path in published:
        parsed, expected, seen, page = [], None, set(), 1
        while True:
            data = response_json(fetcher.get("https://api.odcloud.kr/api" + path, "json", params={
                "serviceKey": key_for(source), "page": page, "perPage": PAGE_SIZE, "returnType": "JSON"}))
            total = data.get("totalCount")
            if type(total) is not int or not 0 <= total <= 10000 or data.get("page") != page or data.get("perPage") != PAGE_SIZE:
                raise ValueError("SH 인증·페이지 schema 확인 필요")
            current = parse_rows(data.get("data"), source, version, latest)
            if expected is None:
                expected = total
            if total != expected or len(current) != min(PAGE_SIZE, max(0, total - len(parsed))) or data.get("currentCount") != len(current):
                raise ValueError("SH 페이지 누락·수집 중 건수 변경")
            for record in current:
                if record[1] in seen:
                    raise ValueError("SH 페이지 간 중복")
                seen.add(record[1])
            parsed.extend(current)
            if len(parsed) >= total:
                break
            page += 1
        records.extend(parsed)
        counts.append(dict(version=version, records=len(parsed), pages=page, complete_query=True, is_latest=version == latest))
    if not records:
        raise ValueError("SH 자료 없음: 기존 데이터 유지")
    return records, dict(collection_mode="TEST_SAMPLE", complete_population=False, dataset_id=source["dataset_id"],
                         dataset_versions=counts, latest_dataset_version=latest,
                         latest_record_count=counts[-1]["records"], period_start=published[0][0], period_end=latest,
                         scope_note="SH 공개본별 전체 조회 페이지. 계획·과거 추진현황이며 현재 공급 실적 미확인. 공개본 간 물량 합산 금지")
