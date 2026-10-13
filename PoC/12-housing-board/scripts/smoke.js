#!/usr/bin/env node
/* 전국 표본 점검: 지역 이름을 /api/v1/codes/search 로 코드로 바꾼 뒤 resolve → buildings → permits → infra 를 차례로 불러
   "번들 없이도 지도가 끝까지 열리는가"를 지역마다 표로 보여 준다(경계 윤곽·건물·인허가·기반시설·응답 시간).
   사용: node scripts/smoke.js [기본주소] [표본파일|지역이름...]   (기본주소 기본값 https://housing-board.vercel.app, 표본 기본값 tests/smoke/regions.json)
   예:   node scripts/smoke.js http://localhost:8000
         node scripts/smoke.js https://housing-board.vercel.app "하남시 감일동" "장위동 68-37"
   호출 사이에 간격(SMOKE_GAP_MS, 기본 900)을 둔다: 행정표준코드·건물대장 API 는 초당 한도가 있어 몰아 부르면 막힌다(키 풀이 하루 소진으로 기록하던 결함의 원인).
   종료 코드: 하나라도 '열리지 않음'(해석 실패·경계 없음)이면 1. 인허가 0건·정류소 없음(서울)은 정상이다.
   시험: tests/js/smoke.test.cjs(판정 함수) */
'use strict';
const fs = require('fs');
const path = require('path');

const GAP_MS = Number(process.env.SMOKE_GAP_MS) > 0 ? Number(process.env.SMOKE_GAP_MS) : 900;
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

/* 경계 윤곽이 쓸 만한가: Polygon/MultiPolygon 이고 점 4개 이상인 링이 하나 이상(필지로 열면 parcel.geometry 가 경계) */
function geometryOk(g) {
  if (!g || !g.type || !Array.isArray(g.coordinates)) return false;
  const rings = g.type === 'Polygon' ? [g.coordinates[0]] : g.type === 'MultiPolygon' ? g.coordinates.map((p) => p[0]) : [];
  return rings.some((r) => Array.isArray(r) && r.length >= 4 && r.every((c) => Array.isArray(c) && Number.isFinite(c[0]) && Number.isFinite(c[1])));
}
/* 중심 좌표 → 건물 칸 번호(0.01° 칸) */
const cellOf = (lon, lat) => `${Math.floor(lon * 100)},${Math.floor(lat * 100)}`;
/* 한 줄 판정: 열림 = 해석 성공 + 경계 있음. 경고는 열리지만 손볼 것 */
function judge(r) {
  const warn = [];
  if (!r.search || !r.search.ok) return { open: false, why: `검색 실패(${(r.search && r.search.status) || '없음'})`, warn };
  if (!r.resolve || !r.resolve.ok) return { open: false, why: `해석 실패(${(r.resolve && r.resolve.status) || '없음'} ${(r.resolve && r.resolve.code) || ''})`, warn };
  if (!r.resolve.geometry) return { open: false, why: '경계 없음', warn };
  if (r.buildings && !r.buildings.ok) warn.push(`건물 ${r.buildings.status}`);
  else if (r.buildings && r.buildings.count === 0) warn.push('건물 0');
  if (r.permits && !r.permits.ok) warn.push(`인허가 ${r.permits.status}`);
  if (r.permits && r.permits.ok && r.permits.ledgerError) warn.push(`대장:${r.permits.ledgerError}`);
  if (r.permits && r.permits.ok && r.permits.parcelErrors) warn.push(`필지 오류 ${r.permits.parcelErrors}`);
  if (r.infra && !r.infra.ok) warn.push(`기반시설 ${r.infra.status}`);
  if (r.infra && r.infra.ok && (r.infra.schoolsError || r.infra.stopsError)) warn.push(`기반시설 일부 실패`);
  const slow = [['해석', r.resolve.ms, 8000], ['건물', r.buildings && r.buildings.ms, 15000], ['인허가', r.permits && r.permits.ms, 20000], ['기반시설', r.infra && r.infra.ms, 12000]].filter(([, ms, lim]) => ms > lim);
  for (const [n, ms] of slow) warn.push(`${n} ${Math.round(ms / 1000)}초(느림)`);
  return { open: true, why: '', warn };
}

async function main() {
  const base = (process.argv[2] || 'https://housing-board.vercel.app').replace(/\/$/, '');
  const rest = process.argv.slice(3);
  const list = rest.length ? rest.map((q) => ({ q })) : JSON.parse(fs.readFileSync(path.join(__dirname, '..', 'tests', 'smoke', 'regions.json'), 'utf8')).regions;
  const call = async (url) => {
    const t = Date.now();
    try {
      const res = await fetch(base + url, { signal: AbortSignal.timeout(60000) });
      const body = await res.json().catch(() => null);
      return { status: res.status, ms: Date.now() - t, body };
    } catch (e) { return { status: 0, ms: Date.now() - t, body: null, error: String(e && e.message) }; }
  };
  const rows = [];
  for (const entry of list) {
    const r = { name: entry.q };
    let s = await call(`/api/v1/codes/search?q=${encodeURIComponent(entry.q)}&limit=3`); await sleep(GAP_MS);
    const first = s.body && s.body.items && s.body.items[0];
    r.search = { ok: s.status === 200 && !!first, status: s.status, ms: s.ms, kind: first && first.kind, code: first && first.code, tier: first && first.tier, n: s.body && s.body.items ? s.body.items.length : 0 };
    if (r.search.ok) {
      const rs = await call(`/api/v1/resolve?${first.kind}=${first.code}&geometry=1`); await sleep(GAP_MS);
      const d = rs.body || {};
      r.resolve = { ok: rs.status === 200, status: rs.status, ms: rs.ms, code: d.code, type: d.type, name: d.name, level: d.level, tier: d.coverage && d.coverage.tier, geometry: geometryOk(d.geometry) || geometryOk(d.parcel && d.parcel.geometry), center: d.center, warnings: (d.warnings || []).length };
      if (r.resolve.ok && Array.isArray(d.center)) {
        const b = await call(`/api/v1/buildings?cell=${cellOf(d.center[0], d.center[1])}`); await sleep(GAP_MS);
        r.buildings = { ok: b.status === 200, status: b.status, ms: b.ms, count: b.body && b.body.features ? b.body.features.length : 0 };
      }
      if (r.resolve.ok && d.bjd) {
        const p = await call(`/api/v1/permits?bjd=${d.bjd}`); await sleep(GAP_MS);
        const m = (p.body && p.body.meta) || {};
        r.permits = { ok: p.status === 200, status: p.status, ms: p.ms, features: p.body && p.body.features ? p.body.features.length : 0, candidates: m.candidates, blocks: m.blockProjects, unlocated: m.unlocated, ledger: m.ledger && m.ledger.used, ledgerError: m.ledger && m.ledger.error, parcelErrors: m.parcelErrors };
        if (r.permits.ok && r.permits.features > 0) {
          const i = await call(`/api/v1/infra?bjd=${d.bjd}`); await sleep(GAP_MS);
          const im = (i.body && i.body.meta) || {};
          r.infra = { ok: i.status === 200, status: i.status, ms: i.ms, schools: i.body && i.body.schools ? i.body.schools.length : 0, stops: i.body && i.body.stops ? i.body.stops.length : 0, noBus: !!im.noBus, schoolsError: im.schoolsError, stopsError: im.stopsError };
        }
      }
    }
    r.verdict = judge(r);
    rows.push(r);
    const v = r.verdict, f = (x) => (x == null ? '-' : x);
    console.log(`${v.open ? '열림' : '실패'}  ${r.name.padEnd(22)} ${f(r.resolve && r.resolve.name)} [${f(r.resolve && r.resolve.type)}/${f(r.resolve && r.resolve.tier)}] 건물 ${f(r.buildings && r.buildings.count)} 인허가 ${f(r.permits && r.permits.features)}(블록 ${f(r.permits && r.permits.blocks)}) 학교 ${f(r.infra && r.infra.schools)} 정류소 ${f(r.infra && r.infra.stops)}${r.infra && r.infra.noBus ? '(자료 없음)' : ''}  ${v.why}${v.warn.length ? ' ⚠ ' + v.warn.join(', ') : ''}`);
  }
  const bad = rows.filter((r) => !r.verdict.open);
  console.log(`\n${base}: ${rows.length}곳 중 열림 ${rows.length - bad.length}, 실패 ${bad.length}, 경고 ${rows.filter((r) => r.verdict.open && r.verdict.warn.length).length}`);
  if (process.env.SMOKE_JSON) fs.writeFileSync(process.env.SMOKE_JSON, JSON.stringify(rows, null, 1));
  process.exitCode = bad.length ? 1 : 0;
}

if (require.main === module) main().catch((e) => { console.error(e); process.exit(2); });
module.exports = { geometryOk, cellOf, judge };
