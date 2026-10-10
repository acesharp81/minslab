"""Official residential land geometry and reviewed district-level project links."""
import json
import re
from collections import defaultdict

from sqlalchemy import text

from .api_samples import key_for, response_json, today

DATA_URL = "https://api.vworld.kr/req/data"
LAYER = "LT_C_LHBLPN"


def district_term(row):
    if row.get("source_id") not in {"lh_sale","lh_rent","lh_construction","lh_history","lh_progress","lh_reit_progress"}:
        return None
    value = row.get("district") or row["name"]
    value = re.sub(r"\([^)]*(?:\)|$)","",value)
    value = re.split(r"\s*[A-Za-z]{1,3}\s*-?\s*\d|\s+주복\d|\s+0\d",value,maxsplit=1)[0]
    return value.strip()


def same_district(term, name):
    def normalize(value):
        value=re.sub(r"\s+","",value).replace("국제화계획","")
        return re.sub(r"(?:공공주택지구|공공지원민간임대주택공급촉진지구|택지개발사업|택지개발지구|지구)+$","",value)
    # A shared prefix is insufficient: 갈매 and 갈매역세권 are separate areas.
    return bool(normalize(term)) and normalize(term)==normalize(name)


def parse_page(data):
    response=data.get("response",{})
    if response.get("status")=="NOT_FOUND":
        return [],0
    if response.get("status")!="OK":
        raise ValueError("VWorld 공동주택용지 응답 확인 필요")
    try:
        total=int(response["record"]["total"])
        features=response["result"]["featureCollection"]["features"]
    except (KeyError,TypeError,ValueError):
        raise ValueError("VWorld 공동주택용지 schema 변경") from None
    if not isinstance(features,list) or not 0<=total<=10000:
        raise ValueError("VWorld 공간정보 건수·페이지 범위 확인 필요")
    for feature in features:
        if feature.get("geometry",{}).get("type") not in {"Polygon","MultiPolygon"} or not feature.get("properties",{}).get("zonename"):
            raise ValueError("공식 용지 도형·지구명 미확인")
    return features,total


def collect_districts(source,fetcher,service):
    projects=service.projects()
    reports=service.rows("project_report")
    terms=sorted({term for row in projects+reports if (term:=district_term(row))})
    zones=defaultdict(dict)
    missing=[]
    for term in terms:
        expected, seen, page = None,set(),1
        while True:
            params={"key":key_for(source),"service":"data","request":"GetFeature","version":"2.0","data":LAYER,
                    "attrFilter":"zonename:like:"+term,"geomFilter":"BOX(126.3,36.8,127.9,38.3)","crs":"EPSG:4326",
                    "size":1000,"page":page,"format":"json"}
            features,total=parse_page(response_json(fetcher.get(DATA_URL,"json",params=params,headers={"Referer":"https://www.minslab.kr/poc/home/"})))
            if expected is None:
                expected=total
            if total!=expected or len(features)!=min(1000,max(0,total-len(seen))):
                raise ValueError("VWorld 용지 페이지 누락·수집 중 건수 변경")
            for feature in features:
                identifier=feature.get("id")
                if not identifier or identifier in seen:
                    raise ValueError("VWorld 용지 식별자 누락·페이지 중복")
                seen.add(identifier)
                properties=feature["properties"]
                if properties.get("blocktype")=="공동주택" and same_district(term,properties["zonename"]):
                    zones[properties["zonename"]][identifier]=feature
            if len(seen)>=total:
                if not total:
                    missing.append(term)
                break
            page+=1
    records=[]
    for name,feature_map in sorted(zones.items()):
        linked=[row for row in projects if (term:=district_term(row)) and same_district(term,name)]
        historic=[row for row in reports if (term:=district_term(row)) and same_district(term,name)]
        if not linked and not historic:
            continue
        polygons=[]
        for feature in sorted(feature_map.values(),key=lambda feature:feature["id"]):
            geometry=feature["geometry"]
            polygons.extend(geometry["coordinates"] if geometry["type"]=="MultiPolygon" else [geometry["coordinates"]])
        geometry={"type":"MultiPolygon","coordinates":polygons}
        # Keep the official raw response; simplify only display geometry (~4 m).
        with service.engine.connect() as connection:
            result=connection.execute(text("""WITH shape AS (
                SELECT ST_MakeValid(ST_SetSRID(ST_GeomFromGeoJSON(:geometry),4326)) AS geom)
                SELECT ST_AsGeoJSON(ST_SimplifyPreserveTopology(geom,0.00004)) AS geometry,
                       ST_AsGeoJSON(ST_PointOnSurface(geom)) AS point FROM shape"""),{"geometry":json.dumps(geometry)}).mappings().one()
        point=json.loads(result["point"])["coordinates"]
        if not 126.3<=point[0]<=127.9 or not 36.8<=point[1]<=38.3:
            raise ValueError("공동주택용지 좌표·조회 범위 불일치")
        payload={"name":name,"geometry":json.loads(result["geometry"]),"longitude":point[0],"latitude":point[1],
                 "project_ids":sorted(row["id"] for row in linked),"regions":sorted({row["region"] for row in linked+historic}),
                 "historical_report_ids":sorted(row["id"] for row in historic),
                 "base_date":today().isoformat(),"date_precision":"COLLECTION","source_layer":LAYER,
                 "land_feature_count":len(feature_map),"coordinate_basis":"공식 지구 공동주택용지 대표 위치 · 개별 사업 블록 미확정",
                 "link_status":"REVIEW","evidence_url":"https://www.vworld.kr/v4po_openapi_s001.do","warnings":[],
                 "availability":"PUBLIC"}
        records.append(("district",name,payload))
    if not records:
        raise ValueError("연결 가능한 공식 공동주택용지 없음: 기존 지도 데이터 유지")
    return records,{"collection_mode":"MAP_LAYER","district_count":len(records),"queried_terms":len(terms),
                    "not_found_terms":missing,"linked_project_count":len({project for _,_,payload in records for project in payload["project_ids"]}),
                    "linked_historical_rows":len({report for _,_,payload in records for report in payload["historical_report_ids"]})}
