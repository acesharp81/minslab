// Verify source-backed document requests remain tasks within their subjects.
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const assert = require('node:assert/strict');
const base = process.env.KJON_BASE || 'http://127.0.0.1:18072';
const ids = ['f09e1d8c-35df-4ded-beb5-310d0830e53e', 'dc09c1f6-763c-4ba6-8e3f-e91512bb67c1'];
(async () => {
  const browser = await chromium.launch({headless:true, executablePath:process.env.CHROMIUM_EXECUTABLE_PATH || undefined, args:['--no-sandbox']});
  try {
    const page = await browser.newPage({viewport:{width:1440,height:1000}});
    const errors=[]; page.on('pageerror', e=>errors.push(e.message));
    const records=[];
    for (const id of ids) {
      const response=await page.request.get(`${base}/api/live/broadcasts/${id}/brief`);
      assert.equal(response.status(),200);
      const record=await response.json();const b=record.structured_brief;
      assert.equal(b.topic_structure.projection_version,'1.5');
      assert.ok(!b.topic_groups.some(g=>g.title==='공통 후속 과제'));
      assert.ok(!b.topics.some(t=>t.title==='자료 제출 요구'));
      const needle=id===ids[0]?'부분을 좀 가능하면 빨리 제출':'법원행정처 격려금 지급회계서류';
      const task=b.tasks.find(t=>(t.request_spans||[]).some(s=>s.source_role==='PROCEDURE'&&s.quote.includes(needle)));
      assert.ok(task);assert.ok(task.related_topic_ids.length);
      const group=b.topic_groups.find(g=>g.topic_ids.some(t=>task.related_topic_ids.includes(t)));
      assert.ok(group);
      const evidence=await page.request.get(`${base}/api/live/broadcasts/${id}/brief/evidence?entity_type=task&entity_id=${task.id}`);
      assert.equal(evidence.status(),200);
      const payload=await evidence.json();
      assert.ok(payload.items.some(t=>t.text.includes(needle)));
      const md=await page.request.get(`${base}/api/live/broadcasts/${id}/brief.md?view=structured`);
      assert.ok((await md.text()).includes('### '+group.title));
      records.push({id,record,task,group,needle});
    }
    await page.goto(base+'/#reports',{waitUntil:'domcontentloaded'});
    await page.locator('#reportBroadcastRows [data-broadcast-id]').first().waitFor({timeout:60000});
    for(let i=0;i<15&&!await page.locator(`#reportBroadcastRows [data-broadcast-id="${ids[0]}"]`).count();i++)await page.evaluate(()=>loadMoreMeetingHistory());
    await page.locator(`#reportBroadcastRows [data-broadcast-id="${ids[0]}"]`).first().click();
    await page.getByRole('button',{name:'쟁점 구조화 · 잠정',exact:true}).waitFor({timeout:60000});
    await page.getByRole('button',{name:'쟁점 구조화 · 잠정',exact:true}).click();
    for(const {id,record,task,group,needle} of records){
      if(id!==ids[0])await page.evaluate(({id,record})=>renderMeetingBrief({broadcast_id:id},{...record,_brief_view:'structured'}),{id,record});
      assert.equal(await page.locator('.meeting-document-task-group').count(),0);
      const row=page.locator('.meeting-topic-task-row').filter({has:page.locator('.meeting-topic-summary-button strong',{hasText:group.title})}).first();
      await row.waitFor();
      const more=row.locator('.meeting-topic-more-tasks');
      if(await more.count())await more.locator('summary').click();
      const button=row.locator('.meeting-topic-task-button').filter({has:page.locator('strong',{hasText:task.title})}).first();
      await button.click();
      await page.locator('#meetingBriefEvidence .meeting-evidence-utterance').first().waitFor({timeout:60000});
      await page.locator('#meetingBriefEvidence .meeting-evidence-utterance').filter({hasText:needle}).first().waitFor({timeout:60000});
    }
    await page.setViewportSize({width:390,height:844});
    assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
    assert.deepEqual(errors,[]);
    console.log(JSON.stringify({passed:true,base,reports:ids,subjectTaskButtons:true,sourceEvidence:true,markdown:true,mobile:true,errors}));
  } finally {await browser.close();}
})().catch(e=>{console.error(e);process.exit(1);});
