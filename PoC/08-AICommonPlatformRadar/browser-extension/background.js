const JOB_KEY = 'poc08PendingOpinionJob';

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message?.type === 'START_OPINION_JOB') {
    const job = {
      ...message.job,
      sourceTabId: sender.tab?.id,
      status: '나라장터 시작 중',
      step: 'start',
      createdAt: Date.now(),
    };
    chrome.storage.local.set({[JOB_KEY]: job}).then(() =>
      chrome.tabs.create({url: 'https://www.g2b.go.kr/'}).then((tab) => {
        chrome.storage.local.set({[JOB_KEY]: {...job, g2bTabId: tab.id}});
        sendResponse({ok: true});
      })
    );
    return true;
  }

  if (message?.type === 'UPDATE_JOB') {
    chrome.storage.local.get(JOB_KEY).then((values) => {
      const job = values[JOB_KEY];
      if (job) chrome.storage.local.set({[JOB_KEY]: {...job, ...message.patch, updatedAt: Date.now()}});
      sendResponse({ok: Boolean(job)});
    });
    return true;
  }

  if (message?.type === 'OPINION_SUBMITTED') {
    chrome.storage.local.get(JOB_KEY).then(async (values) => {
      const job = values[JOB_KEY];
      if (!job) return sendResponse({ok: false});
      await chrome.storage.local.set({[JOB_KEY]: {...job, status: '의견 등록 완료', step: 'submitted'}});
      if (job.sourceTabId) {
        try {
          await chrome.tabs.sendMessage(job.sourceTabId, {
            type: 'OPINION_SUBMITTED_TO_POC08', actionId: job.actionId, noticeId: job.noticeId,
          });
        } catch (_error) {
          // PoC 탭이 닫힌 경우 상태는 확장프로그램에 남겨 수동 반영할 수 있다.
        }
      }
      sendResponse({ok: true});
    });
    return true;
  }

  if (message?.type === 'CANCEL_JOB') {
    chrome.storage.local.remove(JOB_KEY).then(() => sendResponse({ok: true}));
    return true;
  }
});
