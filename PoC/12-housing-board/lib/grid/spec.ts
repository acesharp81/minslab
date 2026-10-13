/* 데이터 그리드(components/ui/data-grid.tsx)의 순수 계산: 칸의 표시·정렬값, 두 줄 머리글, 검색, 합계 행 고정, 긴 표 판정(계획서 17절).
   서버 화면이 클라이언트 그리드로 넘기는 열·행은 직렬화되는 값만 쓴다(함수·JSX 없음). 시험: tests/js/grid.test.cjs */

/* 칸 종류: int 정수(쉼표) · delta 증감률(▲▼, 색) · pct 비율(%) · text 글자. 정하지 않으면 int */
export type Kind = 'int' | 'delta' | 'pct' | 'text';
/* 글자 말고 더 필요한 칸: 링크·색 견본(점선은 자료 없음)·잠정 표시·코드 글꼴·흐린 글자·없음 문구(na), sort 는 표시와 다른 정렬값 */
export type CellObj = { text?: string; sort?: number | string | null; href?: string; swatch?: string; dashed?: boolean; prov?: boolean; code?: boolean; muted?: boolean; na?: string };
export type Cell = number | string | null | undefined | CellObj;
/* wrap 은 긴 글자 열(최소 180px, 줄바꿈), sort:false 는 정렬하지 않는 열, group 이 같은 이웃 열은 위 줄 머리글 한 칸으로 묶인다 */
export type Col = { key: string; label: string; kind?: Kind; group?: string; groupSwatch?: string; wrap?: boolean; sort?: false };
/* pin: 합계 행(top 전국 · bottom 총계)은 정렬·검색과 상관없이 그 자리에 둔다. note: 첫 칸 뒤를 한 칸으로 합친 설명(자료 없는 단계 행)
   detail: 행을 누르면 바로 아래에 펼치는 실제 레코드 예시(열·행, 전체 건수, 출처). 가상 스크롤 표(120행 초과)에서는 펼치지 않는다 */
export type Detail = { cols: Col[]; rows: Row[]; total: number; source: string };
export type Row = { id: string; pin?: 'top' | 'bottom'; note?: string; muted?: boolean; detail?: Detail; c: Record<string, Cell> };
/* 작은 글자 그리드: 감싸는 요소에 주면 본문 13px·머리글 12px·좁은 칸 여백(데이터 원본).
   칸 글자는 한 줄로 고정하지 않고 낱말 단위(keep-all)로 줄을 바꿔, 열 너비는 글자 길이에 맞고 표가 화면 밖으로 넘쳐 잘리지 않는다(대신 행이 높아진다) */
export const GRID_DENSE = '[&_table]:text-[13px] [&_table]:leading-[1.5] [&_th]:px-2 [&_th]:py-1.5 [&_th]:text-[12px] [&_td]:px-2 [&_td]:py-1.5 [&_th]:whitespace-normal [&_td]:whitespace-normal [&_th]:[word-break:keep-all] [&_td]:[word-break:keep-all]';
export type HeadCell = { key?: string; label: string; colSpan: number; rowSpan: number; swatch?: string };

const isObj = (v: Cell): v is CellObj => typeof v === 'object' && v !== null;

/* 정렬값: 값이 없으면 undefined(그리드가 방향과 상관없이 맨 뒤에 둔다) */
export function sortValue(v: Cell): number | string | undefined {
  if (v === null || v === undefined) return undefined;
  if (!isObj(v)) return v;
  if ('sort' in v) return v.sort ?? undefined;
  if (v.na !== undefined) return undefined;
  return v.text;
}

/* 비교: 둘 다 숫자면 크기, 아니면 한글 사전 순(A2BL < A10BL 처럼 숫자는 자연 순) */
export function compare(a: number | string, b: number | string): number {
  if (typeof a === 'number' && typeof b === 'number') return a - b;
  return String(a).localeCompare(String(b), 'ko', { numeric: true });
}

/* 표시 글자와 색(tone: ok 늘어남 · bad 줄어듦 · na 흐리게) */
export function display(v: Cell, kind: Kind = 'int'): { text: string; tone?: 'ok' | 'bad' | 'na' } {
  if (v === null || v === undefined) return { text: '–', tone: 'na' };
  if (isObj(v)) {
    if (v.na !== undefined) return { text: v.na, tone: 'na' };
    return v.muted ? { text: v.text ?? '', tone: 'na' } : { text: v.text ?? '' };
  }
  if (typeof v === 'string') return { text: v };
  if (kind === 'delta') return { text: `${v >= 0 ? '▲' : '▼'} ${Math.abs(v).toFixed(1)}%`, tone: v >= 0 ? 'ok' : 'bad' };
  if (kind === 'pct') return { text: `${v.toFixed(1)}%` };
  return { text: v.toLocaleString('en-US') };
}

/* 머리글 줄: 묶음이 없으면 한 줄. 있으면 두 줄 — 묶이지 않은 열은 두 줄을 차지하고, 이어진 같은 묶음은 위 줄 한 칸이 된다 */
export function headerRows(cols: Col[]): HeadCell[][] {
  const leaf = (c: Col, rowSpan: number): HeadCell => ({ key: c.key, label: c.label, colSpan: 1, rowSpan });
  if (!cols.some((c) => c.group)) return [cols.map((c) => leaf(c, 1))];
  const top: HeadCell[] = [], bottom: HeadCell[] = [];
  cols.forEach((c, i) => {
    if (!c.group) { top.push(leaf(c, 2)); return; }
    bottom.push(leaf(c, 1));
    if (i > 0 && cols[i - 1].group === c.group) { top[top.length - 1].colSpan += 1; return; }
    top.push({ label: c.group, colSpan: 1, rowSpan: 1, ...(c.groupSwatch ? { swatch: c.groupSwatch } : {}) });
  });
  return [top, bottom];
}

/* 묶음이 시작되는 열(앞 열과 묶음이 다른 묶인 열): 세로 구분선을 긋는다 */
export const groupStarts = (cols: Col[]) => new Set(cols.filter((c, i) => c.group && (i === 0 || cols[i - 1].group !== c.group)).map((c) => c.key));

/* 검색: 칸의 표시 글자와 숫자 그대로(쉼표 없이)를 공백·대소문자를 무시하고 찾는다 */
const norm = (s: string) => s.toLowerCase().replace(/\s+/g, '');
export function filterRows(rows: Row[], q: string, cols: Col[]): Row[] {
  const n = norm(q);
  if (!n) return rows;
  return rows.filter((r) => cols.some((c) => {
    const v = r.c[c.key];
    return norm(display(v, c.kind).text).includes(n) || (typeof v === 'number' && String(v).includes(n));
  }));
}

export function splitPinned(rows: Row[]) {
  return { top: rows.filter((r) => r.pin === 'top'), body: rows.filter((r) => !r.pin), bottom: rows.filter((r) => r.pin === 'bottom') };
}

/* 긴 표만: 30행을 넘으면 검색(시도 16행 표는 한눈에 보인다), 120행을 넘으면 보이는 행만 그린다(가상 스크롤) */
export const wants = (n: number) => ({ search: n > 30, virtual: n > 120 });
