import json
from pathlib import Path
from playwright.sync_api import sync_playwright, expect

OUT = Path('/home/ubuntu/apps/myservice/PoC/07-NationalAssembly/docs/evidence/EXPANSION_TEST_20261111')
BID = '00000000-0000-4000-8000-000000000099'
brief = {'headline': '화면 검증용 모의 자료', 'summary': '실제 방송 결과가 아닌 화면 연결 검증 자료입니다.',
         'topics': [{'id': 'fixture-topic', 'title': '모의 주제', 'summary': '검증용 요약', 'utterance_ids': []}],
         'tasks': [], 'utterance_count': 0}
brief['report_summary'] = {'topics': [{'id': 'fixture-topic', 'title': '모의 주제',
                                     'summary': '검증용 요약', 'speaker_points': []}]}
record = {'is_expansion_test': True, 'brief_status': 'READY', 'brief_content_loaded': True,
          'brief': brief, 'generated_at': '2026-11-11T02:00:00Z'}
results = []
with sync_playwright() as p:
    browser = p.chromium.launch(executable_path='/home/ubuntu/.cache/ms-playwright/chromium_headless_shell-1248/chrome-headless-shell-linux64/chrome-headless-shell', args=['--no-sandbox'])
    for width in [1440, 390]:
        page = browser.new_page(viewport={'width': width, 'height': 960})
        errors = []
        requests = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        def response(route):
            requests.append(route.request.url)
            route.fulfill(status=200, content_type='application/json', body=json.dumps(record))
        page.route('**/api/live/broadcasts/' + BID + '/brief', response)
        page.goto('https://kjon.aigov.go.kr/#reports', wait_until='domcontentloaded', timeout=60000)
        expect(page.locator('#expansionTestReports')).to_be_visible(timeout=60000)
        expect(page.locator('#reportBroadcastRows .broadcast-row').first).to_be_visible(timeout=60000)
        before = page.locator('#reportBroadcastRows .broadcast-row').count()
        page.evaluate('''({bid, brief}) => {
            expansionReportState.items=[{broadcast_id:bid, external_id:'BROWSER-FIXTURE',
                title:'화면 검증용 모의 자료', committee_name:'문화체육관광위원회', institution:'LEGISLATURE',
                lifecycle_status:'ENDED', source_system:'assembly.webcast.go.kr', is_expansion_test:true,
                detected_at:'2026-11-11T01:00:00Z', ended_at:'2026-11-11T02:00:00Z', brief_status:'READY',
                meeting_brief:{brief_status:'READY',brief}}];
            renderBroadcastRows(meetingRailHistoryState.statusPayload,
                {items:meetingRailHistoryState.items,has_more:meetingRailHistoryState.hasMore},
                meetingRailHistoryState.executivePayload);
        }''', {'bid': BID, 'brief': brief})
        page.locator('#expansionTestRows .broadcast-row').click()
        expect(page.locator('#liveExpandedTitle')).to_contain_text('[확장성 테스트용]')
        expect(page.locator('#liveExpandedStage')).to_contain_text('검증용 요약')
        expect(page.locator('.meeting-brief-load-error')).to_have_count(0)
        page.locator('#liveExpandedStage').get_by_role('button', name='보고서 만들기', exact=True).click()
        dialog = page.locator('#meetingReportDocumentDialog')
        expect(dialog).to_be_visible()
        expect(dialog.locator('.meeting-summary-paper')).to_contain_text('확장성 테스트용')
        with page.expect_download() as pending:
            dialog.get_by_role('button', name='보고서 MD', exact=True).click()
        download = pending.value
        content = Path(download.path()).read_text()
        OUT.joinpath(f'second-audit-fixture-report-{width}.md').write_text(content)
        assert '확장성 테스트용' in content and '모의 주제' in content, content
        assert BID in dialog.get_by_role('link', name='전체 요약본 MD').get_attribute('href')
        dialog.get_by_role('button', name='닫기', exact=True).click()
        assert page.locator('#reportBroadcastRows .broadcast-row').count() == before
        assert not errors, errors
        assert requests, 'Card must fetch its own report'
        results.append({'width':width,'kind':'BROWSER_ONLY_FIXTURE','card_click_report_loaded':True,
                        'document_opened':True,'report_md_download_checked':True,
                        'full_md_link_correct':True,'regular_list_unchanged':True,
                        'fixture_requests_intercepted':len(requests),'js_errors':errors})
        print(json.dumps(results[-1],ensure_ascii=False),flush=True)
        page.close()
    browser.close()
OUT.joinpath('second-audit-browser.json').write_text(json.dumps(results,ensure_ascii=False,indent=2)+'\n')
