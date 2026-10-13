/* 공급 6단계 계단(발표자료 SHEET 03 '주택공급 6단계, 단계마다 답해야 할 질문'의 그림). 단계를 표기하는 화면(단계별·단계 상세·사업 상세·사업 목록)이 함께 쓴다.
   범례(공개 범위) → 계단 6칸(상자가 단계마다 높아지고 한 기준선에 선다) → 칸마다 질문. 01~04 는 담당자 열람(파랑), 05~06 은 국민 공개(초록).
   current 는 지금 단계(진한 면·주색 고리·'현재'), counts 는 칸 안의 사업 수. 칸은 그 단계의 목록(/stage/NN)으로 가는 링크다.
   900px 이하는 계단 대신 세로 목록(상자 높이를 풀고 질문을 옆에). */
import type { CSSProperties } from 'react';
import Link from 'next/link';
import { cn } from 'cn';
import { STAGES } from '../lib/board/stages';

type Props = { current?: string; counts?: Record<string, number>; className?: string };

const SCOPE = { gov: 'var(--scope-gov)', pub: 'var(--scope-pub)' } as const;

export default function StageLadder({ current, counts, className }: Props) {
  return (
    <div data-slot="stage-ladder" className={cn('mt-3', className)}>
      <p className="m-0 mb-2 flex flex-wrap gap-x-4 gap-y-1 text-[14px] text-muted-foreground" aria-label="공개 범위">
        <span className="flex items-center gap-1.5"><i className="block size-[11px] rounded-[3px] border-2 border-[var(--scope-gov)]" aria-hidden="true" />담당자 열람 (01~04)</span>
        <span className="flex items-center gap-1.5"><i className="block size-[11px] rounded-[3px] border-2 border-[var(--scope-pub)]" aria-hidden="true" />국민에게도 공개 (05~06)</span>
      </p>
      <ol className="m-0 grid list-none grid-cols-6 p-0 mobile:grid-cols-1 mobile:gap-2" aria-label="공급 6단계">
        {STAGES.map((s, i) => {
          const on = s.code === current, n = counts?.[s.code];
          const style = { '--sc': SCOPE[s.scope], '--h': `${64 + i * 16}px`, '--i': i * 1.5 } as CSSProperties;   // --i: 첫 화면에 01→06 차례로 오른다(q-rise)
          return (
            <li key={s.code} className="q-rise flex min-w-0 flex-col mobile:grid mobile:grid-cols-[150px_minmax(0,1fr)] mobile:items-center mobile:gap-3" style={style}>
              <div className="flex h-[148px] items-end border-b-2 border-line2 px-1.5 mobile:h-auto mobile:border-b-0 mobile:px-0">
                <Link href={`/stage/${s.code}`} aria-current={on ? 'step' : undefined}
                  className={cn('card-lift keep-border flex h-[var(--h)] w-full flex-col items-center justify-center gap-0.5 border-2 border-b-0 border-[var(--sc)] px-1 text-center no-underline mobile:h-auto mobile:rounded-[8px] mobile:border-b-2 mobile:py-2',
                    'focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary',
                    on ? 'q-pulse bg-[color-mix(in_srgb,var(--sc)_24%,var(--card))] text-foreground [box-shadow:0_0_0_2px_var(--primary)]' : 'bg-[color-mix(in_srgb,var(--sc)_14%,var(--card))] text-[var(--sc)] hover:bg-[color-mix(in_srgb,var(--sc)_22%,var(--card))]')}>
                  <span className="text-[15px] leading-none tabular-nums">{s.code}</span>
                  <b className="font-display text-[20px] leading-[1.25] font-normal">{s.name}</b>
                  {n !== undefined ? <span className="text-[14px] leading-none text-foreground tabular-nums">{n}건</span> : null}
                  {on ? <span className="mt-0.5 rounded-full bg-primary px-2 text-[12px] leading-[18px] font-bold text-primary-foreground">현재</span> : null}
                </Link>
              </div>
              <p className="m-0 px-2 pt-2.5 text-center text-[14px] leading-[1.5] text-muted-foreground [word-break:keep-all] mobile:p-0 mobile:text-left">{s.q}</p>
            </li>
          );
        })}
      </ol>
    </div>
  );
}
