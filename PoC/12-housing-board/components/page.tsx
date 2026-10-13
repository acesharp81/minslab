/* 대시보드 화면의 틀(옛 dash.css 의 .page .lede 와 .page h1·h2·h3). */
import type { ComponentProps, ReactNode } from 'react';
import { cn } from 'cn';

export const Page = ({ children }: { children: ReactNode }) => (
  <div className="mx-auto max-w-[1200px] px-7 pt-7 pb-12 mobile:px-4 mobile:pb-10">{children}</div>
);
export const PageTitle = ({ className, ...p }: ComponentProps<'h1'>) => <h1 className={cn('mt-1.5 mb-1 text-[32px] leading-[1.25]', className)} {...p} />;
export const Lede = ({ className, ...p }: ComponentProps<'p'>) => <p className={cn('m-0 mb-3 text-[16px] leading-[1.6] [word-break:keep-all] text-muted-foreground', className)} {...p} />;
/* 카드(panel) 안의 제목: .panel>h2 */
export const PanelTitle = ({ className, ...p }: ComponentProps<'h2'>) => <h2 className={cn('m-0 mb-3 text-[22px]', className)} {...p} />;
/* 카드 밖 구역 제목: .page h2 */
export const SectionTitle = ({ className, ...p }: ComponentProps<'h2'>) => <h2 className={cn('mt-7 mb-2.5 text-[22px]', className)} {...p} />;
/* 카드 안 소제목: .page h3 */
export const SubTitle = ({ className, ...p }: ComponentProps<'h3'>) => <h3 className={cn('mt-5 mb-3 text-[18px] font-bold text-muted-foreground', className)} {...p} />;
/* 카드 안 작은 글씨: .panel .sub */
export const sub = 'text-[14px] text-muted-foreground';
/* 표 안의 '값 없음'(.tbl .na). 표 밖의 .na 는 스타일이 없었으므로 쓰지 않는다 */
export const na = 'text-muted-foreground';

/* 목록 카드 격자(.cards)·KPI 격자(.kpis)·두 칸(.cols2): 자동 칸 수 */
export const cardsGrid = 'grid grid-cols-[repeat(auto-fit,minmax(min(260px,100%),1fr))] gap-2.5';
export const kpisGrid = 'mt-3.5 grid grid-cols-[repeat(auto-fit,minmax(min(200px,100%),1fr))] gap-2.5';
export const cols2 = 'mt-1 grid grid-cols-[repeat(auto-fit,minmax(min(420px,100%),1fr))] gap-3.5';
/* 정의 목록(.dl) */
export const Dl = ({ className, ...p }: ComponentProps<'dl'>) => (
  <dl className={cn('mt-2.5 mb-0 grid grid-cols-[max-content_minmax(0,1fr)] gap-x-4 gap-y-2.5 text-[16px] leading-[1.6] [&_dt]:text-muted-foreground [&_dd]:m-0 [&_dd]:[overflow-wrap:anywhere]', className)} {...p} />
);
