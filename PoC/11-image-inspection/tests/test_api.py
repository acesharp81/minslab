import io,time
import pytest
from fastapi.testclient import TestClient
from PIL import Image
from app.config import Settings
from app.main import create_app
from app.rules import PACK

@pytest.fixture
def client(tmp_path):
    s=Settings({'DATA_DIR':str(tmp_path),'ADMIN_PASSWORD':'admin-test','REVIEWER_PASSWORD':'review-test','SESSION_SECRET':'test-secret','EXTERNAL_API_ENABLED':'false','PIXEL_TEXT_ENABLED':'false','SHARED_BUDGET_HTTP':'false','USAGE_GATEWAY_URL':'','SHARED_BUDGET_DATABASE_URL':'','OPENROUTER_API_KEY':'','OPENROUTER_GATEWAY_URL':''})
    with TestClient(create_app(s)) as c:yield c

def login(c,role='admin'):
    assert c.post('/api/login',json={'role':role,'password':'admin-test' if role=='admin' else 'review-test'}).status_code==200


def test_quality_plan_is_read_only_version_scoped_and_execution_is_admin_only(client,monkeypatch):
    from test_quality_recheck import saved
    assert client.get('/api/jobs/missing/runs/old/quality-plan').status_code==401
    login(client);job=client.post('/api/demo').json();engine=client.app.state.engine
    original=engine.store.get(job['id']);run=saved()
    run.update(id='old',created_at=original['created_at'],scope='FULL_IMAGE',results=[],reviews=[],analysis=[])
    from app.rules import placeholder
    run['results']=[{**placeholder('H-01-a','PASS','기존 근거 보존'),'id':'keep'}]
    run['reviews']=[{'finding_id':'keep','status':'REVIEW','reason':'사람 검토 기록'}]
    run['options'].update(mode='live',quality_recheck=False,recheck_object_ids=[])
    original['runs']=[run];engine.store.save(original)
    before=engine.store.get(job['id'])
    path=f'/api/jobs/{job["id"]}/runs/old/quality-plan'
    plan=client.get(path).json();assert plan['recommended_ids']==['hand','sign']
    assert engine.store.get(job['id'])==before
    assert client.get(path.replace('/old/','/missing/')).status_code==404
    payload=dict(mode='live',consent=True,quality_recheck=True,reuse_observation_run_id='old',recheck_object_ids=['hand'])
    client.post('/api/logout');login(client,'reviewer')
    assert client.get(path).status_code==200
    assert client.post(f'/api/jobs/{job["id"]}/runs',json=payload).status_code==403
    client.post('/api/logout');login(client)
    engine.s.values.update(EXTERNAL_API_ENABLED='true',OPENAI_API_KEY='fake-test-only')
    queued=[];monkeypatch.setattr(engine.pool,'submit',lambda *a:queued.append(a))
    invalid={**payload,'recheck_object_ids':['missing']}
    assert client.post(f'/api/jobs/{job["id"]}/runs',json=invalid).status_code==409
    invalid={**payload,'recheck_object_ids':[]}
    assert client.post(f'/api/jobs/{job["id"]}/runs',json=invalid).status_code==400
    result=client.post(f'/api/jobs/{job["id"]}/runs',json=payload)
    assert result.status_code==200 and len(queued)==1
    latest=engine.store.get(job['id'])['runs'][-1]
    assert latest['quality_recheck_plan']['max_calls']==2
    assert latest['observation_reused_from']['run_id']=='old'
    assert set(latest['selected'])=={f'D-02-{c}' for c in 'cdefghi'}
    assert next(r for r in latest['results'] if r['id']=='keep')==run['results'][0]
    assert latest['reviews']==run['reviews']
    assert not latest['calls']  # Worker intentionally not executed; no provider call.


def test_history_summary_and_compact_view_keep_full_report_and_auth(client):
    assert client.get('/api/jobs/missing/versions').status_code==401
    login(client);j=client.post('/api/demo').json();store=client.app.state.engine.store
    saved=store.get(j['id']);run=dict(id='v1',created_at=saved['created_at'],options={'mode':'live','vision_model':'gpt-5.4','analysis_model':'gpt-5.4-mini'},scope='FULL_IMAGE',observation={'objects':[]},results=[],reviews=[],analysis=[],selected=[],rule_pack=PACK)
    saved['runs']=[run,{**run,'id':'v2'}];store.save(saved)
    client.app.state.engine.store.jobs=lambda:(_ for _ in ()).throw(AssertionError('List API must not load full histories'))
    listing=client.get('/api/jobs').json();assert listing[0]['run_count']==2 and 'runs' not in listing[0]
    versions=client.get(f'/api/jobs/{j["id"]}/versions').json();assert [v['id'] for v in versions]==['v1','v2']
    latest=client.get(f'/api/jobs/{j["id"]}?view=latest').json();assert [r['id'] for r in latest['runs']]==['v2']
    old=client.get(f'/api/jobs/{j["id"]}?view=latest&run_id=v1').json();assert old['runs'][0]['id']=='v1'
    assert len(client.get(f'/api/jobs/{j["id"]}').json()['runs'])==2
    assert len(client.get(f'/api/jobs/{j["id"]}/report').json()['runs'])==2
    assert client.get(f'/api/jobs/{j["id"]}?view=latest&run_id=missing').status_code==404

def test_snapshot_reference_image_is_authenticated_and_run_scoped(client):
    login(client)
    job=client.post('/api/demo').json()
    engine=client.app.state.engine;store=engine.store
    saved=store.get(job['id'])
    directory=store.path.parent/'references';directory.mkdir(exist_ok=True)
    (directory/'snapshot.png').write_bytes(b'test-image')
    saved['runs']=[{'id':'test-run','reference_snapshot':[{'id':'test-ref','image_file':'snapshot.png'}]}]
    store.save(saved)
    url=f"/api/jobs/{job['id']}/runs/test-run/references/test-ref/image"
    assert client.get(url).content==b'test-image'
    assert client.get(url.replace('test-run','other-run')).status_code==404
    assert store.references()==[]
    client.post('/api/logout')
    assert client.get(url).status_code==401

def wait(c,jid):
    for _ in range(120):
        j=c.get('/api/jobs/'+jid).json()
        if j['state'] not in ('RUNNING','QUEUED'):return j
        time.sleep(.01)
    raise AssertionError('job timed out')

def test_auth_csrf_prefix_and_secret_nonexposure(client):
    assert client.get('/api/jobs').status_code==401
    assert client.get('/poc/image-inspection/health').json()['steps']==156
    assert client.get('/poc/image-inspection/').status_code==200
    assert client.get('/.env').status_code==404
    assert client.post('/api/login',headers={'Origin':'https://evil.test'},json={'role':'admin','password':'admin-test'}).status_code==403
    assert 'admin-test' not in client.get('/api/config').text
    login(client,'reviewer');assert client.post('/api/usage/sync').status_code==403

@pytest.mark.parametrize('prefix',['','/poc/image-inspection'])
def test_logout_revokes_session_and_clears_cookie_at_login_path(client,prefix):
    response=client.post(prefix+'/api/login',json={'role':'reviewer','password':'review-test'})
    assert response.status_code==200
    token=response.cookies['poc11_session']
    assert client.get(prefix+'/api/jobs').status_code==200
    response=client.post(prefix+'/api/logout')
    assert response.status_code==200
    assert not client.cookies.get('poc11_session')
    assert client.get(prefix+'/api/config').json()['role'] is None
    assert client.get(prefix+'/api/jobs').status_code==401
    assert client.get(prefix+'/api/jobs',headers={'Cookie':'poc11_session='+token}).status_code==401

@pytest.mark.parametrize('options',[
    {'mode':'live','consent':True},
    {'mode':'live','consent':True,'force':True,'reuse_observation_run_id':'old'},
    {'mode':'live','consent':True,'rule_ids':['H-04-a']},
    {'mode':'live','consent':True,'crop_id':'crop-test'},
    {'mode':'live','consent':True,'reuse_observation_run_id':'old','recheck_object_ids':['object-1']},
    {'mode':'mock'},
])
def test_reviewer_cannot_submit_any_analysis(client,monkeypatch,options):
    login(client)
    job=client.post('/api/demo').json()
    login(client,'reviewer')
    submitted=[]
    monkeypatch.setattr(client.app.state.engine,'submit',lambda *args:submitted.append(args))
    response=client.post(f'/api/jobs/{job["id"]}/runs',json=options)
    assert response.status_code==403
    assert not submitted
    assert client.get(f'/api/jobs/{job["id"]}').json()['runs']==[]

def test_reviewer_can_read_export_and_record_review_after_admin_analysis(client):
    login(client)
    job=client.post('/api/demo').json();jid=job['id']
    assert client.post(f'/api/jobs/{jid}/runs',json={'mode':'mock'}).status_code==200
    job=wait(client,jid)
    login(client,'reviewer')
    assert client.get('/api/jobs').status_code==200
    assert client.get(f'/api/jobs/{jid}/image').status_code==200
    assert client.get(f'/api/jobs/{jid}').status_code==200
    finding=job['runs'][-1]['results'][0]
    response=client.post(f'/api/jobs/{jid}/reviews',json={'finding_id':finding['id'],'status':'REVIEW','reason':'검토자 권한으로 근거를 기록합니다.'})
    assert response.status_code==200
    assert response.json()['runs'][-1]['reviews'][-1]['reviewer']=='reviewer'
    assert client.get(f'/api/jobs/{jid}/report').status_code==200

def test_mock_full_flow_reviews_rerun_export_cache(client):
    login(client);job=client.post('/api/demo').json();jid=job['id']
    assert client.post(f'/api/jobs/{jid}/runs',json={'mode':'mock'}).status_code==200
    job=wait(client,jid);run=job['runs'][-1]
    assert len(job['parents'])==25 and len(run['results'])==157
    assert run['calls']==[]
    hand=next(r for r in run['results'] if r['rule_id']=='D-02-e')
    r=client.post(f'/api/jobs/{jid}/reviews',json={'finding_id':hand['id'],'status':'REVIEW','reason':'합성 시연 결과로 실제 검수 필요'})
    assert r.status_code==200 and len(r.json()['runs'][-1]['reviews'])==1
    crop=client.post(f'/api/jobs/{jid}/crops',json={'cell_ids':['R07C03']}).json()
    assert 'R06C02' in crop['context_cells'] and 'R08C04' in crop['context_cells']
    assert client.get(f'/api/jobs/{jid}/crops/{crop["id"]}').status_code==200
    assert client.post(f'/api/jobs/{jid}/runs',json={'mode':'mock'}).status_code==200
    cached=client.get('/api/jobs/'+jid).json()['runs'][-1]
    assert cached['reused_from'] and cached['reviews']==[] and cached['calls']==[]
    assert client.post(f'/api/jobs/{jid}/runs',json={'mode':'blocked','rule_ids':['D-02-e'],'force':True}).status_code==200
    job=wait(client,jid);assert len(job['runs'])==3
    assert all(r['status']=='NOT_RUN' for r in job['runs'][-1]['results'] if r['rule_id']=='D-02-e')
    exported=client.get(f'/api/jobs/{jid}/report');assert exported.status_code==200 and len(exported.json()['parents'])==25
    assert len(exported.json()['runs'][0]['reviews'])==1
    assert client.delete('/api/jobs/'+jid).status_code==200
    assert client.get('/api/jobs/'+jid).status_code==404

def test_upload_errors_live_consent_and_no_fake_pass(client):
    login(client)
    assert client.post('/api/jobs',files={'file':('x.png',b'not an image','image/png')}).status_code==400
    b=io.BytesIO();Image.new('RGB',(72,100),'white').save(b,format='PNG')
    j=client.post('/api/jobs',files={'file':('x.png',b.getvalue(),'image/png')},data={'title':'test'}).json()
    assert client.post('/api/jobs/'+j['id']+'/runs',json={'mode':'live','consent':False}).status_code==400
    client.post('/api/jobs/'+j['id']+'/runs',json={'mode':'mock'})
    out=wait(client,j['id']);assert {r['status'] for r in out['runs'][0]['results']}=={'REVIEW'}

def test_reference_approval_requires_image_for_pattern(client):
    login(client)
    body=dict(name='공식 도안',kind='official-symbols',issuer='테스트 기관',official_url='https://example.org/reference',content='테스트 승인 자료 예시',parent_ids=['H-04'],version='test-1')
    ref=client.post('/api/references',json=body).json()
    assert client.post('/api/references/'+ref['id']+'/approve').status_code==400
    b=io.BytesIO();Image.new('RGB',(100,100),'white').save(b,format='PNG')
    assert client.post('/api/references/'+ref['id']+'/image',files={'file':('x.png',b.getvalue(),'image/png')}).status_code==200
    assert client.post('/api/references/'+ref['id']+'/approve').json()['status']=='APPROVED'
    assert client.post('/api/references/'+ref['id']+'/image',files={'file':('x.png',b.getvalue(),'image/png')}).status_code==409

def test_empty_analysis_is_error_and_call_failures_stop_spending(client):
    from app.providers import ProviderError
    login(client);engine=client.app.state.engine;calls=[]
    engine.s.values['AUTO_VERIFY_MAX_CALLS']='0'
    def fake(model,prompt,images=(),workload='image-inspection'):
        calls.append(workload)
        if workload=='checklist-analysis':return {'results':[]},{'event_id':'fake-analysis','model':model}
        return {'summary':'샘플', 'context':'시연','limitations':'없음','objects':[dict(id='text1',label='제목',description='SAMPLE',text='SAMPLE',visual_concerns='',quality='CLEAR',cell_ids=['R01C01'])]}, {'event_id':'fake-vision','model':model}
    engine.provider.call=fake
    job=client.post('/api/demo').json()
    engine.submit(job['id'],dict(mode='live',vision_model='gpt-6.1-sol',analysis_model='solar-pro4',rule_ids=['D-02-l'],force=True,consent=True,crop_id=None))
    j=wait(client,job['id']);assert j['state']=='COMPLETED_WITH_ERRORS' and j['runs'][-1]['analysis'][0]['error']
    assert calls==['image-observation','checklist-analysis']
    calls.clear()
    def failed(*args,**kwargs):calls.append('call');raise ProviderError('API 네트워크 오류')
    engine.provider.call=failed
    engine.submit(job['id'],dict(mode='live',vision_model='gpt-6.1-sol',analysis_model='solar-pro4',rule_ids=[],force=True,consent=True,crop_id=None))
    j=wait(client,job['id']);assert len(calls)==1 and j['state']=='COMPLETED_WITH_ERRORS'
    assert all(r['status']=='ERROR' for r in j['runs'][-1]['results'])


def test_parent_admin_signature_is_bound_to_method_and_path(client):
    import hashlib,hmac,time
    stamp=str(int(time.time()));path='/poc/image-inspection/api/jobs'
    signature=hmac.new(b'test-secret',f'{stamp}:GET:{path}'.encode(),hashlib.sha256).hexdigest()
    assert client.get(path,headers={'x-inspection-admin':f'{stamp}:{signature}'}).status_code==200
    assert client.get('/poc/image-inspection/api/usage',headers={'x-inspection-admin':f'{stamp}:{signature}'}).status_code==401

def test_remaining_endpoint_requires_login_and_omits_event_details(client,monkeypatch):
    assert client.get('/api/usage/remaining').status_code==401
    login(client,'reviewer')
    monkeypatch.setattr(client.app.state.engine.usage,'budget_snapshot',lambda:{'budget':{'remaining_usd':5,'limit_usd':8,'expires_at':None}})
    response=client.get('/api/usage/remaining')
    assert response.status_code==200
    body=response.json()
    assert len(body['models'])==6 and next(m for m in body['models'] if m['id']=='openai-shared')['remaining']==5
    assert 'events' not in body and 'grant_id' not in response.text


def test_default_run_is_gpt54_read_and_mini_analysis(client):
    from app.main import RunInput
    defaults=RunInput()
    assert defaults.mode=='live'
    assert defaults.vision_model=='gpt-5.4'
    assert defaults.analysis_model=='gpt-5.4-mini' and not defaults.consent
    login(client);job=client.post('/api/demo').json()
    assert client.post('/api/jobs/'+job['id']+'/runs',json={}).status_code==400
    assert client.get('/api/jobs/'+job['id']).json()['runs']==[]


def test_screen_view_defers_snapshots_but_keeps_findings_and_exact_version(client):
    assert client.get('/api/jobs/missing?view=screen').status_code==401
    assert client.get('/api/jobs/missing/runs/old/details').status_code==401
    login(client);j=client.post('/api/demo').json();store=client.app.state.store
    saved=store.get(j['id']);run=dict(id='old',created_at=saved['created_at'],options={'mode':'live'},
        results=[],reviews=[],analysis=[],selected=[],rule_pack=PACK,
        observation={'objects':[{'id':'original-observation'}]},calls=[{'usage':{'input_tokens':42}}],
        reference_snapshot=[{'id':'ref','name':'원래 기준','content':'original '+('large '*3000)}])
    saved['runs']=[run,{**run,'id':'new','reference_snapshot':[{'id':'ref','name':'새 기준','content':'new'}]}];store.save(saved)
    # Reviewer also has read access; permissions for running analyses remain unchanged.
    login(client,'reviewer')
    url=f'/api/jobs/{j["id"]}'
    response=client.get(url+'?view=screen&run_id=old',headers={'Accept-Encoding':'gzip'})
    assert response.headers['content-encoding']=='gzip' and 'accept-encoding' in response.headers['vary'].lower()
    assert response.headers['cache-control']=='no-store'
    screen=response.json();r=screen['runs'][0]
    assert r['id']=='old' and r['details_deferred']
    assert r['reference_snapshot']==[{'id':'ref','name':'원래 기준'}]
    assert r['observation']==run['observation'] and r['calls']==run['calls']
    assert r['results']==run['results'] and r['reviews']==run['reviews']
    assert all(set(step)<= {'rule_id','objective','reference_requirements'} for step in r['rule_pack']['steps'])
    full=client.get(url+'?view=latest&run_id=old').json()
    assert screen['checklist_report']==full['checklist_report'] and screen['parents']==full['parents']
    detail=client.get(url+'/runs/old/details').json()
    assert detail=={'run_id':'old','rule_pack':PACK,'reference_snapshot':run['reference_snapshot']}
    assert client.get(url+'/runs/missing/details').status_code==404
    assert client.get(url+'?view=screen&run_id=missing').status_code==404
    assert client.get(url+'/report').json()['runs']==saved['runs']
    assert store.get(j['id'])==saved


def test_compression_preserves_original_image_and_identity_clients(client):
    login(client);j=client.post('/api/demo').json();url=f'/api/jobs/{j["id"]}'
    response=client.get(url+'?view=screen',headers={'Accept-Encoding':'identity'})
    assert response.status_code==200 and 'content-encoding' not in response.headers
    image=client.get(url+'/image',headers={'Accept-Encoding':'gzip'})
    assert 'content-encoding' not in image.headers
    assert image.content==(client.app.state.settings.data/j['id']/'image.png').read_bytes()


@pytest.mark.parametrize('prefix',['','/poc/image-inspection'])
def test_image_revalidation_preserves_pixels_checks_auth_and_detects_change(client,prefix):
    login(client);j=client.post('/api/demo').json();url=prefix+f'/api/jobs/{j["id"]}/image'
    first=client.get(url);tag=first.headers['etag']
    assert first.status_code==200 and first.headers['cache-control']=='private, no-cache'
    assert 'cookie' in first.headers['vary'].lower()
    assert first.content==(client.app.state.settings.data/j['id']/'image.png').read_bytes()
    for conditional in (tag,tag.removeprefix('W/'),'"old", '+tag):
        cached=client.get(url,headers={'If-None-Match':conditional})
        assert cached.status_code==304 and cached.content==b'' and cached.headers['etag']==tag
    # A changed original can never be masked by its old ETag.
    path=client.app.state.settings.data/j['id']/'image.png'
    im=Image.new('RGB',(31,29),'blue');im.save(path)
    changed=client.get(url,headers={'If-None-Match':tag})
    assert changed.status_code==200 and changed.headers['etag']!=tag and changed.content==path.read_bytes()
    client.post('/api/logout')
    unauthorized=client.get(url,headers={'If-None-Match':changed.headers['etag']})
    assert unauthorized.status_code==401 and unauthorized.headers['cache-control']=='no-store'
    login(client,'reviewer')
    assert client.get(url,headers={'If-None-Match':changed.headers['etag']}).status_code==304
    login(client);assert client.delete(prefix+f'/api/jobs/{j["id"]}').status_code==200
    assert client.get(url,headers={'If-None-Match':'*'}).status_code==404


@pytest.mark.parametrize('path',['/','/assets/app.js','/assets/style.css','/api/rules'])
def test_startup_text_is_compressed_without_changing_content(client,path):
    compressed=client.get(path,headers={'Accept-Encoding':'gzip'})
    plain=client.get(path,headers={'Accept-Encoding':'identity'})
    assert compressed.status_code==plain.status_code==200
    assert compressed.headers['content-encoding']=='gzip'
    assert compressed.content==plain.content
    if path.startswith('/assets/'):
        cached=client.get(path,headers={'If-None-Match':compressed.headers['etag']})
        assert cached.status_code==304 and cached.content==b''
    else:
        assert compressed.headers['cache-control']=='no-store'
