/* 인허가 사업 요청 시 조회 API: 번들이 없는 지역(등급 B·C)에서도 "어디에 어떤 공급 사업이 있나"를 보이기 위해, 법정동 하나의 건축HUB 주택인허가를
   번지(PNU) 단위 사업으로 모으고 필지 경계(V-World 연속지적도)를 붙여 돌려준다.

   GET /api/v1/permits?bjd=<법정동 10자리>        (8자리는 00 을 붙여 받는다)
   → 200 { type:'FeatureCollection', bjd, features:[{properties:{ pnu, jibun, name, label, units, status, mainBldCnt, approvedAt, startedAt, completedAt, plannedStart, plannedCompletion, overdue, address, refs, records }, geometry:Polygon}], meta:{ source, fetchedAt, records, candidates, projects, located, unlocated, unlocatedNames, unlocatedList, blockProjects, blockList, parcelErrors, truncated, skipped } }
   → problem+json: invalid-query 400 · invalid-code 400 · method 405 · keys-exhausted 429 · budget-exhausted 429 · not-configured 503 · upstream 502

   - 사업 후보·상태·이름 규칙은 lib/permits.js(번들 빌드와 같음): 공동주택 + 총세대수 > 0, 번지 단위 집계, 상태는 계획 · 건설 단계 · 입주 단계(분양중·준공 임박은 공고·공정율이 필요해 정하지 않음).
   - 한 법정동 사업은 최대 120개(건설 단계 → 계획 → 입주 단계, 세대수 큰 순)까지 필지를 붙이고 넘으면 meta.truncated. 필지를 못 찾은 사업은 지도에 못 그리므로 meta.unlocatedNames 로만 알린다.
   - 건축HUB 는 간헐적으로 503·빈 본문을 주므로 쪽마다 최대 4번(점점 길게 기다려) 시도한다. 인증키는 lib/keys.js 의 RESOLVE 용도 풀(서비스 'hub'), V-World 는 lib/vworld.js.
   - 사업 id: 사업 레지스트리(registry/projects.json, lib/projects.js)에 발급된 사업이면 features[].properties.projectId 에 `PRJ-{시군구5}-{일련4}` 를 붙인다(허가 관리번호가 같거나 PNU 가 같은 사업).
     캐시된 본문에는 싣지 않고 응답할 때마다 붙이므로 레지스트리를 고치면 바로 반영된다. 발급되지 않은 사업은 projectId 가 없다.
   - 응답은 로컬 캐시 24시간 + CDN 24시간. 필지 경계도 따로 24시간 캐시한다. 필지를 일부라도 못 받았으면(일시 오류) 응답은 캐시하지 않는다.
   - 열린 중계가 되지 않게 인스턴스별 시간당 V-World 필지 호출 상한(PERMITS_UPSTREAM_PER_HOUR, 기본 2000)을 둔다. 키·원천 URL·원천 오류 문구는 응답에 싣지 않는다.
   시험: tests/js/permitsapi.test.cjs */
'use strict';
const path = require('path');
const { createKeyPool, fileStore, memoryStore, KeyPoolError } = require('../../lib/keys.js');
const { fetchPage } = require('../../lib/datagokr.js');
const { createCache, defaultDir } = require('../../lib/cache.js');
const { VWORLD_URL, vworldCreds, redactVworld } = require('../../lib/vworld.js');
const { thinGeometry, largestPolygon } = require('../../lib/geom.js');
const codes = require('../../lib/codes.js');
const Permits = require('../../lib/permits.js');
const { createStan } = require('../../lib/stan.js');
const Projects = require('../../lib/projects.js');
const { readRegistry } = require('../../lib/registry.js');

const HUB_URL = 'https://apis.data.go.kr/1613000/HsPmsHubService/getHpBasisOulnInfo';
const HUB_PLAT_URL = 'https://apis.data.go.kr/1613000/HsPmsHubService/getHpPlatPlcInfo';
const LEDGER_URL = 'https://apis.data.go.kr/1613000/BldRgstHubService/getBrRecapTitleInfo';
const LEDGER_CONCURRENCY = 4;
const LEDGER_GAP_MS = 110;                         // 건물대장은 초당 30건쯤에서 429(…PER_SECOND_EXCEEDS)로 막히고 한동안 풀리지 않는다(실측) → 인스턴스당 초당 9건 안쪽으로 간격을 둔다
const MAX_LEDGER_BJDS = 60;
const DEFAULT_LEDGER_BUDGET_PER_HOUR = 1500;
const PAGE_ROWS = 100;
const MAX_PAGES = 30;
const MAX_PROJECTS = 120;
const PARCEL_CONCURRENCY = 6;
const PARCEL_MAX_POINTS = 80;
const TTL_MS = 24 * 3600 * 1000;
const FETCH_TIMEOUT_MS = 10000;
const DEFAULT_BUDGET_PER_HOUR = 2000;
const ALLOWED = new Set(['bjd']);

/* createService: 핸들러와, 다른 API(/api/v1/infra)가 같은 캐시·키 풀·예산으로 인허가 결과를 얻는 getPermits(bjd) 를 함께 돌려준다 */
function createService(overrides = {}) {
  const env = overrides.env || process.env;
  const now = overrides.now || (() => Date.now());
  const doFetch = overrides.fetch || ((...a) => fetch(...a));
  const sleep = overrides.sleep || ((ms) => new Promise((r) => setTimeout(r, ms)));
  const dir = overrides.cacheDir || defaultDir(env);
  const cache = overrides.cache || createCache({ dir, now });
  const pool = overrides.pool || createKeyPool({ env, now, store: env.VERCEL ? memoryStore() : fileStore(path.join(dir, 'key-usage.json')) });
  const budgetMax = Number(env.PERMITS_UPSTREAM_PER_HOUR) > 0 ? Math.floor(Number(env.PERMITS_UPSTREAM_PER_HOUR)) : DEFAULT_BUDGET_PER_HOUR;
  const budget = { hour: -1, used: 0 }, lbudget = { hour: -1, used: 0 };
  const ledgerMax = Number(env.LEDGER_UPSTREAM_PER_HOUR) > 0 ? Math.floor(Number(env.LEDGER_UPSTREAM_PER_HOUR)) : DEFAULT_LEDGER_BUDGET_PER_HOUR;
  const stan = createStan({ doFetch, pool, cache, sleep });
  const registryIndex = () => overrides.registryIndex || readRegistry(overrides.registryFile).index;
  /* 캐시된 본문은 그대로 두고(공유됨) 사업 id 가 있는 사업에만 projectId 를 붙인 새 본문을 만든다 */
  const withProjectIds = (body) => {
    const idx = registryIndex();
    if (!idx.byId.size) return body;
    let any = false;
    const features = body.features.map((f) => { const id = Projects.projectIdFor(idx, f.properties); if (!id) return f; any = true; return { ...f, properties: { ...f.properties, projectId: id } }; });
    return any ? { ...body, features } : body;
  };

  let ledgerSlot = 0;
  const paceLedger = async () => { const t = now(), at = Math.max(t, ledgerSlot); ledgerSlot = at + LEDGER_GAP_MS; if (at > t) await sleep(at - t); };
  const spendLedger = (n) => {
    const hour = Math.floor(now() / 3600000);
    if (lbudget.hour !== hour) { lbudget.hour = hour; lbudget.used = 0; }
    if (lbudget.used + n > ledgerMax) return false;
    lbudget.used += n;
    return true;
  };
  const spend = (n) => {
    const hour = Math.floor(now() / 3600000);
    if (budget.hour !== hour) { budget.hour = hour; budget.used = 0; }
    if (budget.used + n > budgetMax) return false;
    budget.used += n;
    return true;
  };
  const send = (res, status, body, cacheControl, type = 'application/json; charset=utf-8') => {
    res.statusCode = status;
    res.setHeader('Content-Type', type);
    res.setHeader('Cache-Control', cacheControl);
    res.setHeader('X-Content-Type-Options', 'nosniff');
    res.end(JSON.stringify(body));
  };
  const problem = (res, status, code, title, detail, extra, cc) => send(res, status, Object.assign({ type: `/problems/${code}`, title, status, code, detail }, extra),
    cc || (status >= 500 || status === 429 ? 'no-store' : 'public, s-maxage=60'), 'application/problem+json; charset=utf-8');

  /* 건축HUB 한 쪽(lib/datagokr.js: 일시 오류 재시도·한도 오류는 키 풀이 다음 키로) */
  const hubPage = (key, sigungu, bjdong, page) => fetchPage({ doFetch, sleep, url: HUB_URL, timeoutMs: FETCH_TIMEOUT_MS,
    params: { serviceKey: key, sigunguCd: sigungu, bjdongCd: bjdong, numOfRows: String(PAGE_ROWS), pageNo: String(page), _type: 'json' } });
  async function hubRecords(sigungu, bjdong) {
    const all = []; let pages = 0;
    for (let page = 1; page <= MAX_PAGES; page++) {
      const got = await pool.run('RESOLVE', 'hub', (key) => hubPage(key, sigungu, bjdong, page));
      pages++; all.push(...got.items);
      if (!got.items.length || page * PAGE_ROWS >= got.total) break;
    }
    return { records: all, pages };
  }

  /* 필지 경계: 대표 윤곽 하나(가장 큰 다각형의 바깥 링). 없으면 { none:true }. 일시 오류는 던진다(캐시 안 함) */
  function parcelOf(pnu, creds) {
    return cache.wrap(`parcel:${pnu}`, TTL_MS, async () => {
      if (!spend(1)) { const e = new Error('budget'); e.budget = true; throw e; }
      const q = new URLSearchParams({ service: 'data', request: 'GetFeature', data: 'LP_PA_CBND_BUBUN', key: creds.key, domain: creds.domain, format: 'json', size: '5', crs: 'EPSG:4326', attrFilter: `pnu:=:${pnu}` });
      const r = await doFetch(`${VWORLD_URL}?${q}`, { signal: AbortSignal.timeout(FETCH_TIMEOUT_MS), headers: { Accept: 'application/json' } });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const res = (await r.json()).response, st = res && res.status;
      if (st === 'NOT_FOUND') return { none: true };
      if (st !== 'OK') throw new Error(`V-World ${(res && res.error && res.error.code) || st || '응답 형식'}`);
      const f = (((res.result || {}).featureCollection || {}).features || [])[0];
      const g = f && largestPolygon(thinGeometry(f.geometry, PARCEL_MAX_POINTS));
      return g ? { geometry: g } : { none: true };
    });
  }
  async function mapLimit(items, limit, fn) {
    const out = new Array(items.length); let next = 0;
    await Promise.all(Array.from({ length: Math.min(limit, items.length) }, async () => {
      while (next < items.length) { const i = next++; try { out[i] = { ok: await fn(items[i]) }; } catch (e) { out[i] = { err: e }; } }
    }));
    return out;
  }

  /* 건축HUB 대지위치(getHpPlatPlcInfo): 허가(관리번호)별 대지면적 합계. 24시간 캐시 */
  function platAreas(sigungu, bjdong) {
    return cache.wrap(`plat:${sigungu}${bjdong}`, TTL_MS, async () => {
      const lots = new Map();                                              // 관리번호 → { 'bun-ji': 면적 } (같은 지번이 여러 행이면 한 번만)
      for (let page = 1; page <= MAX_PAGES; page++) {
        const got = await pool.run('RESOLVE', 'hub', (key) => fetchPage({ doFetch, sleep, url: HUB_PLAT_URL, timeoutMs: FETCH_TIMEOUT_MS,
          params: { serviceKey: key, sigunguCd: sigungu, bjdongCd: bjdong, numOfRows: String(PAGE_ROWS), pageNo: String(page), _type: 'json' } }));
        for (const r of got.items) { const ref = String(r.mgmHsrgstPk == null ? '' : r.mgmHsrgstPk).trim(), a = Number(r.platArea); if (ref && a > 0) { const m = lots.get(ref) || lots.set(ref, {}).get(ref); m[`${r.bun}-${r.ji}`] = a; } }
        if (!got.items.length || page * PAGE_ROWS >= got.total) break;
      }
      const out = {};
      for (const [ref, m] of lots) out[ref] = Object.values(m).reduce((a, b) => a + b, 0);
      return out;
    });
  }
  /* 건물대장 총괄표제부(getBrRecapTitleInfo) 법정동 하나: 쓸 수 있는 행만 줄여 24시간 캐시. 권한이 없으면(403) e.ledgerDenied */
  function ledgerRowsOf(bjd) {
    return cache.wrap(`ledger:${bjd}`, TTL_MS, async () => {
      const out = [];
      for (let page = 1; page <= MAX_PAGES; page++) {
        if (!spendLedger(1)) { const e = new Error('budget'); e.ledgerBudget = true; throw e; }
        await paceLedger();
        let got;
        try {
          got = await pool.run('RESOLVE', 'hubledger', (key) => fetchPage({ doFetch, sleep, url: LEDGER_URL, timeoutMs: FETCH_TIMEOUT_MS,
            params: { serviceKey: key, sigunguCd: bjd.slice(0, 5), bjdongCd: bjd.slice(5, 10), numOfRows: String(PAGE_ROWS), pageNo: String(page), _type: 'json' } }));
        } catch (e) { if (/HTTP 40[13]/.test(String(e && e.message))) e.ledgerDenied = true; throw e; }
        for (const r of got.items) { const row = Permits.ledgerRow(r); if (row) out.push(row); }
        if (!got.items.length || page * PAGE_ROWS >= got.total) break;
      }
      return out;
    });
  }

  /* 건물대장으로 보강(규칙은 lib/permits.js): ① 블록 단위 허가의 위치 ② 합필로 지번이 사라진 사업의 현재 지번 ③ 같은 지번 대장의 사용승인일로 준공 확인.
     보조 기능이라 어떤 실패도 인허가 결과를 막지 않고 info.error 에 사유만 남긴다(그때는 캐시하지 않음) */
  const ledgerWhy = (e) => (e && e.ledgerDenied ? '건물대장 서비스 권한이 없음(활용신청 필요)' : e && e.ledgerBudget ? '이 서버의 시간당 건물대장 조회 한도에 닿음' : e && e.throttled ? '건물대장 초당 호출 한도에 걸려 일부만 대조' : e instanceof KeyPoolError ? '인증키 한도·설정 문제로 건물대장을 건너뜀' : '건물대장을 불러오지 못함');
  const jibunOf = (row) => row.platPlc.replace(/^.*?\s(\S+동|\S+읍|\S+면|\S+리)\s*/, '').replace(/번지.*$/, '').trim() || row.pnu;
  async function enrich(bjd, picked, blocks) {
    const info = { used: false, bjds: 0, rows: 0, blocksMatched: 0, blocksAmbiguous: 0, parcelsRecovered: 0, completions: 0 };
    const lostIn = picked.filter((p) => !p.geometry), locatedIn = picked.filter((p) => p.geometry);
    const none = { info, matched: [], blocks, lost: lostIn };
    const needs = blocks.length > 0 || lostIn.length > 0;
    if (!needs && !locatedIn.some((p) => p.status !== '입주 단계')) return none;
    let own;
    try { own = await ledgerRowsOf(bjd); } catch (e) { info.error = ledgerWhy(e); return { ...none, partial: true }; }   // 권한·한도 문제는 여기서 한 번에 걸러진다
    const rows = [...own]; let failed = 0, areas = {};
    if (needs) {
      try { areas = await platAreas(bjd.slice(0, 5), bjd.slice(5, 10)); } catch (e) { info.error = '허가 대지면적을 불러오지 못해 블록·지번 대조를 건너뜀'; }
      if (!info.error && [...blocks, ...lostIn].some((x) => x.units && areas[x.latestRef] > 0)) {
        let others = [];
        try { others = (await stan.umdCodes(bjd.slice(0, 5))).filter((c) => c !== bjd).slice(0, MAX_LEDGER_BJDS - 1); } catch (e) { info.error = '같은 시군구의 법정동 목록을 받지 못해 이 법정동 대장만 대조'; }
        const res = await mapLimit(others, LEDGER_CONCURRENCY, ledgerRowsOf);
        res.forEach((r) => { if (r.err) failed++; else rows.push(...r.ok); });
        if (failed) { const why = new Set(res.filter((r) => r.err).map((r) => `${(r.err && r.err.name) || 'Error'}: ${redactVworld((r.err && r.err.message) || r.err, env).slice(0, 80)}`)); console.error(`permits ${bjd} ledger: ${failed}/${others.length} 법정동 실패 — ${[...why].slice(0, 3).join(' | ')}`); }
        if (failed) info.error = `건물대장 ${failed}개 법정동을 불러오지 못해 일부만 대조`;
        info.bjds = others.length - failed;
      }
    }
    info.used = true; info.bjds += 1; info.rows = rows.length;
    const byPnu = new Map(); for (const r of rows) (byPnu.get(r.pnu) || byPnu.set(r.pnu, []).get(r.pnu)).push(r);
    const t = new Date(now()).toISOString().slice(0, 10), taken = new Set(locatedIn.map((p) => p.pnu));   // 한 필지에 사업이 둘 겹치지 않게
    const found = (item) => { const m = areas && Permits.matchLedger({ units: item.units, platArea: areas[item.latestRef] || 0, name: item.name }, rows.filter((r) => !taken.has(r.pnu))); return m; };
    const ledgerOf = (row, m) => ({ name: row.name, platPlc: row.platPlc, useAprDay: row.useAprDay, areaDiff: m.diff == null ? null : Math.round(m.diff * 10000) / 100, ...(m.by ? { by: m.by } : {}) });
    const matched = [], leftBlocks = [], lost = [];
    for (const b of blocks) {                                                         // ① 블록 단위 허가
      const m = found(b);
      if (m && m.row) {
        const row = m.row, done = Permits.ledgerCompletion(row, b.approvedAt, now()) || (b.completedAt && b.completedAt <= t ? b.completedAt : null), name = Permits.isGenericName(b.name) && row.name ? row.name : b.name;
        taken.add(row.pnu);
        matched.push({ pnu: row.pnu, jibun: jibunOf(row), name, label: Permits.shortLabel(name) || name, units: b.units, status: done ? '입주 단계' : b.status, mainBldCnt: null, approvedAt: b.approvedAt, startedAt: b.startedAt, completedAt: done, plannedStart: null, plannedCompletion: null, overdue: null,
          address: row.platPlc, refs: [], records: b.records, latestRef: b.latestRef, block: b.block, via: 'ledger', ledger: ledgerOf(row, m) });
        info.blocksMatched++;
      } else { if (m && m.ambiguous) info.blocksAmbiguous++; leftBlocks.push(b); }
    }
    for (const p of lostIn) {                                                         // ② 지번이 사라진 사업(합필·분할)
      const m = found(p);
      if (m && m.row) {
        const row = m.row, done = Permits.ledgerCompletion(row, p.approvedAt, now());
        taken.add(row.pnu);
        matched.push({ ...p, pnu: row.pnu, jibun: jibunOf(row), address: row.platPlc, status: done ? '입주 단계' : p.status, completedAt: done || p.completedAt, plannedStart: done ? null : p.plannedStart, overdue: done ? null : p.overdue,
          via: 'ledger', hubJibun: p.jibun, ledger: ledgerOf(row, m) });
        info.parcelsRecovered++;
      } else lost.push(p);
    }
    for (const p of locatedIn.filter((x) => x.status !== '입주 단계')) {              // ③ 같은 지번 대장의 사용승인일로 준공 확인
      const same = byPnu.get(p.pnu) || [];
      const done = same.map((r) => Permits.ledgerCompletion(r, p.approvedAt, now())).filter(Boolean).sort().pop();
      if (done) { Object.assign(p, { status: '입주 단계', completedAt: done, plannedStart: null, overdue: null, statusBy: 'ledger' }); info.completions++; }
    }
    return { info, matched, blocks: leftBlocks, lost, partial: !!info.error };
  }

  async function build(bjd, creds) {
    const { records, pages } = await hubRecords(bjd.slice(0, 5), bjd.slice(5, 10));
    const { projects, blocks, skipped } = Permits.aggregate(records, now());
    const picked = projects.slice(0, MAX_PROJECTS);
    const geo = new Map();                                                           // pnu → { geometry } | { none } | { err }
    async function locate(list) {
      const todo = list.filter((p) => !geo.has(p.pnu));
      const got = await mapLimit(todo, PARCEL_CONCURRENCY, (p) => parcelOf(p.pnu, creds));
      const budgetErr = got.find((g) => g.err && g.err.budget);
      if (budgetErr) throw budgetErr.err;
      todo.forEach((p, i) => geo.set(p.pnu, got[i].err ? { err: got[i].err } : got[i].ok));
    }
    await locate(picked);
    picked.forEach((p) => { const g = geo.get(p.pnu); if (g && g.geometry) p.geometry = g.geometry; });
    let parcelErrors = picked.filter((p) => geo.get(p.pnu) && geo.get(p.pnu).err).length;
    if (picked.length && !picked.some((p) => p.geometry) && parcelErrors) throw new Error('필지 경계를 한 건도 받지 못함');

    let en = { info: { used: false }, matched: [], blocks, lost: picked.filter((p) => !p.geometry) };
    try { en = await enrich(bjd, picked, blocks); } catch (e) {
      en.info = { used: false, error: ledgerWhy(e), partial: true };
      console.error(`permits ${bjd} ledger: ${(e && e.name) || 'Error'}: ${redactVworld((e && e.message) || e, env).slice(0, 160)}`);
    }
    await locate(en.matched);
    const located = picked.filter((p) => p.geometry), unlocated = en.lost.slice();
    for (const m of en.matched) {
      const g = geo.get(m.pnu);
      if (g && g.geometry) { m.geometry = g.geometry; located.push(m); } else { if (g && g.err) parcelErrors++; unlocated.push({ ...m, ...(m.hubJibun ? { jibun: m.hubJibun } : {}) }); }
    }
    const features = located.map((p) => { const { geometry, ...props } = p; return { type: 'Feature', properties: props, geometry }; });
    return {
      body: {
        type: 'FeatureCollection', bjd, features,
        meta: {
          source: '건축HUB 주택인허가정보(getHpBasisOulnInfo·getHpPlatPlcInfo) + 건축HUB 건축물대장정보(총괄표제부) + V-World 연속지적도(LP_PA_CBND_BUBUN)', fetchedAt: new Date(now()).toISOString().slice(0, 10),
          records: records.length, pages, candidates: projects.length + blocks.length, projects: picked.length, located: features.length, unlocated: unlocated.length,
          unlocatedNames: unlocated.slice(0, 10).map((p) => `${p.name}(${p.jibun})`),
          unlocatedList: unlocated.slice(0, 20).map((p) => ({ name: p.name, jibun: p.jibun, status: p.status, units: p.units, approvedAt: p.approvedAt, reason: Permits.unlocatedReason(p, now()) })),
          blockProjects: en.blocks.length, blockList: en.blocks.slice(0, 20), ledger: en.info, parcelErrors, truncated: projects.length > MAX_PROJECTS, skipped,
        },
      },
      cacheable: parcelErrors === 0 && !en.info.error,
    };
  }

  /* 법정동(10자리) 하나의 인허가 사업 결과: { body, cacheable, hit }. 캐시에 있으면 그것, 없으면 만들고(필지를 다 받았을 때만) 24시간 캐시한다 */
  async function getPermits(bjd) {
    const creds = vworldCreds(env);
    const hit = cache.get(`permits:${bjd}`);
    if (hit) return { body: hit, cacheable: true, hit: true };
    const out = await build(bjd, creds);
    if (out.cacheable) cache.set(`permits:${bjd}`, out.body, TTL_MS);
    return { body: out.body, cacheable: out.cacheable, hit: false };
  }
  const handler = async function handler(req, res) {
    if (req.method !== 'GET' && req.method !== 'HEAD') { res.setHeader('Allow', 'GET, HEAD'); return problem(res, 405, 'method', '허용하지 않는 방식', 'GET 만 지원합니다'); }
    const params = new URL(req.url || '/', 'http://local').searchParams;
    const names = [...new Set(params.keys())];
    if (names.some((n) => !ALLOWED.has(n)) || !params.has('bjd') || params.getAll('bjd').length !== 1) return problem(res, 400, 'invalid-query', '쿼리가 맞지 않습니다', 'bjd=<법정동 10자리> 하나만 받습니다', undefined, 'public, s-maxage=3600');
    const c = codes.classify(params.get('bjd'));
    if (!c.ok || c.type !== 'bjd') return problem(res, 400, 'invalid-code', '법정동 코드가 맞지 않습니다', c.ok ? `${c.type} 코드가 왔습니다. 법정동(8 또는 10자리)만 받습니다` : c.detail, c.ok ? { reason: 'type-mismatch' } : { reason: c.reason }, 'public, s-maxage=3600');
    const bjd = c.bjd, creds = vworldCreds(env);
    if (!creds.key || !pool.hasKeys('RESOLVE')) return problem(res, 503, 'not-configured', '인증키가 설정되어 있지 않습니다', 'RESOLVE 용도 공공데이터포털 키와 V-World 키가 필요합니다');
    try {
      const out = await getPermits(bjd);
      return send(res, 200, withProjectIds(out.body), out.cacheable ? 'public, s-maxage=86400, stale-while-revalidate=86400' : 'public, s-maxage=60');
    } catch (e) {
      if (e instanceof KeyPoolError) {
        if (e.code === 'EXHAUSTED') { res.setHeader('Retry-After', String(e.retryAfterSec || 3600)); return problem(res, 429, 'keys-exhausted', '오늘 인증키 한도에 닿았습니다', e.message, { retryAfterSec: e.retryAfterSec }); }
        return problem(res, 503, 'not-configured', '인증키가 설정되어 있지 않습니다', e.message);
      }
      if (e && e.budget) {
        const wait = 3600 - (Math.floor(now() / 1000) % 3600);
        res.setHeader('Retry-After', String(wait));
        return problem(res, 429, 'budget-exhausted', '이 서버의 시간당 필지 조회 한도에 닿았습니다', '잠시 뒤 다시 시도하세요', { retryAfterSec: wait });
      }
      console.error(`permits ${bjd}: ${(e && e.name) || 'Error'}: ${redactVworld((e && e.message) || e, env).slice(0, 200)}`);
      return problem(res, 502, 'upstream', '인허가·필지 서비스를 부르지 못했습니다', '잠시 뒤 다시 시도하세요');   // 원인 문구는 밖으로 내보내지 않는다(키가 섞일 수 있음)
    }
  };
  return { handler, getPermits, withProjectIds, cache, pool, now, sleep, doFetch };
}
const createHandler = (overrides) => createService(overrides).handler;

module.exports = createHandler();
module.exports.createHandler = createHandler;
module.exports.createService = createService;
module.exports.MAX_PROJECTS = MAX_PROJECTS;
module.exports.MAX_PAGES = MAX_PAGES;
