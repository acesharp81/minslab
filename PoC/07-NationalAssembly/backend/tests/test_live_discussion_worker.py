from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import UUID

from app.ingestion import live_discussion_worker as worker
from app.ingestion import meeting_brief_worker, topic_structure_worker

BID='07426947-2688-4272-9dd6-24e35605a0eb'


def setup_worker(monkeypatch):
    conn=Mock();conn.execute.return_value.fetchone.side_effect=lambda: (True,)
    @contextmanager
    def connect(_):yield conn
    monkeypatch.setattr(worker,'connect',connect)
    monkeypatch.setattr(worker,'get_settings',lambda:SimpleNamespace(database_url='test'))
    monkeypatch.setattr(worker,'summary_identity',lambda _:('p','m','v'))
    monkeypatch.setattr(worker,'LiveRepository',lambda _:SimpleNamespace(broadcast_transcript_snapshot=lambda *a,**k:{'segments':[]}))
    repo=Mock();repo.latest.return_value={'groups':{},'assignments':{}}
    monkeypatch.setattr(worker,'LiveDiscussionRepository',lambda _:repo)
    monkeypatch.setattr(worker,'SummaryRepository',lambda _:Mock())
    monkeypatch.setattr(topic_structure_worker,'pace_nim',lambda _:None)
    worker._retry_after.clear()
    return repo


def test_cli_string_uuid_loads_summaries_and_classifies_without_rewriting(monkeypatch):
    repo=setup_worker(monkeypatch)
    def prepare(c,bid,*a,**kw):
        assert isinstance(bid,UUID)
        return [{'utterance_id':'turn-1','content_hash':'hash','first_cursor':1,'last_cursor':2,
                 'summary_kind':'AI_CACHED','summary':'자료 제출 요구','is_final':True,
                 'live_insight':{'topic':'집행 자료','topic_key':'집행 자료'}}]
    monkeypatch.setattr(meeting_brief_worker,'prepare_brief_utterances',prepare)
    client=SimpleNamespace(provider='nvidia',model='test',_post=lambda *a:({'groups':[{'id':'new-1','title':'예산 집행','scope':'예산 자료 제출','utterance_ids':['u0']}]},{}))
    monkeypatch.setattr(topic_structure_worker,'clients',lambda:[client])
    result=worker.process_one(BID)
    assert result['status']=='CLASSIFIED' and result['classified']==1
    repo.save.assert_called_once()


def test_no_unclassified_turns_does_not_call_provider(monkeypatch):
    repo=setup_worker(monkeypatch)
    monkeypatch.setattr(meeting_brief_worker,'prepare_brief_utterances',lambda *a,**kw:[])
    pool=Mock();monkeypatch.setattr(topic_structure_worker,'clients',pool)
    assert worker.process_one(BID)['status']=='CACHED'
    pool.assert_not_called();repo.save.assert_not_called()


def test_invalid_response_keeps_previous_groups_and_defers(monkeypatch):
    repo=setup_worker(monkeypatch)
    monkeypatch.setattr(meeting_brief_worker,'prepare_brief_utterances',lambda *a,**kw:[{'utterance_id':'turn-1','content_hash':'hash','first_cursor':1,'summary_kind':'AI_CACHED','summary':'질의','is_final':True,'live_insight':{'topic':'예산'}}])
    monkeypatch.setattr(topic_structure_worker,'clients',lambda:[SimpleNamespace(provider='nvidia',model='test',_post=lambda *a:({'groups':[]},{}))])
    assert worker.process_one(BID)['status']=='RETRY_WAIT'
    repo.save.assert_not_called()
    assert worker.process_one(BID)['status']=='RETRY_WAIT'
