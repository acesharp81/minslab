'use strict';
// lib/board/calc.ts — 상황판 화면의 계산. data/board/*.json 의 값을 원천 CSV 에서 따로 센 값과 대조한다(화면 숫자 = 원천 숫자).
// calc.ts 는 JSON 을 직접 읽지 않으므로 Node 가 타입 표기를 지우고 그대로 부른다. 원천 CSV 가 없는 환경(data/raw·processed 없음)에서는 대조를 건너뛴다.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const ROOT = path.join(__dirname, '..', '..');
const C = require('../../lib/board/calc.ts');
const molit = require('../../data/board/molit.json');
const lh = require('../../data/board/lh-completion.json');
const PROCESSED = path.join(ROOT, 'data/processed');
const haveCsv = fs.existsSync(path.join(PROCESSED, 'molit_착공_월계.csv'));

/* 통계누리 정리본 CSV(BOM·따옴표 없음) → 행 객체 */
function csv(name) {
  const [head, ...lines] = fs.readFileSync(path.join(PROCESSED, name), 'utf8').replace(/^\uFEFF/, '').trim().split(/\r?\n/);
  const cols = head.split(',');
  return lines.map((l) => Object.fromEntries(l.split(',').map((v, i) => [cols[i], v])));
}

test('월 이동·표기: nextYm 은 해를 넘기고, 연누계는 1월부터 다 있는 해만 값이 있다', () => {
  assert.equal(C.nextYm('2026-11', 3), '2027-02');
  assert.equal(C.nextYm('2026-01', 0), '2026-01');
  assert.equal(C.nextYm('2026-01', -1), '2025-12');
  assert.equal(C.ymDot('2026-08'), '2026.08');
  assert.equal(C.monthLabel('2026-08'), '2026년 8월');
  assert.equal(C.fmt(1234567), '1,234,567');
  assert.equal(C.fmt(null), '–');
  assert.equal(C.ytd(molit, 'permit', C.NATION, '2021-09'), null, '자료가 2021-09 부터라 2021 연누계는 알 수 없다');
  assert.ok(C.ytd(molit, 'permit', C.NATION, '2025-12') > 0);
  assert.deepEqual(C.neighborMonths(molit, '2021-09'), { prev: null, next: '2021-10' });
  assert.deepEqual(C.neighborMonths(molit, C.lastMonth(molit)), { prev: '2026-07', next: null });
});

test('한 달의 시도별 표는 지표마다 시도 합 = 전국이다(전 기간)', () => {
  for (const ym of molit.months) {
    const rows = C.monthTable(molit, ym);
    for (const k of C.METRICS) {
      const nation = rows.find((r) => r.code === C.NATION).values[k];
      if (nation === null) continue;
      const sum = rows.filter((r) => r.code !== C.NATION).reduce((a, r) => a + r.values[k], 0);
      assert.equal(sum, nation, `${ym} ${k}`);
    }
  }
});

test('시행주체 4분류의 합은 총계다(전국·모든 시도·모든 지표·모든 달, 알 수 없는 달은 건너뜀)', () => {
  for (const k of ['permit', 'start', 'complete']) {
    for (const s of molit.sido) {
      const ser = C.seriesOf(molit, k, s.code);
      ser.total.forEach((t, i) => {
        if (t === null) return;
        assert.equal(C.ACTORS.reduce((a, x) => a + ser.actors[x][i], 0), t, `${k} ${s.code} ${molit.months[i]}`);
      });
    }
  }
});

test('화면 숫자 = 원천 숫자: 착공·준공·분양 월 값과 연누계를 원천 CSV 에서 따로 센 값과 비교한다', { skip: !haveCsv }, () => {
  const pick = (name, key, nameOf = (r) => r.시도) => {
    const rows = csv(name).filter((r) => r.구분 === '총계' && r.부문 === '총계');
    return (sido, ym) => rows.filter((r) => nameOf(r) === sido && r.기간 === ym).reduce((a, r) => a + Number(r[key]), 0);
  };
  const start = pick('molit_착공_월계.csv', '착공실적_호'), complete = pick('molit_준공_월계.csv', '준공실적_호');
  for (const ym of ['2022-03', '2025-12', '2026-08']) {
    assert.equal(C.valueAt(molit, 'start', '11', ym), start('서울', ym), `착공 서울 ${ym}`);
    assert.equal(C.valueAt(molit, 'start', C.NATION, ym), start('전국', ym), `착공 전국 ${ym}`);
    assert.equal(C.valueAt(molit, 'complete', '41', ym), complete('경기', ym), `준공 경기 ${ym}`);
  }
  // 광주+전남 합산: 2026-06 까지는 두 행의 합, 2026-07 부터는 전남광주 행
  assert.equal(C.valueAt(molit, 'start', '12', '2026-06'), start('광주', '2026-06') + start('전남', '2026-06'));
  assert.equal(C.valueAt(molit, 'start', '12', '2026-08'), start('전남광주', '2026-08'));
  // 연누계 = 1~8월 월 값의 합
  const sum = [1, 2, 3, 4, 5, 6, 7, 8].reduce((a, m) => a + start('전국', `2026-0${m}`), 0);
  assert.equal(C.ytd(molit, 'start', C.NATION, '2026-08'), sum);
  // 인허가: 원천은 연초 누계. 2026-08 누계 = 우리 월 흐름의 연누계
  const permitRows = csv('molit_인허가_월별누계.csv').filter((r) => r.구분 === '총계' && r.부문 === '총계' && r.시도 === '전국');
  const cum = Object.fromEntries(permitRows.map((r) => [r.기간, Number(r.인허가실적_호)]));
  assert.equal(C.ytd(molit, 'permit', C.NATION, '2026-08'), cum['2026-08']);
  assert.equal(C.valueAt(molit, 'permit', C.NATION, '2026-05'), cum['2026-05'] - cum['2026-04']);
  assert.equal(C.valueAt(molit, 'permit', C.NATION, '2026-01'), cum['2026-01'], '1월은 누계 값 그대로');
  const sale = csv('molit_분양_공동주택.csv').filter((r) => r.구분1 === '합계' && r.기간 === '2026-08')[0];
  assert.equal(C.valueAt(molit, 'sale', C.NATION, '2026-08'), Number(sale.순계_합계));
});

test('잠정치는 2026-01~08 이고 마지막 달이 그 안에 있다', () => {
  assert.equal(C.lastMonth(molit), '2026-08');
  assert.ok(C.isProvisional(molit, '2026-08') && C.isProvisional(molit, '2026-01') && !C.isProvisional(molit, '2025-12'));
});

test('LH 준공 예정: 월별 합이 전체와 같고(351블록·151,590호), 월을 고르면 그 달의 블록만 나온다', () => {
  const all = C.lhByMonth(lh, '2026-01', 82);   // 2026-01 ~ 2032-10
  assert.equal(all.reduce((a, x) => a + x.units, 0), 151590);
  assert.equal(all.reduce((a, x) => a + x.blocks, 0), 351);
  const m = C.lhOfMonth(lh, '2026-01');
  assert.ok(m.length > 0 && m.every((b) => b.date.startsWith('2026-01')));
  assert.equal(C.lhUnits(m), all[0].units);
  const next12 = C.lhByMonth(lh, '2026-10', 12);
  assert.equal(next12.length, 12);
  assert.deepEqual([next12[0].ym, next12[11].ym], ['2026-10', '2027-09']);
  assert.equal(C.monthsBetween('2026-01-27'.slice(0, 7), '2026-10'), 9);   // 파일 기준일이 이만큼 묵었다
});

/* ── 화면이 쓰는 목록과 경로 규칙이 서로 맞는다(없는 링크·이름 없는 시군구를 막는다) ── */
const registry = require('../../registry/projects.json').projects;
const sources = require('../../data/board/sources.json');
const { DETAILS } = require('../../lib/shell/menu.ts');
const { STAGES } = require('../../lib/board/stages.ts');
const { AGENCIES } = require('../../lib/board/agencies.ts');
const fsx = fs;

test('사업 id 는 경로 규칙에 맞고 겹치지 않으며, 모든 사업의 시군구·단계·법정동이 이름 표와 맞는다', () => {
  const ids = registry.map((p) => p.id);
  assert.equal(new Set(ids).size, ids.length);
  for (const p of registry) {
    assert.match(p.id, DETAILS.project.id, p.id);
    assert.ok(STAGES.some((s) => s.code === p.stageCode), `${p.id} 단계 ${p.stageCode}`);
    assert.ok(p.bjdCodes.every((b) => b.startsWith(p.sgg)), `${p.id} 법정동이 시군구 ${p.sgg} 안에 있어야 한다`);
    assert.ok(molit.sido.some((s) => s.code === p.sgg.slice(0, 2)), `${p.id} 시도 ${p.sgg.slice(0, 2)}`);
  }
});

test('SGG 이름 표: 레지스트리의 모든 시군구가 있고, 시도 코드가 시군구 앞 2자리다', () => {
  const { SGG } = (() => { const src = fsx.readFileSync(path.join(ROOT, 'lib/board/data.ts'), 'utf8'); const block = /export const SGG[^=]*= (\{[\s\S]*?\n\});/.exec(src)[1]; return { SGG: Function(`return (${block})`)() }; })();
  for (const sgg of new Set(registry.map((p) => p.sgg))) assert.ok(SGG[sgg], `${sgg} 이름이 없다`);
  for (const [code, s] of Object.entries(SGG)) { assert.equal(s.sido, code.slice(0, 2)); assert.ok(molit.sido.some((x) => x.code === s.sido), code); }
});

test('단계·기관 경로 규칙: 6단계 코드와 기관 id 가 DETAILS 의 식별자 규칙과 같다', () => {
  assert.deepEqual(STAGES.map((s) => s.code), ['01', '02', '03', '04', '05', '06']);
  for (const s of STAGES) assert.match(s.code, DETAILS.stage.id);
  assert.deepEqual(AGENCIES.map((a) => a.id), ['lh', 'local', 'gh', 'sh', 'mnd']);
  for (const a of AGENCIES) assert.match(a.id, DETAILS.agency.id);
  assert.deepEqual(AGENCIES.filter((a) => a.ready).map((a) => a.actor), ['LH', '지자체']);   // 화면에 쓸 데이터가 있는 기관은 통계누리 시행주체와 이어진다
  for (const a of AGENCIES.filter((x) => x.ready)) assert.ok(C.ACTORS.includes(a.actor));
});

test('월 상세로 열리는 달은 실적 60개월 + LH 예정 달이고, 모두 DETAILS.month 규칙에 맞는다', () => {
  const lhMonths = [...new Set(lh.blocks.map((b) => b.date.slice(0, 7)))];
  const all = [...new Set([...molit.months, ...lhMonths])];
  for (const m of all) assert.match(m, DETAILS.month.id, m);
  assert.ok(all.includes('2026-10'), '종합상황판의 월 상세 예시(2026-10)가 열려야 한다');
});

test('카탈로그가 말하는 "이 화면들이 읽음" 은 알려진 화면뿐이다(없는 경로를 링크하지 않는다)', () => {
  const known = new Set(['/', '/area', '/month', '/agency', '/projects', '/project', '/map']);
  for (const s of sources.items) for (const u of s.usedBy) assert.ok(known.has(u), `${s.id}: ${u}`);
});
