const JOB_SELECTOR = '[data-extension-opinion], [data-extension-opinion-view]';

function activateBridge() {
  if (!document.querySelector(JOB_SELECTOR)) return;
  document.documentElement.dataset.poc08ExtensionReady = 'true';
}

activateBridge();
new MutationObserver(activateBridge).observe(document.documentElement, {childList: true, subtree: true});

document.addEventListener('click', async (event) => {
  const button = event.target.closest(JOB_SELECTOR);
  if (!button) return;
  event.preventDefault();
  event.stopImmediatePropagation();
  const viewOnly = button.matches('[data-extension-opinion-view]');
  const guidance = document.querySelector(button.dataset.guidanceTarget)?.value || '';
  const basePath = (document.body.dataset.basePath || '').replace(/\/$/, '');
  let profile = {};
  try {
    const response = await fetch(`${basePath}/api/settings/opinion-sender`, {credentials: 'include'});
    if (!response.ok) throw new Error('설정 로그인이 필요합니다.');
    profile = await response.json();
  } catch (_error) {}
  const title = button.closest('.action-row')?.querySelector('.action-title')?.textContent?.trim()
    || document.querySelector('h1')?.textContent?.trim() || '';
  await chrome.runtime.sendMessage({
    type: 'START_OPINION_JOB',
    job: {
      noticeId: button.dataset.noticeId,
      actionId: button.dataset.actionId,
      registrationNo: button.dataset.registrationNo,
      title,
      guidance,
      profile,
      sourceUrl: location.href,
      mode: viewOnly ? 'view' : 'register',
    },
  });
  window.postMessage({source: 'poc08-g2b-helper', type: 'job-started'}, '*');
}, true);

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (message?.type === 'OPINION_SUBMITTED_TO_POC08') {
    window.postMessage({
      source: 'poc08-g2b-helper', type: 'opinion-submitted', actionId: message.actionId, noticeId: message.noticeId,
    }, '*');
    sendResponse({ok: true});
  }
});
