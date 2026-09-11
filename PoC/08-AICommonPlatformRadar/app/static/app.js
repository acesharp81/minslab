const toast = (message, error = false) => {
  const element = document.querySelector('[data-toast]');
  element.textContent = message;
  element.classList.toggle('error', error);
  element.classList.add('show');
  window.setTimeout(() => element.classList.remove('show'), 3200);
};

const request = async (url, options = {}) => {
  const token = window.localStorage.getItem('radar-admin-token');
  const headers = {'Content-Type': 'application/json', ...(options.headers || {})};
  if (token) headers.Authorization = `Bearer ${token}`;
  const response = await fetch(url, {...options, headers});
  if (response.status === 401 && !token) {
    const value = window.prompt('관리자 토큰이 설정되어 있다면 입력하세요. Basic Auth 사용 시 취소 후 브라우저 인증창을 이용하세요.');
    if (value) {
      window.localStorage.setItem('radar-admin-token', value);
      return request(url, options);
    }
  }
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(payload.detail || `요청 실패 (${response.status})`);
  return payload;
};

document.querySelector('[data-run-collect]')?.addEventListener('click', async (event) => {
  const button = event.currentTarget;
  button.disabled = true;
  button.textContent = '수집 중…';
  try {
    const result = await request('/api/collect/run', {method: 'POST'});
    toast(`수집 ${result.received}건 · 분석 ${result.analyzed}건 완료`);
    window.setTimeout(() => window.location.reload(), 700);
  } catch (error) {
    toast(error.message, true);
  } finally {
    button.disabled = false;
    button.textContent = '지금 수집';
  }
});

document.querySelector('[data-analyze]')?.addEventListener('click', async (event) => {
  const button = event.currentTarget;
  button.disabled = true;
  try {
    await request(`/api/notices/${button.dataset.analyze}/analyze/deep`, {method: 'POST'});
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
    await request(`/api/actions/${form.dataset.actionForm}`, {
      method: 'PATCH', body: JSON.stringify(Object.fromEntries(fields.entries())),
    });
    toast('조치 상태와 메모를 저장했습니다.');
  } catch (error) {
    toast(error.message, true);
  }
});

for (const select of document.querySelectorAll('.filters select')) {
  const current = new URLSearchParams(window.location.search).get(select.name);
  if (current) select.value = current;
}

