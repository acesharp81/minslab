import io,json,zipfile
from fastapi.testclient import TestClient
from app.main import create_app
from app.timeline import reported_progress
from test_flow import generate


def setup(c):
 r=c.post('/api/inheritance-demo');assert r.status_code==200,r.text
 data=r.json();base='/api/cases/'+data['target_case_id'];source='/api/cases/'+data['source_case_id']
 options=c.get(base+'/inheritance-options',headers={'X-Employee':'employee2'}).json();assert len(options)==1
 return base,source,{'basis_case_id':options[0]['id'],'basis_revision_id':options[0]['revision_id']}


def test_continuation_evidence_exports_and_source_immutability(tmp_path):
 with TestClient(create_app(tmp_path)) as c:
  base,source,body=setup(c);original=c.get(source+'/revisions/confirmed').json()
  c.headers['X-Employee']='employee2'
  rev=generate(c,base,body)
  assert rev['payload']['inheritance']['counts']=={'updated':1,'carried':1,'new':1,'review':0}
  assert {i['fields']['title']['value']:reported_progress(i) for i in rev['payload']['items']}=={'지역생활서비스 운영':80,'공공시설 정기점검':30,'겨울철 취약계층 지원':10}
  assert len(rev['payload']['document_ids'])==4
  for item in rev['payload']['items']:
   for field in item['fields'].values():
    for ref in field['evidence']:
     result=c.get(base+'/blocks/'+ref['block_id']);assert result.status_code==200
     assert ref['quote'] in result.json()['text']
  r=c.post(base+'/revisions/'+rev['id']+'/confirm',json={'expected_hash':rev['hash'],'acknowledge_warnings':True});assert r.status_code==200,r.text
  c.headers['X-Employee']='employee3'
  html=c.get(base+'/reports/confirmed');assert html.status_code==200
  assert '이전 인계 보고서 기반' in html.text and '26.1.10.' in html.text
  assert '직원 1 → 직원 2' in html.text and '직원 2 → 직원 3' in html.text
  assert '원본 자료 색인' not in html.text and '인계 범위' not in html.text
  assert 'source-dialog' in html.text and 'showModal()' in html.text
  assert "script-src 'sha256-" in html.headers['content-security-policy']
  assert '이전 인계 보고서 기반' in c.get(base+'/exports/confirmed.md').text
  doc=c.get(base+'/exports/confirmed.docx');assert doc.status_code==200
  with zipfile.ZipFile(io.BytesIO(doc.content)) as z:assert '인수인계 이력' in z.read('word/document.xml').decode()
  assert c.get(source+'/revisions/confirmed').status_code==403 # scoped copies, no old case access
  assert c.post(base+'/accept',json={'expected_hash':rev['hash']}).status_code==200
  c.headers['X-Employee']='employee2'
  assert c.get(source+'/revisions/confirmed').json()==original
  # Disabling the option excludes copied old documents, and preserves the confirmed report.
  fresh=generate(c,base,{'request_id':'without-basis'})
  assert len(fresh['payload']['items'])==2 and 'inheritance' not in fresh['payload']
  assert c.get(base+'/revisions/confirmed').json()['id']==rev['id']


def test_basis_authorization_stale_selection_and_multihop(tmp_path):
 with TestClient(create_app(tmp_path)) as c:
  base,source,body=setup(c)
  other=c.post('/api/cases',json={'title':'unauthorized','predecessor_id':'employee4','successor_id':'employee1'}).json()['id']
  assert not c.get('/api/cases/'+other+'/inheritance-options').json()
  assert c.post('/api/cases/'+other+'/generate',json=body).status_code==409
  assert c.post(base+'/generate',json=body|{'basis_revision_id':'stale'}).status_code==409
  assert c.post(base+'/generate',json={'basis_case_id':body['basis_case_id']}).status_code==422
  rev=generate(c,base,body);assert c.post(base+'/revisions/'+rev['id']+'/confirm',json={'expected_hash':rev['hash'],'acknowledge_warnings':True}).status_code==200
  assert c.post(base+'/accept',json={'expected_hash':rev['hash']},headers={'X-Employee':'employee3'}).status_code==200
  next_id=c.post('/api/cases',json={'title':'next','predecessor_id':'employee3','successor_id':'employee4'}).json()['id']
  next_base='/api/cases/'+next_id
  options=c.get(next_base+'/inheritance-options').json();option=next(o for o in options if o['id']==base.rsplit('/',1)[1])
  following=generate(c,next_base,{'basis_case_id':option['id'],'basis_revision_id':option['revision_id']})
  assert len(following['payload']['handover_chain'])==2 and len(following['payload']['items'])==3
  assert c.post(next_base+'/revisions/'+following['id']+'/confirm',json={'expected_hash':following['hash'],'acknowledge_warnings':True}).status_code==200


def test_demo_sets_people_numbering_and_no_automatic_paid_call(tmp_path):
 with TestClient(create_app(tmp_path)) as c:
  for kind,title in [('practice','4개 업무 복합 처리 시연'),('versions','파일명, 버전 혼선 시연'),('inheritance','업무연결 시연')]:
   for n in (1,2):
    r=c.post('/api/demo-sets',headers={'X-Employee':'employee4'},json={'kind':kind,'predecessor_id':'employee4','successor_id':'employee2'})
    assert r.status_code==201,r.text
    base='/api/cases/'+r.json()['target_case_id'];d=c.get(base).json()
    assert d['title']==f'{title} ({n})' and d['predecessor_id']=='employee4' and d['successor_id']=='employee2'
    assert d['documents'] and not d['jobs']
    if kind=='inheritance':
     option=next(o for o in c.get(base+'/inheritance-options').json() if o['id']==r.json()['source_case_id'])
     assert option['successor']=='직원 4' and option['predecessor']=='직원 1'
  assert c.post('/api/demo-sets',json={'kind':'practice','predecessor_id':'employee1','successor_id':'employee1'}).status_code==422


def test_old_update_cannot_overwrite_baseline_and_manual_fields_survive(tmp_path,monkeypatch):
 # Reconfirm before the dated fixture update; wall-clock dates must not change this contract.
 monkeypatch.setattr("app.main.now", lambda: "2026-11-10T00:00:00+00:00")
 with TestClient(create_app(tmp_path)) as c:
  base,source,body=setup(c)
  accepted=c.get(source+'/revisions/confirmed').json();item=next(i for i in accepted['payload']['items'] if i['fields']['title']['value']=='지역생활서비스 운영')
  # Preserve an explicitly reviewed operational note when the update does not repeat it.
  edited=c.patch(source+'/revisions/'+accepted['id']+'/items/'+item['id'],json={'expected_hash':accepted['hash'],'fields':{'document_locations':'기관 공유함 / 운영 / 원본'},'reason':'원문 보관 위치 확인'}).json()
  assert c.post(source+'/revisions/'+edited['id']+'/confirm',json={'expected_hash':edited['hash'],'acknowledge_warnings':True}).status_code==200
  assert c.post(source+'/accept',json={'expected_hash':edited['hash']},headers={'X-Employee':'employee2'}).status_code==200
  rev=generate(c,base,body|{'basis_revision_id':edited['id']});new=next(i for i in rev['payload']['items'] if i['fields']['title']['value']=='지역생활서비스 운영')
  assert new['fields']['document_locations']['value']=='기관 공유함 / 운영 / 원본'
  assert new['fields']['document_locations']['provenance']=='HUMAN_ENTERED'
  assert new['fields']['status']['value']=='8개 기관 협약 체결 완료'
  assert new['fields']['status']['previous']['value']==item['fields']['status']['value']
  # An old progress report cannot replace the accepted state simply by being uploaded later.
  other=c.post('/api/cases',json={'title':'old update','predecessor_id':'employee2','successor_id':'employee3'}).json()['id'];target='/api/cases/'+other
  text='업무: 지역생활서비스 운영\n담당: 직원 2\n보고일: 2025-12-01\n사업관리번호: CONT-A\n전체 진행률: 99%\n현재 상태: 완료\n기한: 2025-12-31\n다음 행동: 없음'
  assert c.post(target+'/documents',files={'file':('old.txt',text.encode())}).status_code==200
  old=generate(c,target,body|{'basis_revision_id':edited['id']});preserved=next(i for i in old['payload']['items'] if i['fields']['title']['value']=='지역생활서비스 운영')
  assert reported_progress(preserved)==20
  assert preserved['fields']['status']['value']==item['fields']['status']['value']


def test_demo_image_analysis_only_explicit_manual_opt_in(tmp_path,monkeypatch):
 from pathlib import Path
 import zipfile
 from app.vision import Vision
 calls=[]
 monkeypatch.setattr(Vision,'available',property(lambda self:True))
 def fake(self,picture):
  calls.append(picture['sha'])
  return {'text':'합성 그림 검증: 확인 완료 5건','cached':True,'model':'gpt-5.4'}
 monkeypatch.setattr(Vision,'transcribe',fake)
 with TestClient(create_app(tmp_path)) as c:
  base,source,body=setup(c)
  assert c.get(base).json()['demo_image_manual_only']
  assert not calls
  root=Path(__file__).resolve().parents[1]
  target='/api/cases/'+c.post('/api/cases',json={'title':'downloaded demo'}).json()['id']
  with zipfile.ZipFile(root/'release/public/01_최신본_먼저등록.zip') as z:
   name=next(n for n in z.namelist() if n.endswith('.hwpx'));data=z.read(name)
  assert c.post(target+'/documents',files={'file':('renamed.hwpx',data)}).status_code==200
  assert c.get(target).json()['demo_image_manual_only']
  generate(c,target)
  assert not calls
  rev=generate(c,target,{'image_consent':True})
  assert len(calls)==1
  assert sum(len(i.get('image_reviews',[])) for i in rev['payload']['items'])==1
