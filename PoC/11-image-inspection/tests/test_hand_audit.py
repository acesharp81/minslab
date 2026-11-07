import io,json
from types import SimpleNamespace
import httpx
from PIL import Image
from app import hand_audit as h
from app.config import Settings
from app.providers import Provider
from app.rules import PACK
from test_provider import Meter


def check(concerns=None):
    return dict(object_id='hand',coverage='VISIBLE_PARTS',traces=[dict(part='검지',visible_path='손바닥에서 끝까지',obscured_by='꽃')],concerns=concerns or [],summary='보이는 구조 확인')


def test_provider_hand_schema_matches_response_and_uses_shared_meter(tmp_path,monkeypatch):
    settings=Settings({'DATA_DIR':str(tmp_path),'OPENAI_API_KEY':'test','OPENAI_BASE_URL':'https://example.org/v1'})
    real=httpx.Client;seen=[]
    def respond(req):
        body=json.loads(req.content);seen.append(body)
        assert body['text']['format']['schema']['$defs']['HandCheck']['properties']['object_id']['enum']==['hand']
        return httpx.Response(200,json={'status':'completed','usage':{'input_tokens':12,'output_tokens':20},'output':[{'type':'message','content':[{'type':'output_text','text':json.dumps({'results':[check()]})}]}]})
    monkeypatch.setattr('app.providers.httpx.Client',lambda **kw:real(transport=httpx.MockTransport(respond),**kw))
    body,meta=Provider(settings,Meter()).call('gpt-5.4',json.dumps({'tasks':[{'object_id':'hand','image_index':0}]}),[b'image'],workload='hand-topology')
    assert body['results'][0]['object_id']=='hand' and meta['usage']['input_tokens']==12
    assert seen[0]['reasoning']['effort']=='medium'
    assert seen[0]['input'][0]['content'][0]['detail']=='original'


def test_occlusion_does_not_create_findings_and_localized_anomaly_survives(tmp_path):
    run={'options':{},'observation':{'objects':[dict(id='hand',label='손짓',description='',cell_ids=['R04C04'])]},'calls':[], 'rule_pack':PACK,'reference_snapshot':[]}
    calls=[]
    def call(model,prompt,images,workload):
        calls.append(prompt)
        if workload=='hand-location':return {'results':[dict(object_id='hand',found=True,rect=[.2,.2,.7,.7],evidence='손 위치')]},{'event_id':'loc','workload':workload}
        return {'results':[check()]},{'event_id':'e','workload':workload}
    engine=SimpleNamespace(s=Settings({'DATA_DIR':str(tmp_path)}),provider=SimpleNamespace(call=call),checkpoint=lambda *a:None)
    raw=io.BytesIO();Image.new('RGB',(1000,1000),'white').save(raw,format='PNG')
    h.inspect(engine,{'id':'j'},run,raw.getvalue())
    assert len(calls)==2 and run['hand_audit']['status']=='COMPLETED'
    assert h.protect(run,[],['D-02-e'])==[]
    run['hand_audit']['results'][0]['accepted_concerns']=[dict(kind='BRANCH',evidence='보이는 뿌리의 비정상 분기',alternative_explanation='',global_rect=[.2,.2,.3,.3])]
    rows=h.protect(run,[],['D-02-e'])
    assert len(rows)==1 and rows[0]['status']=='REVIEW' and rows[0]['visual_issue']
    assert h.protect(run,[],['H-04-h'])==[]
