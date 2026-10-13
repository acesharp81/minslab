'use strict';
// lib/board/pipeline.ts — 데이터 원본 화면의 수집 흐름(원천 → 보관·실시간 → 화면)과 계획. 자료끼리 맞는지와 화면에 적는 계산을 다시 해 본다.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const ROOT = path.join(__dirname, '..', '..');
const P = require('../../lib/board/pipeline.ts');
const C = require('../../lib/board/calc.ts');
const sources = require('../../data/board/sources.json');
const registry = require('../../registry/projects.json').projects;
const read = (f) => fs.readFileSync(path.join(ROOT, f), 'utf8');

test('원천 카탈로그의 모든 항목이 흐름 안에 자리가 있고, 없는 항목을 가리키지 않는다', () => {
  const ids = sources.items.map((s) => s.id);
  assert.deepEqual(Object.keys(P.PLACE).sort(), [...ids].sort());
  const links = new Set([...P.CHAIN.map((c) => c.id), P.KEYLESS.id]);
  const items = new Set(P.ITEMS.map((i) => i.id));
  for (const [id, p] of Object.entries(P.PLACE)) {
    assert.ok(links.has(p.link), `${id}: 고리 ${p.link}`);
    assert.ok(p.item === null || items.has(p.item), `${id}: 판정 ${p.item}`);
  }
});

test('보관 줄은 여덟 단계이고 네 묶음이 빠짐·겹침 없이 차례대로 나눈다. 상태는 세 값 중 하나다', () => {
  assert.equal(P.STEPS.length, 8);
  assert.deepEqual(P.PHASES.flatMap((p) => p.steps), P.STEPS.map((s) => s.id));
  const all = [...P.STEPS, P.LIVE, ...P.ORIGINS];
  for (const s of all) assert.ok(P.STATUS_LABEL[s.status], `${s.id}: ${s.status}`);
  const ids = [...P.STEPS, P.LIVE].map((s) => s.id);
  assert.equal(new Set(ids).size, ids.length);
  assert.equal(P.ORIGINS.find((o) => o.id === 'input').status, 'plan', '기관 입력 경로는 아직 없다');
});

test('단계가 가리키는 코드 위치는 저장소에 실제로 있다(없는 파일을 근거로 적지 않는다)', () => {
  for (const s of [...P.STEPS, P.LIVE]) for (const f of s.code) assert.ok(fs.existsSync(path.join(ROOT, f)), `${s.id}: ${f}`);
});

test("'지금' 문구의 수치는 저장소 자료와 같다: 레지스트리 77건·5개 시군구·일정 0건, 번들 단지 22곳, 실시간 API 8개", () => {
  assert.equal(registry.length, 77);
  assert.equal(new Set(registry.map((p) => p.sgg)).size, 5);
  assert.equal(registry.filter((p) => p.schedule).length, 0);
  assert.equal(registry.filter((p) => p.refs.some((r) => r.system === 'bundle')).length, 22);
  const ledger = P.STEPS.find((s) => s.id === 'ledger').now;
  assert.match(ledger, /77건\(5개 시군구\)/); assert.match(ledger, /0건/);
  const routes = [];
  const walk = (d) => { for (const e of fs.readdirSync(d, { withFileTypes: true })) { const p = path.join(d, e.name); if (e.isDirectory()) walk(p); else if (e.name === 'route.ts') routes.push(p); } };
  walk(path.join(ROOT, 'app/api'));
  assert.equal(routes.length, 8);
  assert.match(P.LIVE.now, /^8개:/);
});

test('판정 이유는 정의된 기준만 쓰고, 보관은 B 기준·실시간은 R 기준을 하나 이상 갖는다', () => {
  for (const i of P.ITEMS) {
    assert.ok(i.why.length > 0, i.id);
    for (const r of i.why) assert.ok(P.RULES[r], `${i.id}: ${r}`);
    if (i.mode === 'store') assert.ok(i.why.some((r) => r.startsWith('B')), i.id);
    if (i.mode === 'live') assert.ok(i.why.every((r) => r.startsWith('R')), i.id);
    if (i.mode === 'mixed') assert.ok(i.why.some((r) => r.startsWith('B')) && i.why.some((r) => r.startsWith('R')), i.id);
  }
  assert.equal(new Set(P.ITEMS.map((i) => i.id)).size, P.ITEMS.length);
});

test('한도 계산: 버스 4노선 × 86,400 ÷ 60 = 5,760 은 80% 기준(8,000) 안이고, 다른 막대도 모두 기준 안이다', () => {
  const bus = P.ITEMS.find((i) => i.id === 'bus').meter;
  assert.equal(bus.used, 5760);
  assert.ok(bus.used <= P.GUIDE * bus.limit);
  for (const i of P.ITEMS.filter((x) => x.meter)) assert.ok(P.pct(i.meter) < P.GUIDE * 100, `${i.id} ${P.pct(i.meter)}%`);
  assert.equal(P.pct(P.ITEMS.find((i) => i.id === 'hub-hs').meter), 9);     // 대지위치 2.7만 ÷ 30만
  assert.equal(P.pct(P.ITEMS.find((i) => i.id === 'hub-ap').meter), 23);    // 건축 기본개요 6.9만 ÷ 30만
  assert.equal(P.pct(P.ITEMS.find((i) => i.id === 'notices').meter), 14.4); // 6쪽 × 24시간 = 144 ÷ 1,000
  assert.equal(6 * 24, P.ITEMS.find((i) => i.id === 'notices').meter.used);
});

test('한도 계산의 근거가 코드와 같다: 공고 목록 6쪽·버스 하루 예산 8,000·건물 칸 5쪽', () => {
  assert.match(read('handlers/v1/notices.js'), /const MAX_PAGES = 6;/);
  assert.match(read('handlers/v1/buildings.js'), /const MAX_PAGES = 5;/);
  assert.match(read('handlers/bus.js'), /const DAILY_BUDGET = 8000;/);
});

test('시간축: 2026-10 에 시작한 일정 기록은 다음 달에 변경을 감지하고, 6개월 뒤(2027-04) 6개월 추이를 그린다', () => {
  const [start, second, trend] = P.TIMELINE.map((t) => t.ym);
  assert.equal(C.monthsBetween(start, second), 1);
  assert.equal(C.monthsBetween(start, trend), 6);
});

test('끝에서 본 결과: 질문 다섯 개와 국민 화면, 판정 값은 세 가지 중 하나. 계획은 일정 기록부터 시작한다', () => {
  assert.equal(P.QUESTIONS.length, 6);
  for (const q of P.QUESTIONS) assert.ok(P.CAN_LABEL[q.can], q.q);
  assert.match(P.PLAN[0].what, /^일정 기록 시작/);
  for (const p of P.PLAN) assert.ok(p.check.length > 0);
});

test('끝의 화면 링크는 메뉴에 있는 경로뿐이다', () => {
  const { MENU } = require('../../lib/shell/menu.ts');
  const hrefs = new Set(MENU.map((m) => m.href));
  for (const e of P.ENDS) for (const [, href] of e.screens) assert.ok(hrefs.has(href), href);
});

