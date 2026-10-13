import type { Metadata } from 'next';
import type { ReactNode } from 'react';
import TopNav from '../../components/TopNav';
import { THEME_INIT } from '../../lib/shell/theme';
import { doHyeon } from '../../lib/shell/fonts';
import '../tailwind.css';

export const metadata: Metadata = {
  title: '주택파동 공급 지도',
  description: '공공주택 공급 현황을 V-World 공식 건물 위에 3차원으로 보여 주는 지도',
};

/* 루트 레이아웃 ②(상단 메뉴 바 + 지도, 대시보드와 저장된 테마 공유). 지도 앱(assets/js/app.js)은 마운트·해제 개념이 없는 스크립트라서
   대시보드와 루트 레이아웃을 나눠, 들어올 때 새 문서가 열리게 했다. 스타일은 기존 app.css 를 그대로 쓴다. */
export default function MapLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="ko" data-map-shell="" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: THEME_INIT }} />
        {/* 지도가 곧 요청할 외부 서버와 미리 연결해 둔다(첫 타일이 빨리 온다) */}
        <link rel="preconnect" href="https://api.vworld.kr" crossOrigin="" />
        <link rel="preconnect" href="https://s3.amazonaws.com" crossOrigin="" />
        <link rel="preconnect" href="https://tiles.openfreemap.org" crossOrigin="" />
        <link rel="stylesheet" href="/poc/housing-board/assets/vendor/maplibre-gl/5.24.0/maplibre-gl.css" />
        <link rel="stylesheet" href="/poc/housing-board/assets/css/app.css" />
      </head>
      <body className={`font-sans ${doHyeon.variable} [font-synthesis:none]`}>
        <div className="shell-map flex h-screen flex-col overflow-hidden">
          <TopNav compact />
          {children}
        </div>
      </body>
    </html>
  );
}
