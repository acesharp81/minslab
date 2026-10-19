"""Explicitly authorized linkage of collected starts to managed projects.

Keep native facts and approved inputs intact. A business type identifies a
management group, never a policy relationship.
"""
from copy import deepcopy
from collections import Counter
from statistics import median
import re
from sqlalchemy import select, text
from .db import Revision, Mapping, ProgramMapping, Audit, entity_id, upsert_revision, now
from .collectors import urban_project
from .construction_candidates import eligible
from .seoul_cleanup import address_key
from .program_hierarchy import program_id
from .api_samples import today

POLICY = 'POL_2025_0907'
SMALL = '소규모 주택정비 · 정책 귀속 검토'
RENEWAL = '재개발·재건축 · 정책 귀속 검토'
GENERAL = '일반 주택 건설 · 정책 미귀속'
LOCAL = '지역주택조합 · 정책 미귀속'
BATCH = 'start-linkage-20261019-v1'


def stem(name):
    value = re.sub(r'\s+|제(?=\d)', '', name or '')
    for suffix in ('재정비촉진구역', '재정비촉진', '구역', '주택재개발', '주택재건축', '가로주택'):
        if suffix in value:return value.split(suffix)[0]
    return value


def category(row):
    kind = row.get('business_type') or ''
    if kind in ('가로주택정비', '소규모재건축', '소규모재개발', '자율주택정비'):return SMALL, 'UNASSIGNED'
    if kind == '재건축' or kind.startswith('재개발('):return RENEWAL, 'UNASSIGNED'
    if kind == '지역주택':return LOCAL, 'UNASSIGNED'
    return GENERAL, 'UNASSIGNED'


def quantity(row, renewal):
    """Full source total first; incomplete tables remain explicit assumptions."""
    if row.get('sample_kind') == 'general_permit':
        units = row.get('units')
        if type(units) is int and units > 0:
            return units, dict(rule='SOURCE_HOUSEHOLDS', inferred=False, source_entity_id=row['id'])
        # A family count is not a dwelling count. Do not convert it to households.
        return 1, dict(rule='SINGLE_HOUSE_SCOPE_ASSUMPTION', inferred=True,
            basis='단독주택 신축 허가 1건을 주택 1호로 관리 추정. 원천 0과 가구수는 보존하고 합산하지 않음')
    if type(row.get('housing_plan_total')) is int and row['housing_plan_total'] > 0:
        return row['housing_plan_total'], dict(rule='SOURCE_OVERVIEW_TOTAL', inferred=False, source_entity_id=row['id'])
    matches = [r for r in renewal if r.get('region') == row.get('region')
        and r.get('municipality') == row.get('municipality') and stem(r['name']) == stem(row['name'])
        and len(stem(r['name'])) >= 3 and type(r.get('units')) is int and r['units'] > 0]
    if len(matches) == 1:
        r = matches[0]
        return r['units'], dict(rule='SAME_CITY_PROJECT_STEM', inferred=False, source_entity_id=r['id'],
            source_revision_id=r['source_revision_id'], matched_fields=['region','municipality','project_name_stem'],
            basis='같은 시도·자치구·고유 구역명 일치. 공식 정비사업 명부의 계획 세대수 채택')
    parts = row.get('housing_plan_partial_components') or {}
    observed = []
    for value in parts.values():
        if value.get('reported_total') is not None:observed.append(value['reported_total'])
        else:observed.extend(v for v in value.get('area_band_units',[]) if v is not None)
    if observed and sum(observed)>0:
        return sum(observed), dict(rule='PARTIAL_COMPONENT_SUM_ASSUMPTION', inferred=True,
            source_entity_id=row['id'], components=parts,
            basis='현재 확인되는 분양·임대 구간만 합산하여 관리 규모 채택. 공란 구간의 추가 물량은 없는 것으로 가정하며 원문 공란은 유지')
    return None, dict(rule='PEER_CAPACITY_ESTIMATE', inferred=True)


def source_facts(row):
    if row.get('sample_kind') != 'general_permit':return deepcopy(row.get('facts') or [])
    dates = row['dates']; result=[]
    for key,stage,milestone in [('건축허가일 (archPmsDay)','APPROVAL','APPROVAL'),
        ('실제착공일 (realStcnsDay)','CONSTRUCTION','CONSTRUCTION'),
        ('사용승인일 (useAprDay)','CONSTRUCTION','COMPLETION')]:
        if dates.get(key) and dates[key] <= today().isoformat():
            result.append(dict(stage=stage,milestone=milestone,kind='ACTUAL',date=dates[key],
                units=row['units'] if row.get('units',0)>0 else None,basis='동일 일반 건축인허가 관리번호의 '+key))
    return result


def prepare(projects, general, documents, renewal):
    candidates = [r for r in general if eligible(r, f'{today().year}-01-01', today().isoformat())]
    candidates += [r for r in documents if r.get('source_id') == 'seoul_cleanup'
        and r.get('discovery_candidate') and not r.get('matched_project_ids')]
    items=[];held=[];seen={}
    for r in sorted(candidates,key=lambda x:x['id']):
        name=r.get('name')
        if not name or name.strip('.')=='':name=r['address']
        address=address_key(r.get('address'));units,proof=quantity(r,renewal)
        program,policy=category(r)
        facts=source_facts(r)
        starts=sorted({f['date'] for f in facts if f.get('stage')=='CONSTRUCTION' and f.get('milestone')=='CONSTRUCTION' and f.get('kind')=='ACTUAL'})
        approvals=sorted({f['date'] for f in facts if f.get('stage')=='APPROVAL' and f.get('kind')=='ACTUAL'})
        # Several permit amendments are legitimate; an approval occurring after
        # an observed start is not used as the initial permit anchor.
        initial=[d for d in approvals if not starts or d<=starts[0]]
        key=(r['region'],address,starts[0] if starts else None,units)
        if address and key in seen:
            held.append(dict(source_entity_id=r['id'],reason='동일 주소·착공일·호수 원천 중복',same_as=seen[key]));continue
        seen[key]=r['id']
        exact=[p for p in projects if p.get('source_reference_id')==r['id']]
        matches=exact or [p for p in projects if p.get('region')==r['region'] and address
            and address_key(p.get('address'))==address and p.get('planned_units')==units and units is not None]
        if len(matches)>1:
            held.append(dict(source_entity_id=r['id'],reason='같은 주소·규모의 기존 사업 복수 후보',project_ids=[p['id'] for p in matches]));continue
        target=matches[0]['id'] if matches else entity_id('project',r['source_id'],'managed-start:'+r['id'])
        items.append(dict(source=r,project_id=target,existing=bool(matches),name=name,region=r['region'],
            program=program,policy_id=policy,planned_units=units,quantity_proof=proof,facts=facts,
            start_date=starts[0] if starts else None,approval_date=initial[0] if initial else None))
    for i in items:
        if i['planned_units'] is None:
            peers=[p['planned_units'] for p in items if p['program']==i['program'] and type(p['planned_units']) is int
                and p['planned_units']>0 and p['quantity_proof']['rule']!='PEER_CAPACITY_ESTIMATE']
            if not peers:peers=[p['planned_units'] for p in projects if p.get('program')==i['program'] and type(p.get('planned_units')) is int and p['planned_units']>0]
            if not peers:
                held.append(dict(source_entity_id=i['source']['id'],reason='동일 프로그램 규모 추정 표본 미확보'));continue
            i['planned_units']=int(median(peers));i['quantity_proof'].update(sample_units=peers,basis='같은 프로그램의 확인된 사업 규모 중앙값',value=i['planned_units'])
    return dict(items=[i for i in items if i['planned_units'] is not None],held=held)


def apply_links(service,plan,actor,reason):
    result=Counter()
    with service.sessions.begin() as db:
        if service.engine.dialect.name=='postgresql':db.execute(text('SELECT pg_advisory_xact_lock(1019192)'))
        for item in plan['items']:
            src=item['source'];pid=item['project_id'];key='managed-start:'+src['id']
            raw=db.scalar(select(Revision).where(Revision.entity_id==src['id'],Revision.superseded_at.is_(None)))
            if not raw or raw.id!=src['source_revision_id']:raise ValueError('원천 판본 변경: '+item['name'])
            old=db.scalar(select(Revision).where(Revision.entity_id==pid,Revision.superseded_at.is_(None)))
            if old is None:
                cap=None if item['quantity_proof']['inferred'] else item['planned_units']
                city=src.get('municipality') or next((w for w in src['address'].split() if w.endswith(('구','시')) and w!=src['region']), '지역 확인 필요')
                p=urban_project(item['name'],city,item['region'],cap,item['policy_id'],today().isoformat(),item['program'])
                p.update(address=src.get('address'),evidence_url=src.get('overview_url') or src['evidence_url'],
                    source_reference_id=src['id'],source_reference_revision=src['source_revision_id'],
                    source_object_id=src.get('source_object_id'),facts=item['facts'],
                    start_actual_date=item['start_date'],quantity_proof=item['quantity_proof'],
                    source_stage=src.get('source_stage'),source_scope='SINGLE_PROJECT',
                    unit_basis='동일 사업 원천 계획규모; 관리 추정은 project_profile에 별도 보존',
                    mapping_basis=reason+' · '+str(src.get('business_type') or src.get('main_purpose')),
                    policy_relationship='USER_ADOPTED_CATEGORY' if item['policy_id']!= 'UNASSIGNED' else 'NO_POLICY_EVIDENCE')
                row,_=upsert_revision(db,'project',src['source_id'],key,p,BATCH)
                program_key=program_id(item['program'],item['policy_id'])
                program=db.get(ProgramMapping,program_key)
                if program is None:
                    program=ProgramMapping(id=program_key,name=item['program'],seed_policy_id=item['policy_id'],policy_id=item['policy_id'],
                        status='REVIEW',revision_no=1,reviewed_at=now(),basis='사용자 요청에 따른 동일 유형 관리 묶음. 공식 정책 귀속 근거가 없으면 미귀속 유지',evidence_url=src['evidence_url'])
                    db.add(program)
                db.add(Mapping(project_id=pid,policy_id=item['policy_id'],program_id=program_key,status='CONFIRMED',revision_no=1,
                    basis=reason+' · 원천 사업구분 '+str(src.get('business_type') or src.get('main_purpose'))+' → '+item['program']+' · 관리 분류 채택; 공식 개별사업 명단과 구분',
                    evidence_url=src['evidence_url'],reviewed_at=now()))
                db.add(Audit(entity_id=pid,action='START_PROJECT_LINKED',before={},after=dict(actor=actor,reason=reason,source_entity_id=src['id'],project=p)))
                result['projects_added']+=1
            bridge_key=pid+':'+src['id'];bid=entity_id('evidence_bridge','cross_source',bridge_key)
            if db.scalar(select(Revision.id).where(Revision.entity_id==bid,Revision.superseded_at.is_(None))):
                result['links_preserved']+=1;continue
            payload=dict(project_id=pid,name=item['name'],region=item['region'],source_entity_id=src['id'],
                source_revision_no=src['revision_no'],source_id=src['source_id'],evidence_source_id=src['source_id'],
                source_name=src['name'],evidence_url=src['evidence_url'],units=None if item['quantity_proof']['inferred'] else item['planned_units'],
                facts=item['facts'],status='CONFIRMED',reviewed=True,actor=actor,reason=reason,base_date=today().isoformat(),
                relation_type='SAME_SCOPE',matching_version=BATCH,basis='원천 고유 관리번호·동일 사업명·주소 연결; '+reason)
            r,_=upsert_revision(db,'evidence_bridge','cross_source',bridge_key,payload,BATCH)
            db.add(Audit(entity_id=r.entity_id,action='EVIDENCE_BRIDGE_REVIEW',before={},after=payload));result['links_added']+=1
    return dict(result)


def apply_identities(service,plan,actor,reason):
    from .identity import reconcile_identity_links, review_identity_alias
    from .db import IdentityAlias, ProjectEvidence
    reconcile_identity_links(service)
    counts=Counter()
    for item in plan['items']:
        src=item['source']
        with service.sessions.begin() as db:
            target=db.scalar(select(IdentityAlias).where(IdentityAlias.source_entity_id==item['project_id']))
            old=db.scalar(select(IdentityAlias).where(IdentityAlias.source_entity_id==src['id']))
            if old and old.project_id==target.project_id and old.relation_status=='CONFIRMED':
                counts['preserved']+=1;continue
            if old:
                if old.relation_status!='REVIEW':raise ValueError('기존 담당자 식별 판정 보존 필요: '+src['id'])
                request=dict(project_id=target.project_id,expected_project_id=old.project_id,
                    expected_status=old.relation_status,status='CONFIRMED',basis=actor+' · '+reason,
                    evidence_url=src['evidence_url']);alias_id=old.id
            else:
                db.add(IdentityAlias(project_id=target.project_id,source_entity_id=src['id'],source_id=src['source_id'],
                    relation_status='CONFIRMED',match_rule='USER_START_LINKAGE',basis=reason,
                    evidence_revision_id=src['source_revision_id'],evidence_url=src['evidence_url'],reviewed_at=now()))
                db.add(ProjectEvidence(project_id=target.project_id,revision_id=src['source_revision_id'],evidence_role='CONSTRUCTION_CANDIDATE'))
                db.add(Audit(entity_id=src['id'],action='IDENTITY_REVIEW',before={},after=dict(actor=actor,reason=reason,project_id=target.project_id,status='CONFIRMED')))
                request=None
        if request:
            result=review_identity_alias(service,alias_id,**request)
            if result.get('conflict'):raise ValueError('동시 식별 판정 변경')
        counts['linked']+=1
    return dict(counts)
