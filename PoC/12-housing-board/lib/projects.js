/* 사업 레코드·사업 id 발급·사업↔PNU 연결(스펙 9.1, 기획서 결정 5). 순수 함수만 둔다(네트워크·파일 없음). 파일 읽기는 lib/registry.js, 발급 절차는 scripts/issue-projects.js.

   사업 id: `PRJ-{시군구5}-{일련4}`(예 PRJ-41450-0003). 발급형 내부 id 이고, 건축HUB 관리번호 같은 외부 키는 id 로 쓰지 않고 refs 로만 보관한다.
   - 시군구는 발급 시점의 값이고 이후 행정구역이 바뀌어도 id 는 그대로다(현재 시군구는 레코드의 sgg 가 정본). 일련은 시군구 안에서 0001 부터 쓰고 한 번 쓴 번호는 다시 쓰지 않는다(counters).
   - 같은 사업을 다시 만나면(다음 발급 때) 같은 id 를 돌려준다: 레코드가 가진 외부 참조(refs) 가운데 하나라도 같으면 같은 사업이다. 건축HUB 는 변경허가마다 새 관리번호를 내므로 refs 는 합집합으로 쌓여 신원이 이어진다.
   - 후보가 서로 다른 두 사업과 refs 를 공유하면 둘을 합친다: 일련이 작은 쪽이 남고 나머지는 supersededBy 로 승계를 남긴다(폐기된 id 도 그대로 열린다). 분할은 자동으로 알아낼 수 없어 하지 않는다(사람이 registry 를 고친다).
   - 사업은 번지(PNU) 단위로 모은 것이다. 위치(사업↔PNU)는 pnus 로, 걸친 법정동은 bjdCodes 로 둔다. 위치를 못 찾았으면 pnus 가 비고 화면은 "위치 미연결"(법정동 경계)로 연다.
   - 6단계(stageCode)는 9.2 의 제안 매핑을 쓴다: 계획 → 03 인허가(사업승인 기록 없으면 02 사업화) · 건설 단계·준공 임박 → 04 건설 · 분양중 → 05 공급 · 입주 단계 → 06 입주.
   시험: tests/js/projects.test.cjs · tests/js/registry.test.cjs */
'use strict';

const ID_RE = /^PRJ-(\d{5})-(\d{4})$/;
const MAX_SERIAL = 9999;
const STAGES = { '01': '정책', '02': '사업화', '03': '인허가', '04': '건설', '05': '공급', '06': '입주' };
const SCHEMA = 'project-registry/1';

const formatId = (sgg, serial) => {
  if (!/^\d{5}$/.test(String(sgg))) throw new Error(`시군구 코드가 맞지 않음: ${sgg}`);
  if (!Number.isInteger(serial) || serial < 1 || serial > MAX_SERIAL) throw new Error(`일련이 범위(1~${MAX_SERIAL})를 벗어남: ${serial}`);
  return `PRJ-${sgg}-${String(serial).padStart(4, '0')}`;
};
function parseId(id) {
  const m = ID_RE.exec(String(id == null ? '' : id).trim());
  return m ? { sgg: m[1], serial: Number(m[2]) } : null;
}

/* 현재 상태(5종 + 인허가 3종) → 6단계. 사업승인 기록이 없는 '계획'은 아직 인허가 전이라 02 */
function stageOf(status, { approvedAt } = {}) {
  switch (status) {
    case '입주 단계': return '06';
    case '분양중': return '05';
    case '건설 단계': case '준공 임박': return '04';
    case '계획': return approvedAt ? '03' : '02';
    default: return '02';
  }
}

const str = (v) => (v == null ? '' : String(v).trim());
const isPnu = (v) => /^\d{19}$/.test(str(v));
const refKey = (r) => `${r.system}|${r.key}|${r.value}`;
const uniq = (arr) => [...new Set(arr)];

/* 외부 참조 목록 정리: 값은 문자열(관리번호는 앞 0·자릿수가 섞여 숫자로 바꾸면 안 된다), 빈 값·중복 제거 */
function cleanRefs(refs) {
  const seen = new Set(), out = [];
  for (const r of refs || []) {
    if (!r || !str(r.system) || !str(r.key) || !str(r.value)) continue;
    const x = { system: str(r.system), key: str(r.key), value: str(r.value), ...(r.asOf ? { asOf: str(r.asOf) } : {}) };
    if (!seen.has(refKey(x))) { seen.add(refKey(x)); out.push(x); }
  }
  return out;
}

const HUB_SOURCE = { provider: '국토교통부', dataset: '건축HUB 주택인허가정보', url: 'https://www.data.go.kr/data/15134735/openapi.do' };

/* /api/v1/permits 의 한 사업(properties: pnu · name · units · status · approvedAt · refs · latestRef …) → 사업 레코드 후보.
   refs 는 그 번지에 모인 허가 관리번호 전부(+ 블록 단위 허가는 latestRef). 관리번호가 하나도 없으면 null(신원을 잡을 수 없다).
   bjdCodes 는 허가를 낸 법정동과 필지가 있는 법정동의 합집합이다(건물대장으로 위치를 찾은 블록 단위 허가는 필지가 다른 법정동에 있기도 하다). */
function fromPermit(p, { bjd, asOf }) {
  if (!p) return null;
  const refs = cleanRefs(uniq([...(p.refs || []), p.latestRef].map(str).filter(Boolean)).map((v) => ({ system: 'hub-hs-basis', key: 'mgmHsrgstPk', value: v, asOf })));
  if (!refs.length) return null;
  const pnu = isPnu(p.pnu) ? str(p.pnu) : null, b = /^\d{10}$/.test(str(bjd)) ? str(bjd) : pnu ? pnu.slice(0, 10) : null;
  if (!b) return null;
  return {
    sgg: b.slice(0, 5), bjdCodes: uniq([b, pnu && pnu.slice(0, 10)].filter(Boolean)).sort(), pnus: pnu ? [pnu] : [], stageCode: stageOf(p.status, { approvedAt: p.approvedAt }), source: HUB_SOURCE, asOf, refs, approvedAt: str(p.approvedAt),   // approvedAt 은 발급 순서에만 쓰고 레지스트리에는 싣지 않는다
    ...(str(p.name) ? { name: str(p.name) } : {}), ...(Number.isInteger(p.units) && p.units > 0 ? { units: p.units } : {}),
  };
}

/* 지역 번들의 단지(projects.json 한 항목) → 사업 레코드 후보. 번들 단지에는 PNU 가 없어 pnus 는 비어 있고(위치 연결은 발급 도구가 필지를 찾아 채운다) 외부 참조는 번들 자신이다 */
function fromBundleProject(p, region, { asOf }) {
  if (!p || !str(p.id) || !region || !str(region.slug)) return null;
  const sgg = ((region.codes || []).find((c) => c.type === 'sigungu') || {}).code;
  if (!/^\d{5}$/.test(str(sgg))) return null;
  return {
    sgg: str(sgg), bjdCodes: [], pnus: [], stageCode: stageOf(p.status, { approvedAt: true }), asOf,
    source: { provider: '주택파동 지도 번들', dataset: `regions/${region.slug}/projects.json` },
    refs: [{ system: 'bundle', key: str(region.slug), value: str(p.id), asOf }],
    ...(str(p.name) ? { name: str(p.name) } : {}), ...(Number.isInteger(p.units) && p.units > 0 ? { units: p.units } : {}),
  };
}


/* /api/v1/permits 응답 본문 → 사업 레코드 후보들. 지도에 그려진 사업(features)과, 위치를 못 정한 블록 단위 허가(meta.blockList: pnus 가 빈 사업)를 모두 담는다.
   관리번호가 없는 항목·필지도 못 찾은 사업(meta.unlocatedList 는 관리번호를 싣지 않음)은 신원을 잡을 수 없어 빠진다 → skipped 로 센다 */
function fromPermitsBody(body, { asOf } = {}) {
  const out = [], bjd = body && body.bjd;
  let noRef = 0;
  for (const f of (body && body.features) || []) { const c = fromPermit(f.properties, { bjd, asOf }); if (c) out.push(c); else noRef++; }
  for (const b of (body && body.meta && body.meta.blockList) || []) {
    const c = fromPermit({ pnu: null, name: b.name, units: b.units, status: b.status, approvedAt: b.approvedAt, latestRef: b.latestRef, refs: [] }, { bjd, asOf });
    if (c) out.push(c); else noRef++;
  }
  return { candidates: out, noRef, unlocated: (body && body.meta && body.meta.unlocated) || 0 };
}

/* 닫힌 링(또는 열린 링) [[경도, 위도], …] 의 꼭짓점 평균 [경도, 위도]. 점이 3개 미만이면 null */
function ringCentroid(ring) {
  const pts = (ring || []).filter((p) => Array.isArray(p) && Number.isFinite(p[0]) && Number.isFinite(p[1]));
  const open = pts.length > 1 && pts[0][0] === pts[pts.length - 1][0] && pts[0][1] === pts[pts.length - 1][1] ? pts.slice(0, -1) : pts;
  if (open.length < 3) return null;
  return [open.reduce((a, p) => a + p[0], 0) / open.length, open.reduce((a, p) => a + p[1], 0) / open.length];
}

/* ---------- 레지스트리 ---------- */
const emptyRegistry = () => ({ schema: SCHEMA, updatedAt: null, counters: {}, projects: [] });

/* 일관성 검사 → 오류 문구 배열(통과하면 []). 파일이 손으로 고쳐져도 깨진 채 배포되지 않게 시험이 부른다 */
function validateRegistry(reg) {
  const errs = [];
  if (!reg || reg.schema !== SCHEMA) return [`schema 가 ${SCHEMA} 이어야 함`];
  if (!Array.isArray(reg.projects)) return ['projects 가 배열이어야 함'];
  const byId = new Map(), active = new Map(), maxSerial = {};
  for (const p of reg.projects) {
    const at = `${p && p.id}`, parsed = parseId(p && p.id);
    if (!parsed) { errs.push(`${at}: id 형식이 PRJ-{시군구5}-{일련4} 가 아님`); continue; }
    if (byId.has(p.id)) { errs.push(`${at}: id 가 중복`); continue; }
    byId.set(p.id, p);
    maxSerial[parsed.sgg] = Math.max(maxSerial[parsed.sgg] || 0, parsed.serial);
    if (!/^\d{5}$/.test(str(p.sgg))) errs.push(`${at}: sgg 가 5자리 숫자가 아님`);
    if (!Array.isArray(p.bjdCodes) || p.bjdCodes.some((c) => !/^\d{10}$/.test(str(c)))) errs.push(`${at}: bjdCodes 는 10자리 문자열 배열`);
    if (!Array.isArray(p.pnus) || p.pnus.some((c) => !isPnu(c))) errs.push(`${at}: pnus 는 19자리 문자열 배열`);
    else if (p.pnus.some((c) => !(p.bjdCodes || []).includes(c.slice(0, 10)))) errs.push(`${at}: pnus 의 법정동이 bjdCodes 에 없음`);
    if (!STAGES[p.stageCode]) errs.push(`${at}: stageCode 가 01~06 이 아님`);
    if (!p.source || !str(p.source.provider) || !str(p.source.dataset)) errs.push(`${at}: source(provider·dataset) 가 없음`);
    if (!/^\d{4}-\d{2}-\d{2}$/.test(str(p.asOf))) errs.push(`${at}: asOf 가 YYYY-MM-DD 가 아님`);
    if (!Array.isArray(p.refs) || !p.refs.length) errs.push(`${at}: refs 가 1개 이상 필요`);
    else for (const r of p.refs) if (typeof r.value !== 'string' || !str(r.system) || !str(r.key) || !str(r.value)) errs.push(`${at}: refs 의 system·key·value 는 비어 있지 않은 문자열(값은 숫자로 바꾸지 않음)`);
    if (!/^\d{4}-\d{2}-\d{2}$/.test(str(p.issuedAt))) errs.push(`${at}: issuedAt 이 YYYY-MM-DD 가 아님`);
    if (!p.supersededBy) active.set(p.id, p);
  }
  for (const p of byId.values()) {
    if (!p.supersededBy) continue;
    let cur = p, hops = 0;
    while (cur && cur.supersededBy && hops++ < 20) cur = byId.get(cur.supersededBy);
    if (!cur) errs.push(`${p.id}: supersededBy 가 가리키는 사업이 없음`);
    else if (cur.supersededBy) errs.push(`${p.id}: supersededBy 가 돌고 있음`);
  }
  const owner = new Map();
  for (const p of active.values()) for (const r of p.refs || []) {
    const k = refKey(r);
    if (owner.has(k) && owner.get(k) !== p.id) errs.push(`${p.id}: 외부 참조 ${r.system}/${r.key}=${r.value} 가 ${owner.get(k)} 와 겹침(두 사업이 한 참조를 가질 수 없음)`);
    owner.set(k, p.id);
  }
  for (const [sgg, n] of Object.entries(maxSerial)) if ((reg.counters || {})[sgg] == null || reg.counters[sgg] < n) errs.push(`counters[${sgg}] 가 가장 큰 일련 ${n} 보다 작음(번호를 다시 쓰게 된다)`);
  return errs;
}

const serialOf = (id) => parseId(id).serial;

/* 후보 레코드들을 레지스트리에 발급·갱신·합병한다. 입력은 바꾸지 않는다. 반환: { registry, issued:[id], updated:[id], merged:[{from,into}], skipped:[이유] }
   - 발급 순서: 사업승인일이 이른 것부터, 같으면 PNU·이름 순(같은 입력이면 같은 번호가 나온다).
   - 갱신: 후보가 가진 값으로 stageCode·asOf·name·units·source 를 새로 쓰고, refs·bjdCodes·pnus 는 합집합(신원·위치가 이어지게). 후보에 pnus 가 없으면 기존 위치를 지우지 않는다. */
function issue(registry, candidates, { now = Date.now() } = {}) {
  const today = new Date(now).toISOString().slice(0, 10);
  const reg = JSON.parse(JSON.stringify(registry || emptyRegistry()));
  const issued = [], updated = [], merged = [], skipped = [];
  const activeByRef = new Map();
  const reindex = () => { activeByRef.clear(); for (const p of reg.projects) if (!p.supersededBy) for (const r of p.refs) activeByRef.set(refKey(r), p); };
  reindex();
  const maxFor = (sgg) => Math.max(Number((reg.counters || {})[sgg]) || 0, ...reg.projects.filter((p) => parseId(p.id).sgg === sgg).map((p) => serialOf(p.id)), 0);
  const ordered = (candidates || []).filter(Boolean).map((c, i) => ({ c, i })).sort((a, b) => str(a.c.approvedAt).localeCompare(str(b.c.approvedAt)) || str((a.c.pnus || [])[0]).localeCompare(str((b.c.pnus || [])[0])) || str(a.c.name).localeCompare(str(b.c.name), 'ko') || a.i - b.i);
  for (const { c } of ordered) {
    const refs = cleanRefs(c.refs);
    if (!refs.length || !/^\d{5}$/.test(str(c.sgg))) { skipped.push(`${str(c.name) || '(이름 없음)'}: 외부 참조 또는 시군구가 없어 신원을 잡을 수 없음`); continue; }
    const hits = uniq(refs.map((r) => activeByRef.get(refKey(r))).filter(Boolean));
    let target;
    if (!hits.length) {
      const serial = maxFor(c.sgg) + 1;
      if (serial > MAX_SERIAL) throw new Error(`${c.sgg} 의 일련이 ${MAX_SERIAL} 을 넘음`);
      target = { id: formatId(c.sgg, serial), sgg: c.sgg, bjdCodes: [], pnus: [], stageCode: c.stageCode, source: c.source, asOf: c.asOf, refs: [], issuedAt: today };
      reg.projects.push(target); reg.counters[c.sgg] = serial; issued.push(target.id);
    } else {
      hits.sort((a, b) => serialOf(a.id) - serialOf(b.id) || a.id.localeCompare(b.id));
      target = hits[0];
      for (const other of hits.slice(1)) {                                         // 합병: 일련이 작은 사업이 남는다
        target.refs = cleanRefs([...target.refs, ...other.refs]); target.bjdCodes = uniq([...target.bjdCodes, ...other.bjdCodes]).sort(); target.pnus = uniq([...target.pnus, ...other.pnus]).sort();
        other.supersededBy = target.id; merged.push({ from: other.id, into: target.id });
      }
      if (!updated.includes(target.id)) updated.push(target.id);
    }
    target.refs = cleanRefs([...target.refs, ...refs]);
    target.bjdCodes = uniq([...target.bjdCodes, ...(c.bjdCodes || [])]).sort();
    target.pnus = uniq([...target.pnus, ...(c.pnus || [])]).sort();
    target.stageCode = c.stageCode; target.source = c.source; target.asOf = c.asOf; target.sgg = c.sgg;
    if (str(c.name)) target.name = str(c.name);
    if (c.units) target.units = c.units;
    reindex();
  }
  reg.projects.sort((a, b) => a.id.localeCompare(b.id));
  reg.updatedAt = today;
  return { registry: reg, issued, updated: updated.filter((id) => !issued.includes(id)), merged, skipped };
}

/* ---------- 조회 ---------- */
function indexRegistry(reg) {
  const byId = new Map(), byRef = new Map(), byPnu = new Map();
  for (const p of (reg && reg.projects) || []) {
    byId.set(p.id, p);
    if (p.supersededBy) continue;
    for (const r of p.refs || []) byRef.set(refKey(r), p);
    for (const n of p.pnus || []) if (!byPnu.has(n)) byPnu.set(n, p);
  }
  return { byId, byRef, byPnu };
}
/* id → { project, followed:[거친 id] } | null. 폐기된(supersededBy) id 는 남은 사업까지 따라간다 */
function lookup(index, id) {
  let p = index.byId.get(str(id)); const followed = [];
  while (p && p.supersededBy && followed.length < 20) { followed.push(p.id); p = index.byId.get(p.supersededBy); }
  return p && !p.supersededBy ? { project: p, followed } : null;
}
/* /api/v1/permits 의 사업 properties → 사업 id | null. 외부 참조(허가 관리번호)가 우선이고, 없으면 PNU */
function projectIdFor(index, props) {
  if (!props) return null;
  for (const v of [...(props.refs || []), props.latestRef]) {
    const hit = str(v) && index.byRef.get(refKey({ system: 'hub-hs-basis', key: 'mgmHsrgstPk', value: str(v) }));
    if (hit) return hit.id;
  }
  const byPnu = isPnu(props.pnu) && index.byPnu.get(str(props.pnu));
  return byPnu ? byPnu.id : null;
}

module.exports = { ID_RE, MAX_SERIAL, STAGES, SCHEMA, HUB_SOURCE, formatId, parseId, stageOf, refKey, cleanRefs, fromPermit, fromPermitsBody, fromBundleProject, ringCentroid, emptyRegistry, validateRegistry, issue, indexRegistry, lookup, projectIdFor };
