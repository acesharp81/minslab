const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const source=fs.readFileSync(require('node:path').join(__dirname,'../app.js'),'utf8');
const context=vm.createContext({});
vm.runInContext(source.slice(source.indexOf('function reusableObservation('),source.indexOf('function renderFailure(')),context);
const run=()=>({options:{mode:'live',vision_model:'gpt-6.1-sol',analysis_model:'gpt-5.4-mini'},scope:'FULL_IMAGE',analysis:[{error:'공급자 HTTP 520',model:'gpt-5.4-mini'}],calls:[{model:'gpt-6.1-sol',workload:'image-observation',status:'FAILED'}],results:[{status:'ERROR'}]});
test('old vision failures identify the actual model and cannot reuse missing observations',()=>{
 const r=run(),failure=context.inspectionFailure(r);
 assert.equal(failure.stage,'그림 읽기');assert.equal(failure.model,'gpt-6.1-sol');assert.equal(failure.reading,true);assert.equal(context.reusableObservation(r),false);
});
test('a recovered failed attempt does not make a successful run fail',()=>{
 const r=run();r.analysis=[];r.observation={objects:[]};
 assert.equal(context.inspectionFailure(r),null);assert.equal(context.reusableObservation(r),true);
});
test('analysis failure retains usable observations and stage',()=>{
 const r=run();r.failed_phase='ANALYZING';r.calls.push({model:'gpt-5.4-mini',workload:'checklist-analysis',status:'FAILED'});r.observation={objects:[{id:'a'}]};
 const failure=context.inspectionFailure(r);assert.equal(failure.stage,'규칙 분석');assert.equal(failure.model,'gpt-5.4-mini');assert.equal(context.reusableObservation(r),true);
});
test('an earlier recovered vision error is not blamed for a later mini budget failure',()=>{
 const r=run();r.failed_phase='ANALYZING';r.analysis=[{error:'예산 부족',model:'gpt-5.4-mini'}];r.observation={objects:[{id:'a'}]};
 assert.equal(context.inspectionFailure(r).model,'gpt-5.4-mini');
});
