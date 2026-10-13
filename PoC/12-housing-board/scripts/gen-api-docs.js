#!/usr/bin/env node
/* schemas/api/openapi.json(원본) → docs/data-interface/API-정의서.md(사람이 읽는 정의서)를 만든다. 예제는 tests/fixtures/api 의 실제 운영 응답(긴 배열·좌표는 줄임).
   사용: node scripts/gen-api-docs.js          (파일을 새로 씀)
         node scripts/gen-api-docs.js --check  (파일이 최신이 아니면 1 로 끝남: tests/js/contract.test.cjs 가 같은 함수를 부른다) */
'use strict';
const fs = require('fs');
const path = require('path');

const ROOT = path.join(__dirname, '..');
const DOC = JSON.parse(fs.readFileSync(path.join(ROOT, 'schemas/api/openapi.json'), 'utf8'));
const OUT = path.join(ROOT, 'docs/data-interface/API-정의서.md');
const fixture = (f) => JSON.parse(fs.readFileSync(path.join(ROOT, 'tests/fixtures/api', f), 'utf8'));
const S = DOC.components.schemas;
const NO_EXPAND = new Set(['Geometry', 'Position', 'Bbox', 'Coverage', 'Problem', 'PartialDate']);

const refName = (s) => (s && s.$ref ? s.$ref.replace('#/components/schemas/', '') : null);
const esc = (t) => String(t == null ? '' : t).replace(/\|/g, '\\|').replace(/\n/g, ' ');
const unnull = (s) => (s && s.oneOf && s.oneOf.length === 2 && s.oneOf.some((x) => x.type === 'null') ? { nullable: true, schema: s.oneOf.find((x) => x.type !== 'null'), description: s.description } : { nullable: false, schema: s });

/* 형식 문구: 이름 있는 스키마는 이름, 목록은 X[], 열거는 a·b·c, 패턴·날짜는 괄호 */
function typeLabel(sch) {
  const { nullable, schema } = unnull(sch), n = refName(schema);
  let t;
  if (n) t = n;
  else if (schema.const !== undefined) t = `\`${JSON.stringify(schema.const)}\``;
  else if (schema.enum) t = schema.enum.map((v) => `\`${v}\``).join(' · ');
  else if (schema.oneOf) t = schema.oneOf.map(typeLabel).join(' | ');
  else if (schema.type === 'array') t = `${schema.items ? typeLabel(schema.items) : 'any'}[]`;
  else if (Array.isArray(schema.type)) t = schema.type.join(' | ');
  else t = schema.type || '값';
  if (schema.format) t += `(${schema.format})`;
  else if (schema.pattern && !n && schema.type === 'string') t += ` \`${schema.pattern.length > 28 ? schema.pattern.slice(0, 26) + '…' : schema.pattern}\``;
  if (typeof schema.minimum === 'number' || typeof schema.maximum === 'number') t += ` ${schema.minimum != null ? schema.minimum : ''}~${schema.maximum != null ? schema.maximum : ''}`;
  return nullable ? `${t} | null` : t;
}
/* 항목 표 행(객체 항목을 깊이 3까지 펼침) */
function fieldRows(schema, prefix = '', depth = 0, rows = []) {
  const { schema: sch0 } = unnull(schema), n = refName(sch0);
  const sch = n ? S[n] : sch0;
  if (!sch) return rows;
  const target = sch.type === 'array' && sch.items ? (refName(unnull(sch.items).schema) ? S[refName(unnull(sch.items).schema)] : unnull(sch.items).schema) : sch;
  const arr = sch.type === 'array' ? '[]' : '';
  if (!target || !target.properties || (n && NO_EXPAND.has(n)) || depth > 2) return rows;
  const req = new Set(target.required || []);
  for (const [k, v] of Object.entries(target.properties)) {
    const u = unnull(v), vn = refName(u.schema), vs = vn ? S[vn] : u.schema;
    const desc = v.description || u.description || (vn && S[vn] && S[vn].description) || (vs && vs.description) || '';
    rows.push({ path: `${prefix}${k}`, type: typeLabel(v), required: req.has(k), desc });
    if (vs && (vs.type === 'object' || (vs.type === 'array' && vs.items)) && !(vn && NO_EXPAND.has(vn))) fieldRows(v, `${prefix}${k}${vs.type === 'array' ? '[]' : ''}.`, depth + 1, rows);
  }
  void arr;
  return rows;
}
const table = (rows) => ['| 항목 | 형식 | 필수 | 설명 |', '|---|---|---|---|', ...rows.map((r) => `| \`${r.path}\` | ${esc(r.type)} | ${r.required ? '●' : ''} | ${esc(r.desc)} |`)].join('\n');

/* 예제: 실제 응답에서 긴 배열·좌표를 줄인다 */
function shrink(v, key) {
  if (Array.isArray(v)) { if (key === 'coordinates') return ['…']; const head = v.slice(0, key === 'features' || key === 'items' ? 1 : 2).map((x) => shrink(x)); return v.length > head.length ? [...head, '…'] : head; }
  if (v && typeof v === 'object') return Object.fromEntries(Object.entries(v).map(([k, x]) => [k, shrink(x, k)]));
  return v;
}
const example = (f) => '```json\n' + JSON.stringify(shrink(fixture(f)), null, 2).replace(/"…"/g, '"…"') + '\n```';

const OPS = [
  { path: '/api/v1/resolve', ex: [['법정동(번들 없음, 이웃 법정동 목록 포함)', 'resolve-bjd.json'], ['필지(PNU)', 'resolve-pnu.json'], ['사업 id(필지로 열림)', 'resolve-project.json'], ['사업 id(번들 단지: 필지로 열리고 `project.block` 이 번들 단지를 가리킴)', 'resolve-project-bundle.json'], ['번들이 있는 법정동', 'resolve-bundle.json'], ['구만 있는 시(경계를 구에서 합침)', 'resolve-sgg-districts.json']], schema: 'ResolveResponse',
    notes: ['`code` 는 자릿수로 종류를 판별하고(`PRJ-` 접두는 사업 id), `sgg`·`bjd`·`pnu`·`project` 는 종류가 맞아야 한다(`type-mismatch`). 정확히 하나만 쓴다.', '**사업 id**(`PRJ-{시군구5}-{일련4}`)는 사업 레지스트리(`registry/projects.json`)에서 찾아 그 사업의 첫 필지 → 첫 법정동 → 시군구 순으로 열고, 응답의 `type` 은 `project`, `canonical` 은 사업 id, `project` 에 사업 정보가 붙는다. 필지가 없으면 `project-unlocated`, 합병되어 폐기된 id 는 남은 사업으로 열고 `project-superseded`. 레지스트리에 없으면 404 `unknown-project`.', '`geometry` 기본값: 시군구는 생략(커서), 법정동·필지는 포함. 화면은 항상 `geometry=1`.', '**구가 있는 시**(수원·청주·포항·창원·고양·용인·천안·전주·화성 …)는 V-World 시군구 경계에 구만 있어 구 경계를 합쳐 시 경계로 돌려주고 `warnings` 에 `districts-merged` 를 적는다.', '필지가 연속지적도에 없으면 법정동 경계로 후퇴하고 `parcel-not-found`.'] },
  { path: '/api/v1/codes/search', ex: [['이름', 'search-name.json'], ['지번 주소(PNU)', 'search-jibun.json'], ['장소 이름(near)', 'search-place.json'], ['틀린 코드', 'search-code-bad.json']], schema: 'SearchResponse',
    notes: ['후보의 `kind` 가 화면이 여는 매개변수이다: `sgg` → `?sgg=`, `bjd` → `?bjd=`, `pnu` → `?pnu=`. `road`·`place` 후보는 `point` 로 `at=경도,위도,17.5` 를 함께 붙인다.', '`tier` 는 열리는 방식이다(`bundle`·`req`·`edge`, 위 3등급).', '`near` 가 있으면 장소 이름 중 가까운 것을 앞에 둔다(화면은 지금 보는 지도 가운데를 5 km 격자로 맞춰 보낸다).', '행정표준코드와 V-World 중 한쪽만 실패하면 나머지 후보를 주고 `meta.partial` 에 적는다(이때 응답은 `s-maxage=60`).'] },
  { path: '/api/v1/notices', ex: [['하남시(임대·분양 공고)', 'notices-hanam.json'], ['LH 공고가 더해지는 시군구(아산시, `source: "lh"`)', 'notices-asan.json'], ['공고가 없는 시군구(종로구)', 'notices-none.json']], schema: 'NoticesResponse',
    notes: ['공고는 대부분 매입임대·일반매각(개별 주택)이다. 건설 중인 단지(`permits`)와 합치지 않고 화면의 별도 목록으로 보인다. `pnu` 가 있으면 화면이 그 필지로 이동할 수 있다.', '구가 있는 시는 시 코드로 물으면 구 공고를 모두 돌려주고, 구 코드로 물으면 그 구만.', '링크(`url`)는 마이홈·LH 주소만 싣는다.'] },
  { path: '/api/v1/buildings', ex: [['칸 하나(건물은 앞 몇 개만)', 'buildings-cell.json']], schema: 'BuildingsResponse',
    notes: ['건물은 중심점이 있는 칸에만 속한다(이웃 칸과 겹치지 않음). 속성 이름은 번들 `buildings.json` 과 같다.', '칸당 V-World 를 최대 5쪽(1,000동씩) 부르고 넘으면 `meta.truncated`.'] },
  { path: '/api/v1/permits', ex: [['법정동(덕풍동)', 'permits-deokpung.json'], ['공공주택지구(감일동, 건물대장 보강)', 'permits-gamil-ledger.json']], schema: 'PermitsResponse',
    notes: ['후보 규칙: 공동주택 + 총세대수 > 0, 번지(PNU) 단위로 모음. 상태는 인허가로 아는 3가지(`계획`·`건설 단계`·`입주 단계`).', '공공주택지구 블록 단위 허가(필지 번호 없음)는 건축물대장 총괄표제부의 세대수 + 대지면적으로 위치를 정하고 `via: "ledger"` 를 붙인다. 못 정한 것은 `meta.blockList`.', '예정일은 연·월만 있는 값(`YYYY-MM`)이 올 수 있다(`PartialDate`).'] },
  { path: '/api/v1/infra', ex: [['법정동(TAGO 정류소)', 'infra-deokpung.json'], ['서울(서울특별시 정류소정보조회)', 'infra-seoul.json'], ['서울시 조회가 안 될 때(OpenStreetMap 으로 물러남)', 'infra-seoul-osm.json'], ['정류장을 못 받은 경우(OSM 서버도 실패)', 'infra-seoul-nobus.json']], schema: 'InfraResponse',
    notes: ['서버는 임의 좌표를 받지 않고 그 법정동의 인허가 필지 중심만 쓴다(키를 쓰는 열린 중계가 되지 않게). 인허가가 없으면 비어 있다.', '정류장은 TAGO 가 우선이고, 서울은 서울특별시 정류소정보조회(`meta.stopsSource: "seoul"`, 하루 1,000건 한도라 단지 중심 300 m 간격 최대 12곳만 부른다), TAGO·서울시에 자료가 없거나 서울시 조회가 실패하면 OpenStreetMap(`meta.stopsSource: "osm"`, ODbL 출처 표시)으로 보조한다.', '`meta.schoolsError`·`meta.stopsError` 가 있으면 일부만 준 것이며 응답은 `s-maxage=60`.'] },
  { path: '/api/v1/terrain', ex: [], schema: 'PNG(terrarium, 원자료 그대로)',
    notes: ['지도 지형 타일(terrain·hillshade, maxzoom 14)을 미국 동부 S3 대신 이 서버(icn1)와 CDN 에서 받게 한다. 한 번 받은 타일은 CDN 이 1년 보관한다.', '열린 중계가 되지 않게 한국 범위(경도 124~132°, 위도 33~39.5°)에 걸치는 z 0~14 타일만 받는다. 인증키는 쓰지 않는다(그래서 503 이 없다).', 'PNG 응답이라 JSON 예제는 없다. 원천 404 는 404(하루 CDN 캐시)로 돌려준다.'] },
  { path: '/api/bus', ex: [['인천 계양구(앞 3대)', 'bus-gyeyang.json']], schema: 'BusResponse', notes: ['어느 노선을 부를지는 요청이 정하지 못한다(번들의 live 노선만). 오류 모양이 RFC 7807 이 아니라 `{ "error": "<코드>" }` 이다(옛 경로 유지).'] },
];

function build() {
  const L = [];
  const push = (...a) => L.push(...a);
  push('# 주택파동 지도 API 정의서 (v1)', '',
    '> **이 문서는 `schemas/api/openapi.json`(OpenAPI 3.1)에서 `node scripts/gen-api-docs.js` 로 만들어집니다. 직접 고치지 마세요.** 서버·화면 사이의 계약이며, `tests/js/contract.test.cjs`가 운영에서 받은 실제 응답(`tests/fixtures/api/`)이 이 계약을 지키는지, 핸들러가 문서에 적은 오류를 같은 모양으로 내는지, 문서의 매개변수가 코드와 같은지 매번 확인합니다.', '');
  push('## 1. 개요', '', DOC.info.description, '');
  push('### 1.1 세 가지 열기 방식(`tier`)', '', '| 등급 | `tier` | 조건 | 지도에 나오는 것 |', '|---|---|---|---|',
    '| A | `bundle` | `regions/<slug>` 번들이 있는 시군구 | 번들의 단지·동 윤곽·점검·버스(사람이 만든 정밀 자료) |',
    '| B | `req` | 번들 없는 **법정동·필지** | 경계 + 건물(칸 단위 요청) + 인허가 사업(건물대장 보강) + 기반시설(학교·정류장) |',
    '| C | `edge` | 번들 없는 **시군구** | 경계 + 건물(요청 시). 사업·기반시설은 법정동을 골라야 나옴 |', '');
  push('### 1.2 공통 규칙', '',
    '| 항목 | 규칙 |', '|---|---|',
    '| 서버 | ' + DOC.servers.map((s) => `${s.description}: \`${s.url}\``).join(' · ') + ' |',
    '| 메서드 | `GET`(`HEAD` 허용). 그 밖은 405 + `Allow` |',
    '| 쿼리 | **문서에 있는 이름만**. 모르는 이름·중복은 400 `invalid-query`(값을 바꿔 가며 CDN 캐시를 비켜 가는 호출 차단) |',
    '| 오류 | `application/problem+json`(RFC 7807): `type`=`/problems/<code>`, `title`, `status`, `code`, `detail` (+ `reason`·`retryAfterSec`·`suggestions`). `/api/bus` 만 옛 `{ "error" }` |',
    '| 보안 | 오류 문구·응답에 인증키·원천 URL·원천 오류 문구를 싣지 않는다. 서버는 임의 좌표·임의 주소를 받아 대신 부르지 않는다(열린 중계 금지) |',
    '| 캐시 | 서버 로컬 캐시 24시간(상한) + CDN. 일시 오류·일부 실패는 짧게만(`s-maxage=60`), 429·5xx 는 `no-store` |',
    '| 한도 | 인증키 한도(`keys-exhausted` 429, `Retry-After`)와 이 서버의 시간당 호출 상한(`budget-exhausted` 429). **초당 호출 한도는 하루 소진이 아니다**: 쉬었다 다시 부르고 키를 하루 쉬게 하지 않는다 |', '');
  const codes = S.Problem.properties.code.enum;
  const statusOf = {};
  for (const item of Object.values(DOC.paths)) for (const [st, r] of Object.entries(item.get.responses)) { const d = r.description || ''; for (const c of codes) if (new RegExp(`(^|[^-a-z])${c}([^-a-z]|$)`).test(d) || (r.content && r.content['application/problem+json'] && d.includes(c))) (statusOf[c] = statusOf[c] || new Set()).add(st); }
  push('### 1.3 오류 코드', '', '| `code` | HTTP | 쓰이는 곳 |', '|---|---|---|');
  const where = { 'invalid-query': '쿼리 이름·개수·길이·형식', 'invalid-code': '코드 형식·종류 불일치', 'invalid-cell': '건물 칸 번호가 한국 범위 밖', 'out-of-range': '지형 타일이 한국 범위 밖이거나 z 15 이상(terrain)', 'not-found': '원천에 지형 타일이 없음(terrain)', 'unsupported-level': '시도 단위(resolve)', 'unknown-code': '표준코드 표에 없음(resolve, suggestions)', 'unknown-project': '발급되지 않은 사업 id(resolve, project)', method: 'GET·HEAD 외', 'keys-exhausted': '인증키 한도(Retry-After)', 'budget-exhausted': '이 서버의 시간당 호출 상한(Retry-After)', 'not-configured': '인증키 없음', upstream: '원천 서비스 오류' };
  const http = { 'invalid-query': '400', 'invalid-code': '400', 'invalid-cell': '400', 'out-of-range': '400', 'not-found': '404', 'unsupported-level': '422', 'unknown-code': '404', 'unknown-project': '404', method: '405', 'keys-exhausted': '429', 'budget-exhausted': '429', 'not-configured': '503', upstream: '502' };
  for (const c of codes) push(`| \`${c}\` | ${http[c]} | ${where[c]} |`);
  push('');
  OPS.forEach((o, i) => {
    const op = DOC.paths[o.path].get;
    push(`## ${i + 2}. \`GET ${o.path}\` — ${op.summary}`, '', op.description, '', `- operationId: \`${op.operationId}\``, '');
    push('### 매개변수', '', '| 이름 | 필수 | 형식 | 설명 |', '|---|---|---|---|');
    for (const p of op.parameters) { const sc = p.schema; const f = sc.enum ? sc.enum.join(' · ') : [sc.type, sc.pattern ? `\`${sc.pattern}\`` : '', sc.minLength != null ? `${sc.minLength}~${sc.maxLength}자` : '', sc.minimum != null ? `${sc.minimum}~${sc.maximum}` : ''].filter(Boolean).join(' '); push(`| \`${p.name}\` | ${p.required ? '●' : ''} | ${esc(f)} | ${esc(p.description)} |`); }
    push('', '### 응답 `200`', '', `\`${op.responses['200'].content ? Object.keys(op.responses['200'].content)[0] : ''}\` · \`Cache-Control: ${op.responses['200'].headers['Cache-Control'].description}\` · 스키마 \`${o.schema}\``, '', op.responses['200'].description, '', table(fieldRows({ $ref: `#/components/schemas/${o.schema}` })), '');
    if (o.notes.length) push('### 동작', '', ...o.notes.map((n) => `- ${n}`), '');
    push('### 오류', '', '| HTTP | `code` | 설명 |', '|---|---|---|');
    const byStatus = { 404: 'unknown-code', 405: 'method', 422: 'unsupported-level', 502: 'upstream', 503: 'not-configured' };
    for (const [st, r] of Object.entries(op.responses)) {
      if (st === '200') continue;
      let cs;
      if (r.content && r.content['application/json']) cs = S.BusError.properties.error.enum.filter((e) => (r.description || '').includes(e) || (byStatus[st] || '') === e).slice(0, 1).concat(st === '400' ? ['query'] : []).filter((e, i, a) => a.indexOf(e) === i).map((c) => `\`${c}\``);
      else { cs = codes.filter((c) => (r.description || '').includes(c)).map((c) => `\`${c}\``); if (!cs.length && (byStatus[st] || st === '400' || st === '429')) cs = [`\`${byStatus[st] || (st === '400' ? 'invalid-query' : 'keys-exhausted')}\``]; }
      push(`| ${st} | ${cs.join(' · ')} | ${esc(r.description)} |`);
    }
    push('', '### 예제', '');
    for (const [label, f] of o.ex) push(`**${label}** (\`tests/fixtures/api/${f}\`)`, '', example(f), '');
  });
  push(`## ${OPS.length + 2}. 공통 스키마`, '');
  for (const n of ['Problem', 'Position', 'Bbox', 'Geometry', 'Tier', 'Coverage', 'PartialDate']) { const s = S[n]; push(`### \`${n}\``, '', s.description || '', '', s.properties ? table(fieldRows({ $ref: `#/components/schemas/${n}` }).length ? fieldRows({ $ref: `#/components/schemas/${n}` }) : Object.entries(s.properties).map(([k, v]) => ({ path: k, type: typeLabel(v), required: (s.required || []).includes(k), desc: v.description || '' }))) : '`' + JSON.stringify(s) + '`', ''); }
  push(`## ${OPS.length + 3}. 화면(클라이언트) 계약`, '',
    '| 항목 | 규칙 | 구현·시험 |', '|---|---|---|',
    '| 주소 매개변수 | `?pnu=` > `?bjd=` > `?sgg=` > `?code=` 중 앞선 하나가 `?region=` 보다 우선. 보던 상태(`mode`·`panel`·`ring` …)는 이동해도 남고 `region`·`block`·`at` 은 지운다 | `assets/js/region.js` `codeQuery`·`codeUrl`, README 표 |',
    '| 열기 순서 | `resolve`(geometry=1) → coverage `A` 면 번들, 아니면 빈 번들 + `permits` → 단지가 있으면 `infra`(15초까지만 기다리고 못 받으면 점검 없이 열며 자료 안내에 이유) | `region.js` `boot`·`emptyBundle` |',
    '| 어댑터 | `permits` → 번들 단지 모양(`permitsToProjects`: 윤곽=필지, `sponsorClass:"unknown"`, 건물대장 근거 메모·출처), `infra` → 번들 `infra.json` 모양(`schools`·`stops`·`sources`) | `region.js`, 번들-어댑터-정의서 |',
    '| 건물 | 지도에 보이는 0.01° 칸마다 `buildings`(최대 12칸 동시 3, 60,000동 상한), 번들이 있으면 번들 밖만 | `app.js` `DYN` |',
    '| 주소 이동 입력줄 | `search` 후보 → 위 매개변수로 이동. 상태 4가지(대기 .62 · 입력 중 .88 · 이동 중 · 비활성 .46 불투명도). 404·405·503·429 는 비활성 | `assets/js/goto.js`, 스펙 2.5 |',
    '| 실패해도 | 인허가·기반시설·검색이 실패해도 경계와 건물은 열린다(자료 안내·banner 에 이유) | `region.js` |', '');
  push(`## ${OPS.length + 4}. 바꾸는 규칙`, '',
    '- **하위 호환**: 응답에 항목을 *더하는* 것은 같은 버전에서 가능(화면은 모르는 항목을 무시). 항목을 지우거나 형식·뜻을 바꾸거나 오류 코드를 바꾸면 `/api/v2` 로 올린다.',
    '- **절차**: `schemas/api/openapi.json` 수정 → `node scripts/capture-fixtures.js`(운영 응답 다시 받기, 키 풀 한도 때문에 호출 사이 1.2초) → `node scripts/gen-api-docs.js` → `node --test tests/js/contract.test.cjs`.',
    '- **전국 점검**: `node scripts/smoke.js [주소]` 가 표본 59곳(`tests/smoke/regions.json`)을 검색 → 해석 → 건물 → 인허가 → 기반시설 순으로 불러 열림·경고를 표로 보여 준다(호출 사이 0.9초).', '');
  return L.join('\n');
}

if (require.main === module) {
  const text = build();
  if (process.argv.includes('--check')) { const cur = fs.existsSync(OUT) ? fs.readFileSync(OUT, 'utf8') : ''; if (cur !== text) { console.error('docs/data-interface/API-정의서.md 가 최신이 아닙니다: node scripts/gen-api-docs.js'); process.exit(1); } console.log('API 정의서가 최신입니다'); }
  else { fs.writeFileSync(OUT, text); console.log(`씀 ${OUT} (${text.length}자)`); }
}
module.exports = { build, OUT, fieldRows, typeLabel };
