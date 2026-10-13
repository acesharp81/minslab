"""Stored approximate anchors. Never use these points to manufacture parcel IDs."""
import json
import math
import re
from sqlalchemy import text
from .api_samples import key_for,today


def representative_address(value):
    value=re.sub(r'\s*(?:일대|일원|인근)\s*$','',str(value or '')).strip()
    # Multiple representative lots: use the first lot, explicitly approximate.
    return re.sub(r'(\d+(?:-\d+)?)(?:번지)?\s*,.*',r'\1',value).replace('번지','')


def collect_locations(source,fetcher,service):
    projects=service.rows('project');places=service.rows('municipality')+service.rows('policy_municipality')
    documents={r['id']:r for kind in ('document_evidence','notice') for r in service.rows(kind)}
    linked={}
    for b in service.rows('evidence_bridge'):
        if b.get('status') in ('REVIEW','CONFIRMED') and b.get('source_entity_id') in documents:
            linked.setdefault(b['project_id'],[]).append(documents[b['source_entity_id']])
    old={r['project_id']:r for r in service.rows('project_location')}
    records=[];counts={'address_points':0,'area_points':0,'unlocated':0,'preserved':0};cache={}
    for p in projects:
        previous=old.get(p['id'])
        if previous and previous.get('status') in ('CONFIRMED','RELEASED'):
            counts['preserved']+=1;continue
        docs=linked.get(p['id'],[]);municipality=p.get('municipality')
        candidates={d.get('municipality') for d in docs if d.get('municipality')}
        if (not municipality or '확인' in municipality) and len(candidates)==1:municipality=candidates.pop()
        addresses={d['address'] for d in docs if d.get('address')}
        address=p.get('address') or (next(iter(addresses)) if len(addresses)==1 else None)
        if address and (not municipality or '확인' in municipality):
            hit=re.search(r'서울(?:특별시)?\s+([가-힣]+구)\s',address)
            if hit:municipality=hit[1]
        anchor=None;basis=None;evidence=None;query=representative_address(address)
        if query and re.search(r'\d',query):
            if query not in cache:
                try:
                    response=json.loads(fetcher.get('https://api.vworld.kr/req/address','json',params={
                        'service':'address','request':'getCoord','version':'2.0','crs':'EPSG:4326',
                        'address':query,'type':'PARCEL','format':'json','refine':'true','simple':'false','key':key_for(source)},
                        headers={'Referer':'https://www.minslab.kr/poc/home/'}))['response']
                    point=response.get('result',{}).get('point',{})
                    x,y=float(point['x']),float(point['y'])
                    cache[query]=(x,y) if 124<=x<=132 and 33<=y<=39 and all(map(math.isfinite,(x,y))) else None
                except Exception:cache[query]=None
            if cache[query]:
                anchor=cache[query];basis='APPROXIMATE_ADDRESS';evidence='https://www.vworld.kr/v4po_openapi_s001.do';counts['address_points']+=1
        matches=[r for r in places if r['region']==p['region'] and r['name']==municipality]
        if not anchor and matches:
            area=matches[0]
            if area.get('longitude') is not None and area.get('latitude') is not None:
                anchor=(area['longitude'],area['latitude'])
            elif area.get('geometry'):
                with service.engine.connect() as db:
                    point=db.scalar(text('SELECT ST_AsGeoJSON(ST_PointOnSurface(ST_MakeValid(ST_SetSRID(ST_GeomFromGeoJSON(:shape),4326))))'),{'shape':json.dumps(area['geometry'])})
                    anchor=json.loads(point)['coordinates']
            if anchor:basis='APPROXIMATE_AREA';evidence=area.get('evidence_url');counts['area_points']+=1
        if not anchor:counts['unlocated']+=1;continue
        records.append(('project_location',p['id'],dict(project_id=p['id'],name=p['name'],region=p['region'],municipality=municipality,
            longitude=anchor[0],latitude=anchor[1],coordinate_basis=basis,status='REVIEW',address_original=address,
            address_query=query if basis=='APPROXIMATE_ADDRESS' else None,
            location_label='대표 지번 근사 위치 · 사업 경계 아님' if basis=='APPROXIMATE_ADDRESS' else '시군구 대표점 · 사업 위치 상세 미확보',
            evidence_url=evidence,base_date=today().isoformat(),date_precision='COLLECTION',
            warnings=['APPROXIMATE_NOT_PARCEL','NO_PNU_INFERENCE'])))
    return records,dict(counts,complete_population=False,scope_note='원문 대표 지번 우선; 주소 미확보 시 소속 시군구 내부 대표점. 근사 위치를 필지/PNU나 사업 경계로 쓰지 않음')
