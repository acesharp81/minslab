'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const root = path.join(__dirname, '../..');
const read = (file) => fs.readFileSync(path.join(root, file), 'utf8');
const source = JSON.parse(read('data/home10/converted.json'));
const map = JSON.parse(read('data/home10/map.json'));
const rows = source.projects.filter((p) => p.policyId === 'POL_2025_0907');

test('변환본에 9·7 정책과 연결 자료만 저장된다', () => {
  assert.equal(source.projects.length, 152);
  assert.deepEqual(source.policies.map((p) => p.id), ['POL_2025_0907']);
  assert.deepEqual(source.policyMonitor.items.map((p) => p.id), ['POL_2025_0907']);
  assert.equal(source.programs.length, 8);
  assert.ok(source.programs.every((p) => p.policyId === 'POL_2025_0907'));
  assert.equal(source.sources.length, 6);
  assert.ok(source.projects.every((p) => p.policyId === 'POL_2025_0907'));
  assert.ok(source.coverage.every((c) => source.sources.some((s) => s.id === c.sourceId)));
  for (const key of ['annualSupply', 'roadmap', 'plans', 'identitySummary', 'locationSummary']) {
    assert.equal(source[key], undefined, key);
  }
});

test('공개 지도 후보 ID는 PoC 10의 9·7 검토 후보와 정확히 일치한다', () => {
  assert.deepEqual(new Set(map.projects.map((p) => p.id)), new Set(rows.map((p) => p.id)));
  assert.ok(rows.every((p) => p.projectProgramStatus === 'REVIEW'));
  assert.ok(rows.every((p) => p.actualDeliveryUnits === null));
});

test('9·7 화면은 원본 SAMPLE·예시 PRJ·다른 정책 데이터 모듈을 읽지 않는다', () => {
  const pages = ['page.tsx', 'projects/page.tsx', 'area/page.tsx', 'area/[id]/page.tsx', 'stage/page.tsx', 'stage/[id]/page.tsx', 'agency/page.tsx', 'agency/[id]/page.tsx', 'reports/page.tsx', 'sources/page.tsx', 'my-area/page.tsx', 'home-project/[id]/page.tsx'];
  for (const page of pages) {
    const text = read(`app/(dashboard)/${page}`);
    assert.doesNotMatch(text, /lib\/board\/(data|sample)|SAMPLE|registry\/projects/, page);
  }
  for (const page of ['project/[id]/page.tsx', 'month/[id]/page.tsx']) assert.match(read(`app/(dashboard)/${page}`), /notFound\(\)/);
});
