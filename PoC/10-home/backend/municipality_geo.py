"""Official Seoul boroughs / Gyeonggi cities and counties, without name guesses."""
import json
import re
from collections import defaultdict

from sqlalchemy import text

from .api_samples import key_for, response_json, today
from .map_data import DATA_URL

LAYER = "LT_C_ADSIGG_INFO"


def municipal_name(region, name):
    if region == "서울특별시":
        return name if re.fullmatch(r"[가-힣]+구",name or "") else None
    if region == "경기도":
        found = re.match(r"^([가-힣]+?[시군])(?:\s|$)",name or "")
        return found[1] if found else None
    return None


def parse_boundaries(data):
    response=data.get("response",{})
    if response.get("status") != "OK":
        raise ValueError("VWorld 시군구 경계 응답 확인 필요")
    try:
        features=response["result"]["featureCollection"]["features"]
        total=int(response["record"]["total"])
    except (KeyError,TypeError,ValueError):
        raise ValueError("VWorld 시군구 경계 schema 확인 필요") from None
    if not isinstance(features,list) or total != len(features) or not 1 <= total <= 1000:
        raise ValueError("VWorld 시군구 경계 페이지 누락·범위 확인 필요")
    grouped=defaultdict(list)
    seen=set()
    for feature in features:
        properties=feature.get("properties",{})
        code=str(properties.get("sig_cd") or "")
        if code in seen or not re.fullmatch(r"\d{5}",code):
            raise ValueError("VWorld 시군구 코드 중복·형식 확인 필요")
        seen.add(code)
        region={"11":"서울특별시","41":"경기도"}.get(code[:2])
        if not region:continue
        name=municipal_name(region,properties.get("sig_kor_nm"))
        if not name or feature.get("geometry",{}).get("type") not in {"Polygon","MultiPolygon"}:
            raise ValueError("VWorld 시군구 명칭·도형 확인 필요")
        grouped[(region,name)].append(feature)
    # Cover the entire selected jurisdiction, not a partial viewport sample.
    counts={region:sum(key[0]==region for key in grouped) for region in ("서울특별시","경기도")}
    if counts != {"서울특별시":25,"경기도":31}:
        raise ValueError("서울·경기 시군구 경계 모집단 변경·누락 확인 필요")
    return grouped


def collect_municipalities(source,fetcher,service):
    params={"key":key_for(source),"service":"data","request":"GetFeature","version":"2.0","data":LAYER,
            "geomFilter":"BOX(126.3,36.8,127.9,38.3)","crs":"EPSG:4326","size":1000,"page":1,"format":"json"}
    groups=parse_boundaries(response_json(fetcher.get(DATA_URL,"json",params=params,headers={"Referer":"https://www.minslab.kr/poc/home/"})))
    districts=service.rows("district")
    records=[]
    for (region,name),features in sorted(groups.items()):
        polygons=[]
        for feature in features:
            geometry=feature["geometry"]
            polygons.extend(geometry["coordinates"] if geometry["type"]=="MultiPolygon" else [geometry["coordinates"]])
        geometry=json.dumps({"type":"MultiPolygon","coordinates":polygons})
        with service.engine.connect() as connection:
            shape=connection.execute(text("""WITH shape AS (
                SELECT ST_UnaryUnion(ST_MakeValid(ST_SetSRID(ST_GeomFromGeoJSON(:geometry),4326))) geom)
                SELECT ST_AsGeoJSON(ST_SimplifyPreserveTopology(geom,0.0001)) geometry,
                       ST_AsGeoJSON(ST_PointOnSurface(geom)) point FROM shape"""),{"geometry":geometry}).mappings().one()
            linked=[]
            for district in districts:
                covered=connection.scalar(text("SELECT ST_Covers(ST_SetSRID(ST_GeomFromGeoJSON(:geometry),4326), ST_SetSRID(ST_MakePoint(:lon,:lat),4326))"),
                    {"geometry":geometry,"lon":district["longitude"],"lat":district["latitude"]})
                if covered:linked.append(district["name"])
        point=json.loads(shape["point"])["coordinates"]
        records.append(("municipality",region+"|"+name,{"name":name,"region":region,
            "admin_codes":sorted(feature["properties"]["sig_cd"] for feature in features),"geometry":json.loads(shape["geometry"]),
            "longitude":point[0],"latitude":point[1],"district_names":sorted(linked),
            "source_layer":LAYER,"base_date":today().isoformat(),"date_precision":"COLLECTION",
            "coordinate_basis":"공식 시군구 경계 대표점 · 지구 대표점 연결은 검토",
            "evidence_url":"https://www.vworld.kr/v4po_openapi_s001.do","link_status":"REVIEW","warnings":[]}))
    return records,{"municipality_count":len(records),"administrative_feature_count":sum(map(len,groups.values())),"collection_mode":"MUNICIPALITY_LAYER"}
