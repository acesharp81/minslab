/* 데이터 원본의 접는 상자: 요약은 펼쳐 두고 상세(단계별·계산 근거·원천별 카드)는 여기 넣어 필요할 때만 연다.
   상자 안의 앵커(#step-… · #id)로 오면 HashOpen 이 연다. Chromium 은 수화 전에 스스로 열어 open 속성이 서버 HTML 과 달라지므로
   그 차이는 경고하지 않는다(suppressHydrationWarning — 열린 채 두는 것이 맞다). */
import type { ReactNode } from 'react';
import { ChevronRight } from 'lucide-react';
import { cn } from 'cn';

export default function Fold({ title, meta, children, className }: { title: string; meta?: string; children: ReactNode; className?: string }) {
  return (
    <details suppressHydrationWarning className={cn('group mt-3 rounded-[12px] border border-border bg-card', className)}>
      <summary className="flex cursor-pointer list-none flex-wrap items-center gap-x-2 gap-y-0.5 rounded-[12px] px-4 py-2.5 text-[15px] font-bold hover:bg-pn2 focus-visible:outline-2 focus-visible:outline-primary [&::-webkit-details-marker]:hidden">
        <ChevronRight className="size-4 flex-none text-muted-foreground transition-transform group-open:rotate-90" aria-hidden="true" />
        {title}{meta ? <span className="font-normal text-muted-foreground">{meta}</span> : null}
      </summary>
      <div className="border-t border-border px-4 py-3">{children}</div>
    </details>
  );
}
