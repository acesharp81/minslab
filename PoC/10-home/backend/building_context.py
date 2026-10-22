"""Current nearby official building footprints for an evidence-backed block label.

VWorld buildings are contextual existing stock. Spatial proximity alone never
assigns a building, its households or its progress to the selected supply block.
"""
import math
import threading
import time
from weakref import WeakValueDictionary
from datetime import datetime
from zoneinfo import ZoneInfo

from .api_samples import key_for, response_json
from .collectors import Fetcher
from .sources import SOURCES

DATA_URL = "https://api.vworld.kr/req/data"
LAYER = "LT_C_BLDGINFO"
SOURCE_URL = "https://www.data.go.kr/data/15123970/openapi.do"
PAGE_SIZE = 1000
SEARCH_RADII_METRES = (1000, 750, 500, 300)
MAX_FEATURES = 5000
CACHE_SECONDS = 6 * 3600


def parse_buildings(content, page=1):
    response = response_json(content).get("response", {})
    if response.get("status") == "NOT_FOUND":
        return [], 0
    if response.get("status") != "OK":
        raise ValueError("VWorld GIS건물통합정보 응답 확인 필요")
    try:
        total = int(response["record"]["total"])
        features = response["result"]["featureCollection"]["features"]
    except (KeyError, TypeError, ValueError):
        raise ValueError("VWorld GIS건물통합정보 schema 변경") from None
    expected = min(PAGE_SIZE, max(0, total - (page - 1) * PAGE_SIZE))
    if not isinstance(features, list) or total < 0 or page < 1 or len(features) != expected:
        raise ValueError("건물 도형 페이지 불일치")
    output = []
    seen = set()
    for feature in features:
        fid = feature.get("id")
        geometry = feature.get("geometry") or {}
        props = feature.get("properties") or {}
        if not fid or fid in seen or geometry.get("type") not in {"Polygon", "MultiPolygon"}:
            raise ValueError("GIS건물통합정보 식별자·도형 누락 또는 중복")
        seen.add(fid)
        try:
            height = float(props.get("height"))
        except (TypeError, ValueError):
            height = None
        if height is None or not math.isfinite(height) or height <= 0 or height > 500:
            height = None
        try:
            floors = int(props.get("grnd_flr"))
        except (TypeError, ValueError):
            floors = None
        if floors is not None and not 0 < floors <= 150:
            floors = None
        basis = "OFFICIAL_HEIGHT" if height is not None else "FLOOR_ESTIMATE" if floors is not None else "VISUAL_ONLY"
        render_height = height if height is not None else round(floors * 3.0, 1) if floors is not None else 7.5
        output.append({"type": "Feature", "id": str(fid), "geometry": geometry,
                       "properties": {"height_m": height, "floors": floors,
                                      "render_height_m": render_height, "height_basis": basis,
                                      "name": str(props.get("bld_nm") or props.get("dong_nm") or ""),
                                      "use_approval_day": str(props.get("useapr_day") or ""),
                                      "source_feature_id": str(fid), "block_link_status": "UNLINKED"}})
    return output, total


class BuildingContext:
    def __init__(self):
        self._lock = threading.RLock()
        self._cache = {}
        self._key_locks = WeakValueDictionary()

    def get(self, block_id, service, anchor=None):
        cache_key = (block_id, anchor["latitude"], anchor["longitude"], anchor["coordinate_basis"]) if anchor else block_id
        with self._lock:
            key_lock=self._key_locks.setdefault(cache_key,threading.RLock())
        with key_lock:
            cached = self._cache.get(cache_key)
            if cached and time.monotonic() - cached[0] < CACHE_SECONDS:
                with self._lock:
                    self._cache.pop(cache_key,None)
                    self._cache[cache_key] = cached
                return cached[1]
            locations = {"|".join((row["region"], row["district_key"], row["block"])): row
                         for row in service.rows("block_location")}
            point = anchor or locations.get(block_id)
            if not point:
                raise ValueError("개별 위치가 검증된 블록이 아닙니다")
            latitude, longitude = point["latitude"], point["longitude"]
            source = next(row for row in SOURCES if row["id"] == "vworld")
            fetcher = Fetcher("vworld_building_context", service.data_dir / "raw")
            try:
                api_key = key_for(source)
                features = []
                for radius in SEARCH_RADII_METRES:
                    lat_delta = radius / 111320
                    lon_delta = radius / (111320 * math.cos(math.radians(latitude)))
                    box = f"BOX({longitude-lon_delta:.7f},{latitude-lat_delta:.7f},{longitude+lon_delta:.7f},{latitude+lat_delta:.7f})"
                    params = {"key": api_key, "service": "data", "request": "GetFeature", "version": "2.0",
                              "data": LAYER, "geomFilter": box, "crs": "EPSG:4326", "size": PAGE_SIZE,
                              "format": "json"}
                    first, total = parse_buildings(fetcher.get(DATA_URL, "json", params={**params, "page": 1},
                                                          headers={"Referer": "https://www.minslab.kr/poc/home/"}), 1)
                    if total <= MAX_FEATURES:
                        features = first
                        break
                else:
                    raise ValueError("주변 건물 수가 표시 한도를 초과합니다")
                for page in range(2, math.ceil(total / PAGE_SIZE) + 1):
                    batch, page_total = parse_buildings(fetcher.get(DATA_URL, "json", params={**params, "page": page},
                                                                 headers={"Referer": "https://www.minslab.kr/poc/home/"}), page)
                    if page_total != total:
                        raise ValueError("건물 도형 조회 중 원천 건수 변경")
                    features.extend(batch)
                if len(features) != total or len({feature["id"] for feature in features}) != total:
                    raise ValueError("건물 도형 누락 또는 페이지 중복")
                manifest = [entry["sha256"] for entry in fetcher.manifest]
            finally:
                fetcher.close()
            height_count = sum(f["properties"]["height_m"] is not None for f in features)
            floor_estimate_count = sum(f["properties"]["height_basis"] == "FLOOR_ESTIMATE" for f in features)
            visual_only_count = sum(f["properties"]["height_basis"] == "VISUAL_ONLY" for f in features)
            result = {
                "status": "READY" if total else "NO_BUILDINGS",
                "block_id": block_id, "latitude": latitude, "longitude": longitude,
                "location_basis": point["coordinate_basis"],
                "origin": dict(point),
                "context_basis": "VWorld GIS건물통합정보 · 주변 기존 건물 · 공급 블록 건물 매칭 아님",
                "source_url": SOURCE_URL, "source_layer": LAYER,
                "collected_at": datetime.now(ZoneInfo("Asia/Seoul")).date().isoformat(),
                "source_sha256": manifest, "search_radius_metres": radius,
                "feature_count": total, "height_count": height_count,
                "floor_estimate_count": floor_estimate_count, "visual_only_count": visual_only_count,
                "geojson": {"type": "FeatureCollection", "features": features},
            }
            with self._lock:
                self._cache[cache_key] = (time.monotonic(), result)
                while len(self._cache) > 8:self._cache.pop(next(iter(self._cache)),None)
            return result
