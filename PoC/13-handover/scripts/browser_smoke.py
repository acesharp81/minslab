"""Real browser workflow. Use only a dedicated synthetic-data workspace."""
import os
import shutil
from pathlib import Path
from playwright.sync_api import sync_playwright

url = os.getenv("HANDOVER_TEST_URL", "http://127.0.0.1:18130/")
out = Path("test-results")
out.mkdir(exist_ok=True)
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
    context = browser.new_context(viewport={"width": 1440, "height": 1000}, record_video_dir=str(out / "video"), record_video_size={"width": 1440, "height": 1000})
    page = context.new_page()
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.goto(url)
    if os.getenv("HANDOVER_TEST_TOKEN"):
        page.locator("#accessToken").fill(os.environ["HANDOVER_TEST_TOKEN"])
        page.get_by_role("button", name="접속하기", exact=True).click()
    page.get_by_role("button", name="샘플로 시작하기").wait_for()
    page.screenshot(path=str(out / "home.png"), full_page=True)
    reuse=os.getenv('HANDOVER_REUSE_CASE')
    if reuse:
        page.goto(url+'#'+reuse)
        page.get_by_role('heading', name='전임자가 확인한 인수인계본입니다.').wait_for()
    else:
        page.get_by_role("button", name="샘플로 시작하기").click()
        page.get_by_role("heading", name="2027년 생활문화 사업계획", exact=True).wait_for(timeout=180000)
        if os.getenv("HANDOVER_REQUIRE_LLM") == "1":
            page.get_by_text("모델 사용 기록", exact=True).wait_for()
        page.screenshot(path=str(out / "review.png"), full_page=True)
        card = page.locator(".work-card").filter(has=page.get_by_role("heading", name="2027년 생활문화 사업계획", exact=True))
        card.get_by_role("button", name="수정", exact=True).click()
        page.locator("#edit_due_date").fill("2026-11-27")
        page.locator("#editReason").fill("전임자가 최종 일정을 확인")
        page.get_by_role("button", name="새 판본으로 저장").click()
        page.get_by_text("2026-11-27", exact=True).wait_for()
        card.get_by_role("button", name="수정 이력·과거 근거").click()
        page.get_by_text("전임자 입력: 2026-11-27").wait_for()
        page.locator("#searchQuery").fill("영수증")
        page.locator("#searchForm").get_by_role("button", name="검색", exact=True).click()
        page.locator("#searchResults .search-result").first.wait_for()
        page.get_by_role("button", name="검토 완료 · 확정하기").click()
        page.locator("#confirmCheck").check()
        page.get_by_role("button", name="이 판본 확정").click()
        page.get_by_role("heading", name="전임자가 확인한 인수인계본입니다.").wait_for()
    report = page.frame_locator('#reportFrame')
    report.get_by_role('heading', name='업무 인수인계 보고서', exact=True).wait_for()
    report.get_by_role('heading', name='2. 당장 확인·처리할 현안', exact=True).wait_for()
    report.locator('.fact').get_by_text('주민 수요조사 120건 취합 및 사업계획 초안 작성', exact=True).wait_for()
    report.locator('.fact').get_by_text('예산 협의와 사업계획 결재 상신', exact=True).wait_for()
    report_text = report.locator('body').inner_text()
    report_url = page.locator('#reportFrame').get_attribute('src')
    page.locator("#roleSelect").select_option("successor")
    page.frame_locator('#reportFrame').get_by_role('heading', name='업무 인수인계 보고서', exact=True).wait_for()
    assert page.locator('#reportFrame').get_attribute('src') == report_url
    assert page.frame_locator('#reportFrame').locator('body').inner_text() == report_text
    if page.get_by_role("button", name="인수 확인", exact=True).count():
        page.get_by_role("button", name="인수 확인", exact=True).click()
    page.get_by_role("button", name="확인 완료 ✓").wait_for()
    work_url = page.url
    page.locator('[data-action="tab"][data-tab="briefing"]').click()
    page.get_by_role('heading', name='후임자 일정·담당·연락망', exact=True).wait_for()
    page.get_by_text('문화기획팀 culture@example.invalid (합성 연락처)', exact=True).wait_for()
    page.screenshot(path=str(out / 'schedule-v040.png'), full_page=True)
    page.locator('[data-action="tab"][data-tab="questions"]').click()
    page.locator('#questionText').fill('생활문화 사업계획의 최종 기한은 언제인가요?')
    if os.getenv('HANDOVER_REQUIRE_LLM') == '1':
        page.locator('#questionMode').select_option('llm')
        page.locator('#questionConsent').check()
    else:
        page.locator('#questionMode').select_option('local')
    page.get_by_role('button', name='질문하기', exact=True).click()
    page.locator('.answer-fact').get_by_text('2026-11-27', exact=True).wait_for(timeout=120000)
    assert '2026-11-20' not in page.locator('.answer-fact').inner_text()
    page.screenshot(path=str(out / 'questions-v040.png'), full_page=True)
    page.locator('[data-action="tab"][data-tab="report"]').click()
    with page.expect_download() as download:
        page.get_by_role("link", name="MD ↓", exact=True).click()
    assert "2026-11-27" in Path(download.value.path()).read_text()
    with page.expect_download() as html_download:
        page.get_by_role('link', name='HTML ↓', exact=True).click()
    html = Path(html_download.value.path()).read_text()
    assert html.index('현재 어디까지 진행되었나') < html.index('부록. 원문 근거')
    assert '주민 수요조사 120건 취합 및 사업계획 초안 작성' in html
    report_page = context.new_page()
    report_page.goto(report_url)
    report_page.get_by_role('heading', name='업무 인수인계 보고서', exact=True).wait_for()
    report_page.screenshot(path=str(out / 'report.png'), full_page=True)
    report_page.pdf(path=str(out / 'handover-report.pdf'), format='A4', print_background=True)
    report_page.set_viewport_size({'width': 390, 'height': 844})
    assert report_page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
    report_page.screenshot(path=str(out / 'report-mobile.png'), full_page=True)
    report_page.close()
    page.screenshot(path=str(out / "confirmed.png"), full_page=True)
    # Exercise native multi-file and folder inputs in a separate synthetic case.
    page.locator('#roleSelect').select_option('predecessor')
    page.locator('#newCaseSmall').click()
    page.locator('#caseTitle').fill('합성 · 다중 등록 UI 검증')
    page.locator('[data-action="create-case"]').click()
    page.get_by_role('heading', name='합성 · 다중 등록 UI 검증', exact=True).wait_for()
    page.locator('#dropZone').wait_for()
    page.locator('#fileInput').set_input_files([
        {'name': '업무A.txt', 'mimeType': 'text/plain', 'buffer': '업무: 등록 검증 A\n담당: 가상팀\n다음 행동: 자료 확인'.encode()},
        {'name': '업무B.txt', 'mimeType': 'text/plain', 'buffer': '업무: 등록 검증 B\n담당: 가상팀\n다음 행동: 표 확인'.encode()},
    ])
    page.locator('.file-name').filter(has_text='업무B.txt').wait_for()
    folder = out / 'browser-folder'
    folder.mkdir(exist_ok=True)
    (folder / '추가.txt').write_text('업무: 폴더 등록 검증\n담당: 가상팀\n다음 행동: 목록 확인')
    page.locator('#folderInput').set_input_files(str(folder.resolve()))
    page.locator('.file-name').filter(has_text='추가.txt').wait_for()
    assert page.locator('.file-name').count() == 3
    page.locator('[data-action="generate"]').first.click()
    page.locator('#extractMode').select_option('rules')
    page.locator('[data-action="run-generate"]').click()
    page.get_by_role('heading', name='등록 검증 A', exact=True).wait_for()
    page.locator('.readiness summary').wait_for()
    page.screenshot(path=str(out / 'readiness-v040.png'), full_page=True)
    page.goto(work_url)
    page.frame_locator('#reportFrame').get_by_role('heading', name='업무 인수인계 보고서', exact=True).wait_for()
    page.set_viewport_size({"width": 390, "height": 844})
    page.screenshot(path=str(out / "mobile.png"), full_page=True)
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    assert not errors, errors
    print({"result": "PASS", "browser_errors": errors, "url": page.url, "download": download.value.suggested_filename})
    video = page.video
    context.close()
    if video:
        shutil.copyfile(video.path(), out / 'browser-smoke-v040.webm')
    browser.close()
