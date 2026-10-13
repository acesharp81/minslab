/* 표준코드 판별·분해 순수 함수. 기준은 행정표준코드의 법정동코드(10자리: 시도2+시군구3+읍면동3+리2).
   받는 코드: 시군구 5자리(sgg) · 법정동 10자리(bjd, V-World 8자리 emd 는 '00'을 붙임) · 필지 PNU 19자리(법정동10+대지구분1+본번4+부번4) · 사업 id(project, PRJ-{시군구5}-{일련4}, lib/projects.js).
   시도 2자리는 알아보지만 지도 대상은 아니다. 행정동은 여기서 다루지 않는다(법정동↔행정동 연계는 별도 색인).
   시험: tests/js/codes.test.cjs */
'use strict';

/* 행정표준코드 전국 표(2026-10-05)에 있는 시도 코드 */
const KNOWN_SIDO = new Set(['11', '12', '26', '27', '28', '30', '31', '36', '41', '43', '44', '47', '48', '50', '51', '52']);

/* 숫자만 남긴다(공백·하이픈 허용). 숫자가 아닌 글자가 있으면 null */
function clean(input) {
  const s = String(input == null ? '' : input).trim().replace(/[\s-]/g, '');
  return /^\d+$/.test(s) ? s : null;
}

/* PNU → 구성 요소와 건축HUB 인자. 대지구분 1=일반(HUB platGbCd 0), 2=산(HUB platGbCd 1). 본번 0000 은 필지가 아니다 */
function parsePnu(pnu) {
  const s = clean(pnu);
  if (!s || s.length !== 19) return null;
  const landType = s[10], bun = s.slice(11, 15), ji = s.slice(15, 19);
  if (!['1', '2'].includes(landType) || bun === '0000') return null;
  return {
    pnu: s, bjd: s.slice(0, 10), landType, bun, ji,
    jibun: `${Number(bun)}${Number(ji) ? `-${Number(ji)}` : ''}`,
    hub: { sigunguCd: s.slice(0, 5), bjdongCd: s.slice(5, 10), platGbCd: landType === '1' ? '0' : '1', bun, ji },
  };
}

function bjdParts(bjd) {
  return { sido: bjd.slice(0, 2), sgg: bjd.slice(0, 5), umd: bjd.slice(5, 8), ri: bjd.slice(8, 10), vworldEmd8: bjd.slice(0, 8), hubBjdongCd: bjd.slice(5, 10) };
}

/* 입력 → { ok, type: 'sido'|'sgg'|'bjd'|'pnu'|'project', canonical, input, sido, sgg, bjd?, pnu?, project?, padded? } 또는 { ok:false, reason, detail } */
function classify(input) {
  const raw = String(input == null ? '' : input).trim();
  if (!raw) return { ok: false, reason: 'empty', detail: '코드가 비어 있습니다' };
  if (/^PRJ/i.test(raw)) {                                   // 사업 id: 발급 시점의 시군구가 들어 있어(현재 시군구와 다를 수 있음) 시도만 확인한다
    const m = /^PRJ-(\d{5})-(\d{4})$/i.exec(raw);
    if (!m) return { ok: false, reason: 'bad-project', detail: '사업 id 는 PRJ-{시군구5}-{일련4} 형식입니다(예 PRJ-41450-0001)' };
    if (!KNOWN_SIDO.has(m[1].slice(0, 2))) return { ok: false, reason: 'unknown-sido', detail: `알 수 없는 시도 코드 ${m[1].slice(0, 2)}` };
    if (m[2] === '0000') return { ok: false, reason: 'bad-project', detail: '사업 id 의 일련은 0001 부터입니다' };
    const canonical = `PRJ-${m[1]}-${m[2]}`;
    return { ok: true, type: 'project', canonical, input: raw, sido: m[1].slice(0, 2), sgg: m[1], project: canonical };
  }
  const s = clean(raw);
  if (!s) return { ok: false, reason: 'not-digits', detail: '코드는 숫자만 쓸 수 있습니다(공백·하이픈은 무시)' };
  const sido = s.slice(0, 2);
  if (!KNOWN_SIDO.has(sido)) return { ok: false, reason: 'unknown-sido', detail: `알 수 없는 시도 코드 ${sido}` };
  const base = { ok: true, input: raw, sido };
  if (s.length === 2) return { ...base, type: 'sido', canonical: s };
  if (s.length === 5) return { ...base, type: 'sgg', canonical: s, sgg: s };
  if (s.length === 8 || s.length === 10) {
    const bjd = s.length === 8 ? `${s}00` : s, p = bjdParts(bjd);
    if (p.umd === '000' && p.ri === '00') return { ...base, type: 'sgg', canonical: p.sgg, sgg: p.sgg, padded: s.length === 8 };   // 시군구 행(…00000)
    return { ...base, type: 'bjd', canonical: bjd, sgg: p.sgg, bjd, padded: s.length === 8 };
  }
  if (s.length === 19) {
    const p = parsePnu(s);
    if (!p) return { ok: false, reason: 'bad-pnu', detail: 'PNU 형식이 맞지 않습니다(대지구분은 1·2, 본번은 0000이 아니어야 함)' };
    return { ...base, type: 'pnu', canonical: s, sgg: p.bjd.slice(0, 5), bjd: p.bjd, pnu: s };
  }
  return { ok: false, reason: 'bad-length', detail: `자릿수 ${s.length}는 지원하지 않습니다(시군구 5·법정동 8 또는 10·PNU 19)` };
}

/* 행정표준코드 API 행 → 수준 */
function levelOf(row) {
  if (row.sgg_cd === '000') return 'sido';
  if (row.umd_cd === '000') return 'sgg';
  return row.ri_cd === '00' ? 'umd' : 'ri';
}
const findRow = (rows, regionCd) => (rows || []).find((r) => r && r.region_cd === regionCd) || null;
function nameParts(locataddNm) {
  const [sido, a, b, c] = String(locataddNm || '').split(' ');
  return { sido: sido || '', rest: [a, b, c].filter(Boolean) };
}

module.exports = { KNOWN_SIDO, clean, parsePnu, bjdParts, classify, levelOf, findRow, nameParts };
