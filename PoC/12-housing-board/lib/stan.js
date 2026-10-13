/* 행정표준코드(법정동코드) 시군구 단위 조회: 시군구 안의 모든 행(시도·시군구·읍면동·리)을 24시간 캐시로 준다.
   /api/v1/resolve(코드 해석)와 /api/v1/permits(같은 시군구의 이웃 법정동 목록)가 같이 쓴다.
   키는 lib/keys.js 의 RESOLVE 용도 풀(서비스 stan). 시험: tests/js/resolve.test.cjs */
'use strict';

const STAN_URL = 'https://apis.data.go.kr/1741000/StanReginCd/getStanReginCdList';
const TTL_MS = 24 * 3600 * 1000;
const FETCH_TIMEOUT_MS = 10000;
const PACE_MS = 110;                                   // 초당 8건쯤: 12건을 한꺼번에 보내자 429(…PER_SECOND…)가 났다(실측)
const THROTTLE_ATTEMPTS = 3;

function createStan({ doFetch, pool, cache, sleep }) {
  const wait = sleep || ((ms) => new Promise((r) => setTimeout(r, ms)));
  let slot = 0;
  const pace = async () => { const t = Date.now(), at = Math.max(t, slot); slot = at + PACE_MS; if (at > t) await wait(at - t); };   // 초당 한도(30건쯤, 넘으면 한동안 막힘)를 넘지 않게 간격을 둔다
  /* 초당 한도(429 …PER_SECOND…)는 쉬었다 다시 부르고, 계속이면 throttled(키는 쉬게 하지 않음). 그 밖의 429 는 하루 한도로 보고 status 를 남긴다 */
  async function getJson(url) {
    let last;
    for (let attempt = 0; attempt < THROTTLE_ATTEMPTS; attempt++) {
      if (attempt) await wait(1100 * attempt);
      await pace();
      const r = await doFetch(url, { signal: AbortSignal.timeout(FETCH_TIMEOUT_MS), headers: { Accept: 'application/json' } });
      if (r.ok) return r.json();
      const text = r.status === 429 && r.text ? await r.text() : '';
      if (/PER_SECOND/.test(text)) { last = new Error('초당 호출 한도'); last.throttled = true; continue; }
      const e = new Error(`HTTP ${r.status}`); e.status = r.status; throw e;
    }
    throw last;
  }
  /* 시군구 안 표준코드 행 전부(24시간 캐시). 없으면 [] */
  function rows(sido, sgg) {
    return cache.wrap(`stan:${sido}${sgg}`, TTL_MS, () => pool.run('RESOLVE', 'stan', async (key) => {
      const out = [];
      for (let page = 1; page <= 10; page++) {
        const q = new URLSearchParams({ serviceKey: key, type: 'json', numOfRows: '1000', pageNo: String(page), sido_cd: sido, sgg_cd: sgg.slice(2) });
        const json = await getJson(`${STAN_URL}?${q}`);
        const block = json && json.StanReginCd;
        if (!Array.isArray(block)) { if (json && json.RESULT && json.RESULT.resultCode === 'INFO-3') return out; return json; }   // 이상한 모양은 pool 이 한도 오류인지 본다
        const head = block[0] && block[0].head, total = Number(head && head[0] && head[0].totalCount) || 0;
        const rs = (block.find((b) => b && b.row) || {}).row || [];
        out.push(...rs);
        if (out.length >= total || !rs.length) return out;
      }
      return out;
    }).then((r) => { if (!Array.isArray(r)) throw new Error('표준코드 응답 모양이 다름'); return r; }));
  }
  /* 이름 부분 일치 검색(locatadd_nm, 전국): 법정동·시군구 이름으로 표준코드 행을 찾는다. 최대 300행, 24시간 캐시. 못 찾으면 [] */
  function search(name) {
    return cache.wrap(`stan:name:${name}`, TTL_MS, () => pool.run('RESOLVE', 'stan', async (key) => {
      const q = new URLSearchParams({ serviceKey: key, type: 'json', numOfRows: '300', pageNo: '1', locatadd_nm: name });
      const json = await getJson(`${STAN_URL}?${q}`);
      const block = json && json.StanReginCd;
      if (!Array.isArray(block)) { if (json && json.RESULT && json.RESULT.resultCode === 'INFO-3') return []; return json; }
      return (block.find((b) => b && b.row) || {}).row || [];
    }).then((r) => { if (!Array.isArray(r)) throw new Error('표준코드 응답 모양이 다름'); return r; }));
  }
  /* 시군구(5자리) 안의 읍면동 법정동코드(10자리, 리 제외) 목록 */
  async function umdCodes(sgg5) {
    const list = await rows(sgg5.slice(0, 2), sgg5);
    return list.filter((r) => r && r.umd_cd !== '000' && r.ri_cd === '00' && String(r.region_cd).startsWith(sgg5)).map((r) => String(r.region_cd));
  }
  return { rows, umdCodes, search };
}

module.exports = { createStan, STAN_URL };
