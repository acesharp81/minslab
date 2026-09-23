const toast = (message, error = false) => {
  const element = document.querySelector('[data-toast]');
  element.textContent = message;
  element.classList.toggle('error', error);
  element.classList.add('show');
  window.setTimeout(() => element.classList.remove('show'), 3200);
};

const basePath = (document.body.dataset.basePath || '').replace(/\/$/, '');
const appUrl = (path) => `${basePath}${path}`;

const request = async (url, options = {}) => {
  const token = window.localStorage.getItem('radar-admin-token');
  const headers = {'Content-Type': 'application/json', ...(options.headers || {})};
  if (token) headers.Authorization = `Bearer ${token}`;
  const response = await fetch(url, {...options, headers});
  const payload = await response.json().catch(() => ({}));
  if (response.status === 401 && !token && payload.detail !== '홈페이지 관리자 로그인이 필요합니다.') {
    const value = window.prompt('관리자 토큰이 설정되어 있다면 입력하세요. Basic Auth 사용 시 취소 후 브라우저 인증창을 이용하세요.');
    if (value) {
      window.localStorage.setItem('radar-admin-token', value);
      return request(url, options);
    }
  }
  if (!response.ok) throw new Error(payload.detail || `요청 실패 (${response.status})`);
  return payload;
};

document.querySelector('[data-run-collect]')?.addEventListener('click', async (event) => {
  const button = event.currentTarget;
  button.disabled = true;
  button.textContent = '수집·후보판정 중…';
  try {
    const accepted = await request(appUrl('/api/collect/run'), {method: 'POST'});
    toast(accepted.message);
    const deadline = Date.now() + 2 * 60 * 60 * 1000;
    let started = false;
    while (Date.now() < deadline) {
      await new Promise((resolve) => window.setTimeout(resolve, 3000));
      const status = await request(appUrl('/api/collect/status'));
      if (status.id !== accepted.previous_run_id) started = true;
      if (!started || status.state === 'running') {
        const stats = status.stats || {};
        button.textContent = stats.processed
          ? `처리 중 ${stats.processed}/${stats.received || '?'} · 판정 ${stats.analyzed || 0}`
          : '수집·후보판정 시작 중…';
        continue;
      }
      const stats = status.stats || {};
      const deferred = stats.analysis_deferred || 0;
      const failed = stats.analysis_failed || 0;
      toast(`후보 ${stats.rule_candidates || 0}건 · 판정 ${stats.analyzed || 0}건${deferred ? ` · 보류 ${deferred}건` : ''}${failed ? ` · 실패 ${failed}건` : ''}`, status.state !== 'ready');
      window.setTimeout(() => window.location.reload(), 1200);
      return;
    }
    throw new Error('백그라운드 처리가 2시간을 초과했습니다. 배치 상태를 확인하세요.');
  } catch (error) {
    toast(error.message, true);
  } finally {
    button.disabled = false;
    button.textContent = '지금 수집·판정';
  }
});

document.querySelector('[data-run-reparse]')?.addEventListener('click', async (event) => {
  const button = event.currentTarget;
  button.disabled = true;
  button.textContent = '재처리 시작 중…';
  try {
    const accepted = await request(appUrl('/api/maintenance/reparse'), {method: 'POST'});
    toast(accepted.message);
    const deadline = Date.now() + 20 * 60 * 1000;
    let started = false;
    while (Date.now() < deadline) {
      await new Promise((resolve) => window.setTimeout(resolve, 1500));
      const status = await request(appUrl('/api/maintenance/reparse/status'));
      if (status.id !== accepted.previous_run_id) started = true;
      if (!started || status.state === 'running') {
        button.textContent = '문서 오류 재처리 중…';
        continue;
      }
      if (status.state === 'failed') throw new Error(status.error || '재처리에 실패했습니다.');
      const stats = status.stats || {};
      toast(`재처리 ${stats.retried || 0}건 · 성공 ${stats.parsed || 0}건 · 실패 ${stats.failed || 0}건`);
      window.setTimeout(() => window.location.reload(), 700);
      return;
    }
    throw new Error('재처리 시간이 제한을 초과했습니다.');
  } catch (error) {
    toast(error.message, true);
    button.disabled = false;
    button.textContent = '문서 오류 재처리';
  }
});

document.querySelector('[data-report-generate]')?.addEventListener('click', async (event) => {
  const button = event.currentTarget;
  button.disabled = true;
  button.textContent = '재생성 중…';
  try {
    await request(appUrl('/api/reports/daily/generate'), {
      method: 'POST', body: JSON.stringify({report_date: button.dataset.reportGenerate}),
    });
    toast('현재 데이터로 일일 리포트를 갱신했습니다.');
    window.setTimeout(() => window.location.reload(), 500);
  } catch (error) {
    toast(error.message, true);
    button.disabled = false;
    button.textContent = '현재 데이터로 재생성';
  }
});

document.querySelector('[data-analyze]')?.addEventListener('click', async (event) => {
  const button = event.currentTarget;
  button.disabled = true;
  try {
    await request(appUrl(`/api/notices/${button.dataset.analyze}/analyze/deep`), {method: 'POST'});
    toast('근거 검증과 후보 판정을 갱신했습니다.');
    window.setTimeout(() => window.location.reload(), 500);
  } catch (error) {
    toast(error.message, true);
    button.disabled = false;
  }
});

for (const refreshButton of document.querySelectorAll('[data-refresh-opinions]')) refreshButton.addEventListener('click', async (event) => {
  const button = event.currentTarget;
  const originalText = button.textContent;
  button.disabled = true;
  button.textContent = '나라장터 확인 중…';
  try {
    const result = await request(appUrl(`/api/notices/${button.dataset.refreshOpinions}/opinions/refresh`), {method: 'POST'});
    toast(result.status_label || '의견 답변 상태를 갱신했습니다.');
    window.setTimeout(() => window.location.reload(), 500);
  } catch (error) {
    toast(error.message, true);
    button.disabled = false;
    button.textContent = originalText;
  }
});

document.querySelector('[data-mark-opinion-submitted]')?.addEventListener('click', async (event) => {
  const button = event.currentTarget;
  button.disabled = true;
  button.textContent = '등록 상태 확인 중…';
  try {
    const submission = await request(appUrl(`/api/actions/${button.dataset.markOpinionSubmitted}/opinion-submitted`), {
      method: 'POST',
    });
    const result = await request(appUrl(`/api/notices/${button.dataset.noticeId}/opinions/refresh`), {method: 'POST'});
    const mail = submission.notification;
    const message = mail?.sent
      ? '의견 등록을 반영하고 주소록에 이메일을 발송했습니다.'
      : mail?.reason === 'already_sent'
        ? '의견 등록을 반영했습니다. 이메일은 이미 발송되었습니다.'
        : `${result.status_label || '의견 등록 상태를 저장했습니다.'} 이메일 발송 설정을 확인해 주세요.`;
    toast(message, !mail?.sent && mail?.reason !== 'already_sent');
    window.setTimeout(() => window.location.reload(), 500);
  } catch (error) {
    toast(error.message, true);
    button.disabled = false;
    button.textContent = '의견 등록 완료로 표시';
  }
});

const actionForm = document.querySelector('[data-action-form]');
const syncIneligibleReasonField = (form) => {
  const status = form?.querySelector('[data-action-status]');
  const field = form?.querySelector('[data-ineligible-reason-field]');
  const select = field?.querySelector('select');
  if (!status || !field || !select) return;
  const visible = status.value === 'completed_ineligible';
  field.hidden = !visible;
  select.required = visible;
  select.disabled = !visible;
};
if (actionForm) {
  syncIneligibleReasonField(actionForm);
  actionForm.querySelector('[data-action-status]')?.addEventListener('change', () => syncIneligibleReasonField(actionForm));
}

actionForm?.addEventListener('submit', async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const fields = new FormData(form);
  try {
    const saved = await request(appUrl(`/api/actions/${form.dataset.actionForm}`), {
      method: 'PATCH', body: JSON.stringify(Object.fromEntries(fields.entries())),
    });
    toast(saved.classification_code === '6'
      ? '피드백을 반영해 비AI 사업으로 재분류했습니다.'
      : '조치 상태와 기록을 저장했습니다.');
    if (saved.classification_code === '6') window.setTimeout(() => window.location.reload(), 500);
  } catch (error) {
    toast(error.message, true);
  }
});

async function copyGuidance(selector) {
  const field = selector
    ? document.querySelector(selector)
    : document.querySelector('[data-guidance-text]');
  if (!field) return false;
  try {
    await navigator.clipboard.writeText(field.value || field.textContent || '');
    return true;
  } catch (_error) {
    if (typeof field.select === 'function') field.select();
    return false;
  }
}

for (const button of document.querySelectorAll('[data-copy-guidance], [data-copy-target]')) {
  button.addEventListener('click', async () => {
    const copied = await copyGuidance(button.dataset.copyTarget);
    toast(copied ? '조치 의견 문안을 복사했습니다.' : '문안을 선택했습니다. Ctrl+C로 복사하세요.');
  });
}

for (const button of document.querySelectorAll('[data-copy-open-target]')) {
  button.addEventListener('click', async () => {
    // 새 창 열기는 클릭 이벤트 안에서 즉시 실행해야 팝업 차단을 피할 수 있다.
    const destination = button.dataset.openUrl;
    const copyPromise = copyGuidance(button.dataset.copyOpenTarget);
    if (destination) window.open(destination, '_blank', 'noopener');
    const copied = await copyPromise;
    const registration = button.dataset.copyKind === 'registration-home';
    toast(registration
      ? (copied
        ? '등록번호를 복사했습니다. 발주 → 사전규격목록조회로 이동해 등록번호란에 붙여넣으세요.'
        : '나라장터 홈을 열었습니다. 발주 → 사전규격목록조회에서 등록번호를 직접 입력해 주세요.')
      : (copied
        ? '의견 문안을 복사하고 나라장터를 열었습니다. 입력란에 붙여넣으세요.'
        : '나라장터를 열었습니다. 선택된 문안을 Ctrl+C 후 붙여넣으세요.'));
  });
}

for (const select of document.querySelectorAll('.filters select')) {
  const current = new URLSearchParams(window.location.search).get(select.name);
  if (current) select.value = current;
}

const senderForm = document.querySelector('[data-opinion-sender-form]');
const updateSenderPreview = () => {
  if (!senderForm) return;
  const data = Object.fromEntries(new FormData(senderForm).entries());
  const preview = document.querySelector('[data-sender-preview]');
  if (!preview) return;
  const subject = data.organization && data.responsibility
    ? `${data.organization} '${data.responsibility}'을 담당하는`
    : (data.organization || data.responsibility || '');
  const person = [data.name, data.position].filter(Boolean).join(' ');
  const contact = data.phone ? `(${data.phone})` : '';
  const detail = [subject, person, contact].filter(Boolean).join(' ');
  preview.textContent = detail ? `안녕하세요. ${detail}입니다.` : '안녕하세요.';
};

senderForm?.addEventListener('input', updateSenderPreview);
senderForm?.addEventListener('submit', async (event) => {
  event.preventDefault();
  const button = senderForm.querySelector('button[type="submit"]');
  button.disabled = true;
  try {
    await request(appUrl('/api/settings/opinion-sender'), {
      method: 'PUT', body: JSON.stringify(Object.fromEntries(new FormData(senderForm).entries())),
    });
    updateSenderPreview();
    toast('자동입력 정보와 의견 문구 템플릿을 저장했습니다.');
  } catch (error) {
    toast(error.message, true);
  } finally {
    button.disabled = false;
  }
});

const notificationForm = document.querySelector('[data-notification-settings-form]');
notificationForm?.addEventListener('submit', async (event) => {
  event.preventDefault();
  const formData = new FormData(notificationForm);
  const payload = Object.fromEntries(formData.entries());
  payload.enabled = formData.has('enabled');
  payload.use_tls = formData.has('use_tls');
  payload.smtp_port = Number(payload.smtp_port || 587);
  payload.recipients = String(payload.recipients || '').split(/[,\n]/).map((item) => item.trim()).filter(Boolean);
  try {
    await request(appUrl('/api/settings/notifications'), {method: 'PUT', body: JSON.stringify(payload)});
    notificationForm.querySelector('[name="smtp_password"]').value = '';
    toast('의견등록 이메일 설정을 저장했습니다.');
  } catch (error) {
    toast(error.message, true);
  }
});

const errorDialog = document.querySelector('[data-classification-error-dialog]');
for (const button of document.querySelectorAll('[data-report-classification-error]')) {
  button.addEventListener('click', () => {
    errorDialog.querySelector('[name="notice_id"]').value = button.dataset.reportClassificationError;
    errorDialog.querySelector('[data-error-notice-title]').textContent = button.dataset.noticeTitle;
    errorDialog.querySelector('[name="reason"]').value = '';
    errorDialog.showModal();
  });
}
document.querySelector('[data-close-error-dialog]')?.addEventListener('click', () => errorDialog.close());
for (const button of document.querySelectorAll('[data-open-bid-contact]')) {
  button.addEventListener('click', () => {
    const dialog = document.getElementById(button.dataset.openBidContact);
    if (dialog?.showModal) dialog.showModal();
  });
}
document.querySelector('[data-classification-error-form]')?.addEventListener('submit', async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const noticeId = form.elements.notice_id.value;
  try {
    await request(appUrl(`/api/notices/${noticeId}/classification-error`), {
      method: 'POST', body: JSON.stringify({reason: form.elements.reason.value}),
    });
    errorDialog.close();
    toast('판정오류를 기록하고 해당 사업을 부적합으로 변경했습니다.');
    window.setTimeout(() => window.location.reload(), 700);
  } catch (error) {
    toast(error.message, true);
  }
});

for (const button of document.querySelectorAll('[data-extension-opinion], [data-extension-opinion-view]')) {
  button.addEventListener('click', () => {
    window.setTimeout(() => {
      if (document.documentElement.dataset.poc08ExtensionReady !== 'true') {
        toast('조달췤! 확장프로그램이 필요합니다. 상단의 확장프로그램 설치를 먼저 진행하세요.', true);
      }
    }, 250);
  });
}

window.addEventListener('message', async (event) => {
  if (event.source !== window || event.data?.source !== 'poc08-g2b-helper') return;
  if (event.data.type === 'opinion-submitted' && (event.data.actionId || event.data.noticeId)) {
    try {
      const endpoint = event.data.actionId
        ? `/api/actions/${event.data.actionId}/opinion-submitted`
        : `/api/notices/${event.data.noticeId}/opinion-submitted`;
      const result = await request(appUrl(endpoint), {method: 'POST'});
      const mail = result.notification;
      const message = mail?.sent
        ? '나라장터 의견 등록을 확인해 조치중으로 전환하고 주소록에 이메일을 발송했습니다.'
        : mail?.reason === 'already_sent'
          ? '나라장터 의견 등록을 확인했습니다. 이메일은 이미 발송되었습니다.'
          : '의견 등록을 조치중으로 반영했지만 이메일을 발송하지 못했습니다. 설정을 확인해 주세요.';
      toast(message, !mail?.sent && mail?.reason !== 'already_sent');
      window.setTimeout(() => window.location.reload(), 700);
    } catch (error) {
      toast(`의견은 등록됐지만 조치중 자동 반영에 실패했습니다: ${error.message}`, true);
    }
  }
});
