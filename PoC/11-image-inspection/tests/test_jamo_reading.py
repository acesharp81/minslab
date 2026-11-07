import json
import httpx
from app.jamo_reading import as_shape
from app.providers import Provider
from app.config import Settings
from test_provider import Meter

def reading(**changes):
    return dict(dict(region_id='g',coverage='COMPLETE',onset='ㅂ',vowel='ㅜ',coda='ㄱ',vowel_geometry='DOWN',certain=True,quality='CLEAR',evidence='가로 기준 획 아래로 짧은 획'),**changes)

def test_composition_uses_components_and_abstains_on_shape_conflict():
    assert as_shape(reading())['units'][0]['char']=='북'
    assert as_shape(reading(vowel='ㅗ',vowel_geometry='UP'))['units'][0]['char']=='복'
    assert as_shape(reading(onset='ㅎ',vowel='ㅏ',vowel_geometry='RIGHT',coda='NONE'))['units'][0]['char']=='하'
    for r in [reading(vowel='ㅗ'),reading(coda='UNKNOWN'),reading(coverage='PARTIAL'),reading(certain=False)]:
        assert as_shape(r)['units'][0]['char']=='□' and not as_shape(r)['units'][0]['certain']

def test_provider_component_schema_original_input_and_shared_meter(tmp_path,monkeypatch):
    s=Settings({'DATA_DIR':str(tmp_path),'OPENAI_API_KEY':'test','OPENAI_BASE_URL':'https://example.org/v1'})
    real=httpx.Client
    def respond(req):
        body=json.loads(req.content)
        assert body['text']['format']['schema']['$defs']['JamoReading']['properties']['region_id']['enum']==['g']
        assert body['reasoning']['effort']=='low'
        assert body['input'][0]['content'][1]['detail']=='original'
        return httpx.Response(200,json={'status':'completed','usage':{'input_tokens':12,'output_tokens':20},'output':[{'type':'message','content':[{'type':'output_text','text':json.dumps({'results':[reading()]})}]}]})
    monkeypatch.setattr('app.providers.httpx.Client',lambda **kw:real(transport=httpx.MockTransport(respond),**kw))
    data,meta=Provider(s,Meter()).call('gpt-5.4',json.dumps({'tasks':[{'region_id':'g','image_index':0}]}),[b'image'],workload='text-jamo-isolated')
    assert data['results'][0]['vowel']=='ㅜ' and meta['usage']['input_tokens']==12
