'use strict';
/* lib/root.js — 번들러(Next.js/Turbopack)가 __dirname 을 가짜 경로("/ROOT/lib")로 바꿔 데이터 파일을 못 찾던 문제의 재발 방지.
   next start 에서 /api/v1/resolve?project= 가 unknown-project, /api/bus 가 no-live-routes 로 답했다(레지스트리·infra.json 을 못 찾음). */
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('fs');
const path = require('path');

const ROOT = path.join(__dirname, '..', '..');

test('일반 Node 에서 프로젝트 루트는 이 저장소의 루트이고 데이터 폴더가 있다', () => {
  const { ROOT: r } = require('../../lib/root.js');
  assert.equal(r, ROOT);
  for (const p of ['regions/index.json', 'registry/projects.json', 'package.json']) assert.ok(fs.existsSync(path.join(r, p)), p);
});

test('핸들러와 lib 는 __dirname 으로 데이터 경로를 만들지 않는다(lib/root.js 만 쓴다)', () => {
  const walk = (d) => fs.readdirSync(d, { withFileTypes: true }).flatMap((e) => (e.isDirectory() ? walk(path.join(d, e.name)) : [path.join(d, e.name)]));
  for (const f of [...walk(path.join(ROOT, 'lib')), ...walk(path.join(ROOT, 'handlers'))].filter((x) => /\.(js|ts)$/.test(x))) {
    if (path.relative(ROOT, f) === path.join('lib', 'root.js')) continue;
    assert.doesNotMatch(fs.readFileSync(f, 'utf8'), /__dirname/, `${path.relative(ROOT, f)}: 번들 안에서 __dirname 이 가짜 경로가 된다. lib/root.js 의 ROOT 를 쓴다`);
  }
});

test('기본 데이터 경로는 루트 기준이다: 레지스트리·지역 번들·로컬 캐시', () => {
  assert.equal(path.relative(ROOT, require('../../lib/registry.js').DEFAULT_FILE), path.join('registry', 'projects.json'));
  const cov = require('../../lib/coverage.js').readCoverage();
  assert.ok(JSON.stringify(cov).includes('12330'), '기본 경로로 읽은 지역 번들 표에 광산구(12330)가 있어야 한다');
  assert.equal(path.relative(ROOT, require('../../lib/cache.js').defaultDir({})), '.cache');
});
