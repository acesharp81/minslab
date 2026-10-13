const test=require('node:test'),assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs'),path=require('node:path');
const context={num:n=>Number(n).toLocaleString('en-US'),esc:String};vm.createContext(context);vm.runInContext(fs.readFileSync(path.join(__dirname,'../../web/assets/policy-stage-flow.js'),'utf8')+';globalThis.flow=PolicyStageFlow;',context);
const status=(targets,actuals,extra={})=>context.flow.comparisonStatus({asOf:'2026-10-13',comparisons:{SUPPLY:{target_points:targets,actual_points:actuals}},...extra},'SUPPLY');
const due={date:'2026-09-30',units:1000},observed={date:'2026-09-30',units:700};
test('dated cumulative difference is a review gap; interpolated future goals are not overdue',()=>{
 const result=status([due],[observed]);assert.equal(result.status,'GAP');assert.equal(result.gap,300);assert.equal(result.rate,30);
 assert.equal(status([{date:'2026-12-31',units:1000}],[observed]).status,'NOT_DUE');
});
test('missing and stale actuals remain unknown; explicit zero is evidence',()=>{
 assert.equal(status([due],[]).status,'NO_ACTUAL');assert.equal(status([due],[]).gap,null);
 assert.equal(status([due],[{date:'2026-08-31',units:700}]).status,'STALE_ACTUAL');
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
