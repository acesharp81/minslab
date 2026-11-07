import json
from pathlib import Path
from app.config import get_settings
from app.db.connection import connect
from app.db.meeting_brief_repository import MeetingBriefRepository
from app.db.topic_structure_repository import TopicStructureRepository
from app.services.structured_narrative import inputs,validate,merge_field_repair,PROFILE
s=get_settings();p=Path('/app/data/recovery/20261107-report-audit/repairs');bid='f09e1d8c-35df-4ded-beb5-310d0830e53e'
f=next(p.glob(bid+'-*.json'));d=json.loads(f.read_text());issue,plan=d['plans'][0];merged=merge_field_repair(plan,d['response'][issue['id']]);validate([issue],merged)
with connect(s.database_url) as lease:
 assert lease.execute('SELECT pg_try_advisory_lock(hashtext(%s))',('topic-structure:'+bid,)).fetchone()[0]
 with connect(s.database_url) as c:
  item=MeetingBriefRepository(c).latest(bid);repo=TopicStructureRepository(c);brief=repo.ready_current(item);sid=brief['topic_structure']['revision_id'];current={i['id']:i for i in inputs(brief,repo.snapshot(sid))}
  assert current[issue['id']]['fingerprint']==issue['fingerprint']
  hist=repo.batches(sid);repo.record(sid,max(h['index'] for h in hist)+1,1,{'profile':PROFILE,'issues':[issue],'repair_policy':'historical-report-audit/1','repaired_fields':plan['fields']},merged,{'provider':'openai','model':'gpt-6.1-terra','source_response_path':str(f),'additional_model_calls':0,'verification':'Extreme repeated syllables inspected; original point and evidence retained.'},None)
 print('READY_SOURCE_ONLY',bid,issue['id'])
