"""User-authorized officer confirmation of checked, nonofficial start evidence."""
from copy import deepcopy
from datetime import date
import hashlib
import json
from pathlib import Path
from bs4 import BeautifulSoup
from sqlalchemy import select,text
from backend.db import Audit,Mapping,Revision,engine_for,entity_id,upsert_revision
from backend.service import HomeService
from scripts.reconcile_named_starts_deep_20261020 import HELD
from scripts.apply_officer_verified_links_20261020 import protected_in_db
from scripts.review_policy_readmission_20261019 import digest

BATCH='nonofficial-start-confirmed-20261020'
ACTOR='담당자 대행 · 사용자 비공식 원문 확인 시 담당자 확인 완료 분류·연결 지시'
LABEL='담당자 확인 완료 - 비공식 자료: 이투데이(2026-08-12), LH 상반기 민참 착공 보도'
URL='https://www.etoday.co.kr/news/view/2613748'
ARTICLE_SHA='178ba47f0e1c1ef75f53cdf5d48565f8bbdf518186948e16fdc84509f08a72e6'


def apply(service):
    file=service.data_dir/'named-start-deep-20261020/sources/etoday-20260812.html';body=file.read_bytes()
    if hashlib.sha256(body).hexdigest()!=ARTICLE_SHA:raise ValueError('검토한 비공식 원문 판본 변경')
    text_body=BeautifulSoup(body,'html.parser').get_text(' ',strip=True)
    if not all(v in text_body for v in ('상반기 착공','A9','574','A16','A18','1216','A6','A7','1063')):raise ValueError('비공식 원문의 실제 착공·블록·수량 확인 실패')
    groups=[h for h in HELD if '교산' not in h['name']];results=[];supplemental=[]
    with service.sessions.begin() as db:
        if service.engine.dialect.name=='postgresql':db.execute(text('SELECT pg_advisory_xact_lock(10203033)'))
        before=protected_in_db(db)
        for group in groups:
            for pid,(_,units) in zip(group['project_ids'],group['blocks']):
                p=db.scalar(select(Revision).where(Revision.entity_id==pid,Revision.superseded_at.is_(None)))
                m=db.scalar(select(Mapping).where(Mapping.project_id==pid))
                if not p or p.payload.get('planned_units')!=units or not m or m.status!='CONFIRMED' or m.policy_id!='POL_2025_0907':raise ValueError('기존 승인 블록·수량·정책 확인 실패: '+pid)
        def write(kind,sid,key,payload):
            eid=entity_id(kind,sid,key);old=db.scalar(select(Revision).where(Revision.entity_id==eid,Revision.superseded_at.is_(None)))
            if old and old.payload.get('status')=='RELEASED':raise ValueError('해제된 담당자 연결 보존')
            previous=deepcopy(old.payload) if old else {};r,outcome=upsert_revision(db,kind,sid,key,payload,BATCH)
            if outcome!='unchanged':db.add(Audit(entity_id=r.entity_id,action='NONOFFICIAL_SOURCE_CONFIRMED',before=previous,after=payload))
            return r,outcome
        def fact(units,scope):
            return dict(stage='CONSTRUCTION',kind='ACTUAL',date='2026-06-30',units=units,
                date_basis='OBSERVED_BY',source_event_date=None,event_period_start='2026-01-01',event_period_end='2026-06-30',
                source_published_on='2026-08-12',source_type='NON_OFFICIAL',method='OFFICER_CONFIRMED_NONOFFICIAL',
                quantity_basis=scope,basis=LABEL+' · 상반기 기착공 사실·해당 블록 물량 담당자 확인.6월30일은 확인 기간의 상한이며 정확한 실제 착공일 아님.10월 발표 포함 블록 확정과 구별.')
        for group in groups:
            key='named-start-deep-20261020:held:'+group['name'];eid=entity_id('document_evidence','officer',key)
            old=db.scalar(select(Revision).where(Revision.entity_id==eid,Revision.superseded_at.is_(None)))
            if not old:raise ValueError('이전 검토 문서 미확보')
            value=deepcopy(old.payload);basis=LABEL+' · 상반기 실제 착공을 확인한 자료로 분류.기존 승인 사업·블록·호수와 대조하여 연결.정확한 착공일과 정부10월 발표 구성의 완전 동일성은 미확정.'
            if '왕숙' in group['name']:basis+=' 공모·기사 합계1,063을 채택하며 계약 공시1,082와의19호 상충은 보존.블록별 배분510/553은 기존 승인 계획 기준.'
            value.update(review_label=LABEL,review_actor=ACTOR,officer_review_status='CONFIRMED',status='CONFIRMED',reviewed=True,
                review_decision='OFFICER_CONFIRMED_NONOFFICIAL',actual_admission_status='APPLIED',policy_mapping_status='CONFIRMED',
                official_actual_verified=False,official_brief_membership_verified=False,
                confirmed_units=group['units'],facts=[fact(group['units'],'REPORTED_GROUP_TOTAL')],basis=basis,
                original_file=str(file.relative_to(service.data_dir)),original_sha256=hashlib.sha256(body).hexdigest())
            source,outcome=write('document_evidence','officer',key,value)
            for pid,(block,units) in zip(group['project_ids'],group['blocks']):
                f=fact(units,'APPROVED_PLAN_SPLIT_OF_REPORTED_GROUP' if len(group['blocks'])>1 else 'REPORTED_SINGLE_BLOCK')
                bridge=dict(project_id=pid,name=group['name']+' '+block+' · 담당자 확인 완료 착공 근거',region='인천광역시' if '계양' in group['name'] else '경기도',
                    source_entity_id=source.entity_id,source_revision_no=source.revision_no,source_id='officer',evidence_source_id='officer',
                    source_name=LABEL,evidence_url=URL,units=units,facts=[f],status='CONFIRMED',reviewed=True,review_actor=ACTOR,
                    review_label=LABEL,checked_source_type='NON_OFFICIAL',official_actual_verified=False,review_basis=basis,basis=basis,
                    relation_type='OFFICER_CONFIRMED_SAME_BLOCK',base_date='2026-10-20')
                row,result=write('evidence_bridge','cross_source',pid+':'+source.entity_id,bridge)
                results.append(dict(project_id=pid,source=source.entity_id,bridge=row.entity_id,block=block,units=units,outcome=result))
        # The earlier designer source is confirmed within its actual scope:
        # project existence only, without manufacturing an eight-home start.
        prior_id='DOC_af41c4d72153e5430d45df79';old=db.scalar(select(Revision).where(Revision.entity_id==prior_id,Revision.superseded_at.is_(None)))
        if old:
            value=deepcopy(old.payload);label=value['review_label'].replace('담당자 확인 -','담당자 확인 완료 -')
            value.update(review_label=label,officer_review_status='CONFIRMED',status='CONFIRMED',reviewed=True,review_decision='PROJECT_EXISTENCE_CONFIRMED_NONOFFICIAL',review_actor=ACTOR)
            value['basis']=value['basis'].replace('담당자 확인 -','담당자 확인 완료 -')
            write('document_evidence','officer',value['source_object_id'],value)
        gyosan=service.data_dir/'named-start-deep-20261020/sources/gyosan-a3-approval-seoulpn.html'
        if gyosan.exists():
            body=gyosan.read_bytes();sha=hashlib.sha256(body).hexdigest()
            if sha!='4df40b5a18f65ff2bb13612381046260c8bda976a2f14a0f7190386f735d747d':raise ValueError('교산 승인 보도 판본 변경')
            content=BeautifulSoup(body,'html.parser').get_text(' ',strip=True)
            if not all(v in content for v in ('A-3','1100','사업계획승인','2026-04-30')):raise ValueError('교산 승인·규모 보도 대조 실패')
            label='담당자 확인 완료 - 비공식 자료: 서울Pn(2026-04-30), 하남교산 A-3블록 사업계획승인 보도'
            key='nonofficial-20261020:gyosan-a3-approval'
            payload=dict(name='하남교산 GH A3 · 사업계획승인 상태·1100호 담당자 확인 완료',source_object_id=key,
                sample_kind='document_evidence',base_date='2026-10-20',source_date='2026-04-30',region='경기도',municipality='하남시',
                evidence_url='https://m.go.seoul.co.kr/news/publicnews/policy_admin/public_org/2026/04/30/20260430500079',
                review_label=label,review_actor=ACTOR,officer_review_status='CONFIRMED',status='CONFIRMED',reviewed=True,
                checked_source_type='NON_OFFICIAL',review_decision='APPROVAL_STATE_AND_CAPACITY_CONFIRMED_NONOFFICIAL',
                confirmed_scope='APPROVAL_STATE_AND_PROJECT_CAPACITY',confirmed_project_units=1100,
                actual_admission_status='NO_CONSTRUCTION_CLAIM_IN_SOURCE',official_actual_verified=False,
                matched_project_ids=[],units=None,planned_units=None,exclude_from_project_totals=True,
                original_file=str(gyosan.relative_to(service.data_dir)),original_sha256=sha,
                facts=[dict(stage='APPROVAL',kind='STATE',date='2026-04-30',date_basis='OBSERVED_BY',source_event_date=None,units=1100,
                    basis=label+' · 4월30일까지 승인 고시 상태 확인.보도일을 실제 승인일로 전용하지 않음.')],
                basis=label+' · GH·하남 천현동·A3·1100호·승인 고시 상태 대조 완료.착공 사실을 보도한 자료가 아니므로 착공 근거로 사용하지 않음.')
            row,result=write('document_evidence','officer',key,payload);supplemental.append(dict(source=row.entity_id,outcome=result,confirmed_scope=payload['confirmed_scope']))
        after=protected_in_db(db)
        if before!=after:raise ValueError('기존 사업·담당자 입력·정책 연결 변경 감지')
    return dict(results=results,supplemental=supplemental,confirmed_blocks=5,confirmed_group_units=2853,
                protected_before=digest(before),protected_after=digest(after),exact_start_dates_fabricated=0)


if __name__=='__main__':
    from backend.policy_delivery import build_delivery
    from scripts.build_continuation_review_20261020 import metrics
    s=HomeService(engine_for());before=metrics(build_delivery(s,date(2026,10,20),include_portfolio_comparisons=False))
    result=apply(s);after=metrics(build_delivery(s,date(2026,10,20),include_portfolio_comparisons=False))
    result.update(metrics_before=before,metrics_after=after)
    assert before['SUPPLY']==after['SUPPLY']
    folder=s.data_dir/BATCH;folder.mkdir(exist_ok=True)
    filename='idempotence.json' if all(r['outcome']=='unchanged' for r in result['results']+result['supplemental']) else ('supplemental-applied.json' if all(r['outcome']=='unchanged' for r in result['results']) else 'applied.json')
    (folder/filename).write_text(json.dumps(result,ensure_ascii=False,indent=2));print(json.dumps(result,ensure_ascii=False))
