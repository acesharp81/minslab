"""Reviewed 9.7 document supplement, applied explicitly and idempotently."""
import json
from pathlib import Path
from sqlalchemy import select, text
from .db import Revision, ProgramMapping, Mapping, Audit, entity_id, upsert_revision, now
from .program_hierarchy import program_id
from .api_samples import today
POLICY='POL_2025_0907'
CATALOG=Path(__file__).parent/'data/policy_program_catalog.json'
PDF='https://eiec.kdi.re.kr/policy/callDownload.do?filenum=2&num=270716'
FOLLOW='https://eiec.kdi.re.kr/policy/materialView.do?num=271965'

def site_records():
    from .collectors import urban_project
    data=[('과천과천 공공주택지구','경기도','과천시',10000,2029,None,13,'서울 남부권 공공택지 공급 조기화','DISTRICT'),('번동2단지','서울특별시','강북구',3048,2030,2033,3,'노후 공공임대 재건축','COMPLEX'),('원종역사 복합개발','경기도','부천시',None,None,None,24,'철도부지 복합개발','SITE')]
    result=[]
    for name,region,city,units,start,move,page,program,scope in data:
        p=urban_project(name,city,region,units,POLICY,'2025-10-01' if move else '2025-09-07',program)
        p.update(source_scope=scope,source_page=page,evidence_url=FOLLOW if move else PDF,registration_set='POLICY_PROGRAM_20261014',unit_basis='후속 공식 추정 계획호수 · 용적률500% 가정 · 확정 실적 아님' if move else '공식 원문 지구 계획 · 현재 실적과 구분',quantity_status='OFFICIAL_ESTIMATE' if move else 'POLICY_PLAN',policy_period_units=None,warnings=['POLICY_PLAN_NOT_ACTUAL','POLICY_PERIOD_QUANTITY_REVIEW'],mapping_basis='정책 원문 명시 사업 · 범위와 후속 변경 검토',start_plan_year=start)
        if move:p.update(existing_stock_units=1766,net_additional_units=1282,source_move_in_label=str(move)+'년',developer='LH',schedule_basis='2030년 착공 · 2033년 입주 추정 계획')
        result.append(('project',name,p))
    return result

def apply(service,dry_run=True):
    catalog=json.loads(CATALOG.read_text());result=dict(dry_run=dry_run,programs_added=[],sources_saved=0,projects_added=[],links_changed=[],preserved=[],district_plans=20)
    old_programs={p['id']:p for p in service.program_links()}
    idmap={p['external_id']:p.get('reuse_id') or program_id(p['fields']['name'],POLICY) for p in catalog['programs']}
    for p in catalog['programs']:
        pid=idmap[p['external_id']]
        if pid not in old_programs:result['programs_added'].append(dict(id=pid,name=p['fields']['name']))
    if dry_run:return result
    with service.sessions.begin() as db:
        if service.engine.dialect.name=='postgresql':db.execute(text('SELECT pg_advisory_xact_lock(9072026)'))
        for p in catalog['programs']:
            pid=idmap[p['external_id']];row=db.get(ProgramMapping,pid)
            if row is None:
                row=ProgramMapping(id=pid,name=p['fields']['name'],seed_policy_id=POLICY,policy_id=POLICY,status='REVIEW',revision_no=1,basis=p['basis'],evidence_url=p['evidence_url']);db.add(row)
            payload=dict(p,program_id=pid,policy_id=POLICY,base_date=p['source_date'],registration_set='POLICY_PROGRAM_20261014',source_files=catalog['source_files'])
            _,outcome=upsert_revision(db,'program_source','policy_907_plan',pid,payload,'document-review')
            if outcome!='unchanged':
                result['sources_saved']+=1;db.add(Audit(entity_id=pid,action='PROGRAM_SOURCE_SUPPLEMENT',before={},after=dict(source=payload,reason='사업 없는 프로그램 목표와 원문 근거 보완')))
        db.flush()
        for kind,key,p in site_records():
            eid=entity_id(kind,'policy_907',key)
            existing=db.scalar(select(Revision).where(Revision.entity_id==eid,Revision.superseded_at.is_(None)))
            if existing:continue
            row,_=upsert_revision(db,kind,'policy_907',key,p,'document-review')
            n=2 if '과천' in key else 30 if '번동' in key else 38
            ext=next(r['프로그램ID'] for r in catalog['projects'] if r['사업ID']==f'PRJ{n:03}')
            db.add(Mapping(project_id=row.entity_id,policy_id=POLICY,program_id=idmap[ext],status='REVIEW',revision_no=1,basis=p['mapping_basis'],evidence_url=p['evidence_url']))
            db.add(Audit(entity_id=eid,action='PROGRAM_SOURCE_SUPPLEMENT',before={},after=dict(reason='공식 원문 명시 사업 누락 보완',source=p)))
            result['projects_added'].append(key)
        # Existing exact named projects only. District-level supply rows stay evidence, not duplicate projects.
        manual=set(db.scalars(select(Audit.entity_id).where(Audit.action.in_(['PROGRAM_PROJECT_REVIEW','MAPPING_REVIEW']))))
        for r in catalog['projects']:
            if r['검토분류']=='지구 단위 공급계획':
                payload=dict(r,program_id=idmap[r['프로그램ID']],policy_id=POLICY,base_date='2025-09-07',status='DISTRICT_PLAN_BLOCK_UNSPECIFIED',exclude_from_project_totals=True)
                upsert_revision(db,'program_district_plan','policy_907_plan',r['사업ID'],payload,'document-review');continue
            ids=r['현재대응사업ID'].split(' | ') if r['현재대응사업ID'] else []
            for eid in ids:
                mapping=db.scalar(select(Mapping).where(Mapping.project_id==eid))
                if not mapping or mapping.program_id==idmap[r['프로그램ID']]:continue
                if eid in manual or mapping.status!='REVIEW':result['preserved'].append(eid);continue
                parent=db.get(ProgramMapping,mapping.program_id)
                if parent and (parent.policy_id!=POLICY or parent.status=='RELEASED'):result['preserved'].append(eid);continue
                before={k:getattr(mapping,k) for k in ('program_id','policy_id','status','revision_no','basis','evidence_url')}
                mapping.program_id=idmap[r['프로그램ID']];mapping.revision_no+=1
                mapping.basis='공식 원문 명시 사업과 프로그램 범위 대조 · '+r['검토내용'];mapping.evidence_url=r['검증근거URL']
                db.add(Audit(entity_id=eid,action='PROGRAM_SOURCE_SUPPLEMENT',before=before,after=dict(program_id=mapping.program_id,revision_no=mapping.revision_no,reason=mapping.basis,evidence_url=mapping.evidence_url)))
                result['links_changed'].append(eid)
        # Follow-up occupancy years were read but discarded by old registry code.
        moves={'상계마들':2029,'하계5단지':2029,'중계1단지':2031,'가양 노후 임대 재건축':2032,'수서 노후 임대 재건축':2033}
        for old in db.scalars(select(Revision).where(Revision.kind=='project',Revision.source_id=='policy_907',Revision.superseded_at.is_(None))).all():
            name=old.payload.get('name')
            if name not in moves:continue
            p=dict(old.payload)
            if p.get('source_move_in_label'):continue
            p.update(source_move_in_label=str(moves[name])+'년',move_in_evidence_url=FOLLOW)
            _,outcome=upsert_revision(db,'project','policy_907',name,p,'document-review')
            if outcome!='unchanged':db.add(Audit(entity_id=old.entity_id,action='PROGRAM_SOURCE_SUPPLEMENT',before=old.payload,after=dict(source=p,reason='후속 공식표 입주예정연도 누락 보완 · 준공일과 구분')))
    from .collection_repairs import save as repair
    repair(service,'policy-program-document-20261014',dict(title='9·7 세부 프로그램·명시 사업 및 입주예정 누락 보완',repair_type='COLLECTION_GAP',status='PARTIAL',base_date='2026-10-14',source_ids=['policy_907','policy_907_plan'],stages=['POLICY','BUSINESS','CONSTRUCTION','SUPPLY','MOVE_IN'],cause='사업에서 파생한 프로그램만 관리하여 사업 미특정 정책 과제가 누락됨. 명시 사업3개와 후속표 입주연도 저장도 누락.',action='원문 세부프로그램17개 근거 저장, 범위가 같은 기존3개 재사용·14개 별도 등록. 명시 사업3개 추가. 지구별 분양계획20개는 블록 미특정 근거로 별도 보존. 임대 재건축5개 입주연도 보강. 확정 매핑과 사용자 입력 유지.',remaining='지구20개 블록별 대응과 최신 변경계획 추가 확인. 수서·가양 계획호수는 후속 공식 추정 유지. 강서구 하위3부지는 상위558호에 포함해 중복 집계 방지.',impact='사업 없는 프로그램의 목표 관리 가능. 분양계획과 지구 총량·실적을 구분.',related_keys=['program_id','project_id','metric','unit','source_scope','source_move_in_label']))
    repair(service,'program-scope-target-reconciliation-20261014',dict(title='프로그램 관리목표·사업계획 대조 및 분양기간 범위 정비',repair_type='SCOPE_QUANTITY',status='PARTIAL',base_date='2026-10-14',source_ids=['policy_907_plan','lh_sale','lh_notice','cheongyak'],stages=['POLICY','CONSTRUCTION','SUPPLY'],cause='공식 프로그램 목표와 사업 전체 세대수·기간 내 단계 계획이 구분되지 않음. 분양 프로그램이 정책의 신규착공 기간 필터를 공유하여 이전 착공 사업이 누락될 수 있음.',action='원문17개 프로그램의 관리방식·사례·추가 필요자료를 원천 기본값으로 저장. 전체 사업계획과 동일 단계·기간 계획을 별도 대조. 분양 프로그램은 자체2025~2026년 기간 적용. 미확보·효과 목표·다른 단위는 자동 합산 목표로 대체하지 않음. 사업 합계 채택 시 범위·사업 ID·변경자 근거 보존.',remaining='기관별 선정 사업 목록·공식 배정표·최초/변경 일정과 블록 대응표 제공 요청 필요. 공개 공고 API 승인만으로 프로그램 귀속 원장이 확보되는 것은 아님.',impact='계획 차이와 실제 지연을 구분하고 단계·기간이 다른 물량의 과대/누락 집계를 방지.',related_keys=['program_id','project_id','target_mode','metric','unit','period_start','period_end']))
    return result
