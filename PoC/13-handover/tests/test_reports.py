import copy

from app.engine import annotate_items, empty_field
from app.reports import build_report, render_html
from test_flow import client, generate, new_case, seed


def confirm(c, base, rev):
    response = c.post(base + f"/revisions/{rev['id']}/confirm", json={"expected_hash": rev["hash"], "acknowledge_warnings": True})
    assert response.status_code == 200


def test_report_both_parties_same_final_not_new_draft(client):
    c = client
    base, rev = seed(c)
    url = base + f"/reports/{rev['id']}"
    assert c.get(url).status_code == 403
    confirm(c, base, rev)
    predecessor = c.get(base + '/reports/confirmed')
    successor = c.get(base + '/reports/confirmed', headers={'X-Role': 'successor'})
    assert predecessor.status_code == 200 and predecessor.text == successor.text
    assert 'attachment' not in predecessor.headers.get('content-disposition', '')
    assert "frame-ancestors 'self'" in predecessor.headers['content-security-policy']
    assert "style-src 'unsafe-inline'" in predecessor.headers['content-security-policy']
    assert "default-src 'none'" in predecessor.headers['content-security-policy']
    assert "frame-ancestors 'self'" in c.get('/').headers['content-security-policy']
    report = predecessor.text
    for section in ['전체 업무 요약', '당장 확인·처리할 현안', '지금까지 완료한 일·산출물', '앞으로 남은 업무', '후속 실행 계획·일정']:
        assert section in report
    assert report.index('다음에 실행할 구체적 조치') < report.index('부록. 원문 근거')
    assert '주민 수요조사' in report and '11월 말' in report
    assert c.get(base + f"/exports/{rev['id']}.html").text == report
    other = new_case(c)
    assert c.get(other + f"/reports/{rev['id']}").status_code == 404
    generate(c, base)
    assert c.get(base + '/reports/confirmed').text == report


def test_new_progress_fields_and_safe_report(client):
    c = client
    base = new_case(c)
    text = '업무: 문화제 준비\n담당: 문화팀\n상태: 준비 중\n기한: 2026-11-10\n완료한 일: 장소 예약 완료\n남은 업무: 출연진 계약\n다음 행동: 계약서 검토\n현안: 계약 예산 승인 대기'
    c.post(base + '/documents', files={'file': ('실적.txt', text.encode())})
    rev = generate(c, base)
    fields = rev['payload']['items'][0]['fields']
    assert fields['completed_work']['value'] == '장소 예약 완료'
    assert fields['remaining_work']['value'] == '출연진 계약'
    assert fields['issues']['value'] == '계약 예산 승인 대기'
    assert rev['payload']['items'][0]['business_status'] != 'COMPLETED'
    item = rev['payload']['items'][0]
    rev = c.patch(base + f"/revisions/{rev['id']}/items/{item['id']}", json={'expected_hash': rev['hash'], 'fields': {'issues': '<script>alert(1)</script>'}, 'reason': '표시 시험'}).json()
    confirm(c, base, rev)
    for suffix in ['.html', '.md']:
        result = c.get(base + f"/exports/{rev['id']}" + suffix)
        assert '<script>alert' not in result.text and '&lt;script&gt;' in result.text
        assert '장소 예약 완료' in result.text and '출연진 계약' in result.text
        assert '계약 예산 승인 대기' in result.text  # preserved old evidence


def test_legacy_revision_edit_does_not_require_regeneration(client):
    c = client
    base, rev = seed(c)
    # Simulate the exact old schema without mutating any existing revision.
    payload = copy.deepcopy(rev['payload'])
    for item in payload['items']:
        for key in ['completed_work', 'remaining_work', 'issues']:
            item['fields'].pop(key, None)
    store = c.app.state.store
    with store.connect(write=True) as db:
        old_id = store.revision(db, base.split('/')[-1], payload, rev['id'], 'legacy fixture')
    old = c.get(base + '/revisions/' + old_id).json()
    item = old['payload']['items'][0]
    changed = c.patch(base + f"/revisions/{old_id}/items/{item['id']}", json={'expected_hash': old['hash'], 'fields': {'completed_work': '전임자가 실적 확인'}, 'reason': '보완'})
    assert changed.status_code == 200
    new = changed.json()
    confirm(c, base, new)
    assert '전임자가 실적 확인' in c.get(base + '/reports/confirmed').text
    assert c.get(base + '/revisions/' + old_id).json()['hash'] == old['hash']


def test_priority_is_deterministic_and_does_not_invent_completion():
    fields = {k: empty_field() for k in ['title', 'status', 'due_date', 'owner', 'next_action']}
    for k, v in {'title': '안전 점검', 'status': '사전 점검 완료', 'due_date': '2026-11-10'}.items():
        fields[k]['value'] = v
        fields[k]['review_status'] = 'UNREVIEWED'
    item = {'fields': fields}
    annotate_items([item])
    revision = {'id': 'r', 'hash': 'h', 'confirmation': {'created': '2026-11-08T02:00:00+00:00'}, 'payload': {'items': [item], 'generated_at': '2026-11-08', 'model': 'solar-pro4'}, 'warnings': []}
    info = {'title': '인계', 'predecessor': '전', 'successor': '후'}
    report = build_report(info, revision, lambda _: None)
    assert report['completed'] == 0
    assert report['tasks'][0]['reasons'] == ['기준일로부터 7일 이내 기한']
    assert '자료에 미기재' in render_html(report)
    assert report['tasks'][0]['values']['completed_work'] == ''
    assert render_html(report) == render_html(build_report(info, revision, lambda _: None))
