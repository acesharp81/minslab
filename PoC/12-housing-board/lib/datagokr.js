/* 공공데이터포털(apis.data.go.kr) JSON 한 쪽 조회: 일시 오류는 점점 길게 기다려 다시 시도하고, 한도 오류는 e.quota=true 로 던져 키 풀(lib/keys.js)이 다음 키로 넘기게 한다.
   - 다시 시도: HTTP 5xx · 빈 본문 · JSON 아님 · resultCode 99(동시 접속 가득) 최대 attempts 번
   - 초당 한도(…REQUESTS_PER_SECOND_EXCEEDS_ERROR, HTTP 429): 하루 한도가 아니라 순간 과속이므로 잠시 쉬고 다시 시도한다(계속이면 e.throttled, 키는 쉬게 하지 않음)
   - 일일 한도: HTTP 429(본문 없음) · XML 본문의 LIMITED_NUMBER… · resultCode 22 → quota
   - 그 밖의 오류(resultCode 가 00 이 아님·4xx)는 바로 던진다. 오류 문구에 요청 주소(키 포함)를 담지 않는다.
   - 관리번호(mgm…Pk)는 22자리 숫자까지 있고 건축HUB 는 이를 JSON 숫자로 준다(실측: 장위동 47개의 22자리 값이 JSON.parse 뒤 4개로 뭉개져 '1.0000000000000001e+21' 이 됨).
     그대로 두면 서로 다른 허가가 같은 번호가 되므로 파싱 전에 16자리 이상 mgm…Pk 숫자를 문자열로 감싼다(protectBigInts). 13자리 이하는 정확해서 그대로 둔다.
   시험: tests/js/permitsapi.test.cjs · tests/js/infra.api.test.cjs · tests/js/datagokr.test.cjs */
'use strict';
const { isQuotaError } = require('./keys.js');

/* 정밀도를 잃는 큰 정수(16자리 이상)인 mgm…Pk 값을 따옴표로 감싼다: "mgmHsrgstPk":1000000000000000339484 → "mgmHsrgstPk":"1000000000000000339484" */
const protectBigInts = (text) => String(text).replace(/("mgm\w*Pk"\s*:\s*)(\d{16,})/g, '$1"$2"');

const quotaError = () => { const e = new Error('quota'); e.quota = true; return e; };

async function fetchPage({ doFetch, sleep, url, params, timeoutMs = 10000, attempts = 4 }) {
  const q = new URLSearchParams(params);
  let last = '응답 없음', wait = 0, throttled = false;
  for (let attempt = 0; attempt < attempts; attempt++) {
    if (attempt) await sleep(wait || 400 * attempt);
    wait = 0;
    let r;
    try { r = await doFetch(`${url}?${q}`, { signal: AbortSignal.timeout(timeoutMs), headers: { Accept: 'application/json' } }); } catch (e) { last = 'network'; continue; }
    const text = r.status === 429 || r.ok ? await r.text() : '';
    if (/REQUESTS_PER_SECOND/i.test(text)) { last = '초당 호출 한도'; throttled = true; wait = 1100 * (attempt + 1); continue; }
    if (r.status === 429) throw quotaError();
    if (!r.ok) { last = `HTTP ${r.status}`; if (r.status >= 500) continue; throw new Error(last); }
    if (!String(text).trim()) { last = '빈 본문'; continue; }
    if (isQuotaError(text)) throw quotaError();
    let json; try { json = JSON.parse(protectBigInts(text)); } catch (e) { last = 'JSON 아님'; continue; }
    const header = json && json.response && json.response.header, code = String(header && header.resultCode);
    if (code === '22') throw quotaError();
    if (code === '99') { last = '동시 접속 가득'; continue; }
    if (code !== '00') throw new Error(`result ${code}`);
    const body = json.response.body || {}, items = body.items && body.items.item !== undefined ? body.items.item : body.item !== undefined ? body.item : body.items;   // 건축HUB·TAGO 는 body.items.item, 마이홈(HWSPR02)은 body.item
    return { items: Array.isArray(items) ? items : items && typeof items === 'object' ? [items] : [], total: Number(body.totalCount) || 0 };
  }
  const e = new Error(last); if (throttled && last === '초당 호출 한도') e.throttled = true;
  throw e;
}

module.exports = { fetchPage, quotaError, protectBigInts };
