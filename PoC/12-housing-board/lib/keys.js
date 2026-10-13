/* 공공데이터포털 인증키 풀: .env.local(또는 서버 환경변수)의 여러 키를 용도별로 나눠 쓰고, 서비스별 일일 한도를 넘기지 않게 고른다.

   변수 이름
     DATA_GO_KR_KEY_<용도>_<번호>          예 DATA_GO_KR_KEY_BUS_1, DATA_GO_KR_KEY_BUS_2, DATA_GO_KR_KEY_BUILD_1
     DATA_GO_KR_SERVICES_<용도>_<번호>     (선택) 그 키로 활용신청한 서비스 목록 'tago,hub'. 없으면 모든 서비스에 쓸 수 있다고 본다
     DATA_GO_KR_KEY                       기본(호환) 키. 용도에 키가 없거나 모두 소진됐을 때만 쓴다
     DATA_GO_KR_LIMITS                    (선택) 서비스별 일일 한도 'tago=10000,seoul=1000'. 기본값은 DEFAULT_LIMITS
   DATA_GO_KR_PROFILE                   (선택) 'demo' 로 두면 서버가 쓰는 용도(BUS·RESOLVE)는 DATA_GO_KR_KEY_DEMO_<N> 키를 먼저 쓴다. 비우면 개발 키를 쓴다. BUILD 는 영향받지 않는다
   용도: BUILD(번들·색인 배치) · RESOLVE(코드 해석) · BUS(버스 요청 시 조회) · DEMO(시연 프로파일 전용). 이름은 대문자·숫자만.

   규칙
   - 키 값은 어디에도 남기지 않는다(오류 문구·로그·캐시·응답). 키는 'BUS_2' 같은 라벨로만 가리킨다.
   - 고르는 방법: 후보 중 오늘(한국시간) 그 서비스를 가장 적게 쓴 키. 한도에 닿은 키와 한도 오류를 받은 키는 다음 한국시간 자정까지 건너뛴다.
   - 사용량은 store 에 한국시간 날짜별로 센다. 로컬은 파일(.cache/key-usage.json), 서버리스는 인스턴스 메모리(재시작하면 0부터).
   - NEXT_PUBLIC_ 접두를 붙이지 않는다(브라우저로 나가면 안 된다).
   시험: tests/js/keys.test.cjs */
'use strict';
const fs = require('fs');
const path = require('path');

const DEFAULT_LIMITS = { tago: 10000, seoul: 1000, stan: 10000, hub: 10000, hubledger: 10000, myhome: 10000, lh: 10000 };
const KEY_RE = /^DATA_GO_KR_KEY_([A-Z0-9]+)_(\d+)$/;
const KST_MS = 9 * 3600 * 1000;
const RUNTIME_PURPOSES = new Set(['BUS', 'RESOLVE']);   // 시연(demo) 프로파일이 키를 바꿔 끼우는 용도

class KeyPoolError extends Error {
  constructor(code, message, retryAfterSec) { super(message); this.name = 'KeyPoolError'; this.code = code; if (retryAfterSec != null) this.retryAfterSec = retryAfterSec; }
}

const kstDate = (now) => new Date(now + KST_MS).toISOString().slice(0, 10);
function secondsToKstMidnight(now) { const t = new Date(now + KST_MS); const next = Date.UTC(t.getUTCFullYear(), t.getUTCMonth(), t.getUTCDate() + 1); return Math.max(1, Math.ceil((next - (now + KST_MS)) / 1000)); }

function parseLimits(text) {
  const out = {};
  for (const part of String(text || '').split(',')) {
    const [k, v] = part.split('=').map((s) => s.trim());
    const n = Number(v);
    if (k && Number.isFinite(n) && n > 0) out[k.toLowerCase()] = Math.floor(n);
  }
  return out;
}
const decodeKey = (v) => { const s = String(v || '').trim().replace(/^["']|["']$/g, ''); return s.includes('%') ? decodeURIComponent(s) : s; };

/* env → { 용도: [{label, value, services|null}] , fallback: {label,value}|null } */
function loadKeys(env) {
  const byPurpose = {};
  for (const name of Object.keys(env || {})) {
    const m = KEY_RE.exec(name);
    const value = m && decodeKey(env[name]);
    if (!m || !value) continue;
    const purpose = m[1], n = Number(m[2]);
    const svc = String(env[`DATA_GO_KR_SERVICES_${purpose}_${n}`] || '').split(',').map((s) => s.trim().toLowerCase()).filter(Boolean);
    (byPurpose[purpose] = byPurpose[purpose] || []).push({ label: `${purpose}_${n}`, n, value, services: svc.length ? new Set(svc) : null });
  }
  for (const list of Object.values(byPurpose)) list.sort((a, b) => a.n - b.n);
  const legacy = decodeKey(env && env.DATA_GO_KR_KEY);
  return { byPurpose, fallback: legacy ? { label: 'DEFAULT', value: legacy, services: null } : null };
}

/* 사용량 저장소: 메모리(기본) 또는 파일. 모양 { date, counts: {라벨: {서비스: n}}, exhausted: {라벨: {서비스: true}} } */
function memoryStore() {
  let state = null;
  return { load: () => state, save: (s) => { state = s; } };
}
function fileStore(file) {
  return {
    load() { try { return JSON.parse(fs.readFileSync(file, 'utf8')); } catch (e) { return null; } },
    save(s) { try { fs.mkdirSync(path.dirname(file), { recursive: true }); fs.writeFileSync(file, JSON.stringify(s)); } catch (e) { /* 저장 못 해도 동작은 계속(메모리만) */ } },
  };
}

/* 한도 오류 판별: HTTP 429, 공공데이터포털 resultCode 22(JSON·XML), 오류 이름 */
/* 초당 호출 한도(LIMITED_NUMBER_OF_SERVICE_REQUESTS_PER_SECOND_EXCEEDS_ERROR)는 하루 한도가 아니다: 잠시 쉬었다 다시 부르면 되므로 키를 하루 쉬게 하지 않는다 */
function isThrottle(x) {
  if (!x) return false;
  if (x instanceof Error) return x.throttled === true || /PER_SECOND/.test(x.message || '');
  if (typeof x === 'string') return /PER_SECOND/.test(x);
  if (typeof x === 'object') { if (x.throttled === true) return true; const msg = x.cmmMsgHeader || (x.OpenAPI_ServiceResponse && x.OpenAPI_ServiceResponse.cmmMsgHeader); return !!(msg && /PER_SECOND/.test(String(msg.errMsg || '') + String(msg.returnAuthMsg || ''))); }
  return false;
}
function isQuotaError(x) {
  if (!x || isThrottle(x)) return false;
  if (x instanceof Error) return /LIMITED_NUMBER|quota|\b429\b/i.test(x.message || '') || x.status === 429 || x.quota === true;
  if (typeof x === 'object') {
    if (x.status === 429 || x.quota === true) return true;
    const header = x.response && x.response.header;
    if (header && String(header.resultCode) === '22') return true;
    const msg = x.cmmMsgHeader || (x.OpenAPI_ServiceResponse && x.OpenAPI_ServiceResponse.cmmMsgHeader);
    if (msg && (String(msg.returnReasonCode) === '22' || /LIMITED_NUMBER/.test(String(msg.errMsg || '')))) return true;
  }
  if (typeof x === 'string') return /LIMITED_NUMBER_OF_SERVICE_REQUESTS_EXCEEDS_ERROR|<returnReasonCode>22<\/returnReasonCode>/.test(x);
  return false;
}

function createKeyPool({ env = process.env, now = () => Date.now(), store = memoryStore() } = {}) {
  const keys = loadKeys(env);
  const demo = String((env && env.DATA_GO_KR_PROFILE) || '').toLowerCase() === 'demo';
  /* 용도의 키 목록. 시연 프로파일이면 서버 용도(BUS·RESOLVE)는 DEMO 키가 있을 때 그것을 쓴다 */
  const listFor = (purpose) => {
    const p = String(purpose || '').toUpperCase();
    return demo && RUNTIME_PURPOSES.has(p) && (keys.byPurpose.DEMO || []).length ? keys.byPurpose.DEMO : (keys.byPurpose[p] || []);
  };
  const limits = Object.assign({}, DEFAULT_LIMITS, parseLimits(env && env.DATA_GO_KR_LIMITS));
  let rr = 0;   // 같은 사용량일 때 돌려 쓰기

  function state() {
    const today = kstDate(now());
    let s = store.load();
    if (!s || s.date !== today) { s = { date: today, counts: {}, exhausted: {} }; store.save(s); }
    return s;
  }
  const used = (s, label, service) => ((s.counts[label] || {})[service]) || 0;
  const limitOf = (service) => limits[service] || 10000;
  const usable = (s, k, service) => (!k.services || k.services.has(service)) && !((s.exhausted[k.label] || {})[service]) && used(s, k.label, service) < limitOf(service);

  /* 용도의 키 중 쓸 수 있는 것을 고른다. skip 은 이번 호출에서 이미 시도한 라벨. 없으면 null */
  function pick(purpose, service, skip) {
    const s = state(), svc = String(service || '').toLowerCase(), tried = skip || new Set();
    const own = listFor(purpose).filter((k) => !tried.has(k.label) && usable(s, k, svc));
    const pool = own.length ? own : (keys.fallback && !tried.has('DEFAULT') && usable(s, keys.fallback, svc) ? [keys.fallback] : []);
    if (!pool.length) return null;
    const min = Math.min(...pool.map((k) => used(s, k.label, svc)));
    const lows = pool.filter((k) => used(s, k.label, svc) === min);
    return lows[rr++ % lows.length];
  }
  function record(label, service, n = 1) {
    const s = state();
    (s.counts[label] = s.counts[label] || {})[service] = used(s, label, service) + n;
    store.save(s);
  }
  function markExhausted(label, service) {
    const s = state();
    (s.exhausted[label] = s.exhausted[label] || {})[service] = true;
    store.save(s);
  }
  const hasKeys = (purpose) => !!(listFor(purpose).length || keys.fallback);
  /* 용도에 쓸 수 있는 키 수(용도 키가 없으면 기본 키 1개, 그것도 없으면 0). 일일 예산을 키 수만큼 늘릴 때 쓴다 */
  const count = (purpose) => { const n = listFor(purpose).length; return n || (keys.fallback ? 1 : 0); };

  /* call(keyValue, label) 을 키를 바꿔 가며 부른다. 한도 오류면 그 키를 오늘 쉬게 하고 다음 키로. 키가 없거나 모두 소진이면 KeyPoolError */
  async function run(purpose, service, call, opts = {}) {
    const isQuota = opts.isQuota || isQuotaError, tried = new Set();
    for (;;) {
      const k = pick(purpose, service, tried);
      if (!k) {
        throw hasKeys(purpose)
          ? new KeyPoolError('EXHAUSTED', `${String(purpose).toUpperCase()} 용도의 인증키가 모두 오늘 한도에 닿았습니다(${service})`, secondsToKstMidnight(now()))
          : new KeyPoolError('NO_KEY', `${String(purpose).toUpperCase()} 용도의 인증키가 설정되어 있지 않습니다`);
      }
      tried.add(k.label);
      let res, err;
      try { res = await call(k.value, k.label); } catch (e) { err = e; }
      record(k.label, String(service).toLowerCase());
      if (isQuota(err || res)) { markExhausted(k.label, String(service).toLowerCase()); continue; }
      if (err) throw err;
      return res;
    }
  }
  /* 사용 현황(키 값 없이 라벨만): { 날짜, 키: {라벨: {서비스: {used, limit, exhausted}}} } */
  function usage() {
    const s = state(), out = {};
    const all = [...Object.values(keys.byPurpose).flat(), ...(keys.fallback ? [keys.fallback] : [])];
    for (const k of all) {
      out[k.label] = {};
      const services = new Set([...Object.keys(s.counts[k.label] || {}), ...Object.keys(s.exhausted[k.label] || {})]);
      for (const svc of services) out[k.label][svc] = { used: used(s, k.label, svc), limit: limitOf(svc), exhausted: !!(s.exhausted[k.label] || {})[svc] };
    }
    return { date: s.date, keys: out };
  }
  const purposes = () => Object.keys(keys.byPurpose);
  return { pick, record, markExhausted, run, usage, hasKeys, count, purposes, limits, profile: demo ? 'demo' : 'dev' };
}

module.exports = { createKeyPool, loadKeys, parseLimits, isQuotaError, isThrottle, memoryStore, fileStore, KeyPoolError, DEFAULT_LIMITS, kstDate, secondsToKstMidnight };
