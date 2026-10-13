/* 지도 로딩 화면(index.html #loading)의 실시간 진행.
   영역 다섯(지도 프로그램 · 지역 자료 · 배경 지도 · 건물·단지 · 지형)마다 받을 것(스크립트·파일·타일)을 세어 줄마다 실제 비율 막대와 n/m, 끝난 시각을 그린다.
   알리는 쪽: 지도 섬(components/MapIsland.tsx)·index.html 로더가 스크립트를, boot 동안 감싼 fetch(trackFetch)가 지역 자료를, app.js 가 MapLibre 타일 이벤트(watchMap)를.
   시각은 문서를 연 때(performance.now)부터 잰다. 순수 함수(areaView · nameOf · fmtBytes · sec)는 node --test 로 시험한다(tests/js/loading.test.cjs). */
(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.LoadView = api;
})(typeof self !== 'undefined' ? self : this, function () {
  'use strict';

  const AREAS = ['code', 'data', 'base', 'bld', 'dem'];
  const UNIT = { code: '개', data: '개', base: '장', bld: '장', dem: '장' };
  const IDLE = { code: '준비 중', data: '대기', base: '대기', bld: '대기', dem: '대기' };   // 시작 전 글자
  const BEGIN = { code: '받는 중', data: '받는 중', base: '타일 요청 중', bld: '건물 정리 중', dem: '타일 요청 중' };   // 시작했지만 셀 것이 아직 없을 때

  const sec = (ms) => (ms / 1000).toFixed(ms < 9950 ? 1 : 0) + '초';
  const fmtBytes = (b) => (b >= 1048576 ? (b / 1048576).toFixed(1) + 'MB' : b >= 1024 ? Math.round(b / 1024) + 'KB' : b + 'B');

  /* 요청 주소 → 화면 이름. 지역 자료 구간에서 세는 것만 이름을 주고, 나머지는 null(세지 않는다) */
  function nameOf(url) {
    const u = String(url || '');
    if (/(^|\/)regions\/index\.json/.test(u)) return '지역 목록';   // region.js 는 상대 주소(regions/…)로 부른다
    const m = /(^|\/)regions\/[^/]+\/(region|projects|buildings|context|infra)\.json/.exec(u);
    if (m) return { region: '지역 정보', projects: '단지', buildings: '건물', context: '역·학교', infra: '기반시설' }[m[2]];
    if (/api\/v1\/resolve/.test(u)) return '코드 해석';
    if (/api\/v1\/permits/.test(u)) return '인허가';
    if (/api\/v1\/infra/.test(u)) return '기반시설';
    return null;
  }

  function newArea() { return { want: new Set(), got: new Set(), fail: 0, bytes: 0, t0: null, t1: null, now: '' }; }

  /* 영역 하나의 화면 상태: st(wait·active·done) · frac(0~1, 막대) · val(오른쪽 글자) */
  function areaView(id, a) {
    const n = a.got.size, m = Math.max(a.want.size, n), unit = UNIT[id];
    if (a.t1 != null) {
      const extra = [m ? `${m}${unit}` : '', a.bytes ? fmtBytes(a.bytes) : '', a.fail ? `실패 ${a.fail}` : ''].filter(Boolean).join(' · ');
      return { st: 'done', frac: 1, val: `✓ ${sec(a.t1)}`, title: extra };
    }
    if (a.t0 == null) return { st: 'wait', frac: 0, val: IDLE[id], title: '' };
    if (!m) return { st: 'active', frac: 0, val: a.now || BEGIN[id], title: '' };
    return { st: 'active', frac: n / m, val: `${n}/${m}${unit}${a.now ? ' · ' + a.now : ''}`, title: a.fail ? `실패 ${a.fail}` : '' };
  }

  /* ---------- 화면(브라우저 전용) ---------- */
  let CTL = null;
  function ctl() {
    if (CTL) return CTL;
    const doc = typeof document !== 'undefined' ? document : null, box = doc && doc.getElementById('loading');
    const A = Object.fromEntries(AREAS.map((id) => [id, newArea()]));
    const now = () => performance.now();
    let timer = 0, closed = !box;
    const start = (id) => { const a = A[id]; if (a && a.t0 == null) a.t0 = now(); return a; };
    function render() {
      if (!box) return;
      for (const id of AREAS) {
        const li = box.querySelector(`[data-area="${id}"]`); if (!li) continue;
        const v = areaView(id, A[id]);
        if (li.dataset.st !== v.st) li.dataset.st = v.st;
        li.style.setProperty('--p', (v.frac * 100).toFixed(1) + '%');
        const val = li.querySelector('.ld-val'); if (val && val.textContent !== v.val) val.textContent = v.val;
        if (v.title) li.title = v.title; else li.removeAttribute('title');
      }
      const t = doc.getElementById('ldTime'); if (t) t.textContent = sec(now());
    }
    function tick() { if (closed || box.hidden) { timer = 0; return; } render(); timer = setTimeout(tick, 100); }
    if (box) tick();
    CTL = {
      want(id, key, label) { const a = start(id); if (!a || a.t1 != null) return; a.want.add(key); if (label) a.now = label; },
      got(id, key, bytes) { const a = A[id]; if (!a || a.t1 != null) return; start(id); a.want.add(key); a.got.add(key); if (bytes) a.bytes += bytes; },
      fail(id, key) { const a = A[id]; if (!a || a.t1 != null || a.got.has(key)) return; a.fail++; this.got(id, key); },
      drop(id, key) { const a = A[id]; if (a && a.t1 == null && !a.got.has(key)) a.want.delete(key); },
      begin(id, label) { const a = start(id); if (a && label) a.now = label; },
      finish(id) { const a = start(id); if (a && a.t1 == null) { a.t1 = now(); a.now = ''; } render(); },
      sub(text) { const el = doc && doc.getElementById('ldSub'); if (el && text) el.textContent = text; },
      /* 지역 자료 구간 동안만 같은 출처 요청(nameOf 가 이름을 주는 것)을 센다. 돌려주는 함수를 부르면 원래 fetch 로 되돌린다 */
      trackFetch(win) {
        const orig = win.fetch;
        if (!orig || !box) return () => {};
        const self = this;
        win.fetch = function (input, init) {
          const url = typeof input === 'string' ? input : (input && input.url) || '';
          const label = nameOf(url);
          if (!label) return orig.call(this, input, init);
          const key = url + '#' + (self.__n = (self.__n || 0) + 1);
          self.want('data', key, `${label} 받는 중`);
          return orig.call(this, input, init).then((res) => {
            const abs = new URL(url, win.location.href).href;
            const settle = () => { const e = performance.getEntriesByName(abs).pop(); self.got('data', key, e ? e.decodedBodySize || e.encodedBodySize || 0 : 0); };
            res.clone().arrayBuffer().then(settle, settle);   // 본문까지 받은 뒤에 센다(크기는 리소스 타이밍의 풀린 크기)
            return res;
          }, (err) => { self.fail('data', key); throw err; });
        };
        return () => { win.fetch = orig; };
      },
      /* MapLibre 타일 이벤트로 배경·건물·지형을 센다. groups: { base: [소스 id], bld: [...], dem: [...] }. 영역의 소스가 모두 끝나면(타일을 하나 이상 받은 뒤) 완료 */
      watchMap(map, groups) {
        const areaOf = (sid) => Object.keys(groups).find((k) => groups[k].includes(sid));
        const keyOf = (e) => `${e.sourceId}/${e.tile.tileID.key}`;
        Object.keys(groups).forEach((id) => this.begin(id));
        const settled = (id) => A[id].want.size > 0 && groups[id].every((sid) => !map.getSource(sid) || map.isSourceLoaded(sid));
        const on = {
          sourcedataloading: (e) => { const id = e.tile && areaOf(e.sourceId); if (id) this.want(id, keyOf(e)); },
          sourcedata: (e) => { const id = areaOf(e.sourceId); if (!id) return; if (e.tile) this.got(id, keyOf(e)); if (e.isSourceLoaded && settled(id)) this.finish(id); },
          sourcedataabort: (e) => { const id = e.tile && areaOf(e.sourceId); if (id) this.drop(id, keyOf(e)); },
          error: (e) => { const id = e && e.tile && areaOf(e.sourceId); if (id) this.fail(id, keyOf(e)); },
        };
        Object.entries(on).forEach(([k, f]) => map.on(k, f));
        this.__unwatch = () => Object.entries(on).forEach(([k, f]) => map.off(k, f));
      },
      /* 첫 idle: 남은 영역을 모두 끝내고 걷는다(걷히는 0.35초 동안 다 찬 모습) */
      close() {
        if (closed) return;
        AREAS.forEach((id) => this.finish(id));
        if (this.__unwatch) this.__unwatch();
        closed = true; clearTimeout(timer);
        if (box) box.hidden = true;
      },
    };
    return CTL;
  }

  return { AREAS, nameOf, areaView, fmtBytes, sec, newArea, ctl };
});
