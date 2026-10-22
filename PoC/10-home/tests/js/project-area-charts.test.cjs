const test=require('node:test'),assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs'),path=require('node:path');
const ctx={esc:String,safeUrl:v=>v||'#'};vm.createContext(ctx);
for(const name of ['project-living-charts','project-area-charts'])vm.runInContext(fs.readFileSync(path.join(__dirname,'../../web/assets/'+name+'.js'),'utf8'),ctx);
vm.runInContext('globalThis.charts=ProjectAreaCharts',ctx);
const render=data=>{const host={innerHTML:'',querySelectorAll:()=>[]};ctx.charts.render(host,data,{region:'경기도',municipality:'고양시'},{includeLiving:true});return host.innerHTML;};
test('absent local and national industry records preserve the other location cards',()=>{
 for(const national_benchmarks of [undefined,{}, {industry:null,age:null,household:null}]){
  const html=render({census:[],household_size:[],national_benchmarks});
  assert.match(html,/산업별 종사자 비율 자료 미확보/);assert.match(html,/가구원수 비율 자료 미확보/);assert.match(html,/평균 가구소득/);assert.doesNotMatch(html,/NaN|undefined|Cannot read/);
 }
});
test('known local counts survive missing national comparisons',()=>{
 const html=render({census:[{year:2025,workplace_workers:123,industry_workers:{A:{name:'제조업',workers:123}}}],household_size:[{year:2025,total:10,sizes:{'1':10}}],national_benchmarks:{industry:null,household:null}});
 assert.match(html,/123명/);assert.match(html,/10가구/);assert.match(html,/전국 비교 미확보/);assert.doesNotMatch(html,/NaN/);
});
test('national industry comparison requires the same known reference year',()=>{
 const local={year:2025,workplace_workers:100,industry_workers:{A:{name:'제조업',workers:100}}},national={year:2025,total:1000,industry_workers:{A:{name:'제조업',workers:250}}};
 assert.equal(ctx.charts.industryComparison(local,national).all[0].national_pct,25);
 assert.equal(ctx.charts.industryComparison(local,{...national,year:2024}).all[0].national_pct,null);
 assert.equal(ctx.charts.industryComparison({...local,year:undefined},{...national,year:undefined}).all[0].national_pct,null);
});
test('partial national age classes do not discard the local age pyramid',()=>{
 const html=render({age_distribution:{current:{period:'202609',total:20,sex_age_classes:{male:{'0':10,'5':10},female:{'0':10,'5':10}}}},national_benchmarks:{age:{period:'202609',total:100}}});
 assert.match(html,/지역 남 10명/);assert.match(html,/전국 남 미확보/);assert.doesNotMatch(html,/NaN|undefined/);
});
