"""Read-only access to saved real-data evidence cases; never triggers AI calls."""
from functools import lru_cache
from fastapi import HTTPException
from .ai_collection_store import Store
from .evidence_chain import cases
from .publication_evidence import safe_value


def install(app, service, prefix):
    @lru_cache(maxsize=1)
    def store():
        return Store(service.data_dir)

    @app.get(prefix + '/api/ai-agents/evidence-cases')
    def list_cases():
        values = cases(store())
        return safe_value(dict(items=[{k: row.get(k) for k in ('id', 'created_at', 'project_id', 'project_name', 'run_id', 'summary')} for row in values]))

    @app.get(prefix + '/api/ai-agents/evidence-cases/{case_id}')
    def get_case(case_id: str):
        values = cases(store(), case_id)
        if not values:
            raise HTTPException(404, '저장된 근거 연결 사례가 없습니다')
        exported = safe_value(values[0])
        # Display redaction may change text length. Do not return changed source
        # text alongside the original hash as if it were a replayable snapshot.
        for source in exported.get('sources', []):
            source.pop('text', None)
            source['text_omitted'] = True
        exported['representation'] = 'REDACTED_VIEW_ORIGINAL_SOURCE_OFFSETS'
        exported['source_note'] = '인용 위치와 해시는 보존 원문 기준입니다. API는 표시용이며 전체 원문은 생략합니다.'
        return exported
