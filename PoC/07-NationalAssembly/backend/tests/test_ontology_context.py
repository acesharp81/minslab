from copy import deepcopy

import pytest

from app.services.meeting_topic_groups import TARGET_ONTOLOGY, attach_meeting_topic_groups, build_meeting_topic_ontology
from app.services.ontology_context import match_topic_context, review_topic_context


def topic(title, parent, quote):
    return {'id': 'structured-topic-test', 'title': title, 'summary': '답변 1건',
            'coverage_origin': 'EVIDENCE_STRUCTURE', 'evidence_ids': ['u1'],
            'speaker_points': [{'summary': quote, 'evidence_ids': ['u1'], 'evidence_span': {
                'parent': parent, 'issue': title, 'quote': quote, 'evidence_id': 'u1',
                'role': 'ANSWER', 'start': 100, 'end': 100 + len(quote),
                'content_hash': 'saved-hash', 'revision_ids': ['r1'], 'segment_ids': ['s1'],
            }}]}


@pytest.mark.parametrize('title,parent,quote,key', [
    ('정상화종합계획 추진 및 당연직 이사 참여', 'TBS 정상화',
     'TBS 정상화종합계획 추진에 따라 당연직 이사 참여를 검토합니다.', 'media-public-communication'),
    ('외부회생위원 보수 지급 구조', '개인회생 제도',
     '외부회생위원 보수는 개인회생 신청인의 예납금에서 지급됩니다.', 'prosecution-judiciary'),
    ('청소년 전용 스마트폰 도입', '청소년 디지털 안전',
     '청소년 전용 스마트폰 도입을 위한 대안기기 보급을 추진합니다.', 'children-digital-safety'),
    ('헌법 84조 소추 범위', '대통령 재판',
     '헌법 84조 소추 범위를 공소유지까지 볼 것인지 검토합니다.', 'constitutional-order'),
    ('선관위 징계의결서 부실 및 청렴의무 위반', '중앙선관위 운영',
     '중앙선관위 징계의결서 부실과 청렴의무 위반을 확인했습니다.', 'public-discipline'),
    ('자율주행자동차 안전조치 공감대 형성', '도로 운행',
     '자율주행자동차 운행 시 사고 예방을 위한 안전조치가 필요합니다.', 'automotive-ev'),
    ('복수직급제 보직자 인사 현황', '경찰 인사',
     '복수직급제 보직자 인사 현황과 개선 방안을 제출하겠습니다.', 'civil-service-personnel'),
])
def test_issue_or_parent_requires_own_source(title, parent, quote, key):
    item = topic(title, parent, quote)
    match = match_topic_context(item, TARGET_ONTOLOGY)
    assert match['key'] == key
    span = match['supporting_spans'][0]
    assert span['quote'] == quote
    assert span['revision_ids'] == ['r1']
    assert span['end'] - span['start'] == len(quote)


@pytest.mark.parametrize('title,parent,quote', [
    ('학생 스마트폰 도입', '청소년 스마트폰 정책', '전세계의 교육·통신 분야 위상 제고가 필요합니다.'),
    ('휴대전화 보급 문제', '청소년 디지털 안전', '앞서 대정부질문에 답변했습니다. 전세계가 주목하고 있습니다.'),
    ('헌재소장 배우자 출장 허위 보고서 의혹', '헌법재판소 국제 협력', '헌법재판소의 초청장과 출장 보고서가 다릅니다.'),
    ('구속 시점 질의', '교육 정책', '구속영장 청구 시점을 말씀드리겠습니다.'),
    ('정부 정책 문제점 나열', '미래대응기금', '미래대응기금 문제점이 있습니다. 다른 정책도 설명하겠습니다.'),
    ('남소 방지 및 연구인력 확충', '헌법재판소법 입법 협력', '남소 방지를 위한 연구인력 확충이 필요합니다.'),
    ('국무총리 제청권 행사', '정부 인사', '국무총리 제청권 행사를 검토합니다.'),
    ('과도한 제압과 구급차 이송', '경찰 대응', '과도한 제압 이후 구급차로 이송됐습니다.'),
])
def test_no_incidental_or_parent_only_assignment(title, parent, quote):
    assert match_topic_context(topic(title, parent, quote), TARGET_ONTOLOGY) is None


@pytest.mark.parametrize('damage', ['revision', 'length', 'reference', 'quote', 'uncertain'])
def test_invalid_source_is_not_classification_evidence(damage):
    item = topic('외부회생위원 보수 지급', '개인회생 제도', '외부회생위원 보수 지급 기준을 정합니다.')
    point = item['speaker_points'][0]
    span = point['evidence_span']
    if damage == 'revision': span['revision_ids'] = []
    if damage == 'length': span['end'] += 1
    if damage == 'reference': span['evidence_id'] = 'another-turn'
    if damage == 'quote': point['summary'] = '바뀐 원문'
    if damage == 'uncertain': span['role'] = 'UNCERTAIN'
    assert review_topic_context(item, TARGET_ONTOLOGY)['reason'] == 'NO_VERIFIED_SOURCE_SPAN'


def test_competing_supported_targets_remain_pending():
    item = topic('통합돌봄 및 개인회생 지원', '복지와 사법', '통합돌봄 및 개인회생 지원을 논의했습니다.')
    result = review_topic_context(item, TARGET_ONTOLOGY)
    assert result['match'] is None
    assert result['reason'] == 'MULTIPLE_SUPPORTED_TARGETS'


def test_context_is_repeatable_preserves_original_and_counts_separately():
    item = topic('외부회생위원 보수 지급', '개인회생 제도', '외부회생위원 보수 지급 기준을 정합니다.')
    brief = {'topics': [item], 'tasks': []}
    original = deepcopy(brief)
    grouped = attach_meeting_topic_groups(brief)
    assert attach_meeting_topic_groups(grouped)['topic_groups'] == grouped['topic_groups']
    result = build_meeting_topic_ontology([brief])
    assert result['metrics']['context_topic_count'] == 1
    assert result['metrics']['ontology_topic_count'] == 1
    assert result['metrics']['policy_topic_count'] == 1
    example = next(g for g in result['groups'] if g['context_topic_count'])['context_examples'][0]
    assert example['authority_status'] == 'PROVISIONAL'
    assert brief == original


@pytest.mark.parametrize('title,parent,quote,key', [
    ('지방노동감독관 제도 신설', '노동 행정',
     '지방노동감독관 제도를 신설하여 노동감독을 확대하겠습니다.', 'youth-employment'),
    ('선거비용 반환 미이행 및 재출마', '선거 제도',
     '당선무효 확정 후 선거비용을 반환하지 않은 사람이 재출마하고 있습니다.', 'elections-public-opinion'),
    ('소방헬기 정비율 저조', '재난 대응',
     '소방헬기 정비율이 낮아 재난 현장 출동에 어려움이 있습니다.', 'public-safety-health'),
    ('D급 소화기 기준 확대', '소방 안전',
     '금속 화재에 대응하기 위해 D급 소화기 기준을 확대해야 합니다.', 'public-safety-health'),
    ('주택 가격 상승 원인', '서울 주거 정책',
     '주택 가격 상승은 공급 부족과 관련이 있습니다.', 'housing-real-estate'),
    ('장애인 활동지원기관 주민세 부과 문제', '장애인 지원',
     '장애인 활동지원기관에 주민세와 가산세가 부과됐습니다.', 'taxation'),
    ('비공개 행정규칙 목록 공개', '법령 관리',
     '비공개 행정규칙 목록을 공개하도록 요청했습니다.', 'government-operations'),
    ('시각장애인 이동권 보장', '보행 지원',
     '시각장애인의 이동권 보장을 위해 보행 환경을 개선합니다.', 'disability-care-services'),
    ('소년원 정신질환자 치료 지원', '소년 보호',
     '소년원 정신질환자 치료 지원과 시설 협력을 강화합니다.', 'correctional-services'),
    ('정상회담 후속 조치 점검', '외교 후속 조치',
     '정상회담 후속 조치별 이행 현황을 점검하고 있습니다.', 'international-cooperation'),
    ('정수장 현대화 및 상수도관 정비', '물 공급',
     '정수장 현대화와 노후 상수도관 정비를 진행합니다.', 'water-resources-climate'),
    ('세제 개편 및 중장기 재정건전성 계획', '재정 건전성',
     '구조적인 문제입니다. 세제 개편을 할 때가 왔습니다.', 'taxation'),
])
def test_expanded_policy_terms_require_the_issues_saved_source(title, parent, quote, key):
    match = match_topic_context(topic(title, parent, quote), TARGET_ONTOLOGY)
    assert match is not None and match['key'] == key
    assert match['supporting_spans'][0]['quote'] == quote


@pytest.mark.parametrize('title,parent,quote', [
    ('소화기 내과 인력 부족', '병원 운영', '소화기 내과 인력이 부족합니다.'),
    ('의사 면허취소 기준', '의료 면허', '의사 면허취소 기준을 논의했습니다.'),
    ('정신의료기관 폐쇄 병동 화재 대비', '병원 안전',
     '정신의료기관 폐쇄 병동의 잠긴 문 때문에 화재 시 탈출이 어렵습니다.'),
    ('공무원 책임보험의 채용비리 연루자 지원 의혹', '책임보험 운영',
     '공무원연금공단에서 책임보험에 가입합니다.'),
    ('선거비용 반환 미이행', '선거비용 제도', '예, 검토하겠습니다.'),
    ('주택 가격 상승 원인', '주택 가격', '다음 안건으로 넘어가겠습니다.'),
])
def test_expanded_terms_do_not_classify_homonyms_venues_or_unsupported_answers(title, parent, quote):
    assert match_topic_context(topic(title, parent, quote), TARGET_ONTOLOGY) is None


def test_short_word_policy_phrases_still_hold_competing_targets():
    item = topic('주택 가격 및 세제 개편', '주거와 조세',
                 '주택 가격과 세제 개편을 함께 논의합니다.')
    result = review_topic_context(item, TARGET_ONTOLOGY)
    assert result['match'] is None
    assert result['reason'] == 'MULTIPLE_SUPPORTED_TARGETS'
