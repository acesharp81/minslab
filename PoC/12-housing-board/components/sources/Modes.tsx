/* 데이터 원본 ③ 실시간·보관: 자료 17가지를 갈래별 한 줄 목록으로(이름 · 바뀌는 방식 · 주기), 한도 대비 호출을 막대 그림 하나로 모은다.
   판정 기준(B1~B5 · R1~R4)과 자료별 계산은 접는다. 막대는 한 계열(호출 ÷ 한도)이라 범례 없이 값을 글자로 적고 80% 기준선(스펙 5.4)을 긋는다. */
import { Fragment } from 'react';
import { fmt } from '../../lib/board/calc';
import { GUIDE, ITEMS, MODE_LABEL, RULES, pct, type Item, type Mode, type RuleId } from '../../lib/board/pipeline';
import Fold from './Fold';
import { MODE_FILL } from './Summary';

export const ModeSwatch = ({ m }: { m: Mode }) => <i className="inline-block size-[11px] flex-none rounded-[3px]" style={{ background: MODE_FILL[m] }} aria-hidden="true" />;
const NOTE: Record<Mode, string> = {
  store: '지난 기록 · 여러 곳을 합친 값 · 사람이 판단한 값 · 파일로만 받는 자료',
  mixed: '지금 값은 실시간, 이력은 따로 기록',
  live: '한 위치의 상세 · 지금 값이 중요한 것 · 너무 커서 일부만 보는 것',
};
const change = (i: Item) => (i.now === i.mode ? null : i.now === 'none' ? '아직 없음 · 새로 만들 것' : `지금은 ${MODE_LABEL[i.now]} → ${MODE_LABEL[i.mode]}으로 바꿀 계획`);

function List({ m }: { m: Mode }) {
  const list = ITEMS.filter((i) => i.mode === m);
  return (
    <section className="card-soft min-w-0 rounded-[14px] border border-border bg-card px-5 py-4 shadow-[var(--shadow-card)]" aria-label={`${MODE_LABEL[m]} ${list.length}가지`}>
      <h3 className="m-0 flex flex-wrap items-baseline gap-x-2 text-[18px]"><span className="flex items-center gap-2"><ModeSwatch m={m} />{MODE_LABEL[m]}</span><span className="text-[15px] font-normal text-muted-foreground tabular-nums">{list.length}가지</span><span className="text-[13px] font-normal text-muted-foreground">{NOTE[m]}</span></h3>
      <ul className="m-0 mt-2 list-none p-0">
        {list.map((i) => (
          <li key={i.id} id={`item-${i.id}`} className="flex scroll-mt-20 flex-wrap items-baseline justify-between gap-x-3 border-b border-border py-1.5 text-[14px] last:border-b-0" title={i.calc}>
            <span className="font-bold">{i.name}{change(i) ? <span className="ml-2 text-[12px] font-normal text-primary">{change(i)}</span> : null}</span>
            <span className="text-[13px] text-muted-foreground">{i.cycle}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}

/* 한도 대비 호출: 막대가 있는 자료만, 같은 축(0~100%)에 */
function Usage() {
  const rows = ITEMS.filter((i) => i.meter);
  return (
    <section className="card-soft min-w-0 rounded-[14px] border border-border bg-card px-5 py-4 shadow-[var(--shadow-card)]" aria-label="한도 대비 호출">
      <h3 className="m-0 text-[18px]">한도 대비 호출 <span className="text-[13px] font-normal text-muted-foreground">원천이 허용하는 호출 수(한도) 중 우리가 쓰는 몫 — 한도의 {GUIDE * 100}%를 넘지 않게 운영</span></h3>
      <div className="mt-3 grid grid-cols-[minmax(0,210px)_minmax(0,1fr)_92px] items-center gap-x-3 gap-y-2.5 mobile:grid-cols-[minmax(0,1fr)_92px]">
        <span className="mobile:hidden" />
        <span className="relative h-4 text-[12px] text-muted-foreground mobile:col-span-2" aria-hidden="true"><span className="absolute -translate-x-1/2 whitespace-nowrap" style={{ left: `${GUIDE * 100}%` }}>기준 {GUIDE * 100}%</span></span>
        <span className="mobile:hidden" />
        {rows.map((i) => {
          const m = i.meter!, p = pct(m);
          return (
            <Fragment key={i.id}>
              <span className="text-[14px] leading-[1.35] [word-break:keep-all] mobile:col-span-2"><b>{i.name}</b><span className="block text-[12px] text-muted-foreground">{m.label}</span></span>
              <span className="relative h-[12px] rounded-full bg-muted" role="img" aria-label={`${i.name}: 한도의 ${p}%`}>
                <span className="q-grow-x absolute inset-y-0 left-0 rounded-full bg-primary" style={{ width: `${p}%` }} />
                <span className="absolute -top-[4px] -bottom-[4px] w-[2px] bg-foreground/55" style={{ left: `${GUIDE * 100}%` }} />
              </span>
              <span className="text-right text-[13px] text-muted-foreground tabular-nums"><b className="text-[15px] text-foreground">{p}%</b><span className="block text-[11px]">{fmt(m.used)}/{fmt(m.limit)}</span></span>
            </Fragment>
          );
        })}
      </div>
    </section>
  );
}

export default function Modes() {
  return (
    <div data-slot="modes">
      <div className="grid grid-cols-[minmax(0,1.1fr)_minmax(0,1fr)] gap-3 narrow:grid-cols-1">
        <List m="store" />
        <div className="grid content-start gap-3">
          <List m="mixed" />
          <List m="live" />
        </div>
      </div>
      <div className="mt-3"><Usage /></div>
      <Fold title="나눈 기준과 자료별 계산" meta={`보관 기준 5 · 실시간 기준 4 · 자료 ${ITEMS.length}종`}>
        <div className="grid grid-cols-2 gap-x-6 gap-y-1 mobile:grid-cols-1">
          {(['B', 'R'] as const).map((k) => (
            <div key={k}>
              <p className="m-0 mb-1 text-[13px] font-bold text-muted-foreground">{k === 'B' ? '보관 — 하나라도 맞으면' : '실시간 — 위치 하나를 볼 때'}</p>
              <dl className="m-0 grid grid-cols-[max-content_minmax(0,1fr)] gap-x-3 gap-y-1 text-[14px] leading-[1.5] [&_dd]:m-0 [&_dd]:[word-break:keep-all]">
                {(Object.keys(RULES) as RuleId[]).filter((r) => r.startsWith(k)).map((r) => <Fragment key={r}><dt className="font-bold text-muted-foreground">{r}</dt><dd>{RULES[r]}</dd></Fragment>)}
              </dl>
            </div>
          ))}
        </div>
        <ul className="m-0 mt-3 grid list-none gap-1.5 border-t border-border p-0 pt-3 text-[14px] leading-[1.55]">
          {ITEMS.map((i) => (
            <li key={i.id} className="[word-break:keep-all]"><ModeSwatch m={i.mode} /> <b>{i.name}</b> <span className="text-[12px] text-muted-foreground">{i.why.join(' ')}{i.estimate ? ' · 추정' : ''}</span> — {i.calc}</li>
          ))}
        </ul>
      </Fold>
    </div>
  );
}
