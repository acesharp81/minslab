/* Real SSE transport. One request, incremental text, final validated citations. */
async function streamQuestion(path, body, onText, signal){
 const response=await fetch(apiUrl(path+'/stream'),{method:'POST',headers:{'Content-Type':'application/json','X-Role':state.role},body:JSON.stringify(body),signal});
 if(!response.ok){const value=await response.json().catch(()=>({}));if(response.status===401)loginDialog();throw new Error(value.detail||'답변 연결을 시작하지 못했습니다.');}
 if(!response.body)throw new Error('이 브라우저에서 실시간 응답을 받을 수 없습니다.');
 const reader=response.body.getReader(),decoder=new TextDecoder();let buffer='',answer=null;
 const frame=raw=>{let event='',data=[];for(const line of raw.split('\n')){if(line.startsWith('event:'))event=line.slice(6).trim();if(line.startsWith('data:'))data.push(line.slice(5).trimStart());}if(!data.length)return;const value=JSON.parse(data.join('\n'));if(event==='delta')onText(value.text||'');else if(event==='done')answer=value;else if(event==='error')throw new Error(value.message||'답변을 확인하지 못했습니다.');};
 try{while(true){const {value,done}=await reader.read();buffer+=done?decoder.decode():decoder.decode(value,{stream:true});buffer=buffer.replace(/\r\n/g,'\n');let end;while((end=buffer.indexOf('\n\n'))>=0){frame(buffer.slice(0,end));buffer=buffer.slice(end+2);}if(done)break;}if(!answer)throw new Error('답변 연결이 완료되기 전에 끊겼습니다. 다시 질문해 주세요.');return answer;}
 finally{await reader.cancel().catch(()=>{});reader.releaseLock();refreshBudget();}
}
function liveAnswerHTML(question,text=''){
 return `<article class="reader-exchange live-exchange"><p class="reader-question">${esc(question)}</p><div class="reader-answer"><small class="live-status" role="status">답변 생성 중 · 근거 확인 중</small><p class="live-output"><span class="live-text">${esc(text)}</span><span class="typing-cursor" aria-hidden="true"></span></p></div></article>`;
}
function textPainter(findTarget,findScroll){
 let pending=[],frame=0,stopped=false,waiters=[];
 const finish=()=>{const list=waiters;waiters=[];list.forEach(resolve=>resolve());};
 const tick=()=>{frame=0;if(stopped)return;const target=findTarget();if(!target){pending=[];finish();return;}const scroll=findScroll?.(),follow=scroll&&scroll.scrollHeight-scroll.scrollTop-scroll.clientHeight<65;
  const count=matchMedia('(prefers-reduced-motion:reduce)').matches?pending.length:Math.max(1,Math.ceil(pending.length/6));
  const text=pending.splice(0,count).join('');if(!target.firstChild)target.appendChild(document.createTextNode(''));target.firstChild.appendData(text);
  if(follow)scroll.scrollTop=scroll.scrollHeight;
  if(pending.length)frame=requestAnimationFrame(tick);else finish();
 };
 return {push(text){if(stopped)return;pending.push(...Array.from(text));if(!frame)frame=requestAnimationFrame(tick);},drain(){return pending.length?new Promise(resolve=>waiters.push(resolve)):Promise.resolve();},stop(){stopped=true;cancelAnimationFrame(frame);pending=[];finish();}};
}
