const test=require('node:test'),assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs'),path=require('node:path');
const context={num:n=>Number(n).toLocaleString('en-US'),esc:String};vm.createContext(context);vm.runInContext(fs.readFileSync(path.join(__dirname,'../../web/assets/policy-stage-flow.js'),'utf8')+';globalThis.flow=PolicyStageFlow;',context);
const status=(targets,actuals,extra={})=>context.flow.comparisonStatus({asOf:'2026-10-13',comparisons:{SUPPLY:{target_points:targets,actual_points:actuals}},...extra},'SUPPLY');
const due={date:'2026-09-30',units:1000},observed={date:'2026-09-30',units:700};
test('dated cumulative difference uses the threshold; interpolated future goals are not overdue',()=>{
 const result=status([due],[observed]);assert.equal(result.status,'DELAYED');assert.equal(result.gap,300);assert.equal(result.rate,30);
 assert.equal(status([{date:'2026-12-31',units:1000}],[observed]).status,'NOT_DUE');
});
test('missing actuals remain unknown; latest measured and explicit zero are compared',()=>{
 assert.equal(status([due],[]).status,'NO_ACTUAL');assert.equal(status([due],[]).gap,null);
 assert.equal(status([due],[{date:'2026-08-31',units:700}]).status,'DELAYED');
 assert.equal(status([due],[{date:'2026-09-30',units:0}]).gap,1000);
 assert.equal(status([due],[{date:'2026-11-01',units:1000}]).status,'NO_ACTUAL');
});
test('early goal attainment is retained and missing targets never imply zero',()=>{
 assert.equal(status([due],[{date:'2026-09-29',units:1000}]).status,'REACHED');
 assert.equal(status([],[observed]).status,'NO_TARGET');
});
test('confirmed delays deduplicate projects and officer targets take precedence',()=>{
 const m={asOf:'2026-10-13',comparisons:{SUPPLY:{target_points:[due],management_points:[{date:'2026-09-30',units:800}],actual_points:[observed]}},delays:[{stage:'SUPPLY',project_id:'p',units:20},{stage:'SUPPLY',project_id:'p',units:30}]};
 const result=context.flow.comparisonStatus(m,'SUPPLY');assert.equal(result.gap,100);assert.equal(result.confirmedUnits,30);
});

test('reference axis magnifies early activity without counting the policy remainder',()=>{
 const points=[{date:'2026-10-14',totals:{POLICY:210826,UNKNOWN:1677,APPROVAL:3497}}];
 const before=JSON.stringify(points),result=context.flow.referenceAxis({points,asOf:'2026-10-14',fullMax:216000,comparisons:{CONSTRUCTION:{target_points:[{date:'2030-12-31',units:216000}]}}});
 assert.equal(result.focused,true);assert.equal(result.max,4000);assert.equal(JSON.stringify(points),before);
 assert.equal(result.start,'2026-07-14');assert.equal(result.end,'2027-01-14');
});
test('reference axis follows dated goals, keeps cumulative stages separate, and changes with reference date',()=>{
 const comparisons={BUSINESS:{target_points:[{date:'2026-07-01',units:5000},{date:'2027-12-31',units:50000}]},APPROVAL:{target_points:[{date:'2026-07-01',units:5000}]}};
 const early=context.flow.referenceAxis({comparisons,asOf:'2026-07-01',fullMax:216000});
 const later=context.flow.referenceAxis({comparisons,asOf:'2027-10-01',fullMax:216000});
 assert.ok(early.max<later.max);assert.ok(early.max<216000);
 const same=context.flow.referenceAxis({comparisons:{APPROVAL:comparisons.APPROVAL,BUSINESS:comparisons.APPROVAL},asOf:'2026-07-01',fullMax:216000});
 assert.equal(same.peak,5000);assert.ok(same.max<10000);
});
test('reference axis preserves observed zero and has a finite full-range fallback',()=>{
 for(const points of [[],[{date:'2026-10-14',totals:{POLICY:216000}}]]){
  const result=context.flow.referenceAxis({points,asOf:'2026-10-14',fullMax:216000});assert.equal(result.max,216000);assert.equal(result.focused,false);
 }
 assert.ok(context.flow.referenceAxis({asOf:'bad',fullMax:0}).max>0);
 const r=context.flow.referenceAxis({asOf:'2026-10-31',points:[{date:'2026-10-31',totals:{BUSINESS:1}}]});assert.equal(r.start,'2026-07-31');assert.equal(r.end,'2027-01-31');assert.ok(Number.isInteger(r.max/4));
});

test('tracked stacks conserve disjoint quantities and keep missing measurements distinct',()=>{
 const comparisons={BUSINESS:{actual_points:[{date:'2026-01-01',units:100}]},APPROVAL:{actual_points:[{date:'2026-02-01',units:80}]},CONSTRUCTION:{actual_points:[{date:'2026-03-01',units:60}]},SUPPLY:{actual_points:[{date:'2026-04-01',units:40}]},MOVE_IN:{target_points:[{date:'2027-01-01',units:100}],actual_points:[{date:'2026-05-01',units:10}]}};
 const p=context.flow.trackingPoints({comparisons,start:2026,end:2027,asOf:'2026-10-14'}),now=p.find(p=>p.date==='2026-10-14');
 assert.equal(now.totals.BUSINESS,20);assert.equal(now.totals.APPROVAL,20);assert.equal(now.totals.CONSTRUCTION,20);assert.equal(now.totals.SUPPLY,30);assert.equal(now.totals.MOVE_IN,10);
 assert.equal(Object.values(now.totals).reduce((a,b)=>a+b,0),100);
 assert.equal(p.find(p=>p.date==='2027-01-01').totals.MOVE_IN,10);
 assert.equal(p[0].cumulative.MOVE_IN,null);
});
test('stale observations use management severity while retaining a refresh notice',()=>{
 const result=status([due],[{date:'2026-08-31',units:700}]);assert.equal(result.status,'DELAYED');assert.equal(result.difference,300);assert.equal(result.gap,300);assert.equal(result.stale,true);
 const html=context.flow.delaySummary({asOf:'2026-10-13',comparisons:{SUPPLY:{target_points:[due],actual_points:[{date:'2026-08-31',units:700}]}},stages:{SUPPLY:'공급'}});
 assert.match(html,/목표 대비 부족 300호/);assert.match(html,/갱신 필요/);assert.match(html,/측정값/);
});

test('all five shortage callouts fit without overlap even at the same clipped value',()=>{
 for(const anchor of [85,240,410]){
  const labels=context.flow.layoutCallouts(['BUSINESS','APPROVAL','CONSTRUCTION','SUPPLY','MOVE_IN'].map(stage=>({stage,anchor})),89,406);
  assert.equal(labels.length,5);assert.ok(labels[0].y>=89);assert.ok(labels.at(-1).y+36<=406);
  for(let i=1;i<labels.length;i++)assert.ok(labels[i].y>=labels[i-1].y+44);
 }
});

test('monthly curve samples retain exact reference values without changing raw observations',()=>{
 const m={start:2026,end:2026,asOf:'2026-10-14',comparisons:{SUPPLY:{actual_points:[{date:'2026-09-03',units:10},{date:'2026-10-10',units:30}],target_points:[]}}};
 const before=JSON.stringify(m),points=context.flow.monthlyPoints(m);
 assert.equal(points.find(p=>p.date==='2026-09-30').cumulative.SUPPLY,10);
 assert.equal(points.find(p=>p.date===m.asOf).cumulative.SUPPLY,30);
 assert.equal(points.length,14);assert.equal(JSON.stringify(m),before);
});


test('two percent is inclusive and assessed before display rounding',()=>{
 const a=context.flow.assessGap;
 for(const [target,actual,expected] of [[10000,9800,'DELAYED'],[10000,9801,'WARNING'],[10000,9999,'WARNING'],[10000,10000,'NORMAL'],[10000,11000,'NORMAL'],[10000,null,'UNKNOWN'],[0,0,'UNKNOWN'],[null,10,'UNKNOWN'],[100,0,'DELAYED']])assert.equal(a(target,actual).status,expected);
 assert.equal(a(125900,76043).status,'DELAYED');
 assert.equal(a(80000,79442).status,'WARNING');
 assert.equal(a(57300,56727).status,'WARNING');
});
test('future goals and missing values do not produce colored shortage cards',()=>{
 const html=context.flow.summaryTable({asOf:'2026-10-13',stages:{SUPPLY:'공급'},comparisons:{SUPPLY:{target_points:[{date:'2026-12-01',units:1000}],actual_points:[{date:'2026-10-01',units:0}]}}});
 assert.doesNotMatch(html,/is-short|is-warning/);
 const check=status([due],[{date:'2026-09-30',units:991}]);assert.equal(check.status,'WARNING');assert.equal(check.assessment.color,'#e8ad25');
});

test('rounding never displays a warning as 2 percent or zero percent',()=>{assert.equal(context.flow.formatGapRate(1.999),'2% 미만');assert.equal(context.flow.formatGapRate(.001),'0.1% 미만');assert.equal(context.flow.formatGapRate(2),'2.0%');});
