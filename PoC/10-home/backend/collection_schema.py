"""Collected field provenance for linked projects, plus all collected document publishers."""
from collections import defaultdict
from datetime import date, datetime
from urllib.parse import urlsplit
from sqlalchemy import select
from .db import Revision
from .source_authority import authority, LABELS, public_url, publisher_name
from .collection_exports import STAGES, csv_text
from .sources import SOURCES
from .read_scope import projection_reads

ORDER={'OFFICIAL':0,'NONOFFICIAL':1,'INTERNAL':2,'UNKNOWN':3}

def document_sources(service):
    groups={}
    with service.sessions() as db:
        query=select(Revision.entity_id,Revision.source_id,Revision.payload,Revision.recorded_at).where(
            Revision.kind=='document_evidence',Revision.superseded_at.is_(None)).execution_options(yield_per=64)
        for eid,sid,p,recorded_at in db.execute(query):
            url=public_url(p.get('evidence_url') or p.get('source_url'));host=urlsplit(url).hostname or '출처 미기재'
            kind=authority(url,sid);key=(kind,host)
            item=groups.setdefault(key,dict(id='document:'+kind+':'+host,name=publisher_name(url)+' · 수집 문서',org=publisher_name(url),
                url=url,authority=kind,authority_label=LABELS[kind],type='DOCUMENT',data_type_label='수집 문서',
                collection_mode='PUBLIC_DOCUMENT',status='REGISTERED',record_count=0,last_success=None,last_recorded_at=None,stats={},snapshots=[],
                virtual=True,description='수집·검토한 문서 원천. 정책 귀속이나 실적 채택 여부와 별개입니다.'))
            item['record_count']+=1
            stamp=recorded_at.isoformat()
            if not item['last_recorded_at'] or stamp>item['last_recorded_at']:item['last_recorded_at']=stamp
    return sorted(groups.values(),key=lambda r:(ORDER[r['authority']],r['name']))

def build(service,matrix):
    catalog={s['id']:s for s in SOURCES};fields={}
    def add(stage,field,label,path,value,source,identity,url='',name='',basis='사업 연결 원천'):
        if value is None or value=='' or value==[] or value=={}:return
        url=public_url(url or catalog.get(source,{}).get('url'))
        classification=authority(url,source)
        if classification=='INTERNAL':return  # Officer estimates are not collection.
        key=(stage,field);item=fields.setdefault(key,dict(stage=stage,field=field,label=label,path=path,sources={}))
        source_key=(source,classification,urlsplit(url).hostname or '')
        entry=item['sources'].setdefault(source_key,dict(source_id=source,name=catalog.get(source,{}).get('name') or publisher_name(url,name),
            authority=classification,authority_label=LABELS[classification],url=url,identities=set(),basis=basis))
        entry['identities'].add(str(identity))
    reference=date.fromisoformat(matrix['as_of_date']);ids={r['id'] for r in matrix['items']}
    with projection_reads():
        for p in service.policy_rows(reference):
            if p.get('policy_id') not in {r.get('policy_id') for r in matrix['items']}:continue
            for field,label in [('name','정책명'),('announced_at','정책 발표일'),('period_start','정책 시작일'),('period_end','정책 종료일'),('target_units','정책 목표 호수')]:
                add('POLICY',field,label,'policy.'+field,p.get(field),p.get('source_id',''),p.get('id'),p.get('evidence_url'))
        for p in service.rows('project',reference):
            if p['id'] not in ids:continue
            for field,label in [('name','사업명'),('program','사업 분류'),('developer','시행자'),('planned_units','사업 계획 호수'),
                                ('region','시도'),('municipality','시군구'),('address','주소'),('tenure','공급 형태')]:
                add('BUSINESS',field,label,'project.'+field,p.get(field),p['source_id'],p['id'],p.get('evidence_url'))
        for p in matrix['items']:
            for stage,cell in p['cells'].items():
                for r in cell.get('sources',[]):
                    sid=r.get('source_id','')
                    if sid in ('officer','manual_delivery','manual_project') or r.get('inferred') or r.get('method') in ('PREREQUISITE','STAGE_INFERENCE'):continue
                    if r.get('kind') in ('LINK','PLAN_STATUS'):continue
                    target='COMPLETION' if r.get('milestone')=='COMPLETION' else stage
                    identity=r.get('source_entity_id') or (p['id'],stage,r.get('kind'),r.get('date'))
                    planned=r.get('kind')=='PLAN';prefix='예정 ' if planned else ''
                    for field,label in [('date',prefix+'일자'),('units',prefix+'호수'),('pct','관측 공정률')]:
                        add(target,('plan_' if planned else '')+field,label,'stage_source.'+field,r.get(field),sid,identity,
                            r.get('evidence_url'),r.get('name'))
    stages=[]
    for stage,label in STAGES.items():
        entries=[]
        for (key,field),entry in fields.items():
            if key!=stage:continue
            sources=[]
            for s in entry['sources'].values():
                sources.append({k:v for k,v in s.items() if k!='identities'}|{'count':len(s['identities'])})
            entries.append({k:v for k,v in entry.items() if k!='sources'}|{'sources':sorted(sources,key=lambda s:(ORDER[s['authority']],s['name']))})
        stages.append(dict(id=stage,label=label,fields=entries))
    return dict(as_of_date=matrix['as_of_date'],generated_at=datetime.now().astimezone().isoformat(),stages=stages,
        project_count=len(ids),document_sources=document_sources(service),
        scope='9·7 정책 연결 사업의 수집 원천 항목. 담당자 추정·수기 입력은 수집 건수에서 제외합니다.',
        count_note='괄호는 해당 항목을 확보한 서로 다른 원천 기록 건수입니다. 호수·전체 API 수집량이 아닙니다. 같은 기록이 여러 항목에 포함되므로 항목별 건수를 합산하지 않습니다.')

def export(data):
    rows=[]
    for stage in data['stages']:
        for field in stage['fields']:
            for s in field['sources']:
                rows.append([data['as_of_date'],stage['label'],field['label'],field['path'],s['authority_label'],s['source_id'],s['name'],s['count'],'원천 기록 건',s['url'],data['scope']])
    return csv_text(['기준일','단계','수집 항목','스키마 경로','출처 구분','출처ID','출처명','확보 건수','단위','근거 URL','집계 범위'],rows)
