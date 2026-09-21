const JOB_KEY = 'poc08PendingOpinionJob';
const status = document.querySelector('[data-status]');
chrome.storage.local.get(JOB_KEY).then((values) => {
  const job = values[JOB_KEY];
  status.textContent = job ? `${job.registrationNo} · ${job.status}` : '진행 중인 의견 등록이 없습니다.';
});
document.querySelector('[data-cancel]').addEventListener('click', async () => {
  await chrome.runtime.sendMessage({type:'CANCEL_JOB'});
  status.textContent = '진행 작업을 취소했습니다.';
});
