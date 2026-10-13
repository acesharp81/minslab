'use strict';
// 첫 화면 쌓기 연출(시험, 2026-10-10 사용자 요청 "지도 화면이 열릴때 레이어 별로 차곡차곡 쌓이는 초기화 렌더링"): 주소 intro=stack 일 때만,
// 움직임 줄이기면 건너뛰고, 한 번만 돌고, 원래 불투명도·높이 식을 그대로 되돌리고, 누르거나 휠·키를 쓰면 바로 끝나는지 확인한다.
// 앞 묶음은 글자로, 뒤 묶음은 연출 블록을 가짜 지도에 돌려 본다.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const ROOT = path.join(__dirname, '..', '..');
const app = fs.readFileSync(path.join(ROOT, 'assets/js/app.js'), 'utf8');
const HEAD = 'if (INTRO_ON) (function introStack() {';

test('주소 intro=stack 이고 움직임 줄이기가 아닐 때만 돈다(그 밖에는 아무것도 하지 않는다)', () => {
  assert.match(app, /const INTRO_ON = q\.get\('intro'\) === 'stack' && !reduceMotion;/);
  const a = app.indexOf(HEAD);
  assert.ok(a > 0, '연출 블록');
  assert.equal(app.split('INTRO_ON').length - 1, 2, 'INTRO_ON 은 정의와 블록 입구에만');
  const h = app.indexOf('window.__introStack = {');
  assert.ok(h > a && h < app.indexOf('\n})();', a) && app.split('window.__introStack =').length === 2, '시험 훅은 블록 안에서 한 번만');
});

test('한 번만 돈다: 첫 스타일에서 숨기고 첫 idle 에 시작, 스타일을 다시 불러오면 그만둔다', () => {
  assert.match(app, /if \(first\) \{ first = false; show\(0, 0\); map\.once\('idle', start\); return; \}/);
  assert.match(app, /if \(state !== 'wait'\) return; state = 'run';/);
  assert.match(app, /if \(state === 'done'\) return; state = 'done'; stop\(\);/);
  assert.match(app, /state = 'done'; stop\(\); SAVED\.clear\(\); H0 = undefined;/);
});

test('원래 값·식을 저장했다가 그대로 되돌리고, 누르거나 휠·키를 쓰면 바로 끝낸다', () => {
  assert.match(app, /if \(!SAVED\.has\(k\)\) SAVED\.set\(k, \[map\.getPaintProperty\(id, p\), map\.getPaintProperty\(id, p \+ '-transition'\)\]\);/);
  assert.match(app, /map\.setPaintProperty\(id, p, on \? SAVED\.get\(k\)\[0\] : 0\);/);
  assert.match(app, /setK\(0\); setH\(\['\*', H0, \['coalesce', \['feature-state', 'k'\], 1\]\]\);/, '동 높이 식은 한 번만 바꾸고');
  assert.match(app, /if \(k < 1\) \{ setK\(1 - \(1 - k\) \*\* 3\); raf = requestAnimationFrame\(tick\); \} else \{ raf = 0; setH\(H0\); setK\(null\); \}/, '프레임마다 feature-state k 만 바꾼다(워커 재타일링 없음)');
  assert.match(app, /src\('dongs', \{ type: 'geojson', data: dg, promoteId: 'key' \}\)/);
  assert.match(app, /duration: on && L\.type !== 'fill-extrusion' \? dur : 0/, '3D 층은 페이드 없이');
  assert.doesNotMatch(app.slice(app.indexOf(HEAD), app.indexOf('window.__introStack')), /'hillshade-own'/, '지형 음영은 단계에서 뺐다');
  assert.match(app, /show\(STACK\.length, dur\); setH\(H0\);/);
  assert.match(app, /EV = \['pointerdown', 'wheel', 'keydown'\]/);
  assert.match(app, /window\.addEventListener\(e, skip, \{ capture: true, passive: true \}\)/);
  assert.match(app, /function skip\(\) \{ finish\(0\); \}/);
});

/* 연출 블록을 가짜 지도·타이머에 올린다 */
function harness() {
  const a = app.indexOf(HEAD), src = app.slice(a, app.indexOf('\n})();', a) + 6);
  const clone = (v) => (v === undefined ? undefined : JSON.parse(JSON.stringify(v)));
  const PAT = ['interpolate', ['linear'], ['zoom'], 13.5, 0.55, 15.5, 1];
  const fresh = () => ({
    'hillshade-own': { type: 'hillshade', paint: { 'hillshade-exaggeration': 0.3 } },
    'district-mask': { type: 'fill', paint: { 'fill-opacity': 0.12 } },
    'official-3d': { type: 'fill-extrusion', paint: { 'fill-extrusion-opacity': 1, 'fill-extrusion-height': ['get', 'eh'] } },
    'blk-build': { type: 'fill', paint: { 'fill-pattern': 'hatch', 'fill-opacity': PAT } },
    'blk-line': { type: 'line', paint: { 'line-width': 2 } },   // 불투명도를 정하지 않은 레이어(기본값)
    'dong-3d': { type: 'fill-extrusion', paint: { 'fill-extrusion-opacity': 1, 'fill-extrusion-height': ['get', 'h'] } },
    'blk-dot': { type: 'circle', paint: { 'circle-opacity': ['interpolate', ['linear'], ['zoom'], 13.6, 0.95, 14.3, 0] } },
    'blk-badge': { type: 'symbol', paint: { 'text-color': '#172B4D' } },
  });
  const H = { layers: fresh(), ev: {}, once: {}, win: {}, timers: new Map(), rafs: [], now: 0, tid: 0 };
  H.orig = clone(H.layers);
  H.map = {
    getLayer: (id) => H.layers[id], getPaintProperty: (id, p) => clone(H.layers[id].paint[p]),
    setPaintProperty: (id, p, v) => { if (v === undefined) delete H.layers[id].paint[p]; else H.layers[id].paint[p] = clone(v); },
    on: (e, f) => (H.ev[e] = H.ev[e] || []).push(f), once: (e, f) => (H.once[e] = H.once[e] || []).push(f), off: (e, f) => { H.ev[e] = (H.ev[e] || []).filter((x) => x !== f); },
    triggerRepaint() {}, terrain: null,
    getSource: (id) => (id === 'dongs' ? {} : undefined), setFeatureState: (f, s) => { H.fs[f.id] = { ...(H.fs[f.id] || {}), ...s }; }, removeFeatureState: () => { H.fs = {}; },
  };
  H.fs = {};
  H.fire = (e) => { for (const f of H.ev[e] || []) f(); const o = H.once[e] || []; H.once[e] = []; for (const f of o) f(); };
  H.hud = { '#hud': { style: {} }, '#hudSum': { style: {} } };
  H.runTimers = (until) => { for (const [id, [t, f]] of [...H.timers].sort((x, y) => x[1][0] - y[1][0])) if (t <= until && H.timers.has(id)) { H.timers.delete(id); H.now = t; f(); } };
  H.op = () => Object.fromEntries(Object.entries(H.layers).map(([id, l]) => [id, Object.fromEntries(Object.entries(l.paint).filter(([p]) => /opacity|exaggeration/.test(p) && !p.endsWith('-transition')))]));
  H.origOp = H.op();
  H.win.addEventListener = (e, f) => { H.win[e] = f; }; H.win.removeEventListener = (e) => { delete H.win[e]; };
  vm.runInNewContext(src, {
    INTRO_ON: true, map: H.map, $: (s) => H.hud[s], BLK_FILLS: ['blk-build'], DONG_FEATS: [{ properties: { key: 'A2-101' } }, { properties: { key: 'A2-101' } }, { properties: { key: 'A2-102' } }], INFRA_LAYERS: [], INFRA_MODE_LAYERS: [], ZONE_LAYERS: [], BUS_LAYERS: [],
    window: H.win, performance: { now: () => H.now }, requestAnimationFrame: (f) => H.rafs.push(f), cancelAnimationFrame: () => {},
    setTimeout: (f, t) => { H.timers.set(++H.tid, [t, f]); return H.tid; }, clearTimeout: (id) => H.timers.delete(id),
  });
  return H;
}
const ZERO = { 'hillshade-own': { 'hillshade-exaggeration': 0.3 }, 'district-mask': { 'fill-opacity': 0 }, 'official-3d': { 'fill-extrusion-opacity': 0 }, 'blk-build': { 'fill-opacity': 0 }, 'blk-line': { 'line-opacity': 0 }, 'dong-3d': { 'fill-extrusion-opacity': 0 }, 'blk-dot': { 'circle-opacity': 0, 'circle-stroke-opacity': 0 }, 'blk-badge': { 'text-opacity': 0, 'icon-opacity': 0 } };

test('가짜 지도: 첫 스타일에서 모두 0 → 단계마다 드러나고 동은 0 에서 솟음 → 누르면 원래 값·식·전환 그대로', () => {
  const H = harness();
  assert.equal(H.hud['#hud'].style.opacity, '0', 'HUD 는 처음부터 숨긴다');
  H.fire('style.load');
  assert.deepEqual(H.op(), ZERO);
  H.fire('idle');
  H.runTimers(800);
  assert.equal(H.layers['official-3d'].paint['fill-extrusion-opacity'], 1, '③ 기존 건물');
  assert.equal(H.layers['official-3d'].paint['fill-extrusion-opacity-transition'].duration, 0, '3D 는 페이드 없이 바로');
  assert.equal(H.layers['blk-build'].paint['fill-opacity'], 0, '④ 는 아직');
  H.runTimers(1700);
  assert.deepEqual(H.layers['dong-3d'].paint['fill-extrusion-height'], ['*', ['get', 'h'], ['coalesce', ['feature-state', 'k'], 1]], '⑤ 높이 식은 feature-state k 를 곱한 식으로 한 번');
  assert.deepEqual(H.fs, { 'A2-101': { k: 0 }, 'A2-102': { k: 0 } }, '동마다 k=0 에서 시작(같은 동 여러 면은 한 번)');
  H.rafs.shift()(1700 + 450);
  const k = H.fs['A2-101'].k;
  assert.ok(k > 0 && k < 1, `중간 k=${k}`);
  assert.deepEqual(H.layers['dong-3d'].paint['fill-extrusion-height'], ['*', ['get', 'h'], ['coalesce', ['feature-state', 'k'], 1]], '솟는 동안 식은 그대로');
  H.win.pointerdown();
  assert.deepEqual(H.op(), H.origOp, '원래 불투명도(정하지 않았던 것은 다시 기본값)');
  assert.deepEqual(H.layers['dong-3d'].paint['fill-extrusion-height'], ['get', 'h'], '원래 높이 식');
  assert.deepEqual(H.fs, {}, 'feature-state 를 지웠다');
  assert.equal(H.timers.size, 0, '남은 단계 타이머 없음');
  assert.equal(H.win.pointerdown, undefined, '듣기를 뗐다');
  H.fire('render');
  assert.deepEqual(H.layers, H.orig, '전환까지 원래대로');
  assert.equal(H.hud['#hud'].style.opacity, '');
});

test('가짜 지도: 끝까지 가면 원래대로, 다시 idle·테마 바꿈(style.load)이 와도 다시 돌지 않는다', () => {
  const H = harness();
  H.fire('style.load'); H.fire('idle'); H.runTimers(1700);
  H.rafs.shift()(1700 + 900);
  assert.deepEqual(H.fs, {}, '다 솟으면 feature-state 를 지운다');
  H.runTimers(10000); H.fire('render');
  assert.deepEqual(H.layers, H.orig);
  H.fire('idle');
  assert.deepEqual(H.layers, H.orig, '두 번째 idle');
  H.layers = Object.assign(H.layers, JSON.parse(JSON.stringify(H.orig)));
  H.fire('style.load'); H.fire('idle');
  assert.deepEqual(H.layers, H.orig, '스타일을 다시 불러와도 숨기지 않는다');
});

test('가짜 지도: 시험 훅 step(n) 은 n 단계까지 바로 보이고 6 이면 모두 원래 값', () => {
  const H = harness();
  H.fire('style.load');
  const hook = H.win.__introStack;
  hook.step(2);
  assert.equal(H.layers['district-mask'].paint['fill-opacity'], 0.12);
  assert.equal(H.layers['official-3d'].paint['fill-extrusion-opacity'], 0);
  assert.equal(H.hud['#hud'].style.opacity, '0');
  hook.step(6);
  assert.deepEqual(H.op(), H.origOp);
  assert.equal(H.hud['#hud'].style.opacity, '');
  hook.step(0);
  assert.deepEqual(H.op(), ZERO);
});
