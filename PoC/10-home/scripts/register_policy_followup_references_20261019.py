"""Preserve three explicit conversion references without counting them as projects."""
import hashlib
import json
import re
from pypdf import PdfReader
from sqlalchemy import select
from backend.db import engine_for, ProgramMapping, upsert_revision, Audit
from backend.service import HomeService
from backend.policy_attachments import POLICY129_PDF


def main():
    service = HomeService(engine_for())
    path = service.data_dir / 'raw/policy_129/9813bc03471c8899f346fe92415c0331115635184d6b810f5d8d33c30fbe825d.pdf'
    text = PdfReader(path).pages[5].extract_text()
    compact = re.sub(r'\s+', '', text)
    assert all(t in compact for t in ('9.7대책이행실적', '남양주왕숙455호', '파주운정33.2천호', '수원당수490호', '사업계획변경착수'))
    specs = [('남양주왕숙 유보지', 455, '유보지→주택', False),
             ('파주운정3 유보지', 3200, '유보지→주택', True),
             ('수원당수 단독주택용지', 490, '단독→공동', False)]
    result = []
    with service.sessions.begin() as db:
        program = db.scalar(select(ProgramMapping).where(ProgramMapping.name == 'LH 소유 비주택용지 용도전환',
                            ProgramMapping.policy_id == 'POL_2025_0907', ProgramMapping.status == 'CONFIRMED'))
        assert program
        for name, units, conversion, approximate in specs:
            payload = dict(name=name, program_id=program.id, policy_id='POL_2025_0907', base_date='2026-01-29',
                status='DISTRICT_PLAN_BLOCK_UNSPECIFIED', exclude_from_project_totals=True,
                planned_units=units, approximate=approximate, event_label='사업계획 변경 착수', facts=[],
                evidence_url=POLICY129_PDF+'#page=6', source_page=6, printed_page=2,
                document_name='1·29 도심 주택공급 확대 및 신속화 방안 · 9·7 이행실적 참고',
                evidence_basis='9·7 후속 용도전환 명시 입지 · 블록 미특정 · 착공실적 아님',
                original_sha256=hashlib.sha256(path.read_bytes()).hexdigest(), original_file=str(path.relative_to(service.data_dir)),
                source_excerpt=text, review_actor='담당자 대행 · 사용자 검토 지시 2026-10-19',
                **{'사업명': name, '공급목표량또는분양계획량': ('약 ' if approximate else '')+f'{units:,}호 · {conversion}',
                   '분양시기': '개별 분양·착공 시기 미제시',
                   '검토내용': '원문 9·7 이행실적에 명시된 용도전환 대상. 사업계획 변경에 착수했다는 뜻이며 주택건설 착공 아님. 블록·필지 확인 전 기존 지구 사업과 합산하지 않음.',
                   '검증근거URL': POLICY129_PDF+'#page=6'})
            row, outcome = upsert_revision(db, 'program_district_plan', 'policy_129', '907-conversion:'+name, payload, 'conversion-review-20261019')
            if outcome != 'unchanged':
                db.add(Audit(entity_id=row.entity_id, action='PROGRAM_SOURCE_SUPPLEMENT', before={}, after=payload))
            result.append(dict(id=row.entity_id, name=name, units=units, approximate=approximate, result=outcome,
                               exclude_from_project_totals=True, evidence_url=payload['evidence_url']))
    (service.data_dir/'policy-readmission-conversion-references-20261019.json').write_text(json.dumps(result, ensure_ascii=False, indent=2))
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
