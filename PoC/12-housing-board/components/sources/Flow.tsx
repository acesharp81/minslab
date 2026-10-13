/* 원천 → 보관 4개 묶음(8단계) / 실시간 → 화면. 각 단계는 접힌 상세로 연결한다. */
import Link from 'next/link';
import { ArrowLeft, ArrowRight } from 'lucide-react';
import { cn } from 'cn';
import { ENDS, LIVE, ORIGINS, PHASES, STATUS_LABEL, STEPS, TRACE, type Status, type Step } from '../../lib/board/pipeline';

/* 보관·실시간 갈래의 색. 글자는 본문 색이고 색은 선·점이 맡는다 */
export const MODE_TONE = { store: 'var(--primary)', live: 'var(--chart-2)' } as const;

/* 상태 점: 채움(구현됨) · 반 채움(일부) · 빈 원(계획). 모양이 뜻을 갖고 색은 갈래를 따른다 */
export function Dot({ s, tone = MODE_TONE.store, size = 16, className }: { s: Status; tone?: string; size?: number; className?: string }) {
  const fill = s === 'done' ? tone : s === 'part' ? `linear-gradient(90deg, ${tone} 50%, var(--card) 50%)` : 'var(--card)';
  return <i className={cn('inline-block flex-none rounded-full border-2', className)} style={{ width: size, height: size, borderColor: tone, background: fill }} role="img" aria-label={STATUS_LABEL[s]} />;
}
export function DotLegend({ className }: { className?: string }) {
  return (
    <p className={cn('m-0 flex flex-wrap items-center gap-x-3 gap-y-1 text-[13px] text-muted-foreground', className)}>
      <b className="text-foreground">구현 상태</b>
      {(['done', 'part', 'plan'] as Status[]).map((s) => <span key={s} className="flex items-center gap-1.5"><Dot s={s} size={12} />{STATUS_LABEL[s]}</span>)}
    </p>
  );
}

const byId = (id: string) => STEPS.find((s) => s.id === id) as Step;
function Station({ s, tone }: { s: Step; tone: string }) {
  return (
    <li className="relative z-[1] min-w-0">
      <a href={`#step-${s.id}`} title={`${STATUS_LABEL[s.status]} — ${s.now}`}
        className="flex flex-col items-center gap-1.5 rounded-[8px] px-0.5 pb-1 text-center text-foreground no-underline hover:bg-pn2 focus-visible:outline-2 focus-visible:outline-primary mobile:flex-row mobile:gap-3 mobile:px-0 mobile:text-left">
        <Dot s={s.status} tone={tone} size={18} />
        <span className="text-[14px] leading-[1.3] [word-break:keep-all]"><b className="mr-0.5 text-muted-foreground tabular-nums">{s.no}</b> {s.name}</span>
      </a>
    </li>
  );
}

export default function Flow() {
  return (
    <div data-slot="flow" className="rounded-[14px] border border-border bg-card p-5 shadow-[var(--shadow-card)] mobile:p-4">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
        <p className="m-0 text-[14px] font-bold">원천 → 수집·가공 → 화면</p>
        <DotLegend />
      </div>
      <div className="mb-4 flex flex-wrap items-center gap-x-5 gap-y-2 border-b border-border pb-4" aria-label="원천을 받는 방식">
        {ORIGINS.map((o) => <span key={o.id} className="flex items-center gap-2 text-[14px]" title={`${o.how} — ${o.examples.join(', ')}`}><Dot s={o.status} size={12} /><b>{o.name}</b></span>)}
      </div>
      <p className="m-0 mb-2 text-[13px] text-muted-foreground"><b className="text-primary">보관 경로</b> · 미리 받아 검토한 자료를 상황판에 반영</p>
      <div className="grid grid-cols-4 gap-3 mobile:grid-cols-2 phone:grid-cols-1">
        {PHASES.map((phase, i) => <section key={phase.name} className="relative min-w-0 rounded-[10px] bg-muted p-3">
          <h3 className="m-0 mb-3 flex items-center gap-2 text-[17px]"><span className="grid size-6 flex-none place-items-center rounded-full bg-primary text-[13px] text-primary-foreground">{i + 1}</span>{phase.name}</h3>
          <ol className="m-0 grid list-none grid-cols-2 gap-2 p-0 phone:grid-cols-2" aria-label={`${phase.name} 단계`}>
            {phase.steps.map((id) => <Station key={id} s={byId(id)} tone={MODE_TONE.store} />)}
          </ol>
          {i < PHASES.length - 1 ? <ArrowRight className="absolute top-4 -right-[15px] z-[1] size-4 text-muted-foreground mobile:hidden" aria-hidden="true" /> : null}
        </section>)}
      </div>
      <div className="mt-3 flex flex-wrap items-center justify-between gap-2 rounded-[10px] border border-border px-3 py-2.5">
        <a href={`#step-${LIVE.id}`} className="inline-flex items-center gap-2 text-[14px] text-foreground no-underline hover:underline"><Dot s={LIVE.status} tone={MODE_TONE.live} size={14} /><b>실시간 경로</b><span className="text-muted-foreground">지도 상세 · 요청 창구 8개</span></a>
        <span className="text-[12px] text-muted-foreground">열 때 요청 · 최대 24시간 캐시</span>
      </div>
      <div className="mt-4 flex flex-wrap items-center gap-x-5 gap-y-2 border-t border-border pt-3 text-[13px]">
        <b>화면에서 활용</b>
        {ENDS.map((e) => <span key={e.who} className="flex flex-wrap items-center gap-x-2 gap-y-1"><span className="text-muted-foreground">{e.who}</span>{e.screens.map(([name, href]) => (href === '/map' ? <a key={href} href={`/poc/housing-board${href}`}>{name}</a> : <Link key={href} href={href}>{name}</Link>))}</span>)}
      </div>
      <p className="m-0 mt-3 flex flex-wrap items-center gap-x-2 gap-y-1 text-[12px] text-muted-foreground" aria-label="근거 보기: 끝에서 시작으로">
        <b>출처 추적</b>{TRACE.map((t, i) => <span key={t} className="flex items-center gap-2">{i ? <ArrowLeft className="size-3" aria-hidden="true" /> : null}{t.replace('(⑥)', '')}</span>)}
      </p>
    </div>
  );
}

/* 단계 상세(접힌 상자 안): 한 줄에 상태·이름·지금·계획. 정거장 링크가 #step-… 로 온다 */
export function StepList() {
  return (
    <ol className="m-0 grid list-none p-0" aria-label="단계별 지금과 계획">
      {[...STEPS, LIVE].map((s) => (
        <li key={s.id} id={`step-${s.id}`} className="grid scroll-mt-20 grid-cols-[170px_repeat(3,minmax(0,1fr))] gap-x-4 border-b border-border py-2.5 text-[14px] leading-[1.55] last:border-b-0 mobile:grid-cols-1 mobile:gap-y-1">
          <span className="flex items-start gap-2 font-bold"><Dot s={s.status} tone={s.id === 'live' ? MODE_TONE.live : MODE_TONE.store} size={14} className="mt-[3px]" /><span><span className="mr-1 text-muted-foreground tabular-nums">{s.no}</span>{s.name}</span></span>
          <span className="[word-break:keep-all]"><span className="mr-1.5 text-muted-foreground">하는 일</span>{s.does}</span>
          <span className="[word-break:keep-all]"><span className="mr-1.5 text-muted-foreground">지금</span>{s.now}</span>
          <span className="[word-break:keep-all]"><span className="mr-1.5 text-muted-foreground">계획</span>{s.next}</span>
        </li>
      ))}
    </ol>
  );
}
