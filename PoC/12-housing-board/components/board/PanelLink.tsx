import Link from 'next/link';
import { ChevronRight } from 'lucide-react';
import type { ReactNode } from 'react';

/* 이동 동작은 링크로 유지하고, 상황판 카드 제목 줄 오른쪽에 채운 주색 버튼으로 작게 표시한다. 화면에는 줄인 이름(children)을, 마우스를 올리면 원래 이름(full)을 보인다. */
export default function PanelLink({ href, full, children }: { href: string; full: string; children: ReactNode }) {
  return <Link href={href} title={full} className="group/action inline-flex h-7 flex-none items-center gap-1 rounded-md bg-primary px-2.5 text-[13px] leading-none font-medium whitespace-nowrap text-primary-foreground no-underline transition-colors hover:bg-primary/85 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary">
    <span>{children}</span><ChevronRight className="size-3 shrink-0 transition-transform group-hover/action:translate-x-0.5 motion-reduce:transition-none" aria-hidden="true" />
  </Link>;
}
