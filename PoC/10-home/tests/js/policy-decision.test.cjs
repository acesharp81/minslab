const assert=require('node:assert/strict');
const {analyze,forecast}=require('../../web/assets/policy-decision.js');
const base={id:'a',name:'A',units:100,events:[{stage:'SUPPLY',event_date:'2025-06-01',units:80}],schedules:[{stage:'MOVE_IN',due_date:'2026-03-01',units:100}]};
const planned={id:'b',units:200,events:[],schedules:[{stage:'SUPPLY',due_date:'2027-07-01',units:200}]};
let x=analyze([base,planned],'2026-10-12',2026);
assert.equal(x.suppliedUnits,80);assert.equal(x.pendingUnits,80);assert.equal(x.pastDue.length,1);assert.equal(x.projects[0].followup,'VERIFY_DUE');assert.equal(x.projects[1].supplied,null);
assert.equal(x.annual.find(a=>a.year===2027).pending,null);assert.equal(x.annual.find(a=>a.year===2024).pending,null);
x=analyze([{...base,events:[...base.events,{stage:'MOVE_IN',event_date:'2026-09-01',units:5}]}],'2026-10-12',2026);
assert.equal(x.pendingUnits,0);assert.equal(x.projects[0].followup,'STARTED'); // Start known, not 100 households occupied.
x=analyze([base],'2026-10-12',2025);assert.equal(x.pastDue.length,0);
x=analyze([{...base,events:[]}],'2026-10-12',2026);assert.equal(x.pendingUnits,null);
const input=JSON.stringify([base,planned]);let f=forecast([base,planned],'2026-10-12',12);assert.equal(f.total,200);assert.equal(f.years.find(r=>r.year===2027).baseline,200);assert.equal(f.years.find(r=>r.year===2028).scenario,200);assert.equal(JSON.stringify([base,planned]),input);
f=forecast([{...base,schedules:[{stage:'SUPPLY',due_date:'2031-07-01',units:100},{stage:'SUPPLY',due_date:'2031-07-01',units:100}]}],'2026-10-12',12);assert.equal(f.total,20);assert.equal(f.outside,20);
console.log('Policy decision semantics: missing ≠ zero, start ≠ occupied, historical cutoffs, no duplicate schedules, scenario isolation OK');
