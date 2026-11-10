import json
import threading
import httpx
import pytest
from app import main
from app.billing import Meter
from app.store import Store
from app.streaming import preview_text, completion_stream
from test_flow import client, seed
from test_reports import confirm


def test_incremental_preview_unicode_escapes_and_hidden_references():
    paragraphs=[{'text':'첫 문장 "text": "가짜 키"\n다음 줄 😀 한글', 'fact_ids':['F123'],'background_ids':[]}, {'text':'두 번째 문단', 'fact_ids':['F24'],'background_ids':[]}]
    for ascii in [False,True]:
        raw=json.dumps({'paragraphs':paragraphs},ensure_ascii=ascii)
        final='\n\n'.join(p['text'] for p in paragraphs); previous=''
        for end in range(len(raw)+1):
            text=preview_text(raw[:end])
            assert final.startswith(text) and text.startswith(previous)
            assert not any(0xD800<=ord(c)<=0xDFFF for c in text)
            previous=text
        assert previous==final and 'F123' not in previous


def transport(monkeypatch, lines):
    class Response:
        status_code=200
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def iter_lines(self):yield from lines()
    class Client:
        def __init__(self,**kw):pass
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def stream(self, method, url, headers, json):
            assert json['stream'] is True and json['stream_options']['include_usage'] is True
            return Response()
    monkeypatch.setattr(httpx,'Client',Client)


def event(value):return 'data: '+json.dumps(value)


def test_transport_emits_before_completion_and_meters_final_usage(tmp_path,monkeypatch):
    meter=Meter(Store(tmp_path));config={'key':'synthetic','url':'https://api.upstage.ai/v1','model':'solar-pro4','_meter':meter};seen=[]
    def lines():
        yield event({'choices':[{'delta':{'content':'first'}}]})
        assert seen==['first']  # Callback runs before the provider sends its next chunk.
        yield event({'model':'solar-pro4-260806','choices':[{'delta':{'content':' second'},'finish_reason':'stop'}]})
        yield event({'choices':[],'usage':{'prompt_tokens':100,'completion_tokens':20}})
        yield 'data: [DONE]'
    transport(monkeypatch,lines)
    response=completion_stream(config,{},1,'question',seen.append)
    assert seen==['first','first second']
    assert response.json()['choices'][0]['message']['content']=='first second'
    assert meter.summary(config)['used_usd']==pytest.approx(.000054)
    assert meter.summary(config)['calls']==1


def test_interrupted_stream_is_not_completed_and_usage_is_unknown(tmp_path,monkeypatch):
    meter=Meter(Store(tmp_path));config={'key':'synthetic','url':'https://api.upstage.ai/v1','model':'solar-pro4','_meter':meter}
    transport(monkeypatch,lambda:iter([event({'choices':[{'delta':{'content':'partial'}}]})]))
    with pytest.raises(ValueError,match='수신이 완료되지'):
        completion_stream(config,{},1,'question',lambda _:None)
    assert meter.summary(config)['unknown_calls']==1
    stopped=threading.Event();stopped.set()
    with pytest.raises(ValueError,match='중지'):
        completion_stream(config,{},1,'question',lambda _:None,stopped)
    assert meter.summary(config)['calls']==1


def events(response):
    result=[]
    for frame in response.text.split('\n\n'):
        lines=frame.splitlines()
        if len(lines)>=2 and lines[0].startswith('event:'):
            result.append((lines[0][7:],json.loads(lines[1][6:])))
    return result


def test_stream_auth_consent_final_validation_and_revision_change(client,monkeypatch):
    c=client;base,rev=seed(c);confirm(c,base,rev)
    c.app.state.runner.model_config['key']='synthetic'
    body={'question':'정산 업무는?', 'mode':'llm','external_consent':True,'expected_revision':rev['id']}
    assert c.post(base+'/questions/stream',json={**body,'external_consent':False}).status_code==422
    assert c.post(base+'/questions/stream',json={**body,'expected_revision':'wrong'}).status_code==409
    original=main.answer_question
    change=[False];invalid=[False]
    def fake(revision,question,blocks,mode,config,**kw):
        kw['on_delta']('실시간 답변')
        if invalid[0]:raise ValueError('존재하지 않는 근거')
        result=original(revision,question,blocks,'local',config)
        if change[0]:
            with c.app.state.store.connect(write=True) as db:db.execute('UPDATE cases SET confirmed=NULL WHERE id=?',(base.rsplit('/',1)[-1],))
        return result
    monkeypatch.setattr(main,'answer_question',fake)
    response=c.post(base+'/questions/stream',json=body)
    assert response.headers['x-accel-buffering']=='no'
    assert [kind for kind,_ in events(response)]==['start','delta','done']
    invalid[0]=True
    assert [kind for kind,_ in events(c.post(base+'/questions/stream',json=body))]==['start','delta','error']
    invalid[0]=False;change[0]=True
    response=c.post(base+'/questions/stream',json=body)
    assert events(response)[-1][0]=='error' and '확정본이 변경' in events(response)[-1][1]['message']
