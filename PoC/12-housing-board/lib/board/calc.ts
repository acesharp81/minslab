/* 상황판 화면의 계산(순수 함수). JSON 을 직접 읽지 않고 인자로 받아 Node 시험이 그대로 부른다(tests/js/board.test.cjs). */
import type { Actor, LhBlock, LhData, Metric, Molit, Series } from './types';

export const NATION = '00';
export const METRICS: Metric[] = ['permit', 'start', 'sale', 'complete'];   // 6단계 순서(03 인허가 → 04 착공 → 05 분양 → 06 준공, lib/board/stages.ts METRIC_STAGE)
export const ACTORS: Actor[] = ['지자체', 'LH', '주택업체', '민간'];
export const ACTOR_NOTE = '공공(지자체·LH·주택업체)과 민간으로 나눈 시행주체별 호수입니다. 네 분류의 합이 총계입니다.';

export const fmt = (n: number | null | undefined) => (n === null || n === undefined ? '–' : n.toLocaleString('en-US'));
export const ymDot = (ym: string) => ym.replace('-', '.');
export const monthLabel = (ym: string) => `${ym.slice(0, 4)}년 ${Number(ym.slice(5))}월`;

export const lastMonth = (m: Molit) => m.months[m.months.length - 1];
export const monthIndex = (m: Molit, ym: string) => m.months.indexOf(ym);
export const isProvisional = (m: Molit, ym: string) => m.provisional.includes(ym);
export const sidoName = (m: Molit, code: string) => m.sido.find((s) => s.code === code)?.name;
export const seriesOf = (m: Molit, metric: Metric, code: string): Series => m.metrics[metric].series[code];

export function valueAt(m: Molit, metric: Metric, code: string, ym: string): number | null {
  const i = monthIndex(m, ym);
  return i < 0 ? null : seriesOf(m, metric, code).total[i];
}

/* 그해 1월부터 ym 까지의 합(연누계). 알 수 없는 달(null)이 끼면 null. */
export function ytd(m: Molit, metric: Metric, code: string, ym: string, actor?: Actor): number | null {
  const s = seriesOf(m, metric, code);
  const arr = actor ? s.actors?.[actor] : s.total;
  if (!arr) return null;
  const end = monthIndex(m, ym);
  if (end < 0) return null;
  let sum = 0, n = 0;
  for (let i = 0; i <= end; i++) {
    if (!m.months[i].startsWith(ym.slice(0, 4))) continue;
    const v = arr[i];
    if (v === null) return null;
    sum += v; n++;
  }
  return n === (Number(ym.slice(5))) ? sum : null;   // 1월부터 다 있어야 연누계다
}

/* 한 달의 시도별 표: 지표별 값(전국 포함). */
export function monthTable(m: Molit, ym: string) {
  return m.sido.map((s) => ({ code: s.code, name: s.name, values: Object.fromEntries(METRICS.map((k) => [k, valueAt(m, k, s.code, ym)])) as Record<Metric, number | null> }));
}

/* 한 시도(또는 전국)의 최근 n개월 표. */
export function recentMonths(m: Molit, n: number) { return m.months.slice(-n); }

export function neighborMonths(m: Molit, ym: string) {
  const i = monthIndex(m, ym);
  return { prev: i > 0 ? m.months[i - 1] : null, next: i >= 0 && i < m.months.length - 1 ? m.months[i + 1] : null };
}

/* LH 준공 예정: ym 부터 n개월(포함)의 월별 호수·블록 수. */
export function nextYm(ym: string, k = 1) {
  let y = Number(ym.slice(0, 4)), mo = Number(ym.slice(5)) - 1 + k;
  y += Math.floor(mo / 12); mo = ((mo % 12) + 12) % 12;
  return `${y}-${String(mo + 1).padStart(2, '0')}`;
}
export function lhByMonth(lh: LhData, fromYm: string, n: number) {
  return Array.from({ length: n }, (_, i) => {
    const ym = nextYm(fromYm, i);
    const blocks = lh.blocks.filter((b) => b.date.startsWith(ym));
    return { ym, units: blocks.reduce((a, b) => a + b.units, 0), blocks: blocks.length };
  });
}
export const lhOfMonth = (lh: LhData, ym: string): LhBlock[] => lh.blocks.filter((b) => b.date.startsWith(ym));
export const lhUnits = (blocks: LhBlock[]) => blocks.reduce((a, b) => a + b.units, 0);

/* 달 수(개월) 차이: a 에서 b 까지. */
export function monthsBetween(a: string, b: string) { return (Number(b.slice(0, 4)) - Number(a.slice(0, 4))) * 12 + Number(b.slice(5, 7)) - Number(a.slice(5, 7)); }

/* 앞으로의 물량을 세는 기준 달: 종합상황판의 '향후 12개월'과 같은 달(시안의 NOW, 2026.10). 보고자료·우리 동네가 쓴다 */
export const AHEAD_FROM = '2026-10';

/* 시도 하나의 LH 준공 예정 달력: fromYm 부터 n개월, 달마다 그 달의 블록(날짜·사업지구 순)과 세대수. 우리 동네(9.4 지시 '공급계획 사전 공개')가 쓴다 */
export function lhCalendar(lh: LhData, sido: string, fromYm: string, n: number) {
  return Array.from({ length: n }, (_, i) => {
    const ym = nextYm(fromYm, i);
    const blocks = lh.blocks.filter((b) => b.sido === sido && b.date.startsWith(ym)).sort((a, b) => a.date.localeCompare(b.date) || a.district.localeCompare(b.district, 'ko'));
    return { ym, blocks, units: lhUnits(blocks) };
  });
}
