"""Export saved uncertainty faithfully; never turn an evidence link into approval."""
from copy import deepcopy

from app.main import _meeting_brief_markdown


def test_export_preserves_review_tasks_in_grouped_and_unlinked_sections():
    record = {
        'generated_at': '2026-10-26T14:41:11Z',
        'authority_status': 'PROVISIONAL',
        'brief': {
            'headline': '검증용 회의', 'summary': '저장 요약',
            'topic_structure': {'version': 'fixture'},
            'topics': [{'id': 'topic', 'title': '예산', 'summary': '요약'}],
            'topic_groups': [{'title': '정책', 'topic_ids': ['topic']}],
            'tasks': [
                {'id': 'held', 'title': '정비안 검토', 'topic_id': 'topic',
                 'status': 'OPEN', 'topic_link_status': 'REVIEW_REQUIRED', 'evidence_ids': ['u']},
                {'id': 'unlinked', 'title': '협의 필요', 'topic_id': None,
                 'status': 'OPEN', 'topic_link_status': 'REVIEW_REQUIRED', 'evidence_ids': ['v']},
                {'id': 'linked', 'title': '서면 자료 제출', 'topic_id': 'topic',
                 'status': 'OPEN', 'topic_link_status': 'LINKED', 'request_spans': [{'quote': '제출해 주세요'}]},
            ],
        },
    }
    before = deepcopy(record)
    output = _meeting_brief_markdown(record)
    assert output.count('[근거 대조 필요 · 후속조치 확정 아님]') == 2
    assert '- 서면 자료 제출 (담당 부처 미확정)\n' in output
    assert '### 주제 연결 확인 필요' in output
    assert '기초 보고서 저장 시각: 2026-10-26T14:41:11Z' in output
    assert record == before
