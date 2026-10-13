'use client';

import * as React from 'react';
import Link from 'next/link';
import { ChevronDown, ChevronRight, ChevronUp, ChevronsUpDown, Search } from 'lucide-react';
import { constructSortFn, createColumnHelper, createSortedRowModel, rowSortingFeature, tableFeatures, useTable, type SortingState } from '@tanstack/react-table';
import { useVirtualizer } from '@tanstack/react-virtual';
import { cn } from 'cn';
import { Swatch } from '../charts/Legend';
import { Prov } from '../ui';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from './table';
import { compare, display, filterRows, groupStarts, headerRows, sortValue, splitPinned, wants, type Cell, type Col, type Row } from '../../lib/grid/spec';

/* 데이터 그리드(계획서 17절): TanStack Table v9(정렬)과 TanStack Virtual(긴 표)을 기존 Table 마크업 위에 얹는다. 헤드리스라 모양은 Table 그대로다.
   - 머리글을 누르면 정렬(숫자는 큰 값부터, 글자는 가나다순 → 반대 → 원래 순서). 값이 없는 칸은 방향과 상관없이 맨 뒤. th 에 aria-sort.
   - 머리글은 위에, 첫 열(행 이름)은 왼쪽에 붙어 있다(좁은 화면에서 옆으로 밀어도 무슨 행인지 보인다). 합계 행(전국·총계)은 정렬·검색과 상관없이 제자리.
   - 줄무늬, 글자 열은 왼쪽·숫자 열은 오른쪽 정렬, 묶음(머리글 2단)이 바뀌는 곳에 세로 구분선, 없는 값은 흐린 –.
   - 30행을 넘는 표는 검색 칸과 건수를, 120행을 넘는 표는 보이는 행만 그린다(LH 준공 예정 351행: DOM 행 351 → 수십).
   - 행에 detail(실제 레코드 예시)이 있으면 첫 칸에 ▸ 가 붙고, 행을 누르면(또는 ▸ 단추) 바로 아래에 예시 표가 열린다. 칸 안의 링크를 누르면 펼치지 않고 그 링크로 간다.
   서버 화면은 직렬화되는 열·행(lib/grid/spec.ts 의 Col·Row)만 넘긴다. 시험: tests/js/grid.test.cjs */

const features = tableFeatures({
  rowSortingFeature,
  sortedRowModel: createSortedRowModel(),
  sortFns: { grid: constructSortFn({ sort: (a, b) => compare(a, b) }) },
});
const helper = createColumnHelper<typeof features, Row>();

const ROW_H = 46;   // 한 줄 행 높이(16px × 1.6 + 위아래 10px + 테두리). 여러 줄 행은 그린 뒤 잰다
const TONE = { ok: 'text-ok', bad: 'text-bad', na: 'text-muted-foreground' } as const;
const zebra = 'bg-[color-mix(in_srgb,var(--pn2)_45%,var(--card))]';   // 불투명이라야 붙은 첫 열 밑으로 글자가 비치지 않는다
const stickyCell = 'sticky left-0 z-[1] bg-inherit group-data-[scrolled]/grid:shadow-[6px_0_6px_-6px_rgb(0_0_0/0.25)]';   // 옆으로 민 동안만 오른쪽 그림자

/* 하이픈·물결이 든 짧은 낱말(2026-08-31, 2021-09~2026-08, 61-79번지)은 줄을 바꿀 때 가운데서 끊지 않는다(브라우저는 하이픈 뒤에서 끊는다) */
const keepWords = (t: string): React.ReactNode => (/[-~]/.test(t) ? t.split(/( +)/).map((w, i) => (i % 2 || !/[-~]/.test(w) || w.length > 24 ? w : <span key={i} className="whitespace-nowrap">{w}</span>)) : t);

function CellView({ v, col }: { v: Cell; col: Col }) {
  const d = display(v, col.kind);
  const o = typeof v === 'object' && v !== null ? v : undefined;
  const text = o?.code ? <code>{d.text}</code> : keepWords(d.text);
  const body = o?.href ? <Link href={o.href}>{text}</Link> : text;
  return (
    <>
      {o?.dashed ? <i className="mr-1.5 inline-block size-[11px] rounded-[3px] border-[1.5px] border-dashed border-line2 align-[-1px]" aria-hidden="true" /> : o?.swatch ? <Swatch color={o.swatch} /> : null}
      {d.tone ? <span className={TONE[d.tone]}>{body}</span> : body}
      {o?.prov ? <Prov /> : null}
    </>
  );
}

export function DataGrid({ cols, rows, label, sortable = true, maxHeight, virtualize = true }: { cols: Col[]; rows: Row[]; label: string; sortable?: boolean; maxHeight?: number; virtualize?: boolean }) {
  const [sorting, setSorting] = React.useState<SortingState>([]);
  const [q, setQ] = React.useState('');
  const [open, setOpen] = React.useState<ReadonlySet<string>>(new Set());
  const uid = React.useId();
  const { top, body, bottom } = React.useMemo(() => splitPinned(rows), [rows]);
  const want = wants(body.length);
  const wantsVirtual = want.virtual && virtualize;
  const data = React.useMemo(() => filterRows(body, q, cols), [body, q, cols]);
  const columns = React.useMemo(() => helper.columns(cols.map((c) => helper.accessor((r) => sortValue(r.c[c.key]), {
    id: c.key, sortFn: 'grid', sortUndefined: 'last', sortDescFirst: (c.kind ?? 'int') !== 'text', enableSorting: sortable && c.sort !== false,
  }))), [cols, sortable]);
  const table = useTable({ features, columns, data, state: { sorting }, onSortingChange: setSorting, getRowId: (r) => r.id });
  const list = table.getRowModel().rows;

  const heads = React.useMemo(() => headerRows(cols), [cols]);
  const starts = React.useMemo(() => groupStarts(cols), [cols]);
  const textCol = React.useMemo(() => new Set(cols.filter((c) => c.kind === 'text').map((c) => c.key)), [cols]);
  const first = cols[0].key;
  const height = maxHeight ?? (wantsVirtual ? 520 : undefined);
  const scrollRef = React.useRef<HTMLDivElement>(null);
  const v = useVirtualizer({
    count: wantsVirtual ? list.length : 0, getScrollElement: () => scrollRef.current, estimateSize: () => ROW_H, overscan: 10,
    getItemKey: (i) => list[i].id, initialRect: { width: 0, height: height ?? 0 },   // 서버 HTML 에도 첫 화면 행을 그린다
  });
  const items = v.getVirtualItems();
  const shown = wantsVirtual ? items.map((it) => ({ row: list[it.index].original, i: it.index })) : list.map((r, i) => ({ row: r.original, i }));
  const padTop = wantsVirtual && items.length ? items[0].start : 0;
  const padBottom = wantsVirtual && items.length ? v.getTotalSize() - items[items.length - 1].end : 0;
  const lead = heads.length + top.length;   // aria-rowindex 가 1부터 머리글 줄을 포함해 센다

  const expandable = !wantsVirtual && rows.some((r) => r.detail);
  const toggle = (id: string) => setOpen((s) => { const n = new Set(s); if (n.has(id)) n.delete(id); else n.add(id); return n; });
  const detailId = (r: Row) => `${uid}-${r.id}-detail`;
  /* 펼친 예시 표: 칸 폭이 0 에서 시작해(w-0 min-w-full) 바깥 표의 열 너비를 넓히지 않는다. 열이 많아도(최대 20) 넘쳐 잘리지 않게
     머리글(긴 원본 열 이름)은 한글 음절 단위로 줄을 바꾼다(word-break normal). 값 칸은 낱말 단위 그대로라 숫자·낱말이 중간에서 끊기지 않는다 */
  const detailLine = (r: Row) => (
    <tr key={`${r.id}-detail`} id={detailId(r)}>
      <TableCell colSpan={cols.length} className="bg-pn2 px-3 py-2 text-left whitespace-normal">
        <div className="w-0 min-w-full [&_th]:[word-break:normal]!">
          <p className="m-0 text-[12px] text-muted-foreground">예시 {r.detail!.rows.length.toLocaleString('en-US')}건 / 전체 {r.detail!.total.toLocaleString('en-US')}건 · {r.detail!.source}</p>
          <DataGrid label={`${label} · ${display(r.c[first], cols[0].kind).text} 예시`} cols={r.detail!.cols} rows={r.detail!.rows} sortable={false} />
        </div>
      </TableCell>
    </tr>
  );
  const line = (r: Row, i: number, pinned: boolean, measure?: boolean) => [
    <TableRow key={r.id} total={pinned} data-index={measure ? i : undefined} ref={measure ? v.measureElement : undefined}
      aria-rowindex={wantsVirtual ? (pinned ? undefined : lead + i + 1) : undefined}
      onClick={expandable && r.detail ? (e) => { if (!(e.target as HTMLElement).closest('a, button, input')) toggle(r.id); } : undefined}
      className={cn(!pinned && (i % 2 ? zebra : 'bg-card'), r.muted && 'text-muted-foreground', expandable && r.detail && 'cursor-pointer')}>
      {r.note !== undefined ? (
        <>
          <TableCell className={stickyCell}><CellView v={r.c[first]} col={cols[0]} /></TableCell>
          <TableCell colSpan={cols.length - 1} className="text-left whitespace-normal">{r.note}</TableCell>
        </>
      ) : cols.map((c) => (
        <TableCell key={c.key} className={cn(c.key === first && stickyCell, c.kind === 'text' && 'text-left', c.wrap && 'min-w-[180px] whitespace-normal [word-break:keep-all]', starts.has(c.key) && 'border-l')}>
          {expandable && c.key === first ? (r.detail ? (
            <button type="button" aria-expanded={open.has(r.id)} aria-controls={open.has(r.id) ? detailId(r) : undefined} aria-label={`${display(r.c[first], cols[0].kind).text} 예시 ${open.has(r.id) ? '접기' : '펼치기'}`} onClick={() => toggle(r.id)}
              className="mr-1 inline-flex size-4 cursor-pointer items-center justify-center border-0 bg-transparent p-0 align-[-2px] text-muted-foreground hover:text-foreground focus-visible:outline-2 focus-visible:outline-primary">
              <ChevronRight className={cn('size-3.5 transition-transform', open.has(r.id) && 'rotate-90')} aria-hidden="true" />
            </button>
          ) : <span className="mr-1 inline-block w-4" aria-hidden="true" />) : null}
          <CellView v={r.c[c.key]} col={c} />
        </TableCell>
      ))}
    </TableRow>,
    expandable && r.detail && open.has(r.id) ? detailLine(r) : null,
  ];
  const spacer = (h: number, key: string) => (h > 0 ? <tr key={key} aria-hidden="true"><td colSpan={cols.length} className="border-0 p-0" style={{ height: h }} /></tr> : null);

  return (
    <div data-slot="data-grid">
      {want.search ? (
        <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1.5">
          <label className="relative block w-full max-w-[320px]">
            <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" aria-hidden="true" />
            <input type="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder="이 표에서 찾기" aria-label={`${label} 안에서 찾기`}
              className="h-10 w-full rounded-[10px] border-[1.5px] border-line2 bg-card pr-3 pl-9 text-[15px] text-foreground placeholder:text-muted-foreground focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-primary" />
          </label>
          <span className="text-[14px] text-muted-foreground tabular-nums" aria-live="polite">{q.trim() ? `${data.length}건 / 전체 ${body.length}건` : `${body.length}건`}</span>
        </div>
      ) : null}
      <Table aria-label={label} aria-rowcount={wantsVirtual ? lead + list.length + bottom.length : undefined}
        containerClassName={cn('group/grid', height !== undefined && 'overflow-y-auto')}
        containerProps={{ ref: scrollRef, style: height !== undefined ? { maxHeight: height } : undefined, onScroll: (e) => e.currentTarget.toggleAttribute('data-scrolled', e.currentTarget.scrollLeft > 0) }}>
        <TableHeader>
          {heads.map((cells, li) => (
            <tr key={li}>
              {cells.map((h, hi) => {
                const column = h.key ? table.getColumn(h.key) : undefined;
                const can = !!column?.getCanSort();
                const dir = column?.getIsSorted();
                const Icon = dir === 'asc' ? ChevronUp : dir === 'desc' ? ChevronDown : ChevronsUpDown;
                return (
                  <TableHead key={h.key ?? `g${hi}`} colSpan={h.colSpan > 1 ? h.colSpan : undefined} rowSpan={h.rowSpan > 1 ? h.rowSpan : undefined}
                    aria-sort={can ? (dir === 'asc' ? 'ascending' : dir === 'desc' ? 'descending' : 'none') : undefined}
                    className={cn('z-[2]', h.key === first && 'left-0 z-[3] group-data-[scrolled]/grid:shadow-[6px_0_6px_-6px_rgb(0_0_0/0.25)]', !h.key && 'text-center', h.key && textCol.has(h.key) && 'text-left', (h.key ? starts.has(h.key) : true) && h.key !== first && 'border-l', dir && 'text-foreground')}>
                    {h.swatch ? <Swatch color={h.swatch} /> : null}
                    {can ? (
                      <button type="button" onClick={column!.getToggleSortingHandler()} title="눌러서 정렬"
                        className="inline-flex cursor-pointer items-center gap-1 border-0 bg-transparent p-0 font-[inherit] text-inherit hover:text-foreground focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary">
                        {h.label}<Icon className={cn('size-3.5 shrink-0', !dir && 'opacity-40')} aria-hidden="true" />
                      </button>
                    ) : h.label}
                  </TableHead>
                );
              })}
            </tr>
          ))}
        </TableHeader>
        <TableBody>
          {top.map((r) => line(r, -1, true))}
          {spacer(padTop, 'pad-top')}
          {shown.map(({ row, i }) => line(row, i, false, wantsVirtual))}
          {spacer(padBottom, 'pad-bottom')}
          {q.trim() && !data.length ? <TableRow><TableCell colSpan={cols.length} className="text-center whitespace-normal text-muted-foreground">&lsquo;{q.trim()}&rsquo;에 맞는 행이 없습니다</TableCell></TableRow> : null}
          {bottom.map((r) => line(r, -1, true))}
        </TableBody>
      </Table>
    </div>
  );
}
