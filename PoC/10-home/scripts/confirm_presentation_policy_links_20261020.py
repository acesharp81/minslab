"""Evidence-only officer recheck. Preserve projects, mappings and stage quantities."""
import argparse,json,hashlib
from pathlib import Path
from sqlalchemy import select
from backend.db import Revision,Mapping,ProgramMapping,Audit,engine_for,upsert_revision
from backend.service import HomeService
from scripts.review_policy_readmission_20261019 import protected,digest
POLICY='POL_2025_0907'
BATCH='presentation-final-20261020'
ACTOR='담당자 대행 · 공식 명시 9·7 사업 연결 확인 사용자 지시 2026-10-20'
PROGRESS='https://www.korea.kr/common/download.do?fileId=198344116'
SHA='9813bc03471c8899f346fe92415c0331115635184d6b810f5d8d33c30fbe825d'
URBAN=['PRO_47484524b36e9d7b3af3fe27','PRO_2d1e1ea17c963204dbdfbe9a','PRO_4bdc93d4fcf60d9eabdb1081','PRO_e12cd2ca5b4a653afccf0d46']
C5='PRO_3825614a4d690a6e58e8bbad'
def run(apply=False):
 s=HomeService(engine_for());folder=s.data_dir/BATCH
 body=(folder/'live-sources/policy-progress.pdf').read_bytes()
 assert hashlib.sha256(body).hexdigest()==SHA
 before=protected(s);results=[]
 with s.sessions.begin() as db:
  records=list(db.scalars(select(Revision).where(Revision.superseded_at.is_(None),Revision.kind.in_(['project','agency_plan','evidence_bridge']))))
  projects={r.entity_id:r for r in records if r.kind=='project'};bridges=[r for r in records if r.kind=='evidence_bridge']
  plans=[r for r in records if r.kind=='agency_plan' and r.payload.get('policy_relationship') in ['EXPLICIT_FOLLOWUP_TENDER','EXPLICIT_FIRST_ROUND_907']]
  assert len(plans)==14 and sum(r.payload['units'] for r in plans)==8031
  proposals=[]
  for src in plans:
   links=[r for r in bridges if r.payload.get('source_entity_id')==src.entity_id and r.payload.get('status')=='CONFIRMED']
   ids=set(r.payload['project_id'] for r in links);assert len(ids)==1
   pid=ids.pop();p=projects[pid];m=db.scalar(select(Mapping).where(Mapping.project_id==pid))
   assert m and m.policy_id==POLICY and m.status=='CONFIRMED' and p.payload['planned_units']==src.payload['units']
   proposals.append((pid,p,m,dict(source_entity_id=src.entity_id,source_revision_no=src.revision_no,
     units=src.payload['units'],evidence_url=src.payload['evidence_url'],policy_evidence_url=src.payload.get('policy_evidence_url'),
     original_sha256=src.payload.get('original_sha256'),basis=m.basis,scope='EXPLICIT_BLOCK_FOLLOWUP')))
  for pid in URBAN+[C5]:
   p=projects[pid];m=db.scalar(select(Mapping).where(Mapping.project_id==pid));assert m.policy_id==POLICY and m.status=='CONFIRMED'
   proposals.append((pid,p,m,dict(units=p.payload['planned_units'],evidence_url=PROGRESS,
    original_sha256=SHA,basis='9·7 이행실적 공식 원문에 사업명·호수 명시. 기존 승인 연결을 담당자 대행 재확인. C5는 490호·단독→공동 전환과 고시·LH 공모 교차 확인.' if pid==C5 else '9·7 이행실적의 1차 도심 유휴부지 명단과 이름·호수 일치. 후속 공모의 변경 수량과 기존 승인 수량은 별도 보존.',scope='EXPLICIT_NAMED_PROJECT')))
  assert len(proposals)==19 and sum(p[3]['units'] for p in proposals)==12579
  for pid,p,m,meta in proposals:
   payload=dict(name=p.payload['name'],sample_kind='document_evidence',source_object_id=BATCH+':confirmed:'+pid,
     source_date='2026-10-20',base_date='2026-10-20',date_precision='DAY',facts=[],matched_project_ids=[pid],
     proposed_policy=POLICY,policy_mapping_status='CONFIRMED',program_id=m.program_id,
     review_decision='EXPLICIT_POLICY_LINK_RECONFIRMED',review_actor=ACTOR,**meta)
   action='preview'
   if apply:
    row,action=upsert_revision(db,'document_evidence','officer',payload['source_object_id'],payload,BATCH)
    if action!='unchanged':db.add(Audit(entity_id=row.entity_id,action='POLICY_LINK_RECONFIRMED',before={},after=payload))
   results.append(dict(project_id=pid,name=p.payload['name'],units=meta['units'],program_id=m.program_id,action=action,**{k:v for k,v in meta.items() if k!='units'}))
  pg=db.scalar(select(ProgramMapping).where(ProgramMapping.name=='LH 직접시행 전환·토지이용 효율화',ProgramMapping.policy_id==POLICY))
  assert pg and pg.status=='CONFIRMED'
  for name,units in [('남양주왕숙 유보지→주택 전환',455),('파주운정3 유보지→주택 전환',3200)]:
   payload=dict(name=name,sample_kind='document_evidence',source_object_id=BATCH+':district:'+name,
     source_date='2026-10-20',base_date='2026-10-20',units=units,facts=[],matched_project_ids=[],
     evidence_url=PROGRESS,original_sha256=SHA,proposed_policy=POLICY,policy_mapping_status='CONFIRMED',
     program_id=pg.id,review_actor=ACTOR,review_decision='POLICY_CONFIRMED_BLOCK_UNRESOLVED',
     quantity_scope='DISTRICT_CONVERSION_PLAN',basis='공식 9·7 이행실적에 지구명·유보지→주택·호수가 명시되어 정책·프로그램 관계 확인. 개별 블록·기존사업 포함관계 미분리이므로 신규 사업 또는 착공으로 가산하지 않음.')
   action='preview'
   if apply:
    row,action=upsert_revision(db,'document_evidence','officer',payload['source_object_id'],payload,BATCH)
    if action!='unchanged':db.add(Audit(entity_id=row.entity_id,action='POLICY_SCOPE_CONFIRMED',before={},after=payload))
   results.append(dict(name=name,units=units,action=action,scope=payload['quantity_scope'],basis=payload['basis']))
 after=protected(s);assert before==after,'기존 사업·일정·연결 변경'
 result=dict(applied=apply,projects_confirmed=19,project_units=12579,scope_only_records=2,scope_only_units=3655,
     protected_unchanged=True,protected_hash=digest(before),quantity_added=0,results=results)
 dest=folder/('policy-review-applied.json' if apply else 'policy-review-preview.json')
 if apply and all(r['action']=='unchanged' for r in results):dest=folder/'policy-review-idempotence.json'
 dest.write_text(json.dumps(result,ensure_ascii=False,indent=2));print(json.dumps({k:v for k,v in result.items() if k!='results'},ensure_ascii=False))
if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('--apply',action='store_true');run(parser.parse_args().apply)
