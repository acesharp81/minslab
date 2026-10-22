from copy import deepcopy
from unittest.mock import patch

import pytest
from app.services.meeting_topic_groups import (
    TARGET_ONTOLOGY, ONTOLOGY_DOMAINS, attach_meeting_topic_groups,
)
from app.services.ontology_extensions import match_topic_extension, EXTENSION_ALIASES


def topic(title, quote, role='ANSWER'):
    return {'id': 't', 'title': title, 'summary': '답변 1건',
            'coverage_origin': 'EVIDENCE_STRUCTURE', 'evidence_ids': ['u'],
            'speaker_points': [{'summary': quote, 'evidence_ids': ['u'], 'evidence_span': {
                'parent': title, 'quote': quote, 'evidence_id': 'u', 'role': role,
                'start': 10, 'end': 10 + len(quote), 'content_hash': 'hash', 'revision_ids': ['r'],
            }}]}


@pytest.mark.parametrize('title,quote,key', [
    ('양형 적정성에 대한 국민 눈높이', '양형의 적정성에 대한 국민들의 평가를 살펴야 합니다.', 'prosecution-judiciary'),
    ('선관위법 개정 필요성', '선관위법 개정 필요성을 설명합니다.', 'elections-public-opinion'),
    ('청년 국민연금 첫 보험료 지원', '청년 국민연금 첫 보험료 지원을 추진합니다.', 'welfare-care-family'),
    ('청산연금방지법 입법 성과', '청산연금방지법 발의 이후 조합원의 청산유보금을 배당했습니다.', 'housing-real-estate'),
    ('행정통합 걸림돌 해소', '행정통합 걸림돌을 해소해야 합니다.', 'local-council-autonomy'),
    ('석포제련소 환경 책임 검토', '석포제련소 환경 책임 검토가 필요합니다.', 'environment-waste'),
    ('공중보건의 배치 확대', '공중보건의 배치 확대 방안을 검토합니다.', 'healthcare-medical-system'),
])
def test_new_topics_require_matching_original_quote(title, quote, key):
    item = topic(title, quote)
    match = match_topic_extension(item, TARGET_ONTOLOGY)
    assert match['key'] == key
    assert match['supporting_spans'][0]['quote'] == quote
    assert match_topic_extension(topic(title, '검토하고 나중에 말씀드리겠습니다.'), TARGET_ONTOLOGY) is None
    assert match_topic_extension(topic(title, quote, 'UNCERTAIN'), TARGET_ONTOLOGY) is None


def test_existing_hierarchy_assignments_and_report_structure_are_preserved():
    assert set(EXTENSION_ALIASES) <= {key for key, _, _ in TARGET_ONTOLOGY}
    assert {key for _, _, _, keys in ONTOLOGY_DOMAINS for key in keys} == {key for key, _, _ in TARGET_ONTOLOGY}
    brief = {'topics': [topic('공중보건의 배치 확대', '공중보건의 배치 확대가 필요합니다.')],
             'tasks': [{'id': 'task', 'title': '배치 계획 제출', 'topic_id': 't', 'evidence_ids': ['u']}],
             'live_topic_lineage': {'mapped_cluster_count': 44, 'procedural_cluster_count': 4}}
    original = deepcopy(brief)
    result = attach_meeting_topic_groups(brief)
    assert brief == original
    for field in ('topics', 'tasks', 'live_topic_lineage'):
        assert result[field] == original[field]
    # Existing reviewed assignments take precedence even when new vocabulary matches.
    with patch('app.services.meeting_topic_groups.semantic_match', return_value={
        'key': 'public-safety-health', 'title': '국민안전·보건 대응',
        'matched_keyword': 'confirmed', 'matched_field': 'source', 'score': 1,
    }):
        result = attach_meeting_topic_groups(brief)
    assert result['topic_groups'][0]['key'] == 'public-safety-health'


def test_conflicting_targets_and_invalid_source_remain_unclassified():
    item = topic('아동학대 및 가정폭력 보호', '아동학대 및 가정폭력 보호를 논의했습니다.')
    assert match_topic_extension(item, TARGET_ONTOLOGY) is None
    item = topic('행정통합 걸림돌 해소', '행정통합 걸림돌 해소를 요구합니다.')
    item['speaker_points'][0]['evidence_span']['end'] += 1
    assert match_topic_extension(item, TARGET_ONTOLOGY) is None
