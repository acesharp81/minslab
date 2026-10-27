const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const {test}=require('node:test');
const code=fs.readFileSync(require('node:path').join(__dirname,'../app.js'),'utf8');
const pure=code.slice(code.indexOf('function mergeOfficialLiveBroadcasts('),code.indexOf('function renderDetectedAssemblyLive('));
function merge(items,broadcasts){
 const ctx=vm.createContext({items,broadcasts,isWatchTestSource:s=>s==='poc07.test'});
 vm.runInContext(pure,ctx);
 return JSON.parse(vm.runInContext('const p={assembly:{items}}; mergeOfficialLiveBroadcasts(p,{broadcasts}); JSON.stringify(visibleAssemblyMeetings(p.assembly.items))',ctx));
}
const saved=()=>({broadcast_id:'saved',external_id:'meeting',committee_name:'행정안전위원회',source_system:'assembly.webcast.go.kr',lifecycle_status:'LIVE',last_seen_at:new Date().toISOString()});
test('recess retains captured meeting without pretending it is on air',()=>{
 const items=merge([{is_live:false,meeting_external_id:'meeting',status_text:'20:30 계속예정'}],[saved()]);
 assert.equal(items.length,1);assert.equal(items[0].broadcast_id,'saved');assert.equal(items[0].is_live,false);assert.equal(items[0].is_recess,true);
});
test('resumed official broadcast clears recess',()=>{
 const items=merge([{is_live:true,is_recess:true,meeting_external_id:'meeting'}],[saved()]);
 assert.equal(items[0].is_recess,false);assert.equal(items[0].is_live,true);
});
test('same committee cannot substitute a different meeting identity',()=>{
 const official={is_live:false,committee_name:'행정안전위원회',meeting_external_id:'new',status_text:'예정'};
 const items=merge([official],[saved()]);assert.equal(official.broadcast_id,undefined);assert.equal(items[0].external_id,'meeting');
});
test('not-yet-started scheduled meeting is not a saved report',()=>{
 assert.equal(merge([{is_live:false,meeting_external_id:'new',status_text:'20:30 예정'}],[]).length,0);
});
test('temporary official omission keeps recent records but not ended or stale or test records',()=>{
 const items=merge([],[saved(),{...saved(),broadcast_id:'ended',lifecycle_status:'ENDED'},
  {...saved(),broadcast_id:'old',last_seen_at:'2020-01-01T00:00:00Z'},
  {...saved(),broadcast_id:'test',source_system:'poc07.test'}]);
 assert.equal(items.length,1);assert.equal(items[0].is_live,false);assert.equal(items[0].status_text,'방송 상태 확인 중');
});
