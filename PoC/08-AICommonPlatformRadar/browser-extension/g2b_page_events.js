(() => {
  const originalAlert = window.alert;
  window.alert = function patchedAlert(message) {
    window.postMessage({source: 'poc08-g2b-page', type: 'alert', message: String(message || '')}, '*');
    return originalAlert.apply(this, arguments);
  };

  // 나라장터(WebSquare)는 DOM value만 바꾸면 내부 데이터 모델에 반영하지 않는다.
  // 격리된 content script가 지정한 실제 폼 필드만 WebSquare API로 동기화한다.
  window.addEventListener('message', (event) => {
    const data = event.data;
    if (event.source !== window || data?.source !== 'poc08-g2b-isolated' || data.type !== 'set-component-value') return;
    let ok = false;
    try {
      const element = document.getElementById(data.id);
      if (!element) throw new Error('field_not_found');
      const component = window.$p?.getComponentById?.(data.id);
      if (element instanceof HTMLSelectElement) {
        const option = [...element.options].find((item) => item.value === data.value || item.text === data.value);
        if (!option) throw new Error('option_not_found');
        element.selectedIndex = option.index;
        element.dispatchEvent(new Event('change', {bubbles: true}));
        ok = true;
      } else if (component && typeof component.setValue === 'function') {
        component.setValue(String(data.value ?? ''));
        ok = true;
      } else {
        const prototype = element instanceof HTMLTextAreaElement ? HTMLTextAreaElement.prototype
          : element instanceof HTMLSelectElement ? HTMLSelectElement.prototype : HTMLInputElement.prototype;
        const setter = Object.getOwnPropertyDescriptor(prototype, 'value')?.set;
        if (setter) setter.call(element, data.value ?? ''); else element.value = data.value ?? '';
        element.dispatchEvent(new Event('input', {bubbles: true}));
        element.dispatchEvent(new Event('change', {bubbles: true}));
        ok = true;
      }
    } catch (_error) {
      ok = false;
    }
    window.postMessage({
      source: 'poc08-g2b-page', type: 'component-result', requestId: data.requestId, ok,
    }, '*');
  });
})();
