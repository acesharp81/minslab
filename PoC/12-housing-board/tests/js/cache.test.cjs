/* lib/cache.js — 로컬 캐시(메모리+파일, 짧은 보관) */
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const C = require('../../lib/cache.js');

const tmp = () => fs.mkdtempSync(path.join(os.tmpdir(), 'jtc-'));

test('set/get: TTL 안에서는 값을, 지나면 undefined 를 주고 파일도 지운다', () => {
  const dir = tmp(), clock = { t: 1000 }, c = C.createCache({ dir, now: () => clock.t });
  c.set('k', { a: 1 }, 5000);
  assert.deepEqual(c.get('k'), { a: 1 });
  assert.equal(c.stats().files, 1);
  clock.t += 5001;
  assert.equal(c.get('k'), undefined);
  assert.equal(c.stats().files, 0);
  fs.rmSync(dir, { recursive: true, force: true });
});

test('TTL 상한 24시간, TTL 0 이하는 저장하지 않는다', () => {
  const dir = tmp(), clock = { t: 0 }, c = C.createCache({ dir, now: () => clock.t });
  c.set('long', 1, 99 * 24 * 3600 * 1000);
  clock.t = C.MAX_TTL_MS - 1; assert.equal(c.get('long'), 1);
  clock.t = C.MAX_TTL_MS + 1; assert.equal(c.get('long'), undefined);
  c.set('zero', 1, 0); c.set('neg', 1, -5);
  assert.equal(c.get('zero'), undefined);
  assert.equal(c.stats().files, 0);
  fs.rmSync(dir, { recursive: true, force: true });
});

test('다른 인스턴스(재시작)에서도 파일에서 읽는다. 파일 이름은 키가 아니라 해시', () => {
  const dir = tmp(), clock = { t: 0 };
  C.createCache({ dir, now: () => clock.t }).set('stan:28245', [1, 2, 3], 60000);
  const c2 = C.createCache({ dir, now: () => clock.t });
  assert.deepEqual(c2.get('stan:28245'), [1, 2, 3]);
  for (const n of fs.readdirSync(dir)) assert.ok(/^[0-9a-f]{40}\.json$/.test(n), n);
  fs.rmSync(dir, { recursive: true, force: true });
});

test('wrap: 한 번만 가져오고(동시 요청도 공유), 실패는 저장하지 않으며, undefined 는 저장하지 않는다', async () => {
  const dir = tmp(), c = C.createCache({ dir });
  let n = 0;
  const load = async () => { n++; await new Promise((r) => setTimeout(r, 10)); return { v: n }; };
  const [a, b] = await Promise.all([c.wrap('x', 1000, load), c.wrap('x', 1000, load)]);
  assert.deepEqual(a, b); assert.equal(n, 1);
  assert.deepEqual(await c.wrap('x', 1000, load), { v: 1 }); assert.equal(n, 1);
  await assert.rejects(c.wrap('bad', 1000, async () => { throw new Error('upstream'); }), /upstream/);
  assert.equal(c.get('bad'), undefined);
  await c.wrap('none', 1000, async () => undefined);
  assert.equal(c.get('none'), undefined);
  fs.rmSync(dir, { recursive: true, force: true });
});

test('총량 상한을 넘으면 오래된 파일부터 지운다', () => {
  const dir = tmp(), c = C.createCache({ dir, maxBytes: 600 });
  for (let i = 0; i < 6; i++) { c.set('k' + i, 'x'.repeat(150), 60000); fs.utimesSync(path.join(dir, fs.readdirSync(dir).sort((a, b) => fs.statSync(path.join(dir, a)).mtimeMs - fs.statSync(path.join(dir, b)).mtimeMs).slice(-1)[0]), new Date(1000 + i), new Date(1000 + i)); }
  assert.ok(c.stats().bytes <= 600, String(c.stats().bytes));
  assert.ok(c.stats().files < 6);
  fs.rmSync(dir, { recursive: true, force: true });
});

test('purgeExpired: 만료·깨진 파일을 지운다. persist:false 는 파일을 만들지 않는다', () => {
  const dir = tmp(), clock = { t: 0 }, c = C.createCache({ dir, now: () => clock.t });
  c.set('a', 1, 10); c.set('b', 2, 100000); fs.writeFileSync(path.join(dir, 'broken.json'), '{x');
  clock.t = 50;
  assert.equal(c.purgeExpired(), 2);
  assert.equal(c.stats().files, 1);
  const m = C.createCache({ dir: path.join(dir, 'never'), persist: false }); m.set('z', 1, 1000);
  assert.equal(m.get('z'), 1); assert.equal(fs.existsSync(path.join(dir, 'never')), false);
  fs.rmSync(dir, { recursive: true, force: true });
});

test('기본 위치: CACHE_DIR 우선, Vercel 이면 임시 폴더, 로컬은 저장소의 .cache', () => {
  assert.equal(C.defaultDir({ CACHE_DIR: '/x/y' }), '/x/y');
  assert.ok(C.defaultDir({ VERCEL: '1' }).startsWith(os.tmpdir()));
  assert.ok(C.defaultDir({}).endsWith(path.join('housing-board', '.cache')) || C.defaultDir({}).endsWith('.cache'));
});
