const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'../app.js'),'utf8');
function setup(api){
 const nodes=new Map();const ctx={$:id=>{if(!nodes.has(id))nodes.set(id,{innerHTML:'',dataset:{},attrs:{},setAttribute(k,v){this.attrs[k]=v},getAttribute(k){return this.attrs[k]}});return nodes.get(id)},api,config:{role:'admin'},esc:s=>String(s??'').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;')};
 vm.createContext(ctx);vm.runInContext(source.slice(source.indexOf('let historyRequest='),source.indexOf('async function references(')),ctx);return {ctx,nodes};
}
test('history uses one in-flight summary request and renders escaped titles',async()=>{
 let finish,calls=0;const {ctx,nodes}=setup(async p=>{assert.equal(p,'/jobs');calls++;return new Promise(r=>finish=r)});
 const a=ctx.history(),b=ctx.history();assert.equal(calls,1);assert.match(nodes.get('#history-list').innerHTML,/불러오는 중/);
 finish([{id:'j',metadata:{title:'<script>',department:''},created_at:'2026-11-05',state:'COMPLETED',run_count:17}]);await Promise.all([a,b]);
 assert.match(nodes.get('#history-list').innerHTML,/검사 버전 17/);assert.match(nodes.get('#history-list').innerHTML,/&lt;script&gt;/);assert.equal(nodes.get('#history-list').attrs['aria-busy'],'false');
});
test('version summaries load once and keep reanalysis tied to their own job',async()=>{
 let calls=0;const {ctx,nodes}=setup(async p=>{calls++;assert.equal(p,'/jobs/job-b/versions');return [{id:'older',created_at:'2026-11-05',vision_model:'gpt-5.4',analysis_model:'gpt-5.4-mini',result_count:156,review_count:3,reusable_observation:true}]});
 await ctx.showHistoryVersions('job-b');const el=nodes.get('#versions-job-b');assert.match(el.innerHTML,/data-source-job="job-b"/);assert.match(el.innerHTML,/data-source-run="older"/);
 await ctx.showHistoryVersions('job-b');assert.equal(calls,1);assert.equal(el.hidden,true);await ctx.showHistoryVersions('job-b');assert.equal(el.hidden,false);
});
test('failed history fetch clears its busy state and supports retry',async()=>{
 let calls=0;const {ctx,nodes}=setup(async()=>{if(++calls===1)throw Error('temporary');return []});
 await assert.rejects(ctx.history(),/temporary/);assert.equal(nodes.get('#history-list').attrs['aria-busy'],'false');
 await ctx.history();assert.equal(calls,2);assert.match(nodes.get('#history-list').innerHTML,/등록된 검수 이력이 없습니다/);
});
test('reanalyzing an older unloaded version hydrates that exact source',async()=>{
 const ctx={job:{id:'job-b',runs:[{id:'latest'}]},requireAnalysisPermission(){},activeRun(){return this.job.runs[0]},reusableObservation:r=>r.id==='older',requestTransmission:async()=>true,selected:'x',selectedGroup:'x',renderJob(){},toast(){},$:()=>({value:'gpt-5.4-mini'})};
 let submitted;ctx.api=async p=>{assert.equal(p,'/jobs/job-b?view=latest&run_id=older');return {runs:[{id:'older',options:{vision_model:'gpt-5.4',text_sensitivity:'strict'}}]}};
 ctx.post=async(p,body)=>{assert.equal(p,'/jobs/job-b/runs');submitted=body;return ctx.job};
 vm.createContext(ctx);vm.runInContext(source.slice(source.indexOf('async function reanalyze('),source.indexOf('async function openJob(')),ctx);
 await ctx.reanalyze('older');assert.equal(submitted.reuse_observation_run_id,'older');assert.equal(submitted.vision_model,'gpt-5.4');
});
