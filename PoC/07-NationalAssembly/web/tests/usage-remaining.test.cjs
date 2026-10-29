const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const {test}=require('node:test');
const code=fs.readFileSync(require('node:path').join(__dirname,'../app.js'),'utf8');
const source=code.slice(code.indexOf('function aiRemainingCards('),code.indexOf('function renderAiUsage('));
function cards(payload){const c=vm.createContext({payload});vm.runInContext(source,c);return JSON.parse(vm.runInContext('JSON.stringify(aiRemainingCards(payload))',c));}
const payload=()=>({status:'AVAILABLE',workload_groups:[{models:[
{id:'mini',label:'Mini',limit:10000000,remaining:9800000,unit:'tokens',period:'DAILY_UTC'},
{id:'openrouter',label:'OpenRouter',limit:950,remaining:0,unit:'requests',period:'DAILY_UTC'},
{id:'main',label:'GPT-5.4',limit:1000000,remaining:700000,unit:'tokens',period:'DAILY_UTC'},
{id:'terra',label:'Terra',limit:100,remaining:7.5,unit:'USD'},
{id:'mistral',label:'Mistral',limit:10,remaining:8.35,unit:'USD'}]}]});
test('all five models have independent amounts within three groups',()=>{
 const c=cards(payload());assert.equal(c.length,5);assert.equal(c[0].label,'(일) 980만');assert.equal(c[1].label,'(일) 소진');assert.equal(c[2].label,'(일) 70만');assert.equal(c[3].label,'(월) $7.500');assert.equal(c[4].label,'(월) $8.35');
});
test('missing or unavailable usage is never presented as a full balance',()=>{
 assert.ok(cards({status:'UNAVAILABLE'}).every(c=>c.percent===null));assert.ok(cards({}).every(c=>c.percent===null));
});
test('unconfirmed credit is distinguished from exhausted credit',()=>{
 const p=payload();p.workload_groups[0].models[3]={id:'terra',status:'CREDIT_UNCONFIRMED'};
 assert.equal(cards(p)[3].label,'크레딧 확인');
});
test('negative remaining is clamped and service scope is disclosed',()=>{
 const p=payload();p.workload_groups[0].models[0].remaining=-100;
 assert.equal(cards(p)[0].percent,0);assert.match(cards(p)[2].title,/계정 전체 잔액과 다를/);
});

test('Terra is a fraction of the monthly $100, not of its $8 opening balance',()=>{ assert.equal(cards(payload())[3].percent,7.5); });
