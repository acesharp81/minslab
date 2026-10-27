const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const ctx={};vm.createContext(ctx);for(const f of ['policy-stage-flow.js','policy-brief-report.js','progress-report.js','project-brief-report.js'])vm.runInContext(fs.readFileSync(path.join(__dirname,'../../web/assets',f),'utf8'),ctx);
const report=vm.runInContext('ProjectBriefReport',ctx),policy=vm.runInContext('PolicyBriefReport',ctx);
const fixture=name=>JSON.parse(fs.readFileSync(path.join(__dirname,'../fixtures/project-brief',name+'.json'),'utf8'));
const minimal=()=>({scope:{project_id:'P',as_of_date:'2026-10-23'},data:{cohort:{id:'P',name:'시험 사업',units:100,source_ids:['P'],events:[],schedules:[]},projects:[],histories:[],evidence:[],mapping_history:[],locations:[],plan:{}}});
const plan=(stage,units,due_date,rest={})=>({stage,units,due_date,origin:'MANUAL',managed_schedule:true,precision:'DAY',...rest});
const event=(stage,units,event_date,rest={})=>({stage,units,event_date,origin:'SOURCE',...rest});
test('real source snapshot retains both requested graphics and nine chapters, appendices remain lazy',()=>{
 const input=fixture('observed-construction'),before=JSON.stringify(input),m=report.build(input),body=report.body(m);
 assert.equal(m.sections.length,9);assert.equal(m.appendices.length,0);assert.equal(m.appendix_count,4);
 assert.match(body,/사업화부터 입주까지 단계별 진행/);assert.match(body,/사업 단계별 목표·실적 일정 · 10년/);
 assert.equal((body.match(/data-schedule-month=/g)||[]).length,120);assert.equal((body.match(/class="report-chart"/g)||[]).length,2);
 assert.ok(!body.includes('id="project-appendix-'));assert.equal(JSON.stringify(input),before);
 for(const row of m.stages)assert.equal(row.current,policy.contribution(input.data.cohort,row.stage,input.scope.as_of_date).value);
 assert.equal(m.stages.find(r=>r.stage==='MOVE_IN').current,null);
});
test('partial C2 source rows are never summed or used to invent a type split',()=>{
 const m=report.build(fixture('partial-scope'));assert.equal(m.input.data.cohort.units,344);
 const quantities=m.quantities.map(r=>r.raw_units);assert.ok(quantities.includes(344));assert.ok(quantities.includes(1030));
 assert.equal(m.checks.find(r=>r.id==='quantity-scope').status,'REVIEW');
 assert.equal(report.scopeOptions(m.input).find(r=>r.value==='type').disabled,true);
 assert.throws(()=>report.build(m.input,{supply_scope:'type'}));
});
test('changed-plan source reasons and old revisions are preserved without inventing official amendment',()=>{
 const input=fixture('changed-plan'),m=report.build(input),appendix=report.appendixModel(m);
 assert.equal(m.input.data.cohort.units,574);assert.ok(m.source_facts.some(r=>r.method==='AMENDED_APPROVED_STOCK'));assert.match(report.body(m),/568→574/);assert.match(report.body(m),/발생일 미확보/);assert.ok(JSON.stringify(m.input).includes('568'));
 assert.ok(m.input.data.histories.length>0);assert.ok(appendix.appendices[2].tables.some(t=>t.rows.length));
 assert.match(report.body(appendix),/공식 변경 승인으로 단정하지 않습니다/);
});
test('missing is not zero and supply is not construction or real occupancy',()=>{
 const input=minimal();input.data.cohort.events=[event('SUPPLY',100,'2026-10-01')];
 const m=report.build(input);assert.equal(m.stages.find(r=>r.stage==='CONSTRUCTION').current,null);assert.equal(m.stages.find(r=>r.stage==='MOVE_IN').current,null);
 input.data.cohort.events=[event('BUSINESS',0,'2026-10-01')];assert.equal(report.build(input).stages[0].current,0);
});
test('overdue plans without actual remain verification needs, no automatic delay or attainment rate',()=>{
 const input=minimal();input.data.cohort.schedules=[plan('CONSTRUCTION',100,'2026-01-01')];const m=report.build(input);
 assert.equal(m.stages.find(r=>r.stage==='CONSTRUCTION').status,'기한 도래 · 실적 확인 필요');assert.ok(m.risks.every(r=>r.level!=='지연'));assert.ok(!report.body(m).includes('산정 불가'));
});
test('estimated or coarse/partial dates cannot become exact-day delay comparisons',()=>{
 for(const extra of [{precision:'MONTH'},{inferred:true},{date_conversion:'OBSERVED_BY'}]){
  const input=minimal();input.data.cohort.schedules=[plan('CONSTRUCTION',100,'2026-01-31',{...extra,baseline:{due_date:'2026-01-01',units:100}})];input.data.cohort.events=[event('CONSTRUCTION',100,'2026-02-01',{inferred:true})];
  assert.equal(report.build(input).stages.find(r=>r.stage==='CONSTRUCTION').variance,null);
 }
 const input=minimal();input.data.cohort.schedules=[plan('SUPPLY',100,'2026-02-01',{baseline:{due_date:'2026-01-01',units:100}})];input.data.cohort.events=[event('SUPPLY',40,'2026-02-02')];
 const row=report.build(input).stages.find(r=>r.stage==='SUPPLY');assert.equal(row.variance,31);assert.match(row.variance_kind,/현재 계획일/);
});
test('same-scope actual day comparison and previous-report date validation',()=>{
 const input=minimal();input.data.cohort.schedules=[plan('CONSTRUCTION',100,'2026-01-01',{baseline:{due_date:'2026-01-01',units:100}})];input.data.cohort.events=[event('CONSTRUCTION',100,'2026-01-05')];
 assert.equal(report.build(input).stages.find(r=>r.stage==='CONSTRUCTION').variance,4);
 assert.throws(()=>report.build(input,{comparison:'previous'}));input.previous=structuredClone(input);input.previous.scope.as_of_date='2026-10-01';
 assert.equal(report.build(input,{comparison:'previous'}).stages.find(r=>r.stage==='CONSTRUCTION').variance,4);
 input.previous.data.cohort.id='OTHER';assert.throws(()=>report.build(input,{comparison:'previous'}));
});
test('appendices use pinned input and hash, no mutations and no fresh reads',()=>{
 const input=fixture('observed-construction'),m=report.build(input);m.snapshot.input_sha256='pinned';m.report_id='id';const before=JSON.stringify(m);
 input.data.cohort.units=99999;const appendix=report.appendixModel(m);
 assert.equal(appendix.sections.length,0);assert.equal(appendix.appendices.length,4);assert.equal(appendix.snapshot.input_sha256,'pinned');assert.equal(JSON.stringify(m),before);
 assert.ok(appendix.input.data.cohort.units!==99999);assert.match(policy.csv(appendix),/SOURCE_ACCEPTED|근거|사유/);
});
test('HTML and CSV exports escape source text and spreadsheet formulas',()=>{
 const input=minimal();input.data.cohort.name='<script>alert(1)</script>';const m=report.build(input);assert.ok(!report.body(m).includes('<script>'));
 m.sections[0].tables[0].rows.push(['x','=HYPERLINK("bad")']);assert.match(policy.csv(m),/'=HYPERLINK/);
});
test('brief report discloses omitted rows while complete exports preserve the source table',()=>{
 const m=report.build(minimal(),{report_type:'brief'});
 m.sections[0].tables[0].rows=Array.from({length:7},(_,i)=>['항목 '+i,'값 '+i]);
 const before=JSON.stringify(m),body=report.body(m);
 assert.match(body,/주요 4행 \/ 전체 7행/);
 assert.match(body,/본문 CSV·JSON 또는 상세분석보고서/);
 assert.ok(!body.includes('항목 6'));
 assert.match(policy.csv(m),/항목 6/);
 assert.equal(JSON.stringify(m),before);
});
