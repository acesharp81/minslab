/* 서울특별시 버스 정류소(정류소정보조회 서비스, 공공데이터포털 15000303 · ws.bus.go.kr) 조회·변환. /api/v1/infra 가 서울(시도 11)의 정류장을 이것으로 채운다.
   서울은 국토교통부 TAGO 도시 목록에 없어 지금까지 OpenStreetMap 으로 보조했다(누락·공개 서버 장애). 이제 서울시가 직접 내는 자료를 먼저 쓰고, 실패하면 OSM 으로 물러난다.

   실측(2026-10-06, 프로젝트 키로 활용신청 뒤)
   - 주소는 http://ws.bus.go.kr/api/rest/stationinfo/getStationByPos 만 연결된다(https 는 연결 시간 초과). 인증키는 공공데이터포털 키(serviceKey) 그대로.
   - tmX=경도 tmY=위도 radius=미터(2,000 m 까지 한 번에 451곳을 줌, 쪽 나눔 없음) resultType=json.
   - 응답 { msgHeader:{ headerCd, headerMsg, itemCount }, msgBody:{ itemList:[{ stationId, stationNm, arsId, gpsX(경도), gpsY(위도), dist, … }] | null } }
     headerCd '0' 정상 · '4' 결과 없음(itemList null) · '3' 입력 좌표 오류. 그 밖은 오류로 본다.
   - 같은 서비스 묶음의 노선정보조회(busRouteInfo)는 이 키로 401(활용신청 범위 밖)이라 노선 경로 선은 못 그린다. 버스위치정보조회(buspos)·경유노선(getRouteByStation)은 200.
   - 개발계정 하루 1,000건(lib/keys.js DEFAULT_LIMITS seoul).
   한도 오류는 e.quota=true 로 던져 키 풀이 다음 키로 넘기게 하고, 초당 한도는 쉬었다 다시 부른다. 오류 문구에 요청 주소(키 포함)를 담지 않는다.
   시험: tests/js/seoul.test.cjs */
'use strict';
const { isQuotaError } = require('./keys.js');

const STATION_POS_URL = 'http://ws.bus.go.kr/api/rest/stationinfo/getStationByPos';
const SEOUL_SIDO = '11';
const RADIUS_M = 700;            // 중심들을 STOP_SKIP(300 m) 간격으로 고르면 점검 표시 반경(400 m)을 덮는다(300 + 400)
const SKIP_M = 300;
const MAX_CENTERS = 12;          // 한 법정동에서 부르는 최대 횟수(개발계정 하루 1,000건을 지키려고 TAGO 보다 작게)
const TIMEOUT_MS = 10000;

const finite = (v) => typeof v === 'number' && Number.isFinite(v);

/* getStationByPos 항목 → 번들 stops 항목({ id, name, lon, lat, no? }). id 는 'seoul-<stationId>'. 이름·좌표가 이상하면 null */
function seoulStop(it) {
  if (!it) return null;
  const lon = Number(it.gpsX), lat = Number(it.gpsY), sid = String(it.stationId == null ? '' : it.stationId).trim(), name = String(it.stationNm == null ? '' : it.stationNm).trim();
  if (!sid || !name || !finite(lon) || !finite(lat) || !(lat >= 33 && lat <= 39 && lon >= 124 && lon <= 132)) return null;
  const s = { id: `seoul-${sid}`, name, lon: Math.round(lon * 1e6) / 1e6, lat: Math.round(lat * 1e6) / 1e6 };
  const no = String(it.arsId == null ? '' : it.arsId).trim();
  if (no && no !== '0') s.no = no;
  return s;
}

/* 응답 본문(JSON 객체) → 정류소 항목 목록. headerCd 가 정상('0')·결과 없음('4')이 아니면 오류 */
function itemsOf(json) {
  const h = json && json.msgHeader, code = h && String(h.headerCd);
  if (code === '4') return [];
  if (code !== '0') throw new Error(`서울 정류소 응답 ${code === 'undefined' ? '모양 이상' : `headerCd ${code}`}`);
  const list = json.msgBody && json.msgBody.itemList;
  return Array.isArray(list) ? list : list && typeof list === 'object' ? [list] : [];
}

/* 한 중심(경도·위도) 주변 정류소 원본 항목. 일시 오류(5xx·빈 본문·JSON 아님)는 점점 길게 기다려 다시, 초당 한도는 쉬었다 다시, 하루 한도는 e.quota */
async function fetchStations({ doFetch, sleep, key, center, radius = RADIUS_M, attempts = 3 }) {
  const q = new URLSearchParams({ serviceKey: key, tmX: center[0].toFixed(6), tmY: center[1].toFixed(6), radius: String(radius), resultType: 'json' });
  let last = '응답 없음', throttled = false;
  for (let attempt = 0; attempt < attempts; attempt++) {
    if (attempt) await sleep(throttled ? 1100 * attempt : 400 * attempt);
    throttled = false;
    let r;
    try { r = await doFetch(`${STATION_POS_URL}?${q}`, { signal: AbortSignal.timeout(TIMEOUT_MS), headers: { Accept: 'application/json' } }); } catch (e) { last = 'network'; continue; }
    const text = r.ok || r.status === 429 ? await r.text() : '';
    if (/REQUESTS_PER_SECOND/i.test(text)) { last = '초당 호출 한도'; throttled = true; continue; }
    if (r.status === 429 || isQuotaError(text)) { const e = new Error('quota'); e.quota = true; throw e; }
    if (!r.ok) { last = `HTTP ${r.status}`; if (r.status >= 500) continue; throw new Error(last); }
    if (!String(text).trim()) { last = '빈 본문'; continue; }
    let json; try { json = JSON.parse(text); } catch (e) { last = 'JSON 아님'; continue; }
    return itemsOf(json);
  }
  const e = new Error(last); if (throttled) e.throttled = true;
  throw e;
}

module.exports = { STATION_POS_URL, SEOUL_SIDO, RADIUS_M, SKIP_M, MAX_CENTERS, seoulStop, itemsOf, fetchStations };
