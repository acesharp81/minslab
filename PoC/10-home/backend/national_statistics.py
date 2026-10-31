"""Replay preserved MOLIT responses for the 14 previously discarded provinces.
No keys or new API calls are required. Capital observations keep their existing
source identifiers so the same province/month is never counted twice.
"""
from .raw_archive import read_raw
import hashlib
import json
from collections import Counter
from urllib.parse import urlsplit, parse_qs
from sqlalchemy import select
from .db import Batch
from .additional_apis import parse_statistics, STAT_SERIES

REGION_NAMES = {'서울':'서울특별시','경기':'경기도','인천':'인천광역시','부산':'부산광역시','대구':'대구광역시',
    '광주':'광주광역시','대전':'대전광역시','울산':'울산광역시','세종':'세종특별자치시','강원':'강원특별자치도',
    '충북':'충청북도','충남':'충청남도','전북':'전북특별자치도','전남':'전라남도','경북':'경상북도','경남':'경상남도','제주':'제주특별자치도'}
CAPITAL = ('서울특별시','경기도','인천광역시')

def replay(service, source, fetcher):
    with service.sessions() as db:
        batch=db.scalar(select(Batch).where(Batch.source_id=='molit_statistics',Batch.status=='SUCCESS').order_by(Batch.finished_at.desc()))
        if not batch:raise ValueError('국토부 공식 통계 원본 수집이 먼저 필요합니다')
        manifest=list(batch.manifest);upstream=batch.id
    spec=dict(source,stat_regions={k:v for k,v in REGION_NAMES.items() if v not in CAPITAL},all_regions=True)
    records=[];seen=set();files=[]
    for item in manifest:
        q=parse_qs(urlsplit(item.get('url','')).query)
        if not all(k in q for k in ('form_id','style_num','start_dt','end_dt')):continue
        series=next((s for s in STAT_SERIES if s[:2]==(q['form_id'][0],q['style_num'][0])),None)
        if not series:continue
        path=service.data_dir/'raw'/item['file'];content=read_raw(path)
        if hashlib.sha256(content).hexdigest()!=item['sha256']:raise ValueError('원본 무결성 검증 실패')
        data=json.loads(content)
        current=parse_statistics(data,spec,series,q['start_dt'][0],q['end_dt'][0])
        for kind,key,payload in current:
            if key in seen:raise ValueError('전국 통계 재처리 기간 중복')
            seen.add(key);payload.update(upstream_batch_id=upstream,raw_sha256=item['sha256'],raw_region_name=next(k for k,v in REGION_NAMES.items() if v==payload['region']),
                geography_note='현재 시도 명칭으로 정규화 · 원천 지역명 별도 보존 · 9·7 정책 귀속 아님')
            records.append((kind,key,payload))
        files.append(item)
    if not records:raise ValueError('보관 원본에서 추가 시도 통계를 찾지 못했습니다')
    fetcher.manifest.extend(files)
    return records,dict(upstream_batch_id=upstream,replayed_files=len(files),region_counts=dict(Counter(r[2]['region'] for r in records)),
        metric_counts=dict(Counter(r[2]['statistic_metric'] for r in records)),complete_population=False,
        scope_note='국토부 기존 원본의 비수도권 14개 시도 총계 재처리. 수도권 원천과 분리. 전국 사업 목록 확보를 의미하지 않음')
