/* 종합상황판 시안(주택파동_종합상황판_최종)의 SAMPLE 데이터와 계산을 그대로 옮긴 것. 수치는 전부 샘플이다(성북구 사업 외에는 실데이터가 아니다).
   원본을 실행해 뽑은 기준값(tests/fixtures/board-sample-golden.json)과 같은 숫자를 내는지 tests/js/boardsample.test.cjs 가 확인한다.
   계산식은 시안과 일부러 똑같이 두었다. 실데이터가 생기는 위젯은 이 파일이 아니라 lib/board/data.ts 를 읽는 쪽으로 바꿔 간다. */

export const NOW = 21;   // 2026.10 (2025.01 = 0)
export const LAST = 45;  // 2028.10
export const CIR = ['①', '②', '③', '④', '⑤', '⑥'];
export const K = ['계획', '인허가', '착공', '모집', '준공', '입주'];
/* 6단계 색: 테마별 값은 app/tailwind.css 의 --st-* (차트 면 색, 라이트·다크). SVG 와 인라인 스타일이 var() 로 읽는다 */
export const C = ['var(--st-plan)', 'var(--st-permit)', 'var(--st-build)', 'var(--st-sale)', 'var(--st-soon)', 'var(--st-move)'];

type Knot = [number, number[]];
const AN: Knot[] = [
  [0, [52000, 22000, 14000, 4000, 5000, 3000]],
  [9, [40000, 24000, 18000, 6000, 7000, 5000]],
  [15, [31000, 22500, 22000, 7500, 9500, 7500]],
  [21, [24000, 21000, 26000, 9000, 12000, 8000]],
  [27, [17000, 17000, 29000, 10000, 14700, 12300]],
  [33, [11000, 13500, 29000, 10000, 19600, 16900]],
  [45, [4000, 7000, 22000, 8000, 22000, 37000]],
];
export const AD: [number, number][] = [[0, 1200], [9, 3400], [15, 6100], [21, 10000]];
export const AW: [number, number][] = [[0, 2100], [9, 4500], [15, 9800], [21, 18000]];
const STG = [[1800, 3000], [3200, 5400], [4100, 6300], [300, 1200], [400, 1500], [200, 600]];   // [지연, 주의] 2026.10
export const YT = [82000, 100000, 112000, 124000];   // 연도별 총 공급 규모 2025~2028
export const ACH = { p: [34.6, 40.0], a: [29.7, 34.1] };   // 착공 누적 계획·실적(천 호), 2026.08 · 2026.09
export const AG: [string, number, number, number][] = [   // [기관, 정상, 주의, 지연]
  ['LH', 37500, 9100, 5400], ['GH', 14900, 4300, 1800], ['SH', 10300, 2300, 1400], ['지자체·민관', 6000, 1500, 500], ['국방부(군 특공)', 3300, 800, 900],
];

export type Region = { n: string; d: number; w: number; ok: number; big: boolean; tot: number; code: string };
const REG_ROWS: [string, number, number, number, number?][] = [
  ['서울', 15, 33, 120, 1], ['경기', 23, 60, 231, 1],
  ['인천', 6, 12, 41], ['부산', 4, 9, 33], ['대구', 2, 6, 21], ['광주', 1, 3, 14], ['대전', 1, 4, 16], ['울산', 1, 2, 9],
  ['세종', 0, 3, 17], ['강원', 2, 5, 22], ['충북', 2, 5, 20], ['충남', 3, 8, 31], ['전북', 2, 4, 19], ['전남', 3, 6, 24],
  ['경북', 3, 7, 28], ['경남', 4, 9, 35], ['제주', 1, 2, 8],
];
/* 시안의 시도 17곳 → 행정표준코드 시도 2자리. 광주·전남은 2026-07 통합으로 둘 다 12(전남광주)를 가리킨다. */
export const REGION_CODE: Record<string, string> = {
  서울: '11', 경기: '41', 인천: '28', 부산: '26', 대구: '27', 광주: '12', 대전: '30', 울산: '31', 세종: '36', 강원: '51', 충북: '43', 충남: '44', 전북: '52', 전남: '12', 경북: '47', 경남: '48', 제주: '50',
};
export const REG: Region[] = REG_ROWS.map((r) => ({ n: r[0], d: r[1], w: r[2], ok: r[3], big: !!r[4], tot: r[1] + r[2] + r[3], code: REGION_CODE[r[0]] }));

export type Directive = { date: string; t: string; m: string; dv?: number; p: string[]; q: string };
/* 지시 6건. 마지막 카드의 '원천 N곳'만 실데이터(원천 카탈로그의 건수)로 채운다. */
export const makeDir = (sourceCount: number): Directive[] => [
  { date: '08.14', t: '진척 관리', m: '달성률 ' + Math.round(ACH.a[1] / ACH.p[1] * 100) + '%', dv: (ACH.a[1] / ACH.p[1] - ACH.a[0] / ACH.p[0]) * 100, p: ['p-chart'], q: '제1차 점검회의 — 주택공급을 최우선 과제로, 예정 일정대로 이행되는지 매월 진척을 보고받고 매주 현장을 점검한다.' },
  { date: '08.19', t: '사업장별 현황판', m: '482 사업장', p: ['p-region'], q: '인천계양 현장점검 — 현황판으로 사업장별 밀착 관리, 입주 전 교통·교육·전기 기반시설까지 함께 점검한다.' },
  { date: '09.03', t: '범부처 통합·병목', m: '병목 착공 4,100호', p: ['p-trend', 'p-agency'], q: '제2차 점검회의 — 부처별 관리로는 전체를 한눈에 파악해 즉시 대응하기 어렵다. 수시 점검과 병목 해소가 핵심이다.' },
  { date: '09.04', t: '예측가능성', m: '착공 6,200호', p: ['p-fut'], q: '동대문 신축매입주택 점검 — 공급계획을 가능한 범위에서 미리 공개해 수요자의 예측가능성을 높인다.' },
  { date: '09.18', t: '일정 지연 관리', m: '지연 38사업', p: ['p-trend'], q: '태릉지구 점검 — 정부가 제시한 착공일정을 전제로 더 이상 일정 지연이 없어야 한다.' },
  { date: '09.30', t: '국민 공개·공식 원천', m: `원천 ${sourceCount}곳`, p: ['p-flow'], q: '제3차 점검회의 — 국민이 공급 진행을 체감하도록 ‘주택공급 디지털 상황판’을 조속히 구현하고 공식 정보를 일관되게 제공한다.' },
];

/* ── 계산 ── */
export const f = (n: number) => n.toLocaleString('en-US');
export const r10 = (n: number) => Math.round(n / 10) * 10;
export const sg = (n: number) => (n >= 0 ? '+' : '−') + f(Math.abs(n));
export const ml = (m: number) => (2025 + Math.floor(m / 12)) + '.' + String(m % 12 + 1).padStart(2, '0');
export const kind = (m: number) => (m === NOW ? '현재' : (m < NOW ? '실적 기준' : '예정 기준'));
/* 시안의 시점(2025.01=0)을 'YYYY-MM' 로. 실데이터 월 상세로 가는 링크에 쓴다. */
export const ymOf = (m: number) => `${2025 + Math.floor(m / 12)}-${String(m % 12 + 1).padStart(2, '0')}`;

export function inv(m: number): number[] {
  for (let i = 0; i < AN.length - 1; i++) {
    const a = AN[i], b = AN[i + 1];
    if (m >= a[0] && m <= b[0]) { const u = (m - a[0]) / (b[0] - a[0]); return a[1].map((v, k) => v + (b[1][k] - v) * u); }
  }
  return AN[AN.length - 1][1];
}
export function ip(arr: [number, number][], m: number): number {
  const mm = Math.min(m, NOW);
  for (let i = 0; i < arr.length - 1; i++) {
    if (mm >= arr[i][0] && mm <= arr[i + 1][0]) { const u = (mm - arr[i][0]) / (arr[i + 1][0] - arr[i][0]); return arr[i][1] + (arr[i + 1][1] - arr[i][1]) * u; }
  }
  return arr[arr.length - 1][1];
}
export const yr = (m: number) => Math.floor(m / 12);
export const tot = (m: number) => YT[yr(m)];
export const vals = (m: number) => { const t = tot(m); return inv(m).map((v) => v / 100000 * t); };
/* 병목: 지연 합계를 (2026.10 단계별 지연율 × 단계 호수)에 비례해 단계마다 나눈다. 2026.10에는 STG 의 지연과 같다. */
export const RT = STG.map((z, k) => z[0] / inv(NOW)[k]);
export const argmax = (a: number[]) => a.reduce((b, v, i) => (v > a[b] ? i : b), 0);
export function dStage(m: number): number[] {
  const w = vals(m).map((c, k) => RT[k] * c), s = w.reduce((a, b) => a + b, 0), D = ip(AD, m);
  return w.map((x) => D * x / s);
}
export const RANGE = Array.from({ length: LAST + 1 }, (_, i) => i);
export const TOPM = RANGE.map((m) => Math.max(...dStage(m)));
export const PEAK = argmax(TOPM);   // 병목 단계의 지연 정점

/* ── 문구 ── */
export const txSnap = (cur: number) => (cur > NOW ? '예정 구간의 판정은 마지막 실적 판정(2026.10) 값을 유지합니다.' : '');
export function txTrend(cur: number) {
  const c = Math.min(cur, NOW), p = Math.max(c - 1, 0);
  return ml(c) + ' 전월 대비 — 지연 ' + sg(r10(ip(AD, c) - ip(AD, p))) + '호 · 주의 ' + sg(r10(ip(AW, c) - ip(AW, p))) + '호';
}
export const txRegion = (r: Region) => r.n + ' — 사업 ' + r.tot + '건 · 지연율 ' + (r.d / r.tot * 100).toFixed(1) + '% · ' +
  (r.big ? '사업 단위 일정·공정·출처까지 연계' : '판정만 연계된 요약 단계 (사업 상세는 확대 대상)');

/* ── 시도 타일 색(바탕색 = 지연율 단계) ── */
export const RTH = [5, 7, 8.5, 10];
export const RCOL = ['var(--region-0)', 'var(--region-1)', 'var(--region-2)', 'var(--region-3)', 'var(--region-4)', 'var(--region-5)'];
export const RLAB = ['0', '~5', '5~7', '7~8.5', '8.5~10', '10+'];
export const rcls = (rate: number) => (rate === 0 ? 0 : 1 + RTH.filter((t) => rate >= t).length);

/* ── 리본 차트 기하(시안과 같은 수식) ── */
export const VW = 960, PX0 = 46, PW = 908, PITCH = PW / (LAST + 1), TOP = 52, PH = 320, BOT = TOP + PH, YMAX = 125000, S2 = PH / YMAX, Y0 = TOP + PH / 2;
export const X = (x: number) => PX0 + x * PW / (LAST + 1);
export const Tx = (x: number) => {   // 연도 경계 앞뒤 1.5개월에 걸쳐 총량을 이어 붙임
  for (let i = 0; i < 3; i++) { const lo = (i + 1) * 12 - 1.5; if (x >= lo && x <= lo + 3) return YT[i] + (YT[i + 1] - YT[i]) * (x - lo) / 3; }
  return YT[Math.min(3, Math.floor(x / 12))];
};
export type Geo = { x: number; lw: number[]; up: number[]; dl: number[] };
export const GEO: Geo[] = [];   // 0.25개월 간격의 층 경계(lw 아래·up 위)와 지연 띠 두께(dl, px)
for (let x = 0; x <= LAST + 1 + 1e-9; x += 0.25) {
  const Tt = Tx(x), s = inv(Math.max(0, x - 0.5)).map((z) => z / 100000), lw: number[] = [], up: number[] = [], dl: number[] = [];
  const w = s.map((z, k) => RT[k] * z), ws = w.reduce((a, b) => a + b, 0), D = ip(AD, Math.max(0, x - 0.5));
  let below = 0;
  for (let k = 5; k >= 0; k--) { lw[k] = Y0 + Tt * S2 / 2 - below * Tt * S2; up[k] = lw[k] - s[k] * Tt * S2; below += s[k]; }
  w.forEach((z, k) => { dl[k] = D * z / ws * S2; });
  GEO.push({ x, lw, up, dl });
}
export const rp = (k: number, a: number, b: number, band: boolean, precision = 1) => {
  const up: string[] = [], lo: string[] = [];
  GEO.forEach((g) => {
    if (g.x < a - 1e-9 || g.x > b + 1e-9) return;
    const xs = X(g.x).toFixed(precision);
    up.push(xs + ',' + (band ? g.lw[k] - g.dl[k] : g.up[k]).toFixed(precision)); lo.push(xs + ',' + g.lw[k].toFixed(precision));
  });
  return 'M' + up.join(' L') + ' L' + lo.reverse().join(' L') + ' Z';
};
