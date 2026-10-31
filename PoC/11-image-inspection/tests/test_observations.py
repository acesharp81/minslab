import json
import time
import pytest
from app.observations import clean_inventory,legacy_inventory
from app.engine import checklist_batches
from app.rules import STEPS
BATCHES=len(checklist_batches(list(STEPS),STEPS))
from app.config import Settings
from app.main import create_app
from fastapi.testclient import TestClient


def inventory():
    return {'summary':'태극기 퀴즈','context':'오답 선택지는 의도된 비교','limitations':'공식 도안 미비교','objects':[
        {'id':'flag1','label':'태극기 선택지 1','description':'붉고 푸른 태극과 네 모서리 괘','text':'01','visual_concerns':'상단 괘 배치 비교 필요','quality':'CLEAR','cell_ids':['R04C03','R04C04']} ]}

def poll(c,jid):
    for _ in range(200):
        j=c.get('/api/jobs/'+jid).json()
        if j['state'] not in ('QUEUED','RUNNING'):return j
        time.sleep(.01)
    pytest.fail('timeout')

def test_inventory_rejects_duplicate_but_preserves_observation_with_invalid_cells():
    data=inventory();data['objects'].append(data['objects'][0].copy())
    with pytest.raises(ValueError):clean_inventory(data)
    data=inventory();data['objects'][0]['cell_ids']=['R99C99','R04C03','bad','R04C03']
    cleaned=clean_inventory(data)
    assert cleaned['objects'][0]['cell_ids']==['R04C03']
    assert cleaned['objects'][0]['text']=='01' and cleaned['objects'][0]['quality']=='CLEAR'
    assert cleaned['location_warnings'][0]['discarded_count']==2
    data['objects'][0]['cell_ids']=['R12C12']
    assert clean_inventory(data,grid={'id':'crop'})['objects'][0]['cell_ids']==[]
    assert clean_inventory(data)['objects'][0]['cell_ids']==['R12C12']


def test_bounded_visual_recheck_and_analysis_only_reuse(tmp_path):
    s=Settings({'DATA_DIR':str(tmp_path),'ADMIN_PASSWORD':'test','EXTERNAL_API_ENABLED':'true','OPENAI_API_KEY':'test','UPSTAGE_API_KEY':'test'})
    with TestClient(create_app(s)) as c:
        c.post('/api/login',json={'role':'admin','password':'test'})
        calls=[];policies=[]
        for parent in ['H-07','D-03']:
            ref=c.post('/api/references',json={'name':'테스트 '+parent,'kind':'culture','issuer':'테스트','official_url':'https://example.org/ref','content':'부모 항목에 한정한 기준 설명','parent_ids':[parent],'version':'test'}).json()
            assert c.post('/api/references/'+ref['id']+'/approve').status_code==200
        def fake(model,prompt,images=(),workload='image-inspection'):
            p=json.loads(prompt);calls.append((model,workload,len(images)));policies.append(p['text_quality_policy']['sensitivity'])
            if workload=='checklist-analysis':
                parents={r['parent_id'] for r in p['rules']}
                assert all(parents.intersection(r['parent_ids']) for r in p['approved_references'])
                assert len(p['approved_references'])==len(parents.intersection({'H-07','D-03'}))
            meta={'event_id':str(len(calls)),'model':model,'workload':workload,'usage':{'input_tokens':100,'output_tokens':20}}
            if workload=='image-verification':
                from test_verification import recheck
                return {'results':[recheck(t['object_id']) for t in p['tasks']]},meta
            if workload=='image-observation':
                observed=inventory();observed['objects'][0]['cell_ids'].append('R13C01')
                return observed,meta
            return {'results':[{'target_presence':'PRESENT','rule_ids':[r['rule_id']],'status':'NOT_APPLICABLE','evidence_ids':[],'reference_ids':[],'reason':'관찰된 대상 없음','recommended_action':'없음'} for r in p['rules']]},meta
        c.app.state.engine.provider.call=fake
        j=c.post('/api/demo').json();url='/api/jobs/'+j['id']
        assert c.post(url+'/runs',json={'mode':'live','consent':True,'vision_model':'gpt-5.4','analysis_model':'solar-pro4'}).status_code==200
        j=poll(c,j['id']);r=j['runs'][-1]
        assert j['state']=='COMPLETED' and {x['rule_id'] for x in r['results']}==set(STEPS)
        assert any(x.get('coverage_fallback') for x in r['results'])
        assert r['observation']['location_warnings'][0]['discarded_count']==1
        assert len(calls)==2+BATCHES and calls[0]==('gpt-5.4','image-observation',2)
        assert calls[1]==('gpt-5.4','image-verification',2)
        assert all(x[2]==0 for x in calls[2:])
        assert all(x=='strict' for x in policies)
        calls.clear();policies.clear()
        assert c.post(url+'/runs',json={'mode':'live','consent':True,'vision_model':'gpt-5.4','analysis_model':'gpt-6.1-sol','reuse_observation_run_id':r['id'],'text_sensitivity':'standard','force':True}).status_code==200
        j=poll(c,j['id']);new=j['runs'][-1]
        assert len(calls)==BATCHES and all(x==('gpt-6.1-sol','checklist-analysis',0) for x in calls)
        assert new['observation']==r['observation'] and new['observation_reused_from']['run_id']==r['id']
        assert j['runs'][0]==r
        assert new['options']['text_sensitivity']=='strict' and all(x=='strict' for x in policies)
        report=c.get(url+'/report');assert report.status_code==200
        assert 'attachment' in report.headers['content-disposition'] and len(report.json()['runs'])==2
        assert 'gpt-5.4' in c.get('/api/config').json()['analysis_models']
        calls.clear()
        assert c.post(url+'/runs',json={'mode':'live','consent':True,'vision_model':'gpt-5.4','analysis_model':'gpt-5.4-mini','reuse_observation_run_id':r['id'],'recheck_object_ids':['unknown'],'force':True}).status_code==409
        assert c.post(url+'/runs',json={'mode':'live','consent':True,'vision_model':'gpt-5.4','analysis_model':'gpt-5.4-mini','reuse_observation_run_id':r['id'],'recheck_object_ids':['flag1'],'force':True}).status_code==200
        j=poll(c,j['id']);updated=j['runs'][-1]
        assert j['state']=='COMPLETED' and updated['observation']==r['observation']
        assert len(calls)==1+BATCHES and calls[0][1]=='image-verification'
        assert all(call[1]!='image-observation' for call in calls)
        assert j['runs'][0]==r



def test_legacy_inventory_keeps_observations_not_old_verdicts():
    run={'results':[{'status':'REVIEW','observation':'태극기 도안 관찰','model':'gpt-6.1-sol','instance_id':'flag1','cell_ids':['R04C03'],'reason':'판정'}]}
    assert legacy_inventory(run)['objects'][0]['description']=='태극기 도안 관찰'
    with pytest.raises(ValueError):legacy_inventory({'results':[]})


def test_grouped_decisions_expand_and_only_missing_steps_error(tmp_path):
    from app.engine import Engine
    from app.storage import Store
    s=Settings({'DATA_DIR':str(tmp_path)});engine=Engine(s,Store(tmp_path/'test.sqlite3'))
    run={'observation':inventory(),'reference_snapshot':[],'observation_model':'gpt-5.4'}
    group={'target_presence':'PRESENT','rule_ids':['D-02-e','D-02-f'],'status':'NOT_APPLICABLE','evidence_ids':[],'reference_ids':[],'reason':'손이 관찰되지 않음','recommended_action':'없음'}
    found=engine.decisions(run,None,'gpt-5.4',['D-02-e','D-02-f','D-02-g'],{'results':[group]})
    assert [r['status'] for r in found]==['NOT_APPLICABLE','NOT_APPLICABLE','ERROR']
    assert [r['rule_id'] for r in found]==['D-02-e','D-02-f','D-02-g']
    duplicates=engine.decisions(run,None,'gpt-5.4',['D-02-e','D-02-f'],{'results':[group,group]})
    assert len(duplicates)==2 and all(r['status']=='NOT_APPLICABLE' for r in duplicates)
    engine.pool.shutdown()


def test_importing_app_module_does_not_create_runtime_app():
    import app.main
    assert not hasattr(app.main,'app')


def test_absent_target_never_inflates_review_and_uncertain_never_passes(tmp_path):
    from app.engine import Engine
    from app.storage import Store
    engine=Engine(Settings({'DATA_DIR':str(tmp_path)}),Store(tmp_path/'test.sqlite3'))
    run={'observation':inventory(),'reference_snapshot':[],'observation_model':'gpt-5.4'}
    group={'target_presence':'ABSENT','rule_ids':['D-04-a'],'status':'PASS','evidence_ids':['flag1'],'reference_ids':[],'reason':'개인정보 노출 대상이 없음','recommended_action':'없음'}
    result=engine.decisions(run,None,'solar-pro4',['D-04-a'],{'results':[group]})[0]
    assert result['status']=='NOT_APPLICABLE' and result['rects']==[] and result['evidence_ids']==[]
    group.update(target_presence='UNCERTAIN',status='PASS')
    assert engine.decisions(run,None,'solar-pro4',['D-04-a'],{'results':[group]})[0]['status']=='REVIEW'
    engine.pool.shutdown()


def test_duplicate_conflicts_are_reviewed_and_distinct_objects_are_preserved(tmp_path):
    from app.engine import Engine
    from app.storage import Store
    engine=Engine(Settings({'DATA_DIR':str(tmp_path)}),Store(tmp_path/'test.sqlite3'))
    obs=inventory();obs['objects'].append({**obs['objects'][0],'id':'flag2','cell_ids':['R04C08']})
    run={'observation':obs,'reference_snapshot':[],'observation_model':'gpt-5.4'}
    base={'target_presence':'PRESENT','rule_ids':['D-02-e'],'status':'PASS','evidence_ids':['flag1'],'reference_ids':[],'reason':'첫 관찰','recommended_action':'확인'}
    data={'results':[base,{**base,'status':'FAIL','reason':'상충 관찰'},{**base,'evidence_ids':['flag2']}]}
    found=engine.decisions(run,None,'solar-pro4',['D-02-e'],data)
    assert len(found)==2 and found[0]['status']=='REVIEW'
    assert '상충' in found[0]['reason'] and found[1]['evidence_ids']==['flag2']
    engine.pool.shutdown()


def test_cross_parent_absence_group_is_expanded_without_losing_valid_results(tmp_path):
    from app.engine import Engine
    from app.storage import Store
    engine=Engine(Settings({'DATA_DIR':str(tmp_path)}),Store(tmp_path/'test.sqlite3'))
    run={'observation':inventory(),'reference_snapshot':[],'observation_model':'gpt-5.4'}
    ids=['D-04-a','P-01-a','E-01-a']
    group={'target_presence':'ABSENT','rule_ids':ids,'status':'NOT_APPLICABLE','evidence_ids':[],'reference_ids':[],'reason':'해당 대상이 관찰되지 않음','recommended_action':'없음'}
    found=engine.decisions(run,None,'solar-pro4',ids,{'results':[group]})
    assert [r['rule_id'] for r in found]==ids and all(r['status']=='NOT_APPLICABLE' for r in found)
    assert [r['parent_id'] for r in found]==['D-04','P-01','E-01']
    engine.pool.shutdown()


def test_batches_keep_original_questions_whole_and_cover_every_step_once():
    batches=checklist_batches(list(STEPS),STEPS)
    assert len(batches)==5
    assert sorted(rid for batch in batches for rid in batch)==sorted(STEPS)
    owners={}
    for index,batch in enumerate(batches):
        assert len(batch)<=40
        for rid in batch:
            parent=STEPS[rid]['parent_id']
            assert owners.setdefault(parent,index)==index
    assert len(owners)==25


def test_readable_but_degraded_text_survives_inventory_and_analysis():
    from app.engine import Engine
    from app.storage import Store
    import tempfile
    from pathlib import Path
    observed=inventory();obj=observed['objects'][0]
    obj.update(text='댓글에 달기',text_legibility='DEGRADED',legibility_evidence='댓글의 ㄷ 획이 주변 획과 붙음',transcription_inferred=True)
    clean=clean_inventory(observed)
    assert clean['objects'][0]['text']=='댓글에 달기'
    assert clean['objects'][0]['text_legibility']=='DEGRADED'
    assert clean['objects'][0]['transcription_inferred'] is True
    assert clean_inventory(inventory())['objects'][0]['text_legibility']=='UNASSESSED'
    with tempfile.TemporaryDirectory() as tmp:
        engine=Engine(Settings({'DATA_DIR':tmp}),Store(Path(tmp)/'test.sqlite3'))
        run={'observation':clean,'reference_snapshot':[],'observation_model':'gpt-5.4'}
        data={'results':[{'target_presence':'PRESENT','rule_ids':['D-02-l'],'status':'FAIL','evidence_ids':['flag1'],'reference_ids':[],'reason':'글자는 읽히나 획이 붙어 가독성 결함','recommended_action':'원본 글자 재입력'}]}
        assert engine.decisions(run,None,'gpt-5.4',['D-02-l'],data)[0]['status']=='FAIL'
        engine.pool.shutdown()


@pytest.mark.parametrize('recover,status,expected_calls',[(True,520,2),(False,520,2),(False,401,1)])
def test_vision_failure_retry_is_bounded_and_attributed(tmp_path,monkeypatch,recover,status,expected_calls):
    from app.providers import ProviderError
    monkeypatch.setattr('app.engine.time.sleep',lambda seconds:None)
    s=Settings({'DATA_DIR':str(tmp_path),'ADMIN_PASSWORD':'test','EXTERNAL_API_ENABLED':'true','OPENAI_API_KEY':'test','OCR_ENABLED':'false'})
    with TestClient(create_app(s)) as c:
        c.post('/api/login',json={'role':'admin','password':'test'})
        calls=[]
        def fake(model,prompt,images=(),workload='image-inspection'):
            calls.append(workload)
            meta={'event_id':str(len(calls)),'model':model,'workload':workload,'usage':{'input_tokens':10,'output_tokens':10}}
            if workload=='image-observation':
                if not recover or calls.count(workload)==1:
                    exc=ProviderError(f'공급자 HTTP {status}')
                    exc.call_meta={**meta,'status':'FAILED','http_status':status,'retryable':status==520,'usage_unknown':True}
                    raise exc
                return inventory(),meta
            if workload=='image-verification':
                from test_verification import recheck
                return {'results':[recheck(t['object_id']) for t in json.loads(prompt)['tasks']]},meta
            return {'results':[{'target_presence':'ABSENT','rule_ids':['D-02-e'],'status':'NOT_APPLICABLE','evidence_ids':[],'reference_ids':[],'reason':'손 없음','recommended_action':'없음'}]},meta
        c.app.state.engine.provider.call=fake
        job=c.post('/api/demo').json();url='/api/jobs/'+job['id']
        assert c.post(url+'/runs',json={'mode':'live','consent':True,'vision_model':'gpt-6.1-sol','analysis_model':'gpt-5.4-mini','rule_ids':['D-02-e'],'force':True}).status_code==200
        job=poll(c,job['id']);run=job['runs'][-1]
        assert calls.count('image-observation')==expected_calls
        assert len([m for m in run['calls'] if m['workload']=='image-observation'])==expected_calls
        if recover:
            assert job['state']=='COMPLETED' and run['observation']['objects']
            assert 'checklist-analysis' in calls and not run['analysis']
        else:
            assert job['state']=='COMPLETED_WITH_ERRORS' and run['failed_phase']=='READING'
            assert run['analysis'][0]['model']=='gpt-6.1-sol'
            assert all(r['status']=='ERROR' for r in run['results'] if r['rule_id']=='D-02-e')
            assert 'checklist-analysis' not in calls


def test_observed_context_conflict_is_not_lost_when_analysis_checks_only_another_object(tmp_path):
    from app.engine import Engine
    from app.storage import Store
    import copy
    from app.rules import PACK
    s=Settings({'DATA_DIR':str(tmp_path)});engine=Engine(s,Store(tmp_path/'test.sqlite3'))
    obs=inventory();obs['objects']=[dict(id='tail',label='운송수단 꼬리 표식',description='본체와 별개 표식',text='',quality='CLEAR',cell_ids=['R01C11'],text_legibility='NOT_TEXT',visual_concerns='공식 도안 비교 불가',first_visual_concerns='명시된 국가 설명과 국기 유사 표식이 충돌함'),dict(id='building',label='건물',description='일반 건물',text='',quality='CLEAR',cell_ids=['R05C05'])]
    pack=copy.deepcopy(PACK);next(r for r in pack['steps'] if r['rule_id']=='H-05-c')['objective']='배경 시각 단서와 주장된 국가/장소가 충돌하는지 점검한다.'
    run={'observation':obs,'reference_snapshot':[],'observation_model':'gpt-6.1-sol','rule_pack':pack}
    group={'target_presence':'PRESENT','rule_ids':['H-05-c'],'status':'PASS','evidence_ids':['building'],'reference_ids':[],'reason':'건물은 충돌 없음','recommended_action':'없음'}
    found=engine.decisions(run,None,'gpt-5.4-mini',['H-05-c'],{'results':[group]})
    tail=next(r for r in found if r['evidence_ids']==['tail'])
    assert tail['status']=='REVIEW' and tail['review_basis']=='CONTEXT_CONFLICT'
    assert tail['visual_issue'] and tail['model']=='system/observation-coverage'
    assert tail['coverage_fallback'] and '누락' in tail['reason']
    engine.pool.shutdown()


def test_fail_with_explicit_no_defect_fields_is_not_a_red_error(tmp_path):
    from app.engine import Engine
    from app.storage import Store
    engine=Engine(Settings({'DATA_DIR':str(tmp_path)}),Store(tmp_path/'test.db'))
    run=dict(observation=inventory(),reference_snapshot=[],observation_model='reader')
    group=dict(target_presence='PRESENT',rule_ids=['D-02-l'],status='FAIL',evidence_ids=['flag1'],reference_ids=[],reason='문구가 선명해 결함이 보이지 않는다.',recommended_action='수정 불필요',error_type='NONE',review_basis='NONE')
    row=engine.decisions(run,None,'analysis',['D-02-l'],{'results':[group]})[0]
    assert row['status']=='REVIEW' and row['decision_conflict'] and not row['visual_issue']
    engine.pool.shutdown()


def test_truncated_analysis_splits_only_failed_batch_and_accounts_for_attempt(tmp_path):
    from app.engine import Engine
    from app.storage import Store
    from app.rules import PACK,placeholder
    from app.providers import ProviderError
    import copy,io
    from PIL import Image
    s=Settings({'DATA_DIR':str(tmp_path),'OCR_ENABLED':'false'})
    engine=Engine(s,Store(tmp_path/'test.db'));jid='job';(tmp_path/jid).mkdir()
    Image.new('RGB',(100,100),'white').save(tmp_path/jid/'image.png')
    ids=list(STEPS);seen=[]
    run=dict(id='run',options={'vision_model':'gpt-5.4','analysis_model':'solar-pro4'},rule_pack=copy.deepcopy(PACK),selected=ids,
        observation=inventory(),observation_reused_from={'run_id':'old'},observation_model='gpt-5.4',reference_snapshot=[],calls=[],analysis=[],results=[placeholder(r) for r in ids],progress=0)
    def fake(model,prompt,images=(),workload=''):
        request=json.loads(prompt);rules=[r['rule_id'] for r in request['rules']];seen.append(rules)
        if len(seen)==1:
            exc=ProviderError('output truncated');exc.output_truncated=True;exc.call_meta={'event_id':'paid-truncated','usage':{'input_tokens':100,'output_tokens':10000}};raise exc
        return {'results':[dict(rule_ids=[r],target_presence='ABSENT',status='NOT_APPLICABLE',evidence_ids=[],reference_ids=[],reason='대상 없음',recommended_action='없음') for r in rules]}, {'event_id':str(len(seen))}
    engine.provider.call=fake;engine.checkpoint=lambda *a:None
    engine.inspect(dict(id=jid,metadata={}),run,None,time.monotonic())
    assert run['progress']==len(ids) and not run['analysis']
    assert len(run['analysis_retries'])==1 and len(seen)==BATCHES+2
    assert any(c['event_id']=='paid-truncated' for c in run['calls'])
    assert not any(r['status'] in ('ERROR','NOT_RUN') for r in run['results'])
    engine.pool.shutdown()


def test_omitted_observed_text_stays_review_without_fabricated_visual_defect(tmp_path):
    from app.engine import Engine
    from app.storage import Store
    from copy import deepcopy
    engine=Engine(Settings({'DATA_DIR':str(tmp_path)}),Store(tmp_path/'test.db'))
    observed=inventory();other=deepcopy(observed['objects'][0]);other.update(id='text2',label='안내문',text='방문 신청',description='안내 문구');observed['objects'].append(other)
    run=dict(observation=observed,reference_snapshot=[],observation_model='reader')
    group=dict(target_presence='PRESENT',rule_ids=['D-02-l'],status='PASS',evidence_ids=['flag1'],reference_ids=[],reason='확인한 문구 정상',recommended_action='없음',error_type='NONE',review_basis='NONE')
    rows=engine.decisions(run,None,'model',['D-02-l'],{'results':[group]})
    missing=next(r for r in rows if r['evidence_ids']==['text2'])
    assert missing['status']=='REVIEW' and missing['coverage_fallback'] and not missing['visual_issue']
    assert missing['rects'] and '누락' in missing['reason']
    engine.pool.shutdown()
