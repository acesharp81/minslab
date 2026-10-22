(() => {
  const embedded = new URLSearchParams(location.search).get('embedded') === '1';
  if (embedded) {
    document.body.classList.add('is-embedded');
    document.querySelector('.guide-brand').removeAttribute('href');
    document.querySelector('.guide-toolbar nav a:last-child').hidden = true;
    document.addEventListener('keydown', (event) => {
      if (event.key === 'Escape') {
        if (document.querySelector('#guideImageDialog')?.open) {
          event.preventDefault();
          document.querySelector('#guideImageDialog').close();
        } else if (window.parent !== window) {
          event.preventDefault();
          window.parent.document.querySelector('#userGuideDialog')?.close();
        }
      }
    });
  }
  const imageDialog = document.querySelector('#guideImageDialog');
  document.querySelectorAll('figure a').forEach((link) => {
    link.addEventListener('click', (event) => {
      event.preventDefault();
      const source = link.querySelector('img');
      const full = document.querySelector('#guideFullImage');
      full.src = source.src;
      full.alt = source.alt;
      imageDialog.showModal();
    });
  });
  document.querySelector('#guideImageClose').addEventListener('click', () => imageDialog.close());
  const toc = document.querySelector('.guide-toc');
  const tocToggle = document.querySelector('#guideTocToggle');
  tocToggle.addEventListener('click', () => {
    const expanded = toc.classList.toggle('is-open');
    tocToggle.setAttribute('aria-expanded', String(expanded));
  });
  const pages = [...document.querySelectorAll('[data-page]')];
  const links = [...document.querySelectorAll('[data-page-link]')];
  const previous = document.querySelector('#guidePrev');
  const next = document.querySelector('#guideNext');
  let current = 1;
  function showPage() {
    const number = Number(location.hash.replace('#page-', '')) || 1;
    current = Math.min(pages.length, Math.max(1, number));
    for (const page of pages) page.hidden = Number(page.dataset.page) !== current;
    for (const link of links) {
      if (Number(link.dataset.pageLink) === current) link.setAttribute('aria-current', 'page');
      else link.removeAttribute('aria-current');
    }
    previous.disabled = current === 1;
    next.disabled = current === pages.length;
    document.querySelector('#guidePageStatus').textContent = `${current} / ${pages.length}`;
    document.title = `${current}쪽 · 국정ON 사용자 매뉴얼`;
    window.scrollTo({top: 0, behavior: 'instant'});
  }
  previous.addEventListener('click', () => { location.hash = `page-${current - 1}`; });
  next.addEventListener('click', () => { location.hash = `page-${current + 1}`; });
  document.querySelector('#guidePrint').addEventListener('click', () => window.print());
  window.addEventListener('hashchange', () => {
    toc.classList.remove('is-open');
    tocToggle.setAttribute('aria-expanded', 'false');
    showPage();
  });
  let originalTitle = document.title;
  window.addEventListener('beforeprint', () => { originalTitle = document.title; document.title = '국정ON 사용자 매뉴얼'; });
  window.addEventListener('afterprint', () => { document.title = originalTitle; });
  showPage();
})();
