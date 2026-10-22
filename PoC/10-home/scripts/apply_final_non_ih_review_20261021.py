"""Apply source-pinned corrections, retaining source originals and audit history."""
import argparse
from copy import deepcopy
from datetime import date, timedelta
import hashlib
import json
from pathlib import Path
import re
import zipfile
import xml.etree.ElementTree as ET

BATCH='final-non-ih-review-20261021'
ACTOR='담당자 대행 · 공식 원천 범위·일정 최종 대조'
BYEONG='PRO_e05c4608f73fa5151e560558'
GWANG='PRO_9636a0a7813451b2cb76372b'
LH_PLAN='https://apply.lh.or.kr/lhapply/apply/noti/sp/list.do?listCo=100&mi=201523&sUppAisTpCd=05&srchY=Y'
LH_WORK='https://www.lh.or.kr/boardDownload.es?bid=0007&list_no=654682&seq=14'
GOV='https://www.fsc.go.kr/comm/getFile?srvcId=BBSTY1&upperNo=87948&fileTy=ATTACH&fileNo=3#page=6'


def main(apply=False):
    from sqlalchemy import select,text
    from backend.db import Revision,Mapping,Audit,entity_id,upsert_revision,engine_for,now
    from backend.service import HomeService
    from backend.collectors import parse_lh_plan
    from backend.lh_notice_detail import parse_detail,VERSION
    from backend.block_identity import title_blocks
    s=HomeService(engine_for());folder=Path(s.data_dir)/BATCH
    manifest=json.loads((folder/'capture_manifest.json').read_text())
    for source in manifest:
        if source.get('sha256'):assert hashlib.sha256((folder/source['file']).read_bytes()).hexdigest()==source['sha256']
    _,_,rows=parse_lh_plan((folder/'lh_sale_current.html').read_bytes())
    parts=[r for r in rows if r['name']=='병점복합타운 주복1']
    housing=[r for r in parts if '오피스텔' not in r.get('note','')]
    ancillary=[r for r in parts if '오피스텔' in r.get('note','')]
    assert sum(r['units'] for r in housing)==726 and sum(r['units'] for r in ancillary)==54
    assert {r['supply_month'] for r in housing}=={'2026-11'}
    assert {r['supply_month'] for r in ancillary}=={'2026-12'}
    ns={'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
    work_path=folder/'lh_july_construction.docx'
    with zipfile.ZipFile(work_path) as z:root=ET.fromstring(z.read('word/document.xml'))
    work=[]
    for row in root.findall('.//w:tr',ns):
        cells=[' '.join(t.text or '' for t in c.findall('.//w:t',ns)) for c in row.findall('w:tc',ns)]
        if any('병점' in c for c in cells) and '건축' in cells:work.append(cells)
    assert len(work)==1 and work[0][8:12]==['726','호','25-12-31','29-03-07']
    assert '착공일' in ''.join(root.itertext())
    decisions=dict(housing_units=726,ancillary_officetel_rooms=54,government_mixed_total=780,
        construction_actual_date='2025-12-31',completion_plan='2029-03-07',
        supply_plan='2026-11',gwaggyo_supply_plan='2026년4분기',
        actual_start_is_2026_output=False,work_source_row=work[0])
    if not apply:
        print(json.dumps(decisions,ensure_ascii=False,indent=2));return
    results=[]
    with s.sessions.begin() as db:
        db.execute(text('SELECT pg_advisory_xact_lock(9072026)'))
        def current(eid):return db.scalar(select(Revision).where(Revision.entity_id==eid,Revision.superseded_at.is_(None)).with_for_update())
        def put(kind,sid,key,payload,action):
            old=current(entity_id(kind,sid,key));before=deepcopy(old.payload) if old else {}
            r,outcome=upsert_revision(db,kind,sid,key,payload,BATCH)
            if outcome!='unchanged':db.add(Audit(entity_id=r.entity_id,action=action,before=before,after=payload))
            results.append(dict(entity_id=r.entity_id,kind=kind,outcome=outcome,revision_no=r.revision_no))
            return r
        marker=current(entity_id('collection_research','official_review',BATCH))
        if marker:
            print(json.dumps(dict(already_applied=True,decisions=marker.payload['decisions']),ensure_ascii=False));return
        original={r.entity_id:r.payload_hash for r in db.scalars(select(Revision).where(Revision.kind=='project',Revision.superseded_at.is_(None)))}
        mappings=[(r.project_id,r.revision_no,r.status,r.policy_id,r.program_id) for r in db.scalars(select(Mapping).order_by(Mapping.project_id))]
        stamp=now().isoformat()
        def meta(basis,inferred=False):
            return dict(actor=ACTOR,reason=basis,changed_at=stamp,batch_id=BATCH,origin='MANUAL',inferred=inferred)
        def document(key,pid,facts,url,files,**extra):
            p=current(pid).payload
            value=dict(name=p['name']+' · 공식 원천 최종 대조',matched_project_ids=[pid],facts=facts,
                planned_units=726 if pid==BYEONG else 600,region=p['region'],
                sample_kind='document_evidence',verification_status='SOURCE_CONTENT_CHECKED',
                evidence_url=url,checked_source_type='OFFICIAL',source_type='OFFICIAL',
                review_label='공식 자료 자동 매핑',status='CONFIRMED',reviewed=True,
                original_files=[dict(file=BATCH+'/'+f,sha256=hashlib.sha256((folder/f).read_bytes()).hexdigest()) for f in files],
                base_date='2026-10-21',**extra)
            doc=put('document_evidence','official_document',key,value,'OFFICIAL_SCOPE_PINNED')
            bridge=dict(project_id=pid,source_entity_id=doc.entity_id,source_revision_no=doc.revision_no,
                source_id='official_document',evidence_source_id='official_document',source_name=value['name'],
                evidence_url=url,facts=facts,status='CONFIRMED',reviewed=True,review_actor=ACTOR,
                review_label='공식 자료 자동 매핑',checked_source_type='OFFICIAL',
                basis='공식 원천 동일 사업·주택 구성·사건일 확인',relation_type='OFFICIAL_VERIFIED_HOUSING_SCOPE',base_date='2026-10-21')
            put('evidence_bridge','cross_source',pid+':'+doc.entity_id,bridge,'OFFICIAL_SCOPE_LINKED')
            return doc
        basis='공식 LH 공급계획: 아파트726호(11월)와 오피스텔54실(12월)을 분리. 주택 호수에 오피스텔을 합산하지 않음'
        construction=dict(stage='CONSTRUCTION',kind='ACTUAL',milestone='CONSTRUCTION',date='2025-12-31',units=726,
            date_basis='EVENT',source_event_date='2025-12-31',basis='LH 7월 공사추진현황 동일 건축 행:726호·착공2025-12-31',
            evidence_url=LH_WORK,source_type='OFFICIAL',review_label='공식 자료 자동 매핑')
        facts=[construction,
            dict(stage='CONSTRUCTION',kind='PLAN',milestone='COMPLETION',date='2029-03-07',units=726,basis='LH 공사추진현황 준공 예정일 · 실제 준공 아님',evidence_url=LH_WORK),
            dict(stage='SUPPLY',kind='PLAN',milestone='SUPPLY',date='2026-11',units=726,precision='MONTH',basis=basis,evidence_url=LH_PLAN)]
        doc=document(BATCH+':byeong-housing',BYEONG,facts,LH_PLAN,['lh_sale_current.html','lh_july_construction.docx'],
            scope_breakdown={'공공분양':726},ancillary_scope=dict(type='오피스텔',rooms=54,plan_month='2026-12',housing_aggregation=False),
            original_mixed_units=780,construction_source_url=LH_WORK,government_reported_units=780)
        gw_basis='10.16 관계부처 공식 첨부6쪽 광교A17 600호:2026년4분기 공급계획. 일자는 분기말 관리 기준, 실제 공고일 아님'
        gwfact=dict(stage='SUPPLY',kind='PLAN',milestone='SUPPLY',date='2026년4분기',units=600,precision='QUARTER',basis=gw_basis,evidence_url=GOV)
        gwdoc=document(BATCH+':gwaggyo-plan',GWANG,[gwfact],GOV,['government_appendix.pdf','gwaggyo_province_plan.pdf'],
            source_publication_date='2026-10-16',source_document_page=6,
            scope_breakdown={'지분적립형공공분양':240,'일반공공분양':360})
        for pid in (BYEONG,GWANG):
            profile_key=entity_id('project_profile','manual_project',pid);old=current(profile_key)
            assert old
            value=deepcopy(old.payload);overrides=value.setdefault('overrides',{})
            if pid==BYEONG:
                assert overrides.get('planned_units',{}).get('value',780)==780
                overrides['planned_units']=dict(meta(basis),value=726,input_rule='OFFICER_VERIFIED_SOURCE',evidence_url=LH_PLAN)
                value['housing_scope']=dict(housing_units=726,ancillary_rooms=54,original_mixed_total=780,evidence_url=LH_PLAN,basis=basis)
                progress=value.setdefault('progress',{})
                progress['CONSTRUCTION']=dict(meta(construction['basis']),event_date='2025-12-31',units=726,
                    input_rule='OFFICER_VERIFIED_SOURCE',date_basis='EVENT',source_event_date='2025-12-31',evidence_url=LH_WORK)
                for stage in ('BUSINESS','APPROVAL'):
                    reason='동일 주택726호 실제착공 확인에 따른 선행 단계 완료 상한 · 정확한 사업화/인허가 사건일 미확보'
                    progress[stage]=dict(meta(reason,True),event_date='2025-12-31',units=726,input_rule='OFFICER_PREDECESSOR_ESTIMATE',
                        date_basis='OBSERVED_BY',source_event_date=None,observed_by='2025-12-31',evidence_url=LH_WORK)
                # These old percentages were derived from the superseded 2030 start.
                for field in ('progress_pct','progress_date'):
                    if overrides.get(field,{}).get('inferred'):overrides.pop(field)
                value['stage_states']={k:v for k,v in value.get('stage_states',{}).items() if k not in progress}
            else:
                overrides['tenure']=dict(meta('경기도2026주거종합계획:지분적립형240호+일반공공분양360호'),value='공공분양',
                    input_rule='OFFICER_VERIFIED_SOURCE',evidence_url=GOV)
                overrides['supply_type']=dict(meta(gw_basis),value='PUBLIC')
                overrides['supply_type_basis']=dict(meta(gw_basis),value='경기도 공식 계획 광교A17 공공분양600호(지분적립240+일반360)')
                overrides['supply_type_evidence_url']=dict(meta(gw_basis),value=GOV)
                value['supply_form_breakdown']={'지분적립형공공분양':240,'일반공공분양':360}
            value['last_changes']=dict(batch_id=BATCH,basis=basis if pid==BYEONG else gw_basis)
            put('project_profile','manual_project',pid,value,'OFFICIAL_PROFILE_CORRECTED')
        updates={BYEONG:{'BUSINESS':('2025-12-31','DAY',True),'APPROVAL':('2025-12-31','DAY',True),
            'CONSTRUCTION':('2025-12-31','DAY',False),'COMPLETION':('2029-03-07','DAY',False),
            'SUPPLY':('2026-11-30','MONTH',False),'MOVE_IN':('2029-09-07','DAY',True)},
            GWANG:{'SUPPLY':('2026-12-31','QUARTER',False)}}
        for pid,stages in updates.items():
            for stage,(due,precision,inferred) in stages.items():
                key=pid+':'+stage;old=current(entity_id('execution_schedule','officer',key));assert old
                prior=deepcopy(old.payload);value=deepcopy(prior)
                explanation=(basis if stage=='SUPPLY' else 'LH 공사원장 착공·준공예정 채택 및 선후관계 관리 기준 보정') if pid==BYEONG else gw_basis
                if stage=='MOVE_IN':explanation='원천 준공예정2029-03-07+기존 모형 준공→입주 평균184일 · 실제 입주 확정 아님'
                value.update(meta(explanation,inferred),due_date=due,units=726 if pid==BYEONG else 600,
                    status='CONFIRMED',basis=explanation,input_basis=explanation,
                    input_rule='OFFICER_AVERAGE_DURATION' if inferred else 'OFFICIAL_PLAN_ACCEPTED',
                    source_precision=precision,date_precision=precision,source_type='ESTIMATE' if inferred else 'OFFICIAL',
                    source_date_label='2026-11' if pid==BYEONG and stage=='SUPPLY' else '2026년4분기' if pid==GWANG else due,
                    date_conversion='MONTH_END' if precision=='MONTH' else 'PERIOD_END' if precision=='QUARTER' else 'EXACT',
                    evidence_url=LH_PLAN if pid==BYEONG and stage=='SUPPLY' else LH_WORK if pid==BYEONG else GOV,
                    source_entity_id=doc.entity_id if pid==BYEONG else gwdoc.entity_id,
                    previous_schedule=prior,shift_days=(date.fromisoformat(due)-date.fromisoformat(value['baseline']['due_date'])).days)
                value.pop('calculation',None)
                put('execution_schedule','officer',key,value,'OFFICIAL_SCHEDULE_CORRECTED')
        # Correct old AA10-2 documents previously truncated to the AA10 parent.
        for old in db.scalars(select(Revision).where(Revision.kind=='document_evidence',Revision.source_id=='lh_notice_detail',Revision.superseded_at.is_(None))).all():
            if old.payload.get('parser_version')==VERSION:continue
            prior=old.payload;blocks=title_blocks(prior['notice_title'])
            if len(blocks)!=1:raise ValueError('old document requires explicit split review')
            block=next(iter(blocks));notice=current(prior['notice_entity_id'])
            n=dict(notice.payload,id=notice.entity_id,revision_no=notice.revision_no)
            payload=parse_detail((s.data_dir/prior['original_file']).read_bytes(),n,(prior['region'],prior['district'],block))
            payload['original_file']=prior['original_file'];key=n['notice_no']
            assert entity_id('document_evidence','lh_notice_detail',key)==old.entity_id
            put('document_evidence','lh_notice_detail',key,payload,'SPLIT_BLOCK_SCOPE_CORRECTED')
        assert {r.entity_id:r.payload_hash for r in db.scalars(select(Revision).where(Revision.kind=='project',Revision.superseded_at.is_(None)))}==original
        assert [(r.project_id,r.revision_no,r.status,r.policy_id,r.program_id) for r in db.scalars(select(Mapping).order_by(Mapping.project_id))]==mappings
        put('collection_research','official_review',BATCH,dict(decisions=decisions,base_date='2026-10-21',
            ih_api_excluded=True,policy_mappings_changed=0,source_projects_unchanged=True,results=deepcopy(results)),'FINAL_NON_IH_REVIEW')
    output=dict(decisions=decisions,results=results,policy_mappings_changed=0,source_projects_unchanged=True)
    (folder/'applied.json').write_text(json.dumps(output,ensure_ascii=False,indent=2));print(json.dumps(output,ensure_ascii=False))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--apply',action='store_true');args=parser.parse_args();main(args.apply)
