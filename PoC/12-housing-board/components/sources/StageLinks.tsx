'use client';
/* 데이터 원본의 '단계별 데이터 연계' 탭(①계획~⑥입주 + 기타). 단계마다 연계도(SVG)와 자료별 연계 표(DataGrid).
   연계도는 lib/board/stage-links.ts 의 자료를 자동 배치한다: 왼쪽 지금 가진 자료 → 가운데 키 사슬(시도·시군구·법정동·필지·사업 번호)과
   곁가지 키 → 오른쪽 추가로 확보할 자료 → 아래 화면 결과. 고리마다 띠 높이를 상자 수만큼 잡아 상자·선 이름표가 겹치지 않는다.
   도식은 본문 폭에 맞춰 줄어들어 화면을 넘치지 않는다(휴대폰 폭만 상자 안 가로 스크롤). 색은 프로젝트 토큰이라 라이트·다크를 따른다.
   주소 #stage-<id> 로 그 탭을 연다. 마지막 '기타' 탭은 화면이 넘긴 나머지 내용(extra)이다. 늘 그려 두고 숨기기만 해서,
   주소의 #id 가 그 안을 가리키면(기관별 화면의 /sources#원천) 기타 탭을 연 뒤 접힌 상자를 열고 그 자리로 간다. */
import * as React from 'react';
import { cn } from 'cn';
import { DataGrid } from '../ui/data-grid';
import { GRID_DENSE, type Col, type Row } from '../../lib/grid/spec';
import { LEVELS, LEVEL_NAME, VIAS, type Edge, type Level, type LinkItem, type StageLink, type Via } from '../../lib/board/stage-links';

const NUM = ['①', '②', '③', '④', '⑤', '⑥'];
/* 도식 좌표(viewBox 폭 W): 왼쪽 상자 · 가운데 사슬 · 곁가지 키 · 오른쪽 상자. BH 상자 높이, KH 사슬 높이, STEP 같은 고리 안 상자 간격 */
const W = 1110, LX = 4, LW = 320, SX = 444, SW = 200, CX = 544, DX = 570, DW = 150, DC = 645, RX = 786, RW = 320, BH = 54, KH = 56, STEP = 62;
const COLS: Col[] = [
  { key: 'data', label: '지금 가진 자료', kind: 'text' }, { key: 'keys', label: '가진 키', kind: 'text' },
  { key: 'reach', label: '지금 닿는 고리', kind: 'text' }, { key: 'cut', label: '끊긴 곳', kind: 'text' }, { key: 'fix', label: '이어 주는 추가 자료', kind: 'text' },
];
const EDGE: Record<Edge, string> = {
  key: 'stroke-foreground', name: 'stroke-foreground [stroke-dasharray:5_4]', need: 'stroke-warn', none: 'stroke-bad [stroke-dasharray:3_3]',
};
const LABEL: Record<Edge, string> = { key: 'fill-foreground', name: 'fill-foreground', need: 'fill-warn', none: 'fill-bad' };
/* 받는 방식 표지(상자 오른쪽 위): 실시간·API 는 색, CSV 는 진한 테두리, 나머지는 흐리게 */
const VIA_STYLE: Record<Via, { box: string; text: string; pill: string }> = {
  실시간: { box: 'fill-[color-mix(in_srgb,var(--primary)_12%,var(--card))] stroke-primary', text: 'fill-primary', pill: 'border-primary text-primary' },
  API: { box: 'fill-[color-mix(in_srgb,var(--ok)_12%,var(--card))] stroke-ok', text: 'fill-ok', pill: 'border-ok text-ok' },
  CSV: { box: 'fill-card stroke-foreground', text: 'fill-foreground', pill: 'border-foreground text-foreground' },
  파일: { box: 'fill-card stroke-border', text: 'fill-muted-foreground', pill: 'border-border text-muted-foreground' },
  가공: { box: 'fill-card stroke-border', text: 'fill-muted-foreground', pill: 'border-border text-muted-foreground' },
  내부: { box: 'fill-card stroke-border', text: 'fill-muted-foreground', pill: 'border-border text-muted-foreground' },
};
const VIA_NOTE: Record<Via, string> = { 실시간: '조회 때 API', API: 'API 보관', CSV: 'CSV 파일', 파일: 'PDF·hwpx·SHP', 가공: '번들·레지스트리', 내부: '기관 입력·일정 기록' };
const pillW = (t: string) => [...t].reduce((w, ch) => w + (/[가-힣]/.test(ch) ? 11 : 7.2), 0) + 12;
/* 상자 오른쪽 위에 오른쪽부터 차례로 */
function Badges({ via, right, top }: { via: Via[]; right: number; top: number }) {
  let x = right;
  return (
    <>
      {[...via].reverse().map((v) => {
        const w = pillW(v); x -= w;
        const at = x; x -= 4;
        return (
          <g key={v}>
            <rect x={at} y={top} width={w} height={16} rx="8" strokeWidth="1" className={VIA_STYLE[v].box} />
            <text x={at + w / 2} y={top + 12} textAnchor="middle" className={cn('text-[11px] font-bold', VIA_STYLE[v].text)}>{v}</text>
          </g>
        );
      })}
    </>
  );
}

function Diagram({ s }: { s: StageLink }) {
  const uid = React.useId().replace(/:/g, '');
  const mark = (e: Edge) => (e === 'need' ? `url(#${uid}-w)` : e === 'none' ? undefined : `url(#${uid}-f)`);
  /* 고리마다 띠 높이: 왼쪽·오른쪽 중 많은 쪽의 상자 수 */
  const rowY = {} as Record<Level, number>;
  let y = 44;
  for (const l of LEVELS) {
    const n = Math.max(1, s.current.filter((i) => i.level === l).length, s.needed.filter((i) => i.level === l).length);
    rowY[l] = y + (n * STEP + 18) / 2; y += n * STEP + 18;
  }
  const busY = rowY.prj + KH / 2 + 32, outY = busY + 24, outH = 68, H = outY + outH + 6;
  const ow = (W - 2 * LX - (s.outcomes.length - 1) * 30) / s.outcomes.length;
  const outX = (i: number) => LX + i * (ow + 30);
  const a = s.acquire;
  const rightHead = a ? ['추가로 확보할 자료', a.api ? `API ${a.api}` : '', a.file ? `파일 ${a.file}` : '', a.internal ? `내부 ${a.internal}` : ''].filter(Boolean).join(' · ') : '추가로 확보할 자료';

  const items = (list: LinkItem[], left: boolean) => LEVELS.flatMap((l) => {
    const at = list.filter((i) => i.level === l);
    return at.map((it, i) => {
      const iy = rowY[l] + (i - (at.length - 1) / 2) * STEP;
      const ty = rowY[l] + Math.max(-22, Math.min(22, (i - (at.length - 1) / 2) * 16));
      const bx = left ? LX : RX, x1 = left ? LX + LW : RX;
      const x2 = l === 'side' ? (left ? DX - 2 : DX + DW + 2) : (left ? SX - 2 : SX + SW + 2);
      const xEnd = it.edge === 'none' ? x2 - 18 : x2;
      const lx = l === 'side' && !left ? (DX + DW + RX) / 2 : left ? (LX + LW + SX) / 2 : (SX + SW + RX) / 2;
      const ly = iy + (ty - iy) * ((lx - x1) / (xEnd - x1)) - 7;   // 이름표는 선이 그 자리에서 지나는 높이 바로 위
      return (
        <g key={`${left ? 'l' : 'r'}-${l}-${i}`}>
          <rect x={bx} y={iy - BH / 2} width={left ? LW : RW} height={BH} rx="9"
            className={it.edge === 'need' ? 'fill-[color-mix(in_srgb,var(--warn)_12%,var(--card))] stroke-warn' : 'fill-card stroke-border'} strokeWidth="1.2" />
          <text x={bx + 14} y={iy - 5} className="fill-foreground text-[14px] font-bold">{it.name}</text>
          <text x={bx + 14} y={iy + 16} className="fill-muted-foreground text-[12px]">{it.sub}</text>
          <Badges via={it.via ?? []} right={bx + (left ? LW : RW) - 8} top={iy - BH / 2 + 6} />
          <line x1={x1} y1={iy} x2={xEnd} y2={ty} className={EDGE[it.edge]} strokeWidth="1.6" fill="none" markerEnd={mark(it.edge)} />
          {it.edge === 'none' ? <path d={`M${xEnd - 5},${ty - 5} l10,10 M${xEnd + 5},${ty - 5} l-10,10`} className="stroke-bad" strokeWidth="2" /> : null}
          <text x={lx} y={ly} textAnchor="middle" className={cn('text-[12px]', LABEL[it.edge])}>{it.label}</text>
        </g>
      );
    });
  });

  const spine = (l: Exclude<Level, 'side'>) => (
    <g key={l}>
      <rect x={SX} y={rowY[l] - KH / 2} width={SW} height={KH} rx="9" strokeWidth="1.5" className="fill-[color-mix(in_srgb,var(--primary)_10%,var(--card))] stroke-primary" />
      <text x={CX} y={rowY[l] - 4} textAnchor="middle" className="fill-foreground text-[14px] font-bold">{LEVEL_NAME[l].name}</text>
      <text x={CX} y={rowY[l] + 16} textAnchor="middle" className="fill-muted-foreground font-mono text-[12px]">{LEVEL_NAME[l].key}</text>
    </g>
  );
  const down = (a: Level, b: Level, label?: string) => (
    <g key={`${a}-${b}`}>
      <line x1={CX} y1={rowY[a] + KH / 2} x2={CX} y2={rowY[b] - KH / 2 - 2} className="stroke-foreground" strokeWidth="1.5" markerEnd={mark('key')} />
      {label ? <text x={CX - 8} y={(rowY[a] + rowY[b]) / 2 + 4} textAnchor="end" className="fill-muted-foreground text-[12px]">{label}</text> : null}
    </g>
  );
  const sideTop = rowY.side - KH / 2, sideBottom = rowY.side + KH / 2, spineX = CX - 30;
  return (
    <svg viewBox={`0 0 ${W} ${H}`} role="img" className="block h-auto w-full text-foreground phone:min-w-[720px]"
      aria-label={`${s.name} 단계: 지금 가진 자료 ${s.current.length}종과 추가로 확보할 자료 ${s.needed.length}종이 시도·시군구·법정동·필지·${s.side.name}·사업 번호 고리 중 어디까지 닿는지 보여 주는 연계도`}>
      <defs>
        <marker id={`${uid}-f`} viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" className="fill-foreground" /></marker>
        <marker id={`${uid}-w`} viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" className="fill-warn" /></marker>
      </defs>
      <text x={LX + LW / 2} y="24" textAnchor="middle" className="fill-foreground text-[13px] font-bold">지금 가진 자료 · {s.current.length}종</text>
      <text x={CX} y="24" textAnchor="middle" className="fill-foreground text-[13px] font-bold">연결 고리(키)</text>
      <text x={RX + RW / 2} y="24" textAnchor="middle" className="fill-warn text-[13px] font-bold">{rightHead}</text>

      {(['sido', 'sgg', 'bjd', 'pnu', 'prj'] as const).map(spine)}
      {down('sido', 'sgg', '코드 앞자리')}{down('sgg', 'bjd')}{down('bjd', 'pnu')}
      <line x1={spineX} y1={rowY.pnu + KH / 2} x2={spineX} y2={rowY.prj - KH / 2 - 2} className="stroke-foreground" strokeWidth="1.5" markerEnd={mark('key')} />
      <text x={spineX - 8} y={(rowY.pnu + KH / 2 + sideTop) / 2 + 4} textAnchor="end" className="fill-foreground text-[12px]">{s.pnuToPrj}</text>

      <rect x={DX} y={sideTop} width={DW} height={KH} rx="9" strokeWidth="1.6"
        className={s.side.known ? 'fill-[color-mix(in_srgb,var(--primary)_10%,var(--card))] stroke-primary' : 'fill-card stroke-warn [stroke-dasharray:5_4]'} />
      <text x={DC} y={rowY.side - 4} textAnchor="middle" className="fill-foreground text-[14px] font-bold">{s.side.name}</text>
      <text x={DC} y={rowY.side + 15} textAnchor="middle" className="fill-muted-foreground text-[11px]">{s.side.sub}</text>
      <line x1={DC - 14} y1={sideTop} x2={CX + 70} y2={rowY.pnu + KH / 2 + 3} className={EDGE[s.side.toPnu.edge]} strokeWidth="1.6" markerEnd={mark(s.side.toPnu.edge)} />
      <text x={DC} y={(sideTop + rowY.pnu + KH / 2) / 2 + 4} className={cn('text-[12px]', LABEL[s.side.toPnu.edge])}>{s.side.toPnu.label}</text>
      <line x1={DC - 14} y1={sideBottom} x2={CX + 70} y2={rowY.prj - KH / 2 - 3} className={EDGE[s.side.toPrj.edge]} strokeWidth="1.6" markerEnd={mark(s.side.toPrj.edge)} />
      <text x={DC} y={(sideBottom + rowY.prj - KH / 2) / 2 + 4} className={cn('text-[12px]', LABEL[s.side.toPrj.edge])}>{s.side.toPrj.label}</text>

      {items(s.current, true)}
      {items(s.needed, false)}

      <line x1={CX} y1={rowY.prj + KH / 2} x2={CX} y2={busY} className="stroke-foreground" strokeWidth="1.5" />
      <line x1={outX(0) + ow / 2} y1={busY} x2={outX(s.outcomes.length - 1) + ow / 2} y2={busY} className="stroke-foreground" strokeWidth="1.5" />
      {s.outcomes.map((o, i) => (
        <g key={o.name}>
          <line x1={outX(i) + ow / 2} y1={busY} x2={outX(i) + ow / 2} y2={outY - 2} className="stroke-foreground" strokeWidth="1.5" markerEnd={mark('key')} />
          <rect x={outX(i)} y={outY} width={ow} height={outH} rx="9" className="fill-card stroke-foreground" strokeWidth="1.3" />
          <text x={outX(i) + 14} y={outY + 22} className="fill-foreground text-[14px] font-bold">{o.name}</text>
          {o.lines.map((t, k) => <text key={k} x={outX(i) + 14} y={outY + 42 + k * 16} className="fill-muted-foreground text-[12px]">{t}</text>)}
        </g>
      ))}
    </svg>
  );
}

export default function StageLinks({ stages, extra }: { stages: StageLink[]; extra?: React.ReactNode }) {
  const [tab, setTab] = React.useState(0);
  const [pending, setPending] = React.useState<string | null>(null);
  const refs = React.useRef<(HTMLButtonElement | null)[]>([]);
  const extraRef = React.useRef<HTMLDivElement>(null);
  const ETC = stages.length, total = stages.length + (extra ? 1 : 0);
  React.useEffect(() => {   // #stage-permit 은 그 단계 탭, #stage-etc 나 기타 안의 #id 는 기타 탭
    const sync = () => {
      const id = decodeURIComponent(window.location.hash.slice(1));
      const i = stages.findIndex((s) => `stage-${s.id}` === id);
      if (i >= 0) setTab(i);
      else if (extra && id === 'stage-etc') setTab(ETC);
      else if (extra && id && extraRef.current?.contains(document.getElementById(id))) { setTab(ETC); setPending(id); }
    };
    sync();
    window.addEventListener('hashchange', sync);
    return () => window.removeEventListener('hashchange', sync);
  }, [stages, extra, ETC]);
  React.useEffect(() => {   // 기타 탭이 보인 뒤에 접힌 상자를 열고 그 자리로
    if (!pending || tab !== ETC) return;
    const el = document.getElementById(pending);
    for (let d = el?.closest('details'); d; d = d.parentElement?.closest('details') ?? null) d.open = true;
    el?.scrollIntoView();
    setPending(null);
  }, [pending, tab, ETC]);
  const go = (i: number) => { const n = (i + total) % total; setTab(n); refs.current[n]?.focus(); };
  const s = tab < ETC ? stages[tab] : null;
  const rows: Row[] = s ? s.rows.map((r, i) => ({ id: String(i), c: r })) : [];
  const tabCls = 'h-8 cursor-pointer rounded-[8px] border-0 bg-transparent px-3 text-[14px] font-bold whitespace-nowrap text-ink2 [transition:background_.15s,color_.15s] not-aria-selected:hover:bg-pn2 aria-selected:bg-primary aria-selected:text-primary-foreground focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-primary';
  return (
    <div>
      <div role="tablist" aria-label="공급 6단계" className="flex w-fit max-w-full flex-wrap rounded-[10px] bg-card p-[3px] shadow-[var(--shadow-card)]"
        onKeyDown={(e) => { if (e.key === 'ArrowRight') go(tab + 1); else if (e.key === 'ArrowLeft') go(tab - 1); else if (e.key === 'Home') go(0); else if (e.key === 'End') go(total - 1); else return; e.preventDefault(); }}>
        {stages.map((st, i) => (
          <button key={st.id} ref={(el) => { refs.current[i] = el; }} type="button" role="tab" id={`stage-tab-${st.id}`} aria-selected={i === tab} aria-controls={`stage-panel-${st.id}`} tabIndex={i === tab ? 0 : -1}
            onClick={() => setTab(i)} className={tabCls} title={`공식 단계 ${st.official}`}>
            {NUM[i]} {st.name}
          </button>
        ))}
        {extra ? (
          <button ref={(el) => { refs.current[ETC] = el; }} type="button" role="tab" id="stage-tab-etc" aria-selected={tab === ETC} aria-controls="stage-panel-etc" tabIndex={tab === ETC ? 0 : -1}
            onClick={() => setTab(ETC)} className={cn(tabCls, 'ml-1')}>
            기타
          </button>
        ) : null}
      </div>
      {s ? <div role="tabpanel" id={`stage-panel-${s.id}`} aria-labelledby={`stage-tab-${s.id}`} className="mt-3 grid gap-3">
        <div className="flex flex-wrap items-center gap-x-3.5 gap-y-1 text-[12px] text-muted-foreground" aria-label="범례">
          <span><i className="mr-1 inline-block w-6 border-t-2 border-foreground align-middle" />키 연결</span>
          <span><i className="mr-1 inline-block w-6 border-t-[1.5px] border-dashed border-foreground align-middle" />이름·주소만</span>
          <span><i className="mr-1 inline-block w-6 border-t-2 border-warn align-middle" />확보하면 연결</span>
          <span><i className="mr-1 inline-block w-6 border-t-[1.5px] border-dashed border-bad align-middle" />값·키 없음</span>
          <span className="h-3 w-px bg-border" aria-hidden="true" />
          {VIAS.map((v) => <span key={v}><b className={cn('mr-1 inline-block rounded-full border px-1.5 text-[10.5px] leading-[15px] font-bold', VIA_STYLE[v].pill)}>{v}</b>{VIA_NOTE[v]}</span>)}
        </div>
        {/* 도식은 본문 폭에 맞춰 줄어든다(화면을 넘치지 않음). 휴대폰 폭에서만 읽히게 상자 안에서 옆으로 민다 */}
        <div className="overflow-x-auto rounded-[12px] border border-border bg-card px-2 py-1">
          <Diagram s={s} />
        </div>
        <div className={GRID_DENSE}>
          <DataGrid key={s.id} label={`${s.name} 단계 자료별 연계`} cols={COLS} rows={rows} sortable={false} />
        </div>
      </div> : null}
      {extra ? <div role="tabpanel" id="stage-panel-etc" aria-labelledby="stage-tab-etc" ref={extraRef} hidden={tab !== ETC} className="mt-3">{extra}</div> : null}
    </div>
  );
}
