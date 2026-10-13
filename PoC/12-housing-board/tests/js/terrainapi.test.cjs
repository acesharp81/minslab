'use strict';
/* handlers/v1/terrain.js — 지형 타일 중계(계획서 16절, 2026-10-10). 네트워크 없이 가짜 fetch 로 시험한다. */
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const terrain = require('../../handlers/v1/terrain.js');
const { createCache } = require('../../lib/cache.js');

const PNG = Buffer.from([0x89, 0x50, 0x4e, 0x47, 1, 2, 3]);
const bin = (status = 200) => ({ ok: status === 200, status, arrayBuffer: async () => PNG.buffer.slice(PNG.byteOffset, PNG.byteOffset + PNG.length) });
const GY = { z: 14, x: 13960, y: 6345 };   // 인천 계양 근처 타일

function harness(over = {}) {
  const calls = [];
  const clock = { t: 1_000_000 };
  const handler = terrain.createHandler({
    fetch: async (url, opts) => { calls.push(url); return (over.fetch || (async () => bin()))(url, opts); },
    env: over.env || {}, now: () => clock.t, cache: createCache({ persist: false, now: () => clock.t }),
  });
  const run = async (url, method = 'GET') => {
    const res = { headers: {}, statusCode: 0, body: null, setHeader(k, v) { this.headers[k.toLowerCase()] = v; }, end(b) { this.body = b; } };
    await handler({ method, url }, res);
    return res;
  };
  return { run, calls, clock };
}
const q = ({ z, x, y }) => `/api/v1/terrain?z=${z}&x=${x}&y=${y}`;

test('한국 타일은 S3 terrarium 을 받아 PNG 그대로, CDN 1년·브라우저 하루 캐시', async () => {
  const h = harness();
  const r = await h.run(q(GY));
  assert.equal(r.statusCode, 200);
  assert.equal(r.headers['content-type'], 'image/png');
  assert.equal(r.headers['cache-control'], 'public, max-age=86400, s-maxage=31536000, immutable');
  assert.deepEqual(Buffer.from(r.body), PNG);
  assert.deepEqual(h.calls, ['https://s3.amazonaws.com/elevation-tiles-prod/terrarium/14/13960/6345.png']);
});

test('같은 타일은 로컬 캐시에서(원천을 다시 부르지 않는다)', async () => {
  const h = harness();
  await h.run(q(GY)); const r = await h.run(q(GY));
  assert.equal(r.statusCode, 200); assert.deepEqual(Buffer.from(r.body), PNG);
  assert.equal(h.calls.length, 1);
});

test('잘못된 요청·한국 밖·z 15 이상은 400, 원천을 부르지 않는다(열린 중계 방지)', async () => {
  const h = harness();
  for (const [url, code] of [['/api/v1/terrain?z=14&x=1', 'invalid-query'], ['/api/v1/terrain?z=a&x=1&y=1', 'invalid-query'], ['/api/v1/terrain?z=14&x=1&y=1&k=2', 'invalid-query'],
    [q({ z: 14, x: 0, y: 0 }), 'out-of-range'], [q({ z: 15, x: 27920, y: 12690 }), 'out-of-range'], [q({ z: 3, x: 8, y: 1 }), 'out-of-range']]) {
    const r = await h.run(url);
    assert.equal(r.statusCode, 400, url); assert.equal(JSON.parse(r.body).code, code, url);
  }
  assert.equal(h.calls.length, 0);
  assert.equal(terrain.inKorea(0, 0, 0), true, 'z0 한 장은 한국을 덮는다');
  assert.equal(terrain.inKorea(5, 27, 12), true, 'z5 한국 타일');
});

test('GET·HEAD 만, 원천 404 는 404(하루 CDN 캐시), 원천 오류·연결 실패는 502(no-store), 원천 URL 은 응답에 없다', async () => {
  let h = harness();
  const m = await h.run(q(GY), 'POST'); assert.equal(m.statusCode, 405); assert.equal(m.headers.allow, 'GET, HEAD');
  h = harness({ fetch: async () => bin(404) });
  const nf = await h.run(q(GY)); assert.equal(nf.statusCode, 404); assert.equal(nf.headers['cache-control'], 'public, s-maxage=86400');
  h = harness({ fetch: async () => bin(500) });
  const bad = await h.run(q(GY)); assert.equal(bad.statusCode, 502); assert.equal(bad.headers['cache-control'], 'no-store'); assert.doesNotMatch(bad.body, /amazonaws/);
  h = harness({ fetch: async () => { throw new Error('ECONNRESET s3.amazonaws.com'); } });
  const down = await h.run(q(GY)); assert.equal(down.statusCode, 502); assert.doesNotMatch(down.body, /amazonaws|ECONN/);
});

test('인스턴스별 시간당 원천 호출 상한(TERRAIN_UPSTREAM_PER_HOUR)을 넘으면 429, 다음 시간에 풀린다', async () => {
  const h = harness({ env: { TERRAIN_UPSTREAM_PER_HOUR: '2' } });
  assert.equal((await h.run(q({ z: 14, x: 13960, y: 6345 }))).statusCode, 200);
  assert.equal((await h.run(q({ z: 14, x: 13961, y: 6345 }))).statusCode, 200);
  const r = await h.run(q({ z: 14, x: 13962, y: 6345 }));
  assert.equal(r.statusCode, 429); assert.equal(r.headers['cache-control'], 'no-store');
  assert.equal((await h.run(q({ z: 14, x: 13960, y: 6345 }))).statusCode, 200, '캐시된 타일은 상한과 상관없다');
  h.clock.t += 3600 * 1000;
  assert.equal((await h.run(q({ z: 14, x: 13962, y: 6345 }))).statusCode, 200);
});

test('지도는 상황판 안에서만 중계를 쓰고(옛 정적 열기는 S3), 감싸는 쪽은 바이트 본문을 넘긴다', () => {
  const app = fs.readFileSync(path.join(__dirname, '..', '..', 'assets/js/app.js'), 'utf8');
  assert.match(app, /const DEM_TILES = \[SHELL \? `\$\{location\.origin\}\/poc\/housing-board\/api\/v1\/terrain\?z=\{z\}&x=\{x\}&y=\{y\}` : 'https:\/\/s3\.amazonaws\.com\/elevation-tiles-prod\/terrarium\/\{z\}\/\{x\}\/\{y\}\.png'\];/);
  assert.ok(app.indexOf('const SHELL =') < app.indexOf('const DEM_TILES ='), 'SHELL 이 먼저 정해진다');
  assert.match(fs.readFileSync(path.join(__dirname, '..', '..', 'lib/next-handler.ts'), 'utf8'), /end\(chunk\?: string \| Uint8Array\): void;/);
});
