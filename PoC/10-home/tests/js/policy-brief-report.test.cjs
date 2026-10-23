const test=require('node:test'),assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs'),path=require('node:path');
const ctx={};vm.createContext(ctx);for(const file of ['policy-stage-flow.js','policy-brief-report.js'])vm.runInContext(fs.readFileSync(path.join(__dirname,'../../web/assets',file),'utf8'),ctx);const report=vm.runInContext('PolicyBriefReport',ctx);
const fixture=ps=>({kind:'policy',scope:{policy_id:'POL',name:'정책',as_of_date:'2026-10-23'},data:{plan:{name:'9·7 정책',target_units:1350000},cohorts:ps}});
const event=(stage,units,event_date='2026-01-01',more={})=>({stage,units,event_date,origin:'SOURCE',...more});
const project=(id,units,events=[],schedules=[])=>({id,name:id,units,events,schedules,region:'경기도',program_id:'PRG'});
const plan=(stage,units,due_date,more={})=>({stage,units,due_date,origin:'MANUAL',managed_schedule:true,...more});
test('seven chapters are built without appendices; null, zero, future remain distinct',()=>{const input=fixture([project('P',10,[event('BUSINESS',0),event('SUPPLY',10,'2027-01-01')])]),before=JSON.stringify(input),m=report.build(input);assert.equal(m.sections.length,7);assert.equal(m.appendices.length,0);assert.equal(m.stages[0].current,0);assert.equal(m.stages.find(r=>r.stage==='MOVE_IN').current,null);assert.equal(m.stages[0].rate,'산정 불가');assert.equal(JSON.stringify(input),before);assert.match(report.html(m),/실입주 자료 미확보/);assert.match(report.csv(report.appendixModel(m)),/BUSINESS.current/);assert.equal(m.metrics.find(r=>r.metric_id==='BUSINESS.current').value,0);});
test('source, officer, estimate, successor increments are disjoint and preserve reasons',()=>{const p=project('P',100,[event('CONSTRUCTION',20),event('CONSTRUCTION',40,'2026-02-01',{origin:'MANUAL',reason:'검토 채택'}),event('CONSTRUCTION',80,'2026-03-01',{origin:'MANUAL',inferred:true,reason:'관리 추정'}),event('COMPLETION',100)]),c=report.contribution(p,'CONSTRUCTION','2026-10-23');assert.deepEqual(JSON.parse(JSON.stringify(c.composition)),{SOURCE:20,ADOPTED:20,ESTIMATE:40,SEQUENCE:20,REVIEW:0});assert.equal(c.value,100);assert.ok(c.events.some(e=>e.reason==='검토 채택'));assert.equal(report.contribution(p,'MOVE_IN','2026-10-23').value,null);});
test('supply and contracts cannot create starts',()=>{const p=project('P',100,[event('SUPPLY',100),event('CONSTRUCTION',100,'2026-01-01',{origin:'PLANNED'})]);assert.equal(report.contribution(p,'CONSTRUCTION','2026-10-23').value,null);});
test('managed schedules supersede source versions, repeated portions are not summed twice',()=>{const p=project('AA19',1323,[],[plan('SUPPLY',991,'2026-11-01'),plan('SUPPLY',991,'2026-11-01'),plan('SUPPLY',332,'2026-12-01'),{stage:'SUPPLY',units:1323,due_date:'2026-10-01',origin:'SOURCE',source_object_id:'old'}]);assert.deepEqual(Array.from(report.schedules(p,'SUPPLY'),r=>r.units),[991,332]);});
test('same representative ID deduplicates Bupyeong 700 to 350 but distinct AA13 blocks remain',()=>{const a=project('BUP',350,[event('BUSINESS',350)]),m=report.build(fixture([a,a,project('AA13-1',50,[event('BUSINESS',50)]),project('AA13-2',60,[event('BUSINESS',60)])]));assert.equal(m.project_count,3);assert.equal(m.stages[0].current,460);assert.equal(m.checks.at(-1).status,'DEDUPLICATED');});
test('recruitment corrections use a capped maximum; project plan updates retain baseline',()=>{const p=project('A9',574,[event('SUPPLY',568),event('SUPPLY',574,'2026-03-01'),event('SUPPLY',6,'2026-04-01')],[plan('SUPPLY',574,'2026-03-01',{baseline:{units:568,due_date:'2026-02-01'}})]);assert.equal(report.contribution(p,'SUPPLY','2026-10-23').value,574);assert.equal(report.schedules(p,'SUPPLY')[0].baseline.units,568);assert.equal(report.periodActual(p,'SUPPLY','2026-03-01','2026-03-31'),6);});
test('regional filter recalculates all chapters, does not allocate national policy target',()=>{const a=project('Seoul',10,[event('BUSINESS',10)]);a.region='서울특별시';const m=report.build(fixture([a,project('Gyeonggi',20,[event('BUSINESS',20)])]),{region:'서울특별시'});assert.equal(m.project_count,1);assert.equal(m.stages[0].current,10);assert.equal(m.policy.target_units,1350000);assert.deepEqual(Array.from(m.metrics[0].excluded_project_ids),['Gyeonggi']);});
test('month/quarter precision is preserved and plans never become realized occupancy',()=>{assert.equal(report.precisionDate({due_date:'2027-03-31',precision:'MONTH'}),'2027-03');assert.equal(report.precisionDate({due_date:'2027-06-30',precision:'QUARTER'}),'2027년 2분기');const m=report.build(fixture([project('P',10,[],[plan('MOVE_IN',10,'2026-12-31')])]));assert.equal(m.stages.find(r=>r.stage==='MOVE_IN').current,null);assert.equal(m.stages.find(r=>r.stage==='MOVE_IN').expected,10);});
test('forecast reuses dashboard transfer arithmetic and has no ad hoc total addition',()=>{const p=project('P',100,[event('BUSINESS',100),event('APPROVAL',80),event('CONSTRUCTION',60),event('SUPPLY',20)],[plan('BUSINESS',100,'2026-01-01'),plan('APPROVAL',80,'2026-01-01'),plan('CONSTRUCTION',60,'2026-01-01'),plan('SUPPLY',20,'2026-01-01'),plan('SUPPLY',10,'2026-12-01')]);const m=report.build(fixture([p]));assert.equal(m.stages[0].expected,100);assert.equal(m.stages.find(r=>r.stage==='SUPPLY').expected,30);});
test('invalid periods fail and CSV formula strings/HTML markup are escaped',()=>{const p=project('=HYPERLINK("bad")',10);p.name='<script>alert(1)</script>';assert.throws(()=>report.build(fixture([p]),{period_start:'2027-01-01'}));const m=report.build(fixture([p]));assert.ok(!report.html(m).includes('<script>'));p.name='=HYPERLINK("bad")';assert.match(report.csv(report.build(fixture([p]))),/'=HYPERLINK/);});
test('separate type partitions include unresolved classifications without invented assignments',()=>{const p=project('LH 이름만 있는 사업',10,[event('CONSTRUCTION',10)]),m=report.build(fixture([p]));const table=m.sections[1].tables[0];assert.equal(table.rows.find(r=>r[0]==='공공주택')[2],'미확보');assert.equal(table.rows.find(r=>r[0]==='유형 미확인·복합')[2],'10호');});
test('archived official 32-row crosswalk remains plans, respects duplicate IDs and keeps disagreement reasons',()=>{
 const f=JSON.parse(fs.readFileSync(path.join(__dirname,'../fixtures/policy-brief-q4-20261022.json'),'utf8'));
 assert.equal(f.rows.length,32);
 const ps=f.rows.filter(r=>Number(r.count_once_units)>0).map(r=>project(r.home_cohort_id,Number(r.count_once_units),[],[plan('SUPPLY',Number(r.count_once_units),'2026-12-31',{basis:r.discrepancy_reason})]));
 const m=report.build(fixture(ps));
 assert.equal(m.stages.find(r=>r.stage==='SUPPLY').current,null);
 assert.equal(m.project_count,new Set(ps.map(p=>p.id)).size);
 const b=f.rows.find(r=>r.official_name==='인천부평 A');assert.equal(Number(b.count_once_units),350);
 const conflict=f.rows.find(r=>r.comparison_status==='SCOPE_DIFFERENT'&&Number(r.count_once_units)>0);
 assert.ok(m.input.data.cohorts.some(p=>p.schedules[0].basis===conflict.discrepancy_reason));
});
test('missing performance in a due-goal project cannot turn into a complete attainment rate',()=>{
 const a=project('A',10,[event('CONSTRUCTION',10)],[plan('CONSTRUCTION',10,'2026-01-01')]),b=project('B',10,[],[plan('CONSTRUCTION',10,'2026-01-01')]);
 const row=report.build(fixture([a,b])).stages.find(r=>r.stage==='CONSTRUCTION');
 assert.equal(row.current,10);assert.equal(row.target,20);assert.equal(row.rate,'산정 불가');assert.equal(row.remaining,null);assert.equal(row.comparison.rate,'100.0%');assert.equal(row.comparison.unknown_projects,1);
});

test('appendices are generated separately from pinned inputs without mutating the main report',()=>{
 const input=fixture([project('Seoul',10,[event('BUSINESS',10)]),project('Other',25,[event('BUSINESS',25)])]);input.data.cohorts[0].region='서울특별시';
 const m=report.build(input,{region:'서울특별시',period_start:'2026-10-01'});m.snapshot={input_sha256:'pinned-hash'};
 const before=JSON.stringify(m),main=report.html(m);
 assert.equal(m.appendices.length,0);assert.equal((main.match(/class="pb-section"/g)||[]).length,7);assert.ok(!main.includes('id="appendix-'));
 input.data.cohorts[0].units=999;
 const a=report.appendixModel(m);assert.equal(a.sections.length,0);assert.equal(a.appendices.length,3);assert.equal(a.project_count,1);assert.equal(a.snapshot.input_sha256,'pinned-hash');
 assert.equal(a.appendices[1].tables[0].rows.length,1);assert.match(a.appendices[1].tables[0].rows[0][0],/Seoul/);
 const html=report.html(a);assert.equal((html.match(/class="pb-section"/g)||[]).length,3);assert.ok(!html.includes('id="section-'));assert.match(html,/pinned-hash/);
 assert.equal(JSON.stringify(m),before);assert.equal(report.html(m),main);assert.equal(report.appendixModel(m).appendices,a.appendices);
 assert.equal(report.appendixModel(JSON.parse(before)).appendices.length,3);
 assert.match(report.csv(a),/BUSINESS.current/);assert.ok(!report.csv(m).includes('metric-manifest'));assert.ok(!report.markdown(m).includes('## 붙임'));
});
