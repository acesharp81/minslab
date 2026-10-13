'use strict';
// 빌드 직후(.next 가 있을 때만) API 함수의 파일 추적 결과를 점검한다. 제외 패턴이 node_modules 안 파일(next/dist/server/node-environment 등)까지
// 빼면 로컬 next start 는 멀쩡해도 Vercel 함수가 `Cannot find module` 로 죽는다(2026-10-09 미리보기 배포에서 /api/* 500). 빌드 없이 돌리면 건너뛴다.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const ROOT = path.join(__dirname, '..', '..');
const API = path.join(ROOT, '.next/server/app/api');
const built = fs.existsSync(API);
const routes = built ? [['bus'], ['v1', 'resolve'], ['v1', 'permits'], ['v1', 'notices'], ['v1', 'buildings'], ['v1', 'infra'], ['v1', 'codes', 'search']] : [];
const traced = (parts) => {
  const f = path.join(API, ...parts, 'route.js.nft.json');
  return JSON.parse(fs.readFileSync(f, 'utf8')).files.map((x) => path.relative(ROOT, path.resolve(path.dirname(f), x)));
};

test('API 함수 묶음에 next 런타임이 들어 있다(빠지면 배포 후 모든 /api 가 500)', { skip: !built && '.next 가 없다(npm run build 뒤에 돈다)' }, () => {
  for (const r of routes) {
    const files = traced(r);
    assert.ok(files.some((x) => x.startsWith('node_modules/next/dist/')), `${r.join('/')}: node_modules/next/dist 가 추적에 있어야 한다`);
    assert.ok(files.some((x) => x.startsWith(path.join('node_modules', 'next', 'dist', 'server', 'node-environment'))), `${r.join('/')}: next/dist/server/node-environment`);
  }
});

test('API 함수 묶음에 필요한 JSON 은 들어 있고, 로컬 캐시와 큰 번들은 없다', { skip: !built && '.next 가 없다' }, () => {
  const has = (r, p) => traced(r).includes(p);
  assert.ok(has(['v1', 'resolve'], 'registry/projects.json') && has(['v1', 'resolve'], 'regions/index.json'));
  assert.ok(has(['v1', 'permits'], 'registry/projects.json'));
  assert.ok(has(['bus'], 'regions/incheon-gyeyang/infra.json'));
  for (const r of routes) {
    const files = traced(r);
    assert.ok(!files.some((x) => x.startsWith('.cache/')), `${r.join('/')}: .cache`);
    assert.ok(!files.some((x) => /^regions\/[^/]+\/(buildings|projects|context)\.json$/.test(x)), `${r.join('/')}: 큰 번들`);
  }
});
