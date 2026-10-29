import json
import time
import pytest
from fastapi.testclient import TestClient
from app.main import create_app
from app.config import Settings
from app.rules import PACK
from app.rule_editor import parse_markdown,to_markdown


def test_roundtrip_and_missing_duplicate_rule_rejected():
    md=to_markdown(PACK);parsed=parse_markdown(md)
    assert [s['objective'] for s in parsed['steps']]==[s['objective'] for s in PACK['steps']]
    with pytest.raises(ValueError):parse_markdown(md.replace('### H-01-a','### unknown'))
    with pytest.raises(ValueError):parse_markdown(md+'\n### H-01-a\n중복 규칙 테스트')


def test_admin_only_conflict_history_and_run_snapshots(tmp_path):
    settings=Settings({'DATA_DIR':str(tmp_path),'ADMIN_PASSWORD':'admin','REVIEWER_PASSWORD':'review','COOKIE_SECURE':'false'})
    with TestClient(create_app(settings)) as c:
        assert c.get('/api/admin/rules').status_code==401
        c.post('/api/login',json={'role':'reviewer','password':'review'})
        assert c.get('/api/admin/rules').status_code==403
        assert c.put('/api/admin/rules',json={'markdown':'test','base_version':'x'}).status_code==403
        c.post('/api/login',json={'role':'admin','password':'admin'})
        initial=c.get('/api/admin/rules').json();old=initial['pack']['steps'][0]['objective']
        job=c.post('/api/demo').json();path='/api/jobs/'+job['id']
        c.post(path+'/runs',json={'mode':'mock'})
        for _ in range(100):
            job=c.get(path).json()
            if job['state']=='COMPLETED':break
            time.sleep(.01)
        old_run=job['runs'][0]
        draft=initial['markdown'].replace(old,'연도와 장소를 각각 확인하고 근거를 기록한다.')
        body={'markdown':draft,'base_version':initial['version']}
        validated=c.post('/api/admin/rules/validate',json=body)
        assert validated.status_code==200 and 'H-01-a' in validated.json()['changed']
        saved=c.put('/api/admin/rules',json=body);assert saved.status_code==200
        assert c.get(path).json()['runs'][0]==old_run
        assert c.get('/api/rules').json()['steps'][0]['objective']=='연도와 장소를 각각 확인하고 근거를 기록한다.'
        assert c.put('/api/admin/rules',json=body).status_code==409
        bad={**body,'base_version':saved.json()['version'],'markdown':'invalid'}
        assert c.put('/api/admin/rules',json=bad).status_code==422
        state=c.get('/api/admin/rules').json();assert len(state['history'])==1
        seq=state['history'][0]['seq'];assert c.get('/api/admin/rules/versions/'+str(seq)).json()['markdown']==draft
        # A live run consumes the saved objective, while preserving the previous pack.
        prompts=[]
        from test_observations import inventory
        def fake(model,prompt,images=(),workload='image-inspection'):
            p=json.loads(prompt);prompts.append(p)
            meta={'model':model,'usage':{'input_tokens':1,'output_tokens':1}}
            if images:return inventory(),meta
            return {'results':[{'target_presence':'PRESENT','rule_ids':[r['rule_id']],'status':'NOT_APPLICABLE','evidence_ids':[],'reference_ids':[],'reason':'대상 없음','recommended_action':'없음'} for r in p['rules']]},meta
        c.app.state.engine.provider.call=fake
        c.post(path+'/runs',json={'mode':'live','consent':True,'rule_ids':['H-01-a'],'force':True})
        for _ in range(100):
            job=c.get(path).json()
            if job['state']=='COMPLETED':break
            time.sleep(.01)
        assert prompts[-1]['rules'][0]['action']=='연도와 장소를 각각 확인하고 근거를 기록한다.'
        assert job['runs'][-1]['rule_pack']['version']==saved.json()['version']
        assert job['runs'][0]==old_run


def test_authoring_guide_and_rejected_freeform_leave_rules_unchanged(tmp_path):
    with TestClient(create_app(Settings({'DATA_DIR':str(tmp_path),'ADMIN_PASSWORD':'admin'}))) as c:
        c.post('/api/login',json={'role':'admin','password':'admin'})
        initial=c.get('/api/admin/rules').json()
        assert '### H-01-a' in initial['authoring_guide'] and '156' in initial['authoring_guide']
        bad=c.post('/api/admin/rules/validate',json={'markdown':'# 규칙집 v2.0\n#### H-01 | 역사\n`H-01-a`를 검사한다.','base_version':initial['version']})
        assert bad.status_code==422 and '다른 AI' in bad.json()['detail']
        assert c.get('/api/admin/rules').json()['markdown']==initial['markdown']
