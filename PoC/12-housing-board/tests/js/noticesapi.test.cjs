'use strict';
/* api/v1/notices.js — 시군구의 마이홈 공공 모집공고. 네트워크 없이 가짜 fetch 로 시험한다. */
const test = require('node:test');
const assert = require('node:assert/strict');
const { createCache } = require('../../lib/cache.js');
const { createKeyPool, memoryStore } = require('../../lib/keys.js');
const api = require('../../handlers/v1/notices.js');

const row = (cd, nm) => ({ region_cd: cd, sido_cd: cd.slice(0, 2), sgg_cd: cd.slice(2, 5), umd_cd: cd.slice(5, 8), ri_cd: cd.slice(8, 10), locatadd_nm: nm, locallow_nm: nm.split(' ').pop() });
const stanJson = (rows) => (rows.length ? { StanReginCd: [{ head: [{ totalCount: rows.length }, { RESULT: { resultCode: 'INFO-0' } }] }, { row: rows }] } : { RESULT: { resultCode: 'INFO-3' } });
const mh = (items, total = items.length) => ({ response: { header: { resultCode: '00' }, body: { totalCount: total, numOfRows: 100, pageNo: 1, item: items } } });
const LHOK = (rows) => [{ dsSch: [{}] }, { dsList: rows, resHeader: [{ RS_DTTM: '20261006091648', SS_CODE: 'Y' }] }];
const lhRow = (id, nm, over = {}) => ({ PAN_ID: id, PAN_NM: nm, CNP_CD_NM: '경기도', UPP_AIS_TP_CD: '06', AIS_TP_CD_NM: '임대주택', UPP_AIS_TP_NM: '임대주택', PAN_SS: '공고중', PAN_NT_ST_DT: '2026.10.02', CLSG_DT: '2026.10.20', SPL_INF_TP_CD: '063', CCR_CNNT_SYS_DS_CD: '03', DTL_URL: `https://apply.lh.or.kr/lhapply/apply/wt/wrtanc/selectWrtancInfo.do?panId=${id}`, ALL_CNT: '1', ...over });
const ok = (json) => ({ ok: true, status: 200, json: async () => json, text: async () => JSON.stringify(json) });
const raw = (status, text) => ({ ok: status < 400, status, json: async () => JSON.parse(text || 'null'), text: async () => text });
const N = (id, brtc, sgg, over = {}) => ({ pblancId: id, houseSn: 0, sttusNm: '일반공고', pblancNm: `공고 ${id}`, suplyInsttNm: 'LH', houseTyNm: '아파트', brtcNm: brtc, signguNm: sgg, fullAdres: `${brtc} ${sgg} 어딘가 1`, rcritPblancDe: '20261001', beginDe: '20261012', endDe: '20261014', pcUrl: `https://www.myhome.go.kr/n/${id}`, ...over });
const RENTAL = [N('1', '경기도', '하남시'), N('2', '경기도', '하남시', { rcritPblancDe: '20261003' }), N('3', '서울특별시', '성북구')], SALE = [N('9', '경기도', '하남시', { suplyHoCo: undefined, sumSuplyCo: '309' })];

function defaultFetch(url) {
  const u = new URL(url);
  if (u.pathname.endsWith('/getStanReginCdList')) return ok(stanJson(u.searchParams.get('sgg_cd') === '450' ? [row('4145000000', '경기도 하남시'), row('4145011400', '경기도 하남시 감일동')] : []));
  if (u.pathname.endsWith('/rsdtRcritNtcList')) return ok(mh(RENTAL));
  if (u.pathname.endsWith('/ltRsdtRcritNtcList')) return ok(mh(SALE));
  if (u.pathname.endsWith('/lhLeaseNoticeInfo1')) return ok(LHOK([]));                                                       // LH 공고문: 기본은 진행 중 공고 없음
  throw new Error(`예상 밖 호출 ${url}`);
}
function harness(over = {}) {
  const calls = [], clock = { t: Date.parse('2026-10-05T03:00:00Z') };
  const env = over.env || { DATA_GO_KR_KEY_RESOLVE_1: 'NOTICE-KEY-1' };
  const now = () => clock.t;
  const handler = api.createHandler({ env, now, sleep: async () => {}, cache: createCache({ persist: false, now }), pool: createKeyPool({ env, now, store: memoryStore() }), fetch: async (url) => { calls.push(String(url)); return (over.fetch || defaultFetch)(String(url)); } });
  const run = async (url, method = 'GET') => {
    const res = { headers: {}, statusCode: 0, body: '', setHeader(k, v) { this.headers[k.toLowerCase()] = v; }, end(b) { this.body = b; } };
    await handler({ method, url }, res);
    return { status: res.statusCode, headers: res.headers, json: res.body ? JSON.parse(res.body) : null, raw: res.body };
  };
  return { run, calls, clock };
}
const isLh = (u) => /\/lhLeaseNotice(Info1|SplInfo1)\//.test(new URL(u).pathname);
const LH_SOURCE_TEXT = '마이홈포털 공공주택 모집공고(HWSPR02) + 한국토지주택공사 분양임대공고문(15058530)·공급정보(15056765)';
const isList = (u) => /\/(rsdtRcritNtcList|ltRsdtRcritNtcList)$/.test(new URL(u).pathname);

test('시군구의 공고: 임대·분양을 거르고 공고일 최신 순, 이름·집계·캐시 헤더, 키는 응답에 없다', async () => {
  const h = harness();
  const r = await h.run('/api/v1/notices?sgg=41450');
  assert.equal(r.status, 200); assert.equal(r.json.type, 'Notices'); assert.equal(r.json.sgg, '41450'); assert.equal(r.json.name, '경기도 하남시'); assert.equal(r.json.asOf, '2026-10-05');
  assert.deepEqual(r.json.items.map((i) => [i.id, i.kind, i.units]), [['rental-2', 'rental', null], ['rental-1', 'rental', null], ['sale-9', 'sale', 309]]);   // 최신 공고(2, 10-03)가 앞, 공고일이 같으면 id 순(1 → sale-9)
  assert.deepEqual(r.json.meta, { source: LH_SOURCE_TEXT, rental: 3, sale: 1, lh: 0, matched: 3, lhMatched: 0 });
  assert.ok(r.json.items.every((i) => i.source === 'myhome'));
  assert.equal(r.headers['cache-control'], 'public, s-maxage=3600, stale-while-revalidate=3600');
  assert.ok(!r.raw.includes('NOTICE-KEY'));
  const lists = h.calls.filter(isList); assert.equal(lists.length, 2); assert.equal(new URL(lists[0]).searchParams.get('serviceKey'), 'NOTICE-KEY-1'); assert.equal(new URL(lists[0]).searchParams.get('numOfRows'), '100');
  const n = h.calls.length; await h.run('/api/v1/notices?sgg=41450'); assert.equal(h.calls.length, n);                                          // 전국 목록·표준코드 표는 캐시
  h.clock.t += 3600 * 1000 + 1; await h.run('/api/v1/notices?sgg=41450'); assert.equal(h.calls.filter(isList).length, 4);                           // 1시간 뒤 목록만 다시
});

test('여러 쪽: 총건수만큼 100건씩 이어 받는다. 한쪽 목록만 실패하면 나머지를 주고 meta.partial(짧게만 캐시), 둘 다 실패하면 502, 키 없음 503, 한도 429', async () => {
  const pages = harness({ fetch: (url) => { const u = new URL(url); if (u.pathname.endsWith('/rsdtRcritNtcList')) { const p = Number(u.searchParams.get('pageNo')); return ok(mh([N(String(100 + p), '경기도', '하남시')], 150)); } return defaultFetch(url); } });
  const a = await pages.run('/api/v1/notices?sgg=41450'); assert.equal(a.json.meta.rental, 2); assert.equal(pages.calls.filter((u) => new URL(u).pathname.endsWith('/rsdtRcritNtcList')).length, 2);
  const half = harness({ fetch: (url) => (new URL(url).pathname.endsWith('/ltRsdtRcritNtcList') ? raw(503, '') : defaultFetch(url)) });
  const b = await half.run('/api/v1/notices?sgg=41450'); assert.equal(b.status, 200); assert.deepEqual(b.json.meta.partial, ['sale']); assert.equal(b.json.meta.sale, 0); assert.equal(b.json.items.length, 2); assert.equal(b.headers['cache-control'], 'public, s-maxage=60');
  const dead = harness({ fetch: (url) => (isList(url) || isLh(url) ? raw(503, '') : defaultFetch(url)) }); const c = await dead.run('/api/v1/notices?sgg=41450'); assert.equal(c.status, 502); assert.equal(c.json.code, 'upstream'); assert.equal(c.headers['cache-control'], 'no-store');
  const none = await harness({ env: {} }).run('/api/v1/notices?sgg=41450'); assert.equal(none.status, 503); assert.equal(none.json.code, 'not-configured');
  const quota = harness({ fetch: (url) => (isList(url) || isLh(url) ? raw(429, '') : defaultFetch(url)) }); const q = await quota.run('/api/v1/notices?sgg=41450'); assert.equal(q.status, 429); assert.equal(q.json.code, 'keys-exhausted'); assert.ok(Number(q.headers['retry-after']) > 0);
});

test('거절: 쿼리·코드 종류(법정동·PNU 는 시군구가 아님)·표준코드 표에 없는 시군구(404)·방식', async () => {
  const h = harness();
  for (const [url, status, code, reason] of [['/api/v1/notices', 400, 'invalid-query'], ['/api/v1/notices?sgg=41450&x=1', 400, 'invalid-query'], ['/api/v1/notices?sgg=41450&sgg=11230', 400, 'invalid-query'],
    ['/api/v1/notices?sgg=abc', 400, 'invalid-code', 'not-digits'], ['/api/v1/notices?sgg=4145011400', 400, 'invalid-code', 'type-mismatch'], ['/api/v1/notices?sgg=41', 400, 'invalid-code', 'type-mismatch'], ['/api/v1/notices?sgg=99999', 400, 'invalid-code', 'unknown-sido']]) {
    const r = await h.run(url); assert.equal(r.status, status, url); assert.equal(r.json.code, code, url); assert.equal(r.json.type, `/problems/${code}`); if (reason) assert.equal(r.json.reason, reason, url);
  }
  const nf = await h.run('/api/v1/notices?sgg=41111'); assert.equal(nf.status, 404); assert.equal(nf.json.code, 'unknown-code'); assert.equal(nf.json.sgg, '41111');
  const post = await h.run('/api/v1/notices?sgg=41450', 'POST'); assert.equal(post.status, 405); assert.equal(post.headers.allow, 'GET, HEAD');
});

/* ---------- LH 분양임대공고문(15058530)·공급정보(15056765) ---------- */
const SUP = (rows) => [{ dsSch: [{}] }, { dsList01Nm: [{}], resHeader: [{ RS_DTTM: '20261006091015', SS_CODE: 'Y' }], dsList01: rows }];
const lhFetch = (rowsByStatus, supply) => (url) => {
  const u = new URL(url);
  if (u.pathname.endsWith('/lhLeaseNoticeInfo1')) return ok(LHOK(rowsByStatus[u.searchParams.get('PAN_SS')] || []));
  if (u.pathname.endsWith('/getLeaseNoticeSplInfo1')) return supply ? supply(u.searchParams) : raw(503, '');
  return defaultFetch(url);
};
const LH_ROWS = {
  '공고중': [
    lhRow('L1', '하남시 신혼희망타운 행복주택 예비입주자 모집공고(2026.10.01)', { PAN_NT_ST_DT: '2026.10.01' }),        // 마이홈 rental-1 과 같은 제목 → 마이홈만 남는다(N('1') 의 제목은 '공고 1' 이라 아래에서 같은 제목으로 맞춘다)
    lhRow('L2', '하남감일 A-1블록 국민임대주택 입주자 모집공고', { UPP_AIS_TP_CD: '05', AIS_TP_CD_NM: '분양주택', PAN_NT_ST_DT: '2026.10.04' }),
    lhRow('L3', '성남금토 A-4블록 신혼희망타운'), lhRow('L4', '하남 미분양 상가 입찰', { UPP_AIS_TP_CD: '22' }), lhRow('L5', '하남시 토지 매각', { UPP_AIS_TP_CD: '01' }),
    lhRow('L6', '하남시 행복주택', { CNP_CD_NM: '서울특별시' }), lhRow('L7', '하남시 전국 공고', { CNP_CD_NM: '전국' }),
  ],
  '접수중': [lhRow('L8', '하남풍산 영구임대주택 예비입주자 모집', { PAN_SS: '접수중', PAN_NT_ST_DT: '2026.09.20' })],
  '정정공고중': [lhRow('L9', '[정정공고]경기도 하남시 청년 매입임대', { PAN_SS: '정정공고중', PAN_NT_ST_DT: '2026.10.03' })],
};
const SUPPLY = (q) => (q.get('PAN_ID') === 'L2' ? ok(SUP([{ SBD_LGO_NM: '하남감일A1', HTY_NNA: '59A', NOW_HSH_CNT: '40', HSH_CNT: '50' }, { SBD_LGO_NM: '하남감일A1', HTY_NNA: '74A', NOW_HSH_CNT: '60', HSH_CNT: '60' }])) : ok(SUP([])));

test('LH 공고문: 진행 중 주택 공고를 받아 제목에 시군구 이름이 있는 것만 더한다(시도 다름·전국·상가·토지 제외, 마이홈과 같은 제목은 마이홈만), 공급정보로 단지명·세대수를 채운다', async () => {
  const mhRent = [N('1', '경기도', '하남시', { pblancNm: '하남시 신혼희망타운 행복주택 예비입주자 모집공고(2026.10.01)' }), N('3', '서울특별시', '성북구')];
  const h = harness({ fetch: (url) => { const u = new URL(url); if (u.pathname.endsWith('/rsdtRcritNtcList')) return ok(mh(mhRent)); if (u.pathname.endsWith('/ltRsdtRcritNtcList')) return ok(mh([])); return lhFetch(LH_ROWS, SUPPLY)(url); } });
  const r = await h.run('/api/v1/notices?sgg=41450');
  assert.equal(r.status, 200);
  assert.deepEqual(r.json.items.map((i) => [i.id, i.source]), [['lh-L2', 'lh'], ['lh-L9', 'lh'], ['rental-1', 'myhome'], ['lh-L8', 'lh']]);   // 공고일 최신 순: L2 10-04 · L9 10-03 · rental-1 10-01 · L8 09-20
  const l2 = r.json.items[0];
  assert.deepEqual(l2, { id: 'lh-L2', kind: 'sale', title: '하남감일 A-1블록 국민임대주택 입주자 모집공고', agency: '한국토지주택공사', status: '공고중', housingType: '분양주택', supplyType: '임대주택', complex: '하남감일A1', units: 100,
    address: null, pnu: null, announcedAt: '2026-10-04', applyFrom: null, applyTo: '2026-10-20', url: 'https://apply.lh.or.kr/lhapply/apply/wt/wrtanc/selectWrtancInfo.do?panId=L2', source: 'lh' });
  assert.equal(r.json.items[1].complex, null); assert.equal(r.json.items[1].units, null);                                                      // 공급정보가 비어 있으면 그대로 null
  assert.deepEqual(r.json.meta, { source: LH_SOURCE_TEXT, rental: 2, sale: 0, lh: 9, matched: 4, lhMatched: 3 });
  assert.equal(r.headers['cache-control'], 'public, s-maxage=3600, stale-while-revalidate=3600'); assert.ok(!r.raw.includes('NOTICE-KEY'));
  assert.ok(!r.raw.includes('_supply'), '내부 연결 값은 응답에 없다');
  const lists = h.calls.filter((u) => new URL(u).pathname.endsWith('/lhLeaseNoticeInfo1'));
  assert.deepEqual(lists.map((u) => new URL(u).searchParams.get('PAN_SS')), ['공고중', '접수중', '정정공고중']);
  const q = new URL(lists[0]).searchParams; assert.equal(q.get('serviceKey'), 'NOTICE-KEY-1'); assert.equal(q.get('PG_SZ'), '100'); assert.equal(q.get('PAN_ED_DT'), '20261005'); assert.equal(q.get('PAN_ST_DT'), '20251005');
  assert.equal(h.calls.filter((u) => new URL(u).pathname.endsWith('/getLeaseNoticeSplInfo1')).length, 3, '고른 공고마다 공급정보 한 번');
  const n = h.calls.length; await h.run('/api/v1/notices?sgg=41450'); assert.equal(h.calls.length, n, '목록·공급정보·표준코드는 캐시');
});

test('LH 공고문: 쪽 나누기(공고중 125건 → 100건씩 2쪽), 공급정보 호출은 한 응답 20건까지, 같은 공고의 공급정보는 24시간 캐시', async () => {
  const many = Array.from({ length: 125 }, (_, i) => lhRow(`M${String(i).padStart(3, '0')}`, `하남시 매입임대 ${i}`, { PAN_NT_ST_DT: '2026.09.01', ALL_CNT: '125' }));
  const h = harness({ fetch: (url) => {
    const u = new URL(url);
    if (u.pathname.endsWith('/lhLeaseNoticeInfo1')) { if (u.searchParams.get('PAN_SS') !== '공고중') return ok(LHOK([])); const p = Number(u.searchParams.get('PAGE')); return ok(LHOK(many.slice((p - 1) * 100, p * 100))); }
    return lhFetch({}, () => ok(SUP([{ SBD_LGO_NM: 'x', NOW_HSH_CNT: '1' }])))(url);
  } });
  const r = await h.run('/api/v1/notices?sgg=41450');
  assert.equal(r.json.meta.lh, 125); assert.equal(r.json.meta.lhMatched, 125); assert.equal(r.json.items.length, 128, '마이홈 3건 + LH 125건');
  const pagesOf = () => h.calls.filter((u) => new URL(u).pathname.endsWith('/lhLeaseNoticeInfo1') && new URL(u).searchParams.get('PAN_SS') === '공고중').map((u) => new URL(u).searchParams.get('PAGE'));
  assert.deepEqual(pagesOf(), ['1', '2']);
  assert.equal(r.json.items.filter((i) => i.units === 1).length, 20, '공급정보는 20건까지만');
  const supplies = () => h.calls.filter((u) => new URL(u).pathname.endsWith('/getLeaseNoticeSplInfo1')).length;
  assert.equal(supplies(), 20);
  h.clock.t += 3600 * 1000 + 1; await h.run('/api/v1/notices?sgg=41450');
  assert.deepEqual(pagesOf(), ['1', '2', '1', '2'], '1시간 뒤 목록은 다시 받고'); assert.equal(supplies(), 20, '공급정보는 24시간 캐시');
});

test('LH 공고문: 공급정보만 실패하면 공고는 나가고 meta.partial 에 lh-supply(짧게 캐시), 목록이 실패하면 마이홈 공고는 나가고 partial lh, 마이홈 둘 다 실패해도 LH 가 되면 LH 만', async () => {
  const noSupply = harness({ fetch: lhFetch(LH_ROWS, null) });
  const a = await noSupply.run('/api/v1/notices?sgg=41450');
  assert.equal(a.status, 200); assert.ok(a.json.items.some((i) => i.id === 'lh-L2' && i.units === null)); assert.deepEqual(a.json.meta.partial, ['lh-supply']); assert.equal(a.headers['cache-control'], 'public, s-maxage=60');
  const lhDown = harness({ fetch: (url) => (new URL(url).pathname.endsWith('/lhLeaseNoticeInfo1') ? raw(503, '') : defaultFetch(url)) });
  const b = await lhDown.run('/api/v1/notices?sgg=41450');
  assert.equal(b.status, 200); assert.deepEqual(b.json.meta.partial, ['lh']); assert.equal(b.json.meta.lh, 0); assert.equal(b.json.items.length, 3); assert.equal(b.headers['cache-control'], 'public, s-maxage=60');
  const mhDown = harness({ fetch: (url) => (isList(url) ? raw(503, '') : lhFetch(LH_ROWS, SUPPLY)(url)) });
  const c = await mhDown.run('/api/v1/notices?sgg=41450');
  assert.equal(c.status, 200); assert.deepEqual(c.json.meta.partial, ['rental', 'sale']); assert.ok(c.json.items.length > 0 && c.json.items.every((i) => i.source === 'lh'));
  const quota = '<OpenAPI_ServiceResponse><cmmMsgHeader><errMsg>SERVICE ERROR</errMsg><returnAuthMsg>LIMITED_NUMBER_OF_SERVICE_REQUESTS_EXCEEDS_ERROR</returnAuthMsg><returnReasonCode>22</returnReasonCode></cmmMsgHeader></OpenAPI_ServiceResponse>';
  const lhQuota = harness({ fetch: (url) => (isLh(url) ? raw(200, quota) : defaultFetch(url)) });
  const d = await lhQuota.run('/api/v1/notices?sgg=41450'); assert.equal(d.status, 200); assert.deepEqual(d.json.meta.partial, ['lh']);   // LH 한도는 마이홈 공고를 막지 않는다
});
