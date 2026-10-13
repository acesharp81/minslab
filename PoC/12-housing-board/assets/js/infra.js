/* 입주 전 기반시설 점검(infra.json)의 순수 함수.
   단지 하나에 대해 교육·교통·전기 점검 줄을 만들고, 거리·년월 문구를 다듬는다. DOM 은 만지지 않는다(node --test 로 시험: tests/js/infra.test.cjs).
   자료 모양의 정본: schemas/bundle/infra.schema.json
   원칙: 공개 자료로 '있다/없다/언제'만 말한다. 건립 여부를 단정하지 않고, 도시계획시설의 집행 표기는 싣지 않는다.
   줄(row)의 ref 는 화면이 팝업 등에서 다시 쓰라고 남겨 둔 원자료(학교·통학구역·거리)다. */
(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.InfraLib = api;
})(typeof self !== 'undefined' ? self : this, function () {
  'use strict';

  const LEVEL_MARK = { warn: '▲ 주의', info: '● 참고', none: '○ 자료 없음' };
  const WARN_MONTHS = 6;          // 학교 개교가 입주보다 이만큼(개월) 이상 늦으면 '주의'
  const NEW_SCHOOL_M = 1200;      // 신설예정 학교를 '가깝다'고 보는 직선거리(m)
  const SITE_M = 600;             // 일정 미공시 학교 부지를 세는 직선거리(m)
  const STOP_M = 300;             // 정류장을 세는 직선거리(m)
  const STOP_WARN_MONTHS = 12;    // 정류장이 없을 때 '주의'로 보는 입주까지의 기간(개월). 더 먼 단지는 아직 안 생긴 것이 당연하다

  const finite = (v) => typeof v === 'number' && Number.isFinite(v);
  const centroid = (poly) => [poly.reduce((a, p) => a + p[0], 0) / poly.length, poly.reduce((a, p) => a + p[1], 0) / poly.length];
  function distM(a, b) {
    const R = 6371008.8, r = Math.PI / 180, dl = (b[1] - a[1]) * r, dn = (b[0] - a[0]) * r;
    const h = Math.sin(dl / 2) ** 2 + Math.cos(a[1] * r) * Math.cos(b[1] * r) * Math.sin(dn / 2) ** 2;
    return 2 * R * Math.asin(Math.sqrt(h));
  }
  const fmtDist = (d) => (d < 1000 ? `약 ${Math.round(d / 10) * 10} m` : `약 ${(d / 1000).toFixed(1)} km`);
  const fmtYm = (ym) => (typeof ym === 'string' && /^\d{4}-\d{2}$/.test(ym) ? ym.replace('-', '.') : '');
  const fmtDate = (d) => (typeof d === 'string' ? d.replace(/-/g, '.') : '');
  const fmtN = (n) => Number(n).toLocaleString('ko-KR');

  /* 단지의 입주(또는 준공 예정) 문구에서 'YYYY-MM'. 날짜가 없으면 null. */
  function moveInYm(text) {
    const m = /(\d{4})[.-](\d{2})/.exec(text == null ? '' : String(text));
    return m && +m[2] >= 1 && +m[2] <= 12 ? `${m[1]}-${m[2]}` : null;
  }
  function monthsBetween(a, b) {
    const pa = /^(\d{4})-(\d{2})$/.exec(a || ''), pb = /^(\d{4})-(\d{2})$/.exec(b || '');
    return pa && pb ? (+pb[1] - +pa[1]) * 12 + (+pb[2] - +pa[2]) : null;
  }
  /* '준공 예정 …' 문구(임대 단지)면 준공 시기, 그 밖에는(날짜 없음 포함) 입주 시기다. */
  const moveNoun = (block) => (/^준공/.test(String((block && block.moveIn) || '')) ? '준공' : '입주');

  /* 학교 개교 예정 년월을 단지의 입주 시기와 견준다. n = 개교가 입주보다 늦은 개월 수(음수면 앞섬). */
  function compareOpen(openYm, block) {
    const mv = moveInYm(block && block.moveIn), noun = moveNoun(block);
    if (!mv) return { n: null, level: 'info', text: `${noun} 시기 미정` };
    const n = monthsBetween(mv, openYm);
    if (n == null) return { n: null, level: 'info', text: `${noun} 시기 미정` };
    if (n === 0) return { n, level: 'info', text: `${noun === '입주' ? '입주와' : '준공과'} 같은 시기` };
    if (n < 0) return { n, level: 'info', text: `${noun}(${fmtYm(mv)})보다 ${-n}개월 앞섬` };
    return { n, level: n >= WARN_MONTHS ? 'warn' : 'info', text: `${noun}(${fmtYm(mv)})보다 ${n}개월 늦음` };
  }

  const schoolPt = (s) => [s.lon, s.lat];
  function nearest(items, pt, ptOf) {
    let best = null;
    for (const it of items || []) {
      const p = ptOf(it);
      if (!p || !finite(p[0]) || !finite(p[1])) continue;
      const d = distM(pt, p);
      if (!best || d < best.d) best = { item: it, d };
    }
    return best;
  }
  const siteCentroid = (s) => (s.poly && s.poly.length ? centroid(s.poly) : null);

  /* 개교 일정 목록: 신설예정(개교 예정이 이른 순) 다음에 일정 미공시 부지. */
  function sortSchools(schools) {
    const rank = (s) => (s.status === '신설예정' ? 0 : 1);
    return (schools || []).slice().sort((a, b) => rank(a) - rank(b) || String(a.openYm || '9999-99').localeCompare(String(b.openYm || '9999-99')) || String(a.name).localeCompare(String(b.name), 'ko'));
  }
  /* 공사 단계 문구(건축 인허가). */
  function permitStatus(p) {
    if (p.approvalDate) return '사용승인';
    if (p.startDate) return '공사 중';
    return '허가';
  }
  /* 학교 한 곳에서 가장 가까운 단지. blocks 는 화면용 단지(poly 가 있는 것). */
  function nearestBlock(blocks, pt) {
    const hit = nearest(blocks, pt, (b) => (b.poly && b.poly.length ? centroid(b.poly) : null));
    return hit ? { block: hit.item, d: hit.d } : null;
  }
  function scaleText(s) {
    const parts = [];
    if (finite(s.classes)) parts.push(`${fmtN(s.classes)}학급`);
    if (finite(s.students)) parts.push(`${fmtN(s.students)}명`);
    return parts.join('·');
  }
  const BUS_SOURCE_IDS = ['tago-bus', 'seoul-bus', 'osm-bus'];   // 정류장 출처: 국토교통부 TAGO · 서울시 정류소정보조회 · OpenStreetMap(요청 시 조회 지역)
  const busSource = (infra) => (infra.sources || []).find((s) => BUS_SOURCE_IDS.includes(s.id) || /버스정류/.test(s.label || ''));

  /* 단지 하나의 점검 줄. 줄 = { level: 'warn'|'info'|'none', label, text, detail?, generic?, ref? }
     generic = detail 이 단지와 상관없는 공통 설명(기준일·한계)이라 화면이 한 번만 보여 줘도 된다. */
  function projectChecks(block, infra, context) {
    const out = { edu: [], transit: [], power: [] };
    if (!block || !block.poly || !block.poly.length || !infra) return out;
    const c = centroid(block.poly);

    // 교육 (a) 현재 초등 통학구역
    const att = (infra.attendance || []).find((a) => a.projectId === block.pid);
    const zone = att && (infra.zones || []).find((z) => z.id === att.zoneId);
    if (zone) {
      const zd = finite(zone.schoolLon) && finite(zone.schoolLat) ? distM(c, [zone.schoolLon, zone.schoolLat]) : null;
      out.edu.push({ level: 'info', label: '통학구역', text: `${zone.school} 통학구역${zd == null ? '' : ` · 직선 ${fmtDist(zd)}`}`, detail: `${fmtDate(zone.asOf)} 기준 초등 통학구역. 신설 학교가 문을 열면 조정될 수 있음`, generic: true, ref: { zone, d: zd } });
    }
    // 교육 (b) 가까운 신설예정 학교
    // 특수학교는 배정 대상이 달라 일반 학교(유·초·중·고)가 같은 범위에 있으면 그쪽을 먼저 본다.
    const scheduled = (infra.schools || []).filter((s) => s.status === '신설예정' && s.openYm);
    const regular = scheduled.filter((s) => s.level !== '특수학교');
    const near = nearest(regular.length && nearest(regular, c, schoolPt).d <= NEW_SCHOOL_M ? regular : scheduled, c, schoolPt);
    if (near && near.d <= NEW_SCHOOL_M) {
      const s = near.item, cmp = compareOpen(s.openYm, block), sc = scaleText(s);
      out.edu.push({ level: cmp.level, label: '신설 학교', text: `${s.name} ${fmtYm(s.openYm)} 개교 예정 · ${fmtDist(near.d)}${sc ? ` (${sc} 계획)` : ''}`, detail: cmp.text, ref: { school: s, d: near.d, cmp } });
    } else {
      out.edu.push({ level: 'none', label: '신설 학교', text: `${(NEW_SCHOOL_M / 1000).toFixed(1)} km 안에 개교 예정 학교 공시 없음` });
    }
    // 교육 (c) 일정이 공시되지 않은 학교 부지
    const sites = (infra.schools || []).filter((s) => s.status === '부지만' && distM(c, schoolPt(s)) <= SITE_M);
    if (sites.length) out.edu.push({ level: 'info', label: '학교 부지', text: `개교 일정이 공시되지 않은 학교 부지 ${sites.length}곳 (${SITE_M} m 안)` });

    // 교통: 정류장(자료가 없으면 말하지 않는다) + 가까운 역
    const stops = infra.stops || [];
    if (stops.length) {
      const inside = stops.filter((s) => distM(c, [s.lon, s.lat]) <= STOP_M);
      if (!inside.length) {
        const away = infra.asOf && moveInYm(block.moveIn) ? monthsBetween(String(infra.asOf).slice(0, 7), moveInYm(block.moveIn)) : null;
        out.transit.push({ level: away != null && away <= STOP_WARN_MONTHS ? 'warn' : 'info', label: '버스정류장', text: `${STOP_M} m 안 정류장 없음`, detail: busDetail(infra), generic: true });
      } else {
        const n = nearest(inside, c, (s) => [s.lon, s.lat]);
        out.transit.push({ level: 'info', label: '버스정류장', text: `정류장 ${inside.length}곳 · 가장 가까운 ${n.item.name} ${fmtDist(n.d)}`, detail: busDetail(infra), generic: true });
      }
    }
    const st = context && context.stations && context.stations.length ? nearest(context.stations, c, (s) => [s.lon, s.lat]) : null;
    if (st) out.transit.push({ level: 'info', label: '가까운 역', text: `${st.item.name} ${fmtDist(st.d)}` });

    // 전기
    const power = (infra.sites || []).filter((s) => s.category === '전기');
    const pn = nearest(power, c, siteCentroid);
    if (pn) out.power.push({ level: 'info', label: '전기 시설', text: `전기공급설비 부지 ${fmtDist(pn.d)} (지구 안 ${power.length}곳)`, detail: '수전 가능 여부는 한전 협의 사항이라 공개 자료가 없음', generic: true });
    else out.power.push({ level: 'none', label: '전기 시설', text: '전기공급설비 부지 자료 없음' });
    return out;
  }
  function busDetail(infra) {
    const s = busSource(infra), d = s && s.asOf ? ` ${fmtDate(s.asOf)} 기준` : '';
    const name = s && s.id !== 'tago-bus' && s.label ? s.label : '국토교통부 TAGO 버스정류소 정보';
    return `${name}${d} — 입주 때 새로 생기는 정류장은 아직 반영되지 않았을 수 있음`;
  }

  /* ---------- 시각화용: 이름 줄이기, 격차 문구, 종류별 신호, 요약, 연결선, 타임라인 ---------- */
  const GROUP_NAMES = { edu: '교육', transit: '교통', power: '전기' };
  const LEVEL_RANK = { none: 0, info: 1, warn: 2 };
  const shortName = (name) => String(name == null ? '' : name).replace(/^\s*\(가칭\)\s*/, '').trim();
  /* 개교가 입주(또는 준공)보다 얼마나 늦은지를 지도 글자로. cmp 는 compareOpen 의 결과. */
  function gapText(cmp, noun) {
    if (!cmp || cmp.n == null) return `${noun} 시기 미정`;
    if (cmp.n === 0) return `${noun === '입주' ? '입주와' : '준공과'} 같은 시기 개교`;
    return cmp.n > 0 ? `${noun} 후 ${cmp.n}개월 뒤 개교` : `${noun} ${-cmp.n}개월 전 개교`;
  }
  /* 단지 하나의 종류별 대표 신호: 줄 가운데 가장 높은 단계. 줄이 없는 종류는 null. */
  function categoryLevels(checks) {
    const out = {};
    for (const g of Object.keys(GROUP_NAMES)) {
      const rows = (checks && checks[g]) || [];
      out[g] = rows.length ? rows.reduce((a, r) => (LEVEL_RANK[r.level] > LEVEL_RANK[a] ? r.level : a), 'none') : null;
    }
    return out;
  }
  /* 모든 단지의 (단지 × 종류) 칸을 세어 한 줄 요약. headline 은 사이드바 맨 위 한 줄. */
  function summarize(blocks, infra, context) {
    const byCat = {};
    Object.keys(GROUP_NAMES).forEach((g) => { byCat[g] = { warn: 0, info: 0, none: 0 }; });
    const empty = { warn: 0, info: 0, none: 0, byCat, blocks: [], headline: '' };
    if (!infra) return empty;
    const list = (blocks || []).map((b) => {
      const levels = categoryLevels(projectChecks(b, infra, context));
      let warn = 0;
      Object.keys(levels).forEach((g) => { if (levels[g]) { byCat[g][levels[g]]++; if (levels[g] === 'warn') warn++; } });
      return { pid: b.pid, id: b.id, levels, warn };
    });
    const tot = { warn: 0, info: 0, none: 0 };
    Object.values(byCat).forEach((c) => { tot.warn += c.warn; tot.info += c.info; tot.none += c.none; });
    const parts = Object.keys(GROUP_NAMES).filter((g) => byCat[g].warn).map((g) => `${GROUP_NAMES[g]} ${byCat[g].warn}`);
    return { ...tot, byCat, blocks: list, headline: list.length ? (tot.warn ? `주의 ${tot.warn}건 (${parts.join(' · ')})` : '주의할 항목 없음') : '' };
  }
  /* 지도에 그릴 연결선. new = 단지 → 가장 가까운 신설예정 학교(격차 라벨), zone = 단지 → 배정 통학구역의 학교. */
  function connectors(blocks, infra, context) {
    const out = [];
    if (!infra) return out;
    for (const b of blocks || []) {
      if (!b || !b.poly || !b.poly.length) continue;
      const ck = projectChecks(b, infra, context), from = centroid(b.poly);
      const ns = ck.edu.find((r) => r.ref && r.ref.school);
      if (ns) {
        const s = ns.ref.school;
        out.push({ kind: 'new', pid: b.pid, id: b.id, schoolId: s.id, from, to: [s.lon, s.lat], d: ns.ref.d, level: ns.level, label: `${shortName(s.name)} ${fmtDist(ns.ref.d)}\n${gapText(ns.ref.cmp, moveNoun(b))}` });
      }
      const zr = ck.edu.find((r) => r.ref && r.ref.zone);
      if (zr && zr.ref.d != null) {
        const z = zr.ref.zone;
        out.push({ kind: 'zone', pid: b.pid, id: b.id, zoneId: z.id, from, to: [z.schoolLon, z.schoolLat], d: zr.ref.d, level: 'info', label: `${z.school}\n통학구역 ${fmtDist(zr.ref.d)}` });
      }
    }
    return out;
  }
  /* 입주와 기반시설 시점을 한 달력에 겹친 타임라인. 줄: 입주 / 교육(개교 예정 + 교육 대책) / 교통(교통 대책). 같은 달은 한 점에 이름을 쌓는다. */
  function timeline(blocks, infra) {
    if (!infra) return null;
    const lanes = [{ key: 'move', name: '입주', items: [] }, { key: 'edu', name: '교육', items: [] }, { key: 'transit', name: '교통', items: [] }];
    const put = (lane, ym, name, hollow) => {
      if (!ym) return;
      const it = lane.items.find((x) => x.ym === ym) || (lane.items.push({ ym, names: [], hollow: true }), lane.items[lane.items.length - 1]);
      it.names.push(name);
      if (!hollow) it.hollow = false;
    };
    (blocks || []).forEach((b) => put(lanes[0], moveInYm(b.moveIn), b.id, false));
    const regular = [];
    (infra.schools || []).filter((x) => x.status === '신설예정' && x.openYm).forEach((x) => { put(lanes[1], x.openYm, shortName(x.name), false); if (x.level !== '특수학교') regular.push(x); });
    (infra.measures || []).forEach((m) => {
      const lane = m.category === '교육' ? lanes[1] : m.category === '교통' ? lanes[2] : null;
      if (lane && /^\d{4}-\d{2}$/.test(m.when || '')) put(lane, m.when, m.short || m.title, m.status === '검토' || m.status === '미정');
    });
    lanes.forEach((l) => l.items.sort((a, b) => a.ym.localeCompare(b.ym)));
    const yms = lanes.flatMap((l) => l.items.map((i) => i.ym));
    const base = infra.asOf ? String(infra.asOf).slice(0, 7) : null;
    const from = [base, ...yms].filter(Boolean).sort()[0] || null;
    const last = yms.slice().sort().pop() || from;
    const to = from && last ? last : null;
    const firstMove = lanes[0].items[0] ? lanes[0].items[0].ym : null;
    const firstOpen = regular.slice().sort((a, b) => a.openYm.localeCompare(b.openYm))[0];
    const months = firstMove && firstOpen ? monthsBetween(firstMove, firstOpen.openYm) : null;
    return { from, to, lanes, gap: months != null && months > 0 ? { from: firstMove, to: firstOpen.openYm, months, school: shortName(firstOpen.name) } : null };
  }

  /* ---------- 지도 안 단지 라벨(지면 라벨)용 요약 ---------- */
  const shortDist = (d) => (d < 1000 ? `${Math.round(d / 10) * 10} m` : `${(d / 1000).toFixed(1)} km`);
  /* 가장 가까운 역과 직선거리(교통). 역 자료(context)가 없으면 빈 글자. */
  function stationLine(block, context) {
    if (!block || !block.poly || !block.poly.length || !context || !(context.stations || []).length) return '';
    const n = nearest(context.stations, centroid(block.poly), (s) => [s.lon, s.lat]);
    return n ? `${n.item.name} ${shortDist(n.d)}` : '';
  }
  /* 종류별 신호를 기호+글자로. 기본은 주의(▲)만, all 이면 있는 종류 모두. */
  function signalText(levels, all) {
    if (!levels) return '';
    const MARK = { warn: '▲', info: '●', none: '○' };
    return Object.keys(GROUP_NAMES).filter((g) => levels[g] && (all || levels[g] === 'warn')).map((g) => `${MARK[levels[g]]}${GROUP_NAMES[g]}`).join(' ');
  }
  /* 라벨 한 줄 요약에 쓰는 값 묶음: 역, 300 m 안 정류장 수(자료 있을 때), 신호(주의만 / 전부). */
  function groundInfo(block, infra, context) {
    const out = { station: stationLine(block, context), stops: null, warn: '', rest: '', all: '' };
    if (!infra || !block || !block.poly || !block.poly.length) return out;
    const c = centroid(block.poly), stops = infra.stops || [];
    if (stops.length) out.stops = stops.filter((s) => distM(c, [s.lon, s.lat]) <= STOP_M).length;
    const lv = categoryLevels(projectChecks(block, infra, context));
    out.warn = signalText(lv); out.all = signalText(lv, true);
    out.rest = signalText(Object.fromEntries(Object.entries(lv).map(([g, v]) => [g, v === 'warn' ? null : v])), true);   // 주의가 아닌 신호(참고·자료 없음)
    return out;
  }

  /* 지면 라벨 자리: 카메라에 가까운 쪽(보는 방향의 반대편) 가장자리 한가운데에서 바깥으로 offsetM 띄운 점.
     건물은 화면에서 발자국 위로 솟으므로, 이 점 아래에 라벨을 앉히면 라벨이 건물에 겹치지 않고 땅 위에 놓인다. bearing 은 지도가 보는 방향(도, 북=0). */
  function frontPoint(poly, bearing, offsetM) {
    if (!poly || !poly.length) return null;
    const off = offsetM == null ? 8 : offsetM, c = centroid(poly), kx = 111320 * Math.cos(c[1] * Math.PI / 180), ky = 110540;
    const rad = ((bearing || 0) + 180) * Math.PI / 180, dx = Math.sin(rad), dy = Math.cos(rad);   // 가까운 쪽을 가리키는 단위 벡터(동·북)
    const pts = poly.map((p) => ({ x: (p[0] - c[0]) * kx, y: (p[1] - c[1]) * ky })), proj = pts.map((p) => p.x * dx + p.y * dy);
    const max = Math.max(...proj), span = max - Math.min(...proj), edge = pts.filter((p, i) => proj[i] >= max - 0.12 * span);
    const mx = edge.reduce((a, p) => a + p.x, 0) / edge.length, my = edge.reduce((a, p) => a + p.y, 0) / edge.length;
    return [c[0] + (mx + dx * off) / kx, c[1] + (my + dy * off) / ky];
  }

  return { frontPoint, shortDist, stationLine, signalText, groundInfo, GROUP_NAMES, shortName, gapText, categoryLevels, summarize, connectors, timeline, LEVEL_MARK, WARN_MONTHS, NEW_SCHOOL_M, SITE_M, STOP_M, STOP_WARN_MONTHS, centroid, distM, fmtDist, fmtYm, fmtDate, fmtN, moveInYm, monthsBetween, moveNoun, compareOpen, nearest, nearestBlock, sortSchools, permitStatus, scaleText, projectChecks };
});
