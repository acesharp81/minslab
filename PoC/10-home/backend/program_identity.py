"""Pinned programme aliases: reconcile reviewed legacy duplicate IDs without deleting history."""
from sqlalchemy import select,text
from .db import Revision,ProgramMapping,Mapping,Audit,entity_id,upsert_revision,now
POLICY='POL_2025_0907'
PAIRS=[('PRG_c310a281175c3454239974cf','PRG_1c5b82d3c0550e744941eb29'),('PRG_2b40669c4106039664ef8d2c','PRG_61f7be0b56b1d84e8da213f4')]

def resolve_in_session(db,pid):
    seen=set()
    while pid not in seen:
        seen.add(pid)
        r=db.scalar(select(Revision).where(Revision.entity_id==entity_id('program_alias','program_identity',pid),Revision.superseded_at.is_(None)))
        if not r:return pid
        pid=r.payload['canonical_id']
    raise ValueError('프로그램 별칭 순환 연결을 확인하세요')

def apply(service,dry_run=True):
    result=dict(dry_run=dry_run,merged=[],moved_projects=0,skipped=[])
    with service.sessions.begin() as db:
        if service.engine.dialect.name=='postgresql':db.execute(text('SELECT pg_advisory_xact_lock(9072026)'))
        for alias_id,target_id in PAIRS:
            if resolve_in_session(db,alias_id)!=alias_id:continue
            alias=db.get(ProgramMapping,alias_id);target=db.get(ProgramMapping,target_id)
            if not alias or not target:continue
            profiles=db.scalars(select(Revision).where(Revision.kind.in_(['program_source','program_profile']),Revision.superseded_at.is_(None))).all()
            manual=db.scalar(select(Audit.id).where(Audit.entity_id==alias_id,Audit.action.in_(['PROGRAM_POLICY_REVIEW','PROGRAM_PROFILE_UPDATED'])).limit(1))
            if alias.name!=target.name or alias.policy_id!=POLICY or target.policy_id!=POLICY or alias.status!='REVIEW' or target.status not in ('REVIEW','CONFIRMED') or manual or any(r.payload.get('program_id')==alias_id for r in profiles):
                result['skipped'].append(alias_id);continue
            mappings=db.scalars(select(Mapping).where(Mapping.program_id==alias_id).with_for_update()).all()
            item=dict(alias_id=alias_id,canonical_id=target_id,name=target.name,project_count=len(mappings))
            result['merged'].append(item);result['moved_projects']+=len(mappings)
            if dry_run:continue
            basis='동일 정책·동일 프로그램의 최초 정책 구분별 중복 ID 정비 · 공정현황 원천을 대표 프로그램으로 연결 · 정책 귀속 확정 아님'
            for m in mappings:
                before={k:getattr(m,k) for k in ('program_id','policy_id','status','basis','evidence_url','revision_no')}
                m.program_id=target_id;m.revision_no+=1;m.basis=(m.basis or '')+' · '+basis
                after={k:getattr(m,k) for k in before}
                db.add(Audit(entity_id=m.project_id,action='PROGRAM_PROJECT_MERGE',before=before,after=after))
            before={k:getattr(alias,k) for k in ('policy_id','status','basis','evidence_url','revision_no')}
            alias.policy_id='UNASSIGNED';alias.status='RELEASED';alias.revision_no+=1;alias.reviewed_at=now();alias.basis=basis+' · 대표 ID '+target_id
            db.add(Audit(entity_id=alias_id,action='PROGRAM_POLICY_MERGE',before=before,after=dict(policy_id=alias.policy_id,status=alias.status,basis=alias.basis,evidence_url=alias.evidence_url,revision_no=alias.revision_no,canonical_id=target_id)))
            payload=dict(item,base_date='2026-10-14',basis=basis,policy_id=POLICY)
            upsert_revision(db,'program_alias','program_identity',alias_id,payload,'identity-review')
            db.add(Audit(entity_id=target_id,action='PROGRAM_IDENTITY_MERGE',before={},after=payload))
    if not dry_run:
        from .collection_repairs import save
        save(service,'program-duplicate-identity-20261014',dict(title='동일 이름 프로그램의 최초 정책 구분별 중복 ID 정비',repair_type='IDENTITY_LINK',status='RESOLVED',base_date='2026-10-14',source_ids=['lh_progress','lh_construction','lh_sale'],stages=['POLICY','BUSINESS','CONSTRUCTION'],cause='ID 생성 기준에 최초 정책 구분이 포함되어 동일 이름 프로그램이 서로 다른 ID로 생성됨. 이후9.7로 임시 연결되어 3기 신도시·공공주택 건설이 각각2개로 표출됨.',action='공정현황 원천의 중복 프로그램2개를 기존 대표 ID에 별칭 연결하고 사업9건의 프로그램 연결만 이관. 원천·사업·검토상태·변경 이력 보존. 추가 수집 시 저장된 별칭을 조회하여 재생성 방지.',remaining='프로그램과 개별 사업의9.7 정책 귀속은 기존 검토상태 유지. 동일 이름만으로 다른 정책·다른 범위 또는 사용자 목표가 있는 프로그램을 자동 통합하지 않음.',impact='프로그램 목록 중복 해소. 사업 원천 건수·정책 전체 물량은 유지.',related_keys=['seed_policy_id','policy_id','program_id','canonical_id']))
    return result
