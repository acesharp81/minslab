import io
import json
import zipfile
from datetime import date

import httpx

from app import main, questions
from app.engine import annotate_items, empty_field
from app.workflow import briefing, readiness
from test_flow import client, generate, new_case, seed
from test_reports import confirm


def test_batch_all_files_or_none_and_nested_paths(client):
    c = client
    base = new_case(c)
    response = c.post(base+'/documents/batch', files=[('files', ('팀/진행.txt', '업무: 진행'.encode())), ('files', ('팀/완료.txt', '업무: 완료'.encode()))])
    assert response.status_code == 200 and len(response.json()['documents']) == 2
    duplicate = c.post(base+'/documents/batch', files=[('files', ('팀/진행.txt', '업무: 진행'.encode()))])
    assert duplicate.json()['documents'][0]['duplicate']
    bad = io.BytesIO()
    with zipfile.ZipFile(bad, 'w') as z:
        z.writestr('../escape.txt', 'bad')
    response = c.post(base+'/documents/batch', files=[('files', ('새자료.txt', b'new')), ('files', ('bad.zip', bad.getvalue()))])
    assert response.status_code == 422
    assert len(c.get(base).json()['documents']) == 2
    versions = c.post(base+'/documents/batch', files=[('files', ('same.txt', b'a')), ('files', ('same.txt', b'b'))])
    assert versions.status_code == 200 and len(versions.json()['documents']) == 2
    assert len({d['id'] for d in c.get(base).json()['documents'] if d['path']=='same.txt'}) == 2
    assert c.post(base+'/documents/batch', files=[('files', ('x.txt', b'x'))], headers={'X-Role': 'successor'}).status_code == 403


def test_briefing_readiness_and_confirmed_only(client):
    c = client
    base, rev = seed(c)
    assert c.get(base+'/briefing').status_code == 409
    assert 'readiness' in rev
    confirm(c, base, rev)
    first = c.get(base+'/briefing').json()
    assert first['revision_id'] == rev['id']
    contact = next(r for r in first['contacts'] if '생활문화' in r['title'])
    assert contact['owner'] == '문화기획팀'
    assert contact['collaborators'] == '예산팀'
    assert 'culture@example.invalid' in contact['contacts']
    assert any('월간' in r['title'] for r in first['groups']['정기 업무'])
    assert any('생활문화' in r['title'] for r in first['groups']['일정 확인 필요'])
    generate(c, base)
    assert c.get(base+'/briefing').json()['revision_id'] == rev['id']


def test_question_uses_edited_final_not_raw_or_new_draft(client):
    c = client
    base, rev = seed(c)
    item = next(i for i in rev['payload']['items'] if '생활문화' in i['fields']['title']['value'])
    rev = c.patch(base+f"/revisions/{rev['id']}/items/{item['id']}", json={'expected_hash': rev['hash'], 'fields': {'due_date': '2026-11-27'}, 'reason': '확인한 일정'}).json()
    confirm(c, base, rev)
    body = {'question': '생활문화 기한은 언제?', 'expected_revision': rev['id'], 'mode': 'local'}
    result = c.post(base+'/questions', json=body).json()
    assert result['facts'][0]['value'] == '2026-11-27'
    assert result['facts'][0]['provenance'] == 'HUMAN_ENTERED'
    assert not result['background']
    generate(c, base)
    assert c.post(base+'/questions', json=body).json()['facts'][0]['value'] == '2026-11-27'
    other = new_case(c)
    assert c.post(other+'/questions', json=body).status_code == 409
    assert c.post(base+'/questions', json={**body, 'expected_revision': 'wrong'}).status_code == 409
    assert c.post(base+'/questions', json={**body, 'mode': 'llm'}).status_code == 422
    unknown = c.post(base+'/questions', json={**body, 'question': '시장 생일은 언제?'}).json()
    assert unknown['status'] == 'NOT_IN_CONFIRMED' and not unknown['facts']


def test_model_question_id_validation_and_usage(client, monkeypatch):
    c = client
    base, rev = seed(c)
    confirm(c, base, rev)
    c.app.state.runner.model_config['key'] = 'synthetic-not-real-key'
    calls = []
    valid = [True]
    class ModelClient:
        def __init__(self, **kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def post(self, url, headers, json):
            calls.append(json)
            records = __import__('json').loads(json['messages'][1]['content'])['confirmed_facts']
            ref = next(f['id'] for f in records if f['label']=='다음 행동' and '정산' in f['title'])
            return httpx.Response(200, json={'model':'solar-pro4-test', 'usage':{'total_tokens':80}, 'choices':[{'finish_reason':'stop', 'message':{'content':__import__('json').dumps({'paragraphs':[{'text':'정산 승인을 위해 누락된 영수증 제출을 먼저 요청하세요.', 'fact_ids':[ref if valid[0] else 'F999999'], 'background_ids':[]}]})}}]})
    monkeypatch.setattr(questions.httpx, 'Client', ModelClient)
    body = {'question':'정산 다음 행동?', 'expected_revision':rev['id'], 'mode':'llm', 'external_consent':True}
    result = c.post(base+'/questions', json=body)
    assert result.status_code == 200
    answer = result.json()
    assert answer['facts'][0]['value'] == '누락된 영수증 제출 요청'
    assert answer['usage']['total_tokens'] == 80
    assert answer['paragraphs'][0]['text'].startswith('정산 승인을 위해')
    assert c.get('/api/budget').json()['calls'] == 1
    assert 'synthetic-not-real-key' not in result.text
    assert calls[0]['response_format']['json_schema']['strict']
    valid[0] = False
    assert c.post(base+'/questions', json=body).status_code == 422


def test_confirmed_pointer_change_during_question_discards_answer(client, monkeypatch):
    c = client
    base, first = seed(c)
    confirm(c, base, first)
    second = generate(c, base)
    confirm(c, base, second)
    original = main.answer_question
    def changing(*args, **kwargs):
        result = original(*args, **kwargs)
        with c.app.state.store.connect(write=True) as db:
            db.execute('UPDATE cases SET confirmed=? WHERE id=?', (first['id'], base.split('/')[-1]))
        return result
    monkeypatch.setattr(main, 'answer_question', changing)
    result = c.post(base+'/questions', json={'question':'생활문화 기한?', 'expected_revision':second['id']})
    assert result.status_code == 409


def test_schedule_does_not_invent_month_or_recurring_dates():
    items = []
    for n, value in enumerate(['2026-11-01', '2026-11-09', '2026-12-10', '매월 5일', '11월 말']):
        fields = {k: empty_field() for k in ['title', 'due_date', 'status', 'owner']}
        fields['title']['value'] = str(n)
        fields['due_date'].update(value=value, review_status='UNREVIEWED')
        items.append({'id': str(n), 'fields': fields})
    annotate_items(items)
    data = briefing({'id':'r','hash':'h','payload':{'items':items}}, date(2026,11,8))
    assert [len(v) for v in data['groups'].values()] == [1,1,1,1,1,0]
    assert data['groups']['정기 업무'][0]['normalized_date'] is None
    assert data['groups']['일정 확인 필요'][0]['due_date'] == '11월 말'
    assert readiness({'items': items})['missing_fields'] > 0


def test_reader_chat_sources_followup_and_context_bounds(client):
    c=client;base,rev=seed(c)
    item=next(i for i in rev['payload']['items'] if '생활문화' in i['fields']['title']['value'])
    rev=c.patch(base+f'/revisions/{rev["id"]}/items/{item["id"]}',json={'expected_hash':rev['hash'],'fields':{'due_date':'2026-11-27'},'reason':'담당자 일정 확인'}).json()
    confirm(c,base,rev)
    body={'question':'생활문화 기한은?', 'expected_revision':rev['id'],'mode':'local','include_sources':True}
    answer=c.post(base+'/questions',json=body).json()
    assert answer['facts'][0]['value']=='2026-11-27' and answer['facts'][0]['provenance']=='HUMAN_ENTERED'
    assert answer['background'] and all(b['id'] for b in answer['background'])
    follow=c.post(base+'/questions',json={**body,'question':'그럼 담당은?','previous_questions':['생활문화 기한은?']}).json()
    assert len(follow['facts'])==1 and follow['facts'][0]['field']=='owner' and follow['facts'][0]['value']=='문화기획팀'
    assert c.post(base+'/questions',json={**body,'previous_questions':['x']*5}).status_code==422
    assert c.post(base+'/questions',json={**body,'previous_questions':['x'*501]}).status_code==422
    # New uploads are not silently used as evidence for the already confirmed report.
    c.post(base+'/documents',files={'file':('새자료.txt','업무: 생활문화\n기한: 2030-12-30\n참고: 유일비밀대조문구'.encode())})
    generate(c,base)
    answer=c.post(base+'/questions',json={**body,'question':'유일비밀대조문구'}).json()
    assert not answer['facts'] and not answer['background']


def test_conversation_rejects_uncited_and_foreign_references(client, monkeypatch):
    c = client
    base, rev = seed(c); confirm(c, base, rev)
    c.app.state.runner.model_config['key'] = 'synthetic-only'
    response_body = {}
    class ModelClient:
        def __init__(self, **kw): pass
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def post(self, *args, **kw):
            return httpx.Response(200, json={'model':'solar-pro4', 'usage':{'prompt_tokens':10,'completion_tokens':10}, 'choices':[{'finish_reason':'stop','message':{'content':json.dumps({'paragraphs':response_body['paragraphs']})}}]})
    monkeypatch.setattr(questions.httpx, 'Client', ModelClient)
    request = {'question':'정산 다음 행동?', 'expected_revision':rev['id'], 'mode':'llm', 'external_consent':True}
    for paragraph in [
        {'text':'알 수 없는 사실', 'fact_ids':[], 'background_ids':[]},
        {'text':'다른 보고서 내용', 'fact_ids':['F9999'], 'background_ids':[]},
        {'text':'참고자료', 'fact_ids':[], 'background_ids':['B9999']},
    ]:
        response_body.update({'fact_ids':['F1'], 'background_ids':[], 'paragraphs':[paragraph]})
        assert c.post(base+'/questions', json=request).status_code == 422
    response_body.update({'fact_ids':[], 'background_ids':[], 'paragraphs':[]})
    unknown = c.post(base+'/questions', json=request)
    assert unknown.status_code == 200 and unknown.json()['status'] == 'NOT_IN_CONFIRMED'
    budget = c.get('/api/budget').json()
    assert budget['calls'] == 4 and budget['used_usd'] > 0 and budget['unknown_calls'] == 0
