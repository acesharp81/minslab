import pytest
from app.services.structured_document_tasks import document_request_span


def extract(text, role='PROCEDURE'):
    atom={'id':'a','text':text,'offset':0,'evidence_id':'u','content_hash':'h','revision_ids':['r']}
    facet={'issue':'국정감사 안내','role':role,'start':0,'quote':text}
    return document_request_span(atom,facet)


@pytest.mark.parametrize('role',['PROCEDURE','REQUEST'])
@pytest.mark.parametrize('text',[
    '기관증인의 구체적인 명단은 배부해 드린 자료를 참고해 주시기 바랍니다.',
    '보고서는 이미 배부했으니 참조해 주십시오.',
])
def test_distributed_reference_material_is_not_a_new_task(text,role):
    assert extract(text,role) is None


@pytest.mark.parametrize('text',[
    '예산 집행 참고 자료를 제출해 주십시오.',
    '배부 자료를 참고한 뒤 수정 자료를 제출해 주십시오.',
    '명단은 자료를 참고해 주십시오. 별도로 계약 내역을 제출해 주십시오.',
    '산불 피해 복구 계획서를 보내 주시기 바랍니다.',
])
def test_real_document_requests_are_retained(text):
    assert extract(text) is not None


def test_reference_cue_does_not_leave_live_cluster_pending():
    from copy import deepcopy
    from app.services.topic_structure import build_snapshot, validate_response, materialize
    original={'topics':[{'id':'t','evidence_ids':['u']}], 'tasks':[],
              'live_topic_lineage':{'clusters':[{'id':'c','title':'증인 명단 안내','utterance_ids':['u']}]}}
    text='기관증인의 구체적인 명단은 배부해 드린 자료를 참고해 주시기 바랍니다.'
    snapshot=build_snapshot({'brief_id':'b','brief':original,'transcript_hash':'h'},[
        {'utterance_id':'u','text':text,'content_hash':'h','revision_ids':['r'],'segment_ids':['s']}])
    facets=validate_response({'assignments':{a['id']:[{'parent':'국정감사 운영','issue':'증인 명단 안내','role':'PROCEDURE','span_index':0}] for a in snapshot['atoms']}},snapshot['atoms'])
    before=deepcopy((original,snapshot,facets))
    result=materialize(original,snapshot,facets,[],'revision')
    assert result['live_topic_lineage']['unmapped_cluster_count']==0
    assert result['live_topic_lineage']['procedural_cluster_count']==1
    assert result['tasks']==[]
    assert (original,snapshot,facets)==before
