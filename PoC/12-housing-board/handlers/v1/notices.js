/* 공공 모집 공고 요청 시 조회 API: 시군구 하나의 마이홈포털 공공주택 모집공고(임대·분양)와 한국토지주택공사(LH) 분양임대공고문을 돌려준다. 번들이 없는 지역에도 "지금 모집 중인 공공주택"을 보이기 위한 것.

   GET /api/v1/notices?sgg=<시군구 5자리>
   → 200 { type:'Notices', sgg, name, asOf, items:[{ id, kind:'rental'|'sale', title, agency, status, housingType, supplyType, complex, units, address, pnu, announcedAt, applyFrom, applyTo, url, source:'myhome'|'lh' }], meta:{ source, rental, sale, lh, matched, lhMatched, partial? } }
   → problem+json: invalid-query 400 · invalid-code 400 · unknown-code 404 · method 405 · keys-exhausted 429 · not-configured 503 · upstream 502

   - 원천은 마이홈포털 HWSPR02(임대 rsdtRcritNtcList · 분양 ltRsdtRcritNtcList)의 전국 현재 공고(2026-10-05: 324건)이고 시군구 필터가 없어 전체를 받아(100건씩) 1시간 캐시하고,
     행정표준코드의 시군구 이름('경기도 하남시')으로 거른다(lib/myhome.js). 구가 있는 시는 시 전체가 구 공고를 모두 포함한다. 링크는 마이홈·LH 주소만 싣는다.
   - 공고는 대부분 매입임대·일반매각(개별 주택)이라 건설 중인 단지(/api/v1/permits)와 합치지 않는 별도 목록이다. PNU 가 있는 공고는 화면이 그 필지로 이동할 수 있다.
   - 인증키: lib/keys.js 의 RESOLVE 용도 풀(서비스 myhome, 하루 10,000건). 임대·분양 한쪽만 실패하면 나머지를 주고 meta.partial 에 적는다(이때는 캐시하지 않음).
   - LH 공고문(15058530)은 진행 중(공고중·접수중·정정공고중) 주택 공고 전국 약 150건을 받아 1시간 캐시한다(lib/lhnotice.js). 지역은 시도뿐이라 제목에 시군구·법정동 이름이 있을 때만 이 시군구의 공고로 보고(제목 기준 추정, 구가 있는 시의 구는 구 이름만),
     마이홈과 제목이 같은 공고는 마이홈 쪽만 둔다. 고른 공고는 공급정보(15056765)로 단지명·금회공급 세대수를 채운다(24시간 캐시, 실패해도 공고는 나가고 meta.partial 에 'lh-supply').
   - LH 쪽이 실패해도(한도·연결) 마이홈 공고는 나가고 meta.partial 에 'lh'. 마이홈 둘 다 실패해도 LH 가 되면 LH 만 준다(이때도 meta.partial, 짧게 캐시).
   시험: tests/js/noticesapi.test.cjs · tests/js/myhome.test.cjs · tests/js/lhnotice.test.cjs */
'use strict';
const path = require('path');
const { createKeyPool, fileStore, memoryStore, KeyPoolError } = require('../../lib/keys.js');
const { fetchPage } = require('../../lib/datagokr.js');
const { createCache, defaultDir } = require('../../lib/cache.js');
const { createStan } = require('../../lib/stan.js');
const codes = require('../../lib/codes.js');
const M = require('../../lib/myhome.js');
const L = require('../../lib/lhnotice.js');

const BASE = 'https://apis.data.go.kr/1613000/HWSPR02/';
const ENDPOINTS = { rental: 'rsdtRcritNtcList', sale: 'ltRsdtRcritNtcList' };
const PAGE_ROWS = 100;
const MAX_PAGES = 6;
const LIST_TTL_MS = 3600 * 1000;
const SUPPLY_TTL_MS = 24 * 3600 * 1000;
const LH_MAX_PAGES = 5;
const LH_WINDOW_DAYS = 365;                   // 진행 중인 공고 가운데 가장 오래된 것도 1년 안(2025-01 이후 공고중 142건, 2026-04 이후 134건)
const LH_SUPPLY_MAX = 20;                     // 한 응답에서 공급정보를 부르는 공고 수 상한
const LH_SUPPLY_CONCURRENCY = 4;
const FETCH_TIMEOUT_MS = 10000;
const ALLOWED = new Set(['sgg']);

function createHandler(overrides = {}) {
  const env = overrides.env || process.env;
  const now = overrides.now || (() => Date.now());
  const doFetch = overrides.fetch || ((...a) => fetch(...a));
  const sleep = overrides.sleep || ((ms) => new Promise((r) => setTimeout(r, ms)));
  const dir = overrides.cacheDir || defaultDir(env);
  const cache = overrides.cache || createCache({ dir, now });
  const pool = overrides.pool || createKeyPool({ env, now, store: env.VERCEL ? memoryStore() : fileStore(path.join(dir, 'key-usage.json')) });
  const stan = createStan({ doFetch, pool, cache, sleep });

  const send = (res, status, body, cacheControl, type = 'application/json; charset=utf-8') => {
    res.statusCode = status;
    res.setHeader('Content-Type', type);
    res.setHeader('Cache-Control', cacheControl);
    res.setHeader('X-Content-Type-Options', 'nosniff');
    res.end(JSON.stringify(body));
  };
  const problem = (res, status, code, title, detail, extra, cc) => send(res, status, Object.assign({ type: `/problems/${code}`, title, status, code, detail }, extra),
    cc || (status >= 500 || status === 429 ? 'no-store' : 'public, s-maxage=60'), 'application/problem+json; charset=utf-8');

  /* 전국 공고 한 종류(임대 또는 분양): 100건씩 총건수만큼, 1시간 캐시. 실패는 던진다(캐시 안 함) */
  function nationalList(kind) {
    return cache.wrap(`myhome:${kind}`, LIST_TTL_MS, async () => {
      const all = [];
      for (let page = 1; page <= MAX_PAGES; page++) {
        const got = await pool.run('RESOLVE', 'myhome', (key) => fetchPage({ doFetch, sleep, url: BASE + ENDPOINTS[kind], timeoutMs: FETCH_TIMEOUT_MS,
          params: { serviceKey: key, numOfRows: String(PAGE_ROWS), pageNo: String(page), _type: 'json' } }));
        all.push(...got.items);
        if (!got.items.length || page * PAGE_ROWS >= got.total) break;
      }
      return all;
    });
  }

  /* LH 진행 중 공고(전국, 상태별로 받아 합침): 1시간 캐시. 실패는 던진다(캐시 안 함) */
  const ymd = (t) => new Date(t).toISOString().slice(0, 10).replace(/-/g, '');
  function lhNationalList() {
    return cache.wrap('lh:notices', LIST_TTL_MS, async () => {
      const all = [], from = ymd(now() - LH_WINDOW_DAYS * 86400000), to = ymd(now());
      for (const status of L.STATUSES) {
        for (let page = 1; page <= LH_MAX_PAGES; page++) {
          const json = await pool.run('RESOLVE', 'lh', (key) => L.fetchLh({ doFetch, sleep, url: L.LIST_URL, params: { serviceKey: key, PG_SZ: String(PAGE_ROWS), PAGE: String(page), PAN_SS: status, PAN_ST_DT: from, PAN_ED_DT: to } }));
          const got = L.listOf(json);
          all.push(...got.rows);
          if (!got.rows.length || page * PAGE_ROWS >= got.total) break;
        }
      }
      return all;
    });
  }
  /* 공고 하나의 공급정보 → { complex, units } | null(공급정보가 없거나 모양이 다름). 24시간 캐시, 실패는 던진다 */
  function lhSupply(ref) {
    return cache.wrap(`lh:supply:${ref.PAN_ID}`, SUPPLY_TTL_MS, async () => {
      const json = await pool.run('RESOLVE', 'lh', (key) => L.fetchLh({ doFetch, sleep, url: L.SUPPLY_URL, params: { serviceKey: key, PAN_ID: ref.PAN_ID, SPL_INF_TP_CD: ref.SPL_INF_TP_CD, CCR_CNNT_SYS_DS_CD: ref.CCR_CNNT_SYS_DS_CD, UPP_AIS_TP_CD: ref.UPP_AIS_TP_CD } }));
      return L.supplyOf(json) || { complex: null, units: null };
    });
  }
  async function mapLimit(items, limit, fn) {
    const out = new Array(items.length); let next = 0;
    await Promise.all(Array.from({ length: Math.min(limit, items.length) }, async () => {
      while (next < items.length) { const i = next++; try { out[i] = { ok: await fn(items[i]) }; } catch (e) { out[i] = { err: e }; } }
    }));
    return out;
  }

  const handler = async function handler(req, res) {
    if (req.method !== 'GET' && req.method !== 'HEAD') { res.setHeader('Allow', 'GET, HEAD'); return problem(res, 405, 'method', '허용하지 않는 방식', 'GET 만 지원합니다'); }
    const params = new URL(req.url || '/', 'http://local').searchParams;
    const names = [...new Set(params.keys())];
    if (names.some((n) => !ALLOWED.has(n)) || !params.has('sgg') || params.getAll('sgg').length !== 1) return problem(res, 400, 'invalid-query', '쿼리가 맞지 않습니다', 'sgg=<시군구 5자리> 하나만 받습니다', undefined, 'public, s-maxage=3600');
    const c = codes.classify(params.get('sgg'));
    if (!c.ok || c.type !== 'sgg') return problem(res, 400, 'invalid-code', '시군구 코드가 맞지 않습니다', c.ok ? `${c.type} 코드가 왔습니다. 시군구(5자리)만 받습니다` : c.detail, c.ok ? { reason: 'type-mismatch' } : { reason: c.reason }, 'public, s-maxage=3600');
    if (!pool.hasKeys('RESOLVE')) return problem(res, 503, 'not-configured', '인증키가 설정되어 있지 않습니다', 'RESOLVE 용도 공공데이터포털 키가 필요합니다');
    try {
      const rows = await stan.rows(c.sido, c.sgg), row = codes.findRow(rows, `${c.sgg}00000`);
      if (!row) return problem(res, 404, 'unknown-code', '표준코드 표에 없는 시군구입니다', `${c.sgg}는 행정표준코드에 없습니다`, { sgg: c.sgg });
      const [rental, sale, lh] = await Promise.allSettled([nationalList('rental'), nationalList('sale'), lhNationalList()]);
      const failed = [['rental', rental], ['sale', sale], ['lh', lh]].filter(([, r]) => r.status === 'rejected');
      if (failed.length === 3) throw (failed.map(([, r]) => r.reason).find((e) => e instanceof KeyPoolError) || rental.reason);
      const partial = failed.map(([k]) => k);
      const rl = rental.status === 'fulfilled' ? rental.value : [], sl = sale.status === 'fulfilled' ? sale.value : [], lhRows = lh.status === 'fulfilled' ? lh.value : [];
      const mine = M.forRegion(rl, sl, row.locatadd_nm);
      let lhItems = [];
      if (lhRows.length) {
        const umdNames = rows.filter((r) => codes.levelOf(r) === 'umd').map((r) => String(r.locallow_nm || r.locatadd_nm.split(' ').pop()));
        lhItems = L.forRegion(lhRows, row.locatadd_nm, umdNames, new Set(mine.map((n) => L.titleKey(n.title))));
        const got = await mapLimit(lhItems.slice(0, LH_SUPPLY_MAX), LH_SUPPLY_CONCURRENCY, (n) => lhSupply(n._supply));
        let supplyFailed = 0;
        got.forEach((g, i) => { if (g.err) supplyFailed++; else { lhItems[i].complex = g.ok.complex; lhItems[i].units = g.ok.units; } });
        if (supplyFailed) partial.push('lh-supply');
      }
      const items = [...mine, ...lhItems.map(({ _supply, ...n }) => n)].sort((a, b) => String(b.announcedAt || '').localeCompare(String(a.announcedAt || '')) || a.id.localeCompare(b.id));
      const meta = { source: '마이홈포털 공공주택 모집공고(HWSPR02) + 한국토지주택공사 분양임대공고문(15058530)·공급정보(15056765)', rental: rl.length, sale: sl.length, lh: lhRows.length, matched: items.length, lhMatched: lhItems.length };
      if (partial.length) meta.partial = partial;
      return send(res, 200, { type: 'Notices', sgg: c.sgg, name: row.locatadd_nm, asOf: new Date(now()).toISOString().slice(0, 10), items, meta },
        partial.length ? 'public, s-maxage=60' : 'public, s-maxage=3600, stale-while-revalidate=3600');
    } catch (e) {
      if (e instanceof KeyPoolError) {
        if (e.code === 'EXHAUSTED') { res.setHeader('Retry-After', String(e.retryAfterSec || 3600)); return problem(res, 429, 'keys-exhausted', '오늘 인증키 한도에 닿았습니다', e.message, { retryAfterSec: e.retryAfterSec }); }
        return problem(res, 503, 'not-configured', '인증키가 설정되어 있지 않습니다', e.message);
      }
      console.error(`notices ${c.sgg}: ${(e && e.name) || 'Error'}: ${String((e && e.message) || e).slice(0, 200)}`);
      return problem(res, 502, 'upstream', '공공 모집 공고 서비스를 부르지 못했습니다', '잠시 뒤 다시 시도하세요');   // 원인 문구는 밖으로 내보내지 않는다(키가 섞일 수 있음)
    }
  };
  return handler;
}

module.exports = createHandler();
module.exports.createHandler = createHandler;
