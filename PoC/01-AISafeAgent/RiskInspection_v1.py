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
    return None


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
            "value": "-",
            "value_mm": None,
            "source": "none",
            "temperature_c": None,
            "humidity_pct": None,
            "wind_speed_ms": None,
            "wind_direction_deg": None,
            "precipitation_type": None,
            "precipitation_type_label": "",
            "lightning_code": None,
            "precipitation_probability_pct": None,
            "sky_code": None,
            "sky_label": "",
        }
    return points


def _set_rain_hourly_value(points: dict[int, dict[str, Any]], offset: int, value: Any, source: str) -> None:
    if offset not in points:
        return
    if value is None:
        return
    numeric = round(_rain_number(value), 2)
    points[offset]["value"] = _rain_value(value)
    points[offset]["value_mm"] = numeric
    points[offset]["source"] = source


def _weather_number(value: Any) -> float | None:
    text = str(value if value is not None else "").strip()
    if not text or text in {"-", "강수없음", "없음"}:
        return None
    try:
        return round(float(text), 2)
    except ValueError:
        return None


def _precipitation_type_label(value: Any) -> str:
    return {
        "0": "없음",
        "1": "비",
        "2": "비/눈",
        "3": "눈",
        "5": "빗방울",
        "6": "빗방울/눈날림",
        "7": "눈날림",
    }.get(str(value).strip(), f"코드 {value}")


def _sky_label(value: Any) -> str:
    return {"1": "맑음", "3": "구름많음", "4": "흐림"}.get(str(value).strip(), f"코드 {value}")


def _set_weather_item(point: dict[str, Any], category: str, value: Any, overwrite: bool = True) -> None:
    numeric_fields = {
        "T1H": "temperature_c",
        "REH": "humidity_pct",
        "WSD": "wind_speed_ms",
        "VEC": "wind_direction_deg",
        "LGT": "lightning_code",
        "POP": "precipitation_probability_pct",
    }
    field = numeric_fields.get(category)
    if field:
        if overwrite or point.get(field) is None:
            point[field] = _weather_number(value)
        return
    if category == "PTY" and (overwrite or point.get("precipitation_type") is None):
        point["precipitation_type"] = _weather_number(value)
        point["precipitation_type_label"] = _precipitation_type_label(value)
    elif category == "SKY" and (overwrite or point.get("sky_code") is None):
        point["sky_code"] = _weather_number(value)
        point["sky_label"] = _sky_label(value)


def _set_weather_items(point: dict[str, Any], items: list[dict[str, Any]], value_key: str, overwrite: bool = True) -> None:
    for item in items:
        _set_weather_item(point, str(item.get("category") or ""), item.get(value_key), overwrite)


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
            _set_weather_items(hourly_points[offset], items, "obsrValue")
            if offset == 0:
                rain_data["rain_current"] = _rain_value(value)
        rain_data["rain_6h_accum"] = _format_mm(sum(float(point["value_mm"] or 0) for offset, point in hourly_points.items() if -6 <= offset <= -1))
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
            key = f"{item.get('fcstDate', '')}{item.get('fcstTime', '')}"
            value = item.get("fcstValue")
            offset = target_offsets.get(key)
            if offset is None:
                continue
            category = str(item.get("category") or "")
            _set_weather_item(hourly_points[offset], category, value, overwrite=offset != 0)
            if category != "RN1":
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


def _rain_timeline_summary(rain: dict[str, Any]) -> str:
    hourly = rain.get("rain_hourly") if isinstance(rain, dict) else None
    if not isinstance(hourly, list) or not hourly:
        hourly = [
            {"offset": -6, "label": "-6H", "value": "-"},
            {"offset": -5, "label": "-5H", "value": "-"},
            {"offset": -4, "label": "-4H", "value": "-"},
            {"offset": -3, "label": "-3H", "value": "-"},
            {"offset": -2, "label": "-2H", "value": "-"},
            {"offset": -1, "label": "-1H", "value": "-"},
            {"offset": 0, "label": "현재", "value": rain.get("rain_current", "-") if isinstance(rain, dict) else "-"},
            {"offset": 1, "label": "+1H", "value": rain.get("rain_1h_after", "-") if isinstance(rain, dict) else "-"},
            {"offset": 2, "label": "+2H", "value": rain.get("rain_2h_after", "-") if isinstance(rain, dict) else "-"},
            {"offset": 3, "label": "+3H", "value": rain.get("rain_3h_after", "-") if isinstance(rain, dict) else "-"},
        ]
    normalized = sorted(hourly, key=lambda item: int(item.get("offset", 0) or 0))
    points = []
    for item in normalized:
        offset = item.get("offset", "")
        label = item.get("label") or ("현재" if offset == 0 else f"{int(offset):+d}H")
        time = item.get("time") or ""
        value = item.get("value") or _format_mm(float(item.get("value_mm") or 0))
        detail = f"{label}"
        if time:
            detail += f"({time})"
        weather = []
        if item.get("temperature_c") is not None:
            weather.append(f"{item['temperature_c']:g}°C")
        if item.get("humidity_pct") is not None:
            weather.append(f"습도 {item['humidity_pct']:g}%")
        if item.get("wind_speed_ms") is not None:
            wind = f"풍속 {item['wind_speed_ms']:g}m/s"
            if item.get("wind_direction_deg") is not None:
                wind += f"/{item['wind_direction_deg']:g}°"
            weather.append(wind)
        if item.get("precipitation_type_label"):
            weather.append(str(item["precipitation_type_label"]))
        if item.get("sky_label"):
            weather.append(str(item["sky_label"]))
        if item.get("precipitation_probability_pct") is not None:
            weather.append(f"강수확률 {item['precipitation_probability_pct']:g}%")
        if item.get("lightning_code") not in {None, 0, 0.0}:
            weather.append(f"낙뢰 {item['lightning_code']:g}")
        points.append(f"{detail} 강수 {value}" + (f", {', '.join(weather)}" if weather else ""))
    return " | ".join(points)


def _detail_context_lines(title: str, items: list[dict[str, Any]], limit: int = 3) -> list[str]:
    if not items:
        return [f"- {title}: 주변 500m 이내 확인된 항목 없음"]
    lines = []
    for item in items[:limit]:
        parts = [str(item.get("label") or item.get("kind") or title)]
        if item.get("date"):
            parts.append(f"날짜 {item['date']}")
        if item.get("distance_m") is not None:
            parts.append(f"직선거리 {item['distance_m']}m")
        if item.get("address"):
            parts.append(str(item["address"]))
        lines.append(f"- {title}: " + " / ".join(parts))
    if len(items) > limit:
        lines.append(f"- {title}: 외 {len(items) - limit}건 추가")
    return lines


def _report_output_control(rain: dict[str, Any], nearby_risk_count: int) -> str:
    hourly = rain.get("rain_hourly") if isinstance(rain, dict) else []
    points = [item for item in hourly if isinstance(item, dict) and item.get("source") not in {"none", "spatial_only"}]
    current = next((item for item in points if int(item.get("offset", 99) or 0) == 0), {})
    future = [item for item in points if int(item.get("offset", 0) or 0) > 0]

    rain_values = [float(item.get("value_mm") or 0) for item in points if item.get("value_mm") is not None]
    future_rain = [float(item.get("value_mm") or 0) for item in future if item.get("value_mm") is not None]
    rain_peak = max(rain_values, default=0.0)
    current_rain = float(current.get("value_mm") or 0)
    future_total = sum(future_rain[:3])
    past_total = _rain_number(rain.get("rain_6h_accum"))
    wind_peak = max((_to_float(item.get("wind_speed_ms")) or 0 for item in points), default=0.0)
    temperatures = [_to_float(item.get("temperature_c")) for item in points]
    temperatures = [value for value in temperatures if value is not None]
    precipitation_types = [str(item.get("precipitation_type_label") or "") for item in points]
    lightning = any((_to_float(item.get("lightning_code")) or 0) > 0 for item in points)

    hazards = []
    rain_signal = rain_peak >= 3 or future_total >= 10 or past_total >= 20
    risk_overlap = nearby_risk_count > 0 and (current_rain > 0 or any(value > 0 for value in future_rain))
    if risk_overlap:
        hazards.append("비와 주변 침수·산사태·인명피해 우려 이력이 겹침")
    elif rain_signal:
        hazards.append("강하거나 이어질 가능성이 있는 비")
    if any("눈" in value for value in precipitation_types):
        hazards.append("눈 또는 비와 눈이 섞인 강수")
    if lightning:
        hazards.append("낙뢰")
    if wind_peak >= 9:
        hazards.append("강한 바람")
    if temperatures and max(temperatures) >= 33:
        hazards.append("고온")
    if temperatures and min(temperatures) <= -12:
        hazards.append("저온")

    if not hazards:
        return "[보고서 출력 제어]\n- 즉시 알릴 특이사항: 없음\n- 과거 위험 이력만으로 현재 위험을 만들지 말 것"
    return "[보고서 출력 제어]\n- 즉시 알릴 특이사항: 있음\n- 핵심: " + ", ".join(hazards[:2])



def build_prompt_context(lat: float, lng: float, rain: dict[str, Any], kb: DisasterKnowledgeBase) -> tuple[str, dict[str, Any]]:
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

[기상 시간 흐름: 과거 6시간~앞으로 6시간]
{_rain_timeline_summary(rain)}

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
    context += "\n\n[위험 이력과 대피소 상세 요약]"
    for line in [
        *_detail_context_lines("침수 흔적", details["floods"]),
        *_detail_context_lines("산사태 발생/우려", details["landslides"]),
        *_detail_context_lines("인명피해 우려구역", details["vulnerable"]),
        *_detail_context_lines("대피소", details["shelters"]),
    ]:
        context += f"\n{line}"

    nearby_risk_count = len(floods) + len(landslides) + len(vulnerable)
    context += "\n\n" + _report_output_control(rain, nearby_risk_count)

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
        "당신은 시민에게 자연스러운 한국어로 안내하는 AI 안전비서입니다. 입력 데이터만 근거로 핵심부터 간결하게 답하세요. "
        "답변 전에는 과거 위험 이력, 현재 기상, 향후 기상 흐름을 종합해 즉시 알릴 특이사항이 있는지 먼저 판단하되 그 분석 과정은 출력하지 마세요. "
        "강하거나 지속·증가하는 비, 눈, 낙뢰, 강풍, 극심한 기온, 또는 관련 위험 이력과 현재·예상 기상이 겹치는 경우는 위험 신호입니다. 위험 신호가 하나라도 있으면 절대로 특이사항이 없다고 답하지 마세요. "
        "특히 강한 비가 이어지거나 예상되면서 주변에 침수 흔적·산사태·인명피해 우려구역이 있으면 반드시 특이사항으로 안내하세요. "
        "특이사항이 있으면 최대 4줄로 '특이사항: ...'와 '지금 할 일: ...'만 작성하세요. 여러 특이사항은 안전에 중요한 순서로 합쳐 짧게 쓰세요. "
        "위험 신호가 하나도 없을 때만 제목·번호·위험등급·행동요령·'특이사항' 표제 없이 자연스러운 한 문장, 한 줄로 끝내세요. "
        "과거·현재·미래 수치를 시간순으로 읽어 주거나 입력 데이터를 반복 나열하지 말고, 위험 판단에 꼭 필요한 수치만 예외적으로 한 번 사용하세요. "
        "행동요령은 지금 바로 실행할 수 있는 구체적인 행동만 1~2개 제시하세요. '주의하세요', '대비하세요', '안전에 유의하세요' 같은 막연한 표현은 쓰지 마세요. "
        "없는 사실을 만들거나 위험을 단정하지 말고 가능성으로 안내하세요. 값이 제공된 요소만 사용하고 누락값은 추정하지 마세요. 입력에 있는 위험 이력을 없다고 말하지 마세요. "
        "친절하고 담백한 어투를 사용하고 비속어·전문용어·과장된 표현은 피하세요."
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
        completion = client.chat.completions.create(model=model, messages=messages, temperature=0.2, max_tokens=160)
        content = completion.choices[0].message.content or ""
        if content.strip():
            return content
        reasoning = getattr(completion.choices[0].message, "reasoning_content", "") or ""
        if reasoning.strip():
            return reasoning
        raise RuntimeError("AI 응답 내용이 비어 있습니다.")

    payload = json.dumps({"model": model, "messages": messages, "temperature": 0.2, "max_tokens": 160}).encode("utf-8")
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
    try:
        from analytics_store import increment_local_llm_calls
        increment_local_llm_calls()
    except Exception:
        pass
    payload = json.dumps({
        "model": model,
        "messages": messages,
        "stream": False,
        "keep_alive": "5m",
        "think": False,
        "options": {"temperature": 0.2, "top_p": 0.9, "repeat_penalty": 1.1, "num_ctx": 2048, "num_predict": 160},
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


def _fallback_immediate_action(report: str) -> str:
    text = report.lower()
    if "낙뢰" in text:
        return "야외 활동을 멈추고 건물 안으로 이동하세요."
    if "눈" in text or "결빙" in text:
        return "불필요한 이동을 미루고 실내에 머무르세요."
    if "강풍" in text or "바람" in text:
        return "창문을 닫고 간판이나 낙하물 위험이 없는 실내로 이동하세요."
    if "폭염" in text or "고온" in text:
        return "그늘이나 냉방 가능한 실내로 이동하고 물을 마시세요."
    if "한파" in text or "저온" in text:
        return "실내로 이동해 체온을 유지하고 외출을 미루세요."
    if "산사태" in text or "급경사" in text:
        return "산비탈과 급경사지에서 벗어나 가까운 안전한 실내로 이동하세요."
    if any(word in text for word in ("비", "침수", "강수", "하천")):
        return "지하공간과 하천변에서 벗어나 가까운 안전한 실내로 이동하세요."
    return "가까운 안전한 실내로 이동하고 최신 재난 안내를 확인하세요."


def normalize_report_output(prompt_context: str, report: str) -> str:
    """LLM의 판단은 유지하면서 시민에게 보이는 형식만 짧고 실행 가능하게 정리한다."""
    text = str(report or "").strip()
    if not text or text.startswith("AI 보고서 생성"):
        return text
    compact = " ".join(text.split())
    forced_safe = "- 즉시 알릴 특이사항: 없음" in prompt_context
    forced_risk = "- 즉시 알릴 특이사항: 있음" in prompt_context
    control_core = ""
    if forced_risk and "- 핵심:" in prompt_context:
        control_core = prompt_context.split("- 핵심:", 1)[1].splitlines()[0].strip()
    no_risk_markers = ("특이사항은 없습니다", "특이사항이 없습니다", "특이사항 없음", "위험 없음", "위험 신호가 없습니다", "겹치지 않습니다", "확인되지 않습니다", "조치 불필요")
    model_says_safe = any(marker in compact for marker in no_risk_markers)
    if forced_safe or (model_says_safe and not forced_risk):
        return "현재 즉시 대응이 필요한 특이사항은 없습니다."
    if forced_risk and model_says_safe:
        compact = f"특이사항: {control_core or '안전에 영향을 줄 수 있는 상황'}"

    special = ""
    action = ""
    if "특이사항:" in compact:
        remainder = compact.split("특이사항:", 1)[1].strip()
        if "지금 할 일:" in remainder:
            special, action = (part.strip() for part in remainder.split("지금 할 일:", 1))
        else:
            special = remainder
    elif "위험:" in compact:
        special = compact.split("위험:", 1)[1].strip()
    else:
        special = compact

    for marker in ("지금 실행할 행동:", "행동요령:", "조치:"):
        if marker in special:
            special, candidate = (part.strip() for part in special.split(marker, 1))
            action = action or candidate
    special = special.lstrip("-*0123456789. ").strip()
    action = action.lstrip("-*0123456789. ").strip()
    special = special.replace("주변 500m 이내에", "주변에")
    special = special.replace("특별히 주의해야 합니다.", "위험이 커질 가능성이 있습니다.")
    if ". " in special:
        special = special.split(". ", 1)[0].rstrip(".") + "."
    if ". " in action:
        action = action.split(". ", 1)[0].rstrip(".") + "."

    if not special:
        special = "안전에 영향을 줄 수 있는 상황이 확인됐습니다."
    if not action or any(word in action for word in ("주의하세요", "대비하세요", "유의하세요", "조치 불필요")):
        action = _fallback_immediate_action(f"{special} {prompt_context}")
    special = special[:160].rstrip()
    action = action[:160].rstrip()
    return f"특이사항: {special}\n지금 할 일: {action}"



def generate_report(prompt_context: str, model_choice: str | None = None) -> tuple[str, str]:
    """선택한 LLM으로 보고서를 생성한다."""
    messages = [
        {"role": "system", "content": system_instruction()},
        {"role": "user", "content": prompt_context},
    ]
    provider, model, label = normalize_model_choice(model_choice)

    try:
        if provider == "ollama":
            return normalize_report_output(prompt_context, _ollama_completion(model, messages)), label
        if provider == "openrouter":
            api_key = os.getenv("OPENROUTER_API_KEY")
            if not api_key:
                return "AI 보고서 생성을 위해 OPENROUTER_API_KEY 환경변수가 필요합니다.", label
            return normalize_report_output(prompt_context, _chat_completion(OPENROUTER_BASE_URL, api_key, model, messages)), label

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
                return normalize_report_output(prompt_context, _chat_completion(HF_BASE_URL, api_key, candidate, messages)), f"Hugging Face · {candidate}"
            except Exception as error:  # noqa: BLE001 - try fallback model if a provider-specific route fails
                last_error = _extract_hf_error(error)
        return f"AI 보고서 생성 실패: {last_error}", label
    except Exception as error:  # noqa: BLE001 - PoC should report provider errors to the UI
        return f"AI 보고서 생성 실패: {_extract_hf_error(error)}", label


def _spatial_only_rain() -> dict[str, Any]:
    hourly = [
        {
            "offset": offset,
            "label": "현재" if offset == 0 else f"{offset:+d}H",
            "time": "",
            "time_key": "",
            "value": "-",
            "value_mm": None,
            "source": "spatial_only",
            "temperature_c": None,
            "humidity_pct": None,
            "wind_speed_ms": None,
            "wind_direction_deg": None,
            "precipitation_type": None,
            "precipitation_type_label": "",
            "lightning_code": None,
            "precipitation_probability_pct": None,
            "sky_code": None,
            "sky_label": "",
        }
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


def prepare_analysis(
    lat: float,
    lng: float,
    kb_path: Path | None = None,
    rain_info: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """LLM 호출 전에 기상·공간 데이터를 한 번만 정리한다."""
    kb_path = kb_path or latest_kb_path()
    kb = load_knowledge_base(kb_path)
    rain = rain_info if isinstance(rain_info, dict) and rain_info.get("rain_hourly") else get_kma_precipitation_live(lat, lng)
    prompt_context, spatial_summary = build_prompt_context(lat, lng, rain, kb)
    return {
        "lat": lat,
        "lng": lng,
        "rain_info": rain,
        "spatial_summary": spatial_summary,
        "prompt_context": prompt_context,
        "kb_path": str(kb_path) if kb_path else None,
        "kb_filename": kb_path.name if kb_path else None,
    }


def analyze_location(
    lat: float,
    lng: float,
    kb_path: Path | None = None,
    use_ai: bool = True,
    model_choice: str | None = None,
    rain_info: dict[str, Any] | None = None,
) -> dict[str, Any]:
    prepared = prepare_analysis(lat, lng, kb_path, rain_info)
    prompt_context = prepared.pop("prompt_context")
    if use_ai:
        report, model_label = generate_report(prompt_context, model_choice)
    else:
        report, model_label = prompt_context, None
    prepared.update({"model": model_label, "report": report})
    return prepared


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
