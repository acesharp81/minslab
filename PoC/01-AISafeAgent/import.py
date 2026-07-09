"""AI Safe Agent 기초 데이터 생성 모듈.

노트북에서 작성한 공공데이터 수집/전처리 로직을 서버에서 실행 가능한 형태로 정리했다.
실제 API 키는 코드에 두지 않고 apps/myservice/.env에서 읽는다.
"""

from __future__ import annotations

import csv
import json
import math
import os
import pickle
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable
from urllib import parse as url_parse
from urllib import request as url_request

PROJECT_DIR = next(
    (parent for parent in Path(__file__).resolve().parents if (parent / "env_utils.py").is_file()),
    Path(__file__).resolve().parents[2],
)
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

try:
    from env_utils import load_project_env
except ImportError:  # pragma: no cover - standalone fallback
    load_project_env = None

if load_project_env is not None:
    load_project_env(PROJECT_DIR / ".env")

POC_DIR = Path(__file__).resolve().parent
PKL_PREFIX = "integrated_disaster_kb"
LEGACY_PKL = POC_DIR / f"{PKL_PREFIX}.pkl"
DATE_FORMAT = "%Y%m%d_%H%M%S"

SAFETYDATA_APIS = {
    "통합대피소": {
        "url": "https://www.safetydata.go.kr/V2/api/DSSP-IF-10941",
        "key_env": "SAFETYDATA_SHELTER_KEY",
        "csv": "통합대피소_전체데이터.csv",
    },
    "산사태발생이력": {
        "url": "https://www.safetydata.go.kr/V2/api/DSSP-IF-00134",
        "key_env": "SAFETYDATA_LANDSLIDE_KEY",
        "csv": "산사태발생이력_전체데이터.csv",
    },
    "인명피해우려지역": {
        "url": "https://www.safetydata.go.kr/V2/api/DSSP-IF-10705",
        "key_env": "SAFETYDATA_VULNERABLE_KEY",
        "csv": "인명피해우려지역_전체데이터.csv",
    },
    "침수흔적도": {
        "url": "https://www.safetydata.go.kr/V2/api/DSSP-IF-20679",
        "key_env": "SAFETYDATA_FLOOD_KEY",
        "csv": "침수흔적도_전체데이터.csv",
    },
}

Progress = Callable[[str], None]


def emit(progress: Progress | None, message: str) -> None:
    if progress:
        progress(message)
    else:
        print(message, flush=True)


def pkl_candidates() -> list[Path]:
    dated = sorted(POC_DIR.glob(f"{PKL_PREFIX}_*.pkl"), key=lambda path: path.stat().st_mtime, reverse=True)
    if LEGACY_PKL.exists():
        dated.append(LEGACY_PKL)
    return dated


def latest_pkl_path() -> Path | None:
    candidates = pkl_candidates()
    return candidates[0] if candidates else None


def parse_pkl_date(path: Path) -> datetime | None:
    stem = path.stem
    prefix = f"{PKL_PREFIX}_"
    if stem.startswith(prefix):
        raw = stem.removeprefix(prefix)
        try:
            return datetime.strptime(raw, DATE_FORMAT)
        except ValueError:
            return None
    try:
        return datetime.fromtimestamp(path.stat().st_mtime)
    except OSError:
        return None


def get_pkl_status() -> dict[str, Any]:
    path = latest_pkl_path()
    if not path:
        return {"exists": False, "message": "PKL 파일 없음", "filename": None, "created_at": None, "display_date": None}
    created_at = parse_pkl_date(path)
    display_date = created_at.strftime("%Y-%m-%d %H:%M:%S") if created_at else None
    return {
        "exists": True,
        "message": f"PKL 파일 생성완료({display_date or path.name})",
        "filename": path.name,
        "path": str(path),
        "created_at": created_at.isoformat() if created_at else None,
        "display_date": display_date,
        "size": path.stat().st_size,
    }


def require_api_key(env_name: str) -> str:
    value = os.getenv(env_name, "").strip()
    if not value:
        raise RuntimeError(f"{env_name} 환경변수가 필요합니다.")
    return value


def extract_items(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        return []
    body = payload.get("body")
    if isinstance(body, list):
        return [item for item in body if isinstance(item, dict)]
    if isinstance(body, dict):
        for key in ("items", "item", "data"):
            value = body.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
            if isinstance(value, dict):
                nested = value.get("item") or value.get("data")
                if isinstance(nested, list):
                    return [item for item in nested if isinstance(item, dict)]
    response_body = payload.get("response", {}).get("body") if isinstance(payload.get("response"), dict) else None
    if isinstance(response_body, dict):
        items = response_body.get("items", {})
        if isinstance(items, dict):
            items = items.get("item", [])
        if isinstance(items, list):
            return [item for item in items if isinstance(item, dict)]
    return []


def fetch_page(url: str, api_key: str, page: int, num_of_rows: int) -> list[dict[str, Any]]:
    params = {
        "serviceKey": api_key,
        "returnType": "json",
        "numOfRows": num_of_rows,
        "pageNo": page,
    }
    full_url = f"{url}?{url_parse.urlencode(params)}"
    request = url_request.Request(full_url, headers={"User-Agent": "MinsLab-AISafeAgent/1.0"})
    with url_request.urlopen(request, timeout=30) as response:
        charset = response.headers.get_content_charset() or "utf-8"
        text = response.read().decode(charset, errors="replace")
    return extract_items(json.loads(text))


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8-sig")
        return
    fieldnames: list[str] = []
    seen = set()
    for row in rows:
        for key in row.keys():
            if key not in seen:
                fieldnames.append(key)
                seen.add(key)
    with path.open("w", encoding="utf-8-sig", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def fetch_all_sources(progress: Progress | None = None, num_of_rows: int = 1000) -> dict[str, list[dict[str, Any]]]:
    datasets: dict[str, list[dict[str, Any]]] = {}
    for name, info in SAFETYDATA_APIS.items():
        api_key = require_api_key(info["key_env"])
        emit(progress, f"[{name}] 수집 시작")
        rows: list[dict[str, Any]] = []
        page = 1
        while True:
            emit(progress, f"[{name}] {page}페이지 요청 중")
            items = fetch_page(info["url"], api_key, page, num_of_rows)
            if not items:
                emit(progress, f"[{name}] 더 이상 수집할 데이터가 없습니다")
                break
            rows.extend(items)
            emit(progress, f"[{name}] 누적 {len(rows)}건 수집")
            if len(items) < num_of_rows:
                break
            page += 1
            time.sleep(0.1)
        csv_path = POC_DIR / info["csv"]
        write_csv(csv_path, rows)
        emit(progress, f"[{name}] CSV 저장 완료: {csv_path.name} ({len(rows)}건)")
        datasets[name] = rows
    return datasets


def safe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        text = str(value).strip().replace(",", "")
        if not text:
            return None
        return float(text)
    except ValueError:
        return None


def web_mercator_to_wgs84(x: float, y: float) -> tuple[float, float]:
    lon = (x / 6378137.0) * 180.0 / math.pi
    lat = (2.0 * math.atan(math.exp(y / 6378137.0)) - math.pi / 2.0) * 180.0 / math.pi
    return lat, lon


def normalize_xy_to_wgs84(x_value: Any, y_value: Any) -> tuple[float | None, float | None]:
    x = safe_float(x_value)
    y = safe_float(y_value)
    if x is None or y is None:
        return None, None
    if 124.0 <= x <= 132.0 and 33.0 <= y <= 39.5:
        return y, x
    lat, lng = web_mercator_to_wgs84(x, y)
    if 33.0 <= lat <= 39.5 and 124.0 <= lng <= 132.0:
        return lat, lng
    # Some notebook experiments produced oversized but already degree-like numbers.
    scaled_lng, scaled_lat = x / 100000.0, y / 100000.0
    if 33.0 <= scaled_lat <= 39.5 and 124.0 <= scaled_lng <= 132.0:
        return scaled_lat, scaled_lng
    return None, None


def preprocess_flood(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result = []
    for row in rows:
        lat, lng = normalize_xy_to_wgs84(row.get("X") or row.get("XCRD"), row.get("Y") or row.get("YCRD"))
        if lat is None or lng is None:
            continue
        item = dict(row)
        item["converted_lat"] = lat
        item["converted_lng"] = lng
        result.append(item)
    return result


def preprocess_shelter(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result = []
    for row in rows:
        lat = safe_float(row.get("LAT") or row.get("Y_CRD") or row.get("YCRD"))
        lng = safe_float(row.get("LOT") or row.get("X_CRD") or row.get("XCRD"))
        if lat is None or lng is None:
            continue
        item = dict(row)
        item["LAT"] = lat
        item["LOT"] = lng
        result.append(item)
    return result


def preprocess_vulnerable(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result = []
    for row in rows:
        lat = safe_float(row.get("YCRD") or row.get("LAT") or row.get("lat"))
        lng = safe_float(row.get("XCRD") or row.get("LOT") or row.get("lng"))
        if lat is None or lng is None:
            continue
        item = dict(row)
        item["lat"] = lat
        item["lng"] = lng
        item["zone_name"] = str(row.get("DSTRCT_NM") or row.get("zone_name") or "지정 안 됨")
        item["danger_reason"] = str(row.get("DSTRCT_DSGN_RSN_DTL_CN") or row.get("danger_reason") or "")
        item["expected_pop"] = safe_float(row.get("EXPC_DAM_NOPE")) or 0.0
        item["expected_bldg"] = safe_float(row.get("EXPC_DAM_BLDG_CNT")) or 0.0
        item["evac_target_house"] = safe_float(row.get("SHNT_TRGT_HSHD_CNT")) or 0.0
        item["expected_area"] = safe_float(row.get("EXPC_DAM_AREA")) or 0.0
        result.append(item)
    return result


def preprocess_landslide(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result = []
    for row in rows:
        lat, lng = normalize_xy_to_wgs84(row.get("XMAP_CRTS") or row.get("XCRD"), row.get("YMAP_CRTS") or row.get("YCRD"))
        if lat is None or lng is None:
            continue
        item = dict(row)
        item["lat"] = lat
        item["lng"] = lng
        item["occur_date"] = str(row.get("OCRN_YMD") or row.get("occur_date") or "")
        item["disaster_name"] = str(row.get("DST_NM") or row.get("disaster_name") or "")
        item["address"] = str(row.get("ADDR") or row.get("address") or "")
        result.append(item)
    return result


def delete_existing_pkl(progress: Progress | None = None) -> None:
    for path in pkl_candidates():
        try:
            path.unlink()
            emit(progress, f"기존 PKL 삭제: {path.name}")
        except OSError as error:
            emit(progress, f"기존 PKL 삭제 실패: {path.name} ({error})")


def build_knowledge_base(progress: Progress | None = None, force: bool = True) -> dict[str, Any]:
    emit(progress, "기초 데이터 생성을 시작합니다")
    datasets = fetch_all_sources(progress)
    emit(progress, "CSV 다운로드 완료, 전처리 시작")

    flooding = preprocess_flood(datasets.get("침수흔적도", []))
    emit(progress, f"침수흔적도 전처리 완료: {len(flooding)}건")
    shelter = preprocess_shelter(datasets.get("통합대피소", []))
    emit(progress, f"통합대피소 전처리 완료: {len(shelter)}건")
    vulnerable = preprocess_vulnerable(datasets.get("인명피해우려지역", []))
    emit(progress, f"인명피해우려지역 전처리 완료: {len(vulnerable)}건")
    landslide = preprocess_landslide(datasets.get("산사태발생이력", []))
    emit(progress, f"산사태발생이력 전처리 완료: {len(landslide)}건")

    kb = {
        "flooding": flooding,
        "shelter": shelter,
        "vulnerable_zone": vulnerable,
        "landslide": landslide,
    }

    if force:
        delete_existing_pkl(progress)
    timestamp = datetime.now().strftime(DATE_FORMAT)
    output_path = POC_DIR / f"{PKL_PREFIX}_{timestamp}.pkl"
    with output_path.open("wb") as pkl_file:
        pickle.dump(kb, pkl_file, protocol=pickle.HIGHEST_PROTOCOL)
    emit(progress, f"PKL 저장 완료: {output_path.name}")

    status = get_pkl_status()
    status["counts"] = {key: len(value) for key, value in kb.items()}
    emit(progress, status["message"])
    return status


if __name__ == "__main__":
    build_knowledge_base()
