"""Persist completed regional read models; requests never build these datasets."""
from collections import OrderedDict
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
from threading import RLock
from time import sleep
from .api_samples import today
from .projection_cache import projection_version, COLLECTION_REVISION_KINDS, RAW_BUILDING_KINDS
from .read_scope import projection_reads

REGIONS=('서울특별시','경기도','인천광역시')
FORMAT=1
CHECK_SECONDS=300
MAX_AGE_SECONDS=21600
KINDS=tuple(sorted(set(COLLECTION_REVISION_KINDS)-set(RAW_BUILDING_KINDS)|{
    'area_stat','area_benchmark','area_living','living_stat','unsold','statistic','statistic_reference'}))

def folder(service):return Path(service.data_dir)/'runtime/area-snapshots'
def file_path(service,year):return folder(service)/f'area-{int(year)}.json'
def stamp(service):
    version=projection_version(service,KINDS,batch_sources=(),audit_actions=())
    return hashlib.sha256(repr((FORMAT,today(),version)).encode()).hexdigest()

def atomic_json(path,data):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_name(path.name+'.'+str(os.getpid())+'.tmp')
    try:
        temp.write_text(json.dumps(data,ensure_ascii=False,separators=(',',':')))
        os.replace(temp,path)
    finally:
        if temp.exists():temp.unlink()

def build_year(service,year,places=None):
    from .area_stats import area_context,area_places
    from .area_outlook import area_outlook
    from .annual_supply import annual_supply
    places=places or area_places(service);contexts={};annual={};outlooks={}
    with projection_reads():
        for region in REGIONS:
            contexts[region]={'':area_context(service,region,None,year)}
            annual[region]=annual_supply(service,region,year)
            if year==today().year:outlooks[region]=area_outlook(service,region)
            for municipality in places['regions'].get(region,[]):
                contexts[region][municipality]=area_context(service,region,municipality,year)
                sleep(.01)  # Bound background CPU/DB pressure while warming all municipalities.
    return dict(format=FORMAT,year=year,places=places,contexts=contexts,annual=annual,outlooks=outlooks,
                generated_at=datetime.now(timezone.utc).isoformat())

class SnapshotStore:
    """Small, bounded file cache, refreshed on atomic replacement, including after restart."""
    def __init__(self,service):self.service=service;self.cache=OrderedDict();self.lock=RLock()
    def read(self,year):
        path=file_path(self.service,year)
        try:
            stat=path.stat();key=(year,stat.st_mtime_ns,stat.st_size)
            with self.lock:
                if key not in self.cache:
                    data=json.loads(path.read_text())
                    if data.get('format')!=FORMAT or data.get('year')!=year:return None
                    self.cache[key]=data
                    while len(self.cache)>3:self.cache.popitem(last=False)
                self.cache.move_to_end(key)
                return self.cache[key]
        except (OSError,ValueError,TypeError):return None
    def health(self):
        try:return json.loads((folder(self.service)/'health.json').read_text())
        except (OSError,ValueError):return {}
    def bundle(self,region,municipality,year):
        data=self.read(year)
        if data is None:return None
        if region not in REGIONS or (municipality or '') not in data['contexts'][region]:
            raise ValueError('해당 지역의 저장된 자료가 없습니다. 시군구 선택을 확인하세요.')
        health=self.health();generated=datetime.fromisoformat(data['generated_at'])
        return dict(data=data['contexts'][region][municipality or ''],
            regions={r:data['contexts'][r][''] for r in REGIONS},supply=data['annual'][region],
            outlook=data['outlooks'].get(region),places=data['places'],
            snapshot=dict(generated_at=data['generated_at'],source_checked_at=health.get('source_checked_at'),
                refresh_interval_seconds=CHECK_SECONDS,max_refresh_seconds=MAX_AGE_SECONDS,
                refreshing=health.get('status')=='BUILDING',refresh_failed=bool(health.get('last_error')),
                stale=(datetime.now(timezone.utc)-generated).total_seconds()>MAX_AGE_SECONDS+3600,
                basis='내부 DB의 수집 원천으로 미리 계산한 자료. 실제 자료 기준일은 각 그래프에 표기합니다.'))

def refresh(service,state=None,stop=None,years=None):
    """Only replace a year after a complete build and unchanged committed inputs."""
    from .area_stats import area_places
    state=state if state is not None else {};store=SnapshotStore(service)
    version=stamp(service);places=area_places(service)
    state.update(source_checked_at=datetime.now(timezone.utc).isoformat(),last_error=None)
    years=years if years is not None else range(today().year,2017,-1)
    done=[]
    for year in years:
        if stop and stop.is_set():break
        previous=store.read(year)
        if previous and previous.get('version')==version and (datetime.now(timezone.utc)-datetime.fromisoformat(previous['generated_at'])).total_seconds()<MAX_AGE_SECONDS:continue
        state.update(status='BUILDING',building_year=year)
        result=build_year(service,year,places)
        if stamp(service)!=version:
            state.update(status='RETRYING',last_error='SOURCE_CHANGED_DURING_BUILD')
            return done  # Never publish mixed source versions; keep the last good file.
        result['version']=version;atomic_json(file_path(service,year),result);done.append(year)
    state.update(status='READY',building_year=None,last_success_at=datetime.now(timezone.utc).isoformat())
    return done
