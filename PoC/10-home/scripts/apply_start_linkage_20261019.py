"""Explicit user-requested linkage + the existing incremental estimate workflow."""
import json
from pathlib import Path
import sys
from copy import deepcopy
from sqlalchemy import select
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from backend.service import HomeService
from backend.db import engine_for, Revision, now
from backend.start_linkage import prepare, apply_links, apply_identities, BATCH
from backend.incremental_estimates import values, apply as apply_estimates
from backend.api_samples import today
from backend.project_profile import STAGES

FOLDER=ROOT/'data/remediation/start-linkage-20261019'
ACTOR='사용자 요청'
REASON='기존과 동일하게 선후 관계의 값을 확인하여 연결성을 확보하고 이에 따른 추정값 반영'


def save(name,value):
    FOLDER.mkdir(parents=True,exist_ok=True)
    (FOLDER/(name+'.json')).write_text(json.dumps(value,ensure_ascii=False,indent=2,default=str)+'\n')


def read(name):return json.loads((FOLDER/(name+'.json')).read_text())


def main(action):
    s=HomeService(engine_for(),ROOT/'data')
    if action=='prepare':
        if (FOLDER/'link-plan.json').exists():raise ValueError('기존 적용안 보존')
        plan=prepare(s.projects(),s.rows('general_permit'),s.rows('document_evidence'),s.rows('renewal_inventory'))
        save('link-plan',plan)
        save('protected-before',dict(profiles=s.rows('project_profile'),schedules=s.rows('execution_schedule'),
            mappings=[dict(project_id=p['id'],mapping=p['mapping']) for p in s.rows('project')]))
        print(json.dumps(dict(items=len(plan['items']),held=plan['held']),ensure_ascii=False));return
    plan=read('link-plan')
    if action=='links':
        result=apply_links(s,plan,ACTOR,REASON)
        result['identities']=apply_identities(s,plan,ACTOR,REASON)
        save('links-applied',result);print(json.dumps(result,ensure_ascii=False));return
    if action=='estimate':
        if (FOLDER/'estimate-plan.json').exists():raise ValueError('기존 추정안 보존')
        with s.sessions() as db:
            model_row=db.scalar(select(Revision).where(Revision.kind=='officer_duration_model').order_by(Revision.recorded_at.desc()).limit(1))
            model=model_row.payload['model'];model_ref=dict(entity_id=model_row.entity_id,revision_id=model_row.id,historical_model=True)
        projects={p['id']:p for p in s.projects()};prior={p['project_id'] for p in s.rows('project_profile')}
        work=[];skipped=[]
        for item in plan['items']:
            p=projects[item['project_id']]
            if p['id'] in prior:
                skipped.append(dict(id=p['id'],reason='기존 담당자 입력 보존'));continue
            cells={stage:dict(sources=[],targets=[],progress={},assessment=None) for stage in ('POLICY','BUSINESS','APPROVAL','CONSTRUCTION','SUPPLY','MOVE_IN')}
            anchors=[]
            for f in item['facts']:
                stage=f.get('stage');milestone=f.get('milestone') or stage;day=f.get('date')
                if f.get('kind')!='ACTUAL' or not day or day>today().isoformat() or stage not in cells:continue
                if stage=='APPROVAL' and day!=item['approval_date']:continue
                if milestone=='CONSTRUCTION' and day!=item['start_date']:continue
                cells[stage]['sources'].append(dict(f,units=f.get('units'),source_id=item['source']['source_id'],
                    evidence_url=item['source']['evidence_url'],review_status='CONFIRMED'))
                if milestone in STAGES:
                    anchors.append(dict(stage=milestone,due_date=day,precision='DAY',
                        source_entity_id=item['source']['id'],source_revision_id=item['source']['source_revision_id'],
                        evidence_url=item['source']['evidence_url'],basis=f['basis']))
            # Use the adopted quantity only in the managed overlay. The source
            # project keeps None for incomplete source totals.
            p=deepcopy(p);p['planned_units']=item['planned_units']
            result=values(p,cells,model,now().isoformat(),ACTOR,REASON,today(),anchors)
            proof=item['quantity_proof']
            result['overrides']['planned_units'].update(value=item['planned_units'],inferred=proof['inferred'],
                input_rule=proof['rule'],input_basis=proof.get('basis','동일 사업 원천 호수'),field_provenance={'value':proof})
            refs=[dict(entity_id=p['id'],revision_id=p['source_revision_id']),
                dict(entity_id=item['source']['id'],revision_id=item['source']['source_revision_id']),model_ref]
            if proof.get('source_revision_id'):refs.append(dict(entity_id=proof['source_entity_id'],revision_id=proof['source_revision_id']))
            result.update(mapping_revision_no=p['mapping']['revision_no'],policy_id=p['mapping']['policy_id'],
                evidence_url=p['evidence_url'],pinned_inputs=refs,quantity_proof=proof)
            work.append(result)
        summary=dict(projects=len(work),skipped=skipped,targets=sum(len(p['targets']) for p in work),
            estimated_measurements=sum(len(p['progress']) for p in work),
            construction_2026_units=sum(p['progress']['CONSTRUCTION']['units'] for p in work
                if 'CONSTRUCTION' in p['progress'] and p['progress']['CONSTRUCTION']['event_date'].startswith('2026')))
        save('estimate-plan',dict(reference_date=today().isoformat(),projects=work,summary=summary))
        print(json.dumps(summary,ensure_ascii=False));return
    if action=='apply':
        result=apply_estimates(s,read('estimate-plan'),BATCH+'-estimates',ACTOR,REASON)
        save('estimates-applied',result);print(json.dumps(result,ensure_ascii=False));return
    if action=='verify':
        old=read('protected-before');profiles={r['project_id']:r for r in s.rows('project_profile')}
        schedules={r['id']:r for r in s.rows('execution_schedule')};projects={p['id']:p for p in s.projects()}
        assert all(profiles[p['project_id']]['source_payload_hash']==p['source_payload_hash'] for p in old['profiles'])
        assert all(schedules[p['id']]['source_payload_hash']==p['source_payload_hash'] for p in old['schedules'])
        assert all(projects[p['project_id']]['mapping']==p['mapping'] for p in old['mappings'])
        ids={i['project_id'] for i in plan['items']}
        result=dict(old_profiles_preserved=len(old['profiles']),old_schedules_preserved=len(old['schedules']),
            old_mappings_preserved=len(old['mappings']),projects=[p for p in projects.values() if p['id'] in ids],
            profiles=[p for k,p in profiles.items() if k in ids],
            schedules=[p for p in schedules.values() if p['project_id'] in ids])
        save('verified',result);print(json.dumps({k:v for k,v in result.items() if isinstance(v,int)},ensure_ascii=False));return
    raise ValueError('unknown action')


if __name__=='__main__':main(sys.argv[1])
