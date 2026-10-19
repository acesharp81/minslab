const test=require('node:test'),assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs'),path=require('node:path');
const ctx={num:n=>Number(n).toLocaleString('en-US'),esc:String};vm.createContext(ctx);vm.runInContext(fs.readFileSync(path.join(__dirname,'../../web/assets/policy-stage-flow.js'),'utf8'),ctx);vm.runInContext(fs.readFileSync(path.join(__dirname,'../../web/assets/map-progress-tracking.js'),'utf8')+';globalThis.view=MapProgressTracking;',ctx);
test('confirmed one month or range only; unknown endpoints and same month are concise',()=>{
 const label=ctx.view.periodLabel;
 assert.equal(label({start:'2026-04-01'}),'2026.4.');
 assert.equal(label({start:'2026-04-01',end:'2026-07-31'}),'2026.4.~2026.7.');
 assert.equal(label({end:'2026-07-31'}),'2026.7.');
 assert.equal(label({start:'2026-04-01',end:'2026-04-30'}),'2026.4.');assert.equal(label({}),'');
});
test('cards never substitute targets or later-stage cumulative counts for stage actuals',()=>{
 const d={as_of_date:'2026-10-15',policy_target:1332,stages:{},comparisons:{BUSINESS:{label:'사업화',target_points:[{date:'2026-04-01',units:1332}],actual_points:[{date:'2026-10-01',units:1332}],display_actual_points:[{date:'2026-04-01',units:100}],actual_period:{start:'2026-04-01'}},APPROVAL:{label:'인허가',actual_points:[{date:'2026-10-01',units:1332}],display_actual_points:[]}}};
 const html=ctx.view.summary(d,'사업');assert.match(html,/사업화<\/small><b>100호/);assert.match(html,/인허가<\/small><b>미측정/);assert.match(html,/2026.4./);assert.doesNotMatch(html,/누적 목표/);
});

test('actual cards preserve the shared two-percent red/yellow management rule',()=>{
 const d={as_of_date:'2026-10-15',policy_target:1000,comparisons:{BUSINESS:{target_points:[{date:'2026-04-01',units:1000}],display_actual_points:[{date:'2026-04-01',units:970}]},APPROVAL:{target_points:[{date:'2026-04-01',units:1000}],display_actual_points:[{date:'2026-04-01',units:990}]}}};
 const html=ctx.view.summary(d,'사업');assert.match(html,/gap-management delayed/);assert.match(html,/gap-management warning/);assert.doesNotMatch(html,/누적 목표/);
});
