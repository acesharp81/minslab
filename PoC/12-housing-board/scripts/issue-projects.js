#!/usr/bin/env node
/* 사업 id 발급 도구: 건축HUB 인허가 사업과 지역 번들 단지를 사업 레지스트리(registry/projects.json)에 발급·갱신한다.
   node scripts/issue-projects.js --bjd 4145010800 [--bjd …] [--region incheon-gyeyang …] [--link-pnu] [--dry-run]

   --bjd <법정동 10자리>   그 법정동의 건축HUB 인허가 사업(/api/v1/permits 와 같은 결과: 번지 단위, 건물대장 보강)을 발급한다. 필지가 연결된 사업은 pnus 를, 블록 단위 허가는 위치 없이 bjdCodes 만 갖는다.
   --region <slug>         지역 번들(regions/<slug>/projects.json)의 단지를 발급한다. 번들 단지에는 PNU 가 없어 --link-pnu 로 단지 윤곽 중심의 필지(연속지적도)와 법정동(읍면동 경계)을 V-World 에서 찾아 채운다.
   --link-pnu              (번들 단지) 위치 연결. 필지를 못 찾으면 법정동만, 그것도 못 찾으면 비워 둔다(화면은 위치 미연결로 연다).
   --dry-run               레지스트리를 쓰지 않고 무엇이 발급·갱신·합병될지만 보인다.
   같은 사업은 같은 id 를 받는다(외부 참조가 하나라도 겹치면 같은 사업, lib/projects.js). 키는 .env.local(DATA_GO_KR_KEY…, V-World 개발키)을 쓴다. 키 값은 출력하지 않는다.
   저장소의 registry/projects.json 을 고친 뒤에는 커밋하고 배포해야 운영(resolve·permits)에 반영된다. */
'use strict';
const fs = require('fs');
const path = require('path');
const { loadEnv } = require('./dev.js');
const P = require('../lib/projects.js');
const { readRegistry, writeRegistry, DEFAULT_FILE } = require('../lib/registry.js');
const { vworldCreds, VWORLD_URL, redactVworld } = require('../lib/vworld.js');

const ROOT = path.resolve(__dirname, '..');

function parseArgs(argv) {
  const a = { bjd: [], region: [], linkPnu: false, dryRun: false, file: DEFAULT_FILE };
  for (let i = 0; i < argv.length; i++) {
    const t = argv[i];
    if (t === '--bjd') a.bjd.push(String(argv[++i] || ''));
    else if (t === '--region') a.region.push(String(argv[++i] || ''));
    else if (t === '--file') a.file = path.resolve(String(argv[++i] || ''));
    else if (t === '--link-pnu') a.linkPnu = true;
    else if (t === '--dry-run') a.dryRun = true;
    else throw new Error(`알 수 없는 인자: ${t}`);
  }
  for (const b of a.bjd) if (!/^\d{10}$/.test(b)) throw new Error(`--bjd 는 법정동 10자리여야 합니다: ${b}`);
  for (const r of a.region) if (!/^[a-z0-9-]{1,40}$/.test(r)) throw new Error(`--region 은 지역 slug 여야 합니다: ${r}`);
  if (!a.bjd.length && !a.region.length) throw new Error('--bjd 또는 --region 이 필요합니다');
  return a;
}

/* V-World 점 질의: 그 점을 품은 필지(PNU)·읍면동(emd_cd 8자리). 못 찾으면 null, 일시 오류는 던진다 */
async function vworldAt(env, layer, lon, lat, doFetch = fetch) {
  const { key, domain } = vworldCreds(env);
  if (!key) throw new Error('VWORLD_KEY/VWORLD_DEV_KEY 가 없음');
  const q = new URLSearchParams({ service: 'data', request: 'GetFeature', data: layer, key, domain, format: 'json', size: '2', crs: 'EPSG:4326', geomFilter: `POINT(${lon} ${lat})`, geometry: 'false' });
  const r = await doFetch(`${VWORLD_URL}?${q}`, { signal: AbortSignal.timeout(15000), headers: { Accept: 'application/json' } });
  if (!r.ok) throw new Error(`V-World HTTP ${r.status}`);
  const res = (await r.json()).response, st = res && res.status;
  if (st === 'NOT_FOUND') return null;
  if (st !== 'OK') throw new Error(`V-World ${(res && res.error && res.error.code) || st || '응답 형식'}`);
  const f = (((res.result || {}).featureCollection || {}).features || [])[0];
  return (f && f.properties) || null;
}

/* 번들 단지 윤곽 중심의 필지·법정동으로 위치를 채운 후보를 돌려준다(못 찾으면 그대로) */
async function linkBundleCandidate(env, cand, project, log, doFetch) {
  const c = P.ringCentroid(project.outline && project.outline.poly);
  if (!c) return cand;
  try {
    const parcel = await vworldAt(env, 'LP_PA_CBND_BUBUN', c[0], c[1], doFetch);
    const pnu = parcel && /^\d{19}$/.test(String(parcel.pnu)) ? String(parcel.pnu) : null;
    if (pnu) return { ...cand, pnus: [pnu], bjdCodes: [pnu.slice(0, 10)] };
    const emd = await vworldAt(env, 'LT_C_ADEMD_INFO', c[0], c[1], doFetch);
    const e8 = emd && /^\d{8}$/.test(String(emd.emd_cd)) ? String(emd.emd_cd) : null;
    if (e8) { log(`  ${project.id}: 필지는 못 찾고 법정동만(${e8}00)`); return { ...cand, bjdCodes: [`${e8}00`] }; }
    log(`  ${project.id}: 필지·법정동 모두 못 찾음`);
  } catch (e) { log(`  ${project.id}: 위치 연결 실패 — ${redactVworld(e.message, env).slice(0, 80)}`); }
  return cand;
}

async function main(argv, io = {}) {
  const log = io.log || console.log, args = parseArgs(argv);
  const env = io.env || Object.assign({}, loadEnv(path.join(ROOT, '.env.local')), process.env);
  const cur = readRegistry(args.file);
  if (cur.invalid) throw new Error(`레지스트리가 일관성 검사를 통과하지 못해 중단합니다:\n  ${cur.invalid.slice(0, 8).join('\n  ')}`);
  const asOf = new Date().toISOString().slice(0, 10), candidates = [];

  for (const bjd of args.bjd) {
    const svc = (io.createService || require('../handlers/v1/permits.js').createService)({ env });
    const out = await svc.getPermits(bjd);
    const { candidates: cs, noRef, unlocated } = P.fromPermitsBody(out.body, { asOf });
    log(`${bjd}: 사업 ${cs.length}건(위치 연결 ${cs.filter((c) => c.pnus.length).length}, 블록 단위·위치 미연결 ${cs.filter((c) => !c.pnus.length).length})${noRef ? ` · 관리번호가 없어 제외 ${noRef}` : ''}${unlocated ? ` · 필지를 못 찾아 목록에서 빠진 ${unlocated}` : ''}${out.cacheable ? '' : ' · ⚠ 일시 오류로 일부만 받음(다시 실행하면 채워짐)'}`);
    candidates.push(...cs);
  }
  for (const slug of args.region) {
    const dir = path.join(ROOT, 'regions', slug);
    const region = JSON.parse(fs.readFileSync(path.join(dir, 'region.json'), 'utf8')), projects = JSON.parse(fs.readFileSync(path.join(dir, 'projects.json'), 'utf8')).projects || [];
    let n = 0;
    for (const p of projects) {
      let c = P.fromBundleProject(p, region, { asOf });
      if (!c) { log(`  ${p.id}: 번들 단지를 사업으로 바꾸지 못함(시군구 코드 없음)`); continue; }
      if (args.linkPnu) c = await linkBundleCandidate(env, c, p, log, io.fetch);
      candidates.push(c); n++;
    }
    log(`${slug}: 번들 단지 ${n}건${args.linkPnu ? `(위치 연결 ${candidates.slice(-n).filter((c) => c.pnus.length).length}, 법정동만 ${candidates.slice(-n).filter((c) => !c.pnus.length && c.bjdCodes.length).length})` : ''}`);
  }

  const r = P.issue(cur.registry, candidates);
  const errs = P.validateRegistry(r.registry);
  if (errs.length) throw new Error(`발급 결과가 일관성 검사를 통과하지 못해 쓰지 않습니다:\n  ${errs.slice(0, 8).join('\n  ')}`);
  log(`발급 ${r.issued.length} · 갱신 ${r.updated.length} · 합병 ${r.merged.length} · 건너뜀 ${r.skipped.length} → 전체 ${r.registry.projects.length}건(폐기 ${r.registry.projects.filter((p) => p.supersededBy).length})`);
  for (const m of r.merged) log(`  합병 ${m.from} → ${m.into}`);
  for (const s of r.skipped.slice(0, 10)) log(`  건너뜀: ${s}`);
  if (args.dryRun) { log('--dry-run: 레지스트리를 쓰지 않았습니다'); return r; }
  writeRegistry(r.registry, args.file);
  log(`${path.relative(ROOT, args.file)} 에 썼습니다. 커밋·배포해야 운영에 반영됩니다.`);
  return r;
}

if (require.main === module) main(process.argv.slice(2)).catch((e) => { console.error(`오류: ${e.message}`); process.exit(1); });
module.exports = { parseArgs, vworldAt, linkBundleCandidate, main };
