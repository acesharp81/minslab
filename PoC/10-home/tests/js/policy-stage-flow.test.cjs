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
 assert.equal(result.focused,true);assert.ok(Math.abs(3497/result.max-.7)<.001);assert.equal(JSON.stringify(points),before);
 assert.equal(result.start,'2026-07-14');assert.equal(result.end,'2027-01-14');
});
test('reference axis follows dated goals, keeps cumulative stages separate, and changes with reference date',()=>{
 const comparisons={BUSINESS:{target_points:[{date:'2026-07-01',units:5000},{date:'2027-12-31',units:50000}]},APPROVAL:{target_points:[{date:'2026-07-01',units:5000}]}};
 const early=context.flow.referenceAxis({comparisons,asOf:'2026-07-01',fullMax:216000});
 const later=context.flow.referenceAxis({comparisons,asOf:'2027-10-01',fullMax:216000});
 assert.ok(early.max<later.max);assert.ok(early.max<216000);
 const same=context.flow.referenceAxis({comparisons:{APPROVAL:comparisons.APPROVAL,BUSINESS:comparisons.APPROVAL},asOf:'2026-07-01',fullMax:216000});
 assert.equal(same.peak,5000);assert.ok(Math.abs(5000/same.max-.7)<.001);
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
 assert.equal(points.length,14);assert.equal(context.flow.trackingPoints(m).find(p=>p.date==='2026-10-10').cumulative.SUPPLY,30);assert.equal(JSON.stringify(m),before);
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

test('cards pair current cumulative measurements with selected December saved cumulative plan',()=>{
 const comparisons={SUPPLY:{target_points:[{date:'2026-09-01',units:100},{date:'2026-12-31',units:450},{date:'2027-01-01',units:900}],actual_points:[{date:'2026-10-01',units:80},{date:'2026-11-01',units:200}]}};
 const html=context.flow.summaryTable({asOf:'2026-10-19',year:2026,stages:{SUPPLY:'공급'},comparisons});
 assert.match(html,/누적 측정량\(&#39;26\.10\.19\. 기준\)<\/small><b>80호/);
 assert.match(html,/예상 누적량\(&#39;26\.12\.31\. 기준\)<\/small><b>450호/);
 assert.doesNotMatch(html,/900호|200호|도래 목표/);
 const later=context.flow.summaryTable({asOf:'2026-10-19',year:2027,stages:{SUPPLY:'공급'},comparisons});
 assert.match(later,/예상 누적량\(&#39;27\.12\.31\. 기준\)<\/small><b>900호/);
 const missing=context.flow.summaryTable({asOf:'2026-10-19',year:2025,stages:{SUPPLY:'공급'},comparisons});
 assert.match(missing,/미측정/);
});


test('cards, graph and report projections share the larger stage baseline and dated goal increases',()=>{
 const keys=['BUSINESS','APPROVAL','CONSTRUCTION','SUPPLY','MOVE_IN'],actual=[120,100,80,40,10],target=[100,90,70,30,0],future=[140,120,100,50,10];
 const comparisons=Object.fromEntries(keys.map((k,i)=>[k,{actual_points:[{date:'2026-10-01',units:actual[i]}],target_points:[{date:'2026-10-01',units:target[i]},{date:'2026-12-31',units:future[i]}],forecast_points:[{date:'2026-12-31',units:999}]}]));
 const model={asOf:'2026-10-22',comparisonDate:'2026-12-31',stages:Object.fromEntries(keys.map(k=>[k,k])),comparisons};
 const values=context.flow.summaryValues(model),before=JSON.stringify(comparisons);
 // Starting exclusive stages: max(20,10), max(20,20), max(40,40), max(30,30), max(10,0).
 assert.equal(values.BUSINESS.expected_units,160);assert.equal(values.CONSTRUCTION.expected_units,110);assert.equal(values.CONSTRUCTION.remaining_plan_units,30);
 for(const k of keys)assert.equal(values[k].expected_units,context.flow.stageBands(model,'2026-12-31','actual')[k].cumulative);
 assert.equal(context.flow.projectedStages(model,model.asOf).CONSTRUCTION.units,40);
 const html=context.flow.summaryTable(model);assert.match(html,/160호/);assert.match(html,/110호/);assert.doesNotMatch(html,/999호/);assert.equal(JSON.stringify(comparisons),before);
});

test('reference dates independently measure historical and future cumulative values and quarter ends',()=>{
 const base={asOf:'2026-06-30',dataAsOf:'2026-10-22',comparisonDate:'2026-09-30',stages:{SUPPLY:'공급'},comparisons:{SUPPLY:{actual_points:[{date:'2025-12-01',units:20},{date:'2026-06-30',units:80},{date:'2026-09-01',units:120},{date:'2026-10-22',units:150}],forecast_points:[{date:'2026-09-01',units:200},{date:'2026-12-31',units:230}],target_points:[]}}};
 let v=context.flow.summaryValues(base).SUPPLY;assert.equal(v.current_units,80);assert.equal(v.expected_units,120);assert.equal(v.comparison_kind,'MEASUREMENT');
 v=context.flow.summaryValues({...base,comparisonDate:'2026-12-31'}).SUPPLY;assert.equal(v.current_units,80);assert.equal(v.expected_units,150);assert.equal(v.comparison_kind,'FORECAST');
 v=context.flow.summaryValues({...base,comparisonDate:'2025-12-31'}).SUPPLY;assert.equal(v.expected_units,20);
 v=context.flow.summaryValues({...base,comparisonDate:'2024-12-31'}).SUPPLY;assert.equal(v.expected_units,null);
 assert.equal(context.flow.quarterEnd('2026-02-10'),'2026-03-31');assert.equal(context.flow.quarterEnd('2026-04-01'),'2026-06-30');assert.equal(context.flow.quarterEnd('2026-09-30'),'2026-09-30');assert.equal(context.flow.quarterEnd('2026-10-22'),'2026-12-31');
 assert.match(context.flow.summaryTable(base),/누적 측정량\(&#39;26\.09\.30\. 기준\)/);assert.doesNotMatch(context.flow.summaryTable(base),/12월 말/);
});

test('stage bands use adjacent differences and place each shortage after actual units',()=>{
 const keys=['BUSINESS','APPROVAL','CONSTRUCTION','SUPPLY','MOVE_IN'],counts=[100,80,60,40,10];
 const comparisons=Object.fromEntries(keys.map((k,i)=>[k,{actual_points:[{date:'2026-01-01',units:counts[i]}],target_points:[{date:'2026-01-01',units:counts[i]+10}]}]));
 const m={tracking:true,start:2026,end:2026,asOf:'2026-10-22',comparisons},before=JSON.stringify(m);
 const bands=context.flow.stageBands(m,m.asOf,'actual');
 assert.deepEqual(Object.keys(bands),keys);assert.equal(bands.BUSINESS.lo,0);
 let base=0;for(let i=0;i<keys.length;i++){const band=bands[keys[i]],units=counts[i]-(counts[i+1]??0),gap=i===4?10:0;assert.equal(band.lo,base);assert.equal(band.hi-band.lo,units);assert.equal(band.cumulative,counts[i]);assert.equal(context.flow.stageBands(m,m.asOf)[keys[i]].lo,base+units);base+=units+gap;}
 assert.equal(bands.SUPPLY.hi-bands.SUPPLY.lo,30);
 assert.equal(context.flow.stackExtent(m,m.asOf),110);
 assert.equal(JSON.stringify(m),before);
 delete comparisons.MOVE_IN.actual_points;assert.equal(context.flow.stageBands(m,m.asOf,'actual').MOVE_IN.hi,null);
});
test('rendered bands preserve ascending stage order, numerical gaps and curved boundaries',()=>{
 for(const file of ['d3-path/d3-path.min.js','d3-shape/d3-shape.min.js'])vm.runInContext(fs.readFileSync(path.join(__dirname,'../../web/assets/vendor',file),'utf8'),context);
 const stages={POLICY:'정책',BUSINESS:'사업화',APPROVAL:'인허가',CONSTRUCTION:'건설',SUPPLY:'공급',MOVE_IN:'입주'},keys=Object.keys(stages).slice(1),counts=[100,80,60,40,10];
 const comparisons=Object.fromEntries(keys.map((k,i)=>[k,{actual_points:[{date:'2026-01-01',units:counts[i]}],target_points:[{date:'2026-01-01',units:counts[i]+10}],forecast_points:[{date:'2026-12-31',units:counts[i]+20}]}]));
 const html=context.flow.render({tracking:true,start:2026,end:2026,asOf:'2026-10-22',referenceDate:'2026-10-22',comparisonDate:'2026-12-31',year:2026,max:500,stages,comparisons,colors:Object.fromEntries(Object.keys(stages).map(k=>[k,'#123456']))});
 assert.deepEqual([...html.matchAll(/data-d907-band="([^"]+)"/g)].map(m=>m[1]),keys);
 for(const kind of ['actual','target']){const markers=[...html.matchAll(new RegExp('data-d907-reference-value="'+kind+'" data-stage="([^"]+)" data-units="([^"]+)" data-base="[^"]+"[^>]*? cx="[^"]+" cy="([^"]+)"','g'))];const ys=Object.fromEntries(markers.map(m=>[m[1],Number(m[3])]));for(let i=1;i<keys.length;i++)assert.ok(ys[keys[i]]<ys[keys[i-1]]);assert.equal(Number(markers.find(m=>m[1]==='BUSINESS')[2]),kind==='actual'?100:110);}
 const aux=[...html.matchAll(/data-d907-aux-value data-stage="([^"]+)" data-units="([^"]+)" cx="[^"]+" cy="([^"]+)"/g)];assert.equal(aux.length,5);assert.equal(Number(aux.find(m=>m[1]==='BUSINESS')[2]),110);assert.match(html,/data-projection-basis="max-stage-plus-target-increments"/);assert.ok(Number(aux.find(m=>m[1]==='BUSINESS')[3])>Number(aux.find(m=>m[1]==='SUPPLY')[3]));
 for(const k of keys){const target=html.match(new RegExp('data-d907-target-line="'+k+'" d="([^"]*)"'))[1],forecast=html.match(new RegExp('data-d907-forecast-line="'+k+'" d="([^"]*)"'))[1];assert.equal(target,forecast,'same curve and tangent across current boundary: '+k);}
 assert.equal([...html.matchAll(/<pattern[^>]+>[\s\S]*?stroke="#b51f38"/g)].length,5);
 assert.match(html,/입주 목표대비 10호 부족 \(50\.0%\)/);assert.match(html,/data-d907-gap-callout="MOVE_IN"/);assert.match(html,/data-d907-gap="BUSINESS"/);assert.doesNotMatch(html,/d907-target-[^ ]*pattern/);assert.match(html,/data-d907-cumulative-area="BUSINESS"/);assert.match(html,/data-curve="monotone-x"/);for(const path of html.matchAll(/data-d907-(?:actual-line|target-line)="[^"]+" d="([^"]+)"/g))assert.match(path[1],/C/);
});

test('hatching spans only observed cumulative shortfalls through the data date',()=>{
 const m={asOf:'2026-10-22',comparisons:{BUSINESS:{target_points:[{date:'2026-01-01',units:100},{date:'2026-12-01',units:200}],actual_points:[{date:'2026-03-01',units:80},{date:'2026-09-01',units:110}]}}};
 assert.equal(context.flow.gapBand(m,'BUSINESS','2026-02-01'),null);
 const gap=context.flow.gapBand(m,'BUSINESS','2026-05-01');assert.equal(gap.lo,80);assert.equal(gap.hi,100);assert.equal(gap.hi-gap.lo,20);
 assert.equal(context.flow.gapBand(m,'BUSINESS','2026-10-01'),null);
 assert.equal(context.flow.gapBand(m,'BUSINESS','2026-12-01'),null);
 m.comparisons.BUSINESS.actual_points=[{date:'2026-01-01',units:0}];assert.equal(context.flow.gapBand(m,'BUSINESS','2026-05-01').lo,0);
});

test('upper-stage shortfalls retain their amount above the shared lower-stage baseline',()=>{
 const m={tracking:true,asOf:'2026-10-22',comparisons:{BUSINESS:{target_points:[{date:'2026-01-01',units:100}],actual_points:[{date:'2026-01-01',units:120}]},APPROVAL:{target_points:[{date:'2026-01-01',units:80}],actual_points:[{date:'2026-01-01',units:60}]}}};
 const target=context.flow.stageBands(m,m.asOf),actual=context.flow.stageBands(m,m.asOf,'actual'),gap=context.flow.gapBand(m,'APPROVAL',m.asOf);
 assert.equal(target.APPROVAL.lo,120);assert.equal(actual.APPROVAL.lo,60);assert.equal(gap.lo,120);assert.equal(gap.hi,140);assert.equal(gap.hi-gap.lo,20);assert.equal(context.flow.gapBand(m,'BUSINESS',m.asOf),null);
});

const currentCase=()=>{
 const keys=['BUSINESS','APPROVAL','CONSTRUCTION','SUPPLY','MOVE_IN'],actual=[90746,87098,79357,35410,null],goal=[151044,98097,79829,58768,null],forecast=[153402,106771,98603,73114,3845];
 return {tracking:true,asOf:'2026-10-22',referenceDate:'2026-10-22',comparisons:Object.fromEntries(keys.map((k,i)=>[k,{actual_points:actual[i]==null?[]:[{date:'2026-10-01',units:actual[i]}],target_points:goal[i]==null?[]:[{date:'2026-10-01',units:goal[i]}],forecast_points:[{date:'2026-12-31',units:forecast[i]}]}]))};
};
test('requested live example: 3648 actual plus 49299 shortage, then approval and construction',()=>{
 const m=currentCase(),before=JSON.stringify(m),b=context.flow.stageLayout(m,m.asOf);
 assert.equal(b.BUSINESS.actual.units,3648);assert.equal(b.BUSINESS.target.units,52947);assert.equal(b.BUSINESS.gap,49299);
 assert.equal(b.BUSINESS.actual.lo,0);assert.equal(b.BUSINESS.actual.hi,3648);assert.equal(b.BUSINESS.target.lo,3648);assert.equal(b.BUSINESS.target.hi,52947);
 assert.equal(b.APPROVAL.actual.lo,52947);assert.equal(b.APPROVAL.actual.units,7741);assert.equal(b.APPROVAL.gap,10527);
 assert.equal(b.CONSTRUCTION.actual.units,43947);assert.equal(b.CONSTRUCTION.gap,0);
 assert.equal(b.MOVE_IN.actual.units,null);assert.equal(b.MOVE_IN.gap,null);assert.equal(b.SUPPLY.actual.nextMissing,true);
 assert.equal(context.flow.stackExtent(m,m.asOf),173930);assert.equal(JSON.stringify(m),before);
 const max=context.flow.axisMaximum(151044,173930);assert.equal(max,216000);assert.ok(Math.abs(151044/max-.7)<.001);
 assert.ok(context.flow.axisMaximum(100,400)>400);
});
test('future bands start at the larger stage amount and add subsequent target increases',()=>{
 const m=currentCase(),goals=[160000,120000,100000,70000,5000];
 Object.values(m.comparisons).forEach((c,i)=>c.target_points.push({date:'2026-12-31',units:goals[i]}));
 const b=context.flow.stageLayout(m,'2026-12-31');
 assert.equal(b.BUSINESS.actual.units,40000);assert.equal(b.APPROVAL.actual.units,20000);assert.equal(b.MOVE_IN.actual.units,5000);assert.equal(b.BUSINESS.actual.cumulative,182886);assert.equal(b.BUSINESS.future,true);
 assert.equal(context.flow.stackExtent(m,'2026-12-31'),182886);assert.equal(b.BUSINESS.gap,0);
 assert.equal(context.flow.gapBand(m,'BUSINESS','2026-12-31'),null);
 assert.equal(context.flow.stageBands(m,m.asOf,'forecast').BUSINESS.units,52947);
 assert.equal(context.flow.stageBands(m,m.asOf,'actual').BUSINESS.units,3648);
 m.referenceDate='2026-09-30';assert.equal(context.flow.stageLayout(m,'2026-10-22').BUSINESS.future,false);
 assert.equal(context.flow.stageBands(m,'2026-09-30','actual').BUSINESS.cumulative,null);
});
test('inverted cumulative stages do not create negative areas or change the original measurements',()=>{
 const m=currentCase();m.comparisons.APPROVAL.actual_points[0].units=100000;
 const b=context.flow.stageLayout(m,m.asOf).BUSINESS;
 assert.equal(b.actual.raw,-9254);assert.equal(b.actual.units,0);assert.equal(b.actual.cumulative,90746);
});

test('shortage percentage uses the gap plus cumulative achievement, not the stage-only amount',()=>{
 assert.equal(context.flow.shortageRate(49299,90746).toFixed(1),'35.2');
 assert.equal(context.flow.shortageRate(10527,87098).toFixed(1),'10.8');
 assert.equal(context.flow.shortageRate(23358,35410).toFixed(1),'39.7');
 assert.equal(context.flow.shortageRate(10,0),100);assert.equal(context.flow.shortageRate(0,0),0);assert.equal(context.flow.shortageRate(10,null),null);
});

test('query dates move cursors without changing chart paths, labels or the actual/future clips',()=>{
 const m={...currentCase(),start:2026,end:2027,year:2026,max:216000,comparisonDate:'2026-12-31',stages:{BUSINESS:'사업화',APPROVAL:'인허가',CONSTRUCTION:'착공',SUPPLY:'공급',MOVE_IN:'입주'},colors:{BUSINESS:'#a66b00',APPROVAL:'#0072b2',CONSTRUCTION:'#d55e00',SUPPLY:'#00856a',MOVE_IN:'#7a3e9d'}};
 const before=context.flow.render(m),after=context.flow.render({...m,referenceDate:'2026-05-20',comparisonDate:'2027-06-30'});
 const paths=html=>[...html.matchAll(/<path[^>]*>/g)].map(x=>x[0]);
 assert.deepEqual(paths(after),paths(before));
 const clips=html=>[...html.matchAll(/<clipPath[^>]*>[\s\S]*?<\/clipPath>/g)].map(x=>x[0]);assert.deepEqual(clips(after),clips(before));
 const cursor=html=>html.match(/data-d907-now-line x1="([^"]+)"/)[1];assert.notEqual(cursor(after),cursor(before));
 assert.equal(context.flow.stageLayout({...m,referenceDate:'2026-05-20'},'2026-10-01').BUSINESS.future,false);
 assert.equal(context.flow.stageLayout({...m,referenceDate:'2026-05-20'},'2026-11-01').BUSINESS.future,true);
});

test('a scheduled supply of 10 transfers 10 from construction to supply without adding total units',()=>{
 const stages=['BUSINESS','APPROVAL','CONSTRUCTION','SUPPLY','MOVE_IN'];
 const m={asOf:'2026-10-22',comparisons:Object.fromEntries(stages.map((stage,i)=>[stage,{target_points:[{date:'2026-01-01',units:[100,100,100,20,0][i]}],forecast_points:[{date:'2026-01-01',units:999}],actual_points:[]}]))};
 m.comparisons.SUPPLY.target_points.push({date:'2026-12-31',units:30});
 const before=context.flow.stageLayout(m,'2026-12-30'),after=context.flow.stageLayout(m,'2026-12-31');
 assert.equal(after.CONSTRUCTION.actual.units-before.CONSTRUCTION.actual.units,-10);
 assert.equal(after.SUPPLY.actual.units-before.SUPPLY.actual.units,10);
 assert.equal(context.flow.stackExtent(m,'2026-12-30'),100);assert.equal(context.flow.stackExtent(m,'2026-12-31'),100);
});

test('future start exactly matches each existing actual-plus-shortfall band, preserving an exceeded construction goal',()=>{
 const m=currentCase(),current=context.flow.stageLayout(m,m.asOf),future=context.flow.stageLayout(m,m.asOf,true);
 for(const k of Object.keys(current)){
  assert.equal(future[k].actual.lo,current[k].actual.lo);
  assert.equal(future[k].actual.units,current[k].actual.units==null&&current[k].target.units==null?null:Math.max(current[k].actual.units??0,current[k].target.units??0));
  assert.equal(future[k].actual.hi??future[k].actual.lo,current[k].target.hi??current[k].actual.hi??current[k].actual.lo);
 }
 assert.equal(future.CONSTRUCTION.actual.units,43947);assert.equal(current.CONSTRUCTION.gap,0);
 assert.equal(context.flow.stackExtent(m,'2026-10-23'),173930);
});
test('an exceeded goal is preserved while supply moves exactly 10 units out of construction',()=>{
 const keys=['BUSINESS','APPROVAL','CONSTRUCTION','SUPPLY','MOVE_IN'],m={asOf:'2026-10-22',comparisons:Object.fromEntries(keys.map((k,i)=>[k,{target_points:[{date:'2026-01-01',units:[100,100,100,40,0][i]}],actual_points:[{date:'2026-10-01',units:[100,100,100,20,0][i]}]}]))};
 m.comparisons.SUPPLY.target_points.push({date:'2026-12-31',units:50});
 const before=context.flow.projectedStages(m,'2026-12-30'),after=context.flow.projectedStages(m,'2026-12-31');
 assert.equal(before.CONSTRUCTION.units,80);assert.equal(after.CONSTRUCTION.units,70);assert.equal(before.SUPPLY.units,40);assert.equal(after.SUPPLY.units,50);
 assert.equal(context.flow.stackExtent(m,'2026-12-30'),120);assert.equal(context.flow.stackExtent(m,'2026-12-31'),120);
});

test('visible axis uses the interval peak with 30 percent headroom, including future growth',()=>{
 const m={asOf:'2026-10-22',comparisons:{BUSINESS:{actual_points:[{date:'2025-01-01',units:80}],target_points:[{date:'2025-01-01',units:100},{date:'2027-06-01',units:200},{date:'2030-01-01',units:1000}]}}};
 const current=context.flow.windowAxis(m,'2026-01-01','2026-12-31');
 const future=context.flow.windowAxis(m,'2027-01-01','2027-12-31');
 assert.equal(current.peak,100);assert.equal(future.peak,200);
 assert.ok(current.max>=130&&current.max<=132);assert.ok(future.max>=260&&future.max<=264);
 assert.equal(context.flow.windowAxis(m,'2027-08-01','2027-12-31').peak,200);
 assert.ok(context.flow.windowAxis(m,'2024-01-01','2024-12-31').max>0);
});
test('visible axis includes stacked shortfall above achieved quantities without mutating data',()=>{
 const m={asOf:'2026-10-22',comparisons:{BUSINESS:{actual_points:[{date:'2026-01-01',units:200}],target_points:[{date:'2026-01-01',units:180}]},APPROVAL:{actual_points:[{date:'2026-01-01',units:100}],target_points:[{date:'2026-01-01',units:150}]}}};
 const before=JSON.stringify(m),axis=context.flow.windowAxis(m,'2026-01-01','2026-12-31');
 assert.equal(axis.peak,250);assert.ok(axis.max>=325&&axis.max<=328);assert.equal(JSON.stringify(m),before);
});

test('a later calculation sees in-place edits and reordered dates without mutating source series',()=>{
 const c={actual_points:[{date:'2026-09-01',units:80},{date:'2026-01-01',units:40},{date:'2027-01-01',units:999}],target_points:[{date:'2026-12-31',units:120},{date:'2026-01-01',units:100}]},m={asOf:'2026-10-22',comparisons:{BUSINESS:c}};
 assert.equal(context.flow.windowAxis(m,'2026-01-01','2026-10-22').peak,100);
 c.actual_points[0].units=140;c.actual_points[0].date='2026-03-01';
 const before=JSON.stringify(m);assert.equal(context.flow.windowAxis(m,'2026-01-01','2026-10-22').peak,140);
 assert.equal(JSON.stringify(m),before);
 c.actual_points.push({date:'2026-03-01',units:150});
 assert.equal(context.flow.stageLayout(m,'2026-03-01').BUSINESS.actual.cumulative,150);
 assert.equal(context.flow.stageLayout(m,'2026-02-28').BUSINESS.actual.cumulative,40);
 assert.equal(context.flow.stageLayout(m,'2025-12-31').BUSINESS.actual.cumulative,null);
});
