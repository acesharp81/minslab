const JOB_KEY = 'poc08PendingOpinionJob';
let job;
let stopped = false;
let saveClicked = false;
let lastSearchAt = 0;
let lastNavigationAt = 0;
let bridgeSequence = 0;
const bridgeRequests = new Map();

const textOf = (node) => (node?.textContent || node?.value || '').replace(/\s+/g, ' ').trim();
const visible = (node) => Boolean(node && node.getClientRects().length);
const interactable = (node) => {
  if (!visible(node)) return false;
  const style = getComputedStyle(node);
  const rect = node.getBoundingClientRect();
  return style.display !== 'none' && style.visibility !== 'hidden' && Number(style.opacity || 1) !== 0
    && rect.width > 0 && rect.height > 0
    && rect.bottom > 0 && rect.right > 0 && rect.top < innerHeight && rect.left < innerWidth;
};

function status(message, error = false) {
  let box = document.getElementById('poc08-g2b-helper');
  if (!box) {
    box = document.createElement('aside');
    box.id = 'poc08-g2b-helper';
    box.innerHTML = '<strong>조달체크 의견 도우미</strong><p></p><div><button data-poc08-complete>저장 완료 반영</button><button data-poc08-stop>중지</button></div>';
    Object.assign(box.style, {position:'fixed',right:'20px',bottom:'20px',zIndex:'2147483647',width:'320px',padding:'16px',borderRadius:'12px',background:'#102d2b',color:'#fff',boxShadow:'0 12px 35px #0005',font:'14px sans-serif'});
    box.querySelectorAll('button').forEach((button) => Object.assign(button.style, {marginRight:'6px',padding:'7px 10px',border:'0',borderRadius:'7px',cursor:'pointer'}));
    box.querySelector('[data-poc08-complete]').addEventListener('click', markSubmitted);
    box.querySelector('[data-poc08-stop]').addEventListener('click', () => { stopped = true; status('자동화를 중지했습니다.', true); });
    document.documentElement.appendChild(box);
  }
  box.querySelector('[data-poc08-complete]').style.display = job?.mode === 'view' ? 'none' : '';
  box.querySelector('p').textContent = message;
  box.style.background = error ? '#7a2727' : '#102d2b';
  chrome.runtime.sendMessage({type:'UPDATE_JOB', patch:{status:message}}).catch(() => {});
}

function candidatesByText(label) {
  return [...document.querySelectorAll('button,input[type="button"],input[type="submit"],a,span,div,td,th,label,li')]
    .filter((node) => visible(node) && textOf(node) === label)
    .sort((a, b) => a.children.length - b.children.length);
}

function activate(node) {
  if (!node) return false;
  node.scrollIntoView?.({block: 'center', inline: 'center'});
  for (const type of ['mouseover', 'mouseenter', 'mousedown', 'mouseup']) {
    node.dispatchEvent(new MouseEvent(type, {bubbles:true, cancelable:true, view:window}));
  }
  if (typeof node.click === 'function') node.click();
  else node.dispatchEvent(new MouseEvent('click', {bubbles:true, cancelable:true, view:window}));
  return true;
}

function clickText(...labels) {
  for (const label of labels) {
    const found = candidatesByText(label)[0];
    if (found) {
      const clickable = found.closest('button,a,[role="button"],li') || found;
      return activate(clickable);
    }
  }
  return false;
}

function dismissNoticePopup() {
  const noticeWindows = [...document.querySelectorAll('.w2window[role="dialog"], .w2popup_window[role="dialog"], [role="dialog"]')]
    .filter((node) => interactable(node) && /나라장터\s*공지사항/u.test(textOf(node)));
  const scope = noticeWindows.at(-1);
  if (!scope) return false;
  const closeButtons = [...scope.querySelectorAll('input[type="button"],button,a,[role="button"],span,.w2window_close')]
    .filter((node) => interactable(node) && (
      textOf(node) === '닫기'
      || node.value === '닫기'
      || node.classList.contains('w2window_close')
      || /닫기/u.test(node.getAttribute('aria-label') || '')
      || /닫기/u.test(node.getAttribute('title') || '')
    ));
  const close = closeButtons.at(-1);
  if (!close) return false;
  status(`나라장터 공지사항 창을 닫는 중입니다${noticeWindows.length > 1 ? ` (${noticeWindows.length}개)` : ''}.`);
  return activate(close.closest('button,a,[role="button"]') || close);
}

function dismissBlockingPopup() {
  const dialogs = [...document.querySelectorAll('.w2window[role="dialog"], .w2popup_window[role="dialog"], [role="dialog"]')]
    .filter(interactable);
  const messageDialog = dialogs.filter((node) => /안내\s*메시지/u.test(textOf(node))).at(-1);
  if (messageDialog) {
    const confirm = [...messageDialog.querySelectorAll('input[type="button"],button')]
      .find((button) => interactable(button) && (button.value === '확인' || textOf(button) === '확인'));
    if (confirm) {
      status('나라장터 안내 메시지를 확인하고 검색 조건을 복구합니다.');
      return activate(confirm);
    }
  }
  return dismissNoticePopup();
}

function fieldNearLabel(label, selector = 'input,textarea,select') {
  const labelNode = candidatesByText(label)[0];
  if (!labelNode) return null;
  for (const container of [labelNode.closest('tr'), labelNode.parentElement, labelNode.parentElement?.parentElement]) {
    const field = container?.querySelector(selector);
    if (field && visible(field)) return field;
  }
  return null;
}

function setField(field, value) {
  if (!field || value == null || value === '') return false;
  const prototype = field instanceof HTMLTextAreaElement ? HTMLTextAreaElement.prototype
    : field instanceof HTMLSelectElement ? HTMLSelectElement.prototype : HTMLInputElement.prototype;
  const setter = Object.getOwnPropertyDescriptor(prototype, 'value')?.set;
  if (setter) setter.call(field, value); else field.value = value;
  field.dispatchEvent(new Event('input', {bubbles:true}));
  field.dispatchEvent(new Event('change', {bubbles:true}));
  return true;
}

function setFieldReliable(field, value) {
  if (!field || value == null || value === '') return Promise.resolve(false);
  setField(field, value);
  if (!field.id) return Promise.resolve(true);
  const requestId = `poc08-${Date.now()}-${bridgeSequence += 1}`;
  return new Promise((resolve) => {
    const timer = window.setTimeout(() => {
      bridgeRequests.delete(requestId);
      resolve(false);
    }, 1200);
    bridgeRequests.set(requestId, (ok) => {
      window.clearTimeout(timer);
      resolve(Boolean(ok));
    });
    window.postMessage({
      source: 'poc08-g2b-isolated', type: 'set-component-value', requestId, id: field.id, value,
    }, '*');
  });
}

function registrationInput() {
  return fieldNearLabel('등록번호', 'input') || [...document.querySelectorAll('input')].find((input) => /bfSpecRgstNo|rgst.*no/i.test(`${input.id} ${input.name}`));
}

function clickRegistrationRow() {
  const registrationCell = [...document.querySelectorAll('td')]
    .find((item) => textOf(item) === job.registrationNo);
  const row = registrationCell?.closest('tr');
  if (!row) return false;
  const titleCell = [...row.querySelectorAll('td')]
    .find((cell) => visible(cell) && (cell.classList.contains('link_txt') || textOf(cell) === job.title));
  const target = titleCell || [...row.querySelectorAll('td')].find((cell) => visible(cell) && textOf(cell).includes(job.title));
  if (!target) return false;
  return activate(target);
}

function fieldByIdSuffix(suffix, fallbackLabel, selector = 'input,textarea,select') {
  return [...document.querySelectorAll(selector)].find((field) => visible(field) && field.id.endsWith(suffix))
    || (fallbackLabel ? fieldNearLabel(fallbackLabel, selector) : null);
}

async function waitForOtherOpinionField() {
  for (let attempt = 0; attempt < 8; attempt += 1) {
    const field = [...document.querySelectorAll('input,textarea')].find((item) => (
      visible(item) && /(?:etc.*opnn|opnn.*etc|etcOpinion|otherOpinion)/i.test(`${item.id} ${item.name}`)
    )) || fieldNearLabel('기타의견', 'input,textarea');
    if (field) return field;
    await new Promise((resolve) => window.setTimeout(resolve, 150));
  }
  return null;
}

async function fillOpinionForm() {
  const profile = job.profile || {};
  const password = profile.opinion_password || '';
  const title = `${job.title} 범정부 인공지능공통기반 이용 검토 요청`.slice(0, 180);
  const fields = [
    [fieldByIdSuffix('wq_uuid_3077', '제목', 'input'), title],
    [fieldByIdSuffix('iptOgdpNm', '소속', 'input'), profile.organization],
    [fieldByIdSuffix('ibxWrtrNm', '성명', 'input'), profile.name],
    [fieldByIdSuffix('ibxPicTlphNo', '전화번호', 'input'), profile.phone],
    [fieldByIdSuffix('ibxEml', '이메일', 'input'), profile.email],
    [fieldByIdSuffix('ibxPswd', '비밀번호', 'input'), password],
    [fieldByIdSuffix('sbxBfSpecOpnnKndCd', '사전규격 의견 구분', 'select'), profile.opinion_type],
  ];
  for (const [field, value] of fields) await setFieldReliable(field, value);
  const otherOpinion = await waitForOtherOpinionField();
  await setFieldReliable(otherOpinion, profile.other_opinion || '');
  await setFieldReliable(fieldByIdSuffix('txaAnsCn', null, 'textarea'), job.guidance);
  const privacy = [...document.querySelectorAll('input[type="checkbox"]')]
    .find((checkbox) => visible(checkbox) && checkbox.id.includes('cbxPvtInfoGtrgAgre'));
  if (privacy && !privacy.checked) activate(privacy);
  job.step = 'form_filled';
  status(password
    ? '입력을 완료했습니다. 내용을 확인하고 나라장터의 저장을 누르세요.'
    : '입력을 완료했습니다. 설정되지 않은 값은 빈칸으로 두었습니다. 확인 후 저장하세요.');
  await chrome.runtime.sendMessage({type:'UPDATE_JOB', patch:{step:'form_filled'}});
}

document.addEventListener('click', (event) => {
  const button = event.target.closest('button,a,input[type="button"],[role="button"]');
  const buttonText = textOf(button) || button?.value || '';
  if (!button || buttonText !== '저장' || !/사전규격\s*의견(?:관리)?\s*등록/u.test(textOf(document.body))) return;
  saveClicked = true;
  status('나라장터 응답을 확인하는 중입니다. 저장 성공 후 자동으로 조치중에 반영합니다.');
}, true);

async function markSubmitted() {
  if (!job || job.submitted) return;
  job.submitted = true;
  status('의견 등록 완료를 PoC 8에 반영하고 있습니다.');
  await chrome.runtime.sendMessage({type:'OPINION_SUBMITTED'});
  status('의견 등록 완료 · PoC 8 조치중 반영 요청 완료');
}

function inspectMessages() {
  const helperText = textOf(document.getElementById('poc08-g2b-helper'));
  const body = textOf(document.body).replace(helperText, '');
  if (saveClicked && /(정상적으로.{0,20}(등록|저장)|(등록|저장)(이|가)?\s*(완료|되었습니다))/u.test(body) && !/(에러|오류|실패)/u.test(body)) {
    markSubmitted();
  }
  if (/(입력,수정,삭제하는데 에러|조회하는데 에러|오류가 발생)/u.test(body)) {
    status('나라장터 오류가 표시됐습니다. 저장 완료로 처리하지 않았습니다.', true);
  }
}

async function advance() {
  if (stopped || !job) return;
  // 모달이 남은 상태에서 뒤쪽 메뉴나 검색 버튼을 누르면 나라장터가 잘못된
  // 검증 오류를 띄우므로 어떤 화면 처리보다 먼저 최상위 팝업을 제거한다.
  if (dismissBlockingPopup()) return;
  const body = textOf(document.body);
  if (/사전규격\s*의견(?:관리)?\s*등록/u.test(body)) {
    if (job.step !== 'form_filled') await fillOpinionForm();
    return;
  }
  if (body.includes('사전규격상세조회')) {
    if (job.mode === 'view') {
      stopped = true;
      job.step = 'view_opened';
      status('해당 사전규격을 열었습니다. 화면의 등록 의견과 답변 현황을 확인하세요.');
      await chrome.runtime.sendMessage({type:'UPDATE_JOB', patch:{step:'view_opened'}});
      return;
    }
    status('상세 화면에서 의견등록을 여는 중입니다.');
    if (Date.now() - lastNavigationAt > 2500) {
      lastNavigationAt = Date.now();
      const opinionButton = document.getElementById('mf_wfm_container_btnOpnnReg')
        || [...document.querySelectorAll('input[type="button"],button')]
          .find((button) => visible(button) && (button.value === '의견등록' || textOf(button) === '의견등록'));
      if (!activate(opinionButton)) clickText('의견등록');
    }
    return;
  }
  const currentPreNoticeRadio = document.querySelector('input[type="radio"][title="사전규격공개"]');
  const currentBusinessName = document.getElementById('mf_wfm_container_txtBizNm')
    || [...document.querySelectorAll('input')].find((input) => input.title === '사업명');
  if (currentPreNoticeRadio && currentBusinessName) {
    document.getElementById('mf_wfm_gnb')?.classList.remove('menu-dpt2-show');
    if (!currentPreNoticeRadio.checked) {
      status('발주목록에서 사전규격공개를 선택합니다.');
      activate(currentPreNoticeRadio);
      return;
    }
    const startDate = document.querySelector('input[id$="ibxStrDay"]');
    const endDate = document.querySelector('input[id$="ibxEndDay"]');
    if (!startDate?.value || !endDate?.value) {
      const sixMonths = document.querySelector('input[type="radio"][title="6개월"]');
      status('비어 있는 검색기간을 최근 6개월로 설정합니다.');
      activate(sixMonths);
      return;
    }
    if (clickRegistrationRow()) {
      status('검색 결과에서 해당 사전규격을 여는 중입니다.');
      return;
    }
    if (Date.now() - lastSearchAt > 3500) {
      lastSearchAt = Date.now();
      status(`사업명으로 사전규격 ${job.registrationNo}를 검색합니다.`);
      await setFieldReliable(currentBusinessName, job.title);
      const search = document.getElementById('mf_wfm_container_btnS0001')
        || [...document.querySelectorAll('input[type="button"],button')].find((button) => visible(button) && (button.value === '검색' || textOf(button) === '검색'));
      activate(search);
    }
    return;
  }
  if (body.includes('사전규격목록조회')) {
    const input = registrationInput();
    if (body.includes(job.registrationNo)) {
      status('검색 결과에서 해당 사전규격을 여는 중입니다.');
      clickRegistrationRow();
      return;
    }
    if (input) {
      if (input.value !== job.registrationNo) setField(input, job.registrationNo);
      if (Date.now() - lastSearchAt > 3500) {
        lastSearchAt = Date.now();
        status(`등록번호 ${job.registrationNo}를 입력하고 조회합니다.`);
        clickText('조회', '검색');
      }
    }
    return;
  }
  status('나라장터 메뉴에서 발주 → 발주목록 → 사전규격공개로 이동하는 중입니다.');
  if (!clickText('발주목록', '사전규격목록조회', '사전규격 검색', '사전규격')) clickText('발주');
}

window.addEventListener('message', (event) => {
  if (event.source !== window || event.data?.source !== 'poc08-g2b-page') return;
  if (event.data.type === 'component-result') {
    const resolve = bridgeRequests.get(event.data.requestId);
    if (resolve) {
      bridgeRequests.delete(event.data.requestId);
      resolve(event.data.ok);
    }
    return;
  }
  if (event.data.type !== 'alert') return;
  const message = event.data.message || '';
  if (saveClicked && /(정상적으로.{0,20}(등록|저장)|(등록|저장)(이|가)?\s*(완료|되었습니다))/u.test(message) && !/(않|에러|오류|실패)/u.test(message)) markSubmitted();
  if (/(에러|오류|실패)/u.test(message)) status(`나라장터: ${message}`, true);
});

(async () => {
  const values = await chrome.storage.local.get(JOB_KEY);
  job = values[JOB_KEY];
  if (!job || ['submitted', 'view_opened'].includes(job.step) || Date.now() - job.createdAt > 24 * 60 * 60 * 1000) return;
  status(job.mode === 'view'
    ? `사전규격 ${job.registrationNo}의 등록 의견 현황을 찾습니다.`
    : `사전규격 ${job.registrationNo} 자동입력을 준비합니다.`);
  new MutationObserver(inspectMessages).observe(document.documentElement, {childList:true, subtree:true, characterData:true});
  window.setInterval(() => advance().catch((error) => status(`자동화 오류: ${error.message}`, true)), 1200);
  advance();
})();
