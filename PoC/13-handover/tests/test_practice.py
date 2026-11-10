import copy,io,zipfile
from test_flow import client,new_case,generate
from test_reports import confirm
from app.flow_demo import WORKS
from app.practice_demo import PROFILES,resources as original_resources
from app.practice_report import resources
from app.reports import build_report,render_html
from app.timeline import reported_progress


def test_practical_report_complete_and_shared_resources(client):
 c=client;base=new_case(c);archive=c.get('/samples/practice.zip');assert archive.status_code==200
 with zipfile.ZipFile(io.BytesIO(archive.content)) as z:assert len(z.namelist())==15
 assert c.post(base+'/practice-demo').status_code==200
 rev=generate(c,base);assert len(rev['payload']['items'])==5
 for index,w in enumerate(WORKS):
  item=next(i for i in rev['payload']['items'] if i['fields']['title']['value']==w['title'])
  for k,v in (PROFILES[index]|original_resources(index)).items():assert item['fields'][k]['value']==v,(w['title'],k,item['fields'][k]['value'])
  assert len(item['timeline'])==(3 if index<3 else 1)
  assert reported_progress(item)==(w['reports'][-1][2] if index<3 else 20)
 assert next(c for c in rev['payload']['coverage'] if c['path'].startswith('08_'))['status']=='REFERENCE_ONLY'
 items=rev['payload']['items'];target=next(i for i in items if i['fields']['title']['value']==WORKS[3]['title']);source=next(i for i in items if i['fields']['title']['value']=='예약포털 접근성 보완')
 resp=c.post(base+f'/revisions/{rev["id"]}/match',json={'expected_hash':rev['hash'],'target_id':target['id'],'source_id':source['id'],'owner':'디지털지원팀','reason':'09_업무동일성_담당확인.txt 대조: 동일 전체 사업 범위·보고 진행률·담당 확인'})
 assert resp.status_code==200,resp.text
 rev=resp.json();assert reported_progress(next(i for i in rev['payload']['items'] if i['id']==target['id']))==75
 assert rev['readiness']['missing_fields']==0
 confirm(c,base,rev);confirmed=c.get(base+'/revisions/confirmed').json()
 r=build_report(c.get(base).json(),confirmed,lambda bid:c.get(base+'/blocks/'+bid).json());d=resources(r)
 assert len(d['budgets'])==5 and len(d['contacts'])==11
 assert d['totals']=={'편성액':358000000,'집행액':212000000,'지급예정액':33000000,'가용잔액':113000000}
 assert not d['notes']
 html=render_html(r)
 for needle in ['class="gantt-wrap"','공통 회의','358,000,000원','미승인','실무 처리 순서','A07','D01','example.invalid','관계자 연락망']:assert needle in html
 assert html.index('class="gantt-wrap"')<html.index('id="task-1"')
 # Exact same ID with conflicting amounts cannot silently become a portfolio total.
 bad=copy.deepcopy(r);bad['tasks'][0]['values']['budget']=bad['tasks'][0]['values']['budget'].replace('2,000,000원','3,000,000원')
 assert resources(bad)['totals'] is None
 for fmt in ['html','md','docx']:
  response=c.get(base+f'/exports/{rev["id"]}.{fmt}');assert response.status_code==200
  if fmt=='docx':
   with zipfile.ZipFile(io.BytesIO(response.content)) as z:text=z.read('word/document.xml').decode()
  else:text=response.text
  for needle in ['358,000,000원','공통','실무 처리 순서']:assert needle in text


def test_declared_profile_uses_exact_labels_and_does_not_mask_unlabelled_text():
 from app.engine import structured_profile
 def b(n,text):return {'id':str(n),'doc_id':'d','parse_id':'p','text':text}
 blocks=[b(0,'합성자료 · 예시'),b(1,'문서역할: 업무기준정보'),b(2,'보고일: 2026-11-09'),b(3,'업무: 시험 업무'),b(4,'성과 지표: 지표: 접수 | 실적: 1 | 목표: 2 | 단위: 건')]
 result=structured_profile({'id':'d'},blocks)
 assert result['mode']=='structured' and result['status']=='EXTRACTED'
 assert result['candidates'][0]['fields']['performance']['value']=='지표: 접수 | 실적: 1 | 목표: 2 | 단위: 건'
 assert not result['candidates'][0]['fields']['objectives']['value']
 assert structured_profile({'id':'d'},blocks+[b(5,'별도로 중요한 업무가 서술되어 있습니다.')]) is None
 assert structured_profile({'id':'d'},[b(3,'업무: 시험 업무')]) is None


def test_successor_can_find_new_budget_and_operational_fields_without_model():
 from app.questions import local_select
 facts=[{'id':'F1','title':'생활문화 공모사업 추진','field':'status'}, {'id':'F2','title':'생활문화 공모사업 추진','field':'budget'},{'id':'F3','title':'생활문화 공모사업 추진','field':'operating_steps'}]
 assert local_select('공모사업 예산은?',facts)==['F2']
 assert local_select('공모사업 처리 절차는?',facts)==['F3']
