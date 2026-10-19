"""Narrow, transactional correction of this task's category-only policy links."""
import json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from backend.service import HomeService
from backend.db import engine_for
from backend.policy_scope_correction import correct
from backend.api_samples import today
FOLDER=ROOT/'data/remediation/start-linkage-20261019'
s=HomeService(engine_for(),ROOT/'data')
plan=json.loads((FOLDER/'link-plan.json').read_text())
old=json.loads((FOLDER/'protected-before.json').read_text())
profiles={p['project_id']:p for p in s.rows('project_profile')}
result=correct(s,plan)
after={p['project_id']:p for p in s.rows('project_profile')}
assert {k:p['source_payload_hash'] for k,p in profiles.items()}=={k:p['source_payload_hash'] for k,p in after.items()}
projects={p['id']:p for p in s.projects()};schedules={p['id']:p for p in s.rows('execution_schedule')}
assert all(projects[p['project_id']]['mapping']==p['mapping'] for p in old['mappings'])
assert all(schedules[p['id']]['source_payload_hash']==p['source_payload_hash'] for p in old['schedules'])
for item in plan['items']:
    assert projects[item['project_id']]['mapping']['policy_id']=='UNASSIGNED'
result.update(profiles_preserved=len(profiles),prior_mappings_preserved=len(old['mappings']),prior_schedules_preserved=len(old['schedules']))
(FOLDER/'policy-scope-corrected.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
snapshot=dict(local_date=today().isoformat(),projects=list(projects.values()),raw_projects=s.rows('project'),profiles=list(after.values()),bridges=s.rows('evidence_bridge'),stage_links=s.rows('stage_evidence'),programs=s.program_links(projects=list(projects.values())))
(FOLDER/'scope-corrected-snapshot.json').write_text(json.dumps(snapshot,ensure_ascii=False,default=str)+'\n')
print(json.dumps(result,ensure_ascii=False))
