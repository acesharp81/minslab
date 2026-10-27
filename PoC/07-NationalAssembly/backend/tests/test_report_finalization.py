from copy import deepcopy
from unittest.mock import Mock, patch
from app.ingestion.report_finalization import assess
from app.ingestion.meeting_brief_worker import map_unlinked_brief_once
from app.services.live_topic_mapping import MAPPING_VERSION
from app.main import _public_meeting_brief


def structure():
    return {'topic_structure':{'automatic_review':{'status':'COMPLETED'},'rejected':[], 'uncertain':[]},
            'topic_grouping':{'unclassified_topic_count':0},
            'narrative_coverage':{'issue_count':3,'status':'COMPLETE'}}


def test_synthesis_alone_is_not_final():
    assert assess(None,{'status':'PENDING'},[])['phase']=='STRUCTURING'
    assert assess(structure(),{'status':'REVIEW_REQUIRED'},[])['status']=='PENDING'


def test_failed_atoms_and_pending_ontology_or_narratives_cannot_publish():
    s=structure();s['topic_structure']['rejected']=[{'atom_id':'a'}]
    assert assess(s,{'status':'COMPLETED'},[])['phase']=='REVIEWING'
    assert assess(structure(),{'status':'COMPLETED'},[{'topic_id':'t'}])['phase']=='ONTOLOGY'
    s=structure();s['narrative_coverage']['status']='PENDING'
    assert assess(s,{'status':'COMPLETED'},[])['phase']=='NARRATIVE'


def test_genuine_reviewed_source_limits_are_not_forced_to_false_matches():
    s=structure();s['topic_grouping']['unclassified_topic_count']=1;s['topic_structure']['uncertain']=[{'atom_id':'a'}]
    result=assess(s,{'status':'COMPLETED'},[])
    assert result['status']=='COMPLETED' and result['source_limited_topics']==1 and result['source_limited_discussions']==1


def test_api_keeps_draft_readable_without_announcing_completion():
    item={'brief_id':'b','broadcast_id':'m','transcript_hash':'h','source_last_event_cursor':1,'provider':'gemini',
          'model':'fixture','prompt_version':'assembly-meeting-brief/2.0','authority_status':'PROVISIONAL','review_status':'UNREVIEWED','generated_at':'2026-10-26',
          'brief':{'utterance_count':10,'finalization':{'status':'DEFERRED','phase':'ONTOLOGY'}}}
    result=_public_meeting_brief(item,{},include_content=False)
    assert result['brief_status']=='PROCESSING' and result['brief_progress']['status']=='DEFERRED'
    item['brief']['finalization']['status']='COMPLETED'
    assert _public_meeting_brief(item,{},include_content=False)['brief_status']=='READY'


def test_failed_same_version_mapping_is_retried():
    brief={'topics':[], 'live_topic_assignment':{'semantic_mapping_version':MAPPING_VERSION,'semantic_mapping_status':'FAILED'}}
    client=Mock(model='fixture');client.map_live_topics.return_value=({'assignments':[],'unresolved_cluster_ids':[]},{})
    with patch('app.ingestion.meeting_brief_worker.unresolved_live_topic_clusters',return_value=[{'id':'c'}]), patch('app.ingestion.meeting_brief_worker.apply_semantic_mapping',return_value=brief):
        _,result=map_unlinked_brief_once(brief,client)
    assert result['status']=='COMPLETED';client.map_live_topics.assert_called_once()


def test_successful_same_version_mapping_is_not_paid_for_again():
    brief={'topics':[], 'live_topic_assignment':{'semantic_mapping_version':MAPPING_VERSION,'semantic_mapping_status':'COMPLETED'}}
    client=Mock(model='fixture')
    _,result=map_unlinked_brief_once(brief,client)
    assert result['status']=='CACHED';client.map_live_topics.assert_not_called()


def test_ontology_failures_resume_after_utc_reset(monkeypatch):
    from datetime import datetime,timedelta,timezone
    from app.ingestion import ontology_review_worker as worker
    from app.services.ontology_semantic import PROFILE,BATCH_START
    monkeypatch.setattr(worker,'_ontology_match',lambda _:None)
    monkeypatch.setattr(worker,'match_topic_context',lambda *_:None)
    item={'fingerprint':'f','topic_id':'t'}
    monkeypatch.setattr(worker,'review_input',lambda *_:item)
    topic={'id':'t'}
    failed={'status':'FAILED','index':BATCH_START,'request':{'profile':PROFILE,'items':[item]},'error':'ReadTimeout'}
    today=datetime.now(timezone.utc)
    assert worker.pending_items({'topics':[topic]},[{**failed,'created_at':today} for _ in range(3)])==[]
    assert worker.pending_items({'topics':[topic]},[{**failed,'created_at':today-timedelta(days=1)} for _ in range(3)])==[item]


def test_finalization_metadata_does_not_invalidate_source_batches():
    from app.services.topic_structure import source_hash
    brief={'topics':[{'id':'t'}],'tasks':[],'live_topic_lineage':{'clusters':[]}}
    original=source_hash(brief)
    brief['finalization']={'status':'PROCESSING','phase':'ONTOLOGY'}
    assert source_hash(brief)==original
