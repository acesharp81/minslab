"""Evidence-backed nearby transit, schools, hospitals and large marts."""
import math
import re
import threading
import time
from weakref import WeakValueDictionary
from datetime import datetime
from zoneinfo import ZoneInfo

from .api_samples import key_for, response_json
from .collectors import Fetcher
from .sources import SOURCES

SEARCH_URL = "https://api.vworld.kr/req/search"
SOURCE_URL = "https://www.vworld.kr/dev/v4dv_search2_s001.do"
RADIUS_METRES = 3500
PAGE_SIZE = 1000
MAX_TOTAL_PER_QUERY = 3000
CACHE_SECONDS = 24 * 3600
QUERIES = (("subway", "지하철역"), ("bus", "버스정류장"), ("school", "초등학교"), ("school", "중학교"),
           ("school", "고등학교"), ("childcare", "어린이집"), ("hospital", "병원"),
           ("mart", "대형마트"), ("mart", "이마트"), ("mart", "홈플러스"),
           ("mart", "롯데마트"), ("mart", "코스트코"), ("mart", "트레이더스"), ("mart", "하나로클럽"))
DISPLAY_LIMITS = {"subway": 10, "bus": 20, "school": 25, "childcare": 25, "hospital": 12, "mart": 12}
GTX_RADIUS_METRES = 12000
# GTX-A operation is checked against MOLIT's opened sections. These are
# VWorld POIs checked on 2026-10-04. A station POI is preferred; when absent,
# a named station-exit bus stop is an explicitly labelled vicinity proxy.
# No planned station coordinates or unrelated business POIs are used.
GTX_A_STATUS_URL = "https://molit.go.kr/USR/NEWS/m_71/dtl.jsp?id=95090716"
GTX_A_PLANNED_URL = "https://www.molit.go.kr/USR/deptInfo/m_94/lst.jsp?DEPT_ID=1613104&DEPT_NM=%EC%B2%A0%EB%8F%84%EA%B5%AD"
GTX_A_STATIONS = (
    ("킨텍스역", 37.66541669710184, 126.74753329997795, "POI01000000NHKD96", "VWORLD_STATION_EXIT_BUS_STOP_PROXY"),
    ("대곡역", 37.631629000806576, 126.81102500039492, "POI01000000BROQGS"),
    ("연신내역", 37.61896199988207, 126.92116209992392, "POI01000000JP2RTQ"),
    ("서울역", 37.55356539067728, 126.97249959965218, "POI01000000BROFCD"),
    ("수서역", 37.48763300119657, 127.10111800024477, "POI01000000BROMU2"),
    ("성남역", 37.39470352026701, 127.1194453997421, "POI01000000LTFV6Q"),
    ("구성역", 37.29901300112689, 127.10566399971539, "POI01000000BRON8H"),
    ("동탄역", 37.19958330280638, 127.09608330044945, "POI01000000AREZMW", "VWORLD_STATION_EXIT_BUS_STOP_PROXY"),
)


def nearby_gtx_stations(latitude, longitude):
    result = []
    for entry in GTX_A_STATIONS:
        name, lat, lon, poi_id = entry[:4]
        location_basis = entry[4] if len(entry) > 4 else "VWORLD_EXISTING_STATION_POI"
        distance = distance_metres(latitude, longitude, lat, lon)
        if distance <= GTX_RADIUS_METRES:
            location_note = "역 출구 인근 버스정류장 위치" if location_basis.endswith("PROXY") else "기존 역 POI 대표 위치"
            result.append({"id": poi_id, "kind": "subway", "line": "GTX-A", "name": name,
                           "category": "GTX-A 운영역 · VWorld " + location_note,
                           "latitude": lat, "longitude": lon, "distance_m": distance,
                           "address": "", "service_status": "OPERATING",
                           "service_status_source_url": GTX_A_STATUS_URL,
                           "location_basis": location_basis})
    return sorted(result, key=lambda row: (row["distance_m"], row["name"]))


def distance_metres(lat1, lon1, lat2, lon2):
    a = math.sin(math.radians(lat2 - lat1) / 2) ** 2
    a += math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    return round(6371000 * 2 * math.asin(min(1, math.sqrt(a))))


def parse_places(content, page=1):
    response = response_json(content).get("response", {})
    if response.get("status") == "NOT_FOUND":
        return [], 0
    if response.get("status") != "OK":
        raise ValueError("VWorld 장소 검색 응답 확인 필요")
    try:
        total = int(response["record"]["total"])
        items = response["result"]["items"]
    except (KeyError, TypeError, ValueError):
        raise ValueError("VWorld 장소 검색 schema 변경") from None
    if isinstance(items, dict):
        items = items.get("item", [])
    if isinstance(items, dict):
        items = [items]
    expected = min(PAGE_SIZE, max(0, total - (page - 1) * PAGE_SIZE))
    if not isinstance(items, list) or total < 0 or page < 1 or len(items) != expected:
        raise ValueError("VWorld 장소 검색 페이지 불일치")
    return items, total


def mart_name(name):
    return re.sub(r"\s+|\(주\)|㈜|주식회사", "", name).replace("트레이더스홈세일", "트레이더스홀세일")


def is_large_mart(name, category):
    """VWorld uses several retail/permit categories for the same large store.

    Require a main-store name plus compatible category. Exclude SSM/convenience
    stores, tenants and station/parking POIs, even if a brand appears in them.
    This classifies the stored POI; it does not verify today's opening hours.
    """
    name = mart_name(name)
    if re.search(r"이마트24|에브리데이|익스프레스|메트로|노브랜드|롯데슈퍼|폐점|폐업|폐쇄|예정|주차|입구|버스|정류장|문화센터|문화비|도서", name):
        return False
    retail = any(word in category for word in ("대형마트", "대형할인", "슈퍼마켓", "판매시설",
        "기타식사용가공처리조리식품", "재해구호물자구매업체"))
    brand_store = re.fullmatch(r"(?:이마트(?:트레이더스)?|홈플러스|롯데마트(?:맥스)?|코스트코(?:코리아)?|"
        r"트레이더스(?:홀세일클럽|홈세일클럽)?|(?:농협)?하나로클럽)[가-힣A-Za-z0-9-]*점", name)
    generic_store = ("대형마트" in category or "대형할인" in category) and bool(re.search(r"마트|할인점|하나로클럽", name))
    return bool(retail and (brand_store or generic_store))


def normalize_place(item, kind, latitude, longitude, radius_metres=RADIUS_METRES):
    name = str(item.get("title") or "").strip()
    category = str(item.get("category") or "").strip()
    if not name:
        return None
    if kind == "subway" and ("철도/지하철" not in category or not name.endswith("역")):
        return None
    if kind == "bus" and (not category.endswith("버스정류장") or re.search(r"미정차|폐쇄|폐지|운행중지", name)):
        return None
    if kind == "school" and (not re.search(r"(초등학교|중학교|고등학교|초교|중교|고교)$", name)
                              or not any(word in category for word in ("초등학교", "중학교", "고등학교"))):
        return None
    if kind == "childcare" and ("어린이집" not in category or not name.endswith("어린이집") or re.search(r"폐원|폐쇄|예정", name)):
        return None
    if kind == "hospital" and (not category.startswith("병원") or not name.endswith("병원")):
        return None
    if kind == "mart" and not is_large_mart(name, category):
        return None
    try:
        point = item["point"]
        lat, lon = float(point["y"]), float(point["x"])
    except (KeyError, TypeError, ValueError):
        return None
    if not (33 <= lat <= 39 and 124 <= lon <= 132):
        return None
    distance = distance_metres(latitude, longitude, lat, lon)
    if distance > radius_metres:
        return None
    address = item.get("address") or {}
    if not isinstance(address, dict):
        address = {}
    return {"id": str(item.get("id") or ""), "kind": kind, "name": name,
            "category": category, "latitude": lat, "longitude": lon,
            "distance_m": distance, "address": str(address.get("road") or address.get("parcel") or "")}


def deduplicate_places(places):
    """Keep opposite-direction bus stops; other POIs retain name/proximity dedupe."""
    def canonical(name):
        return re.sub(r"\s+", "", name).replace("초교", "초등학교").replace("중교", "중학교").replace("고교", "고등학교")
    result=[]
    for row in places:
        if row['kind']=='bus':
            duplicate=any(other['kind']=='bus' and ((row['id'] and other['id']==row['id']) or
                (not row['id'] and not other['id'] and row['name']==other['name'] and row['latitude']==other['latitude'] and row['longitude']==other['longitude'])) for other in result)
        else:
            duplicate=any(other['kind']==row['kind'] and (mart_name(other['name']) if row['kind']=='mart' else canonical(other['name']))==(mart_name(row['name']) if row['kind']=='mart' else canonical(row['name'])) and
                distance_metres(other['latitude'],other['longitude'],row['latitude'],row['longitude'])<=150 for other in result)
        if not duplicate:result.append(row)
    return result


def merge_rail_stations(items,gtx_stations):
    """GTX is a rail line, not a separate facility class; keep its provenance."""
    result=[dict(row) for row in items]
    for gtx in gtx_stations:
        existing=next((r for r in result if r['kind']=='subway' and
            (r['id']==gtx['id'] or (r['name']==gtx['name'] and distance_metres(r['latitude'],r['longitude'],gtx['latitude'],gtx['longitude'])<=150))),None)
        if existing is None:result.append(dict(gtx))
        else:
            existing.update(line=gtx['line'],service_status=gtx['service_status'],service_status_source_url=gtx['service_status_source_url'],
                            location_basis='VWORLD_EXISTING_STATION_POI',category=existing['category']+' · '+gtx['line']+' 운영역')
    return result


class InfrastructureContext:
    def __init__(self):
        self._lock = threading.RLock()
        self._cache = {}
        self._key_locks = WeakValueDictionary()

    def get(self, block_id, service, anchor=None):
        cache_key=(block_id,anchor['latitude'],anchor['longitude'],anchor['coordinate_basis'],anchor['label']) if anchor else block_id
        with self._lock:
            key_lock=self._key_locks.setdefault(cache_key,threading.RLock())
        # A slow external lookup for one location must not block another
        # location or a previously collected result.
        with key_lock:
            cached = self._cache.get(cache_key)
            if cached and time.monotonic() - cached[0] < CACHE_SECONDS:
                return cached[1]
            if anchor:
                point=anchor
            else:
                locations = {"|".join((row["region"], row["district_key"], row["block"])): row for row in service.rows("block_location")}
                point = locations.get(block_id)
                if not point:raise ValueError("개별 위치가 검증된 블록이 아닙니다")
            latitude, longitude = point["latitude"], point["longitude"]
            source = next(row for row in SOURCES if row["id"] == "vworld")
            fetcher = Fetcher("vworld_infrastructure", service.data_dir / "raw")
            all_places = []
            try:
                api_key = key_for(source)
                rail_radius = RADIUS_METRES
                for kind, query in QUERIES:
                    # UI radius controls only presentation. Search farther when no
                    # nearby rail station exists, so a distant GTX cannot hide a
                    # closer conventional station outside the default radius.
                    for radius in ((RADIUS_METRES, 12000, 50000) if kind == "subway" else (RADIUS_METRES,)):
                        lat_delta = radius / 111320
                        lon_delta = radius / (111320 * math.cos(math.radians(latitude)))
                        bbox = f"{longitude-lon_delta:.7f},{latitude-lat_delta:.7f},{longitude+lon_delta:.7f},{latitude+lat_delta:.7f}"
                        params = {"key": api_key, "service": "search", "request": "search", "version": "2.0",
                                  "query": query, "type": "place", "bbox": bbox, "crs": "EPSG:4326",
                                  "size": PAGE_SIZE, "format": "json"}
                        first, total = parse_places(fetcher.get(SEARCH_URL, "json", params={**params, "page": 1},
                                                                headers={"Referer": "https://www.minslab.kr/poc/home/"}), 1)
                        if total > MAX_TOTAL_PER_QUERY:
                            raise ValueError("시설 검색 결과가 표시 한도를 초과합니다")
                        items = first
                        for page in range(2, math.ceil(total / PAGE_SIZE) + 1):
                            batch, page_total = parse_places(fetcher.get(SEARCH_URL, "json", params={**params, "page": page},
                                                                         headers={"Referer": "https://www.minslab.kr/poc/home/"}), page)
                            if page_total != total:
                                raise ValueError("시설 검색 중 원천 건수 변경")
                            items.extend(batch)
                        found = [p for item in items if (p := normalize_place(item, kind, latitude, longitude, radius))]
                        all_places.extend(found)
                        if kind == "subway":
                            rail_radius = radius
                        if found or (kind == "subway" and any(r["distance_m"] <= radius for r in nearby_gtx_stations(latitude, longitude))):
                            break
                manifest = [entry["sha256"] for entry in fetcher.manifest]
            finally:
                fetcher.close()
            all_places.sort(key=lambda row: (row["distance_m"], row["name"]))
            unique = deduplicate_places(all_places)
            counts = {kind: 0 for kind in DISPLAY_LIMITS}
            items = []
            for place in unique:
                kind = place["kind"]
                if counts[kind] >= DISPLAY_LIMITS[kind]:
                    continue
                counts[kind] += 1
                items.append(place)
            gtx_items = nearby_gtx_stations(latitude, longitude)
            items = merge_rail_stations(items, gtx_items)
            items.sort(key=lambda row: (row["distance_m"], row["name"]))
            counts["subway"] = sum(row["kind"] == "subway" for row in items)
            planned_gtx = []
            if point.get("district_key") == "고양창릉":
                planned_gtx.append({"line": "GTX-A", "name": "창릉역", "service_status": "PLANNED",
                                    "location_status": "UNLINKED", "source_url": GTX_A_PLANNED_URL})
            from .facility_plans import nearby_plans
            planned_facilities, plan_coverage = nearby_plans(latitude, longitude, distance_metres, district_key=point.get("district_key"))
            result = {"planned_facilities": planned_facilities, "plan_coverage_note": plan_coverage, "status": "READY", "block_id": block_id, "search_radius_metres": RADIUS_METRES,
                      "gtx_search_radius_metres": GTX_RADIUS_METRES,
                      "subway_search_radius_metres": rail_radius,
                      "gtx_status_source_url": GTX_A_STATUS_URL,
                      "gtx_location_source_url": SOURCE_URL,
                      "planned_gtx": planned_gtx,
                      "mart_note": "대형마트·창고형 매장 장소 정보 · 편의점/기업형 슈퍼/입점 매장 제외 · 영업 여부·시간은 별도 확인",
                      "bus_note": "정류장 위치 정보 · 노선·배차·실시간 도착 정보 아님 · 미정차 표기 제외",
                      "distance_basis": "블록 라벨점부터의 직선거리 · 도보/차량 이동거리 아님",
                      "source_url": SOURCE_URL, "source_name": "VWorld 국가관심지점 장소 검색",
                      "collected_at": datetime.now(ZoneInfo("Asia/Seoul")).date().isoformat(),
                      "source_sha256": manifest, "counts": counts, "items": items}
            result['origin']=anchor or dict(latitude=latitude,longitude=longitude,coordinate_basis='LH_PUBLIC_BLOCK_LABEL_POINT',label='LH 공개 블록 대표점',approximate=False,block_id=block_id)
            if anchor:result['distance_basis']=anchor['label']+'부터의 참고 직선거리 · 도보/차량 이동거리 아님'
            with self._lock:
                self._cache[cache_key] = (time.monotonic(), result)
                while len(self._cache)>64:self._cache.pop(next(iter(self._cache)),None)
            return result
