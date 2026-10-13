/* 로컬 캐시: 메모리 + 파일, 짧은 보관(TTL). 원천 응답을 오래 쌓아 두지 않는다.

   - 위치: CACHE_DIR 환경변수, 없으면 Vercel 에서는 os.tmpdir()/jt-cache(인스턴스가 끝나면 사라짐), 로컬은 저장소의 .cache/(gitignore).
   - TTL 은 호출하는 쪽이 정한다(상한 MAX_TTL_MS=24시간). 만료된 파일은 읽을 때 지운다. 총량이 maxBytes(기본 50 MB)를 넘으면 오래된 파일부터 지운다.
   - 같은 키를 동시에 요청하면 한 번만 가져온다(wrap 의 진행 중 요청 공유).
   - 값은 JSON 으로 저장 가능한 것만. 키 문자열은 해시해 파일 이름으로 쓰고, 인증키 같은 비밀을 키나 값에 넣지 않는다.
   시험: tests/js/cache.test.cjs */
'use strict';
const fs = require('fs');
const os = require('os');
const path = require('path');
const crypto = require('crypto');

const MAX_TTL_MS = 24 * 3600 * 1000;
const DEFAULT_MAX_BYTES = 50 * 1024 * 1024;

function defaultDir(env = process.env) {
  if (env.CACHE_DIR) return env.CACHE_DIR;
  return env.VERCEL ? path.join(os.tmpdir(), 'jt-cache') : path.join(require('./root.js').ROOT, '.cache');
}

function createCache({ dir = defaultDir(), maxBytes = DEFAULT_MAX_BYTES, now = () => Date.now(), persist = true } = {}) {
  const mem = new Map();        // key → { exp, value }
  const inflight = new Map();   // key → Promise
  const fileOf = (key) => path.join(dir, crypto.createHash('sha1').update(String(key)).digest('hex') + '.json');
  const clampTtl = (ttlMs) => Math.max(0, Math.min(Number(ttlMs) || 0, MAX_TTL_MS));

  function get(key) {
    const m = mem.get(key);
    if (m) { if (m.exp > now()) return m.value; mem.delete(key); }
    if (!persist) return undefined;
    const f = fileOf(key);
    try {
      const rec = JSON.parse(fs.readFileSync(f, 'utf8'));
      if (rec.key === key && rec.exp > now()) { mem.set(key, { exp: rec.exp, value: rec.value }); return rec.value; }
      fs.unlinkSync(f);
    } catch (e) { /* 없거나 깨졌으면 없는 것으로 */ }
    return undefined;
  }
  function set(key, value, ttlMs) {
    const exp = now() + clampTtl(ttlMs);
    if (exp <= now()) return;
    mem.set(key, { exp, value });
    if (!persist) return;
    try {
      fs.mkdirSync(dir, { recursive: true });
      fs.writeFileSync(fileOf(key), JSON.stringify({ key, exp, value }));
      trim();
    } catch (e) { /* 디스크에 못 써도 메모리 캐시만으로 동작 */ }
  }
  /* 총량 상한: 오래된(수정 시각이 이른) 파일부터 지운다 */
  function trim() {
    try {
      const files = fs.readdirSync(/*turbopackIgnore: true*/ dir).filter((n) => n.endsWith('.json')).map((n) => { const p = path.join(/*turbopackIgnore: true*/ dir, n), st = fs.statSync(/*turbopackIgnore: true*/ p); return { p, size: st.size, t: st.mtimeMs }; });
      let total = files.reduce((a, f) => a + f.size, 0);
      for (const f of files.sort((a, b) => a.t - b.t)) { if (total <= maxBytes) break; fs.unlinkSync(f.p); total -= f.size; }
    } catch (e) { /* 무시 */ }
  }
  /* 캐시에 있으면 그 값, 없으면 loader() 결과를 ttlMs 동안 저장. loader 가 실패하면 저장하지 않는다 */
  async function wrap(key, ttlMs, loader) {
    const hit = get(key);
    if (hit !== undefined) return hit;
    if (inflight.has(key)) return inflight.get(key);
    const p = (async () => { try { const v = await loader(); if (v !== undefined) set(key, v, ttlMs); return v; } finally { inflight.delete(key); } })();
    inflight.set(key, p);
    return p;
  }
  /* 만료된 파일 정리(시작할 때나 가끔 부른다) → 지운 개수 */
  function purgeExpired() {
    let n = 0;
    if (!persist) return n;
    try {
      for (const name of fs.readdirSync(/*turbopackIgnore: true*/ dir)) {
        if (!name.endsWith('.json')) continue;
        const p = path.join(/*turbopackIgnore: true*/ dir, name);
        try { if (JSON.parse(fs.readFileSync(/*turbopackIgnore: true*/ p, 'utf8')).exp <= now()) { fs.unlinkSync(p); n++; } } catch (e) { fs.unlinkSync(p); n++; }
      }
    } catch (e) { /* 폴더 없음 */ }
    return n;
  }
  function stats() {
    let files = 0, bytes = 0;
    if (persist) try { for (const n of fs.readdirSync(/*turbopackIgnore: true*/ dir)) if (n.endsWith('.json')) { files++; bytes += fs.statSync(/*turbopackIgnore: true*/ path.join(/*turbopackIgnore: true*/ dir, n)).size; } } catch (e) { /* 없음 */ }
    return { memory: mem.size, files, bytes, dir: persist ? dir : null, maxBytes };
  }
  return { get, set, wrap, purgeExpired, stats, MAX_TTL_MS };
}

module.exports = { createCache, defaultDir, MAX_TTL_MS, DEFAULT_MAX_BYTES };
