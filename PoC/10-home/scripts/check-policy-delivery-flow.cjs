'use strict';
const assert=require('node:assert/strict');
const flow=require('../web/assets/policy-delivery-flow.js');
const group={target_units:1000,project_ids:['A','B'],chart_schedule_ids:['A','B']};
const items=[
  {id:'A',name:'A4',schedule_events:[{stage:'SUPPLY',month:'2025-12',units:200},{stage:'SUPPLY',month:'2026-11',units:100}],notice_evidence_id:'N1',notice_source_date:'2026-03-01',current_notice_units:100},
  {id:'B',name:'S1',schedule_events:[{stage:'SUPPLY',month:'2026-09',units:300},{stage:'SUPPLY',month:'2027-08',units:200}],notice_evidence_id:'N2',notice_source_date:'2026-09-20',current_notice_units:150},
];
let model=flow.model({group,items,asOf:'2026-10-10',selectedYear:2027});
assert.equal(model.current.actual,250);
assert.equal(model.current.overdue,250); // A 200-100; B 300-150
assert.equal(model.current.upcoming,100); // November remains within the current year
assert.equal(model.chosen.upcoming,300); // November and 2027 source schedules
assert.equal(model.chosen.remaining,200);
assert.equal(model.issues.length,2);
assert.match(flow.render(model),/일정 경과·공고 미확인/);
assert.match(flow.render(model),/현재 2026.10/);
assert.match(flow.render(model),/2026년 400호/);
assert.match(flow.render(model),/11년 전체 흐름/);
assert.match(flow.render(model),/data-flow-layer="overdue"/);
assert.match(flow.render(model),/ C[0-9]/); // monthly curved joins, not year-sized rectangles
assert.equal(model.monthlyPoints.length,132);
assert.equal(model.focusStart,2026);
const later=flow.model({group,items,asOf:'2026-10-10',selectedYear:2029});
assert.equal(later.focusStart,2028);
assert.match(flow.render(later),/2028.01/);
assert.doesNotMatch(flow.render(later),/>2025.01</);
model=flow.model({group,items,asOf:'2026-08-10',selectedYear:2026});
assert.equal(model.current.overdue,100); // September B not overdue yet
assert.equal(model.current.actual,100);
const shared=[items[0],{...items[1],notice_evidence_id:'N1',notice_source_date:'2026-03-01',current_notice_units:100}];
model=flow.model({group,items:shared,asOf:'2026-10-10'});
assert.equal(model.current.actual,100); // Same notice not double-counted
model=flow.model({group:{...group,target_units:null},items,asOf:'2026-10-10'});
assert.equal(model.target,null);
assert.equal(model.current.remaining,null);
assert.match(flow.render(model),/미확보/);
console.log('Policy delivery flow checks passed');
