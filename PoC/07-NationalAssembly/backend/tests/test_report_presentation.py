from contextlib import contextmanager
from copy import deepcopy
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.main import _meeting_brief_markdown, ended_live_broadcast_brief_evidence
from app.services.report_presentation import report_summary


def fixture():
    text = '법원의 안전 대책에 관한 자료를 제출해 주십시오.'
    summary = '법원 안전 대책의 자료 제출이 요구됐다.'
    brief = {'topics': [{'id': 't', 'title': '법원 안전 대책', 'summary': summary, 'evidence_ids': ['u']}]}
    brief['topics'][0]['speaker_points'] = [{'id': 'p', 'summary': '법원 안전 관련 자료를 요청했다.', 'evidence_ids': ['u']}]
    brief['topic_groups'] = [{'id': 'g', 'title': '사법 제도', 'topic_ids': ['t']}]
    snapshot = {'atoms': [{'id': 'a', 'evidence_id': 'u', 'text': text, 'offset': 0,
                          'content_hash': 'hash', 'revision_ids': ['r'], 'segment_ids': ['s']}]}
    return brief, snapshot


def test_reuse_summary_without_mutating_original_or_reclassifying_evidence():
    brief, snapshot = fixture()
    before = deepcopy(brief)
    result = report_summary(brief, snapshot)
    assert brief == before
    assert result['status'] == 'AVAILABLE'
    assert result['topics'][0]['summary'] == brief['topics'][0]['summary']
    assert result['topics'][0]['evidence_ids'] == ['u']
    assert result['topics'][0]['authority_status'] == 'PROVISIONAL'


@pytest.mark.parametrize('kind', ['quote', 'title', 'preserved', 'fallback'])
def test_raw_quotes_and_placeholder_titles_never_masquerade_as_summary(kind):
    brief, snapshot = fixture()
    if kind == 'quote':
        brief['topics'][0]['summary'] = snapshot['atoms'][0]['text']
    elif kind == 'fallback':
        brief['result_kind'] = 'DETERMINISTIC_FALLBACK'
    else:
        brief['topics'][0]['summary_source'] = {'title': 'TITLE_FALLBACK', 'preserved': 'PRESERVED_LIVE_TOPIC'}[kind]
    result = report_summary(brief, snapshot)
    assert result['status'] == 'PENDING'
    assert result['topics'] == []


@pytest.mark.parametrize('missing', [False, True])
@pytest.mark.parametrize('entity_type', ['summary_topic', 'summary_speaker'])
def test_summary_source_endpoint_uses_original_source_snapshot(missing, entity_type):
    brief, snapshot = fixture()
    summary = report_summary(brief, snapshot)
    structured = {'report_summary': summary, 'topic_structure': {'revision_id': 'rev'}}
    @contextmanager
    def connection(_):
        yield MagicMock()
    with patch('app.main.connect', connection), patch('app.main.MeetingBriefRepository') as briefs, \
         patch('app.main.TopicStructureRepository') as structures, patch('app.main.LiveRepository') as live:
        briefs.return_value.latest.return_value = {'brief_id': uuid4(), 'brief': brief}
        structures.return_value.ready_current.return_value = structured
        structures.return_value.snapshot.return_value = snapshot
        live.return_value.broadcast_official_context.return_value = None
        live.return_value.broadcast_official_material.return_value = {}
        if missing:
            with pytest.raises(HTTPException) as exc:
                ended_live_broadcast_brief_evidence(uuid4(), entity_type, 'structured-summary-missing')
            assert exc.value.status_code == 404
            return
        entity = summary['topics'][0] if entity_type == 'summary_topic' else summary['topics'][0]['speaker_points'][0]
        result = ended_live_broadcast_brief_evidence(uuid4(), entity_type, entity['id'])
    assert result['source'] == 'LIVE_STRUCTURE_SNAPSHOT'
    assert result['authority_status'] == 'PROVISIONAL'
    assert result['items'][0]['text'] == snapshot['atoms'][0]['text']
    assert result['items'][0]['revision_ids'] == ['r']


def test_markdown_summary_precedes_collapsed_verbatim_appendix():
    brief, snapshot = fixture()
    narrative = report_summary(brief, snapshot)
    quote = snapshot['atoms'][0]['text']
    result = _meeting_brief_markdown({'brief': {
        'report_summary': narrative, 'topic_structure': {'version': 'v'},
        'topics': [{'id': 't', 'title': '법원 안전', 'speaker_points': [
            {'summary': quote, 'summary_kind': 'SOURCE_QUOTE'}]}],
    }})
    assert result.index(narrative['topics'][0]['summary']) < result.index('<details>') < result.index(quote) < result.index('</details>')
    assert '[근거 원문]' in result


def test_group_then_bundle_then_detail_summaries_are_preserved_in_order():
    brief, snapshot = fixture()
    second = deepcopy(brief['topics'][0])
    second.update(id='t2', title='수사 제도', summary='수사 절차의 개선 방안이 논의됐다.')
    brief['topics'].append(second)
    brief['topic_groups'][0]['topic_ids'] = ['t2', 't']
    original = deepcopy(brief)
    narrative = report_summary(brief, snapshot)
    by_id = {t['id']: t for t in narrative['topics']}
    group = narrative['topic_groups'][0]
    assert group['title'] == '사법 제도'
    assert [by_id[i]['source_topic_id'] for i in group['topic_ids']] == ['t2', 't']
    assert by_id[group['topic_ids'][0]]['speaker_points'][0]['source_point_id'] == 'p'
    markdown = _meeting_brief_markdown({'brief': {'report_summary': narrative, 'topic_structure': {'version': 'v'}}})
    assert markdown.index('### 사법 제도') < markdown.index('#### 수사 제도') < markdown.index('- 법원 안전 관련 자료를 요청했다.') < markdown.index('#### 법원 안전 대책')
    assert brief == original


def test_legacy_duplicate_topic_ids_do_not_drop_summary_bundles():
    brief, snapshot = fixture()
    second = deepcopy(brief['topics'][0])
    second.update(title='다른 논의', summary='별도 논의의 개선 필요성이 제기됐다.')
    brief['topics'].append(second)
    result = report_summary(brief, snapshot)
    ids = [t['id'] for t in result['topics']]
    assert len(set(ids)) == 2
    assert sorted(i for g in result['topic_groups'] for i in g['topic_ids']) == sorted(ids)


@pytest.mark.parametrize('view', ['official', 'provisional', 'structured'])
def test_all_report_views_share_narrative_contract_and_keep_source_authority(view):
    from app.services.report_presentation import narrative_projection
    brief, snapshot = fixture()
    if view == 'structured':
        brief['report_summary'] = report_summary(brief, snapshot)
    elif view == 'official':
        point = brief['topics'][0]['speaker_points'][0]
        point.update(provisional_summary=point['summary'], summary='이것은 공식 원문 그대로입니다.',
                     summary_verification='OFFICIAL_SOURCE_EXCERPT', official_evidence_ids=['official-1'])
    before = deepcopy(brief)
    result = narrative_projection(brief)
    assert result['presentation_version'] == 'meeting-summary/3'
    assert result['topic_groups'][0]['title'] == '사법 제도'
    assert result['topics'][0]['speaker_points'][0]['summary'] == '법원 안전 관련 자료를 요청했다.'
    point = result['topics'][0]['speaker_points'][0]
    assert point['authority_status'] == 'PROVISIONAL'
    assert point['evidence_type'] == ('summary_speaker' if view == 'structured' else 'speaker')
    if view == 'official':
        assert point['official_evidence_ids'] == ['official-1']
    assert brief == before


def test_official_markdown_uses_ai_detail_summary_and_collapses_verbatim_source():
    brief, _ = fixture()
    point = brief['topics'][0]['speaker_points'][0]
    point.update(provisional_summary=point['summary'], summary='공식 원문 그대로의 긴 발언입니다.',
                 summary_verification='OFFICIAL_SOURCE_EXCERPT')
    text = _meeting_brief_markdown({'brief': brief, 'authority_status': 'OFFICIAL'})
    body, appendix = text.split('<details>', 1)
    assert '- 법원 안전 관련 자료를 요청했다.' in body
    assert '공식 원문 그대로의 긴 발언입니다.' not in body
    assert '공식 원문 그대로의 긴 발언입니다.' in appendix
    assert 'AI 요약 · 잠정' in body


def test_original_card_contains_its_summaries_and_tasks_with_owner():
    from app.services.report_presentation import narrative_projection
    brief, _ = fixture()
    brief['topics'].append({'id': 'other', 'title': '다른 논의', 'summary': '다른 정책을 논의했다.', 'evidence_ids': ['other-u']})
    brief['topic_groups'].append({'id': 'other-group', 'title': '다른 정책', 'topic_ids': ['other']})
    brief['tasks'] = [
        {'id': 'task-1', 'title': '자료 제출', 'topic_id': 't', 'status': 'OPEN', 'ministries': ['법무부']},
        {'id': 'task-2', 'title': '관계없는 과제', 'topic_id': 'other', 'status': 'OPEN'},
    ]
    result = narrative_projection(brief)
    assert result['topics'][0]['task_ids'] == ['task-1']
    brief['report_summary'] = result
    body = _meeting_brief_markdown({'brief': brief}).split('<details>')[0]
    assert '**과제**: 자료 제출 · 법무부' in body
    assert '관계없는 과제' not in body.split('### 다른 정책')[0]


def test_structured_task_card_preserves_original_topic_and_never_fans_out_by_source():
    from app.services.report_presentation import narrative_projection
    brief, snapshot = fixture()
    narrative = report_summary(brief, snapshot)
    other = deepcopy(narrative['topics'][0])
    other.update(id='summary-other', source_topic_id='other', title='다른 주제')
    narrative['topics'].append(other)
    task = {'id': 'structured-task-a', 'source_task_id': 'task-1', 'source_topic_id': 't',
            'title': '자료 제출', 'status': 'OPEN', 'related_topic_ids': ['structured-topic'],
            'task_evidence_spans': [{'evidence_id': 'u', 'quote': '제출해 주십시오'}]}
    brief.update(report_summary=narrative, tasks=[task], topic_structure={'revision_id': 'r'})
    result = narrative_projection(brief)
    assert result['topics'][0]['task_ids'] == ['structured-task-a']
    assert result['topics'][1]['task_ids'] == []
    task.pop('source_task_id'); task.pop('source_topic_id')
    result = narrative_projection(brief)
    assert all(not t['task_ids'] for t in result['topics'])
