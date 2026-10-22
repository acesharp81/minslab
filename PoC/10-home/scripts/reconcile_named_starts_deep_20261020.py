"""Pin independent municipal start evidence; preserve approved management inputs."""
import argparse
from copy import deepcopy
from datetime import date
import hashlib
import json
from pathlib import Path
import re

from bs4 import BeautifulSoup
from sqlalchemy import select, text
from backend.db import Audit, Mapping, Revision, engine_for, entity_id, upsert_revision
from backend.service import HomeService
from scripts.apply_officer_verified_links_20261020 import protected_in_db
from scripts.review_policy_readmission_20261019 import digest

BATCH = 'named-start-deep-20261020'
ACTOR = '담당자 대행 · 사용자 8개 사업 착공 심층 재검증 지시 2026-10-20'
POLICY = 'POL_2025_0907'
SPECS = [
    dict(key='sinlim2-gwanak', pid='PRO_8afa3f6b5386e8b6e5f1eda2', name='신림2재정비촉진',
         municipality='관악구', units=1430, event_date='2026-05-06', published='2026-05-18',
         url='https://www.gwanak.go.kr/site/gwanak/ex/bbs/View.do?bcIdx=79314&cateCont=25023004&cbIdx=456',
         sha256='1f9aa281b389152a721d06b0533012758b5585854f61a2e704843cd320087ccd'),
    dict(key='seoul-start-table', pid='PRO_af0e615a920526eee9302fe0', name='흑석11재정비촉진',
         municipality='동작구', units=1515, event_date='2026-02-06', published='2026-10-20',
         url='https://housinginfo.seoul.go.kr/hmpg/mabu/prst/cons/consDetail.do', sha256=None),
    dict(key='seoul-press-465574', pid='PRO_f5bf0d92748d113c80d49497', name='중계본동',
         municipality='노원구', units=3178, event_date=None, published='2026-09-07',
         url='https://www.seoul.go.kr/news/news_report.do?bbsNo=158&nttNo=465574',
         sha256='7fcf7f190ba9b4edaa542232950db4ccb08f6348791eb40d6feb34875d5ed102'),
]
HELD = [
    dict(name='남양주왕숙2', units=1063, blocks=[('A6',510),('A7',553)],
         project_ids=['PRO_7dbd1a018c8b1cda73879b7d','PRO_1a399402c5ac572891b50a88']),
    dict(name='부천대장', units=574, blocks=[('A9',574)], project_ids=['PRO_91a176954d241b2aac791074']),
    dict(name='인천계양 추가 후보', units=1216, blocks=[('A16',434),('A18',782)],
         project_ids=['PRO_795bc2926b42e5534efe75ef','PRO_bf06ad6b8b22e4c3ed114ae6']),
    dict(name='하남교산 비교 블록 재검토', units=1100, blocks=[('A3',1100)], project_ids=[]),
]


def validate_source(spec, body):
    """Validate the date and quantity in the same official project context."""
    sha=hashlib.sha256(body).hexdigest()
    if spec.get('sha256') and sha != spec['sha256']:
        raise ValueError('검토 원문 판본 변경: '+spec['key'])
    soup=BeautifulSoup(body,'html.parser');content=soup.get_text(' ',strip=True)
    if spec['key']=='sinlim2-gwanak':
        if not re.search(r'2026\s*\.\s*05\s*\.\s*06\s*\.?\s*[:：]\s*착공',content):
            raise ValueError('신림2 실제 착공일 원문 불일치')
        if '1,430' not in content or '관악구 신림동 324-25' not in content:
            raise ValueError('신림2 물량·위치 불일치')
    elif spec['key']=='seoul-start-table':
        rows=[[td.get_text(' ',strip=True) for td in tr.find_all('td')] for tr in soup.select('tr')]
        matched=[r for r in rows if len(r)==8 and r[3]=='흑석11' and r[2]=='동작구']
        if len(matched)!=1 or matched[0][1]!='2026-02-06' or matched[0][7]!='1,515':
            raise ValueError('흑석11 착공 목록 행 불일치')
        # Existing households (1,829) must never be substituted for supply units.
    else:
        if not re.search(r'중계본동\s*\(\s*3,178\s*호\s*\)',content) or '올해 착공한' not in content:
            raise ValueError('중계본동 공식 기착공·물량 문맥 불일치')
        if '2026-09-07' not in content:
            raise ValueError('서울시 발표일 불일치')
    return sha


def reconcile(service, folder, apply=False):
    evidence=[]
    for spec in SPECS:
        body=(Path(folder)/(spec['key']+'.html')).read_bytes()
        evidence.append((spec,validate_source(spec,body)))
    outcomes=[]
    with service.sessions.begin() as db:
        if service.engine.dialect.name=='postgresql':db.execute(text('SELECT pg_advisory_xact_lock(10203033)'))
        before=protected_in_db(db)
        for spec,_ in evidence:
            project=db.scalar(select(Revision).where(Revision.entity_id==spec['pid'],Revision.superseded_at.is_(None)))
            mapping=db.scalar(select(Mapping).where(Mapping.project_id==spec['pid']))
            if not project or project.payload.get('planned_units')!=spec['units'] or not mapping or mapping.policy_id!=POLICY or mapping.status!='CONFIRMED':
                raise ValueError('기존 사업 물량·정책 승인 상태 불일치: '+spec['name'])
        def put(kind,source,key,payload,action):
            eid=entity_id(kind,source,key)
            old=db.scalar(select(Revision).where(Revision.entity_id==eid,Revision.superseded_at.is_(None)))
            if old and old.payload.get('status')=='RELEASED':raise ValueError('담당자 해제 연결 보존: '+eid)
            if not apply:return eid,old.revision_no if old else 1,'preview'
            prior=deepcopy(old.payload) if old else {}
            row,outcome=upsert_revision(db,kind,source,key,payload,BATCH)
            if outcome!='unchanged':db.add(Audit(entity_id=eid,action=action,before=prior,after=dict(payload,actor=ACTOR)))
            return eid,row.revision_no,outcome
        for spec,sha in evidence:
            actual=spec['event_date'];when=actual or spec['published']
            basis=('지자체 공식 사업별 착공일·공급 세대수 직접 확인. ' if actual else
                   '서울시 별도 보도자료에서 올해 기착공 사업명·정확 물량 확인. 발표일은 확인 상한일이며 실제 착공일 아님. ')
            basis+='기존 사업·관리 추정·원천 관측일 보존, 동일 현장을 다시 가산하지 않음.'
            fact=dict(stage='CONSTRUCTION',kind='ACTUAL',date=when,units=spec['units'],
                      date_basis='EVENT' if actual else 'OBSERVED_BY',source_event_date=actual,
                      observed_on=spec['published'],method='MUNICIPAL_START_DATE' if actual else 'MUNICIPAL_ANNOUNCED_STATE',basis=basis)
            if not actual:fact['event_period_start']='2026-01-01'
            payload=dict(name=spec['name']+' · 지자체 독립 착공 검증',region='서울특별시',municipality=spec['municipality'],
                         sample_kind='document_evidence',source_object_id=BATCH+':'+spec['key'],source_date=spec['published'],
                         base_date='2026-10-20',date_precision='DAY' if actual else 'OBSERVATION',units=spec['units'],
                         evidence_url=spec['url'],original_sha256=sha,review_actor=ACTOR,
                         matched_project_ids=[spec['pid']],policy_mapping_status='CONFIRMED',proposed_policy=POLICY,
                         quantity_scope='SAME_PROJECT_TOTAL',facts=[fact],basis=basis,independent_of_october_brief=True)
            eid,revision,outcome=put('document_evidence','official_document',payload['source_object_id'],payload,'NAMED_START_SOURCE_VERIFIED')
            bridge=dict(project_id=spec['pid'],name=payload['name'],region='서울특별시',source_entity_id=eid,
                        source_revision_no=revision,source_id='official_document',evidence_source_id='official_document',
                        source_name=payload['name'],evidence_url=spec['url'],units=spec['units'],facts=[fact],
                        status='CONFIRMED',reviewed=True,review_actor=ACTOR,review_basis=basis,relation_type='SAME_SCOPE',
                        basis=basis,base_date='2026-10-20')
            bid,_,result=put('evidence_bridge','cross_source',spec['pid']+':'+eid,bridge,'EVIDENCE_BRIDGE_REVIEW')
            outcomes.append(dict(name=spec['name'],source=eid,bridge=bid,outcome=result,event_date=actual,observed_on=spec['published'],units=spec['units']))
        for candidate in HELD:
            held_key=BATCH+':held:'+candidate['name']
            previous=db.scalar(select(Revision).where(Revision.entity_id==entity_id('document_evidence','officer',held_key),Revision.superseded_at.is_(None)))
            if previous and previous.payload.get('review_decision')=='OFFICER_CONFIRMED_NONOFFICIAL':
                outcomes.append(dict(name=candidate['name'],source=previous.entity_id,outcome='unchanged',confirmed_units=previous.payload.get('confirmed_units')))
                continue
            unofficial='교산' not in candidate['name']
            review_label=('담당자 확인 - 비공식 자료: 이투데이(2026-08-12), LH 상반기 민참 착공 보도' if unofficial else
                          '담당자 확인 - 공식 계획자료: 경기도 2026년 주거종합계획')
            payload=dict(name=candidate['name']+' · 공식 착공 구성 재검토 후보',sample_kind='document_evidence',
                         source_object_id=BATCH+':held:'+candidate['name'],source_date='2026-10-20',base_date='2026-10-20',
                         evidence_url='https://www.etoday.co.kr/news/view/2613748' if '교산' not in candidate['name'] else
                         'https://web1.gg.go.kr/uploads/CONTENTS/site/gg/2026%EB%85%84%2B%EA%B2%BD%EA%B8%B0%EB%8F%84%2B%EC%A3%BC%EA%B1%B0%EC%A2%85%ED%95%A9%EA%B3%84%ED%9A%8D_v20260513.pdf',
                         facts=[],units=None,planned_units=None,candidate_units=candidate['units'],candidate_blocks=candidate['blocks'],
                         matched_project_ids=candidate['project_ids'],exclude_from_project_totals=True,comparison_eligible=False,
                         review_actor=ACTOR,review_decision='HOLD_OFFICIAL_ACTUAL_SOURCE',policy_mapping_status='CANDIDATE_ONLY',
                         review_label=review_label,officer_review_status='CONTENT_CHECKED',
                         checked_source_type='NON_OFFICIAL' if unofficial else 'OFFICIAL_PLAN',
                         official_actual_verified=False,official_brief_membership_verified=False,actual_admission_status='NOT_APPLIED',
                         basis=review_label+' · 사업·블록·물량 대조. 시행기관의 블록별 실제 착공 원문 및 발표 구성 미확정. 실적 미가산.')
            eid,_,outcome=put('document_evidence','officer',payload['source_object_id'],payload,'NAMED_START_SCOPE_HELD')
            outcomes.append(dict(name=candidate['name'],source=eid,outcome=outcome,held_units=candidate['units']))
        after=protected_in_db(db)
        if before!=after:raise ValueError('기존 사업·담당자 입력·매핑 변경 감지')
    return dict(applied=apply,results=outcomes,protected_before=digest(before),protected_after=digest(after),
                added_projects=0,held_candidate_units=sum(r.get('held_units',0) for r in outcomes),independent_municipal_evidence=3)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--apply',action='store_true');args=parser.parse_args()
    service=HomeService(engine_for());folder=service.data_dir/BATCH
    from backend.policy_delivery import build_delivery
    from scripts.build_continuation_review_20261020 import metrics
    before=metrics(build_delivery(service,date(2026,10,20),include_portfolio_comparisons=False))
    result=reconcile(service,folder/'sources',args.apply)
    after=metrics(build_delivery(service,date(2026,10,20),include_portfolio_comparisons=False))
    result.update(metrics_before=before,metrics_after=after)
    if before!=after:raise RuntimeError('집계 변화 발생: 추가 대조 필요')
    filename='applied.json' if args.apply else 'preview.json'
    if args.apply and all(r['outcome']=='unchanged' for r in result['results']):filename='idempotence.json'
    path=folder/filename
    path.write_text(json.dumps(result,ensure_ascii=False,indent=2))
    print(json.dumps(result,ensure_ascii=False))


if __name__=='__main__':main()
