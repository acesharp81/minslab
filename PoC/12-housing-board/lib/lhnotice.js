/* 한국토지주택공사 분양임대공고문(공공데이터포털 15058530 lhLeaseNoticeInfo1)과 분양임대공고별 공급정보(15056765 lhLeaseNoticeSplInfo1) 변환·시군구 거르기. /api/v1/notices 가 마이홈 공고에 더한다.
   실측(2026-10-06, 프로젝트 키로 활용신청 뒤)
   - 목록: https://apis.data.go.kr/B552555/lhLeaseNoticeInfo1/lhLeaseNoticeInfo1  PG_SZ(≤100)·PAGE·PAN_ST_DT·PAN_ED_DT(YYYYMMDD, 기본은 두 달)·PAN_SS(공고상태: 공고중 142 · 접수중 3 · 정정공고중 5 · 접수마감 1,583건)
     UPP_AIS_TP_CD(05 분양주택 · 06 임대주택 · 13 주거복지 · 39 공공분양(신혼희망) · 54 이익공유형 분양주택 · 01 토지 · 22 상가)·CNP_CD(시도).
     응답은 배열 [{dsSch:[조회조건]}, {dsList:[행…], resHeader:[{SS_CODE:'Y', RS_DTTM}]}], 행 { PAN_ID, PAN_NM, CNP_CD_NM(시도: '인천광역시'·'인천광역시 외'·'전국'), UPP_AIS_TP_CD, AIS_TP_CD_NM, PAN_SS, PAN_NT_ST_DT('2026.10.02'), CLSG_DT, DTL_URL, SPL_INF_TP_CD, CCR_CNNT_SYS_DS_CD, ALL_CNT(전체 건수) }. 결과가 없으면 dsList 가 빈 배열.
   - 지역은 시도뿐이다(시군구·주소 없음). 공급정보에도 주소는 없고 단지명·주택형·세대수(NOW_HSH_CNT 금회공급 · HSH_CNT)만 있다 → 공고 제목에 시군구·법정동 이름이 들어 있을 때만 그 시군구의 공고로 본다(inRegion).
   - 마이홈 공고(HWSPR02)와는 id 가 달라(LH PAN_ID 2015122300020858 ↔ 마이홈 pblancId 21378) 제목이 같으면 같은 공고로 보고 마이홈 쪽만 둔다(titleKey).
   - 공급정보: https://apis.data.go.kr/B552555/lhLeaseNoticeSplInfo1/getLeaseNoticeSplInfo1  PAN_ID·SPL_INF_TP_CD·CCR_CNNT_SYS_DS_CD·UPP_AIS_TP_CD 가 모두 목록 행의 값이다. 응답의 dsList01: { SBD_LGO_NM 단지명, HTY_NNA 주택형, NOW_HSH_CNT, HSH_CNT }.
   순수 함수(네트워크·키 없음)와 응답 한 번 읽기(fetchLh)만 둔다. 링크는 LH 주소만 싣는다. 시험: tests/js/lhnotice.test.cjs */
'use strict';
const { isQuotaError } = require('./keys.js');

const LIST_URL = 'https://apis.data.go.kr/B552555/lhLeaseNoticeInfo1/lhLeaseNoticeInfo1';
const SUPPLY_URL = 'https://apis.data.go.kr/B552555/lhLeaseNoticeSplInfo1/getLeaseNoticeSplInfo1';
const STATUSES = ['공고중', '접수중', '정정공고중'];                      // 진행 중인 것만(접수마감 1,583건은 지나간 공고)
const KIND_OF = { '05': 'sale', '06': 'rental', '13': 'rental', '39': 'sale', '54': 'sale' };   // 주택 공고만. 토지(01)·상가(22) 등은 뺀다
const HOSTS = ['https://apply.lh.or.kr/', 'https://www.myhome.go.kr/'];
const FETCH_TIMEOUT_MS = 10000;

const clean = (v) => (v == null ? '' : String(v).replace(/\s+/g, ' ').trim());
/* '2026.10.02' → '2026-10-02'. 달력에 없는 날짜는 null */
function dateOf(v) {
  const m = /^(\d{4})[.\-](\d{2})[.\-](\d{2})$/.exec(clean(v));
  if (!m) return null;
  const iso = `${m[1]}-${m[2]}-${m[3]}`, t = new Date(`${iso}T00:00:00Z`);
  return !Number.isNaN(t.getTime()) && t.toISOString().slice(0, 10) === iso ? iso : null;
}
const safeUrl = (u) => { const s = clean(u); return HOSTS.some((h) => s.startsWith(h)) ? s : ''; };

/* 목록 행 → 공고 한 건(마이홈 공고와 같은 모양, source:'lh'). 주택 공고가 아니거나 제목이 없거나 진행 중이 아니면 null */
function notice(raw) {
  if (!raw) return null;
  const kind = KIND_OF[clean(raw.UPP_AIS_TP_CD)], title = clean(raw.PAN_NM), id = clean(raw.PAN_ID), status = clean(raw.PAN_SS);
  if (!kind || !title || !id || !STATUSES.includes(status)) return null;
  return {
    id: `lh-${id}`, kind, title, agency: '한국토지주택공사', status, housingType: clean(raw.AIS_TP_CD_NM) || null, supplyType: clean(raw.UPP_AIS_TP_NM) || null,
    complex: null, units: null, address: null, pnu: null,
    announcedAt: dateOf(raw.PAN_NT_ST_DT), applyFrom: null, applyTo: dateOf(raw.CLSG_DT), url: safeUrl(raw.DTL_URL) || safeUrl(raw.DTL_URL_MOB) || null, source: 'lh',
  };
}

/* 제목 비교용 키: 글자와 숫자만 남긴다('공고(26.10.02)'와 "공고('26.10.02)"가 같아진다) */
const titleKey = (title) => clean(title).replace(/[^\p{L}\p{N}]/gu, '');

/* 이름 낱말: '하남시'→['하남시','하남'], '영통구'→['영통구','영통'], '서구'→['서구'](한 글자 줄임은 쓰지 않음) */
function placeWords(name) {
  const t = clean(name), m = /^(.{2,}?)(시|군|구)$/.exec(t);
  return m ? [t, m[1]] : t.length >= 2 ? [t] : [];
}
/* 법정동 이름 → { full, stem }: '석남동'→{full:'석남동', stem:'석남'}, '을지로3가'→'을지로', '장위1동'→'장위'. 줄임이 두 글자 미만이면 stem 은 없다 */
function dongParts(name) {
  const full = clean(name), stem = full.replace(/\d*[동읍면가리]$/, '');
  return { full, stem: stem !== full && stem.length >= 2 ? stem : '' };
}
/* 시도 이름 맞추기: LH 는 '인천광역시 외'처럼 여러 시도를 한 공고에 적기도 한다. '전국'은 어느 지역도 가리키지 않는다 */
const sidoOf = (cnpName) => clean(cnpName).replace(/\s*외$/, '');
const sidoStem = (sido) => clean(sido).replace(/(특별자치도|특별자치시|특별시|광역시|도)$/, '');   // '경기도'→'경기', '제주특별자치도'→'제주', '인천광역시'→'인천'

/* 이 시군구(표준코드 전체 이름 '경기도 하남시', '경기도 수원시 영통구')의 공고인가. LH 공고에는 시도뿐이라 제목을 본다(제목 기준 추정):
   ① 시도가 같고 ② 제목에 이 시군구 이름(구가 있는 시의 구는 구 이름만 — '수원'은 다른 구의 공고에도 쓰인다) 또는
   법정동 전체 이름('금토동')이 있거나, 법정동 줄임말이 시도·시 줄임말 바로 뒤에 붙어 있을 때('성남금토'·'인천석남'·'하남감일'; 줄임말만으로는 '전주평화'가 익산 평화동으로 잡힌다).
   시도 줄임말과 같은 시 이름('제주시'의 '제주')은 시 이름으로 쓰지 않는다('[제주지역본부-서귀포시]'가 제주시 공고가 된다) */
function inRegion(raw, regionName, umdNames = []) {
  const parts = clean(regionName).split(' ').filter(Boolean);
  if (parts.length < 2) return false;
  const sido = parts[0], places = parts.slice(1), sstem = sidoStem(sido);
  if (sidoOf(raw && raw.CNP_CD_NM) !== sido) return false;
  const title = clean(raw && raw.PAN_NM);
  if (!title) return false;
  const own = placeWords(places[places.length - 1]).filter((w) => w !== sstem);
  if (own.some((w) => title.includes(w))) return true;
  const flat = titleKey(title);
  const prefixes = [sstem, ...places.filter((p) => /[시군]$/.test(p)).map((p) => placeWords(p).pop())].filter((p) => p && p.length >= 2);
  return umdNames.some((n) => {
    const d = dongParts(n);
    return (d.full.length >= 3 && title.includes(d.full)) || (d.stem && prefixes.some((p) => flat.includes(p + d.stem)));
  });
}

/* 목록 행들 → 이 시군구의 진행 중 주택 공고(공고일 최신 순, 같은 id 는 하나). exclude 는 이미 있는 공고(마이홈) 제목 키 집합 */
function forRegion(rows, regionName, umdNames = [], exclude = new Set()) {
  const out = [], seen = new Set();
  for (const raw of rows || []) {
    const n = notice(raw);
    if (!n || seen.has(n.id) || !inRegion(raw, regionName, umdNames) || exclude.has(titleKey(n.title))) continue;
    seen.add(n.id); out.push({ ...n, _supply: { PAN_ID: clean(raw.PAN_ID), SPL_INF_TP_CD: clean(raw.SPL_INF_TP_CD), CCR_CNNT_SYS_DS_CD: clean(raw.CCR_CNNT_SYS_DS_CD), UPP_AIS_TP_CD: clean(raw.UPP_AIS_TP_CD) } });
  }
  return out.sort((a, b) => String(b.announcedAt || '').localeCompare(String(a.announcedAt || '')) || a.id.localeCompare(b.id));
}

/* 공급정보 응답(JSON 배열) → { complex, units } | null. 단지명은 중복을 빼고(2개 넘으면 '… 외 N'), 세대수는 금회공급(없으면 세대수)의 합 */
function supplyOf(json) {
  const block = Array.isArray(json) ? json.find((b) => b && Array.isArray(b.dsList01)) : null;
  if (!block || !block.dsList01.length) return null;
  const names = [], seen = new Set(); let units = 0, any = false;
  for (const r of block.dsList01) {
    const name = clean(r && r.SBD_LGO_NM);
    if (name && !seen.has(name)) { seen.add(name); names.push(name); }
    const n = Number(clean(r && (r.NOW_HSH_CNT || r.HSH_CNT)).replace(/,/g, ''));
    if (Number.isInteger(n) && n > 0) { units += n; any = true; }
  }
  if (!names.length && !any) return null;
  return { complex: names.length ? (names.length > 2 ? `${names.slice(0, 2).join(', ')} 외 ${names.length - 2}` : names.join(', ')) : null, units: any ? units : null };
}

/* LH 한 쪽 조회(목록·공급정보 공통). 응답은 JSON 배열이고 resHeader[0].SS_CODE 가 'Y' 면 정상이다.
   일시 오류(연결·5xx·빈 본문·JSON 아님)는 점점 길게 기다려 다시, 초당 한도는 쉬었다 다시, 하루 한도(HTTP 429·XML LIMITED_NUMBER…)는 e.quota. 오류 문구에 요청 주소(키 포함)를 담지 않는다 */
async function fetchLh({ doFetch, sleep, url, params, attempts = 3 }) {
  const q = new URLSearchParams(params);
  let last = '응답 없음', throttled = false;
  for (let attempt = 0; attempt < attempts; attempt++) {
    if (attempt) await sleep(throttled ? 1100 * attempt : 400 * attempt);
    throttled = false;
    let r;
    try { r = await doFetch(`${url}?${q}`, { signal: AbortSignal.timeout(FETCH_TIMEOUT_MS), headers: { Accept: 'application/json' } }); } catch (e) { last = 'network'; continue; }
    const text = r.ok || r.status === 429 ? await r.text() : '';
    if (/REQUESTS_PER_SECOND/i.test(text)) { last = '초당 호출 한도'; throttled = true; continue; }
    if (r.status === 429 || isQuotaError(text)) { const e = new Error('quota'); e.quota = true; throw e; }
    if (!r.ok) { last = `HTTP ${r.status}`; if (r.status >= 500) continue; throw new Error(last); }
    if (!String(text).trim()) { last = '빈 본문'; continue; }
    let json; try { json = JSON.parse(text); } catch (e) { last = 'JSON 아님'; continue; }
    const head = Array.isArray(json) ? (json.find((b) => b && Array.isArray(b.resHeader)) || {}).resHeader : null;
    if (!head || !head[0]) { last = '응답 모양 이상'; continue; }
    if (clean(head[0].SS_CODE) !== 'Y') throw new Error(`SS_CODE ${clean(head[0].SS_CODE) || '없음'}`);
    return json;
  }
  const e = new Error(last); if (throttled) e.throttled = true;
  throw e;
}
/* 목록 응답 → { rows, total } */
function listOf(json) {
  const block = Array.isArray(json) ? json.find((b) => b && Array.isArray(b.dsList)) : null, rows = block ? block.dsList : [];
  return { rows, total: rows.length ? Number(clean(rows[0].ALL_CNT)) || rows.length : 0 };
}

module.exports = { LIST_URL, SUPPLY_URL, STATUSES, KIND_OF, HOSTS, dateOf, safeUrl, notice, titleKey, placeWords, dongParts, sidoOf, sidoStem, inRegion, forRegion, supplyOf, fetchLh, listOf };
