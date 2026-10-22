const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'../../web/assets/delivery-operations.js'),'utf8');
function setup(request){const ctx={request,$:()=>({value:'2026-10-22'}),esc:String,num:String};vm.runInNewContext(source+';globalThis.subject=DeliveryOperations;',ctx);return ctx.subject;}
test('shared policy summary preserves selected-project filtering after removal of the management workspace',async()=>{
 const rows=[{project_id:'a',name:'선택 사업',cause:'PERMIT',units:120,responsible_org:'기관',action:'검토',due_date:'2026-10-30',status:'OPEN'},{project_id:'b',name:'다른 사업'}];let calls=0;
 const subject=setup(async()=>{calls++;return {cases:rows};}),host={isConnected:true};
 await subject.mountPolicy(['a'],host);assert.match(host.innerHTML,/선택 사업/);assert.match(host.innerHTML,/120호/);assert.doesNotMatch(host.innerHTML,/다른 사업/);
 await subject.mountPolicy([],host);assert.match(host.innerHTML,/등록된 병목·조치가 없습니다/);assert.doesNotMatch(host.innerHTML,/시나리오에서|mapping-operations-workspace/);assert.equal(calls,1);
});
test('a failed policy read can retry and a detached panel is not updated',async()=>{
 let calls=0;const subject=setup(async()=>{if(++calls===1)throw Error('일시 조회 오류');return {cases:[]};}),host={isConnected:true};
 await subject.mountPolicy([],host);assert.equal(host.textContent,'일시 조회 오류');
 await subject.mountPolicy([],host);assert.match(host.innerHTML,/등록된 병목·조치가 없습니다/);assert.equal(calls,2);
 const detached={isConnected:false,innerHTML:'기존 화면'};await subject.mountPolicy([],detached);assert.equal(detached.innerHTML,'기존 화면');
});
