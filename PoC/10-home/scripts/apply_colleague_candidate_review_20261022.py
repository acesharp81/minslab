"""Verify official follow-up relationships without changing housing attribution."""
import argparse
from copy import deepcopy
from datetime import date
import hashlib
import io
import json
from pathlib import Path
import re

BATCH='colleague-candidates-20261022'
POLICY='POL_2025_0907'
URL129='https://www.korea.kr/common/download.do?fileId=198344116'
URL813='https://www.korea.kr/common/download.do?fileId=198524605&tblKey=GMN'
URL930='https://www.korea.kr/common/download.do?fileId=198562238&tblKey=GMN'


def norm(x):return re.sub(r'\s+','',x)


def normalize(value):
    if isinstance(value,dict):return {k:normalize(v) for k,v in value.items()}
    if isinstance(value,list):return sorted((normalize(v) for v in value),key=lambda v:json.dumps(v,sort_keys=True))
    return value


def main(apply=False):
    from pypdf import PdfReader
    from sqlalchemy import select,text
    from sqlalchemy.orm import sessionmaker
    from backend.db import Revision,Mapping,Audit,engine_for,entity_id,upsert_revision
    from backend.service import HomeService
    from backend.policy_attachments import parse_urban930_attachment
    from backend.policy_delivery import build_delivery
    from backend.read_scope import projection_reads
    engine=engine_for();service=HomeService(engine)
    root=Path(service.data_dir)/BATCH;src=root/'sources'
    files={name:(src/(name+'.pdf')).read_bytes() for name in ('policy129','policy813','urban930')}
    pages={name:[p.extract_text(extraction_mode='layout') or '' for p in PdfReader(io.BytesIO(data)).pages] for name,data in files.items()}
    hashes={name:hashlib.sha256(data).hexdigest() for name,data in files.items()}
    rows930,_=parse_urban930_attachment(pages['urban930'])
    normalized813=[norm(t) for t in pages['policy813']]
    page813=next(i+1 for i,t in enumerate(normalized813) if '9.7대책이행력을제고' in t)
    boundarypage=next(i+1 for i,t in enumerate(normalized813) if '1.29공급방안대비' in t and '추가주택착공물량' in t)
    assert '8.13' in pages['urban930'][0]
    assert '135만' in norm((src/'briefing129.html').read_text())
    selected={name:p for _,name,p in rows930}
    assert len(selected)==16
    aliases={'은평구 불광동 일원':('불광동연구원',9),
             '하남 신장테니스장 부지':('신장테니스장',14),
             '고양시 소재 구 국방대학교':('구국방대학교',15),
             '과천 경마장·방첩사 부지':('과천경마장',11)}
    with service.sessions() as db:
        raw=list(db.scalars(select(Revision).where(Revision.kind=='project',Revision.superseded_at.is_(None))))
        candidates={m.project_id for m in db.scalars(select(Mapping).where(Mapping.policy_id.in_(['POL_2026_0129','POL_2026_0813'])))}
        targets=[r for r in raw if r.entity_id in candidates and (r.source_id=='policy_129' or r.source_id=='urban_930' and r.payload['name'] in selected)]
    assert len(targets)==63
    evidence=[]
    for r in targets:
        p=r.payload;name=p['name']
        if r.source_id=='policy_129':
            anchor=aliases.get(name,(norm(name),None))[0]
            page=aliases.get(name,('',None))[1] or next((i+1 for i,t in enumerate(pages['policy129']) if anchor in norm(t)),None)
            assert page and anchor in norm(pages['policy129'][page-1]),name
            event=None;url=URL129;file='policy129';kind='FOLLOWUP_129_NAMED_SITE'
        else:
            check=selected[name]
            assert p['planned_units']==check['planned_units'] and p.get('designation_date')==check.get('designation_date'),name
            page=check['source_page'];url=URL930;file='urban930'
            candidate=check['stage']=='CANDIDATE';kind='813_FOLLOWUP_CANDIDATE' if candidate else 'EXISTING_DISTRICT_DESIGNATED'
            event=dict(stage='BUSINESS',kind='STATE',milestone='CANDIDATE_SELECTED' if candidate else 'DISTRICT_DESIGNATED',
                date='2026-09-30' if candidate else check['designation_date'],date_basis='EVENT',units=check['planned_units'],
                reference_only=True,basis='공식 후보지 선정 사실' if candidate else '복합지구 지정 사실 · 주택사업계획 승인 및 착공과 구분')
        evidence.append(dict(project_id=r.entity_id,name=name,source_id=r.source_id,source_revision_no=r.revision_no,
            official_url=url,source_page=page,source_file=file,sha256=hashes[file],
            planned_units=p.get('planned_units'),relationship=kind,event=event))
    plan=dict(official_project_evidence_links=63,selection_events=11,designation_events=5,
        primary_policy_changes=0,policy907_new_quantity=0,construction_added_units=0,
        policy_relationships=3,project_relationships=63,policy813_basis_page=page813,quantity_boundary_page=boundarypage)
    (root/'verified_sources.json').write_text(json.dumps(dict(plan=plan,projects=evidence,hashes=hashes),ensure_ascii=False,indent=2))
    if not apply:print(json.dumps(plan,ensure_ascii=False));return
    receipts=[]
    with engine.begin() as conn:
        conn.execute(text('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ'))
        conn.execute(text('SELECT pg_advisory_xact_lock(9072026)'))
        tx=HomeService(engine,service.data_dir);tx.sessions=sessionmaker(bind=conn,expire_on_commit=False)
        with projection_reads():before=build_delivery(tx,date(2026,10,22),include_portfolio_comparisons=False)
        with tx.sessions.begin() as db:
            def current(eid):return db.scalar(select(Revision).where(Revision.entity_id==eid,Revision.superseded_at.is_(None)))
            if current(entity_id('collection_research','official_review',BATCH)):
                print(json.dumps(dict(already_applied=True,plan=plan),ensure_ascii=False));return
            original={r.entity_id:r.payload_hash for r in db.scalars(select(Revision).where(Revision.kind=='project',Revision.superseded_at.is_(None)))}
            mappings={m.project_id:(m.policy_id,m.program_id,m.status,m.revision_no) for m in db.scalars(select(Mapping))}
            def put(kind,sid,key,value):
                previous=current(entity_id(kind,sid,key));old=deepcopy(previous.payload) if previous else {}
                row,outcome=upsert_revision(db,kind,sid,key,value,BATCH)
                if outcome!='unchanged':db.add(Audit(entity_id=row.entity_id,action='OFFICIAL_FOLLOWUP_REVIEW',before=old,after=value))
                receipts.append(dict(kind=kind,entity_id=row.entity_id,revision_no=row.revision_no,outcome=outcome));return row
            links=[('POL_2026_0129',POLICY,'FOLLOWUP_IMPLEMENTATION',
                'https://www.korea.kr/briefing/policyBriefingView.do?newsId=156742030',None),
                ('POL_2026_0813',POLICY,'IMPLEMENTATION_AND_ADDITIONAL_SUPPLY',URL813,page813),
                ('ANNOUNCEMENT_2026_0930','POL_2026_0813','EXPLICIT_FOLLOWUP',URL930,1)]
            for child,parent,kind,url,page in links:
                put('policy_relationship','official_review',child+':'+parent,dict(child_policy_id=child,parent_policy_id=parent,
                    relationship=kind,status='CONFIRMED',evidence_url=url,source_page=page,source_type='OFFICIAL',
                    review_label='공식 자료 자동 연결',aggregate_into_parent=False,
                    quantity_attribution_status='PROJECT_OVERLAP_AND_ORIGINAL_TARGET_SCOPE_UNRESOLVED',
                    basis='후속 추진 관계 확인. 원 정책 135만호 산입 또는 새 착공 실적을 자동 인정하지 않음.',
                    boundary_evidence_url=URL813,boundary_page=boundarypage,verified_at='2026-10-22'))
            for e in evidence:
                pid=e['project_id'];original_policy=mappings[pid][0]
                assert original_policy==('POL_2026_0129' if e['source_id']=='policy_129' else 'POL_2026_0813')
                label='공식 자료 자동 연결 · 후속 정책 및 개별 사업 근거'
                basis=('1·29 개별 입지 및 9·7 목표 이행 관련 발표 확인' if e['source_id']=='policy_129' else
                    '8·13 후속 도심복합 선정·지정 공식 원문 확인')+'; 원 정책 연결 보존. 9·7 원 목표 물량 산입 및 착공 사건으로 자동 전환하지 않음.'
                facts=[e['event']] if e['event'] else []
                doc=put('document_evidence','official_document',BATCH+':'+pid,dict(name=e['name']+' · 후속 정책 원문 검증',
                    matched_project_ids=[pid],sample_kind='document_evidence',source_type='OFFICIAL',checked_source_type='OFFICIAL',
                    verification_status='SOURCE_CONTENT_CHECKED',review_label=label,evidence_url=e['official_url'],source_page=e['source_page'],
                    source_base_date='2026-01-29' if e['source_id']=='policy_129' else '2026-09-30',base_date='2026-10-22',
                    original_file=BATCH+'/sources/'+e['source_file']+'.pdf',original_sha256=e['sha256'],
                    planned_units=e['planned_units'],unit_basis='계획규모 · 실착공량 및 새 순증 공급량 아님',facts=facts,
                    policy_relationship=dict(primary_policy_id=original_policy,related_policy_id=POLICY,relationship=e['relationship'],
                        aggregate_into_parent=False,attribution_status='FOLLOWUP_CONTEXT_ONLY'),basis=basis))
                put('evidence_bridge','cross_source',pid+':'+doc.entity_id,dict(project_id=pid,source_entity_id=doc.entity_id,
                    source_revision_no=doc.revision_no,evidence_source_id='official_document',source_id='official_document',
                    source_name=e['name']+' · 후속 정책 원문 검증',evidence_url=e['official_url'],status='CONFIRMED',
                    source_type='OFFICIAL',review_label=label,match_rule='EXACT_OFFICIAL_NAMED_SITE_AND_SOURCE_ROW',
                    reason=basis,basis=basis,facts=facts,excluded_from_new_quantity=True,reviewed_at='2026-10-22',
                    reviewed_by='담당자 대행 · 공식 원문 검증'))
                put('policy_relationship','official_review',pid+':'+POLICY,dict(project_id=pid,primary_policy_id=original_policy,
                    related_policy_id=POLICY,relationship=e['relationship'],status='CONFIRMED',source_type='OFFICIAL',
                    evidence_url=e['official_url'],evidence_document_id=doc.entity_id,source_page=e['source_page'],
                    policy_chain=[original_policy,POLICY],aggregate_into_parent=False,quantity_attribution_status='UNVERIFIED',
                    review_label=label,basis=basis,verified_at='2026-10-22'))
            assert original=={r.entity_id:r.payload_hash for r in db.scalars(select(Revision).where(Revision.kind=='project',Revision.superseded_at.is_(None)))}
            assert mappings=={m.project_id:(m.policy_id,m.program_id,m.status,m.revision_no) for m in db.scalars(select(Mapping))}
        with projection_reads():after=build_delivery(tx,date(2026,10,22),include_portfolio_comparisons=False)
        for key in ('portfolio_cohorts','official_alignment','regional_start_months'):
            assert normalize(before[key])==normalize(after[key]),key
        with tx.sessions.begin() as db:
            put('collection_research','official_review',BATCH,dict(name='조원 후보검증 · 공식 후속관계 보완',
                base_date='2026-10-22',plan=plan,verified=True,original_projects_and_mappings_preserved=True,
                policy_cumulative_unchanged=True,official_comparison_unchanged=True,source_hashes=hashes))
    result=dict(plan=plan,receipts=receipts,verified=True)
    (root/'applied.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
    print(json.dumps(dict(plan=plan,revisions=len(receipts),verified=True),ensure_ascii=False))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--apply',action='store_true');main(parser.parse_args().apply)
