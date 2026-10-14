const test=require('node:test'),assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs'),path=require('node:path');
const ctx={esc:String,num:String};vm.createContext(ctx);
for(const file of ['project-information.js','project-location.js'])vm.runInContext(fs.readFileSync(path.join(__dirname,'../../web/assets',file),'utf8'),ctx);
const stage=v=>vm.runInContext('ProjectWorkspace.currentStage',ctx)(v),visible=vm.runInContext('ProjectLocation.visibleFacilities',ctx);
const measured=(date,units,extra={})=>({management:{measurement:[{date,units,...extra}]}});
test('current stage uses recorded progress, including officer estimates, not future targets or zero quantities',()=>{
 const value={as_of_date:'2026-10-14',cells:{BUSINESS:measured('2026-01-01',500),CONSTRUCTION:measured('2026-07-31',500),SUPPLY:measured('2026-02-28',200,{manual:true,inferred:true}),MOVE_IN:{...measured(null,null),target:[{date:'2027-01-31',units:500}]}}};
 assert.equal(stage(value),'SUPPLY');
 value.cells.MOVE_IN=measured('2026-11-01',500);assert.equal(stage(value),'SUPPLY');
 value.cells.MOVE_IN=measured('2026-09-01',0);assert.equal(stage(value),'SUPPLY');
 value.cells.MOVE_IN=measured('2026-09-01',20);assert.equal(stage(value),'MOVE_IN');
});
test('dated milestone without quantity and positive progress are reached; documents alone are not',()=>{
 assert.equal(stage({as_of_date:'2026-10-14',cells:{APPROVAL:measured('2026-01-01',null)}}),'APPROVAL');
 assert.equal(stage({as_of_date:'2026-10-14',cells:{CONSTRUCTION:{management:{progress_pct:{date:'2026-01-01',pct:30}}}}}),'CONSTRUCTION');
 assert.equal(stage({as_of_date:'2026-10-14',cells:{BUSINESS:{sources:[{kind:'DOCUMENT',date:'2026-01-01'}]}}}),null);
});
test('nearest subway stays visible at every radius; other facilities remain radius filtered; planned rail excluded',()=>{
 const rows=[{kind:'gtx',name:'먼역',distance_m:4400},{kind:'subway',name:'가까운역',distance_m:1800},{kind:'bus',name:'버스',distance_m:228},{kind:'school',name:'학교',distance_m:900},{kind:'subway',name:'계획역',distance_m:30,service_status:'PLANNED'}];
 for(const radius of [500,1000,3500])assert.equal(visible(rows,radius).find(r=>r.kind==='subway').name,'가까운역');
 assert.equal(visible(rows,500).some(r=>r.kind==='school'),false);assert.equal(visible(rows,1000).some(r=>r.kind==='school'),true);
 assert.equal(rows[0].kind,'gtx');assert.equal(visible(rows,500).some(r=>r.name==='계획역'),false);
});
