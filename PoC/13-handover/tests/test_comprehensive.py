"""Integrated synthetic sample: source versions, grouping, review, delivery and reports."""
import copy,io,json,zipfile
from pathlib import Path
from fastapi.testclient import TestClient
from app.main import create_app
from app.timeline import reported_progress
from app.reports import build_report
from app.practice_report import resources
from app.vision import postprocess
from test_flow import generate
ROOT=Path(__file__).resolve().parents[1]

def exercise(c,artifact_dir=None):
 c.headers['X-Employee']='employee2'
 response=c.post('/api/demo-sets',json={'kind':'comprehensive','predecessor_id':'employee2','successor_id':'employee3'});assert response.status_code==201,response.text
 ids=response.json();base='/api/cases/'+ids['target_case_id'];source='/api/cases/'+ids['source_case_id'];d=c.get(base).json()
 assert len(d['documents'])==19 and not d['jobs'] and d['demo_image_manual_only']
 assert sum(x['path']=='자료/보고서.hwpx' for x in d['documents'])==3
 original=c.get(source+'/revisions/confirmed').json();opts=c.get(base+'/inheritance-options').json();option=next(o for o in opts if o['id']==ids['source_case_id'])
 rev=generate(c,base,{'basis_case_id':option['id'],'basis_revision_id':option['revision_id']})
 items=rev['payload']['items'];assert len(items)==7,[(i['fields']['title']['value'],reported_progress(i)) for i in items]
 first=next(i for i in items if i['fields']['title']['value']=='지역생활서비스 통합지원');assert reported_progress(first)==65
 selected=next(e for e in first['timeline'] if e['selection_status']=='selected');assert selected['revision_no']==3 and selected['path']=='자료/보고서.hwpx',selected
 assert any(e['selection_status']=='excluded' and e['revision_no']==4 for e in first['timeline'])
 assert len(rev['payload']['document_ids'])==21
 for title,progress,revision,stamp,excluded in [
  ('보조금 정산 승인',40,2,'2026-11-08T16:00',{'대체됨'}),
  ('공공데이터 개방 품질개선',60,3,'2026-11-08T17:30',{'검토중','폐기'})]:
  item=next(i for i in items if i['fields']['title']['value']==title)
  chosen=next(e for e in item['timeline'] if e['selection_status']=='selected')
  assert reported_progress(item)==progress and chosen['revision_no']==revision and chosen['issued_at']==stamp,chosen
  assert excluded <= {e['document_state'] for e in item['timeline'] if e['selection_status']=='excluded'}
  # Raw table-only details must be available through the same source API as the report viewer.
  blocks=c.get(base+'/documents/'+chosen['document_id']+'/blocks').json()
  marker='TBL-CP3-R1' if revision==2 else 'TBL-CP5-R1'
  assert any(marker in b['text'] for b in blocks),marker
 groups=[];related=[]
 for item in items:
  if any(e.get('work_code')=='CP-002' for e in item.get('timeline',[])):related.append(item)
  else:groups.append({'item_ids':[item['id']],'title':item['fields']['title']['value'],'owner':item['fields']['owner']['value']})
 assert len(related)==3
 groups.append({'item_ids':[i['id'] for i in related],'title':'문화시설 통합예약 개선','owner':'디지털지원팀 한새봄(가상)'})
 r=c.post(base+f'/revisions/{rev["id"]}/groups',json={'expected_hash':rev['hash'],'groups':groups,'reason':'memo.pdf에서 CP-002 동일 전체 범위·진행률 기준·담당 확인'});assert r.status_code==200,r.text;rev=r.json()
 expected=json.loads((ROOT/'release/public/comprehensive-expected.json').read_text())
 assert {i['fields']['title']['value']:reported_progress(i) for i in rev['payload']['items']}==expected['progress']
 assert rev['payload']['inheritance']['counts']=={'updated':1,'carried':1,'new':3,'review':0}
 assert next(i for i in rev['payload']['items'] if i['fields']['title']['value']=='공공시설 안전점검')['business_status']=='COMPLETED'
 # The reference ledger provides a common date. The old accepted report stays immutable.
 item=next(i for i in rev['payload']['items'] if i['fields']['title']['value']=='공공시설 안전점검')
 value=item['fields']['budget']['value'].replace('2026-01-08','2026-11-08')
 r=c.patch(base+f'/revisions/{rev["id"]}/items/{item["id"]}',json={'expected_hash':rev['hash'],'fields':{'budget':value,'notes':'인수자와 11월 11일 오전 진행상황 재확인 예정'},'reason':'q77.xlsx 예산 검산 시트의 11월 8일 잔액 대조, 인수자 협의 예정 기록'});assert r.status_code==200,r.text;rev=r.json()
 assert rev['readiness']['missing_fields']==0,rev['readiness']
 c.post(base+f'/revisions/{rev["id"]}/confirm',json={'expected_hash':rev['hash'],'acknowledge_warnings':True}).raise_for_status()
 confirmed=c.get(base+'/revisions/confirmed').json();report=build_report(c.get(base).json(),confirmed,lambda bid:c.get(base+'/blocks/'+bid).json());shared=resources(report)
 assert len(shared['budgets'])==6 and len(shared['contacts'])==6,shared
 assert shared['totals']=={'편성액':400000000,'집행액':259000000,'지급예정액':45000000,'가용잔액':96000000},shared
 assert not shared['notes'],shared['notes']
 store=c.app.state.store;docs=store.rows('SELECT * FROM documents WHERE case_id=?',(ids['target_case_id'],));calls=[]
 class MockImage:
  def transcribe(self,picture):calls.append(picture['sha']);return {'text':'검증용 대체 응답: 확인 완료 5건','cached':False}
 images,notes=postprocess(store,MockImage(),copy.deepcopy(rev['payload']['items']),docs,ids['target_case_id']);assert len(calls)==1 and len(images)==1
 assert not rev['payload']['image_notes'] # no automatic image call during generation
 opinion='보조금 누락 영수증을 우선 요청하고, 11월 13일 협약 원본 접수를 확인해 주세요.'
 c.post(base+'/deliver',json={'revision_id':rev['id'],'expected_hash':rev['hash'],'recipient_id':'employee3','message':opinion}).raise_for_status()
 c.headers['X-Employee']='employee3';assert c.get(base).json()['deliveries'][0]['message']==opinion
 exports={}
 for fmt in ['html','md','docx']:
  r=c.get(base+f'/exports/{rev["id"]}.{fmt}');r.raise_for_status();exports[fmt]=r.content
 text=exports['html'].decode()
 for needle in ['gantt-wrap','이전 인계 보고서 기반','400,000,000원','96,000,000원','D01','G05','source-dialog']:assert needle in text,needle
 assert text.index('gantt-wrap')<text.index('id="task-1"')
 assert '지연 306일' not in text and '신규 업무 3건' in text
 c.post(base+'/accept',json={'expected_hash':rev['hash']}).raise_for_status();assert c.get(base).json()['accepted']
 c.headers['X-Employee']='employee2';assert c.get(source+'/revisions/confirmed').json()==original
 result={'documents':21,'same_name_versions':3,'draft_candidates':7,'final_tasks':5,'progress':expected['progress'],'unique_budgets':6,'unique_contacts':6,'budget_totals':shared['totals'],'inheritance_preserved':True,'version_selection':True,'same_day_revision_selection':True,'same_revision_timestamp_selection':True,'excluded_states':['초안','검토중','대체됨','폐기'],'three_way_grouping':True,'field_review':True,'report_exports':list(exports),'delivery_and_acceptance':True,'image_selection_mocked':{'latest':len(images),'excluded':2},'paid_model_calls':0,'scope':'합성 라벨 자료 기능 검증; Solar 응답·실제 그림 판독 정확도 평가 아님'}
 if artifact_dir:
  artifact_dir.mkdir(parents=True,exist_ok=True)
  for fmt,data in exports.items():(artifact_dir/f'comprehensive-report.{fmt}').write_bytes(data)
  (artifact_dir/'validation.json').write_text(json.dumps(result,ensure_ascii=False,indent=2));(artifact_dir/'report-data.json').write_text(json.dumps(report,ensure_ascii=False,indent=2));(artifact_dir/'case.json').write_text(json.dumps(ids))
 return result

def test_comprehensive_end_to_end(tmp_path):
 with TestClient(create_app(tmp_path)) as c:exercise(c)


def test_budget_dates_do_not_override_report_date():
 from app.versions import metadata
 blocks=[{'text':'보고일: 2026-11-08'}, {'text':'○ (예산 현황) 예산코드: B1 | 편성액: 100원 |\n기준일: 2026-01-08 | 범위: 사업\n예산코드: B2 | 기준일: 2026-11-01 | 편성액: 200원'}]
 m=metadata(blocks,lambda b,q:{'quote':q})
 assert m['reported_at']=='2026-11-08' and not m['metadata_problems']
 m=metadata(blocks+[{'text':'내용 기준일: 2026-11-07'}],lambda b,q:{'quote':q})
 assert m['reported_at'] is None and 'reported_at 본문 값 상충' in m['metadata_problems']


def test_hwpx_breaks_and_existing_parse_readback(tmp_path,monkeypatch):
 from app.parsers import parse
 from app.store import digest
 from test_flow import new_case
 with zipfile.ZipFile(ROOT/'release/public/comprehensive-current.zip') as z:data=z.read('자료/보고서.hwpx')
 path=tmp_path/'input.hwpx';path.write_bytes(data);status,_,blocks=parse(path,'.hwpx')
 assert status=='PARTIAL' and digest(path.read_bytes())==digest(data)
 budget=next(b['text'] for b in blocks if '○ (예산 현황)' in b['text'])
 assert '\n예산코드: CP-COM' in budget
 import app.jobs as jobs,app.main as main
 original_parser=jobs.PARSER_VERSION
 monkeypatch.setattr(jobs,'PARSER_VERSION','source-v2-legacy');monkeypatch.setattr(main,'PARSER_VERSION','source-v2-legacy')
 with TestClient(create_app(tmp_path/'app')) as c:
  base=new_case(c);c.post(base+'/documents',files={'file':('input.hwpx',data)}).raise_for_status();generate(c,base)
  doc=c.get(base).json()['documents'][0]
  monkeypatch.setattr(jobs,'PARSER_VERSION',original_parser);monkeypatch.setattr(main,'PARSER_VERSION',original_parser)
  old=c.get(base).json()['documents'][0];assert old['status']=='PARTIAL' and old['parse_id']==doc['parse_id']
  old_blocks=c.get(base+'/documents/'+doc['id']+'/blocks');assert old_blocks.status_code==200 and old_blocks.json()
  generate(c,base,{'request_id':'reparse-v3'})
  current=c.get(base).json()['documents'];assert len(current)==1 and current[0]['parse_id']!=doc['parse_id']


def test_integrated_public_preview_has_inline_security_policy(tmp_path):
 with TestClient(create_app(tmp_path)) as c:
  r=c.get('/downloads/comprehensive-report.html')
  assert r.status_code==200
  assert r.headers['content-disposition'].startswith('inline')
  assert 'script-src' in r.headers['content-security-policy']
  assert '400,000,000원' in r.text


def inspect_source_tables(tmp_path):
 from collections import Counter
 from xml.etree import ElementTree as ET
 from app.parsers import parse
 expected=json.loads((ROOT/'release/public/comprehensive-expected.json').read_text())
 counts=Counter();tables=0;markers=0
 for index,entry in enumerate(expected['files']):
  with zipfile.ZipFile(ROOT/'release/public'/entry['pack']) as z:data=z.read(entry['file'])
  path=tmp_path/(str(index)+Path(entry['file']).suffix);path.write_bytes(data)
  status,warnings,blocks=parse(path,path.suffix)
  assert status in {'SUCCESS','PARTIAL'},(entry,status,warnings)
  text='\n'.join(b['text'] for b in blocks)
  for marker in entry['table_markers']:
   assert marker in text,(entry['file'],entry['pack'],marker)
   markers+=1
  # Verify real tables/worksheets rather than decorative text labelled as a table.
  if path.suffix=='.hwpx':
   with zipfile.ZipFile(path) as z:
    actual=sum(sum(1 for e in ET.fromstring(z.read(n)).iter() if e.tag.endswith('}tbl')) for n in z.namelist() if n.startswith('Contents/section') and n.endswith('.xml'))
   assert actual==5,(entry,actual)
  if path.suffix=='.xlsx':
   from openpyxl import load_workbook
   w=load_workbook(path,read_only=True);assert len(w.sheetnames)==6;w.close()
  counts[path.suffix]+=1;tables+=entry['tables']
 assert tables==95 and markers==76 and counts=={'.hwpx':9,'.xlsx':5,'.pdf':5}
 return {'business_report_documents':19,'business_report_tables':tables,'table_only_markers_verified':markers,'formats':dict(counts)}


def test_all_report_tables_preserve_details(tmp_path):
 inspect_source_tables(tmp_path)


def test_latest_selection_unchanged_by_reverse_upload(tmp_path):
 from test_flow import new_case
 with TestClient(create_app(tmp_path/'data')) as c:
  base=new_case(c)
  # Deliberately upload excluded states first and current documents last.
  for pack in ['comprehensive-draft.zip','comprehensive-old.zip','comprehensive-current.zip']:
   with zipfile.ZipFile(ROOT/'release/public'/pack) as z:
    for name in reversed(z.namelist()):c.post(base+'/documents',files={'file':(name,z.read(name))}).raise_for_status()
  rev=generate(c,base);items=rev['payload']['items']
  assert len(items)==6
  for title,value in [('지역생활서비스 통합지원',65),('보조금 정산 승인',40),('공공데이터 개방 품질개선',60)]:
   item=next(i for i in items if i['fields']['title']['value']==title)
   assert reported_progress(item)==value,(title,item)
