/* The guide embeds the real UI with isolated synthetic data, never the user's workspace. */
const tourSteps=[
 {title:'업무자료를 등록하세요',description:'실제 업무자료 화면입니다. 파일이나 ZIP을 올린 뒤 초안을 생성합니다. 같은 파일명의 여러 판본도 함께 등록할 수 있습니다.',hint:'밝은 자료 등록 영역을 누르면 등록을 가상으로 마치고 다음 단계로 이동합니다.'},
 {title:'같은 업무를 묶고 검토하세요',description:'실제 초안 검토 화면과 동일합니다. 업무 전체 보고 묶기를 눌러 팝업을 열고, 카드를 같은 업무로 끌어 놓아 보세요.',hint:'묶음 저장은 가상으로 처리됩니다. 위·아래 끝에 카드를 가져가면 목록이 자동 스크롤됩니다.'},
 {title:'보고서를 확인하고 확정하세요',description:'실제 보고서 화면입니다. 목차·진척 차트·원문 근거를 확인하고, 검토 완료·확정하기를 누릅니다.',hint:'이 안내에는 합성 보고서가 표시됩니다. 확정 버튼을 누르면 인계하기 단계로 넘어갑니다.'},
 {title:'의견과 함께 최종본을 인계하세요',description:'변경 이력 오른쪽의 인계하기에서 받을 직원과 확정 판본을 확인합니다. 우선 처리할 일과 전달 의견을 적고 인계합니다.',hint:'전달 의견 입력과 확인 체크를 연습할 수 있습니다. 실제 인계 기록은 만들지 않습니다.'},
 {title:'받은 의견을 읽고 인수 확인하세요',description:'인수자도 같은 최종 보고서와 전달 의견을 확인합니다. 내용을 읽고 인수 확인을 누르면 인수인계가 완료됩니다.',hint:'가상 체험입니다. 실제 자료·직원 선택·보고서·전달 상태는 바뀌지 않습니다.'}
];
function startTour(index){
 if(index>=tourSteps.length){closeDialog();toast('사용 안내를 마쳤습니다. 새 인수인계 또는 시연 메뉴에서 시작해 보세요.');return;}
 index=Math.max(0,index);state.tourStep=index;const step=tourSteps[index];
 const url=new URL('.',location.href);url.searchParams.set('walkthrough',index);
 modal('처음이라면 이렇게 시작하세요','실제 화면 구성으로 따라 하는 5단계 · 합성 자료로 가상 진행',`<div class="tour-layout tour-real-layout"><div class="tour-real-scene"><iframe class="tour-live-frame" title="${index+1}단계 실제 구성 가상 화면" src="${esc(url.href)}"></iframe></div><aside class="tour-explanation" aria-live="polite"><span class="tour-step-count">STEP 0${index+1} / 05</span><div class="tour-dots">${tourSteps.map((_,i)=>`<i class="${i===index?'active':i<index?'done':''}"></i>`).join('')}</div><h3>${step.title}</h3><p>${step.description}</p><small>${step.hint}</small></aside></div>`,(index?button('tour-prev','← 이전'):button('close','닫기'))+button('tour-next',index===4?'안내 마치기':'다음 단계 →','primary'));
 $('#dialog').classList.add('tour-dialog');
}
document.addEventListener('DOMContentLoaded',()=>window.addEventListener('message',event=>{
 const frame=document.querySelector('.tour-live-frame');
 if(event.origin!==location.origin||!frame||event.source!==frame.contentWindow||event.data?.type!=='handover-tour-next')return;
 startTour((state.tourStep||0)+1);
}));
