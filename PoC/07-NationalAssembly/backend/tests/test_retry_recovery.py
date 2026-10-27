from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock
import pytest
from app.ingestion import structure_review_worker as review, meeting_brief_worker as meeting
from app.services.structure_retry import retry_pool, review_retry_history
from app.services.compact_brief_ids import encode, transform
from app.services.meeting_brief import MalformedMeetingBriefResponse
from app.db.openai_daily_budget import DailyTokenLimitReached


def test_compact_references_roundtrip_preserves_every_source_and_does_not_replace_prose():
    ids={'long-source-001','long-source-002'}
    analyses=[{'topics':[{'summary':'e0라는 발언도 문장 그대로 보존', 'evidence_ids':sorted(ids)}]}]
    wire,clusters,evidence,refs=encode(analyses,[{'id':'long-cluster','title':'정책'}],ids)
    assert transform(wire,evidence,refs)==analyses
    assert transform({'live_topic_cluster_ids':[clusters[0]['id']]},evidence,refs)=={'live_topic_cluster_ids':['long-cluster']}
    assert len(str(wire))<len(str(analyses))


def test_provider_rotation_wraps_and_cooled_round_restarts_at_nim():
    history=[{'status':'FAILED','request':{'schema_revision':2},'attempt':i,'error':'AuxiliaryUnavailable','created_at':datetime.now(timezone.utc)} for i in range(1,4)]
    pool=['nim','gemini','groq','openai']
    assert retry_pool(pool,[history])==['openai','nim','gemini','groq']
    for h in history:h['created_at']-=timedelta(hours=1)
    assert retry_pool(pool,[history])==pool


def test_review_failures_reset_at_utc_midnight_without_losing_success():
    old={'status':'FAILED','created_at':datetime.now(timezone.utc)-timedelta(days=1)}
    assert review_retry_history([old])==[]
    assert review_retry_history([{**old,'status':'READY'}])


def test_length_error_is_five_minutes_not_six_hours():
    assert meeting.brief_retry_hours(MalformedMeetingBriefResponse({'finish_reason':'length'}))==5/60


def test_deferred_provider_does_not_block_other_free_provider(monkeypatch):
    from test_meeting_brief_provider_pool import settings
    s=settings();s.gemini_aux_enabled=True;s.gemini_api_key='fixture';s.groq_aux_enabled=False
    monkeypatch.setattr(meeting,'get_settings',lambda:s)
    monkeypatch.setattr(meeting,'eligible_broadcast_ids',lambda *_:['broadcast'])
    monkeypatch.setattr(meeting,'meeting_brief_identity',lambda *_:('nvidia','fixture','v'))
    monkeypatch.setattr(meeting,'openrouter_brief_has_capacity',lambda _:False)
    generate=Mock(side_effect=[{'status':'DEFERRED'},{'status':'GENERATED'}]);monkeypatch.setattr(meeting,'generate_one',generate)
    assert meeting.process_available()[0]['status']=='GENERATED'
    assert [c.kwargs['provider_override'] for c in generate.call_args_list]==['nvidia','gemini']


def test_review_budget_error_is_saved_and_next_model_runs(monkeypatch):
    connection=MagicMock();connection.execute.side_effect=lambda sql,*_:SimpleNamespace(fetchone=lambda:('ENDED',) if 'lifecycle_status' in sql else (True,))
    @contextmanager
    def connect(_):yield connection
    repo=MagicMock();repo.batches.return_value=[];repo.snapshot.return_value={}
    repo.ready_current.return_value={'topic_structure':{'revision_id':'s'},'topic_groups':[],'topics':[]}
    monkeypatch.setattr(review,'connect',connect);monkeypatch.setattr(review,'get_settings',lambda:SimpleNamespace(database_url='fixture'))
    monkeypatch.setattr(review,'TopicStructureRepository',lambda _:repo)
    monkeypatch.setattr(review,'MeetingBriefRepository',lambda _:SimpleNamespace(latest=lambda _:{'brief_id':'b'}))
    monkeypatch.setattr(review,'review_candidates',lambda *_:[{'profile':'test','atom':{'id':'a'},'targets':[]}])
    monkeypatch.setattr(review,'review_prompt',lambda _:'prompt');monkeypatch.setattr(review,'review_schema',lambda _:{});monkeypatch.setattr(review,'pace_nim',lambda _:None)
    monkeypatch.setattr(review,'validated_review',lambda *_:[]);monkeypatch.setattr(review,'materialize',lambda *_:{'topic_structure':{'uncertain':[]}})
    paid=SimpleNamespace(provider='openai',model='test',_post=Mock(side_effect=DailyTokenLimitReached()))
    free=SimpleNamespace(provider='gemini',model='test',_post=Mock(return_value=({},{})))
    monkeypatch.setattr(review,'clients',lambda *_:[paid,free])
    result=review.process_one('b')
    assert result['status']=='PROCESSING' and result['batches']==1
    assert [call.args[-1] for call in repo.record.call_args_list]==['DAILY_TOKEN_LIMIT',None]
    free._post.assert_called_once()


def test_valid_review_atoms_survive_one_bad_topic_without_new_model_call(monkeypatch):
    from app.services import structure_review as service, topic_structure
    request={'profile':'review','atoms':[{'id':x} for x in 'abcd'],'targets':[{'atom_id':x} for x in 'abcd']}
    response={'assignments':{x:[] for x in 'abcd'},'reasons':{x:'원문 확인' for x in 'abcd'}}
    monkeypatch.setattr(service,'validated_review',lambda *_:[])
    monkeypatch.setattr(topic_structure,'materialize',lambda *_:{'topic_structure':{'uncertain':[{'atom_id':'d','uncertainty_reason':'ISSUE_SOURCE_MISMATCH'}]}})
    req,res=service.valid_review_subset(request,response,{},set('abcd'))
    assert [x['id'] for x in req['atoms']]==list('abc')
    assert set(res['assignments'])==set(res['reasons'])==set('abc')
    assert len(response['assignments'])==4


def test_completed_reduction_parts_resume_without_repeating_timed_out_parent(monkeypatch):
    from app.services.meeting_brief import NvidiaMeetingBriefClient
    base={'title':'예산 심사','summary':'예산 집행 적정성을 점검했다.','speaker_points':[],'evidence_ids':['u-1']}
    chunk={'topics':[{**base,'tasks':[]}]}
    final={'headline':'예산 심사 결과','summary':'예산 집행 현황과 후속 과제를 논의했다.',
           'topics':[{**base,'title':t,'live_topic_cluster_ids':[]} for t in ['예산 심사','집행 현황','후속 과제']], 'tasks':[]}
    client=NvidiaMeetingBriefClient('fixture',model='fixture',base_url='https://fixture.invalid')
    post=Mock(return_value=(final,{}));monkeypatch.setattr(client,'_post',post)
    utterance={'utterance_id':'u-1','text':'예산 심사와 집행 현황을 논의합니다.','speaker_label':'화자 미확인'}
    monkeypatch.setattr('app.services.meeting_brief.iter_meeting_chunks',lambda _:[[utterance]]*9)
    client.generate({'title':'예산 회의','committee_name':'예산결산특별위원회'},[utterance],
        load_chunk=lambda index,_: {'reduction_split':True,'reduction_parts':[chunk,chunk]} if index==1001 else chunk)
    assert post.call_count==1
    assert post.call_args.args[2]=='meeting_brief'


def test_nim_final_length_retries_once_with_compact_ids_and_restores_evidence(monkeypatch):
    from app.services.meeting_brief import NvidiaMeetingBriefClient
    source='original-source-reference-1234567890'
    base={'title':'예산 심사','summary':'예산 집행 적정성을 점검했다.','speaker_points':[],'evidence_ids':[source]}
    chunk={'topics':[{**base,'tasks':[]}]}
    final={'headline':'예산 심사 결과','summary':'예산 집행 현황과 후속 과제를 논의했다.',
           'topics':[{**base,'title':t,'evidence_ids':['e0'],'live_topic_cluster_ids':[]} for t in ['예산 심사','집행 현황','후속 과제']], 'tasks':[]}
    client=NvidiaMeetingBriefClient('fixture',model='fixture',base_url='https://fixture.invalid')
    post=Mock(side_effect=[MalformedMeetingBriefResponse({'finish_reason':'length'}),(final,{})])
    monkeypatch.setattr(client,'_post',post);monkeypatch.setattr('app.services.meeting_brief.time.sleep',lambda _:None)
    utterance={'utterance_id':source,'text':'예산 심사와 집행 현황을 논의합니다.','speaker_label':'화자 미확인'}
    result=client.generate({'title':'예산 회의','committee_name':'예산결산특별위원회'},[utterance],load_chunk=lambda *_:chunk)
    assert post.call_count==2
    assert source not in post.call_args_list[0].args[0]
    assert all(t['evidence_ids']==[source] for t in result.brief['topics'])


def test_incomplete_but_progressing_narrative_is_not_a_retry_failure():
    from app.ingestion.report_finalization import made_progress
    assert made_progress({'status':'PENDING','batches':[{'status':'PARTIAL','salvaged_issues':3},{'status':'READY'}]})
    assert not made_progress({'status':'PENDING','batches':[{'status':'BUDGET_DEFERRED'}]})
    assert not made_progress({'status':'PARTIAL','batches':[{'status':'PARTIAL','error':'invalid'}]})
