from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import Mock
import json
import pytest
import requests
from app.config import Settings
from app.services import auxiliary_models as aux
from app.db.auxiliary_model_budget import AuxiliaryUnavailable
from app.services.meeting_brief import MalformedMeetingBriefResponse
from app.ingestion import topic_structure_worker as structure, meeting_brief_worker as meeting
from test_structure_provider_policy import settings as policy_settings


def settings(**values):
    return Settings(_env_file=None, groq_api_key='fixture',groq_aux_enabled=True,**values)


@pytest.fixture
def budget(monkeypatch):
    @contextmanager
    def connect(_):yield object()
    b=Mock();b.reserve.return_value='reservation'
    monkeypatch.setattr(aux,'connect',connect)
    monkeypatch.setattr(aux,'AuxiliaryModelBudget',lambda _:b)
    return b


def response(code=200,finish='stop',usage=True):
    r=Mock(status_code=code,headers={},text='')
    r.json.return_value={'choices':[{'message':{'content':'{"result":"근거 요약"}'},'finish_reason':finish}],
                         'usage':{'total_tokens':12} if usage else {}}
    return r


def test_oversized_input_skips_before_budget_and_network(budget,monkeypatch):
    post=Mock();monkeypatch.setattr(aux.requests,'post',post)
    with pytest.raises(AuxiliaryUnavailable,match='INPUT_TOO_LARGE'):
        aux.AuxiliaryMeetingBriefClient(settings(),'groq')._post('한'*4000,{},'test')
    post.assert_not_called();budget.reserve.assert_not_called()


def test_rate_or_daily_gate_skips_network(budget,monkeypatch):
    budget.reserve.side_effect=AuxiliaryUnavailable('AUXILIARY_RATE_WAIT')
    post=Mock();monkeypatch.setattr(aux.requests,'post',post)
    with pytest.raises(AuxiliaryUnavailable):aux.AuxiliaryMeetingBriefClient(settings(),'groq')._post('한국어',{},'test')
    post.assert_not_called()


def test_success_settles_actual_tokens_and_cannot_override_with_paid_model(budget,monkeypatch):
    post=Mock(return_value=response());monkeypatch.setattr(aux.requests,'post',post)
    result,metadata=aux.AuxiliaryMeetingBriefClient(settings(),'groq')._post('한국어',{},'test',model_override='paid-model')
    assert result=={'result':'근거 요약'} and metadata['provider']=='groq'
    assert post.call_args.kwargs['json']['model']=='openai/gpt-oss-120b'
    assert budget.settle.call_args.args[-1]=='COMPLETED'
    assert budget.reserve.call_args.kwargs['interval']==65


def test_truncated_output_never_published_but_usage_counted(budget,monkeypatch):
    monkeypatch.setattr(aux.requests,'post',Mock(return_value=response(finish='length')))
    with pytest.raises(MalformedMeetingBriefResponse):aux.AuxiliaryMeetingBriefClient(settings(),'groq')._post('한국어',{},'test')
    assert budget.settle.call_args.args[1]['usage']['total_tokens']==12


def test_timeout_keeps_unknown_reservation_charged(budget,monkeypatch):
    monkeypatch.setattr(aux.requests,'post',Mock(side_effect=requests.Timeout()))
    with pytest.raises(requests.Timeout):aux.AuxiliaryMeetingBriefClient(settings(),'groq')._post('한국어',{},'test')
    assert budget.settle.call_args.args[-1]=='UNKNOWN'


def test_plain_429_is_not_daily_exhaustion(budget,monkeypatch):
    monkeypatch.setattr(aux.requests,'post',Mock(return_value=response(code=429)))
    with pytest.raises(requests.HTTPError):aux.AuxiliaryMeetingBriefClient(settings(),'groq')._post('한국어',{},'test')
    budget.cooldown.assert_called_once_with('groq',65)


def test_gemini_preserves_schema_and_accounts_thinking(budget,monkeypatch):
    r=response();r.json.return_value={'candidates':[{'finishReason':'STOP','content':{'parts':[{'text':'{"ok":true}'}]}}],
        'usageMetadata':{'promptTokenCount':10,'candidatesTokenCount':2,'thoughtsTokenCount':3,'totalTokenCount':15}}
    post=Mock(return_value=r);monkeypatch.setattr(aux.requests,'post',post)
    s=settings(gemini_aux_enabled=True,gemini_api_key='fixture')
    _,meta=aux.AuxiliaryMeetingBriefClient(s,'gemini')._post('요약',{'type':'object'},'test')
    assert meta['usage']['total_tokens']==15 and meta['usage']['completion_tokens']==5
    assert budget.reserve.call_args.kwargs['zone']=='America/Los_Angeles'
    assert '?key=' not in post.call_args.args[0]


@pytest.mark.parametrize('capacity,expected',[(True,['nvidia','openrouter','groq']),(None,['nvidia','openrouter','groq']),(False,['nvidia','groq','openai'])])
def test_auxiliaries_precede_openai_preserving_nim_priority(monkeypatch,capacity,expected):
    s=policy_settings();s.groq_aux_enabled=True;s.groq_api_key='fixture';s.groq_aux_model='openai/gpt-oss-120b'
    monkeypatch.setattr(structure,'get_settings',lambda:s)
    monkeypatch.setattr(meeting,'openrouter_brief_has_capacity',lambda _:capacity)
    assert [c.provider for c in structure.clients("verification")]==expected
    assert meeting.next_brief_provider(s,'groq',RuntimeError())==('openai' if capacity is False else None)


def test_disabled_credentials_do_not_enable_provider():
    assert aux.enabled_auxiliaries(Settings(_env_file=None,gemini_api_key='fixture'))==[]


def test_all_providers_get_bounded_retry_slot():
    from app.services.structure_retry import retry_allowance
    assert retry_allowance([],round_size=4)==4
    assert retry_allowance([],round_size=100)==5


def test_groq_narrative_subsets_keep_complete_source_context(monkeypatch):
    from app.ingestion.structured_narrative_worker import post_with_nim_retry
    from test_structured_narrative import fixture
    from app.services.structured_narrative import prompt, schema
    _,items,_=fixture()
    client=Mock(provider='groq')
    client.fits_request.side_effect=lambda p,s:len(s['properties'])==1
    client._post.return_value=({'one':'result'},{'usage':{'total_tokens':10}})
    original=json.dumps(items,ensure_ascii=False)
    post_with_nim_retry(client,items)
    assert client._post.call_args.args[:2]==(prompt(items[:1]),schema(items[:1]))
    assert json.dumps(items,ensure_ascii=False)==original


def test_idle_mapping_tries_auxiliary_before_openai(monkeypatch):
    s=policy_settings();s.meeting_brief_provider='auto';s.groq_aux_enabled=True;s.groq_api_key='fixture'
    monkeypatch.setattr(meeting,'get_settings',lambda:s)
    monkeypatch.setattr(meeting,'eligible_broadcast_ids',lambda *_:[])
    monkeypatch.setattr(meeting,'recent_openai_mapping_candidate',lambda:'test')
    monkeypatch.setattr(meeting,'openrouter_brief_has_capacity',lambda _:False)
    monkeypatch.setattr(meeting,'openai_mapping_budget_available',lambda _:True)
    mapping=Mock(side_effect=[AuxiliaryUnavailable(),{'status':'MAPPED'}])
    monkeypatch.setattr(meeting,'map_existing_brief_one',mapping)
    assert meeting.process_available()[0]['status']=='MAPPED'
    assert [c.kwargs['provider_override'] for c in mapping.call_args_list]==['groq','openai']


@pytest.mark.parametrize('capacity,expected',[
    (True,['nvidia','openrouter','gemini','groq']),
    (None,['nvidia','openrouter','gemini','groq']),
    (False,['nvidia','gemini','groq','openai']),
])
def test_both_confirmed_auxiliaries_follow_nim_and_gate_openai(monkeypatch,capacity,expected):
    s=policy_settings()
    for provider,model in [('gemini','gemini-3.1-flash-lite'),('groq','openai/gpt-oss-120b')]:
        setattr(s,provider+'_aux_enabled',True)
        setattr(s,provider+'_api_key','fixture')
        setattr(s,provider+'_aux_model',model)
    monkeypatch.setattr(structure,'get_settings',lambda:s)
    monkeypatch.setattr(meeting,'openrouter_brief_has_capacity',lambda _:capacity)
    assert [c.provider for c in structure.clients("verification")]==expected
    assert meeting.next_brief_provider(s,'openrouter',RuntimeError())=='gemini'
    assert meeting.next_brief_provider(s,'gemini',RuntimeError())=='groq'
    assert meeting.next_brief_provider(s,'groq',RuntimeError())==('openai' if capacity is False else None)


def test_gemini_final_schema_retains_contract_without_expensive_grammar_bounds(budget,monkeypatch):
    from app.services.meeting_brief import brief_response_schema
    schema=brief_response_schema()
    original=json.dumps(schema,sort_keys=True)
    r=response();r.json.return_value={'candidates':[{'finishReason':'STOP','content':{'parts':[{'text':json.dumps({'headline':'자료 없음','summary':'자료 미제공','topics':[],'tasks':[]})}]}}], 'usageMetadata':{'totalTokenCount':64}}
    post=Mock(return_value=r);monkeypatch.setattr(aux.requests,'post',post)
    client=aux.AuxiliaryMeetingBriefClient(settings(gemini_aux_enabled=True,gemini_api_key='fixture'),'gemini')
    client._post('요약',schema,'meeting_brief')
    config=post.call_args.kwargs['json']['generationConfig']
    wire=config['responseJsonSchema']
    assert wire['required']==schema['required']
    assert 'maxItems' not in wire['properties']['topics']
    assert 'maxItems' in wire['properties']['topics']['description']
    assert config['maxOutputTokens']==32768
    assert budget.reserve.call_args.args[2]==client.estimated_request_tokens('요약',schema)
    assert json.dumps(schema,sort_keys=True)==original
    assert post.call_args.kwargs['timeout']==300


@pytest.mark.parametrize('value,schema',[
    ('abcd',{'maxLength':3}), ([],{'minItems':1}),
    ({'nested':['toolong']},{'properties':{'nested':{'items':{'maxLength':3}}}}),
])
def test_omitted_wire_bounds_are_enforced_locally(value,schema):
    with pytest.raises(ValueError,match='SCHEMA_BOUND'):aux.validate_local_bounds(value,schema)


def test_invalid_gemini_bound_keeps_usage_and_never_returns_partial_result(budget,monkeypatch):
    r=response();r.json.return_value={'candidates':[{'finishReason':'STOP','content':{'parts':[{'text':'{"title":"too long"}'}]}}], 'usageMetadata':{'totalTokenCount':20}}
    monkeypatch.setattr(aux.requests,'post',Mock(return_value=r))
    client=aux.AuxiliaryMeetingBriefClient(settings(gemini_aux_enabled=True,gemini_api_key='fixture'),'gemini')
    with pytest.raises(MalformedMeetingBriefResponse):
        client._post('요약',{'properties':{'title':{'type':'string','maxLength':3}}},'test')
    assert budget.settle.call_args.args[1]['usage']['total_tokens']==20
    assert budget.settle.call_args.args[-1]!='COMPLETED'


@pytest.mark.parametrize('provider',['gemini','groq'])
def test_completed_auxiliary_report_is_ready_and_stale_input_still_waits(provider):
    from app.main import _public_meeting_brief
    from app.services.meeting_brief import PROMPT_VERSION
    item={'brief_id':'b','broadcast_id':'m','transcript_hash':'h','source_last_event_cursor':7,
          'provider':provider,'model':'fixture','prompt_version':PROMPT_VERSION,
          'authority_status':'PROVISIONAL','review_status':'UNREVIEWED','generated_at':'2026-10-26T00:00:00Z','brief':{'utterance_count':10}}
    assert _public_meeting_brief(item,{},include_content=False)['brief_status']=='READY'
    progress={'transcript_hash':'new','current_source_last_event_cursor':8,'status':'PROCESSING'}
    assert _public_meeting_brief(item,progress,include_content=False)['brief_status']=='PROCESSING'


def test_gemini_full_report_fits_but_daily_budget_and_input_ceiling_remain(budget,monkeypatch):
    from app.services.meeting_brief import brief_response_schema
    client=aux.AuxiliaryMeetingBriefClient(settings(gemini_aux_enabled=True,gemini_api_key='fixture'),'gemini')
    schema=brief_response_schema()
    assert client.fits_request('x'*90800,schema)
    assert not client.fits_request('x'*150000,schema)
    budget.reserve.side_effect=AuxiliaryUnavailable('AUXILIARY_DAILY_LIMIT')
    post=Mock();monkeypatch.setattr(aux.requests,'post',post)
    with pytest.raises(AuxiliaryUnavailable,match='DAILY_LIMIT'):client._post('x'*90800,schema,'meeting_brief')
    assert budget.reserve.call_args.kwargs['token_limit']==300000
    post.assert_not_called()
def test_request_specific_model_error_does_not_disable_platform_for_hour():
    from types import SimpleNamespace
    from app.services.auxiliary_models import failure_cooldown
    for status in (400,404,500):
        assert failure_cooldown('groq',SimpleNamespace(status_code=status)) == 65
    for status in (401,403):
        assert failure_cooldown('groq',SimpleNamespace(status_code=status)) == 3600

