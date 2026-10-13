/* 종합상황판의 공통 클래스(옛 board.css 의 .disp · 버튼 초기화 · .ptitle · .plink · .row2 · 막대 행). Board 와 RealPanels 가 함께 쓴다. */

/* 숫자 글씨(.disp): 본문과 같은 글꼴과 같은 폭 숫자를 쓴다. */
export const disp = "font-display font-bold tabular-nums tracking-[0]";   // 숫자·패널 제목은 Do Hyeon(계획서 14절 T1). 본문 글자는 시스템 본문 글꼴

/* 옛 `.board button` 초기화(app/tailwind.css 의 .btn-reset, components 레이어). 단추마다 붙이면 뒤에 덧입힌 유틸리티가 이긴다 */
export const btn = "btn-reset";

/* 패널 제목(.ptitle)과 그 안의 작은 설명(.ptitle small). 제목 안의 표지는 10.5px */
export const ptitle = `m-0 text-[22px] leading-[1.25] ${disp} [&_[data-slot=badge]]:text-[12px]`;
export const ptSmall = "[font-family:inherit] text-[14px] font-normal text-muted-foreground";
export const ptSmallBlock = `${ptSmall} mt-0.5 block`;

/* 패널 제목 줄(왼쪽 제목, 오른쪽 위 이동 버튼 묶음). 좁으면 버튼은 그대로 두고 제목이 줄바꿈한다 */
export const phead = "flex items-start gap-3";
export const pacts = "ml-auto flex flex-none gap-1.5";

/* 두 칸 행(.row2: 월별 실적 흐름 | 전국 17개 시도)과 막대 행(.ags .ag .an .ad .bar3).
   시도 칸은 타일 6열(112×6 + 간격 6×5 + 안쪽 여백 42 = 744)이 들어가는 750px 로 고정해 17곳이 3줄로 끝나게 한다 — 시도 카드(약 447)와 실적 카드(약 454) 높이가 비슷하고, 남는 높이는 타일이 늘어나 채운다.
   1280px 미만에서는 실적 그래프 칸이 너무 좁아져 위아래로 쌓는다. */
export const row2 = "mt-3.5 grid grid-cols-1 items-stretch gap-3.5 min-[1280px]:grid-cols-[minmax(0,1fr)_750px]";
export const ags = "mt-2.5 flex flex-auto flex-col justify-around gap-1.5";
export const ag = "grid items-center gap-2.5";
export const agName = "flex min-w-0 flex-wrap items-baseline gap-x-[5px] [&_b]:text-[15px] [&_b]:leading-[1.3]";
export const agVal = "flex items-baseline justify-end gap-[5px] whitespace-nowrap [&_b]:font-display [&_b]:text-[20px] [&_b]:leading-[1.2]";
export const bar3 = "flex gap-px overflow-hidden";   // 막대 그래프는 모서리를 둥글리지 않는다(계획서 11절)
