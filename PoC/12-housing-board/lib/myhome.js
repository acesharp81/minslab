/* 마이홈포털 공공주택 모집공고(HWSPR02: 임대 rsdtRcritNtcList · 분양 ltRsdtRcritNtcList) 변환·시군구 거르기. 순수 함수(네트워크·키 없음).
   원천은 전국 현재 공고 목록(2026-10-05: 임대 244 + 분양 80)이고 시군구 필터가 없어 전체를 받아 이름으로 거른다.
   공고는 대부분 매입임대·일반매각(개별 주택)이라 건설 중인 단지(인허가 사업)와는 다른 층이다 → 사업과 합치지 않고 '모집 공고' 목록으로 따로 보인다.
   시험: tests/js/myhome.test.cjs */
'use strict';

const KINDS = { rental: '임대', sale: '분양' };
const HOSTS = ['https://www.myhome.go.kr/', 'https://m.myhome.go.kr/', 'https://apply.lh.or.kr/'];   // 링크는 이 주소로 시작하는 것만(원천 응답을 그대로 믿고 내보내지 않는다)

const clean = (v) => (v == null ? '' : String(v).replace(/\s+/g, ' ').trim());
/* '20261002' → '2026-10-02'. 달력에 없는 날짜는 null */
function dateOf(v) {
  const s = clean(v);
  if (!/^\d{8}$/.test(s)) return null;
  const iso = `${s.slice(0, 4)}-${s.slice(4, 6)}-${s.slice(6, 8)}`, t = new Date(`${iso}T00:00:00Z`);
  return !Number.isNaN(t.getTime()) && t.toISOString().slice(0, 10) === iso ? iso : null;
}
const intOf = (v) => { const n = Number(clean(v).replace(/,/g, '')); return Number.isInteger(n) && n > 0 ? n : null; };
const safeUrl = (u) => { const s = clean(u); return HOSTS.some((h) => s.startsWith(h)) ? s : ''; };

/* 원천 한 행 → 화면에 보일 공고 한 건. 제목·주소가 없으면 null */
function notice(raw, kind) {
  if (!raw || !KINDS[kind]) return null;
  const title = clean(raw.pblancNm), address = clean(raw.fullAdres);
  if (!title) return null;
  const pnu = /^\d{19}$/.test(clean(raw.pnu)) ? clean(raw.pnu) : null;
  return {
    id: `${kind}-${clean(raw.pblancId)}${raw.houseSn ? `-${raw.houseSn}` : ''}`, kind, title,
    agency: clean(raw.suplyInsttNm) || null, status: clean(raw.sttusNm) || null, housingType: clean(raw.houseTyNm) || null, supplyType: clean(raw.suplyTyNm) || null,
    complex: clean(raw.hsmpNm) || null, units: intOf(raw.suplyHoCo) || intOf(raw.sumSuplyCo) || null, address: address || null, pnu,
    announcedAt: dateOf(raw.rcritPblancDe), applyFrom: dateOf(raw.beginDe), applyTo: dateOf(raw.endDe), url: safeUrl(raw.pcUrl) || safeUrl(raw.url) || null, source: 'myhome',
  };
}
/* 시군구 전체 이름('경기도 하남시')에 속한 공고인가: 주소가 그 이름으로 시작하거나, 시도·시군구 필드가 맞는다.
   구가 있는 시('경기도 수원시 영통구')는 주소 앞부분이, 시 전체('경기도 수원시')는 구를 가리지 않고 시까지만 맞으면 된다 */
function inRegion(raw, regionName) {
  const name = clean(regionName);
  if (!name) return false;
  const addr = clean(raw && raw.fullAdres), pair = `${clean(raw && raw.brtcNm)} ${clean(raw && raw.signguNm)}`.trim();
  return addr === name || addr.startsWith(`${name} `) || pair === name || pair.startsWith(`${name} `);
}
/* 임대·분양 원천 행 → 이 시군구의 공고(공고일 최신 순, 같은 id 는 하나) */
function forRegion(rental, sale, regionName) {
  const out = [], seen = new Set();
  for (const [kind, list] of [['rental', rental], ['sale', sale]]) for (const raw of list || []) {
    if (!inRegion(raw, regionName)) continue;
    const n = notice(raw, kind);
    if (n && !seen.has(n.id)) { seen.add(n.id); out.push(n); }
  }
  return out.sort((a, b) => String(b.announcedAt || '').localeCompare(String(a.announcedAt || '')) || a.id.localeCompare(b.id));
}

module.exports = { KINDS, HOSTS, dateOf, intOf, safeUrl, notice, inRegion, forRegion };
