import localFont from 'next/font/local';

// 로고·본문·차트·지도 패널이 같은 전체 글꼴 파일을 공유한다.
// display 'block': 대체 글꼴(Apple SD Gothic Neo 등)로 먼저 그렸다가 바꾸면 글자 폭이 달라 상단 메뉴가 좌우로 오므라들었다(2026-10-10 실측: 메뉴 708→655px, 로고 100→88px).
// 우리 서버의 200KB 글꼴이라 처음 열 때 글자가 잠깐(보통 0.1초 이하) 비어 있다가 제 글꼴로 한 번에 나온다.
export const doHyeon = localFont({
  src: '../../assets/fonts/do-hyeon/DoHyeon-Regular.woff2',
  weight: '400',
  style: 'normal',
  display: 'block',
  variable: '--font-do-hyeon',
  adjustFontFallback: false,
  fallback: ['Apple SD Gothic Neo', 'Malgun Gothic', 'sans-serif'],
});
