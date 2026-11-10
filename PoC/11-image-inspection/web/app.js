/* Image, SVG and pins share one transform. Pins counter-scale to stay legible. */
function zoomAt(view, scale, point, center) {
  const next = Math.max(.5, Math.min(8, scale));
  const ratio = next / view.scale;
  return {scale: next, x: view.x + (point.x - center.x) * (1 - ratio), y: view.y + (point.y - center.y) * (1 - ratio)};
}

class ImageViewport {
  constructor(stage, wrap, image) {
    this.stage = stage; this.wrap = wrap; this.image = image;
    this.view = {scale: 1, x: 0, y: 0}; this.ignoreClickUntil = 0;
    const controls = document.createElement('div'); controls.className = 'image-zoom-controls';
    controls.setAttribute('role', 'group'); controls.setAttribute('aria-label', '이미지 확대 축소');
    controls.innerHTML = '<button type="button" data-zoom="out" aria-label="이미지 축소" title="축소">−</button><button type="button" data-zoom="reset" aria-label="이미지 화면 맞춤" title="화면 맞춤">100%</button><button type="button" data-zoom="in" aria-label="이미지 확대" title="확대">+</button>';
    stage.append(controls); this.controls = controls;
    controls.addEventListener('click', event => {
      const action = event.target.closest('[data-zoom]')?.dataset.zoom;
      if (action === 'reset') this.reset();
      else if (action) this.zoom(this.view.scale * (action === 'in' ? 1.25 : .8));
    });
    stage.addEventListener('wheel', event => {
      if (!this.ready() || event.ctrlKey || event.metaKey || !event.deltaY) return;
      event.preventDefault();
      const delta = event.deltaY * (event.deltaMode === 1 ? 16 : event.deltaMode === 2 ? stage.clientHeight : 1);
      this.zoom(this.view.scale * Math.exp(-Math.max(-120, Math.min(120, delta)) * .002), {x: event.clientX, y: event.clientY});
    }, {passive: false});
    stage.addEventListener('pointerdown', event => {
      if (!this.ready() || this.view.scale <= 1 || event.button !== 0 || event.target.closest('button')) return;
      this.drag = {id: event.pointerId, x: event.clientX, y: event.clientY, start: {...this.view}, moved: false};
    });
    stage.addEventListener('pointermove', event => {
      const drag = this.drag; if (!drag || drag.id !== event.pointerId) return;
      const dx = event.clientX - drag.x, dy = event.clientY - drag.y;
      if (!drag.moved && Math.hypot(dx, dy) < 5) return;
      drag.moved = true; stage.setPointerCapture(event.pointerId);
      this.view = {...drag.start, x: drag.start.x + dx, y: drag.start.y + dy}; this.apply();
      event.preventDefault();
    });
    const stop = event => {
      if (!this.drag || this.drag.id !== event.pointerId) return;
      if (this.drag.moved) this.ignoreClickUntil = performance.now() + 250;
      this.drag = null;
      if (stage.hasPointerCapture(event.pointerId)) stage.releasePointerCapture(event.pointerId);
    };
    stage.addEventListener('pointerup', stop); stage.addEventListener('pointercancel', stop);
    stage.addEventListener('lostpointercapture', stop);
    stage.addEventListener('click', event => {
      if (performance.now() < this.ignoreClickUntil && !event.target.closest('.image-zoom-controls')) {event.preventDefault(); event.stopPropagation();}
    }, true);
    image.draggable = false;
    new ResizeObserver(() => this.apply()).observe(stage);
    this.apply();
  }
  ready() { return !this.image.hidden && this.image.naturalWidth > 0; }
  reset() { this.view = {scale: 1, x: 0, y: 0}; this.apply(); }
  zoom(scale, point) {
    if (!this.ready()) return;
    const box = this.wrap.getBoundingClientRect(), viewport = this.stage.getBoundingClientRect();
    const center = {x: box.left + box.width / 2, y: box.top + box.height / 2};
    this.view = zoomAt(this.view, scale, point || {x: viewport.left + viewport.width / 2, y: viewport.top + viewport.height / 2}, center);
    this.apply();
  }
  apply() {
    const pad = getComputedStyle(this.stage);
    const width = this.stage.clientWidth - parseFloat(pad.paddingLeft) - parseFloat(pad.paddingRight);
    const height = this.stage.clientHeight - parseFloat(pad.paddingTop) - parseFloat(pad.paddingBottom);
    const maxX = Math.max(0, (this.wrap.offsetWidth * this.view.scale - width) / 2);
    const maxY = Math.max(0, (this.wrap.offsetHeight * this.view.scale - height) / 2);
    this.view.x = Math.max(-maxX, Math.min(maxX, this.view.x));
    this.view.y = Math.max(-maxY, Math.min(maxY, this.view.y));
    this.wrap.style.transform = `translate(${this.view.x}px, ${this.view.y}px) scale(${this.view.scale})`;
    this.wrap.style.setProperty('--pin-scale', 1 / this.view.scale);
    this.stage.classList.toggle('image-can-pan', this.view.scale > 1);
    const reset = this.controls.querySelector('[data-zoom="reset"]');
    reset.textContent = Math.round(this.view.scale * 100) + '%';
    reset.setAttribute('aria-label', `현재 ${Math.round(this.view.scale * 100)}%, 누르면 화면 맞춤`);
    this.controls.querySelector('[data-zoom="out"]').disabled = !this.ready() || this.view.scale <= .5;
    this.controls.querySelector('[data-zoom="in"]').disabled = !this.ready() || this.view.scale >= 8;
  }
}

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
function requireAnalysisPermission(){
 if(config.role!=='admin')throw Error('분석 실행은 관리자만 가능합니다. 검토자는 기존 결과를 확인하고 검토 의견을 기록할 수 있습니다.');
}
function applyExecutionPermissions(){
 const allowed=config.role==='admin';
 document.body.classList.toggle('can-run-analysis',allowed);
 for(const id of ['vision-model','analysis-model','text-sensitivity'])$('#'+id).disabled=!allowed;
 $('#reviewer-permission-note').hidden=config.role!=='reviewer';
 $('#empty-state p').textContent=config.role==='reviewer'?'검수 이력에서 결과를 열어 검토해 주세요.':'이미지를 첨부한 후 그림 + 분석 실행을 눌러주세요.';
}
async function refreshConfig(){config=await api('/config');applyExecutionPermissions();$('#rules-nav').hidden=config.role!=='admin';if(config.role!=='admin'&&$('#rules-admin').classList.contains('active'))tab('workspace');$('#login-button').textContent=config.role?`${config.role==='admin'?'관리자':'검토자'} · 로그아웃`:'로그인';$('#key-status').textContent=`OpenAI ${config.openai_configured?'연결 설정됨':'키 미설정'} · Solar ${config.upstage_configured?'연결 설정됨':'키 미설정'} · OpenRouter ${config.openrouter_configured?'연결 설정됨':'키 미설정'} · 규칙 ${config.rule_pack_version}`;void refreshRemaining()}
let remainingLoading=false;
function renderRemaining(payload, fallback='잔여량 미확인'){
 const models=payload?.models||[{id:'gpt-5.4',label:'GPT 5.4'},{id:'gpt-5.4-mini',label:'GPT 5.4 mini'},{id:'openai-shared',label:'GPT 6.0·6.1'},{id:'solar-pro4',label:'Solar Pro 4'},{id:'openrouter-free',label:'Nemotron 3.5 Super VL'}];
 const rendered=new Map(models.map(m=>{
  if(m.status==='UNLIMITED')return [m.id,`<button type="button" class="model-quota" data-tab="usage" data-quota-model="${esc(m.id)}"><span class="quota-name">Solar 4</span><b>무제한</b><small>사용 ${Number((m.input_tokens||0)+(m.output_tokens||0)).toLocaleString()} 토큰</small><small>유료 단가 환산 $${Number(m.used||0).toFixed(4)} · 실제 청구액 아님</small><small>PoC7·10·11 사용량 기록</small></button>`];
  const known=m.remaining!=null&&m.limit!=null&&Number.isFinite(Number(m.remaining))&&Number.isFinite(Number(m.limit))&&Number(m.limit)>0;
  const left=known?Math.max(0,Number(m.remaining)):null,percent=known?Math.min(100,left/Number(m.limit)*100):null;
  const requests=m.unit==='requests',tokens=m.unit==='tokens';
  const value=known?(left===0?'소진':tokens?(left>=10000?(Math.floor(left/1000)/10).toLocaleString()+'만':left.toLocaleString()):requests?`${left.toLocaleString()}회`:`$${left.toFixed(2)}`):(m.display||fallback);
  const note=m.note||fallback;
  const expiry=m.expires_at?(m.id==='openai-shared'?' · 갱신 ':' · 기간 종료 ')+new Date(m.expires_at).toLocaleString('ko-KR',{timeZone:'Asia/Seoul'}):'';
  const title=known?`${m.label}: ${tokens?left.toLocaleString()+' 토큰':requests?left.toLocaleString()+'회':'$'+left.toFixed(3)} / ${tokens?Number(m.limit).toLocaleString()+' 토큰':requests?m.limit+'회':'$'+Number(m.limit).toFixed(2)} 남음. ${note}${expiry}`:`${m.label}: ${note}`;
  const shortName=({'gpt-5.4-mini':'5.4 mini','gpt-5.4':'5.4','openai-shared':'6계열','solar-pro4':'Solar 4','openrouter-free':'Nemotron','naver-ocr':'CLOVA'})[m.id]||m.label;
  const period=tokens||m.id==='openrouter-free'?'일':m.id==='solar-pro4'?'누적':['naver-ocr','openai-shared'].includes(m.id)?'월':'주기';
  return [m.id,`<button type="button" class="model-quota ${known&&percent<10?'is-low':''}" data-tab="usage" data-quota-model="${esc(m.id)}" title="${esc(title)}" aria-label="${esc(title)}"><span class="quota-name">${esc(shortName)}</span><b>${known?'('+period+') ':''}${esc(value)}</b><span class="quota-percent">${known?percent.toFixed(1)+'%':'—'}</span><span class="quota-meter ${known?'':'is-unknown'}" role="${known?'progressbar':'img'}" aria-label="${esc(m.label)} 잔여 예산${known?'':' 미확인'}" ${known?`aria-valuemin="0" aria-valuemax="100" aria-valuenow="${Math.floor(percent)}"`:''}><i style="width:${known?percent:0}%"></i></span><small>${known?(tokens?`일 ${Number(m.limit).toLocaleString()} 토큰 · 공용 · 09시 초기화`:requests?(m.id==='naver-ocr'?`월 ${m.limit}회 · 앱 한도`:m.scope==='POC7_SHARED_OPENROUTER_REQUESTS'?`PoC7 공용 · 공식 잔여 ${m.official_remaining}회`:`일 ${m.limit}회 · 계정 공용`):`${m.id==='solar-pro4'?'누적':'월'} $${Number(m.limit).toFixed(0)} · PoC7·10·11 공용`):'공용 예산 확인 필요'}</small>${m.expires_at?`<small class="quota-reset">${esc(new Date(m.expires_at).toLocaleString('ko-KR',{timeZone:'Asia/Seoul'}))} ${tokens?'초기화':m.id==='openai-shared'?'갱신':'기간 종료'}</small>`:m.id==='solar-pro4'?'<small class="quota-reset">누적 한도 · 자동 초기화 없음</small>':''}</button>`];
 }));
 const groups=[['OpenAI · 일일',['gpt-5.4-mini','gpt-5.4']],['공용 크레딧',['openai-shared','solar-pro4']],['기타 · 요청량',['openrouter-free','naver-ocr']]];
 $('#model-remaining').innerHTML=groups.map(([name,ids])=>`<section class="quota-compact-group"><h3>${esc(name)}</h3>${ids.map(id=>rendered.get(id)||'').join('')}</section>`).join('');
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
function reviewMarkerKind(row,run){
 const basis=row.review_basis;
 // Scope/identity/approval limitations take precedence over a model's category label.
 if(row.diagnostic_only||row.coverage_fallback||row.binding_uncertain||/^D-03-/.test(row.rule_id)||/^D-04-[de]$/.test(row.rule_id))return '';
 const objects=(run?.analysis_observation||run?.observation)?.objects||[];
 const related=objects.filter(o=>row.evidence_ids?.includes(o.id));
 const comparisons=[...(row.direct_comparisons||[]),...(run?.verification?.results||[]).filter(v=>row.evidence_ids?.includes(v.object_id)).flatMap(v=>(v.comparisons||[]).filter(c=>c.rule_ids?.includes(row.rule_id)))];
 if(comparisons.some(c=>c.status==='MISMATCH'&&c.evidence?.trim()))return 'observed';
 const handDetails=[...(row.hand_scope?.hands||[]),...related.flatMap(o=>o.hands||[])];
 if(/^D-02-[c-i]$/.test(row.rule_id)&&handDetails.some(h=>h.visible_structure==='ANOMALOUS'&&h.anomaly_evidence?.trim()))return 'observed';
 if(['OBSERVED_ANOMALY','CONTEXT_CONFLICT'].includes(basis)&&row.reason?.trim())return 'observed';
 if(row.decision_conflict||basis==='DOCUMENT_CHECK')return '';
 const glyph=row.glyph_audit_evidence,assessment=glyph?.assessment;
 if(assessment?.location_verified&&assessment?.issue&&(assessment.error_type==='VISUAL_TEXT_DEFECT'||glyph?.isolated_glyphs?.reading_conflicts?.length||glyph?.isolated_glyphs?.character_conflicts?.length||glyph?.retained_detector_conflict))return 'reading';
 if(row.independent_reading_conflicts?.some(c=>c.status==='UNRESOLVED'&&c.detector_text&&c.independent_text&&c.detector_text!==c.independent_text))return 'reading';
 if(['TYPO_CONFIRMED','VISUAL_TEXT_DEFECT'].includes(row.error_type)&&row.reason?.trim())return 'reading';
 // Not reading a small object, lacking a reference or awaiting approval is not a located anomaly.
 // Explicit old visual findings remain usable; bare uncertainty flags do not create pins.
 return (!basis||basis==='UNASSESSED')&&row.visual_issue&&row.reason?.trim()?'observed':'';
}
function isVisualReview(row,run){return !!reviewMarkerKind(row,run)}
function reviewDisplayLabel(row,run){
 const kind=reviewMarkerKind(row,run);
 if(row.binding_uncertain)return '문자·객체 위치 연결 미확정';
 if(/^D-03-/.test(row.rule_id)||/^D-04-[de]$/.test(row.rule_id))return '사용 동의·증빙 확인';
 if(kind)return ({observed:'관찰된 차이 확인',reading:'판독 한계 · 원본 확인',comparison:'기준 도안 비교 필요'})[kind];
 if(row.coverage_fallback)return '분석 미완료 · 추가 확인';
 if(row.decision_conflict)return '모델 판정 상충 · 추가 확인';
 if(/^D-02-[c-i]$/.test(row.rule_id)&&row.review_basis==='READING_LIMIT')return '손의 가림·확인 범위';
 if(row.review_basis==='REFERENCE_MISSING')return '기준자료·비교 미확정';
 if(row.review_basis==='READING_LIMIT'||['OCR_UNREADABLE','OCR_UNCERTAIN'].includes(row.error_type))return '판독 미확정 · 이상 근거 미확보';
 return row.document_review||['DOCUMENT_CHECK','NONE'].includes(row.review_basis)?'문서·맥락·승인 확인':'추가 검토';
}
function issueGroups(){
 const run=activeRun(),wrap=$('#image-wrap'),box=wrap.getBoundingClientRect(),w=wrap.clientWidth||box.width||500,h=wrap.clientHeight||box.height||600;
 const key=[run,run?.results,run?.reviews,run?.rule_pack,selected,$('#pass-toggle').checked,w,h];
 if(issueGroups.cache?.key.every((value,i)=>value===key[i]))return issueGroups.cache.rows;
 const groups=new Map(),objects=new Map(((run?.analysis_observation||run?.observation)?.objects||[]).map(o=>[o.id,o]));
 const structuralRows=findings().filter(r=>['H-04-h','H-04-i','H-04-m'].includes(r.rule_id)&&r.id&&!['NOT_RUN','ERROR','NOT_APPLICABLE'].includes(effective(r)));
 const structuralFlags=structuralRows.length?measuredFlags().filter(f=>f.status==='MISMATCH'||$('#pass-toggle').checked):[];
 for(const r of findings()){
  if(structuralFlags.some(f=>flagObjectRows(f,findings().filter(r=>r.id&&!['NOT_RUN','ERROR','NOT_APPLICABLE'].includes(effective(r))),run).includes(r)))continue;
  const status=effective(r);if(['NOT_APPLICABLE','NOT_RUN'].includes(status)||(status==='PASS'&&!$('#pass-toggle').checked&&r.id!==selected))continue;
  const visualReview=isVisualReview(r,run);
  const document=r.location_unresolved||!r.rects?.length||(status==='REVIEW'&&!visualReview)||(r.parent_id==='D-03'&&!visualReview);
  const actionable=status==='FAIL'||status==='REVIEW'&&visualReview;
  const ids=document?[actionable?'unlocated:'+(r.evidence_ids?.join('|')||r.id):'document:'+r.parent_id+':'+status]:(r.evidence_ids?.length&&activeRun()?.scope!=='CROP'?r.evidence_ids:['legacy:'+r.rects.map(a=>a.join(',')).sort().join('|')]);
  for(const id of ids){
   const object=objects.get(id),rects=object?(object.rects||object.cell_ids.map(cell=>{const y=Number(cell.slice(1,3))-1,x=Number(cell.slice(4,6))-1;return [x/12,y/12,(x+1)/12,(y+1)/12]})):r.rects;
   if(!groups.has(id))groups.set(id,{id,label:document?(actionable?(r.object_label||(r.evidence_ids||[]).map(e=>objects.get(e)?.label).filter(Boolean).join(' · ')||r.instance_id||r.rule_id)+' · 위치 확인 필요':'추가 확인 · '+(pack.parents.find(p=>p.id===r.parent_id)?.title||r.parent_id)):r.object_label||object?.label||r.instance_id,rows:[],rects:document?[]:rects.map(a=>[...a])});
   const g=groups.get(id);if(!g.rows.some(x=>x.id===r.id))g.rows.push(r);
   if(actionable)g.actionable=true;
   if(!document&&r.emblem_geometry?.rect)g.rects=[r.emblem_geometry.rect];
   if(!document&&r.location_evidence?.status==='VERIFIED_REGION'){g.groundedRects=[...new Map([...(g.groundedRects||[]),...r.location_evidence.rects].map(a=>[a.join(','),a])).values()];g.rects=g.groundedRects;}
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
 // Cluster nearby markers into one selectable group instead of shifting them away from evidence.
 let merged=true;while(merged){merged=false;outer:for(let i=0;i<rows.length;i++)for(let j=i+1;j<rows.length;j++){
  const a=rows[i],b=rows[j];if(!a.anchor||!b.anchor||a.technical||b.technical)continue;
  if(Math.max(Math.abs((a.anchor[0]-b.anchor[0])*w),Math.abs((a.anchor[1]-b.anchor[1])*h))<36&&locationComponents([...a.rects,...b.rects]).length===1){
   a.rows=[...new Map([...a.rows,...b.rows].map(r=>[r.id,r])).values()];a.rects.push(...b.rects);a.label='인접 객체 묶음';a.anchor=evidenceAnchor(a.rects);rows.splice(j,1);merged=true;break outer;
  }
 }}
 rows.sort((a,b)=>(a.anchor?.[1]??2)-(b.anchor?.[1]??2)||(a.anchor?.[0]??2)-(b.anchor?.[0]??2));
 let number=0;for(const g of rows){g.status=g.technical?(g.comparison.status==='MISMATCH'||g.rows.some(r=>effective(r)==='FAIL')?'FAIL':g.rows.some(r=>effective(r)==='REVIEW'&&isVisualReview(r,run))?'REVIEW':g.comparison.status==='MATCH'?'PASS':'REVIEW'):['FAIL','ERROR','REVIEW','PASS'].find(status=>g.rows.some(r=>effective(r)===status));g.number=(g.anchor||g.locationAmbiguous||g.status==='FAIL'||g.actionable)?++number:null;}
 // Uncertain locations stay in the result list, never over an unrelated image object.
 issueGroups.cache={key,rows};return rows;
}
function pinRows(){return issueGroups().filter(g=>g.anchor||g.calloutAnchor)}
function unmarkedReviewHTML(groups,run,statusOf=r=>r.status){
 const extra=groups.filter(g=>!g.number&&!g.anchor).map(g=>({...g,rows:g.rows.filter(r=>statusOf(r)==='REVIEW')})).filter(g=>g.rows.length);
 if(!extra.length)return '';
 const count=new Set(extra.flatMap(g=>g.rows.map(r=>r.id))).size;
 return `<summary><strong>번호 없는 검토 의견 ${count}건</strong><span>${extra.length}개 묶음 · 펼쳐서 확인</span></summary><p>판독·비교 미확정, 검사 미완료, 사용 동의·증빙 확인 의견입니다. 구체적인 이상 근거가 없어 그림 위 번호로 표시하지 않았습니다. 의견을 누르면 상세 근거와 검토 기록을 볼 수 있습니다.</p><div class="unmarked-review-list">${extra.map(g=>`<div class="unmarked-review-group"><h3>${esc(g.label)}</h3>${g.rows.map(r=>`<button class="unmarked-review-row" data-group="${esc(g.id)}" data-finding="${esc(r.id)}"><b>${esc(r.rule_id)} · ${esc(reviewDisplayLabel(r,run))}</b><span>${esc(r.reason)}</span></button>`).join('')}</div>`).join('')}</div>`;
}
// Hit testing uses saved evidence, independently of visible pins and status filters.
function imageAnalysisTargets(run,statusOf=r=>r.status){
 if(!run)return [];
 const rows=(run.results||[]).filter(r=>r.id&&!r.location_unresolved&&!['NOT_APPLICABLE','NOT_RUN','ERROR'].includes(statusOf(r)));
 const targets=[],assigned=new Set(),full=run.scope!=='CROP';
 for(const r of rows)if(r.location_evidence?.status==='VERIFIED_REGION'&&r.rects?.length){targets.push({id:'grounded:'+r.id,label:r.object_label||r.instance_id||r.rule_id,rects:r.rects,rows:[r]});assigned.add(r.id)}
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

function tokenModelName(model){
 const canonical=String(model||'알 수 없음').replace(/-\d{4}-\d{2}-\d{2}$/,'');
 return ({'gpt-5.4':'GPT-5.4','gpt-5.4-mini':'GPT-5.4 mini','gpt-6.1-sol':'GPT-6.1 Sol','gpt-6-astra':'GPT-6 Astra','solar-pro4':'Solar Pro 4','nvidia/nemotron-3.5-super-vl:free':'Nemotron 3.5 Super VL'})[canonical]||canonical;
}
function stageTokenUsage(run){
 const stages=[{id:'reading',label:'① 그림 읽기'},{id:'checking',label:'② 정밀 검사'},{id:'analysis',label:'③ 규칙 분석'},{id:'other',label:'기타 호출'}].map(s=>({...s,models:new Map()}));
 const workloads={'image-observation':0,'image-verification':1,'text-ocr':1,'text-ocr-recheck':1,'hand-location':1,'hand-topology':1,'text-shape':1,'text-glyph-isolated':1,'text-jamo-isolated':1,'text-pixel-confirm':1,'text-spelling-audit':1,'checklist-analysis':2};
 const row=(stage,model,unit='tokens')=>{
  const name=unit==='api_call'&&(!model||model==='naver-ocr')?'NAVER CLOVA OCR':tokenModelName(model),key=name+'|'+unit;
  if(!stages[stage].models.has(key))stages[stage].models.set(key,{model:name,unit,input:0,output:0,calls:0,unknown:0,reused:false});
  return stages[stage].models.get(key);
 };
 const calls=run?.calls||[],count=n=>Number.isFinite(n)&&n>=0;
 for(const call of calls){
  const r=row(call.unit==='api_call'?1:workloads[call.workload]??3,call.requested_model||call.model,call.unit==='api_call'?'api_call':'tokens');
  r.calls++;
  if(r.unit==='api_call')continue;
  const usage=call.usage||{};
  if(count(usage.input_tokens))r.input+=usage.input_tokens;
  if(count(usage.output_tokens))r.output+=usage.output_tokens;
  // Cached input and reasoning are subsets; never add them to the total again.
  if(call.usage_unknown||!count(usage.input_tokens)||!count(usage.output_tokens))r.unknown++;
 }
 const inherited=!!(run?.observation_reused_from||run?.reused_from||run?.local_revision);
 const reuse=(stage,model,workload)=>{if(model&&!calls.some(c=>c.workload===workload&&tokenModelName(c.requested_model||c.model)===tokenModelName(model)))row(stage,model).reused=true};
 if(inherited&&run?.observation)reuse(0,run.observation_model||run.options?.vision_model,'image-observation');
 if(inherited)for(const result of run.verification?.results||[])reuse(1,result.model||run.observation_model,'image-verification');
 if(inherited&&run.text_ocr?.vision_checked)reuse(1,run.text_ocr.model||run.observation_model,'text-ocr');
 if(inherited&&run.hand_audit?.calls)reuse(1,run.hand_audit.model,'hand-topology');
 if(inherited&&run.hand_audit?.locations)reuse(1,'gpt-5.4-mini','hand-location');
 if(inherited&&run.glyph_audit?.regions?.some(r=>r.assessment))reuse(1,run.glyph_audit.model,'text-shape');
 if(run?.pixel_text?.confirmation?.calls)reuse(1,run.pixel_text.confirmation.model||'gpt-5.4','text-pixel-confirm');
 if(run?.spelling_audit?.calls)reuse(1,run.spelling_audit.model||'gpt-5.4-mini','text-spelling-audit');
 if(run?.reused_from||run?.local_revision||run?.analysis_reused_from){
  for(const result of run.results||[])if(!['ERROR','NOT_RUN'].includes(result.status)&&result.model&&!result.model.startsWith('system/')&&!['none','mock-fixture'].includes(result.model))reuse(2,result.model,'checklist-analysis');
 }
 // NAVER reports request counts, not tokens. It is stored separately from LLM calls.
 const naver=run?.text_ocr?.naver;
 if(naver?.event_id&&!calls.some(c=>c.event_id===naver.event_id)){
  const r=row(1,'naver-ocr','api_call');if(inherited)r.reused=true;else r.calls++;
 }
 return stages.filter(s=>s.id!=='other'||s.models.size).map(s=>({...s,models:[...s.models.values()]}));
}
function stageTokensHTML(run){
 if(!run)return '';
 if(run.options?.mode==='mock')return '<div class="stage-token-heading"><strong>샘플 시연 · 실제 토큰 사용 없음</strong></div>';
 const stages=stageTokenUsage(run),rows=stages.flatMap(s=>s.models),total=rows.reduce((n,r)=>n+r.input+r.output,0),unknown=rows.reduce((n,r)=>n+r.unknown,0);
 const number=n=>n.toLocaleString('ko-KR'),finished=!!run.finished_at||run.phase==='DONE';
 const failedCrops=new Set((run.verification?.deferred||[]).filter(x=>/^자동 재검사 실패:|^재검사 비교 검증 실패:/.test(x.reason||'')).map(x=>x.object_id));
 const incomplete=[run.glyph_audit?.error,run.hand_audit?.error,failedCrops.size?`확대 확인 ${failedCrops.size}개 영역 응답 실패 · 정상 판정 아님`:null].filter(Boolean);
 return `<div class="stage-token-heading"><strong>단계별 · 모델별 토큰</strong><span>이번 검사 추가 사용 <b>${unknown?'확인된 ':''}${number(total)}</b> 토큰${unknown?' · 미확정 '+unknown+'회':''}</span></div>${finished&&incomplete.length?`<p class="review-display-note">추가 정밀 확인 미완료 · ${incomplete.map(esc).join(' / ')}</p>`:''}<div class="stage-token-list">${stages.map(stage=>`<div class="stage-token-row"><span class="stage-token-label">${esc(stage.label)}</span><div class="stage-token-models">${stage.models.map(r=>`<div class="stage-token-model"><b>${esc(r.model)}</b><span class="stage-token-amount">${r.reused&&!r.calls?'재사용 · 추가 0 '+(r.unit==='api_call'?'회':'토큰'):r.unit==='api_call'?'API '+r.calls+'회':`${r.unknown?'확인된 ':''}${number(r.input+r.output)} 토큰`}${r.unknown?' · 미확정 '+r.unknown+'회':''}</span>${r.calls&&r.unit!=='api_call'?`<small>입력 ${number(r.input)} · 출력 ${number(r.output)}${r.reused?' · 일부 결과 재사용':''}</small>`:''}</div>`).join('')||`<span class="stage-token-empty">${finished?'미실행':'대기 중'}</span>`}</div></div>`).join('')}</div>${!finished?'<small class="stage-token-note">응답이 완료된 호출부터 집계됩니다. 생성 중 토큰은 미확정입니다.</small>':''}`;
}
function textRoutingHTML(run){
 const routing=run?.text_routing;if(!routing)return '';
 const states={FRAGMENT_MATCH:'문구 일부 일치 · 전체 판독과 비교 보류',QUALITY_CONFLICT:'획 품질 확인 후보',AGREED:'전사 일치',DISAGREEMENT:'판독 불일치',UNREAD:'전사 없음',NO_SCENE_MATCH:'최초 관찰 누락 후보',LOW_CONFIDENCE:'낮은 인식 신뢰도',AMBIGUOUS_TARGET:'대상 연결 미확정',INVALID_LOCATION:'위치 미확정'};
 const deferred={OBSERVATION_REUSED:'저장 판독 재사용',EXISTING_OCR_PATH:'기존 OCR 경로 사용',DISABLED:'자동 재판독 끔',SHARED_CROP_CALL_LIMIT:'확대 호출 한도',REGION_LIMIT:'영역 한도',CALL_FAILED:'재판독 미완료'};
 const shapes={NOT_MEASURED:'획 측정 미완료',REGION_LIMIT:'획 측정 영역 한도',INVALID_LOCATION:'위치 미확정',UNSUPPORTED_ROTATION:'기울임 미지원',UNSUPPORTED_PERSPECTIVE:'원근 미지원',INSUFFICIENT_PIXELS_OR_CONTRAST:'픽셀·대비 부족',UNSUPPORTED_BACKGROUND:'복잡한 배경',UNSUPPORTED_TEXT:'획 비교 지원 범위 밖',INSUFFICIENT_EDGE_DETAIL:'획 대비 부족',SEGMENTATION_MISMATCH:'음절 분리 미확정',UNSUPPORTED_FONT_OR_GLYPH:'글꼴·획 대조 미지원',TEMPLATE_MATCH:'로컬 형태 일치',UNCERTAIN_TEMPLATE:'형태 대조 미확정',CONFLICT_CANDIDATE:'형태 차이 후보',BLUR_CANDIDATE:'가독성 결함 후보'};
 return `<details class="text-routing"><summary>문자 검사 대상 · ${routing.regions.length}영역 · 누락·미처리 사유 보기</summary><p>${esc(routing.note)} 로컬 형태 일치는 철자·획 정상의 최종 판정이 아닙니다.</p><p>${Object.entries(routing.counts).map(([k,n])=>`${esc(states[k]||'추가 확인')} ${n}`).join(' · ')}</p><div class="text-routing-rows">${routing.regions.map(r=>`<div><b>${esc(r.detector_text||'[전사 없음]')}</b><span>${esc(states[r.state]||'추가 확인')} · ${esc(r.action==='RECHECKED'?'원본 재판독 완료':r.deferred_reason?deferred[r.deferred_reason]||'보류':'검사 후보')} · ${esc(shapes[r.shape_status]||'획 측정 상태 확인')}</span></div>`).join('')}</div></details>`;
}
function artifactScreenHTML(run){
 const a=run?.artifact_screen;if(!a)return '';
 const names={LOCAL_BLUR_SIGNAL:'원본 획 번짐 신호',DETECTED_UNREAD:'탐지 후 전사 없음',READING_DISAGREEMENT:'독립 판독 차이',SHAPE_CONFLICT:'획 형태 후보 불일치',OBSERVED_HAND_ANOMALY:'손 구조 이상 관찰'};
 return `<details class="artifact-screen"><summary>로컬 이상 후보 · ${a.candidates?.length||0}곳 · 추가 API 0회</summary><p>${esc(a.note)}</p><p>${a.mode==='ROUTING'?'기존 확대 예산 안에서 후보 확인':'기록만 수행 · 추가 재판독 꺼짐'} · 로컬 ${esc(a.seconds??0)}초</p>${(a.candidates||[]).map(c=>`<p>${esc(c.source_id||c.object_ids?.join(', ')||c.candidate_id)} · ${(c.signals||[]).map(s=>esc(names[s]||s)).join(' / ')}</p>`).join('')}${a.diagnostics?.filter(d=>d.state!=='MEASURED').length?`<p>범위 제한·미측정 ${a.diagnostics.filter(d=>d.state!=='MEASURED').length}곳 · 정상 또는 결함 판정에 포함하지 않음</p>`:''}</details>`;
}
function qualityRecheckHTML(run){
 if(!run?.options?.quality_recheck)return '';
 const events=new Set((run.calls||[]).filter(c=>c.workload==='image-verification').map(c=>c.event_id).filter(Boolean));
 const attempted=[...(run.verification?.results||[]),...(run.verification?.attempt_results||[])].filter(r=>events.has(r.event_id));
 const labels=new Map((run.quality_recheck_plan?.entries||[]).map(e=>[e.object_id,e.label]));
 return `<details class="quality-recheck-report" open><summary>선택 영역 새 판독 결과</summary><p>전체 그림 관찰은 재사용했습니다. 미완료 영역은 정상으로 새로 판정한 것이 아닙니다.</p>${(run.options.recheck_object_ids||[]).map(id=>{
  const r=attempted.find(r=>r.object_id===id),reasons=(run.verification?.deferred||[]).filter(d=>d.object_id===id).map(d=>d.reason);
  return `<p><b>${esc(labels.get(id)||id)}</b> · ${r?(r.coverage==='COMPLETE'?'새 판독 완료':'새 판독 부분 확인'):'새 판독 미완료'}${reasons.length?`<br><small>${reasons.map(esc).join(' / ')}</small>`:''}${r?`<br>${esc(r.legibility_evidence||r.visual_concerns||r.description)}${(r.hands||[]).filter(h=>h.anomaly_evidence).map(h=>`<br>${esc(h.anomaly_evidence)}`).join('')}`:''}</p>`;
 }).join('')}</details>`;
}
function handGeometryHTML(audit){
 return (audit?.local_geometry||[]).map(g=>`<p><b>${esc(g.object_id)} · 로컬 손 도안 측정</b><br>외곽 돌출부 ${g.measurement.visible_protrusions}개 · ${g.accepted_concerns?.length?'형태 확인 필요':'추가 경고 없음 (정상 인증 아님)'}</p>`).join('');
}
function refinementReportHTML(run){
 const glyph=run?.glyph_audit,hand=run?.hand_audit;
 if(!glyph&&!hand)return '';
 const status={COMPLETED:'완료',PARTIAL:'일부 완료',RUNNING:'진행 중',UNAVAILABLE:'미완료',NOT_NEEDED:'대상 없음'};
 return `<details class="quality-recheck-report"><summary>자동 손·글자 정밀 확인</summary><p>그림부터 새로 검사할 때 실행합니다. 판독 일치나 가림만으로 정상·오류를 확정하지 않습니다.</p>${glyph?`<p><b>글자 획 · ${esc(status[glyph.status]||glyph.status)}</b> · ${glyph.regions?.length||0}영역${glyph.deferred_count?' · 범위 밖 '+glyph.deferred_count+'영역':''}</p>${(glyph.regions||[]).map(r=>`<p>OCR: ${esc(r.detector_text||'[전사 없음]')} → 독립 획 판독: ${esc(r.assessment?.literal_text||'[미완료]')}${r.isolated_glyphs?`<br>문맥 없는 음절 판독: ${esc(r.isolated_glyphs.literal_text)} · ${r.isolated_glyphs.agreed?'두 모델 일치':'미확정'}`:''}</p>`).join('')}`:''}${hand?`<p><b>손 연결 구조 · ${esc(status[hand.status]||hand.status)}</b> · ${hand.results?.length||0}객체${hand.deferred_ids?.length?' · 범위 밖 '+hand.deferred_ids.length+'객체':''}</p>${(hand.results||[]).map(r=>`<details><summary>${esc(r.object_id)} · 구체적 이상 소견 ${r.accepted_concerns?.length||0}건</summary><p>${esc(r.summary)}</p>${(r.traces||[]).map(t=>`<p><b>${esc(t.part)}</b> · ${esc(t.visible_path)}${t.obscured_by?' · 가림: '+esc(t.obscured_by):''}</p>`).join('')}${(r.accepted_concerns||[]).map(c=>`<p>${esc(c.evidence)}<br>${esc(c.alternative_explanation)}</p>`).join('')}</details>`).join('')}${handGeometryHTML(hand)}${hand.error?`<p>${esc(hand.error)}</p>`:''}`:''}</details>`;
}
function inspectionCoverage(run){
 if(!run)return {partial:false,items:[],failedCalls:0};
 const items=[],objects=new Map(((run.analysis_observation||run.observation)?.objects||[]).map(o=>[o.id,o.label]));
 const pending=run.verification?.deferred||[];
 if(pending.length)items.push({label:`확대·도안 확인 미완료 ${new Set(pending.map(d=>d.object_id)).size}곳`,reasons:pending.map(d=>`${objects.get(d.object_id)||d.object_id}: ${d.reason}`)});
 const glyph=run.glyph_audit;
 if(glyph&&(glyph.status==='PARTIAL'||glyph.status==='UNAVAILABLE'))items.push({label:`문자 정밀 확인 ${(glyph.regions||[]).filter(r=>r.assessment).length}/${glyph.candidate_count??glyph.regions?.length??0}곳 · 일부 미완료`,reasons:[glyph.error,glyph.deferred_count?`검사 범위 밖 ${glyph.deferred_count}곳`:''].filter(Boolean)});
 const hand=run.hand_audit;
 if(hand&&(hand.status==='UNAVAILABLE'||hand.deferred_ids?.length))items.push({label:'손 구조 확인 일부 미완료',reasons:[hand.error,...(hand.deferred_ids||[]).map(id=>`${objects.get(id)||id}: 정밀 확인 범위 밖`)].filter(Boolean)});
 const ocr=run.text_ocr;
 if(ocr&&(ocr.status==='UNAVAILABLE'||ocr.status==='PARTIAL'||ocr.vision_deferred||ocr.deferred_count))items.push({label:'독립 문자 확인 일부 미완료',reasons:[ocr.error,`확인 ${ocr.vision_checked??0}곳 · 미확인 ${ocr.vision_deferred??0}곳 · 범위 밖 ${ocr.deferred_count??0}곳`].filter(Boolean)});
 return {partial:items.length>0,items,failedCalls:(run.calls||[]).filter(c=>c.status==='FAILED').length,inheritedFailedCalls:run.local_revision?.inherited_failed_calls?.length||0};
}
function coverageSummaryHTML(run){
 const coverage=inspectionCoverage(run);if(!coverage.partial&&!coverage.failedCalls&&!coverage.inheritedFailedCalls)return '';
 return `<strong>${coverage.partial?'분석 종료 · 일부 정밀 확인 미완료':'실행 중 호출 실패 기록 있음'}</strong><p>${coverage.items.map(i=>esc(i.label)).join(' · ')}${coverage.failedCalls?` · 이번 실행 중 실패 호출 ${coverage.failedCalls}회`:''}${coverage.inheritedFailedCalls?` · 저장 검사의 실패 호출 기록 ${coverage.inheritedFailedCalls}회`:''}</p><details><summary>미완료 이유 보기</summary>${coverage.items.map(i=>`<p><b>${esc(i.label)}</b></p><ul>${i.reasons.map(r=>`<li>${esc(r)}</li>`).join('')}</ul>`).join('')}<p>미완료는 정상이나 오류 판정이 아닙니다. 이 안내를 열어도 추가 AI 호출은 발생하지 않습니다.</p></details>`;
}
function renderCoverage(running){
 let panel=$('#inspection-coverage');if(!panel){panel=document.createElement('section');panel.id='inspection-coverage';panel.className='inspection-coverage';panel.setAttribute('role','status');$('#progress-panel').before(panel)}
 const html=coverageSummaryHTML(activeRun());panel.hidden=running||!html;panel.innerHTML=panel.hidden?'':html;
}
function renderTokens(){
 const run=activeRun(),totals=new Map();
 const summary=$('#stage-tokens'),html=stageTokensHTML(run);summary.hidden=!run;if(summary.innerHTML!==html)summary.innerHTML=html;
 for(const call of run?.calls||[]){const model=call.model||'알 수 없음',r=totals.get(model)||{input:0,output:0,calls:0,unknown:0,cached:0,cachedKnown:false,reasoning:0,reasoningKnown:false,unit:call.unit};r.input+=call.usage?.input_tokens||0;r.output+=call.usage?.output_tokens||0;r.calls++;if(Number.isFinite(call.usage?.cached_input_tokens)){r.cached+=call.usage.cached_input_tokens;r.cachedKnown=true}if(Number.isFinite(call.usage?.reasoning_tokens)){r.reasoning+=call.usage.reasoning_tokens;r.reasoningKnown=true}if(call.usage_unknown)r.unknown++;totals.set(model,r)}
 $('#run-tokens').innerHTML=run?`<strong>이번 검사 모델별 사용량</strong>${run.observation_reused_from?`<span class="badge">${run.options.recheck_object_ids?.length?'전체 이미지 관찰 재사용 · 선택 영역 새로 판독':'전체 이미지 읽기 재사용 · 추가 호출은 아래 사용량 참고'}</span>`:''}<div class="token-rows">${[...totals].map(([m,r])=>`<span><b>${esc(m)}</b> ${r.unit==='api_call'?`API ${r.calls}회`:`입력 ${r.input.toLocaleString()} · 출력 ${r.output.toLocaleString()} · 합계 ${(r.input+r.output).toLocaleString()} 토큰 / ${r.calls}회`}${r.cachedKnown?' · 캐시 입력 '+r.cached.toLocaleString():''}${r.reasoningKnown?' · 출력 중 추론 '+r.reasoning.toLocaleString():''}${r.unknown?' · 미확정 '+r.unknown+'회':''}</span>`).join('')||'<span>아직 완료된 API 호출이 없습니다.</span>'}</div><small>호출 응답을 받은 뒤 갱신됩니다. 생성 중 토큰은 공급자 응답 전까지 미확정입니다.</small>`:'';
 if(run?.local_revision)$('#run-tokens').innerHTML+=`<p>${esc(run.local_revision.note)}</p>`;
 $('#run-tokens').innerHTML+=textRoutingHTML(run);
 $('#run-tokens').innerHTML+=artifactScreenHTML(run);
 $('#run-tokens').innerHTML+=qualityRecheckHTML(run)+refinementReportHTML(run);
 if(run?.evidence_revision)$('#run-tokens').innerHTML+=`<p>${esc(run.evidence_revision.note)}</p>`;
 const observation=run?.observation;
 const cv=run?.text_coverage,v=run?.verification;
 if(cv)$('#run-tokens').innerHTML+=`<p>탐지 문자 ${cv.detected_text_regions} · 전사 ${cv.transcribed_regions} · 판독 어려움 ${cv.unreadable_regions} · 재검사 ${cv.rechecked_text_regions} · 판독 차이 ${cv.ocr_disagreement_regions}</p><small>${esc(cv.note)}</small>`;
 if(cv?.roles)$('#run-tokens').innerHTML+=`<p>문구별 확대 확인: ${Object.values(cv.roles).filter(r=>r.detected).map(r=>`${esc(r.label)} ${r.rechecked}/${r.detected}`).join(' · ')} (확인/탐지)</p>`;
 if(run?.source_copy)$('#run-tokens').innerHTML+=`<p>승인 원고 대조 ${run.source_copy.results.length}곳 · 대상 미확정 ${run.source_copy.unresolved.length}건</p><small>${esc(run.source_copy.note)}</small>`;
 const px=run?.pixel_text;if(px)$('#run-tokens').innerHTML+=`<p>원본 글자 획 대조 · ${px.status==='COMPLETED'?'완료':'미완료'} · ${px.processed_count??0}/${px.candidate_count??0} 영역 · 로컬 처리 ${px.seconds??0}초${px.confirmation?.calls?' · GPT-5.4 획 확인 '+((run.calls||[]).some(c=>c.workload==='text-pixel-confirm')?'이번 검사 1회':'저장 근거 재사용'):''}</p><small>${esc(px.error||'형태 비교는 철자·사실관계 검사와 별개이며 지원되지 않는 글꼴은 정상으로 확정하지 않습니다.')}</small>`;
 const sa=run?.spelling_audit;if(sa)$('#run-tokens').innerHTML+=`<p>독립 철자 검사 · GPT-5.4 mini · ${sa.status==='COMPLETED'?'완료':sa.status==='NOT_NEEDED'?'독립 판독 일치 문구 없음':'미완료'} · ${sa.tasks?.length||0}개 문구${sa.calls?((run.calls||[]).some(c=>c.workload==='text-spelling-audit')?' · 이번 검사 1회':' · 저장 결과 재사용'):''}</p><small>${esc(sa.error||'원본 글자 품질과 철자·띄어쓰기를 구분하여 검사합니다.')}</small>`;
 const pc=run?.precheck_guidance;if(pc?.items?.length)$('#run-tokens').innerHTML+=`<p>사전점검 참고자료 · ${pc.items.filter(i=>i.routing==='RELATED_TARGET').length}/${pc.items.length}개 주제 관련 대상 연결 · 추가 API 0회</p><small>지침 연결 건수이며 210개 개별 검사 완료율이 아닙니다.${pc.mapping_changes?.length?' 규칙 변경으로 재검토할 매핑 '+pc.mapping_changes.length+'개':''}</small>`;
 const tx=run?.text_ocr;
 if(tx)$('#run-tokens').innerHTML+=`<p>독립 한국어 OCR · ${tx.status==='COMPLETED'?'완료':tx.status==='PARTIAL'?'일부 미확정':tx.status==='RUNNING'?'검사 중':'미완료'} · 문자 후보 ${tx.candidate_count??0} · 원본 획 검사 ${tx.vision_checked??0} · 미검사 ${(tx.vision_deferred??0)+(tx.deferred_count??0)}</p><small>${esc(tx.error||tx.note)}${tx.naver?' · NAVER: '+esc(tx.naver.note||tx.naver.status):''}</small>`;
 if(v?.deferred?.length)$('#run-tokens').innerHTML+=`<p>자동 재검사 미확정 ${v.deferred.length}개 · 상세에서 이유와 선택 재검사를 확인하세요.</p>`;
 $('#observation-summary').hidden=!observation;
 if(observation)$('#observation-summary').innerHTML=`<summary>저장된 이미지 인식 · ${esc(run.observation_model||run.options.vision_model)} · ${observation.objects.length}개 객체</summary><p>${esc(observation.summary)}</p><p>${esc(observation.context)}</p><p>${esc(observation.limitations)}</p>${observation.location_warnings?.length?`<p>위치 정보 ${observation.location_warnings.length}개 객체 확인 필요: 범위를 벗어난 셀만 제외하고 관찰 내용은 분석에 사용했습니다.</p>`:''}`;
}
function reusableObservation(run){return run?.options?.mode==='live'&&run.scope!=='CROP'&&(Array.isArray(run.observation?.objects)||(run.results||[]).some(r=>!['ERROR','NOT_RUN','NOT_APPLICABLE'].includes(r.status)&&r.observation&&!['none','mock-fixture'].includes(r.model)))}
function inspectionFailure(run){
 if(!run)return null;
 const errors=(run.analysis||[]).filter(x=>x.error);
 const failed=[...(run.calls||[])].reverse().find(c=>c.status==='FAILED');
 if(!errors.length&&!run.stopped_reason)return null;
 const phase=run.failed_phase||errors.at(-1)?.phase||(!run.observation&&failed?.workload==='image-observation'?'READING':'ANALYZING');
 const reading=phase==='READING',workloads=({READING:['image-observation'],VERIFYING:['image-verification','hand-location','hand-topology'],TEXT_OCR:['text-ocr','text-ocr-recheck'],GLYPH_AUDIT:['text-shape','text-glyph-isolated','text-jamo-isolated'],ANALYZING:['checklist-analysis']})[phase]||[];
 const failedHere=[...(run.calls||[])].reverse().find(c=>c.status==='FAILED'&&workloads.includes(c.workload));
 return {reading,model:failedHere?.model||(reading?run.options.vision_model:errors.at(-1)?.model)||run.options.analysis_model,
  stage:({READING:'그림 읽기',VERIFYING:'확대 판독',TEXT_OCR:'문자 품질 검사',GLYPH_AUDIT:'독립 문자 획 검사',ANALYZING:'규칙 분석'})[phase]||'검사',
  reason:run.stopped_reason||errors.map(x=>x.error).join(' / ')};
}
function renderFailure(running){
 let banner=$('#inspection-failure');
 if(!banner){banner=document.createElement('section');banner.id='inspection-failure';banner.className='inspection-failure';banner.setAttribute('role','alert');$('#progress-panel').before(banner)}
 const run=activeRun(),failure=inspectionFailure(run);banner.hidden=running||!failure;
 if(banner.hidden){banner.replaceChildren();return}
 const previous=[...job.runs].reverse().find(r=>r.id!==run.id&&reusableObservation(r))||job.previous_reusable_run;
 banner.innerHTML=`<strong>${esc(failure.stage)} 실패 · ${esc(failure.model||'')}</strong><p>${failure.reading?'이미지 판독 결과를 받지 못해 분석 모델은 실행되지 않았습니다. 발견 0건이나 정상 판정이 아닙니다.':'검사가 끝나지 않았습니다. 완료된 결과만 표시하며, 미완료 항목은 정상 판정이 아닙니다.'}</p><p class="micro">${esc(failure.reason)}</p><div class="row"><button class="secondary" id="retry-failed-inspection">같은 모델로 그림 + 분석 재시도</button>${previous?`<button class="quiet" data-source-run="${esc(previous.id)}">이전 ${esc(previous.observation_model||previous.options.vision_model)} 판독으로 재분석</button>`:''}</div>${previous?`<p class="micro">이전 판독: ${esc(new Date(previous.created_at).toLocaleString('ko-KR'))} · ${previous.observation?.objects?previous.observation.objects.length+'개 관찰':'이전 관찰 기록'}. 이전 기록을 재사용하며, 이번에 선택한 모델로 이미지를 새로 읽지 않습니다.</p>`:''}`;
 $('#retry-failed-inspection').onclick=guard(async()=>{$('#vision-model').value=run.options.vision_model;$('#analysis-model').value=run.options.analysis_model;$('#text-sensitivity').value=run.options.text_sensitivity||'strict';await startRun([],null,true)});
}
function runModelSummary(run){
 if(!run)return '';
 const names={'gpt-5.4':'GPT-5.4','gpt-5.4-mini':'GPT-5.4 mini','gpt-6.1-sol':'GPT-6.1 Sol','gpt-6-astra':'GPT-6 Astra','solar-pro4':'Solar Pro 4','nvidia/nemotron-3.5-super-vl:free':'Nemotron 3.5 Super VL'};
 const label=m=>names[m]||m||'확인 불가';
 if(run.options?.mode==='mock')return '샘플 시연 · 실제 모델 호출 없음';
 const calls=run.calls||[],read=run.observation_model||calls.find(c=>c.workload==='image-observation'&&c.status!=='FAILED')?.model;
 const analyses=[...new Set((run.results||[]).filter(r=>!['ERROR','NOT_RUN'].includes(r.status)&&r.model&&!r.model.startsWith('system/')).map(r=>r.model))];
 if(!analyses.length)for(const c of calls)if(c.workload==='checklist-analysis'&&c.status!=='FAILED'&&!analyses.includes(c.model))analyses.push(c.model);
 const local=!!run.local_revision&&!calls.length;
 return `그림 읽기: ${read?label(read)+(run.observation_reused_from?' (재사용)':''):'미완료'} · 분석: ${analyses.length?analyses.map(label).join(', ')+(local?' (재사용)':''):'미실행'}${local?(run.local_revision.method==='baseline-retained'?' · 이전 판정 유지(API 0회)':run.local_revision.method==='evidence-reconcile-v1'?' · 근거·위치 정리(API 0회)':run.local_revision.method==='review-evidence-v1'?' · 근거·표출 정리(API 0회)':run.local_revision.method==='text-location-v1'?' · 문자 위치 확인: 로컬 계산(API 0회)':' · 문양 구성 비교: 로컬 계산(API 0회)'):''}${run.spelling_audit?.calls?' · 철자 확인: GPT-5.4 mini'+(calls.some(c=>c.workload==='text-spelling-audit')?'':' (재사용)'):''}${run.pixel_text?.confirmation?.calls?' · 문자 획 확인: GPT-5.4'+(calls.some(c=>c.workload==='text-pixel-confirm')?'':' (재사용)'):''}${run.glyph_audit?' · 별도 획 검사: '+label(run.glyph_audit.model)+(run.glyph_audit.status==='COMPLETED'?'':run.glyph_audit.status==='UNAVAILABLE'?' (미실행)':' (일부 완료)'):''}`;
}
function renderJob(){
 $('#work-area').hidden=false;$('#empty-state').hidden=true;$('#job-title').textContent=job.metadata.title;$('#demo-badge').hidden=activeRun()?.options.mode!=='mock';$('#preview-empty').hidden=true;$('#drop-zone').hidden=true;$('.image-stage').hidden=false;$('#inspection-image').hidden=false;$('#image-click-hint').hidden=!activeRun();
 const running=['RUNNING','QUEUED'].includes(job.state);const run=activeRun();
 let models=$('#job-models');if(!models){models=document.createElement('span');models.id='job-models';models.className='micro';$('#job-state').after(models)}
 models.textContent=running?'':runModelSummary(run);models.hidden=running||!run;
 $('#job-state').textContent=({READY:'검사 준비',RUNNING:'분석 중',QUEUED:'대기 중',COMPLETED:'검사 종료',COMPLETED_WITH_ERRORS:'오류 확인 필요',INTERRUPTED:'중단됨'})[job.state]||job.state;
 $('#run').disabled=running||submitting;$('#text-sensitivity').disabled=running||config.role!=='admin';$('#file').disabled=running;$('#rerun').disabled=running;$('#reanalyze').disabled=running||!reusableObservation(run);$('#quality-recheck').disabled=running||!reusableObservation(run)||config.role!=='admin';$('#progress-panel').hidden=!running;$('#scanner').hidden=!running;
 if(run){$('#scanner span').textContent=run.phase==='STRUCTURE'?'원본 획 구조 비교 중':run.phase==='GLYPH_AUDIT'?'기존 판독과 별도로 원본 문자 획 검사 중':run.phase==='TEXT_OCR'?'문자 탐지 · 독립 OCR · 원본 획 비교 중':run.phase==='VERIFYING'?'확대 판독 · 공식 도안 비교 중':run.phase==='ANALYZING'?'저장된 관찰로 규칙 분석 중':'이미지 읽는 중';const failure=inspectionFailure(run);$('#notice').textContent=failure?failure.stage+' 중 오류가 발생했습니다: '+failure.reason:'자동 검수는 최종 공개 승인이 아닙니다. 오류 의심·검토 필요 항목은 담당자가 근거를 확인하세요.';$('#progress-text').textContent=run.phase==='READING'?(run.reading_retry?'1 / 3 · 공급자 오류 후 그림 읽기 1회 재시도 중':'1 / 3 · 전체 이미지 관찰 중'):run.phase==='GLYPH_AUDIT'?'2 / 3 · 독립 문자 획 검사 '+(run.glyph_audit?.regions?.filter(r=>r.assessment).length||0)+' / '+(run.glyph_audit?.regions?.length||0):run.phase==='TEXT_OCR'?'2 / 3 · 문자 탐지·원본 획 독립 검사':run.phase==='VERIFYING'?'2 / 3 · 필요한 영역 묶음 재검사':`3 / 3 · 저장된 관찰로 규칙 분석 ${run.progress} / ${run.total}`;
 $('#progress-bar').style.width=(run.total?run.progress/run.total*100:0)+'%';$('#elapsed').textContent=`${running?Math.max(0,Math.floor((Date.now()-new Date(run.created_at).getTime())/1000)):run.elapsed_seconds||0}초 · API ${run.calls.length}회`;
 if(run.reused_from)$('#job-state').textContent='동일 조건 결과 재사용 · API 0회';if(run.local_revision)$('#job-state').textContent=run.local_revision.method==='baseline-retained'?'실험 검증 후 이전 판정 유지':run.local_revision.kind==='user-feedback'?'사용자 지적 반영 · 자동 검출과 별도':'기존 검사 결과 · 누락 의견 보완 · API 0회';if(run.evidence_revision)$('#job-state').textContent='추가 독립 검증 반영 · 기존 규칙 분석 유지';if(!running&&inspectionCoverage(run).partial)$('#job-state').textContent='분석 종료 · 일부 확인 미완료';}
 const imageURL=BASE+`/api/jobs/${job.id}/image`;if($('#inspection-image').getAttribute('src')!==imageURL)$('#inspection-image').src=imageURL;
 renderFailure(running);renderCoverage(running);renderIssues();renderChecklist();renderOverlay();renderDetail();renderTokens();renderOriginalReport();
 if(running&&!timer)timer=setTimeout(poll,1700);
}
async function poll(){timer=null;if(!job)return;try{job=await api(`/jobs/${job.id}?view=latest`);renderJob();if(!['RUNNING','QUEUED'].includes(job.state))void refreshRemaining()}catch(e){toast(e.message);timer=setTimeout(poll,5000)}}
function renderIssues(){
 const groups=issueGroups(),unlocated=groups.filter(g=>g.number&&!g.anchor);
 const extra=$('#unmarked-reviews'),extraHTML=unmarkedReviewHTML(groups,activeRun(),effective);extra.hidden=!extraHTML;if(extra.innerHTML!==extraHTML)extra.innerHTML=extraHTML;
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
function findingCells(row){
 if(row.location_unresolved)return [];
 if(row.crop_id||row.location_evidence?.status!=='VERIFIED_REGION')return row.cell_ids||[];
 const cells=new Set();
 for(const [a,b,c,d] of row.location_evidence.rects||[])for(let y=Math.max(0,Math.floor(b*12));y<Math.min(12,Math.ceil(d*12));y++)for(let x=Math.max(0,Math.floor(a*12));x<Math.min(12,Math.ceil(c*12));x++)cells.add(`R${String(y+1).padStart(2,'0')}C${String(x+1).padStart(2,'0')}`);
 return [...cells].sort();
}
function precheckItem(ref){try{const p=JSON.parse(ref.content);return p.schema==='chekmi-precheck-item-v1'?p:null}catch{return null}}
function precheckReferenceHTML(ref){
 const p=precheckItem(ref);if(!p)return `<div class="card"><h2>${esc(ref.name)}</h2><p>참고자료 형식 확인 필요</p></div>`;
 return `<div class="card reference-card"><div class="panel-title"><h2>${esc(ref.name)}</h2><span class="badge">${esc(ref.status)} · 내부 검수 참고</span></div><p>PDF ${p.source_page}쪽 · 10개 요령 · ${esc(ref.parent_ids.join(', '))} · ${esc(ref.version)}</p><p>${esc(p.description)}</p><p class="micro">${esc(p.limitations)}</p>${ref.document_file?`<a href="${BASE}/api/references/${encodeURIComponent(ref.id)}/document#page=${p.source_page}" target="_blank" rel="noopener noreferrer">원문 PDF ${p.source_page}쪽 보기 ↗</a>`:''}<details><summary>검수 요령 10개와 연결 규칙</summary>${p.tips.map(t=>`<div class="audit-entry"><strong>${esc(t.id)} · ${esc(t.title)}</strong><p>${esc(t.action)}</p><small>${esc(t.rule_ids.join(', '))} · ${t.execution_scope==='HUMAN_OR_OTHER_MEDIA'?'사람/다른 매체 확인 포함':'이미지·증빙 구분 확인'}</small></div>`).join('')}</details>${ref.image_file?`<details><summary>원문 사례 사진·설명 보기 (공식 정상 도안과 구분)</summary><p class="micro">기사 사례는 별도 사실 확인이 필요합니다. 도안·권리·현재 정책의 확정 근거가 아닙니다.${p.cases.some(c=>c.status==='QUARANTINED_FUTURE_EVENT')?' 이 페이지의 미래 조치일 사례는 판단 근거에서 제외했습니다.':''}</p><img loading="lazy" src="${BASE}/api/references/${encodeURIComponent(ref.id)}/image" alt="내부 참고자료 원문 ${p.source_page}쪽의 사례 사진·검수 요령"></details>`:''}<p class="micro">승인: ${esc(ref.approved_by||'승인 전')} · 원문 SHA-256 ${esc(p.source_sha256.slice(0,16))}…</p></div>`;
}
function precheckEvidenceHTML(row,run){
 return (row.precheck_references||[]).map(link=>{
  const ref=run.reference_snapshot.find(r=>r.id===link.reference_id),p=ref&&precheckItem(ref);if(!p)return '';
  const base=`${BASE}/api/jobs/${encodeURIComponent(job.id)}/runs/${encodeURIComponent(run.id)}/references/${encodeURIComponent(ref.id)}`;
  return `<details class="recheck-card"><summary>사전점검 참고 · ${esc(p.title)} · PDF ${p.source_page}쪽</summary><p class="micro">${esc(ref.version)} · 내부 참고 지침 · 원본 도안/증빙 대조는 별도</p>${p.tips.filter(t=>link.tip_ids.includes(t.id)).map(t=>`<p><strong>${esc(t.id)} · ${esc(t.title)}</strong><br>${esc(t.action)}</p>`).join('')}<p class="micro">${esc(p.limitations)}</p>${ref.document_file?`<a href="${base}/document#page=${p.source_page}" target="_blank" rel="noopener noreferrer">이 검사에 연결된 원문 보기 ↗</a>`:''}${ref.image_file?`<details><summary>사례 사진·설명 확인</summary><p class="micro">정상 비교 도안이 아닙니다. 사례 사실관계는 별도 확인이 필요합니다.${p.cases.some(c=>c.status==='QUARANTINED_FUTURE_EVENT')?' 미래 조치일 사례는 실행 근거에서 제외했습니다.':''}</p><img loading="lazy" style="max-width:100%;height:auto" src="${base}/image" alt="참고자료 ${p.source_page}쪽 사례 사진"></details>`:''}</details>`;
 }).join('');
}

function readingConflictHTML(row){
 return (row.independent_reading_conflicts||[]).map(c=>`<div class="recheck-card"><strong>${c.status==='TARGET_UNRESOLVED'?'위치 연결 미확정 · 이전 비교 기록':'같은 위치의 독립 판독 비교'}</strong><p>OCR: ${esc(c.detector_text)}<br>그림 판독: ${esc(c.independent_text)}</p><p>${c.status==='TARGET_UNRESOLVED'?'서로 다른 객체의 문구가 연결됐을 가능성이 있어 이 비교는 오탈자 근거로 사용하지 않습니다. 이전 판독은 기록으로 보존합니다.':'오탈자인지 OCR 오인식인지 아직 확정되지 않았습니다. 원본 음절을 확인하세요.'}</p></div>`).join('');
}
function sourceChecksHTML(row){
 let html='';const name=row.official_term_check,geometry=row.symbol_geometry;
 if(row.source_copy_check){const c=row.source_copy_check;html+=`<div class="recheck-card"><strong>승인 원고 글자별 대조</strong><p>판독: ${esc(c.literal||'[판독 불가]')}<br>원고: ${esc(c.expected)}</p><table><thead><tr><th>판독 글자</th><th>원고 글자</th></tr></thead><tbody>${c.differences.map(d=>`<tr><td>${esc(d.observed.replace(/ /g,'␠')||'∅')}</td><td>${esc(d.expected.replace(/ /g,'␠')||'∅')}</td></tr>`).join('')}</tbody></table><small>␠ 공백 · ∅ 글자 없음 · ${c.confirmed?'독립 판독 일치':'판독 미확정'} · 원고 일치와 획 품질은 별개입니다.</small></div>`;}
 if(row.precheck_references?.length)html+=precheckEvidenceHTML(row,activeRun());
 if(row.spelling_audit_evidence){const a=row.spelling_audit_evidence;html+=`<div class="recheck-card"><strong>독립 철자 검사 · GPT-5.4 mini</strong><p>확인된 원문: ${esc(a.literal)}</p>${a.correction?`<p>수정 후보: ${esc(a.correction)}</p>`:''}<p>${esc(a.reason)}</p><small>${a.source?.source==='confirmed-source-glyphs'?'원본 글자 획을 독립 비교해 확인한 문구를 검사했습니다.':'원본 관찰과 OCR이 일치한 문구를 검사했습니다.'} 철자 판단은 원본 획 품질과 별개입니다.</small></div>`;}
 if(row.pixel_text_evidence){const p=row.pixel_text_evidence,h=1000*job.image.height/job.image.width;html+=`<div class="recheck-card"><strong>원본 문자 획 대조</strong><p>${p.blur_observed?'원본에서 획 경계 번짐 측정':'독립 OCR: '+esc(p.detector_text)+'<br>픽셀 형태 후보: '+esc(p.shape_text||'미확정')}</p>${p.shape_checks?.length?`<table><thead><tr><th>원본</th><th>OCR</th><th>획 후보</th><th>추가 확인</th></tr></thead><tbody>${p.shape_checks.filter(c=>c.shape_char!==c.ocr_char&&c.accepted).map(c=>{const [x,y,z,b]=c.rect;return `<tr><td><svg width="48" height="48" viewBox="${x*1000} ${y*h} ${(z-x)*1000} ${(b-y)*h}" aria-label="원본 글자 확대"><image href="${BASE}/api/jobs/${esc(job.id)}/image" width="1000" height="${h}"/></svg></td><td>${esc(c.ocr_char)}</td><td>${esc(c.shape_char)}</td><td>${c.independent_comparison?.agrees?'형태 일치':c.independent_comparison?'미확정':'미실행'}</td></tr>`}).join('')}</tbody></table>`:''}<p class="micro">${p.blur_observed?'원본 픽셀의 경계 강도 '+esc(p.metrics.edge_strength)+' · 경계 변화량 '+esc(p.metrics.laplacian):'글꼴 형태 유사도는 오류 확률이 아닙니다. 단어를 추측하지 않고 자모 획을 비교했습니다.'}</p></div>`;}
 if(row.location_unresolved)html+=`<div class="recheck-card"><strong>위치 확인 필요</strong><p>${esc(row.location_evidence?.reason||'분석 의견은 보존했지만 이미지에서 위치를 확정하지 못했습니다.')}</p></div>`;
 html+=readingConflictHTML(row);
 if(row.hand_topology_evidence){const h=row.hand_topology_evidence;html+=`<div class="recheck-card"><strong>${h.source==='LOCAL_PIXELS'?'손 도안 외곽 측정 · 로컬 처리':'손 연결 구조 독립 확인'}</strong><p>${esc(h.summary)}</p>${(h.traces||[]).map(t=>`<p><b>${esc(t.part)}</b> · ${esc(t.visible_path)}${t.obscured_by?' · 가림: '+esc(t.obscured_by):''}</p>`).join('')}</div>`;}
 if(row.glyph_audit_evidence){const g=row.glyph_audit_evidence,a=g.assessment;html+=`<div class="recheck-card"><strong>문자 판독과 별도 획 검사</strong><p>OCR 전사: ${esc(g.detector_text||'[전사 없음]')}<br>문자 단위 판독: ${esc(a.literal_text||'[판독 불가]')}</p><p>${esc(a.reading.evidence)}</p>${g.isolated_glyphs?`<details><summary>문맥 없는 음절 판독 비교 · ${g.isolated_glyphs.agreed?'모델 간 일치 (정상 판정 아님)':'판독 불일치'}</summary><table><thead><tr><th>원본</th><th>GPT-5.4</th><th>mini</th></tr></thead><tbody>${g.isolated_glyphs.parts.map(p=>{const [x,y,z,b]=p.rect,h=1000*job.image.height/job.image.width;return `<tr><td><svg width="45" height="45" viewBox="${x*1000} ${y*h} ${(z-x)*1000} ${(b-y)*h}" role="img" aria-label="원본 음절"><image href="${BASE}/api/jobs/${esc(job.id)}/image" width="1000" height="${h}"/></svg></td>${['gpt-5.4','gpt-5.4-mini'].map(m=>`<td>${esc(p.readings[m].units.map(u=>u.char).join(''))}${p.readings[m].units.every(u=>u.certain)?'':' (미확정)'}${p.jamo_readings?.[m]?`<small>${esc(p.jamo_readings[m].onset)} · ${esc(p.jamo_readings[m].vowel)} · ${esc(p.jamo_readings[m].coda)}<br>${esc(p.jamo_readings[m].evidence)}</small>`:''}</td>`).join('')}</tr>`}).join('')}</tbody></table><p class="micro">같은 글자로 읽어도 실제 철자나 획 품질의 정상 여부는 별도 확인합니다.</p></details>`:''}<p class="micro">기존 문자열·교정안을 제공하지 않고 원본과 겹치는 부분 영역을 검사했습니다. 판독 일치만으로 정상 판정하지 않습니다.</p><details><summary>음절별 획 근거</summary>${a.reading.units.map(u=>`<p>${esc(u.char)} · ${esc(u.strokes)}${u.certain?'':' · 미확정'}</p>`).join('')}</details></div>`;}
 if(row.reported_issues)html+=`<div class="detail-label">사용자 지적 · 자동 판정과 별도</div><p class="micro">${esc(row.reported_issues.note)}</p>${row.reported_issues.parts.map(p=>`<p><b>${esc(p.part)}</b><br>${esc(p.reason)}</p>`).join('')}<p class="micro">직전 모델 판정: ${esc(labels[row.reported_issues.prior_model_status]||row.reported_issues.prior_model_status)} · ${esc(row.reported_issues.prior_model_reason)}</p>`;
 if(name)html+=`<div class="detail-label">공식 명칭 문자 대조</div><p>원문: <b>${esc(name.literal)}</b> · 공식 표기: <b>${esc(name.canonical)}</b></p><p class="micro">${name.independent_reading_agrees?'원본 관찰과 독립 재판독 일치':'전사 미확정 · 원본 확인 필요'} · ${(name.sources||[]).filter(url=>/^https:\/\/((www\.)?mois\.go\.kr|news\.koreanair\.com|www\.airportal\.go\.kr)\//.test(url)).map(url=>`<a href="${esc(url)}" target="_blank" rel="noopener noreferrer">공식 출처 ↗</a>`).join(' · ')}</p>`;
 if(row.glyph_evidence)html+=`<div class="detail-label">문구 판독과 별개인 획 품질</div>${row.glyph_evidence.checks.map(g=>`<p><b>${esc(g.literal||'문자 영역')}</b> · ${g.quality==='DEFECT'?'획 결함 관찰':'판독 불확실'}<br>${esc(g.evidence)}</p>`).join('')}`;
 if(geometry)html+=`<div class="detail-label">중앙 태극 원본 색상 영역 비교</div><p class="micro">정면 도안 일치율 ${(geometry.normal_score*100).toFixed(1)}% · 좌우 반전 도안 일치율 ${(geometry.mirrored_score*100).toFixed(1)}%. 색상 영역 비교값이며 오류 확률이 아닙니다. 깃면 뒷면·4괘 배치는 별도로 확인합니다.</p>`;
 if(row.emblem_geometry){
  const e=row.emblem_geometry,[x,y,z,b]=e.rect,h=1000*job.image.height/job.image.width,run=activeRun();
  html+=`<div class="recheck-card"><strong>원본 픽셀과 기준 문양 비교</strong><table><thead><tr><th>측정 항목</th><th>원본</th><th>기준</th></tr></thead><tbody><tr><td>내부 분리 도형 수</td><td>${esc(e.observed_components)}</td><td>${esc(e.reference_components)}</td></tr></tbody></table><div class="verification-images"><figure><svg viewBox="${x*1000} ${y*h} ${(z-x)*1000} ${(b-y)*h}" role="img" aria-label="문양 원본 확대"><image href="${BASE}/api/jobs/${esc(job.id)}/image" width="1000" height="${h}"/></svg><figcaption>원본에서 측정한 문양</figcaption></figure><figure><img loading="lazy" src="${BASE}/api/jobs/${esc(job.id)}/runs/${esc(run.id)}/references/${esc(e.reference_id)}/image" alt="비교 기준 문양"><figcaption>이 검사에 사용한 기준</figcaption></figure></div><p class="micro">삼각형·막대 등 서로 분리된 내부 도형을 셉니다. 정면 단색 원형 문양의 형태·배치 비교이며 공식 사용 승인과는 별도입니다. 추가 API 호출 없이 계산했습니다.</p>${(row.model_verdicts_before_geometry||[]).map(p=>`<p class="micro">측정 전 모델 의견(보존): ${esc(labels[p.status]||p.status)} · ${esc(p.reason)}</p>`).join('')}</div>`;
 }
 return html;
}
const detailLoads=new WeakMap();
async function loadRunDetails(currentJob,run){
 if(!run?.details_deferred)return;
 if(detailLoads.has(run))return detailLoads.get(run);
 const request=api(`/jobs/${encodeURIComponent(currentJob.id)}/runs/${encodeURIComponent(run.id)}/details`).then(data=>{
  if(data.run_id!==run.id)throw Error('검사 버전이 일치하지 않습니다. 다시 열어 주세요.');
  run.rule_pack=data.rule_pack;run.reference_snapshot=data.reference_snapshot;run.details_deferred=false;
 }).finally(()=>detailLoads.delete(run));
 detailLoads.set(run,request);return request;
}
function showDeferredDetail(target,run){
 const currentJob=job;target.className='';target.innerHTML='<p role="status">상세 근거를 불러오는 중…</p>';
 loadRunDetails(currentJob,run).then(()=>{if(job===currentJob&&activeRun()===run)renderDetail()}).catch(error=>{
  if(job!==currentJob||activeRun()!==run)return;
  target.innerHTML=`<p role="alert">${esc(error.message)}</p><button id="retry-detail" class="secondary">상세 근거 다시 불러오기</button>`;
  $('#retry-detail').onclick=()=>renderDetail();
 });
}
function renderDetail(){
 const r=findings().find(x=>x.id===selected),run=activeRun(),target=$('#finding-detail');
 if(!r){target.className='detail-empty';target.textContent='미리보기의 번호 또는 결과 항목을 선택하면 근거와 검토 의견을 볼 수 있습니다.';return}
 if(run.details_deferred){showDeferredDetail(target,run);return}
 target.className='';const group=selectedAnalysisGroup();const groupHTML=group?`<div class="group-opinions"><h2>${group.number?'번호 '+group.number+' · ':''}${esc(group.label)}</h2>${group.technical?`<p class="measurement-verdict status-${group.status}">측정 결과 · ${esc(group.measurement)}</p><p class="micro">빨강은 원본과 기준의 구조 불일치입니다. 아래 원문 의견의 ‘검토 필요’는 퀴즈 등 제작 의도에 대한 판단입니다.</p>`:''}${group.locationAmbiguous?`<p class="location-warning">위치 미확정 · 서로 떨어진 ${group.locationRegions.length}개 영역이 한 객체로 인식됐습니다. 이미지 가장자리의 번호는 의견을 여는 버튼입니다. 정확한 글자 경계를 확인하지 못해 사각형은 표시하지 않습니다.</p>`:''}${group.rows.map(x=>`<button data-group="${esc(group.id)}" data-finding="${x.id}" class="opinion ${x.id===r.id?'selected':''}"><b>${esc(x.rule_id)} · ${labels[effective(x)]}</b><span>${esc(x.reason)}</span><small>조치: ${esc(x.recommended_action)}</small></button>`).join('')}</div>`:'';const step=(run.rule_pack||pack).steps.find(s=>s.rule_id===r.rule_id);const running=['QUEUED','RUNNING'].includes(job.state);
 target.innerHTML=groupHTML+(group?.comparison?comparisonHTML(group.comparison):r.comparison?comparisonHTML(r.comparison):'')+`<div class="panel-title"><h2>${esc(r.rule_id)} · ${labels[effective(r)]}</h2><span class="badge">${esc(r.instance_id)}</span></div>${effective(r)==='REVIEW'?`<p class="review-display-note">노랑 · ${esc(reviewDisplayLabel(r,run))} — 오류 확정이 아닌 검토 요청입니다.</p>`:''}<p>${esc(step.objective)}</p><div class="detail-label">직접 관찰</div><div>${esc(r.spelling_audit_evidence?'확인한 원문: '+r.spelling_audit_evidence.literal+' · '+(r.spelling_audit_evidence.source?.label||'문자 영역'):r.observation||'관찰 기록 없음')}</div>${textQualityHTML(r)}${verificationHTML(r)}${sourceChecksHTML(r)}<div class="detail-label">판정 이유</div><div>${esc(r.reason)}</div><div class="detail-label">근거와 위치</div><div class="micro">${esc(r.model)} · 규칙 ${esc(r.rule_version)} · ${esc(r.evidence_quality)}<br>${r.comparison?'원본 픽셀의 괘 구조 비교 · 객체 영역':(r.crop_id?'확대 격자 '+esc(r.crop_id.slice(0,13)):'전체 이미지 · 대략적 위치')+' / '+esc(findingCells(r).join(', ')||'위치 없음')}<br>${r.reference_ids.map(id=>esc(run.reference_snapshot.find(x=>x.id===id)?.name||id)).join(', ')||(r.technical_reference?'내장 기술 기준: '+esc(r.technical_reference.name):'인용한 승인 자료 없음')}</div>${run.analysis.filter(a=>a.finding_id===r.id).map(a=>`<div class="detail-label">${esc(a.model)} 분석 의견 · ${labels[a.opinion]}</div><div>${esc(a.reason)}</div>`).join('')}<div class="finding-actions"><button id="retry-step" class="secondary" ${running?'disabled':''}>이 행동만 재검사</button>${findingCells(r).length&&!r.crop_id?`<button id="crop-step" class="secondary" ${running?'disabled':''}>주변 포함 확대 재검사</button>`:''}</div><form id="review-form" class="review-form"><select name="status" aria-label="사람 검토 판정"><option value="REVIEW">검토 보류</option><option value="PASS">정상으로 수정</option><option value="FAIL">오류 의심 확인</option><option value="NOT_APPLICABLE">해당 없음</option></select><button class="primary" ${running?'disabled':''}>검토 기록 저장</button><textarea name="reason" required minlength="5" maxlength="2000" placeholder="판단 근거와 수정 사유를 입력하세요. 최종 공개 승인을 대신하지 않습니다."></textarea></form>${run.reviews.filter(x=>x.finding_id===r.id).map(x=>`<div class="audit-entry"><strong>${labels[x.previous_status]} → ${labels[x.status]}</strong> · ${esc(x.reviewer)} · ${new Date(x.at).toLocaleString('ko-KR')}<br>${esc(x.reason)}</div>`).join('')}`;
 $('#retry-step').onclick=guard(()=>startRun([r.rule_id],null,true));
 if($('#crop-step'))$('#crop-step').onclick=guard(async()=>{const c=await post(`/jobs/${job.id}/crops`,{cell_ids:findingCells(r)});cropPending={crop:c,rule_ids:[r.rule_id]};$('#crop-image').src=BASE+`/api/jobs/${job.id}/crops/${c.id}`;$('#crop-dialog').showModal()});
 $('#review-form').onsubmit=guard(async e=>{e.preventDefault();const f=new FormData(e.target);job=await post(`/jobs/${job.id}/reviews`,{finding_id:r.id,status:f.get('status'),reason:f.get('reason')});renderJob();toast('검토 이력을 저장했습니다.')});
}
async function startRun(ids=[],cropID=null,force=false,mode='live'){requireAnalysisPermission();if(!job)return;const consent=mode==='live'?await requestTransmission(false):false;if(mode==='live'&&!consent)return;job=await post(`/jobs/${job.id}/runs`,{mode,vision_model:$('#vision-model').value,analysis_model:$('#analysis-model').value,consent,text_sensitivity:$('#text-sensitivity').value,rule_ids:ids,crop_id:cropID,force});selected=null;selectedGroup=null;renderJob()}
async function reanalyze(sourceRunID){
 requireAnalysisPermission();
 if(!job)return;
 let source=job.runs.find(r=>r.id===sourceRunID);
 if(sourceRunID&&!source){const saved=await api(`/jobs/${job.id}?view=latest&run_id=${encodeURIComponent(sourceRunID)}`);source=saved.runs[0]}
 source=source||activeRun();
 if(!reusableObservation(source)){toast('재사용할 그림 판독이 없습니다. 그림 + 분석 실행으로 다시 시도하세요.');return}
 const consent=await requestTransmission(true);if(!consent)return;
 job=await post(`/jobs/${job.id}/runs`,{mode:'live',vision_model:source.options.vision_model,analysis_model:$('#analysis-model').value||'gpt-5.4-mini',consent,text_sensitivity:source.options.text_sensitivity||'standard',rule_ids:[],force:true,reuse_observation_run_id:source.id});
 selected=null;selectedGroup=null;renderJob();toast('저장된 이미지 관찰로 원문 25개 항목 전체를 재분석합니다.');
}
let qualitySelection=null;
function qualityPlanHTML(plan,currentJob){
 const states={NOT_RECHECKED:'확대 검사 미실행',PARTIAL:'기존 확대에서 일부만 확인',STRUCTURE_NOT_RECORDED:'세부 손 구조·획 기록 없음',PREVIOUSLY_CHECKED:'기존 판독 있음 · 다시 확인 가능'};
 return plan.entries.map(e=>{
  const r=e.preview_rect,w=currentJob.image.width,h=currentJob.image.height;
  const preview=r?`<svg viewBox="${r[0]*w} ${r[1]*h} ${(r[2]-r[0])*w} ${(r[3]-r[1])*h}" role="img" aria-label="${esc(e.label)} 확대 범위"><image href="${BASE}/api/jobs/${esc(currentJob.id)}/image" width="${w}" height="${h}"/></svg>`:'';
  return `<label class="quality-target"><input type="checkbox" value="${esc(e.object_id)}" ${e.selectable?'':'disabled'} ${plan.recommended_ids.includes(e.object_id)?'checked':''}>${preview}<span><b>${esc(e.label)}</b><small>${e.focus==='anatomy'?'손 구조':'글자 획'} · ${esc(states[e.state]||e.state)}</small><small>${e.selectable?'미검사 상태는 오류 판정이 아닙니다.':'위치가 없어 선택할 수 없습니다.'}</small></span></label>`;
 }).join('')||'<p>저장된 관찰에 선택할 손·글자 영역이 없습니다. 이 경우 그림 + 분석 실행으로 새 관찰이 필요합니다.</p>';
}
function updateQualitySelection(){
 if(!qualitySelection)return;
 const count=$$('#quality-targets input:checked').length,max=qualitySelection.plan.max_objects;
 $('#quality-count').textContent=`${count} / ${max}곳 선택 · 확대 판독 최대 ${Math.min(qualitySelection.plan.max_calls,Math.ceil(count/3))}회 + 관련 규칙 분석`;
 $('#quality-submit').disabled=!count||count>max||config.role!=='admin';
}
async function openQualityRecheck(){
 requireAnalysisPermission();const source=activeRun(),currentJob=job;
 if(!reusableObservation(source)||['RUNNING','QUEUED'].includes(job.state))return;
 const plan=await api(`/jobs/${currentJob.id}/runs/${source.id}/quality-plan`);
 if(job?.id!==currentJob.id||activeRun()?.id!==source.id)return;
 qualitySelection={jobId:currentJob.id,runId:source.id,plan};
 $('#quality-note').textContent=plan.note;
 $('#quality-targets').innerHTML=qualityPlanHTML(plan,currentJob);updateQualitySelection();
 $('#quality-dialog').showModal();
}
async function submitQualityRecheck(){
 requireAnalysisPermission();const selection=qualitySelection;
 if(!selection||selection.jobId!==job?.id||selection.runId!==activeRun()?.id)throw Error('검사 버전이 바뀌었습니다. 영역을 다시 선택해 주세요.');
 const ids=$$('#quality-targets input:checked').map(e=>e.value);
 if(!ids.length||ids.length>selection.plan.max_objects)throw Error(`1~${selection.plan.max_objects}개 영역을 선택해 주세요.`);
 if(['RUNNING','QUEUED'].includes(job.state))throw Error('진행 중인 검사가 끝난 뒤 실행해 주세요.');
 const vision=$('#vision-model').value,analysis=$('#analysis-model').value||'gpt-5.4-mini';
 $('#quality-dialog').close();
 const consent=await requestTransmission(false,{key:['quality',selection.runId,ids],message:`선택한 ${ids.length}개 영역의 원본 확대를 ${vision} 모델에 전송해 새로 읽고, ${analysis} 모델로 선택 영역의 손·글자 관련 규칙을 재분석합니다. 전체 그림 읽기와 NAVER OCR은 다시 호출하지 않습니다. 확대 판독 최대 ${selection.plan.max_calls}회와 관련 규칙 분석 토큰이 공용 한도에서 차감됩니다.`});
 if(!consent){if(job?.id===selection.jobId&&activeRun()?.id===selection.runId)$('#quality-dialog').showModal();return;}
 if(job?.id!==selection.jobId||activeRun()?.id!==selection.runId)throw Error('검사 버전이 변경되었습니다. 다시 선택해 주세요.');
 job=await post(`/jobs/${job.id}/runs`,{mode:'live',vision_model:vision,analysis_model:analysis,consent,text_sensitivity:'strict',rule_ids:[],force:true,reuse_observation_run_id:selection.runId,recheck_object_ids:ids,quality_recheck:true});
 qualitySelection=null;selected=null;selectedGroup=null;renderJob();toast('선택한 손·글자 영역을 새로 판독한 뒤 관련 규칙만 분석합니다.');
}
async function openJob(id){
 const ticket=(openJob.ticket||0)+1;openJob.ticket=ticket;
 if(timer){clearTimeout(timer);timer=null}
 const image=$('#inspection-image'),previousSrc=image.getAttribute('src'),previousHidden=image.hidden;
 const buttons=$$('[data-open-job]').filter(b=>b.dataset.openJob===id);
 const originalLabels=buttons.map(b=>b.textContent);
 buttons.forEach(b=>{b.disabled=true;b.textContent='불러오는 중…';b.setAttribute('aria-busy','true')});
 openJob.loading=true;image.hidden=true;$('#pins').hidden=true;$('#overlays').hidden=true;
 const request=api('/jobs/'+encodeURIComponent(id)+'?view=screen');
 const imageURL=BASE+`/api/jobs/${encodeURIComponent(id)}/image`;
 if(image.getAttribute('src')!==imageURL)image.src=imageURL;
 try{
  const next=await request;if(ticket!==openJob.ticket)return;
  job=next;pendingFile=null;$('#file').value='';clearPreviewURL();fillMetadata();selected=null;selectedGroup=null;
  openJob.loading=false;tab('workspace');renderJob();imageViewport.reset();resultView('original');
 }catch(error){
  if(ticket===openJob.ticket){if(previousSrc)image.src=previousSrc;else image.removeAttribute('src');image.hidden=previousHidden;if(job)renderJob()}
  throw error;
 }finally{
  buttons.forEach((b,i)=>{b.disabled=false;b.textContent=originalLabels[i];b.setAttribute('aria-busy','false')});
  if(ticket===openJob.ticket){openJob.loading=false;$('#pins').hidden=false;$('#overlays').hidden=false}
 }
}
let historyRequest=null;
async function history(){
 if(historyRequest)return historyRequest;
 const target=$('#history-list');target.setAttribute('aria-busy','true');target.innerHTML='<p class="micro" role="status">검수 이력을 불러오는 중입니다.</p>';
 historyRequest=(async()=>{try{const rows=await api('/jobs');target.innerHTML=rows.map(j=>`<div class="card history-row"><div><h2>${esc(j.metadata.title)}</h2><p>${esc(j.metadata.department)} · ${new Date(j.created_at).toLocaleString('ko-KR')} · ${esc(j.state)}</p></div><div class="history-controls"><button class="secondary" data-open-job="${esc(j.id)}">결과 열기</button><button class="secondary" data-reanalysis-job="${esc(j.id)}">분석 모델 변경</button><button class="quiet" data-versions="${esc(j.id)}">검사 버전${j.run_count?' '+j.run_count:''}</button>${config.role==='admin'?`<button class="quiet" data-delete-job="${esc(j.id)}">삭제</button>`:''}</div><div id="versions-${esc(j.id)}"></div></div>`).join('')||'<div class="card">등록된 검수 이력이 없습니다.</div>'}
 catch(error){target.innerHTML='<p class="micro">검수 이력을 불러오지 못했습니다. 검수 이력을 다시 선택해 주세요.</p>';throw error}
 finally{target.setAttribute('aria-busy','false');historyRequest=null}})();
 return historyRequest;
}
function historyVersionsHTML(rows,jid){
 return rows.map((r,i)=>`<p class="micro">검사 ${i+1} · ${esc(new Date(r.created_at).toLocaleString('ko-KR'))} · ${esc(r.vision_model||'미선택')} / ${esc(r.analysis_model||'미선택')} · ${r.result_count}개 결과 · 검토 ${r.review_count}건 ${r.reusable_observation?`<button class="quiet" data-source-job="${esc(jid)}" data-source-run="${esc(r.id)}">이 버전의 관찰로 재분석</button>`:''}</p>`).join('')+'<p class="micro">전체 버전의 상세 결과·기준자료·검토 기록은 JSON 보고서에 포함됩니다.</p>';
}
async function showHistoryVersions(jid){
 const target=$('#versions-'+jid);if(target.dataset.loaded){target.hidden=!target.hidden;return}
 if(target.getAttribute('aria-busy')==='true')return;
 target.setAttribute('aria-busy','true');target.innerHTML='<p class="micro" role="status">검사 버전을 불러오는 중입니다.</p>';
 try{const rows=await api(`/jobs/${jid}/versions`);target.innerHTML=historyVersionsHTML(rows,jid);target.dataset.loaded='true'}
 catch(error){target.textContent='검사 버전을 다시 선택해 주세요.';throw error}
 finally{target.setAttribute('aria-busy','false')}
}
async function references(){const rows=await api('/references');$('#reference-list').innerHTML=rows.map(r=>r.kind==='inspection-guidance'?precheckReferenceHTML(r):`<div class="card reference-card"><div class="panel-title"><h2>${esc(r.name)}</h2><span class="badge">${esc(r.status)}</span></div><p>${esc(r.issuer)} · ${esc(r.version)} · ${esc(r.parent_ids.join(', '))}</p><a href="${esc(r.official_url)}" target="_blank" rel="noopener noreferrer">공식 출처 ↗</a><pre>${esc(r.content)}</pre>${r.image_file?`<img src="${BASE}/api/references/${r.id}/image" alt="공식 비교 이미지">`:''}<p class="micro">${r.approved_at?'승인: '+esc(r.approved_by)+' / '+new Date(r.approved_at).toLocaleString('ko-KR'):'승인 전 자료는 검사에 사용되지 않습니다.'}</p>${config.role==='admin'&&r.status==='DRAFT'?`<button class="secondary" data-approve="${r.id}">출처·적용범위 확인 후 승인</button>`:''}</div>`).join('')||'<div class="card"><h2>아직 승인된 기준자료가 없습니다.</h2><p>공식 도안·정책·이용권을 확인할 수 없는 항목은 검토 필요로 유지합니다.</p></div>'}
async function usage(){const u=await api('/usage');let shared=u.shared?.external_breakdown||[];const b=u.budget;$('#usage-body').innerHTML=`<div class="metrics"><div class="metric"><small>PoC11 누적 호출</small><strong>${u.events.length}</strong><small>시연·캐시 재사용은 미포함</small></div><div class="metric"><small>PoC11 추정 비용</small><strong>$${u.cost_usd.toFixed(4)}</strong><small>비용 미확정 ${u.unknown_cost_calls}회</small></div><div class="metric"><small>PoC7 공용 원장 잔여</small><strong>${b?'$'+b.remaining_usd.toFixed(2):'확인 필요'}</strong><small>${b?'예산 $'+b.limit_usd+' · 예약 $'+b.reserved_usd.toFixed(2):esc(u.budget_error||'공용 예산 미연결')}</small></div><div class="metric"><small>중앙 전송 대기</small><strong>${u.pending}</strong><small>${u.shared_error?esc(u.shared_error):'PoC7 중앙 서비스 연결됨'}</small></div></div><div class="notice">${esc(u.cost_basis)}. GPT-5.4는 일 100만, mini는 일 1,000만 토큰을 PoC7과 공유해 예약·정산합니다. GPT 6.0·6.1은 공용 크레딧을 사용합니다. 아래 비용은 표준 요금 환산값이며 무료 적용 후 청구액이 아닙니다. Solar 사용량은 중앙 집계하며 공급자 잔액으로 표시하지 않습니다. 중앙 일별 기록은 수신일(UTC) 기준입니다.</div>${u.naver_ocr?`<div class="notice"><b>NAVER CLOVA OCR · ${u.naver_ocr.remaining} / ${u.naver_ocr.limit}회 남음</b><p>${esc(u.naver_ocr.note)}</p><small>이번 달 ${u.naver_ocr.used}회 · 미확정 ${u.naver_ocr.unknown}회 · 갱신 ${new Date(u.naver_ocr.expires_at).toLocaleString('ko-KR')}</small><details><summary>NAVER 호출 이력</summary>${u.naver_ocr_events.map(e=>`<p>${new Date(e.at).toLocaleString('ko-KR')} · ${esc(e.state)} · ${esc(e.detail)}</p>`).join('')||'호출 이력 없음'}</details></div>`:''}<h2>PoC11 호출 내역</h2><div class="table-wrap"><table><thead><tr><th>시각</th><th>단계</th><th>모델</th><th>입력 / 출력 토큰</th><th>추정 USD</th><th>중앙 전송</th></tr></thead><tbody>${u.events.slice().reverse().map(e=>`<tr><td>${new Date(e.recorded_at).toLocaleString('ko-KR')}</td><td>${esc(e.workload)}</td><td>${esc(e.model)}</td><td>${e.input_tokens} / ${e.output_tokens}</td><td>${e.cost_usd===null?'미확정':e.cost_usd.toFixed(5)}</td><td>${e.synced?'완료':'대기'} · ${esc(e.status)}</td></tr>`).join('')}</tbody></table></div><h2 style="margin-top:28px">공용 게이트웨이 · 오늘(UTC)</h2><div class="table-wrap"><table><thead><tr><th>프로젝트</th><th>모델</th><th>호출</th><th>토큰</th><th>USD</th></tr></thead><tbody>${shared.map(r=>`<tr><td>${esc(r.project)}</td><td>${esc(r.model)}</td><td>${r.count}</td><td>${r.input_tokens+r.output_tokens}</td><td>${r.cost_usd??'미확정'}</td></tr>`).join('')}</tbody></table></div>`}
function clearPreviewURL(){if(previewURL){URL.revokeObjectURL(previewURL);previewURL=null}}
function fillMetadata(){for(const el of $('#upload-form').elements){if(el.name&&el.name!=='file'){el.value=job.metadata[el.name]||'';el.disabled=true}}$('#file-label').textContent=job.metadata.title;}
async function runImageAnalysis(){
 requireAnalysisPermission();
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
$('#demo').onclick=guard(async()=>{requireAnalysisPermission();job=await post('/demo');pendingFile=null;$('#file').value='';clearPreviewURL();fillMetadata();selected=null;selectedGroup=null;renderJob();await startRun([],null,false,'mock');resultView('original')});
$('#run').onclick=guard(runImageAnalysis);
$('#reanalyze').onclick=guard(()=>reanalyze());
$('#quality-recheck').onclick=guard(openQualityRecheck);
$('#quality-close').onclick=()=>$('#quality-dialog').close();
$('#quality-targets').onchange=updateQualitySelection;
$('#quality-submit').onclick=guard(submitQualityRecheck);
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
async function logoutSession(){
 const button=$('#login-button');button.disabled=true;
 try{
  await post('/logout');
  const current=await api('/config');
  if(current.role)throw Error('로그인 세션이 아직 남아 있습니다. 다시 로그아웃해 주세요.');
  clearTimeout(timer);timer=null;
  // Discard private results, editor contents and pending requests with the page.
  location.reload();
 }finally{button.disabled=false}
}
$('#login-button').onclick=guard(async()=>{if(config.role)await logoutSession();else $('#login-dialog').showModal()});
$('#close-login').onclick=()=>$('#login-dialog').close();$('#login-form').onsubmit=guard(async e=>{e.preventDefault();const f=new FormData(e.target);await post('/login',Object.fromEntries(f));$('#login-dialog').close();e.target.reset();await refreshConfig();toast('로그인했습니다.')});
$('#source-copy-template').onclick=()=>{
 if(!job?.image?.normalized_sha256||!activeRun()?.observation){toast('검수 이력에서 이미지를 먼저 선택하세요.');return;}
 const form=$('#reference-form');form.elements.kind.value='source-data';form.elements.parent_ids.value='D-02,H-06';
 form.elements.content.value=JSON.stringify({schema:'chekmi-source-copy-v1',image_sha256:job.image.normalized_sha256,entries:activeRun().observation.objects.filter(o=>o.text).map(o=>({object_id:o.id,label:o.label,text:''})).slice(0,40)},null,2);
 toast('빈 text에 승인 원고를 입력하고 불필요한 항목은 삭제하세요. OCR 결과는 정답으로 복사하지 않습니다.');
};
$('#reference-form').onsubmit=guard(async e=>{e.preventDefault();const f=new FormData(e.target),image=f.get('reference_image');f.delete('reference_image');const d=Object.fromEntries(f);d.parent_ids=d.parent_ids.split(',').map(x=>x.trim());const r=await post('/references',d);if(image?.size){const fd=new FormData();fd.set('file',image);await api(`/references/${r.id}/image`,{method:'POST',body:fd})}e.target.reset();await references();toast('기준자료 초안을 등록했습니다.')});
$('#sync-usage').onclick=guard(async()=>{await post('/usage/sync');await usage()});
document.addEventListener('click',guard(async e=>{const f=e.target.closest('[data-finding]');if(f){openFinding(f.dataset.finding,f.dataset.group);return}const nav=e.target.closest('[data-tab]');if(nav){tab(nav.dataset.tab);if(nav.dataset.tab==='history')await history();if(nav.dataset.tab==='references')await references();if(nav.dataset.tab==='usage')await usage();if(nav.dataset.tab==='rules-admin'&&!rulesState)await loadRuleEditor();return}const filterButton=e.target.closest('[data-filter]');if(filterButton){filter=filterButton.dataset.filter;$$('.filter').forEach(x=>x.classList.toggle('active',x===filterButton));renderIssues();return}const reanalysis=e.target.closest('[data-reanalysis-job]');if(reanalysis){await openJob(reanalysis.dataset.reanalysisJob);$('#analysis-model').focus();toast('분석 모델을 선택하고 ‘이미지 재사용 · 재분석’을 누르세요.');return}const source=e.target.closest('[data-source-run]');if(source){if(source.dataset.sourceJob&&source.dataset.sourceJob!==job?.id)await openJob(source.dataset.sourceJob);tab('workspace');await reanalyze(source.dataset.sourceRun);return}const open=e.target.closest('[data-open-job]');if(open)return openJob(open.dataset.openJob);const del=e.target.closest('[data-delete-job]');if(del&&confirm('이미지와 검토 내용을 영구 삭제하시겠습니까? 사용량 기록은 유지됩니다.')){await api('/jobs/'+del.dataset.deleteJob,{method:'DELETE'});return history()}const approve=e.target.closest('[data-approve]');if(approve){await post('/references/'+approve.dataset.approve+'/approve');return references()}const versions=e.target.closest('[data-versions]');if(versions)await showHistoryVersions(versions.dataset.versions)}));
(async()=>{try{await refreshConfig();pack=await api('/rules')}catch(e){toast(e.message)}})();

const imageViewport=new ImageViewport($('.image-stage'),$('#image-wrap'),$('#inspection-image'));
$('#inspection-image').onload=()=>{imageViewport.reset();if(job&&!openJob.loading){renderIssues();renderOverlay()}};
new ResizeObserver(()=>{if(job&&!openJob.loading){renderIssues();renderOverlay()}}).observe($('#image-wrap'));

$('#vision-model').addEventListener('change',()=>{$('#openrouter-note').hidden=!$('#vision-model').value.endsWith(':free')});

function comparisonHTML(flag){
 return `<div class="flag-comparison"><h3>실제 획 구성과 공식 배치</h3><table><thead><tr><th>위치</th><th>원본</th><th>읽은 괘</th><th>공식 기준</th><th>비교</th></tr></thead><tbody>${flag.trigrams.map(t=>{const [x,y,x1,y1]=t.rect,w=job.image.width,h=job.image.height;return `<tr class="comparison-${t.match===false?'mismatch':t.match===true?'match':'uncertain'}"><td>${esc(t.position)}</td><td><svg viewBox="${x*w} ${y*h} ${(x1-x)*w} ${(y1-y)*h}" width="72" height="72" role="img" aria-label="${esc(t.position)} 원본 확대"><image href="${BASE}/api/jobs/${job.id}/image" width="${w}" height="${h}" preserveAspectRatio="none"/></svg></td><td>${esc(t.observed||'판독 불가')}<br>${t.pattern?t.pattern.map(n=>n===1?'━━':'━ ━').join('<br>'):''}</td><td>${esc(t.expected)}</td><td><strong class="status-${t.match===true?'PASS':t.match===false?'FAIL':'REVIEW'}">${t.match===true?'일치':t.match===false?'불일치':'미확정'}</strong></td></tr>`}).join('')}</tbody></table><p class="micro"><a href="https://www.guri.go.kr/www/contents.do?key=461" target="_blank" rel="noopener noreferrer">공식 기준: 구리시 · 국기의 제작 ↗</a> · 4괘 획·위치만 비교. 퀴즈 오답의 의도 여부는 사람 확인.</p></div>`;
}
let checklistFilter='all';
function originalBodyHTML(p){
  const evidence=p.technical_evidence?.flags?.length?`<details class="support-evidence"><summary>H-04 보조 근거 · 괘 구조 측정 ${p.technical_evidence.flags.length}개 도안</summary><p>아래는 원문 판정을 뒷받침하는 부분 측정입니다. 퀴즈의 제작 의도와 공식 자료의 적용 범위는 위 분석 의견에서 확인하세요.</p>${p.technical_evidence.flags.map(f=>`<details><summary>${esc(f.label)} · ${f.status==='MATCH'?'측정 배치 일치':f.status==='MISMATCH'?'측정 배치 차이':'측정 미확정'}</summary>${comparisonHTML(f)}</details>`).join('')}</details>`:'';
 return `${!p.complete?`<div class="notice">원문 판정 미완료: ${p.missing_rule_ids.map(esc).join(', ')}. 보조 측정만으로 원문 분석을 완료 처리하지 않습니다.</div>`:''}${p.evaluations.map(g=>`<article class="original-evaluation"><div><b class="status-${g.status}">${labels[g.status]}</b> <small>${g.rule_ids.map(esc).join(', ')}</small></div><dl><dt>관찰 근거</dt><dd>${esc(g.observation||(g.status==='NOT_APPLICABLE'?'관련 대상이 관찰되지 않았다는 분석 결과입니다.':'직접 관찰 근거 없음'))}</dd><dt>분석 의견</dt><dd>${esc(g.reason)}</dd><dt>확인·수정 사항</dt><dd>${esc(g.action||'추가 조치 없음')}</dd></dl><small>분석: ${esc(g.model)} · 기준자료: ${g.reference_ids.map(id=>esc(activeRun().reference_snapshot.find(r=>r.id===id)?.name||id)).join(', ')||'인용 자료 없음'}</small><div class="original-step-links">${g.finding_ids.map(id=>{const r=findings().find(r=>r.id===id);return `<button class="quiet" data-finding="${esc(id)}">${esc(r?.rule_id)} 상세·위치·검토 기록</button>`}).join('')}</div></article>`).join('')}${evidence}`;
}
function fillOriginalBody(card){
 const body=card.querySelector('.original-body');if(!body||body.dataset.loaded==='true')return;
 const item=job?.checklist_report?.items.find(p=>p.id===card.dataset.parent);if(!item)return;
 body.innerHTML=originalBodyHTML(item);body.dataset.loaded='true';
}
document.addEventListener('toggle',e=>{if(e.target.matches?.('.original-item')&&e.target.open)fillOriginalBody(e.target)},true);
window.addEventListener('beforeprint',()=>$$('.original-item').forEach(fillOriginalBody));
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

  return `<details class="original-item" id="original-${p.id}" data-parent="${p.id}" ${opened.has(p.id)?'open':''}><summary><div class="original-title"><strong>${esc(p.id)} ${esc(p.title)}</strong><span class="status-${p.status}">${labels[p.status]}</span></div>${detected.length?`<p class="detected-summary ${detected.some(f=>f.status==='MISMATCH')?'status-FAIL':''}">태극기 ${detected.length}개 확인 · 괘 배치 불일치 ${detected.filter(f=>f.status==='MISMATCH').length}개 · 미리보기 번호에서 근거 확인</p>`:''}<p class="original-question">${esc(p.original)}</p><p class="original-verdict">${esc(first?.reason||'아직 원문 분석 결과가 없습니다.')}</p><small>세부 규칙 ${p.assessed_count}/${p.step_count}개 분석${!p.complete?' · 미완료':''} · 근거와 분석 의견 펼치기</small></summary><div class="original-body" data-loaded="${opened.has(p.id)?'true':'false'}">${opened.has(p.id)?originalBodyHTML(p):''}</div></details>`;
 }).join('')||'<p>해당하는 항목이 없습니다.</p>';
}
document.addEventListener('click',e=>{const f=e.target.closest('[data-checklist-filter]');if(f){checklistFilter=f.dataset.checklistFilter;$$('[data-checklist-filter]').forEach(x=>x.classList.toggle('active',x===f));renderOriginalReport();}const p=e.target.closest('[data-parent-analysis]');if(p){resultView('original');checklistFilter='all';$$('[data-checklist-filter]').forEach(x=>x.classList.toggle('active',x.dataset.checklistFilter==='all'));renderOriginalReport();const card=$('#original-'+p.dataset.parentAnalysis);if(card){fillOriginalBody(card);card.open=true;card.scrollIntoView({behavior:'smooth',block:'start'})}}});

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
function requestTransmission(reuse,extra=null){
 const vision=$('#vision-model').value,analysis=$('#analysis-model').value;
 const key=JSON.stringify([job.id,reuse?'observation':vision,analysis,...(extra?[extra.key]:[])]);
 if(transmissionGrants.has(key))return Promise.resolve(true);
 const dialog=$('#transmission-dialog');
 $('#transmission-context').textContent=extra?.message||(reuse?`저장된 이미지 관찰 기록을 ${analysis} 모델에 전송해 분석합니다. 손·글자 영역을 새로 읽으려면 ‘손·글자 확대 재검사’를 사용하세요.`:`이 이미지를 ${vision} 모델에, 관찰 기록을 ${analysis} 모델에 전송합니다.`);
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
 const confirmed=row.spelling_audit_evidence;if(confirmed?.source?.source==='confirmed-source-glyphs')return `<div class="text-quality-evidence"><b>원본 획으로 확인한 문자</b><p>확인한 원문: <strong>${esc(confirmed.literal)}</strong></p><p>처음 OCR의 문맥 복원과 다른 글자 획을 독립 비교했습니다. 철자 판정은 아래 검사 근거에서 확인하세요.</p></div>`;
 const objects=((activeRun()?.analysis_observation||activeRun()?.observation)?.objects||[]).filter(o=>row.evidence_ids?.includes(o.id)&&o.text_legibility&&o.text_legibility!=='NOT_TEXT'&&o.text_legibility!=='UNASSESSED');
 const names={CLEAR:'획·외형 정상',DEGRADED:'획 손상·뭉개짐 관찰',UNREADABLE:'문자 식별 어려움'};
 return objects.length?`<div class="text-quality-evidence"><b>문자 인식과 외형 품질</b>${objects.map(o=>`<p><strong>${esc(o.label)} · ${o.text_disagreement?'판독 불일치 · 원본 확인 필요':names[o.text_legibility]}</strong><br>읽은 내용: ${esc(o.text||'[판독불가]')}${o.transcription_inferred?(o.glyph_region?' · 음절 판독 미확정':' · 문맥 추정 포함'):''}<br>외형 근거: ${esc(o.legibility_evidence||'별도 외형 근거 없음')}</p>`).join('')}</div>`:'';
}

function verificationHTML(row){
 const run=activeRun(),v=run?.verification,ids=row.evidence_ids||[];
 const results=[...(v?.results||[]),...(v?.attempt_results||[]),...(v?.reference_results||[])].filter(r=>ids.includes(r.object_id)&&r.status==='COMPLETED');
 const deferred=(v?.deferred||[]).filter(r=>ids.includes(r.object_id));
 const states={NOT_REQUIRED:'추가 증빙 불필요',VERIFIED:'해당 범위 근거 확인',REQUIRED:'기준·증빙 필요',UNAVAILABLE:'비교 미확정'};
 const types={OCR_OMISSION:'OCR 전사 누락',OCR_UNCERTAIN:'문자 판독 미확정',OCR_RECOGNITION_ERROR:'OCR 인식 오류 후보',TYPO_CONFIRMED:'원본 오탈자',OCR_MISMATCH:'판독 결과 불일치',OCR_UNREADABLE:'판독 어려움',VISUAL_TEXT_DEFECT:'글자 외형 결함',SOURCE_MISMATCH:'정본 불일치',FACT_OR_STYLE_ISSUE:'사실·표현 확인'};
 const status=row.evidence_status?`<p>증빙: ${states[row.evidence_status]||esc(row.evidence_status)}${types[row.error_type]?' · '+types[row.error_type]:''}</p>`:'';
 const cards=results.map(r=>{
  const comparisons=(r.comparisons||[]).filter(c=>c.rule_ids.includes(row.rule_id));
  const [x,y,z,w]=r.crop_rect;
  const picture=$('#inspection-image'),height=1000*(picture.naturalHeight||job.image.height)/(picture.naturalWidth||job.image.width);
  const original=`<svg viewBox="${x*1000} ${y*height} ${(z-x)*1000} ${(w-y)*height}" role="img" aria-label="주변 포함 확대 원본"><image href="${esc(picture.src)}" width="1000" height="${height}"/></svg>`;
  return `<div class="recheck-card"><strong>확대 재검사 · ${esc(r.object_id)}${r.coverage==='COMPLETE'?' · 전체 확인':' · 부분 확인'}</strong><p>1차 전사: ${esc(r.first_text||'문자 없음')}<br>독립 재판독: ${esc(r.text||'문자 없음')}${r.transcription_disagreement?' · 판독 차이 있음':''}</p><p>${esc(r.legibility_evidence||r.description)}</p>${r.emblem_parts?`<p><b>부위별 관찰</b><br>${esc(r.emblem_parts)}</p>`:''}${comparisons.map(c=>`<p><b>${esc(c.status)}</b> · ${esc(c.evidence)}</p><div class="verification-images"><figure>${original}<figcaption>확대 원본</figcaption></figure><figure><img loading="lazy" src="${BASE}/api/jobs/${esc(job.id)}/runs/${esc(run.id)}/references/${esc(c.reference_id)}/image" alt="공식 비교 도안"><figcaption>${esc(run.reference_snapshot.find(ref=>ref.id===c.reference_id)?.name||c.reference_id)}</figcaption></figure></div>`).join('')}</div>`;
 }).join('');
 return status+supplementalEvidenceHTML(row)+ocrEvidenceHTML(row)+cards+deferred.map(r=>`<p class="location-warning">${esc(r.reason)}</p>`).join('')+(v?.reused_without_verification?'<p class="location-warning">이전 인식 기록에는 확대·직접 비교 기록이 없습니다. 손·글자 영역은 확대 재검사에서 선택해 새로 확인할 수 있습니다.</p>':'');
}

function supplementalEvidenceHTML(row){
 return (row.supplemental_evidence||[]).map(d=>{
  const [x,y,z,b]=d.rect,picture=$('#inspection-image'),height=1000*(picture.naturalHeight||job.image.height)/(picture.naturalWidth||job.image.width);
  const original=`<svg viewBox="${x*1000} ${y*height} ${(z-x)*1000} ${(b-y)*height}" role="img" aria-label="추가 검증 원본"><image href="${esc(picture.src)}" width="1000" height="${height}"/></svg>`;
  const content=d.kind==='glyph'?`<p>전문 OCR 문구: ${esc(d.word_text)}<br>독립 음절: ${d.characters.map(c=>esc(c.literal_text)).join(' / ')}</p><table><thead><tr><th>음절</th><th>읽은 글자</th><th>원본 획 판독 근거</th></tr></thead><tbody>${d.characters.map((c,i)=>`<tr><td>${i+1}</td><td>${esc(c.literal_text)}</td><td>${esc(c.glyph_evidence)}</td></tr>`).join('')}</tbody></table><small>문구와 음절의 판독 차이를 표시합니다. 음절 분리 과정의 영향과 인식 오류가 남아 있어 위 전사를 정답으로 확정하지 않습니다.</small>`:`<p>${esc(d.description)}</p><p>${esc(d.visual_concerns)}</p><small>검출하지 못했다는 사실은 이미지가 정상이라는 증거가 아닙니다.</small>`;
  return `<div class="recheck-card"><strong>추가 독립 검증 · ${esc(d.model)}</strong><div class="verification-images"><figure>${original}<figcaption>검증 대상 원본 영역</figcaption></figure></div>${content}</div>`;
 }).join('');
}

function ocrEvidenceHTML(row){
 const r=row.ocr_evidence;if(!r)return '';
 const v=r.vision,rect=r.crop_rect||r.rect,[x,y,z,b]=rect,picture=$('#inspection-image');
 const height=1000*(picture.naturalHeight||job.image.height)/(picture.naturalWidth||job.image.width);
 const original=`<svg viewBox="${x*1000} ${y*height} ${(z-x)*1000} ${(b-y)*height}" role="img" aria-label="문자 원본 확대"><image href="${esc(picture.src)}" width="1000" height="${height}"/></svg>`;
 return `<div class="recheck-card"><strong>독립 문자 판독 · 원본 획 검사</strong><div class="verification-images"><figure>${original}<figcaption>격자 없는 원본 · 손상 복원 없음</figcaption></figure></div><dl><dt>${esc(r.recognition_engine||'PaddleOCR')}</dt><dd>${esc(r.text||'[전사 없음]')} · 인식 신뢰도 ${Math.round((r.recognition_score||0)*100)}%</dd>${r.paddle_text!==undefined?`<dt>PaddleOCR 최초 전사</dt><dd>${esc(r.paddle_text||'[전사 없음]')}</dd>`:''}<dt>독립 이미지 판독</dt><dd>${esc(v?.literal_text||'[미검사]')}</dd><dt>글자 모양</dt><dd>${esc(v?.glyph_evidence||'획 품질을 확인하지 못했습니다.')}</dd><dt>철자 검토</dt><dd>${esc(v?.spelling_evidence||'교정 의견 없음')}${v?.suggested_text?' · 교정 후보: '+esc(v.suggested_text):''}</dd></dl><small>인식 신뢰도는 이미지 정상 확률이 아닙니다. 판독 불일치는 원본 오타와 구분합니다.</small></div>`;
}
