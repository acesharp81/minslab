const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const source=fs.readFileSync(require('node:path').join(__dirname,'../app.js'),'utf8'),context=vm.createContext({});
vm.runInContext(source.slice(source.indexOf('function runModelSummary('),source.indexOf('function renderJob(')),context);
test('completed result uses stored model evidence and distinguishes reused observation',()=>{
 const r={observation_model:'gpt-6.1-sol',observation_reused_from:{run_id:'old'},options:{vision_model:'gpt-5.4',analysis_model:'gpt-6-astra'},results:[{status:'PASS',model:'gpt-5.4-mini'},{status:'REVIEW',model:'system/independent-evidence'}]};
 assert.equal(context.runModelSummary(r),'그림 읽기: GPT-6.1 Sol (재사용) · 분석: GPT-5.4 mini');
 assert.equal(context.runModelSummary({options:{vision_model:'gpt-5.4'},results:[]}), '그림 읽기: 미완료 · 분석: 미실행');
});
