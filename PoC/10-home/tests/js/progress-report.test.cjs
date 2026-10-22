const test=require('node:test'),assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs'),path=require('node:path');
const context={};vm.createContext(context);for(const file of ['policy-stage-flow.js','portfolio-progress-report.js','progress-report.js'])vm.runInContext(fs.readFileSync(path.join(__dirname,'../../web/assets',file),'utf8'),context);const report=vm.runInContext('ProgressReport',context);
const fixture=()=>({kind:'policy',scope:{name:'9·7 정책',year:2026,as_of_date:'2026-10-22'},data:{summary_cards:{CONSTRUCTION:{current_units:8,expected_units:12},MOVE_IN:{current_units:null,expected_units:0}},cohorts:[{id:'p',name:'선택 사업',program:'프로그램',units:8,planned_units:8,events:[{stage:'CONSTRUCTION',event_date:'2024-01-01',units:8,status:'ACTUAL'}],schedules:[{stage:'SUPPLY',due_date:'2026-12-01',units:8}]}]},operations:{cases:[]},availability:[]});
test('summary and charts preserve selected totals, earlier cumulative starts, missing and zero',()=>{const c=fixture(),m=report.model(c),md=report.markdown(m);assert.match(md,/현재 누적 착공 8호/);assert.match(md,/2026년 말 착공 예상 12호/);assert.equal(m.stageRows.find(r=>r.stage==='MOVE_IN').current,null);assert.equal(m.stageRows.find(r=>r.stage==='MOVE_IN').expected,0);assert.equal(report.reached(c.data.cohorts[0],'CONSTRUCTION','2026-10-22'),8);assert.equal(m.groups[0].construction,8);assert.match(report.html(m),/<svg/);assert.match(md,/xychart-beta/);});
test('all complete exports exclude source links and appendices and escape dynamic markup',()=>{const c=fixture();c.scope.name='<script>bad()</script>';c.data.reference_sources={evidence_url:'https://secret.example/doc'};c.operations.cases=[{project_id:'p',status:'OPEN',basis:'일정 조정 https://secret.example/doc'}];const before=JSON.stringify(c),m=report.model(c);assert.doesNotMatch(report.html(m),/<script>|<img|secret.example|집계 기준 및 출처|작성 형식 참고/);assert.doesNotMatch(report.markdown(m),/secret.example|사업별 단계 근거/);assert.equal(JSON.stringify(c),before);});
test('policy groups programs, program groups regions, normal projects are not listed',()=>{const c=fixture();c.data.cohorts[0].region='서울';c.data.cohorts.push({...c.data.cohorts[0],id:'b',name:'사업B',program:'다른 프로그램',region:'경기'});const p=report.model(c);assert.equal(p.groups.length,2);c.kind='program';const m=report.model(c);assert.deepEqual(Array.from(m.groups,r=>r.label).sort(),['경기','서울']);assert.equal(m.riskSections[0].rows.length,0);assert.ok(!m.sections.some(s=>s.title.includes('사업별 추진현황')));});
test('project centers six stages and date timeline, separating completion and future plans',()=>{const c={kind:'project',scope:{name:'사업',year:2026,as_of_date:'2026-10-22'},data:{project:{project:{id:'p',name:'사업',planned_units:8},cells:{CONSTRUCTION:{management:{measurement:[{milestone:'CONSTRUCTION',date:'2024-01-01',units:8},{milestone:'COMPLETION',date:'2026-01-01',units:4}],target:[{milestone:'COMPLETION',date:'2027-03-01',units:8}]}}}}},availability:[]};const m=report.model(c);assert.equal(m.stageRows.find(r=>r.stage==='CONSTRUCTION').current,8);assert.equal(m.stageRows.find(r=>r.stage==='COMPLETION').current,4);assert.equal(m.stageRows.find(r=>r.stage==='MOVE_IN').current,null);assert.equal(m.charts[0].type,'steps');assert.equal(m.charts[2].type,'timeline');assert.match(report.markdown(m),/2027-03-01/);assert.doesNotMatch(report.html(m),/NaN|Infinity/);});
test('risks use same 2 percent boundary, never treat missing as zero, and count each project once',()=>{const c=fixture();c.data.cohorts=[{id:'d',name:'지연',units:1000,events:[{stage:'APPROVAL',event_date:'2026-01-01',units:980}],schedules:[{stage:'APPROVAL',due_date:'2026-09-01',units:1000}]},{id:'w',name:'주의',units:1000,events:[{stage:'APPROVAL',event_date:'2026-01-01',units:981}],schedules:[{stage:'APPROVAL',due_date:'2026-09-01',units:1000},{stage:'SUPPLY',due_date:'2026-09-01',units:1000}]},{id:'u',name:'미확보',units:8,events:[],schedules:[{stage:'SUPPLY',due_date:'2026-09-01',units:8}]},{id:'f',name:'미도래',units:8,events:[],schedules:[{stage:'SUPPLY',due_date:'2026-12-01',units:8}]}];const m=report.model(c);assert.equal(m.counts.DELAYED,1);assert.equal(m.counts.WARNING,1);assert.equal(m.counts.UNKNOWN,1);assert.equal(m.riskSections[0].rows.length,2);assert.equal(m.riskSections[1].rows.length,2);assert.equal(m.riskSections[0].rows[0][4],'20호');});
test('later future or planned events are never current achievements; group missing totals remain null',()=>{const c=fixture();c.data.cohorts[0].events=[{stage:'SUPPLY',event_date:'2027-01-01',units:8},{stage:'CONSTRUCTION',event_date:'2026-01-01',units:8,origin:'PLANNED'}];assert.equal(report.model(c).groups[0].construction,null);assert.equal(report.model(c).groups[0].supply,null);});
test('report preserves chosen comparison date and historical measurement wording',()=>{const c=fixture();c.scope.comparison_date='2026-09-30';c.scope.data_as_of_date='2026-10-22';const m=report.model(c),md=report.markdown(m);assert.match(md,/보조 기준일: 2026-09-30/);assert.match(md,/2026-09-30 누적 측정/);assert.doesNotMatch(md,/2026년 말 착공 예상/);assert.equal(m.charts[0].series[1].label,'2026-09-30 누적 측정');});

test('policy and program reports exactly preserve the former model, HTML and Markdown',()=>{
 const previous=vm.runInContext('PortfolioProgressReport',context);
 for(const kind of ['policy','program']){const c=fixture();c.kind=kind;const m=report.model(c),old=previous.model(c);assert.equal(JSON.stringify(m),JSON.stringify(old));assert.equal(report.html(m),previous.html(old));assert.equal(report.markdown(m),previous.markdown(old));assert.match(report.html(m),/Ⅲ. 지연·주의 사업 점검/);assert.doesNotMatch(report.html(m),/1부\.|2부\.|120개월/);}
});
test('only explicit stage events count and planned measurements cannot become project achievements',()=>{
 const c=fixture();
 c.kind='project';c.data.project={project:{id:'p',name:'P',planned_units:8},cells:{BUSINESS:{management:{measurement:[{date:'2026-01-01',units:8,origin:'PLANNED'}],target:[{date:'2026-01-01',units:8}]}}}};
 assert.equal(report.model(c).stageRows[0].current,null);assert.equal(report.model(c).progress.rows[0].actual,null);
});
test('location uses household totals including five-plus, handles zero baselines and separates planned facilities',()=>{
 const c=fixture();c.kind='project';c.data.project={project:{id:'p',name:'P'},cells:{}};c.data.area={region:'경기도',municipality:'시험시',household_size:[{year:2020,total:100,sizes:{'1':10,'2':20,'3':0,'4':null,'5+':70}},{year:2025,total:200,sizes:{'1':30,'2':40,'3':10,'4':20,'5+':100}}]};
 c.data.infrastructure={origin:{approximate:true},collected_at:'2026-10-22',items:[{kind:'school',name:'운영학교',distance_m:300},{kind:'school',name:'계획학교',distance_m:20,service_status:'PLANNED'},{kind:'subway',name:'역',distance_m:1500}],planned_facilities:[{kind:'school',name:'계획학교',opening_date:'2027-03-01',distance_m:20}]};
 const m=report.model(c),rows=m.location.sections[0].rows,html=report.html(m);
 assert.equal(rows[0][3],'20가구 / 200.0%');assert.equal(rows[0][4],'15.0%');assert.equal(rows[2][3],'10가구 / 산출 불가');assert.equal(rows[3][3],'비교 미확보');
 const facilities=m.location.sections[1].rows;assert.equal(facilities.find(r=>r[0]==='학교')[1],'운영학교');assert.equal(facilities.find(r=>r[0]==='학교')[3],'1개');assert.equal(facilities[0][3],'0개');assert.match(html,/대표점 기준 참고 거리/);assert.match(html,/2027-03-01/);assert.match(html,/30가구/);assert.doesNotMatch(html,/NaN|Infinity/);
 c.data.area.household_size=c.data.area.household_size.slice(-1);assert.equal(report.model(c).location.sections[0].rows[0][3],'비교 미확보');
});

test('part one contains only summary and overview, stage cards, then a five-stage 120-month schedule',()=>{
 const c={kind:'project',scope:{name:'사업',year:2026,as_of_date:'2026-10-22'},data:{project:{project:{id:'p',name:'사업',planned_units:8},cells:{}}}};
 const dates={BUSINESS:['2020-04-09','2025-02-25'],APPROVAL:['2023-02-21','2025-02-25'],CONSTRUCTION:['2025-02-25','2025-02-25'],SUPPLY:['2025-06-30','2025-06-30'],MOVE_IN:['2028-03-31','2028-03-31']};
 for(const [stage,[target,actual]] of Object.entries(dates))c.data.project.cells[stage]={management:{target:[{date:target,units:8}],measurement:[{date:actual,units:8}]}};
 const m=report.model(c),html=report.html(m),first=html.split('<h2>1부.')[1].split('<h2 id="report-location"')[0],md=report.markdown(m).split('## 2부.')[0];
 assert.equal(m.schedule.start,'2020-04');assert.equal(m.schedule.end,'2030-03');assert.equal(m.schedule.months.length,120);assert.equal(m.schedule.rows[0].points.length,5);assert.equal(m.schedule.rows[0].points.at(-1).actual,null);
 assert.ok(first.indexOf('추진 현황 요약')<first.indexOf('report-meta'));assert.ok(first.indexOf('report-meta')<first.indexOf('사업화부터 입주까지 단계별 진행'));assert.ok(first.indexOf('사업화부터 입주까지 단계별 진행')<first.indexOf('사업 단계별 목표·실적 일정 · 10년'));
 assert.equal((first.match(/<figure\b/g)||[]).length,2);assert.equal((first.match(/data-schedule-month=/g)||[]).length,120);
 for(const removed of ['기준일 현재 목표 대비 이행','단계별 실적과 목표 물량','목표일 대비 이행 일정','중점 점검 사업 현황','지연·주의 사업 및 점검 단계','향후 단계별 이행 일정','실적·목표 비교 기준']){assert.ok(!first.includes(removed),removed);assert.ok(!md.includes(removed),removed);}
 const svg=first.split('class="report-schedule"').at(-1);assert.match(first,/stroke="#a5cdee"/);assert.match(first,/stroke="#e681a8"/);
 const schedule=first.slice(first.indexOf('aria-label="사업 단계별 목표·실적 일정'));
 assert.match(schedule,/y="360"[^>]*>사업화/);assert.match(schedule,/y="280"[^>]*>인허가/);assert.match(schedule,/y="200"[^>]*>착공/);assert.match(schedule,/y="120"[^>]*>공급/);assert.match(schedule,/y="40"[^>]*>입주/);assert.doesNotMatch(schedule,/>준공</);
});
test('schedule handles absent dates without fabricating a timeline or rendering invalid coordinates',()=>{
 const c=fixture();c.kind='project';c.data.project={project:{id:'p',name:'미확보'},cells:{}};const m=report.model(c);assert.equal(m.schedule.start,null);assert.equal(m.schedule.months.length,0);assert.match(report.html(m),/일정 데이터 미확보/);assert.doesNotMatch(report.html(m),/NaN|Infinity/);
});

test('legends use printable colored SVG samples and distinguish date estimates from quantity estimates',()=>{
 const c={kind:'project',scope:{name:'사업',year:2026,as_of_date:'2026-10-22'},data:{project:{project:{id:'p',name:'사업',planned_units:8},cells:{
  BUSINESS:{management:{target:[{date:'2020-01-01',units:8}],measurement:[{date:'2020-01-01',units:8,inferred:true,field_provenance:{event_date:{rule:'TARGET_EQUALS_MISSING_MEASUREMENT'}}}]}},
  CONSTRUCTION:{management:{target:[{date:'2024-01-01',units:8}],measurement:[{date:'2024-01-01',units:8,inferred:true,field_provenance:{event_date:{rule:'SOURCE_ACCEPTED'},units:{rule:'TARGET_EQUALS_MISSING_MEASUREMENT'}}}]}}
 }}}};
 const m=report.model(c),html=report.html(m),points=m.schedule.rows[0].points;
 assert.equal(points[0].actualEstimated,true);assert.equal(points[2].actualEstimated,false);
 assert.match(html,/<svg class="report-legend-swatch"[^>]*width="34"[^>]*height="16"/);assert.match(html,/stroke="#a5cdee"/);assert.match(html,/stroke="#e681a8"/);assert.doesNotMatch(html,/<i style="background:/);assert.match(html,/data-schedule-estimated="true"/);assert.match(html,/추정\(선후관계 검증\)/);assert.match(html,/print-color-adjust:exact/);
 const portfolio=report.html(report.model(fixture()));assert.match(portfolio,/report-legend-swatch/);assert.doesNotMatch(portfolio,/<i style="background:/);
});

test('a collected milestone date remains visible when its quantity is unavailable',()=>{
 const c={kind:'project',scope:{name:'사업',year:2026,as_of_date:'2026-10-22'},data:{project:{project:{id:'p',name:'사업'},cells:{CONSTRUCTION:{management:{measurement:[{date:'2025-03-01',units:null}],target:[]}}}}}};
 const m=report.model(c);assert.equal(m.schedule.rows[0].points[2].actual,'2025-03-01');assert.equal(m.stageRows[2].current,null);
});
