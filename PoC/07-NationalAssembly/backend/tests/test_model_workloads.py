from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from app.services.model_workloads import openai_limit,INTEGRATION_SCHEMAS
from app.services.meeting_brief import OpenAIMeetingBriefClient
from app.db.openai_daily_budget import DailyTokenLimitReached
from app.ingestion import topic_structure_worker as structure,meeting_brief_worker as meeting
from test_structure_provider_policy import settings


def test_only_integration_can_use_the_protected_300k():
    s=SimpleNamespace(openai_daily_token_limit=650000,openai_integration_reserved_tokens=300000)
    assert all(openai_limit(s,name)==650000 for name in INTEGRATION_SCHEMAS)
    assert openai_limit(s,'discussion_context_review')==350000
    assert openai_limit(s,'meeting_chunk_analysis')==350000


def test_general_pool_never_spends_openai_capacity(monkeypatch):
    monkeypatch.setattr(structure,'get_settings',settings)
    monkeypatch.setattr(meeting,'openrouter_brief_has_capacity',lambda _:False)
    assert [c.provider for c in structure.clients()]==['nvidia']
    assert [c.provider for c in structure.clients('integration')]==['openai','nvidia']
    assert [c.provider for c in structure.clients('verification')]==['nvidia','openai']


def test_zero_output_allowance_skips_even_input_count_network(monkeypatch):
    error=DailyTokenLimitReached('reserved');error.skip_input_count=True
    reserve=Mock(side_effect=error);post=Mock()
    monkeypatch.setattr('app.services.meeting_brief.requests.post',post)
    client=OpenAIMeetingBriefClient('fixture',model='fixture',base_url='https://fixture.invalid',
        reserve_tokens=Mock(),settle_tokens=Mock(),reserve_for_workload=reserve)
    with pytest.raises(DailyTokenLimitReached):client._post('요약',{},'meeting_brief')
    post.assert_not_called();assert reserve.call_args.args[1]=='meeting_brief'


def test_nim_reduction_timeout_splits_and_reuses_completed_batches(monkeypatch):
    import requests
    from app.services.meeting_brief import NvidiaMeetingBriefClient
    base={'title':'예산 심사','summary':'예산 집행 적정성을 점검했다.','speaker_points':[],'evidence_ids':['u-1']}
    chunk={'topics':[{**base,'tasks':[]}]}
    final={'headline':'예산 심사 결과','summary':'예산 집행 현황과 후속 과제를 논의했다.',
           'topics':[{**base,'title':title,'live_topic_cluster_ids':[]} for title in ['예산 심사','집행 현황','후속 과제']], 'tasks':[]}
    client=NvidiaMeetingBriefClient('fixture',model='fixture',base_url='https://fixture.invalid')
    post=Mock(side_effect=[requests.ReadTimeout(),(chunk,{}),(chunk,{}),(final,{})]);monkeypatch.setattr(client,'_post',post)
    utterance={'utterance_id':'u-1','text':'예산 심사와 집행 현황을 논의합니다.','speaker_label':'화자 미확인'}
    monkeypatch.setattr('app.services.meeting_brief.iter_meeting_chunks',lambda _:[[utterance]]*9)
    saved=[]
    result=client.generate({'title':'예산 회의','committee_name':'예산결산특별위원회'},[utterance],
        load_chunk=lambda index,_:chunk if index<=9 or index==1002 else None,
        save_chunk=lambda index,*_:saved.append(index))
    assert saved==[1001,10011,10012,1001]
    assert post.call_count==4 and result.brief['headline']=='예산 심사 결과'
