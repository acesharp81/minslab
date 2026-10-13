'use strict';
/* assets/js/goto.js — 주소 이동 입력줄. 순수 모델(상태·후보 행·이동 주소)과 가짜 DOM 으로 본 연결, 정적 구조(HTML·CSS·로더)를 시험한다. */
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const G = require('../../assets/js/goto.js');
const R = require('../../assets/js/region.js');

const ROOT = path.join(__dirname, '..', '..');
const html = fs.readFileSync(path.join(ROOT, 'index.html'), 'utf8');
const css = fs.readFileSync(path.join(ROOT, 'assets/css/app.css'), 'utf8');

const ITEM_BJD = { code: '4145011400', kind: 'bjd', name: '경기도 하남시 감일동', parts: { sido: '경기도', sgg: '하남시', umd: '감일동' }, tier: 'req' };
const ITEM_PNU = { code: '1129013800100680037', kind: 'pnu', name: '서울특별시 성북구 장위동 68-37', parts: { sido: '서울특별시', sgg: '성북구', umd: '장위동', jibun: '68-37' }, tier: 'req', point: [127.05302, 37.612292] };
const ITEM_ROAD = { code: '4145011400', kind: 'bjd', name: '경기도 하남시 감일로15번길 78 (감일동)', parts: { sido: '경기도', sgg: '하남시', umd: '감일동', road: '감일로15번길 78' }, tier: 'req', point: [127.14546, 37.509897], road: true };
const ITEM_SGG = { code: '28245', kind: 'sgg', name: '인천광역시 계양구', parts: { sido: '인천광역시', sgg: '계양구' }, tier: 'bundle' };
const run = (events, s = G.initialState()) => events.reduce((st, e) => G.reduce(st, e), s);

test('searchUrl·normalize·isSearchable: 주소는 인코딩하고 공백을 정리하며 2~60자만 검색한다', () => {
  assert.equal(G.searchUrl('감일 동'), 'api/v1/codes/search?q=%EA%B0%90%EC%9D%BC%20%EB%8F%99&limit=8');
  assert.equal(G.searchUrl('x', 'https://h/api'), 'https://h/api?q=x&limit=8');
  assert.equal(G.normalize('  하남시   감일동 '), '하남시 감일동'); assert.equal(G.normalize(null), '');
  assert.deepEqual([G.isSearchable('가'), G.isSearchable('가나'), G.isSearchable('가'.repeat(60)), G.isSearchable('가'.repeat(61))], [false, true, true, false]);
});

test('highlight: 친 낱말이 걸린 구간(첫 낱말 시작~마지막 낱말 끝)을 나눈다. 못 찾으면 통째로 앞부분', () => {
  assert.deepEqual(G.highlight('경기도 하남시 감일동', '감일'), { pre: '경기도 하남시 ', hit: '감일', post: '동' });
  assert.deepEqual(G.highlight('경기도 하남시 감일동 100', '하남시 감일동 100'), { pre: '경기도 ', hit: '하남시 감일동 100', post: '' });
  assert.deepEqual(G.highlight('서울특별시 성북구 장위동', '없는말'), { pre: '서울특별시 성북구 장위동', hit: '', post: '' });
});

test('subText·rowsOf·chipsOf: 후보 한 줄의 보조 글자·강조·유형 글자, 고른 후보의 코드 단위 칩', () => {
  assert.equal(G.subText(ITEM_BJD), '법정동 4145011400'); assert.equal(G.subText(ITEM_PNU), '번지 68-37 · 필지 경계로 이동'); assert.equal(G.subText(ITEM_ROAD), '도로명 주소 · 법정동 4145011400'); assert.equal(G.subText(ITEM_SGG), '시군구 28245');
  const rows = G.rowsOf([ITEM_BJD, ITEM_PNU], '감일', 1);
  assert.deepEqual(rows.map((r) => [r.id, r.selected, r.kind, r.tierLabel, r.hit]), [['cmdO0', false, 'bjd', '요청 시 조회', '감일'], ['cmdO1', true, 'pnu', '요청 시 조회', '']]);
  assert.deepEqual(G.rowsOf([ITEM_SGG], '계양', 0)[0].tierLabel, '번들');
  assert.deepEqual(G.chipsOf(ITEM_PNU).map((c) => [c.label, c.text, c.code || '', c.goal || '']), [['시도', '서울특별시', '', ''], ['시군구', '성북구', '11290', ''], ['법정동', '장위동', '1129013800', ''], ['번지', '68-37', '', '필지로 이동']]);
  assert.equal(G.chipsOf(ITEM_BJD).slice(-1)[0].goal, '법정동으로 이동'); assert.equal(G.chipsOf(ITEM_SGG).slice(-1)[0].goal, '시군구 경계로 이동'); assert.equal(G.chipsOf(ITEM_ROAD).slice(-1)[0].goal, '법정동·좌표로 이동');
  assert.deepEqual(G.chipsOf(ITEM_ROAD).map((c) => c.label), ['시도', '시군구', '법정동', '도로명']);
  const ri = G.chipsOf({ code: '4373035027', kind: 'bjd', parts: { sido: '충청북도', sgg: '옥천군', umd: '청산면', ri: '장위리' } }); assert.deepEqual(ri.map((c) => c.label), ['시도', '시군구', '읍면동', '리']); assert.equal(ri[3].code, '4373035027');
  assert.deepEqual(G.chipsOf(null), []);
});

test('gotoParams·codeUrl: 후보를 지도 주소로(코드 매개변수 교체, region·block·at 삭제, 보던 상태는 유지, 도로명만 좌표를 붙임)', () => {
  assert.deepEqual(G.gotoParams(ITEM_PNU), { name: 'pnu', value: '1129013800100680037' });
  assert.deepEqual(G.gotoParams(ITEM_BJD), { name: 'bjd', value: '4145011400' }); assert.deepEqual(G.gotoParams(ITEM_SGG), { name: 'sgg', value: '28245' });
  assert.deepEqual(G.gotoParams(ITEM_ROAD), { name: 'bjd', value: '4145011400', at: '127.14546,37.509897,17.5' });
  const href = 'https://housing-board.vercel.app/?region=incheon-gyeyang&block=A6&mode=progress&sgg=28245&at=126.7,37.5,14&panel=1';
  assert.equal(R.codeUrl(href, 'bjd', '4145011400'), 'https://housing-board.vercel.app/?mode=progress&panel=1&bjd=4145011400');
  assert.equal(R.codeUrl(href, 'bjd', '4145011400', '127.1,37.5,17.5'), 'https://housing-board.vercel.app/?mode=progress&panel=1&bjd=4145011400&at=127.1%2C37.5%2C17.5');
  assert.equal(R.codeUrl('http://localhost:8000/?pnu=1&bjd=2&code=3', 'sgg', '28245'), 'http://localhost:8000/?sgg=28245');
});

test('상태: 대기 → 입력 중 → 후보 → 이동 중. 오래된 응답은 버리고 글자 길이에 따라 검색 여부가 정해진다', () => {
  let s = G.initialState(); assert.equal(s.mode, 'idle');
  s = run([{ type: 'focus' }], s); assert.equal(s.mode, 'active');
  s = run([{ type: 'input', q: '감' }], s); assert.deepEqual([s.mode, s.searching], ['active', false]);                      // 한 글자는 검색 안 함
  s = run([{ type: 'input', q: '감일' }], s); assert.equal(s.searching, true);
  const stale = G.reduce(s, { type: 'results', q: '감', items: [ITEM_PNU], meta: {} }); assert.equal(stale, s);              // 글자가 바뀐 뒤 늦게 온 응답
  s = run([{ type: 'results', q: '감일', items: [ITEM_BJD, ITEM_PNU], meta: {} }], s); assert.deepEqual([s.items.length, s.searching, s.notice, s.sel], [2, false, '', 0]);
  s = run([{ type: 'move', delta: 1 }], s); assert.equal(s.sel, 1); s = run([{ type: 'move', delta: 1 }], s); assert.equal(s.sel, 0); s = run([{ type: 'move', delta: -1 }], s); assert.equal(s.sel, 1);   // 순환
  s = run([{ type: 'hover', index: 0 }], s); assert.equal(s.sel, 0); assert.equal(G.reduce(s, { type: 'hover', index: 9 }), s);
  const go = G.reduce(s, { type: 'submit' }); assert.deepEqual([go.mode, go.target.code], ['busy', '4145011400']);               // 고른 줄(0번)로
  assert.equal(G.reduce(go, { type: 'input', q: 'x' }), go); assert.equal(G.reduce(go, { type: 'submit' }), go);              // 이동 중에는 입력·재제출 무시
  assert.equal(G.reduce(s, { type: 'pick', index: 1 }).target.code, '1129013800100680037'); assert.equal(G.reduce(s, { type: 'pick', index: 5 }), s);
  assert.equal(G.reduce(G.initialState(), { type: 'recent', item: ITEM_SGG }).target.kind, 'sgg');
});

test('상태: 후보가 없으면 이유 문구, 부분 실패 경고, 검색 중 Enter 는 결과가 오면 첫 후보로 이동', () => {
  let s = run([{ type: 'focus' }, { type: 'input', q: '없는곳이름' }, { type: 'results', q: '없는곳이름', items: [], meta: {} }]);
  assert.equal(s.notice, G.NOTICE.none);
  s = run([{ type: 'input', q: '12345' }, { type: 'results', q: '12345', items: [], meta: { reason: 'unknown-code' } }], s); assert.equal(s.notice, G.NOTICE['unknown-code']);
  s = run([{ type: 'input', q: '감일' }, { type: 'results', q: '감일', items: [ITEM_BJD], meta: { partial: ['vworld'] } }], s); assert.equal(s.warn, '주소 검색이 일시적으로 안 되어 이름 검색 결과만 보입니다.'); assert.equal(s.notice, '');
  const typing = run([{ type: 'focus' }, { type: 'input', q: '장위동' }, { type: 'submit' }]); assert.deepEqual([typing.mode, typing.wantGo], ['active', true]);   // 검색 중 Enter
  const arrived = G.reduce(typing, { type: 'results', q: '장위동', items: [ITEM_PNU, ITEM_BJD], meta: {} }); assert.deepEqual([arrived.mode, arrived.target.kind], ['busy', 'pnu']);
  const none = G.reduce(typing, { type: 'results', q: '장위동', items: [], meta: {} }); assert.deepEqual([none.mode, none.wantGo], ['active', false]);
  const empty = run([{ type: 'focus' }, { type: 'submit' }]); assert.equal(empty.notice, G.NOTICE.short);                                   // 빈 칸 Enter
});

test('상태: 서버가 없거나(404·405) 설정이 없거나(503) 한도(429)면 비활성. 한도는 시간이 지나면 풀리고 나머지는 그대로, 일시 오류는 입력 중에 문구만', () => {
  const base = run([{ type: 'focus' }, { type: 'input', q: '감일' }]);
  for (const [status, reason] of [[404, 'static'], [405, 'static'], [503, 'config'], [429, 'limit']]) {
    const d = G.reduce(base, { type: 'fail', status, retryAfter: 45 }); assert.deepEqual([d.mode, d.reason], ['disabled', reason], String(status));
    assert.equal(G.reduce(d, { type: 'input', q: '가나' }), d); assert.equal(G.reduce(d, { type: 'focus' }), d); assert.equal(G.reduce(d, { type: 'submit' }), d);   // 비활성은 입력·이동을 받지 않는다
    assert.equal(G.reduce(d, { type: 'enable' }).mode, reason === 'limit' ? 'idle' : 'disabled');
  }
  assert.equal(G.reduce(base, { type: 'fail', status: 429, retryAfter: 45 }).retryAfter, 45);
  const soft = G.reduce(base, { type: 'fail', status: 502 }); assert.deepEqual([soft.mode, soft.searching, soft.notice], ['active', false, G.NOTICE.failed]);
  assert.deepEqual([G.reduce(G.initialState(), { type: 'blur' }).mode, G.reduce(run([{ type: 'focus' }]), { type: 'blur' }).mode], ['idle', 'idle']);
});

test('상태: Esc 는 목록을 닫고(글자는 남김), 열 것이 없고 글자만 있으면 지운다. 지우기는 목록·알림을 비운다', () => {
  let s = run([{ type: 'focus' }, { type: 'input', q: '감일' }, { type: 'results', q: '감일', items: [ITEM_BJD], meta: {} }]);
  const closed = G.reduce(s, { type: 'escape' }); assert.deepEqual([closed.mode, closed.q], ['idle', '감일']);
  const one = run([{ type: 'focus' }, { type: 'input', q: '감' }]); const cleared = G.reduce(one, { type: 'escape' }); assert.deepEqual([cleared.mode, cleared.q], ['active', '']);   // 목록이 없어 글자를 지움
  assert.equal(G.reduce(G.initialState(), { type: 'escape' }).mode, 'idle');
  const c = G.reduce(s, { type: 'clear' }); assert.deepEqual([c.q, c.items.length, c.notice, c.mode], ['', 0, '', 'active']);
});

test('view: 상태별로 그릴 것(목록·최근·안내·찾는 중), 이동 가능 여부, 지우기·/ 키 힌트, 비활성 문구, 칩', () => {
  const recent = [ITEM_BJD, ITEM_SGG];
  const idle = G.view(G.initialState(), recent); assert.deepEqual([idle.mode, idle.panel, idle.key, idle.clear, idle.canGo, idle.disabled], ['idle', 'none', true, false, false, false]);
  const focus = G.view(run([{ type: 'focus' }]), recent); assert.deepEqual([focus.panel, focus.rows.length, focus.rows[0].pre], ['recent', 2, '경기도 하남시 감일동']);
  assert.equal(G.view(run([{ type: 'focus' }]), []).note, G.NOTICE.help); assert.equal(G.view(run([{ type: 'focus' }]), []).panel, 'note');
  const typing = run([{ type: 'focus' }, { type: 'input', q: '장위동' }]); const t = G.view(typing, recent); assert.deepEqual([t.panel, t.clear, t.key], ['searching', true, false]);
  const short = G.view(run([{ type: 'focus' }, { type: 'input', q: '가' }]), recent); assert.deepEqual([short.panel, short.note], ['note', G.NOTICE.short]);
  const got = run([{ type: 'results', q: '장위동', items: [ITEM_PNU, ITEM_BJD], meta: { partial: ['budget'] } }], typing);
  const v = G.view(got, recent); assert.deepEqual([v.panel, v.rows.length, v.canGo, v.active, v.status, v.stale, v.warn], ['rows', 2, true, 'cmdO0', '후보 2곳', false, G.view(got, []).warn]);
  assert.equal(v.warn, '주소 검색 호출 한도에 닿아 이름 검색 결과만 보입니다.'); assert.deepEqual(v.chips.map((c) => c.label), ['시도', '시군구', '법정동', '번지']);
  const again = G.view(run([{ type: 'input', q: '장위동 6' }], got), recent); assert.equal(again.stale, true);                              // 새 검색이 오는 동안 이전 목록은 흐리게
  const busy = G.view(G.reduce(got, { type: 'submit' }), recent); assert.deepEqual([busy.mode, busy.busy, busy.panel, busy.canGo], ['busy', true, 'none', false]);
  const off = G.view(G.reduce(got, { type: 'fail', status: 404 }), recent); assert.deepEqual([off.disabled, off.panel, off.placeholder, off.clear], [true, 'none', G.DISABLED_TEXT.static, false]);   // 비활성은 지우기도 숨긴다
  const local = G.view(G.reduce(got, { type: 'fail', status: 404 }), [], { local: true }); assert.equal(local.placeholder, G.DISABLED_TEXT.static + G.LOCAL_HINT);   // 로컬 404 는 옛 개발 서버 안내가 붙는다
  assert.equal(G.view(G.reduce(got, { type: 'fail', status: 503 }), [], { local: true }).placeholder, G.DISABLED_TEXT.config);                 // 다른 이유에는 붙지 않는다
  assert.equal(G.view(G.reduce(got, { type: 'fail', status: 503 }), []).placeholder, G.DISABLED_TEXT.config); assert.equal(G.view(G.reduce(got, { type: 'fail', status: 429 }), []).placeholder, G.DISABLED_TEXT.limit);
});

test('최근 이동: 5개까지 중복 없이 맨 앞에, 저장소를 못 쓰면 조용히 넘어간다', () => {
  const mem = {}; const win = { localStorage: { getItem: (k) => (k in mem ? mem[k] : null), setItem: (k, v) => { mem[k] = v; } } };
  assert.deepEqual(G.loadRecent(win), []);
  for (const it of [ITEM_BJD, ITEM_PNU, ITEM_SGG, ITEM_ROAD, { ...ITEM_BJD, code: '4145010800', name: '경기도 하남시 덕풍동' }, { ...ITEM_BJD, code: '1111010100', name: '서울 종로구 청운동' }]) G.saveRecent(win, it);
  const list = G.loadRecent(win); assert.equal(list.length, 5); assert.equal(list[0].code, '1111010100');
  G.saveRecent(win, ITEM_SGG); assert.deepEqual(G.loadRecent(win).map((x) => x.code).slice(0, 2), ['28245', '1111010100']); assert.equal(G.loadRecent(win).filter((x) => x.code === '28245').length, 1);
  const road = G.loadRecent(win).find((x) => x.road); assert.deepEqual(road.point, ITEM_ROAD.point);                                       // 도로명 후보는 좌표도 저장
  assert.equal(JSON.parse(mem[G.RECENT_KEY])[0].parts.sido, '인천광역시');
  mem[G.RECENT_KEY] = '{깨짐'; assert.deepEqual(G.loadRecent(win), []);
  assert.doesNotThrow(() => G.saveRecent({ localStorage: { getItem() { throw new Error('막힘'); }, setItem() { throw new Error('막힘'); } } }, ITEM_BJD));
});

/* ---------- 가짜 DOM 으로 mount 의 연결을 본다 ---------- */
class El {
  constructor(tag, doc) { this.tagName = tag.toUpperCase(); this.doc = doc; this.children = []; this.attrs = {}; this.dataset = {}; this.className = ''; this.listeners = {}; this.hidden = false; this.value = ''; this.disabled = false; this.readOnly = false; this.placeholder = ''; this.title = ''; this._text = ''; this.parent = null; this.id = ''; this.innerHTML = ''; const set = new Set(); this.classList = { add: (c) => set.add(c), toggle: (c, on) => (on ? set.add(c) : set.delete(c)), contains: (c) => set.has(c) }; }
  get textContent() { return this.children.length ? this.children.map((c) => c.textContent).join('') : this._text; }
  set textContent(v) { this.children = []; this._text = String(v); }
  appendChild(c) { this.children.push(c); c.parent = this; return c; }
  setAttribute(k, v) { this.attrs[k] = String(v); } getAttribute(k) { return this.attrs[k]; } removeAttribute(k) { delete this.attrs[k]; }
  addEventListener(t, f) { (this.listeners[t] = this.listeners[t] || []).push(f); }
  fire(t, ev) { for (const f of this.listeners[t] || []) f(Object.assign({ target: this, preventDefault() { this.prevented = true; } }, ev)); }
  matches(sel) { if (sel === '.mapwrap') return this.className.split(' ').includes('mapwrap') || this.classList.contains('mapwrap'); if (sel === '.cmd-o') return this.className.split(' ').includes('cmd-o'); if (sel === '.cmd-key') return this.className.split(' ').includes('cmd-key'); if (sel === '[aria-selected="true"]') return this.attrs['aria-selected'] === 'true'; return false; }
  closest(sel) { for (let n = this; n; n = n.parent) if (n.matches(sel)) return n; return null; }
  querySelector(sel) { for (const c of this.children) { if (c.matches && c.matches(sel)) return c; const f = c.querySelector && c.querySelector(sel); if (f) return f; } return null; }
  focus() { this.doc.activeElement = this; this.fire('focus'); } blur() { if (this.doc.activeElement === this) this.doc.activeElement = null; this.fire('blur'); } scrollIntoView() {}
}
function fakePage() {
  const doc = { activeElement: null, byId: {}, listeners: {}, getElementById(id) { return this.byId[id] || null; }, createElement(tag) { return new El(tag, doc); }, createTextNode(t) { const n = new El('#text', doc); n.textContent = t; return n; }, addEventListener(t, f) { (this.listeners[t] = this.listeners[t] || []).push(f); } };
  const wrap = new El('main', doc); wrap.className = 'mapwrap';
  const mk = (id, tag, parent) => { const e = new El(tag, doc); e.id = id; doc.byId[id] = e; if (parent) { e.parent = parent; } return e; };
  const root = mk('cmd', 'div', wrap); root.hidden = true; root.className = 'cmd';
  const form = mk('cmdForm', 'form', root), input = mk('cmdIn', 'input', form), res = mk('cmdRes', 'div', root), parse = mk('cmdParse', 'div', root), clear = mk('cmdClear', 'button', form), go = mk('cmdGo', 'button', form), sr = mk('sr', 'div', null);
  const key = new El('kbd', doc); key.className = 'cmd-key'; form.appendChild(key);
  const mem = {}; const assigned = [];
  const win = { location: { href: 'https://housing-board.vercel.app/?mode=progress&region=incheon-gyeyang', search: '?mode=progress', assign: (u) => assigned.push(u) }, localStorage: { getItem: (k) => (k in mem ? mem[k] : null), setItem: (k, v) => { mem[k] = v; } }, AbortController, RegionLoader: R };
  return { doc, win, el: { root, form, input, res, parse, clear, go, sr, wrap, key }, assigned, mem };
}
const flush = () => new Promise((r) => setImmediate(r));
const okJson = (data) => ({ ok: true, status: 200, headers: { get: () => null }, json: async () => data });
const type = (page, text) => { page.el.input.value = text; page.el.input.fire('input'); };

test('mount: 입력 → 320ms 뒤 검색 한 번 → 후보 줄과 인식 칩 → Enter 로 지도 주소 이동, 최근 이동 저장', async (t) => {
  t.mock.timers.enable({ apis: ['setTimeout'] });
  const page = fakePage(), calls = [];
  const h = G.mount(page.win, page.doc, { fetch: async (u) => { calls.push(u); return okJson({ items: [ITEM_PNU, ITEM_BJD], meta: {} }); } });
  assert.ok(h); assert.equal(page.el.root.hidden, false); assert.equal(page.el.wrap.classList.contains('hascmd'), true);   // .mapwrap 에 표시(재생바·안내 자리 규칙이 씀)
  assert.equal(page.el.root.dataset.state, 'idle'); assert.equal(page.el.input.disabled, false); assert.equal(page.el.input.placeholder, '주소·법정동·단지 또는 코드 입력');
  page.el.input.focus(); assert.equal(page.el.root.dataset.state, 'active'); assert.equal(page.el.res.hidden, false); assert.equal(page.el.res.textContent.includes('/'), false);   // 최근이 없으면 안내 문구
  type(page, '장'); t.mock.timers.tick(400); assert.equal(calls.length, 0);                                                                 // 한 글자는 검색 안 함
  type(page, '장위동 68-37'); t.mock.timers.tick(100); type(page, '장위동 68-37'); t.mock.timers.tick(319); assert.equal(calls.length, 0);   // 디바운스
  t.mock.timers.tick(5); await flush(); await flush();
  assert.equal(calls.length, 1); assert.equal(calls[0], 'api/v1/codes/search?q=%EC%9E%A5%EC%9C%84%EB%8F%99%2068-37&limit=8');
  assert.equal(page.el.res.children.length, 3);                                                                                             // 머리글 + 후보 2줄
  const row0 = page.el.res.children[1]; assert.equal(row0.attrs.role, 'option'); assert.equal(row0.attrs['aria-selected'], 'true'); assert.equal(row0.textContent.includes('서울특별시 성북구 장위동 68-37'), true); assert.equal(row0.textContent.includes('요청 시 조회'), true);
  assert.equal(page.el.input.attrs['aria-activedescendant'], 'cmdO0'); assert.equal(page.el.input.attrs['aria-expanded'], 'true'); assert.equal(page.el.go.disabled, false);
  assert.equal(page.el.parse.hidden, false); assert.equal(page.el.parse.textContent.replace(/\s/g, ''), '인식'.replace('인식', '') + '시도서울특별시›시군구성북구11290›법정동장위동1129013800›번지68-37→필지로이동');
  assert.equal(page.el.sr.textContent, '후보 2곳');
  page.el.input.fire('keydown', { key: 'ArrowDown' }); assert.equal(page.el.input.attrs['aria-activedescendant'], 'cmdO1'); assert.equal(page.el.parse.textContent.includes('68-37'), false);   // 법정동 후보로 바뀌면 칩도
  page.el.form.fire('submit');
  assert.equal(page.el.root.dataset.state, 'busy'); assert.equal(page.el.input.readOnly, true); assert.equal(page.el.input.attrs['aria-busy'], 'true');
  assert.deepEqual(page.assigned, ['https://housing-board.vercel.app/?mode=progress&bjd=4145011400']);                                       // 고른 두 번째(법정동) 후보로, region 삭제·mode 유지
  assert.equal(JSON.parse(page.mem[G.RECENT_KEY])[0].code, '4145011400');
});

test('mount: 후보를 누르면 이동(도로명은 좌표 at 포함), 같은 검색은 캐시, 서버가 없으면(404) 비활성 표시', async (t) => {
  t.mock.timers.enable({ apis: ['setTimeout'] });
  const page = fakePage(); let n = 0;
  const h = G.mount(page.win, page.doc, { fetch: async () => { n++; return okJson({ items: [ITEM_ROAD], meta: {} }); } });
  page.el.input.focus(); type(page, '경기도 하남시 감일로15번길 78'); t.mock.timers.tick(330); await flush(); await flush(); assert.equal(n, 1);
  page.el.res.fire('mousedown'); const row = page.el.res.children[1]; row.dataset.index = '0';
  page.el.res.fire('click', { target: row });
  assert.deepEqual(page.assigned, ['https://housing-board.vercel.app/?mode=progress&bjd=4145011400&at=127.14546%2C37.509897%2C17.5']);
  const two = fakePage(); let m = 0;
  G.mount(two.win, two.doc, { fetch: async () => { m++; return okJson({ items: [ITEM_BJD], meta: {} }); } });
  two.el.input.focus(); type(two, '감일동'); t.mock.timers.tick(330); await flush(); await flush(); type(two, '감일'); type(two, '감일동'); t.mock.timers.tick(10); await flush(); await flush();
  assert.equal(m, 1); assert.equal(two.el.res.children.length, 2);                                                                          // 같은 글자는 캐시에서 바로
  const off = fakePage(); G.mount(off.win, off.doc, { fetch: async () => ({ ok: false, status: 404, headers: { get: () => null }, json: async () => ({}) }) });
  off.el.input.focus(); type(off, '감일동'); t.mock.timers.tick(330); await flush(); await flush();
  assert.equal(off.el.root.dataset.state, 'disabled'); assert.equal(off.el.input.disabled, true); assert.equal(off.el.input.placeholder, G.DISABLED_TEXT.static);   // 가짜 창은 호스트가 없어 로컬 힌트 없음 assert.equal(off.el.input.title, G.DISABLED_TEXT.static); assert.equal(off.el.go.hidden, true); assert.equal(off.el.res.hidden, true);
  assert.equal(off.el.input.value, '');                                                                                       // 이유 문구(자리표시)가 보이도록 친 글자는 가린다
});

test('mount: 한도(429)는 Retry-After 만큼 쉬었다 풀리고, 네트워크 오류는 입력 중에 안내만. / 키는 입력줄로, 입력 중에는 가만히', async (t) => {
  t.mock.timers.enable({ apis: ['setTimeout'] });
  const page = fakePage();
  G.mount(page.win, page.doc, { fetch: async () => ({ ok: false, status: 429, headers: { get: (k) => (k === 'retry-after' ? '20' : null) }, json: async () => ({}) }) });
  page.el.input.focus(); type(page, '감일동'); t.mock.timers.tick(330); await flush(); await flush();
  assert.equal(page.el.root.dataset.state, 'disabled'); assert.equal(page.el.input.placeholder, G.DISABLED_TEXT.limit);
  t.mock.timers.tick(19000); assert.equal(page.el.root.dataset.state, 'disabled'); t.mock.timers.tick(1500); assert.equal(page.el.root.dataset.state, 'idle'); assert.equal(page.el.input.disabled, false);
  assert.equal(page.el.input.value, '감일동');                                                                                 // 풀리면 친 글자가 돌아온다
  const net = fakePage(); G.mount(net.win, net.doc, { fetch: async () => { throw new Error('연결 실패'); } });
  net.el.input.focus(); type(net, '감일동'); t.mock.timers.tick(330); await flush(); await flush();
  assert.equal(net.el.root.dataset.state, 'active'); assert.equal(net.el.res.textContent, G.NOTICE.failed);
  const key = fakePage(); G.mount(key.win, key.doc, { fetch: async () => okJson({ items: [], meta: {} }) });
  const slash = { key: '/', target: { tagName: 'DIV' }, preventDefault() { this.prevented = true; } }; key.doc.listeners.keydown[0](slash); assert.equal(slash.prevented, true); assert.equal(key.doc.activeElement, key.el.input);
  const typingIn = { key: '/', target: { tagName: 'INPUT' }, preventDefault() { this.prevented = true; } }; key.doc.listeners.keydown[0](typingIn); assert.equal(typingIn.prevented, undefined);
  const withCtrl = { key: '/', ctrlKey: true, target: { tagName: 'DIV' }, preventDefault() { this.prevented = true; } }; key.doc.listeners.keydown[0](withCtrl); assert.equal(withCtrl.prevented, undefined);
});

test('mount: 필요한 요소가 없으면 만들지 않고(null), 후보의 글자는 textContent 로만 넣는다(마크업이 들어 있어도 태그가 되지 않음)', async (t) => {
  t.mock.timers.enable({ apis: ['setTimeout'] });
  const empty = fakePage(); delete empty.doc.byId.cmdIn; assert.equal(G.mount(empty.win, empty.doc), null);
  const page = fakePage(); const evil = { ...ITEM_BJD, name: '<img src=x onerror=alert(1)> 감일동' };
  G.mount(page.win, page.doc, { fetch: async () => okJson({ items: [evil], meta: {} }) });
  page.el.input.focus(); type(page, '감일'); t.mock.timers.tick(330); await flush(); await flush();
  const row = page.el.res.children[1]; assert.equal(row.textContent.includes('<img src=x onerror=alert(1)>'), true);
  const walk = (n) => [n, ...n.children.flatMap(walk)]; assert.equal(walk(page.el.res).filter((x) => x.tagName === 'IMG').length, 0);
  assert.equal(walk(page.el.res).filter((x) => x.innerHTML && /<img/i.test(x.innerHTML)).length, 0);                                       // innerHTML 은 고정 아이콘 SVG 뿐
});

test('index.html 의 인라인 로더 스크립트가 문법 오류 없이 읽힌다(줄 중간 // 주석이 뒤 코드를 삼킨 적이 있다)', () => {
  const m = /<script>\n([\s\S]*?)<\/script>/.exec(html); assert.ok(m, '인라인 스크립트가 있어야 한다');
  assert.doesNotThrow(() => new (require('node:vm').Script)(m[1]));
});

test('구조: index.html 에 입력줄 마크업(콤보박스·목록·인식 줄)이 있고 goto.js 를 app.js 다음에 선택적으로 불러온다, 좁은 화면과 안내와의 자리 규칙이 있다(입주 시기 재생바는 2026-10-10 없앴다)', () => {
  for (const id of ['cmd', 'cmdForm', 'cmdIn', 'cmdRes', 'cmdParse', 'cmdClear', 'cmdGo']) assert.match(html, new RegExp(`id="${id}"`), id);
  assert.match(html, /<div class="cmd" id="cmd" data-state="idle" hidden>/);                                                                 // JS 가 붙기 전에는 보이지 않는다
  assert.match(html, /role="combobox"[^>]*aria-controls="cmdRes"[^>]*aria-autocomplete="list"/); assert.match(html, /<label class="sr" for="cmdIn">/); assert.match(html, /role="listbox"/);
  assert.doesNotMatch(html + css, /timebar/);
  assert.match(html, /load\('assets\/js\/app\.js'\); \}\)\.then\(function \(\) \{ return load\('assets\/js\/goto\.js'\)[^}]*GotoBar\.mount\(window, document\)[^}]*\}\)\.catch\(function \(\) \{\}\)/);   // 실패해도 지도는 열린다
  assert.match(css, /\.mapwrap\.hascmd \.dynhint\{/);
  const mobile = /@media \(max-width:900px\)\{([\s\S]*?)\n\}\n/.exec(css)[1];
  assert.match(mobile, /\.cmd\{left:12px;right:68px;top:56px;bottom:auto;/); assert.match(mobile, /\.cmd-bar input\{font-size:16px\}/);
  assert.match(css, /\.cmd\[hidden\]\{display:none\}/); assert.match(css, /\.cmd-res\[hidden\],\.cmd-parse\[hidden\]\{display:none\}/);
  assert.match(css, /@keyframes spin/); assert.match(css, /prefers-reduced-motion:reduce\)\{\.cmd-bar,\.cmd-res,\.cmd-parse\{transition:none\}/);
});

const ITEM_PLACE = { code: '4145010600105200000', kind: 'pnu', name: '하남시청', parts: { sido: '경기도', sgg: '하남시', umd: '신장동', jibun: '520', place: '하남시청' }, tier: 'req', point: [127.2145, 37.5392], place: true, category: '지방행정기관', addr: '경기도 하남시 대청로 10' };

test('장소 이름: near 를 5 km 격자로 맞춰 주소에 붙이고, 후보 줄(분류 · 주소)·인식 칩(장소)·이동 주소(필지 + at)·최근 이동이 장소를 안다', () => {
  assert.equal(G.nearOf([127.1712, 37.5499]), '127.15,37.55'); assert.equal(G.nearOf([127.174, 37.526]), '127.15,37.55'); assert.equal(G.nearOf(null), ''); assert.equal(G.nearOf([NaN, 37]), '');
  assert.equal(G.searchUrl('시청', undefined, '127.15,37.55'), 'api/v1/codes/search?q=%EC%8B%9C%EC%B2%AD&limit=8&near=127.15,37.55'); assert.equal(G.searchUrl('시청', undefined, ''), 'api/v1/codes/search?q=%EC%8B%9C%EC%B2%AD&limit=8');
  assert.equal(G.subText(ITEM_PLACE), '지방행정기관 · 경기도 하남시 대청로 10');
  assert.equal(G.subText({ ...ITEM_PLACE, category: '철도시설 > 철도/지하철 > 지하철역', addr: '경기도 하남시 덕풍동 406-17' }), '지하철역 · 경기도 하남시 덕풍동 406-17');   // 분류의 마지막 마디만
  assert.deepEqual(G.chipsOf(ITEM_PLACE).map((c) => [c.label, c.text, c.goal || '']), [['시도', '경기도', ''], ['시군구', '하남시', ''], ['법정동', '신장동', ''], ['장소', '하남시청', '그 필지·좌표로 이동']]);
  assert.deepEqual(G.gotoParams(ITEM_PLACE), { name: 'pnu', value: '4145010600105200000', at: '127.2145,37.5392,17.5' });                             // 필지를 강조하고 그 좌표로 가까이
  assert.deepEqual(G.gotoParams(ITEM_PNU), { name: 'pnu', value: '1129013800100680037' });                                                         // 지번 주소의 필지에는 at 이 없다(해석 결과가 시작 위치)
  assert.equal(R.codeUrl('https://h/?mode=infra', 'pnu', ITEM_PLACE.code, '127.2145,37.5392,17.5'), 'https://h/?mode=infra&pnu=4145010600105200000&at=127.2145%2C37.5392%2C17.5');
  const mem = {}; const win = { localStorage: { getItem: (k) => (k in mem ? mem[k] : null), setItem: (k, v) => { mem[k] = v; } } };
  G.saveRecent(win, ITEM_PLACE); G.saveRecent(win, { ...ITEM_PLACE, name: '하남시청역', code: '4145010800104060017' }); G.saveRecent(win, ITEM_PLACE);
  const rec = G.loadRecent(win); assert.deepEqual(rec.map((x) => x.name), ['하남시청', '하남시청역']); assert.deepEqual([rec[0].place, rec[0].category, rec[0].addr, rec[0].point], [true, '지방행정기관', '경기도 하남시 대청로 10', [127.2145, 37.5392]]);
  assert.equal(G.subText(rec[0]), '지방행정기관 · 경기도 하남시 대청로 10');                                                                          // 저장했다 읽어도 같은 줄
});

test('mount: 지금 지도 가운데(win.getMapCenter)를 near 로 보내고, 가운데가 바뀌면 다른 검색으로 본다(캐시 키에 포함). 지도 가운데를 모르면 near 없이', async (t) => {
  t.mock.timers.enable({ apis: ['setTimeout'] });
  const page = fakePage(), urls = []; let center = [127.1712, 37.5499];
  page.win.getMapCenter = () => center;
  G.mount(page.win, page.doc, { fetch: async (u) => { urls.push(u); return okJson({ items: [ITEM_PLACE], meta: {} }); } });
  page.el.input.focus(); type(page, '시청'); t.mock.timers.tick(330); await flush(); await flush();
  assert.equal(urls[0], 'api/v1/codes/search?q=%EC%8B%9C%EC%B2%AD&limit=8&near=127.15,37.55');
  const row = page.el.res.children[1]; assert.equal(row.textContent.includes('하남시청'), true); assert.equal(row.textContent.includes('지방행정기관 · 경기도 하남시 대청로 10'), true);
  type(page, '시청 '); type(page, '시청'); t.mock.timers.tick(5); await flush(); await flush(); assert.equal(urls.length, 1);                      // 같은 곳·같은 글자는 캐시
  center = [128.5, 35.9]; type(page, '시청'); t.mock.timers.tick(330); await flush(); await flush();
  assert.equal(urls.length, 2); assert.match(urls[1], /near=128\.50,35\.90$/);                                                                      // 다른 동네는 다시 검색
  page.el.form.fire('submit'); assert.deepEqual(page.assigned, ['https://housing-board.vercel.app/?mode=progress&pnu=4145010600105200000&at=127.2145%2C37.5392%2C17.5']);
  const none = fakePage(), nurls = []; G.mount(none.win, none.doc, { fetch: async (u) => { nurls.push(u); return okJson({ items: [], meta: {} }); } });
  none.el.input.focus(); type(none, '시청'); t.mock.timers.tick(330); await flush(); await flush(); assert.equal(nurls[0], 'api/v1/codes/search?q=%EC%8B%9C%EC%B2%AD&limit=8');
});

test('안내 띠(2026-10-10 피드백): 입력줄이 붙으면 띠를 입력줄 아래로 옮기고, 반투명 유리로 요약 한 줄만 보인다', () => {
  const page = fakePage();
  const pv = new El('div', page.doc); pv.id = 'pvBanner'; pv.parent = page.el.wrap; page.doc.byId.pvBanner = pv;
  G.mount(page.win, page.doc, { fetch: async () => okJson({ items: [], meta: {} }) });
  assert.equal(pv.parent, page.el.root, '띠가 입력줄(#cmd) 안으로');
  assert.equal(page.el.root.children.at(-1), pv, '입력줄의 맨 끝(인식 줄 다음)');
  const none = fakePage(); assert.doesNotThrow(() => G.mount(none.win, none.doc, { fetch: async () => okJson({ items: [], meta: {} }) }), '띠가 없는 문서');
  const rule = (sel) => { const m = new RegExp(`(?:^|\\n)${sel.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}\\{([^}]*)\\}`).exec(css); assert.ok(m, `${sel} 규칙`); return m[1]; };
  const b = rule('.cmd .pvbanner');
  assert.match(b, /position:static;/); assert.match(b, /transform:none;/);
  assert.match(b, /background:var\(--glass-note\)/); assert.match(b, /-webkit-backdrop-filter:var\(--glass-blur\)/); assert.match(b, /[^-]backdrop-filter:var\(--glass-blur\)/);
  assert.match(rule('.cmd .pv-s'), /white-space:nowrap;overflow:hidden;text-overflow:ellipsis/, '요약은 한 줄');
  const mobile = /@media \(max-width:900px\)\{([\s\S]*?)\n\}\n/.exec(css)[1];
  assert.match(mobile, /\.cmd \.pvbanner\{order:-1/, '좁은 화면(입력줄 위쪽·후보 아래로)에서도 띠는 입력줄 아래');
  assert.match(css, /\.mapwrap\.hascmd:has\(\.cmd \.pvbanner:not\(\[hidden\]\)\) \.dynhint\{/, '건물 불러오는 안내는 띠만큼 더 위로');
});
