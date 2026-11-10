'use strict';
// Loaded with the collection view; no requests until the user opens the export.
{
  const $=id=>document.getElementById(id);
  const dialog=$('pc-slice-dialog');
  let timer=null, job=null;
  const message=text=>{$('pc-slice-message').textContent=text;};
  const stamp=value=>new Date(value.replace(' ','T').replace(/([+-]\d{2})$/,'$1:00'));
  const local=value=>stamp(value).toLocaleString('ko-KR',{timeZone:'Asia/Seoul',hour12:false});
  function busy(value){$('pc-slice-create').disabled=value;for(const id of ['pc-slice-target','pc-slice-mode','pc-slice-since','pc-slice-golden'])$(id).disabled=value||(id==='pc-slice-since'&&$('pc-slice-mode').value==='full');}
  function render(state){
    const running=state.status==='RUNNING';busy(running);message(state.message);
    $('pc-slice-progress').hidden=!running;
    const download=$('pc-slice-download');download.hidden=true;
    if(state.status==='COMPLETED'){
      const r=state.result;download.href=API+'/project-collection/slices/jobs/'+encodeURIComponent(state.id)+'/download';download.hidden=false;
      $('pc-slice-result').textContent=(r.since?'변경 기준 '+local(r.since):'전체 자료')+' → '+local(r.until)+' (한국시간)\n'+r.rows.toLocaleString('ko-KR')+'행 · '+r.files+'파일 · '+(r.bytes/1024/1024).toFixed(1)+' MB'+(r.full_fallback?'\n담당자 정보 제거가 기존 행에도 영향을 주어, 누락 방지를 위해 전체 자료로 생성했습니다.':'')+'\n다운로드는 생성 후 24시간 동안 가능합니다.';
    }
    clearTimeout(timer);
    if(running&&dialog.open)timer=setTimeout(poll,4000);
  }
  async function poll(){
    if(!job||!dialog.open)return;
    try{render(await request('/project-collection/slices/jobs/'+encodeURIComponent(job)));}
    catch(error){message(error.message+' · 생성 상태를 다시 확인해 주세요.');busy(false);$('pc-slice-progress').hidden=true;}
  }
  $('pc-slice-open').addEventListener('click',async()=>{
    dialog.showModal();
    if(job){poll();return;}
    try{
      const data=await request('/project-collection/slices');
      $('pc-slice-target').replaceChildren(...data.targets.map(t=>new Option(t.name+' · '+t.format,t.id)));
    }catch(error){message(error.message);}
  });
  $('pc-slice-close').addEventListener('click',()=>dialog.close());
  dialog.addEventListener('close',()=>clearTimeout(timer));
  $('pc-slice-mode').addEventListener('change',()=>{$('pc-slice-since').disabled=$('pc-slice-mode').value==='full';});
  $('pc-slice-form').addEventListener('submit',async event=>{
    event.preventDefault();busy(true);$('pc-slice-download').hidden=true;$('pc-slice-result').textContent='';message('생성을 요청하고 있습니다…');
    const query=new URLSearchParams({target:$('pc-slice-target').value,mode:$('pc-slice-mode').value,since:$('pc-slice-since').value,golden:String($('pc-slice-golden').checked)});
    try{
      const state=await request('/project-collection/slices/start?'+query);job=state.id;
      try{sessionStorage.setItem('home-slice-job',job);}catch(_){}render(state);
    }catch(error){message(error.message);busy(false);}
  });
  try{job=sessionStorage.getItem('home-slice-job');}catch(_){/* Storage can be disabled. */}
  $('pc-slice-refresh').addEventListener('click',poll);
}
