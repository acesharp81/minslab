"""Apply archived collector output, scopes, research findings and common repair logs."""
import argparse,hashlib,json,shutil
from collections import Counter,defaultdict
from pathlib import Path
from sqlalchemy import select
from backend.db import Audit,Batch,Revision,upsert_revision,engine_for,now,uid,entity_id
from backend.service import HomeService
from backend.api_samples import today
from backend.project_collection import collection_matrix
from backend.evidence_bridge import reconcile,by_project
from backend.collection_repairs import save
from backend.gh_portal import pdf_schedules
from backend.lh_notice_detail import parse_detail
from scripts.research_missing_sources import apply as apply_research
from scripts.repair_reviewed_project_cases import explicit_link


def refresh_review_bridge(service,project,source,evidence,basis):
 outcome=explicit_link(service,project,source,evidence,basis)
 if outcome!='preserved':return outcome
 key=project['id']+':'+source['id'];eid=entity_id('evidence_bridge','cross_source',key)
 with service.sessions.begin() as db:
  old=db.scalar(select(Revision).where(Revision.entity_id==eid,Revision.superseded_at.is_(None)))
  if not old or old.payload.get('status')!='REVIEW' or old.payload.get('reviewed'):return 'preserved'
  if old.payload.get('source_revision_no')==source['revision_no']:return 'preserved'
  payload=dict(old.payload,source_revision_no=source['revision_no'],facts=evidence,base_date=today().isoformat())
  row,result=upsert_revision(db,'evidence_bridge','cross_source',key,payload,'research_source_refresh')
  if result!='unchanged':db.add(Audit(entity_id=row.entity_id,action='EVIDENCE_SOURCE_REFRESH',before=old.payload,after=payload))
 return 'refreshed'


def archived_collectors(service,root):
 results={};shutil.copytree(root/'raw',service.data_dir/'raw',dirs_exist_ok=True)
 for sid in ['gh_notice','seoul_cleanup']:
  records=json.loads((root/(sid+'-records.json')).read_text());manifest=json.loads((root/(sid+'-manifest.json')).read_text());batch_id=uid();counts=Counter()
  with service.sessions.begin() as db:
   for kind,key,payload in records:
    if kind=='document_evidence' and sid=='gh_notice' and payload.get('pdf_original_file'):
     file=root/payload['pdf_original_file']
     if file.exists():
      plans,metadata=pdf_schedules(file.read_bytes());payload=dict(payload,**metadata)
      for f in plans:
       if payload['notice_round']!='MAIN':f=dict(f,scope_partial=True,scope_units=payload.get('offered_units'),scope_label='금회 추가 모집 범위')
       if f not in payload['facts']:payload['facts'].append(f)
    row,outcome=upsert_revision(db,kind,sid,key,payload,batch_id);counts[outcome]+=1
   db.add(Batch(id=batch_id,source_id=sid,status='SUCCESS',finished_at=now(),manifest=manifest,
       stats=dict(counts,record_count=len(records),complete_query=True,complete_population=False,scope_note='공식 목록 전체 대조와 동일 사업 상세 원문 저장 · 연구 보완 배치')))
  results[sid]=dict(counts,record_count=len(records))
 from backend.seoul_cleanup import reconcile as seoul
 results['seoul_links']=seoul(service)
 projects={p['id']:p for p in service.rows('project')}
 for doc in service.rows('document_evidence'):
  if doc['source_id']!='gh_notice':continue
  for pid in doc.get('matched_project_ids',[]):
   if pid in projects:
    value=refresh_review_bridge(service,projects[pid],doc,doc['facts'],doc['matching_basis']);results['gh_links:'+value]=results.get('gh_links:'+value,0)+1
 return results


def lh_mixed_notices(service,root):
 manifest=json.loads((root/'manifest.json').read_text());projects=service.rows('project');out=[]
 for file,typ,identifier in [('lh-aa19-national','국민임대','2015122300020607'),('lh-aa19-permanent','영구임대','2015122300020602')]:
  body=(root/file).read_bytes();url=manifest[file]['url']
  n=dict(name='인천검단 AA19 '+typ+' 최초 모집공고',region='인천광역시',notice_type=typ,notice_no=identifier,id='source-capture:'+identifier,revision_no=1,source_date='2026-08-20',evidence_url=url)
  payload=parse_detail(body,n,('인천광역시','인천검단','AA19'));digest=hashlib.sha256(body).hexdigest();dest=service.data_dir/'raw'/'lh_notice_detail'/(digest+'.html');dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(body)
  payload=dict(payload,original_file=str(dest.relative_to(service.data_dir)),base_date=today().isoformat(),date_precision='COLLECTION')
  # The date actually displayed on the page is authoritative; the placeholder
  # source_date is never used for its recruitment event.
  if payload.get('announcement_date'):payload['source_date']=payload['announcement_date']
  with service.sessions.begin() as db:r,state=upsert_revision(db,'document_evidence','lh_notice_detail',identifier,payload,'source_research')
  source=dict(payload,id=r.entity_id,source_id='lh_notice_detail',revision_no=r.revision_no)
  for p in projects:
   if '인천검단' in p['name'] and 'AA19' in p['name'] and p.get('tenure')==typ and p.get('planned_units')==payload['planned_units']:
    out.append(refresh_review_bridge(service,p,source,source['facts'],'공식 LH 최초 모집공고의 인천검단 AA19·주택유형·유형 호수 대조 · 전체 1,323호의 구성표를 포함 관계 증빙으로 보존'))
 return dict(Counter(out))


def held_research(service,held):
 sources={r['id']:r for kind in ['project','document_evidence','lh_completion_plan'] for r in service.rows(kind)};existing={(b['project_id'],b['source_entity_id']) for b in service.rows('evidence_bridge')};groups=defaultdict(list)
 for h in held:
  sid=h.get('source_entity_id');pid=h['project_id'];source=sources.get(sid)
  if not source or (pid,sid) in existing:continue
  facts=source.get('facts',[]);stages=sorted({f['stage'] for f in facts if f.get('stage') not in ('POLICY',)})
  if not stages:continue
  groups[pid].append((h,source,stages))
 for pid,rows in groups.items():
  payload=dict(name=rows[0][0]['name'],project_ids=[pid],stages=sorted({s for _,_,ss in rows for s in ss}),link_stages=sorted({s for _,_,ss in rows for s in ss}),
   base_date=today().isoformat(),checked_at=today().isoformat(),case_code='SCOPE_IDENTITY_REVIEW',case_label='원천은 확보 · 동일 사업/물량 범위 연결 검토',iteration=2,
   status='LINK_PENDING',status_label='원천 확보 · 연결 대기',query=rows[0][0]['name']+' 원천 대조',
   result_note='수집된 원천 후보가 있으나 물량 범위·임대유형·복수블록 계약이 달라 자동 연결되지 않았습니다. 기존 담당자 결정은 보존합니다.',
   candidates=[dict(title=s['name'],url=s.get('evidence_url'),primary=True,verification_label=h['reason'],source_entity_id=s['id'],source_revision_no=s.get('revision_no')) for h,s,_ in rows[:8]])
  with service.sessions.begin() as db:upsert_revision(db,'collection_research','research_case','held:'+pid,payload,'source_research')
 return len(groups)


def metrics(data):
 return dict(projects=data['total'],status=dict(Counter(c['status'] for p in data['items'] for c in p['cells'].values())),
  progress=dict(Counter(c.get('progress',{}).get('code','LEGACY') for p in data['items'] for s,c in p['cells'].items() if s!='POLICY')),
  actual_by_stage={s:sum(p['cells'][s]['actual_available'] for p in data['items']) for s in data['stages']},
  collection_tasks=sum(g.get('action_required',True) for p in data['items'] for g in p['gaps']))


def repair(service,key,title,kind,ids,sources,cause,action,remaining):
 return save(service,key,dict(title=title,repair_type=kind,project_ids=ids,source_ids=sources,stages=['BUSINESS','APPROVAL','CONSTRUCTION','SUPPLY','MOVE_IN'],
   status='APPLIED_REVIEW_PENDING',base_date=today().isoformat(),cause=cause,action=action,remaining=remaining))


def apply(service,root):
 before=collection_matrix(service);collectors=archived_collectors(service,root);mixed=lh_mixed_notices(service,root)
 research=apply_research(service,root);links=reconcile(service,apply=True);held=held_research(service,links['held']);after=collection_matrix(service)
 gh=[p['id'] for p in service.rows('project') if p['source_id'].startswith('gh_')]
 repair(service,'gh-real-portal-collection','GH · 수동 시험 원천과 실제 청약 게시판 분리로 공고 누락','COLLECTION_GAP',gh,['gh_notice','gh_supply_plan'],
  'GH 공고가 TEST_SAMPLE·manual_only로 분류돼 자동 수집에서 제외됐고 청약 임대센터의 전체 공고·상세·PDF가 사업 원장에 연결되지 않았다.',
  '실제 공식 임대주택 게시판 252건, 26페이지를 전수 대조하고 동일 사업 상세 공고 4건과 첨부를 저장했다. 다산지금A3 최초 공급 518호(2026-05-28)와 PDF 입주예정 2027-05, 광주역세권 최초 316호(2025-07-31) 및 추가 142/105호를 구분해 연결했다. 앞으로 같은 경로를 자동 수집한다.',
  '추가모집은 기존 316호에 더하지 않는다. 이전 GH 계획의 다산 입주 표기와 최신 공고 2027-05 차이는 담당자 일정 판본 검토 대상. 실제 입주 시작·건설·인허가의 구체적 사건 원문은 별도 검증한다.')
 repair(service,'seoul-phase-vs-missing-source','서울 정비사업 · 현재 추진단계와 수집 누락 혼용','AVAILABILITY_STATE',[],['seoul_cleanup','sh_inventory'],
  '공식 사업장 목록에 조합설립·정비계획 단계가 표시돼 있는데 후속 인허가·건설·입주 빈칸을 일괄 수집 방법 미확인으로 표시했다. 짧은 숫자 구역명·대표 지번 차이도 단일 후보 연결을 막았다.',
  '공식 목록 전체 1,177개와 사업 원장을 대조해 19개 사업의 추진단계·추진경과를 다시 보존했다. 같은 자치구의 고유 숫자 구역명을 숫자 경계로 구분한다. 현재 원천 단계상 미진행, 미래 예정, 명시적 미정, 실제 수집 과제를 표·상세·CSV에서 구분한다.',
  '목록 조회일은 사건일이 아니다. 미진행 표시는 원천 추진단계 기준이며 최신 갱신 여부는 확인 필요하다. 서로 다른 자치구나 1/15 같은 구역은 합치지 않는다.')
 mixed_ids=[p['id'] for p in service.rows('project') if '인천검단' in p['name'] and 'AA19' in p['name']]
 repair(service,'mixed-rental-complex-containment','혼합임대 · 총 건설호수와 임대유형 호수 차이로 선행 연결 누락','SCOPE_QUANTITY',mixed_ids,['lh_notice_detail','lh_incheon_construction','lh_incheon_rent'],
  '인천검단 AA19 전체 1,323호와 국민임대 991호·영구임대 332호가 동일호수 비교에서 분리됐으며 임대 모집공고의 전체 구성표를 읽지 못했다.',
  '공식 원문의 동일 블록 혼합 단지 구성표를 보존하고 유형별 호수 합계가 전체와 일치하는 경우에만 건설·인허가 등 선행 근거를 해당 유형 호수에 한정해 전달하도록 전체 규칙을 확장했다. 모집공고의 입주예정 2027-11은 실제 입주와 구분한다.',
  '전체 1,323호와 유형별 호수는 중복 합산하지 않는다. 복수 단지 본문의 다른 블록 구성표는 사용하지 않으며 원천 판본·담당자 결정은 보존한다.')
 repair(service,'repeated-web-source-research','전체 사업 · 검색→원문 검증→유형별 보완→재점검 이력','COLLECTION_GAP',[],['official_document','lh_notice_detail','seoul_cleanup','gh_notice'],
  f'수집 방안 미확인과 원천·연결 누락을 한 상태로 표시했고 개별 인터넷 조회 결과가 공통 규칙과 영구 검토 이력으로 남지 않았다. {research["projects"]}개 기록을 {research["research_records"]}개 검색 단위로 개별 점검했다.',
  f'검색어·후보 출처·원문 검증·반복 회차를 DB에 저장했다. 원문을 확보한 {research["document_captures"]}개 사업 범위 문서와 {research["links_added"]}개 연결을 보완하고 미연결 원천 {held}개 사업은 따로 검토 대상으로 관리한다. 검색 결과에서 사건일·물량을 만들어 넣지 않는다.',
  '원문 조회 실패·사업 식별 불명확·복수블록/주택유형 범위 차이는 추가 검증 대상. 원문 미확인과 실제 자료 부재는 구분한다. 신규 원천·판본을 대조하고 반복 검색 기록을 이어갈 수 있다.')
 ids=[p['id'] for p in service.rows('project') if p.get('region') in ('서울특별시','경기도','인천광역시')]
 repair(service,'representative-map-overlap-picker','대표 위치 중첩 · 사업을 클릭할 수 없는 지도 표식','IDENTITY_LINK',ids,[],
  '원천 대표 좌표가 같거나 화면에서 가까운 여러 사업의 라벨·가상 건물이 겹쳐 첫 사업만 선택됐다.',
  '화면상 겹치는 표식을 묶어 각 사업명·원천 구분·물량을 가진 선택 목록으로 연다. 동일 근사점의 가상 모델 배치만 분산하고 원천 좌표·물량·사업 ID는 그대로 보존한다.',
  '가상 배치 이동은 실제 필지·건물 위치가 아니다. 근사 좌표는 주소·PNU 확보 시 정밀도를 보완하며 묶음 물량을 합산하지 않는다.')
 result=dict(before=metrics(before),after=metrics(after),collectors=collectors,mixed_notices=mixed,research=research,links_added=links['added_links'],held_project_groups=held)
 (service.data_dir/'source_research').mkdir(exist_ok=True);(service.data_dir/'source_research'/'round-20261013.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
 return result

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);a=p.parse_args();print(json.dumps(apply(HomeService(engine_for(),'/app/data'),a.root),ensure_ascii=False,indent=2))
