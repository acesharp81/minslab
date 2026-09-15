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

document.querySelector('[data-action-form]')?.addEventListener('submit', async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const fields = new FormData(form);
  try {
    await request(appUrl(`/api/actions/${form.dataset.actionForm}`), {
      method: 'PATCH', body: JSON.stringify(Object.fromEntries(fields.entries())),
    });
    toast('조치 상태와 메모를 저장했습니다.');
  } catch (error) {
    toast(error.message, true);
  }
});

for (const button of document.querySelectorAll('[data-copy-guidance], [data-copy-target]')) {
  button.addEventListener('click', async () => {
    const selector = button.dataset.copyTarget;
    const field = selector
      ? document.querySelector(selector)
      : document.querySelector('[data-guidance-text]');
    if (!field) return;
    try {
      await navigator.clipboard.writeText(field.value || field.textContent || '');
      toast('조치 의견 문안을 복사했습니다.');
    } catch (_error) {
      if (typeof field.select === 'function') field.select();
      toast('문안을 선택했습니다. Ctrl+C로 복사하세요.');
    }
  });
}

for (const select of document.querySelectorAll('.filters select')) {
  const current = new URLSearchParams(window.location.search).get(select.name);
  if (current) select.value = current;
}
