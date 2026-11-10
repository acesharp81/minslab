import io,json,zipfile
from pathlib import Path
from fastapi.testclient import TestClient
from app.main import create_app
from app.timeline import reported_progress
from app.vision import postprocess,images,Vision
from app.store import Store,digest
from test_flow import generate,new_case
ROOT=Path(__file__).resolve().parents[1]

def upload(c,base,name):
 r=c.post(base+'/documents',files={'file':(name,(ROOT/'release/public'/name).read_bytes())});assert r.status_code==200,r.text

def test_same_names_all_versions_reverse_and_stale_confirmation(tmp_path):
 with TestClient(create_app(tmp_path)) as c:
  base=new_case(c)
  upload(c,base,'01_최신본_먼저등록.zip');first=generate(c,base)
  assert len(first['payload']['items'])==4
  assert c.post(base+f"/revisions/{first['id']}/confirm",json={'expected_hash':first['hash'],'acknowledge_warnings':True}).status_code==200
  upload(c,base,'02_구판_나중등록.zip')
  assert c.post(base+f"/revisions/{first['id']}/confirm",json={'expected_hash':first['hash'],'acknowledge_warnings':True}).status_code==409
  upload(c,base,'03_미승인초안_마지막등록.zip');rev=generate(c,base)
  assert len(rev['payload']['document_ids'])==12
  assert sorted(reported_progress(i) for i in rev['payload']['items'])==[55,65,70,90]
  assert all(len(i['timeline'])==3 for i in rev['payload']['items'])
  assert c.get(base+'/revisions/confirmed').json()['id']==first['id']
  # Opposite ingestion order produces exactly the same content decision.
  other=new_case(c)
  for name in ['03_미승인초안_마지막등록.zip','02_구판_나중등록.zip','01_최신본_먼저등록.zip']:upload(c,other,name)
  reverse=generate(c,other)
  assert sorted(reported_progress(i) for i in reverse['payload']['items'])==[55,65,70,90]

def test_employee_ring_ownership_accept_and_idempotency(tmp_path):
 with TestClient(create_app(tmp_path)) as c:
  assert len(c.post('/api/employee-demo').json()['created'])==6
  assert not c.post('/api/employee-demo').json()['created']
  for n in range(1,5):
   h={'X-Employee':f'employee{n}'};rows=c.get('/api/cases',headers=h).json()
   assert len(rows)==3
   assert sum(r['my_role']=='successor' for r in rows) in (1,2)
   assert sum(bool(r['accepted']) for r in rows)==1
  base='/api/cases/employee-ring-v1-2-active'
  assert c.get(base,headers={'X-Employee':'employee1'}).status_code==403
  assert c.post(base+'/generate',json={},headers={'X-Employee':'employee3','X-Role':'predecessor'}).status_code==403
  rev=c.get(base+'/revisions/confirmed',headers={'X-Employee':'employee3'}).json()
  assert c.post(base+'/accept',json={'expected_hash':rev['hash']},headers={'X-Employee':'employee2','X-Role':'successor'}).status_code==403
  assert c.post(base+'/accept',json={'expected_hash':rev['hash']},headers={'X-Employee':'employee3'}).status_code==200
  # Browser iframe/download uses the employee cookie too.
  c.cookies.set('handover_employee','employee1')
  assert c.get(base+'/revisions/confirmed').status_code==403

def test_image_postprocessing_only_selected_not_old_draft_or_ambiguous(tmp_path,monkeypatch):
 import app.vision as v
 with TestClient(create_app(tmp_path)) as c:
  base=new_case(c)
  for name in ['01_최신본_먼저등록.zip','02_구판_나중등록.zip','03_미승인초안_마지막등록.zip']:upload(c,base,name)
  rev=generate(c,base);store=c.app.state.store;docs=store.rows('SELECT * FROM documents WHERE case_id=?',(base.rsplit('/',1)[1],))
  calls=[];extracted=[];original=v.images
  class Fake:
   def transcribe(self,p):calls.append(p['sha']);return {'text':'확인 완료: 5건','cached':False}
  def spy(path,ext):extracted.append(path.name);return original(path,ext)
  monkeypatch.setattr(v,'images',spy)
  snap,notes=postprocess(store,Fake(),rev['payload']['items'],docs,base.rsplit('/',1)[1])
  selected={i['latest_document_id'] for i in rev['payload']['items']}
  assert set(extracted)=={d['sha'] for d in docs if d['id'] in selected}
  assert len(calls)==1 and len(snap)==1
  assert sum(len(i['image_reviews']) for i in rev['payload']['items'])==1
  for i in rev['payload']['items']:i.pop('latest_document_id')
  calls.clear();extracted.clear()
  _,notes=postprocess(store,Fake(),rev['payload']['items'],docs,base.rsplit('/',1)[1])
  assert not calls and not extracted and len(notes)==4

def test_paid_image_cache_durable_settlement_and_image_only_request(tmp_path,monkeypatch):
 from PIL import Image
 store=Store(tmp_path);v=Vision(store,{'key':'synthetic','url':'https://example.test/v1','gateway':'https://meter.test','meter_token':'synthetic'})
 events=[];requests=[]
 monkeypatch.setattr(v,'gateway',lambda path,body=None:events.append((path,body)) or {})
 class Response:
  status_code=200
  def json(self):return {'status':'completed','usage':{'input_tokens':100,'output_tokens':20},'output':[{'content':[{'type':'output_text','text':'그림 표: 5건'}]}]}
 def post(url,**kw):requests.append(kw['json']);return Response()
 monkeypatch.setattr('app.vision.httpx.post',post)
 out=io.BytesIO();Image.new('RGB',(100,100),'white').save(out,format='PNG');pic={'data':out.getvalue(),'sha':digest(out.getvalue())}
 assert not v.transcribe(pic)['cached'];assert v.transcribe(pic)['cached']
 assert len(requests)==1
 assert requests[0]['model']=='gpt-5.4' and all(x['type']=='input_image' for x in requests[0]['input'][0]['content'])
 assert [p for p,b in events]==['budget/reserve','budget/settle','usage-events']
 assert events[-1][1]['project']=='poc13-handover'

def test_many_work_grouping_atomic_history_and_stale_revision(tmp_path):
 with TestClient(create_app(tmp_path)) as c:
  base=new_case(c);upload(c,base,'grouping-samples.zip');rev=generate(c,base)
  assert len(rev['payload']['items'])==5
  members=[i for i in rev['payload']['items'] if any(e['work_code']=='GROUP-B' for e in i['timeline'])]
  assert len(members)==3
  groups=[{'item_ids':[i['id']],'title':i['fields']['title']['value'],'owner':i['fields']['owner']['value']} for i in rev['payload']['items'] if i not in members]
  groups.append({'item_ids':[i['id'] for i in members],'title':'문화시설 통합예약 접근성 개선','owner':'디지털지원팀'})
  url=base+f"/revisions/{rev['id']}/groups";body={'expected_hash':rev['hash'],'groups':groups}
  bad={**body,'groups':groups[:-1]};assert c.post(url,json=bad).status_code==422
  assert c.get(base+'/revisions/current').json()['id']==rev['id']
  assert c.post(url,json=body,headers={'X-Role':'successor'}).status_code==403
  r=c.post(url,json=body);assert r.status_code==200,r.text
  latest=r.json();assert len(latest['payload']['items'])==3
  item=next(i for i in latest['payload']['items'] if i['fields']['title']['value']=='문화시설 통합예약 접근성 개선')
  assert len(item['source_documents'])==3 and len(item['timeline'])==3 and len(item['match_history'])==2
  assert reported_progress(item)==75 and item['fields']['owner']['provenance']=='HUMAN_ENTERED'
  assert c.get(base+f"/revisions/{rev['id']}").json()['payload']==rev['payload']
  assert c.post(url,json=body).status_code==409
  assert len(c.get(base).json()['history'])==2

def test_budget_denial_never_sends_image_and_timeout_never_retries(tmp_path,monkeypatch):
 import pytest,httpx
 v=Vision(Store(tmp_path),{'key':'synthetic','url':'https://example.test/v1','gateway':'https://meter.test','meter_token':'synthetic'})
 sent=[];pic={'data':b'synthetic-image','sha':'synthetic-sha'}
 def deny(*args,**kwargs):raise ValueError('공유 한도 부족')
 monkeypatch.setattr(v,'gateway',deny)
 monkeypatch.setattr('app.vision.httpx.post',lambda *a,**kw:sent.append(kw))
 with pytest.raises(ValueError,match='공유 한도'):v.transcribe(pic)
 assert not sent
 monkeypatch.setattr(v,'gateway',lambda *a,**kw:{})
 def timeout(*a,**kw):sent.append(kw);raise httpx.ReadTimeout('synthetic')
 monkeypatch.setattr('app.vision.httpx.post',timeout)
 with pytest.raises(ValueError,match='자동 재호출'):v.transcribe(pic)
 with pytest.raises(ValueError,match='자동 재호출'):v.transcribe(pic)
 assert len(sent)==1
 row=v.store.one('SELECT * FROM vision_calls');assert json.loads(row['settlement'])['cost_usd'] is None and row['synced']==1
