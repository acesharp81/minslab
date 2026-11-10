import copy,json,random,zipfile
from pathlib import Path
import pytest
from app.versions import newest
from app.timeline import project_latest,reported_progress,report_metadata
from app.engine import FIELDS,empty_field,merge_candidates,llm_discover
from app.parsers import parse
ROOT=Path(__file__).resolve().parents[1]

def event(id='a',day='2026-11-08',revision=1,time='2026-11-08T10:00',progress=80,state='확정',owner='과 김담당',code='A-1'):
 fields={k:empty_field() for k in FIELDS}
 for k,v in {'title':'같은 사업','status':str(progress)+'% 진행 중','owner':owner,'issues':'업무 현안','due_date':'2026-11-13'}.items():fields[k]['value']=v
 return dict(document_id=id,path=id+'.hwpx',reported_at=day,revision_no=revision,issued_at=time,progress=progress,report_id='R-1',document_state=state,work_code=code,fields=fields)

def candidate(e):return {'id':e['document_id'],'fields':copy.deepcopy(e['fields']),'timeline':[e],'source_documents':[e['document_id']]}

def test_later_same_day_correction_can_reduce_progress():
 old=event();new=event('b',revision=2,time='2026-11-08T16:00',progress=65)
 for es in [[old,new],[new,old]]:
  item=project_latest(merge_candidates([{'candidates':[candidate(copy.deepcopy(e))]} for e in es])[0])
  assert reported_progress(item)==65 and item['latest_document_id']=='b'
  assert item['fields']['status']['value']=='65% 진행 중'

@pytest.mark.parametrize('change',[{'reported_at':None},{'metadata_problems':['reported_at 상충']},{'revision_no':1,'issued_at':'2026-11-08T10:00'},{'revision_no':2,'issued_at':'2026-11-08T09:00'},{'report_id':None}])
def test_uncertain_versions_abstain(change):
 a=event();b=event('b',progress=65);b.update(change)
 assert newest([a,b])[0] is None


def test_draft_exclusion_and_human_override():
 approved=event();draft=event('d',day='2026-11-09',revision=3,progress=100,state='초안')
 item=candidate(approved);item['timeline'].append(draft)
 item['fields']['owner'].update(value='사람이 확인한 담당',provenance='HUMAN_ENTERED')
 project_latest(item)
 assert reported_progress(item)==80 and item['fields']['owner']['value']=='사람이 확인한 담당'
 assert item['fields']['status']['value']=='80% 진행 중'
 assert item['timeline'][-1]['selection_status']=='excluded'


def test_explicit_project_identity_survives_owner_change():
 a=event();b=event('b',revision=2,time='2026-11-08T16:00',owner='과 신담당')
 assert len(merge_candidates([{'candidates':[candidate(a),candidate(b)]}]))==1
 a=event();b=event('b',code='B-2')
 assert len(merge_candidates([{'candidates':[candidate(a),candidate(b)]}]))==2


def test_filename_never_reaches_model(monkeypatch):
 seen=[]
 class Response:
  status_code=200
  def json(self):return {'choices':[{'finish_reason':'stop','message':{'content':'{"items":[]}'}}],'usage':{}}
 def completion(config,request,*args):seen.append(request['messages']);return Response()
 monkeypatch.setattr('app.engine.completion_request',completion)
 for filename in ['기밀제목_최신2027.pdf','무관한파일.pdf']:
  llm_discover({'path':filename,'id':'d'},[{'id':'b','text':'동일 본문'}],{'model':'test','key':'not-real'})
 assert seen[0]==seen[1]
 assert '기밀제목' not in json.dumps(seen,ensure_ascii=False)


def test_all_authored_formats_metadata_and_negative_packages(tmp_path):
 expected=json.loads((ROOT/'release/public/version-expected.json').read_text())
 assert len(expected['inputs'])==13
 lookup={}
 for pack in ['version-samples.zip','version-samples-shuffled.zip','version-edge-conflict.zip','version-edge-undated.zip','version-edge-reversed.zip']:
  events=[]
  with zipfile.ZipFile(ROOT/'release/public'/pack) as z:
   for n,name in enumerate(z.namelist()):
    path=tmp_path/(str(n)+Path(name).suffix);path.write_bytes(z.read(name));status,_,blocks=parse(path,path.suffix)
    assert status in {'SUCCESS','PARTIAL'} and len(blocks)>30
    for i,b in enumerate(blocks):b.update(id=str(i),doc_id=str(n),parse_id='test')
    meta=report_metadata(blocks)
    e=event(str(n),progress=meta['progress']);e.update(meta);e['fields']['status']['value']=str(meta['progress']);events.append(e)
  if 'edge-' in pack:assert newest(events)[0] is None,pack
  else:
   selected={code:newest([e for e in events if e['work_code']==code and e['document_state']=='확정'])[0] for code in {e['work_code'] for e in events}}
   for item in expected['expected_works']:
    actual=selected[item['work_code']]
    assert actual['progress']==item['progress'] and actual['revision_no']==3
   lookup[pack]={k:(v['progress'],v['reported_at'],v['revision_no']) for k,v in selected.items()}
 assert lookup['version-samples.zip']==lookup['version-samples-shuffled.zip']


def test_metadata_spreadsheet_columns_and_duplicate_abstention():
 block={'id':'b','doc_id':'d','parse_id':'p','text':'A1: 보고일: 2026-11-08 | B1: 전체 진행률: 65%'}
 m=report_metadata([block]);assert m['reported_at']=='2026-11-08' and m['progress']==65 and not m['metadata_problems']
 block2={**block,'id':'c','text':'○ (내용 기준일) 2026. 11. 7.'}
 m=report_metadata([block,block2]);assert m['metadata_problems']


def test_rich_report_keeps_version_proof_and_excludes_draft_from_progress():
 from app.reports import build_report,render_html,render_markdown,render_docx
 from app.engine import annotate_items
 from io import BytesIO
 a=event();b=event('b',revision=2,time='2026-11-08T16:00',progress=65);draft=event('c',day='2026-11-09',revision=3,progress=100,state='초안')
 for e in [a,b,draft]:e['fields']['overview']['value']='사업 개요 원문'
 item=annotate_items([project_latest(merge_candidates([{'candidates':[candidate(e) for e in [a,b,draft]]}])[0])])[0]
 r=build_report({'title':'검증','predecessor':'전임','successor':'후임'},{'id':'r','hash':'h','payload':{'items':[item],'generated_at':'2026-11-09','model':'test'},'confirmation':{'created':'2026-11-09T00:00:00+00:00'},'warnings':[]},lambda bid:{})
 t=r['tasks'][0];assert len(t['timeline'])==2 and len(t['version_history'])==3 and t['progress']==65
 html=render_html(r);assert '최신본 채택·구판 및 초안 제외 근거' in html and '현재 기준본:</b> b.hwpx' in html and '현재 기준에서 제외' in html
 md=render_markdown(r);assert '본문 판본 선택 근거' in md and '현재 기준본' in md
 with zipfile.ZipFile(BytesIO(render_docx(r))) as z:assert '현재 기준본: b.hwpx'.encode() in z.read('word/document.xml')
