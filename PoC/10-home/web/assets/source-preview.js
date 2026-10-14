'use strict';
const SourcePreview=(()=>{
 const value=v=>v===null?'null':typeof v==='object'?JSON.stringify(v):String(v);
 function table(data){
  if(!data.items.length)return '<p class="source-preview-empty">현재 저장된 수집 레코드가 없습니다. 샘플 데이터는 생성하지 않습니다.</p>';
  const fields=data.fields;
  return '<p>현재 저장 '+num(data.total)+'건 중 최근 '+data.items.length+'행 · 최신 리비전만 표시 · 인증정보 제외</p><div class="source-preview-fields"><b>표본에서 확인한 수집 필드 ('+fields.length+'개)</b><p>'+fields.map(f=>'<code>'+esc(f)+'</code>').join(' ')+'</p></div><p class="source-preview-note">최대 50행을 표시합니다. 10행을 넘으면 표 안에서 스크롤하세요. 긴 값은 셀을 선택하면 전체 내용을 확인할 수 있습니다.</p><div class="source-preview-scroll" tabindex="0" role="region" aria-label="실제 수집 샘플 최대 50행"><table><thead><tr><th scope="col">행</th><th scope="col">레코드 유형</th>'+fields.map(f=>'<th scope="col">'+esc(f)+'</th>').join('')+'</tr></thead><tbody>'+data.items.map((r,i)=>'<tr><th scope="row">'+(i+1)+'</th><td>'+esc(r.kind)+'</td>'+fields.map(f=>{const v=Object.hasOwn(r.data,f)?value(r.data[f]):'—';return '<td>'+(v.length>90?'<button type="button" class="source-preview-value" data-value="'+esc(v)+'" aria-label="'+esc(f)+' 전체 값 보기">'+esc(v.slice(0,90))+'…</button>':esc(v))+'</td>';}).join('')+'</tr>').join('')+'</tbody></table></div>';
 }
 function attach(host,sources){
  host.querySelectorAll('.source-card').forEach((card,i)=>{
   const source=sources[i],details=document.createElement('section'),header=document.createElement('div'),toggle=document.createElement('button');details.className='source-preview';details.hidden=true;details.id='source-preview-'+source.id;header.className='source-row-header';
   toggle.type='button';toggle.className='button secondary source-preview-toggle';toggle.textContent='수집항목·샘플 펼치기';toggle.setAttribute('aria-expanded','false');toggle.setAttribute('aria-controls',details.id);
   const title=card.querySelector('.source-title'),description=card.querySelector('p'),counts=card.querySelector('.source-data'),link=card.querySelector(':scope > a');
   for(const node of [title,description,counts,link])if(node)header.append(node);
   while(card.firstChild)details.append(card.firstChild);
   const body=document.createElement('div');body.className='source-preview-body';body.setAttribute('aria-live','polite');details.append(body);header.append(toggle);card.append(header,details);
   let loaded=false,loading=false;
   async function load(){if(loaded||loading||details.hidden)return;loading=true;const body=details.querySelector('.source-preview-body');body.innerHTML='<p role="status">실제 수집 데이터를 불러오는 중…</p>';
    try{const data=await request('/sources/'+encodeURIComponent(source.id)+'/samples');if(!details.isConnected)return;body.innerHTML=table(data);loaded=true;}
    catch(error){body.innerHTML='<p>샘플 조회 실패: '+esc(error.message)+'</p><button type="button" class="button secondary" data-source-retry>다시 불러오기</button>';body.querySelector('[data-source-retry]').onclick=load;}
    finally{loading=false;}
   }
   toggle.addEventListener('click',()=>{details.hidden=!details.hidden;toggle.setAttribute('aria-expanded',String(!details.hidden));toggle.textContent=details.hidden?'수집항목·샘플 펼치기':'수집항목·샘플 접기';load();});
   details.addEventListener('click',event=>{const button=event.target.closest('[data-value]');if(!button)return;const dialog=document.createElement('dialog');dialog.className='source-value-dialog';const close=document.createElement('button');close.className='button secondary';close.textContent='닫기';const pre=document.createElement('pre');pre.textContent=button.dataset.value;dialog.append(close,pre);document.body.append(dialog);close.onclick=()=>dialog.close();dialog.addEventListener('close',()=>dialog.remove());dialog.showModal();});
  });
 }
 return {attach};
})();
