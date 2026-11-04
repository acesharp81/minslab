import copy,hashlib,json
from pathlib import Path
from types import SimpleNamespace
import pytest
from app import precheck as p,verification
from app.config import Settings
from app.rules import PACK

ROOT=Path(__file__).resolve().parents[1]
CATALOG=json.loads((ROOT/'rules/precheck-library/catalog.json').read_text())

def reference(number=5):
    item=CATALOG['items'][number-1]
    return dict(id='guide-'+str(number),kind=p.KIND,name='태극기 내부 사례' if number==5 else item['title'],status='APPROVED',version=item['version'],content=json.dumps(item,ensure_ascii=False),image_file='case.png',parent_ids=item['parent_ids'])

def run_for(objects):
    pack=copy.deepcopy(PACK)
    for step in pack['steps']:
        # Match the independently reviewed current authored rule text.
        for item in CATALOG['items']:
            if step['rule_id'] in item['mapped_rule_hashes']:
                step['objective']='fixture rule '+step['rule_id'];break
    refs=[]
    for n in range(1,22):
        ref=reference(n);item=json.loads(ref['content'])
        item['mapped_rule_hashes']={rid:hashlib.sha256(('fixture rule '+rid).encode()).hexdigest() for rid in item['mapped_rule_hashes']};ref['content']=json.dumps(item,ensure_ascii=False);refs.append(ref)
    run=dict(selected=[s['rule_id'] for s in pack['steps']],rule_pack=pack,reference_snapshot=refs,observation={'objects':objects})
    engine=SimpleNamespace(s=Settings({'DATA_DIR':'/tmp/poc11-precheck-test'}))
    p.prepare(engine,{},run);return run

def obj(label,text='',**kw):return dict(id='o1',label=label,description=label,text=text,text_legibility='CLEAR' if text else 'NOT_TEXT',quality='CLEAR',**kw)

def test_full_mapping_preserves_25_parents_156_steps_and_210_traceable_tips():
    assert len(PACK['parents'])==25 and len(PACK['steps'])==156
    assert len(CATALOG['items'])==21
    ids=[]
    for item in CATALOG['items']:
        p.parse(json.dumps(item,ensure_ascii=False));ids.extend(t['id'] for t in item['tips'])
        assert len(item['questions'])==3 and item['source_page']==item['number']+2
    assert len(ids)==len(set(ids))==210
    case=next(i for i in CATALOG['items'] if i['id']=='O18')['cases'][1]
    assert case['status']=='QUARANTINED_FUTURE_EVENT' and not case['runtime_use']

def test_absent_flag_gets_no_flag_guidance_and_never_generates_a_verdict():
    run=run_for([obj('배경')]);before=copy.deepcopy(run)
    assert p.compact(run,['H-04-h'])==[]
    assert p.annotate(run,[],['H-04-h'])==[]
    assert run==before

def test_only_relevant_tip_and_object_are_routed_and_annotated():
    run=run_for([obj('태극기')]);routed=p.compact(run,['H-04-h'])
    assert len(routed)==1 and routed[0]['item_id']=='O05'
    assert all(t['rule_ids']==['H-04-h'] for t in routed[0]['tips'])
    assert 'cases' not in str(routed) and 'image_file' not in str(routed)
    rows=[dict(rule_id='H-04-h',status='REVIEW',evidence_ids=['o1']),dict(rule_id='H-04-h',status='NOT_APPLICABLE',evidence_ids=[])]
    p.annotate(run,rows,['H-04-h'])
    assert rows[0]['status']=='REVIEW' and 'OFFICIAL-05-03' in rows[0]['official_tip_ids']
    assert not rows[1].get('official_tip_ids')

def test_rules_edited_after_mapping_do_not_silently_use_stale_guidance():
    run=run_for([obj('태극기')]);next(s for s in run['rule_pack']['steps'] if s['rule_id']=='H-04-h')['objective']='changed action'
    assert not p.compact(run,['H-04-h'])
    p.prepare(SimpleNamespace(s=Settings({'DATA_DIR':'/tmp/poc11-precheck-test'})),{},run)
    assert any(x['rule_id']=='H-04-h' for x in run['precheck_guidance']['mapping_changes'])

def test_case_page_can_never_be_selected_as_official_visual_reference():
    ref=reference();target=obj('태극기')
    assert verification.reference_candidates(target,[ref])==[]
    official={**ref,'id':'real','kind':'official-symbols','name':'대한민국 태극기 — 정면 도안'}
    assert verification.reference_candidates(target,[ref,official])==[official]

def test_disabled_router_and_invalid_records_keep_old_path():
    run=run_for([obj('태극기')]);engine=SimpleNamespace(s=Settings({'DATA_DIR':'/tmp/poc11-precheck-test','PRECHECK_GUIDANCE_ENABLED':'false'}))
    p.prepare(engine,{},run);assert not p.compact(run,['H-04-h'])
    bad=json.loads(reference()['content']);bad['tips'][1]['id']=bad['tips'][0]['id']
    with pytest.raises(ValueError,match='누락·중복'):p.parse(json.dumps(bad))

def test_pdf_and_page_are_authenticated_and_snapshot_uses_registered_document(tmp_path):
    from fastapi.testclient import TestClient
    from app.main import create_app
    raw=b'%PDF-1.7\nsynthetic test source\n%%EOF'
    item=copy.deepcopy(CATALOG['items'][4]);item['source_sha256']=hashlib.sha256(raw).hexdigest()
    settings=Settings({'DATA_DIR':str(tmp_path),'ADMIN_PASSWORD':'test','REVIEWER_PASSWORD':'review','SESSION_SECRET':'test-secret','EXTERNAL_API_ENABLED':'false'})
    with TestClient(create_app(settings)) as c:
        c.post('/api/login',json={'role':'admin','password':'test'})
        body=dict(name='사전점검 태극기 참고',kind=p.KIND,issuer='내부 참고',official_url='',content=json.dumps(item,ensure_ascii=False),parent_ids=item['parent_ids'],version='test')
        response=c.post('/api/references',json=body);assert response.status_code==200
        ref=response.json();url='/api/references/'+ref['id']+'/document'
        assert c.post(url,files={'file':('x.pdf',b'%PDF-wrong','application/pdf')}).status_code==400
        assert c.post(url,files={'file':('x.pdf',raw,'application/pdf')}).status_code==200
        assert c.get(url).content==raw
        assert c.post('/api/references/'+ref['id']+'/approve').status_code==200
        assert c.post(url,files={'file':('x.pdf',raw,'application/pdf')}).status_code==409
        job=c.post('/api/demo').json();store=c.app.state.store
        job['runs']=[dict(id='saved-run',reference_snapshot=store.references())];store.save(job)
        scoped=f"/api/jobs/{job['id']}/runs/saved-run/references/{ref['id']}/document"
        assert c.get(scoped).content==raw
        assert c.get(scoped.replace('saved-run','other-run')).status_code==404
        c.post('/api/logout');assert c.get(url).status_code==401 and c.get(scoped).status_code==401

def test_engine_routes_guidance_in_existing_batch_without_extra_model_call(tmp_path):
    from app.engine import Engine
    from app.storage import Store
    from PIL import Image
    import time
    target=obj('태극기');target['cell_ids']=['R02C02']
    run=run_for([target]);run.update(id='run',options={'vision_model':'gpt-5.4','analysis_model':'gpt-5.4-mini'},observation_model='gpt-5.4',
        observation_reused_from={'run_id':'old'},selected=['H-04-h'],results=[],calls=[],analysis=[],progress=0)
    (tmp_path/'job').mkdir();Image.new('RGB',(100,100),'white').save(tmp_path/'job/image.png')
    engine=Engine(Settings({'DATA_DIR':str(tmp_path),'PIXEL_TEXT_ENABLED':'false','SPELLING_AUDIT_ENABLED':'false'}),Store(tmp_path/'jobs.sqlite3'));calls=[]
    def call(model,prompt,images=(),workload=''):
        payload=json.loads(prompt);calls.append(workload)
        assert model=='gpt-5.4-mini' and workload=='checklist-analysis' and not images
        assert payload['approved_references']==[]
        assert payload['inspection_guidance']['items'][0]['item_id']=='O05'
        assert len(payload['inspection_guidance']['items'][0]['tips'])<10
        return {'results':[dict(rule_ids=['H-04-h'],target_presence='PRESENT',status='REVIEW',evidence_ids=['o1'],reference_ids=[],reason='도안 원본이 없어 미확정',recommended_action='공식 도안 확인')]},{'model':model}
    engine.provider.call=call;engine.checkpoint=lambda *a:None
    engine.inspect({'id':'job','metadata':{}},run,None,time.monotonic())
    assert calls==['checklist-analysis'] and run['progress']==1
    assert run['results'][0]['official_tip_ids'] and run['results'][0]['status']=='REVIEW'
    engine.pool.shutdown()

def test_plain_title_never_gets_vehicle_or_english_tip_or_contact_badge_routing():
    run=run_for([obj('일반 제목','읽을 수 있는 제목')]);routed=p.compact(run,['D-02-l'])
    tips={t['id'] for i in routed for t in i['tips']}
    assert 'OFFICIAL-20-03' in tips and 'OFFICIAL-20-06' not in tips and 'OFFICIAL-19-09' not in tips
    run=run_for([obj('상단 번호 배지','01')]);assert not any(i['item_id']=='O10' for i in p.compact(run,['D-01-a']))
    text=obj('원본 획 대조 1','한글 문구');text['description']='OCR first_text / shape_text 독립 대조 결과'
    run=run_for([text]);tips={t['id'] for i in p.compact(run,['D-02-l']) for t in i['tips']}
    assert 'OFFICIAL-19-09' not in tips and 'OFFICIAL-19-04' not in tips
