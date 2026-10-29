import json
import pytest,httpx
from app.config import Settings
from app.providers import Provider,ProviderError
from app.usage import token_cost
from test_observations import inventory

class Meter:
    def __init__(self):self.events=[]
    def preflight(self,p):pass
    def reserve(self,*args):return {'event_id':args[0]}
    def record(self,e,r):self.events.append((e,r))

@pytest.mark.parametrize('mode',['timeout','refusal','incomplete','badjson','schema','unauthorized'])
def test_provider_errors_preserve_usage_and_no_pass(tmp_path,monkeypatch,mode):
    meter=Meter();s=Settings({'DATA_DIR':str(tmp_path),'OPENAI_API_KEY':'secret-test','OPENAI_BASE_URL':'https://example.org/v1'})
    real=httpx.Client
    def respond(req):
        if mode=='timeout':raise httpx.ReadTimeout('timeout',request=req)
        if mode=='unauthorized':return httpx.Response(401,json={'error':{}})
        body={'status':'completed','usage':{'input_tokens':10,'output_tokens':4},'output':[{'type':'message','content':[{'type':'output_text','text':'{"results":[]}'}]}]}
        if mode=='refusal':body['output'][0]['content']=[{'type':'refusal','refusal':'cannot'}]
        if mode=='incomplete':body['status']='incomplete'
        if mode=='badjson':body['output'][0]['content'][0]['text']='broken'
        if mode=='schema':body['output'][0]['content'][0]['text']='{"bbox": [1,2]}'
        return httpx.Response(200,json=body)
    monkeypatch.setattr('app.providers.httpx.Client',lambda **kwargs:real(transport=httpx.MockTransport(respond)))
    with pytest.raises(ProviderError):Provider(s,meter).call('gpt-6.1-sol','test')
    assert len(meter.events)==1 and meter.events[0][0]['status']=='FAILED'
    assert meter.events[0][0]['cost_usd'] is None if mode=='timeout' else meter.events[0][0]['cost_usd'] is not None


def test_solar_never_receives_images(tmp_path):
    meter=Meter();s=Settings({'DATA_DIR':str(tmp_path),'UPSTAGE_API_KEY':'test'})
    with pytest.raises(ProviderError):Provider(s,meter).call('solar-pro4','test',[b'image'])
    assert meter.events==[]

def test_cost_unknown_and_standard_rates():
    assert token_cost('gpt-6.1-sol',{})==(0,0,None)
    assert token_cost('gpt-6.1-sol',{'input_tokens':1000,'output_tokens':1000})==(1000,1000,.012)
    assert token_cost('gpt-6-astra',{'input_tokens':1000,'output_tokens':1000})==(1000,1000,.06)


@pytest.mark.parametrize('model',['gpt-5.4','gpt-5.4-mini'])
def test_analysis_dynamic_schema_preserves_auth_key(tmp_path,monkeypatch,model):
    meter=Meter();s=Settings({'DATA_DIR':str(tmp_path),'OPENAI_API_KEY':'secret-test','OPENAI_BASE_URL':'https://example.org/v1'})
    real=httpx.Client
    def respond(req):
        assert req.headers['authorization']=='Bearer secret-test'
        body=json.loads(req.content);props=body['text']['format']['schema']['$defs']['Assessment']['properties']
        assert body['text']['format']['schema']['properties']['assessments']['required']==['D-02-e'] and props['reference_ids']['maxItems']==0
        result={'target_presence':'PRESENT','rule_ids':['D-02-e'],'status':'NOT_APPLICABLE','evidence_ids':[],'reference_ids':[],'reason':'손 없음','recommended_action':'없음'}
        return httpx.Response(200,json={'status':'completed','usage':{'input_tokens':10,'output_tokens':10},'output':[{'type':'message','content':[{'type':'output_text','text':json.dumps({'assessments':{'D-02-e':[{k:v for k,v in result.items() if k!='rule_ids'}]}})}]}]})
    monkeypatch.setattr('app.providers.httpx.Client',lambda **kwargs:real(transport=httpx.MockTransport(respond)))
    data,meta=Provider(s,meter).call(model,json.dumps({'rules':[{'rule_id':'D-02-e'}],'observation':{'objects':[{'id':'obj1'}]},'approved_references':[]}),workload='checklist-analysis')
    assert meta['usage']['input_tokens']==10


def test_openrouter_free_envelope_never_uses_paid_fallback(tmp_path,monkeypatch):
    meter=Meter();s=Settings({'DATA_DIR':str(tmp_path),'OPENROUTER_API_KEY':'router-test','OPENROUTER_GATEWAY_URL':'','OPENROUTER_REQUIRE_SHARED':'false'})
    real=httpx.Client
    def respond(req):
        assert str(req.url)=='https://openrouter.ai/api/v1/chat/completions'
        assert req.headers['authorization']=='Bearer router-test'
        body=json.loads(req.content)
        obj=body['response_format']['json_schema']['schema']['$defs']['ObjectObservation']
        assert set(obj['required'])==set(obj['properties'])
        assert all('default' not in v for v in obj['properties'].values())
        assert 'DEGRADED' in obj['properties']['text_legibility']['enum']
        cells=body['response_format']['json_schema']['schema']['$defs']['ObjectObservation']['properties']['cell_ids']['items']['enum']
        assert len(cells)==144 and 'R12C12' in cells and 'R13C01' not in cells
        assert body['provider']['max_price']=={'prompt':0,'completion':0}
        assert body['provider']['allow_fallbacks'] is False
        assert body['messages'][1]['content'][0]['type']=='image_url'
        return httpx.Response(200,json={'model':'nvidia/nemotron-3.5-super-vl:free','usage':{'prompt_tokens':20,'completion_tokens':40},'choices':[{'finish_reason':'stop','message':{'content':json.dumps(inventory())}}]})
    monkeypatch.setattr('app.providers.httpx.Client',lambda **kwargs:real(transport=httpx.MockTransport(respond)))
    data,meta=Provider(s,meter).call('nvidia/nemotron-3.5-super-vl:free',json.dumps({'grid':{'rows':12,'cols':12}}),[b'image'],workload='image-observation')
    assert meta['cost_usd']==0 and meta['usage']['output_tokens']==40
    assert meter.events[0][0]['provider']=='openrouter'


def test_openrouter_uses_shared_admission_and_missing_gateway_fails_closed(tmp_path,monkeypatch):
    meter=Meter();s=Settings({'DATA_DIR':str(tmp_path),'OPENROUTER_API_KEY':'router-test','OPENROUTER_GATEWAY_URL':'http://shared:8071','OPENROUTER_REQUIRE_SHARED':'true','USAGE_METER_TOKEN':'meter-test'})
    real=httpx.Client
    def respond(req):
        assert str(req.url)=='http://shared:8071/api/v1/chat/completions'
        assert 'authorization' not in req.headers
        assert req.headers['x-minslab-meter-token']=='meter-test'
        assert req.headers['x-minslab-project']=='poc11-image-inspection'
        assert req.headers['x-minslab-priority']=='30'
        assert req.headers['x-idempotency-key']
        return httpx.Response(200,json={'usage':{'prompt_tokens':20,'completion_tokens':40},'choices':[{'finish_reason':'stop','message':{'content':json.dumps(inventory())}}]})
    monkeypatch.setattr('app.providers.httpx.Client',lambda **kwargs:real(transport=httpx.MockTransport(respond)))
    Provider(s,meter).call('nvidia/nemotron-3.5-super-vl:free',json.dumps({'grid':{'rows':12,'cols':12}}),[b'image'],workload='image-observation')
    s.values['OPENROUTER_GATEWAY_URL']=''
    with pytest.raises(ProviderError):Provider(s,meter).call('nvidia/nemotron-3.5-super-vl:free',json.dumps({'grid':{'rows':12,'cols':12}}),[b'image'],workload='image-observation')


def test_schema_requires_independent_verdict_for_every_rule(tmp_path,monkeypatch):
    s=Settings({'DATA_DIR':str(tmp_path),'OPENAI_API_KEY':'test','OPENAI_BASE_URL':'https://example.org/v1'})
    real=httpx.Client;ids=['D-02-e','D-02-f','D-02-g']
    def respond(req):
        schema=json.loads(req.content)['text']['format']['schema']
        assert schema['properties']['assessments']['required']==ids
        group={'target_presence':'ABSENT','status':'NOT_APPLICABLE','evidence_ids':[],'reference_ids':[],'reason':'손 없음','recommended_action':'없음'}
        payload={'assessments':{rid:[group] for rid in ids}}
        return httpx.Response(200,json={'status':'completed','usage':{'input_tokens':1,'output_tokens':1},'output':[{'type':'message','content':[{'type':'output_text','text':json.dumps(payload)}]}]})
    monkeypatch.setattr('app.providers.httpx.Client',lambda **kwargs:real(transport=httpx.MockTransport(respond)))
    data,_=Provider(s,Meter()).call('gpt-5.4',json.dumps({'rules':[{'rule_id':r} for r in ids],'observation':{'objects':[]},'approved_references':[]}),workload='checklist-analysis')
    assert [r['rule_ids'] for r in data['results']]==[[rid] for rid in ids]


def test_different_original_questions_cannot_share_verdict_group(tmp_path,monkeypatch):
    s=Settings({'DATA_DIR':str(tmp_path),'OPENAI_API_KEY':'test','OPENAI_BASE_URL':'https://example.org/v1'})
    meter=Meter();real=httpx.Client;ids=['H-03-a','E-01-a']
    def respond(req):
        schema=json.loads(req.content)['text']['format']['schema']
        assignments=schema['properties']['assessments']['properties']
        assert all(v['type']=='array' and v['minItems']==1 and v['items']=={'$ref':'#/$defs/Assessment'} for v in assignments.values())
        group={'group_id':'H-03-g1','target_presence':'PRESENT','status':'PASS','evidence_ids':['o1'],'reference_ids':[],
               'reason':'문구가 선명함','recommended_action':'없음'}
        payload={'groups':[group],'assignments':dict.fromkeys(ids,'H-03-g1')}
        return httpx.Response(200,json={'status':'completed','usage':{'input_tokens':20,'output_tokens':10},'output':[{'type':'message','content':[{'type':'output_text','text':json.dumps(payload)}]}]})
    monkeypatch.setattr('app.providers.httpx.Client',lambda **kwargs:real(transport=httpx.MockTransport(respond)))
    with pytest.raises(ProviderError,match='필수 규칙별 판정'):
        Provider(s,meter).call('gpt-5.4',json.dumps({'rules':[{'rule_id':r} for r in ids],'observation':{'objects':[{'id':'o1'}]},'approved_references':[]}),workload='checklist-analysis')
    assert meter.events[0][0]['status']=='FAILED' and meter.events[0][0]['input_tokens']==20


def test_one_rule_preserves_different_object_verdicts_and_rejects_empty_array(tmp_path,monkeypatch):
    s=Settings({'DATA_DIR':str(tmp_path),'OPENAI_API_KEY':'test','OPENAI_BASE_URL':'https://example.org/v1'})
    real=httpx.Client;outputs=[]
    for oid,state in [('o1','PASS'),('o2','FAIL')]:
        outputs.append(dict(target_presence='PRESENT',status=state,evidence_ids=[oid],reference_ids=[],reason='관찰 근거',recommended_action='확인',error_type='NONE'))
    def respond(req):
        payload=json.loads(req.content)
        assessment=payload['text']['format']['schema']['$defs']['Assessment']
        assert assessment['properties']['evidence_ids']['maxItems']==1
        return httpx.Response(200,json={'status':'completed','usage':{'input_tokens':10,'output_tokens':10},'output':[{'type':'message','content':[{'type':'output_text','text':json.dumps({'assessments':{'D-02-e':outputs}})}]}]})
    monkeypatch.setattr('app.providers.httpx.Client',lambda **kwargs:real(transport=httpx.MockTransport(respond)))
    prompt=json.dumps({'rules':[{'rule_id':'D-02-e'}],'observation':{'objects':[{'id':'o1'},{'id':'o2'}]},'approved_references':[]})
    data,_=Provider(s,Meter()).call('gpt-5.4',prompt,workload='checklist-analysis')
    assert [(r['evidence_ids'][0],r['status']) for r in data['results']]==[('o1','PASS'),('o2','FAIL')]
    outputs.clear()
    with pytest.raises(ProviderError,match='판정 배열'):Provider(s,Meter()).call('gpt-5.4',prompt,workload='checklist-analysis')


def test_mini_supports_verification_envelope_and_required_coverage(tmp_path,monkeypatch):
    from test_verification import recheck
    s=Settings({'DATA_DIR':str(tmp_path),'OPENAI_API_KEY':'test','OPENAI_BASE_URL':'https://example.org/v1'})
    real=httpx.Client
    def respond(req):
        body=json.loads(req.content);schema=body['text']['format']['schema']
        assert body['model']=='gpt-5.4-mini'
        assert len([c for c in body['input'][0]['content'] if c['type']=='input_image'])==2
        assert '검사 대상 o1' in body['input'][0]['content'][0]['text']
        assert body['input'][0]['content'][1]['type']=='input_image'
        assert '위치 참고 격자' in body['input'][0]['content'][2]['text']
        assert 'coverage' in schema['$defs']['Recheck']['required']
        assert schema['$defs']['Recheck']['properties']['comparisons']['maxItems']==0
        return httpx.Response(200,json={'status':'completed','usage':{'input_tokens':100,'output_tokens':20},'output':[{'type':'message','content':[{'type':'output_text','text':json.dumps({'results':[recheck('o1')]})}]}]})
    monkeypatch.setattr('app.providers.httpx.Client',lambda **kwargs:real(transport=httpx.MockTransport(respond)))
    data,_=Provider(s,Meter()).call('gpt-5.4-mini',json.dumps({'tasks':[{'object_id':'o1','label':'표지','clean_image_index':0,'grid_image_index':1}],'reference_images':[]}),[b'original',b'grid'],workload='image-verification')
    assert data['results'][0]['coverage']=='COMPLETE'


@pytest.mark.parametrize('effort',['none','low','high'])
def test_solar_standard_and_reasoning_keep_structured_response_contract(tmp_path,monkeypatch,effort):
    s=Settings({'DATA_DIR':str(tmp_path),'UPSTAGE_API_KEY':'test-solar','UPSTAGE_BASE_URL':'https://api.upstage.ai/v1','UPSTAGE_REASONING_EFFORT':effort})
    real=httpx.Client
    def respond(req):
        body=json.loads(req.content)
        assert str(req.url)=='https://api.upstage.ai/v1/responses'
        assert req.headers['authorization']=='Bearer test-solar'
        assert body['model']=='solar-pro4' and body['reasoning']=={'effort':effort}
        assert body['text']['format']['schema']['properties']['assessments']['properties']['D-02-e']['type']=='array'
        item={'target_presence':'PRESENT','status':'FAIL','evidence_ids':['o1'],'reference_ids':[],'reason':'여섯 손가락 확인','recommended_action':'손 구조 수정','error_type':'NONE'}
        return httpx.Response(200,json={'status':'completed','model':'solar-pro4-260806','usage':{'input_tokens':10,'output_tokens':20},'output':[{'type':'message','content':[{'type':'output_text','text':json.dumps({'assessments':{'D-02-e':[item]}})}]}]})
    monkeypatch.setattr('app.providers.httpx.Client',lambda **kwargs:real(transport=httpx.MockTransport(respond)))
    data,meta=Provider(s,Meter()).call('solar-pro4',json.dumps({'rules':[{'rule_id':'D-02-e'}],'observation':{'objects':[{'id':'o1'}]},'approved_references':[]}),workload='checklist-analysis')
    assert data['results'][0]['status']=='FAIL' and meta['model']=='solar-pro4-260806'
