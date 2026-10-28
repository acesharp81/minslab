"""Bounded official API samples, separate from approved policy/project records."""
import json
import os
import re
from datetime import date, datetime
from urllib.parse import unquote
from zoneinfo import ZoneInfo

from .collectors import clean, integer
from .collection_period import annual_windows, collection_start

NOTICE_URL = "https://api.odcloud.kr/api/ApplyhomeInfoDetailSvc/v1/getAPTLttotPblancDetail"
PERMIT_URL = "https://apis.data.go.kr/1613000/HsPmsHubService/getHpBasisOulnInfo"
GEO_URL = "https://api.vworld.kr/req/address"
REGIONS = {"100": "서울특별시", "410": "경기도", "400": "인천광역시"}
DISTRICTS = [("서울특별시", "11680", "10300", "강남구 개포동"),
             ("서울특별시", "11740", "10200", "강동구 고덕동"),
             ("서울특별시", "11380", "11400", "은평구 진관동"),
             ("경기도", "41117", "10300", "수원시 영통구 이의동"),
             ("경기도", "41360", "11200", "남양주시 다산동"),
             ("경기도", "41450", "10800", "하남시 덕풍동")]
SAMPLE_LIMIT = 100  # API page size, independent of collection scope.


def today():
    return datetime.now(ZoneInfo("Asia/Seoul")).date()


def day(value):
    text = re.sub(r"[-./]", "", clean(value))
    if not re.fullmatch(r"\d{8}", text):
        return None
    try:
        return date(int(text[:4]), int(text[4:6]), int(text[6:])).isoformat()
    except ValueError:
        return None


def key_for(source):
    key = os.environ.get(source["key_env"], "").strip()
    if not key and source.get('fallback_key_env'):
        key = os.environ.get(source['fallback_key_env'], '').strip()
    if not key:
        raise ValueError("API 키 미설정: HOME .env와 실행 설정을 확인하세요")
    return unquote(key) if re.search(r"%[0-9a-fA-F]{2}", key) else key


def response_json(content):
    try:
        data = json.loads(content)
    except (ValueError, UnicodeDecodeError):
        raise ValueError("API JSON 응답 미확인: 인증·원천 상태 확인 필요") from None
    if not isinstance(data, dict):
        raise ValueError("API 응답 schema 변경")
    return data


def base(source, kind, name, region, address, source_date=None):
    return {"sample_kind": kind, "name": name, "region": region, "address": address, "units": None,
            "base_date": today().isoformat(), "date_precision": "COLLECTION", "base_date_basis": "표본 수집일 (원천 갱신일과 구분)",
            "source_date": source_date, "source_date_label": "원천 날짜", "sample_mode": "TEST_SAMPLE",
            "policy_mapping_status": "UNMAPPED", "availability": "PUBLIC", "warnings": [], "evidence_url": source["url"],
            "stage_label": "API 표본 · 정책/진행사업 연결 검토 전"}


def parse_notices(data, source, region_code, start, end):
    rows = data.get("data")
    if not isinstance(rows, list) or not isinstance(data.get("matchCount"), int):
        raise ValueError("청약홈 인증/응답 schema 확인 필요")
    if len(rows) > SAMPLE_LIMIT or data["matchCount"] < len(rows):
        raise ValueError("청약홈 표본 개수·페이지 불일치")
    records, seen = [], set()
    for row in rows:
        code = str(row.get("SUBSCRPT_AREA_CODE", ""))
        announced = day(row.get("RCRIT_PBLANC_DE"))
        if code != region_code or not announced or not start <= announced <= end:
            raise ValueError("청약홈 지역·공고 기간 필터 불일치")
        house, notice = clean(row.get("HOUSE_MANAGE_NO")), clean(row.get("PBLANC_NO"))
        name, address = clean(row.get("HOUSE_NM")), clean(row.get("HSSPLY_ADRES"))
        if not house or not notice or not name:
            raise ValueError("청약홈 공고 식별자 미확인")
        identifier = house + ":" + notice
        if identifier in seen:
            raise ValueError("청약홈 표본 공고 중복")
        seen.add(identifier)
        payload = base(source, "notice", name, REGIONS[code], address, announced)
        payload.update(source_object_id=identifier, house_manage_no=house, notice_no=notice,
                       units=integer(row.get("TOT_SUPLY_HSHLDCO")), unit_basis="모집공고 공급세대수 (사업 전체 목표 아님)",
                       source_date_label="모집공고일", developer=clean(row.get("BSNS_MBY_NM")), contractor=clean(row.get("CNSTRCT_ENTRPS_NM")),
                       dates={"청약 시작일": day(row.get("RCEPT_BGNDE")), "청약 종료일": day(row.get("RCEPT_ENDDE")),
                              "계약 시작일": day(row.get("CNTRCT_CNCLS_BGNDE")), "계약 종료일": day(row.get("CNTRCT_CNCLS_ENDDE"))},
                       move_in_plan_month=str(row.get("MVN_PREARNGE_YM", "")).strip() or None)
        records.append(("notice", identifier, payload))
    return records


def collect_notices(source, fetcher):
    start = collection_start().isoformat()
    end = today().isoformat()
    records, counts, annual_counts, global_seen = [], {}, [], set()
    for code, region in REGIONS.items():
        regional_total,regional_pages=0,0
        for period_start,period_end in annual_windows(today()):
            begin,finish=period_start.isoformat(),period_end.isoformat()
            expected, parsed, page = None, [], 1
            while True:
                params = {"serviceKey": key_for(source), "page": page, "perPage": SAMPLE_LIMIT,
                          "cond[SUBSCRPT_AREA_CODE::EQ]": code, "cond[RCRIT_PBLANC_DE::GTE]": begin, "cond[RCRIT_PBLANC_DE::LTE]": finish}
                data = response_json(fetcher.get(NOTICE_URL, "json", params=params))
                current = parse_notices(data, source, code, begin, finish)
                total = data["matchCount"]
                if expected is None: expected = total
                if total != expected or total > 10000 or len(current) != min(SAMPLE_LIMIT, max(0, total-len(parsed))):
                    raise ValueError("청약 공고 페이지 누락·수집 중 건수 변경")
                for record in current:
                    if record[1] in global_seen: raise ValueError("청약 공고 페이지·연도 간 중복")
                    global_seen.add(record[1])
                parsed.extend(current)
                if len(parsed) >= total: break
                page += 1
            records.extend(parsed)
            regional_total+=len(parsed);regional_pages+=page
            annual_counts.append({'year':period_start.year,'region':region,'period_start':begin,'period_end':finish,
                'matching_notices':expected,'pages':page,'complete_query':True,
                'status':'COLLECTED' if expected else 'NO_RESULTS_UNVERIFIED'})
        counts[region] = {"matching_notices": regional_total, "sampled": regional_total, "pages": regional_pages, "complete_query": True}
    if not records:
        raise ValueError("서울·경기 기간 내 공고 표본 없음: 기존 데이터 유지")
    return records, {"collection_mode": "TEST_SAMPLE", "complete_population": False, "page_size": SAMPLE_LIMIT,
                     "period_start": start, "period_end": end, "region_counts": counts,"annual_counts":annual_counts,
                     "scope_note":"정책 기원 연도부터 연도·지역별 전체 조회 페이지. API 미제공 연도와 정책 실적 0을 구분"}


def parse_permits(data, source, region, sigungu, bjdong):
    response = data.get("response", {})
    if str(response.get("header", {}).get("resultCode", "")) != "00":
        raise ValueError("건축HUB 인증/응답 오류: 활용승인·호출량 확인 필요")
    body = response.get("body")
    if not isinstance(body, dict) or "totalCount" not in body:
        raise ValueError("건축HUB 응답 schema 변경")
    items = body.get("items") or {}
    rows = items.get("item", []) if isinstance(items, dict) else None
    if isinstance(rows, dict):
        rows = [rows]
    if not isinstance(rows, list):
        raise ValueError("건축HUB 행 schema 변경")
    if len(rows) > SAMPLE_LIMIT or int(body["totalCount"]) < len(rows):
        raise ValueError("건축HUB 표본 개수·페이지 불일치")
    records, seen = [], set()
    for row in rows:
        address = clean(row.get("platPlc"))
        if str(row.get("sigunguCd")) != sigungu or str(row.get("bjdongCd")) != bjdong or not address.startswith(region):
            raise ValueError("건축HUB 법정동·지역 필터 불일치")
        identifier = clean(row.get("mgmHsrgstPk"))
        if not identifier or identifier in seen:
            raise ValueError("건축HUB PK 누락/중복")
        seen.add(identifier)
        payload = base(source, "permit", clean(row.get("bldNm")) or address, region, address, day(row.get("crtnDay")))
        payload.update(source_object_id=identifier, sigungu_code=sigungu, bjdong_code=bjdong,
                       units=integer(row.get("totHhldCnt")), unit_basis="원천 기본개요 총세대수 (중복·공급묶음 검토 전)",
                       main_purpose=clean(row.get('mainPurpsCdNm')) or None,block=clean(row.get('block')) or None,
                       lot=clean(row.get('lot')) or None,bun=clean(row.get('bun')) or None,ji=clean(row.get('ji')) or None,
                       source_date_label="원천 레코드 생성일", warnings=["USE_INSPECTION_FIELD_REVIEW"],
                       dates={"원천 허가일 (apprvDay)": day(row.get("apprvDay")), "원천 착공일 (stcnsDay)": day(row.get("stcnsDay")),
                              "원천 착공예정일 (stcnsSchedDay)": day(row.get("stcnsSchedDay")),
                              "사용검사 필드 useInsptDay": day(row.get("useInsptDay")),
                              "사용검사 필드 useInsptSchedDay": day(row.get("useInsptSchedDay"))})
        if payload["units"] == 0:
            payload["warnings"].append("ZERO_UNITS_REVIEW")
        from .parcel_identity import enrich_source
        enrich_source(payload, row)
        records.append(("permit", identifier, payload))
    return records, int(body["totalCount"])


def collect_permits(source, fetcher, service=None):
    records, counts = [], {}
    districts=DISTRICTS;scope_total=None
    if service is not None:
        from .building_scope import next_districts
        districts,counts,scope_total=next_districts(service,source['id'])
    configured=int(os.environ.get("POC10_PERMIT_DISTRICT_LIMIT", "0"))
    limit=10000 if configured==0 else max(10,min(10000,configured))
    for region, sigungu, bjdong, label in districts:
        parsed, expected, seen, page = [], None, set(), 1
        while True:
            params = {"serviceKey": key_for(source), "sigunguCd": sigungu, "bjdongCd": bjdong, "numOfRows": SAMPLE_LIMIT, "pageNo": page, "_type": "json"}
            current, total = parse_permits(response_json(fetcher.get(PERMIT_URL, "json", params=params)), source, region, sigungu, bjdong)
            if expected is None:
                expected = total
            if total>10000:
                raise ValueError("법정동별 인허가 10,000건 안전 범위 초과: 수집 범위 분할 필요")
            if total != expected or len(current) != min(SAMPLE_LIMIT, max(0,total-(page-1)*SAMPLE_LIMIT)):
                raise ValueError("건축HUB 페이지 누락·수집 중 건수 변경")
            for record in current:
                if record[1] in seen:
                    raise ValueError("건축HUB 페이지 간 중복")
                seen.add(record[1])
            parsed.extend(current[:max(0,limit-len(parsed))])
            if len(parsed) >= min(total,limit):
                break
            page += 1
        records.extend(parsed)
        counts[sigungu+bjdong if service is not None else label] = {"matching_records": expected, "sampled": len(parsed), "pages": page, "complete_query": len(parsed)==expected,"legal_dong_code":sigungu+bjdong,"label":label}
        if service is not None:
            from .db import now
            counts[sigungu+bjdong]['checked_at']=now().isoformat()
    if service is not None:
        from .building_scope import expansion_stats
        return records,dict(expansion_stats(counts,scope_total,len(records)),collection_mode='TEST_SAMPLE',complete_population=False,
            period_start=collection_start().isoformat(),period_end=today().isoformat())
    if not records:
        raise ValueError("인허가 표본 없음: 기존 데이터 유지")
    return records, {"collection_mode": "TEST_SAMPLE", "complete_population": False, "sample_per_district": configured or None,
                     "period_start":collection_start().isoformat(),"period_end":today().isoformat(),
                     "district_counts": counts, "scope_note": "서울·경기 6개 법정동 전체 페이지(기본). 과거 허가·착공일도 보존하며 생성일과 실제 사업 상태는 별도 확인"}


def location_candidates(service):
    """Stream only identity/address columns; permit payloads can be very large."""
    from sqlalchemy import select, case
    from .db import Revision
    p=Revision.payload
    address=p['address'].as_string()
    query=select(Revision.entity_id.label('id'),Revision.kind.label('sample_kind'),
        p['name'].as_string().label('name'),p['region'].as_string().label('region'),
        p['source_object_id'].as_string().label('source_object_id'),address.label('address')).where(
        Revision.kind.in_(('notice','permit')),Revision.superseded_at.is_(None),address.is_not(None),address!='').order_by(
        case({region:i for i,region in enumerate(REGIONS.values())},value=p['region'].as_string(),else_=99),
        Revision.kind,p['source_object_id'].as_string(),Revision.entity_id).execution_options(yield_per=500)
    with service.sessions() as db:
        for row in db.execute(query).mappings():
            yield row


def collect_locations(source, fetcher, service):
    inputs, seen = [], set()
    previous = service.rows('location')
    cache = {(r.get('parent_sample_id'),r.get('address')) for r in previous}
    limit = max(1, min(25, int(os.environ.get("POC10_GEOCODE_PER_KIND_REGION", "25"))))
    pending=0;candidate_count=0;selected={}
    for row in location_candidates(service):
        candidate_count+=1;address=row['address'];group=(row['region'],row['sample_kind'])
        if (row['id'],address) in cache:continue
        pending+=1
        if row['region'] not in REGIONS.values() or address in seen or selected.get(group,0)>=limit:continue
        seen.add(address);inputs.append(dict(row));selected[group]=selected.get(group,0)+1
    if not inputs:
        if not previous: raise ValueError("좌표 조회 대상 없음: 청약홈·건축HUB 표본을 먼저 수집하세요")
        metadata={'id','source_id','revision_no','recorded_at','source_age_days'}
        preserved=[('location',r['parent_sample_id'],{k:v for k,v in r.items() if k not in metadata})
                   for r in previous if r.get('parent_sample_id')]
        return preserved,dict(collection_mode='TEST_SAMPLE',complete_population=False,complete_query=pending==0,
            queried=0,resolved=0,not_found=0,remaining_parents=pending,cached_parents=len(cache),
            scope_note='이전 조회 주소를 건너뛰는 누적 수집. 동일 주소의 NOT_FOUND 재검토는 별도 필요')
    records, resolved = [], 0
    for row in inputs:
        original = row["address"]
        address = re.sub(r"\([^)]*\)", "", original)
        address = clean(re.sub(r"\s+일원.*$", "", address))
        address_type = "ROAD" if re.search(r"(?:로|길)\s*\d", address) else "PARCEL"
        params = {"key": key_for(source), "service": "address", "request": "getcoord", "version": "2.0", "crs": "EPSG:4326",
                  "format": "json", "type": address_type, "address": address, "domain": "https://www.minslab.kr"}
        data = response_json(fetcher.get(GEO_URL, "json", params=params, headers={"Referer": "https://www.minslab.kr/poc/home/"})).get("response", {})
        if data.get("status") not in {"OK", "NOT_FOUND"}:
            raise ValueError("VWorld 인증/응답 오류: 키·허용 도메인 확인 필요")
        payload = base(source, "location", row["name"], row["region"], original)
        payload.update(source_object_id=row["id"], parent_sample_id=row["id"], parent_kind=row["sample_kind"],
                       query_address=address, resolution_status=data["status"], longitude=None, latitude=None,
                       coordinate_basis="주소검색 좌표 (사업구역·블록 경계 아님)", units=None)
        if address != original or "일원" in original:
            payload["warnings"].append("ADDRESS_APPROXIMATE")
        if data["status"] == "OK":
            point = data.get("result", {}).get("point", {})
            try:
                lon, lat = float(point["x"]), float(point["y"])
            except (ValueError, KeyError, TypeError):
                raise ValueError("VWorld 좌표 schema 변경") from None
            refined_region = data.get("refined", {}).get("structure", {}).get("level1")
            if not (124 <= lon <= 132 and 33 <= lat <= 39) or (refined_region and refined_region != row["region"]):
                raise ValueError("VWorld 좌표·정제주소 지역 불일치")
            payload.update(longitude=lon, latitude=lat)
            resolved += 1
        else:
            payload["warnings"].append("GEOCODE_NOT_FOUND")
        records.append(("location", row["id"], payload))
    return records, {"collection_mode": "TEST_SAMPLE", "complete_population": False, "complete_query":pending==len(inputs),
        "queried": len(inputs), "resolved": resolved, "not_found": len(inputs)-resolved,
        "candidate_parent_count":candidate_count,"cached_parents":len(cache),"remaining_parents":pending-len(inputs),
        "scope_note":f"기존 조회 주소를 건너뛰고 유형·시도별 최대 {limit}건씩 누적. 사업 경계·전체 좌표 확보 아님"}


def collect_sample(source, fetcher, service):
    from .additional_apis import collect_register, collect_lh_notices, collect_statistics
    from .sh_apis import collect_sh
    if source["id"] in {"sh_supply_plan", "sh_redevelopment"}:
        return collect_sh(source, fetcher)
    additional = {"building_register": collect_register, "lh_notice": collect_lh_notices, "molit_statistics": collect_statistics}
    if source["id"] in additional:
        return collect_register(source,fetcher,service) if source["id"]=="building_register" else additional[source["id"]](source, fetcher)
    if source["id"] == "cheongyak":
        return collect_notices(source, fetcher)
    if source["id"] == "building_hub":
        return collect_permits(source, fetcher, service)
    if source["id"] == "vworld":
        return collect_locations(source, fetcher, service)
    raise ValueError("지원하지 않는 테스트 원천")
