"""Officer review requested for six new programmes and their active projects."""
from copy import deepcopy
from datetime import datetime
from html import escape
import hashlib
import json
from pathlib import Path
import sys
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
FOLDER = ROOT / 'data/remediation/policy-connections-20261018'
POLICY = 'POL_2025_0907'
ROUND = 'HOME-INTEGRITY-R01-CONSOLIDATED-20261017'
ACTOR = '김민'
REASON = '공식 자료 확인 및 IH 추가 연결'
REVIEW = 'POLICY-PROGRAM-PROJECT-20261018'
NAMES = {'공공주택 후보', '민간정비 후보', 'iH 공공분양', 'iH 통합공공임대',
         'iH 주택건설 후보', 'iH 공공분양, 공공임대(6년 분양전환)'}
POLICY_URL = 'https://www.korea.kr/news/policyNewsView.do?newsId=148948818'


def read(name):
    return json.loads((FOLDER / (name + '.json')).read_text())


def write(name, value):
    FOLDER.mkdir(parents=True, exist_ok=True)
    (FOLDER / (name + '.json')).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def service():
    from backend.db import engine_for
    from backend.service import HomeService
    return HomeService(engine_for(), ROOT / 'data')


def capture():
    from backend.data_integrity import get_round
    if (FOLDER / 'plan.json').exists():
        raise ValueError('기존 검토안·변경 전 기록을 덮어쓰지 않습니다.')
    s = service(); projects = s.projects(); programs = s.program_links(projects=projects)
    chosen = [p for p in programs if p['name'] in NAMES and p['policy_id'] == POLICY]
    assert len(chosen) == 6 and all(p['status'] == 'REVIEW' for p in chosen)
    ids = {p['id'] for p in chosen}
    active = [p for p in projects if p['mapping'].get('program_id') in ids and p['mapping']['status'] not in ('RELEASED', 'REJECTED')]
    inactive = [p for p in projects if p['mapping'].get('program_id') in ids and p['mapping']['status'] in ('RELEASED', 'REJECTED')]
    assert len(active) == 11 and len(inactive) == 1
    proof = []
    for p in active:
        if p['source_id'] == 'ih_notice':
            body = (s.data_dir / p['original_file']).read_bytes()
            assert hashlib.sha256(body).hexdigest() == p['original_sha256']
        proof.append(dict(id=p['id'], name=p['name'], source_id=p['source_id'],
            source_revision_id=p['source_revision_id'], source_payload_hash=p['source_payload_hash'],
            original_file=p.get('original_file'), original_sha256=p.get('original_sha256'),
            source_fields=p.get('source_fields'), planned_units=p.get('planned_units'),
            evidence_url=p['evidence_url'], mapping=p['mapping']))
    write('evidence', proof)
    write('programs-before', programs)
    write('projects-before', [dict(id=p['id'], mapping=p['mapping']) for p in projects])
    write('round-before', get_round(s, ROUND))
    (FOLDER / 'round-before.html').write_text(get_round(s, ROUND, html=True))
    programme_basis = ('9·7 공식 정책의 수도권 공공택지·공공주택 및 민간 재개발·재건축 공급 관리 범위와 '
                       '원천 사업의 지역·사업유형을 대조하여 관리 연결을 확정. '
                       '개별 블록의 해당 연도 실적과 정책 기여 물량은 사건 증빙으로 별도 검증.')
    plan = dict(programs=[dict(id=p['id'], name=p['name'], revision_no=p['revision_no'], policy_id=POLICY,
        explanation=programme_basis, evidence_url=POLICY_URL,
        evidence_urls=[POLICY_URL] + [r['evidence_url'] for r in active if r['mapping']['program_id'] == p['id']]) for p in chosen],
        projects=[dict(id=p['id'], name=p['name'], revision_no=p['mapping']['revision_no'], policy_id=POLICY,
            program_id=p['mapping']['program_id'],
            explanation=('iH 공식 사업개요의 사업명·위치·블록·공급유형 대조' if p['source_id'] == 'ih_notice' else
                         '공식 발표의 사업명과 보유 국토부 정비사업 원장 대조' if p['source_id'] == 'molit_renewal_inventory' else
                         '공식 발표의 광교 사업과 건축HUB A17 명칭·주소·600호 대조, 중복 허가 기록 제외')
                         + ' · ' + programme_basis,
            evidence_url=p['evidence_url'], evidence_urls=[p['evidence_url'], POLICY_URL],
            source_revision_id=p['source_revision_id']) for p in active],
        excluded=[dict(id=p['id'], name=p['name'], status=p['mapping']['status'], basis=p['mapping']['basis']) for p in inactive],
        before_policy_projects=len([p for p in projects if p['mapping']['policy_id'] == POLICY]),
        expected_policy_projects=208, actual_events_authorized=False)
    assert plan['before_policy_projects'] == 197
    write('plan', plan)
    print(json.dumps(dict(programs=6, projects=11, excluded=1, before=197, expected=208), ensure_ascii=False))


def apply():
    from backend.connection_confirmation import apply_review
    s = service(); result = apply_review(s, REVIEW, read('plan'), ACTOR, REASON)
    write('applied', result)
    after = s.projects(); programs = s.program_links(projects=after)
    before = {p['id']:p['mapping'] for p in read('projects-before')}
    reviewed = {p['id'] for p in read('plan')['projects']}
    fields = ('status', 'policy_id', 'program_id', 'revision_no', 'basis', 'evidence_url')
    for p in after:
        if p['id'] not in reviewed:
            assert {k:p['mapping'].get(k) for k in fields} == {k:before[p['id']].get(k) for k in fields}
    selected = [p for p in after if p['mapping']['policy_id'] == POLICY]
    assert len(selected) == 208
    assert all(p['mapping']['status'] == 'CONFIRMED' and p['mapping']['policy_status'] == 'CONFIRMED' for p in selected)
    assert not [p for p in programs if p['policy_id'] == POLICY and p['status'] == 'REVIEW']
    write('verification', dict(policy_project_count=len(selected), confirmed_programs=6, confirmed_projects=11,
        excluded_duplicate=read('plan')['excluded'], other_project_mappings_unchanged=True,
        actor=ACTOR, reason=REASON, checked_at=datetime.now(ZoneInfo('Asia/Seoul')).isoformat()))
    print(json.dumps(read('verification'), ensure_ascii=False))


def amend():
    from backend.data_integrity import amend_round
    s = service(); before = read('round-before'); current = deepcopy(before['result'])
    message = ('공식 자료 및 iH 원문 검토 후 정책–프로그램 6건과 프로그램–사업 11건의 관리 연결을 '
               '김민 / 공식 자료 확인 및 IH 추가 연결로 확정했다. 9·7 수집·연계 조회는 197 → 208개 사업 기록. '
               '광교 중복 의심 해제 1건은 제외했다. 연결 확정과 실제 착공·분양·입주 실적 인정은 별도이며 '
               '기술 점수·기존 직접 사건 스냅샷은 이번 관리 연결만으로 재채점하지 않는다.')
    current['management_connection_update'] = dict(comment=message, **read('verification'))
    old_ih = next(p for p in read('ih-before') if p.get('block') == 'S3')
    new_ih = next(p for p in read('ih-after') if p.get('block') == 'S3')
    collection_note = (f"기본 수집 보정: 검암 S3의 면적별 계획 물량을 합산하여 {old_ih['planned_units']:,} → "
                       f"{new_ih['planned_units']:,}호로 정정. 계획 세대수이며 신규 착공·분양 실적이 아니다. "
                       '수집 배치·원문 판본 이력으로 보존하고 담당자 연결 확인과 구분했다.')
    current['management_connection_update']['base_collection_note'] = collection_note
    html = (FOLDER / 'round-before.html').read_text()
    for c in current['categories']:
        for item in c['items']:
            if item['id'] in ('B1', 'C2', 'C3', 'H3', 'J4'):
                old = item['change_comment']; item['change_comment'] += ' ' + message
                item['reason'] = item['change_comment']
                html = html.replace(escape(old), escape(item['change_comment']))
    current['reason'] = REASON
    html = html.replace('<main>', '<main><section class="section box" id="management-connection-update"><h2>정책–프로그램–사업 연결 확정 · 2026-10-18</h2><p>'
                        + escape(message) + '</p><p>' + escape(collection_note) + '</p></section>', 1)
    begin = html.index('<script type="application/json" id="report-data">') + len('<script type="application/json" id="report-data">')
    end = html.index('</script>', begin)
    html = html[:begin] + json.dumps(current, ensure_ascii=False, allow_nan=False).replace('<', '\\u003c') + html[end:]
    write('round', current); (FOLDER / 'round.html').write_text(html)
    print(amend_round(s, ROUND, before['digest'], current, html, ACTOR, REASON))


if __name__ == '__main__':
    globals()[sys.argv[1]]()
