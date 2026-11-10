const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const source=fs.readFileSync(require('node:path').join(__dirname,'../app.js'),'utf8');
const escape=s=>String(s??'').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;');
function context(extra={}){
 const ctx={esc:escape,BASE:'',...extra};vm.createContext(ctx);
 vm.runInContext(source.slice(source.indexOf('let qualitySelection='),source.indexOf('async function openJob(')),ctx);
 vm.runInContext(source.slice(source.indexOf('function qualityRecheckHTML('),source.indexOf('function renderTokens(')),ctx);
 return ctx;
}
test('preview shows the selected source crop and clear prior readings remain selectable',()=>{
 const ctx=context(),plan={entries:[{object_id:'a',label:'<글자>',focus:'text',state:'PREVIOUSLY_CHECKED',preview_rect:[.1,.2,.3,.4],selectable:true}],recommended_ids:['a']};
 const html=ctx.qualityPlanHTML(plan,{id:'j',image:{width:1000,height:800}});
 assert.match(html,/&lt;글자&gt;/);assert.match(html,/기존 판독 있음/);assert.match(html,/value="a"  checked/);assert.match(html,/\/api\/jobs\/j\/image/);
 assert.ok(!html.includes('data-finding')&&!html.includes('status-FAIL'));
});
test('reused old evidence cannot be displayed as a completed new crop read',()=>{
 const ctx=context();const run={options:{quality_recheck:true,recheck_object_ids:['a']},calls:[],verification:{results:[{object_id:'a',event_id:'old',coverage:'COMPLETE'}]}};
 assert.match(ctx.qualityRecheckHTML(run),/새 판독 미완료/);
 run.calls=[{event_id:'new',workload:'image-verification'}];run.verification.attempt_results=[{object_id:'a',event_id:'new',coverage:'PARTIAL',description:'일부 손만 확인'}];
 assert.match(ctx.qualityRecheckHTML(run),/새 판독 부분 확인/);
});
test('cancelled selection never posts or performs a model call',async()=>{
 let posts=0,shown=0;const j={id:'j',state:'COMPLETED'},run={id:'r'};
 const ctx=context({job:j,activeRun:()=>run,requireAnalysisPermission(){},requestTransmission:async()=>false,
  post:async()=>{posts++},$$:()=>[{value:'hand'}],$:s=>({value:s==='#vision-model'?'gpt-5.4':'gpt-5.4-mini',close(){},showModal(){shown++}})});
 vm.runInContext("qualitySelection={jobId:'j',runId:'r',plan:{max_objects:6,max_calls:2}}",ctx);
 await ctx.submitQualityRecheck();assert.equal(posts,0);assert.equal(shown,1);
});
test('accepted selection uses the stored run and explicitly requests crop reinspection',async()=>{
 let payload;const j={id:'j',state:'COMPLETED'};
 const ctx=context({job:j,activeRun:()=>({id:'r'}),requireAnalysisPermission(){},requestTransmission:async()=>true,
  post:async(path,body)=>{payload=body;return j},$$:()=>[{value:'hand'}],$:s=>({value:s==='#vision-model'?'gpt-5.4':'gpt-5.4-mini',close(){}}),renderJob(){},toast(){}});
 vm.runInContext("qualitySelection={jobId:'j',runId:'r',plan:{max_objects:6,max_calls:2}}",ctx);
 await ctx.submitQualityRecheck();assert.equal(payload.quality_recheck,true);assert.equal(payload.reuse_observation_run_id,'r');assert.deepEqual(Array.from(payload.recheck_object_ids),['hand']);assert.equal(payload.vision_model,'gpt-5.4');
});
test('automatic refinements expose traces and uncertainty without claiming normality',()=>{
 const ctx=context();const html=ctx.refinementReportHTML({glyph_audit:{status:'PARTIAL',regions:[{detector_text:'가',assessment:{literal_text:'□'},isolated_glyphs:{literal_text:'□',agreed:false}}]},hand_audit:{status:'COMPLETED',results:[{object_id:'hand',summary:'<관찰>',traces:[{part:'검지',visible_path:'끝까지 보임',obscured_by:'꽃'}],accepted_concerns:[]}]}});
 assert.match(html,/자동 손·글자 정밀 확인/);assert.match(html,/미확정/);assert.match(html,/이상 소견 0건/);assert.match(html,/&lt;관찰&gt;/);assert.match(html,/가림: 꽃/);
});
test('local hand measurements remain visibly distinct from model topology',()=>{
 const ctx=context();const html=ctx.refinementReportHTML({hand_audit:{status:'COMPLETED',results:[],local_geometry:[{object_id:'h',measurement:{visible_protrusions:6},accepted_concerns:[{}]}]}});
 assert.match(html,/로컬 손 도안 측정/);assert.match(html,/돌출부 6개/);assert.match(html,/형태 확인 필요/);
});

test('completion summary exposes bounded and failed checks without inventing success',()=>{
 const ctx=context(),run={verification:{deferred:[{object_id:'map',reason:'호출 시간 초과 <test>'}]},observation:{objects:[{id:'map',label:'지도'}]},glyph_audit:{status:'PARTIAL',candidate_count:24,deferred_count:20,regions:Array.from({length:4},()=>({assessment:{}}))},calls:[{status:'FAILED'}]};
 const coverage=ctx.inspectionCoverage(run);assert.equal(coverage.partial,true);assert.equal(coverage.failedCalls,1);
 const html=ctx.coverageSummaryHTML(run);assert.match(html,/4\/24곳/);assert.match(html,/확인 미완료/);assert.match(html,/&lt;test&gt;/);assert.ok(!html.includes('data-action')&&!html.includes('<test>'));
 assert.equal(ctx.coverageSummaryHTML({calls:[],glyph_audit:{status:'COMPLETED'}}),'');
});
