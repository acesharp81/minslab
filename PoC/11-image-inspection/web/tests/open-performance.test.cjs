const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'../app.js'),'utf8');
test('nearby group merging never appends coordinates to stored observation arrays',()=>{
 const a=[.1,.2,.2,.3],b=[.15,.2,.25,.3];
 const run={results:[{id:'a',rule_id:'D-02-l',parent_id:'D-02',status:'FAIL',rects:[a],evidence_ids:['one']},{id:'b',rule_id:'D-02-l',parent_id:'D-02',status:'FAIL',rects:[b],evidence_ids:['two']}],reviews:[],observation:{objects:[{id:'one',label:'첫째',rects:[a]},{id:'two',label:'둘째',rects:[b]}]}};
 const saved=JSON.stringify(run);let width=500;
 const ctx={activeRun:()=>run,findings:()=>run.results,effective:r=>r.status,selected:null,pack:{parents:[]},$:s=>s==='#pass-toggle'?{checked:false}:{getBoundingClientRect:()=>({width,height:600})}};
 vm.createContext(ctx);vm.runInContext(source.slice(source.indexOf('function measuredFlags()'),source.indexOf('function pinRows()')),ctx);
 const first=JSON.stringify(ctx.issueGroups());assert.equal(JSON.stringify(run),saved);
 width=520;ctx.issueGroups();width=500;assert.equal(JSON.stringify(ctx.issueGroups()),first);assert.equal(JSON.stringify(run),saved);
});
function details(api){
 const ctx={api};vm.createContext(ctx);
 vm.runInContext(source.slice(source.indexOf('const detailLoads='),source.indexOf('function showDeferredDetail(')),ctx);return ctx;
}
test('snapshot hydration shares one request, preserves results and uses the exact run',async()=>{
 let finish,calls=0;const ctx=details(p=>{assert.equal(p,'/jobs/j/runs/old/details');calls++;return new Promise(r=>finish=r)});
 const run={id:'old',details_deferred:true,results:[{id:'finding'}]},j={id:'j'};
 const a=ctx.loadRunDetails(j,run),b=ctx.loadRunDetails(j,run);assert.equal(calls,1);
 finish({run_id:'old',rule_pack:{version:'old'},reference_snapshot:[{id:'old-ref'}]});await Promise.all([a,b]);
 assert.equal(run.details_deferred,false);assert.equal(run.rule_pack.version,'old');assert.equal(run.results[0].id,'finding');
 await ctx.loadRunDetails(j,run);assert.equal(calls,1);
});
test('failed or mismatched detail responses can retry without altering the existing view',async()=>{
 let calls=0;const ctx=details(async()=>{if(++calls===1)throw Error('offline');return {run_id:calls===2?'wrong':'r',rule_pack:{version:'v'},reference_snapshot:[]}});
 const run={id:'r',details_deferred:true,reference_snapshot:[{name:'saved'}]},j={id:'j'};
 await assert.rejects(ctx.loadRunDetails(j,run),/offline/);await assert.rejects(ctx.loadRunDetails(j,run),/일치하지/);
 assert.equal(run.reference_snapshot[0].name,'saved');assert.ok(run.details_deferred);
 await ctx.loadRunDetails(j,run);assert.equal(run.details_deferred,false);
});
function openSetup(api){
 const nodes=new Map(),button={dataset:{openJob:'j'},textContent:'검사 열기',setAttribute(){}};
 const node=id=>{if(!nodes.has(id))nodes.set(id,{hidden:false,src:'old-image',getAttribute(k){return this[k]},removeAttribute(k){delete this[k]}});return nodes.get(id)};
 const ctx={api,$:node,$$:()=>[button],BASE:'',timer:null,job:{id:'previous'},clearTimeout(){},clearPreviewURL(){},fillMetadata(){},tab(){},renderJob(){},resultView(){},imageViewport:{reset(){}}};
 vm.createContext(ctx);vm.runInContext(source.slice(source.indexOf('async function openJob('),source.indexOf('let historyRequest=')),ctx);return {ctx,nodes,button};
}
test('image request starts before JSON resolves and loading state clears',async()=>{
 let finish;const {ctx,nodes,button}=openSetup(p=>{assert.equal(p,'/jobs/j?view=screen');return new Promise(r=>finish=r)});
 const pending=ctx.openJob('j');assert.equal(nodes.get('#inspection-image').src,'/api/jobs/j/image');assert.equal(button.disabled,true);
 finish({id:'j',runs:[]});await pending;assert.equal(ctx.job.id,'j');assert.equal(button.disabled,false);assert.equal(nodes.get('#pins').hidden,false);
});
test('late response cannot replace a newer selection',async()=>{
 const pending={};const {ctx}=openSetup(p=>new Promise(r=>pending[p]=r));
 const a=ctx.openJob('a'),b=ctx.openJob('b');pending['/jobs/b?view=screen']({id:'b'});await b;pending['/jobs/a?view=screen']({id:'a'});await a;
 assert.equal(ctx.job.id,'b');
});
test('failed open keeps previous inspection and restores the image',async()=>{
 const {ctx,nodes,button}=openSetup(async()=>{throw Error('failed')});await assert.rejects(ctx.openJob('j'),/failed/);
 assert.equal(ctx.job.id,'previous');assert.equal(nodes.get('#inspection-image').src,'old-image');assert.equal(button.disabled,false);
});
test('accordion body renders only when requested and only once',()=>{
 let rendered=0;const body={dataset:{loaded:'false'},innerHTML:''};const card={dataset:{parent:'H-01'},querySelector:()=>body};
 const ctx={job:{checklist_report:{items:[{id:'H-01'}]}},originalBodyHTML:p=>{rendered++;return p.id}};
 vm.createContext(ctx);vm.runInContext(source.slice(source.indexOf('function fillOriginalBody('),source.indexOf("document.addEventListener('toggle'")),ctx);
 assert.equal(rendered,0);ctx.fillOriginalBody(card);ctx.fillOriginalBody(card);assert.equal(rendered,1);assert.equal(body.innerHTML,'H-01');
});
test('group memoization invalidates on review data, selection, normal toggle and image size',()=>{
 const run={results:[{id:'f',rule_id:'D-02-l',parent_id:'D-02',status:'FAIL',rects:[[.1,.2,.3,.4]]}],reviews:[],observation:{objects:[]}};
 let width=500,showNormal=false,reads=0;
 const ctx={activeRun:()=>run,findings:()=>run.results,effective:r=>{reads++;return r.status},selected:null,pack:{parents:[]},$:s=>s==='#pass-toggle'?{checked:showNormal}:{getBoundingClientRect:()=>({width,height:600})}};
 vm.createContext(ctx);vm.runInContext(source.slice(source.indexOf('function measuredFlags()'),source.indexOf('function pinRows()')),ctx);
 const a=ctx.issueGroups(),first=reads;assert.equal(ctx.issueGroups(),a);assert.equal(reads,first);
 width=800;assert.notEqual(ctx.issueGroups(),a);let previous=reads;
 run.reviews=[{finding_id:'f',status:'REVIEW'}];ctx.issueGroups();assert.ok(reads>previous);previous=reads;
 ctx.selected='f';ctx.issueGroups();assert.ok(reads>previous);previous=reads;
 showNormal=true;ctx.issueGroups();assert.ok(reads>previous);
});
