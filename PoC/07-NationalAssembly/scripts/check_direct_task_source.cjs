const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const assert=require('node:assert/strict');
const base=process.env.KJON_BASE||'http://127.0.0.1:18072';
const id='65c8a5d4-82f3-4d2b-b74a-bbc92ba4db1a';
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:process.env.CHROMIUM_EXECUTABLE_PATH||undefined,args:['--no-sandbox']});
 try{
  const page=await browser.newPage({viewport:{width:1440,height:1000}});
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  const res=await page.request.get(`${base}/api/live/broadcasts/${id}/brief`);assert.equal(res.status(),200);
  const record=await res.json(),brief=record.structured_brief;
  const task=brief.tasks.find(t=>t.title==='국정감사 지적사항 검토 및 업무 개선 반영');
  assert.equal(task.related_topic_ids.length,1);assert.equal(task.task_evidence_spans.length,1);
  const quote=task.task_evidence_spans[0].quote;assert.ok(quote.includes('검토하여 업무 개선의 기회로 삼겠습니다'));
  const evidence=await page.request.get(`${base}/api/live/broadcasts/${id}/brief/evidence?entity_type=task&entity_id=${task.id}`);
  const payload=await evidence.json();assert.equal(payload.direct_task_spans[0].quote,quote);
  await page.goto(base+'/#reports',{waitUntil:'domcontentloaded'});
  await page.locator('#reportBroadcastRows [data-broadcast-id]').first().waitFor({timeout:60000});
  for(let i=0;i<15&&!await page.locator(`#reportBroadcastRows [data-broadcast-id="${id}"]`).count();i++)await page.evaluate(()=>loadMoreMeetingHistory());
  await page.locator(`#reportBroadcastRows [data-broadcast-id="${id}"]`).first().click();
  const button=page.locator(`.meeting-topic-task-detail[data-evidence-id="${task.id}"]`);
  await button.waitFor({timeout:60000});assert.equal(await button.count(),1);
  assert.ok((await button.locator('.meeting-task-direct-quote').innerText()).includes(quote));
  await button.click();
  const mark=page.locator('#meetingBriefEvidence mark').filter({hasText:quote});await mark.waitFor({timeout:60000});
  assert.equal(await mark.innerText(),quote);
  await page.setViewportSize({width:390,height:844});assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
  assert.deepEqual(errors,[]);console.log(JSON.stringify({passed:true,base,taskOccurrences:1,directQuote:quote,exactHighlight:true,mobile:true,errors}));
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exit(1)});
