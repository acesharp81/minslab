const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const {test}=require('node:test');
const code=fs.readFileSync(require('node:path').join(__dirname,'../app.js'),'utf8');
const source=code.slice(code.indexOf('function aiRemainingCards('),code.indexOf('function renderAiUsage('));
function cards(payload){const c=vm.createContext({payload});vm.runInContext(source,c);return JSON.parse(vm.runInContext('JSON.stringify(aiRemainingCards(payload))',c));}
const payload=()=>({status:'AVAILABLE',providers:[{provider:'nvidia',limit:null},{provider:'openrouter',limit:1000,operational_limit:950,used:950,operational_remaining:0},{provider:'openai',limit:650000,used:580000,remaining:60000,reserved_tokens:10000},{provider:'mistral',credit_usd:10,cost_usd:1.65}],auxiliary_models:[{provider:'gemini',daily_token_cap:300000,charged_tokens:3000,daily_request_cap:200,request_count:2},{provider:'groq',daily_token_cap:100000,charged_tokens:5000,daily_request_cap:400,request_count:20}]});
test('five cards use operational allowance and reservations, not headline quotas',()=>{
 const c=cards(payload());assert.equal(c.length,5);assert.equal(c[0].percent,0);assert.equal(c[0].label,'소진');assert.ok(c[3].percent<10);assert.equal(c[4].label,'83% 남음');
});
test('NIM is excluded from display even when present in the API',()=>{
 assert.ok(cards(payload()).every(c=>c.provider!=='nvidia'));
});
test('auxiliary request exhaustion takes precedence over unused tokens',()=>{
 const p=payload();p.auxiliary_models[0].request_count=200;assert.equal(cards(p)[1].label,'소진');
});
test('failed or missing usage never defaults to a full balance',()=>{
 assert.ok(cards({status:'UNAVAILABLE'}).every(c=>c.percent===null));assert.ok(cards({}).every(c=>c.percent===null));
});
test('fractional and overspent balances are bounded accurately',()=>{
 const p=payload();p.providers[2].remaining=1;p.providers[3].cost_usd=12;const c=cards(p);assert.equal(c[3].label,'1% 미만');assert.equal(c[4].label,'소진');
});
