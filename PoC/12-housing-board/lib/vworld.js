/* V-World 호출 공통: 키·domain 선택과 데이터 API 주소.
   키는 발급할 때 등록한 서비스 URL과 같은 domain 값을 보내야 통과한다(아니면 INCORRECT_KEY).
   운영키(VWORLD_KEY)는 운영 도메인에, 개발키(VWORLD_DEV_KEY)는 localhost 에 등록되어 있다.
   Vercel(env.VERCEL)에서는 VWORLD_KEY, 그 밖(로컬 개발 서버)에서는 VWORLD_DEV_KEY 가 있으면 그것을 쓴다.
   시험: tests/js/resolve.test.cjs */
'use strict';

const VWORLD_URL = 'https://api.vworld.kr/req/data';
const VWORLD_SEARCH_URL = 'https://api.vworld.kr/req/search';     // 장소(POI) 검색: 이름 → 좌표·지번·도로명
const VWORLD_ADDRESS_URL = 'https://api.vworld.kr/req/address';   // 주소 → 좌표·지번(PARCEL 은 구조에 PNU 가 옴)·도로명(ROAD)

function vworldCreds(env) {
  const key = (!env.VERCEL && env.VWORLD_DEV_KEY) || env.VWORLD_KEY;
  return { key, domain: env.VWORLD_DOMAIN || env.VERCEL_PROJECT_PRODUCTION_URL || 'localhost' };
}

/* 오류 문구에서 V-World 키·domain 값을 가린다(로그용) */
function redactVworld(text, env) {
  let msg = String(text);
  for (const k of ['VWORLD_KEY', 'VWORLD_DEV_KEY', 'VWORLD_DOMAIN']) if (env[k]) msg = msg.split(env[k]).join('<' + k + '>');
  return msg;
}

module.exports = { VWORLD_URL, VWORLD_SEARCH_URL, VWORLD_ADDRESS_URL, vworldCreds, redactVworld };
