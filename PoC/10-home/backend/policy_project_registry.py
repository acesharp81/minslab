"""Reviewed source-document registrations; policy attribution remains officer-reviewable.

These are named sites/site groups, not a complete census or actual delivery.
Stable source keys keep supplemental registrations intact across recollection.
"""
from copy import deepcopy

POLICY_ID = 'POL_2025_0907'
ORIGINAL_URL = 'https://molit.go.kr/atmo/USR/N0201/m_36515/dtl.jsp?id=95091185&lcmspage=2'
FOLLOWUP_URL = 'https://www.korea.kr/common/download.do?fileId=198344116'
# name, municipality, units, source PDF page, programme, scope
SITES = [
    ('서울 서리풀', '서초구', 20000, 13, '공공택지 공급 조기화', 'DISTRICT'),
    ('성대야구장', '도봉구', 1800, 23, '유휴부지·노후청사 복합개발', 'SITE'),
    ('위례 업무용지', '송파구', 1000, 23, '유휴부지·노후청사 복합개발', 'SITE'),
    ('구 한국교육개발원', '서초구', 700, 23, '유휴부지·노후청사 복합개발', 'SITE'),
    ('강서구 이전부지', '강서구', 558, 23, '유휴부지·노후청사 복합개발', 'SITE_GROUP'),
    ('상계마들', '노원구', None, 19, '노후 공공임대 재건축', 'COMPLEX'),
    ('하계5단지', '노원구', None, 19, '노후 공공임대 재건축', 'COMPLEX'),
    ('중계1단지', '노원구', None, 19, '노후 공공임대 재건축', 'COMPLEX'),
    ('수서 노후 임대 재건축', '강남구', None, 19, '노후 공공임대 재건축', 'SITE_GROUP'),
    ('가양 노후 임대 재건축', '강서구', None, 19, '노후 공공임대 재건축', 'SITE_GROUP'),
    ('창동역 복합개발', '도봉구', None, 24, '철도부지 복합개발', 'SITE'),
    ('금천구청역 유휴부지', '금천구', None, 24, '철도부지 복합개발', 'SITE'),
    ('인천검암', '서구', None, 14, '공공택지 공급 조기화', 'DISTRICT'),
    ('제물포 도심공공복합', '미추홀구', 3500, 5, '도심공공주택 복합사업', 'DISTRICT'),
    ('남인천 우체국', '남동구', 29, 19, '유휴부지·노후청사 복합개발', 'SITE'),
    ('청라동 92-29', '서구', 110, 19, '유휴부지·노후청사 복합개발', 'SITE'),
]


def registry_records(source_id):
    from .collectors import urban_project
    if source_id not in ('policy_907', 'policy_129'):
        return []
    result = []
    for i, (name, city, units, page, program, scope) in enumerate(SITES):
        followup = i >= 13
        if source_id != ('policy_129' if followup else 'policy_907'):
            continue
        region = '인천광역시' if i >= 12 else '서울특별시'
        base_date = '2026-01-29' if followup else '2025-09-07'
        p = urban_project(name, city, region, units, POLICY_ID, base_date, program)
        p.update(evidence_url=FOLLOWUP_URL if followup else ORIGINAL_URL,
                 source_page=page, registration_set='SEOUL_INCHEON_20261013',
                 source_policy_id='POL_2026_0129' if followup else POLICY_ID,
                 policy_relationship='FOLLOWUP_IMPLEMENTATION_REVIEW' if followup else 'ORIGINAL_NAMED_SITE',
                 source_scope=scope, policy_period_units=None,
                 unit_basis='공식 문서 계획호수 · 정책 기간 산입량과 현재 실적은 별도 검토' if units is not None else '신규 계획호수 미확인 · 기존 임대 세대수로 대체하지 않음',
                 mapping_basis=('1·29 공식 후속자료에 명시된 9·7 이행사업 연결 후보' if followup else '9·7 공식 원문에 명시된 사업·사업군') + ' · 사업 경계·기간별 산입량 담당자 검토 필요',
                 warnings=['POLICY_PLAN_NOT_ACTUAL', 'POLICY_PERIOD_QUANTITY_REVIEW'])
        if scope in ('DISTRICT', 'SITE_GROUP'):
            p['warnings'].append('SITE_SCOPE_REVIEW')
        if name == '서울 서리풀':
            p.update(start_plan_year=2029, schedule_basis='9·7 원문 2029년 착공 추진 · 월 미확인 · 지구 전체 2만호',
                     scope_note='1·29 후속자료의 1지구 1.8만호와 범위가 다름. 블록별 기간 물량 추가 검증 필요')
        if name == '강서구 이전부지':
            p.update(scope_note='가양동별관 98 + 강서구의회 163 + 강서구보건소 297 = 558호. 하위 사업과 중복 합산 금지',
                     source_components=[dict(name=n,planned_units=q) for n,q in [('가양동별관',98),('강서구의회',163),('강서구보건소',297)]])
        renewal={
            '하계5단지':(570,1336,'SH',2026,2029),
            '상계마들':(140,363,'SH',2026,2029),
            '중계1단지':(882,1370,'LH',2028,2031),
            '가양 노후 임대 재건축':(1998,3235,'LH',2029,2032),
            '수서 노후 임대 재건축':(2565,3899,'LH',2030,2033),
        }
        if name in renewal:
            existing,planned,agency,start,move=renewal[name]
            p.update(existing_stock_units=existing,planned_units=planned,developer=agency,
                     source_move_in_label=str(move)+'년',move_in_evidence_url='https://eiec.kdi.re.kr/policy/materialView.do?num=271965',
                     net_additional_units=planned-existing,start_plan_year=start,
                     unit_basis='국토부 2025-10-01 후속계획의 재건축 후 계획호수 · 기존 재고/순증과 구분',
                     quantity_status='APPROVED_PLAN' if agency=='SH' else 'OFFICIAL_ESTIMATE',
                     quantity_evidence_url='https://www.molit.go.kr/USR/NEWS/m_71/dtl.jsp?id=95091291',
                     scope_note='국토부 후속계획: 기존 '+str(existing)+'호 → 계획 '+str(planned)+'호. 승인 전 LH 단지는 용적률 500% 가정 전망으로 변동 가능. 분양·임대별 배분 미확인',
                     schedule_basis=str(start)+'년 착공 계획 · 국토부 2025-10-01 후속 발표, 실제 착공 아님')
            if name=='수서 노후 임대 재건축':
                p.update(address='서울특별시 강남구 수서동 707',source_scope='COMPLEX',
                         scope_note=p['scope_note']+' · 수서(LH)·수서주공, 일원동 711 수서1-1(SH)와 다른 단지')
        if name == '제물포 도심공공복합':
            p.update(start_plan_year=2026, schedule_basis='1·29 후속자료의 2026년 착공 예정 사례 · 실제 착공 미확인')
        if name in ('남인천 우체국','청라동 92-29'):
            p.update(start_plan_month='2030-12', schedule_basis='1·29 별첨 착공 예정월 · 공급·준공·입주월 아님')
        result.append(('project', name, p))
    return deepcopy(result)


def supplement_records(source_id, records):
    """Prefer a newly parsed source row; never duplicate or overwrite it with a snapshot."""
    present = {(kind, key) for kind, key, _ in records}
    from .program_catalog import site_records
    extra = [r for r in registry_records(source_id)+(site_records() if source_id=='policy_907' else []) if r[:2] not in present]
    return list(records) + extra


def register_reviewed_sites(service, apply=False):
    """Atomic one-time backfill; retries preserve existing source and staff decisions."""
    import re
    from sqlalchemy import select, text, func
    from .db import Revision, Mapping, Batch, Audit, entity_id, upsert_revision, now
    real_policies = {p['policy_id']: p for p in service.mapping_policies() if p.get('monitor_kind') == 'POLICY'}
    if POLICY_ID not in real_policies:
        raise ValueError('9·7 정책 원장이 필요합니다')
    records = [(sid, key, payload) for sid in ('policy_907', 'policy_129') for _, key, payload in registry_records(sid)]
    result = dict(apply=apply, added=[], existing=[], batches=[])
    norm = lambda s: re.sub(r'\s+', '', s).casefold()
    with service.sessions.begin() as db:
        if service.engine.dialect.name == 'postgresql':
            db.execute(text('SELECT pg_advisory_xact_lock(1019090)'))
        current = db.scalars(select(Revision).where(Revision.kind == 'project', Revision.superseded_at.is_(None))).all()
        pending = []
        for sid, key, p in records:
            eid = entity_id('project', sid, key)
            old = next((r for r in current if r.entity_id == eid), None)
            collisions = [r for r in current if r.entity_id != eid and r.payload.get('region') == p['region'] and norm(r.payload.get('name','')) == norm(p['name'])]
            if collisions:
                raise ValueError('동일 명칭 기존 사업과 중복 검토 필요: ' + p['name'])
            item = dict(id=eid, name=p['name'], source_id=sid, region=p['region'], planned_units=p['planned_units'])
            result['existing' if old else 'added'].append(item)
            if old is None:
                pending.append((sid, key, p))
        if not apply:
            return result
        for sid in ('policy_907', 'policy_129'):
            additions = [(key,p) for s,key,p in pending if s == sid]
            if not additions:
                continue
            previous = db.scalar(select(Batch).where(Batch.source_id==sid, Batch.status=='SUCCESS').order_by(Batch.finished_at.desc()).limit(1))
            b = Batch(source_id=sid, status='RUNNING', manifest=list(previous.manifest or []) if previous else [])
            db.add(b);db.flush()
            for key,p in additions:
                row,_ = upsert_revision(db,'project',sid,key,p,b.id)
                mapping = Mapping(project_id=row.entity_id,policy_id=POLICY_ID,status='REVIEW',revision_no=1,
                                  basis=p['mapping_basis'],evidence_url=p['evidence_url'])
                db.add(mapping)
                service._attach_program(db,mapping,p,real_policies)
                db.add(Audit(entity_id=row.entity_id,action='MAPPING_AUTO',before={},after=dict(
                    project_id=row.entity_id,policy_id=POLICY_ID,program_id=mapping.program_id,status='REVIEW',
                    basis=mapping.basis,evidence_url=mapping.evidence_url,revision_no=1,
                    registration_set=p['registration_set'],source_policy_id=p['source_policy_id'])))
            db.flush()
            ids=list(db.scalars(select(Revision.entity_id).where(Revision.source_id==sid,Revision.superseded_at.is_(None))))
            b.status='SUCCESS';b.finished_at=now()
            b.stats=dict(previous.stats or {}) if previous else {}
            b.stats.update(collection_mode='DOCUMENT_REGISTRATION',registration_set='SEOUL_INCHEON_20261013',
                           registration_added=len(additions),record_count=len(ids),entity_ids=ids,
                           named_projects=db.scalar(select(func.count()).select_from(Revision).where(
                               Revision.source_id==sid,Revision.kind=='project',Revision.superseded_at.is_(None))),
                           scope_note='보관 공식 문서 점검 후 명시 사업 등록. 신규 원천 조회 아님. 사업 경계·기간 물량 담당자 검토 필요')
            result['batches'].append(b.id)
    return result
