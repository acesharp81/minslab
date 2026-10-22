"""Source-pinned candidate review, preserving government comparison populations.

This does not infer new policy membership from generic housing types. One new
source inherits a previously approved physical site's policy assignment; its
previously omitted, single-block construction inventory is recovered once.
"""
import argparse
from copy import deepcopy
from datetime import date
import hashlib
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET
import zipfile

BATCH='candidate-ext-review-20261021'
POLICY='POL_2025_0907'
SONG='PRO_b2a3fc2ab9bda6c7ffaa3b0e'
SONG_OLD='PRO_97cb44fc1d3d65cddf98e848'
YEON='PRO_0abce10856b8c6218fa0d63e'
PAIRS=[('PRO_4b859c7f4b18222558932b97','PRO_9a256c5d211050be9f0814ff',350,'105250'),
       ('PRO_4e534476d1d747285e612f85','PRO_1c2a1be12daff06cef52f8c6',110,'105409'),
       ('PRO_a9e2bffb100945377e90ef33','PRO_85998117430f9302232be12d',58,'105410')]
ACTOR='담당자 대행 · 외부 후보 공식 대조'
YEON_URL='https://www.eum.go.kr/web/gs/gv/gvGosiDet.jsp?seq=614277'
LH_URL='https://www.lh.or.kr/boardDownload.es?bid=0007&list_no=654682&seq=14'


def signature(model):
    cs=model['portfolio_cohorts']
    def amount(c,stages,first=None):
        return min(c['units'],max([e.get('units') or 0 for e in c['events'] if e['stage'] in stages and
            e.get('status','ACTUAL')=='ACTUAL' and e.get('event_date','9999')<='2026-10-21' and
            (not first or e.get('event_date','')>=first)]+[0]))
    return dict(cohorts=len(cs),capacity=sum(c['units'] for c in cs),
        construction_direct=sum(amount(c,['CONSTRUCTION']) for c in cs),
        construction_reached=sum(amount(c,['CONSTRUCTION','COMPLETION','SUPPLY','MOVE_IN']) for c in cs),
        construction_2026_event_filter=sum(amount(c,['CONSTRUCTION'],first='2026-01-01') for c in cs),
        supply=sum(amount(c,['SUPPLY']) for c in cs))


def main(apply=False):
    from sqlalchemy import select,text
    from sqlalchemy.orm import sessionmaker
    from backend.db import Revision,Mapping,Audit,engine_for,entity_id,upsert_revision,now
    from backend.service import HomeService
    from backend.policy_delivery import build_delivery
    from backend.lh_progress import detail_data
    from backend.read_scope import projection_reads
    engine=engine_for();s=HomeService(engine);folder=Path(s.data_dir)/'candidate-external-review-20261021';src=folder/'sources'
    manifest=json.loads((src/'capture_manifest.json').read_text())
    for item in manifest:
        if item.get('sha256'):assert hashlib.sha256((src/item['file']).read_bytes()).hexdigest()==item['sha256']
    ns={'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
    with zipfile.ZipFile(src/'lh_july_construction.docx') as z:root=ET.fromstring(z.read('word/document.xml'))
    work=[]
    for tr in root.findall('.//w:tr',ns):
        cells=[' '.join(t.text or '' for t in c.findall('.//w:t',ns)) for c in tr.findall('w:tc',ns)]
        if '송림4' in re.sub(r'\s+','',str(cells)) and '건축' in cells:work.append(cells)
    assert len(work)==1 and work[0][8:12]==['1198','호','24-07-10','28-01-21']
    info=detail_data((src/(SONG+'.html')).read_bytes())['cntCwsttDetailInfo']
    assert info['hshCnt']==1198 and info['csstDt']=='2024-07-10'
    gosi_text=(src/'yeonnam_final_0.txt').read_text()
    assert all(x in gosi_text for x in ['2025.3.13.','82','2025. 7. 3.','244-16'])
    plan=dict(new_independent_policy_admissions=0,existing_approved_site_recovered=1,
        recovered_housing_units=1198,recovered_construction_date='2024-07-10',
        added_2026_construction_units=0,duplicate_source_augmentations=len(PAIRS),non_official_company_evidence_links=1,
        unassigned_candidate_correction=dict(project_id=YEON,old_estimate=167,official_housing_units=82,sale_units=65,rent_units=17),
        original_project_payloads_preserved=True,original_policy_program_assignments_preserved=True)
    if not apply:
        print(json.dumps(plan,ensure_ascii=False,indent=2));return
    receipts=[]
    with engine.begin() as conn:
        conn.execute(text('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ'))
        conn.execute(text('SELECT pg_advisory_xact_lock(9072026)'))
        tx=HomeService(engine,s.data_dir);tx.sessions=sessionmaker(bind=conn,expire_on_commit=False)
        with projection_reads():before=build_delivery(tx,date(2026,10,21),include_portfolio_comparisons=False)
        protected={c['id']:c for c in before['portfolio_cohorts']}
        with tx.sessions.begin() as db:
            def current(eid):return db.scalar(select(Revision).where(Revision.entity_id==eid,Revision.superseded_at.is_(None)))
            marker=current(entity_id('collection_research','official_review',BATCH))
            if marker:
                print(json.dumps(dict(already_applied=True,plan=marker.payload['plan']),ensure_ascii=False));return
            original={r.entity_id:r.payload_hash for r in db.scalars(select(Revision).where(Revision.kind=='project',Revision.superseded_at.is_(None)))}
            mappings={m.project_id:(m.policy_id,m.program_id,m.status,m.revision_no) for m in db.scalars(select(Mapping))}
            stamp=now().isoformat()
            def put(kind,sid,key,value,action='CANDIDATE_REVIEW'):
                prev=current(entity_id(kind,sid,key));prior=deepcopy(prev.payload) if prev else {}
                row,outcome=upsert_revision(db,kind,sid,key,value,BATCH)
                if outcome!='unchanged':db.add(Audit(entity_id=row.entity_id,action=action,before=prior,after=value))
                receipts.append(dict(kind=kind,entity_id=row.entity_id,revision_no=row.revision_no,outcome=outcome));return row
            def meta(basis,inferred=False):
                return dict(origin='MANUAL',actor=ACTOR,reason=basis,changed_at=stamp,batch_id=BATCH,
                    inferred=inferred,input_rule='OFFICER_VERIFIED_SOURCE' if not inferred else 'PREDECESSOR_ASSUMPTION',input_basis=basis)
            old=current(SONG_OLD);cand=current(SONG)
            assert old.payload['construction_start_evidence']['scope']=='SINGLE_BLOCK'
            assert old.payload['planned_units']==cand.payload['planned_units']==1198
            assert cand.payload['source_object_id']=='102283|01'
            prior_mapping=db.scalar(select(Mapping).where(Mapping.project_id==SONG_OLD));assert prior_mapping.status=='CONFIRMED' and prior_mapping.policy_id==POLICY
            target_mapping=db.scalar(select(Mapping).where(Mapping.project_id==SONG));assert target_mapping.policy_id=='UNASSIGNED' and target_mapping.status=='REVIEW'
            basis=('공식 자료 자동 매핑 - 기존 승인 동일 현장 원천 보강. 인천송림4 지구102283·블록01, '
                '건축1198호·2024-07-10 착공을 LH 공사원장 동일 행과 공사진행현황으로 대조. '
                '기존 CONFIRMED 원천 '+SONG_OLD+'의 정책·프로그램 승인을 승계한다. '
                '숫자블록1의 건설 원천이 관리집계에서 제외돼 있던 단일 현장을 한 번 복원. '
                '새로운 9·7 개별 선정 공고 확보나 2026년 신규 착공이라는 뜻이 아님.')
            source_fact=dict(stage='CONSTRUCTION',kind='ACTUAL',milestone='CONSTRUCTION',date='2024-07-10',
                units=1198,date_basis='EVENT',source_event_date='2024-07-10',source_type='OFFICIAL',
                basis='LH 2026년7월 공사추진현황의 송림4 단일블록 건축 행:1198호·착공24-07-10',evidence_url=LH_URL)
            document=dict(name='인천송림4 1블록 · 단일 주택공사 범위 확인',sample_kind='document_evidence',
                region='인천광역시',district='인천송림4',block='1',planned_units=1198,
                matched_project_ids=[SONG,SONG_OLD],facts=[source_fact],source_type='OFFICIAL',checked_source_type='OFFICIAL',
                verification_status='SOURCE_CONTENT_CHECKED',review_label='공식 자료 자동 매핑',evidence_url=LH_URL,
                source_base_date='2026-07-01',base_date='2026-10-21',source_row=work[0],
                original_file='candidate-external-review-20261021/sources/lh_july_construction.docx',
                original_sha256=hashlib.sha256((src/'lh_july_construction.docx').read_bytes()).hexdigest(),
                government_2026_actual_inclusion=False,policy_admission='EXISTING_APPROVAL_SAME_SITE',
                completion_source_conflict={'work_register':'2028-01-21','progress_page':'2027-09-30','resolution':'미확정. 착공 사실 검증과 구분; 준공·입주 실적 생성 안 함'})
            doc=put('document_evidence','official_document',BATCH+':songrim',document)
            put('evidence_bridge','cross_source',SONG+':'+doc.entity_id,dict(project_id=SONG,source_entity_id=doc.entity_id,
                source_revision_no=doc.revision_no,evidence_source_id='official_document',source_id='official_document',
                source_name=document['name'],evidence_url=LH_URL,facts=[source_fact],units=1198,status='CONFIRMED',reviewed=True,
                review_label='공식 자료 자동 매핑',source_type='OFFICIAL',checked_source_type='OFFICIAL',
                relation_type='EXACT_EXISTING_APPROVED_SITE',basis=basis,base_date='2026-10-21'))
            target_mapping.policy_id=prior_mapping.policy_id;target_mapping.program_id=prior_mapping.program_id
            target_mapping.status='CONFIRMED';target_mapping.revision_no+=1;target_mapping.basis=basis
            target_mapping.evidence_url=cand.payload['evidence_url'];target_mapping.reviewed_at=now()
            db.add(Audit(entity_id=SONG,action='EXISTING_SITE_SOURCE_LINK',before=dict(policy_id='UNASSIGNED',status='REVIEW'),
                after=dict(policy_id=target_mapping.policy_id,program_id=target_mapping.program_id,basis=basis)))
            for source_pid,master_pid,units,code in PAIRS:
                source=current(source_pid);master=current(master_pid)
                assert source.payload['planned_units']==units and source.payload['source_object_id']==code+'|01'
                assert master.payload['planned_units']==units
                m=db.scalar(select(Mapping).where(Mapping.project_id==master_pid));assert m.status=='CONFIRMED' and m.policy_id==POLICY
                label='공식 자료 자동 매핑 - 동일 LH 지구코드·블록·호수 원천 보강; 신규 물량0호'
                put('evidence_bridge','cross_source',master_pid+':'+source_pid,dict(project_id=master_pid,
                    source_entity_id=source_pid,source_revision_no=source.revision_no,source_id='lh_progress',evidence_source_id='lh_progress',
                    source_name=source.payload['name'],evidence_url=source.payload['evidence_url'],facts=[],units=units,
                    status='CONFIRMED',reviewed=True,review_label=label,source_type='OFFICIAL',checked_source_type='OFFICIAL',
                    relation_type='EXACT_EXISTING_SITE_IDENTITY_ONLY',basis=label,identity_scope=dict(lh_district_code=code,block='01',units=units),
                    excluded_from_new_quantity=True,base_date='2026-10-21'))
            yeon_fact=dict(stage='APPROVAL',kind='ACTUAL',milestone='APPROVAL',date='2025-03-13',units=82,
                source_type='OFFICIAL',evidence_url=YEON_URL,basis='2025-118호 원문7항 최초사업시행계획 인가일; 변경고시2025-07-03과 별개')
            yeon_doc=put('document_evidence','official_document',BATCH+':yeonnam',dict(name='연남동244-16 변경인가 공식82호',
                sample_kind='document_evidence',region='서울특별시',municipality='마포구',address='서울특별시 마포구 연남동244-16',
                matched_project_ids=[YEON],facts=[yeon_fact],planned_units=82,scope_breakdown={'분양':65,'임대':17},
                original_file='candidate-external-review-20261021/sources/yeonnam_final_0.pdf',
                original_sha256=hashlib.sha256((src/'yeonnam_final_0.pdf').read_bytes()).hexdigest(),
                source_date='2025-07-03',base_date='2026-10-21',evidence_url=YEON_URL,source_type='OFFICIAL',
                checked_source_type='OFFICIAL',verification_status='SOURCE_CONTENT_CHECKED',review_label='공식 자료 자동 매핑',
                notice_number='서울특별시 마포구 제2025-118호',source_page=1,policy_membership='UNVERIFIED'))
            put('evidence_bridge','cross_source',YEON+':'+yeon_doc.entity_id,dict(project_id=YEON,
                source_entity_id=yeon_doc.entity_id,source_revision_no=yeon_doc.revision_no,source_id='official_document',
                evidence_source_id='official_document',source_name='마포구2025-118호 변경인가 원문',evidence_url=YEON_URL,
                facts=[yeon_fact],units=82,status='CONFIRMED',reviewed=True,review_label='공식 자료 자동 매핑',
                relation_type='EXACT_NAME_ADDRESS_OFFICIAL_PERMIT',source_type='OFFICIAL',checked_source_type='OFFICIAL',
                basis='같은 사업명·대표지번244-16·조합 및 원문 합계82호 대조. 9·7 정책 귀속은 별도 유보',base_date='2026-10-21'))
            company_url='https://samhyundnc.co.kr/works/yeonnam-244-16-lh'
            company_label='담당자 검토 - 비공식 자료: 삼현디앤씨 사업실적'
            company_fact=dict(stage='CONSTRUCTION',kind='STATE',date='2026-10-21',date_basis='OBSERVED_BY',
                basis=company_label+' · 시공중 표제 및2026.01 철거진행중 이력. 실제 착공일 확정 아님',source_type='NON_OFFICIAL')
            company_doc=put('document_evidence','external_officer',BATCH+':yeonnam-company',dict(
                name='연남동244-16 삼현디앤씨 사업실적',sample_kind='document_evidence',region='서울특별시',
                matched_project_ids=[YEON],planned_units=82,facts=[company_fact],evidence_url=company_url,
                source_type='NON_OFFICIAL',checked_source_type='NON_OFFICIAL',review_label=company_label,
                verification_status='SOURCE_CONTENT_CHECKED',base_date='2026-10-21',source_publication_date=None,
                original_file='candidate-external-review-20261021/sources/yeonnam_manager.html',
                original_sha256=hashlib.sha256((src/'yeonnam_manager.html').read_bytes()).hexdigest(),
                source_conflicts=['공식고시대지2787.0㎡와사업관리소개2756.1㎡차이:공식고시우선'],
                policy_membership='UNVERIFIED',exact_construction_start_date=None))
            put('evidence_bridge','cross_source',YEON+':'+company_doc.entity_id,dict(project_id=YEON,
                source_entity_id=company_doc.entity_id,source_revision_no=company_doc.revision_no,source_id='external_officer',
                evidence_source_id='external_officer',source_name='삼현디앤씨 연남동244-16 사업실적',evidence_url=company_url,
                facts=[company_fact],units=82,status='CONFIRMED',reviewed=True,review_label=company_label,
                source_type='NON_OFFICIAL',checked_source_type='NON_OFFICIAL',relation_type='OFFICER_NAME_ADDRESS_SCOPE',
                basis=company_label+' · 동일 사업명244-16·마포구·82호·인가2025.03 대조. 정책 귀속은 별도 유보',base_date='2026-10-21'))
            profile=current(entity_id('project_profile','manual_project',YEON));value=deepcopy(profile.payload)
            assert value['overrides']['planned_units']['value']==167 and value['overrides']['planned_units']['inferred']
            prior=deepcopy(value['overrides']['planned_units'])
            note='마포구2025-118호 원문82호(분양65·임대17). 기존167호는 동종사업 중앙값 추정이며 공식 수량이 아니므로 대체'
            value['overrides']['planned_units']=dict(meta(note),value=82,evidence_url=YEON_URL,
                source_entity_id=yeon_doc.entity_id,previous_estimate=prior)
            value['progress']['BUSINESS']=dict(meta('공식 인가일 이전 사업화 도달의 관측상한; 정확한 사업화일 미확보',True),
                event_date='2025-03-13',source_event_date=None,date_basis='OBSERVED_BY',units=82,evidence_url=YEON_URL)
            value['progress']['APPROVAL']=dict(meta(yeon_fact['basis']),event_date='2025-03-13',source_event_date='2025-03-13',
                date_basis='EVENT',units=82,evidence_url=YEON_URL,source_entity_id=yeon_doc.entity_id,source_type='OFFICIAL',review_label='공식 자료 자동 매핑')
            value.get('stage_states',{}).pop('APPROVAL',None)
            value['last_changes']=dict(batch_id=BATCH,capacity=note,policy_membership='UNASSIGNED 유지',
                schedule_note='후속 추정 일정은 기존 관리 추정이며 실제 사건 증빙 아님. 이번에는 공식 확인 인가일·호수만 확정')
            put('project_profile','manual_project',YEON,value)
            for goal in list(db.scalars(select(Revision).where(Revision.kind=='execution_schedule',Revision.superseded_at.is_(None)))):
                if goal.payload.get('project_id')!=YEON:continue
                g=deepcopy(goal.payload);g.update(units=82,actor=ACTOR,reason=note,changed_at=stamp,batch_id=BATCH)
                if g['stage'] in ('BUSINESS','APPROVAL'):
                    g.update(due_date='2025-03-13',inferred=g['stage']=='BUSINESS',input_rule='PREDECESSOR_ASSUMPTION' if g['stage']=='BUSINESS' else 'OFFICIAL_PLAN_ACCEPTED',
                        input_basis='최초 인가일 확인 기준선; 사업화는 상한 추정' if g['stage']=='BUSINESS' else yeon_fact['basis'],evidence_url=YEON_URL)
                else:g['input_basis']=g.get('input_basis','')+' · 82호 공식범위로 수량 보정; 일정은 기존 추정'
                put('execution_schedule',goal.source_id,YEON+':'+g['stage'],g)
            marker_value=dict(name='외부 후보 재검증 결과',plan=plan,base_date='2026-10-21',facts=[],evidence_url=YEON_URL,
                policy_id=POLICY,source_type='REVIEW_RECORD',review_label='기존 승인현장 복원·신규 귀속 유보')
            put('collection_research','official_review',BATCH,marker_value)
            db.flush()
            assert original=={r.entity_id:r.payload_hash for r in db.scalars(select(Revision).where(Revision.kind=='project',Revision.superseded_at.is_(None)))}
            after_mappings={m.project_id:(m.policy_id,m.program_id,m.status,m.revision_no) for m in db.scalars(select(Mapping))}
            assert {k:v for k,v in mappings.items() if k!=SONG}=={k:v for k,v in after_mappings.items() if k!=SONG}
            assert after_mappings[YEON][0]=='UNASSIGNED'
        with projection_reads():after=build_delivery(tx,date(2026,10,21),include_portfolio_comparisons=False)
        ac={c['id']:c for c in after['portfolio_cohorts']}
        assert set(ac)-set(protected)=={SONG} and not set(protected)-set(ac)
        assert all(ac[k]==v for k,v in protected.items()),'기존 관리사업 값 변경 감지'
        bs=signature(before);ass=signature(after)
        assert ass['capacity']-bs['capacity']==1198
        assert ass['construction_reached']-bs['construction_reached']==1198
        assert ass['construction_direct']-bs['construction_direct']==1198
        assert ass['construction_2026_event_filter']==bs['construction_2026_event_filter']
        assert ass['supply']==bs['supply']
        result=dict(plan=plan,before=bs,after=ass,existing_cohorts_exactly_preserved=True,
            existing_individual_official_comparison_values_preserved=True,original_project_payloads_preserved=True,
            changed_mapping_project_ids=[SONG],receipts=receipts)
    (folder/'applied.json').write_text(json.dumps(result,ensure_ascii=False,indent=2,default=str))
    print(json.dumps({k:v for k,v in result.items() if k!='receipts'},ensure_ascii=False,indent=2))

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--apply',action='store_true');args=parser.parse_args();main(args.apply)
