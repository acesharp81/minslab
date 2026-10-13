const $ = (s) => document.querySelector(s);
const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const fmt = (n) => Number(n).toLocaleString('ko-KR');
const pct = (n, d) => (d ? (100 * n / d).toFixed(0) : '0') + '%';
const maplibregl = window.maplibregl;
if (!maplibregl) {
  const f = $('#fatal'); f.hidden = false;
  f.textContent = '지도 라이브러리(MapLibre)를 불러오지 못했습니다. 인터넷 연결을 확인한 뒤 새로고침해 주세요.';
  throw new Error('maplibregl not loaded');
}
const reduceMotion = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
const say = (m) => { $('#sr').textContent = m; };

/* ---------- 데이터 ---------- */
const GY = window.GY_BUILDINGS, PR = window.GY_PROJECTS;
const DYN_ON = !!(GY && GY.dynamic) && new URLSearchParams(location.search).get('dyn') !== '0';   // 건물을 요청 시 칸 단위로 불러 붙이는가(번들이 없는 지역, 또는 번들 밖)
const HAS_GY = !!(GY && GY.features && (GY.features.length || GY.dynamic));
const HAS_PR = !!(PR && PR.blocks && PR.blocks.length);
const REG = window.REGION || {};                               // 지역 정보(어댑터가 채움): 이름·시작 위치·출처·단지 찾기
const DISTRICTS = HAS_PR ? (PR.districts && PR.districts.length ? PR.districts : (PR.district ? [PR.district] : [])) : [];   // 지구 경계(여러 개 가능)
const FACTOR = (HAS_GY && GY.meta.factor) || {};
function floorsToHeight(f) {
  const k = f <= 5 ? '공동주택_1-5' : f <= 10 ? '공동주택_6-10' : f <= 15 ? '공동주택_11-15' : f <= 20 ? '공동주택_16-20' : '공동주택_21+';
  return Math.round(f * (FACTOR[k] || 2.85) * 10) / 10;
}
const BLOCKS = HAS_PR ? PR.blocks.slice() : [];             // 순서는 어댑터가 정한다(region.projectOrder → 상태 → 세대수 → 이름)
let HOME_VISIBLE = new Set(BLOCKS.map((b) => b.id));
const HAS_PRIV = BLOCKS.some((b) => b.priv);                  // 공공택지 위 민간 단지가 있는 지역인가
const KIND = { '분양중': 'sale', '건설 단계': 'build', '준공 임박': 'soon', '입주 단계': 'move', '계획': 'plan' };
const kindOf = (b) => (b.priv ? 'priv' : KIND[b.status]);    // 색·무늬를 정하는 종류. 민간 단지는 상태와 상관없이 회색(priv)
const STATUS_ORDER = ['분양중', '건설 단계', '준공 임박', '입주 단계', '계획'];
const unitsTxt = (b) => b.candidateIds ? (b.unitsKnown === false ? '계획 호수 미확보' : `계획 ${fmt(b.units)}호`) : (b.unitsKnown === false ? '세대수 미확인' : `${fmt(b.units)}세대`);
const dongN = (b) => b.dongCount || (b.dongs ? b.dongs.length : 0);
/* 단지 이름(label)은 자료에서 오므로 따옴표·쉼표·꺾쇠가 있어도 속성과 선택자가 깨지지 않게 한다. */
const idsAttr = (ids) => esc(JSON.stringify(ids));                                       // data-ids 에는 JSON 배열을 넣는다
const idsOf = (el) => { try { const v = JSON.parse(el.dataset.ids); return Array.isArray(v) ? v : []; } catch (_) { return []; } };
const byId = (scope, name, id) => scope.querySelector(`[${name}="${CSS.escape(String(id))}"]`);
// 색: 상황판 시안(M3)의 6단계 색. 모집(sale)·착공(build)·준공(soon)·입주(move)·계획(plan)이 서로 다른 밝기·색상이고, 면 무늬도 달리한다(모집 단색 / 착공 해칭 / 준공 점무늬 / 입주 격자 / 계획 점선 / 공공택지 민간 회색 단색).
// 패널·지도 모두 어두운 네이비 바탕이라 글자·칩·지도 위 색에 같은 값을 쓴다(네이비 #101A44 위 대비 7:1 이상, tests/js/glass.test.cjs). 지도 위 색은 THEME에서 가져온다
const COLOR = { sale: '#C7D0DA', build: '#FF9F43', soon: '#A5E56D', move: '#D9A6FF', plan: '#7BA7FF', priv: '#98A3C9' };
// Next 지도(data-map-shell)는 저장된 테마를 따르고, 단계색은 대시보드와 같은 토큰(app/tailwind.css 의 --st-*-ink)에서 읽는다.
// 독립 index.html 은 tailwind.css 가 없으므로 위 다크 값을 그대로 쓴다.
const SHELL = document.documentElement.hasAttribute('data-map-shell');
let LIGHT_MAP = SHELL && !document.documentElement.classList.contains('dark');
function applyStageInk() {
  const cs = getComputedStyle(document.documentElement), read = (k) => { const v = cs.getPropertyValue(`--st-${k}-ink`).trim(); return /^#[0-9a-f]{6}$/i.test(v) ? v.toUpperCase() : null; };
  for (const k of Object.keys(COLOR)) { const v = read(k); if (v) COLOR[k] = v; }
}
if (SHELL) applyStageInk();
/* 공급 6단계 [번호, 이름, 속하는 단지 상태들, 색] — 대시보드와 같은 01 정책 ~ 06 입주(lib/board/stages.ts). 머리 줄의 단계 필터와 사이드바 카드의 '공급 단계 위치'가 같이 쓴다.
   단지 상태 5종 → 6단계는 사업 레지스트리와 같은 매핑(docs/product/상황판-스펙.md 9.2, lib/projects.js stageOf): 계획 → 03 인허가, 건설 단계·준공 임박 → 04 건설, 분양중 → 05 공급, 입주 단계 → 06 입주.
   01 정책·02 사업화에 해당하는 단지 상태는 없다(지도의 '계획' 단지는 인허가 기록이 있는 단지라 레지스트리에서도 03 이다). 색은 그 단계 단지가 지도에 그려지는 색(첫 상태 기준), 단지가 없는 단계는 보조 글자색. */
const stageColor = (sts) => (sts.length ? COLOR[KIND[sts[0]]] : 'var(--mute)');
const STAGES6 = [['01', '정책', []], ['02', '사업화', []], ['03', '인허가', ['계획']], ['04', '건설', ['건설 단계', '준공 임박']], ['05', '공급', ['분양중']], ['06', '입주', ['입주 단계']]].map((s) => [...s, stageColor(s[2])]);
/* 단지 상태 → 6단계 이름('04 건설'). 범례·옵션 창의 상태를 6단계 순서로 놓고 번호를 붙인다(머리 줄 6단계 필터와 같은 대응) */
const stageOfSt = (st) => { if (REG.home && st === '계획') return '02·03 사업화·인허가'; const s = STAGES6.find((x) => x[2].includes(st)); return s ? `${s[0]} ${s[1]}` : ''; };
const BY_STAGE = STAGES6.flatMap((s) => s[2]);   // 계획 · 건설 단계 · 준공 임박 · 분양중 · 입주 단계
const pctTxt = (v) => (v >= 99.95 ? '100' : v >= 10 ? v.toFixed(1) : v.toFixed(2).replace(/0$/, '')) + '%';
function sparkline(h) {
  const W = 56, H = 18, n = h.length, mx = Math.max(...h.map((x) => x[1]), 1);
  const pts = h.map((x, i) => `${(i / (n - 1) * (W - 4) + 2).toFixed(1)},${(H - 2 - x[1] / mx * (H - 4)).toFixed(1)}`).join(' ');
  return `<svg viewBox="0 0 ${W} ${H}" aria-hidden="true"><polyline points="${pts}" fill="none" stroke="var(--mute)" stroke-width="1.6"/><circle cx="${pts.split(' ').pop().split(',')[0]}" cy="${pts.split(' ').pop().split(',')[1]}" r="2.2" fill="var(--ink)"/></svg>`;
}
function progressRow(b, k) {
  const p = b.progress, color = COLOR[k];
  return `<span class="pg" style="--c:${color}" title="공사 공정율 ${esc(p.rate)}% (${esc(p.asOf)} 기준)"><span>공사</span><span class="bar2"><i style="width:${Math.max(p.rate, 0.8)}%"></i></span><b>${pctTxt(p.rate)}</b>${p.history.length >= 3 ? sparkline(p.history) : ''}</span>`;
}
const centroid = (poly) => [poly.reduce((a, p) => a + p[0], 0) / poly.length, poly.reduce((a, p) => a + p[1], 0) / poly.length];
const hex2 = (h) => [1, 3, 5].map((i) => parseInt(h.slice(i, i + 2), 16));
function mixTone(kind, t0, tone = TONE) { const t = 0.3 + 0.7 * t0; const [a, b] = tone[kind].map(hex2); return '#' + a.map((v, i) => Math.round(v + (b[i] - v) * t).toString(16).padStart(2, '0')).join(''); }
function floorsRange(b) { const fl = b.dongs ? b.dongs.map((d) => d.floors) : null; return fl ? [Math.min(...fl), Math.max(...fl)] : null; }

const ST = { n: 0, src: { '공식높이': 0, '층수환산': 0, '정보없음': 0 } };
if (HAS_GY) GY.features.forEach((f, i) => { f.properties.i = i; ST.n++; ST.src[f.properties.src]++; });
const STATIC_N = HAS_GY ? GY.features.length : 0;   // 번들에 든 건물 수(요청 시 조회로 붙는 것과 구분)

/* ---------- 지도 ---------- */
const KEY = String(window.VWORLD_KEY || '').trim();
let usingVworld = !!KEY;
const q = new URLSearchParams(location.search);
/* 지도 위에 그리는 모든 색은 여기서만 정한다(스타일을 다시 불러와도 같은 값으로 다시 그려진다). */
const THEME = {
  vw: String(window.VWORLD_LAYER || 'midnight'), ofm: 'dark', bg: '#0A1030', text: '#E8EDFF', sub: '#9AA8D6', halo: '#0A1030', sky: ['#0A1030', '#0E1740'],
  mask: ['#000000', 0.32], shadow: ['#000000', 0.4], hillShadow: '#000000', hillHi: '#3A4C8C', hillAcc: '#141C4A', district: '#B8C4F0', dong: '#E8EDFF', other: ['#5566BE', '#3A4C8C'],
  ramp: ['#17204D', '#222E66', '#2A3A7A', '#33468D', '#4155A3'], flat: '#16225A',   // 기존 건물: 낮은 건물은 어둡고 높을수록 밝다(어두운 바탕에서는 밝을수록 눈에 띈다)
  ghost: { fill: '#6C7DC0', fillOp: 0.3, line: '#9AA8D6', lineOp: 0.8 },   // 평면으로만 그리는 도형(src '정보없음' 또는 g=1): 솟지 않는 연한 평면 + 점선 윤곽
  color: COLOR,
  tone: { sale: ['#7C8696', '#C7D0DA'], build: ['#B86F2A', '#FF9F43'], soon: ['#6B9F3E', '#A5E56D'], move: ['#9A6FC0', '#D9A6FF'], plan: ['#4A6FB5', '#7BA7FF'], priv: ['#59648E', '#98A3C9'] },   // 같은 단지 안: 낮은 동은 어둡게, 높은 동은 상태색 그대로
  infra: { edu: '#B79CFF', power: '#FFC24D', transit: '#E8EDFF', warn: '#FFD66E', ink: '#10162E' },   // ink: 색 바탕 기호 안의 그림 색
  // 기존 건물 중 기반시설(학교·병원·공공·복지): c 는 건물 색(상태색·점검 보라와 색상각이 떨어지게 고름), t 는 이름표 글자색(네이비 바탕에서 7:1 이상)
  fac: { edu: { c: '#F7C600', t: '#FFD84D' }, med: { c: '#E5384F', t: '#FF8FA0' }, pub: { c: '#2EC4B6', t: '#7FE3D8' } },
};
const LIGHT_THEME = {
  ...THEME,
  // raster: 백지도의 공원 무늬·초록을 한 단계 눌러 단지·이름표가 먼저 보이게
  vw: 'white', ofm: 'liberty', raster: { 'raster-saturation': -0.35, 'raster-contrast': -0.05 }, bg: '#F5F7FA', text: '#172B4D', sub: '#526176', halo: '#FFFFFF', sky: ['#E5EDF5', '#F5F7FA'],
  mask: ['#FFFFFF', 0.12], shadow: ['#334960', 0.16], hillShadow: '#72859B', hillHi: '#FFFFFF', hillAcc: '#C3CFDC', district: '#537294', dong: '#172B4D', other: ['#778EAB', '#A8B9CD'],
  ramp: ['#DDE5EE', '#CBD6E3', '#B9C9DA', '#9FB4CD', '#819DBC'], flat: '#D7E1EC',
  ghost: { fill: '#9FB4CD', fillOp: 0.25, line: '#637B96', lineOp: 0.8 },
  tone: { sale: ['#C9D1DE', '#7286A8'], build: ['#F1CAAD', '#DA7426'], soon: ['#C1D9B4', '#5B9B3A'], move: ['#D3C5EC', '#8B67CC'], plan: ['#B5CDF0', '#3D7BD8'], priv: ['#CED6E0', '#8C99AB'] },   // 높은 층 끝 = app/tailwind.css 라이트 --st-*(차트 면 색). 글자용 진한 색을 쓰면 덩어리처럼 무겁다
  infra: { edu: '#7955AD', power: '#895716', transit: '#344960', warn: '#7F6300', ink: '#FFFFFF' },
  fac: { edu: { c: '#BE9900', t: '#806B13' }, med: { c: '#C94359', t: '#A92B42' }, pub: { c: '#26958B', t: '#18756B' } },
};
const TH = () => LIGHT_MAP ? LIGHT_THEME : THEME;
let TONE = TH().tone;   // 패널 막대용. 지도 위 동 색은 TH().tone
const wmts = (layer) => `https://api.vworld.kr/req/wmts/1.0.0/${KEY}/${layer}/{z}/{y}/{x}.png`;
const ofmUrl = () => `https://tiles.openfreemap.org/styles/${TH().ofm}`;
function baseStyle() {
  if (REG.home?.isSchematicPreview) return { version: 8, glyphs: 'https://tiles.openfreemap.org/fonts/{fontstack}/{range}.pbf',
    sources: {}, layers: [{ id: 'bg', type: 'background', paint: { 'background-color': TH().bg } }] };
  if (!KEY || !usingVworld) return ofmUrl();
  return { version: 8, glyphs: 'https://tiles.openfreemap.org/fonts/{fontstack}/{range}.pbf',
    sources: { vworld: { type: 'raster', tileSize: 256, maxzoom: 18, tiles: [wmts(TH().vw)], attribution: '배경 © 국토교통부 V-World · 지명 © OpenStreetMap contributors' } },
    layers: [{ id: 'bg', type: 'background', paint: { 'background-color': TH().bg } }, { id: 'vworld', type: 'raster', source: 'vworld', paint: TH().raster || {} }] };
}
$('#baseNote').textContent = REG.home?.isSchematicPreview ? '위치 미확보 · 배경지도 없는 가상 모형' : KEY ? '' : '배경: OpenFreeMap';

/* 지형 타일: 상황판 안(Next.js, SHELL)에서는 우리 서버 중계(/api/v1/terrain → CDN 1년 캐시)로 받는다. S3(미국 동부) 직접은 장당 응답 시작 ~0.7 s 라 첫 로딩이 가장 길었다(계획서 16절).
   API 가 없는 옛 정적 열기(index.html 직접)는 S3 를 그대로 쓴다 */
const DEM_TILES = [SHELL ? `${location.origin}/poc/housing-board/api/v1/terrain?z={z}&x={x}&y={y}` : 'https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png'];
const STATUS = { loaded: false, errors: [], officialData: HAS_GY, projects: HAS_PR, base: KEY ? 'vworld' : 'openfreemap' };   // 시험용 상태. ?selftest 일 때만 window에 공개한다
if (q.get('selftest')) window.__mapStatus = STATUS;
/* 주소 ?at=경도,위도,확대[,기울기,방위] 로 시작 위치를 바꾼다(어디를 봐야 하는지 알려 줄 때). 값이 이상하면 무시한다 */
function atParam() {
  const v = String(q.get('at') || '').split(',').map((s) => (s.trim() === '' ? NaN : Number(s)));
  const [lon, lat, zoom, pitch, bearing] = v;
  if (![lon, lat, zoom].every(Number.isFinite) || lon < 120 || lon > 135 || lat < 30 || lat > 45 || zoom < 0 || zoom > 22) return {};
  const out = { center: [lon, lat], zoom };
  if (Number.isFinite(pitch) && pitch >= 0 && pitch <= 80) out.pitch = pitch;
  if (Number.isFinite(bearing) && bearing >= -360 && bearing <= 360) out.bearing = bearing;
  return out;
}
const RES = window.RESOLVED || null;                            // 표준코드(?code= 등)로 열었을 때 해석 결과: 시작 위치와 강조할 경계
const START = { pitch: 52, bearing: 0, ...(REG.view || { center: [126.7585, 37.5515], zoom: 14.4 }), ...((RES && RES.start) || {}), ...atParam() };   // 지역의 시작 위치(코드로 열면 그 법정동·필지, 주소 ?at= 가 있으면 그 위치가 우선)
const map = new maplibregl.Map({
  container: 'map', style: baseStyle(), ...START, maxPitch: 80, minZoom: REG.home ? 7 : 11, attributionControl: { compact: true },
  canvasContextAttributes: { antialias: q.get('aa') !== '0' },   // 모서리 계단 방지(4배 다중 샘플). 저사양이면 주소에 ?aa=0
  localIdeographFontFamily: getComputedStyle(document.body).fontFamily,
});
if (REG.home) window.__housingMap = map;   // HOME 근거 레이어가 원본 3D 지도에 붙는 접점
map.addControl(new maplibregl.ScaleControl({ unit: 'metric' }), 'bottom-right');
/* 로딩 화면(index.html #loading, assets/js/loadview.js): 지도가 생긴 뒤의 배경·건물·지형 타일을 소스별로 세어 실시간으로 보인다. 첫 idle 에서 걷는다.
   LoadView 가 없으면(옛 로더) 첫 idle 에 #loading 만 숨긴다. */
const LV = window.LoadView ? window.LoadView.ctl() : null;
if (LV) {
  LV.sub([REG.name, BLOCKS.length ? `단지 ${BLOCKS.length}곳` : '', HAS_GY && GY.features.length ? `건물 ${fmt(GY.features.length)}동` : ''].filter(Boolean).join(' · ') || '지도를 준비하고 있습니다');
  LV.watchMap(map, { base: ['vworld', 'openmaptiles', 'ofm'], bld: ['official', 'dongs', 'dong-shadow', 'blocks', 'other-blocks'], dem: ['dem', 'dem-shade'] });   // 건물 그림자(official-shadow)는 첫 idle 뒤에 붙는다
}
let popup = null, selId = null, selDong = null, vwFail = 0, DONG_FEATS = [];
const SHOWN = new Set(BLOCKS.map((b) => b.status));          // 지도에 보이는 상태
let viewMode = window.GY_INFRA ? 'infra' : 'floors';   // 기반시설 보기로 연다(점검 자료가 없는 지역은 층수 높이). 층수·공정율·입주 시기 보기 전환은 없앴다(2026-10-10 사용자 결정)
let privOn = q.get('priv') !== '0';                            // 공공택지 민간 단지: 기본 켬
let hudOn = q.get('hud') !== '0';                              // 단지 모서리 표시선(레티클): 기본 켬(옵션은 모두 켠 채로 연다, 2026-10-10 사용자 요청). 주소 hud=0 이면 끔
let cardsOn = q.get('cards') !== '0';                          // 단지 정보 카드(떠 있는 상자, 표시선 포함): 기본 켬. 끄면(cards=0) 단지 요약을 지도 안 라벨로 단지 위치에 붙인다
let ctxOn = q.get('ctx') !== '0';                              // 역·학교(OSM): 기본 켬
let ringOn = q.get('ring') !== '0';                            // 역 반경 원(500 m·1 km): 기본 켬
let infraOn = q.get('infra') !== '0';                          // 입주 전 점검(학교·정류장·전기 시설): 기본 켬. 자료가 있는 지역에서만 쓰인다
let zoneOn = q.get('zone') !== '0';                            // 초등 통학구역 경계: 기본 켬
let busOn = q.get('bus') !== '0';                              // 버스 노선·위치(3D): 기본 켬. 실시간 노선이 있는 지역에서만 쓰인다
let dimExisting = q.get('dim') !== '0';                       // 기존 건물 흐리게: 기본 켬 = 학교·병원·공공시설만 3D, 나머지는 채우지 않은 점선 윤곽만(주소에 dim=0 이면 끔 = 모두 3D). 옵션 창이 아니라 위 도구 줄의 '건물 흐리게' 단추
map.on('error', (e) => {
  STATUS.errors.push((e && e.error && e.error.message) || String(e));
  // V-World 타일이 거절되면(키 오류·등록하지 않은 주소 등) 한 번만 OpenFreeMap으로 바꾼다.
  // 확대한 깊은 단계(19 이상)에는 V-World 타일이 없어 오류가 나므로 무시하고, 낮은 단계 타일이 2번 이상 실패할 때만 바꾼다.
  const tz = e && e.tile && e.tile.tileID && e.tile.tileID.canonical ? e.tile.tileID.canonical.z : 0;
  if (usingVworld && e && e.sourceId === 'vworld' && tz <= 17 && ++vwFail >= 2) {
    usingVworld = false; STATUS.base = 'openfreemap(fallback)';
    $('#baseNote').textContent = 'V-World 배경지도를 불러오지 못해 OpenFreeMap으로 바꿨습니다. 키와 등록한 서비스 주소를 확인하세요.';
    map.setStyle(baseStyle(), { diff: false });
  }
});

const rgba = (h, a) => { const [r, g, b] = hex2(h); return `rgba(${r},${g},${b},${a})`; };
/* 블록 무늬(사선·격자·점). 그림 24px 을 배율 2 로 올려 화면에서 12px 주기로 반복한다.
   예전 8px 그림(4px 주기)은 기울인 지도의 먼 쪽에서 화소보다 촘촘해져 무아레·계단이 생겼다(2026-10-09, 레티나 2배 캡처로 확인).
   선은 화소 경계에 맞추지 않고 굵기 2.5px(화면 1.25px)로 두어 어느 배율에서도 끊기지 않게 한다. */
function patternImage(kind) {
  const s = 24, c = document.createElement('canvas'); c.width = c.height = s; const x = c.getContext('2d'), T = TH();
  if (kind === 'hatch') {            // 건설 단계: 사선(45°, 한 칸에 한 줄 — 가장자리 조각까지 그려 이음매가 없게)
    const col = T.color.build;
    x.fillStyle = rgba(col, .12); x.fillRect(0, 0, s, s); x.strokeStyle = col; x.lineWidth = 2.5; x.lineCap = 'square'; x.beginPath();
    for (const o of [-s, 0, s]) { x.moveTo(o - 2, s + 2); x.lineTo(o + s + 2, -2); }
    x.stroke();
  } else if (kind === 'cross') {     // 입주 단계: 격자(가로·세로 한 줄씩)
    const col = T.color.move;
    x.fillStyle = rgba(col, .12); x.fillRect(0, 0, s, s); x.strokeStyle = col; x.lineWidth = 2.5; x.beginPath();
    x.moveTo(0, s / 2); x.lineTo(s, s / 2); x.moveTo(s / 2, 0); x.lineTo(s / 2, s); x.stroke();
  } else {                           // 준공 임박: 점
    const col = T.color.soon;
    x.fillStyle = rgba(col, .14); x.fillRect(0, 0, s, s); x.fillStyle = col; x.beginPath(); x.arc(s / 2, s / 2, 4, 0, Math.PI * 2); x.fill();
  }
  return x.getImageData(0, 0, s, s);
}
function roundRectPath(x, a, b, w, h, r) { x.beginPath(); x.moveTo(a + r, b); x.arcTo(a + w, b, a + w, b + h, r); x.arcTo(a + w, b + h, a, b + h, r); x.arcTo(a, b + h, a, b, r); x.arcTo(a, b, a + w, b, r); x.closePath(); }
/* 단지 배지: 늘어나는 알약 모양 그림(9-slice). 밝은 상태색 알약에 네이비 테두리. */
function badgeImage(kind) {
  const W = 48, H = 28, c = document.createElement('canvas'); c.width = W; c.height = H; const x = c.getContext('2d'), plan = kind === 'plan';
  const col = COLOR[kind];
  roundRectPath(x, 3, 3, W - 6, H - 6, 9);
  x.lineWidth = 4; x.strokeStyle = 'rgba(10,16,48,.94)'; x.stroke();
  x.fillStyle = plan ? TH().bg : col; x.fill();
  if (plan) { roundRectPath(x, 3, 3, W - 6, H - 6, 9); x.lineWidth = 1.8; x.setLineDash([4, 3]); x.strokeStyle = col; x.stroke(); }
  return { data: x.getImageData(0, 0, W, H), opts: { pixelRatio: 2, stretchX: [[14, 34]], stretchY: [[11, 17]], content: [12, 8, 36, 20] } };
}
/* 지면 라벨 그림: 짙은 네이비 카드(M3의 칩 문법: 얇은 테두리 + 왼쪽 상태색 띠). 상태색 단색 알약(bd-*)보다 대비가 약해 HUD 카드와 같은 결이다.
   지도 안 기호는 backdrop-filter를 못 쓰므로 투명도를 .9로 두어 어떤 건물 위에서도 글자 대비(밝은 글자 #E8EDFF 기준 10:1 이상)가 유지된다. */
function groundImage(kind) {
  const W = 56, H = 32, c = document.createElement('canvas'); c.width = W; c.height = H; const x = c.getContext('2d'), plan = kind === 'plan';
  const col = COLOR[kind];
  roundRectPath(x, 1, 1, W - 2, H - 2, 6); x.fillStyle = LIGHT_MAP ? 'rgba(255,255,255,.97)' : 'rgba(16,26,68,.9)'; x.fill();
  x.lineWidth = 1.2; x.strokeStyle = LIGHT_MAP ? '#B9C6D6' : '#3A4C8C'; if (plan) x.setLineDash([3, 2]); x.stroke(); x.setLineDash([]);
  x.fillStyle = col; x.fillRect(1, 2, 4, H - 4);
  return { data: x.getImageData(0, 0, W, H), opts: { pixelRatio: 2, stretchX: [[10, 46]], stretchY: [[10, 22]], content: [9, 6, 48, 26] } };
}
/* 기반시설 그림 기호: 흰 고리 안의 둥근 배지 + 단순한 그림. 학교(보라), 번개(황토), 버스(검정) — 상태색(주황·파랑·초록·분홍)과 겹치지 않게 골랐다.
   그림은 SVG 경로 하나로 두어 지도 기호(캔버스)와 범례(SVG)가 같은 모양을 쓴다. */
const GLYPH = {
  school: 'M12 3 2.5 9.5H4V20h16V9.5h1.5L12 3ZM10 14.5h4v5h-4ZM7.5 11H10v2.5H7.5ZM14 11h2.5v2.5H14Z',
  bolt: 'M13.5 2 5 13.5h5.5L9.5 22 19 9.5h-5.8L13.5 2Z',
  bus: 'M6 3h12a2 2 0 0 1 2 2v12h-1.5v2.2a.8.8 0 0 1-.8.8h-1.4a.8.8 0 0 1-.8-.8V17H8.5v2.2a.8.8 0 0 1-.8.8H6.3a.8.8 0 0 1-.8-.8V17H4V5a2 2 0 0 1 2-2ZM6.5 5.5v6h11v-6ZM8 14.2a1.1 1.1 0 1 0 2.2 0 1.1 1.1 0 1 0-2.2 0ZM13.8 14.2a1.1 1.1 0 1 0 2.2 0 1.1 1.1 0 1 0-2.2 0Z',
};
const INFRA_ICONS = ['edu-new', 'edu-site', 'power', 'bus', 'garage'];
function infraIconSpec(kind) {
  const I = TH().infra, ink = I.ink, paper = TH().bg;
  return { 'edu-new': { shape: 'circle', fill: I.edu, ink, glyph: 'school' }, 'edu-site': { shape: 'circle', fill: paper, ink: I.edu, glyph: 'school', dash: I.edu },
    power: { shape: 'circle', fill: I.power, ink, glyph: 'bolt' }, bus: { shape: 'circle', fill: I.transit, ink, glyph: 'bus' }, garage: { shape: 'square', fill: I.transit, ink, glyph: 'bus' } }[kind];
}
function infraIcon(kind) {
  const S = 48, c = document.createElement('canvas'); c.width = c.height = S; const x = c.getContext('2d'), sp = infraIconSpec(kind), halo = TH().halo;
  const shape = (r) => { x.beginPath(); if (sp.shape === 'square') roundRectPath(x, 24 - r, 24 - r, 2 * r, 2 * r, 8); else x.arc(24, 24, r, 0, Math.PI * 2); };
  shape(22); x.fillStyle = halo; x.fill();                         // 바깥 고리(배경과 분리)
  shape(19); x.fillStyle = sp.fill; x.fill();
  if (sp.dash) { x.lineWidth = 2.6; x.setLineDash([4.5, 3.2]); x.strokeStyle = sp.dash; x.stroke(); x.setLineDash([]); }
  const k = 1.15; x.save(); x.translate(24 - 12 * k, 24 - 12 * k); x.scale(k, k); x.fillStyle = sp.ink; x.fill(new Path2D(GLYPH[sp.glyph]), 'evenodd'); x.restore();
  return { data: x.getImageData(0, 0, S, S), opts: { pixelRatio: 2 } };
}
/* 범례용 같은 기호(SVG). 색은 현재 테마 값. */
function infraIconSvg(kind) {
  const sp = infraIconSpec(kind), sh = sp.shape === 'square' ? `<rect x="2" y="2" width="20" height="20" rx="4"` : '<circle cx="12" cy="12" r="10.5"';
  return `<svg class="lgi" viewBox="0 0 24 24" aria-hidden="true">${sh} fill="${sp.fill}" stroke="${sp.dash || sp.fill}" stroke-width="1.4"${sp.dash ? ' stroke-dasharray="3 2"' : ''}/><g transform="translate(5.2 5.2) scale(.57)"><path d="${GLYPH[sp.glyph]}" fill="${sp.ink}" fill-rule="evenodd"/></g></svg>`;
}
/* 2026-10을 0으로 센 달 수(소수는 그 달 안의 날짜). 입주 시기 보기와 다음 일정에서 쓴다. */
const moveText = (b) => (/^\d/.test(b.moveIn) ? `입주 ${b.moveIn}` : String(b.moveIn));
/* 지면 라벨의 글자 식. 이름(굵게)+세대수 / 층수 + 교통 / 신호. 신호는 주의만 갈색(기반시설 보기에서는 세 종류 모두). */
function groundText(inline) {
  const second = 'gf', gw = inline ? 'gwi' : 'gw', gr = inline ? 'gri' : 'gr';
  const warn = TH().infra.warn;
  return ['format', ['get', 'id'], { 'font-scale': 1.12, 'text-font': ['literal', ['Noto Sans Bold']] }, '  ', {}, ['get', 'gu'], {},
    inline ? ' · ' : '\n', { 'font-scale': 0.86 }, ['get', second], { 'font-scale': 0.86 }, ['get', 'tr'], { 'font-scale': 0.86 }, ['get', gw], { 'font-scale': 0.86, 'text-color': warn }, ['get', gr], { 'font-scale': 0.86 }];
}
const GROUND = new Map();   // 단지 → 지면 라벨 요약(가까운 역, 정류장 수, 신호). 자료가 정해지면 한 번만 만든다
function groundOf(b) {
  if (!GROUND.has(b.id)) GROUND.set(b.id, window.InfraLib ? window.InfraLib.groundInfo(b, window.GY_INFRA || null, window.GY_CONTEXT || null) : { station: '', stops: null, warn: '', all: '' });
  return GROUND.get(b.id);
}
function blockProps(b) {
  const g = groundOf(b), fr = floorsRange(b), sig = infraOn && window.GY_INFRA;
  return { id: b.id, status: b.status, kind: kindOf(b), priv: !!b.priv, units: b.units, short: b.id, l2: `${b.status} · ${unitsTxt(b)}`,
    lc: `${b.id} · ${b.status}`,
    /* 지면 라벨(요약): 세대수 / 층수 / 교통(가까운 역) / 신호(주의만·전부) */
    gu: unitsTxt(b), gf: fr ? `${b.homeModelKind === 'SCHEMATIC' ? '가상 ' : ''}${fr[0] === fr[1] ? fr[0] : fr[0] + '~' + fr[1]}층` : '층수 미확인',
    tr: g.station ? ` · ${g.station}` : '',
    /* 신호: 주의는 갈색 구간(gw), 기반시설 보기에서만 나머지(참고·자료 없음)를 보통 글자색 구간(gr)으로 이어 붙인다. …i 는 한 줄 라벨용 */
    gw: sig && g.warn ? `\n${g.warn}` : '', gr: sig && viewMode === 'infra' && g.rest ? (g.warn ? `  ${g.rest}` : `\n${g.rest}`) : '',
    gwi: sig && g.warn ? `  ${g.warn}` : '', gri: sig && viewMode === 'infra' && g.rest ? `  ${g.rest}` : '' };
}
function refreshGround() {   // 보기/기반시설 켬·끔이 바뀌면 라벨 속성을 다시 채운다
  for (const id of ['block-pts', 'block-fronts']) { const src = map.getSource(id); if (src) src.setData(id === 'block-pts' ? blockPointsGeoJSON() : blockFrontsGeoJSON()); }
}
function blocksGeoJSON() {
  return { type: 'FeatureCollection', features: BLOCKS.map((b) => ({ type: 'Feature', properties: blockProps(b), geometry: { type: 'Polygon', coordinates: [[...b.poly, b.poly[0]]] } })) };
}
function districtLabelPoint(d) {   // 단지 라벨과 겹치지 않게 지구 남쪽 1/3 지점에 둔다
  const ps = d.poly, lons = ps.map((p) => p[0]), lats = ps.map((p) => p[1]);
  return [(Math.min(...lons) + Math.max(...lons)) / 2 + 0.002, Math.min(...lats) + (Math.max(...lats) - Math.min(...lats)) * 0.16];
}
function blockPointsGeoJSON() {
  return { type: 'FeatureCollection', features: BLOCKS.map((b) => ({ type: 'Feature', properties: blockProps(b), geometry: { type: 'Point', coordinates: centroid(b.poly) } })) };
}
let frontBearing = null;   // 지면 라벨 자리를 마지막으로 계산한 지도 방향
function blockFrontsGeoJSON() {   // 지면 라벨은 단지 발자국에서 카메라에 가까운 쪽 가장자리 바깥(땅 위)에 앉힌다 — 건물에 겹치지 않게
  frontBearing = map.getBearing();
  return { type: 'FeatureCollection', features: BLOCKS.map((b) => ({ type: 'Feature', properties: blockProps(b), geometry: { type: 'Point', coordinates: IL.frontPoint(b.poly, frontBearing, 7) || centroid(b.poly) } })) };
}
function ringArea(r) { let a = 0; for (let i = 0; i < r.length; i++) { const p = r[i], q2 = r[(i + 1) % r.length]; a += p[0] * q2[1] - q2[0] * p[1]; } return Math.abs(a) / 2; }
function dongsGeoJSON() {
  const feats = [], labels = [], tone = TH().tone;
  BLOCKS.forEach((b) => {
    if (!b.dongs) return; const kind = kindOf(b); const r = floorsRange(b);
    b.dongs.forEach((d) => {
      const t = r && r[1] > r[0] ? (d.floors - r[0]) / (r[1] - r[0]) : 1;
      const color = mixTone(kind, t, tone);
      d.poly.forEach((ring) => feats.push({ type: 'Feature', properties: { key: `${b.id}-${d.no}`, block: b.id, no: d.no, floors: d.floors, h: d.h != null ? d.h : floorsToHeight(d.floors), hEst: d.h != null ? 0 : 1, tier: d.tier, color, status: b.status, priv: !!b.priv },
        geometry: { type: 'Polygon', coordinates: [[...ring, ring[0]]] } }));
      const big = d.poly.reduce((m, ring) => (ringArea(ring) > ringArea(m) ? ring : m), d.poly[0]);
      labels.push({ type: 'Feature', properties: { text: `${d.no}${b.homeModelKind === 'SCHEMATIC' ? ' · 예시' : '동'} ${d.floors}층`, no: d.no, block: b.id, status: b.status, priv: !!b.priv }, geometry: { type: 'Point', coordinates: centroid(big) } });
    });
  });
  return [{ type: 'FeatureCollection', features: feats }, { type: 'FeatureCollection', features: labels }];
}
/* 동 그림자: 북서쪽에서 해가 비친다고 보고, 높이의 0.6배만큼 남동쪽으로 늘어뜨린 바닥 그림자(외곽 볼록껍질). 장식이며 실제 일조 계산이 아니다. */
function hull(P) {
  P = P.slice().sort((a, b) => a[0] - b[0] || a[1] - b[1]);
  const cr = (o, a, b) => (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0]); const lo = [], up = [];
  for (const p of P) { while (lo.length >= 2 && cr(lo[lo.length - 2], lo[lo.length - 1], p) <= 0) lo.pop(); lo.push(p); }
  for (const p of P.slice().reverse()) { while (up.length >= 2 && cr(up[up.length - 2], up[up.length - 1], p) <= 0) up.pop(); up.push(p); }
  return lo.slice(0, -1).concat(up.slice(0, -1));
}
function shadowGeoJSON(feats) {
  return { type: 'FeatureCollection', features: feats.map((f) => {
    const ring = f.geometry.coordinates[0], lat = ring[0][1], L = f.properties.h * 0.6, k = Math.SQRT1_2;
    const dx = L * k / (111320 * Math.cos(lat * Math.PI / 180)), dy = -L * k / 111320;
    const h = hull(ring.concat(ring.map((p) => [p[0] + dx, p[1] + dy]))); h.push(h[0]);
    return { type: 'Feature', properties: { status: f.properties.status, priv: f.properties.priv, block: f.properties.block || f.properties.id || '', fc: f.properties.fc || '' }, geometry: { type: 'Polygon', coordinates: [h] } };
  }) };
}
/* 지구 밖을 살짝 어둡게 하는 마스크: 넓은 사각형에서 지구 경계를 구멍으로 뺀다. */
function maskGeoJSON() {
  const holes = DISTRICTS.map((d) => [...d.poly, d.poly[0]]);
  return { type: 'Feature', properties: {}, geometry: { type: 'Polygon', coordinates: [[[120, 30], [135, 30], [135, 45], [120, 45], [120, 30]], ...holes] } };
}
/* 주변 맥락(OpenStreetMap): 역 반경 원, 역, 학교 */
const CTX = window.GY_CONTEXT, HAS_CTX = !!(CTX && ((CTX.stations || []).length || (CTX.schools || []).length));   // 역이 없어도 학교만 있으면 쓴다
const distM = (a, b) => { const R = 6371008.8, r = Math.PI / 180, dl = (b[1] - a[1]) * r, dn = (b[0] - a[0]) * r; const h = Math.sin(dl / 2) ** 2 + Math.cos(a[1] * r) * Math.cos(b[1] * r) * Math.sin(dn / 2) ** 2; return 2 * R * Math.asin(Math.sqrt(h)); };
const distTxt = (d) => (d < 1000 ? `약 ${Math.round(d / 10) * 10} m` : `약 ${(d / 1000).toFixed(1)} km`);
function nearestCtx(pt) {
  const best = (arr) => arr.map((s) => ({ name: s.name, d: distM(pt, [s.lon, s.lat]) })).sort((a, b) => a.d - b.d)[0];
  return { st: (CTX.stations || []).length ? best(CTX.stations) : null, sch: CTX.schools && CTX.schools.length ? best(CTX.schools) : null };
}
function ctxGeoJSON() {
  const ring = (s, rM) => { const pts = [], dl = rM / 111320, dn = rM / (111320 * Math.cos(s.lat * Math.PI / 180)); for (let i = 0; i <= 72; i++) { const a = i / 72 * Math.PI * 2; pts.push([s.lon + Math.cos(a) * dn, s.lat + Math.sin(a) * dl]); } return pts; };
  const pt = (s) => ({ type: 'Feature', properties: { name: s.name }, geometry: { type: 'Point', coordinates: [s.lon, s.lat] } });
  return {
    st: { type: 'FeatureCollection', features: (CTX.stations || []).map(pt) },
    sch: { type: 'FeatureCollection', features: (CTX.schools || []).map(pt) },
    ring: { type: 'FeatureCollection', features: (CTX.stations || []).flatMap((s) => [[500, '500 m'], [1000, '1 km']].map(([r, label]) => ({ type: 'Feature', properties: { label }, geometry: { type: 'LineString', coordinates: ring(s, r) } }))) },
  };
}

/* 입주 전 기반시설(infra.json): 신설예정 학교·학교 부지·전기 시설·정류장·초등 통학구역. 자료가 없는 지역에는 아무것도 만들지 않는다.
   점검 문구와 거리 계산은 InfraLib(assets/js/infra.js). 도시계획시설의 '집행' 표기는 건립 여부와 맞지 않아 싣지 않는다. */
const INFRA = window.GY_INFRA || null, IL = window.InfraLib, FL = window.FacilityLib;
/* 기존 건물 중 기반시설(학교·병원·공공·복지): 건물 속성 fc 에 분류를 남기고(색·팝업), 이름 있는 것은 라벨 점으로 모은다 */
let FAC = HAS_GY && FL ? FL.annotate(GY.features) : { count: { edu: 0, med: 0, pub: 0 }, points: { type: 'FeatureCollection', features: [] } };
const HAS_FAC = DYN_ON || FAC.count.edu + FAC.count.med + FAC.count.pub > 0;   // 요청 시 조회하면 나중에 생기므로 레이어를 미리 만든다
const HAS_INFRA = !!(INFRA && IL && HAS_PR && ['schools', 'zones', 'stops', 'sites', 'permits', 'measures', 'attendance'].some((k) => (INFRA[k] || []).length));
if (viewMode === 'infra' && !HAS_INFRA) viewMode = 'floors';
const INFRA_PICKS = ['infra-school', 'infra-site-ic', 'infra-stop', 'infra-site-fill'];
const INFRA_LAYERS = ['infra-site-fill', 'infra-site-line', 'infra-site-dash', 'infra-site-ic', 'infra-site-label', 'infra-stop', 'infra-school', 'infra-school-label', 'infra-link-new', 'infra-link-new-label'];
const INFRA_MODE_LAYERS = ['infra-link-zone', 'infra-link-zone-label', 'infra-ring-fill', 'infra-ring-line', 'infra-ring-label'];   // '기반시설' 보기에서만
const ZONE_LAYERS = ['infra-zone-fill', 'infra-zone-line', 'infra-zone-label'];
const infraSrcText = (ids) => { const lab = {}; (INFRA.sources || []).forEach((x) => { lab[x.id] = x.label; }); return (ids || []).map((i) => lab[i] || i).join(' · '); };
const safeUrl = (u) => (/^https?:\/\//i.test(String(u || '')) ? String(u) : null);   // 출처 링크는 http(s)만
function circleRing(c, rM) {   // 중심에서 반경 rM 미터의 원(72각형)
  const dl = rM / 111320, dn = rM / (111320 * Math.cos(c[1] * Math.PI / 180)), out = [];
  for (let i = 0; i < 72; i++) { const a = i / 72 * Math.PI * 2; out.push([c[0] + Math.cos(a) * dn, c[1] + Math.sin(a) * dl]); }
  return out;
}
function infraGeoJSON() {
  const fc = (features) => ({ type: 'FeatureCollection', features });
  const pol = (properties, ring) => ({ type: 'Feature', properties, geometry: { type: 'Polygon', coordinates: [[...ring, ring[0]]] } });
  const pt = (properties, c) => ({ type: 'Feature', properties, geometry: { type: 'Point', coordinates: c } });
  const sites = [], pts = [], stops = [], zones = [], zpts = [], spts = [], links = [], lpts = [], rings = [];
  (INFRA.schools || []).forEach((s) => {
    const sched = s.status === '신설예정';
    if (s.poly) sites.push(pol({ id: s.id, kind: 'school', cat: sched ? 'edu-new' : 'edu-site', name: s.name }, s.poly));
    pts.push(pt({ id: s.id, kind: 'school', status: s.status, name: s.name, label: sched ? `${IL.shortName(s.name)}\n${IL.fmtYm(s.openYm)} 개교 예정` : `${s.level} 부지\n일정 미공시` }, [s.lon, s.lat]));
  });
  (INFRA.sites || []).forEach((s) => {
    const cat = s.category === '전기' ? 'power' : s.category === '교통' ? 'transit' : 'other';
    sites.push(pol({ id: s.id, kind: 'site', cat, name: s.name }, s.poly));
    if (cat !== 'other') spts.push(pt({ id: s.id, kind: 'site', cat, name: s.name, label: s.name }, IL.centroid(s.poly)));
  });
  IL.connectors(BLOCKS, INFRA, CTX).forEach((c) => {
    const pr = { kind: c.kind, level: c.level, pid: c.pid, label: c.label };
    links.push({ type: 'Feature', properties: pr, geometry: { type: 'LineString', coordinates: [c.from, c.to] } });
    lpts.push(pt(pr, [c.from[0] + (c.to[0] - c.from[0]) * 0.68, c.from[1] + (c.to[1] - c.from[1]) * 0.68]));   // 글자는 학교 쪽에 둔다(단지 표지에 덜 가림)
  });
  BLOCKS.forEach((b) => {
    const c = IL.centroid(b.poly), n = (INFRA.stops || []).filter((s) => IL.distM(c, [s.lon, s.lat]) <= IL.STOP_M).length;
    rings.push(pol({ pid: b.pid, empty: n === 0 }, circleRing(c, IL.STOP_M)));
    rings.push(pt({ pid: b.pid, empty: n === 0, text: n ? `정류장 ${n}곳` : '▲ 정류장 없음' }, [c[0], c[1] - IL.STOP_M / 111320]));
  });
  (INFRA.stops || []).forEach((s) => stops.push(pt({ name: s.name, id: s.id || '' }, [s.lon, s.lat])));
  (INFRA.zones || []).forEach((z) => { zones.push(pol({ id: z.id, name: z.name }, z.poly)); zpts.push(pt({ text: `${z.school} 통학구역` }, IL.centroid(z.poly))); });
  return { sites: fc(sites), pts: fc(pts), stops: fc(stops), zones: fc(zones), zpts: fc(zpts), spts: fc(spts), links: fc(links), lpts: fc(lpts), rings: fc(rings) };
}
const INFRA_GJ = HAS_INFRA ? infraGeoJSON() : null;
/* 버스 노선·위치: 노선(번들의 busRoutes, 정류소를 이은 선)은 정적이고, 위치는 서버 중계(/api/bus)를 서버가 알려 준 간격 이상으로만 불러 3D 로 그린다.
   방향·3D 면·보간은 BusLib(assets/js/bus.js). 위치는 몇 십 초 전 값일 수 있어 '실시간'이라 하지 않는다. 중계 함수가 없거나 키가 없으면(404·405·503) 다시 부르지 않고 노선 선만 보인다. */
const BL = window.BusLib;
const LIVE_ROUTES = HAS_INFRA && BL ? (INFRA.busRoutes || []).filter((r) => r.live && Array.isArray(r.path) && r.path.length > 1) : [];
const HAS_BUS = LIVE_ROUTES.length > 0 && !!REG.slug;
const EMPTY_FC = () => ({ type: 'FeatureCollection', features: [] });
const BUS = { cur: [], prev: [], shown: [], scale: 0, at: null, ttl: 60, failures: 0, off: false, loading: false, cooldownUntil: 0, raf: 0, solids: EMPTY_FC(), labels: EMPTY_FC() };
const BUS_ROUTES_GJ = { type: 'FeatureCollection', features: LIVE_ROUTES.map((r) => ({ type: 'Feature', properties: { id: r.id, no: r.no, c: BL.routeColor(r.type) }, geometry: { type: 'LineString', coordinates: r.path } })) };
const BUS_LAYERS = ['bus-route-line', 'bus-route-label', 'bus-3d', 'bus-label'], BUS_TWEEN_MS = 1200;
const IS_LOCAL = /^(localhost|127\.0\.0\.1|\[::1\])$/.test(location.hostname);   // 로컬에서만 해결 방법(개발 서버)을 화면에 적는다
const SUMM = HAS_INFRA ? IL.summarize(BLOCKS, INFRA, CTX) : null, SUMM_BY = new Map(SUMM ? SUMM.blocks.map((x) => [x.id, x]) : []);
const LVL_MARK = { warn: '▲', info: '●', none: '○' }, LVL_WORD = { warn: '주의', info: '참고', none: '자료 없음' };
/* 단지 표지·요약에 붙는 작은 신호 칩: 교육 ▲ · 교통 ● · 전기 ● (색만으로 구분하지 않게 기호와 글자를 함께) */
const chipsOf = (b, all) => { const x = SUMM_BY.get(b.id); return x ? Object.keys(IL.GROUP_NAMES).filter((g) => x.levels[g] && (all || x.levels[g] === 'warn')).map((g) => `<em class="hc ${x.levels[g]}" title="${IL.GROUP_NAMES[g]} ${LVL_WORD[x.levels[g]]}"><u>${LVL_MARK[x.levels[g]]}</u>${IL.GROUP_NAMES[g]}</em>`).join('') : ''; };
function infraSumHtml() {
  if (!SUMM || !SUMM.blocks.length) return '';
  const chips = Object.keys(IL.GROUP_NAMES).map((g) => [g, SUMM.byCat[g]]).filter(([, c]) => c.warn + c.info + c.none)
    .map(([g, c]) => { const lv = c.warn ? 'warn' : c.info ? 'info' : 'none'; return `<em class="hc ${lv}"><u>${LVL_MARK[lv]}</u>${IL.GROUP_NAMES[g]}${c.warn ? ` ${c.warn}` : ''}</em>`; }).join('');
  return `<span class="isum-h">입주 전 점검</span><span class="isum-t">${esc(SUMM.headline)}</span><span class="isum-c">${chips}</span><span class="isum-go">기반시설 보기 ›</span>`;
}

/* V-World 래스터 배경에는 지명이 없어 OpenFreeMap(OSM) 벡터 타일의 지명·도로명만 얹는다. 글자가 지형에 휘지 않고 곧게 선다.
   OpenFreeMap 스타일 JSON을 실행 때마다 받지 않으려고, 쓰는 층 6개의 정의만 여기에 내장했다(2026-10 positron 스타일에서 추려 글꼴·간격만 손봄).
   나라·도·시 이름, 물 이름은 지도를 11단계 아래로 줄일 수 없게 해서 쓰지 않는다. */
const OFM_LABELS = [{"id":"highway-name-major","source-layer":"transportation_name","minzoom":13.5,"filter":["match",["get","class"],["primary","secondary","tertiary","trunk"],true,false],"layout":{"symbol-placement":"line","text-field":["case",["has","name:nonlatin"],["concat",["get","name:latin"]," ",["get","name:nonlatin"]],["coalesce",["get","name_en"],["get","name"]]],"text-font":["Noto Sans Regular"],"text-rotation-alignment":"map","text-size":11,"symbol-spacing":900}},{"id":"highway-name-minor","source-layer":"transportation_name","minzoom":16.2,"filter":["all",["match",["geometry-type"],["LineString","MultiLineString"],true,false],["match",["get","class"],["minor","service","track"],true,false]],"layout":{"symbol-placement":"line","text-field":["case",["has","name:nonlatin"],["concat",["get","name:latin"]," ",["get","name:nonlatin"]],["coalesce",["get","name_en"],["get","name"]]],"text-font":["Noto Sans Regular"],"text-rotation-alignment":"map","text-size":11,"symbol-spacing":900}},{"id":"highway-name-path","source-layer":"transportation_name","minzoom":17,"filter":["==",["get","class"],"path"],"layout":{"symbol-placement":"line","text-field":["case",["has","name:nonlatin"],["concat",["get","name:latin"]," ",["get","name:nonlatin"]],["coalesce",["get","name_en"],["get","name"]]],"text-font":["Noto Sans Regular"],"text-rotation-alignment":"map","text-size":11,"symbol-spacing":900}},{"id":"label_other","source-layer":"place","minzoom":8,"filter":["match",["get","class"],["city","continent","country","state","town","village"],false,true],"layout":{"text-field":["case",["has","name:nonlatin"],["concat",["get","name:latin"],"\n",["get","name:nonlatin"]],["coalesce",["get","name_en"],["get","name"]]],"text-font":["Noto Sans Regular"],"text-letter-spacing":0.1,"text-max-width":9,"text-size":["interpolate",["linear"],["zoom"],8,9,12,10]}},{"id":"label_village","source-layer":"place","minzoom":9,"filter":["==",["get","class"],"village"],"layout":{"text-anchor":"bottom","text-field":["case",["has","name:nonlatin"],["concat",["get","name:latin"],"\n",["get","name:nonlatin"]],["coalesce",["get","name_en"],["get","name"]]],"text-font":["Noto Sans Regular"],"text-max-width":8,"text-size":["interpolate",["exponential",1.2],["zoom"],7,10,11,12]}},{"id":"label_town","source-layer":"place","minzoom":6,"filter":["==",["get","class"],"town"],"layout":{"text-anchor":"bottom","text-field":["case",["has","name:nonlatin"],["concat",["get","name:latin"],"\n",["get","name:nonlatin"]],["coalesce",["get","name_en"],["get","name"]]],"text-font":["Noto Sans Regular"],"text-max-width":8,"text-size":["interpolate",["exponential",1.2],["zoom"],7,12,11,14]}}];
function addOfmLabels() {
  if (!map.getStyle()) return;
  const T = TH();
  if (!map.getSource('ofm')) map.addSource('ofm', { type: 'vector', url: 'https://tiles.openfreemap.org/planet' });
  const before = map.getLayer('blk-label-lo') ? 'blk-label-lo' : undefined;
  for (const l of OFM_LABELS) {
    const id = 'ofm-' + l.id; if (map.getLayer(id)) continue;
    map.addLayer({ ...l, id, type: 'symbol', source: 'ofm', layout: { ...l.layout, 'text-field': ['coalesce', ['get', 'name:ko'], ['get', 'name']] },
      paint: { 'text-color': T.sub, 'text-halo-color': T.halo, 'text-halo-width': 2 } }, before);
  }
}
/* 기존 건물 색(장식): 높이 램프 + 용도 색조 + 연식 + 동마다 ±4.5% 명도 흔들림.
   색조는 용도·연식을 '참고로' 비춘 것이고 높이의 뜻(진할수록 높음)을 바꾸지 않을 만큼만 준다. 건물마다 4가지 색을
   미리 계산해 속성에 넣는다: c 벽, cr 지붕. */
const ROOF_T = 0.8;   // 지붕 층 두께(m). 벽은 그만큼 낮추고 그 위에 밝은 얇은 층을 얹는다.
const USE_TINT = [[/공동주택|단독주택|숙박/, [7, 1, -8], 1], [/근린생활|판매|업무|문화|운동/, [-5, 0, 6], 1], [/공장|창고|위험물|자동차/, [-5, -5, -3], 0.95], [/교육|의료|노유자|종교|수련/, [-3, 4, -1], 1], [/동.식물|농/, [-5, 5, -6], 1]];
function paintBuildings() {
  if (!HAS_GY) return;
  const T = TH(), flat = hex2(T.flat);
  const stops = [[3, T.ramp[0]], [12, T.ramp[1]], [25, T.ramp[2]], [45, T.ramp[3]], [70, T.ramp[4]]].map(([h, c]) => [h, hex2(c)]);
  const mix = (a, b, t) => a.map((v, i) => v + (b[i] - v) * t);
  const hexOf = (c) => '#' + c.map((v) => Math.max(0, Math.min(255, Math.round(v))).toString(16).padStart(2, '0')).join('');
  const rampAt = (eh) => { if (eh <= stops[0][0]) return stops[0][1]; for (let i = 1; i < stops.length; i++) if (eh <= stops[i][0]) { const [h0, c0] = stops[i - 1], [h1, c1] = stops[i]; return mix(c0, c1, (eh - h0) / (h1 - h0)); } return stops[stops.length - 1][1]; };
  GY.features.forEach((f, i) => {
    const p = f.properties, unknown = p.src === '정보없음', fac = p.fc && T.fac[p.fc];
    let c = fac ? hex2(fac.c) : unknown ? flat.slice() : rampAt(p.eh);
    if (!unknown && !fac) {
      const t = USE_TINT.find(([re]) => re.test(p.u || ''));
      if (t) c = c.map((v, j) => v + t[1][j]).map((v) => v * t[2]);
      if (p.a && p.a < 1990) c = mix(c, [150, 146, 140], 0.2); else if (p.a && p.a >= 2010) c = mix(c, [255, 255, 255], 0.12);   // 오래된 건물은 칙칙하게, 새 건물은 산뜻하게
    }
    const j = (((i * 2654435761) >>> 0) % 1000) / 1000 - 0.5; c = c.map((v) => v * (1 + j * (fac ? 0.04 : unknown ? 0.04 : 0.09)));
    const cr = mix(c, [255, 255, 255], 0.26);
    p.c = hexOf(c); p.cr = hexOf(cr);
  });
}
/* 기존 건물 그림자: 북서 해 기준으로 높이 0.6배를 남동쪽으로 늘어뜨린 바닥 판. 3 m 이상 건물만, 확대 14.3 이상에서 처음 필요할 때 만든다
   (16,696동 · 약 5.5 MB라 시작을 느리게 하지 않으려고). 얇은 불투명도 extrusion이라 서로 겹쳐도 이중으로 어두워지지 않는다.
   평면으로만 그리는 도형(isFlat)은 그림자도 만들지 않는다. */
const shadowStyle = () => (['#000000', 0.4]);
function officialShadowData() {
  const L = []; GY.features.forEach((f) => { const p = f.properties; if (p.eh < 3 || isFlat(p)) return; const ring = f.geometry.type === 'Polygon' ? f.geometry.coordinates[0] : f.geometry.coordinates[0][0]; L.push({ type: 'Feature', properties: { h: p.eh, status: '', fc: p.fc || '' }, geometry: { type: 'Polygon', coordinates: [ring] } }); });
  return shadowGeoJSON(L);
}
function addOfficialShadows() {
  if (!HAS_GY || map.getSource('official-shadow') || !map.getLayer('official-3d')) return;
  map.addSource('official-shadow', { type: 'geojson', data: officialShadowData(), maxzoom: 16 });
  const sh = shadowStyle();
  map.addLayer({ id: 'official-shadow', type: 'fill-extrusion', source: 'official-shadow', minzoom: 14.3,
    paint: { 'fill-extrusion-color': sh[0], 'fill-extrusion-height': 0.06, 'fill-extrusion-base': 0, 'fill-extrusion-opacity': sh[1] } }, 'official-3d');
  applyOfficial();   // 흐리게가 켜져 있으면 시설 건물의 그림자만 남긴다
}
const OFFICIAL_LAYERS = ['official-far', 'official-3d', 'official-roof'];
/* 실재하는지 알 수 없는 도형은 솟게 하지 않고 평면(official-flat·official-flat-line)으로만 그린다. 둘이다:
   ① src '정보없음': 높이·층수가 모두 없는 도형. 원천(V-World 건물 레이어)에는 대장에 연결되지 않은 도형이 남아 있어 신도시(나주 혁신도시)에서는 차로·공원 위에도 놓인다.
   ② g=1: 신도시 지구 안에서 지금 있는 건물(도로명주소 건물)과 겹치지 않는 옛 건물(철거 의심). 대장 속성이 있어도 철거된 자리에 남은 것이다(tools/regiontools/existence.py, dataset.md 2.6).
   3 m 건물이나 옛 높이로 세우면 도로 위 건물처럼 보여서 입체로 주장하지 않는다. */
const KNOWN_H = ['all', ['!=', ['get', 'src'], '정보없음'], ['!=', ['get', 'g'], 1]], NO_INFO = ['any', ['==', ['get', 'src'], '정보없음'], ['==', ['get', 'g'], 1]];
const isFlat = (p) => p.src === '정보없음' || p.g === 1;   // 위 KNOWN_H·NO_INFO 와 같은 판정(속성 객체용)
const IS_FAC = ['has', 'fc'], NOT_FAC = ['!', ['has', 'fc']];   // 학교·병원·공공·복지 건물(FacilityLib 가 fc 를 붙인다)인가
const FLAT_SEL_H = 0.3;   // 평면 도형을 골랐을 때 노란 표시의 두께(m)
const BLK_FILLS = ['blk-sale', 'blk-build', 'blk-soon', 'blk-move', 'blk-plan', 'blk-priv'];
const HUD_MAXZ = 16.3;   // HUD는 이 확대 단계보다 멀리 볼 때만 보이고, 가까이에서는 지도 위 이름표가 대신한다
function kindExpr(colors) { return ['match', ['get', 'kind'], 'sale', colors.sale, 'build', colors.build, 'soon', colors.soon, 'move', colors.move, 'priv', colors.priv, colors.plan]; }
function setupCustom() {
  const T = TH(), layers = map.getStyle().layers, firstSymbol = (layers.find((l) => l.type === 'symbol') || {}).id;
  const add = (l) => { if (!map.getLayer(l.id)) map.addLayer(l, firstSymbol); };
  const empty = { type: 'FeatureCollection', features: [] };
  const src = (id, spec) => { if (!map.getSource(id)) map.addSource(id, spec); };

  /* --- 자료 --- */
  src('dem', { type: 'raster-dem', tiles: DEM_TILES, tileSize: 256, encoding: 'terrarium', maxzoom: 14,   // 원자료가 30 m급이라 14단계면 충분하고, 지명 벡터 타일(최대 14)과 맞아 경고도 없다
   
    attribution: 'Terrain: <a href="https://registry.opendata.aws/terrain-tiles/" target="_blank" rel="noopener">AWS Terrain Tiles</a> (SRTM·GMTED2010 © USGS, ETOPO1 © NOAA 등)' });
  src('dem-shade', { type: 'raster-dem', tiles: DEM_TILES, tileSize: 256, encoding: 'terrarium', maxzoom: 14 });
  src('sel', { type: 'geojson', data: empty });
  if (HAS_GY) paintBuildings();   // 건물 색 4종을 계산해 속성에 넣은 뒤 소스에 올린다(낮/밤을 바꿔 다시 불러도 새 색)
  if (HAS_GY) src('official', { type: 'geojson', data: GY, maxzoom: 16, attribution: '건물 © 국토교통부 GIS건물통합정보(V-World, CC BY 2.0 KR)' });
  if (HAS_FAC) src('fac-pts', { type: 'geojson', data: FAC.points });
  if (HAS_PR) {
    const [dg, dl] = dongsGeoJSON(); DONG_FEATS = dg.features;
    src('blocks', { type: 'geojson', data: blocksGeoJSON() });
    src('block-pts', { type: 'geojson', data: blockPointsGeoJSON() });
    src('block-fronts', { type: 'geojson', data: blockFrontsGeoJSON() });
    src('dongs', { type: 'geojson', data: dg, promoteId: 'key' });   // key(단지-동) 로 feature-state 를 단다(쌓기 연출의 동 솟기)
    src('dong-shadow', { type: 'geojson', data: shadowGeoJSON(dg.features) });
    src('dong-labels', { type: 'geojson', data: dl });
    if (DISTRICTS.length) {
      const osm = (REG.sources || []).some((s) => /OpenStreetMap/.test(s.label));
      src('district', { type: 'geojson', data: { type: 'FeatureCollection', features: DISTRICTS.map((d) => ({ type: 'Feature', properties: { name: d.name }, geometry: { type: 'Polygon', coordinates: [[...d.poly, d.poly[0]]] } })) }, ...(osm ? { attribution: '지구경계 © OpenStreetMap contributors' } : {}) });
      src('district-pt', { type: 'geojson', data: { type: 'FeatureCollection', features: DISTRICTS.map((d) => ({ type: 'Feature', properties: { name: d.name }, geometry: { type: 'Point', coordinates: districtLabelPoint(d) } })) } });
      src('district-mask', { type: 'geojson', data: maskGeoJSON() });
    }
    if (PR.otherBlocks && PR.otherBlocks.length) src('other-blocks', { type: 'geojson', data: { type: 'FeatureCollection', features: PR.otherBlocks.map((r) => ({ type: 'Feature', properties: {}, geometry: { type: 'Polygon', coordinates: [[...r, r[0]]] } })) } });
    if (!map.hasImage('hatch')) map.addImage('hatch', patternImage('hatch'), { pixelRatio: 2 });
    if (!map.hasImage('dots')) map.addImage('dots', patternImage('dots'), { pixelRatio: 2 });
    if (!map.hasImage('cross')) map.addImage('cross', patternImage('cross'), { pixelRatio: 2 });
    for (const k of ['sale', 'build', 'soon', 'move', 'priv', 'plan']) { if (!map.hasImage('bd-' + k)) { const b = badgeImage(k); map.addImage('bd-' + k, b.data, b.opts); } if (!map.hasImage('gl-' + k)) { const g = groundImage(k); map.addImage('gl-' + k, g.data, g.opts); } }
  }
  if (HAS_INFRA) for (const k of INFRA_ICONS) if (!map.hasImage('ic-' + k)) { const im = infraIcon(k); map.addImage('ic-' + k, im.data, im.opts); }
  if (HAS_CTX) { const g = ctxGeoJSON(); src('ctx-st', { type: 'geojson', data: g.st, attribution: '역·학교 © OpenStreetMap contributors' }); src('ctx-sch', { type: 'geojson', data: g.sch }); src('ctx-ring', { type: 'geojson', data: g.ring }); }
  if (HAS_INFRA) for (const [id, d] of [['infra-sites', INFRA_GJ.sites], ['infra-pts', INFRA_GJ.pts], ['infra-stops', INFRA_GJ.stops], ['infra-zone', INFRA_GJ.zones], ['infra-zone-pt', INFRA_GJ.zpts], ['infra-site-pts', INFRA_GJ.spts], ['infra-links', INFRA_GJ.links], ['infra-link-pts', INFRA_GJ.lpts], ['infra-rings', INFRA_GJ.rings]]) src(id, { type: 'geojson', data: d });
  if (RES && RES.shape) src('resolved', { type: 'geojson', data: { type: 'Feature', properties: { name: RES.name }, geometry: RES.shape } });   // 코드로 연 법정동·필지 경계
  if (HAS_BUS) { src('bus-routes', { type: 'geojson', data: BUS_ROUTES_GJ, attribution: '버스 © 국토교통부 TAGO' }); src('bus-solids', { type: 'geojson', data: BUS.solids }); src('bus-lbl', { type: 'geojson', data: BUS.labels }); }

  /* --- 지형·하늘·빛 --- */
  if (!REG.home?.isSchematicPreview) add({ id: 'hillshade-own', type: 'hillshade', source: 'dem-shade',
    paint: { 'hillshade-exaggeration': 0.3, 'hillshade-shadow-color': T.hillShadow, 'hillshade-highlight-color': T.hillHi, 'hillshade-accent-color': T.hillAcc, 'hillshade-illumination-direction': 315, 'hillshade-illumination-anchor': 'map' } });
  try { map.setSky({ 'sky-color': T.sky[0], 'horizon-color': T.sky[1], 'fog-color': T.sky[1], 'sky-horizon-blend': 0.5, 'horizon-fog-blend': 0.6, 'fog-ground-blend': 0.25 }); } catch (_) {}
  if (!REG.home?.isSchematicPreview) map.setTerrain({ source: 'dem', exaggeration: 1 });   // 1.5 → 1(2026-10-10): 30m급 표고를 과장하면 평지 단지 위 바닥 선·면이 물결처럼 휘고 움직일 때 튄다(계획서 14.3 ①). 끄는 것은 지형 입체감을 없애는 제품 결정이라 보류
  // 해는 북서쪽(315°)에서 비춘다. 지도를 돌려도 방향이 그대로이며, 언덕 음영(hillshade)과 같은 방향이다. 어두운 면이 너무 검어지지 않게 세기를 낮게 둔다.
  try { map.setLight({ anchor: 'map', position: [1.5, 315, 38], color: '#FFFFFF', intensity: 0.3 }); } catch (_) {}

  /* --- 바닥(높이를 모르는 도형, 지구 마스크, 용지, 블록, 그림자, 선택 윤곽) --- */
  if (HAS_GY) {   // 평면 도형은 가장 아래에 깔아 단지·지구 표시를 가리지 않게 한다(위 KNOWN_H·NO_INFO 설명)
    const G = T.ghost;
    add({ id: 'official-flat', type: 'fill', source: 'official', minzoom: 14, filter: NO_INFO, paint: { 'fill-color': G.fill, 'fill-opacity': G.fillOp } });
    add({ id: 'official-flat-line', type: 'line', source: 'official', minzoom: 15, filter: NO_INFO, paint: { 'line-color': G.line, 'line-opacity': G.lineOp, 'line-width': 1, 'line-dasharray': [2, 2] } });
  }
  if (HAS_PR) {
    if (DISTRICTS.length) {
      add({ id: 'district-mask', type: 'fill', source: 'district-mask', paint: { 'fill-color': T.mask[0], 'fill-opacity': T.mask[1] } });
      add({ id: 'district-line', type: 'line', source: 'district', paint: { 'line-color': T.district, 'line-width': 1.4, 'line-dasharray': [4, 3], 'line-opacity': 0.9 } });
    }
    if (PR.otherBlocks && PR.otherBlocks.length) {
      add({ id: 'other-fill', type: 'fill', source: 'other-blocks', minzoom: 13.5, paint: { 'fill-color': T.other[0], 'fill-opacity': 0.1 } });
      add({ id: 'other-line', type: 'line', source: 'other-blocks', minzoom: 13.5, paint: { 'line-color': T.other[1], 'line-width': 1.2, 'line-dasharray': [2, 2], 'line-opacity': 0.9 } });
    }
    const PAT_OP = ['interpolate', ['linear'], ['zoom'], 13.5, 0.55, 15.5, 1];   // 멀리서는 무늬를 옅게(작게 줄어든 무늬가 지글거리지 않게)
    const NP = ['!=', ['get', 'priv'], true];   // 공공택지 민간 단지는 상태 무늬 대신 회색 면(blk-priv)으로 그린다
    add({ id: 'blk-sale', type: 'fill', source: 'blocks', filter: ['all', ['==', ['get', 'status'], '분양중'], NP], paint: { 'fill-color': T.color.sale, 'fill-opacity': 0.2 } });
    add({ id: 'blk-build', type: 'fill', source: 'blocks', filter: ['all', ['==', ['get', 'status'], '건설 단계'], NP], paint: { 'fill-pattern': 'hatch', 'fill-opacity': PAT_OP } });
    add({ id: 'blk-soon', type: 'fill', source: 'blocks', filter: ['all', ['==', ['get', 'status'], '준공 임박'], NP], paint: { 'fill-pattern': 'dots', 'fill-opacity': PAT_OP } });
    add({ id: 'blk-move', type: 'fill', source: 'blocks', filter: ['all', ['==', ['get', 'status'], '입주 단계'], NP], paint: { 'fill-pattern': 'cross', 'fill-opacity': PAT_OP } });
    add({ id: 'blk-plan', type: 'fill', source: 'blocks', filter: ['all', ['==', ['get', 'status'], '계획'], NP], paint: { 'fill-color': T.color.plan, 'fill-opacity': 0.1 } });
    add({ id: 'blk-priv', type: 'fill', source: 'blocks', filter: ['==', ['get', 'priv'], true], paint: { 'fill-color': T.tone.priv[1], 'fill-opacity': 0.26 } });
    add({ id: 'blk-line', type: 'line', source: 'blocks', filter: ['!=', ['get', 'kind'], 'plan'], paint: { 'line-color': kindExpr(T.color), 'line-width': 2 } });
    add({ id: 'blk-line-plan', type: 'line', source: 'blocks', filter: ['==', ['get', 'kind'], 'plan'], paint: { 'line-color': T.color.plan, 'line-width': 2, 'line-dasharray': [3, 2] } });
    add({ id: 'dong-shadow', type: 'fill', source: 'dong-shadow', paint: { 'fill-color': T.shadow[0], 'fill-opacity': T.shadow[1] } });
    add({ id: 'dong-line', type: 'line', source: 'dongs', paint: { 'line-color': T.dong, 'line-width': 1, 'line-dasharray': [2, 2], 'line-opacity': ['step', ['zoom'], 0, 15.6, 0.75] } });   // minzoom 대신 투명도 단계: 숨은 층이 있으면 지형 바닥 텍스처가 매 프레임 무효가 된다(계획서 14.3 ③)
  }
  if (HAS_INFRA) {
    const E = T.infra.edu, siteColor = ['match', ['get', 'cat'], 'edu-new', E, 'edu-site', E, 'power', T.infra.power, 'transit', T.infra.transit, T.sub];
    add({ id: 'infra-ring-fill', type: 'fill', source: 'infra-rings', filter: ['==', ['geometry-type'], 'Polygon'], layout: { visibility: 'none' }, paint: { 'fill-color': ['case', ['get', 'empty'], T.infra.warn, T.infra.transit], 'fill-opacity': ['case', ['get', 'empty'], 0.12, 0.04] } });
    add({ id: 'infra-ring-line', type: 'line', source: 'infra-rings', filter: ['==', ['geometry-type'], 'Polygon'], layout: { visibility: 'none' }, paint: { 'line-color': ['case', ['get', 'empty'], T.infra.warn, T.infra.transit], 'line-width': 1.8, 'line-dasharray': [2, 2], 'line-opacity': 0.95 } });
    add({ id: 'infra-zone-fill', type: 'fill', source: 'infra-zone', layout: { visibility: 'none' }, paint: { 'fill-color': E, 'fill-opacity': 0.05 } });
    add({ id: 'infra-zone-line', type: 'line', source: 'infra-zone', layout: { visibility: 'none' }, paint: { 'line-color': E, 'line-width': 1.8, 'line-dasharray': [5, 3], 'line-opacity': 0.9 } });
    add({ id: 'infra-site-fill', type: 'fill', source: 'infra-sites', layout: { visibility: 'none' }, paint: { 'fill-color': siteColor, 'fill-opacity': ['match', ['get', 'cat'], 'edu-new', 0.3, 'edu-site', 0.12, 'transit', 0.14, 0.28] } });
    add({ id: 'infra-site-line', type: 'line', source: 'infra-sites', filter: ['!=', ['get', 'cat'], 'edu-site'], layout: { visibility: 'none' }, paint: { 'line-color': siteColor, 'line-width': 2.8 } });
    add({ id: 'infra-site-dash', type: 'line', source: 'infra-sites', filter: ['==', ['get', 'cat'], 'edu-site'], layout: { visibility: 'none' }, paint: { 'line-color': E, 'line-width': 2.4, 'line-dasharray': [3, 2] } });
  }
  if (HAS_CTX) add({ id: 'ctx-ring', type: 'line', source: 'ctx-ring', layout: { visibility: 'none' }, paint: { 'line-color': T.sub, 'line-width': 1.2, 'line-dasharray': [2, 2], 'line-opacity': 0.85 } });
  if (RES && RES.shape) {
    add({ id: 'resolved-fill', type: 'fill', source: 'resolved', paint: { 'fill-color': '#FF8A65', 'fill-opacity': RES.type === 'pnu' || RES.parcel ? 0.28 : 0.07 } });
    add({ id: 'resolved-halo', type: 'line', source: 'resolved', paint: { 'line-color': T.halo, 'line-width': 7, 'line-opacity': 0.9 } });
    add({ id: 'resolved-line', type: 'line', source: 'resolved', paint: { 'line-color': '#FF8A65', 'line-width': 3, 'line-dasharray': RES.type === 'pnu' || RES.parcel ? [1, 0] : [3, 2] } });
  }
  add({ id: 'sel-line-halo', type: 'line', source: 'sel', paint: { 'line-color': T.halo, 'line-width': 7, 'line-opacity': 0.9 } });
  add({ id: 'sel-line', type: 'line', source: 'sel', paint: { 'line-color': '#FFFFFF', 'line-width': 3 } });

  if (HAS_GY) {
    // '기존 건물 흐리게'(기본): 시설이 아닌 건물은 채우지 않은 점선 윤곽만(확대 15 이상, 그보다 멀리서는 그리지 않는다). 윤곽은 클릭할 수 없어 보이지 않는 면(official-hit)이 클릭을 받는다.
    // 지구 밖 마스크·단지 면에 가려 흐려지지 않게 입체 층 바로 앞에 둔다.
    const G = T.ghost;
    add({ id: 'official-outline', type: 'line', source: 'official', minzoom: 15, filter: NOT_FAC, layout: { visibility: 'none' }, paint: { 'line-color': G.line, 'line-opacity': G.lineOp, 'line-width': 1, 'line-dasharray': [2, 2] } });
    add({ id: 'official-hit', type: 'fill', source: 'official', minzoom: 15, filter: NOT_FAC, layout: { visibility: 'none' }, paint: { 'fill-color': '#000000', 'fill-opacity': 0 } });
  }
  /* --- 입체(선택, 기존 건물, 동) --- */
  add({ id: 'sel-3d', type: 'fill-extrusion', source: 'sel', paint: { 'fill-extrusion-color': ['get', 'c'], 'fill-extrusion-height': ['get', 'eh'], 'fill-extrusion-base': 0, 'fill-extrusion-opacity': 0.97 } });
  if (HAS_GY) {
    // 멀리(12~14)서는 10 m 이상만(6,586동), 가까이(14~)서는 전부. 벽은 지붕 두께만큼 낮추고 지붕 층을 따로 그린다. 높이를 모르는 도형(정보없음)은 솟지 않는 평면 + 점선.
    const ao = ['#000000', 0.5];
    add({ id: 'official-far', type: 'fill-extrusion', source: 'official', minzoom: 12, maxzoom: 14, filter: ['all', ['>=', ['get', 'eh'], 10], KNOWN_H],
      paint: { 'fill-extrusion-color': ['get', 'c'], 'fill-extrusion-height': ['get', 'eh'], 'fill-extrusion-base': 0, 'fill-extrusion-opacity': 1 } });
    // 건물 아래 바닥이 살짝 어두워지는 접지 음영(의사 AO)
    add({ id: 'official-ao', type: 'line', source: 'official', minzoom: 15, filter: KNOWN_H,
      paint: { 'line-color': ao[0], 'line-opacity': ao[1], 'line-width': ['interpolate', ['exponential', 2], ['zoom'], 15, 2, 18, 14], 'line-blur': ['interpolate', ['linear'], ['zoom'], 15, 2, 18, 8] } });
    add({ id: 'official-3d', type: 'fill-extrusion', source: 'official', minzoom: 14, filter: KNOWN_H,
      paint: { 'fill-extrusion-color': ['get', 'c'], 'fill-extrusion-height': ['max', 0.5, ['-', ['get', 'eh'], ROOF_T]], 'fill-extrusion-base': 0, 'fill-extrusion-opacity': 1 } });
    add({ id: 'official-roof', type: 'fill-extrusion', source: 'official', minzoom: 14, filter: KNOWN_H,
      paint: { 'fill-extrusion-color': ['get', 'cr'], 'fill-extrusion-base': ['max', 0.5, ['-', ['get', 'eh'], ROOF_T]], 'fill-extrusion-height': ['max', 1.3, ['get', 'eh']], 'fill-extrusion-opacity': 1 } });
  }
  if (HAS_PR) {
    add({ id: 'dong-3d', type: 'fill-extrusion', source: 'dongs', paint: { 'fill-extrusion-color': ['get', 'color'], 'fill-extrusion-height': ['get', 'h'], 'fill-extrusion-base': 0, 'fill-extrusion-opacity': 1 } });
    // 멀리서 볼 때는 단지를 점(세대수만큼 크기)으로 보여 준다.
    add({ id: 'blk-dot', type: 'circle', source: 'block-pts', maxzoom: 14.3,
      paint: { 'circle-radius': ['interpolate', ['linear'], ['get', 'units'], 300, 7, 800, 12], 'circle-color': kindExpr(T.color), 'circle-stroke-color': T.halo, 'circle-stroke-width': 2, 'circle-opacity': ['interpolate', ['linear'], ['zoom'], 13.6, 0.95, 14.3, 0] } });
  }
  if (HAS_INFRA) {
    const E = T.infra.edu, newS = ['==', ['get', 'status'], '신설예정'], W = T.infra.warn, warn = ['==', ['get', 'level'], 'warn'];
    const ICON_SZ = ['interpolate', ['linear'], ['zoom'], 13.2, 0.62, 15, 0.82, 17, 1.02];       // 멀리서도 읽히고 가까이서 커지지 않게
    // 단지 → 가까운 신설 학교 연결선(주의는 굵은 갈색 점선, 참고는 보라 점선), '기반시설' 보기에서는 배정 통학구역 학교로 가는 가는 회색 선도
    add({ id: 'infra-link-zone', type: 'line', source: 'infra-links', filter: ['==', ['get', 'kind'], 'zone'], layout: { visibility: 'none' }, paint: { 'line-color': T.sub, 'line-width': 1.6, 'line-opacity': 0.9 } });
    add({ id: 'infra-link-new', type: 'line', source: 'infra-links', filter: ['==', ['get', 'kind'], 'new'], layout: { visibility: 'none', 'line-cap': 'butt' }, paint: { 'line-color': ['case', warn, W, E], 'line-width': ['case', warn, 3.2, 2.2], 'line-dasharray': [2, 1.4], 'line-opacity': 0.97 } });
    add({ id: 'infra-stop', type: 'symbol', source: 'infra-stops', minzoom: 15.2, layout: { visibility: 'none', 'icon-image': 'ic-bus', 'icon-size': ['interpolate', ['linear'], ['zoom'], 15.2, 0.42, 17, 0.62], 'icon-allow-overlap': true, 'icon-ignore-placement': true } });
    add({ id: 'infra-site-ic', type: 'symbol', source: 'infra-site-pts', minzoom: 13.2, layout: { visibility: 'none', 'icon-image': ['match', ['get', 'cat'], 'power', 'ic-power', 'ic-garage'], 'icon-size': ICON_SZ, 'icon-allow-overlap': true, 'icon-ignore-placement': true } });
    add({ id: 'infra-school', type: 'symbol', source: 'infra-pts', minzoom: 13.2, layout: { visibility: 'none', 'icon-image': ['case', newS, 'ic-edu-new', 'ic-edu-site'], 'icon-size': ICON_SZ, 'icon-allow-overlap': true, 'icon-ignore-placement': true } });
  }
  if (HAS_BUS) {   // 노선 선(정류소를 이은 선) 위에 3D 버스(차체+창띠). 버스는 눈에 띄도록 BusLib.BUS_SCALE 배로 그린다
    add({ id: 'bus-route-line', type: 'line', source: 'bus-routes', minzoom: 13.2, layout: { visibility: 'none', 'line-cap': 'round', 'line-join': 'round' }, paint: { 'line-color': ['get', 'c'], 'line-width': ['interpolate', ['linear'], ['zoom'], 13.2, 1.4, 17, 3.2], 'line-opacity': 0.5 } });
    add({ id: 'bus-3d', type: 'fill-extrusion', source: 'bus-solids', minzoom: 13.8, layout: { visibility: 'none' }, paint: { 'fill-extrusion-color': ['get', 'c'], 'fill-extrusion-base': ['get', 'base'], 'fill-extrusion-height': ['get', 'h'], 'fill-extrusion-opacity': 1 } });
  }
  if (HAS_CTX) {
    add({ id: 'ctx-school', type: 'circle', source: 'ctx-sch', minzoom: 14.8, layout: { visibility: 'none' }, paint: { 'circle-radius': 4.5, 'circle-color': T.sub, 'circle-stroke-color': T.halo, 'circle-stroke-width': 1.6 } });
    add({ id: 'ctx-station', type: 'circle', source: 'ctx-st', layout: { visibility: 'none' }, paint: { 'circle-radius': 7, 'circle-color': '#FFFFFF', 'circle-stroke-color': T.halo, 'circle-stroke-width': 3 } });
  }

  /* --- 글자 --- */
  if (HAS_PR) {
    const fontLayer = layers.find((l) => l.type === 'symbol' && l.layout && l.layout['text-font']);
    const font = fontLayer ? fontLayer.layout['text-font'] : ['Noto Sans Regular'];
    const sym = (l) => { if (!map.getLayer(l.id)) map.addLayer({ ...l, layout: { 'text-font': font, ...l.layout } }); };
    const badgeIcon = ['match', ['get', 'kind'], 'sale', 'gl-sale', 'build', 'gl-build', 'soon', 'gl-soon', 'move', 'gl-move', 'priv', 'gl-priv', 'gl-plan'];
    sym({ id: 'blk-label-lo', type: 'symbol', source: 'block-pts', maxzoom: 14.3,
      layout: { 'text-field': ['get', 'short'], 'text-size': 13, 'text-allow-overlap': false, 'text-variable-anchor': ['top', 'bottom', 'left', 'right'], 'text-radial-offset': 1.1, 'symbol-sort-key': ['-', 0, ['get', 'units']] },
      paint: { 'text-color': T.text, 'text-halo-color': T.halo, 'text-halo-width': 2 } });
    // 지면 라벨: 단지 앞쪽 땅 위(건물에 겹치지 않는 곳)에 14.3~16.6은 두세 줄(이름·세대수 / 보기별 한 줄·가까운 역 / 주의), 그보다 가까우면 한 줄로. 글자색은 보통 글자, 주의만 갈색.
    sym({ id: 'blk-badge', type: 'symbol', source: 'block-fronts', minzoom: 14.3, maxzoom: 16.6,
      layout: { 'icon-image': badgeIcon, 'icon-text-fit': 'both', 'icon-text-fit-padding': [2, 5, 2, 5], 'icon-allow-overlap': false, 'text-allow-overlap': false, 'symbol-sort-key': ['-', 0, ['get', 'units']],
        'text-variable-anchor': ['top', 'top-left', 'top-right', 'left', 'right'], 'text-radial-offset': 0.35,   // 이웃한 라벨과 겹치면 옆으로 비켜 선다
        'text-field': groundText(false), 'text-size': 13, 'text-justify': 'left', 'text-max-width': 24 },
      paint: { 'text-color': T.text } });
    sym({ id: 'blk-badge-top', type: 'symbol', source: 'block-fronts', minzoom: 16.6,
      layout: { 'icon-image': badgeIcon, 'icon-text-fit': 'both', 'icon-text-fit-padding': [1, 5, 1, 5], 'icon-allow-overlap': true, 'text-allow-overlap': true,
        'text-field': groundText(true), 'text-size': 12.5, 'text-anchor': 'top', 'text-offset': [0, 0.4], 'text-max-width': 40 },
      paint: { 'text-color': T.text } });
    // 동 이름표: 모든 동에 "602동 15층"처럼 번호와 층수를 보인다(확대 16.6부터).
    const dongPaint = { 'text-color': T.text, 'text-halo-color': T.halo, 'text-halo-width': 1.8 };
    sym({ id: 'dong-label', type: 'symbol', source: 'dong-labels', minzoom: 16.6,
      layout: { 'text-field': ['get', 'text'], 'text-size': 11.5, 'text-allow-overlap': false, 'text-variable-anchor': ['top', 'bottom'], 'text-radial-offset': 0.4 }, paint: dongPaint });
    // 기존 기반시설 이름표: 이름 있는 학교·병원·공공·복지 건물만. 같은 이름은 가장 큰 한 동에만, 확대 15.2부터. 글자색은 건물 강조색의 진한 변형.
    if (HAS_FAC) sym({ id: 'fac-label', type: 'symbol', source: 'fac-pts', minzoom: 15.2,
      layout: { 'text-field': ['get', 'n'], 'text-size': ['interpolate', ['linear'], ['zoom'], 15.2, 11.5, 17, 13], 'text-anchor': 'top', 'text-offset': [0, 0.5], 'text-max-width': 7, 'text-padding': 2, 'symbol-sort-key': ['-', 0, ['get', 'eh']] },
      paint: { 'text-color': ['match', ['get', 'cat'], 'edu', T.fac.edu.t, 'med', T.fac.med.t, T.fac.pub.t], 'text-halo-color': T.halo, 'text-halo-width': 2.2 } });
    if (DISTRICTS.length) sym({ id: 'district-label', type: 'symbol', source: 'district-pt', maxzoom: 14.6,
      layout: { 'text-field': ['get', 'name'], 'text-size': 13, 'text-letter-spacing': 0.08 }, paint: { 'text-color': T.sub, 'text-halo-color': T.halo, 'text-halo-width': 2 } });
    if (HAS_CTX) {
      const cp = { 'text-color': T.text, 'text-halo-color': T.halo, 'text-halo-width': 2 };
      sym({ id: 'ctx-ring-label', type: 'symbol', source: 'ctx-ring', maxzoom: 16.5, layout: { visibility: 'none', 'symbol-placement': 'line', 'symbol-spacing': 900, 'text-field': ['get', 'label'], 'text-size': 11 }, paint: { ...cp, 'text-color': T.sub } });
      sym({ id: 'ctx-station-label', type: 'symbol', source: 'ctx-st', minzoom: 11.5, layout: { visibility: 'none', 'text-field': ['get', 'name'], 'text-size': 13, 'text-anchor': 'top', 'text-offset': [0, 0.9], 'text-allow-overlap': true }, paint: cp });
      sym({ id: 'ctx-school-label', type: 'symbol', source: 'ctx-sch', minzoom: 15.6, layout: { visibility: 'none', 'text-field': ['get', 'name'], 'text-size': 11.5, 'text-anchor': 'top', 'text-offset': [0, 0.8] }, paint: { ...cp, 'text-color': T.sub } });
    }
    if (HAS_INFRA) {
      const ip = { 'text-color': T.infra.edu, 'text-halo-color': T.halo, 'text-halo-width': 2.2 }, iw = { ...ip, 'text-color': T.infra.warn };
      const warnTxt = ['case', ['==', ['get', 'level'], 'warn'], T.infra.warn, T.infra.edu];
      sym({ id: 'infra-school-label', type: 'symbol', source: 'infra-pts', minzoom: 14.2, layout: { visibility: 'none', 'text-field': ['get', 'label'], 'text-size': ['interpolate', ['linear'], ['zoom'], 14.2, 11, 16, 12.5], 'text-justify': 'center', 'text-anchor': 'top', 'text-offset': [0, 1.15], 'text-allow-overlap': false, 'text-optional': true }, paint: ip });
      sym({ id: 'infra-site-label', type: 'symbol', source: 'infra-site-pts', minzoom: 14.2, layout: { visibility: 'none', 'text-field': ['get', 'label'], 'text-size': 12, 'text-anchor': 'top', 'text-offset': [0, 1.15], 'text-allow-overlap': false }, paint: { ...ip, 'text-color': ['match', ['get', 'cat'], 'power', T.infra.power, T.text] } });
      // 연결선 글자: 학교 쪽에 거리와 개교까지의 기간. 글자는 늘 바로 선다.
      const lk = { 'text-justify': 'center', 'text-rotation-alignment': 'viewport', 'text-pitch-alignment': 'viewport', 'text-allow-overlap': false };
      sym({ id: 'infra-link-new-label', type: 'symbol', source: 'infra-link-pts', minzoom: 14.4, filter: ['==', ['get', 'kind'], 'new'], layout: { visibility: 'none', 'text-field': ['concat', ['case', ['==', ['get', 'level'], 'warn'], '▲ ', ''], ['get', 'label']], 'text-size': 11.5, ...lk }, paint: { ...iw, 'text-color': warnTxt, 'text-halo-width': 2.6 } });
      sym({ id: 'infra-link-zone-label', type: 'symbol', source: 'infra-link-pts', minzoom: 14.4, filter: ['==', ['get', 'kind'], 'zone'], layout: { visibility: 'none', 'text-field': ['get', 'label'], 'text-size': 11, ...lk }, paint: { ...ip, 'text-color': T.sub } });
      sym({ id: 'infra-ring-label', type: 'symbol', source: 'infra-rings', minzoom: 14.6, filter: ['==', ['geometry-type'], 'Point'], layout: { visibility: 'none', 'text-field': ['get', 'text'], 'text-size': 11.5, 'text-anchor': 'top', 'text-offset': [0, 0.2], 'text-allow-overlap': false }, paint: { ...ip, 'text-color': ['case', ['get', 'empty'], T.infra.warn, T.text] } });
      sym({ id: 'infra-zone-label', type: 'symbol', source: 'infra-zone-pt', minzoom: 13.5, maxzoom: 16.5, layout: { visibility: 'none', 'text-field': ['get', 'text'], 'text-size': 12, 'text-letter-spacing': 0.04, 'text-allow-overlap': false }, paint: ip });
    }
    if (HAS_BUS) {
      const bp = { 'text-color': ['get', 'c'], 'text-halo-color': T.halo, 'text-halo-width': 2.4 };
      sym({ id: 'bus-route-label', type: 'symbol', source: 'bus-routes', minzoom: 14.6, layout: { visibility: 'none', 'symbol-placement': 'line', 'symbol-spacing': 420, 'text-field': ['concat', ['get', 'no'], '번'], 'text-size': 11.5, 'text-max-angle': 30 }, paint: bp });
      sym({ id: 'bus-label', type: 'symbol', source: 'bus-lbl', minzoom: 13.8, layout: { visibility: 'none', 'text-field': ['get', 'text'], 'text-font': ['Noto Sans Bold'], 'text-size': ['interpolate', ['linear'], ['zoom'], 13.8, 11, 17, 14.5], 'text-anchor': 'bottom', 'text-offset': [0, -1.3], 'text-allow-overlap': true, 'text-ignore-placement': true }, paint: { ...bp, 'text-halo-width': 2.8 } });
    }
  }
  if (usingVworld && !REG.home?.isSchematicPreview) addOfmLabels();
  // 지형 위 바닥(2D) 선 층을 첫 3D 층(sel-3d) 앞으로 모은다: 3D 층 뒤에 끼면 바닥 그림 묶음이 쪼개져 매 프레임 다시 굽는다(계획서 14.3 ③, 2026-10-10 실측 계양 18회/프레임)
  if (map.getLayer('sel-3d')) for (const id of ['official-ao', 'infra-link-zone', 'infra-link-new', 'bus-route-line']) if (map.getLayer(id)) map.moveLayer(id, 'sel-3d');
  if (map.getZoom() >= 14.3) { if (firstIdle) map.once('idle', addOfficialShadows); else addOfficialShadows(); }   // 첫 화면이 뜬 뒤에: 건물이 많은 지역(계양 16,724동)에서 그림자 도형 계산과 두 번째 큰 GeoJSON 타일링이 로딩을 늦춘다
  applyAll();
  if (!usingVworld) for (const l of layers) if (l.type === 'symbol' && /name/.test(JSON.stringify(map.getLayoutProperty(l.id, 'text-field') || ''))) map.setLayoutProperty(l.id, 'text-field', ['coalesce', ['get', 'name:ko'], ['get', 'name']]);
}
map.on('style.load', setupCustom);
map.on('zoom', () => { if (!firstIdle && map.getZoom() >= 14.3) addOfficialShadows(); });

/* ---------- 건물 요청 시 조회(번들이 없는 지역 · 번들 밖) ----------
   GY 를 '자라는 배열'로 둔다. 지도에 보이는 0.01° 칸(약 0.9×1.1 km)을 /api/v1/buildings 로 받아 GY.features 에 붙이면
   3D·색·학교/병원 강조·그림자·선택이 기존 경로 그대로 동작한다. 번들 건물이 있으면 번들 영역(box) 안은 번들이 맡고 밖만 조회한다.
   서버가 없거나(404·405·503) 키가 없으면 더 부르지 않는다. 스펙: docs/product/상황판-스펙.md 4절(등급 B·C) */
const DYN = { on: DYN_ON, off: false, minZ: 14.6, maxCells: 12, maxFeatures: 60000, conc: 3, cells: new Map(), queue: [], inflight: 0, added: 0, failed: 0, truncated: 0, full: false, timer: 0, box: null };
function featCenter(g) {
  const ring = g && (g.type === 'Polygon' ? g.coordinates[0] : g.type === 'MultiPolygon' ? g.coordinates[0][0] : null);
  if (!ring || !ring.length) return null;
  const n = ring.length > 1 && ring[0][0] === ring[ring.length - 1][0] && ring[0][1] === ring[ring.length - 1][1] ? ring.length - 1 : ring.length;
  let x = 0, y = 0; for (let i = 0; i < n; i++) { x += ring[i][0]; y += ring[i][1]; }
  return [x / n, y / n];
}
if (DYN.on && STATIC_N) {   // 번들 건물이 차지한 영역
  let x0 = 180, y0 = 90, x1 = -180, y1 = -90;
  for (const f of GY.features) { const g = f.geometry, polys = g.type === 'Polygon' ? [g.coordinates] : g.coordinates; for (const p of polys) for (const [x, y] of p[0]) { if (x < x0) x0 = x; if (x > x1) x1 = x; if (y < y0) y0 = y; if (y > y1) y1 = y; } }
  DYN.box = [x0, y0, x1, y1];
}
const inBox = (c) => !!(DYN.box && c && c[0] >= DYN.box[0] && c[0] <= DYN.box[2] && c[1] >= DYN.box[1] && c[1] <= DYN.box[3]);
const cellInBox = (ix, iy) => !!(DYN.box && ix / 100 >= DYN.box[0] && (ix + 1) / 100 <= DYN.box[2] && iy / 100 >= DYN.box[1] && (iy + 1) / 100 <= DYN.box[3]);
function addBuildings(feats) {
  for (const f of feats) {
    if (GY.features.length >= DYN.maxFeatures) { DYN.full = true; break; }
    if (!f || !f.geometry || inBox(featCenter(f.geometry))) continue;
    const i = GY.features.length;
    f.properties.i = i; GY.features.push(f); ST.n++; ST.src[f.properties.src] = (ST.src[f.properties.src] || 0) + 1; DYN.added++;
  }
}
function flushBuildings() {   // 붙은 건물을 지도에 반영: 색 → 학교·병원 강조 → 소스 → 그림자
  DYN.timer = 0;
  const t0 = performance.now();
  paintBuildings();
  if (FL) { FAC = FL.annotate(GY.features); const s = map.getSource('fac-pts'); if (s) s.setData(FAC.points); }
  const o = map.getSource('official'); if (o) o.setData(GY);
  const sh = map.getSource('official-shadow'); if (sh) sh.setData(officialShadowData());
  $('#basis').textContent = `${BASIS} · 건물 ${fmt(GY.features.length)}동`;
  DYN.flushMs = Math.round(performance.now() - t0); DYN.flushes = (DYN.flushes || 0) + 1;   // 시험용: 반영에 걸린 시간(ms)
  updateDynHint();
}
const scheduleFlush = () => { if (!DYN.timer) DYN.timer = setTimeout(flushBuildings, 150); };
function updateDynHint() {
  const el = $('#dynHint'); if (!el) return;
  let t = '';
  if (DYN.on && !DYN.off) {
    if (map.getZoom() < DYN.minZ) t = `건물은 지도를 확대(${DYN.minZ.toFixed(1)} 이상)하면 요청 시 불러옵니다`;
    else if (DYN.inflight || DYN.queue.length) t = '건물 불러오는 중…';
    else if (DYN.full) t = `건물이 많아 ${fmt(DYN.maxFeatures)}동까지만 불러왔습니다`;
    else if (DYN.failed) t = '일부 건물을 불러오지 못했습니다(잠시 뒤 다시 시도)';
    else if (DYN.truncated) t = '건물이 아주 많은 칸은 일부만 불러왔습니다';
  } else if (DYN.on && DYN.off) t = '건물 조회 서버가 없어 건물은 보이지 않습니다';
  el.textContent = t; el.hidden = !t;
}
async function dynFetchCell(ix, iy) {
  const key = `${ix},${iy}`;
  DYN.cells.set(key, 'loading'); DYN.inflight++; updateDynHint();
  try {
    const res = await fetch(`api/v1/buildings?cell=${key}`);
    if ([404, 405, 503].includes(res.status)) { DYN.off = true; DYN.cells.delete(key); console.warn(`건물 조회: /api/v1/buildings 를 쓸 수 없습니다(${res.status}). 로컬에서는 ./run-app.sh 로 여세요.`); return; }
    if (!res.ok) throw new Error(String(res.status));
    const data = await res.json();
    if (!data || data.type !== 'FeatureCollection' || !Array.isArray(data.features)) throw new Error('shape');
    addBuildings(data.features); DYN.cells.set(key, 'done');
    if (data.meta && data.meta.truncated) DYN.truncated++;
    if (DYN.failed) DYN.failed--;
  } catch (e) { DYN.cells.set(key, Date.now() + 30000); DYN.failed++; }   // 30초 뒤 다시 시도할 수 있다
  finally { DYN.inflight--; scheduleFlush(); dynPump(); }
}
function dynPump() {
  while (!DYN.off && DYN.inflight < DYN.conc && DYN.queue.length) {
    const [ix, iy] = DYN.queue.shift(), st = DYN.cells.get(`${ix},${iy}`);
    if (st === 'done' || st === 'loading') continue;
    dynFetchCell(ix, iy);
  }
  if (!DYN.inflight && !DYN.queue.length) updateDynHint();
}
function dynLoad() {   // 지도가 멈출 때마다 보이는 칸 중 아직 없는 것을 중심에서 가까운 순으로 최대 maxCells 개
  updateDynHint();
  if (!DYN.on || DYN.off || DYN.full || map.getZoom() < DYN.minZ) return;
  const b = map.getBounds(), c = map.getCenter(), want = [];
  const ix0 = Math.floor(b.getWest() * 100), ix1 = Math.floor(b.getEast() * 100), iy0 = Math.floor(b.getSouth() * 100), iy1 = Math.floor(b.getNorth() * 100);
  if ((ix1 - ix0 + 1) * (iy1 - iy0 + 1) > 400) return;   // 비정상적으로 넓은 화면(아주 멀리 보는 기울기)은 건물이 의미 없다
  for (let ix = ix0; ix <= ix1; ix++) for (let iy = iy0; iy <= iy1; iy++) {
    const st = DYN.cells.get(`${ix},${iy}`);
    if (st === 'done' || st === 'loading' || (typeof st === 'number' && st > Date.now()) || cellInBox(ix, iy)) continue;
    want.push([ix, iy, Math.hypot((ix + 0.5) / 100 - c.lng, ((iy + 0.5) / 100 - c.lat) * 1.25)]);
  }
  want.sort((a, d) => a[2] - d[2]);
  DYN.queue = want.slice(0, DYN.maxCells).map(([ix, iy]) => [ix, iy]);
  dynPump();
}
window.getMapCenter = () => { const c = map.getCenter(); return [c.lng, c.lat]; };   // 주소 이동 입력줄이 장소 이름을 가까운 곳 먼저 찾으려고 읽는다(goto.js)
if (q.get('selftest')) window.__dyn = DYN;   // 시험용: 요청 시 조회 상태
if (DYN.on) { map.on('moveend', dynLoad); map.on('zoom', updateDynHint); map.once('idle', dynLoad); }


/* ---------- 팝업 ---------- */
const TODAY = new Date().toISOString().slice(0, 10);
const BASIS_STATIC = HAS_GY && GY.meta.basis ? String(GY.meta.basis).replace(/(\d{4})(\d\d)(\d\d)/, '$1-$2-$3') : '';
const BASIS = DYN_ON ? (BASIS_STATIC ? `${BASIS_STATIC}(번들) · 번들 밖은 ${TODAY} 조회` : `${TODAY} 조회(요청 시)`) : HAS_GY ? BASIS_STATIC : '-';
/* 카드는 건물을 가리지 않도록 건물의 오른쪽(없으면 왼쪽, 그것도 없으면 위)에 띄운다. */
const PW = 236 + 12;           // 카드 폭 + 꼬리
function bboxOf(rings, hM) {
  let x0 = Infinity, x1 = -Infinity, y0 = Infinity, y1 = -Infinity;
  for (const r of rings) for (const p of r) { const s = map.project(p); x0 = Math.min(x0, s.x); x1 = Math.max(x1, s.x); y0 = Math.min(y0, s.y); y1 = Math.max(y1, s.y); }
  const mpp = 40075016.686 * Math.cos(map.getCenter().lat * Math.PI / 180) / (512 * Math.pow(2, map.getZoom()));
  const hp = (hM || 0) / mpp * Math.sin(map.getPitch() * Math.PI / 180);   // 기울인 화면에서 건물 높이가 차지하는 세로 픽셀(근사)
  return { x0, x1, top: y0 - hp, bottom: y1 };
}
function showCard(html, rings, hM, clickX) {
  if (popup) { const o = popup; popup = null; o.remove(); }
  const H = map.getContainer().clientHeight, gap = 12, BAR = 52;
  const W = map.getContainer().clientWidth;
  const bb = bboxOf(rings, hM);
  const cy = Math.min(Math.max((bb.top + bb.bottom) / 2, 150), H - BAR - 150);
  const roomR = bb.x1 + gap + PW <= W - 8, roomL = bb.x0 - gap - PW >= 8;
  const wantL = clickX != null && clickX < (bb.x0 + bb.x1) / 2;       // 누른 건물이 단지 왼쪽에 있으면 카드도 왼쪽에
  let anchor, pt;
  if ((wantL && roomL) || (!roomR && roomL)) { anchor = 'right'; pt = [bb.x0 - gap, cy]; }
  else if (roomR) { anchor = 'left'; pt = [bb.x1 + gap, cy]; }
  else { anchor = 'bottom'; pt = [(bb.x0 + bb.x1) / 2, Math.max(bb.top - gap, 320)]; }
  popup = new maplibregl.Popup({ anchor, maxWidth: 'none', offset: [0, 0] }).setLngLat(map.unproject(pt)).setHTML(html).addTo(map);
  if (REG.home) {   // 원천 설명·연결 후보가 긴 카드도 지도 안에서 끝까지 읽을 수 있게 한다.
    const card = popup.getElement().querySelector('.pc');
    if (card) { card.style.maxHeight = `${Math.max(140, H - BAR - 136)}px`; card.style.overflowY = 'auto'; card.style.overscrollBehavior = 'contain'; card.tabIndex = 0; }
  }
  popup.on('close', () => { if (selId != null || selDong != null) select(null); });
  // 카드가 지도 위·아래 끝(하단 바 포함)을 벗어나면 세로로만 밀어 넣는다.
  const r = popup.getElement().getBoundingClientRect(), m = map.getContainer().getBoundingClientRect();
  let dy = r.top < m.top + 8 ? m.top + 8 - r.top : (r.bottom > m.bottom - BAR ? m.bottom - BAR - r.bottom : 0);
  // 오른쪽 위의 확대 묶음(.rctl)은 카드를 가리지 않게, 가로로 겹치면 그 아래로 내린다(폭을 줄이지 않는다). 공급 요약은 머리 줄로 옮겼다
  for (const o of [$('.rctl')]) {
    if (!o || o.hidden || !o.offsetParent) continue;
    const q2 = o.getBoundingClientRect();
    if (r.right > q2.left - 4 && r.left < q2.right + 4 && r.top + dy < q2.bottom + 8 && r.bottom > q2.top) dy = Math.max(dy, q2.bottom + 8 - r.top);
  }
  if (dy) popup.setOffset([0, dy]);
  say(popup.getElement().innerText.replace(/\s+/g, ' '));
}
function floorHistogram(b) {
  const h = {}; b.dongs.forEach((d) => { h[d.floors] = (h[d.floors] || 0) + 1; });
  return `<span class="pc-fl">${Object.keys(h).map(Number).sort((a, c) => c - a).map((f) => `<span>${f}층 ${h[f]}개동</span>`).join('')}</span>`;
}
const chipHtml = (cls, t) => `<span class="pc-chip ${cls}">${esc(t)}</span>`;
const dlHtml = (rows) => `<dl class="pc-dl">${rows.filter(Boolean).map(([k, v]) => `<dt>${k}</dt><dd>${v}</dd>`).join('')}</dl>`;
const ringsOf = (g) => (g.type === 'Polygon' ? [g.coordinates[0]] : g.coordinates.map((p) => p[0]));
function dongBars(b, cur) {
  const max = Math.max(...b.dongs.map((d) => d.floors)), k = kindOf(b);
  return `<div class="pc-bars" role="img" aria-label="${dongN(b)}개동 층수 비교" style="--tone:${mixTone(k, 1)}">` +
    b.dongs.slice().sort((a, c) => a.no.localeCompare(c.no)).map((d) => `<i class="${d.no === cur ? 'on' : ''}" title="${esc(d.no)}동 ${d.floors}층" style="height:${Math.round(26 * d.floors / max)}px"></i>`).join('') + '</div>';
}
function homeCandidateLinks(b) {
  if (!b.candidateIds) return '';
  return '<div class="pc-cap">' + b.candidateIds.map((id, i) => `<a href="/poc/housing-board/home-project/${encodeURIComponent(id)}">${esc(b.candidateNames?.[i] || id)} · 원천 상세</a>`).join('<br>') + '</div>';
}
function dongPopup(p, clickX) {
  const b = BLOCKS.find((x) => x.id === p.block), r = floorsRange(b);
  const same = b.dongs.filter((x) => x.floors === p.floors).length;
  const n = dongN(b);
  const rank = same === 1 && p.floors === r[1] ? `${n}개동 중 가장 높은 동` : same === 1 && p.floors === r[0] ? `${n}개동 중 가장 낮은 동` : r[0] === r[1] ? `${n}개동 모두 ${p.floors}층` : `${n}개동 중 ${same}개동이 ${p.floors}층`;
  const dnote = b.homeModelKind ? b.note : p.tier === 'schematic' ? '동 위치·높이는 근사값(10~20 m)이며, 층수는 공급 자료 기준입니다.' : '동 윤곽은 실제 건물 자료입니다. 층수·높이는 자료 기준입니다.';
  showCard(`<div class="pc">
    <div class="pc-h"><b>${esc(p.no)}동</b><span class="pc-sub">${esc(b.id)}</span>${chipHtml(KIND[b.status], b.status)}${b.priv ? chipHtml('priv', '공공택지 민간') : ''}</div>
    <div class="pc-big"><strong>${b.homeModelKind === 'SCHEMATIC' ? '가상 ' : ''}${p.floors}층</strong><span>${b.homeModelKind === 'SCHEMATIC' ? '모형 ' : ''}높이 약 ${Math.round(p.h)} m${p.hEst ? ' (추정)' : ''}</span></div>
    ${dongBars(b, p.no)}<div class="pc-cap">${rank}</div>
    ${dlHtml([b.progress ? ['단지 공정율', `${pctTxt(b.progress.rate)} <small>(${esc(b.progress.asOf)})</small>`] : null, ['입주', esc(b.moveIn)]])}
    ${homeCandidateLinks(b)}<p class="pc-foot">${esc(dnote)}</p></div>`,
    b.dongs.flatMap((x) => x.poly), floorsToHeight(r[1]), clickX);
}
const shortSchool = (n) => String(n || '').replace(/초등학교$/, '초').replace(/중학교$/, '중').replace(/고등학교$/, '고');
const ymDot = (d) => String(d || '').slice(0, 7).replace('-', '.');
function blockPopup(b, clickX) {
  const fr = floorsRange(b), hist = fr ? floorHistogram(b) : null, nr = HAS_CTX ? nearestCtx(centroid(b.poly)) : null;
  const hmax = fr ? floorsToHeight(fr[1]) : 0;
  const ck = HAS_INFRA ? IL.projectChecks(b, INFRA, CTX) : null, zr = ck && ck.edu.find((r) => r.ref && r.ref.zone), sr = ck && ck.edu.find((r) => r.ref && r.ref.school);
  /* 학교 줄: 가까운 학교가 통학구역의 학교와 같으면 한 줄로 합친다 */
  const zone = zr && zr.ref.zone, sameSch = zone && nr && nr.sch && shortSchool(zone.school) === shortSchool(nr.sch.name);
  const schoolRows = sameSch ? [['학교', `${esc(shortSchool(zone.school))} <small>통학구역 · ${IL.shortDist(nr.sch.d)}</small>`]]
    : [nr && nr.sch ? ['학교', `${esc(shortSchool(nr.sch.name))} <small>${IL.shortDist(nr.sch.d)}</small>`] : null, zone ? ['통학구역', `${esc(shortSchool(zone.school))}${zr.ref.d != null ? ` <small>${IL.shortDist(zr.ref.d)}</small>` : ''}`] : null];
  const more = [b.outlineHow, nr ? '역·학교: OpenStreetMap, 단지 중심에서 직선거리' : '', zr || sr ? '통학구역·신설예정 학교: 교육부 공개 자료(입주 전 점검)' : ''].filter(Boolean).map(esc).join('<br>');
  showCard(`<div class="pc">
    <div class="pc-h"><b>${esc(b.id)}</b><span class="pc-sub">${esc(b.kind.replace('(공공분양)', ''))}</span>${chipHtml(KIND[b.status], b.status)}${b.priv ? chipHtml('priv', '공공택지 민간') : ''}</div>
    <div class="pc-big"><strong>${unitsTxt(b)}</strong>${dongN(b) ? `<span>${b.homeModelKind === 'SCHEMATIC' ? '가상 ' : ''}${dongN(b)}개동</span>` : ''}</div>
    ${b.note ? `<div class="pc-cap">${esc(b.note)}</div>` : ''}
    ${homeCandidateLinks(b)}
    ${dlHtml([b.projectId ? ['사업 id', `<a class="pc-pid" href="${esc(window.RegionLoader.codeUrl(location.href, 'project', b.projectId))}" title="이 사업을 바로 여는 링크">${esc(b.projectId)}</a>`] : null, b.progress ? ['공정율', `${pctTxt(b.progress.rate)} <small>(${esc(String(b.progress.asOf).slice(5))} 기준)</small>`] : null, [b.homeModelKind === 'SCHEMATIC' ? '모형 층수' : '층수', hist || '미확인'], ['입주', esc(b.moveIn)],
      b.progress && b.progress.start && b.progress.end ? ['공사', `${ymDot(b.progress.start)} ~ ${ymDot(b.progress.end)}`] : null,
      b.builder ? ['시공', esc(b.builder) + (b.contractM ? ` <small>${fmt(Math.round(b.contractM / 100))}억원</small>` : '')] : null,
      nr && nr.st ? ['교통', `${esc(nr.st.name)} <small>${IL.shortDist(nr.st.d)}</small>`] : null, ...schoolRows,
      sr ? ['신설 학교', `${esc(IL.shortName(sr.ref.school.name))} <small>${esc(IL.fmtYm(sr.ref.school.openYm))} 개교 · ${IL.shortDist(sr.ref.d)}</small>`] : null])}
    ${sr && sr.level === 'warn' ? `<p class="pc-warn">▲ 학교 개교가 ${esc(sr.detail)}</p>` : ''}
    <p class="pc-foot">${b.src ? `출처: ${esc(b.src)}` : ''}</p>
    ${more ? `<details class="pc-more"><summary>자료 설명</summary><p>${more}</p></details>` : ''}</div>`,
    b.dongs ? b.dongs.flatMap((x) => x.poly).concat([b.poly]) : [b.poly], hmax, clickX);
}
function officialPopup(p, geom, clickX) {
  const none = p.src === '정보없음';   // 높이·층수가 모두 없는 도형: 평면으로만 그렸고, 실재하는 건물인지 알 수 없다
  const gone = !none && p.g === 1;     // 신도시 지구 안에서 지금 있는 건물(도로명주소 건물)과 겹치지 않는 옛 건물: 철거 의심, 역시 평면으로만 그렸다
  const name = p.n ? esc(p.n) : none ? '건물 정보 없음' : '이름 없는 건물';
  let chip, big;
  if (p.src === '공식높이') { chip = chipHtml('off', '공식 높이'); big = `<strong>${p.h} m</strong>`; }
  else if (p.src === '층수환산') { chip = chipHtml('est', '층수로 추정'); big = `<strong>약 ${Math.round(p.eh)} m</strong><span>${p.f}층 × ${(p.eh / p.f).toFixed(2)} m</span>`; }
  else { chip = chipHtml('none', '정보 없음'); big = `<strong>-</strong><span>높이를 알 수 없어 평면으로만 표시</span>`; }
  if (gone) chip = chipHtml('none', '현존 미확인');   // 높이 칩 대신: 옛 대장 값이라 지금 있는 건물의 높이라고 주장하지 않는다
  const fl = [p.f != null ? `지상 ${p.f}` : null, p.b != null ? `지하 ${p.b}` : null].filter(Boolean).join(' · ');
  /* 정보 없는 도형은 비어 있는 줄('정보 없음'·'미기재'·'연도 없음')을 늘어놓지 않고 값이 있는 줄만 보인다 */
  const rows = none ? [fl ? ['층수', esc(fl) + '층'] : null, p.u ? ['용도', esc(p.u)] : null, p.a != null ? ['사용승인', p.a + '년'] : null].filter(Boolean)
    : [['층수', fl ? esc(fl) + '층' : '정보 없음'], ['용도', esc(p.u || '미기재')], ['사용승인', p.a != null ? p.a + '년' : '연도 없음']];
  showCard(`<div class="pc">
    <div class="pc-h"><b>${name}</b>${p.d || p.fc ? `<span class="pc-sub">${esc([p.d, p.fc && FL.NAMES[p.fc]].filter(Boolean).join(' · '))}</span>` : ''}${chip}</div>
    <div class="pc-big">${big}</div>
    ${none ? '<p class="pc-cap">건축물대장과 이어지는 정보가 없는 도형입니다. 실제와 다를 수 있어(철거된 건물이거나 건물이 아닐 수 있음) 입체로 그리지 않았습니다.</p>' : ''}
    ${gone ? '<p class="pc-cap">지금 있는 건물(도로명주소 건물)과 겹치지 않습니다. 신도시를 만들며 철거된 옛 건물일 수 있어 입체로 그리지 않았습니다.</p>' : ''}
    ${rows.length ? dlHtml(rows) : ''}
    ${p.x ? `<p class="pc-warn">⚠ 높이 ${p.h} m와 지상 ${p.f}층이 어긋납니다. 둘 중 하나가 틀렸을 수 있습니다.</p>` : ''}
    <p class="pc-foot">국토교통부 GIS건물통합정보 (V-World)<br>${esc(BASIS)} 기준</p></div>`,
    ringsOf(geom), none || gone ? 0 : p.eh, clickX);
}
/* 기반시설 카드: 신설예정 학교·학교 부지, 전기 등 시설 부지, 정류장 */
const ptRing = (c, d = 0.00018) => [[c[0] - d, c[1] - d], [c[0] + d, c[1] - d], [c[0] + d, c[1] + d], [c[0] - d, c[1] + d]];
function schoolPopup(s, clickX) {
  const sched = s.status === '신설예정', nb = IL.nearestBlock(BLOCKS, [s.lon, s.lat]), cmp = sched && nb ? IL.compareOpen(s.openYm, nb.block) : null, sc = IL.scaleText(s);
  showCard(`<div class="pc">
    <div class="pc-h"><b>${esc(s.name)}</b><span class="pc-sub">${esc(s.level)}</span>${chipHtml(sched ? 'edu' : 'site', sched ? '신설예정' : '일정 미공시')}</div>
    <div class="pc-big">${sched ? `<strong>${esc(IL.fmtYm(s.openYm))}</strong><span>개교 예정 (공시)</span>` : '<strong>미공시</strong><span>개교 일정이 공시되지 않은 학교 부지</span>'}</div>
    ${cmp ? `<p class="${cmp.level === 'warn' ? 'pc-warn' : 'pc-cap'}">${cmp.level === 'warn' ? '▲ ' : ''}${esc(nb.block.id)} ${esc(cmp.text)}</p>` : ''}
    ${dlHtml([sc ? ['규모', `${esc(sc)} <small>계획</small>`] : null, s.address ? ['주소', esc(s.address)] : null, s.areaM2 ? ['부지', `${fmt(Math.round(s.areaM2))}㎡`] : null,
      nb ? ['가까운 단지', `${esc(nb.block.id)} <small>${IL.fmtDist(nb.d)} · ${esc(nb.block.moveIn)}</small>`] : null])}
    <p class="pc-foot">${s.note ? `${esc(s.note)}<br>` : ''}출처: ${esc(infraSrcText(s.sources))}</p>
    <details class="pc-more"><summary>자료 설명</summary><p>부지는 도시계획시설 결정 자료이며 학교가 지어졌는지는 알려 주지 않습니다.</p></details></div>`,
    [s.poly || ptRing([s.lon, s.lat])], 0, clickX);
}
function sitePopup(s, clickX) {
  const power = s.category === '전기';
  showCard(`<div class="pc">
    <div class="pc-h"><b>${esc(s.name)}</b>${chipHtml(power ? 'pow' : 'site', s.category)}</div>
    ${dlHtml([['종류', `${esc(s.category)} 시설 부지`], s.areaM2 ? ['면적', `${fmt(Math.round(s.areaM2))}㎡`] : null])}
    ${power ? '<p class="pc-cap">수전 가능 여부는 한전 협의 사항이라 공개 자료가 없습니다.</p>' : ''}
    <p class="pc-foot">${s.note ? `${esc(s.note)}<br>` : ''}출처: ${esc(infraSrcText(s.sources))}</p>
    <details class="pc-more"><summary>자료 설명</summary><p>도시계획시설 결정 자료이며 건립 여부는 알려 주지 않습니다.</p></details></div>`,
    [s.poly], 0, clickX);
}
function stopPopup(p, geom, clickX) {
  const srcId = /^seoul-/.test(p.id || '') ? 'seoul-bus' : /^osm-/.test(p.id || '') ? 'osm-bus' : 'tago-bus';   // 정류장 id 머리말이 출처(요청 시 조회 지역: 서울시·OpenStreetMap)
  const src = (INFRA.sources || []).find((x) => x.id === srcId), st = p.id ? (INFRA.stops || []).find((s) => s.id === p.id) : null;
  const byId = new Map((INFRA.busRoutes || []).map((r) => [r.id, r])), routes = ((st && st.routes) || []).map((id) => byId.get(id)).filter(Boolean);
  const chips = routes.map((r) => `<em class="pc-route${r.live ? ' live' : ''}" style="--rc:${BL ? BL.routeColor(r.type) : '#56627A'}" title="${esc(r.type || '')} ${esc(r.from || '')} ↔ ${esc(r.to || '')}">${esc(r.no)}</em>`).join(' ');
  showCard(`<div class="pc">
    <div class="pc-h"><b>${esc(p.name)}</b>${chipHtml('bus', '버스정류소')}</div>
    ${dlHtml([st && st.no ? ['정류소 번호', esc(st.no)] : null, routes.length ? ['지나는 노선', chips] : null])}
    <p class="pc-foot">${src ? `출처: ${esc(src.label)}${src.asOf ? ` (${esc(src.asOf)} 받음)` : ''}<br>` : ''}번들을 만들 때 한 번 받은 정보라 이후에 생기거나 바뀐 정류소·노선은 아직 없을 수 있습니다.${routes.some((r) => r.live) ? ' 테두리가 있는 번호 노선은 지도에서 버스 위치를 보여 줍니다.' : ''}</p></div>`,
    [ptRing(geom.coordinates)], 0, clickX);
}
function busPopup(p, clickX) {
  const bus = BUS.cur.find((b) => b.v === p.v), route = LIVE_ROUTES.find((r) => r.id === p.r);
  if (!bus) return;
  const d = BL.describe(bus, route, BLOCKS, (b) => IL.centroid(b.poly), BUS.at);
  showCard(`<div class="pc">
    <div class="pc-h"><b>${esc(d.title)}</b>${chipHtml('bus', '버스')}</div>
    ${dlHtml([['차량', esc(d.plate)], d.where ? ['지나는 중', esc(d.where)] : null, d.near ? ['가까운 단지', esc(d.near.text)] : null, d.passes.length ? ['이 노선이 지나는 단지', esc(d.passes.join(' · '))] : null, d.from ? ['구간', `${esc(d.from)} ↔ ${esc(d.to)}`] : null])}
    <p class="pc-foot">출처: 국토교통부 TAGO 버스위치정보${d.age ? ` · 위치 기준 ${esc(d.age)}` : ''}<br>${esc(busTime(BUS.at))}에 조회한 값이며 자동으로 갱신되지 않습니다(새로 보려면 '버스 새로고침'). 방향과 지나는 단지는 노선 경로(정류소를 이은 선)로 어림했습니다.</p></div>`,
    [ptRing([bus.lon, bus.lat])], 0, clickX);
}
function statusFilter() {
  const status = ['in', ['get', 'status'], ['literal', [...SHOWN]]];
  const f = REG.home ? ['all', status, ['in', ['coalesce', ['get', 'block'], ['get', 'id']], ['literal', [...HOME_VISIBLE]]]] : status;
  return privOn ? f : ['all', f, ['!=', ['get', 'priv'], true]];
}
const blockVisible = (b) => !!b && SHOWN.has(b.status) && (privOn || !b.priv) && (!REG.home || HOME_VISIBLE.has(b.id));   // 지금 지도에 보이는 단지인가(상태 선택 + 민간 스위치)
function dongFilter() { return selDong == null ? statusFilter() : ['all', statusFilter(), ['!=', ['get', 'key'], selDong]]; }
const vis = (id, on) => { if (map.getLayer(id)) map.setLayoutProperty(id, 'visibility', on ? 'visible' : 'none'); };
const SEL_COLOR = '#F0E442';   // 고른 건물: Okabe-Ito의 노랑(상태색 어디와도 겹치지 않음) + 바닥 윤곽선
function applySel() {
  const src = map.getSource('sel');
  let feats = [];
  if (selId != null && HAS_GY) { const sp = GY.features[selId].properties; feats = [{ type: 'Feature', properties: { eh: isFlat(sp) ? FLAT_SEL_H : sp.eh, c: SEL_COLOR }, geometry: GY.features[selId].geometry }]; }   // 평면 도형은 솟지 않게 얇은 판으로만 표시
  else if (selDong != null) feats = DONG_FEATS.filter((f) => f.properties.key === selDong).map((f) => ({ type: 'Feature', properties: { eh: f.properties.h, c: SEL_COLOR }, geometry: f.geometry }));
  if (src) src.setData({ type: 'FeatureCollection', features: feats });
  applyOfficial();
  if (map.getLayer('dong-3d')) map.setFilter('dong-3d', dongFilter());
}
/* 보이는 상태 고르기 */
function applyFilters() {
  if (!map.getLayer('blk-line')) return;
  const f = statusFilter();
  for (const [id, st] of [['blk-sale', '분양중'], ['blk-build', '건설 단계'], ['blk-soon', '준공 임박'], ['blk-move', '입주 단계'], ['blk-plan', '계획']]) {
    vis(id, SHOWN.has(st));
    map.setFilter(id, ['all', f, ['==', ['get', 'status'], st], ['!=', ['get', 'priv'], true]]);
  }
  vis('blk-priv', privOn); map.setFilter('blk-priv', ['all', f, ['==', ['get', 'priv'], true]]);
  map.setFilter('blk-line', ['all', f, ['!=', ['get', 'kind'], 'plan']]);
  map.setFilter('blk-line-plan', ['all', f, ['==', ['get', 'kind'], 'plan']]);
  for (const id of ['blk-dot', 'blk-label-lo', 'blk-badge', 'blk-badge-top', 'dong-label', 'dong-shadow', 'dong-line']) if (map.getLayer(id)) map.setFilter(id, f);
  if (map.getLayer('dong-3d')) map.setFilter('dong-3d', dongFilter());
  document.querySelectorAll('#projList li, #infraList li').forEach((li) => { const card = li.querySelector('.card'); if (!card || !card.dataset.id) return; li.hidden = !blockVisible(BLOCKS.find((x) => x.id === card.dataset.id)); });
  scheduleHud();
  document.querySelectorAll('#timeline .tlp').forEach((g) => { const ids = idsOf(g); g.style.opacity = ids.some((id) => blockVisible(BLOCKS.find((b) => b.id === id))) ? 1 : 0.25; });
}
/* 표시 갱신: 단지 카드·이름표·기반시설(보기 전환은 없앴다 — 기반시설 보기 고정, 자료가 없으면 층수 높이) */
function applyMode() {
  if (!map.getLayer('dong-3d')) return;
  // HUD가 켜져 있으면 먼 곳의 점·알약 이름표는 HUD로 대신하고, 가까워지는 16.3부터 북쪽 끝 이름표가 이어받는다.
  // 단지 요약은 평소 지도 안 라벨(지면 라벨)이 맡는다. 떠 있는 정보 카드(HUD)는 옵션을 켰을 때만 이름표를 대신한다.
  const cards = cardsOn;
  for (const id of ['blk-badge', 'blk-dot', 'blk-label-lo']) vis(id, !cards);
  if (map.getLayer('blk-badge-top')) map.setLayerZoomRange('blk-badge-top', cards ? HUD_MAXZ : 16.6, 24);
  refreshGround();
  if (map.getLayer('blk-badge')) map.setLayoutProperty('blk-badge', 'text-field', groundText(false));
  if (map.getLayer('blk-badge-top')) map.setLayoutProperty('blk-badge-top', 'text-field', groundText(true));
  applyDim();
  if (HAS_INFRA) applyInfra();
  if (BLOCKS.length) setLegend();
  applySel();
  renderHudContent();
}
/* 기존 건물 레이어. '기존 건물 흐리게'(기본 켬)이면 학교·병원·공공시설(IS_FAC)만 평소처럼 3D 로 두고, 나머지 건물은 채우지 않은 점선 윤곽(official-outline)으로만 그린다.
   끄면 모든 건물이 3D 로 채워진다. 고른 건물은 sel-3d 가 따로 그리므로 여기서 뺀다(윤곽·클릭 판도 마찬가지). */
function applyOfficial() {
  if (!map.getLayer('official-3d')) return;
  const dim = dimExisting, notSel = selId == null ? null : ['!=', ['get', 'i'], selId];
  const but = (f) => (notSel ? ['all', f, notSel] : f);
  const solid = (f) => but(dim ? ['all', f, IS_FAC] : f);   // 3D(또는 평면 면)로 그리는 건물
  map.setFilter('official-3d', solid(KNOWN_H)); map.setFilter('official-roof', solid(KNOWN_H));
  if (map.getLayer('official-far')) map.setFilter('official-far', solid(['all', ['>=', ['get', 'eh'], 10], KNOWN_H]));   // 멀리서도 평면 도형(정보없음·g=1)은 솟지 않는다(높이 10 m 이상 철거 의심 건물이 남던 구멍)
  for (const id of ['official-flat', 'official-flat-line']) if (map.getLayer(id)) map.setFilter(id, solid(NO_INFO));
  if (map.getLayer('official-ao')) map.setFilter('official-ao', dim ? ['all', KNOWN_H, IS_FAC] : KNOWN_H);
  if (map.getLayer('official-shadow')) map.setFilter('official-shadow', dim ? ['!=', ['get', 'fc'], ''] : null);
  for (const id of ['official-outline', 'official-hit']) if (map.getLayer(id)) { map.setFilter(id, but(NOT_FAC)); vis(id, dim); }
}
function applyDim() {
  applyOfficial();
  if (BLOCKS.length) setLegend();
}
function applyCtx() {
  for (const id of ['ctx-station', 'ctx-station-label', 'ctx-school', 'ctx-school-label']) vis(id, ctxOn);
  for (const id of ['ctx-ring', 'ctx-ring-label']) vis(id, ctxOn && ringOn);
  if (BLOCKS.length) setLegend();
}
function applyInfra() {
  for (const id of INFRA_LAYERS) vis(id, infraOn);
  for (const id of INFRA_MODE_LAYERS) vis(id, infraOn && viewMode === 'infra');
  for (const id of ZONE_LAYERS) vis(id, zoneOn);
  refreshGround();   // 단지 라벨의 신호 줄도 켜고 끄는 대로
  if (BLOCKS.length) setLegend();
  renderHudContent();   // 단지 표지의 신호 칩도 켜고 끄는 대로
}
/* ---- 버스 위치(3D): 서버가 알려 준 ttl 이상 간격으로만 부르고, 탭이 숨겨지거나 옵션이 꺼지면 멈춘다. 실패하면 간격을 2배씩 늘린다 ---- */
function setBusData(list) {   // 버스 모형 조각(3D)과 번호 라벨 점을 지도 소스에 놓는다. 크기는 지금 확대 단계에 맞춘다
  BUS.shown = list; BUS.scale = BL.scaleFor(map.getZoom());
  const f = BL.features(list, LIVE_ROUTES, BL.scaleFor(map.getZoom()));
  BUS.solids = f.solids; BUS.labels = f.labels;
  const a = map.getSource('bus-solids'), b = map.getSource('bus-lbl');
  if (a) a.setData(f.solids);
  if (b) b.setData(f.labels);
}
function busTween() {   // 새 위치로 1.2초 동안 부드럽게. 탭이 숨겨졌거나 움직임 줄이기를 켠 환경에서는 바로 놓는다(숨은 탭은 애니메이션 프레임이 멈춘다)
  cancelAnimationFrame(BUS.raf); BUS.raf = 0;
  if (document.hidden || (window.matchMedia && matchMedia('(prefers-reduced-motion: reduce)').matches)) { setBusData(BUS.cur); return; }
  const t0 = performance.now(), step = (now) => {
    const k = Math.min(1, (now - t0) / BUS_TWEEN_MS);
    setBusData(BL.interpolate(BUS.prev, BUS.cur, k));
    BUS.raf = k < 1 ? requestAnimationFrame(step) : 0;
  };
  BUS.raf = requestAnimationFrame(step);
}
function busGo() {   // 지금 지도 가운데에서 가장 가까운 버스로 날아간다(버스가 어디 있는지 찾기 어려울 때)
  if (!BUS.cur.length) return;
  const c = map.getCenter(), near = BUS.cur.map((b) => ({ b, d: BL.distM([c.lng, c.lat], [b.lon, b.lat]) })).sort((x, y) => x.d - y.d)[0].b;
  map.flyTo({ center: [near.lon, near.lat], zoom: 17.4, pitch: 58, speed: 1.4, essential: true });
  setOpt(false); say(`가장 가까운 버스, ${(LIVE_ROUTES.find((r) => r.id === near.r) || {}).no || ''}번으로 이동합니다.`);
}
const busTime = (at) => { try { return new Date(at).toLocaleTimeString('ko-KR', { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false }); } catch (_) { return ''; } };
function updateBusStat() {
  const has = BUS.cur.length > 0, can = HAS_BUS && busOn && !BUS.off, wait = Math.ceil((BUS.cooldownUntil - Date.now()) / 1000);
  const go = $('#busGo'); if (go) go.hidden = !(can && has);
  const lb = $('#lblBus small'); if (lb) lb.textContent = BUS.off ? '위치 서버 없음' : '3D, 버튼으로 조회';
  const btn = $('#busLoad');
  if (btn) {   // 위치는 이 버튼을 누를 때만 조회한다(자동 갱신 없음). 조회 뒤 서버 ttl 동안은 다시 누를 수 없다
    btn.hidden = !can; btn.disabled = BUS.loading || wait > 0;
    btn.textContent = BUS.loading ? '조회 중…' : has ? '버스 새로고침' : '버스위치';
    btn.title = BUS.loading ? '버스 위치를 가져오는 중입니다' : wait > 0 ? `${wait}초 뒤 다시 조회할 수 있습니다` : '버튼을 누를 때만 버스 위치를 조회합니다(자동 갱신 없음)';
  }
  const el = $('#busStat'); if (!el) return;
  el.textContent = BUS.off ? `위치를 받을 수 없음${IS_LOCAL ? ' — 로컬은 node scripts/dev.js 로 여세요' : ''}` : has ? `${BUS.cur.length}대 · ${busTime(BUS.at)} 조회` : (BUS.failures ? '위치 조회에 실패했습니다' : '“버스위치”를 누르면 표시됩니다');
}
async function busLoad() {   // 사용자가 누를 때 한 번만 조회한다. 실시간 검색·자동 갱신은 하지 않는다
  if (!HAS_BUS || !busOn || BUS.off || BUS.loading) return;
  const wait = Math.ceil((BUS.cooldownUntil - Date.now()) / 1000);
  if (wait > 0) { say(`${wait}초 뒤 다시 조회할 수 있습니다.`); return; }
  BUS.loading = true; updateBusStat();
  try {
    const res = await fetch(`api/bus?region=${encodeURIComponent(REG.slug)}`);
    if ([404, 405, 503].includes(res.status)) {   // 중계 함수가 없거나(404·405: 정적 서버) 키가 없다(503): 더 부르지 않고 노선 선만 보인다
      BUS.off = true; BUS.loading = false; applyBus(); setLegend();
      console.warn(res.status === 503 ? '버스 위치: 서버에 DATA_GO_KR_KEY 계열 환경변수가 없습니다. 노선 선만 보입니다.' : `버스 위치: /api/bus 가 없습니다(${res.status}). python3 -m http.server 같은 정적 서버에는 함수가 없습니다. 로컬에서는 ./run-app.sh 로 여세요. 노선 선만 보입니다.`);
      say('버스 위치를 받을 수 없어 노선 선만 보여 줍니다.');
      return;
    }
    if (!res.ok) throw new Error(String(res.status));
    const data = BL.parse(await res.json());
    if (!data) throw new Error('shape');
    BUS.failures = 0; BUS.ttl = data.ttl; BUS.at = data.at; BUS.cooldownUntil = Date.now() + data.ttl * 1000;
    BUS.prev = BUS.cur; BUS.cur = BL.withHeading(data.buses, LIVE_ROUTES, BUS.cur);
    applyBus(); busTween();
    setTimeout(updateBusStat, data.ttl * 1000 + 100);   // 쿨다운이 끝나면 버튼을 다시 켠다
    say(`버스 ${BUS.cur.length}대의 위치를 불러왔습니다.`);
  } catch (_) { BUS.failures += 1; say('버스 위치를 불러오지 못했습니다.'); }
  BUS.loading = false; updateBusStat();
}
function applyBus() {   // 노선 선은 옵션이 켜져 있으면 늘 보이고, 버스(3D)와 번호는 조회한 뒤에만 보인다
  if (!HAS_BUS) return;
  const posOn = busOn && !BUS.off && BUS.cur.length > 0;
  for (const id of BUS_LAYERS) vis(id, id === 'bus-3d' || id === 'bus-label' ? posOn : busOn);
  if (!busOn) { cancelAnimationFrame(BUS.raf); BUS.raf = 0; } else if (BUS.cur.length && !BUS.raf) setBusData(BUS.cur);   // 스타일을 다시 불러왔을 때 마지막 위치를 놓는다
  updateBusStat();
}
let busRescaling = false;
function busRescale() {   // 확대를 바꾸면 버스 크기도 맞춘다(애니메이션 중이면 프레임마다 맞추므로 건너뜀, 프레임당 한 번만)
  if (!HAS_BUS || !busOn || BUS.raf || busRescaling || !BUS.shown.length || BL.scaleFor(map.getZoom()) === BUS.scale) return;
  busRescaling = true;
  requestAnimationFrame(() => { busRescaling = false; if (busOn && !BUS.raf) setBusData(BUS.shown); });
}
map.on('zoom', busRescale);
function applyAll() { applyFilters(); applyMode(); applyCtx(); applyInfra(); applyBus(); }
function select(i) { selId = i; selDong = null; applySel(); }
function selectDong(key) { selId = null; selDong = key; applySel(); }
map.on('click', (e) => {
  const pick = (ids) => { const use = ids.filter((id) => map.getLayer(id)); return use.length ? map.queryRenderedFeatures(e.point, { layers: use })[0] : undefined; };
  const far = map.getZoom() < 14.3;     // 멀리서는 점이 단지를 대표하므로 점을 먼저 고른다
  const pickInfra = () => (HAS_INFRA && infraOn ? pick(['infra-school']) || pick(['infra-stop']) || pick(['infra-site-fill']) : undefined);
  const pickBus = () => { if (!(HAS_BUS && busOn && map.getLayer('bus-3d'))) return undefined; const r = 7, p = e.point; return map.queryRenderedFeatures([[p.x - r, p.y - r], [p.x + r, p.y + r]], { layers: ['bus-3d'] })[0]; };   // 버스는 작아서 주변 7px 안까지
  const f = pickBus() || (far && (pick(['blk-dot']) || pick(BLK_FILLS))) || pick(['dong-3d']) || pick(BLK_FILLS) || pick(['blk-dot', 'blk-badge', 'blk-badge-top']) || pickInfra() || pick(['official-3d', 'official-roof', 'official-far']) || pick(['official-flat']) || pick(['official-hit']);
  if (popup) { const o = popup; popup = null; o.remove(); }
  if (!f) { select(null); return; }
  if (f.layer.id === 'bus-3d') { select(null); busPopup(f.properties, e.point.x); }
  else if (f.layer.id === 'dong-3d') { selectDong(f.properties.key); dongPopup(f.properties, e.point.x); }
  else if (f.layer.id.startsWith('blk-')) { select(null); blockPopup(BLOCKS.find((b) => b.id === f.properties.id), e.point.x); }
  else if (f.layer.id.startsWith('infra-')) {
    select(null);
    if (f.layer.id === 'infra-stop') stopPopup(f.properties, f.geometry, e.point.x);
    else if (f.properties.kind === 'school') schoolPopup((INFRA.schools || []).find((x) => x.id === f.properties.id), e.point.x);
    else sitePopup((INFRA.sites || []).find((x) => x.id === f.properties.id), e.point.x);
  }
  else { const i = f.properties.i; select(i); officialPopup(GY.features[i].properties, GY.features[i].geometry, e.point.x); }
});
map.on('mousemove', (e) => {
  const ids = ['dong-3d', ...BLK_FILLS, 'blk-dot', 'blk-badge', 'blk-badge-top', ...(HAS_INFRA && infraOn ? INFRA_PICKS : []), ...(HAS_BUS && busOn ? ['bus-3d'] : []), ...OFFICIAL_LAYERS, 'official-flat', 'official-hit'].filter((id) => map.getLayer(id));
  map.getCanvas().style.cursor = ids.length && map.queryRenderedFeatures(e.point, { layers: ids }).length ? 'pointer' : '';
});

/* ---------- 패널 ---------- */
function setLegend() {
  /* 하단 한 줄(요약)과 '자세히'로 펼치는 목록을 같은 자료로 만든다. 요약에는 기호+짧은 이름만 넣는다. */
  const present = new Set(BLOCKS.filter((b) => !b.priv).map((b) => b.status));
  const rows = [], chips = [];   // rows = 자세한 목록 [기호, 이름, 설명], chips = 요약 한 줄 [기호, 이름]
  const add = (sw, t, n, short = t) => { rows.push([sw, t, n]); if (short) chips.push([sw, short]); };
  const NOTE = { '준공 임박': ' · 공정율 90% 이상, 입주 3개월 안', '입주 단계': ' · 입주를 시작했거나 마침' };
  BY_STAGE.forEach((st) => { if (present.has(st)) add(`<i class="sw ${KIND[st]}"></i>`, st, `<small>${stageOfSt(st)}${NOTE[st] || ''}</small>`); });   // 6단계 순서, 단계 번호를 붙인다
  if (HAS_PRIV && privOn) add('<i class="sw priv"></i>', '공공택지 민간', '<small>회색 면, 상태는 글자로</small>');
  const dimNow = dimExisting;
  if (dimNow) add('<i class="sw outline"></i>', '기존 건물', `<small>점선 윤곽만${HAS_FAC ? ', 학교·병원·공공시설은 3D' : ''}</small>`);
  else add('<i class="sw ramp"></i>', '기존 건물', '<small>높을수록 밝게, 색조는 참고</small>');
  if (HAS_FAC) add('<i class="sw fac-edu"></i><i class="sw fac-med"></i><i class="sw fac-pub"></i>', '기존 학교·병원·공공시설', '<small>노랑 교육 · 빨강 의료 · 청록 공공·복지, 이름은 확대하면</small>', '학교·병원');
  if (PR.otherBlocks && PR.otherBlocks.length) add('<i class="sw other"></i>', '이름 모르는 주택 용지', '<small>공식 윤곽, 점선</small>', '');
  const anyDongs = BLOCKS.some((b) => b.dongs && b.dongs.length), schem = BLOCKS.some((b) => (b.dongs || []).some((d) => d.tier === 'schematic'));
  if (anyDongs) add('<i class="sw tone"></i>', '같은 단지 안', '<small>밝을수록 높은 동</small>', '');
  if (schem) add('<i class="sw dash"></i>', REG.home ? '가상 아파트 모형' : '동 위치는 근사', REG.home ? '<small>동수·층수·배치는 가정 · 실제 설계 아님</small>' : '<small>동 윤곽은 공급 자료를 옮긴 값</small>', REG.home ? '가상 모형 포함' : '');
  if (ctxOn && HAS_CTX) add('<i class="sw stn"></i><i class="sw sch"></i>', '역 · 학교', ringOn ? '<small>점선 원 500 m · 1 km</small>' : '');
  let infraLegend = '';
  if (HAS_INFRA && infraOn) {   // 기반시설 기호는 짝지어 2열 목록으로, 요약 줄에는 기호+이름으로
    const sc = INFRA.schools || [], newS = sc.some((x) => x.status === '신설예정'), siteS = sc.some((x) => x.status === '부지만'), st = INFRA.sites || [];
    const pw = st.some((x) => x.category === '전기'), gr = st.some((x) => x.category === '교통'), links = INFRA_GJ.links.features;
    const items = [];
    const it = (sw, t) => { items.push(`<span>${sw}${t}</span>`); chips.push([sw, t]); };
    if (newS) it(infraIconSvg('edu-new'), '신설 학교');
    if (siteS) it(infraIconSvg('edu-site'), '학교 부지');
    if (pw || gr) it(`${pw ? infraIconSvg('power') : ''}${gr ? infraIconSvg('garage') : ''}`, [pw ? '전기' : '', gr ? '차고지' : ''].filter(Boolean).join('·'));
    if ((INFRA.stops || []).length) it(infraIconSvg('bus'), '정류장');
    if (links.some((f) => f.properties.kind === 'new')) it('<i class="sw link"></i>', '단지→학교');
    if (viewMode === 'infra') {
      if (links.some((f) => f.properties.kind === 'zone')) it('<i class="sw linkz"></i>', '배정 학교');
      it('<i class="sw ring"></i>', '정류장 300 m');
    }
    chips.push(['<b class="lgwarn">▲</b>', '개교 6개월+ 늦음']);
    infraLegend = `<li class="lgrid"><b>입주 전 점검</b><div>${items.join('')}</div><small>점선 부지는 개교 일정 미공시 · ▲는 개교가 입주보다 6개월 이상 늦음${viewMode === 'infra' ? ' · 갈색 면은 반경 안에 정류장 없음' : ''}</small></li>`;
  }
  if (HAS_INFRA && zoneOn && (INFRA.zones || []).length) { rows.push(['<i class="sw zone"></i>', '초등 통학구역', '<small>점선</small>']); chips.push(['<i class="sw zone"></i>', '통학구역']); }
  if (HAS_BUS && busOn) { const sw = '<i class="sw bus3d"></i>'; rows.push([sw, '버스 노선 · 위치', '<small id="busStat"></small>']); chips.push([sw, BUS.off ? '버스 선만' : '버스']); }
  $('#legendSum').innerHTML = chips.map(([sw, t]) => `<span>${sw}${t}</span>`).join('');
  $('#legendList').innerHTML = rows.map(([sw, t, n]) => `<li>${sw}<span>${t} ${n}</span></li>`).join('') + infraLegend;
  updateBusStat();
}
let SUM_TOTAL = null, SUM_COMPACT = '';   // 지도 위 가로 요약(#hudSum)용: 합계 주·보조 문구와 번호만 있는 범례
if (BLOCKS.length) {
  /* 합계 */
  const by = {}; BLOCKS.forEach((b) => { const k = kindOf(b); by[k] = (by[k] || 0) + b.units; });
  const total = BLOCKS.reduce((a, b) => a + b.units, 0), unk = BLOCKS.filter((b) => b.unitsKnown === false).length;
  const grp = [...STATUS_ORDER.map((st) => ({ key: KIND[st], label: st })), { key: 'priv', label: '공공택지 민간' }].filter((g) => g.key in by);
  const known = new Set(BLOCKS.filter((b) => b.unitsKnown !== false).map(kindOf));   // 세대수를 아는 단지가 하나도 없는 묶음은 0 대신 '세대수 미확인'
  const gTxt = (g) => (known.has(g.key) ? fmt(by[g.key]) + '세대' : '세대수 미확인');
  $('#sumTotal').innerHTML = `<span class="big">${fmt(total)}</span><span class="unit">세대</span> <span class="cnt">${BLOCKS.length}개 단지${unk ? `, 세대수 미확인 ${unk}곳 제외` : ''}</span>`;
  $('#sumBar').innerHTML = grp.map((g) => `<i style="width:${total ? 100 * by[g.key] / total : 0}%;background:${g.key === 'plan' ? 'repeating-linear-gradient(90deg,var(--plan) 0 4px,var(--bg) 4px 7px)' : COLOR[g.key]}" title="${g.label} ${gTxt(g)}"></i>`).join('');
  $('#sumBar').setAttribute('aria-label', grp.map((g) => `${g.label} ${gTxt(g)}`).join(', '));
  SUM_TOTAL = { main: `${fmt(total)}세대`, sub: `공급 예정 ${BLOCKS.length}개 단지${unk ? `, 세대수 미확인 ${unk}곳 제외` : ''}`, n: BLOCKS.length, unk };
  SUM_COMPACT = grp.map((g) => `<span title="${esc(g.label)} ${esc(known.has(g.key) ? `${fmt(by[g.key])}세대 (${pct(by[g.key], total)})` : '세대수 미확인')}"><i class="sw ${g.key}"></i>${known.has(g.key) ? fmt(by[g.key]) : '미확인'}</span>`).join('');
  if (HAS_INFRA) { $('#infraSum').innerHTML = infraSumHtml(); $('#infraSum').hidden = false; }
  $('#sumLeg').innerHTML = grp.map((g) => `<span><i class="sw ${g.key}"></i>${g.label} ${known.has(g.key) ? `${fmt(by[g.key])} (${pct(by[g.key], total)})` : '세대수 미확인'}</span>`).join('');
  setLegend();

  /* 단지 카드: 접어 두고, 눌러서 선택하면 펼친다 */
  $('#projList').innerHTML = BLOCKS.map((b) => {
    const k = kindOf(b), fr = floorsRange(b);
    const sub = [b.priv ? '공공택지 민간' : null, unitsTxt(b), dongN(b) ? `${dongN(b)}개동` : null, fr ? `${fr[0] === fr[1] ? fr[0] : fr[0] + '~' + fr[1]}층` : null, /^\d/.test(b.moveIn) ? `입주 ${b.moveIn}` : b.moveIn].filter(Boolean).join(' · ');
    const dates = stageDates(b), stage = STAGES6.map(([, name, sts]) => { const now = sts.includes(b.status); return `<span class="${now ? `now ${k}` : ''}">${name}<small>${dates[name] || (now ? '현재' : '')}</small></span>`; }).join('');
    const bars = fr ? b.dongs.slice().sort((a, c) => a.no.localeCompare(c.no)).map((d) => `<i title="${esc(d.no)}동 ${d.floors}층" style="height:${Math.round(34 * d.floors / 15)}px;background:${mixTone(k, fr[1] > fr[0] ? (d.floors - fr[0]) / (fr[1] - fr[0]) : 1)}"></i>`).join('') + '<em>동별 층수</em>' : '';
    const mini = b.progress ? `<span class="mini" style="--c:${COLOR[k]}" title="공정율 ${esc(b.progress.rate)}%"><i style="width:${Math.max(b.progress.rate, 1)}%"></i></span>` : '';
    const more = `<span class="more"><span class="stage" aria-hidden="true">${stage}</span>${b.progress ? progressRow(b, k) : ''}${bars ? `<span class="fl">${bars}</span>` : ''}${b.builder ? `<span class="bld">시공 ${esc(b.builder)}</span>` : ''}</span>`;
    return `<li><button type="button" class="card" aria-expanded="false" data-id="${esc(b.id)}" aria-label="${esc(b.id)} ${esc(b.status)}, ${esc(sub)}"><i class="sw ${k}"></i><b>${esc(b.id)} ${esc(b.kind.replace('(공공분양)', ''))}</b><span class="st" style="color:${COLOR[k]}">${esc(b.status)}</span><span class="sub">${esc(sub)}</span>${mini}${more}</button></li>`;
  }).join('');

  /* 단지가 아는 단계별 날짜(준공 예정·입주). 월까지만 '26.12 로 적는다. 모르는 단계는 비워 둔다. */
  function stageDates(b) {
    const ym = (v) => { const m = /(\d{4})[.-](\d\d)/.exec(v || ''); return m ? `${m[1].slice(2)}.${m[2]}` : ''; }, digit = /^\d/.test(b.moveIn);
    return { 건설: ym(digit ? (b.progress && b.progress.end) : b.moveIn), 입주: digit ? ym(b.moveIn) : '' };   // 04 건설 칸 아래는 준공 예정, 06 입주 칸 아래는 입주
  }
  /* 입주·준공 예정 타임라인 (2026-10 ~ 2029-12). 같은 달은 한 점에 묶는다 */
  const when = (m) => { const mm = /(\d{4})[.-](\d\d)/.exec(m); return mm ? (Number(mm[1]) - 2026) * 12 + Number(mm[2]) - 10 : null; };
  const SPAN = 38, X0 = 22, X1 = 278, CY = 52, tx = (mo) => X0 + (X1 - X0) * mo / SPAN;
  let svg = `<line x1="${X0}" y1="${CY}" x2="${X1}" y2="${CY}" stroke="var(--line2)" stroke-width="2"/>`;
  for (const [lab, mo, anc] of [['2027', 3, 'middle'], ['2028', 15, 'middle'], ['2029', 27, 'middle']]) svg += `<line x1="${tx(mo)}" y1="${CY - 6}" x2="${tx(mo)}" y2="${CY + 6}" stroke="var(--mute)" stroke-width="2"/><text x="${anc === 'start' ? tx(mo) - 4 : tx(mo)}" y="114" font-size="12.5" fill="var(--mute)" text-anchor="${anc}">${lab}${lab.length === 4 ? '년' : ''}</text>`;
  const groups = new Map();
  BLOCKS.forEach((b) => { const mo = when(b.moveIn); if (mo == null || mo < 0 || mo > SPAN) return; (groups.get(mo) || groups.set(mo, []).get(mo)).push(b); });
  const items = [...groups.entries()].sort((a, c) => a[0] - c[0]);
  items.forEach(([mo, bs], idx) => {
    const x = tx(mo), units = bs.reduce((a, b) => a + b.units, 0), r = 5 + Math.sqrt(units) / 4.5, k = kindOf(bs[0]), up = idx % 2 === 0;
    const yid = up ? 17 : 80, ydt = up ? 31 : 94, ids = bs.map((b) => b.id), dt = String(bs[0].moveIn).replace(/[^0-9.\-]/g, '').slice(2, 7).replace('-', '.');
    svg += `<g class="tlp" tabindex="0" role="button" data-ids="${idsAttr(ids)}" aria-label="${esc(ids.join('·'))} ${esc(bs[0].moveIn)} 입주·준공 예정, 누르면 지도에서 보기">`
      + `<circle cx="${x}" cy="${CY}" r="${Math.max(r, 11)}" fill="transparent"/>`
      + `<circle cx="${x}" cy="${CY}" r="${r}" fill="${COLOR[k]}" fill-opacity="${k === 'build' ? .88 : 1}"/>`
      + `<text x="${x}" y="${yid}" font-size="13" font-weight="700" fill="var(--ink)" text-anchor="middle">${esc(ids.join('·'))}</text>`
      + `<text x="${x}" y="${ydt}" font-size="12.5" fill="var(--mute)" text-anchor="middle">${dt}</text></g>`;
  });
  $('#timeline').innerHTML = svg;
  $('#h-tl').closest('section').hidden = !items.length;   // 날짜가 있는 단지가 없으면 빈 축만 보이지 않게 구역을 숨긴다(레일 점도)
  $('#prail [data-sec="h-tl"]').hidden = !items.length;
  $('#timeline').setAttribute('aria-label', '입주·준공 예정: ' + items.map(([, bs]) => `${bs.map((b) => b.id).join('·')} ${bs[0].moveIn}`).join(', '));
} else {
  const near = Array.isArray(REG.nearby) ? REG.nearby : [];   // 번들 없는 지역: 같은 시군구의 다른 법정동(인허가 사업은 법정동 단위로 찾는다)
  const chips = near.length && window.RegionLoader ? `<li class="nearby"><b>같은 시군구의 다른 법정동 ${near.length}곳</b><span class="nb-list">${near.map((x) => `<a href="${esc(window.RegionLoader.codeUrl(location.href, 'bjd', x.bjd))}">${esc(x.name)}</a>`).join('')}</span></li>` : '';
  $('#projList').innerHTML = '<li class="empty">이 지역에는 아직 표시할 단지가 없습니다. ' + (near.length ? '인허가 사업은 법정동 단위로 찾으니 아래에서 다른 법정동을 골라 보세요.' : '자료가 들어오면 이곳에 나타납니다.') + '</li>' + chips;
  for (const id of ['h-sum', 'h-tl']) { const s = document.getElementById(id).closest('section'); if (s) s.hidden = true; }
}
/* 공공 모집 공고(마이홈): 번들 없는 지역에서만, 지도·단지를 막지 않게 늦게 채운다. 못 받으면 구역을 숨긴 채 둔다 */
async function loadNotices() {
  if (REG.slug || !RES || !RES.sgg || !window.RegionLoader || !window.RegionLoader.fetchNotices) return;
  const data = await window.RegionLoader.fetchNotices(window, RES.sgg);
  if (!data) return;
  const rows = window.RegionLoader.noticeRows(data);
  $('#secNotice').hidden = false;
  $('#noticeSub').textContent = rows.length ? `${data.name} · 공공주택 모집공고 ${rows.length}건(마이홈포털·LH 분양임대공고문. 대부분 매입임대·일반매각이며 건설 중인 단지와 별도입니다${rows.some((r) => r.fromLh) ? '. LH 공고는 제목의 지역 이름으로 이 지역에 실은 것이라 틀릴 수 있습니다' : ''})` : `${data.name}에는 지금 모집 중인 공공주택 공고가 없습니다(마이홈포털·LH 기준).`;
  $('#noticeList').innerHTML = rows.map((r) => `<li><span class="nt">${esc(r.title)}</span>${r.meta ? `<span class="nm">${esc(r.meta)}</span>` : ''}${r.period ? `<span class="nm">${esc(r.period)}</span>` : ''}${r.place ? `<span class="nm">${esc(r.place)}</span>` : ''}`
    + (r.url || r.pnu ? `<span class="na">${r.url ? `<a href="${esc(r.url)}" target="_blank" rel="noopener noreferrer">공고 보기</a>` : ''}${r.pnu ? `<a href="${esc(window.RegionLoader.codeUrl(location.href, 'pnu', r.pnu))}">지도에서 보기</a>` : ''}</span>` : '') + '</li>').join('');
}
loadNotices();
function flyTo(opts) { if (reduceMotion) map.jumpTo(opts); else map.flyTo({ ...opts, duration: 1600 }); }
function setSheet(state) {
  const h = { peek: '176px', half: '48vh', full: '88vh' }[state] || '176px';
  document.documentElement.style.setProperty('--sh', h); $('#panel').dataset.sheet = state; $('#sheetHandle').setAttribute('aria-expanded', String(state !== 'peek'));
}
const openId = () => { const c = document.querySelector('#projList .card[aria-expanded="true"]'); return c ? c.dataset.id : null; };
function syncUrl(id) {
  try {
    const u = new URL(location.href), set = (k, v) => (v ? u.searchParams.set(k, v) : u.searchParams.delete(k));
    set('block', id); set('priv', privOn ? '' : '0'); set('mode', ''); set('ctx', ctxOn ? '' : '0'); set('ring', ringOn ? '' : '0'); set('hud', hudOn ? '' : '0'); set('cards', cardsOn ? '' : '0'); set('dim', dimExisting ? '' : '0'); set('infra', HAS_INFRA && !infraOn ? '0' : ''); set('zone', HAS_INFRA && !zoneOn ? '0' : ''); set('bus', HAS_BUS && !busOn ? '0' : ''); set('panel', $('.app').classList.contains('collapsed') ? '' : '1');
    history.replaceState(null, '', u);
  } catch (_) { /* file:// 에서는 막힐 수 있음 */ }
}
function focusBlock(id, { toggle = true, tour = false, scroll = true } = {}) {
  if (!tour) stopMotion();
  const btn = byId($('#projList'), 'data-id', id), b = BLOCKS.find((x) => x.id === id); if (!b) return;
  const was = btn && btn.getAttribute('aria-expanded') === 'true';
  document.querySelectorAll('#projList .card').forEach((c) => c.setAttribute('aria-expanded', c === btn && !(toggle && was) ? 'true' : 'false'));
  if (scroll && btn && btn.getAttribute('aria-expanded') === 'true') btn.scrollIntoView({ block: 'nearest', behavior: reduceMotion ? 'auto' : 'smooth' });   // 사이드바에서 펼친 카드가 보이게
  if (!SHOWN.has(b.status)) { SHOWN.add(b.status); syncChips(); applyFilters(); }
  if (b.priv && !privOn) { privOn = true; syncChips(); applyFilters(); }
  if (innerWidth <= 900) setSheet('peek');
  syncUrl(id);
  select(null);
  map.once('moveend', () => setTimeout(() => blockPopup(b), 80));   // 즉시 이동(동작 줄이기)도 놓치지 않도록 이동 전에 등록한다.
  flyTo({ center: centroid(b.poly), zoom: 16.5, pitch: 58, bearing: -10 });
  say(`${b.id} 블록으로 이동합니다.`);
}
$('#projList').addEventListener('click', (e) => { const btn = e.target.closest('button[data-id]'); if (btn) focusBlock(btn.dataset.id); });
/* 타임라인의 점이나 '다음 일정'을 누르면 그 시기 단지로 이동 */
function showGroup(ids) {
  stopMotion();
  const bs = ids.map((i) => BLOCKS.find((b) => b.id === i)).filter(Boolean); if (!bs.length) return;
  if (bs.length === 1) { focusBlock(ids[0], { toggle: false }); return; }
  document.querySelectorAll('#projList .card').forEach((c) => c.setAttribute('aria-expanded', 'false'));
  const bb = new maplibregl.LngLatBounds(); bs.forEach((b) => b.poly.forEach((p) => bb.extend(p)));
  if (popup) { popup.remove(); popup = null; }
  select(null);
  if (innerWidth <= 900) setSheet('peek');
  map.fitBounds(bb, { padding: { top: 90, bottom: 90, left: 60, right: 60 }, pitch: 56, bearing: -8, duration: reduceMotion ? 0 : 1200, maxZoom: 16.4 });
  say(`${ids.join('과 ')} 블록을 함께 봅니다.`);
}
function onTimeline(e) {
  if (e.type === 'keydown' && e.key !== 'Enter' && e.key !== ' ') return;
  const g = e.target.closest('.tlp'); if (!g) return; e.preventDefault();
  showGroup(idsOf(g));
}
$('#timeline').addEventListener('click', onTimeline); $('#timeline').addEventListener('keydown', onTimeline);
const dur = reduceMotion ? 0 : 700;
function fitAll() {
  const pts = BLOCKS.flatMap((b) => b.poly); if (!pts.length) return;
  const bb = new maplibregl.LngLatBounds(); pts.forEach((p) => bb.extend(p));
  map.fitBounds(bb, { padding: { top: 70, bottom: 90, left: 50, right: 50 }, pitch: 52, bearing: 0, duration: reduceMotion ? 0 : 900, maxZoom: 16.2 });
}
$('#vAll').addEventListener('click', () => { stopMotion(); fitAll(); });
/* 단지와 가까운 신설 학교·시설이 한 화면에 들어오게 맞춘다('기반시설' 보기를 열 때). */
function fitInfra() {
  const bb = new maplibregl.LngLatBounds();
  BLOCKS.flatMap((b) => b.poly).forEach((p) => bb.extend(p));
  (INFRA.schools || []).forEach((x) => { if (bb.contains([x.lon, x.lat]) || BLOCKS.some((b) => IL.distM(IL.centroid(b.poly), [x.lon, x.lat]) <= IL.NEW_SCHOOL_M)) bb.extend([x.lon, x.lat]); });
  map.fitBounds(bb, { padding: { top: 90, bottom: 100, left: 60, right: 60 }, pitch: 50, bearing: 0, duration: reduceMotion ? 0 : 900, maxZoom: 16 });
}
function openInfra() {
  stopMotion();
  if (!infraOn) { infraOn = true; syncChips(); }
  viewMode = 'infra'; applyMode(); syncUrl(openId()); say(INFRA_SAY); fitInfra();
  const sec = document.getElementById('secInfra'); if (sec && !sec.hidden) setInfraOpen(true);
  if (sec && !sec.hidden && !$('.app').classList.contains('collapsed')) sec.scrollIntoView({ block: 'start', behavior: reduceMotion ? 'auto' : 'smooth' });
}
$('#vPlane').addEventListener('click', () => map.easeTo({ pitch: map.getPitch() < 5 ? 58 : 0, duration: dur }));

/* 자동 회전: 컨트롤이나 지도를 만지면 멈춘다. 움직임 줄이기 설정이면 버튼을 숨긴다. */
let orbitRaf = 0, orbitOn = false;
function stopOrbit() {
  if (!orbitOn) return; orbitOn = false; if (orbitRaf) cancelAnimationFrame(orbitRaf); orbitRaf = 0;
  $('#vOrbit').setAttribute('aria-pressed', 'false'); $('#vOrbit').textContent = '자동'; say('자동 회전을 멈췄습니다.');
}
function startOrbit() {
  stopTour(); orbitOn = true;
  if (popup) { popup.remove(); popup = null; }   // 돌면 카드가 건물을 가리게 되므로 닫는다
  $('#vOrbit').setAttribute('aria-pressed', 'true'); $('#vOrbit').textContent = '멈춤'; say('지금 보이는 지도를 그대로 천천히 돌립니다. 지도나 컨트롤을 만지면 멈춥니다.');
  // 화면 가운데·확대·기울기를 바꾸지 않고, 지금 보이는 지도를 그 자리에서 돌린다.
  let last = performance.now();
  const tick = (t) => { map.setBearing(map.getBearing() + (t - last) / 1000 * 7.5); last = t; orbitRaf = requestAnimationFrame(tick); };
  orbitRaf = requestAnimationFrame(tick);
}
$('#vOrbit').addEventListener('click', () => { stopTour(); if (orbitOn) stopOrbit(); else startOrbit(); });
if (reduceMotion) $('#vOrbit').hidden = true;

/* 순회 투어: 보이는 단지를 하나씩 날아가 카드까지 열어 보여 주고, 한 바퀴 돌면 전체 보기로 돌아온다. 지도를 만지면 멈춘다. */
let tourOn = false, tourT = 0;
function stopTour() {
  if (!tourOn) return; tourOn = false; clearTimeout(tourT); tourT = 0;
  $('#vTour').setAttribute('aria-pressed', 'false'); $('#vTour').textContent = '투어'; say('투어를 멈췄습니다.');
}
function startTour() {
  stopOrbit(); tourOn = true;
  $('#vTour').setAttribute('aria-pressed', 'true'); $('#vTour').textContent = '멈춤'; say('단지를 차례로 보여 줍니다. 지도를 만지면 멈춥니다.');
  const seq = BLOCKS.filter(blockVisible).map((b) => b.id); let i = 0;
  const step = () => {
    if (!tourOn) return;
    if (i >= seq.length) { stopTour(); fitAll(); return; }
    focusBlock(seq[i++], { toggle: false, tour: true });
    tourT = setTimeout(step, 6500);
  };
  step();
}
$('#vTour').addEventListener('click', () => { if (tourOn) stopTour(); else startTour(); });
function stopMotion() { stopOrbit(); stopTour(); }
for (const ev of ['mousedown', 'touchstart', 'wheel']) map.on(ev, () => stopMotion());
$('#map').addEventListener('keydown', () => stopMotion());

/* 좌우 돌리기: ◀▶ 로 15°씩 돌리고 길게 누르면 계속 돈다. 북쪽 맞추기와 보는 방향 표시는 오른쪽 위 나침반이 맡는다.
   자동 회전·투어·마우스 등 무엇으로 돌든 나침반이 따라간다. 값은 카메라가 보는 방향이며 0°는 북쪽이 위다. */
const DIRS = ['북', '북동', '동', '남동', '남', '남서', '서', '북서'];
let holdT = 0, holdRaf = 0, held = false, heldAt = 0;
const normB = (b) => ((Math.round(b) % 360) + 360) % 360;
function syncPlane() { const f = String(map.getPitch() < 5), el = $('#vPlane'); if (el.getAttribute('aria-pressed') !== f) el.setAttribute('aria-pressed', f); }
map.on('move', syncPlane);
function holdStart(dir) {
  stopMotion(); held = false; clearTimeout(holdT);
  holdT = setTimeout(() => {
    held = true; let last = performance.now();
    const tick = (t) => { map.setBearing(map.getBearing() + dir * (t - last) / 1000 * 45); last = t; holdRaf = requestAnimationFrame(tick); };
    holdRaf = requestAnimationFrame(tick);
  }, 260);
}
function holdEnd() { clearTimeout(holdT); holdT = 0; if (holdRaf) { cancelAnimationFrame(holdRaf); holdRaf = 0; } if (held) { held = false; heldAt = performance.now(); } }
for (const [sel, dir] of [['#dLeft', -1], ['#dRight', 1]]) {
  const el = $(sel);
  el.addEventListener('pointerdown', (e) => { if (!e.button) holdStart(dir); });
  for (const t of ['pointerup', 'pointercancel', 'pointerleave']) el.addEventListener(t, holdEnd);
  el.addEventListener('contextmenu', (e) => e.preventDefault());
  el.addEventListener('click', () => {
    if (performance.now() - heldAt < 350) return;   // 길게 눌러 돌렸다면 손을 뗄 때의 클릭은 무시
    stopMotion(); map.easeTo({ bearing: map.getBearing() + dir * 15, duration: reduceMotion ? 0 : 250, easing: (t) => t });
  });
}
$('#zIn').addEventListener('click', () => { stopMotion(); map.zoomIn({ duration: dur }); });
$('#zOut').addEventListener('click', () => { stopMotion(); map.zoomOut({ duration: dur }); });

/* 옵션 창: 자주 바꾸지 않는 설정을 모았다. 기본은 모두 켬이고, 꺼 둔 설정이 있으면 버튼에 개수를 보인다. */
const ALL_ST = new Set(BLOCKS.map((b) => b.status));
const optCount = () => (SHOWN.size < ALL_ST.size ? 1 : 0) + (HAS_CTX && !ctxOn ? 1 : 0) + (HAS_CTX && ctxOn && !ringOn ? 1 : 0) + (!hudOn ? 1 : 0) + (!cardsOn ? 1 : 0) + (HAS_PRIV && !privOn ? 1 : 0) + (HAS_INFRA && !infraOn ? 1 : 0) + (HAS_INFRA && !zoneOn ? 1 : 0) + (HAS_BUS && !busOn ? 1 : 0);
function syncChips() {
  document.querySelectorAll('#optStatus input').forEach((i) => { i.checked = SHOWN.has(i.dataset.status); });
  document.querySelectorAll('#stageF button[data-status]:not(:disabled)').forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.status.split('|').every((st) => SHOWN.has(st)))));
  $('#dimBtn').setAttribute('aria-pressed', String(dimExisting)); $('#hudChip').checked = hudOn; $('#cardsChip').checked = cardsOn; if (HAS_PRIV) $('#privChip').checked = privOn;
  if (HAS_CTX) { $('#ctxChip').checked = ctxOn; $('#ringChip').checked = ringOn; $('#ringChip').disabled = !ctxOn; $('#lblRing').classList.toggle('dis', !ctxOn); }
  if (HAS_INFRA) { $('#infraChip').checked = infraOn; $('#zoneChip').checked = zoneOn; }
  if (HAS_BUS) $('#busChip').checked = busOn;
  const n = optCount(); $('#optN').hidden = !n; $('#optN').textContent = String(n);
  $('#optBtn').setAttribute('aria-label', n ? `옵션, 기본값과 다른 설정 ${n}개` : '옵션');
}
function setOpt(open) {
  $('#optPanel').hidden = !open; $('#optBtn').setAttribute('aria-expanded', String(open));
  if (open) positionOpt();
}
function positionOpt() {
  const w = $('.mapwrap').getBoundingClientRect(), b = $('#optBtn').getBoundingClientRect(), pw = $('#optPanel').offsetWidth || 272;
  $('#optPanel').style.setProperty('--ox', Math.max(12, Math.min(b.left - w.left, w.width - pw - 12)) + 'px');
  $('#optPanel').style.setProperty('--oy', (b.bottom - w.top + 6) + 'px');
}
(function wireTop() {
  const present = BY_STAGE.filter((st) => ALL_ST.has(st));
  $('#optStatus').innerHTML = present.map((st) => `<label><input type="checkbox" data-status="${st}" checked><i class="sw ${KIND[st]}"></i>${st} <small>${stageOfSt(st)}</small></label>`).join('');
  if (!HAS_CTX) { $('#lblCtx').hidden = true; $('#lblRing').hidden = true; }
  /* 머리 줄의 6단계 필터: 옵션의 '보일 단지 상태'와 같은 SHOWN 을 켜고 끈다. 단지가 없는 단계는 눌리지 않게 흐리게 둔다 */
  $('#stageF').hidden = !BLOCKS.length;
  $('#stageF').innerHTML = STAGES6.map(([no, name, sts, col]) => {
    const live = sts.filter((st) => ALL_ST.has(st)), bs = BLOCKS.filter((b) => live.includes(b.status)), units = bs.reduce((a, b) => a + b.units, 0);
    return `<button type="button" class="sf" data-status="${live.join('|')}" data-name="${no} ${name}" style="--c:${col}" aria-pressed="${!!bs.length}"${bs.length ? '' : ' disabled'}><span class="sf-h"><i class="sf-sw"></i>${no} ${name}<span class="sf-n">${bs.length ? `${bs.length}단지` : '없음'}</span></span><b class="sf-v">${fmt(units)}<small>세대</small></b></button>`;
  }).join('');
  $('#stageF').addEventListener('click', (e) => {
    const b = e.target.closest('button[data-status]'); if (!b || b.disabled) return;
    const sts = b.dataset.status.split('|'), on = sts.every((st) => SHOWN.has(st)), name = b.dataset.name;
    if (on && [...SHOWN].every((st) => sts.includes(st))) { say('한 단계는 켜 두어야 합니다.'); return; }   // 한 단계(04 건설)는 상태 두 개를 함께 켜고 끈다
    sts.forEach((st) => (on ? SHOWN.delete(st) : SHOWN.add(st))); syncChips(); applyFilters(); say(`${name} ${on ? '숨김' : '보임'}`);
  });
  const hd = $('#hdRegion'); hd.textContent = REG.name || ''; hd.hidden = !$('#regionBox').hidden;   // 지역을 고를 수 있으면 고르는 상자가, 아니면 이름만
  $('#lblPriv').hidden = !HAS_PRIV;
  $('#fsInfra').hidden = !HAS_INFRA;
  $('#lblBus').hidden = !HAS_BUS;
  $('#busGo').addEventListener('click', busGo);
  $('#busLoad').addEventListener('click', busLoad);
  if (HAS_INFRA) $('#infraSum').addEventListener('click', openInfra);
  $('#optBtn').addEventListener('click', () => setOpt($('#optPanel').hidden));
  $('#dimBtn').addEventListener('click', () => { dimExisting = !dimExisting; syncChips(); applyDim(); syncUrl(openId()); say(dimExisting ? '기존 건물을 점선 윤곽으로 흐리게 봅니다.' : '기존 건물을 모두 3D 로 봅니다.'); });
  $('#optPanel').addEventListener('change', (e) => {
    const t = e.target;
    if (t.dataset.status) {
      const st = t.dataset.status;
      if (!t.checked && SHOWN.size === 1) { t.checked = true; say('한 가지 상태는 켜 두어야 합니다.'); return; }
      t.checked ? SHOWN.add(st) : SHOWN.delete(st); syncChips(); applyFilters(); say(`${st} ${SHOWN.has(st) ? '보임' : '숨김'}`);
    } else if (t.id === 'privChip') { privOn = t.checked; syncChips(); applyFilters(); setLegend(); syncUrl(openId()); say(privOn ? '공공택지 민간 단지를 보여 줍니다.' : '공공택지 민간 단지를 숨깁니다.'); }
    else if (t.id === 'ctxChip') { ctxOn = t.checked; syncChips(); applyCtx(); syncUrl(openId()); say(ctxOn ? '역과 학교를 보여 줍니다.' : '역과 학교를 숨깁니다.'); }
    else if (t.id === 'ringChip') { ringOn = t.checked; syncChips(); applyCtx(); syncUrl(openId()); }
    else if (t.id === 'infraChip') { infraOn = t.checked; syncChips(); applyInfra(); syncUrl(openId()); say(infraOn ? '학교·정류장·전기 시설을 보여 줍니다.' : '학교·정류장·전기 시설을 숨깁니다.'); }
    else if (t.id === 'busChip') { busOn = t.checked; syncChips(); applyBus(); setLegend(); syncUrl(openId()); say(busOn ? '버스 노선과 위치를 3D로 보여 줍니다.' : '버스 노선과 위치를 숨깁니다.'); }
    else if (t.id === 'zoneChip') { zoneOn = t.checked; syncChips(); applyInfra(); syncUrl(openId()); say(zoneOn ? '초등 통학구역 경계를 보여 줍니다.' : '초등 통학구역 경계를 숨깁니다.'); }
    else if (t.id === 'cardsChip') { cardsOn = t.checked; applyMode(); syncChips(); syncUrl(openId()); say(cardsOn ? '단지 정보 카드를 보여 줍니다.' : '단지 정보 카드를 숨기고 지도 위 라벨로 보여 줍니다.'); }
    else if (t.id === 'hudChip') { hudOn = t.checked; applyMode(); syncChips(); syncUrl(openId()); say(hudOn ? '단지 모서리 표시선을 켭니다.' : '단지 모서리 표시선을 끕니다.'); }
  });
  $('#optReset').addEventListener('click', () => {
    ALL_ST.forEach((st) => SHOWN.add(st)); ctxOn = true; ringOn = true; infraOn = true; zoneOn = true; busOn = true; hudOn = true; cardsOn = true; privOn = true; applyMode();
    applyFilters(); applyCtx(); applyInfra(); applyBus(); if (BLOCKS.length) setLegend(); syncChips(); syncUrl(openId()); say('옵션을 기본값(모두 켬)으로 되돌렸습니다.');
  });
  document.addEventListener('pointerdown', (e) => { if (!$('#optPanel').hidden && !e.target.closest('#optPanel, #optBtn')) setOpt(false); });
  document.addEventListener('keydown', (e) => { if (e.key === 'Escape' && !$('#optPanel').hidden) { setOpt(false); $('#optBtn').focus(); } });
  window.addEventListener('resize', () => { if (!$('#optPanel').hidden) positionOpt(); });
  syncChips(); syncPlane();
})();
const INFRA_SAY = '기반시설 보기: 단지와 학교·정류장·전기 시설의 관계, 개교 시점과의 차이를 보여 줍니다.';

/* 다음 일정: 가까운 준공·입주 3건을 D-n으로. 달만 아는 입주는 개월 수로 어림한다. */
function buildNext() {
  const today = new Date(); today.setHours(0, 0, 0, 0);
  const parse = (str) => { const m = /(\d{4})[.-](\d\d)(?:[.-](\d\d))?/.exec(str || ''); return m ? { d: new Date(+m[1], +m[2] - 1, m[3] ? +m[3] : 1), exact: !!m[3] } : null; };
  const ev = [];
  BLOCKS.forEach((b) => {
    const digit = /^\d/.test(b.moveIn), mv = parse(b.moveIn), end = b.progress ? parse(b.progress.end) : null;
    if (digit && end) ev.push({ kind: '준공 예정', b, ...end });
    if (!digit && mv) ev.push({ kind: '준공 예정', b, ...mv });      // 임대: 입주계획의 준공 예정일
    if (digit && mv) ev.push({ kind: '입주 시작', b, ...mv, exact: false });
  });
  const days = (d) => Math.round((d - today) / 864e5);
  const groups = new Map();
  ev.filter((e) => days(e.d) >= 0).sort((a, c) => a.d - c.d).forEach((e) => { const k = `${e.kind}|${e.d.getTime()}`; (groups.get(k) || groups.set(k, { ...e, bs: [] }).get(k)).bs.push(e.b); });
  const rows = [...groups.values()].slice(0, 3);
  $('#h-next').parentElement.hidden = !rows.length;
  $('#prail [data-sec="h-next"]').hidden = !rows.length;
  $('#nextList').innerHTML = rows.map((g) => {
    const n = days(g.d), ids = g.bs.map((b) => b.id), units = g.bs.reduce((a, b) => a + b.units, 0);
    const dn = !g.exact ? (n < 30 ? '이번 달' : `${Math.round(n / 30.4)}개월 뒤`) : n === 0 ? 'D-day' : n <= 120 ? `D-${n}` : `${Math.round(n / 30.4)}개월 뒤`;
    const when = g.exact ? `${g.d.getFullYear()}.${String(g.d.getMonth() + 1).padStart(2, '0')}.${String(g.d.getDate()).padStart(2, '0')}` : `${g.d.getFullYear()}.${String(g.d.getMonth() + 1).padStart(2, '0')} 예정`;
    return `<li><button type="button" class="nx" data-ids="${idsAttr(ids)}" aria-label="${esc(ids.join('·'))} ${g.kind} ${when}, ${dn}, 누르면 지도에서 보기"><span class="dn${g.kind === '입주 시작' ? ' move' : ''}">${dn}</span><span><b>${esc(ids.join('·'))} ${g.kind}</b><span class="s">${when} · ${fmt(units)}세대</span></span></button></li>`;
  }).join('');
}
buildNext();

/* 입주 전 점검: 단지마다 교육·교통·전기 줄, 개교 일정, 보도 근거 대책, 지구 안 건축 인허가. 구역은 자료가 있을 때만 보인다(레일 점도 같이). */
/* 입주와 기반시설 시점을 한 달력에 겹친 그림: 입주 줄과 교육·교통 줄, 첫 입주부터 가장 이른 일반 학교 개교까지를 띠로 칠한다. */
function buildInfraTimeline() {
  const t = IL.timeline(BLOCKS, INFRA);
  const lanes = t ? t.lanes.filter((l) => l.items.length) : [];
  if (!t || lanes.length < 2) return;
  const X0 = 40, X1 = 286, mo = (ym) => +ym.slice(0, 4) * 12 + +ym.slice(5, 7) - 1;
  const m0 = mo(t.from), m1 = Math.max(mo(t.to) + 1, m0 + 12), tx = (ym) => X0 + (X1 - X0) * (mo(ym) - m0) / (m1 - m0);
  const INK = { move: 'var(--mute)', edu: 'var(--edu)', transit: 'var(--ink)' };   // 테마 변수(라이트·다크 모두)
  const LINE = 14, TOP = 26, nameW = (n) => [...n].reduce((a, ch) => a + (/[가-힣]/.test(ch) ? 12 : 7), 0);
  let y = TOP, body = '', bandBottom = TOP;
  lanes.forEach((l) => {
    // 달 라벨(작은 회색)과 이름을 점 아래에 쌓고, 옆 점의 라벨과 겹치면 한 행 아래로 내린다.
    const ends = [], blockH = (1 + Math.max(...l.items.map((i) => i.names.length))) * LINE + 3;
    l.items.forEach((i) => {
      const x = tx(i.ym), w = Math.max(30, ...i.names.map(nameW));
      i.anchor = x + w / 2 > X1 + 8 ? 'end' : x - w / 2 < X0 - 6 ? 'start' : 'middle';
      i.tx = i.anchor === 'end' ? x + 4 : i.anchor === 'start' ? x - 4 : x;
      const left = i.anchor === 'end' ? x + 4 - w : i.anchor === 'start' ? x - 4 : x - w / 2;
      let r = 0; while (r < ends.length && ends[r] + 4 > left) r++;
      ends[r] = left + w; i.row = r;
    });
    const base = y + 9, h = 9 + 8 + ends.length * blockH + 3;
    body += `<text x="2" y="${base + 4}" font-size="13" font-weight="700" fill="var(--mute)">${esc(l.name)}</text><line x1="${X0}" y1="${base}" x2="${X1}" y2="${base}" stroke="var(--line2)" stroke-width="2"/>`;
    l.items.forEach((i) => {
      const x = tx(i.ym), top = base + 15 + i.row * blockH;
      body += (i.row ? `<line x1="${x.toFixed(1)}" y1="${base + 6}" x2="${x.toFixed(1)}" y2="${top - 9}" stroke="var(--line2)" stroke-width="1"/>` : '')
        + `<circle cx="${x.toFixed(1)}" cy="${base}" r="5.5" fill="${i.hollow ? 'var(--bg)' : INK[l.key]}" stroke="${INK[l.key]}" stroke-width="2"${i.hollow ? ' stroke-dasharray="2.6 1.8"' : ''}/>`
        + `<text x="${i.tx.toFixed(1)}" y="${top}" font-size="12" fill="var(--mute)" text-anchor="${i.anchor}">${esc(IL.fmtYm(i.ym).slice(2))}</text>`
        + i.names.map((n, k) => `<text x="${i.tx.toFixed(1)}" y="${top + (k + 1) * LINE}" font-size="12.5" font-weight="${k === 0 ? 700 : 400}" fill="var(--ink)" text-anchor="${i.anchor}">${esc(n)}</text>`).join('');
    });
    y += h; if (l.key === 'edu') bandBottom = y - 2;
  });
  if (bandBottom === TOP) bandBottom = y - 2;
  let band = '';
  if (t.gap) {
    const gx0 = tx(t.gap.from), gx1 = tx(t.gap.to);
    band = `<rect x="${gx0.toFixed(1)}" y="${TOP - 4}" width="${(gx1 - gx0).toFixed(1)}" height="${(bandBottom - TOP + 4).toFixed(1)}" fill="var(--warn)" fill-opacity=".14" stroke="var(--warn)" stroke-width="1.2" stroke-dasharray="4 3"/>`
      + `<text x="${((gx0 + gx1) / 2).toFixed(1)}" y="${TOP - 9}" font-size="12" font-weight="700" fill="var(--warn)" text-anchor="middle">▲ 새 학교 없는 기간 ${t.gap.months}개월</text>`;
  }
  let axis = `<line x1="${X0}" y1="${y + 2}" x2="${X1}" y2="${y + 2}" stroke="var(--line2)" stroke-width="1"/>`;
  for (let m = Math.ceil(m0 / 12) * 12; m <= m1; m += 12) { const x = X0 + (X1 - X0) * (m - m0) / (m1 - m0); axis += `<line x1="${x.toFixed(1)}" y1="${y - 1}" x2="${x.toFixed(1)}" y2="${y + 5}" stroke="var(--mute)" stroke-width="1.5"/><text x="${x.toFixed(1)}" y="${y + 17}" font-size="12" fill="var(--mute)" text-anchor="middle">${m / 12}년</text>`; }
  const H = y + 22;
  const svg = $('#infraTl');
  svg.setAttribute('viewBox', `0 0 300 ${H}`);
  svg.innerHTML = band + body + axis;
  const desc = lanes.map((l) => `${l.name}: ${l.items.map((i) => `${IL.fmtYm(i.ym)} ${i.names.join('·')}`).join(', ')}`).join('. ');
  svg.setAttribute('aria-label', `입주와 기반시설 시점. ${t.gap ? `새 학교 없는 기간 ${t.gap.months}개월. ` : ''}${desc}`);
  $('#infraTlNote').textContent = t.gap
    ? `${t.gap.school} 개교 전까지는 현 통학구역 기준이며 배정은 교육청이 정합니다. 속 빈 점은 검토 단계 대책입니다.`
    : '속 빈 점은 검토 단계 대책입니다.';
  $('#infraTlBox').hidden = false;
}
function buildInfra() {
  if (!HAS_INFRA) return;
  buildInfraTimeline();
  const GROUPS = [['edu', '교육'], ['transit', '교통'], ['power', '전기']];
  // 단지마다 되풀이되는 설명(자료 기준일 등)은 카드마다 쓰지 않고 목록 아래에 한 번만 적는다.
  const checks = BLOCKS.map((b) => IL.projectChecks(b, INFRA, CTX)), seen = new Map();
  checks.forEach((ck) => GROUPS.forEach(([g]) => ck[g].forEach((r) => { if (r.detail && r.generic) { const e = seen.get(r.detail) || { n: 0, label: r.label }; e.n++; seen.set(r.detail, e); } })));
  const common = new Map([...seen].filter(([, e]) => e.n >= 2));
  $('#infraNotes').innerHTML = [...common].map(([d, e]) => `<li><b>${esc(e.label)}</b> ${esc(d)}</li>`).join('');
  $('#infraNotes').hidden = !common.size;
  // 입주(또는 준공 예정)가 이른 단지부터. 시기를 모르면 맨 뒤(같으면 지도 목록 순서).
  const order = BLOCKS.map((b, i) => i).sort((a, c) => String(IL.moveInYm(BLOCKS[a].moveIn) || '9999-99').localeCompare(String(IL.moveInYm(BLOCKS[c].moveIn) || '9999-99')) || a - c);
  $('#infraList').innerHTML = order.map((bi) => {
    const b = BLOCKS[bi], ck = checks[bi], k = kindOf(b);
    // 단지당 제목 줄 + 주의(▲) 줄만. 참고 내용은 지도 위 상세 카드와 '자료 기준·출처'에 있다.
    const warns = GROUPS.flatMap(([g]) => ck[g].filter((r) => r.level === 'warn'));
    const lines = warns.map((r) => `<span class="iw"><span class="im warn">▲</span> <b>${esc(r.label)}</b> ${esc(r.ref && r.ref.cmp ? r.detail : r.text)}</span>`).join('');
    return `<li><button type="button" class="card icard" data-id="${esc(b.id)}"><i class="sw ${k}"></i><b>${esc(b.id)} ${esc(b.kind.replace('(공공분양)', ''))}</b><span class="st" style="color:${COLOR[k]}">${esc(b.status)}</span><span class="sub">${esc(moveText(b))}${warns.length ? '' : ' · 주의 없음'}</span>${lines}</button></li>`;
  }).join('');
  const schools = IL.sortSchools(INFRA.schools), sched = schools.filter((s) => s.status === '신설예정'), sites = schools.length - sched.length;
  $('#infraSchools').innerHTML = sched.map((s) => {
    const nb = IL.nearestBlock(BLOCKS, [s.lon, s.lat]), sc = IL.scaleText(s);
    const sub = [s.level, sc ? `${sc} 계획` : null, nb ? `가까운 단지 ${nb.block.id} ${IL.fmtDist(nb.d)}` : null].filter(Boolean).join(' · ');
    return `<li><button type="button" class="ibtn" data-sid="${esc(s.id)}" aria-label="${esc(`${s.name}, ${IL.fmtYm(s.openYm)} 개교 예정. 누르면 지도에서 보기`)}"><span class="iy">${esc(IL.fmtYm(s.openYm))}</span><span><b>${esc(s.name)}</b><span class="s">${esc(sub)}</span></span></button></li>`;
  }).join('') || '<li class="inote">개교 일정이 공시된 학교가 없습니다.</li>';
  $('#infraSchoolsBox').hidden = !schools.length; $('#infraSchoolsN').textContent = `개교 ${sched.length}곳${sites ? ` · 일정 미공시 부지 ${sites}곳(지도에 표시)` : ''}`;
  const whenTxt = (w) => (/^\d{4}-\d{2}$/.test(w || '') ? IL.fmtYm(w) : /^\d{4}$/.test(w || '') ? `${w}년` : '');
  const link = (id) => { const x = (INFRA.sources || []).find((y) => y.id === id); if (!x) return esc(id); const u = safeUrl(x.url); return u ? `<a href="${esc(u)}" target="_blank" rel="noopener noreferrer">${esc(x.label)}</a>` : esc(x.label); };
  const measures = INFRA.measures || [];
  $('#infraMeasures').innerHTML = measures.map((m) => {
    const meta = [whenTxt(m.when), m.status].filter(Boolean).join(' · ');
    return `<li><span class="ihead"><span class="ichip ${esc(m.category)}">${esc(m.category)}</span><b>${esc(m.title)}</b></span>${meta ? `<span class="imeta">${esc(meta)}</span>` : ''}${m.detail ? `<small title="${esc(m.detail)}">${esc(m.detail)}</small>` : ''}<span class="isrc">출처: ${(m.sources || []).map(link).join(' · ')}</span></li>`;
  }).join('');
  $('#infraMeasuresBox').hidden = !measures.length; $('#infraMeasuresN').textContent = `${measures.length}건`;
  $('#infraSrc').textContent = `기준 ${INFRA.asOf}. 출처: ${(INFRA.sources || []).map((x) => x.label).join(' · ')}. 정류장은 연 1회 수집한 위치 자료이고, 학교 부지는 도시계획시설 결정 자료라 지어졌는지는 알려 주지 않습니다.`;
  $('#secInfra').hidden = false;
}
buildInfra();
/* 입주 전 점검은 길어서 기본 접힘이다. 구역 제목을 누르거나, 요약의 '기반시설 보기'·보기 기준의 '기반시설'을 누르면 열린다. */
function setInfraOpen(open) {
  const b = $('#infraToggle'); b.setAttribute('aria-expanded', String(open)); $('#infraBody').hidden = !open;
  b.querySelector('.sech-h').textContent = open ? '접기' : '펼치기';
}
$('#infraToggle').addEventListener('click', () => setInfraOpen($('#infraBody').hidden));
if (HAS_INFRA && viewMode === 'infra') setInfraOpen(true);
/* 개교 일정에서 학교를 누르면 그 학교로 날아가 카드를 연다(꺼 둔 기반시설 표시는 켠다). */
function focusSchool(id) {
  const s = (INFRA.schools || []).find((x) => x.id === id); if (!s) return;
  stopMotion();
  if (!infraOn) { infraOn = true; syncChips(); applyInfra(); syncUrl(openId()); }
  if (innerWidth <= 900) setSheet('peek');
  select(null);
  map.once('moveend', () => setTimeout(() => schoolPopup(s), 80));
  flyTo({ center: [s.lon, s.lat], zoom: 16.3, pitch: 56, bearing: -10 });
  say(`${s.name} 부지로 이동합니다.`);
}
if (HAS_INFRA) {
  $('#infraList').addEventListener('click', (e) => { const btn = e.target.closest('button[data-id]'); if (btn) focusBlock(btn.dataset.id, { toggle: false, scroll: false }); });
  $('#infraSchools').addEventListener('click', (e) => { const btn = e.target.closest('button[data-sid]'); if (btn) focusSchool(btn.dataset.sid); });
}
$('#nextList').addEventListener('click', (e) => { const b = e.target.closest('button[data-ids]'); if (b) showGroup(idsOf(b)); });
$('#sheetHandle').addEventListener('click', () => setSheet({ peek: 'half', half: 'full', full: 'peek' }[$('#panel').dataset.sheet]));
if (innerWidth <= 900) setSheet('peek');

if (REG.home?.isSchematicPreview) $('#basis').textContent = '가상 모형 · 실제 위치·설계 아님';
else if (HAS_GY) $('#basis').textContent = BASIS;
else $('#baseNote').textContent = ['이 지역의 공식 건물 자료가 아직 없습니다', $('#baseNote').textContent].filter(Boolean).join(' · ');

let firstIdle = true;
map.on('idle', () => {
  const s = STATUS; s.loaded = true;
  if (firstIdle) {
    firstIdle = false; if (LV) LV.close(); else $('#loading').hidden = true;   // 남은 영역을 모두 채우고 0.35초 동안 걷는다
    const at = document.querySelector('.maplibregl-ctrl-attrib'); if (at) { at.classList.remove('maplibregl-compact-show'); at.removeAttribute('open'); }   // 출처 표기는 접어 두고 ⓘ를 누르면 펼친다
    const want = q.get('block') || (RES && RES.block), wb = want && REG.resolveBlock ? REG.resolveBlock(want) : null; if (wb && BLOCKS.includes(wb)) focusBlock(wb.id, { toggle: false });   // 주소 ?block= 이 우선, 없으면 필지로 열었을 때 그 필지의 인허가 단지
  }
  const c = map.getCenter(); s.center = [c.lng, c.lat]; s.zoom = map.getZoom(); s.pitch = map.getPitch(); s.terrain = !!map.getTerrain();
  try {
    const dongs = map.getLayer('dong-3d') ? map.queryRenderedFeatures(undefined, { layers: ['dong-3d'] }) : [];
    s.dongPieces = dongs.length; s.dongNos = [...new Set(dongs.map((f) => f.properties.no))].sort();
    s.blocks = map.getLayer('blk-line') ? [...new Set(map.queryRenderedFeatures(undefined, { layers: ['blk-line', 'blk-line-plan'] }).map((f) => f.properties.id))].sort() : [];
  } catch (_) {}
  if (q.get('selftest')) document.documentElement.setAttribute('data-status', JSON.stringify(s));
});

/* ---------- 첫 화면 쌓기 연출(시험): 주소에 intro=stack 이 있을 때만. 로딩 화면이 걷힌 뒤 레이어를 묶음별로 차례로 드러낸다(약 3초) ----------
   ① 배경 지도·지형 음영(걷힐 때 이미 보임) → ② 지구 경계·마스크 → ③ 기존 건물 → ④ 단지 면·무늬·윤곽 → ⑤ 동 3D(바닥에서 솟음) → ⑥ 이름표·HUD·역·학교·기반시설·버스.
   불투명도는 paint '*-transition' 으로 올린다(처음 숨길 때 원래 값·식과 전환을 저장했다가 그대로 되돌린다). 3D 층은 페이드 없이 바로 켠다(벽·지붕이 함께 반투명하면 겹쳐 보인다).
   동 높이는 자료 식이라 전환이 안 되므로 원래 식 × feature-state k 로 한 번 바꾸고 프레임마다 k(0→1)만 바꾼 뒤 원래 식으로 되돌린다(식을 매 프레임 바꾸면 워커 재타일링·바닥 텍스처 비우기 — 계획서 14.3 ④).
   지형 음영은 평지에서 얼룩만 만들어 단계에서 뺐다(2026-10-10, 14.3 ①).
   지형(terrain)이 켜져 있으면 바닥 층(면·선·음영)은 타일 텍스처에 구워 두고 스타일이 바뀔 때만 다시 그리므로, 서서히 드러나는 동안에는 프레임마다 그 텍스처를 비운다.
   한 번만 돈다. 테마·배경을 바꿔 스타일을 다시 불러오면(새 레이어는 원래 값) 그만둔다. 움직임 줄이기면 하지 않고, 누르거나 휠·키를 쓰면 바로 끝낸다.
   시험 캡처용 window.__introStack.step(n): n 단계까지 바로(전환 없이) 보인다(0 = 배경만, 6 = 모두). */
const INTRO_ON = q.get('intro') === 'stack' && !reduceMotion;
if (INTRO_ON) (function introStack() {
  const STACK = [
    [],                                                                                        // ① 배경 지도·지형 음영
    ['district-mask', 'district-line', 'resolved-fill', 'resolved-halo', 'resolved-line'],    // ② 지구 경계·마스크(코드로 연 경계 포함)
    ['official-flat', 'official-flat-line', 'official-outline', 'official-ao', 'official-shadow', 'official-far', 'official-3d', 'official-roof'],   // ③ 기존 건물
    ['other-fill', 'other-line', ...BLK_FILLS, 'blk-line', 'blk-line-plan'],                  // ④ 단지 면·무늬·윤곽
    ['dong-shadow', 'dong-line', 'dong-3d'],                                     // ⑤ 동 3D(높이는 grow 가 키운다)
    ['blk-dot', 'blk-label-lo', 'blk-badge', 'blk-badge-top', 'dong-label', 'fac-label', 'district-label', 'ctx-ring', 'ctx-school', 'ctx-station', 'ctx-ring-label', 'ctx-station-label', 'ctx-school-label', ...INFRA_LAYERS, ...INFRA_MODE_LAYERS, ...ZONE_LAYERS, ...BUS_LAYERS],   // ⑥ 이름표·역·학교·기반시설·버스(+ HUD)
  ];
  const AT = [0, 350, 800, 1250, 1700, 2200], FADE = 450, GROW = 900, GROW_AT = 4;   // 단계 시작(첫 idle 부터 ms) · 드러나는 시간 · 동이 솟는 시간 · 솟는 단계(⑤)
  const OP = { fill: ['fill-opacity'], line: ['line-opacity'], 'fill-extrusion': ['fill-extrusion-opacity'], circle: ['circle-opacity', 'circle-stroke-opacity'], symbol: ['text-opacity', 'icon-opacity'], hillshade: ['hillshade-exaggeration'] };
  const HUD_EL = [$('#hud')].filter(Boolean), EV = ['pointerdown', 'wheel', 'keydown'], SAVED = new Map(), timers = [];
  let state = 'wait', first = true, raf = 0, H0, fadeUntil = 0;   // wait → run → done(한 번만)
  function put(id, on, dur) {   // 레이어 하나를 원래 불투명도(on) 또는 0 으로. 처음 만날 때 원래 값·전환을 저장한다. 숨길 때는 늘 바로
    const L = map.getLayer(id); if (!L) return;
    for (const p of OP[L.type] || []) {
      const k = id + '|' + p;
      if (!SAVED.has(k)) SAVED.set(k, [map.getPaintProperty(id, p), map.getPaintProperty(id, p + '-transition')]);
      map.setPaintProperty(id, p + '-transition', { duration: on && L.type !== 'fill-extrusion' ? dur : 0, delay: 0 });   // 3D 는 바로
      map.setPaintProperty(id, p, on ? SAVED.get(k)[0] : 0);
    }
  }
  function show(n, dur) {   // n 단계까지 보이고 나머지는 숨긴다
    STACK.forEach((ids, i) => { for (const id of ids) put(id, i < n, dur); });
    for (const el of HUD_EL) { el.style.transition = dur ? `opacity ${dur}ms` : ''; el.style.opacity = n >= STACK.length ? '' : '0'; }
    if (dur) fadeUntil = performance.now() + dur + 50;
  }
  const setH = (v) => { if (v !== undefined && map.getLayer('dong-3d')) map.setPaintProperty('dong-3d', 'fill-extrusion-height', v); };
  const setK = (k) => { if (!map.getSource('dongs')) return; if (k == null) map.removeFeatureState({ source: 'dongs' }); else for (const id of new Set(DONG_FEATS.map((f) => f.properties.key))) map.setFeatureState({ source: 'dongs', id }, { k }); };
  function grow() {   // ⑤ 원래 높이 식 × feature-state k(끝으로 갈수록 느리게). k 는 경과 시간으로 정해 프레임이 밀려도 같은 때 끝난다
    if (!map.getLayer('dong-3d')) return;
    H0 = map.getPaintProperty('dong-3d', 'fill-extrusion-height'); put('dong-3d', true, 0);
    setK(0); setH(['*', H0, ['coalesce', ['feature-state', 'k'], 1]]);   // 식은 한 번만 바꾼다
    const t0 = performance.now(), tick = (t) => { const k = Math.min(1, (t - t0) / GROW); if (k < 1) { setK(1 - (1 - k) ** 3); raf = requestAnimationFrame(tick); } else { raf = 0; setH(H0); setK(null); } };
    raf = requestAnimationFrame(tick);
  }
  function rtt() { const tm = performance.now() < fadeUntil && map.terrain && map.terrain.tileManager; if (tm && tm.freeRtt) tm.freeRtt(); }   // 지형 위 바닥 층 텍스처 비우기(MapLibre 5.x 내부 API, 없으면 단계마다 한 번씩만 바뀐다)
  function stop() { timers.forEach(clearTimeout); timers.length = 0; cancelAnimationFrame(raf); raf = 0; EV.forEach((e) => window.removeEventListener(e, skip, true)); map.off('render', rtt); }
  function finish(dur) {   // 모두 원래대로: 원래 불투명도(dur 0 이면 바로)·원래 높이 식, 그것이 그려진 다음에 원래 전환
    if (state === 'done') return; state = 'done'; stop();
    show(STACK.length, dur); setH(H0); if (H0 !== undefined) setK(null);
    map.once('render', () => { for (const [k, v] of SAVED) { const [id, p] = k.split('|'); if (map.getLayer(id)) map.setPaintProperty(id, p + '-transition', v[1]); } for (const el of HUD_EL) el.style.transition = ''; });
    map.triggerRepaint();
  }
  function skip() { finish(0); }
  function start() {   // 첫 idle(로딩 화면이 걷히기 시작할 때). ① 은 바로, 나머지는 AT 시각에
    if (state !== 'wait') return; state = 'run';
    EV.forEach((e) => window.addEventListener(e, skip, { capture: true, passive: true }));
    map.on('render', rtt);
    show(1, FADE);   // 첫 idle 에 붙은 건물 그림자(official-shadow)도 여기서 숨긴다
    AT.forEach((t, i) => { if (i) timers.push(setTimeout(() => { show(i + 1, FADE); if (i === GROW_AT) grow(); }, t)); });
    timers.push(setTimeout(() => finish(FADE), Math.max(AT[GROW_AT] + GROW, AT[AT.length - 1] + FADE) + 100));
  }
  for (const el of HUD_EL) el.style.opacity = '0';   // HUD 는 지도보다 먼저 그려질 수 있다
  map.on('style.load', () => {   // setupCustom 다음에 불린다(먼저 등록됨)
    if (first) { first = false; show(0, 0); map.once('idle', start); return; }   // 첫 스타일: 그리기 전에 숨긴다. 첫 idle 의 로딩 화면 걷기·그림자 추가보다 뒤에 불린다
    state = 'done'; stop(); SAVED.clear(); H0 = undefined; for (const el of HUD_EL) { el.style.transition = ''; el.style.opacity = ''; }   // 스타일을 다시 불러왔다: 새 레이어는 원래 값이므로 그만두고 다시 돌지 않는다
  });
  window.__introStack = { step(n) { stop(); state = 'done'; show(n, 0); setH(H0); if (H0 !== undefined) setK(null); } };   // 시험 캡처용: n 단계 뒤 모습으로 바로
})();

/* ---------- 나침반: 지도가 돌면 바늘(북쪽=검정)이 함께 돌아 북쪽이 어디인지 보인다. 보는 방향(도)은 이름표(aria-label·title)로 알린다 ---------- */
const cpRose = $('#cpRose');
function syncCompass() {
  const b = map.getBearing(), n = normB(b), name = DIRS[Math.round(n / 45) % 8];
  cpRose.setAttribute('transform', `rotate(${(-b).toFixed(2)})`);
  const lab = `나침반. 보는 방향 ${n}도, ${name}쪽. 누르면 북쪽이 위로 오게 합니다`;
  if ($('#compass').getAttribute('aria-label') !== lab) { $('#compass').setAttribute('aria-label', lab); $('#compass').title = lab; }
}
$('#compass').addEventListener('click', () => { stopMotion(); map.easeTo({ bearing: 0, duration: dur }); });
map.on('move', syncCompass);
syncCompass();

/* ---------- 사이드바 스크롤: 큰 제목이 접히고, 구역 제목이 위에 붙어 따라오며, 오른쪽 점 레일로 구역을 오간다 ---------- */
(function panelScroll() {
  const sc = $('#pscroll'), head = $('#phead'), cur = $('#pcur');
  const secs = [...document.querySelectorAll('#prail button')].map((b) => ({ btn: b, el: document.getElementById(b.dataset.sec).closest('section'), name: b.getAttribute('aria-label') }));
  const topOf = (el) => el.getBoundingClientRect().top - sc.getBoundingClientRect().top + sc.scrollTop;
  let raf = 0;
  const upd = () => {
    raf = 0;
    const vis = secs.filter((x) => !x.el.hidden), max = sc.scrollHeight - sc.clientHeight, y = sc.scrollTop;
    head.classList.toggle('scrolled', y > 6);
    let now = vis[0];
    for (const x of vis) if (topOf(x.el) <= y + 40) now = x;
    if (max > 8 && y >= max - 4) now = vis[vis.length - 1];   // 맨 아래에 닿으면 마지막 구역
    secs.forEach((x) => {
      const on = x === now;
      if ((x.btn.getAttribute('aria-current') === 'true') !== on) { if (on) x.btn.setAttribute('aria-current', 'true'); else x.btn.removeAttribute('aria-current'); }
      const t0 = topOf(x.el); x.el.classList.toggle('stuck', t0 < y - 1 && t0 + x.el.offsetHeight > y + 36);   // 제목이 위에 붙어 있는 구역에만 그림자
    });
    const t = `${vis.indexOf(now) + 1}/${vis.length} ${now.name}`; if (cur.textContent !== t) cur.textContent = t;
  };
  const sched = () => { if (!raf) raf = requestAnimationFrame(upd); };
  sc.addEventListener('scroll', sched, { passive: true });
  window.addEventListener('resize', sched);
  if (window.ResizeObserver) { const ro = new ResizeObserver(sched); ro.observe(sc); secs.forEach((x) => ro.observe(x.el)); }
  $('#prail').addEventListener('click', (e) => {
    const b = e.target.closest('button[data-sec]'); if (!b) return;
    if (b.dataset.sec === 'h-infra') setInfraOpen(true);   // 접혀 있으면 열고 간다
    const x = secs.find((y) => y.btn === b); sc.scrollTo({ top: x === secs.find((z) => !z.el.hidden) ? 0 : topOf(x.el), behavior: reduceMotion ? 'auto' : 'smooth' });
  });
  secs.forEach((x) => { x.btn.hidden = x.el.hidden; });   // 내용이 없는 구역(예: 다음 일정)은 레일에서도 뺀다
  upd();
})();

/* ---------- HUD: 단지마다 모서리 표시선(레티클)과 정보창을 화면에 고정된 크기로 그린다 ---------- */
let hudRaf = 0; const hudPrev = {}, hudSz = {};
function renderHudContent() {
  const host = $('#hudTags'); if (!host || !BLOCKS.length) return;
  if (!host.children.length) host.innerHTML = BLOCKS.map((b) => `<button type="button" class="hudtag" data-id="${esc(b.id)}"></button>`).join('');
  const T = TH();
  BLOCKS.forEach((b) => {
    const el = byId(host, 'data-id', b.id), k = kindOf(b), fr = floorsRange(b);
    el.style.setProperty('--c', T.color[k]); el.style.setProperty('--cd', COLOR[k]);
    const line = fr ? `${b.homeModelKind === 'SCHEMATIC' ? '가상 ' : ''}${fr[0] === fr[1] ? fr[0] : fr[0] + '~' + fr[1]}층` : '층수 미확인';
    const chips = HAS_INFRA && infraOn ? chipsOf(b, viewMode === 'infra') : '';   // 평소엔 주의만(지도를 덜 가리게), 기반시설 보기에서는 세 종류 모두
    el.innerHTML = `<span class="ht-h"><b>${esc(b.id)}</b><i>${esc(b.status)}</i></span><span class="ht-m">${unitsTxt(b)}${dongN(b) ? ` · ${b.homeModelKind === 'SCHEMATIC' ? '가상 ' : ''}${dongN(b)}개동` : ''}</span><span class="ht-s">${line}${chips && viewMode !== 'infra' ? `<span class="ht-i">${chips}</span>` : ''}</span>${chips && viewMode === 'infra' ? `<span class="ht-i">${chips}</span>` : ''}`;   // 평소엔 층수 줄 끝에 붙여 높이를 늘리지 않는다
    const sx = HAS_INFRA && infraOn ? SUMM_BY.get(b.id) : null;
    el.setAttribute('aria-label', `${b.id} ${b.status}${b.priv ? ', 공공택지 민간' : ''}, ${unitsTxt(b)}${dongN(b) ? `, ${dongN(b)}개동` : ''}${sx ? `. 입주 전 점검 ${Object.keys(IL.GROUP_NAMES).filter((g) => sx.levels[g]).map((g) => `${IL.GROUP_NAMES[g]} ${LVL_WORD[sx.levels[g]]}`).join(', ')}` : ''}. 누르면 지도에서 보기`);
    delete hudSz[b.id];
  });
  scheduleHud();
}
function scheduleHud() { if (!hudRaf) hudRaf = requestAnimationFrame(renderHud); }
/* 하단 띠(범례) 높이를 CSS 변수로 알려 지도 컨트롤·시간 바가 그 위에 서게 한다 */
(function botbarSize() {
  const bb = $('#botbar'), wrap = $('.mapwrap'); if (!bb || !wrap) return;
  const set = () => wrap.style.setProperty('--botbar-h', bb.offsetHeight + 'px');
  if (window.ResizeObserver) new ResizeObserver(set).observe(bb);
  set();
})();
const HUD_EXCL = '.topbar, .rctl, .maplibregl-ctrl-bottom-right, #botbar, #optPanel:not([hidden]), #panelToggle';
function renderHud() {
  hudRaf = 0;
  const hud = $('#hud'), on = (hudOn || cardsOn) && HAS_PR && BLOCKS.length && map.getZoom() < HUD_MAXZ;
  hud.hidden = !on; if (!on) return;
  const mr = hud.getBoundingClientRect(), W = mr.width, H = mr.height, T = TH(), pad = 6;
  const ex = [...document.querySelectorAll(HUD_EXCL + (innerWidth <= 900 ? ', #panel' : ''))].map((e) => e.getBoundingClientRect()).filter((r) => r.width > 2 && r.height > 2)
    .map((r) => ({ l: r.left - mr.left - pad, t: r.top - mr.top - pad, r: r.right - mr.left + pad, b: r.bottom - mr.top + pad }));
  const hit = (a, b) => a.l < b.r && b.l < a.r && a.t < b.b && b.t < a.b;
  const placed = [], parts = [];
  const order = BLOCKS.filter(blockVisible).sort((a, c) => c.units - a.units);
  BLOCKS.forEach((b) => { const el = byId($('#hudTags'), 'data-id', b.id); el.hidden = !cardsOn || !blockVisible(b); });
  for (const b of order) {
    const el = byId($('#hudTags'), 'data-id', b.id), k = kindOf(b), col = T.color[k];
    const ps = b.poly.map((c) => map.project(c));
    let x0 = Math.min(...ps.map((p) => p.x)), x1 = Math.max(...ps.map((p) => p.x)), y0 = Math.min(...ps.map((p) => p.y)), y1 = Math.max(...ps.map((p) => p.y));
    if (x1 < -30 || x0 > W + 30 || y1 < -30 || y0 > H + 30) { el.hidden = true; continue; }
    const cx = (x0 + x1) / 2, cy = (y0 + y1) / 2;
    if (x1 - x0 < 22) { x0 = cx - 11; x1 = cx + 11; } if (y1 - y0 < 22) { y0 = cy - 11; y1 = cy + 11; }
    x0 -= 6; x1 += 6; y0 -= 6; y1 += 6;
    const L = Math.max(6, Math.min(14, (x1 - x0) / 3, (y1 - y0) / 3));
    const d = `M${x0},${y0 + L}V${y0}H${x0 + L}M${x1 - L},${y0}H${x1}V${y0 + L}M${x1},${y1 - L}V${y1}H${x1 - L}M${x0 + L},${y1}H${x0}V${y1 - L}`;   // 모서리 표시선(레티클)
    if (!cardsOn) { el.hidden = true; parts.push(`<path d="${d}" fill="none" stroke="${T.halo}" stroke-width="5" stroke-linecap="square"/><path d="${d}" fill="none" stroke="${col}" stroke-width="2.2" stroke-linecap="square"/>`); continue; }
    const sz = hudSz[b.id] || (hudSz[b.id] = { w: el.offsetWidth, h: el.offsetHeight }), TW = sz.w, TH_ = sz.h;
    const cands = [[x1 + 16, y0 - 4], [x0 - 16 - TW, y0 - 4], [x1 + 16, y1 - TH_ + 4], [x0 - 16 - TW, y1 - TH_ + 4], [cx - TW / 2, y0 - 16 - TH_], [cx - TW / 2, y1 + 16]];
    const rectOf = (c) => ({ l: c[0], t: c[1], r: c[0] + TW, b: c[1] + TH_ });
    const inside = (r) => r.l >= 4 && r.t >= 4 && r.r <= W - 4 && r.b <= H - 4;
    const conflicts = (r) => (inside(r) ? 0 : 3) + ex.filter((e) => hit(r, e)).length + placed.filter((e) => hit(r, e)).length;
    const first = hudPrev[b.id] != null ? hudPrev[b.id] : 0;
    let best = first, bestC = conflicts(rectOf(cands[first]));
    if (bestC > 0) cands.forEach((c, i) => { const n = conflicts(rectOf(c)); if (n < bestC) { best = i; bestC = n; } });
    hudPrev[b.id] = best;
    const c = cands[best], r = rectOf(c); placed.push(r);
    el.style.transform = `translate(${Math.round(c[0])}px,${Math.round(c[1])}px)`;
    // 정보창(카드)으로 이어지는 점선
    const kx = c[0] > cx ? x1 : x0, ky = c[1] + TH_ / 2 > cy ? y1 : y0;
    const tx = Math.min(Math.max(kx, r.l), r.r), ty = Math.min(Math.max(ky, r.t), r.b);
    parts.push(`<path d="${d}" fill="none" stroke="${T.halo}" stroke-width="5" stroke-linecap="square"/><path d="${d}" fill="none" stroke="${col}" stroke-width="2.2" stroke-linecap="square"/>`
      + `<line x1="${kx}" y1="${ky}" x2="${tx}" y2="${ty}" stroke="${T.halo}" stroke-width="3.5"/><line x1="${kx}" y1="${ky}" x2="${tx}" y2="${ty}" stroke="${col}" stroke-width="1.4" stroke-dasharray="3 3"/>`
      + `<circle cx="${kx}" cy="${ky}" r="3" fill="${col}" stroke="${T.halo}" stroke-width="1.5"/>`);
  }
  $('#hudSvg').innerHTML = parts.join('');
}
$('#hudTags').addEventListener('click', (e) => { const t = e.target.closest('button[data-id]'); if (t) focusBlock(t.dataset.id); });
map.on('rotate', () => {   // 카메라 방향이 바뀌면 '가까운 쪽'도 바뀌므로 라벨 자리를 다시 잡는다(20도 이상 돌았을 때만)
  const b = map.getBearing(), d = frontBearing == null ? 999 : Math.abs(((b - frontBearing + 540) % 360) - 180);
  if (d >= 20) { const src = map.getSource('block-fronts'); if (src) src.setData(blockFrontsGeoJSON()); }
});
map.on('render', scheduleHud); map.on('resize', () => { for (const k in hudSz) delete hudSz[k]; scheduleHud(); });

/* ---------- 사이드바 접기 + 공급 요약(머리 줄 오른쪽) ---------- */
/* 공급 요약: 머리 줄 '06 입주' 카드 오른쪽(옛 보기 기준 단추 자리)에 합계·단계 막대·번호 범례 | 입주 전 점검 칩. 2026-10-10 지도 위 떠 있는 카드에서 옮겼다.
   지역 이름·바꾸기는 머리 줄 왼쪽, 다음 일정은 사이드바에 있어 여기서는 뺀다. 900px 이하는 하단 시트가 대신한다 */
const HS_ICON = {   // lucide building · circle-question-mark(ISC)
  blk: '<svg viewBox="0 0 24 24"><rect x="4" y="2" width="16" height="20" rx="2"/><path d="M9 22v-3a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v3M8 6h.01M16 6h.01M12 6h.01M12 10h.01M12 14h.01M16 10h.01M16 14h.01M8 10h.01M8 14h.01"/></svg>',
  unk: '<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="10"/><path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3M12 17h.01"/></svg>',
};
function syncHudSum() {
  if (REG.home) return;   // HOME 요약은 중복 미조정 원천 호수를 합산하지 않는다.
  const tot = SUM_TOTAL || { main: $('#sumTotal').textContent, sub: '' };
  const side = HAS_INFRA && SUMM && SUMM.blocks.length ? `<button type="button" class="isum" data-act="infra">${infraSumHtml()}</button>` : '';
  $('#hudSum').classList.toggle('solo', !side);   // 점검 자료가 없는 지역은 합계 열만
  /* 단지 수·세대수 미확인 수는 아이콘+숫자로 줄여 한 줄에 둔다(문장이 두 줄이 되면 머리 줄을 넘쳤다, 2026-10-10). 문장은 title 과 화면 낭독기용으로 남긴다 */
  const meta = tot.n == null ? `<span>${esc(tot.sub)}</span>`
    : `<span class="hs-meta" title="${esc(tot.sub)}"><span class="sr">${esc(tot.sub)}</span><span aria-hidden="true">${HS_ICON.blk}${tot.n}</span>${tot.unk ? `<span aria-hidden="true">${HS_ICON.unk}${tot.unk}</span>` : ''}</span>`;
  $('#hudSum').innerHTML = `<div class="hs-a"><div class="hs-total"><b>${esc(tot.main)}</b>${meta}</div>`
    + `<div class="sbar" role="img" aria-label="${esc($('#sumBar').getAttribute('aria-label') || '')}">${$('#sumBar').innerHTML}</div><div class="sleg">${SUM_COMPACT}</div></div>`
    + (side ? `<div class="hs-b">${side}</div>` : '');
}
function setCollapsed(on, { quiet = false } = {}) {
  $('.app').classList.toggle('collapsed', on);
  const t = $('#panelToggle'); t.setAttribute('aria-expanded', String(!on));
  const lab = on ? '사이드바 펼치기' : '사이드바 접기'; t.setAttribute('aria-label', lab); t.title = lab; t.firstElementChild.textContent = on ? '‹' : '›';
  requestAnimationFrame(() => { map.resize(); scheduleHud(); });
  if (!quiet) { syncUrl(openId()); say(on ? '사이드바를 접었습니다.' : '사이드바를 펼쳤습니다.'); }
}
$('#panelToggle').addEventListener('click', () => setCollapsed(!$('.app').classList.contains('collapsed')));
$('#hudSum').addEventListener('click', (e) => { if (e.target.closest('.isum')) openInfra(); });
syncHudSum();
setCollapsed(!REG.home && q.get('panel') !== '1', { quiet: true });   // 9·7 후보 지도는 목록이 보이게 패널을 연다. 기존 지역 지도의 접힘 동작은 유지한다.
renderHudContent();

if (REG.home) window.__homeScene = {
  blocks: BLOCKS,
  focus(candidateId) {
    const b = BLOCKS.find((site) => site.candidateIds?.includes(candidateId));
    if (!b) return false;
    HOME_VISIBLE.add(b.id); applyFilters(); focusBlock(b.id, { toggle: false });
    const url = new URL(location.href); url.searchParams.set('homeProject', candidateId); history.replaceState(null, '', url);
    return true;
  },
  filter(candidateIds) {
    const ids = new Set(candidateIds);
    HOME_VISIBLE = new Set(BLOCKS.filter((b) => b.candidateIds?.some((id) => ids.has(id))).map((b) => b.id));
    applyFilters();
  },
};

if (q.get('selftest')) {   // 시험 전용 훅(운영 주소에는 붙지 않음)
  window.__map = map; window.__blocks = BLOCKS;
  window.__st = () => ({ viewMode, ctxOn, ringOn, infraOn, zoneOn, busOn, bus: HAS_BUS ? { n: BUS.cur.length, at: BUS.at, ttl: BUS.ttl, failures: BUS.failures, off: BUS.off } : null, selId, selDong, tourOn });
}


/* 헤더의 테마 전환: 카메라·필터·펼친 카드는 유지하고 스타일과 색만 다시 적용한다. */
if (document.documentElement.hasAttribute('data-map-shell')) {
  window.addEventListener('housing:theme-change', () => {
    const nextLight = !document.documentElement.classList.contains('dark');
    if (nextLight === LIGHT_MAP) return;
    const oldColor = { ...COLOR };
    LIGHT_MAP = nextLight;
    applyStageInk();   // 클래스가 바뀐 뒤라 새 테마의 --st-*-ink 를 읽는다
    TONE = TH().tone;
    const newColor = { ...COLOR };
    STAGES6.forEach((stage) => { stage[3] = stageColor(stage[2]); });
    // 이미 열린 카드의 클릭 핸들러와 펼침 상태를 보존하면서 인라인 상태색을 바꾼다.
    const replacement = new Map(Object.keys(oldColor).map((kind) => [oldColor[kind].toLowerCase(), newColor[kind]]));
    document.querySelectorAll('.app [style], .maplibregl-popup [style]').forEach((element) => {
      const style = element.getAttribute('style');
      const updated = style.replace(/#[0-9a-f]{6}/gi, (color) => replacement.get(color.toLowerCase()) || color);
      if (style !== updated) element.setAttribute('style', updated);
    });
    document.querySelectorAll('.app svg [fill], .app svg [stroke]').forEach((element) => {
      for (const name of ['fill', 'stroke']) {
        const value = element.getAttribute(name);
        const next = value && replacement.get(value.toLowerCase());
        if (next) element.setAttribute(name, next);
      }
    });
    STATUS.loaded = false;
    map.once('style.load', () => { STATUS.loaded = true; });
    map.setStyle(baseStyle(), { diff: false });
  });
}
