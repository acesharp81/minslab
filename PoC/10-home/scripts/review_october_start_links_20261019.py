"""User-authorized official-announcement review; exact IDs, no blanket attribution.

Keeps approved quantities and original event dates. Repeated runs are idempotent.
Run with --apply after preparing /app/data/confirmation-plan-20261019.json.
"""
import argparse,hashlib,json
from pathlib import Path
from sqlalchemy import select
from backend.db import engine_for,Revision,Mapping,IdentityAlias,Audit,upsert_revision,entity_id
from backend.service import HomeService
from backend.identity import review_identity_alias
from backend.evidence_bridge import review
from backend.api_samples import today

URL='https://www.korea.kr/briefing/policyBriefingView.do?newsId=156785506'
ACTOR='담당자 대행 · 사용자 지시 2026-10-19'
CASES=[('PRO_af0e615a920526eee9302fe0','흑석11',1515,2500),('PRO_8afa3f6b5386e8b6e5f1eda2','신림2',1430,1400)]

def put_bridge(s,target,source,facts,basis,apply):
    key=target['id']+':'+source['id'];eid=entity_id('evidence_bridge','cross_source',key)
    with s.sessions() as db:
        old=db.scalar(select(Revision).where(Revision.entity_id==eid,Revision.superseded_at.is_(None)))
        if old and old.payload.get('status')=='CONFIRMED':return dict(id=eid,result='already_confirmed')
        if old and old.payload.get('status')=='RELEASED':raise ValueError('기존 해제 연결 보존: '+eid)
    payload=dict(project_id=target['id'],name=target['name'],region=target['region'],source_entity_id=source['id'],
        source_revision_no=source['revision_no'],evidence_source_id=source['source_id'],source_id=source['source_id'],
        source_name=source['name'],relation_type='SAME_PROJECT_MANAGEMENT_SCOPE',evidence_url=source['evidence_url'],
        units=target['planned_units'],facts=facts,status='REVIEW',reviewed=False,basis=basis,
        matching_version='USER_AUTHORIZED_OFFICIAL_REVIEW_20261019',base_date=str(today()),review_actor=ACTOR)
    if not apply:return dict(id=eid,result='proposed',target=target['name'],units=target['planned_units'])
    with s.sessions.begin() as db:
        row,_=upsert_revision(db,'evidence_bridge','cross_source',key,payload,'october-start-review-20261019')
        db.add(Audit(entity_id=eid,action='OFFICIAL_REVIEW_LINK_PREPARED',before=old.payload if old else {},after=payload))
        revision=row.revision_no
    result=review(s,eid,revision,'CONFIRMED',ACTOR+' · '+basis)
    if result.get('conflict'):raise ValueError('연결 판본 변경')
    return dict(id=eid,result='confirmed',target=target['name'],units=target['planned_units'])

def main(apply=False):
    s=HomeService(engine_for());projects={p['id']:p for p in s.projects()};plan=json.loads((s.data_dir/'confirmation-plan-20261019.json').read_text())
    official=(s.data_dir/'review-evidence/briefing_official.html').read_bytes()
    text=(s.data_dir/'review-evidence/briefing_official.txt').read_text()
    assert all(v in text for v in ['흑석11구역','신림2구역','착공되었으며','인천 계양'])
    sha=hashlib.sha256(official).hexdigest();out=dict(actor=ACTOR,applied=apply,duplicates=[],announced=[],held=[])
    for candidate in plan:
        p=projects[candidate['id']]
        same=[r for r in candidate['matches'] if r['units']==p['planned_units']]
        contracts=[r for r in same if r['source'] in ('lh_construction','lh_incheon_construction')]
        chosen=contracts if len(contracts)==1 else same
        if len(chosen)!=1:
            out['held'].append(dict(id=p['id'],name=p['name'],reason='기존 승인 사업의 동일 블록·동일 호수 단일 상대 없음; 분할 블록·정책 근거 추가 확인'));continue
        target=projects[chosen[0]['id']]
        assert target['mapping']['status']=='CONFIRMED' and target['mapping']['policy_id']=='POL_2025_0907'
        assert target['planned_units']==p['planned_units'] and p.get('progress_pct',0)>0
        basis=f"{ACTOR} · 시도·지구·블록 {candidate['key']} 및 총 {p['planned_units']}호 일치. 기존 승인 사업 {target['id']}의 LH 공정 원천. 신규 사업·호수 가산 없음. 원천 공사기간 시작을 실제 착공일로 전용하지 않음."
        if '계양' in p['name']:basis+=' 10월 공식 발표의 인천계양 착공 사업명과도 일치; 지구 약 2,300호를 블록별로 반복 배분하지 않음. '+URL
        facts=[dict(stage='CONSTRUCTION',kind='ACTUAL',date=p['progress_date'],observed_on=p['progress_date'],source_event_date=None,
            date_basis='OBSERVED_BY',units=p['planned_units'],pct=p['progress_pct'],method='OFFICIAL_PROGRESS_OBSERVED',basis=basis)]
        link=put_bridge(s,target,p,facts,basis,apply)
        if apply:
            with s.sessions() as db:
                a=db.scalar(select(IdentityAlias).where(IdentityAlias.source_entity_id==p['id']));ta=db.scalar(select(IdentityAlias).where(IdentityAlias.source_entity_id==target['id']))
                if not a or not ta:raise ValueError('기존 식별 앵커 미확보')
                aid,pid,status,tid=a.id,a.project_id,a.relation_status,ta.project_id
            if pid!=tid or status!='CONFIRMED':
                result=review_identity_alias(s,aid,project_id=tid,expected_project_id=pid,expected_status=status,status='CONFIRMED',basis=basis,evidence_url=p['evidence_url'])
                if result.get('conflict'):raise ValueError('식별 판본 변경')
            mapping=p['mapping']
            if mapping['status']!='RELEASED':
                assert mapping['status']=='REVIEW' and mapping['policy_id']=='UNASSIGNED'
                result=s.confirm_mapping(p['id'],'UNASSIGNED',mapping['revision_no'],'RELEASED',basis,p['evidence_url'])
                if result.get('conflict'):raise ValueError('중복 후보 판본 변경')
        out['duplicates'].append(dict(source=p['id'],name=p['name'],target=target['id'],units=p['planned_units'],link=link))
    for pid,term,units,reported in CASES:
        p=projects[pid];assert term in p['name'] and p['planned_units']==units and p['mapping']['status']=='CONFIRMED'
        key='announcement-20261016-start-'+pid;did=entity_id('document_evidence','official_document',key)
        basis=f"{ACTOR} · 국토부 2026-10-16 공식 브리핑에서 {term}구역을 올해 착공 사업으로 명시. 기존 승인 사업명·자치구와 대조. 기존 승인 관리량 {units}호 유지. 발표 약 {reported}호를 정확한 블록 물량으로 덮어쓰지 않음. 2026-10-16은 착공 확인 상한일이며 정확한 착공일 미공표. 서울 정보몽땅의 철거 상태와 상충은 원문별로 보존하고 국토부의 명시적 착공 발표를 채택."
        fact=dict(stage='CONSTRUCTION',kind='ACTUAL',date='2026-10-16',date_basis='OBSERVED_BY',observed_on='2026-10-16',source_event_date=None,
            event_period_start='2026-01-01',units=units,method='OFFICIAL_ANNOUNCED_STATE',basis=basis)
        payload=dict(name=p['name']+' · 10월 공식 착공 발표',region=p['region'],municipality=p.get('municipality'),
            source_object_id=key,sample_kind='document_evidence',source_date='2026-10-16',base_date='2026-10-16',date_precision='DAY',
            evidence_url=URL,original_sha256=sha,original_file='review-evidence/briefing_official.html',verification_status='SOURCE_CONTENT_CHECKED',
            planned_units=None,management_units=units,official_reported_units=reported,official_quantity_qualifier='APPROXIMATE',
            matched_project_ids=[pid],facts=[fact],unit_basis=basis,review_actor=ACTOR)
        source=dict(payload,id=did,revision_no=1,source_id='official_document')
        if apply:
            with s.sessions.begin() as db:
                row,action=upsert_revision(db,'document_evidence','official_document',key,payload,'october-start-review-20261019')
                if action!='unchanged':db.add(Audit(entity_id=did,action='OFFICIAL_DOCUMENT_REVIEWED',before={},after=payload))
                source['revision_no']=row.revision_no
        out['announced'].append(put_bridge(s,p,source,[fact],basis,apply))
    file=s.data_dir/('october-start-review-applied-20261019.json' if apply else 'october-start-review-plan-20261019.json')
    file.write_text(json.dumps(out,ensure_ascii=False,indent=2));print(json.dumps(out,ensure_ascii=False,indent=2))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--apply',action='store_true');main(p.parse_args().apply)
