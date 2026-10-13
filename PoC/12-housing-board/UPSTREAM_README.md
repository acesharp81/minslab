# 주택파동 공급 지도

공공주택 공급 현황을, 국토교통부 GIS건물통합정보(V-World) 공식 건물 위에 3차원으로 보여 주는 지도입니다. 지역마다 자료 묶음(번들)만 바꿔 끼우면 같은 화면으로 다른 지역을 보여 줍니다.

지금 올라 있는 지역: **인천 계양구**(계양 테크노밸리, 기본) · **광주 광산구**(선운2지구) · **전남 나주시**(빛가람 혁신도시).

**번들이 없는 지역도 지도가 열립니다.** 번들(위 세 지역)이 있으면 단지·동·점검을 모두 보이고, 없으면 시군구·법정동·필지 코드나 주소 이동 입력줄로 열어 경계를 강조하고 기존 건물 3D·건축HUB 인허가 사업(번지 단위 단지)·신설예정 학교·버스 정류장·공공 모집 공고를 **요청 시에** 서버에서 받아 그립니다(`/api/v1/*`). 전국 표본 59곳으로 점검합니다(`scripts/smoke.js`).

데이터(번들 구조·수집한 원천·가공 과정)는 이 파일에 두지 않고 **[dataset.md](dataset.md)** 에, 서버 API의 요청·응답 규격은 **[docs/data-interface/API-정의서.md](docs/data-interface/API-정의서.md)**(정본 `schemas/api/openapi.json`)에 모았습니다.

## 실행

지역 자료(`regions/*.json`)를 `fetch`로 읽으므로 **더블클릭(`file://`)으로는 열리지 않고, 서버가 필요합니다.**

**상황판(상단 메뉴 바·상세 화면)과 지도(`/map`)는 Next.js 앱입니다**(설계 `docs/product/상황판-셸-설계.md`). `.env.local` 의 키는 서버 함수(`/api/*`)가 읽습니다.

```
npm install                      # 처음 한 번
npm run dev                      # http://localhost:3000/ — 종합상황판(/) · 상세 · 지도(/map). 옛 주소 /?region=… 는 /map?… 로 넘어갑니다
npm run build && npm start       # 운영과 같은 빌드로 확인(포트 3000, -- -p 3100 처럼 바꿀 수 있음)
```

`./run-app.sh` 는 `npm run dev` 를 `127.0.0.1` 에 켜고 브라우저로 첫 화면을 열어 주는 도우미입니다(포트 기본 8000, 서버가 준비되면 엽니다). 코드를 주면 그 코드의 지도(`/map?…`)를, 주지 않으면 종합상황판(`/`)을 엽니다.

```
./run-app.sh                     # 이 폴더에서. 종합상황판(/)을 엽니다(포트 기본 8000)
./run-app.sh 8001 4145011100     # 포트와 코드: 시군구 5·법정동 8/10·필지 19자리(?sgg= ?bjd= ?pnu=), 또는 region:incheon-gyeyang → 그 코드의 지도(/map?…)
```

이전 개발 서버(`node scripts/dev.js 8000` — 루트 `index.html` 을 `/` 에 여는 지도 전용, 상단 메뉴 바·상세 화면 없음)는 지도를 React 로 옮길 때까지 남겨 둡니다.

- **버스 위치(3D 버스)는 인천 계양구에서만** 나옵니다(`?region=incheon-gyeyang`, 기본 지역). 확대 14 이상에서 노선 선을 따라 움직이는 3D 버스 모형과 노선 번호가 보입니다(확대 17.5 이상에서 실제 크기).
- `.env.local`에 공공데이터포털 인증키가 있어야 위치를 받아옵니다(`DATA_GO_KR_KEY_BUS_1` 처럼 용도별 여러 개, 또는 `DATA_GO_KR_KEY` 하나). 없으면 지도는 노선 선만 보여 줍니다. 키 이름·용도·한도는 `env.example`을 보세요.
- **버스 위치는 `버스 위치 조회` 버튼을 누를 때만 한 번 조회합니다**(자동 갱신 없음). 누른 뒤 서버 `ttl`(기본 60초) 동안은 다시 누를 수 없고, 같은 시간 동안 서버도 응답을 재사용합니다.
- 버스가 어디 있는지 모르겠으면 **옵션 → `가장 가까운 버스 보기`** 를 누르세요(버스가 움직이므로 고정 위치가 없습니다). 시작 위치는 주소 `?at=경도,위도,확대[,기울기,방위]`로 정할 수 있습니다(예: `?region=incheon-gyeyang&at=126.7573,37.5588,17.2,58,25`).
- `python3 -m http.server 8000` 같은 정적 서버로도 지도는 열리지만 **버스 위치 함수가 없어(404) 노선 선만 보입니다.** 이때 하단 범례에 `버스 선만`, 옵션에 `위치 서버 없음`이 뜹니다.

- 화면에 `지역 자료를 불러오지 못했습니다. regions/index.json: Failed to fetch`가 뜨면 `file://`로 열었거나 서버가 꺼져 있는 것입니다. 서버를 켜고 `http://localhost:포트/`로 여세요.
- 인터넷이 필요합니다: 배경지도(V-World), 지형 고도(AWS), 지명 글자(OpenFreeMap)를 내려받습니다.
- V-World 배경을 쓰려면 `config.js`에 인증키를 넣습니다(`config.example.js` 참고). 비어 있으면 OpenFreeMap 어두운 지도로 대신 나옵니다.
- 지도 아래 가운데의 입력줄(`/` 키로 바로)에 장소 이름(`하남시청`, 지금 보는 곳 근처 먼저)·동 이름·지번(`장위동 68-37`)·도로명·법정동 코드(8·10자리)·PNU(19자리)를 치면 그곳으로 지도를 다시 엽니다. 투명도로 상태를 말합니다(대기 .78 · 입력 중 .94 · 비활성 .62). 서버(`node scripts/dev.js`·Vercel)가 없으면 비활성으로 보입니다.
- 지역이 둘 이상이면 지역 선택기가 보입니다(머리 줄 로고 옆, 사이드바가 접혀 있을 때는 지도 오른쪽 위 요약 카드 왼쪽 위). 지역 목록에 없는 `?region=` 값은 안내 화면이 뜹니다.
- **지도는 팝업(`window.open`)이나 새 탭으로 여세요. `<iframe>`에는 넣을 수 없습니다**(응답 헤더 `X-Frame-Options: DENY`, `frame-ancestors 'none'`).

주소 매개변수(모두 선택). 화면에서 바꾸면 주소에도 반영되어 링크가 보던 상태를 따라갑니다.

| 매개변수 | 값 | 동작 |
|---|---|---|
| `permits` | `0` | 번들 없는 법정동·필지에서 건축HUB 인허가 사업을 조회하지 않음 |
| `dyn` | `0` · `1` | 건물 요청 시 조회: `0`이면 끔(번들 없는 지역은 경계만), `1`이면 번들 있는 지역에서도 번들 밖 건물을 조회(코드로 열면 기본 켬) |
| `region` | slug | 열 지역(없으면 기본 지역). 지역을 바꾸면 `block`과 코드 매개변수는 지워집니다. 코드가 함께 오면 코드가 우선 |
| `code` `sgg` `bjd` `pnu` | 표준코드(법정동 기준): 시군구 5 · 법정동 8 또는 10 · 필지 PNU 19자리. 둘 이상이면 `pnu` > `bjd` > `sgg` > `code` | 코드를 해석해(`/api/v1/resolve`) 번들이 있는 지역이면 그곳으로 열고 법정동·필지로 이동해 경계를 강조합니다. 번들이 없는 지역(예: 서울·하남)도 지도가 열립니다: 경계를 강조하고 건물은 보이는 칸마다 요청 시 조회해 3D로 그리며, 법정동·필지로 열면 그 법정동의 건축HUB 인허가 사업을 단지로, 그 가까이의 신설예정 학교·버스 정류장을 입주 전 점검으로 보입니다(버스 노선·시행자·분양·통학구역은 번들이 없어 없음. 서울은 TAGO에 정류소 자료가 없음). 예: `?bjd=2824510900`(번들 있음), `?bjd=1129013800`(서울 장위동, 번들 없음) |
| `block` | 단지 `label` 또는 `id`(예 `A6`) | 그 단지 카드를 열고 지도로 이동 |
| `mode` | `progress` `time` `infra` | 보기 기준(기본 층수). `infra`는 점검 자료가 있는 지역만 |
| `panel` | `0` | 데스크톱에서 사이드바를 접은 채 열기(기본은 펼침) |
| `priv` `ctx` `infra` | `0` | 공공택지 민간 단지 · 역·학교 · 입주 전 점검 표시를 끈다 |
| `dim` | `0` | 기존 건물 흐리게를 끈다(모든 기존 건물을 3D 로 채움) |
| `ring` `zone` `hud` `cards` | `1` | 역 반경 원 · 초등 통학구역 경계 · 단지 모서리 표시선 · 단지 정보 카드를 켠다 |
| `aa` | `0` | 안티앨리어싱 끄기(저사양) |
| `selftest` | 아무 값 | 시험용 훅(`window.__map` 등)을 붙인다 |

## 폴더 구조

```
index.html               지도 마크업의 정본: Next.js 가 /map 을 그릴 때 읽고(components/MapIsland.tsx 가 지역 불러오기 → 키 → 앱 순으로 스크립트를 읽음), 이전 개발 서버는 / 에 그대로 엽니다
app/(dashboard)/         상단 메뉴 바 + 종합상황판(/, 시안 이식: SAMPLE 표지 + 실데이터 위젯) · 목록·상세 실데이터 화면(/area /month /projects /project /stage /agency /sources), 준비 중(/reports /my-area)
data/board/              상황판 화면 자료(통계누리 월 계열·LH 준공 예정·원천 카탈로그). tools/boarddata 가 만들어 커밋(dataset.md 2.23)
app/(map)/map/           지도 화면(/map): 루트 레이아웃이 따로라 오갈 때 전체 문서가 새로 열린다(app.js 는 문서당 한 번만 도는 스크립트)
app/api/**/route.ts      /api/* 라우트: handlers/ 의 핸들러를 lib/next-handler.ts 가 Request→Response 로 이어 준다(+ 실행 시간 상한)
components/              TopNav(상단 메뉴 바·라이트/다크 토글) · Crumbs(빵부스러기) · MapIsland(지도 스크립트 로더) · board/(종합상황판 이식) · charts/(서버가 그리는 SVG 차트)
proxy.ts  next.config.ts 옛 지도 주소 리다이렉트 · 보안·캐시 헤더와 함수 번들 규칙
package.json             Next.js 16 · React 19 · TypeScript 5.9 (npm install)
config.js                V-World 인증키 등 설정 (공유 금지) / config.example.js 는 키가 빈 견본
vercel.json  .vercelignore   배포 설정(Next.js · 함수 지역 icn1 · 올라가면 안 되는 파일 제외)
handlers/bus.js               버스 위치 중계(Vercel 함수): 키를 숨기고 TAGO 호출 수를 묶음(요청 시에만, 키 풀·로컬 캐시)
handlers/v1/resolve.js        표준코드 해석 API: 행정표준코드 표 + V-World 경계·필지 + 번들 coverage
handlers/v1/infra.js          기반시설 요청 시 조회 API: 인허가 단지 가까이의 신설예정 학교(교육재정알리미)와 버스 정류장(TAGO)을 번들 infra 와 같은 모양으로
handlers/v1/codes/search.js  이동할 곳 검색 API: 이름·지번·도로명·표준코드 → 법정동·필지 후보(표준코드 이름 검색 + V-World 주소). 주소 이동 입력줄이 부름
handlers/v1/notices.js        공공 모집 공고 API: 마이홈포털 임대·분양 모집공고(전국)를 시군구 이름으로 걸러(번들 없는 지역의 사이드바 "공공 모집 공고")
handlers/v1/permits.js        인허가 사업 요청 시 조회 API: 법정동 하나의 건축HUB 주택인허가를 번지 단위 사업 + 필지 경계로(번들 없는 지역). 건축물대장 총괄표제부로 블록 단위 허가의 위치·합필 지번·준공을 보강
handlers/v1/buildings.js      건물 요청 시 조회 API: 0.01° 칸 단위로 V-World 건물을 번들과 같은 속성으로(번들 없는 지역·번들 밖)
lib/                     서버 공용(프로젝트 루트 root.js · Next 어댑터 next-handler.ts · 메뉴 정의 shell/menu.ts · 키 풀 keys.js · 로컬 캐시 cache.js · 코드 판별 codes.js · 번들 있는 시군구 판별 coverage.js · 건물 변환 buildings.js · 인허가 규칙·건물대장 대조 permits.js · 기반시설·OSM 정류장 변환 infra.js · 마이홈 공고 변환 myhome.js · 공공데이터포털 쪽 조회 datagokr.js · 행정표준코드 stan.js · 경계 단순화 geom.js · V-World 키 vworld.js)
env.example              .env.local 견본(키 이름·용도·한도, 값 없음)
assets/
  css/app.css            화면 모양 (상황판 시안 M3의 네이비 팔레트, 반투명 유리 변수 --glass-*)
  img/                   주택파동 로고(wave-lockup-ondark.svg: 지붕·글자 흰색 + 리본 브랜드 색 #D65535, 어두운 바탕용)
  js/region.js           지역 로더와 어댑터 (순수 함수 + 얇은 DOM 부분)
  js/goto.js             주소 이동 입력줄(하단 커맨드 라인): 상태(대기·입력 중·이동 중·비활성)·후보·이동 주소 모델 + 얇은 DOM 부분
  js/infra.js            입주 전 점검 판정 (순수 함수)
  js/facility.js         기존 건물 시설 분류 (순수 함수)
  js/bus.js              버스 노선·위치 계산 (방향·3D 면·보간·경유 단지, 순수 함수)
  js/app.js              화면 동작 (지도·레이어·HUD·카드·옵션·사이드바)
  vendor/maplibre-gl/    MapLibre GL JS 5.24.0 (자체 호스팅, BSD-3, LICENSE.txt 동봉)
regions/                 지역별 자료 묶음(번들) — 구조는 dataset.md
schemas/                 번들·입력 규격(JSON Schema) · schemas/api/openapi.json(서버 API 계약, OpenAPI 3.1)
tools/                   데이터를 만들고 검증하는 도구 — dataset.md
run-app.sh               로컬 실행(개발 서버 + 브라우저 열기)
dataset.md               지도 데이터 (쓰는 것 · 만드는 절차 · 안 쓰는 것 · 구조 · 수집 출처 · 가공 과정)
docs/                    데이터 인터페이스 정의서(docs/data-interface/: 번들 정의서·어댑터 정의서·**서버 API 정의서**)·설계 문서(docs/superpowers/)·상황판 기획서와 스펙(docs/product/)·정책 근거·발표자료·평가 자료(docs/ 바로 아래 문서, `eval/` `media/` `발표자료_pptx/`)·시안 html(`design/`, 추적하지 않음)
scripts/build.js         Vercel 빌드
scripts/dev.js           로컬 개발 서버(정적 파일 + /api/bus + /api/v1/*)
scripts/smoke.js         전국 표본 점검: 지역 이름 → 코드 → resolve·buildings·permits·infra 를 불러 "번들 없이 열리는가"를 표로(tests/smoke/regions.json 59곳)
scripts/capture-fixtures.js  운영 응답을 tests/fixtures/api/ 에 받아 계약 시험의 기준으로 갱신
scripts/gen-api-docs.js  schemas/api/openapi.json → docs/data-interface/API-정의서.md 생성(--check 로 최신 여부 확인)
tests/                   Python(unittest)·Node(node --test) 시험 · fixtures/api(운영 응답 기준 파일) · smoke(전국 표본)
data/{raw,processed,tools}/  원천 자료·정리본·가공 도구 — 배포하지 않음 (설명: data/README.md). data/board/ 만 배포에 올라감
videos/                  소개 영상 HyperFrames 프로젝트(housing-wave-intro) — 배포하지 않음
```

## 처리 구조

서버는 정적 파일(`index.html` · `assets/` · `regions/`)만 주고, 브라우저가 지역 자료를 읽어 지도를 그립니다. 자료를 만드는 과정과 파일 구조는 [dataset.md](dataset.md), 배포는 아래 "배포"에 있습니다.

```
index.html ─► region.js(RegionLoader.boot) ─► config.js ─► app.js
               지역 자료 읽기 → 화면용 전역으로 변환          MapLibre 지도 · 레이어 · 사이드바 · 카드 · 옵션
```

### 브라우저 안의 순서

1. **`index.html`** — 첫 화면(불러오는 중 안내)을 먼저 그린 뒤, `maplibre-gl.js` · `region.js` · `infra.js` · `facility.js` · `bus.js`를 병렬로 받아 **받은 순서가 아니라 적힌 순서대로** 실행합니다.
2. **`RegionLoader.boot()`**(`region.js`) — `regions/index.json`에서 주소의 `?region=`으로 지역을 고르고, 그 지역 폴더의 자료를 병렬로 받아 화면이 쓰는 모양으로 바꿔 전역 변수에 넣습니다(파일·필드 구조는 dataset.md). 선택 파일이 없으면 그 기능은 꺼집니다. 제목·푸터 문구를 채우고 지역 선택기와 미리보기 띠를 붙이며, 실패하면 안내 화면(`#fatal`)을 띄우고 멈춥니다.
3. **`config.js`**(없어도 됨)로 V-World 키를 읽은 뒤 **`app.js`**를 불러옵니다.
4. **`app.js`** — 주소 매개변수와 전역 자료로 상태를 만들고, MapLibre 지도를 만들고, 기존 건물을 분류하고, 사이드바(합계·다음 일정·단지 카드·입주 전 점검·타임라인)를 그립니다. 지도 스타일이 올라오면(`style.load`) `setupCustom()`이 자료원과 레이어를 올리고 `applyAll()`이 보기·필터·옵션을 반영합니다.
5. **상호작용** — 단지 카드·지도 클릭·타임라인·옵션·상단 버튼이 상태 변수를 바꾸고 `apply*()` 함수가 레이어를 다시 칠하며, `syncUrl()`이 `history.replaceState`로 주소에 반영합니다. 지역을 바꾸면 `?region=`을 바꿔 페이지를 새로 불러옵니다(지도 안에서 갈아끼우지 않음).

화면 구성과 담당 코드:

| 화면 | 위치 | 비고 |
|---|---|---|
| 머리 줄 | 맨 위(`#mhead`) | 주택파동 로고·지역 선택 · **6단계 필터**(`#stageF`: 계획·인허가·착공·모집·준공·입주, 눌러 단계별로 켜고 끔. 옵션의 '보일 단지 상태'와 같은 값. 인허가는 대응하는 상태가 없어 비어 있음) · 보기 기준(`#modeSeg`: 층수·공정율·입주 시기·기반시설). 모바일은 두 줄 |
| 사이드바 | 오른쪽(`#panel`) | 요약·다음 일정·단지(펼치면 6단계 위치)·입주 전 점검(기본 접힘)·타임라인·출처 문구. 데스크톱은 기본 펼침(`?panel=0`이면 접음), 모바일(≤900px)은 하단 시트 |
| 지도 위 도구줄 | 지도 왼쪽 위(`.tools`) | 옵션 · 전체/평면/투어 · ◀▶ 돌리기/자동. 한 줄, 좁으면 가로로 밀림 |
| 확대·나침반 | 지도 오른쪽 위(`.rctl`) | +/− 와 나침반(누르면 북쪽 복귀) |
| 가로 요약 | 확대 카드 왼쪽(`#hudSum`) | 사이드바를 접었을 때만. 지역 선택·합계·막대·점검 한 줄·다음 일정 2건 |
| 범례 | 지도 아래(`#botbar`) | 한 줄 + `자세히`로 펼침 |
| 옵션 창 | 상단 `옵션` 아래(`#optPanel`) | 보일 단지 상태·역·학교·반경·기존 건물 흐리게(기본 켬: 학교·병원·공공시설만 3D, 나머지 건물은 채우지 않은 점선 윤곽만, 확대 15 이상에서만 그림)·점검 표시·표시선·정보 카드 |
| 상세 카드 | 지도 위 팝업 | 단지·동·기존 건물·학교·정류장·부지. 요약·확대 카드와 겹치면 아래로 비킴 |

지도에 올리는 자료원과 레이어(이름은 `app.js`의 id):

| 묶음 | 자료원 → 레이어 |
|---|---|
| 배경 | `vworld`(또는 OpenFreeMap) · `dem` → 지형·`hillshade-own` |
| 지구·단지 | `district*` → `district-mask/line/label` · `blocks` → `blk-sale/build/soon/move/plan/priv`·`blk-line*` · `block-pts` → `blk-dot`·`blk-label-lo` · `block-fronts` → `blk-badge`·`blk-badge-top` · `other-blocks` → `other-fill/line` |
| 동 | `dongs` → `dong-3d/ghost/line/shadow` · `dong-labels` → `dong-label` |
| 기존 건물 | `official` → `official-far/3d/roof/ao`·`official-shadow`(높이를 아는 건물만 솟음) · `official-flat`·`official-flat-line`(높이·층수가 모두 없는 도형 `정보없음`과 철거 의심 `g=1`은 솟지 않는 평면 + 점선) · `fac-pts` → `fac-label`(기반시설 이름표) · `sel`(선택) → `sel-3d`·`sel-line*` |
| 역·학교(OSM) | `ctx-st` `ctx-sch` `ctx-ring` → `ctx-*` |
| 입주 전 점검 | `infra-*` → 신설 학교·부지·정류장·전기·통학구역·연결선·반경 |
| 버스 노선·위치 | `bus-routes` `bus-solids` `bus-lbl` → `bus-route-line` `bus-route-label` `bus-3d`(3D 버스) `bus-label`(번호) |

## 시험

```
.venv/bin/python -m unittest discover -s tests       # Python
node --test "tests/js/*.test.cjs"                     # Node (따옴표 필수)
```

| 시험 | 확인하는 것 |
|---|---|
| `tests/js/region.test.cjs` | 어댑터: 지역 고르기·단지 변환·문구·불러오기·표준코드 진입(`boot`) |
| `tests/js/infra.test.cjs` | 입주 전 점검 판정 |
| `tests/js/facility.test.cjs` | 기반시설 분류·이름표·강조색과 지도 연결(실제 계양 자료 회귀 포함) |
| `tests/js/build.test.cjs` | `scripts/build.js`(복사 범위·미리보기 지역 제외) |
| `tests/js/busapi.test.cjs` | `handlers/bus.js`: 호출 수 묶기(ttl, 키 수)·노선 제한·쿼리 거절·실패 처리·키 인코딩·키 교체·한도 소진·키 값이 캐시에 없음 |
| `tests/js/keys.test.cjs` `cache.test.cjs` | `lib/keys.js`(용도별 키 풀·한도·시연 프로파일) · `lib/cache.js`(TTL·50 MB 상한) |
| `tests/js/codes.test.cjs` `resolve.test.cjs` | 코드 판별과 `/api/v1/resolve`(표준코드 표·경계·필지·후퇴·오류·coverage) |
| `tests/js/infra.api.test.cjs` | 기반시설 요청 시 조회: 신설예정 학교·정류소 변환, 인허가 단지 중심에서만 조회, 서울 건너뜀, 한쪽 실패·키 교체·상한 |
| `tests/js/goto.test.cjs` `codessearch.test.cjs` | 주소 이동 입력줄: 상태·후보 행·인식 칩·이동 주소·최근 이동·가짜 DOM 연결·HTML/CSS 구조, 검색 API(이름·지번·도로명·코드·부분 실패·캐시·거절) |
| `tests/js/permits.test.cjs` `permitsapi.test.cjs` | 인허가 사업 요청 시 조회: Python 번들 빌드와의 일치(PNU·상태·짧은 이름)·번지 단위 집계·건물대장 대조 규칙, 인허가 API(쪽 넘김·재시도·키 교체·필지·상한·건물대장으로 블록 위치·합필 복구·준공·초당 한도) |
| `tests/js/buildings.test.cjs` `buildingsapi.test.cjs` `dynbuildings.test.cjs` | 건물 요청 시 조회: Python 건물 변환과의 일치·칸 계산, 건물 API(칸 소속·캐시·시간당 상한), 화면 연결 |
| `tests/js/myhome.test.cjs` `noticesapi.test.cjs` | 마이홈 공고 변환·시군구 거르기·링크 제한, 공고 API(전국 목록 캐시·한쪽 실패·키 교체·오류) |
| `tests/js/contract.test.cjs` | 인터페이스 계약: 문서 온전성·운영 응답 20개가 스키마를 통과·핸들러 오류 모양·매개변수 이름 일치 |
| `tests/js/smoke.test.cjs` | 전국 표본 점검의 판정 함수(경계 윤곽·칸 번호·열림/경고 판정)와 표본 파일 구조 |
| `tests/js/vercelconf.test.cjs` | `next.config.ts`·`vercel.json`·`app/api`: iframe 차단 헤더·함수 번들 파일·실행 시간 상한 |
| `tests/js/board.test.cjs` `boardsample.test.cjs` | 화면 숫자 = 원천 CSV 숫자·시도 합 = 전국·시행주체 합 = 총계·경로 규칙, 시안 계산 이식 = 원본 실행 기준값(`tests/fixtures/board-sample-golden.json`)·SAMPLE/실데이터 표지 |
| `tests/test_boarddata.py` | `tools/boarddata` 규칙·항등식·`data/board` 낡음 검사 |
| `tests/js/shell.test.cjs` | 메뉴·상세 식별자·지도 섬 스크립트 순서·루트 레이아웃 둘·옛 주소 리다이렉트 |
| `tests/js/root.test.cjs` | `lib/root.js`: 번들러가 `__dirname`을 가짜 경로로 바꾸는 문제의 재발 방지 |
| `tests/js/bus.test.cjs` | 버스 계산(방향·3D 면·보간·경유 단지)과 화면 연결(옵션·요청 시에만 조회 약속) |
| `tests/js/glass.test.cjs` `sidebar.test.cjs` `topbar.test.cjs` | 반투명 유리 글자 대비 · 사이드바(글자 13px 이상·기본 펼침·요약) · 머리 줄의 보기 기준·지도 위 도구줄·확대 카드·가로 요약 |

화면의 실제 겹침·높이는 정적 시험이 보지 못하므로, 화면을 고친 뒤에는 `?selftest`로 열어 `window.__map`으로 레이어·위치를 확인합니다. Python 시험(번들을 만드는 도구·검증기)은 [dataset.md](dataset.md)의 "지역을 추가하거나 고칠 때"에 정리했습니다.

서버 API를 고칠 때는 정본 `schemas/api/openapi.json`을 먼저 고치고 문서를 다시 만든 뒤 계약 시험을 돌립니다. 배포한 뒤에는 전국 표본을 점검합니다(호출 사이에 간격을 두므로 약 15분 걸리고, 행정표준코드·건물대장은 초당 한도가 있어 몰아 부르면 막힙니다).

```
node scripts/gen-api-docs.js             # openapi.json → docs/data-interface/API-정의서.md (--check 는 최신 여부만 확인)
node scripts/capture-fixtures.js [주소]  # 운영 응답을 tests/fixtures/api/ 에 받아 계약 시험의 기준을 갱신(키·원천 주소는 응답에 없음)
node scripts/smoke.js [주소] ["하남시 감일동" …]   # 전국 표본 59곳(또는 이름 지정): 이름 → 코드 → resolve·buildings·permits·infra, 열리지 않으면 종료 코드 1
```

## 배포

Vercel은 Next.js 프로젝트로 빌드합니다(`vercel.json`의 `framework: nextjs`·`buildCommand: npm run build`·`outputDirectory: .next`·함수 지역 `icn1`. 프로젝트 설정에 남은 옛 빌드 명령·출력 폴더를 덮어쓰려고 명시합니다). `npm run build`의 `prebuild`가 `scripts/build.js`를 돌려 `assets/`·`regions/`를 `public/`에 모으고 `config.js`를 만든 뒤 `next build`가 화면과 `/api/*` 함수를 만듭니다. 함수(`app/api/**/route.ts`)는 `handlers/`의 핸들러를 가져가고, 함수가 읽는 `regions/`·`registry/` 파일은 `next.config.ts`의 `outputFileTracingIncludes`로 함께 올라가며, 로컬 캐시·큰 번들은 `outputFileTracingExcludes`로 뺍니다. 보안·캐시 헤더도 `next.config.ts`입니다. 운영 빌드(`VERCEL_ENV=production`)는 `visibility: preview` 지역을 뺍니다. `data/raw/`·`data/processed/`·`data/tools/`·`videos/`·`tools/`·`tests/`·`docs/`와 `*.md`는 올라가지 않습니다.

**인증키**: `config.js`와 `.env*`는 저장소에 없습니다(`.gitignore`). Vercel 프로젝트 환경변수 `VWORLD_KEY`(선택: `VWORLD_LAYER`)를 넣으면 빌드가 `public/config.js`를 만들어 줍니다. 환경변수가 없으면 로컬 `config.js`, 그것도 없으면 빈 키(OpenFreeMap 어두운 지도)로 빌드합니다.

```
vercel env add VWORLD_KEY production      # 값은 프롬프트에 붙여넣기
vercel env add VWORLD_KEY preview
vercel --prod
```

**공공데이터포털 키(서버 전용)**: 서울 버스 API(정류소정보조회·버스위치정보조회)와 LH 분양임대공고문·공급정보도 같은 키로 부르며(키마다 활용신청이 따로 필요, 2026-10-06 현재 키는 신청 완료) 서울은 `seoul`, LH 는 `lh` 서비스로 한도를 셉니다. 함수는 `lib/keys.js`의 키 풀로 키를 고릅니다. 이름은 `DATA_GO_KR_KEY_<용도>_<번호>`(용도 `BUS` 버스 위치 · `RESOLVE` 코드 해석 · `BUILD` 번들 제작 · `DEMO` 시연)이고, 같은 용도의 키가 여러 개면 오늘 가장 적게 쓴 키부터 쓰며 한도 오류(`resultCode` 22·HTTP 429)를 받은 키는 한국시간 자정까지 쉽니다. 용도 키가 없으면 `DATA_GO_KR_KEY` 하나를 씁니다. 시연일에는 `DATA_GO_KR_PROFILE=demo`로 `DEMO` 키를 먼저 쓰게 합니다. 값은 `+ / =`가 든 디코딩된 형태 그대로 적고, `NEXT_PUBLIC_` 접두를 붙이지 않습니다(브라우저로 나갑니다). 키가 없으면 함수가 503을 주고 지도는 노선 선만 보입니다. 키마다 TAGO 버스위치정보(15098533)를 **활용신청**해 두어야 합니다(자동승인). 코드 해석에는 행정표준코드(법정동코드) 신청과 `VWORLD_KEY`·`VWORLD_DOMAIN`도 필요합니다. 인허가 사업 조회에는 건축HUB 주택인허가정보(15136560)와 **건축물대장정보(15134735)** 활용신청도 키마다 필요하고(없으면 대장 보강만 빠지고 `meta.ledger.error`로 알림), 건물대장은 초당 약 30건에서 막혀 함수가 호출 간격을 둡니다. 자세한 규칙은 [docs/product/상황판-스펙.md](docs/product/상황판-스펙.md) 6절.

```
vercel env add DATA_GO_KR_KEY_BUS_1 production   # 값은 프롬프트에 붙여넣기(번호를 늘려 가며)
vercel env add DATA_GO_KR_KEY_BUS_1 preview
vercel env add VWORLD_DOMAIN production         # 코드 해석이 V-World 를 서버에서 부를 때 보내는 서비스 도메인
```

**V-World 키(운영키·개발키)**: 키는 발급 때 등록한 서비스 URL과 같은 `domain`을 보내야 통과합니다(아니면 `INCORRECT_KEY`). Vercel에는 운영키 `VWORLD_KEY`와 `VWORLD_DOMAIN=housing-board.vercel.app`을 두고, 로컬 `.env.local`에는 개발키 `VWORLD_DEV_KEY`와 `VWORLD_DOMAIN=localhost`를 둡니다. 로컬 개발 서버·수집 도구는 `VWORLD_DEV_KEY`가 있으면 그것을 쓰고, Vercel 함수는 `VWORLD_KEY`를 씁니다. 함수는 서울(`vercel.json`의 `regions: ["icn1"]`)에서 실행합니다. 미국 지역에서는 V-World 호출이 연결 실패했습니다.

**호출 예산(환경변수, 값은 인스턴스별 시간당 원천 호출 수)**: `BUILDINGS_UPSTREAM_PER_HOUR`(기본 1200) · `PERMITS_UPSTREAM_PER_HOUR`(2000) · `LEDGER_UPSTREAM_PER_HOUR`(1500) · `INFRA_UPSTREAM_PER_HOUR`(600) · `SEARCH_UPSTREAM_PER_HOUR`(600) · `SEOUL_UPSTREAM_PER_HOUR`(120, 서울시 정류소정보조회 — 개발계정 하루 1,000건). 전국 표본 점검에서 이전 값(600)으로는 몇 곳만 열어도 닿아 올렸고, 운영에는 `vercel env`로 production·preview 모두 넣었습니다(견본은 `env.example`). 마이홈 공고(`/api/v1/notices`)에는 키마다 **마이홈포털 공공주택 모집공고(15108420)** 활용신청도 필요합니다. 서울 TAGO 버스정보가 없어 서울 정류장은 OpenStreetMap으로 대신하며, 서울시 버스 API를 쓰려면 서울 열린데이터광장·공공데이터포털에서 사용자가 직접 활용신청해야 합니다(아직 하지 않음).

하루 호출은 (실시간 노선 수) × 86400 ÷ ttl 회로 묶입니다. 응답을 서버 캐시와 CDN이 ttl초(최소 60초) 동안 나눠 쓰기 때문입니다(계양 4개 노선이면 최대 5,760회, 개발계정 한도 10,000회). 노선이 늘면 ttl이 길어지고, BUS 키가 늘면 키 수만큼 짧아집니다. 로컬 캐시는 `.cache/`(gitignore, 최대 24시간·50 MB), Vercel에서는 인스턴스 임시 폴더입니다.

인증키는 결국 브라우저에 그대로 보이므로 환경변수는 '저장소에 안 올리는' 용도일 뿐이고, 실제 보호는 V-World 콘솔의 서비스 URL 제한이 전부입니다. 배포 주소(운영 도메인)를 그곳에 등록해야 배경지도가 뜹니다. 미리보기 배포 주소는 배포마다 바뀌므로 등록하지 않으면 OpenFreeMap 어두운 지도로 나옵니다.

`/regions/*`는 5분 캐시(`max-age=300`)라, 자료를 고쳐 다시 배포해도 최대 5분은 옛 자료가 보일 수 있습니다.

## 운영 최적화 메모

- 첫 화면(불러오는 중 안내)을 먼저 그린 뒤 스크립트를 순서대로 불러옵니다(`index.html`의 로더). 지역 자료는 `fetch`로 병렬로 받습니다.
- 지명·도로명 글자 층 6개의 정의는 `app.js`에 내장해 OpenFreeMap 스타일 JSON을 매번 받지 않습니다. 지도는 11단계 아래로 줄어들지 않습니다.
- 지형 고도는 14단계까지만 받습니다(원자료가 30 m급). 줌 12~14에서는 높이 10 m 이상 건물만 그립니다.
- 시험용 훅(`window.__map` 등)은 주소에 `?selftest`가 있을 때만 붙습니다.
- 오류가 나면 먼저 `?aa=0`(안티앨리어싱 끄기)으로 열어 보세요. 단지 모서리 표시선(`hud`)과 정보 카드(`cards`)는 기본이 꺼져 있습니다.

## 외부 서비스와 출처 표기

| 서비스 | 용도 | 비고 |
|---|---|---|
| V-World WMTS (`api.vworld.kr`) | 배경지도(midnight, 야간) | 인증키 필요, 최대 확대 18 |
| AWS Terrain Tiles (`s3.amazonaws.com/elevation-tiles-prod`) | 지형 고도 | 키 없음. SRTM 등 |
| OpenFreeMap (`tiles.openfreemap.org`) | 지명·도로명 글자, 키가 없을 때 대체 배경 | 키 없음 |
| OpenStreetMap Overpass (`overpass-api.de`·`overpass.kumi.systems`) | TAGO에 없는 지역(서울 등)의 버스 정류장(서버가 24시간 캐시) | 키 없음, ODbL. 공개 서버라 느리거나 꺼질 수 있음(실패해도 지도는 열림) |
| 마이홈포털 공공주택 모집공고(`apis.data.go.kr/1613000/HWSPR02`) | 번들 없는 지역의 사이드바 "공공 모집 공고" | 공공데이터포털 키 필요 |

건물 © 국토교통부 GIS건물통합정보(V-World, CC BY 2.0 KR) · 역·학교와 TAGO 밖 지역의 버스 정류장 © OpenStreetMap contributors(ODbL). 지도 오른쪽 아래 출처 표기와 사이드바 아래쪽 문구가 지역 자료의 출처에서 자동으로 만들어집니다.

## 사업 id 발급 (사업 레지스트리)

상황판이 사업을 가리키는 내부 id(`PRJ-{시군구5}-{일련4}`, 예 `PRJ-41450-0001`)를 `registry/projects.json` 에 발급해 둡니다. 건축HUB 관리번호는 id 가 아니라 `refs` 로만 보관하고, 사업이 있는 필지(PNU)를 `pnus` 로 잇습니다. 요청 시 발급은 없고(서버리스에 공유 쓰기 저장소가 없음) 운영자가 도구를 돌려 발급한 뒤 커밋·배포합니다. 같은 사업은 같은 id 를 받습니다(외부 참조가 하나라도 겹치면 같은 사업).

```bash
node scripts/issue-projects.js --bjd 4145010800 --bjd 4145011400   # 법정동의 건축HUB 인허가 사업(번지 단위, 건물대장 보강)
node scripts/issue-projects.js --region incheon-gyeyang --link-pnu  # 번들 단지: 윤곽 중심의 필지를 V-World 에서 찾아 PNU 를 잇는다
node scripts/issue-projects.js --bjd 4145010800 --dry-run           # 쓰지 않고 발급·갱신·합병만 본다
```

- 지도는 `?project=PRJ-41450-0001` 로 그 사업을 엽니다(필지가 있으면 필지로, 없으면 법정동·시군구 경계로, 번들 단지는 번들을 연 뒤 그 단지를 엶). 단지 카드의 "사업 id" 링크가 이 주소입니다. API: `GET /api/v1/resolve?project=…`, `GET /api/v1/permits` 의 `projectId`.
- 규칙·형식·합병은 `docs/product/상황판-스펙.md` 9.1.1, 데이터 쪽 설명은 `dataset.md` 2.22. 일관성 검사는 `node --test "tests/js/*.test.cjs"`(`registry.test.cjs`)가 저장소 파일에 매번 합니다.

