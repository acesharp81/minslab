"""Pinned official-document review; default preview, explicit --apply to persist.

Existing officer quantities, mappings and schedules are immutable in this review.
Conversion-based policy admission is a delegated assessment, not a claim that
the government individually named these four blocks as 9.7 projects.
"""
import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from sqlalchemy import select, text
from backend.collectors import urban_project
from backend.db import Audit, Mapping, ProgramMapping, Revision, engine_for, entity_id, upsert_revision
from backend.service import HomeService
from backend.lh_spring_followup import review_key
from scripts.review_policy_readmission_20261019 import protected, digest

POLICY='POL_2025_0907'
ACTOR='담당자 대행 · 남은 작업 완료 사용자 지시 2026-10-20'
PROGRAM='LH 직접시행 전환·토지이용 효율화'
C5='PRO_3825614a4d690a6e58e8bbad'
SKKU='PRO_47484524b36e9d7b3af3fe27'
WIRYE='PRO_2d1e1ea17c963204dbdfbe9a'
POLICY_URL='https://www.korea.kr/common/download.do?fileId=198344116#page=6'
CASES=[
 dict(district='수원당수2',block='B5',units=364,city='수원시',area=23922,far=170,alias='C1',notice='636471',
      basis='국토부 제2025-807호의 C1(민간분양)과 LH 공모 B5의 부지 23,922㎡·364호·용적률 170%가 일치한다. 평형별 239+125=364호를 대조했다.'),
 dict(district='수원당수2',block='B7',units=880,city='수원시',area=42841,far=230,alias='C4',notice='636471',
      basis='국토부 제2025-807호의 C4(민간분양)와 LH 공모 B7의 부지 42,841㎡·880호·용적률 230%가 일치한다. 과거 C4+C5 통합 계획과 신규 블록 명칭을 구분했다.'),
 dict(district='안산장상',block='A10',units=320,city='안산시',area=12989,far=200,alias='A10',notice='623464',
      basis='국토부 제2025-665호 A10의 기정 민간분양→변경 공공분양을 확인했다. LH 공모의 A10·부지 12,989㎡·용적률 200%가 일치한다. 지구계획 325호와 개별 공모 건설계획 320호를 구분하여 후자의 320호를 채택했다.'),
 dict(district='고양창릉',block='B1',units=1594,city='고양시',area=79119,far=200,alias='B1',notice='628391',
      basis='국토부 제2025-813호 B1의 민간분양 1,059호→공공분양 1,059호 전환과 통합공공임대 317호를 확인했다. LH 공모 B1의 부지 79,119㎡·용적률 200%가 일치한다. 지구계획 1,376호와 후속 공모 1,594호를 구분하여 전체 사업 규모는 1,594호로 채택하되, 이를 정책 순증 또는 전환분 1,594호로 해석하지 않는다.'),
]

def main(apply=False):
    s=HomeService(engine_for());folder=s.data_dir/'completion-20261020'
    lh=json.loads((folder/'lh-documents-manifest.json').read_text())
    lh+=json.loads((folder/'lh-extra-manifest.json').read_text())
    land=json.loads((folder/'land-documents-manifest.json').read_text())
    tender=next(x for x in lh if x['id']=='732709-1')
    press=next(x for x in lh if x['id']=='press-12011')
    docs=[dict(x,key=x['id'],source_date=x.get('date')) for x in (tender,press)]
    awards={key:next(x for x in lh if x['id']==key) for key in ('733310-1','733198-1','733303-1')}
    docs += [dict(x,key=x['id'],source_date=x['date']) for x in awards.values()]
    docs += [dict(x,key='eum-'+x['id'],source_date=x['date']) for x in land if x['id'] in ('623464','628391')]
    old=json.loads((s.data_dir/'continuation-20261020/followup-documents-manifest.json').read_text())
    for key in ('notice-636471','notice-636472'):
        x=next(x for x in old if x['key']==key)
        docs.append(dict(x,key=key,file='../continuation-20261020/'+x['file'],
                         text_file='../continuation-20261020/'+key+'.txt'))
    for d in docs:
        if hashlib.sha256((folder/d['file']).read_bytes()).hexdigest()!=d['sha256']:
            raise ValueError('검토 원문 판본 변경: '+d['key'])
    tender_text=(folder/tender['text_file']).read_text()
    if not all(x in tender_text for x in ('12,989','79,119','23,922','42,841','35,553','26.12월')):
        raise ValueError('공모의 검토 필드 변경')
    before=protected(s);actions=[];links=[];result_projects=[]
    with s.sessions.begin() as db:
        if s.engine.dialect.name=='postgresql':db.execute(text('SELECT pg_advisory_xact_lock(1019193)'))
        projects=db.scalars(select(Revision).where(Revision.kind=='project',Revision.superseded_at.is_(None))).all()
        by_id={p.entity_id:p for p in projects}
        pg=db.scalar(select(ProgramMapping).where(ProgramMapping.name==PROGRAM,ProgramMapping.policy_id==POLICY,ProgramMapping.status=='CONFIRMED'))
        if not pg:raise ValueError('승인 프로그램 미확보')
        for pid,units in [(C5,490),(SKKU,1800),(WIRYE,1000)]:
            if pid not in by_id or by_id[pid].payload.get('planned_units')!=units:
                raise ValueError('기존 승인 사업 판본 변경: '+pid)
        def save(kind,source,key,payload):
            if not apply:return entity_id(kind,source,key),1
            row,outcome=upsert_revision(db,kind,source,key,payload,'completion-20261020')
            actions.append(dict(kind=kind,id=row.entity_id,outcome=outcome))
            if outcome!='unchanged':
                db.add(Audit(entity_id=row.entity_id,action='COMPLETION_EVIDENCE_REVIEW',before={},
                    after=dict(actor=ACTOR,kind=kind,basis=payload.get('basis') or payload.get('mapping_basis'))))
            return row.entity_id,row.revision_no
        saved={}
        for d in docs:
            url=d.get('landing_url') or d.get('listing') or d['url']
            date=d.get('source_date') or '2026-04-08'
            p=dict(name=d.get('name') or d['key'],source_object_id='completion:'+d['key'],sample_kind='document_evidence',
                source_date=date,base_date=date,evidence_url=url,attachment_url=d['url'],original_sha256=d['sha256'],
                original_file=str((folder/d['file']).resolve().relative_to(s.data_dir.resolve())),
                content_text=(folder/d['text_file']).read_text(),facts=[],units=None,exclude_from_project_totals=True,
                review_actor=ACTOR,verification_status='SOURCE_CONTENT_CHECKED')
            saved[d['key']]=(save('document_evidence','official_document',p['source_object_id'],p),p)
        def bridge(pid,key,basis,facts=None,reference=None,extra=None):
            (sid,rev),doc=saved[key]
            p=dict(project_id=pid,name=doc['name'],source_entity_id=sid,source_revision_no=rev,
                source_id='official_document',evidence_source_id='official_document',source_name=doc['name'],
                evidence_url=doc['evidence_url'],status='CONFIRMED',reviewed=True,review_actor=ACTOR,
                relation_type='REVIEWED_PLAN_AND_IDENTITY',facts=facts or [],reference_facts=reference or [],
                basis=basis,base_date='2026-10-20',units=None,**(extra or {}))
            save('evidence_bridge','cross_source',pid+':'+sid,p)
            links.append(dict(project_id=pid,document=key,facts=p['facts'],reference_facts=p['reference_facts']))
        for case in CASES:
            key='reviewed:732709:'+case['district']+':'+case['block']
            pid=entity_id('project','lh_policy_followup',key)
            same=[p for p in projects if review_key(p.payload)==('경기도',case['district'],case['block'])]
            if any(p.entity_id!=pid for p in same):raise ValueError('동일 블록 중복: '+key)
            basis=(case['basis']+' 9·7 정책의 민간매각 공공택지 LH 직접시행 전환 방식과 '
                '정책 발표 후 공식 지구계획·LH 공공주택 공모를 함께 대조하여 담당자 대행으로 프로그램 귀속을 확정했다. '
                '정부가 이 블록을 9·7 대상으로 개별 명시했다고 주장하는 연결은 아니다. 실제 착공 기록은 추가하지 않는다.')
            if same:
                m=db.scalar(select(Mapping).where(Mapping.project_id==pid))
                if same[0].payload.get('planned_units')!=case['units'] or not m or m.policy_id!=POLICY or m.program_id!=pg.id or m.status!='CONFIRMED':
                    raise ValueError('기존 담당자 변경 보존 필요')
            else:
                p=urban_project(case['district']+' '+case['block'],case['city'],'경기도',case['units'],POLICY,'2026-06-09',PROGRAM)
                p.update(district=case['district'],block=case['block'],developer='LH',tenure='공공분양',
                    source_object_id=key,evidence_url=tender['listing'],policy_evidence_url=POLICY_URL,
                    source_document_sha256=tender['sha256'],source_scope='SINGLE_BLOCK',mapping_basis=basis,
                    facts=[],registration_set='COMPLETION_20261020',land_area_sqm=case['area'],
                    unit_basis='LH 개별 공모 전체 건설계획 · 정책 순증과 구분',
                    schedule_basis='2026년 12월 착공 계획 · 실제 착공 확인 아님')
                save('project','lh_policy_followup',key,p)
                if apply:
                    db.add(Mapping(project_id=pid,policy_id=POLICY,program_id=pg.id,status='CONFIRMED',revision_no=1,
                        basis=ACTOR+' · '+basis,evidence_url=tender['listing']))
                    db.add(Audit(entity_id=pid,action='MAPPING_REVIEW',before={},after=dict(actor=ACTOR,
                        policy_id=POLICY,program_id=pg.id,status='CONFIRMED',basis=basis)))
            fact=dict(stage='CONSTRUCTION',kind='PLAN',date='2026-12',precision='MONTH',units=case['units'],
                      basis='LH 2026.06.09 개별 공모: 주택건설공사 착공 2026년 12월')
            facts=[fact]
            if case['district'] in ('안산장상','고양창릉'):
                facts.append(dict(stage='APPROVAL',kind='PLAN',date='2026-12',precision='MONTH',units=case['units'],
                    basis='LH 2026.06.09 개별 공모: 주택건설사업계획 승인 2026년 12월'))
            bridge(pid,'732709-1',basis,facts)
            bridge(pid,('notice-' if case['notice']=='636471' else 'eum-')+case['notice'],basis)
            award_key={'수원당수2':'733310-1','안산장상':'733303-1','고양창릉':'733198-1'}[case['district']]
            award=awards[award_key]
            business_basis=(f"LH {award['date']} 우선협상대상자 선정 결과에 해당 블록이 명시되어 사업화 단계 도달을 확인. "
                f"공모에서 확인한 동일 블록 관리량 {case['units']}호. 선정 확인일은 최초 사업화일 또는 실제 착공일이 아니다.")
            bridge(pid,award_key,business_basis,[dict(stage='BUSINESS',kind='ACTUAL',date=award['date'],precision='DAY',
                units=case['units'],date_basis='OBSERVED_BY',observed_on=award['date'],source_event_date=None,
                method='OFFICIAL_PARTNER_SELECTED',basis=business_basis)])
            result_projects.append(dict(case,id=pid,basis=basis,new=not same))
        alias_basis=('수원당수 C5의 170+320=490호·면적 35,553㎡·용적률 140%와 '
            'LH 2026.06.09 공모 B4의 동일 필드가 모두 일치한다. 같은 블록의 문서별 명칭으로 연결하고 신규 사업은 만들지 않는다.')
        bridge(C5,'732709-1',alias_basis,[dict(stage='CONSTRUCTION',kind='PLAN',date='2026-12',precision='MONTH',units=490,
            basis='LH 공모 B4(C5 동일 블록)의 2026년 12월 착공 계획')],extra=dict(matched_aliases=['수원당수 C5','수원당수 B4']))
        bridge(C5,'notice-636472',alias_basis)
        business_basis=('LH 2026.07.30 선정 결과의 수원당수 B4는 C5와 같은 490호 블록이다. '
            '계룡건설산업 컨소시엄 우선협상대상자 선정으로 사업화 단계 도달을 확인. 최초 사업화일·실제 착공일로 사용하지 않음.')
        bridge(C5,'733310-1',business_basis,[dict(stage='BUSINESS',kind='ACTUAL',date='2026-07-30',precision='DAY',units=490,
            date_basis='OBSERVED_BY',observed_on='2026-07-30',source_event_date=None,method='OFFICIAL_PARTNER_SELECTED',basis=business_basis)])
        for pid,name,month,units,area in [(SKKU,'서울도봉01 = 성균관대 야구장','2027-06',2100,48055),(WIRYE,'위례 업무용지','2027-03',999,35319)]:
            basis=(f'LH 2026.04.08 보도자료의 9·7 후속 {name}, 부지면적 {area:,}㎡, '
                f'계획 {units:,}호를 기존 사업에 연결했다. 기존 담당자 승인 수량·수동 일정을 유지하고 '
                '새 공모 수량·일정은 참조 근거로 보존한다. 별도 사업으로 중복 가산하지 않는다.')
            bridge(pid,'press-12011',basis,reference=[dict(stage='CONSTRUCTION',kind='PLAN',date=month,precision='MONTH',units=units,basis=basis)],
                extra=dict(approved_schedule_preserved=True,source_plan_units=units))
    after=protected(s);changed=[k for k,v in before.items() if after.get(k)!=v]
    if changed:raise RuntimeError('기존 승인 기록 변경: '+str(changed))
    result=dict(applied=apply,projects=result_projects,new_project_units=sum(c['units'] for c in CASES),
        added_construction_plan_units=sum(c['units'] for c in CASES)+490,added_approval_plan_units=1914,
        business_reached_units_added=3648,actual_construction_units_added=0,
        existing_project_duplicates_prevented=[SKKU,C5],links=links,actions=actions,
        action_counts=dict(Counter(a['outcome'] for a in actions)),protected_existing_records=len(before),
        protected_before=digest(before),protected_after=digest({k:after.get(k) for k in before}),changed_existing_keys=changed)
    filename='registration-preview.json' if not apply else 'registration-idempotence.json' if actions and all(a['outcome']=='unchanged' for a in actions) else 'registration-applied.json'
    if filename=='registration-applied.json' and (folder/filename).exists():
        filename='registration-refinement.json';n=2
        while (folder/filename).exists():
            filename=f'registration-refinement-{n}.json';n+=1
    (folder/filename).write_text(json.dumps(result,ensure_ascii=False,indent=2))
    print(json.dumps({k:v for k,v in result.items() if k not in ('projects','links','actions')},ensure_ascii=False))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--apply',action='store_true');main(p.parse_args().apply)
