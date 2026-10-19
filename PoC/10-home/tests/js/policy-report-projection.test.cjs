const test=require('node:test'),assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs'),path=require('node:path');
function fixture(){
 const calls=[],ctx={esc:String,num:v=>Number(v).toLocaleString('en-US'),$:()=>({value:'2026-10-15'}),request:async url=>{calls.push(url);return {region:'서울특별시',baseline:{housing_units:10000},years:Array.from({length:6},(_,i)=>({year:2026+i,forecast_households:10000,observed_completion_since_baseline:i===0?0:null}))};}};
 vm.createContext(ctx);vm.runInContext(fs.readFileSync(path.join(__dirname,'../../web/assets/policy-report.js'),'utf8'),ctx);
 return {report:vm.runInContext('PolicyReport',ctx),calls};
}
const flush=()=>new Promise(resolve=>setImmediate(resolve));
test('scoped comparison counts duplicate completion dates once and caps later installments at project capacity',async()=>{
 const {report,calls}=fixture(),host={isConnected:true,innerHTML:''};
 const plan=(due_date,units)=>({stage:'COMPLETION',due_date,units});
 report.statisticsProjection(host,[{region:'서울특별시',units:1000,schedules:[plan('2027-06-01',700),plan('2027-06-01',700),plan('2028-06-01',600),{stage:'SUPPLY',due_date:'2029-01-01',units:1000}]}],'','');
 await flush();assert.equal(calls.length,1);assert.match(host.innerHTML,/단순 잔여 1,000호/);assert.doesNotMatch(host.innerHTML,/단순 잔여 2,000호/);assert.match(host.innerHTML,/<details><summary>비교 기준·산출 가정/);
});
test('municipality selection explicitly withholds a forecast instead of applying a province forecast to city units',()=>{
 const {report,calls}=fixture(),host={isConnected:true,innerHTML:''};
 report.statisticsProjection(host,[],'11|강남구','서울특별시',{region:'서울특별시',name:'강남구'});
 assert.equal(calls.length,0);assert.match(host.innerHTML,/시군구 공급량과 합쳐/);assert.doesNotMatch(host.innerHTML,/<svg/);
});
test('missing schedules remain missing and detached views do not receive late async writes',async()=>{
 const {report}=fixture(),host={isConnected:true,innerHTML:''};report.statisticsProjection(host,[],'','서울특별시');await flush();assert.match(host.innerHTML,/정책 효과 산정 미확보/);assert.doesNotMatch(host.innerHTML,/단순 잔여/);
 const detached={isConnected:true,innerHTML:''};report.statisticsProjection(detached,[],'','서울특별시');detached.isConnected=false;await flush();assert.doesNotMatch(detached.innerHTML,/<svg/);
});
