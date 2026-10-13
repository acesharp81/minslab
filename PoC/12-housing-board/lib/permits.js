/* 건축HUB 주택인허가 기본개요(getHpBasisOulnInfo) → 번지(PNU) 단위 사업 후보. 요청 시 조회(/api/v1/permits)가 쓴다.
   tools/regiontools/build_region.py 의 규칙을 JS 로 옮겼다(make_pnu · ymd · is_candidate_record · permit_events · short_label)
   + tools/regiontools/status.py 의 상태 규칙 중 인허가로 알 수 있는 3가지(계획 · 건설 단계 · 입주 단계).
   - 건축HUB 는 허가 '이벤트' 단위라 한 사업·필지에 기록이 여럿(변경허가·분할)이다 → PNU 로 모은다(레코드 단위 판정은 약 46% 오탐, 정의서).
   - 후보: 공동주택 + 총세대수 > 0 (번들 빌드의 is_candidate_record 와 같음). 이름 없는 소규모 허가는 사업으로 보지 않는다.
   - 공공주택지구 허가는 필지가 아니라 블록 단위(platGbCd 2, block 'B1BL')라 PNU 를 만들 수 없다. blocks 로 모아 목록만 알리고 지도에는 올리지 않는다(블록 레이어에 이름이 없어 자동으로 위치를 맞출 수 없음).
   - 분양중·준공 임박은 공고·공정율이 필요해 인허가만으로는 정하지 않는다.
   - '계획'은 착공·사용검사 기록이 원천에 없다는 뜻이다(건축인허가에도 없고 건축물대장은 키 권한이 없어 보강 못 함). 예정일(착공예정일·사용검사예정일, 'YYYYMM'·'YYYY' 부분 날짜 포함)이 지났는데 기록이 없으면 overdue 로 사실만 덧붙인다.
   시험: tests/js/permits.test.cjs (Python 구현에서 뽑은 기준값과 맞춤) */
'use strict';
const { toPosInt } = require('./buildings.js');

const GENERIC_WORDS = ['신축공사', '주택건설사업', '건설공사'];

/* 시군구5 + 법정동5 + 대지구분1(일반 1, 산 2) + 본번4 + 부번4. HUB platGbCd 0=대지, 1=산, 2=블록(→ null). 본번 0 은 null */
function makePnu(sigungu, bjdong, bun, ji, platGb = '0') {
  const land = { 0: '1', 1: '2' }[String(platGb == null ? '0' : platGb).trim()];
  if (!land) return null;
  const bt = String(bun == null ? '' : bun).trim(), jt = String(ji == null ? '0' : ji).trim();
  if (!/^\d+$/.test(bt) || !/^\d*$/.test(jt)) return null;
  const b = Number.parseInt(bt, 10), j = jt === '' ? 0 : Number.parseInt(jt, 10);
  if (b <= 0) return null;
  return `${String(sigungu).trim()}${String(bjdong).trim()}${land}${String(b).padStart(4, '0')}${String(j).padStart(4, '0')}`;
}
const recordPnu = (r) => makePnu(r.sigunguCd || '', r.bjdongCd || '', r.bun, r.ji, r.platGbCd);

/* 'YYYYMMDD' → 'YYYY-MM-DD'. 달력에 없는 날짜·형식 위반은 null */
function ymd(s) {
  const t = String(s == null ? '' : s).trim();
  if (!/^\d{8}$/.test(t)) return null;
  const y = +t.slice(0, 4), m = +t.slice(4, 6), d = +t.slice(6, 8), dt = new Date(Date.UTC(y, m - 1, d));
  return dt.getUTCFullYear() === y && dt.getUTCMonth() === m - 1 && dt.getUTCDate() === d ? `${t.slice(0, 4)}-${t.slice(4, 6)}-${t.slice(6, 8)}` : null;
}

/* 예정일은 'YYYYMMDD'·'YYYYMM'(2004년 7월)·'YYYY'로 섞여 온다. {iso, end}: iso 는 적힌 정밀도 그대로('YYYY-MM-DD'·'YYYY-MM'·'YYYY'),
   end 는 그 기간의 마지막 날('YYYY-MM-DD', 경과 판정용). 알 수 없으면 null */
function ymdLoose(s) {
  const t = String(s == null ? '' : s).trim();
  if (/^\d{8}$/.test(t)) { const d = ymd(t); return d ? { iso: d, end: d } : null; }
  if (/^\d{6}$/.test(t)) {
    const y = +t.slice(0, 4), m = +t.slice(4, 6);
    if (y < 1900 || y > 2100 || m < 1 || m > 12) return null;
    return { iso: `${t.slice(0, 4)}-${t.slice(4, 6)}`, end: new Date(Date.UTC(y, m, 0)).toISOString().slice(0, 10) };
  }
  if (/^\d{4}$/.test(t)) { const y = +t; return y >= 1900 && y <= 2100 ? { iso: t, end: `${t}-12-31` } : null; }
  return null;
}
const monthsBetween = (fromIso, now) => {   // fromIso(마지막 날) 이후 지난 달 수(내림)
  const [y, m, d] = fromIso.split('-').map(Number), t = new Date(now);
  let n = (t.getUTCFullYear() - y) * 12 + (t.getUTCMonth() + 1 - m);
  if (t.getUTCDate() < d) n -= 1;
  return Math.max(n, 0);
};

const isCandidate = (r) => !!toPosInt(r.totHhldCnt) && String(r.purpsCdNm || '').includes('공동주택');

/* 지도용 짧은 이름: '신축공사' 등을 빼고 8자 이내(끝의 'N차'·'N단지'는 살림) */
function shortLabel(name, maxlen = 8) {
  let s = String(name == null ? '' : name);
  for (const w of GENERIC_WORDS.slice().sort((a, b) => b.length - a.length)) s = s.split(w).join('');
  s = s.replace(/\s+/g, ' ').trim().replace(/\s*아파트$/, '').trim();
  if (s.length <= maxlen) return s;
  const m = /(\s*)(\d+)\s*(차|단지)$/.exec(s);
  if (m) {
    const sep = m[1] ? ' ' : '', base = s.slice(0, m.index).trim(), tokens = base.split(' ').filter(Boolean), t0 = tokens.length ? tokens : [base];
    const full = m[2] + m[3], short = m[2] + (m[3] === '차' ? '차' : '');
    for (const cand of [base.replace(/ /g, '') + sep + full, t0[0] + sep + full, t0[0] + sep + short]) if (cand.length <= maxlen) return cand;
    return t0[0].slice(0, Math.max(maxlen - sep.length - short.length, 1)) + sep + short;
  }
  const first = s.split(' ')[0];
  return first.length <= maxlen ? first : s.replace(/ /g, '').slice(0, maxlen);
}

/* ---------- 사건·상태 ---------- */
const day = (iso) => { const [y, m, d] = iso.split('-').map(Number); return Date.UTC(y, m - 1, d); };
const todayOf = (now) => { const d = new Date(now); return Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate()); };

/* 기록 하나 → 사건 [{type, date, value?, ref, suspect?}]. 실제 날짜가 오늘보다 미래이거나 기록 안 날짜 순서가 모순이면 suspect */
function permitEvents(rec, now = Date.now()) {
  const ref = String(rec.mgmHsrgstPk == null ? '' : rec.mgmHsrgstPk).trim() || null;
  const apprv = ymd(rec.apprvDay), stcns = ymd(rec.stcnsDay), insp = ymd(rec.useInsptDay);
  const evs = [];
  if (apprv) evs.push({ type: 'permit_approved', date: apprv, value: toPosInt(rec.totHhldCnt), ref });
  if (stcns) evs.push({ type: 'construction_start', date: stcns, ref });
  if (insp) evs.push({ type: 'completion_inspection', date: insp, ref });
  const t = todayOf(now), bad = new Set();
  if (apprv && stcns && apprv > stcns) { bad.add('permit_approved'); bad.add('construction_start'); }
  if (stcns && insp && stcns > insp) { bad.add('construction_start'); bad.add('completion_inspection'); }
  if (apprv && insp && apprv > insp) { bad.add('permit_approved'); bad.add('completion_inspection'); }
  return evs.map((e) => { const s = day(e.date) > t || bad.has(e.type); return s ? { ...e, suspect: true } : e; });
}
/* 인허가 사건만으로 정하는 상태: 실제 준공검사 → 입주 단계, 실제 착공 → 건설 단계, 그 밖 → 계획. suspect 는 쓰지 않는다 */
function statusOf(events, now = Date.now()) {
  const t = todayOf(now), ev = events.filter((e) => !e.suspect && e.date);
  const actual = (type) => ev.some((e) => e.type === type && day(e.date) <= t);
  if (actual('completion_inspection')) return '입주 단계';
  if (actual('construction_start')) return '건설 단계';
  return '계획';
}

/* ---------- 번지 단위로 모으기 ---------- */
const STATUS_RANK = { '건설 단계': 0, '계획': 1, '입주 단계': 2 };
const maxBy = (arr, f) => arr.reduce((b, x) => (b === undefined || f(x) > f(b) ? x : b), undefined);

/* HUB 기록 목록 → 사업 후보(번지 단위). 정렬: 건설 단계 → 계획 → 입주 단계, 세대수 큰 순. 반환 항목에는 필지 경계가 아직 없다 */
function aggregate(records, now = Date.now()) {
  const groups = new Map(), skipped = { notCandidate: 0, noPnu: 0 }, blockRecs = new Map();
  for (const r of records || []) {
    if (!isCandidate(r)) { skipped.notCandidate++; continue; }
    const pnu = recordPnu(r);
    if (!pnu) {
      skipped.noPnu++;
      // 공공주택지구는 허가가 필지가 아니라 블록 단위(platGbCd 2, 주소 '○○동 블록', block 'B1BL')라 PNU 가 없다 → 위치를 정할 수 없지만 목록으로는 알린다
      if (String(r.platGbCd == null ? '' : r.platGbCd).trim() === '2') { const k = String(r.block || r.bldNm || '').replace(/[\s-]/g, '').toUpperCase(); (blockRecs.get(k) || blockRecs.set(k, []).get(k)).push(r); }
      continue;
    }
    (groups.get(pnu) || groups.set(pnu, []).get(pnu)).push(r);
  }
  const out = [];
  for (const [pnu, recs] of groups) {
    const events = recs.flatMap((r) => permitEvents(r, now));
    const named = recs.filter((r) => String(r.bldNm || '').trim());
    const latestNamed = maxBy(named, (r) => ymd(r.apprvDay) || '') || recs[0];
    const withUnits = recs.map((r) => [ymd(r.apprvDay) || '', toPosInt(r.totHhldCnt)]).filter((v) => v[1]);
    const units = withUnits.length ? withUnits.reduce((b, v) => (v[0] > b[0] || (v[0] === b[0] && v[1] > b[1]) ? v : b))[1] : null;
    const jibun = `${Number(pnu.slice(11, 15))}${Number(pnu.slice(15, 19)) ? `-${Number(pnu.slice(15, 19))}` : ''}`;
    const status = statusOf(events, now);
    const valid = (type) => events.filter((e) => e.type === type && !e.suspect).map((e) => e.date).sort();
    const latestLoose = (field) => recs.map((r) => ymdLoose(r[field])).filter(Boolean).sort((a, b) => (a.end < b.end ? -1 : a.end > b.end ? 1 : 0)).pop() || null;
    const plannedDone = latestLoose('useInsptSchedDay'), plannedStartL = latestLoose('stcnsSchedDay'), today = new Date(now).toISOString().slice(0, 10);
    // 예정일이 지났는데 실제 기록이 없으면 사실만 덧붙인다(지연이라고 판정하지는 않는다): 계획인데 착공 예정일 경과 / 건설 단계인데 사용검사 예정일 경과
    const late = status === '계획' && plannedStartL && plannedStartL.end < today ? ['착공', plannedStartL] : status === '건설 단계' && plannedDone && plannedDone.end < today ? ['준공', plannedDone] : null;
    const name = String(latestNamed.bldNm || '').trim();
    out.push({
      pnu, jibun, name: name || `${jibun}번지`, label: shortLabel(name) || `${jibun}번지`, units, status,
      mainBldCnt: toPosInt(maxBy(recs, (r) => toPosInt(r.mainBldCnt) || 0).mainBldCnt),
      approvedAt: valid('permit_approved').pop() || null, startedAt: valid('construction_start')[0] || null, completedAt: valid('completion_inspection').pop() || null,
      plannedStart: status === '계획' && plannedStartL ? plannedStartL.iso : null, plannedCompletion: status === '입주 단계' || !plannedDone ? null : plannedDone.iso,
      overdue: late ? { kind: late[0], plannedAt: late[1].iso, months: monthsBetween(late[1].end, now) } : null,
      address: String(latestNamed.platPlc || '').trim() || null, refs: [...new Set(events.map((e) => e.ref).filter(Boolean))], records: recs.length,
      latestRef: String((maxBy(recs, (r) => ymd(r.apprvDay) || '') || recs[0]).mgmHsrgstPk == null ? '' : (maxBy(recs, (r) => ymd(r.apprvDay) || '') || recs[0]).mgmHsrgstPk).trim() || null,
    });
  }
  const blocks = [];
  for (const recs of blockRecs.values()) {
    const latest = maxBy(recs, (r) => ymd(r.apprvDay) || ''), events = recs.flatMap((r) => permitEvents(r, now));
    blocks.push({ name: String(latest.bldNm || '').trim() || String(latest.block || '').trim(), block: String(latest.block || '').trim() || null, units: toPosInt(maxBy(recs, (r) => toPosInt(r.totHhldCnt) || 0).totHhldCnt),
      status: statusOf(events, now), approvedAt: ymd(latest.apprvDay), records: recs.length, latestRef: String(latest.mgmHsrgstPk == null ? '' : latest.mgmHsrgstPk).trim() || null,
      startedAt: events.filter((e) => e.type === 'construction_start' && !e.suspect).map((e) => e.date).sort()[0] || null, completedAt: events.filter((e) => e.type === 'completion_inspection' && !e.suspect).map((e) => e.date).sort().pop() || null });
  }
  blocks.sort((a, b) => (STATUS_RANK[a.status] - STATUS_RANK[b.status]) || ((b.units || 0) - (a.units || 0)) || a.name.localeCompare(b.name));
  out.sort((a, b) => (STATUS_RANK[a.status] - STATUS_RANK[b.status]) || ((b.units || 0) - (a.units || 0)) || a.pnu.localeCompare(b.pnu));
  return { projects: out, blocks, skipped };
}

/* ---------- 건물대장(건축HUB 건축물대장정보 총괄표제부 getBrRecapTitleInfo)으로 보강 ----------
   쓰임 1) 블록 단위 허가(필지 번호 없음)의 위치: 준공된 단지는 대장에 '○○동 ○○번지'가 있다. 허가의 총세대수와 대지면적(주택인허가 대지위치 getHpPlatPlcInfo 의 platArea 합)이
   대장의 hhldCnt·platArea 와 같으면 그 지번이 그 블록이다. 하남 블록 허가 23건 중 16건이 면적 오차 0.0~0.2% 로 맞았다. 세대수만 같은 우연(교산 A8↔망월동 904번지, 면적 29.6% 차이)은 면적으로 걸러진다.
   쓰임 2) 준공 뒤 합필·분할로 허가 때 지번이 사라진 사업의 현재 지번(장위동 144-24 → 322번지 등).
   쓰임 3) 사용승인일: 허가보다 늦은 사용승인일이 같은 지번 대장에 있으면 준공으로 본다(옛 건물의 사용승인일은 허가보다 앞서 걸러진다).
   모호하면(후보가 둘이고 면적 차이가 비슷) 채택하지 않는다. 시험: tests/js/permits.test.cjs */
const LEDGER_AREA_TOL = 0.02;       // 대지면적 상대 오차 허용(2%)
const LEDGER_MARGIN = 0.003;        // 1등과 2등의 오차 차이가 이보다 작으면 모호(0.3%p)
const normName = (s) => String(s == null ? '' : s).replace(/[\s\-.·()]/g, '').replace(/아파트|공동주택|신축공사|주택건설사업|건설공사/g, '').toUpperCase();
const GENERIC_NAME = /^(LH|엘에이치|한국토지주택공사)?$|^(LH)?(공공주택|행복주택|신혼희망타운)?$|BL$|블[록럭]$/i;
const isGenericName = (s) => { const n = normName(s); return n.length < 2 || GENERIC_NAME.test(n); };

/* 총괄표제부 행 → 필요한 필드만. 지번(PNU)·세대수·대지면적·사용승인일(ISO). 쓸 수 없으면 null */
function ledgerRow(r) {
  const pnu = makePnu(r.sigunguCd, r.bjdongCd, r.bun, r.ji, r.platGbCd);
  if (!pnu) return null;
  const units = toPosInt(r.hhldCnt), area = Number(r.platArea);
  return { pnu, bjd: `${String(r.sigunguCd).trim()}${String(r.bjdongCd).trim()}`, name: String(r.bldNm == null ? '' : r.bldNm).trim(), units: units || 0, platArea: Number.isFinite(area) && area > 0 ? area : 0,
    useAprDay: ymd(r.useAprDay), platPlc: String(r.platPlc == null ? '' : r.platPlc).trim(), purps: String(r.mainPurpsCdNm == null ? '' : r.mainPurpsCdNm).trim() };
}

/* 사업/블록 item({units, platArea, name}) 에 맞는 대장 행을 찾는다. { row, diff } | { ambiguous: [...] } | null.
   조건: 세대수 같음 + 대지면적 오차 ≤ 2%(둘 다 알 때만; 면적으로 못 맞추면 — 허가 쪽 면적이 없거나 어긋나면 — 세대수·이름이 같은 하나일 때만, diff null·by 'name'). 후보가 여럿이면 가장 가까운 것이 다음보다 0.3%p 이상 가까워야 하고, 아니면 이름이 같은 하나로 가린다 */
function matchLedger(item, rows) {
  if (!item || !item.units) return null;
  const nameLike = (rowName, n) => { const m = normName(rowName); return !!m && (m === n || (n.length >= 4 && (m.includes(n) || n.includes(m)))); };
  const byName = () => {                                        // 면적으로 못 맞출 때(허가에 대지위치가 없거나 일부 필지뿐): 세대수가 같고 구별되는 이름이 같은 대장이 딱 하나일 때만
    if (isGenericName(item.name)) return null;
    const n = normName(item.name), same = (rows || []).filter((r) => r.units === item.units && nameLike(r.name, n));
    return same.length === 1 ? { row: same[0], diff: null, by: 'name' } : same.length ? { ambiguous: same.slice(0, 4) } : null;
  };
  if (!(item.platArea > 0)) return byName();
  const cands = [];
  for (const r of rows || []) {
    if (r.units !== item.units || !(r.platArea > 0)) continue;
    const diff = Math.abs(r.platArea - item.platArea) / item.platArea;
    if (diff <= LEDGER_AREA_TOL) cands.push({ row: r, diff });
  }
  if (!cands.length) return byName();
  cands.sort((a, b) => a.diff - b.diff);
  if (cands.length === 1 || cands[1].diff - cands[0].diff >= LEDGER_MARGIN) return cands[0];
  const n = normName(item.name), same = !isGenericName(item.name) ? cands.filter((c) => nameLike(c.row.name, n)) : [];
  return same.length === 1 ? same[0] : { ambiguous: cands.slice(0, 4) };
}
/* 같은 지번 대장의 사용승인일이 허가일 이후이고 오늘 이전이면 그 날짜(ISO). 아니면 null(옛 건물·미래 날짜는 쓰지 않음) */
function ledgerCompletion(row, approvedAt, now = Date.now()) {
  if (!row || !row.useAprDay) return null;
  const t = new Date(now).toISOString().slice(0, 10);
  return row.useAprDay <= t && (!approvedAt || row.useAprDay >= approvedAt) ? row.useAprDay : null;
}

/* 필지(연속지적도)를 못 찾은 사업의 추정 원인. 5개 법정동 81개 번지 중 9개를 확인해 정리한 규칙(스펙 4.1):
   준공 뒤 합필·분할로 허가 때 지번이 사라짐 · 택지개발지구(산 지번·BL 블록)는 지적이 아직 안 나뉨 · 15년 넘은 허가 · 그 밖 */
function unlocatedReason(p, now = Date.now()) {
  if (p.status === '입주 단계') return '준공 뒤 합필·분할로 지번이 없어졌을 수 있음';
  if (p.pnu && p.pnu[10] === '2' || /\bBL\b|블록/.test(p.name || '')) return '택지개발지구 등 지적이 아직 나뉘지 않은 곳일 수 있음';
  const y = p.approvedAt ? Number(p.approvedAt.slice(0, 4)) : null;
  if (y && new Date(now).getUTCFullYear() - y >= 15) return '15년 넘은 허가라 지번이 바뀌었을 수 있음';
  return '연속지적도에 없음(원인 미상)';
}

module.exports = { LEDGER_AREA_TOL, LEDGER_MARGIN, normName, isGenericName, ledgerRow, matchLedger, ledgerCompletion, unlocatedReason, makePnu, recordPnu, ymd, ymdLoose, monthsBetween, isCandidate, shortLabel, permitEvents, statusOf, aggregate };
