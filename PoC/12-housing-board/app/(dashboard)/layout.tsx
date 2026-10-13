import type { Metadata } from 'next';
import type { ReactNode } from 'react';
import TopNav from '../../components/TopNav';
import { THEME_INIT } from '../../lib/shell/theme';
import { doHyeon } from '../../lib/shell/fonts';
import '../tailwind.css';

export const metadata: Metadata = {
  title: { default: '9·7 주택공급 정책 상황판 · 주택파동', template: '%s · 주택파동' },
  description: 'PoC 10 공개 원천에 기반한 9·7 주택공급 정책 검토 후보 상황판',
};

/* 저장된 테마가 다크일 때만 그리기 전에 <html class="dark"> 를 켠다(켜 두지 않으면 라이트가 기본이다). 그리기 전에 돌아야 깜빡이지 않는다. */

/* 루트 레이아웃 ①(상단 메뉴 바 + 본문). 지도(`app/(map)`)는 루트 레이아웃이 달라서 오갈 때 전체 문서가 새로 열린다. */
export default function DashboardLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="ko" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: THEME_INIT }} />
      </head>
      {/* 본문 바탕·글꼴(옛 dash.css 의 body): 위쪽 오른편이 살짝 밝아지는 바탕(--page-bg, 테마별), 15px/1.55.
          클래스가 없는 기본 링크(상세 화면의 dl 안 링크)는 브라우저 기본 파랑 대신 주색으로 보인다. */}
      <body className={`font-sans ${doHyeon.variable} m-0 min-h-screen text-[16px] leading-[1.6] text-foreground [&_a:not([class])]:text-primary [background:var(--page-bg)] [font-synthesis:none]`}>
        <TopNav />
        <main>{children}</main>
      </body>
    </html>
  );
}
