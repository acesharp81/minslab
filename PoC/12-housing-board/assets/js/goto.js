/* 주소 이동 입력줄(지도 아래 가운데 어두운 유리 한 줄).
   글자(법정동·시군구 이름, 지번·도로명 주소)나 표준코드를 치면 /api/v1/codes/search 가 후보를 주고, 고르면 ?pnu= | ?bjd= | ?sgg= 로 지도를 다시 연다(/api/v1/resolve 가 해석).
   상태 4가지(어두운 유리 투명도가 다르다): idle 대기(.62) · active 입력 중(.88) · busy 이동 중(.88) · disabled 비활성(.46).
   순수 모델(reduce·view·searchUrl·rowsOf…)은 node --test 로 시험하고(tests/js/goto.test.cjs), DOM 은 mount 에서만 만진다.
   후보의 글자는 모두 textContent 로 넣는다(API 응답을 innerHTML 에 넣지 않는다). 스펙: docs/product/상황판-스펙.md 2.4 */
(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.GotoBar = api;
})(typeof self !== 'undefined' ? self : this, function () {
  'use strict';

  const MIN_Q = 2;
  const MAX_Q = 60;
  const DEBOUNCE_MS = 320;
  const RECENT_MAX = 5;
  const RECENT_KEY = 'jt.goto.recent';
  const TIER_LABEL = { bundle: '번들', req: '요청 시 조회', edge: '경계만' };
  const NOTICE = {
    none: '일치하는 곳이 없습니다. 장소 이름(하남시청)·동 이름·지번(장위동 68-37)·도로명을 입력해 보세요.',
    'unknown-code': '행정표준코드 표에 없는 코드입니다.',
    'bad-length': '코드는 시군구 5자리, 법정동 8·10자리, 필지(PNU) 19자리입니다.',
    'bad-pnu': 'PNU 형식이 맞지 않습니다(대지구분 1·2, 본번 0000 아님).',
    'unsupported-level': '시도 단위는 지도로 열 수 없습니다. 시군구 이하를 입력하세요.',
    'unknown-sido': '알 수 없는 시도 코드입니다.',
    'not-digits': '코드는 숫자만 쓸 수 있습니다.',
    short: '두 글자 이상 입력하세요.',
    help: '장소 이름(하남시청) · 동 이름 · 지번(장위동 68-37) · 도로명 · 법정동 코드(8·10자리) · PNU(19자리)를 입력할 수 있습니다.',
    failed: '검색을 불러오지 못했습니다. 잠시 뒤 다시 시도하세요.',
  };
  const WARN = { vworld: '주소 검색이 일시적으로 안 되어 이름 검색 결과만 보입니다.', budget: '주소 검색 호출 한도에 닿아 이름 검색 결과만 보입니다.', stan: '이름 검색이 일시적으로 안 되어 주소 결과만 보입니다.', 'vworld-key': '주소 검색 키가 없어 이름 검색 결과만 보입니다.' };
  const DISABLED_TEXT = {
    static: '이 서버에서는 주소 이동을 쓸 수 없습니다',
    config: '주소 이동이 설정되지 않았습니다',
    limit: '검색 한도에 닿았습니다. 잠시 뒤 다시 시도하세요',
  };
  const LOCAL_HINT = ' — 개발 서버(node scripts/dev.js)를 다시 시작하세요';   // 로컬에서 404 는 옛 서버가 새 경로를 모르는 경우가 대부분이다
  const PARAM = { pnu: 'pnu', bjd: 'bjd', sgg: 'sgg' };

  const normalize = (s) => String(s == null ? '' : s).replace(/\s+/g, ' ').trim();
  const isSearchable = (q) => q.length >= MIN_Q && q.length <= MAX_Q;
  /* near 는 지금 보는 지도 가운데(경도,위도). 약 5 km 격자로 맞춰 같은 동네에서는 같은 주소가 되게 한다(CDN 캐시가 겹침) */
  const nearOf = (c) => (Array.isArray(c) && c.length === 2 && c.every(Number.isFinite) ? `${(Math.round(c[0] * 20) / 20).toFixed(2)},${(Math.round(c[1] * 20) / 20).toFixed(2)}` : '');
  const searchUrl = (q, base, near) => `${base || 'api/v1/codes/search'}?q=${encodeURIComponent(q)}&limit=8${near ? `&near=${near}` : ''}`;

  /* 이름에서 친 글자가 걸린 구간(첫 낱말 시작 ~ 마지막 낱말 끝)을 굵게 표시하려고 나눈다. 못 찾으면 통째로 pre */
  function highlight(name, q) {
    const tokens = normalize(q).split(' ').filter(Boolean), text = String(name || '');
    const found = tokens.map((k) => ({ k, p: text.indexOf(k) })).filter((x) => x.p >= 0);
    if (!found.length) return { pre: text, hit: '', post: '' };
    const a = Math.min(...found.map((x) => x.p)), b = Math.max(...found.map((x) => x.p + x.k.length));
    return { pre: text.slice(0, a), hit: text.slice(a, b), post: text.slice(b) };
  }
  /* 후보 한 줄의 보조 글자 */
  function subText(item) {
    if (item.place) return [String(item.category || '').split(' > ').pop(), item.addr].filter(Boolean).join(' · ');   // 분류의 마지막 마디 + 도로명(없으면 지번) 주소
    if (item.kind === 'pnu') { const j = item.parts && item.parts.jibun; return j ? `번지 ${j} · 필지 경계로 이동` : '필지 경계로 이동'; }
    if (item.kind === 'sgg') return `시군구 ${item.code}`;
    return item.road ? `도로명 주소 · 법정동 ${item.code}` : `법정동 ${item.code}`;
  }
  const rowsOf = (items, q, sel) => items.map((it, i) => Object.assign({ id: `cmdO${i}`, index: i, selected: i === sel, kind: it.kind, sub: subText(it), tier: it.tier, tierLabel: TIER_LABEL[it.tier] || '' }, highlight(it.name, q)));

  /* 고른 후보를 "시도 › 시군구 · 코드 › 법정동 · 코드 › 번지" 칩으로 풀어 보여 준다(어디로 가는지 코드 단위로 확인) */
  function chipsOf(item) {
    if (!item) return [];
    const p = item.parts || {}, chips = [];
    if (p.sido) chips.push({ label: '시도', text: p.sido });
    if (p.sgg) chips.push({ label: '시군구', text: p.sgg, code: String(item.code).slice(0, 5) });
    if (p.umd) chips.push({ label: p.ri ? '읍면동' : '법정동', text: p.umd, code: p.ri ? '' : String(item.code).slice(0, 10) });
    if (p.ri) chips.push({ label: '리', text: p.ri, code: String(item.code).slice(0, 10) });
    if (p.road) chips.push({ label: '도로명', text: p.road });
    if (p.place) chips.push({ label: '장소', text: p.place, goal: '그 필지·좌표로 이동' });
    else if (p.jibun) chips.push({ label: '번지', text: p.jibun, goal: '필지로 이동' });
    else if (item.road) chips[chips.length - 1].goal = '법정동·좌표로 이동';
    else if (chips.length) chips[chips.length - 1].goal = item.kind === 'sgg' ? '시군구 경계로 이동' : '법정동으로 이동';
    return chips;
  }

  /* ---------- 상태 ---------- */
  const initialState = () => ({ mode: 'idle', q: '', items: [], sel: 0, searching: false, notice: '', warn: '', reason: '', wantGo: false, target: null });
  const goState = (s, item) => Object.assign({}, s, { mode: 'busy', target: item, wantGo: false, searching: false });
  const noticeOf = (meta, count, qn) => {
    if (count) return '';
    if (meta && meta.reason) return NOTICE[meta.reason] || meta.detail || NOTICE.none;
    return qn.length ? NOTICE.none : '';
  };

  /* 이벤트 → 새 상태(원본은 바꾸지 않는다). 검색 요청·이동은 mount 가 상태 변화를 보고 한다 */
  function reduce(s, e) {
    switch (e.type) {
      case 'focus': return s.mode === 'idle' ? Object.assign({}, s, { mode: 'active' }) : s;
      case 'blur': return s.mode === 'active' ? Object.assign({}, s, { mode: 'idle' }) : s;
      case 'input': {
        if (s.mode === 'disabled' || s.mode === 'busy') return s;
        const qn = normalize(e.q), ok = isSearchable(qn);
        return Object.assign({}, s, { mode: 'active', q: e.q, sel: 0, searching: ok, items: ok ? s.items : [], notice: '', warn: '', wantGo: false });
      }
      case 'results': {
        if (normalize(s.q) !== e.q || s.mode === 'disabled') return s;
        const items = Array.isArray(e.items) ? e.items : [], meta = e.meta || {};
        const next = Object.assign({}, s, { items, sel: 0, searching: false, notice: noticeOf(meta, items.length, e.q), warn: (meta.partial || []).map((k) => WARN[k]).filter(Boolean)[0] || '' });
        return s.wantGo && items.length ? goState(next, items[0]) : Object.assign(next, { wantGo: false });
      }
      case 'fail': {
        if (e.status === 404 || e.status === 405) return Object.assign({}, s, { mode: 'disabled', reason: 'static', searching: false, wantGo: false });
        if (e.status === 503) return Object.assign({}, s, { mode: 'disabled', reason: 'config', searching: false, wantGo: false });
        if (e.status === 429) return Object.assign({}, s, { mode: 'disabled', reason: 'limit', searching: false, wantGo: false, retryAfter: e.retryAfter || 30 });
        return Object.assign({}, s, { searching: false, wantGo: false, notice: NOTICE.failed });
      }
      case 'move': {
        const n = s.items.length;
        return n && s.mode === 'active' ? Object.assign({}, s, { sel: (s.sel + e.delta + n) % n }) : s;
      }
      case 'hover': return s.mode === 'active' && e.index >= 0 && e.index < s.items.length ? Object.assign({}, s, { sel: e.index }) : s;
      case 'submit': {
        if (s.mode === 'disabled' || s.mode === 'busy') return s;
        if (s.items.length) return goState(s, s.items[s.sel] || s.items[0]);
        if (s.searching) return Object.assign({}, s, { wantGo: true });
        const qn = normalize(s.q);
        return Object.assign({}, s, { mode: 'active', notice: qn.length < MIN_Q ? NOTICE.short : NOTICE.none });
      }
      case 'pick': return s.mode === 'active' && s.items[e.index] ? goState(s, s.items[e.index]) : s;
      case 'recent': return s.mode === 'idle' || s.mode === 'active' ? goState(s, e.item) : s;
      case 'clear': return s.mode === 'disabled' || s.mode === 'busy' ? s : Object.assign({}, s, { q: '', items: [], sel: 0, searching: false, notice: '', warn: '', wantGo: false, mode: s.mode });
      case 'escape': {
        if (s.mode !== 'active') return s;
        if (s.items.length || s.notice || s.searching || s.q === '') return Object.assign({}, s, { mode: 'idle', searching: false });   // 목록을 닫는다(글자는 남김)
        return reduce(s, { type: 'clear' });
      }
      case 'enable': return s.mode === 'disabled' && s.reason === 'limit' ? Object.assign({}, s, { mode: 'idle', reason: '', retryAfter: 0 }) : s;
      default: return s;
    }
  }

  /* 상태 → 화면에 그릴 것. panel: none | rows | recent | note | searching */
  function view(s, recent, opts) {
    const qn = normalize(s.q), active = s.mode === 'active', list = recent || [];
    const rows = s.items.length && qn ? rowsOf(s.items, qn, s.sel) : [];
    let panel = 'none', note = '';
    if (active) {
      if (rows.length) panel = 'rows';
      else if (!qn) { panel = list.length ? 'recent' : 'note'; note = NOTICE.help; }
      else if (s.searching) panel = 'searching';
      else if (s.notice) { panel = 'note'; note = s.notice; }
      else if (!isSearchable(qn)) { panel = 'note'; note = qn.length < MIN_Q ? NOTICE.short : NOTICE.none; }
    }
    const recentRows = panel === 'recent' ? list.map((it, i) => Object.assign({ id: `cmdO${i}`, index: i, selected: false, kind: it.kind, sub: subText(it), tier: it.tier, tierLabel: TIER_LABEL[it.tier] || '' }, { pre: it.name, hit: '', post: '' })) : [];
    const chosen = panel === 'rows' ? s.items[s.sel] : null;
    return {
      mode: s.mode, panel, rows: panel === 'recent' ? recentRows : rows, note, warn: panel === 'rows' ? s.warn : '', chips: chipsOf(chosen),
      canGo: active && s.items.length > 0, clear: !!s.q && s.mode !== 'disabled', key: s.mode === 'idle' && !s.q, busy: s.mode === 'busy',
      disabled: s.mode === 'disabled', placeholder: s.mode === 'disabled' ? (DISABLED_TEXT[s.reason] || DISABLED_TEXT.static) + (s.reason === 'static' && opts && opts.local ? LOCAL_HINT : '') : '주소·법정동·단지 또는 코드 입력',
      stale: panel === 'rows' && s.searching, active: s.mode === 'active' && s.items.length > 0 ? `cmdO${s.sel}` : '', status: panel === 'rows' ? `후보 ${rows.length}곳` : panel === 'searching' ? '찾는 중' : '',
    };
  }

  /* 후보를 지도 주소로: 코드 매개변수를 이 후보 하나로 바꾸고(region·block·at 은 지움) 도로명 후보는 좌표로 가까이 간다 */
  function gotoParams(item) {
    const out = { name: PARAM[item.kind], value: String(item.code) };
    if ((item.road || item.place) && Array.isArray(item.point) && item.point.length === 2) out.at = `${item.point[0]},${item.point[1]},17.5`;   // 도로명·장소는 그 좌표로 가까이
    return out;
  }

  /* ---------- 최근 이동(localStorage, 이 브라우저에만) ---------- */
  function loadRecent(win) {
    try {
      const v = JSON.parse(win.localStorage.getItem(RECENT_KEY) || '[]');
      return Array.isArray(v) ? v.filter((x) => x && PARAM[x.kind] && x.code && x.name).slice(0, RECENT_MAX) : [];
    } catch (e) { return []; }
  }
  function saveRecent(win, item) {
    try {
      const keep = { kind: item.kind, code: item.code, name: item.name, parts: item.parts || {}, tier: item.tier };
      if (item.road) { keep.road = true; keep.point = item.point; }
      if (item.place) { keep.place = true; keep.point = item.point; keep.category = item.category; keep.addr = item.addr; }
      const list = [keep, ...loadRecent(win).filter((x) => !(x.kind === item.kind && x.code === item.code && !!x.road === !!item.road && (!item.place || x.name === item.name)))].slice(0, RECENT_MAX);
      win.localStorage.setItem(RECENT_KEY, JSON.stringify(list));
    } catch (e) { /* 저장을 못 해도 이동은 된다 */ }
  }

  /* ---------- DOM 연결 ---------- */
  const ICON = {
    pin: '<svg viewBox="0 0 20 20" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.6" aria-hidden="true"><path d="M10 18s6-5.2 6-9.5a6 6 0 1 0-12 0C4 12.8 10 18 10 18Z"/><circle cx="10" cy="8.5" r="2.2"/></svg>',
    area: '<svg viewBox="0 0 20 20" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.6" aria-hidden="true"><path d="M3.5 6.5 10 3l6.5 3.5v7L10 17l-6.5-3.5Z"/></svg>',
    recent: '<svg viewBox="0 0 20 20" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.6" aria-hidden="true"><circle cx="10" cy="10" r="7"/><path d="M10 6v4.4l3 1.8"/></svg>',
  };
  function mount(win, doc, opts) {
    const o = opts || {}, $ = (id) => doc.getElementById(id);
    const el = { root: $('cmd'), form: $('cmdForm'), input: $('cmdIn'), res: $('cmdRes'), parse: $('cmdParse'), clear: $('cmdClear'), go: $('cmdGo'), sr: $('sr') };
    if (!el.root || !el.form || !el.input || !el.res) return null;
    const RL = o.RegionLoader || win.RegionLoader, fetchFn = o.fetch || ((...a) => win.fetch(...a));
    const local = /^(localhost|127\.0\.0\.1|\[::1\])$/.test((win.location && win.location.hostname) || '');
    const nearNow = () => nearOf(typeof win.getMapCenter === 'function' ? win.getMapCenter() : null);   // app.js 가 알려 주는 지금 지도 가운데
    const state = { s: initialState(), recent: loadRecent(win), cache: new Map(), timer: null, ctl: null, retry: null, lastStatus: '' };
    el.root.closest('.mapwrap') && el.root.closest('.mapwrap').classList.add('hascmd');
    const pv = $('pvBanner'); if (pv) el.root.appendChild(pv);   // 지역 안내 띠는 입력줄 아래 요약 한 줄로(2026-10-10 피드백). 입력줄이 없으면 지도 위쪽 그대로

    const make = (tag, cls, text) => { const n = doc.createElement(tag); if (cls) n.className = cls; if (text != null) n.textContent = text; return n; };
    function renderRow(r, withHeader) {
      const row = make('div', 'cmd-o'); row.id = r.id; row.setAttribute('role', 'option'); row.setAttribute('aria-selected', r.selected ? 'true' : 'false'); row.dataset.index = String(r.index);
      const ic = make('span', 'cmd-ic'); ic.innerHTML = withHeader === 'recent' ? ICON.recent : r.kind === 'sgg' ? ICON.area : ICON.pin;   // 고정 SVG 문자열만 innerHTML
      const main = make('span', 'cmd-m'), t = make('span', 'cmd-t');
      t.appendChild(make('span', null, r.pre)); if (r.hit) t.appendChild(make('b', null, r.hit)); if (r.post) t.appendChild(make('span', null, r.post));
      main.appendChild(t); main.appendChild(make('span', 'cmd-s', r.sub));
      const tier = make('span', 'cmd-tier'); tier.appendChild(make('i', `sw-${r.tier}`)); tier.appendChild(doc.createTextNode(r.tierLabel));
      row.appendChild(ic); row.appendChild(main); row.appendChild(tier);
      return row;
    }
    function render() {
      const v = view(state.s, state.recent, { local }), s = state.s;
      el.root.dataset.state = v.mode; el.root.classList.toggle('has-q', !!s.q);
      el.input.disabled = v.disabled; el.input.readOnly = v.busy; el.input.placeholder = v.placeholder; el.input.setAttribute('aria-busy', v.busy ? 'true' : 'false');
      const shown = v.disabled ? '' : s.q;   // 비활성이면 글자를 가리고 이유(자리표시)를 보인다. 풀리면 친 글자가 돌아온다
      if (el.input.value !== shown) el.input.value = shown;
      el.input.setAttribute('aria-expanded', v.panel === 'rows' || v.panel === 'recent' ? 'true' : 'false');
      if (v.active) el.input.setAttribute('aria-activedescendant', v.active); else el.input.removeAttribute('aria-activedescendant');
      if (v.disabled) el.input.title = v.placeholder; else el.input.removeAttribute('title');
      el.clear.hidden = !v.clear || v.busy; el.go.disabled = !v.canGo; el.go.hidden = v.disabled;
      const key = el.root.querySelector('.cmd-key'); if (key) key.hidden = !v.key;
      el.res.textContent = ''; el.res.hidden = v.panel === 'none'; el.res.dataset.stale = v.stale ? '1' : '';
      if (v.panel === 'rows' || v.panel === 'recent') {
        el.res.appendChild(make('div', 'cmd-h', v.panel === 'recent' ? '최근 이동' : '일치'));
        for (const r of v.rows) el.res.appendChild(renderRow(r, v.panel));
        if (v.warn) el.res.appendChild(make('div', 'cmd-w', v.warn));
      } else if (v.panel === 'searching') el.res.appendChild(make('div', 'cmd-n', '찾는 중…'));
      else if (v.panel === 'note') el.res.appendChild(make('div', 'cmd-n', v.note));
      el.res.setAttribute('role', v.panel === 'rows' || v.panel === 'recent' ? 'listbox' : 'status');
      el.parse.textContent = ''; el.parse.hidden = !v.chips.length;
      v.chips.forEach((c, i) => {
        if (i) el.parse.appendChild(make('span', 'cmd-sep', '›'));
        const chip = make('span', i === v.chips.length - 1 ? 'cmd-chip last' : 'cmd-chip'); chip.appendChild(make('i', null, c.label)); chip.appendChild(make('b', null, [c.text, c.code, c.goal ? `→ ${c.goal}` : ''].filter(Boolean).join(' ')));
        el.parse.appendChild(chip);
      });
      const sel = el.res.querySelector('[aria-selected="true"]'); if (sel && sel.scrollIntoView) sel.scrollIntoView({ block: 'nearest' });
      if (el.sr && v.status && v.status !== state.lastStatus) el.sr.textContent = v.status;
      state.lastStatus = v.status;
    }
    function go(item) {
      saveRecent(win, item);
      const p = gotoParams(item);
      win.location.assign(RL.codeUrl(win.location.href, p.name, p.value, p.at));
    }
    function search(qn) {
      const near = nearNow(), ck = `${qn}|${near}`;
      if (state.cache.has(ck)) return dispatch({ type: 'results', q: qn, items: state.cache.get(ck).items, meta: state.cache.get(ck).meta });
      if (state.ctl) state.ctl.abort();
      const ctl = typeof win.AbortController === 'function' ? new win.AbortController() : null; state.ctl = ctl;
      Promise.resolve().then(() => fetchFn(searchUrl(qn, undefined, near), ctl ? { signal: ctl.signal } : undefined)).then(async (res) => {
        if (!res.ok) return dispatch({ type: 'fail', status: res.status, retryAfter: Number(res.headers && res.headers.get && res.headers.get('retry-after')) || 0 });
        const data = await res.json();
        if (!data || !Array.isArray(data.items)) return dispatch({ type: 'fail', status: 0 });
        state.cache.set(ck, { items: data.items, meta: data.meta || {} });
        return dispatch({ type: 'results', q: qn, items: data.items, meta: data.meta || {} });
      }).catch((e) => { if (e && e.name === 'AbortError') return null; return dispatch({ type: 'fail', status: 0 }); });
    }
    function dispatch(ev) {
      const prev = state.s;
      state.s = reduce(prev, ev);
      if (ev.type === 'input') {
        clearTimeout(state.timer);
        const qn = normalize(state.s.q);
        if (state.s.searching) state.timer = setTimeout(() => search(qn), state.cache.has(`${qn}|${nearNow()}`) ? 0 : DEBOUNCE_MS);
        else if (state.ctl) { state.ctl.abort(); state.ctl = null; }
      }
      if (state.s.mode === 'disabled' && prev.mode !== 'disabled' && state.s.reason === 'limit') { clearTimeout(state.retry); state.retry = setTimeout(() => dispatch({ type: 'enable' }), Math.min(60, state.s.retryAfter || 30) * 1000); }
      render();
      if (state.s.mode === 'busy' && prev.mode !== 'busy' && state.s.target) go(state.s.target);
      return state.s;
    }

    el.input.addEventListener('focus', () => dispatch({ type: 'focus' }));
    el.input.addEventListener('blur', () => { setTimeout(() => { if (doc.activeElement !== el.input) dispatch({ type: 'blur' }); }, 120); });   // 후보를 누를 시간을 주고, 다시 포커스를 받았으면 닫지 않는다
    el.input.addEventListener('input', () => dispatch({ type: 'input', q: el.input.value }));
    el.input.addEventListener('keydown', (e) => {
      if (e.key === 'ArrowDown' || e.key === 'ArrowUp') { if (state.s.items.length) { e.preventDefault(); dispatch({ type: 'move', delta: e.key === 'ArrowDown' ? 1 : -1 }); } }
      else if (e.key === 'Escape') { dispatch({ type: 'escape' }); if (state.s.mode === 'idle') el.input.blur(); }
    });
    el.form.addEventListener('submit', (e) => {
      e.preventDefault();
      if (state.s.mode === 'active' && !state.s.items.length && !state.s.searching && state.s.q === '' && state.recent.length) return;
      dispatch({ type: 'submit' });
    });
    el.clear.addEventListener('click', () => { dispatch({ type: 'clear' }); el.input.focus(); });
    el.res.addEventListener('mousedown', (e) => e.preventDefault());   // 후보를 눌러도 입력줄이 포커스를 잃지 않게
    el.res.addEventListener('mousemove', (e) => { const row = e.target.closest && e.target.closest('.cmd-o'); if (row && state.s.mode === 'active' && state.s.items.length) dispatch({ type: 'hover', index: Number(row.dataset.index) }); });
    el.res.addEventListener('click', (e) => {
      const row = e.target.closest && e.target.closest('.cmd-o'); if (!row) return;
      const i = Number(row.dataset.index);
      if (view(state.s, state.recent).panel === 'recent') dispatch({ type: 'recent', item: state.recent[i] }); else dispatch({ type: 'pick', index: i });
    });
    doc.addEventListener('keydown', (e) => {   // / 키로 입력줄에 바로 간다(다른 입력 중이거나 조합키가 있으면 건드리지 않음)
      const t = e.target, typing = t && (t.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName || ''));
      if (e.key === '/' && !typing && !e.ctrlKey && !e.metaKey && !e.altKey && state.s.mode !== 'disabled') { e.preventDefault(); el.input.focus(); }
    });
    render();
    el.root.hidden = false;
    const handle = { dispatch, state: () => state.s, view: () => view(state.s, state.recent, { local }), el };
    if (/[?&]selftest\b/.test(win.location.search || '')) win.__goto = handle;   // 시험 전용 훅(운영 주소에는 붙지 않음)
    return handle;
  }

  return { MIN_Q, MAX_Q, DEBOUNCE_MS, RECENT_KEY, NOTICE, DISABLED_TEXT, LOCAL_HINT, normalize, isSearchable, nearOf, searchUrl, highlight, subText, rowsOf, chipsOf, initialState, reduce, view, gotoParams, loadRecent, saveRecent, mount };
});
