"""AI Safe Agent 위험 점검 PoC.

Jupyter Notebook에서 실험한 위험 분석 로직을 단독 실행 가능한 스크립트로 정리한 버전입니다.
API 키와 지식베이스 경로는 코드에 저장하지 않고 환경변수로 주입합니다.

필수/선택 환경변수:
- HF_API_KEY: Hugging Face Router API 키
- OPENROUTER_API_KEY: OpenRouter API 키
- KMA_AUTH_KEY: 기상청 API Hub 인증키
- DISASTER_KB_PATH: integrated_disaster_kb.pkl 경로, 기본값은 현재 작업 폴더
- HF_BASE_URL: 기본값 https://router.huggingface.co/v1
- OPENROUTER_BASE_URL: 기본값 https://openrouter.ai/api/v1
- AI_SAFE_AGENT_MODEL: 기본값 Qwen/Qwen3.6-35B-A3B
"""

from __future__ import annotations

import argparse
import json
import math
import os
import pickle
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from urllib import parse as url_parse
from urllib import request as url_request

try:
    import requests
except ImportError:  # pragma: no cover - optional convenience dependency
    requests = None

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

try:
    import joblib
except ImportError:  # pragma: no cover - optional runtime dependency
    joblib = None

try:
    from openai import OpenAI
except ImportError:  # pragma: no cover - optional runtime dependency
    OpenAI = None


HF_BASE_URL = os.getenv("HF_BASE_URL", "https://router.huggingface.co/v1")
OPENROUTER_BASE_URL = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
MODEL_NAME = os.getenv("AI_SAFE_AGENT_MODEL", "Qwen/Qwen3.6-35B-A3B")
HF_QWEN25_MODEL = os.getenv("AI_SAFE_HF_QWEN25_MODEL", "Qwen/Qwen2.5-72B-Instruct")
OPENROUTER_MODEL = os.getenv("AI_SAFE_OPENROUTER_MODEL", "openai/gpt-4o-mini")
POC_DIR = Path(__file__).resolve().parent
_KB_CACHE: dict[str, Any] = {"path": None, "mtime": None, "kb": None}
PKL_PREFIX = "integrated_disaster_kb"
DEFAULT_KB_PATH = Path(os.getenv("DISASTER_KB_PATH", "")) if os.getenv("DISASTER_KB_PATH") else None
KMA_ULTRA_SHORT_URL = os.getenv("KMA_ULTRA_SHORT_URL", "https://apihub-pub.kma.go.kr/api/typ02/openApi/VilageFcstInfoService_2.0/getUltraSrtFcst")
KMA_ULTRA_NCST_URL = os.getenv("KMA_ULTRA_NCST_URL", "https://apihub-pub.kma.go.kr/api/typ02/openApi/VilageFcstInfoService_2.0/getUltraSrtNcst")


@dataclass
class DisasterKnowledgeBase:
    floods: list[dict[str, Any]]
    shelters: list[dict[str, Any]]
    vulnerable: list[dict[str, Any]]
    landslides: list[dict[str, Any]]

    @classmethod
    def empty(cls) -> "DisasterKnowledgeBase":
        return cls(floods=[], shelters=[], vulnerable=[], landslides=[])


def latest_kb_path() -> Path | None:
    """날짜가 붙은 최신 PKL을 우선 사용하고, 없으면 legacy 파일을 사용한다."""
    if DEFAULT_KB_PATH and DEFAULT_KB_PATH.is_file():
        return DEFAULT_KB_PATH
    dated = sorted(POC_DIR.glob(f"{PKL_PREFIX}_*.pkl"), key=lambda item: item.stat().st_mtime, reverse=True)
    if dated:
        return dated[0]
    legacy = POC_DIR / f"{PKL_PREFIX}.pkl"
    return legacy if legacy.is_file() else None


def load_pickle_payload(path: Path) -> dict:
    if joblib is not None:
        try:
            return joblib.load(path)
        except Exception:
            pass
    with path.open("rb") as pkl_file:
        return pickle.load(pkl_file)


def clear_knowledge_base_cache() -> None:
    _KB_CACHE.update({"path": None, "mtime": None, "kb": None})


def load_knowledge_base(path: Path | None = None) -> DisasterKnowledgeBase:
    """PKL 지식베이스를 메모리에 올려 재사용한다."""
    target_path = path if path is not None else latest_kb_path()
    if target_path is None or not target_path.is_file():
        clear_knowledge_base_cache()
        return DisasterKnowledgeBase.empty()

    target_path = target_path.resolve()
    mtime = target_path.stat().st_mtime_ns
    if _KB_CACHE.get("path") == target_path and _KB_CACHE.get("mtime") == mtime and _KB_CACHE.get("kb") is not None:
        return _KB_CACHE["kb"]

    try:
        kb = load_pickle_payload(target_path)
    except Exception as error:  # noqa: BLE001 - PoC should degrade gracefully
        print(f"지식베이스 로드 실패, 빈 데이터로 대체합니다: {error}")
        clear_knowledge_base_cache()
        return DisasterKnowledgeBase.empty()

    result = DisasterKnowledgeBase(
        floods=kb.get("flooding", []),
        shelters=kb.get("shelter", []),
        vulnerable=kb.get("vulnerable_zone", []),
        landslides=kb.get("landslide", []),
    )
    _KB_CACHE.update({"path": target_path, "mtime": mtime, "kb": result})
    return result


def convert_grid(lat: float, lng: float) -> tuple[int, int]:
    """위경도를 기상청 동네예보 격자 좌표로 변환한다."""
    re = 6371.00877 / 5.0
    slat1 = 30.0 * math.pi / 180.0
    slat2 = 60.0 * math.pi / 180.0
    olong = 126.0 * math.pi / 180.0
    olat = 38.0 * math.pi / 180.0
    xo, yo = 43, 136
    sn = math.tan(math.pi * 0.25 + slat2 * 0.5) / math.tan(math.pi * 0.25 + slat1 * 0.5)
    sn = math.log(math.cos(slat1) / math.cos(slat2)) / math.log(sn)
    sf = math.tan(math.pi * 0.25 + slat1 * 0.5)
    sf = (math.cos(slat1) * sf**sn) / sn
    ro = math.tan(math.pi * 0.25 + olat * 0.5)
    ro = (re * sf) / (ro**sn)

    ra = math.tan(math.pi * 0.25 + lat * math.pi / 180.0 * 0.5)
    ra = (re * sf) / (ra**sn)
    theta = lng * math.pi / 180.0 - olong
    if theta > math.pi:
        theta -= 2.0 * math.pi
    if theta < -math.pi:
        theta += 2.0 * math.pi
    theta *= sn
    return math.floor(ra * math.sin(theta) + xo + 0.5), math.floor(ro - ra * math.cos(theta) + yo + 0.5)


def _rain_number(value: Any) -> float:
    text = str(value or "0").strip()
    if text in {"강수없음", "없음", "0", "0.0", "-"}:
        return 0.0
    cleaned = text.replace("mm", "").replace("㎜", "").replace("미만", "").strip()
    number = "".join(ch for ch in cleaned if ch.isdigit() or ch == ".")
    try:
        return float(number) if number else 0.0
    except ValueError:
        return 0.0


def _format_mm(value: float) -> str:
    return f"{int(value)}mm" if float(value).is_integer() else f"{value:.1f}mm"


def _rain_value(value: Any) -> str:
    text = str(value or "0").strip()
    if text in {"강수없음", "없음", "0", "0.0", "-"}:
        return "0mm"
    return text if "mm" in text or "㎜" in text else _format_mm(_rain_number(text))


def _kma_key_params() -> list[str]:
    key_param = os.getenv("KMA_KEY_PARAM", "authKey")
    key_params = [key_param]
    if os.getenv("KMA_TRY_SERVICE_KEY", "").lower() in {"1", "true", "yes"} and key_param != "serviceKey":
        key_params.append("serviceKey")
    return key_params


def _extract_kma_error(error: Exception) -> str:
    if hasattr(error, "read"):
        try:
            error_text = error.read().decode("utf-8", "replace")
            error_payload = json.loads(error_text)
            message = error_payload.get("result", {}).get("message") or error_payload.get("message")
            if message:
                return f"HTTP {getattr(error, 'code', '')}: {message}"
        except Exception:
            pass
    response = getattr(error, "response", None)
    if response is not None:
        try:
            payload = response.json()
            message = payload.get("result", {}).get("message") or payload.get("message")
            if message:
                return f"HTTP {response.status_code}: {message}"
        except Exception:
            try:
                return f"HTTP {response.status_code}: {response.text[:120]}"
            except Exception:
                pass
    return str(error)


def _kma_items(endpoint: str, base_params: dict[str, Any], auth_key: str) -> list[dict[str, Any]]:
    last_error: Exception | str | None = None
    for key_param in _kma_key_params():
        params = {key_param: auth_key, **base_params}
        try:
            if requests is not None:
                response = requests.get(endpoint, params=params, timeout=6)
                response.raise_for_status()
                content_type = response.headers.get("content-type", "")
                text = response.text
            else:
                query = url_parse.urlencode(params)
                with url_request.urlopen(f"{endpoint}?{query}", timeout=6) as response:
                    content_type = response.headers.get("content-type", "")
                    text = response.read().decode("utf-8", "replace")
            if "json" not in content_type.lower() and not text.lstrip().startswith("{"):
                raise ValueError(f"non_json_response({content_type or 'unknown content-type'})")
            payload = json.loads(text)
            return payload.get("response", {}).get("body", {}).get("items", {}).get("item", []) or []
        except Exception as error:  # noqa: BLE001 - try authKey/serviceKey variants
            last_error = _extract_kma_error(error)
    raise RuntimeError(str(last_error))


def _rn1_value(items: list[dict[str, Any]], value_key: str) -> Any:
    for item in items:
        if item.get("category") == "RN1":
            return item.get(value_key)
    return "0"


def _base_params(base_time_obj: datetime, nx: int, ny: int, time_format: str) -> dict[str, Any]:
    return {
        "pageNo": 1,
        "numOfRows": 100,
        "dataType": "JSON",
        "base_date": base_time_obj.strftime("%Y%m%d"),
        "base_time": base_time_obj.strftime(time_format),
        "nx": nx,
        "ny": ny,
    }


def _rain_hourly_points(now_floor: datetime) -> dict[int, dict[str, Any]]:
    points = {}
    for offset in range(-6, 7):
        target = now_floor + timedelta(hours=offset)
        points[offset] = {
            "offset": offset,
            "label": "현재" if offset == 0 else f"{offset:+d}H",
            "time": target.strftime("%m-%d %H:%M"),
            "time_key": target.strftime("%Y%m%d%H00"),
            "value": "0mm",
            "value_mm": 0.0,
            "source": "none",
        }
    return points


def _set_rain_hourly_value(points: dict[int, dict[str, Any]], offset: int, value: Any, source: str) -> None:
    if offset not in points:
        return
    numeric = round(_rain_number(value), 2)
    points[offset]["value"] = _rain_value(value)
    points[offset]["value_mm"] = numeric
    points[offset]["source"] = source


def get_kma_precipitation_live(lat: float, lng: float, auth_key: str | None = None) -> dict[str, Any]:
    """기상청 초단기실황/초단기예보를 이용해 강수 추계를 조회한다."""
    now = datetime.now()
    now_floor = now.replace(minute=0, second=0, microsecond=0)
    hourly_points = _rain_hourly_points(now_floor)
    rain_data: dict[str, Any] = {
        "rain_current": "0mm",
        "rain_1h_after": "0mm",
        "rain_2h_after": "0mm",
        "rain_3h_after": "0mm",
        "rain_6h_accum": "0mm",
        "rain_hourly": list(hourly_points.values()),
        "status": "not_requested",
    }
    auth_key = auth_key or os.getenv("KMA_AUTH_KEY")
    if not auth_key:
        rain_data["status"] = "missing KMA_AUTH_KEY"
        return rain_data

    nx, ny = convert_grid(lat, lng)
    obs_base = now_floor if now.minute >= 40 else now_floor - timedelta(hours=1)

    errors = []
    try:
        for offset in range(-6, 1):
            obs_time = now_floor + timedelta(hours=offset)
            if obs_time > obs_base:
                continue
            items = _kma_items(KMA_ULTRA_NCST_URL, _base_params(obs_time, nx, ny, "%H00"), auth_key)
            value = _rn1_value(items, "obsrValue")
            _set_rain_hourly_value(hourly_points, offset, value, "observation")
            if offset == 0:
                rain_data["rain_current"] = _rain_value(value)
        rain_data["rain_6h_accum"] = _format_mm(sum(point["value_mm"] for offset, point in hourly_points.items() if -6 <= offset <= -1))
    except Exception as error:  # noqa: BLE001 - forecast can still fill part of the display
        errors.append(f"ncst_error: {_extract_kma_error(error)}")

    try:
        fcst_base = now - timedelta(hours=1) if now.minute < 45 else now
        items = _kma_items(KMA_ULTRA_SHORT_URL, _base_params(fcst_base, nx, ny, "%H30"), auth_key)
        target_offsets = {
            (now_floor + timedelta(hours=offset)).strftime("%Y%m%d%H00"): offset
            for offset in range(0, 7)
        }
        legacy_fields = {0: "rain_current", 1: "rain_1h_after", 2: "rain_2h_after", 3: "rain_3h_after"}
        filled_forecast_offsets = set()
        future_rn1: list[tuple[str, Any]] = []
        for item in items:
            if item.get("category") != "RN1":
                continue
            key = f"{item.get('fcstDate', '')}{item.get('fcstTime', '')}"
            value = item.get("fcstValue")
            offset = target_offsets.get(key)
            if offset is None:
                continue
            future_rn1.append((key, value))
            if offset == 0 and hourly_points[0]["source"] == "observation":
                continue
            _set_rain_hourly_value(hourly_points, offset, value, "forecast")
            filled_forecast_offsets.add(offset)
            if offset in legacy_fields and (offset != 0 or rain_data["rain_current"] == "0mm"):
                rain_data[legacy_fields[offset]] = _rain_value(value)
        future_rn1.sort(key=lambda item: item[0])
        for index, field in enumerate(("rain_1h_after", "rain_2h_after", "rain_3h_after"), start=1):
            if index not in filled_forecast_offsets and index < len(future_rn1):
                rain_data[field] = _rain_value(future_rn1[index][1])
    except Exception as error:  # noqa: BLE001 - surface API details in status chip
        errors.append(f"fcst_error: {_extract_kma_error(error)}")

    rain_data["rain_hourly"] = [hourly_points[offset] for offset in range(-6, 7)]
    rain_data["status"] = "ok" if not errors else "; ".join(errors)
    return rain_data


def _to_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _coords(record: dict[str, Any], lat_keys: tuple[str, ...], lng_keys: tuple[str, ...]) -> tuple[float, float] | None:
    lat = next((_to_float(record.get(key)) for key in lat_keys if _to_float(record.get(key)) is not None), None)
    lng = next((_to_float(record.get(key)) for key in lng_keys if _to_float(record.get(key)) is not None), None)
    return (lat, lng) if lat is not None and lng is not None else None


def approx_distance_m(lat1: float, lng1: float, lat2: float, lng2: float) -> int:
    """하버사인 공식으로 두 위경도 사이 실제 지표 거리를 계산한다."""
    earth_radius_m = 6_371_008.8
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return int(round(earth_radius_m * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))))


def nearby_records(
    records: list[dict[str, Any]],
    lat: float,
    lng: float,
    lat_keys: tuple[str, ...],
    lng_keys: tuple[str, ...],
    radius_m: int = 500,
) -> list[dict[str, Any]]:
    nearby = []
    for record in records:
        coords = _coords(record, lat_keys, lng_keys)
        if not coords:
            continue
        distance = approx_distance_m(lat, lng, coords[0], coords[1])
        if distance <= radius_m:
            nearby.append({**record, "distance_m": distance})
    return sorted(nearby, key=lambda item: item["distance_m"])


def _indexed_records(
    kb: DisasterKnowledgeBase,
    name: str,
    records: list[dict[str, Any]],
    lat_keys: tuple[str, ...],
    lng_keys: tuple[str, ...],
) -> list[tuple[float, float, dict[str, Any]]]:
    indexes = getattr(kb, "_spatial_indexes", None)
    if indexes is None:
        indexes = {}
        setattr(kb, "_spatial_indexes", indexes)
    if name not in indexes:
        indexed = []
        for record in records:
            coords = _coords(record, lat_keys, lng_keys)
            if coords:
                indexed.append((coords[0], coords[1], record))
        indexes[name] = indexed
    return indexes[name]


def nearby_indexed_records(
    kb: DisasterKnowledgeBase,
    name: str,
    records: list[dict[str, Any]],
    lat: float,
    lng: float,
    lat_keys: tuple[str, ...],
    lng_keys: tuple[str, ...],
    radius_m: int = 500,
) -> list[dict[str, Any]]:
    indexed = _indexed_records(kb, name, records, lat_keys, lng_keys)
    lat_delta = radius_m / 111_320
    lng_scale = max(math.cos(math.radians(lat)), 0.01)
    lng_delta = radius_m / (111_320 * lng_scale)
    nearby = []
    for item_lat, item_lng, record in indexed:
        if abs(item_lat - lat) > lat_delta or abs(item_lng - lng) > lng_delta:
            continue
        distance = approx_distance_m(lat, lng, item_lat, item_lng)
        if distance <= radius_m:
            nearby.append({**record, "distance_m": distance})
    return sorted(nearby, key=lambda item: item["distance_m"])


def _first_text(record: dict[str, Any], keys: tuple[str, ...], fallback: str) -> str:
    for key in keys:
        value = record.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return fallback


def _map_feature(
    record: dict[str, Any],
    category: str,
    kind: str,
    label_keys: tuple[str, ...],
    lat_keys: tuple[str, ...],
    lng_keys: tuple[str, ...],
    fallback: str,
) -> dict[str, Any] | None:
    coords = _coords(record, lat_keys, lng_keys)
    if not coords:
        return None
    return {
        "category": category,
        "kind": kind,
        "label": _first_text(record, label_keys, fallback),
        "lat": round(coords[0], 7),
        "lng": round(coords[1], 7),
        "distance_m": record.get("distance_m"),
    }


def _limited_features(features: list[dict[str, Any] | None], limit: int = 120) -> list[dict[str, Any]]:
    return [feature for feature in features if feature is not None][:limit]


def _optional_text(record: dict[str, Any], keys: tuple[str, ...]) -> str:
    for key in keys:
        value = record.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def _compact_detail(
    record: dict[str, Any],
    kind: str,
    label_keys: tuple[str, ...],
    date_keys: tuple[str, ...],
    address_keys: tuple[str, ...],
    lat_keys: tuple[str, ...],
    lng_keys: tuple[str, ...],
    fallback: str,
    field_keys: tuple[str, ...],
) -> dict[str, Any]:
    coords = _coords(record, lat_keys, lng_keys)
    fields = {}
    for key in field_keys:
        value = record.get(key)
        if value is not None and str(value).strip():
            fields[key] = value
    return {
        "kind": kind,
        "label": _first_text(record, label_keys, fallback),
        "date": _optional_text(record, date_keys),
        "address": _optional_text(record, address_keys),
        "distance_m": record.get("distance_m"),
        "lat": round(coords[0], 7) if coords else None,
        "lng": round(coords[1], 7) if coords else None,
        "fields": fields,
    }


def _limited_details(records: list[dict[str, Any]], limit: int = 80, **kwargs: Any) -> list[dict[str, Any]]:
    return [_compact_detail(record, **kwargs) for record in records[:limit]]


def build_prompt_context(lat: float, lng: float, rain: dict[str, str], kb: DisasterKnowledgeBase) -> tuple[str, dict[str, Any]]:
    floods = nearby_indexed_records(kb, "floods", kb.floods, lat, lng, ("converted_lat", "lat", "LAT", "YCRD"), ("converted_lng", "lng", "LOT", "XCRD"))
    landslides = nearby_indexed_records(kb, "landslides", kb.landslides, lat, lng, ("lat", "YMAP_CRTS"), ("lng", "XMAP_CRTS"))
    vulnerable = nearby_indexed_records(kb, "vulnerable", kb.vulnerable, lat, lng, ("lat", "YCRD", "XCRD"), ("lng", "XCRD", "YCRD"))
    shelters = nearby_indexed_records(kb, "shelters", kb.shelters, lat, lng, ("LAT", "Y_CRD", "lat"), ("LOT", "X_CRD", "lng"))

    nearest_shelter = shelters[0] if shelters else None
    context = f"""
[분석 좌표]
- 위도: {lat:.6f}
- 경도: {lng:.6f}

[기상청 실시간 예보 현황]
- 현재 실황 강수량: {rain['rain_current']}
- 6시간 누적 강수량: {rain['rain_6h_accum']}
- 1시간 후 예상 강수량: {rain['rain_1h_after']}
- 2시간 후 예상 강수량: {rain['rain_2h_after']}
- 3시간 후 예상 강수량: {rain['rain_3h_after']}

[공간 지식베이스 인프라 정보]
- 반경 500m 침수 흔적: {len(floods)}건
- 반경 500m 산사태 발생/우려: {len(landslides)}건
- 반경 500m 인명피해 우려구역: {len(vulnerable)}건
- 반경 500m 대피소: {len(shelters)}건
""".strip()
    if vulnerable:
        first = vulnerable[0]
        context += f"\n- 대표 우려구역: {first.get('DSTRCT_NM', '취약지구')} / {first.get('DSTRCT_DSGN_RSN_DTL_CN', '사유 정보 없음')}"
    if nearest_shelter:
        name = nearest_shelter.get("REARE_NM") or nearest_shelter.get("VT_ACM_PLC_NM") or "대피소"
        context += f"\n- 가장 가까운 대피소: {name} ({nearest_shelter['distance_m']}m)"

    risk_features = _limited_features(
        [
            *[
                _map_feature(
                    item,
                    "risk",
                    "침수 흔적",
                    ("FLUD_NM2", "FLUD_NM", "ADDR", "address"),
                    ("converted_lat", "lat", "LAT", "YCRD"),
                    ("converted_lng", "lng", "LOT", "XCRD"),
                    "침수 흔적",
                )
                for item in floods
            ],
            *[
                _map_feature(
                    item,
                    "risk",
                    "산사태 발생/우려",
                    ("disaster_name", "DST_NM", "ADDR", "address"),
                    ("lat", "YMAP_CRTS"),
                    ("lng", "XMAP_CRTS"),
                    "산사태 발생/우려",
                )
                for item in landslides
            ],
            *[
                _map_feature(
                    item,
                    "risk",
                    "인명피해 우려구역",
                    ("DSTRCT_NM", "HYTM_NM", "RMRK", "ROAD_NM_ADDR"),
                    ("lat", "YCRD", "XCRD"),
                    ("lng", "XCRD", "YCRD"),
                    "인명피해 우려구역",
                )
                for item in vulnerable
            ],
        ]
    )
    shelter_features = _limited_features(
        [
            _map_feature(
                item,
                "shelter",
                "대피소",
                ("REARE_NM", "VT_ACM_PLC_NM", "SHLT_SE_NM", "RONA_DADDR"),
                ("LAT", "Y_CRD", "lat"),
                ("LOT", "X_CRD", "lng"),
                "대피소",
            )
            for item in shelters
        ]
    )

    details = {
        "floods": _limited_details(
            floods,
            kind="침수 흔적",
            label_keys=("FLUD_NM2", "FLUD_NM", "ADDR", "address"),
            date_keys=("SAT_DATE", "END_DATE", "FLUD_YEAR", "EXMN_YEAR"),
            address_keys=("ADDR", "address", "FLUD_NM2", "FLUD_NM"),
            lat_keys=("converted_lat", "lat", "LAT", "YCRD"),
            lng_keys=("converted_lng", "lng", "LOT", "XCRD"),
            fallback="침수 흔적",
            field_keys=("FLUD_NM2", "FLUD_NM", "FLUD_YEAR", "SAT_DATE", "SAT_TM", "END_DATE", "END_TM", "FLUD_AR", "AVG_FLDWTL", "distance_m"),
        ),
        "landslides": _limited_details(
            landslides,
            kind="산사태 발생/우려",
            label_keys=("disaster_name", "DST_NM", "ADDR", "address"),
            date_keys=("OCRN_YMD", "occur_date"),
            address_keys=("ADDR", "address"),
            lat_keys=("lat", "YMAP_CRTS"),
            lng_keys=("lng", "XMAP_CRTS"),
            fallback="산사태 발생/우려",
            field_keys=("DST_NM", "OCRN_YMD", "occur_date", "ADDR", "address", "SN", "distance_m"),
        ),
        "vulnerable": _limited_details(
            vulnerable,
            kind="인명피해 우려구역",
            label_keys=("DSTRCT_NM", "HYTM_NM", "RMRK", "ROAD_NM_ADDR"),
            date_keys=("DSGN_YMD", "RMV_YMD"),
            address_keys=("ROAD_NM_ADDR", "RONA_DADDR", "SHNT_PLC_NM"),
            lat_keys=("lat", "YCRD", "XCRD"),
            lng_keys=("lng", "XCRD", "YCRD"),
            fallback="인명피해 우려구역",
            field_keys=("DSTRCT_NM", "HYTM_NM", "DSGN_YMD", "RMV_YMD", "ROAD_NM_ADDR", "RONA_DADDR", "SHNT_PLC_NM", "DSTRCT_DSGN_RSN_CD", "DSTRCT_DSGN_RSN_DTL_CN", "EXPC_DAM_NOPE", "distance_m"),
        ),
        "shelters": _limited_details(
            shelters,
            kind="대피소",
            label_keys=("REARE_NM", "VT_ACM_PLC_NM", "SHLT_SE_NM", "RONA_DADDR"),
            date_keys=(),
            address_keys=("RONA_DADDR",),
            lat_keys=("LAT", "Y_CRD", "lat"),
            lng_keys=("LOT", "X_CRD", "lng"),
            fallback="대피소",
            field_keys=("REARE_NM", "VT_ACM_PLC_NM", "SHLT_SE_NM", "RONA_DADDR", "MNG_SN", "distance_m"),
        ),
    }
    summary = {
        "floods_count": len(floods),
        "landslides_count": len(landslides),
        "vulnerable_count": len(vulnerable),
        "shelters_count": len(shelters),
        "nearest_shelter": nearest_shelter,
        "map_features": [*risk_features, *shelter_features],
        "details": details,
    }
    return context, summary


def system_instruction() -> str:
    return (
        "당신은 실시간 기상 데이터와 지식베이스를 융합해 국민들이 안심하고 대처할 수 있도록 안내하는 "
        "대국민 방재 서비스 소통 전문가입니다. 확인된 데이터에 근거해 위험 요소 종합 분석, 등급 평가, "
        "즉각적인 행동 요령만 간결하게 작성하세요. 확인되지 않은 사실은 추측하지 마세요. "
        "모든 강수량이 0mm이고 주변 위험 기록도 없다면 '주변 반경 500m 이내 특이 위험 요인 없음 (안전)'만 출력하세요."
    )


def _extract_hf_error(error: Exception) -> str:
    if not hasattr(error, "read"):
        return str(error)
    try:
        body = error.read().decode("utf-8", "replace")
        payload = json.loads(body)
        message = payload.get("error", {}).get("message") or payload.get("message")
        if message:
            return f"HTTP {getattr(error, 'code', '')}: {message}"
        if "Access denied" in body and "Cloudflare" in body:
            return f"HTTP {getattr(error, 'code', '')}: provider access denied by Cloudflare"
    except Exception:
        pass
    return str(error)


def _extract_hf_content(result: dict[str, Any]) -> str:
    message = result.get("choices", [{}])[0].get("message", {})
    return (message.get("content") or message.get("reasoning_content") or "").strip()


def _chat_completion(base_url: str, api_key: str, model: str, messages: list[dict[str, str]], timeout: int = 60) -> str:
    if OpenAI is not None:
        client = OpenAI(base_url=base_url, api_key=api_key)
        completion = client.chat.completions.create(model=model, messages=messages, temperature=0.2)
        content = completion.choices[0].message.content or ""
        if content.strip():
            return content
        reasoning = getattr(completion.choices[0].message, "reasoning_content", "") or ""
        if reasoning.strip():
            return reasoning
        raise RuntimeError("AI 응답 내용이 비어 있습니다.")

    payload = json.dumps({"model": model, "messages": messages, "temperature": 0.2}).encode("utf-8")
    request = url_request.Request(
        f"{base_url.rstrip('/')}/chat/completions",
        data=payload,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json", "X-Title": "MinsLab AI Safe Agent"},
        method="POST",
    )
    with url_request.urlopen(request, timeout=timeout) as response:
        result = json.loads(response.read().decode("utf-8"))
    content = _extract_hf_content(result)
    if content:
        return content
    raise RuntimeError("AI 응답 내용이 비어 있습니다.")


def _ollama_completion(model: str, messages: list[dict[str, str]]) -> str:
    payload = json.dumps({
        "model": model,
        "messages": messages,
        "stream": False,
        "keep_alive": "5m",
        "options": {"temperature": 0.2, "top_p": 0.9, "repeat_penalty": 1.1, "num_ctx": 8192},
    }).encode("utf-8")
    request = url_request.Request(
        f"{OLLAMA_BASE_URL.rstrip('/')}/api/chat",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with url_request.urlopen(request, timeout=120) as response:
        result = json.loads(response.read().decode("utf-8"))
    content = result.get("message", {}).get("content", "")
    if content.strip():
        return content
    raise RuntimeError("Ollama 응답 내용이 비어 있습니다.")


def normalize_model_choice(model_choice: str | None) -> tuple[str, str, str]:
    choice = (model_choice or "").strip()
    if choice.startswith("ollama:"):
        model = choice.split(":", 1)[1]
        return "ollama", model, f"Ollama · {model}"
    if choice.startswith("huggingface:"):
        model = choice.split(":", 1)[1] or HF_QWEN25_MODEL
        return "huggingface", model, f"Hugging Face · {model}"
    if choice.startswith("openrouter:"):
        model = choice.split(":", 1)[1] or OPENROUTER_MODEL
        return "openrouter", model, f"OpenRouter · {model}"
    if choice:
        return "huggingface", choice, f"Hugging Face · {choice}"
    return "huggingface", MODEL_NAME, f"Hugging Face · {MODEL_NAME}"


def generate_report(prompt_context: str, model_choice: str | None = None) -> tuple[str, str]:
    """선택한 LLM으로 보고서를 생성한다."""
    messages = [
        {"role": "system", "content": system_instruction()},
        {"role": "user", "content": prompt_context},
    ]
    provider, model, label = normalize_model_choice(model_choice)

    try:
        if provider == "ollama":
            return _ollama_completion(model, messages), label
        if provider == "openrouter":
            api_key = os.getenv("OPENROUTER_API_KEY")
            if not api_key:
                return "AI 보고서 생성을 위해 OPENROUTER_API_KEY 환경변수가 필요합니다.", label
            return _chat_completion(OPENROUTER_BASE_URL, api_key, model, messages), label

        api_key = os.getenv("HF_API_KEY")
        if not api_key:
            return "AI 보고서 생성을 위해 HF_API_KEY 환경변수가 필요합니다.", label
        models = [model]
        if ":" in model:
            base_model = model.split(":", 1)[0]
            if base_model not in models:
                models.append(base_model)
        last_error = None
        for candidate in models:
            try:
                return _chat_completion(HF_BASE_URL, api_key, candidate, messages), f"Hugging Face · {candidate}"
            except Exception as error:  # noqa: BLE001 - try fallback model if a provider-specific route fails
                last_error = _extract_hf_error(error)
        return f"AI 보고서 생성 실패: {last_error}", label
    except Exception as error:  # noqa: BLE001 - PoC should report provider errors to the UI
        return f"AI 보고서 생성 실패: {_extract_hf_error(error)}", label


def _spatial_only_rain() -> dict[str, Any]:
    hourly = [
        {"offset": offset, "label": "현재" if offset == 0 else f"{offset:+d}H", "time": "", "time_key": "", "value": "-", "value_mm": 0.0, "source": "spatial_only"}
        for offset in range(-6, 7)
    ]
    return {
        "rain_current": "-",
        "rain_1h_after": "-",
        "rain_2h_after": "-",
        "rain_3h_after": "-",
        "rain_6h_accum": "-",
        "rain_hourly": hourly,
        "status": "spatial_only",
    }


def analyze_spatial_location(lat: float, lng: float, kb_path: Path | None = None) -> dict[str, Any]:
    kb_path = kb_path or latest_kb_path()
    kb = load_knowledge_base(kb_path)
    _, spatial_summary = build_prompt_context(lat, lng, _spatial_only_rain(), kb)
    return {
        "lat": lat,
        "lng": lng,
        "radius_m": 500,
        "rain_info": _spatial_only_rain(),
        "spatial_summary": spatial_summary,
        "kb_path": str(kb_path) if kb_path else None,
        "kb_filename": kb_path.name if kb_path else None,
    }


def analyze_location(
    lat: float,
    lng: float,
    kb_path: Path | None = None,
    use_ai: bool = True,
    model_choice: str | None = None,
) -> dict[str, Any]:
    kb_path = kb_path or latest_kb_path()
    kb = load_knowledge_base(kb_path)
    rain = get_kma_precipitation_live(lat, lng)
    prompt_context, spatial_summary = build_prompt_context(lat, lng, rain, kb)
    if use_ai:
        report, model_label = generate_report(prompt_context, model_choice)
    else:
        report, model_label = prompt_context, None
    return {
        "lat": lat,
        "lng": lng,
        "model": model_label,
        "rain_info": rain,
        "spatial_summary": spatial_summary,
        "report": report,
        "kb_path": str(kb_path) if kb_path else None,
        "kb_filename": kb_path.name if kb_path else None,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="AI Safe Agent 위험 점검 PoC")
    parser.add_argument("--lat", type=float, required=True, help="분석할 위도")
    parser.add_argument("--lng", type=float, required=True, help="분석할 경도")
    parser.add_argument("--kb", type=Path, default=None, help="integrated_disaster_kb.pkl 경로")
    parser.add_argument("--no-ai", action="store_true", help="LLM 호출 없이 프롬프트 컨텍스트만 출력")
    args = parser.parse_args()

    result = analyze_location(args.lat, args.lng, args.kb, use_ai=not args.no_ai)
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
