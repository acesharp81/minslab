# Tailwind CSS · shadcn/ui 전환 계획 (2026-10-09)

- 결정(사용자): ① 예전 요소(바닐라 지도 앱·옛 CSS·옛 개발 서버)를 버리고 **Next.js · React · Tailwind CSS · shadcn/ui**로 옮긴다. ② **지도 앱은 React 선언형으로 전부 재작성**한다(엔진 유지안은 채택하지 않음). ③ 화면은 **픽셀 단위로 완전히 같아야** 한다. ④ **1~4단계를 먼저** 하고, 지도(5~7단계)는 그 결과를 보고 진행 여부를 다시 정한다.
- 기준 커밋: `1f63b3d`(로컬 태그 `pre-tailwind`). 이 커밋의 화면이 "현재 상태"다.

## 분석 요약 (2026-10-09 측정)

| 예전 요소 | 규모 |
|---|---|
| `assets/js/app.js` | 1,785줄 · `#id` 참조 162회(고유 87) · 이벤트 39 · 레이어 69 · 전역 `window.*` |
| `assets/js/` 나머지 5개 | 1,270줄(`region` `goto` `infra` `bus` `facility`) — 순수 함수 |
| `index.html` · `assets/css/app.css` | 187줄 · 516줄(클래스 212, `backdrop-filter` 23) |
| 대시보드 CSS | `dash.css` 86 · `board.css` 153 · `shell.css` 50 |
| 시험 | 순수 함수 144건(옮기기 쉬움) · 문자열 검사 약 60건(다시 써야 함) |

임시 폴더에서 Next 16.4 · React 19.3 · Tailwind 4 · shadcn 4.21.4 로 `init` + 컴포넌트 22개 + `next build` 성공을 확인했다. shadcn 기본 스타일은 `base-nova`(Radix가 아닌 **Base UI**, `lucide-react` 1.x, `cmdk`, `cn`)이고, `Sidebar`는 아이콘 모드·모바일 `Sheet`를 기본 제공한다.

## 단계

| 단계 | 내용 | 통과 조건 |
|---|---|---|
| 1 | 화면 비교 기준선·도구 — **완료** | 같은 화면 반복 촬영이 한 픽셀도 안 다름(알려진 잡음 제외) |
| 2 | Tailwind · shadcn 기반(토큰·`cn`·`components.json`), **preflight 보류** — **완료** | 기준선과 같음: 80장 모두 같음 |
| 3 | 대시보드 화면(레일·빵부스러기·카드·표·차트 틀)을 shadcn/Tailwind로, `dash.css`·`shell.css` 삭제 — **완료** | 기준선과 같음: 80장 모두 같음 |
| 4 | `/` 종합상황판(`board.css` 삭제). 리본 차트 SVG 계산은 유지 — **완료** | 옛 코드와 80장 모두 같음 |
| 5~7 | 지도 앱 React 선언형 재작성·옛 파일 삭제·정리 | (1~4 결과를 보고 다시 정함) |

## 화면 비교 도구 (`scripts/visual/`)

```
npm run build && npx next start -p 3100 &
node scripts/visual/shoot.js --base http://localhost:3100 --out .visual/current --map
node scripts/visual/diff.mjs .visual/baseline .visual/current       # 다르면 종료 코드 1, 차이는 current/diff/ 에 빨간 PNG
```

- 대상: 대시보드 22개 경로 × 해상도 3(1440·1100·390) + 상호작용 상태 11종 + `/map` 레일 잘라내기 = **80장**(`.visual/`은 gitignore). **기준선은 변환 직전 커밋의 빌드를 같은 하네스로 찍은 것이다** — 촬영 방식을 바꾸면 기준선도 같은 방식으로 다시 찍어야 하므로, 옛 커밋을 작업 트리로 빌드해 따로 서버(포트 3200)를 띄우고 `--legacy` 로 찍는다(`git worktree add ../housing-board-old <커밋>`, `node_modules` 는 심볼릭 링크가 아니라 복사: Turbopack 이 심볼릭 링크를 거부한다). 4단계 기준선은 `3ee6978`(종합상황판 변환 직전)이다.
- 결정적이게: `prefers-reduced-motion`(시안 순환·전환 끔), 촬영 전 포인터를 화면 밖으로 치움, 글꼴 로딩 대기, 툴팁은 보일 때까지 대기.
- **긴 페이지는 뷰포트 높이를 페이지 전체로 키워 화면 안에서 찍는다.** `captureBeyondViewport`로 화면 밖을 찍으면 스크롤 컨테이너 안 `sticky` 표 헤더의 글자 가장자리가 CSS와 무관하게 다르게 래스터되는 아티팩트가 생겼다(2026-10-09: 비어 있는 CSS와 `@layer` 한 줄뿐인 CSS가 서로 다른 화면을 냈고, 전체 높이로 키우자 같아졌다). 원인을 가려 내려고 변경을 하나씩 빼 가며 비교한 결과다.
- **이미지는 CSS 픽셀과 1:1**이어야 한다. `ego-browser`의 `page.screenshot`은 화면 배율(이 기계 1.1) 보정이 겹쳐 이미지가 줄어들어, `Page.captureScreenshot`을 `clip.scale: 1`로 직접 부른다. 뷰포트 폭도 같은 배율로 보정해 준다(모바일 에뮬레이션 폭은 그대로).
- 비교는 한 픽셀의 R·G·B 최대 차이가 **2 이하면 같은 것**으로 본다(그라데이션 디더링 잡음: 같은 화면을 두 번 찍어도 ±1~2). 알려진 잡음은 `noise.json`에 파일 이름과 픽셀 수로 적는다 — `/` 의 1440 상태 화면 8장이 같은 코드에서도 실행마다 최대 약 100px(차이 35) 흔들린다. 한 번 나타났다 사라지는 14×14 흰 사각형·화살표(차이 200 이상)는 허용 목록이 아니라 그 화면만 다시 찍어 확인한다.
- 지도 캔버스는 타일·버스 때문에 비교하지 않는다. 지도 화면의 껍데기 비교는 5단계에서 정한다. 모바일 지도 크롭은 햄버거 영역(위 100px)만 비교한다(그 아래는 지도 캔버스).
- **하네스가 흔들림 없이 찍으려고 막은 것들(2026-10-09)**: ① 모든 이동이 `about:blank` 를 거친다 — 앞 화면이 모바일 폭이었는지에 따라 본문 폭이 14px 달라지는(스크롤바 방식) 문제. ② 높이가 안정될 때까지 기다린 뒤 잰다. ③ 방문한 링크 색을 방문 전과 같게 보이게 한다(`@layer base{:where(a:visited){color:LinkText}}` 주입) — 브라우저가 방문 기록을 비동기로 반영해서 같은 화면의 기본 링크 색이 실행마다 파랑/보라로 갈렸다. `-webkit-link` 는 방문 상태에 따라 풀려서 소용없고, 레이어 없이 주입하면 레이어 안의 Tailwind 색까지 이긴다. ④ ego lite 를 앞으로 띄우지 않는다: 작업 공간 하나(`.visual/.ego-space`)를 계속 이어 쓰면 활성화 없이도 캡처가 되고(새 창을 만들었다 닫기를 반복하면 가려진 창에서 `Page.captureScreenshot` 이 멈췄다), 끝나도 닫지 않는다(`--close` 일 때만). ⑤ 캡처 영역 단위(DIP): 영역을 화면 배율만큼 곱하고 `scale: 1/배율`로 찍는다 — 예전에는 그냥 `scale 1` 로 찍어 오른쪽 9% 가 잘리고 1.1배로 확대돼 있었다. ⑥ **촬영 주소는 `http://127.0.0.1:포트`** 로 한다: 이 브라우저 프로필에는 `localhost` 만 110% 확대가 저장돼 있어 화면 배율이 1.1 이 되고, 소수 픽셀 반올림 때문에 카드·표의 1px 테두리가 실행마다 다르게 그려졌다(같은 화면 두 번에 최대 차이 57). `127.0.0.1` 은 배율 1 이라 두 번 찍어도 완전히 같다. ⑦ 스크롤바를 숨긴다(`Emulation.setScrollbarsHidden`).
- `scripts/visual/geom.js`: 스크린샷이 다르다고만 나올 때, 두 서버의 같은 화면에서 모든 요소의 위치·크기를 DOM 순서로 비교해 **어느 요소부터 어긋나는지** 알려 준다(스크롤바를 숨기고 잰다). 4단계에서 범례 단추 글자 크기·1100px 경계를 이것으로 찾았다.

## 알려진 한계

- 브라우저 기본 위젯(`<input type=range>` · `<select>` · `<details>` · 체크박스)은 shadcn 컴포넌트로 바꾸면 픽셀이 달라진다. 픽셀 동일이 우선이라 이런 곳은 기본 위젯을 유지하고 Tailwind로 겉만 맞춘다.
- shadcn 기본값(둥근 정도·높이·포커스 링)은 우리 디자인과 다르므로 컴포넌트마다 덮어쓴다. Tailwind `preflight`는 전역 리셋이라 마지막 단계에서 켠다.

## 3·4단계 기록 (2026-10-09)

- **새 컴포넌트(`components/ui/`)**: `card`(panel·kpi·link·source·board) · `badge`(default·warn·ok·solid) · `table` · `alert` · `breadcrumb` · `button` · `stepper`(shadcn 에 없는 부품) · `sheet` · `sidebar`. 모두 shadcn(base-nova, Base UI) 골격을 따르되 이 앱이 쓰는 것만 남겼고, 값은 옛 치수 그대로 고정했다. 페이지 틀은 `components/page.tsx`, 종합상황판 공통 값은 `components/board/styles.ts`·`tags.tsx`.
- **Sidebar**(※ 같은 날 상단 바로 대체되어 삭제됨 — 아래 '상단 바·라이트 모드'): shadcn 은 `fixed` 레일 + 자리 차지용 빈 칸 두 겹이지만, 그렇게 하면 본문의 둥근 모서리가 다르게 그려져(기준선과 69px 차이) 옛 레일처럼 **흐름 안의 `sticky` 한 요소**로 두었다. 접힘(220↔56px)·900px 이하 서랍(Base UI Dialog: Esc·바깥 누르기·포커스 가둠)·`localStorage rail-folded`·지도 레이아웃의 강제 접힘은 그대로다. 레이아웃은 `ShellRail` 이 레일과 본문을 `SidebarProvider` 로 함께 감싼다.
- **Tailwind 와 옛 CSS 의 차이 — 다음에도 걸린다**:
  1. `max-[N]` 은 `N 미만`(`not all and (min-width:N)`)으로 컴파일되지만 옛 `@media (max-width:N)` 은 `N 이하`다. 정확히 N 인 화면에서 어긋난다(1100px 에서 종합상황판이 두 칸으로 남고, 900px 에서 햄버거가 안 보인다). `app/tailwind.css` 에 `mobile`(900)·`narrow`(1100)·`phone`(520) 변형을 정의해 썼다.
  2. `[font:inherit]` 같은 `font` 단축 속성을 유틸리티와 함께 쓰면 생성 순서에 따라 `text-[12.5px]` 를 덮는다. 단추 초기화는 `@layer components` 의 `.btn-reset` 으로 옮겼다(유틸리티가 항상 이긴다).
  3. `rounded-full` 은 `calc(infinity * 1px)` 라 옛 `border-radius:50%` 원과 가장자리가 다르게 그려진다. 원은 `rounded-[50%]`.
  4. 옛 CSS 의 전환·애니메이션은 `[transition:…]`·`animate-[…]` 임의 값으로 옮겨야 곡선(ease)까지 같다(`transition-*` 유틸리티는 곡선이 다르다). `board-vflow` 키프레임은 `tailwind.css` 에 있다.
- **옛 CSS 가 먹지 않던 곳은 옮기지 않았다**(그래서 겉모습이 같다): 표 밖의 `.na`, 사업 상세의 `.sub`(`.panel .sub` 만 있었다), `.box b` 에 가려진 `.warn`. 옛 `board.css` 의 안 쓰던 규칙(`.brand h1`·`.lockup`·`#quote`·`.pnl .chartwrap .chart`)도 뺐다.
- **옛 CSS 의 우연한 효과 하나는 일부러 남겼다**: 종합상황판 시점 요약 표의 '현재/증감' 칸에 `dash.css` 의 `.dl`(정의 목록 격자: `display:grid`·`margin-top:10px`)이 클래스 이름이 같다는 이유로 걸려 있었다. 픽셀 동일이 우선이라 같은 격자·여백을 그대로 두었다(`Board.tsx` 에 주석). 고치려면 그 칸의 격자와 위 여백을 빼면 된다(겉모습이 달라진다).
- **전역 기본값의 새 자리**: 본문 바탕·글꼴은 대시보드 레이아웃의 `<body>` 클래스, `*{box-sizing:border-box}` 는 `tailwind.css` 의 base 레이어. 지도 레이아웃은 `app.css` 가 그대로 정한다. 지도 래퍼와 옛 지도 마크업의 접점 세 줄(`.shell-map>.app` 등)은 `assets/css/app.css` 끝으로 옮겼다 — 지도가 React 로 옮겨질 때 함께 사라진다.
- **preflight 는 아직 안 켠다.** 지도(`app.css`·`app.js`)가 브라우저 기본값에 기대고 있어, 켜면 지도가 달라진다. 5~7단계에서 지도를 옮긴 뒤 켠다. 그때 `.btn-reset` 은 preflight 의 `button` 규칙으로 대신한다.
- 남은 옛 CSS: `assets/css/app.css`(지도). 삭제된 것: `dash.css`·`board.css`·`shell.css`.
- **Vercel**: 이 빌드(`npm run build`)는 로컬과 같고, 잠금 파일에 Tailwind(`@tailwindcss/oxide`)·`lightningcss` 의 리눅스용 네이티브 패키지가 들어 있다. 실제 배포 확인(미리보기)은 사용자 승인 뒤에 한다.

## 상단 바·라이트 모드 (2026-10-09, 사용자 지시)

- **결정(사용자 선택)**: ① 좌측 사이드바를 없애고 **상단 메뉴 바**로 바꾼다 — 대시보드와 지도 모두. ② **한 줄 텍스트 메뉴**(PC 높이 64px·≤900px 48px, 현재 위치는 아래 밑줄·굵게, ≤900px 은 햄버거 하나로 접혀 아래로 펼침). ③ **라이트 모드가 기본**이고 다크(옛 남색 팔레트)는 상단 바의 토글로 고른다(선택은 `localStorage('theme')` 에 기억, 그리기 전에 `<html class="dark">` 를 켜서 깜빡이지 않는다). ④ 라이트는 **대시보드 먼저** — 지도(`/map`)는 상단 바만 얹고 색은 어두운 채로 둔다(지도 UI 516줄과 V-World 바탕의 라이트 전환은 지도 재작성 단계).
- 이 변경은 겉모습을 **의도적으로** 바꾸므로 '픽셀 동일' 기준은 여기서 끝난다. 기준선은 이 변경 직후의 화면으로 다시 만든다(라이트 기본 + 다크·메뉴 열림 상태 포함).
- **구현**: `components/TopNav.tsx`(메뉴·햄버거·테마 토글, 지도 화면도 같은 헤더). 토큰은 `app/tailwind.css` — `:root` 가 라이트, `.dark` 가 옛 남색 값(그대로). 라이트 주색은 처음 진한 주황(`#C2410C`)이었다가 남색(`#23466D`)으로 바뀌었다. 시험이 라이트 글자색의 대비(4.5:1 이상)와 라이트·다크의 토큰 이름 일치를 검사한다. 차트(단계색 `--st-*`·`--st-*-ink`, 리본 차트 `--rb-*`; 옛 `--s-*` 는 2026-10-09 배색 개선에서 의미 이름으로 바꿈 — `docs/product/화면-배색-개선-계획.md`)는 CSS 변수라 같은 SVG 가 두 테마를 그린다(SVG 속성의 `var()` 는 동작함). 로고는 밝은 바탕용(`assets/img/wave-lockup-onlight.svg`)을 더했다.
- 지도 레이아웃은 세로 flex(위 상단 바, 아래 `.app`)이고 `.app` 은 남은 높이를 채운다(`app.css` 의 `.shell-map .app{…height:auto}`). 삭제: `ShellRail`·`ui/sidebar`·`ui/sheet`·`use-mobile`, 사이드바 토큰.
- **후속(사용자 지시, 같은 날)**: 한때 PC 메뉴를 목적별 4개 그룹(드롭다운 + 하위 탭 줄)으로 묶었으나 "기존처럼 여러 개 보이게" 되돌렸다 — 메뉴 9개를 한 줄로 두고, 메뉴 글자는 16px(901~1100px 은 15px·좁은 여백으로 한 줄에 맞춘다), 로고는 SVG 아이콘 + 글자('Do Hyeon' 글꼴, `lib/shell/fonts.ts`). 종합상황판 맨 아래의 '상세 화면' 링크 줄(지역별·사업·단계별·기관별·데이터 원본·지도)은 상단 메뉴와 위젯 안 링크가 있어 지웠다. 이어서 '시행주체별 진행 현황' 카드를 '전국 17개 시도' 카드로 대체하고(월별 실적 흐름 옆 줄), '데이터 흐름' 카드는 지웠다(지시 09.30 은 강조할 패널이 없다). 두 카드 높이를 맞추려 시도 칸을 750px(타일 6열·3줄)로 고정하고 실적 칸이 나머지를 쓴다(1477px 에서 761→620px, 높이 757→523px). 1280px 미만은 위아래로 쌓는다. 시도 카드 아래의 안내 칸(선택한 시도의 사업 수·지연율 문장)도 지웠다. 링크 카드(`cardVariants` 의 `link`: `/projects`·`/agency`·`/area`·`/area/{id}`·`/sources`)는 높이를 절반으로 — 여백·글자를 줄이고, 카드 자체가 링크라 경로 표시 줄(`/area/11290` 등)은 뺐다(124→63px). `/agency` 는 설명이 한 줄에 들어가게 카드 최소 폭을 340px 로(148→64px).
- 남은 일: 지도 화면의 머리 줄(68px)이 상단 바(PC 64px) 아래에 한 겹 더 있다 — 지도를 옮길 때 합칠 수 있다. 클래스 없는 기본 링크는 본문 `<body>` 규칙으로 주색이다.

## 2단계 기록

- `app/tailwind.css`: `@layer theme, base, components, utilities;` + `theme.css`·`utilities.css`만 레이어로 가져온다(**preflight 없음**) + `tw-animate-css` + `shadcn/tailwind.css` + 남색 팔레트를 shadcn 토큰에 연결(`dash.css :root`와 같은 값, 시험이 대조). `<html class="dark">`로 `dark:` 변형을 항상 켠다.
- Tailwind는 `next.config.ts`의 Turbopack 로더(`@tailwindcss/turbopack`)로 연결한다(Next 16.4 `create-next-app`과 같은 방식). 모든 `.css`가 이 로더를 지나므로 Lightning CSS가 기존 CSS의 선언 순서를 바꾸고 글꼴 이름의 따옴표를 뺀다 — 의미는 같고 화면 비교가 같음을 확인했다.
- `shadcn`(CLI)은 하위 패키지에 고위험 취약점 7건이 있어 **개발 의존성**으로 두었다(운영 의존성 감사 0건). 앱이 쓰는 것은 `shadcn/tailwind.css` 한 줄뿐이다. shadcn 4.21의 `cn`은 npm 패키지이고 기본 스타일 `base-nova`는 Base UI 위에 만들어진다.
- 기반 확인용으로 `components/ui/button.tsx`(shadcn `button`)를 추가했다. 3단계에서 `.btn`을 이것으로 바꾼다.
