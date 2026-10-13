/* 데이터 원본 ② 키 사슬: 시도 → 시군구 → 법정동 → 필지 → 사업. 원천은 어느 고리에 걸리느냐로 자리가 정해진다.
   키가 없는 원천(주소 문장·이름만)은 점선 상자에서 다리(주소검색·연결표)를 건너 사슬에 오르고, 좌표·칸 자료는 지도에서만 쓰는 곁가지다. */
import { ArrowRight, ArrowUp } from 'lucide-react';
import { CHAIN, KEYLESS, POINT } from '../../lib/board/pipeline';

export default function KeyChain() {
  return (
    <div data-slot="key-chain">
      <ol className="m-0 grid list-none grid-cols-[repeat(5,minmax(0,1fr))] gap-2.5 p-0 mobile:grid-cols-1" aria-label="키 사슬">
        {CHAIN.map((c, i) => (
          <li key={c.id} id={`link-${c.id}`} className="relative min-w-0 scroll-mt-20">
            <div className="h-full rounded-[12px] border-2 border-primary/45 bg-card px-3 py-2.5">
              <p className="m-0 flex items-baseline justify-between gap-2"><b className="font-display text-[20px] leading-tight font-normal">{c.name}</b><code className="text-[13px] whitespace-nowrap text-muted-foreground">{c.key}</code></p>
              <ul className="m-0 mt-1.5 list-none p-0 text-[14px] leading-[1.5] [word-break:keep-all]" aria-label={`${c.name}에 걸리는 원천`}>
                {c.sources.map((s) => <li key={s} className="flex gap-1.5"><span className="text-muted-foreground" aria-hidden="true">·</span>{s}</li>)}
              </ul>
            </div>
            {i < CHAIN.length - 1 ? (
              <span className="absolute top-1/2 -right-[17px] z-[1] grid size-[24px] -translate-y-1/2 place-items-center rounded-full border border-border bg-card text-muted-foreground mobile:top-auto mobile:right-auto mobile:-bottom-[17px] mobile:left-1/2 mobile:-translate-x-1/2 mobile:translate-y-0" aria-hidden="true">
                <ArrowRight className="size-3.5 mobile:rotate-90" strokeWidth={2.5} />
              </span>
            ) : null}
          </li>
        ))}
      </ol>
      <div className="mt-2.5 grid grid-cols-[minmax(0,3fr)_minmax(0,2fr)] gap-2.5 mobile:grid-cols-1">
        <div id="link-keyless" className="min-w-0 scroll-mt-20 rounded-[12px] border-2 border-dashed border-line2 bg-card px-3 py-2.5">
          <p className="m-0 flex items-center gap-2"><ArrowUp className="size-4 text-muted-foreground" aria-hidden="true" /><b className="font-display text-[20px] leading-tight font-normal">{KEYLESS.name}</b><span className="text-[14px] text-muted-foreground">→ 아래 방법으로 필지 고리에 올림</span></p>
          <p className="m-0 mt-1 text-[14px] leading-[1.5] [word-break:keep-all]">{KEYLESS.sources.join(' · ')}</p>
          <p className="m-0 mt-1 text-[14px] leading-[1.5] text-muted-foreground [word-break:keep-all]">{KEYLESS.bridge}</p>
        </div>
        <div className="min-w-0 rounded-[12px] border border-border bg-card px-3 py-2.5">
          <p className="m-0"><b className="font-display text-[20px] leading-tight font-normal">{POINT.name}</b> <span className="text-[14px] text-muted-foreground">{POINT.note}</span></p>
          <p className="m-0 mt-1 text-[14px] leading-[1.5] [word-break:keep-all]">{POINT.sources.join(' · ')}</p>
        </div>
      </div>
    </div>
  );
}
