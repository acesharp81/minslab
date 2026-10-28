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


@pytest.mark.parametrize('text',[
    '그러면 의사진행발언 및 자료 요청 요구를 먼저 받도록 하겠습니다 용혜인 위원님 말씀해 주십시오',
    '그러면 의사진행발언과 자료제출 요구를 우선 자료제출 의사진행발언과 자료제출 요구를 섞어서 같이 그렇게 하도록 하겠습니다',
    '권영진 위원님 광명기준 순으로 하고 토론과 의사진행발언 자료제출 요구 마무리하겠습니다',
])
def test_announcing_document_request_floor_is_not_itself_a_task(text):
    assert extract(text) is None


def test_floor_announcement_does_not_hide_following_concrete_request():
    assert extract('자료제출 요구를 먼저 받도록 하겠습니다. 예산 집행 내역을 제출해 주십시오.') is not None


def test_submission_word_in_procedural_title_does_not_enable_elliptical_fallback():
    text = '권영진 위원님 순으로 하고 토론과 의사진행발언 자료제출 요구 마무리하겠습니다'
    atom = {'id': 'a', 'text': text, 'offset': 0, 'evidence_id': 'u'}
    facet = {'issue': '의사진행발언 자료제출 요구 마무리', 'role': 'PROCEDURE', 'start': 0, 'quote': text}
    assert document_request_span(atom, facet) is None


def test_inviting_members_to_make_requests_is_floor_management():
    text = '박형수 간사 자료제출 요구하시고 김남희 위원 의사진행발언하시고 곽규택 위원 자료제출 요구하십시오 시간은 2분씩 드리겠습니다'
    assert extract(text) is None
    assert extract(text + '. 별도로 계약 내역을 제출해 주십시오.') is not None
