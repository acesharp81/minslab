'use strict';
const $=s=>document.querySelector(s), $$=s=>[...document.querySelectorAll(s)];
const BASE=location.pathname.startsWith('/poc/image-inspection')?'/poc/image-inspection':'';
const labels={PASS:'정상',FAIL:'오류 의심',REVIEW:'검토 필요',NOT_APPLICABLE:'해당 없음',ERROR:'실행 오류',NOT_RUN:'미실행'};
const colors={PASS:'#2563eb',FAIL:'#dc2626',REVIEW:'#eab308'};
let config={},pack,job=null,selected=null,selectedGroup=null,filter='all',timer=null,cropPending=null,pendingFile=null,previewURL=null,submitting=false;
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function toast(message){$('#toast').textContent=message;$('#toast').hidden=false;setTimeout(()=>$('#toast').hidden=true,6500)}
async function api(path,opts={}){const r=await fetch(BASE+'/api'+path,{...opts,headers:{...(opts.body instanceof FormData?{}:{'Content-Type':'application/json'}),...opts.headers}});let data;try{data=await r.json()}catch{throw Error('응답을 읽을 수 없습니다.')}if(!r.ok){if(r.status===401)$('#login-dialog').showModal();throw Error(typeof data.detail==='string'?data.detail:'입력 항목을 확인하십시오.')}return data}
const post=(path,data={})=>api(path,{method:'POST',body:JSON.stringify(data)});
const guard=fn=>async e=>{try{await fn(e)}catch(err){toast(err.message)}};
function tab(name){$$('.tab').forEach(x=>x.classList.toggle('active',x.id===name));$$('.nav').forEach(x=>x.classList.toggle('active',x.dataset.tab===name))}
async function refreshConfig(){config=await api('/config');$('#rules-nav').hidden=config.role!=='admin';if(config.role!=='admin'&&$('#rules-admin').classList.contains('active'))tab('workspace');$('#login-button').textContent=config.role?`${config.role==='admin'?'관리자':'검토자'} · 로그아웃`:'로그인';$('#key-status').textContent=`OpenAI ${config.openai_configured?'연결 설정됨':'키 미설정'} · Solar ${config.upstage_configured?'연결 설정됨':'키 미설정'} · OpenRouter ${config.openrouter_configured?'연결 설정됨':'키 미설정'} · 규칙 ${config.rule_pack_version}`;void refreshRemaining()}
let remainingLoading=false;
function renderRemaining(payload, fallback='잔여량 미확인'){
 const models=payload?.models||[{id:'gpt-5.4',label:'GPT 5.4'},{id:'gpt-5.4-mini',label:'GPT 5.4 mini'},{id:'openai-shared',label:'GPT 6.0·6.1'},{id:'solar-pro4',label:'Solar Pro 4'},{id:'openrouter-free',label:'Nemotron 3.5 Super VL'}];
 $('#model-remaining').innerHTML=models.map(m=>{
  const known=m.remaining!=null&&m.limit!=null&&Number.isFinite(Number(m.remaining))&&Number.isFinite(Number(m.limit))&&Number(m.limit)>0;
  const left=known?Math.max(0,Number(m.remaining)):null,percent=known?Math.min(100,left/Number(m.limit)*100):null;
  const requests=m.unit==='requests',tokens=m.unit==='tokens';
  const value=known?(left===0?'소진':tokens?`${left.toLocaleString()} 토큰`:requests?`${left.toLocaleString()}회`:`$${left.toFixed(3)}`):(m.display||fallback);
  const note=m.note||fallback;
  const expiry=m.expires_at?' · 기간 종료 '+new Date(m.expires_at).toLocaleString('ko-KR',{timeZone:'Asia/Seoul'}):'';
  const title=known?`${m.label}: ${value} / ${tokens?Number(m.limit).toLocaleString()+' 토큰':requests?m.limit+'회':'$'+Number(m.limit).toFixed(2)} 남음. ${note}${expiry}`:`${m.label}: ${note}`;
  return `<button type="button" class="model-quota ${known&&percent<10?'is-low':''}" data-tab="usage" data-quota-model="${esc(m.id)}" title="${esc(title)}" aria-label="${esc(title)}"><span class="quota-name">${esc(m.label)}</span><b>${esc(value)}</b><span class="quota-percent">${known?percent.toFixed(1)+'%':'—'}</span><span class="quota-meter ${known?'':'is-unknown'}" role="${known?'progressbar':'img'}" aria-label="${esc(m.label)} 잔여 예산${known?'':' 미확인'}" ${known?`aria-valuemin="0" aria-valuemax="100" aria-valuenow="${Math.floor(percent)}"`:''}><i style="width:${known?percent:0}%"></i></span><small>${known?(tokens?`일 ${Number(m.limit).toLocaleString()} 토큰 · PoC7 공용`:requests?(m.id==='naver-ocr'?`월 ${m.limit}회 · 앱 한도`:m.scope==='POC7_SHARED_OPENROUTER_REQUESTS'?`PoC7 공용 · 공식 잔여 ${m.official_remaining}회`:`일 ${m.limit}회 · 계정 공용`):`월 $${Number(m.limit).toFixed(0)} · PoC7 공용`):(m.id==='solar-pro4'&&payload?'사용량만 집계':'공용 예산 확인 필요')}</small></button>`;
 }).join('');
 $('#remaining-updated').textContent=payload?.checked_at?new Date(payload.checked_at).toLocaleTimeString('ko-KR',{timeZone:'Asia/Seoul',hour:'2-digit',minute:'2-digit'})+' 확인 · 30초 갱신':fallback;
}
async function refreshRemaining(){
 if(!config.role){renderRemaining(null,'로그인 후 확인');return}
 if(remainingLoading)return;
 remainingLoading=true;
 try{const r=await fetch(BASE+'/api/usage/remaining',{cache:'no-store'});if(!r.ok)throw Error();renderRemaining(await r.json())}
 catch{renderRemaining(null,'확인 불가')}
 finally{remainingLoading=false}
}
setInterval(()=>{if(!document.hidden)void refreshRemaining()},30000);
document.addEventListener('visibilitychange',()=>{if(!document.hidden)void refreshRemaining()});
function activeRun(){return job?.runs.at(-1)}
function effective(r){const reviews=activeRun()?.reviews||[];return [...reviews].reverse().find(x=>x.finding_id===r.id)?.status||r.status}
function findings(){return activeRun()?.results||[]}
function measuredFlags(){return activeRun()?.scope==='CROP'?[]:(activeRun()?.structural_checks?.flags||[])}
function flagRelatedRows(flag,rows,run){
 if(!run?.analysis_observation)return rows;
 const objects=new Map(run.analysis_observation.objects.map(o=>[o.id,o]));
 return rows.filter(r=>(r.evidence_ids||[]).some(id=>{
  const o=objects.get(id);if(!o)return false;
  const rects=o.rects||o.cell_ids.map(c=>{const y=+c.slice(1,3)-1,x=+c.slice(4,6)-1;return [x/12,y/12,(x+1)/12,(y+1)/12]});
  const area=f=>rects.reduce((n,a)=>n+Math.max(0,Math.min(a[2],f.rect[2])-Math.max(a[0],f.rect[0]))*Math.max(0,Math.min(a[3],f.rect[3])-Math.max(a[1],f.rect[1])),0);
  const best=[...(run.structural_checks?.flags||[])].sort((a,b)=>area(b)-area(a))[0];
  return best?.id===flag.id&&area(best)>0;
 }));
}

function flagObjectRows(flag,rows,run){
 const core=flagRelatedRows(flag,rows.filter(r=>['H-04-h','H-04-i','H-04-m'].includes(r.rule_id)),run);
 if(!run?.analysis_observation)return core;
 const ids=new Set(core.flatMap(r=>r.evidence_ids||[]));
 return rows.filter(r=>core.includes(r)||r.rects?.length&&(r.evidence_ids||[]).some(id=>ids.has(id)));
}
function locationComponents(rects){
 const groups=[];
 for(const rect of rects){
  const touching=groups.filter(g=>g.some(r=>rect[0]<=r[2]+1e-6&&rect[2]>=r[0]-1e-6&&rect[1]<=r[3]+1e-6&&rect[3]>=r[1]-1e-6));
  if(!touching.length)groups.push([rect]);
  else{const first=touching[0];first.push(rect);for(const other of touching.slice(1)){first.push(...other);groups.splice(groups.indexOf(other),1)}}
 }
 return groups;
}
function evidenceAnchor(rects){
 const centers=rects.map(r=>[(r[0]+r[2])/2,(r[1]+r[3])/2]);
 const mean=[0,1].map(i=>centers.reduce((n,c)=>n+c[i],0)/centers.length);
 return centers.reduce((best,c)=>Math.hypot(c[0]-mean[0],c[1]-mean[1])<Math.hypot(best[0]-mean[0],best[1]-mean[1])?c:best);
}
function issueGroups(){
 const groups=new Map(),run=activeRun(),objects=new Map(((run?.analysis_observation||run?.observation)?.objects||[]).map(o=>[o.id,o]));
 const structuralRows=findings().filter(r=>['H-04-h','H-04-i','H-04-m'].includes(r.rule_id)&&r.id&&!['NOT_RUN','ERROR','NOT_APPLICABLE'].includes(effective(r)));
 const structuralFlags=structuralRows.length?measuredFlags().filter(f=>f.status==='MISMATCH'||$('#pass-toggle').checked):[];
 for(const r of findings()){
  if(structuralFlags.some(f=>flagObjectRows(f,findings().filter(r=>r.id&&!['NOT_RUN','ERROR','NOT_APPLICABLE'].includes(effective(r))),run).includes(r)))continue;
  const status=effective(r);if(['NOT_APPLICABLE','NOT_RUN'].includes(status)||(status==='PASS'&&!$('#pass-toggle').checked&&r.id!==selected))continue;
  const visualReview=r.visual_issue||(['TYPO_CONFIRMED','VISUAL_TEXT_DEFECT','OCR_UNREADABLE','OCR_MISMATCH'].includes(r.error_type)&&r.evidence_ids?.length)||(run?.verification?.results||[]).some(v=>r.evidence_ids?.includes(v.object_id)&&v.comparisons?.some(c=>c.rule_ids.includes(r.rule_id)&&['UNCERTAIN','MISMATCH'].includes(c.status)));
  const document=(status==='REVIEW'&&!visualReview)||r.document_review||!r.rects?.length||r.reason.includes('승인된 기준자료 미확보')||r.parent_id==='D-03';
  const ids=document?['document:'+r.parent_id+':'+status]:(r.evidence_ids?.length&&activeRun()?.scope!=='CROP'?r.evidence_ids:['legacy:'+r.rects.map(a=>a.join(',')).sort().join('|')]);
  for(const id of ids){
   const object=objects.get(id),rects=object?(object.rects||object.cell_ids.map(cell=>{const y=Number(cell.slice(1,3))-1,x=Number(cell.slice(4,6))-1;return [x/12,y/12,(x+1)/12,(y+1)/12]})):r.rects;
   if(!groups.has(id))groups.set(id,{id,label:document?'추가 확인 · '+(pack.parents.find(p=>p.id===r.parent_id)?.title||r.parent_id):r.object_label||object?.label||r.instance_id,rows:[],rects:document?[]:rects});
   const g=groups.get(id);if(!g.rows.some(x=>x.id===r.id))g.rows.push(r);
  }
 }
 for(const flag of structuralFlags){
  const related=flagObjectRows(flag,findings().filter(r=>r.id&&!['NOT_RUN','ERROR','NOT_APPLICABLE'].includes(effective(r))),run);if(!related.length)continue;
  const id='structure:'+flag.id;groups.set(id,{id,label:flag.label,rows:related,rects:[flag.rect],comparison:flag,technical:true,measurement:flag.status==='MISMATCH'?'괘 배치 불일치':flag.status==='MATCH'?'괘 배치 일치':'측정 미확정'});
 }
 let rows=[...groups.values()];
 for(const g of rows)if(g.rects.length){
  g.locationRegions=locationComponents(g.rects);
  g.locationAmbiguous=!g.technical&&g.locationRegions.length>1;
  if(!g.locationAmbiguous)g.anchor=evidenceAnchor(g.rects);
 }
 const box=$('#image-wrap').getBoundingClientRect(),w=box.width||500,h=box.height||600;
 // Cluster nearby markers into one selectable group instead of shifting them away from evidence.
 let merged=true;while(merged){merged=false;outer:for(let i=0;i<rows.length;i++)for(let j=i+1;j<rows.length;j++){
  const a=rows[i],b=rows[j];if(!a.anchor||!b.anchor||a.technical||b.technical)continue;
  if(Math.max(Math.abs((a.anchor[0]-b.anchor[0])*w),Math.abs((a.anchor[1]-b.anchor[1])*h))<36&&locationComponents([...a.rects,...b.rects]).length===1){
   a.rows=[...new Map([...a.rows,...b.rows].map(r=>[r.id,r])).values()];a.rects.push(...b.rects);a.label='인접 객체 묶음';a.anchor=evidenceAnchor(a.rects);rows.splice(j,1);merged=true;break outer;
  }
 }}
 rows.sort((a,b)=>(a.anchor?.[1]??2)-(b.anchor?.[1]??2)||(a.anchor?.[0]??2)-(b.anchor?.[0]??2));
 let number=0;for(const g of rows){g.status=g.technical?(g.comparison.status==='MISMATCH'||g.rows.some(r=>effective(r)==='FAIL')?'FAIL':g.comparison.status==='MATCH'?'PASS':'REVIEW'):['FAIL','ERROR','REVIEW','PASS'].find(status=>g.rows.some(r=>effective(r)===status));g.number=(g.anchor||g.locationAmbiguous||g.status==='FAIL')?++number:null;}
 // Uncertain locations stay in the result list, never over an unrelated image object.
 return rows;
}
function pinRows(){return issueGroups().filter(g=>g.anchor||g.calloutAnchor)}
// Hit testing uses saved evidence, independently of visible pins and status filters.
function imageAnalysisTargets(run,statusOf=r=>r.status){
 if(!run)return [];
 const rows=(run.results||[]).filter(r=>r.id&&!['NOT_APPLICABLE','NOT_RUN','ERROR'].includes(statusOf(r)));
 const targets=[],assigned=new Set(),full=run.scope!=='CROP';
 const structural=rows.filter(r=>['H-04-h','H-04-i','H-04-m'].includes(r.rule_id));
 if(full&&structural.length)for(const flag of run.structural_checks?.flags||[]){
  const related=flagObjectRows(flag,rows,run);if(!related.length)continue;
  targets.push({id:'structure:'+flag.id,label:flag.label,rects:[flag.rect],rows:related,technical:true,comparison:flag,
   status:flag.status==='MATCH'?'PASS':flag.status==='MISMATCH'?'FAIL':'REVIEW',
   measurement:flag.status==='MATCH'?'괘 배치 일치':flag.status==='MISMATCH'?'괘 배치 불일치':'측정 미확정'});
  related.forEach(r=>assigned.add(r.id));
 }
 if(full)for(const object of (run.analysis_observation||run.observation)?.objects||[]){
  const rects=object.rects||(object.cell_ids||[]).flatMap(cell=>{
   const m=/^R(\d{2})C(\d{2})$/.exec(cell);if(!m)return [];
   const y=Number(m[1]),x=Number(m[2]);return x>=1&&x<=12&&y>=1&&y<=12?[[ (x-1)/12,(y-1)/12,x/12,y/12 ]]:[];
  });
  const related=rows.filter(r=>!r.crop_id&&!assigned.has(r.id)&&!structural.includes(r)&&r.evidence_ids?.includes(object.id));
  // Without measured flags, structural opinions still use their observed objects.
  if(!targets.some(t=>t.technical))related.push(...structural.filter(r=>!r.crop_id&&r.evidence_ids?.includes(object.id)));
  if(rects.length&&related.length){targets.push({id:object.id,label:object.label,rects,rows:related});related.forEach(r=>assigned.add(r.id))}
 }
 for(const row of rows)if(!assigned.has(row.id)&&row.rects?.length){
  targets.push({id:'area-result:'+row.id,label:row.object_label||row.instance_id||row.rule_id,rects:row.rects,rows:[row]});
 }
 return targets;
}
function analysisAtPoint(targets,x,y){
 if(x<0||x>1||y<0||y>1)return [];
 const matches=new Map();
 for(const target of targets){
  // Check each evidence cell, never the empty gap between disconnected cells.
  if(!target.rects.some(r=>x>=r[0]&&x<=r[2]&&y>=r[1]&&y<=r[3]))continue;
  for(const row of target.rows)if(!matches.has(row.id))matches.set(row.id,{row,groupId:target.id,label:target.label,technical:target.technical});
 }
 return [...matches.values()];
}
function selectedAnalysisGroup(){
 return issueGroups().find(g=>selectedGroup?g.id===selectedGroup:g.rows.some(r=>r.id===selected))||
  (selectedGroup?imageAnalysisTargets(activeRun(),effective).find(g=>g.id===selectedGroup):null);
}
function openFinding(id,groupId){
 if(!findings().some(r=>r.id===id)){toast('분석 결과가 변경되었습니다. 이미지 영역을 다시 선택하세요.');return}
 if($('#area-dialog').open)$('#area-dialog').close();
 selected=id;selectedGroup=groupId||null;renderIssues();renderOverlay();renderDetail();
 const detail=$('#finding-detail');detail.focus({preventScroll:true});detail.scrollIntoView({behavior:matchMedia('(prefers-reduced-motion: reduce)').matches?'auto':'smooth',block:'start'});
}
function inspectImagePoint(event){
 if(event.target.closest('[data-finding]')||!activeRun())return;
 const box=$('#inspection-image').getBoundingClientRect();if(!box.width||!box.height)return;
 const x=(event.clientX-box.left)/box.width,y=(event.clientY-box.top)/box.height;
 const matches=analysisAtPoint(imageAnalysisTargets(activeRun(),effective),x,y);
 if(!matches.length){toast('이 영역에 연결된 분석이 없습니다. 원문별 결과에서도 확인할 수 있습니다.');return}
 if(matches.length===1){openFinding(matches[0].row.id,matches[0].groupId);return}
 $('#area-dialog-count').textContent=`이 영역의 분석 ${matches.length}개`;
 $('#area-dialog-list').innerHTML=matches.map(({row,groupId,label,technical})=>`<button class="area-choice" data-finding="${esc(row.id)}" data-group="${esc(groupId)}"><span class="area-choice-heading"><b>${esc(row.rule_id)}</b><span class="status-${effective(row)}">${labels[effective(row)]}</span></span><strong>${esc(label)}</strong><span>${esc(row.reason)}</span><small>${technical?'원본 구조 비교 포함':'저장된 대략적 위치 기준'} · 분석 내용 보기 →</small></button>`).join('');
 $('#area-dialog').showModal();
}
$('#image-wrap').addEventListener('click',inspectImagePoint);
$('#close-area-dialog').onclick=()=>$('#area-dialog').close();
$('#area-dialog').addEventListener('click',e=>{if(e.target!==e.currentTarget)return;const b=e.currentTarget.getBoundingClientRect();if(e.clientX<b.left||e.clientX>b.right||e.clientY<b.top||e.clientY>b.bottom)e.currentTarget.close()});

function renderTokens(){
 const run=activeRun(),totals=new Map();
 for(const call of run?.calls||[]){const model=call.model||'알 수 없음',r=totals.get(model)||{input:0,output:0,calls:0,unknown:0};r.input+=call.usage?.input_tokens||0;r.output+=call.usage?.output_tokens||0;r.calls++;if(call.usage_unknown)r.unknown++;totals.set(model,r)}
 $('#run-tokens').innerHTML=run?`<strong>이번 검사 모델별 사용량</strong>${run.observation_reused_from?'<span class="badge">이미지 읽기 재사용 · 이미지 호출 0회</span>':''}<div class="token-rows">${[...totals].map(([m,r])=>`<span><b>${esc(m)}</b> 입력 ${r.input.toLocaleString()} · 출력 ${r.output.toLocaleString()} · 합계 ${(r.input+r.output).toLocaleString()} 토큰 / ${r.calls}회${r.unknown?' · 미확정 '+r.unknown+'회':''}</span>`).join('')||'<span>아직 완료된 API 호출이 없습니다.</span>'}</div><small>호출 응답을 받은 뒤 갱신됩니다. 생성 중 토큰은 공급자 응답 전까지 미확정입니다.</small>`:'';
 const observation=run?.observation;
 const cv=run?.text_coverage,v=run?.verification;
 if(cv)$('#run-tokens').innerHTML+=`<p>탐지 문자 ${cv.detected_text_regions} · 전사 ${cv.transcribed_regions} · 판독 어려움 ${cv.unreadable_regions} · 재검사 ${cv.rechecked_text_regions} · 판독 차이 ${cv.ocr_disagreement_regions}</p><small>${esc(cv.note)}</small>`;
 const tx=run?.text_ocr;
 if(tx)$('#run-tokens').innerHTML+=`<p>독립 한국어 OCR · ${tx.status==='COMPLETED'?'완료':tx.status==='PARTIAL'?'일부 미확정':tx.status==='RUNNING'?'검사 중':'미완료'} · 문자 후보 ${tx.candidate_count??0} · 원본 획 검사 ${tx.vision_checked??0} · 미검사 ${(tx.vision_deferred??0)+(tx.deferred_count??0)}</p><small>${esc(tx.error||tx.note)}${tx.naver?' · NAVER: '+esc(tx.naver.note||tx.naver.status):''}</small>`;
 if(v?.deferred?.length)$('#run-tokens').innerHTML+=`<p>자동 재검사 미확정 ${v.deferred.length}개 · 상세에서 이유와 선택 재검사를 확인하세요.</p>`;
 $('#observation-summary').hidden=!observation;
 if(observation)$('#observation-summary').innerHTML=`<summary>저장된 이미지 인식 · ${esc(run.observation_model||run.options.vision_model)} · ${observation.objects.length}개 객체</summary><p>${esc(observation.summary)}</p><p>${esc(observation.context)}</p><p>${esc(observation.limitations)}</p>${observation.location_warnings?.length?`<p>위치 정보 ${observation.location_warnings.length}개 객체 확인 필요: 범위를 벗어난 셀만 제외하고 관찰 내용은 분석에 사용했습니다.</p>`:''}`;
}
function renderJob(){
 $('#work-area').hidden=false;$('#empty-state').hidden=true;$('#job-title').textContent=job.metadata.title;$('#demo-badge').hidden=activeRun()?.options.mode!=='mock';$('#preview-empty').hidden=true;$('#drop-zone').hidden=true;$('.image-stage').hidden=false;$('#inspection-image').hidden=false;$('#image-click-hint').hidden=!activeRun();
 const running=['RUNNING','QUEUED'].includes(job.state);const run=activeRun();
 $('#job-state').textContent=({READY:'검사 준비',RUNNING:'분석 중',QUEUED:'대기 중',COMPLETED:'검사 종료',COMPLETED_WITH_ERRORS:'오류 확인 필요',INTERRUPTED:'중단됨'})[job.state]||job.state;
 $('#run').disabled=running||submitting;$('#text-sensitivity').disabled=running;$('#file').disabled=running;$('#rerun').disabled=running;$('#reanalyze').disabled=running||!run||run.options.mode!=='live'||run.scope==='CROP';$('#progress-panel').hidden=!running;$('#scanner').hidden=!running;
 if(run){$('#scanner span').textContent=run.phase==='STRUCTURE'?'원본 획 구조 비교 중':run.phase==='TEXT_OCR'?'문자 탐지 · 독립 OCR · 원본 획 비교 중':run.phase==='VERIFYING'?'확대 판독 · 공식 도안 비교 중':run.phase==='ANALYZING'?'저장된 관찰로 규칙 분석 중':'이미지 읽는 중';const errors=run.analysis.filter(x=>x.error);$('#notice').textContent=errors.length?'2차 분석 중 오류가 발생했습니다: '+errors.map(x=>x.error).join(' / '):'자동 검수는 최종 공개 승인이 아닙니다. 오류 의심·검토 필요 항목은 담당자가 근거를 확인하세요.';$('#progress-text').textContent=run.phase==='READING'?'1 / 3 · 전체 이미지 관찰 중':run.phase==='TEXT_OCR'?'2 / 3 · 문자 탐지·원본 획 독립 검사':run.phase==='VERIFYING'?'2 / 3 · 필요한 영역 묶음 재검사':`3 / 3 · 저장된 관찰로 규칙 분석 ${run.progress} / ${run.total}`;
 $('#progress-bar').style.width=(run.total?run.progress/run.total*100:0)+'%';$('#elapsed').textContent=`${running?Math.max(0,Math.floor((Date.now()-new Date(run.created_at).getTime())/1000)):run.elapsed_seconds||0}초 · API ${run.calls.length}회`;
 if(run.reused_from)$('#job-state').textContent='동일 조건 결과 재사용 · API 0회';}
 const imageURL=BASE+`/api/jobs/${job.id}/image`;if($('#inspection-image').getAttribute('src')!==imageURL)$('#inspection-image').src=imageURL;
 renderIssues();renderChecklist();renderOverlay();renderDetail();renderTokens();renderOriginalReport();
 if(running&&!timer)timer=setTimeout(poll,1700);
}
async function poll(){timer=null;if(!job)return;try{job=await api(`/jobs/${job.id}`);renderJob();if(!['RUNNING','QUEUED'].includes(job.state))void refreshRemaining()}catch(e){toast(e.message);timer=setTimeout(poll,5000)}}
function renderIssues(){
 const groups=issueGroups(),unlocated=groups.filter(g=>g.number&&!g.anchor);
 $('#issue-count').textContent=`이미지 위치 ${groups.filter(g=>g.anchor).length} · 위치 미확정 ${unlocated.length} · 추가 확인 ${groups.filter(g=>!g.number).length}`;
 $('#location-total').textContent=groups.filter(g=>g.number).length;
 const summary=$('#unlocated-findings');summary.hidden=!unlocated.length;
 summary.innerHTML=unlocated.length?`<h2>발견 내용 · 위치 확인 필요</h2>${unlocated.map(g=>`<button class="unlocated-finding" data-group="${esc(g.id)}" data-finding="${esc(g.rows[0].id)}"><span class="number" style="border-color:${colors[g.status]||'#a873b5'}">${g.number}</span><span class="unlocated-content"><b class="status-${g.status}">${labels[g.status]} · ${g.rows.length}개 검토 의견</b>${[...new Set(g.rows.map(r=>r.reason))].map(reason=>`<span>${esc(reason)}</span>`).join('')}<small>발견 내용은 유지됩니다. ${g.calloutAnchor?'이미지 가장자리의 번호를 누르면 의견을 볼 수 있습니다. 글자 경계는 아직 확인되지 않았습니다.':'좌표가 없어 결과 목록에 번호를 표시합니다.'} · 의견 보기</small></span></button>`).join('')}`:'';
 const rows=filter==='all'?groups:groups.filter(g=>g.status===filter||(!g.technical&&g.rows.some(r=>effective(r)===filter)));
 $('#issues').innerHTML=rows.map(g=>`<button class="issue ${(selectedGroup?g.id===selectedGroup:g.rows.some(r=>r.id===selected))?'selected':''}" data-group="${esc(g.id)}" data-finding="${g.rows[0].id}"><div class="issue-head"><span class="number" style="border-color:${colors[g.status]||'#a873b5'}">${g.number||'·'}</span><span class="status-${g.status}">${g.measurement||labels[g.status]}</span><span>${g.rows.length}개 항목</span></div><strong>${esc(g.label)}</strong>${g.locationAmbiguous?'<small class="location-note">위치 확인 필요 · 발견 내용 유지</small>':''}<p>${esc(g.technical?(g.comparison.status==='MISMATCH'?'원본 획·위치에서 확인한 불일치입니다. 퀴즈 제작 의도 검토는 별개입니다.':g.comparison.status==='MATCH'?'측정한 괘 획·위치는 기준과 일치합니다. 전체 국기의 적합성 판정은 별개입니다.':'일부 획·위치의 측정이 불확실하여 원본 확인이 필요합니다.'):g.rows[0].reason)}</p><small>${[...new Set(g.rows.map(r=>r.parent_id))].map(esc).join(' · ')}</small></button>`).join('')||'<div class="empty-note">현재 표시할 발견 사항이 없습니다.<br>규칙 분석이 끝난 묶음부터 표시됩니다.</div>';
}
function renderChecklist(){
 const checked=new Set($$('.parent-select:checked').map(x=>x.value));let last='';
 $('#checklist').innerHTML=job.parents.map(p=>{const group=last!==p.category?`<div class="check-group">${p.category} / ${esc(pack.categories[p.category])}</div>`:'';last=p.category;
 const rows=findings().filter(r=>r.parent_id===p.id);return group+`<div class="check-row"><input type="checkbox" class="parent-select" value="${p.id}" aria-label="${p.id} 재검사 선택" ${checked.has(p.id)?'checked':''}><div><button class="check-original-link" data-parent-analysis="${p.id}">${p.id} ${esc(p.title)}</button><small>${p.reviewed}/${p.total} 사람 검토${!p.complete?' · 미완료 항목 있음':''}</small><details><summary class="micro">원문·세부 행동 ${rows.length}</summary><p class="micro">${esc(p.original)}</p><div class="step-list">${rows.map(r=>`<button data-finding="${r.id}">${esc(r.rule_id)} · ${labels[effective(r)]} · ${esc(r.instance_id)}</button>`).join('')}</div></details></div><span class="check-state status-${p.status}">${labels[p.status]}</span></div>`}).join('');
}
function renderOverlay(){
 let svg='';if($('#grid-toggle').checked)for(let r=0;r<12;r++)for(let c=0;c<12;c++)svg+=`<rect class="grid-cell" x="${c/12*1000}" y="${r/12*1000}" width="${1000/12}" height="${1000/12}"/>`;
 const pins=pinRows();
 const group=selectedAnalysisGroup();
 // Draw only connected evidence extents; never bridge separate panels.
 if(group?.technical)for(const region of locationComponents(group.rects)){const xs=region.flatMap(r=>[r[0],r[2]]),ys=region.flatMap(r=>[r[1],r[3]]);svg+=`<rect x="${Math.min(...xs)*1000}" y="${Math.min(...ys)*1000}" width="${(Math.max(...xs)-Math.min(...xs))*1000}" height="${(Math.max(...ys)-Math.min(...ys))*1000}" rx="8" ${group.locationAmbiguous?'stroke-dasharray="5 4"':''} stroke="${colors[group.status]||'#a873b5'}"/>`}
 $('#overlays').innerHTML=svg;
 $('#pins').innerHTML=pins.map(g=>`<button class="pin ${g.technical?'technical':''} ${g.calloutAnchor?'location-callout':''} status-${g.status} ${g.id===group?.id?'selected':''}" data-group="${esc(g.id)}" data-finding="${g.rows[0].id}" style="left:${(g.anchor||g.calloutAnchor)[0]*100}%;top:${(g.anchor||g.calloutAnchor)[1]*100}%;--pin-color:${colors[g.status]||'#a873b5'};border-color:${colors[g.status]||'#a873b5'}" title="${esc(g.label+' · '+g.rows.length+'개 검토 의견'+(g.calloutAnchor?' · 문구 위치 확인 필요':''))}" aria-label="${g.number} ${esc(g.label)} ${g.rows.length}개 항목">${g.number}</button>`).join('');
}
function renderDetail(){
 const r=findings().find(x=>x.id===selected),run=activeRun(),target=$('#finding-detail');
 if(!r){target.className='detail-empty';target.textContent='미리보기의 번호 또는 결과 항목을 선택하면 근거와 검토 의견을 볼 수 있습니다.';return}
 target.className='';const group=selectedAnalysisGroup();const groupHTML=group?`<div class="group-opinions"><h2>${group.number?'번호 '+group.number+' · ':''}${esc(group.label)}</h2>${group.technical?`<p class="measurement-verdict status-${group.status}">측정 결과 · ${esc(group.measurement)}</p><p class="micro">빨강은 원본과 기준의 구조 불일치입니다. 아래 원문 의견의 ‘검토 필요’는 퀴즈 등 제작 의도에 대한 판단입니다.</p>`:''}${group.locationAmbiguous?`<p class="location-warning">위치 미확정 · 서로 떨어진 ${group.locationRegions.length}개 영역이 한 객체로 인식됐습니다. 이미지 가장자리의 번호는 의견을 여는 버튼입니다. 정확한 글자 경계를 확인하지 못해 사각형은 표시하지 않습니다.</p>`:''}${group.rows.map(x=>`<button data-group="${esc(group.id)}" data-finding="${x.id}" class="opinion ${x.id===r.id?'selected':''}"><b>${esc(x.rule_id)} · ${labels[effective(x)]}</b><span>${esc(x.reason)}</span><small>조치: ${esc(x.recommended_action)}</small></button>`).join('')}</div>`:'';const step=(run.rule_pack||pack).steps.find(s=>s.rule_id===r.rule_id);const running=['QUEUED','RUNNING'].includes(job.state);
 target.innerHTML=groupHTML+(group?.comparison?comparisonHTML(group.comparison):r.comparison?comparisonHTML(r.comparison):'')+`<div class="panel-title"><h2>${esc(r.rule_id)} · ${labels[effective(r)]}</h2><span class="badge">${esc(r.instance_id)}</span></div><p>${esc(step.objective)}</p><div class="detail-label">직접 관찰</div><div>${esc(r.observation||'관찰 기록 없음')}</div>${textQualityHTML(r)}${verificationHTML(r)}<div class="detail-label">판정 이유</div><div>${esc(r.reason)}</div><div class="detail-label">근거와 위치</div><div class="micro">${esc(r.model)} · 규칙 ${esc(r.rule_version)} · ${esc(r.evidence_quality)}<br>${r.comparison?'원본 픽셀의 괘 구조 비교 · 객체 영역':(r.crop_id?'확대 격자 '+esc(r.crop_id.slice(0,13)):'전체 이미지 · 대략적 위치')+' / '+esc(r.cell_ids.join(', ')||'위치 없음')}<br>${r.reference_ids.map(id=>esc(run.reference_snapshot.find(x=>x.id===id)?.name||id)).join(', ')||(r.technical_reference?'내장 기술 기준: '+esc(r.technical_reference.name):'인용한 승인 자료 없음')}</div>${run.analysis.filter(a=>a.finding_id===r.id).map(a=>`<div class="detail-label">${esc(a.model)} 분석 의견 · ${labels[a.opinion]}</div><div>${esc(a.reason)}</div>`).join('')}<div class="finding-actions"><button id="retry-step" class="secondary" ${running?'disabled':''}>이 행동만 재검사</button>${r.cell_ids.length&&!r.crop_id?`<button id="crop-step" class="secondary" ${running?'disabled':''}>주변 포함 확대 재검사</button>`:''}</div><form id="review-form" class="review-form"><select name="status" aria-label="사람 검토 판정"><option value="REVIEW">검토 보류</option><option value="PASS">정상으로 수정</option><option value="FAIL">오류 의심 확인</option><option value="NOT_APPLICABLE">해당 없음</option></select><button class="primary" ${running?'disabled':''}>검토 기록 저장</button><textarea name="reason" required minlength="5" maxlength="2000" placeholder="판단 근거와 수정 사유를 입력하세요. 최종 공개 승인을 대신하지 않습니다."></textarea></form>${run.reviews.filter(x=>x.finding_id===r.id).map(x=>`<div class="audit-entry"><strong>${labels[x.previous_status]} → ${labels[x.status]}</strong> · ${esc(x.reviewer)} · ${new Date(x.at).toLocaleString('ko-KR')}<br>${esc(x.reason)}</div>`).join('')}`;
 $('#retry-step').onclick=guard(()=>startRun([r.rule_id],null,true));
 if($('#crop-step'))$('#crop-step').onclick=guard(async()=>{const c=await post(`/jobs/${job.id}/crops`,{cell_ids:r.cell_ids});cropPending={crop:c,rule_ids:[r.rule_id]};$('#crop-image').src=BASE+`/api/jobs/${job.id}/crops/${c.id}`;$('#crop-dialog').showModal()});
 $('#review-form').onsubmit=guard(async e=>{e.preventDefault();const f=new FormData(e.target);job=await post(`/jobs/${job.id}/reviews`,{finding_id:r.id,status:f.get('status'),reason:f.get('reason')});renderJob();toast('검토 이력을 저장했습니다.')});
}
async function startRun(ids=[],cropID=null,force=false,mode='live'){if(!job)return;const consent=mode==='live'?await requestTransmission(false):false;if(mode==='live'&&!consent)return;job=await post(`/jobs/${job.id}/runs`,{mode,vision_model:$('#vision-model').value,analysis_model:$('#analysis-model').value,consent,text_sensitivity:$('#text-sensitivity').value,rule_ids:ids,crop_id:cropID,force});selected=null;selectedGroup=null;renderJob()}
async function reanalyze(sourceRunID){
 if(!job)return;
 const source=job.runs.find(r=>r.id===sourceRunID)||activeRun();
 const consent=await requestTransmission(true);if(!consent)return;
 job=await post(`/jobs/${job.id}/runs`,{mode:'live',vision_model:source.options.vision_model,analysis_model:$('#analysis-model').value||'gpt-5.4-mini',consent,text_sensitivity:source.options.text_sensitivity||'standard',rule_ids:[],force:true,reuse_observation_run_id:source.id});
 selected=null;selectedGroup=null;renderJob();toast('저장된 이미지 관찰로 원문 25개 항목 전체를 재분석합니다.');
}
async function openJob(id){if(timer){clearTimeout(timer);timer=null}job=await api('/jobs/'+id);pendingFile=null;$('#file').value='';clearPreviewURL();fillMetadata();selected=null;selectedGroup=null;tab('workspace');renderJob();resultView('original')}
async function history(){const rows=await api('/jobs');$('#history-list').innerHTML=rows.map(j=>`<div class="card history-row"><div><h2>${esc(j.metadata.title)}</h2><p>${esc(j.metadata.department)} · ${new Date(j.created_at).toLocaleString('ko-KR')} · ${esc(j.state)}</p></div><div class="history-controls"><button class="secondary" data-open-job="${j.id}">결과 열기</button><button class="secondary" data-reanalysis-job="${j.id}">분석 모델 변경</button><button class="quiet" data-versions="${j.id}">검사 버전</button>${config.role==='admin'?`<button class="quiet" data-delete-job="${j.id}">삭제</button>`:''}</div><div id="versions-${j.id}"></div></div>`).join('')||'<div class="card">등록된 검수 이력이 없습니다.</div>'}
async function references(){const rows=await api('/references');$('#reference-list').innerHTML=rows.map(r=>`<div class="card reference-card"><div class="panel-title"><h2>${esc(r.name)}</h2><span class="badge">${esc(r.status)}</span></div><p>${esc(r.issuer)} · ${esc(r.version)} · ${esc(r.parent_ids.join(', '))}</p><a href="${esc(r.official_url)}" target="_blank" rel="noopener noreferrer">공식 출처 ↗</a><pre>${esc(r.content)}</pre>${r.image_file?`<img src="${BASE}/api/references/${r.id}/image" alt="공식 비교 이미지">`:''}<p class="micro">${r.approved_at?'승인: '+esc(r.approved_by)+' / '+new Date(r.approved_at).toLocaleString('ko-KR'):'승인 전 자료는 검사에 사용되지 않습니다.'}</p>${config.role==='admin'&&r.status==='DRAFT'?`<button class="secondary" data-approve="${r.id}">출처·적용범위 확인 후 승인</button>`:''}</div>`).join('')||'<div class="card"><h2>아직 승인된 기준자료가 없습니다.</h2><p>공식 도안·정책·이용권을 확인할 수 없는 항목은 검토 필요로 유지합니다.</p></div>'}
async function usage(){const u=await api('/usage');let shared=u.shared?.external_breakdown||[];const b=u.budget;$('#usage-body').innerHTML=`<div class="metrics"><div class="metric"><small>PoC11 누적 호출</small><strong>${u.events.length}</strong><small>시연·캐시 재사용은 미포함</small></div><div class="metric"><small>PoC11 추정 비용</small><strong>$${u.cost_usd.toFixed(4)}</strong><small>비용 미확정 ${u.unknown_cost_calls}회</small></div><div class="metric"><small>PoC7 공용 원장 잔여</small><strong>${b?'$'+b.remaining_usd.toFixed(2):'확인 필요'}</strong><small>${b?'예산 $'+b.limit_usd+' · 예약 $'+b.reserved_usd.toFixed(2):esc(u.budget_error||'공용 예산 미연결')}</small></div><div class="metric"><small>중앙 전송 대기</small><strong>${u.pending}</strong><small>${u.shared_error?esc(u.shared_error):'PoC7 중앙 서비스 연결됨'}</small></div></div><div class="notice">${esc(u.cost_basis)}. GPT-5.4는 일 100만, mini는 일 1,000만 토큰을 PoC7과 공유해 예약·정산합니다. GPT 6.0·6.1은 공용 크레딧을 사용합니다. 아래 비용은 표준 요금 환산값이며 무료 적용 후 청구액이 아닙니다. Solar 사용량은 중앙 집계하며 공급자 잔액으로 표시하지 않습니다. 중앙 일별 기록은 수신일(UTC) 기준입니다.</div>${u.naver_ocr?`<div class="notice"><b>NAVER CLOVA OCR · ${u.naver_ocr.remaining} / ${u.naver_ocr.limit}회 남음</b><p>${esc(u.naver_ocr.note)}</p><small>이번 달 ${u.naver_ocr.used}회 · 미확정 ${u.naver_ocr.unknown}회 · 갱신 ${new Date(u.naver_ocr.expires_at).toLocaleString('ko-KR')}</small><details><summary>NAVER 호출 이력</summary>${u.naver_ocr_events.map(e=>`<p>${new Date(e.at).toLocaleString('ko-KR')} · ${esc(e.state)} · ${esc(e.detail)}</p>`).join('')||'호출 이력 없음'}</details></div>`:''}<h2>PoC11 호출 내역</h2><div class="table-wrap"><table><thead><tr><th>시각</th><th>단계</th><th>모델</th><th>입력 / 출력 토큰</th><th>추정 USD</th><th>중앙 전송</th></tr></thead><tbody>${u.events.slice().reverse().map(e=>`<tr><td>${new Date(e.recorded_at).toLocaleString('ko-KR')}</td><td>${esc(e.workload)}</td><td>${esc(e.model)}</td><td>${e.input_tokens} / ${e.output_tokens}</td><td>${e.cost_usd===null?'미확정':e.cost_usd.toFixed(5)}</td><td>${e.synced?'완료':'대기'} · ${esc(e.status)}</td></tr>`).join('')}</tbody></table></div><h2 style="margin-top:28px">공용 게이트웨이 · 오늘(UTC)</h2><div class="table-wrap"><table><thead><tr><th>프로젝트</th><th>모델</th><th>호출</th><th>토큰</th><th>USD</th></tr></thead><tbody>${shared.map(r=>`<tr><td>${esc(r.project)}</td><td>${esc(r.model)}</td><td>${r.count}</td><td>${r.input_tokens+r.output_tokens}</td><td>${r.cost_usd??'미확정'}</td></tr>`).join('')}</tbody></table></div>`}
function clearPreviewURL(){if(previewURL){URL.revokeObjectURL(previewURL);previewURL=null}}
function fillMetadata(){for(const el of $('#upload-form').elements){if(el.name&&el.name!=='file'){el.value=job.metadata[el.name]||'';el.disabled=true}}$('#file-label').textContent=job.metadata.title;}
async function runImageAnalysis(){
 if(submitting)return;
 if(!pendingFile&&!job)throw Error('먼저 이미지를 첨부하세요.');
 submitting=true;$('#run').disabled=true;
 try{
  if(pendingFile){
   const form=$('#upload-form');if(!form.reportValidity())return;
   job=await api('/jobs',{method:'POST',body:new FormData(form)});pendingFile=null;clearPreviewURL();fillMetadata();
  }
  selected=null;selectedGroup=null;await startRun([],null,true);resultView('original');
 }finally{submitting=false;if(job)renderJob();else $('#run').disabled=!pendingFile}
}
$('#upload-form').onsubmit=guard(async e=>{e.preventDefault();await runImageAnalysis()});
$('#file').onchange=guard(async()=>{
 const file=$('#file').files[0];if(!file)return;
 if(file.size>20*1024*1024)throw Error('20MB 이하 이미지를 첨부하세요.');
 if(!['image/png','image/jpeg','image/webp'].includes(file.type))throw Error('PNG, JPG, WebP 이미지를 첨부하세요.');
 if(timer){clearTimeout(timer);timer=null}pendingFile=file;job=null;$('#image-click-hint').hidden=true;selected=null;selectedGroup=null;clearPreviewURL();
 for(const el of $('#upload-form').elements)if(el.name&&el.name!=='file')el.disabled=false;
 $('#upload-form [name=title]').value=file.name.replace(/\.[^.]+$/,'');$('#file-label').textContent=file.name;
 previewURL=URL.createObjectURL(file);$('#inspection-image').src=previewURL;$('#inspection-image').hidden=false;$('#preview-empty').hidden=true;$('#drop-zone').hidden=true;$('.image-stage').hidden=false;
 $('#overlays').innerHTML='';$('#pins').innerHTML='';$('#unlocated-findings').innerHTML='';$('#unlocated-findings').hidden=true;$('#scanner').hidden=true;$('#work-area').hidden=true;$('#empty-state').hidden=false;
 $('#run').disabled=false;$('#reanalyze').disabled=true;$('#rerun').disabled=true;
});
$('#demo').onclick=guard(async()=>{job=await post('/demo');pendingFile=null;$('#file').value='';clearPreviewURL();fillMetadata();selected=null;selectedGroup=null;renderJob();await startRun([],null,false,'mock');resultView('original')});
$('#run').onclick=guard(runImageAnalysis);
$('#reanalyze').onclick=guard(()=>reanalyze());
$('#rerun').onclick=guard(()=>{const p=$$('.parent-select:checked').map(x=>x.value);if(!p.length)throw Error('오른쪽에서 재검사할 항목을 선택하십시오.');return startRun(pack.steps.filter(s=>p.includes(s.parent_id)).map(s=>s.rule_id),null,true)});
$('#run-crop').onclick=guard(async()=>{$('#crop-dialog').close();await startRun(cropPending.rule_ids,cropPending.crop.id,true)});
$('#close-crop').onclick=()=>$('#crop-dialog').close();
$('#export').onclick=guard(async()=>{
 if(!job)return;const button=$('#export');button.disabled=true;
 try{const response=await fetch(BASE+`/api/jobs/${job.id}/report`);if(!response.ok){let body={};try{body=await response.json()}catch{}throw Error(body.detail||'보고서 저장에 실패했습니다. 화면과 이력은 유지됩니다.')}
 const blob=await response.blob();JSON.parse(await blob.text());const url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download=`chekmi-${job.id}.json`;document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),30000);toast('JSON 보고서를 저장했습니다.');}
 finally{button.disabled=false}
});$('#print').onclick=()=>window.print();
$('#grid-toggle').onchange=renderOverlay;$('#pass-toggle').onchange=()=>{renderIssues();renderOverlay()};$('#clear-selection').onclick=()=>{selected=null;selectedGroup=null;renderIssues();renderOverlay();renderDetail()};
$('#login-button').onclick=guard(async()=>{if(config.role){await post('/logout');await refreshConfig();toast('독립 로그인 세션을 종료했습니다. MinsLab 관리자 세션은 별도로 로그아웃하십시오.')}else $('#login-dialog').showModal()});
$('#close-login').onclick=()=>$('#login-dialog').close();$('#login-form').onsubmit=guard(async e=>{e.preventDefault();const f=new FormData(e.target);await post('/login',Object.fromEntries(f));$('#login-dialog').close();e.target.reset();await refreshConfig();toast('로그인했습니다.')});
$('#reference-form').onsubmit=guard(async e=>{e.preventDefault();const f=new FormData(e.target),image=f.get('reference_image');f.delete('reference_image');const d=Object.fromEntries(f);d.parent_ids=d.parent_ids.split(',').map(x=>x.trim());const r=await post('/references',d);if(image?.size){const fd=new FormData();fd.set('file',image);await api(`/references/${r.id}/image`,{method:'POST',body:fd})}e.target.reset();await references();toast('기준자료 초안을 등록했습니다.')});
$('#sync-usage').onclick=guard(async()=>{await post('/usage/sync');await usage()});
document.addEventListener('click',guard(async e=>{const f=e.target.closest('[data-finding]');if(f){openFinding(f.dataset.finding,f.dataset.group);return}const nav=e.target.closest('[data-tab]');if(nav){tab(nav.dataset.tab);if(nav.dataset.tab==='history')await history();if(nav.dataset.tab==='references')await references();if(nav.dataset.tab==='usage')await usage();if(nav.dataset.tab==='rules-admin'&&!rulesState)await loadRuleEditor();return}const filterButton=e.target.closest('[data-filter]');if(filterButton){filter=filterButton.dataset.filter;$$('.filter').forEach(x=>x.classList.toggle('active',x===filterButton));renderIssues();return}const reanalysis=e.target.closest('[data-reanalysis-job]');if(reanalysis){await openJob(reanalysis.dataset.reanalysisJob);$('#analysis-model').focus();toast('분석 모델을 선택하고 ‘이미지 재사용 · 재분석’을 누르세요.');return}const source=e.target.closest('[data-source-run]');if(source){tab('workspace');await reanalyze(source.dataset.sourceRun);return}const open=e.target.closest('[data-open-job]');if(open)return openJob(open.dataset.openJob);const del=e.target.closest('[data-delete-job]');if(del&&confirm('이미지와 검토 내용을 영구 삭제하시겠습니까? 사용량 기록은 유지됩니다.')){await api('/jobs/'+del.dataset.deleteJob,{method:'DELETE'});return history()}const approve=e.target.closest('[data-approve]');if(approve){await post('/references/'+approve.dataset.approve+'/approve');return references()}const versions=e.target.closest('[data-versions]');if(versions){const j=await api('/jobs/'+versions.dataset.versions);$('#versions-'+j.id).innerHTML=j.runs.map((r,i)=>`<p class="micro">검사 ${i+1} · ${new Date(r.created_at).toLocaleString('ko-KR')} · ${esc(r.options.vision_model)} / ${esc(r.options.analysis_model)} · ${r.results.length}개 결과 · 검토 ${r.reviews.length}건 ${r.options.mode==='live'&&r.scope!=='CROP'?`<button class="quiet" data-source-run="${r.id}">이 버전의 관찰로 재분석</button>`:''}</p>`).join('')+'<p class="micro">전체 버전의 상세 결과·기준자료·검토 기록은 JSON 보고서에 포함됩니다.</p>'}}));
(async()=>{try{await refreshConfig();pack=await api('/rules')}catch(e){toast(e.message)}})();

$('#inspection-image').onload=()=>{if(job){renderIssues();renderOverlay()}};
new ResizeObserver(()=>{if(job){renderIssues();renderOverlay()}}).observe($('#image-wrap'));

$('#vision-model').addEventListener('change',()=>{$('#openrouter-note').hidden=!$('#vision-model').value.endsWith(':free')});

function comparisonHTML(flag){
 return `<div class="flag-comparison"><h3>실제 획 구성과 공식 배치</h3><table><thead><tr><th>위치</th><th>원본</th><th>읽은 괘</th><th>공식 기준</th><th>비교</th></tr></thead><tbody>${flag.trigrams.map(t=>{const [x,y,x1,y1]=t.rect,w=job.image.width,h=job.image.height;return `<tr class="comparison-${t.match===false?'mismatch':t.match===true?'match':'uncertain'}"><td>${esc(t.position)}</td><td><svg viewBox="${x*w} ${y*h} ${(x1-x)*w} ${(y1-y)*h}" width="72" height="72" role="img" aria-label="${esc(t.position)} 원본 확대"><image href="${BASE}/api/jobs/${job.id}/image" width="${w}" height="${h}" preserveAspectRatio="none"/></svg></td><td>${esc(t.observed||'판독 불가')}<br>${t.pattern?t.pattern.map(n=>n===1?'━━':'━ ━').join('<br>'):''}</td><td>${esc(t.expected)}</td><td><strong class="status-${t.match===true?'PASS':t.match===false?'FAIL':'REVIEW'}">${t.match===true?'일치':t.match===false?'불일치':'미확정'}</strong></td></tr>`}).join('')}</tbody></table><p class="micro"><a href="https://www.guri.go.kr/www/contents.do?key=461" target="_blank" rel="noopener noreferrer">공식 기준: 구리시 · 국기의 제작 ↗</a> · 4괘 획·위치만 비교. 퀴즈 오답의 의도 여부는 사람 확인.</p></div>`;
}
let checklistFilter='all';
function renderOriginalReport(){
 const report=job?.checklist_report,target=$('#checklist-report');target.hidden=!report;
 if(!report)return;
 $('#checklist-coverage').textContent=`원문 ${report.complete_count}/${report.total}개 분석 · 세부 ${report.assessed_steps}/${report.step_total}개`;
 $('#checklist-scope').textContent=`적용 규칙 ${report.version} · 이번 실행 범위 ${report.requested_steps}/${report.step_total}개${report.requested_steps<report.step_total?' · 나머지는 이전 결과를 포함합니다. 전체 재분석으로 모두 새로 평가할 수 있습니다.':''} · 분석 완료와 사람의 공개 승인은 별개입니다.`;
 const opened=new Set($$('#original-analysis-list > details[open]').map(e=>e.dataset.parent));
 const items=report.items.filter(p=>checklistFilter==='all'||checklistFilter==='attention'&&['FAIL','REVIEW','ERROR'].includes(p.status)||checklistFilter==='na'&&p.status==='NOT_APPLICABLE'||checklistFilter==='incomplete'&&!p.complete);
 $('#original-analysis-list').innerHTML=items.map(p=>{
  const first=['FAIL','ERROR','REVIEW','PASS','NOT_APPLICABLE','NOT_RUN'].map(status=>p.evaluations.find(g=>g.status===status)).find(Boolean);
  const detected=p.technical_evidence?.flags||[];
  const evidence=p.technical_evidence?.flags?.length?`<details class="support-evidence"><summary>H-04 보조 근거 · 괘 구조 측정 ${p.technical_evidence.flags.length}개 도안</summary><p>아래는 원문 판정을 뒷받침하는 부분 측정입니다. 퀴즈의 제작 의도와 공식 자료의 적용 범위는 위 분석 의견에서 확인하세요.</p>${p.technical_evidence.flags.map(f=>`<details><summary>${esc(f.label)} · ${f.status==='MATCH'?'측정 배치 일치':f.status==='MISMATCH'?'측정 배치 차이':'측정 미확정'}</summary>${comparisonHTML(f)}</details>`).join('')}</details>`:'';
  return `<details class="original-item" id="original-${p.id}" data-parent="${p.id}" ${opened.has(p.id)?'open':''}><summary><div class="original-title"><strong>${esc(p.id)} ${esc(p.title)}</strong><span class="status-${p.status}">${labels[p.status]}</span></div>${detected.length?`<p class="detected-summary ${detected.some(f=>f.status==='MISMATCH')?'status-FAIL':''}">태극기 ${detected.length}개 확인 · 괘 배치 불일치 ${detected.filter(f=>f.status==='MISMATCH').length}개 · 미리보기 번호에서 근거 확인</p>`:''}<p class="original-question">${esc(p.original)}</p><p class="original-verdict">${esc(first?.reason||'아직 원문 분석 결과가 없습니다.')}</p><small>세부 규칙 ${p.assessed_count}/${p.step_count}개 분석${!p.complete?' · 미완료':''} · 근거와 분석 의견 펼치기</small></summary><div class="original-body">${!p.complete?`<div class="notice">원문 판정 미완료: ${p.missing_rule_ids.map(esc).join(', ')}. 보조 측정만으로 원문 분석을 완료 처리하지 않습니다.</div>`:''}${p.evaluations.map(g=>`<article class="original-evaluation"><div><b class="status-${g.status}">${labels[g.status]}</b> <small>${g.rule_ids.map(esc).join(', ')}</small></div><dl><dt>관찰 근거</dt><dd>${esc(g.observation||(g.status==='NOT_APPLICABLE'?'관련 대상이 관찰되지 않았다는 분석 결과입니다.':'직접 관찰 근거 없음'))}</dd><dt>분석 의견</dt><dd>${esc(g.reason)}</dd><dt>확인·수정 사항</dt><dd>${esc(g.action||'추가 조치 없음')}</dd></dl><small>분석: ${esc(g.model)} · 기준자료: ${g.reference_ids.map(id=>esc(activeRun().reference_snapshot.find(r=>r.id===id)?.name||id)).join(', ')||'인용 자료 없음'}</small><div class="original-step-links">${g.finding_ids.map(id=>{const r=findings().find(r=>r.id===id);return `<button class="quiet" data-finding="${esc(id)}">${esc(r?.rule_id)} 상세·위치·검토 기록</button>`}).join('')}</div></article>`).join('')}${evidence}</div></details>`;
 }).join('')||'<p>해당하는 항목이 없습니다.</p>';
}
document.addEventListener('click',e=>{const f=e.target.closest('[data-checklist-filter]');if(f){checklistFilter=f.dataset.checklistFilter;$$('[data-checklist-filter]').forEach(x=>x.classList.toggle('active',x===f));renderOriginalReport();}const p=e.target.closest('[data-parent-analysis]');if(p){resultView('original');checklistFilter='all';$$('[data-checklist-filter]').forEach(x=>x.classList.toggle('active',x.dataset.checklistFilter==='all'));renderOriginalReport();const card=$('#original-'+p.dataset.parentAnalysis);if(card){card.open=true;card.scrollIntoView({behavior:'smooth',block:'start'})}}});

let rulesState=null,rulesDirty=false;
function rulePreview(){
 $('#rules-preview').innerHTML=$('#rules-markdown').value.split('\n').map(line=>{
 const match=line.match(/^(#{1,3}) (.*)$/);return match?`<h${match[1].length}>${esc(match[2])}</h${match[1].length}>`:line.trim()?`<p>${esc(line).replace(/\*\*(.+?)\*\*/g,'<strong>$1</strong>').replace(/`([^`]+)`/g,'<code>$1</code>')}</p>`:'';
 }).join('');
}
async function loadRuleEditor(){
 if(rulesDirty&&!confirm('저장하지 않은 편집 내용을 버리고 최신 규칙을 불러올까요?'))return;
 rulesState=await api('/admin/rules');$('#rules-authoring-guide').textContent=rulesState.authoring_guide;$('#rules-markdown').value=rulesState.markdown;$('#rules-markdown').scrollTop=0;rulesDirty=false;
 $('#rules-status').textContent='현재 버전 '+rulesState.version+' · 저장 후 새 검사에 적용';rulePreview();
 $('#rules-history').innerHTML=(rulesState.history||[]).map(r=>`<div class="audit-entry"><b>${esc(r.version)}</b> · ${new Date(r.created).toLocaleString('ko-KR')} · ${esc(r.actor)} <button class="quiet" data-rule-version="${r.seq}">이 버전을 편집기에 불러오기</button></div>`).join('')||'<p>아직 변경 이력이 없습니다. 최초 규칙을 표시합니다.</p>';
}
$('#rules-markdown').oninput=()=>{rulesDirty=true;$('#rules-status').textContent='저장하지 않은 변경 사항이 있습니다.'};
$('#rules-load').onclick=guard(loadRuleEditor);
$('#rules-file').onchange=guard(async e=>{const file=e.target.files[0];if(!file)return;if(file.size>600000)throw Error('Markdown 파일은 600KB 이하로 올려주세요.');$('#rules-markdown').value=await file.text();rulesDirty=true;rulePreview();$('#rules-status').textContent='파일을 불러왔습니다. 형식을 검사하고 저장하면 적용됩니다.';e.target.value=''});
$('#rules-download').onclick=guard(async()=>{if(!rulesState)await loadRuleEditor();const url=URL.createObjectURL(new Blob([$('#rules-markdown').value],{type:'text/markdown;charset=utf-8'}));const a=document.createElement('a');a.href=url;a.download='chekmi-rules-'+rulesState.version+'.md';a.click();setTimeout(()=>URL.revokeObjectURL(url),30000)});
async function validateRuleDraft(){
 if(!rulesState)throw Error('먼저 최신 규칙을 불러오세요.');
 let data;
 try{data=await post('/admin/rules/validate',{markdown:$('#rules-markdown').value,base_version:rulesState.version})}
 catch(error){$('#rules-status').textContent='저장되지 않음 · '+error.message;$('#rules-status').classList.add('status-FAIL');throw error}
 $('#rules-status').classList.remove('status-FAIL');rulePreview();
 $('#rules-status').textContent='형식 정상 · 변경 '+data.changed.length+'개: '+(data.changed.join(', ')||'없음')+(data.warnings?.length?' · 내용 확인: '+data.warnings.join(' / '):'');return data;
}
$('#rules-validate').onclick=guard(validateRuleDraft);
$('#rules-save').onclick=guard(async()=>{
 await validateRuleDraft();const button=$('#rules-save');button.disabled=true;
 try{const saved=await api('/admin/rules',{method:'PUT',body:JSON.stringify({markdown:$('#rules-markdown').value,base_version:rulesState.version})});rulesDirty=false;pack=saved.pack;await loadRuleEditor();await refreshConfig();toast('새 규칙 버전을 저장했습니다. 이후 시작하는 검사에 적용됩니다.');}
 finally{button.disabled=false}
});
document.addEventListener('click',guard(async e=>{const button=e.target.closest('[data-rule-version]');if(!button)return;if(rulesDirty&&!confirm('저장하지 않은 내용을 버리고 선택한 버전을 불러올까요?'))return;const version=await api('/admin/rules/versions/'+button.dataset.ruleVersion);$('#rules-markdown').value=version.markdown;rulesDirty=true;rulePreview();$('#rules-status').textContent=version.version+'을 불러왔습니다. 새 버전 저장을 눌러야 적용됩니다.'}));
window.addEventListener('beforeunload',e=>{if(rulesDirty){e.preventDefault();e.returnValue=''}});

function resultView(name){
 $$('.result-view').forEach(el=>el.classList.toggle('active',el.id===name+'-view'));
 $$('[data-result-view]').forEach(el=>el.classList.toggle('active',el.dataset.resultView===name));
 $('#finding-detail').classList.add('detail-empty');$('#results-scroll').scrollTop=0;
}
document.addEventListener('click',e=>{const button=e.target.closest('[data-result-view]');if(button)resultView(button.dataset.resultView)});

$('#choose-image').onclick=()=>$('#file').click();
const transmissionGrants=new Set();
function requestTransmission(reuse){
 const vision=$('#vision-model').value,analysis=$('#analysis-model').value;
 const key=JSON.stringify([job.id,reuse?'observation':vision,analysis]);
 if(transmissionGrants.has(key))return Promise.resolve(true);
 const dialog=$('#transmission-dialog');
 $('#transmission-context').textContent=reuse?`저장된 이미지 관찰 기록을 ${analysis} 모델에 전송해 분석합니다.`:`이 이미지를 ${vision} 모델에, 관찰 기록을 ${analysis} 모델에 전송합니다.`;
 $('#transmission-policy').hidden=reuse||!vision.endsWith(':free');
 return new Promise(resolve=>{
  function finish(accepted){dialog.close();dialog.oncancel=null;$('#allow-transmission').onclick=null;$('#cancel-transmission').onclick=null;if(accepted)transmissionGrants.add(key);resolve(accepted)}
  $('#allow-transmission').onclick=()=>finish(true);$('#cancel-transmission').onclick=()=>finish(false);
  dialog.oncancel=e=>{e.preventDefault();finish(false)};dialog.showModal();
 });
}

function ruleHandoff(){
 const draft=$('#rules-markdown').value;
 return rulesState.authoring_guide+'\n\n=== 현재 저장 형식과 전체 규칙 시작 ===\n'+rulesState.markdown+'\n=== 현재 규칙 끝 ===\n\n=== 변경 요청 / 변환할 초안 ===\n'+(draft!==rulesState.markdown?draft:'이 아래에 개선 요청 또는 새 규칙집을 붙여 주세요. 현재 규칙 전체를 유지하며 수정합니다.');
}
$('#rules-copy-guide').onclick=guard(async()=>{
 if(!rulesState)await loadRuleEditor();const text=ruleHandoff();
 try{await navigator.clipboard.writeText(text);toast('작성 안내·현재 규칙 전체·편집 중인 초안을 복사했습니다. 다른 AI에 붙여넣으세요.')}
 catch{const dialog=$('#rules-copy-dialog');$('#rules-copy-text').value=text;dialog.showModal();$('#rules-copy-text').focus();$('#rules-copy-text').select()}
});
$('#rules-copy-close').onclick=()=>$('#rules-copy-dialog').close();

function textQualityHTML(row){
 const objects=((activeRun()?.analysis_observation||activeRun()?.observation)?.objects||[]).filter(o=>row.evidence_ids?.includes(o.id)&&o.text_legibility&&o.text_legibility!=='NOT_TEXT'&&o.text_legibility!=='UNASSESSED');
 const names={CLEAR:'획·외형 정상',DEGRADED:'획 손상·뭉개짐 관찰',UNREADABLE:'문자 식별 어려움'};
 return objects.length?`<div class="text-quality-evidence"><b>문자 인식과 외형 품질</b>${objects.map(o=>`<p><strong>${esc(o.label)} · ${names[o.text_legibility]}</strong><br>읽은 내용: ${esc(o.text||'[판독불가]')}${o.transcription_inferred?' · 문맥 추정 포함':''}<br>외형 근거: ${esc(o.legibility_evidence||'별도 외형 근거 없음')}</p>`).join('')}</div>`:'';
}

function verificationHTML(row){
 const run=activeRun(),v=run?.verification,ids=row.evidence_ids||[];
 const results=(v?.results||[]).filter(r=>ids.includes(r.object_id)&&r.status==='COMPLETED');
 const deferred=(v?.deferred||[]).filter(r=>ids.includes(r.object_id));
 const states={NOT_REQUIRED:'추가 증빙 불필요',VERIFIED:'해당 범위 근거 확인',REQUIRED:'기준·증빙 필요',UNAVAILABLE:'비교 미확정'};
 const types={OCR_OMISSION:'OCR 전사 누락',OCR_UNCERTAIN:'문자 판독 미확정',OCR_RECOGNITION_ERROR:'OCR 인식 오류 후보',TYPO_CONFIRMED:'원본 오탈자',OCR_MISMATCH:'판독 결과 불일치',OCR_UNREADABLE:'판독 어려움',VISUAL_TEXT_DEFECT:'글자 외형 결함',SOURCE_MISMATCH:'정본 불일치',FACT_OR_STYLE_ISSUE:'사실·표현 확인'};
 const status=row.evidence_status?`<p>증빙: ${states[row.evidence_status]||esc(row.evidence_status)}${types[row.error_type]?' · '+types[row.error_type]:''}</p>`:'';
 const cards=results.map(r=>{
  const comparisons=(r.comparisons||[]).filter(c=>c.rule_ids.includes(row.rule_id));
  const [x,y,z,w]=r.crop_rect;
  const picture=$('#inspection-image'),height=1000*(picture.naturalHeight||job.image.height)/(picture.naturalWidth||job.image.width);
  const original=`<svg viewBox="${x*1000} ${y*height} ${(z-x)*1000} ${(w-y)*height}" role="img" aria-label="주변 포함 확대 원본"><image href="${esc(picture.src)}" width="1000" height="${height}"/></svg>`;
  return `<div class="recheck-card"><strong>확대 재검사 · ${esc(r.object_id)}${r.coverage==='COMPLETE'?' · 전체 확인':' · 부분 확인'}</strong><p>1차 전사: ${esc(r.first_text||'문자 없음')}<br>독립 재판독: ${esc(r.text||'문자 없음')}${r.transcription_disagreement?' · 판독 차이 있음':''}</p><p>${esc(r.legibility_evidence||r.description)}</p>${comparisons.map(c=>`<p><b>${esc(c.status)}</b> · ${esc(c.evidence)}</p><div class="verification-images"><figure>${original}<figcaption>확대 원본</figcaption></figure><figure><img loading="lazy" src="${BASE}/api/references/${esc(c.reference_id)}/image" alt="공식 비교 도안"><figcaption>${esc(run.reference_snapshot.find(ref=>ref.id===c.reference_id)?.name||c.reference_id)}</figcaption></figure></div>`).join('')}</div>`;
 }).join('');
 return status+ocrEvidenceHTML(row)+cards+deferred.map(r=>`<p class="location-warning">${esc(r.reason)}</p>`).join('')+(v?.reused_without_verification?'<p class="location-warning">이전 인식 기록에는 확대·직접 비교 기록이 없습니다. 새 그림+분석으로 확인하세요.</p>':'');
}

function ocrEvidenceHTML(row){
 const r=row.ocr_evidence;if(!r)return '';
 const v=r.vision,rect=r.crop_rect||r.rect,[x,y,z,b]=rect,picture=$('#inspection-image');
 const height=1000*(picture.naturalHeight||job.image.height)/(picture.naturalWidth||job.image.width);
 const original=`<svg viewBox="${x*1000} ${y*height} ${(z-x)*1000} ${(b-y)*height}" role="img" aria-label="문자 원본 확대"><image href="${esc(picture.src)}" width="1000" height="${height}"/></svg>`;
 return `<div class="recheck-card"><strong>독립 문자 판독 · 원본 획 검사</strong><div class="verification-images"><figure>${original}<figcaption>격자 없는 원본 · 손상 복원 없음</figcaption></figure></div><dl><dt>${esc(r.recognition_engine||'PaddleOCR')}</dt><dd>${esc(r.text||'[전사 없음]')} · 인식 신뢰도 ${Math.round((r.recognition_score||0)*100)}%</dd>${r.paddle_text!==undefined?`<dt>PaddleOCR 최초 전사</dt><dd>${esc(r.paddle_text||'[전사 없음]')}</dd>`:''}<dt>독립 이미지 판독</dt><dd>${esc(v?.literal_text||'[미검사]')}</dd><dt>글자 모양</dt><dd>${esc(v?.glyph_evidence||'획 품질을 확인하지 못했습니다.')}</dd><dt>철자 검토</dt><dd>${esc(v?.spelling_evidence||'교정 의견 없음')}${v?.suggested_text?' · 교정 후보: '+esc(v.suggested_text):''}</dd></dl><small>인식 신뢰도는 이미지 정상 확률이 아닙니다. 판독 불일치는 원본 오타와 구분합니다.</small></div>`;
}
