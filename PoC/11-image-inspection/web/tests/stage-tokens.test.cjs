const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const source=fs.readFileSync(path.join(__dirname,'../app.js'),'utf8');
const ctx={esc:s=>String(s).replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;')};
vm.createContext(ctx);vm.runInContext(source.slice(source.indexOf('function tokenModelName('),source.indexOf('function renderTokens(')),ctx);
const call=(workload,model,input,output,extra={})=>({workload,model,usage:{input_tokens:input,output_tokens:output},...extra});
test('same-stage calls sum per model while reading and analysis remain separate',()=>{
 const run={calls:[call('image-observation','gpt-5.4-2026-03-05',100,20),call('image-verification','gpt-5.4-2026-03-05',200,30),call('text-pixel-confirm','gpt-5.4',300,40),call('text-spelling-audit','gpt-5.4-mini-2026-03-17',400,50),call('checklist-analysis','gpt-5.4-mini',500,60),call('checklist-analysis','gpt-5.4-mini',600,70)]};
 const stages=ctx.stageTokenUsage(run);
 assert.equal(stages[0].models[0].model,'GPT-5.4');assert.equal(stages[0].models[0].input,100);
 assert.equal(stages[1].models.length,2);assert.equal(stages[1].models[0].input,500);assert.equal(stages[1].models[0].output,70);
 assert.equal(stages[2].models[0].calls,2);assert.equal(stages[2].models[0].input,1100);
 assert.match(ctx.stageTokensHTML(run),/2,370/);
});
test('provider cache and reasoning subsets never inflate totals',()=>{
 const c=call('image-observation','provider-snapshot',1000,200,{requested_model:'gpt-5.4'});Object.assign(c.usage,{cached_input_tokens:900,reasoning_tokens:150});
 const run={calls:[c]},r=ctx.stageTokenUsage(run)[0].models[0];
 assert.equal(r.model,'GPT-5.4');assert.equal(r.input+r.output,1200);
 assert.match(ctx.stageTokensHTML(run),/입력 1,000 · 출력 200/);
});
test('reused read, glyph and spelling results cost zero additional tokens',()=>{
 const run={observation:{objects:[]},observation_model:'gpt-6.1-sol',observation_reused_from:{run_id:'old'},pixel_text:{confirmation:{calls:1}},spelling_audit:{calls:1},calls:[call('checklist-analysis','gpt-5.4-mini',24000,1500)]};
 const stages=ctx.stageTokenUsage(run);
 assert.equal(stages[0].models[0].calls,0);assert.equal(stages[0].models[0].reused,true);
 assert.equal(stages[1].models.length,2);assert.ok(stages[1].models.every(r=>r.reused&&!r.calls));
 const html=ctx.stageTokensHTML(run);assert.match(html,/25,500/);assert.match(html,/GPT-6.1 Sol/);assert.equal((html.match(/재사용 · 추가 0 토큰/g)||[]).length,3);
});
test('local history revisions mark inherited analysis without reporting it as new spend',()=>{
 const run={local_revision:{method:'evidence-reconcile-v1'},calls:[],results:[{model:'gpt-5.4-mini',status:'FAIL'},{model:'system/independent-evidence',status:'REVIEW'}],finished_at:'2026-11-04'};
 const r=ctx.stageTokenUsage(run)[2].models;assert.equal(r.length,1);assert.equal(r[0].reused,true);
 assert.match(ctx.stageTokensHTML(run),/이번 검사 추가 사용 <b>0<\/b> 토큰/);
});
test('partial reanalysis keeps reused models distinct from the newly called model',()=>{
 const run={analysis_reused_from:{run_id:'old'},calls:[call('checklist-analysis','gpt-5.4-mini',100,20)],results:[{model:'gpt-6-astra',status:'NOT_APPLICABLE'},{model:'gpt-5.4-mini',status:'PASS'}]};
 const rows=ctx.stageTokenUsage(run)[2].models;assert.equal(rows.length,2);
 assert.equal(rows.find(r=>r.model==='GPT-6 Astra').reused,true);assert.equal(rows.find(r=>r.model==='GPT-5.4 mini').reused,false);
 assert.match(ctx.stageTokensHTML(run),/이번 검사 추가 사용 <b>120<\/b> 토큰/);
});
test('failed unknown usage and missing fields stay visibly uncertain',()=>{
 const run={calls:[{workload:'image-observation',model:'gpt-6.1-sol',status:'FAILED',usage_unknown:true},{workload:'new-workload',model:'<script>',usage:{input_tokens:50}}]};
 const stages=ctx.stageTokenUsage(run);assert.equal(stages[0].models[0].unknown,1);assert.equal(stages[3].models[0].unknown,1);
 const html=ctx.stageTokensHTML(run);assert.match(html,/미확정 2회/);assert.match(html,/기타 호출/);assert.ok(html.includes('&lt;script&gt;')&&!html.includes('<script>'));
});
test('NAVER is counted as requests, with inherited OCR separated from new calls',()=>{
 const run={text_ocr:{naver:{event_id:'naver-one',status:'COMPLETED'}},calls:[]};
 let r=ctx.stageTokenUsage(run)[1].models[0];assert.equal(r.unit,'api_call');assert.equal(r.calls,1);assert.match(ctx.stageTokensHTML(run),/API 1회/);
 run.calls=[{event_id:'naver-one',unit:'api_call',model:'naver-ocr',workload:'naver-ocr'}];assert.equal(ctx.stageTokenUsage(run)[1].models[0].calls,1);
 run.calls=[];run.observation_reused_from={run_id:'old'};r=ctx.stageTokenUsage(run)[1].models[0];assert.equal(r.calls,0);assert.equal(r.reused,true);assert.match(ctx.stageTokensHTML(run),/재사용 · 추가 0 회/);
});
test('header shows mock, waiting and finished states without inventing usage',()=>{
 assert.equal(ctx.stageTokensHTML(null),'');assert.match(ctx.stageTokensHTML({options:{mode:'mock'}}),/실제 토큰 사용 없음/);
 assert.match(ctx.stageTokensHTML({calls:[]}),/대기 중/);assert.match(ctx.stageTokensHTML({phase:'DONE',calls:[]}),/미실행/);
});
test('component readings are image verification spend, not unclassified or analysis spend',()=>{
 const stages=ctx.stageTokenUsage({calls:[call('text-jamo-isolated','gpt-5.4',120,80)]});
 assert.equal(stages[1].models[0].input,120);assert.equal(stages[1].models[0].output,80);
 assert.equal(stages[2].models.length,0);assert.equal(stages.length,3);
});
test('completed analysis still exposes failed supplemental crops without calling them normal',()=>{
 const run={phase:'DONE',calls:[],verification:{deferred:[
  {object_id:'a',reason:'자동 재검사 실패: 응답 시간 초과'},
  {object_id:'a',reason:'자동 재검사 실패: 응답 시간 초과'},
  {object_id:'b',reason:'자동 재검사 객체 한도: 선택 확대 재검사 가능'}]}};
 assert.match(ctx.stageTokensHTML(run),/확대 확인 1개 영역 응답 실패 · 정상 판정 아님/);
});
