const test=require('node:test'),assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs'),path=require('node:path');
const ctx=vm.createContext({});vm.runInContext(fs.readFileSync(path.join(__dirname,'../../web/assets/policy-region-map.js'),'utf8'),ctx);const distribution=vm.runInContext('PolicyRegionMap.stageDistribution',ctx);
const event=(stage,extra={})=>({stage,event_date:'2026-04-01',units:100,...extra});
const project=(id,events=[])=>({id,units:100,events});
const calc=rows=>distribution(rows,'2026-12-31','2026-10-16');
test('shares are weighted by housing units, not project count',()=>{
 const keys=['POLICY','BUSINESS','APPROVAL','CONSTRUCTION','SUPPLY','MOVE_IN'],counts=[5,5,2,1,1,1],rows=[];
 keys.forEach((key,i)=>{for(let n=0;n<counts[i];n++)rows.push(project(rows.length,keys.slice(1,i+1).map(k=>event(k))))});rows[0].units=5000;
 const d=calc(rows);assert.equal(d.total,6400);assert.deepEqual(Array.from(keys,k=>d.counts[k]),[5400,500,200,100,100,100]);assert.equal(Object.values(d.counts).reduce((a,b)=>a+b),6400);assert.equal(d.unit,"호");
});
test('counts each project once and uses furthest recorded stage rather than latest event date',()=>{
 const d=calc([project('a',[event('SUPPLY')]),project('a',[event('BUSINESS',{event_date:'2026-10-01'})]),project('b',[event('COMPLETION')])]);
 assert.equal(d.total,200);assert.equal(d.counts.SUPPLY,100);assert.equal(d.counts.CONSTRUCTION,100);assert.equal(d.counts.BUSINESS,0);
});
test('future, planned, delayed and zero quantity events do not advance projects; past cutoff applies',()=>{
 const rows=[project(1,[event('MOVE_IN',{event_date:'2027-01-01'})]),project(2,[event('SUPPLY',{origin:'PLANNED'})]),project(3,[event('CONSTRUCTION',{status:'DELAYED'})]),project(4,[event('APPROVAL',{units:0})]),project(5,[event('BUSINESS')])];
 const d=calc(rows);assert.equal(d.counts.POLICY,400);assert.equal(d.counts.BUSINESS,100);assert.equal(distribution(rows,'2025-12-31','2026-10-16').counts.POLICY,500);assert.equal(calc([]).total,0);
});

test('partial supply and occupancy leave remaining units in earlier stages, without overlap',()=>{
 const d=calc([{id:'partial',units:1000,events:[event('CONSTRUCTION',{units:600}),event('SUPPLY',{units:200}),event('MOVE_IN',{units:50})]}]);
 assert.deepEqual(Array.from(['POLICY','BUSINESS','APPROVAL','CONSTRUCTION','SUPPLY','MOVE_IN'],k=>d.counts[k]),[400,0,0,400,150,50]);assert.equal(d.total,1000);
});
test('repeated or inconsistent stage observations stay capped and quantities remain conserved',()=>{
 const d=calc([{id:'a',units:1000,events:[event('BUSINESS',{units:100}),event('SUPPLY',{units:500}),event('SUPPLY',{units:500}),event('MOVE_IN',{units:1500})]}]);
 assert.equal(d.counts.MOVE_IN,1000);assert.equal(Object.values(d.counts).reduce((a,b)=>a+b),1000);assert.ok(Object.values(d.counts).every(n=>n>=0));assert.equal(calc([{id:'b',units:0,events:[event('SUPPLY')]}]).total,0);
});
