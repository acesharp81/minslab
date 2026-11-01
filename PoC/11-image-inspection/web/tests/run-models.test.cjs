const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const source=fs.readFileSync(require('node:path').join(__dirname,'../app.js'),'utf8'),context=vm.createContext({});
vm.runInContext(source.slice(source.indexOf('function runModelSummary('),source.indexOf('function renderJob(')),context);
test('completed result uses stored model evidence and distinguishes reused observation',()=>{
 const r={observation_model:'gpt-6.1-sol',observation_reused_from:{run_id:'old'},options:{vision_model:'gpt-5.4',analysis_model:'gpt-6-astra'},results:[{status:'PASS',model:'gpt-5.4-mini'},{status:'REVIEW',model:'system/independent-evidence'}]};
 assert.equal(context.runModelSummary(r),'그림 읽기: GPT-6.1 Sol (재사용) · 분석: GPT-5.4 mini');
 assert.equal(context.runModelSummary({options:{vision_model:'gpt-5.4'},results:[]}), '그림 읽기: 미완료 · 분석: 미실행');
 r.local_revision={method:'flat-emblem-components-v1'};r.calls=[];
 assert.match(context.runModelSummary(r),/분석: GPT-5.4 mini \(재사용\) · 문양 구성 비교: 로컬 계산\(API 0회\)/);
});
test('additional daily glyph reader and reuse are visible even with another primary model',()=>{
 const r={observation_model:'gpt-6.1-sol',options:{},results:[],pixel_text:{confirmation:{calls:1}},calls:[{workload:'text-pixel-confirm',model:'gpt-5.4'}]};
 assert.match(context.runModelSummary(r),/문자 획 확인: GPT-5.4$/);
 r.calls=[];assert.match(context.runModelSummary(r),/문자 획 확인: GPT-5.4 \(재사용\)$/);
});
test('text-only spelling helper is shown separately from scene reading',()=>{
 const r={observation_model:'gpt-5.4',options:{},results:[],spelling_audit:{calls:1},calls:[{workload:'text-spelling-audit',model:'gpt-5.4-mini'}]};
 assert.match(context.runModelSummary(r),/철자 확인: GPT-5.4 mini/);
});
