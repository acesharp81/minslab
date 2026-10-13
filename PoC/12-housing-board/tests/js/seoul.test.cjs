'use strict';
/* lib/seoul.js — 서울시 정류소정보조회 변환·호출. 네트워크 없이 가짜 fetch 로 시험한다. 응답 모양은 2026-10-06 실측(시청 주변 반경 300 m). */
const test = require('node:test');
const assert = require('node:assert/strict');
const S = require('../../lib/seoul.js');

const ok = (json) => ({ ok: true, status: 200, text: async () => JSON.stringify(json) });
const raw = (status, text) => ({ ok: status < 400, status, text: async () => text });
const HEADER = (cd, msg = '') => ({ msgHeader: { headerCd: cd, headerMsg: msg, itemCount: 0 } });
const body = (items) => ({ ...HEADER('0', '정상적으로 처리되었습니다.'), msgBody: { itemList: items } });
const REAL = { stationId: '101000227', stationNm: '시청.덕수궁', gpsX: '126.976921', gpsY: '37.566254', posX: '197961.29', posY: '451862.90', stationTp: '0', arsId: '02662', dist: '99' };

test('seoulStop: 실측 항목을 번들 stops 모양으로(id seoul-, 경도 gpsX·위도 gpsY, 번호 arsId). 번호 0·이름 없음·좌표 이상은 걸러낸다', () => {
  assert.deepEqual(S.seoulStop(REAL), { id: 'seoul-101000227', name: '시청.덕수궁', lon: 126.976921, lat: 37.566254, no: '02662' });
  assert.equal('no' in S.seoulStop({ ...REAL, arsId: '0' }), false);
  assert.equal('no' in S.seoulStop({ ...REAL, arsId: null }), false);
  for (const bad of [null, {}, { ...REAL, stationNm: ' ' }, { ...REAL, stationId: '' }, { ...REAL, gpsX: 'x' }, { ...REAL, gpsY: '0' }, { ...REAL, gpsX: '10', gpsY: '10' }]) assert.equal(S.seoulStop(bad), null);
});

test('itemsOf: 정상(0)은 목록, 결과 없음(4)은 빈 목록, 입력 좌표 오류(3)·시스템 에러·모양 이상은 오류. 항목 하나뿐인 객체도 목록으로', () => {
  assert.deepEqual(S.itemsOf(body([REAL, REAL])), [REAL, REAL]);
  assert.deepEqual(S.itemsOf(body(REAL)), [REAL]);
  assert.deepEqual(S.itemsOf({ ...HEADER('4', '결과가 없습니다.'), msgBody: { itemList: null } }), []);
  assert.deepEqual(S.itemsOf({ ...HEADER('0'), msgBody: {} }), []);
  for (const bad of [HEADER('3', '입력좌표가 올바르지 않습니다.'), HEADER('1', '시스템 에러'), {}, null, { msgBody: {} }]) assert.throws(() => S.itemsOf(bad), /서울 정류소 응답/);
});

const call = (fetchImpl, over = {}) => S.fetchStations({ doFetch: fetchImpl, sleep: async () => {}, key: 'K+/=', center: [126.9769, 37.5662], ...over });

test('fetchStations: 주소·매개변수(http, tmX=경도 tmY=위도 radius resultType json, 키는 한 번만 인코딩)와 정상·결과 없음 처리', async () => {
  const seen = [];
  const got = await call(async (url, init) => { seen.push({ url, init }); return ok(body([REAL])); });
  assert.deepEqual(got, [REAL]);
  const u = new URL(seen[0].url);
  assert.equal(`${u.protocol}//${u.host}${u.pathname}`, 'http://ws.bus.go.kr/api/rest/stationinfo/getStationByPos');
  assert.deepEqual([u.searchParams.get('tmX'), u.searchParams.get('tmY'), u.searchParams.get('radius'), u.searchParams.get('resultType')], ['126.976900', '37.566200', String(S.RADIUS_M), 'json']);
  assert.equal(u.searchParams.get('serviceKey'), 'K+/=', '디코딩된 키가 한 번만 인코딩되어 원래 값으로 돌아온다');
  assert.ok(seen[0].url.includes('serviceKey=K%2B%2F%3D'));
  assert.deepEqual(await call(async () => ok({ ...HEADER('4'), msgBody: { itemList: null } })), []);
  assert.deepEqual(await call(async () => ok(body([REAL])), { radius: 300 }).then((r) => r.length), 1);
});

test('fetchStations: 일시 오류(연결·5xx·빈 본문·JSON 아님)는 다시 시도하고 끝내 안 되면 오류, 4xx 는 바로 오류', async () => {
  for (const [label, bad] of [['network', () => { throw new Error('x'); }], ['HTTP 503', () => raw(503, '')], ['빈 본문', () => raw(200, '  ')], ['JSON 아님', () => raw(200, '<html>')]]) {
    let n = 0;
    await assert.rejects(call(async () => { n++; return bad(); }), (e) => e.message === label && !e.quota);
    assert.equal(n, 3, `${label}: 3번 시도`);
  }
  let n = 0;
  const got = await call(async () => (++n < 3 ? raw(502, '') : ok(body([REAL]))));
  assert.equal(got.length, 1); assert.equal(n, 3);
  let m = 0;
  await assert.rejects(call(async () => { m++; return raw(401, '{"error":"Unauthorized","message":"유효하지 않은 서비스키입니다"}'); }), (e) => e.message === 'HTTP 401' && !/K\+/.test(e.message));
  assert.equal(m, 1);
});

test('fetchStations: 하루 한도(HTTP 429·XML LIMITED_NUMBER…)는 e.quota 로 바로, 초당 한도는 쉬었다 다시 하고 끝내 안 풀리면 e.throttled', async () => {
  const xml = '<OpenAPI_ServiceResponse><cmmMsgHeader><errMsg>SERVICE ERROR</errMsg><returnAuthMsg>LIMITED_NUMBER_OF_SERVICE_REQUESTS_EXCEEDS_ERROR</returnAuthMsg><returnReasonCode>22</returnReasonCode></cmmMsgHeader></OpenAPI_ServiceResponse>';
  for (const bad of [() => raw(429, ''), () => raw(200, xml), () => raw(429, xml)]) {
    let n = 0;
    await assert.rejects(call(async () => { n++; return bad(); }), (e) => e.quota === true);
    assert.equal(n, 1);
  }
  const perSec = '<OpenAPI_ServiceResponse><cmmMsgHeader><errMsg>SERVICE ERROR</errMsg><returnAuthMsg>LIMITED_NUMBER_OF_SERVICE_REQUESTS_PER_SECOND_EXCEEDS_ERROR</returnAuthMsg></cmmMsgHeader></OpenAPI_ServiceResponse>';
  const waits = []; let n = 0;
  const got = await S.fetchStations({ doFetch: async () => (++n < 3 ? raw(429, perSec) : ok(body([REAL]))), sleep: async (ms) => { waits.push(ms); }, key: 'k', center: [127, 37.5] });
  assert.equal(got.length, 1); assert.deepEqual(waits, [1100, 2200], '초당 한도는 점점 길게 쉬었다 다시');
  await assert.rejects(S.fetchStations({ doFetch: async () => raw(429, perSec), sleep: async () => {}, key: 'k', center: [127, 37.5] }), (e) => e.throttled === true && !e.quota);
});

test('상수: 중심 간격 + 점검 표시 반경이 조회 반경 안이다(300 + 400 ≤ 700), 한 법정동 최대 호출 12', () => {
  const { STOP_SHOW_M } = require('../../lib/infra.js');
  assert.ok(S.SKIP_M + STOP_SHOW_M <= S.RADIUS_M);
  assert.equal(S.MAX_CENTERS, 12); assert.equal(S.SEOUL_SIDO, '11');
});
