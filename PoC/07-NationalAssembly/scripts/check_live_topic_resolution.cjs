// Operational regression for the hearing's preserved official and provisional views.
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const assert = require('node:assert/strict');
const base = process.env.KJON_BASE || 'http://127.0.0.1:18072';
const id = '96e52910-09e4-457b-b090-19dfc3f19f4b';
(async () => {
  const browser = await chromium.launch({headless:true, executablePath:process.env.CHROMIUM_EXECUTABLE_PATH || undefined,
    args:['--no-sandbox','--enable-webgl','--use-gl=angle','--use-angle=swiftshader']});
  try {
    const page = await browser.newPage({viewport:{width:1440,height:1000}});
    const errors = []; page.on('pageerror', error => errors.push(error.message));
    const response = await page.request.get(`${base}/api/live/broadcasts/${id}/brief`);
    assert.equal(response.status(), 200);
    const record = await response.json(), resolution = record.live_topic_resolution;
    assert.equal(record.default_brief_view, 'OFFICIAL');
    assert.equal(resolution.authority_status, 'PROVISIONAL');
    assert.equal(resolution.legacy_pending_count, 26);
    assert.equal(resolution.legacy_pending_linked_count, 22);
    assert.equal(resolution.legacy_pending_procedural_count, 4);
    assert.equal(resolution.legacy_pending_review_count, 0);
    assert.equal(resolution.review_count, 1);
    const pending = resolution.entries.find(entry => entry.status === 'PARTIAL');
    assert.ok(pending.review_evidence_ids.length >= 2);
    for (const item of pending.review_items) {
      const response = await page.request.get(`${base}/api/live/broadcasts/${id}/brief/evidence?entity_type=structure_review&entity_id=${item.id}`);
      assert.equal(response.status(), 200);
      const evidence = await response.json();
      assert.equal(evidence.authority_status, 'PROVISIONAL');
      assert.equal(evidence.source, 'LIVE_STRUCTURE_SNAPSHOT');
      assert.ok(evidence.items.some(turn => turn.text.includes(item.summary)));
    }
    const md = await page.request.get(`${base}/api/live/broadcasts/${id}/brief.md?view=official`);
    assert.ok((await md.text()).includes('기존 요약의 연결 확인 26묶음 중 구조화 연결 22'));
    await page.goto(base+'/#reports', {waitUntil:'domcontentloaded'});
    await page.locator('#reportBroadcastRows [data-broadcast-id]').first().waitFor({timeout:60000});
    for (let attempt = 0; attempt < 15 && !await page.locator(`#reportBroadcastRows [data-broadcast-id="${id}"]`).count(); attempt++) {
      await page.evaluate(() => loadMoreMeetingHistory());
    }
    const row = page.locator(`#reportBroadcastRows [data-broadcast-id="${id}"]`).first();
    await row.waitFor({timeout:60000}); await row.click();
    await page.locator('.meeting-live-resolution').waitFor({timeout:60000});
    assert.match(await page.locator('.meeting-live-resolution').innerText(), /추가 확인 1묶음/);
    assert.equal(await page.locator('.meeting-live-resolution').evaluate(panel => panel.open), false);
    assert.equal(await page.locator('.meeting-live-resolution-pending').isVisible(), false);
    await page.locator('.meeting-live-resolution > summary').click();
    assert.equal(await page.locator('.meeting-live-resolution-pending').isVisible(), true);
    await page.locator('.meeting-live-resolution > summary').click();
    assert.equal(await page.locator('.meeting-live-resolution-pending').isVisible(), false);
    await page.locator('.meeting-live-resolution > summary').click();
    await page.locator('.meeting-live-resolution-linked > summary').click();
    const link = page.locator('[data-resolution-topic-id]').first();
    const topicId = await link.getAttribute('data-resolution-topic-id');
    await link.click();
    await page.locator('#meeting-topic-detail-'+topicId).waitFor();
    await page.locator('#meetingBriefEvidence .meeting-evidence-utterance').first().waitFor({timeout:60000});
    assert.match(await page.locator('.meeting-brief-labels').innerText(), /AI 잠정/);
    await page.getByRole('button', {name:record.official_integration?.comparison_mode === 'SOURCE_ONLY_TIMEOUT' ? '공식 발언·화자' : '공식 대조본', exact:true}).click();
    await page.locator('.meeting-live-resolution > summary').click();
    await page.locator('.meeting-live-resolution-pending button').first().click();
    await page.locator('#meetingBriefEvidence .meeting-evidence-utterance').first().waitFor({timeout:60000});
    await page.setViewportSize({width:390,height:844});
    assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth+1));
    assert.deepEqual(errors, []);
    console.log(JSON.stringify({passed:true,base,linked:22,procedural:4,legacy_pending:0,report_review:1,review_evidence:pending.review_evidence_ids.length,mobile:true,errors}));
  } finally { await browser.close(); }
})().catch(error => {console.error(error);process.exit(1);});
