const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const {test}=require('node:test');
const code=fs.readFileSync(require('node:path').join(__dirname,'../app.js'),'utf8');
const source=code.slice(code.indexOf('function meetingBriefProgressTag('),code.indexOf('function renderMeetingBriefProcessing('));
function tag(p){const c=vm.createContext({item:{brief_progress:p}});vm.runInContext(source,c);return vm.runInContext('meetingBriefProgressTag(item)',c);}
function stages(item){const c=vm.createContext({item});vm.runInContext(source,c);return vm.runInContext('meetingBriefStageTags(item)',c);}
test('partly linked clusters are not described as wholly unclassified',()=>{
 const c=vm.createContext({});vm.runInContext(source,c);
 const text=c.structuredLineageSummary({live_topic_lineage:{clusters:[
  {final_topic_ids:['a'],review_evidence_ids:['e']}, {final_topic_ids:['b'],review_evidence_ids:[]}]},
  topic_structure:{uncertain:[{atom_id:'a'}],automatic_review:{pending_atom_count:0}}});
 assert.match(text,/2묶음 중 2묶음/);assert.match(text,/이 중 1묶음/);assert.doesNotMatch(text,/주제 미연결|판단 보류/);
});
test('every stage is shown and real narrative count is used instead of analysis count',()=>{
 const t=stages({brief_progress:{completed_chunks:33,total_chunks:33,stages:[
  {key:'INTEGRATION',status:'COMPLETED'}, {key:'REVIEWING',status:'COMPLETED'},
  {key:'NARRATIVE',status:'PROCESSING',completed:212,total:349}, {key:'FINALIZING',status:'PENDING'}]}});
 assert.equal(t.map(x=>x.label).join('|'),'통합 완료|주제 검증 완료|세부 요약 중 (212/349)|최종 확인 대기');
});
test('completion removes all stage tags for both current and legacy reports',()=>{
 for(const item of [{brief_status:'READY'},{meeting_brief:{brief_finalization:{status:'COMPLETED'}}}]){
  const t=stages(item);assert.equal(t.length,1);assert.equal(t[0].label,'비공식 정리 완료');
 }
});
test('waiting keeps completed count and never claims to be processing',()=>{
 const t=stages({brief_progress:{stages:[{key:'REVIEWING',status:'WAITING',completed:36,total:44}]}});
 assert.equal(t[0].label,'주제 검증 재시도 대기 (36/44)');
});
test('unknown future totals are not invented; synthesis does not reuse analysis counts',()=>{
 const t=stages({brief_progress:{phase:'SYNTHESIZING',status:'PROCESSING',completed_chunks:33,total_chunks:33}});
 assert.equal(t.length,6);assert.equal(t[1].label,'통합 중');assert.equal(t[2].label,'주제 검증 대기');
 assert.ok(!t.some(x=>x.label.includes('33')));
});
test('analysis progress remains a completed/total count',()=>assert.equal(tag({status:'PROCESSING',phase:'ANALYZING',completed_chunks:25,total_chunks:33}).label,'정리중 25/33'));
test('33/33 explicitly distinguishes final synthesis from completion',()=>assert.equal(tag({status:'PROCESSING',phase:'SYNTHESIZING',completed_chunks:33,total_chunks:33}).label,'최종 통합중 33/33'));
test('deferred or failed synthesis is never shown as running',()=>{for(const status of ['DEFERRED','FAILED'])assert.equal(tag({status,phase:'SYNTHESIZING',completed_chunks:33,total_chunks:33}).label,'재시도 대기 33/33');});
test('reduction denominator counts integration batches',()=>{const t=tag({status:'PROCESSING',phase:'REDUCING',completed_chunks:2,total_chunks:3});assert.equal(t.label,'주제 통합중 2/3');assert.match(t.title,/주제 통합 묶음/);});
test('quality checks never reuse the 33/33 analysis count as verification progress',()=>{
 for(const phase of ['STRUCTURING','REVIEWING','ONTOLOGY','NARRATIVE','FINALIZING']){
  const t=tag({status:'PROCESSING',phase,completed_chunks:33,total_chunks:33});assert.doesNotMatch(t.label,/33/);
  assert.equal(tag({status:'DEFERRED',phase}).label,'검증 재시도 대기');
 }
});
test('draft polling ignores timestamp-only changes but detects real content and state changes',()=>{
 const src=code.slice(code.indexOf('function meetingBriefRenderSignature('),code.indexOf('function expandMeetingBrief('));
 const c=vm.createContext({});vm.runInContext(src,c);
 const signature=r=>c.meetingBriefRenderSignature(r);
 const r={brief_status:'PROCESSING',brief:{summary:'요약',finalization:{updated_at:'a'}},brief_finalization:{status:'PROCESSING',phase:'STRUCTURING'}};
 const before=signature(r);r.brief.finalization.updated_at='b';assert.equal(signature(r),before);
 r.brief.summary='새 요약';assert.notEqual(signature(r),before);
});
test('partitioned consolidation shows saved batches and deferred status',()=>{
 assert.equal(tag({status:'PROCESSING',phase:'CONSOLIDATING',completed_chunks:1,total_chunks:8}).label,'쟁점 통합중 1/8');
 assert.equal(tag({status:'DEFERRED',phase:'CONSOLIDATING',completed_chunks:1,total_chunks:8}).label,'재시도 대기 1/8');
});
