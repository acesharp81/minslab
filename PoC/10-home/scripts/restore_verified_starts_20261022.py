"""Restore two lost starts using independently checked official evidence."""
import argparse
from copy import deepcopy
import hashlib,json,re
from pathlib import Path
from urllib.request import urlopen
from bs4 import BeautifulSoup
from pypdf import PdfReader
from sqlalchemy import select,text
from backend.db import Audit,Revision,entity_id,engine_for,now,upsert_revision
from backend.service import HomeService
from backend.project_collection import collection_matrix
from backend.measurement_estimates import reconcile,goals_from_cells
BATCH='verified-starts-20261022';ACTOR='담당자 대행 · 기존 채택 근거 원문 재검증'
OUT=Path('data/remediation/verified-starts-20261022')
URL='https://record.icouncil.go.kr/vod/viewer.do?cvUid=856&seek=2384'
GH_HASH='5709a83d392213db801fb1adb2bb192a04d705e21ba1638bda3362917efd7431'
NOTICE_HASH='0b1c9e3cb06d5892b28f11c3577558a16e73a714d45c2e0dd12ed5e026466f8f'

def current(db,eid):return db.scalar(select(Revision).where(Revision.entity_id==eid,Revision.superseded_at.is_(None)))

def prepare(s):
    raw=OUT/'icouncil-20240614.html'
    if not raw.exists():
        raw.write_bytes(urlopen(URL,timeout=40).read())
    txt=BeautifulSoup(raw.read_bytes(),'html.parser').get_text(' ',strip=True);compact=re.sub(r'\s+','',txt)
    assert all(t in compact for t in ['2024-06-14','AA10-1BL','1458세대','작년11월','8.94%'])
    cert=Path('data/raw/gh_completion_evidence')/(GH_HASH+'.pdf');assert hashlib.sha256(cert.read_bytes()).hexdigest()==GH_HASH
    main=Path('data/raw/gh_notice')/(NOTICE_HASH+'.pdf');assert hashlib.sha256(main.read_bytes()).hexdigest()==NOTICE_HASH
    notice_text=PdfReader(main).pages[0].extract_text();assert all(t in notice_text for t in ['417-2','316','통합공공임대'])
    records=[
      dict(pid='PRO_f6263baf545293a2283f4ad1',key='geomdan-aa10-1',units=1458,stage='CONSTRUCTION',date='2024-06-14',date_basis='OBSERVED_BY',url=URL,
        source_date='2024-06-14',source_event_month='2023-11',original_file=str(raw.relative_to('data')),sha256=hashlib.sha256(raw.read_bytes()).hexdigest(),
        reason='기존 iH 사업일정 채택 사유를 공식 시의회 2024-06-14 보고와 대조: AA10-1BL 1458세대, 전년 11월 착공 및 4월 말 공정률8.94% 명시. 착공 도달은 확인, 정확한 일자는 미제시. 기존 2023-11-30은 월말 관리 추정일로 복구. 준공·공급은 이 자료로 확정하지 않음'),
      dict(pid='PRO_e57577ac296a4798617e617b',key='gwangju-completion',units=316,stage='COMPLETION',date='2026-09-16',date_basis='EVENT',
        url='https://apply.gh.or.kr/cs/sr/sr7900/selectNoticeDetailView.do?bbsSn=111',source_date='2026-09-28',original_file=str(cert.relative_to('data')),sha256=GH_HASH,
        reason='수집된 사용검사 확인증 이미지 직접 검토: 2026-09-16, 광주시 역동417-2, GH biz& 경기광주역, 주택건설사업 전체 검사. GH 최초 모집공고742의 동일 소재지·통합공공임대316호와 대조하여 기존 원장 범위에 연결. 확인증 세대수 칸은 공란으로 316호를 증서 직접 기재값이라 주장하지 않음. 기존 공공임대(오피스텔) 분류·물량 보존. 준공 확인으로 선행 착공 관리 추정 복구; 입주 실적 생성 없음',
        scope_source_id='DOC_08f4537ab922a0d7fa8c8e0a',scope_source_sha256=NOTICE_HASH,
        visual_review=dict(date='2026-09-16',address='경기도 광주시 역동 417-2',scope='주택건설사업 전체',permit_no='2023-주택정책과-주택건설사업계획승인-2',units_on_certificate=None))]
    ps={p['id']:p for p in s.projects()};cells={p['id']:p['cells'] for p in collection_matrix(s,policy_id='POL_2025_0907',include_link_history=False)['items']}
    items=[]
    with s.sessions() as db:
      for r in records:
        p=ps[r['pid']];assert p['planned_units']==r['units'] and p['mapping']['status']=='CONFIRMED'
        prior=current(db,entity_id('project_profile','manual_project',r['pid']));assert not prior.payload.get('progress',{}).get('CONSTRUCTION')
        r.update(name=p['name'],project_revision_id=p['source_revision_id'],expected_profile_revision_id=prior.id,
                 before=deepcopy(prior.payload),mapping_revision_no=p['mapping']['revision_no'])
        sid=entity_id('document_evidence','official_document',BATCH+':'+r['key'])
        fact=dict(stage=r['stage'],milestone=r['stage'],kind='ACTUAL',date=r['date'],units=r['units'],date_basis=r['date_basis'],
          observed_on=r['date'] if r['date_basis']=='OBSERVED_BY' else None,source_event_month=r.get('source_event_month'),
          basis=r['reason'],scope_partial=False,scope_units=r['units'],source_id='official_document',source_entity_id=sid,review_status='CONFIRMED')
        c=deepcopy(cells[r['pid']]);c['CONSTRUCTION']['sources'].append(fact)
        result=reconcile(prior.payload.get('progress',{}),goals_from_cells(c),c,'2026-10-22',scope_limit=r['units'])
        stages=['CONSTRUCTION']+(['COMPLETION'] if r['stage']=='COMPLETION' else [])
        after=deepcopy(prior.payload)
        for st in stages:
          v=result['progress'][st];assert v['units']==r['units'] and v['event_date']
          after.setdefault('progress',{})[st]=dict(v,origin='MANUAL',actor=ACTOR,reason=r['reason'],evidence_url=r['url'],batch_id=BATCH,changed_at=now().isoformat())
          after.get('stage_states',{}).pop(st,None)
        r.update(after=after,fact=fact,stages=stages)
        items.append(r)
    return dict(items=items,summary=dict(projects=2,construction_restored_units=1774,completion_confirmed_units=316,supply_added_units=0,move_in_added_units=0))

def apply(s,plan):
    written=[]
    with s.sessions.begin() as db:
      if s.engine.dialect.name=='postgresql':db.execute(text('SELECT pg_advisory_xact_lock(9072026)'))
      for r in plan['items']:
        assert current(db,r['pid']).id==r['project_revision_id']
        assert current(db,entity_id('project_profile','manual_project',r['pid'])).id==r['expected_profile_revision_id']
      for r in plan['items']:
        key=BATCH+':'+r['key'];fact={k:v for k,v in r['fact'].items() if k not in ['source_id','source_entity_id','review_status']}
        doc=dict(name=r['name']+' · 복구 근거 재검증',sample_kind='document_evidence',source_object_id=key,source_date=r['source_date'],base_date='2026-10-22',
            evidence_url=r['url'],original_file=r['original_file'],original_sha256=r['sha256'],facts=[fact],matched_project_ids=[r['pid']],
            planned_units=r['units'],verification_status='SOURCE_CONTENT_CHECKED',source_type='OFFICIAL',checked_source_type='OFFICIAL',status='CONFIRMED',reviewed=True,
            review_actor=ACTOR,basis=r['reason'],visual_review=r.get('visual_review'),scope_source_id=r.get('scope_source_id'),scope_source_sha256=r.get('scope_source_sha256'))
        dr,_=upsert_revision(db,'document_evidence','official_document',key,doc,BATCH)
        bridge=dict(project_id=r['pid'],source_entity_id=dr.entity_id,source_revision_no=dr.revision_no,source_id='official_document',evidence_source_id='official_document',
            source_name=doc['name'],evidence_url=r['url'],facts=[fact],units=r['units'],status='CONFIRMED',reviewed=True,review_actor=ACTOR,
            relation_type='OFFICIAL_VERIFIED_HOUSING_SCOPE',basis=r['reason'],base_date='2026-10-22')
        br,_=upsert_revision(db,'evidence_bridge','cross_source',r['pid']+':'+dr.entity_id,bridge,BATCH)
        pr,_=upsert_revision(db,'project_profile','manual_project',r['pid'],r['after'],BATCH)
        for row,before,after in [(dr,{},doc),(br,{},bridge),(pr,r['before'],r['after'])]:
          db.add(Audit(entity_id=row.entity_id,action='VERIFIED_START_RESTORE',before=before,after=after))
        written.append(dict(project_id=r['pid'],name=r['name'],stages=r['stages'],revision_id=pr.id,source_id=dr.entity_id))
    return dict(summary=plan['summary'],written=written)

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--apply',action='store_true');args=p.parse_args();OUT.mkdir(parents=True,exist_ok=True);path=OUT/'plan.json';s=HomeService(engine_for())
 if args.apply:r=apply(s,json.loads(path.read_text()));(OUT/'applied.json').write_text(json.dumps(r,ensure_ascii=False,indent=2))
 else:
  assert not path.exists();r=prepare(s);path.write_text(json.dumps(r,ensure_ascii=False,indent=2))
 print(json.dumps(r['summary'],ensure_ascii=False))
