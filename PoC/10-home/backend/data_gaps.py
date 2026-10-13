"""Evidence-based availability audit. A missing value is never interpreted as zero."""

from collections import Counter, defaultdict
from datetime import date

from sqlalchemy import select

from .db import Revision


# A target period is an audit window, not a claim that the publisher has issued
# every annual file. The observed years below always come from saved revisions.
SERIES = (
    ("molit_statistics", "준공 · 지역 전체", "준공", "REGIONAL_TOTAL"),
    ("molit_demolition", "멸실 · 지역 전체", "멸실", "REGIONAL_TOTAL"),
    ("molit_statistics", "착공 · 지역 전체", "착공", "REGIONAL_TOTAL"),
    ("molit_statistics", "인허가 · 지역 전체", "인허가", "REGIONAL_TOTAL"),
    ("lh_supply_history", "LH 공공분양 공고 호수", None, "AGENCY_PARTIAL"),
    ("lh_movein_history", "LH 입주 예정 호수", None, "PLAN_ONLY"),
    ("lh_progress", "LH 블록별 실제 공정 이력", None, "PROJECT_PARTIAL"),
    ("kosis_housing", "주택 재고 · 시도", "housing_units_province", "PROVINCIAL_SERIES"),
    ("kosis_housing", "주택 재고 · 시군구", "housing_units", "MUNICIPAL_PARTIAL"),
    ("kosis_housing", "주택총조사 주택수 · 시군구", "census_housing_units", "MUNICIPAL_CENSUS"),
    ("kosis_household_size", "가구원수별 가구 · 시군구", None, "MUNICIPAL_PARTIAL"),
    ("sgis_area", "인구·가구·종사자 · 시군구", None, "MUNICIPAL_PARTIAL"),
    ("kosis_employment", "고용·취업 · 시군구", None, "MUNICIPAL_PARTIAL"),
)

NEXT_ACTION = {
    "molit_statistics": "누락 연도 통계표·발표 주기를 원천에서 확인; 지역 총계를 개별 사업 실적으로 배분하지 않음",
    "molit_demolition": "2025년 이후 공식 공표 여부 확인; 시군구·사업별 멸실량으로 임의 배분하지 않음",
    "lh_supply_history": "2018~2019 원본 공개본 탐색 및 공고 정정·중복 확인",
    "lh_movein_history": "2018~2021 입주계획 원본 탐색; 실제 입주와 별도 보관",
    "lh_progress": "공개 이력 밖 블록·연도 원천 확보 및 사업 식별자 검토",
    "kosis_housing": "시군구별 과거 주택 재고 표·발표 가능 연도 확인",
    "kosis_household_size": "원천 발표 연도와 시군구 행 수 확인",
    "sgis_area": "발표 지연·지역 누락 여부를 SGIS 원천에서 확인",
    "kosis_employment": "반기 고용 통계의 발표 연도·지역 누락 확인",
    "kosis_household_forecast": "시도 단위 2026~2036 전망; 시군구 추계와 실제 가구 수를 혼동하지 않음",
}

UNSTARTED = (
    ("municipal_forecast", "시군구 장래가구 추계", "서울 25구/경기 31시군", "https://kosis.kr/openapi/devGuide/devGuide_0201List.do", "공식 시군구 추계 표·공표 범위 확인; 현 시도 추계를 시군구로 임의 배분하지 않음"),
    ("actual_move_in_start", "사업별 실제 입주 시작일", "정책/프로그램/블록", None, "기관별 실제 입주 시작일 원본과 단지 식별자 확보; 예정월과 실제 시작일을 구분"),
    ("sh_gh_progress", "SH·GH 블록별 실제 공정 이력", "서울/경기 블록", None, "공개 공정자료 또는 기관 확인 자료의 기준월·블록 식별자 확보"),
    ("legal_plan_chain", "전체 계획 고시 변경 이력", "서울/경기 전체 사업", None, "최초 지정~변경 고시 목록·원문을 수집하고 사업 연결 검토"),
)


def project_data_status(row):
    """Describe what the project evidence says without inferring non-start."""
    stage = row.get("stage")
    not_started_verified = row.get("not_started_verified") is True and bool(row.get("not_started_evidence_url"))
    move_in_start = row.get("move_in_start") or {}
    start_date = move_in_start.get("date") if isinstance(move_in_start, dict) else None
    completion_verified = bool(row.get("completion_actual_date") and row.get("completion_evidence_url"))
    if not_started_verified:
        phase = "원천 근거로 사업 미착수 확인"
    elif row.get("start_actual_date"):
        phase = "착공일 근거 있음"
    elif stage in {"PLANNING", "PLANNED_SUPPLY", "DESIGNATED", "CANDIDATE", "PROPOSED_DISTRICT", "APPROVAL"}:
        phase = "원천상 계획·지정 단계 · 실제 착공 여부 미확인"
    elif stage == "CONSTRUCTION":
        phase = "원천상 공사 단계 · 착공일은 별도 확인"
    else:
        phase = "현재 단계 원천 근거 미확보"
    return {
        "phase": phase,
        "not_started_verified": not_started_verified,
        "planned_units": "확보" if row.get("planned_units") is not None else "개별 물량 미확보",
        "progress": "실제 공정률 근거 있음" if row.get("progress_pct") is not None else "블록별 실제 공정률 미입수",
        "move_in_start": "입주 시작 예정월 확보" if start_date else "입주 시작일 미확보",
        "completion_date": "실제 준공일 근거 있음" if completion_verified else "실제 준공일 미입수",
        "schedule": "예정 일정 확보" if row.get("schedule_month") else "개별 일정 미정·미입수 구분 필요",
    }


def _year_for(source_id, source_date, payload_year):
    raw = payload_year if source_id in {"kosis_housing", "kosis_household_size", "sgis_area", "kosis_employment"} else source_date
    try:
        year = int(str(raw)[:4])
        return year if 2000 <= year <= 2100 else None
    except (TypeError, ValueError):
        return None


def _cell_status(count, source, source_id=None, source_year=None, other_region_count=0):
    if count:
        return "ACQUIRED"
    if not source or not source.get("last_attempt"):
        return "NOT_STARTED"
    if not source.get("last_success") and source.get("status") == "FAILED":
        return "FAILED"
    stats = source.get("stats") or {}
    if source_id == "molit_demolition" and stats.get("complete_query") is True and stats.get("latest_year") is not None and source_year > int(stats["latest_year"]):
        return "SOURCE_NOT_PUBLISHED"
    if source_id in {"lh_supply_history", "lh_movein_history"} and other_region_count and stats.get("complete_query") is True:
        first, last = stats.get("period_start"), stats.get("period_end")
        if first and last and int(str(first)[:4]) <= source_year <= int(str(last)[:4]):
            return "NO_SOURCE_RECORD"
    return "NOT_ACQUIRED"


def data_gap_audit(session, sources, projects, year=None):
    """Annual source evidence, collection scope and project-field gaps."""
    current_year = year or date.today().year
    years = list(range(2018, current_year + 1))
    source_map = {source["id"]: source for source in sources}
    tracked = {item[0] for item in SERIES} | {"kosis_household_forecast"}
    query = select(
        Revision.source_id, Revision.sample_region, Revision.sample_source_date,
        Revision.payload["year"].as_string(),
        Revision.payload["statistic_metric"].as_string(),
        Revision.payload["housing_units"].as_string(),
        Revision.payload["census_housing_units"].as_string(),
        Revision.payload["municipality"].as_string(),
    ).where(Revision.source_id.in_(tracked), Revision.superseded_at.is_(None))
    counts = Counter()
    for sid, region, source_date, payload_year, metric, housing, census_housing, municipality in session.execute(query):
        if region not in {"서울특별시", "경기도"}:
            continue
        source_year = _year_for(sid, source_date, payload_year)
        if sid == "kosis_household_forecast":
            try:
                forecast_year = int(str(payload_year)[:4])
                if 2026 <= forecast_year <= current_year + 10:
                    counts[(sid, None, region, forecast_year)] += 1
            except (TypeError, ValueError):
                pass
            continue
        if source_year is None:
            continue
        for series_sid, _, selector, _ in SERIES:
            if sid != series_sid:
                continue
            if sid in {"molit_statistics", "molit_demolition"} and metric != selector:
                continue
            if sid == "kosis_housing":
                if selector == "census_housing_units":
                    if census_housing is None or not municipality or municipality == region:
                        continue
                else:
                    if housing is None:
                        continue
                    if selector == "housing_units_province" and municipality and municipality != region:
                        continue
                    if selector == "housing_units" and (not municipality or municipality == region):
                        continue
            if sid in {"kosis_household_size", "sgis_area", "kosis_employment"} and (not municipality or municipality == region):
                continue
            counts[(sid, selector, region, source_year)] += 1

    rows = []
    for sid, label, selector, meaning in SERIES:
        source = source_map.get(sid)
        for region in ("서울특별시", "경기도"):
            observed = sorted(y for (s, sel, r, y), amount in counts.items()
                              if s == sid and sel == selector and r == region and amount)
            other_region = "경기도" if region == "서울특별시" else "서울특별시"
            cells = [{"year": y, "count": counts[(sid, selector, region, y)],
                      "status": _cell_status(counts[(sid, selector, region, y)], source, sid, y,
                                             counts[(sid, selector, other_region, y)])} for y in years]
            missing = [cell["year"] for cell in cells if cell["status"] != "ACQUIRED"]
            rows.append({"source_id": sid, "label": label, "region": region, "meaning": meaning,
                         "cells": cells, "observed_years": observed, "missing_years": missing,
                         "source_url": source.get("url") if source else None,
                         "last_attempt": source.get("last_attempt") if source else None,
                         "last_success": source.get("last_success") if source else None,
                         "collection_status": source.get("status") if source else None,
                         "next_action": ("시도 2018년 이후 관측 재고; 시군구 과거값으로 임의 분해하지 않음"
                                         if selector == "housing_units_province" else
                                         "총조사 주택_계는 다가구 보정 재고와 다른 기준; 수급 차이 계산에 대체 사용하지 않음"
                                         if selector == "census_housing_units" else NEXT_ACTION[sid])})

    forecast_source = source_map.get("kosis_household_forecast")
    forecast_years = list(range(current_year, current_year + 11))
    forecast_rows = []
    for region in ("서울특별시", "경기도"):
        forecast_rows.append({"region": region, "source_url": forecast_source.get("url") if forecast_source else None,
            "cells": [{"year": y, "count": counts[("kosis_household_forecast", None, region, y)],
                       "status": _cell_status(counts[("kosis_household_forecast", None, region, y)], forecast_source)}
                      for y in forecast_years]})

    scope = []
    for sid, label in (("building_hub", "주택인허가"), ("building_register", "주거용 건축물대장"),
                       ("building_hub_details", "인허가 동·필지 상세")):
        source = source_map.get(sid, {})
        stats = source.get("stats") or {}
        done = stats.get("scope_completed_dongs")
        total = stats.get("scope_total_dongs")
        scope.append({"source_id": sid, "label": label, "completed": done, "total": total,
                      "remaining": max(0, total - done) if isinstance(total, int) and isinstance(done, int) else None,
                      "status": "PARTIAL" if done is not None and total and done < total else
                                "ACQUIRED" if done is not None and total and done >= total else
                                _cell_status(0, source),
                      "last_attempt": source.get("last_attempt"), "last_success": source.get("last_success"),
                      "source_url": source.get("url"),
                      "next_action": "남은 법정동부터 재개 수집; 조회 완료 동도 개별 정책사업 연결은 미확정"})

    project_counts = Counter()
    for project in projects:
        status = project_data_status(project)
        project_counts["total"] += 1
        project_counts["planned_units_acquired"] += status["planned_units"] == "확보"
        project_counts["progress_acquired"] += status["progress"] == "실제 공정률 근거 있음"
        project_counts["start_date_acquired"] += bool(project.get("start_actual_date"))
        project_counts["schedule_acquired"] += bool(project.get("schedule_month"))
        project_counts["planning_stage"] += project.get("stage") in {"PLANNING", "PLANNED_SUPPLY", "DESIGNATED", "CANDIDATE", "PROPOSED_DISTRICT", "APPROVAL"}
        project_counts["mapping_review"] += project.get("mapping", {}).get("status") != "CONFIRMED"
        project_counts["not_started_verified"] += status["not_started_verified"]
        project_counts["move_in_start_acquired"] += bool((project.get("move_in_start") or {}).get("date"))

    unstarted = [{"id": sid, "label": label, "scope": target, "status": "NOT_STARTED",
                  "source_url": url, "next_action": action} for sid, label, target, url, action in UNSTARTED]
    return {"years": years, "rows": rows, "forecast_years": forecast_years,
            "forecast_rows": forecast_rows, "scope": scope, "projects": dict(project_counts),
            "not_started": unstarted,
            "notice": "미입수는 0건·미착수를 뜻하지 않습니다. 계획/공고/준공 예정과 입주 시작 예정일을 구분합니다. 연도 칸은 저장된 원천 증거만 표시하며, 원천 발표 여부는 별도 확인이 필요합니다."}
