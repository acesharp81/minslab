"""Prepare/apply/check the eleven newly confirmed projects, retaining prior 197."""
from copy import deepcopy
from datetime import timedelta
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from sqlalchemy import select, text
from sqlalchemy.orm import sessionmaker
from backend.db import engine_for, Revision, Mapping, ProgramMapping, Audit, now, upsert_revision
from backend.service import HomeService, KST
from backend.project_collection import collection_matrix
from backend.incremental_estimates import values, apply as apply_plan
from backend.independent_metrics import build, digest
from backend.project_profile import STAGES
from backend.officer_completion import POLICY, normalized

FOLDER=ROOT/'data/remediation/incremental-estimates-20261018'
BATCH='officer-added-20261018-v1'
ACTOR='김민'
REASON='공식 자료 확인 및 IH 추가 연결'


def write(name,value):
    FOLDER.mkdir(parents=True,exist_ok=True)
    (FOLDER/(name+'.json')).write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n')


def read(name):return json.loads((FOLDER/(name+'.json')).read_text())
def service():return HomeService(engine_for(),ROOT/'data')


def capture(s,known):
    projects=s.projects()
    # The original duration-model revision shares the old batch's entity key
    # with its completion marker. Read the immutable historical model by kind.
    with s.sessions() as db:
        models=[dict(r.payload,id=r.entity_id,source_revision_id=r.id,historical_model=True) for r in db.scalars(
            select(Revision).where(Revision.kind=='officer_duration_model',Revision.recorded_at<known).order_by(Revision.recorded_at.desc()).limit(1))]
    return dict(known_at=known.isoformat(),projects=projects,raw_projects=s.rows('project'),
        profiles=s.rows('project_profile'),schedules=s.rows('execution_schedule'),
        programs=s.program_links(projects=projects),bridges=s.rows('evidence_bridge'),
        stage_links=s.rows('stage_evidence'),duration_models=models,
        independent=build(s,known,period_start='2026-01-01',period_end=known.astimezone(KST).date().isoformat()))


def prepare():
    if (FOLDER/'plan.json').exists():raise ValueError('기존 적용안은 덮어쓰지 않습니다')
    s=service()
    with s.engine.connect().execution_options(isolation_level='REPEATABLE READ') as connection:
        with connection.begin():
            connection.execute(text('SET TRANSACTION READ ONLY'))
            known=now();s.known_at=known
            s.sessions=sessionmaker(bind=connection,expire_on_commit=False,join_transaction_mode='create_savepoint')
            before=capture(s,known)
            declared=json.loads((ROOT/'data/remediation/policy-connections-20261018/plan.json').read_text())
            ids={p['id'] for p in declared['projects']}
            ps=[p for p in before['projects'] if p['id'] in ids]
            assert len(ps)==11 and not ids & {p['project_id'] for p in before['profiles']}
            cells={p['id']:p['cells'] for p in collection_matrix(s,policy_id=POLICY)['items']}
            model=before['duration_models'][-1]['model'];stamp=known.isoformat();reference=known.astimezone(KST).date()
            candidate_ids={c['source_entity_id'] for link in before['stage_links'] if link['project_id'] in ids for c in link.get('candidates',[]) if c.get('source_id','').startswith('building_hub')}
            candidate_ids|={p['id'] for p in ps if p['source_id'].startswith('building_hub')}
            candidate_ids|={p['source_reference_id'] for p in ps if p.get('source_reference_id','').startswith('PER_')}
            with s.sessions() as db:
                candidates={r.entity_id:dict(r.payload,id=r.entity_id,source_revision_id=r.id,revision_no=r.revision_no) for r in db.scalars(select(Revision).where(Revision.entity_id.in_(candidate_ids),Revision.superseded_at.is_(None)))}
            work=[]
            for p in ps:
                cc=deepcopy(cells[p['id']]);anchors=[];refs=[dict(entity_id=p['id'],revision_id=p['source_revision_id'])]
                # Use a stored permit only when its region, quantity, unique
                # project-name stem and the already proposed relationship agree.
                proposed={c['source_entity_id'] for link in before['stage_links'] if link['project_id']==p['id'] for c in link.get('candidates',[]) if c.get('source_id','').startswith('building_hub') and c.get('score',0)>=.85}
                proposed|={p['id']} if p['source_id'].startswith('building_hub') else set()
                if p.get('source_reference_id') in candidates:proposed.add(p['source_reference_id'])
                norm=lambda v:re.sub(r'[^가-힣A-Z0-9]','',str(v).upper())
                stem=norm(p['name']).replace('재정비촉진','').replace('주택재개발정비사업','')
                rows=[candidates[i] for i in proposed if i in candidates and candidates[i].get('region')==p['region'] and candidates[i].get('units')==p['planned_units'] and stem in norm(candidates[i].get('name',''))]
                if p.get('source_reference_id') in {r['id'] for r in rows}:
                    rows=[candidates[p['source_reference_id']]]
                if len(rows)==1:
                    r=rows[0];refs.append(dict(entity_id=r['id'],revision_id=r['source_revision_id']))
                    for stage,token in [('APPROVAL','(apprvDay)'),('CONSTRUCTION','(stcnsSchedDay)'),('COMPLETION','useInsptSchedDay')]:
                        dates=[normalized(value) for field,value in r.get('dates',{}).items() if token in field and normalized(value)]
                        if len(set(dates))==1:
                            anchors.append(dict(stage=stage,due_date=dates[0],precision='DAY',
                                source_entity_id=r['id'],source_revision_id=r['source_revision_id'],evidence_url=r.get('evidence_url'),
                                review_status='ESTIMATION_REFERENCE',basis='사업명·동일 지역·총규모가 일치하는 저장 인허가 후보를 추정 기준으로 사용 · 실제 착공 확정 아님'))
                peers=[x.get('source_values',{}).get('planned_units',x.get('planned_units')) for x in before['projects'] if x['mapping']['program_id']==p['mapping']['program_id']]
                if not any(type(v) is int and v>0 for v in peers):peers=[x.get('source_values',{}).get('planned_units',x.get('planned_units')) for x in before['projects'] if x['mapping']['policy_id']==POLICY]
                result=values(p,cc,model,stamp,ACTOR,REASON,reference,anchors,peers)
                result.update(mapping_revision_no=p['mapping']['revision_no'],evidence_url=p.get('evidence_url'),pinned_inputs=refs)
                # Retain model provenance and all linked fact revisions used in calculations.
                evidence_ids={e.get('source_entity_id') for cell in cc.values() for e in cell.get('sources',[]) if e.get('source_entity_id')}
                model_record=before['duration_models'][-1]
                result['pinned_inputs'].append(dict(entity_id=model_record['id'],revision_id=model_record['source_revision_id'],historical_model=True))
                with s.sessions() as db:
                    for r in db.scalars(select(Revision).where(Revision.entity_id.in_(evidence_ids),Revision.superseded_at.is_(None))):
                        if r.entity_id not in {v['entity_id'] for v in result['pinned_inputs']}:result['pinned_inputs'].append(dict(entity_id=r.entity_id,revision_id=r.id))
                work.append(result)
    summary=dict(projects=len(work),targets=sum(len(p['targets']) for p in work),
        estimated_measurements=sum(len(p['progress']) for p in work),
        pending_measurements=sum(6-len(p['progress']) for p in work),
        source_capacity_recovered=sum(p['overrides']['planned_units'].get('input_rule')=='STORED_EXPLICIT_CAPACITY' for p in work),
        source_anchors=sum(len(p['source_anchors']) for p in work),prior_projects_preserved=197)
    plan=dict(reference_date=reference.isoformat(),known_at=known.isoformat(),projects=work,summary=summary)
    write('before',before);write('candidate-inputs',list(candidates.values()));write('plan',plan)
    print(json.dumps(summary,ensure_ascii=False))


def apply():
    result=apply_plan(service(),read('plan'),BATCH,ACTOR,REASON)
    write('applied',result);print(json.dumps(result,ensure_ascii=False))


def verify():
    s=service();plan=read('plan');before=read('before');ids={p['project_id'] for p in plan['projects']}
    after=capture(s,now());write('after',after)
    # Compare all raw revisions, mappings, old manual profiles and old schedules.
    assert {p['id']:p['source_revision_id'] for p in before['raw_projects']}=={p['id']:p['source_revision_id'] for p in after['raw_projects']}
    assert {p['id']:p['mapping'] for p in before['projects']}=={p['id']:p['mapping'] for p in after['projects']}
    for kind in ('profiles','schedules'):
        old={r['id']:r['source_revision_id'] for r in before[kind] if r['project_id'] not in ids}
        current={r['id']:r['source_revision_id'] for r in after[kind] if r['project_id'] not in ids}
        assert old==current
    profiles={r['project_id']:r for r in after['profiles']};goals={}
    for r in after['schedules']:goals.setdefault(r['project_id'],{})[r['stage']]=r
    for p in plan['projects']:
        profile=profiles[p['project_id']]
        assert len(goals[p['project_id']])==6
        assert all(r['inferred'] and r['actor']==ACTOR and r['reason']==REASON for r in profile['progress'].values())
        assert all(r['event_date']<=plan['reference_date'] for r in profile['progress'].values())
        assert goals[p['project_id']]['CONSTRUCTION']['due_date']<goals[p['project_id']]['COMPLETION']['due_date']
    event_signature=lambda x:sorted((e['event_id'],e['quantity'],e['event_date']) for e in x['independent']['selected_events'])
    assert event_signature(before)==event_signature(after)
    policy=[p for p in after['projects'] if p['mapping']['policy_id']==POLICY]
    assert len(policy)==208 and all(p['id'] in profiles for p in policy)
    with s.sessions() as db:
        audits=[dict(entity_id=a.entity_id,action=a.action,before=a.before,after=a.after,recorded_at=a.recorded_at.isoformat()) for a in db.scalars(select(Audit).where(Audit.after['batch_id'].as_string()==BATCH))]
    assert len(audits)==78+sum(a['after'].get('estimate_metadata_correction',False) for a in audits)
    write('history',audits)
    result=dict(**plan['summary'],policy_projects=208,profiles_before=197,profiles_after=208,
        independent_primary_events_unchanged=True,source_revisions_unchanged=True,mappings_unchanged=True,
        prior_manual_values_unchanged=True,audit_records=len(audits),actor=ACTOR,reason=REASON,
        idempotent=apply_plan(s,plan,BATCH,ACTOR,REASON).get('unchanged') is True)
    write('verification',result);print(json.dumps(result,ensure_ascii=False))


def repair_metadata():
    # Correct the first-run capacity provenance envelope, preserving its prior
    # revision and the original applied-plan digest rather than rewriting either.
    s=service();ids={p['project_id'] for p in read('plan')['projects']};changed=[]
    with s.sessions.begin() as db:
        db.execute(text('SELECT pg_advisory_xact_lock(9072026)'))
        for old in db.scalars(select(Revision).where(Revision.kind=='project_profile',Revision.superseded_at.is_(None)).with_for_update()):
            if old.payload.get('project_id') not in ids:continue
            value=deepcopy(old.payload);cap=value.get('overrides',{}).get('planned_units',{})
            proof=cap.get('field_provenance',{})
            if isinstance(proof.get('rule'),str):cap['field_provenance']={'value':dict(proof,value=cap['value'])}
            elif not (cap.get('input_rule')=='STORED_EXPLICIT_CAPACITY' and proof.get('value',{}).get('rule')!='SOURCE_ACCEPTED'):continue
            if cap.get('input_rule')=='STORED_EXPLICIT_CAPACITY':
                cap['field_provenance']['value'].update(rule='SOURCE_ACCEPTED',derivation_rule='STORED_EXPLICIT_CAPACITY')
            value.update(estimate_metadata_correction=True,actor=ACTOR,reason=REASON,changed_at=now().isoformat())
            new,_=upsert_revision(db,'project_profile','manual_project',value['project_id'],value,BATCH)
            db.add(Audit(entity_id=new.entity_id,action='PROJECT_PROFILE_UPDATED',before=old.payload,after=value))
            changed.append(dict(project_id=value['project_id'],old_revision=old.id,new_revision=new.id))
    previous=read('metadata-correction') if (FOLDER/'metadata-correction.json').exists() else []
    write('metadata-correction',previous+changed);print(json.dumps(changed,ensure_ascii=False))


if __name__=='__main__':globals()[sys.argv[1]]()
