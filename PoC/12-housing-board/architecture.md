# architecture — 프로덕션 기술 요소 (지도 중심)

기준: 프로덕션 `https://housing-board.vercel.app` = 커밋 `a897a95`(2026-10-07 배포). 근거는 저장소 파일. 미배포 항목은 맨 아래.

## 1. 계층 한눈에

| 계층 | 구성 | 위치 |
|---|---|---|
| 브라우저 | 순수 JavaScript(프레임워크·번들러 없음) + MapLibre GL JS 5.24.0 | `index.html` `assets/` |
| 정적 자료 | 지역 번들 JSON(`regions/<slug>/*.json`) · `config.js`(빌드가 생성) | `regions/` `public/` |
| 서버 함수 | Vercel Functions(Node.js, CommonJS) 7개: 중계·캐시·키 보관 | `api/` `lib/` |
| 외부 서비스 | V-World · 공공데이터포털 · 교육재정알리미 · OpenStreetMap · AWS Terrain · OpenFreeMap | `resource.md` |
| 만들기·검증(배포 안 함) | Python 표준 라이브러리 번들 빌더 · Node 스크립트 · JSON Schema · OpenAPI | `tools/` `scripts/` `schemas/` |

```
브라우저 ──정적──► Vercel CDN (index.html · assets/ · regions/ · config.js)
        ──/api/*──► Vercel Functions(icn1) ──► 공공데이터포털 · V-World · 교육재정알리미 · Overpass
        ──타일────► V-World WMTS · AWS Terrain · OpenFreeMap  (브라우저가 직접 호출)
```

## 2. 호스팅·배포

| 항목 | 내용 | 근거 |
|---|---|---|
| 호스팅 | Vercel (`framework: null`, 정적 출력 `public/` + `api/` 함수) | `vercel.json` |
| 함수 지역 | 서울 `icn1` (기본 지역 미국 `iad1`에서는 V-World 호출이 `fetch failed`로 실패) | `vercel.json` · `dataset.md` 2.15 |
| 런타임 | Node.js(Vercel 기본, 버전 저장소에 미지정), CommonJS, 내장 `fetch` · `AbortSignal.timeout` | `api/*.js` |
| 의존성 | **npm 의존성 0** (`package.json` 없음, 내장 모듈 `fs` `path` `os` `http` `crypto`만 사용) | `lib/` `api/` `scripts/` |
| 빌드 | `node scripts/build.js`: `index.html` + `assets/` + `regions/`(색인에 오른 지역)만 `public/`로 복사, `config.js` 생성. 운영 빌드(`VERCEL_ENV=production`)는 `visibility: preview` 지역 제외 | `scripts/build.js` |
| 배포 제외 | `data/raw/` `data/processed/` `data/tools/` `videos/` `tools/` `tests/` `docs/` `schemas/` `*.md` `.env*` `config.js` `.cache/` | `.vercelignore` |
| 배포 방법 | `git archive HEAD` 사본에서 `vercel --prod --yes` (로컬 `.env.local`·`config.js`가 올라가지 않게) | `dataset.md` · 운영 절차 |
| 함수 제한 | `maxDuration` 20초(`bus` `resolve` `codes/search` `notices`) · 30초(`buildings` `permits` `infra`), 함수마다 필요한 `regions/` 파일만 포함 | `vercel.json` |
| 환경변수(비밀) | `DATA_GO_KR_KEY` · `DATA_GO_KR_KEY_<용도>_<N>` · `VWORLD_KEY`(운영키) · `VWORLD_DOMAIN`(`housing-board.vercel.app`) | `lib/keys.js` `lib/vworld.js` |
| 환경변수(상한, 비밀 아님) | `BUILDINGS_UPSTREAM_PER_HOUR`=1200 · `PERMITS_UPSTREAM_PER_HOUR`=2000 · `LEDGER_UPSTREAM_PER_HOUR`=1500 · `INFRA_UPSTREAM_PER_HOUR`=600 · `SEARCH_UPSTREAM_PER_HOUR`=600 (`SEOUL_UPSTREAM_PER_HOUR` 기본 120) | `dataset.md` · `env.example` |
| 브라우저로 나가는 키 | **V-World 배경 지도 키 하나**(`window.VWORLD_KEY`, 등록 도메인에서만 통과). 공공데이터포털 키는 서버 함수에만 있음 | `scripts/build.js` · `lib/vworld.js` |
| 로컬 실행 | `./run-app.sh` → `scripts/dev.js`(정적 파일 + `api/` 함수 그대로, 127.0.0.1만, `.env.local` 사용) | `scripts/dev.js` |

## 3. HTTP 헤더·캐시

| 대상 | 헤더 | 근거 |
|---|---|---|
| `/assets/vendor/*` | `Cache-Control: public, max-age=31536000, immutable` | `vercel.json` |
| `/regions/*` | `public, max-age=300, stale-while-revalidate=3600` | `vercel.json` |
| 모든 경로 | `X-Content-Type-Options: nosniff` · `Referrer-Policy: strict-origin-when-cross-origin` · `X-Frame-Options: DENY` · `Content-Security-Policy: frame-ancestors 'none'` | `vercel.json` |
| `/api/v1/buildings` · `infra` | CDN `s-maxage=86400, stale-while-revalidate=86400` | `api/v1/*.js` |
| `/api/v1/notices` | CDN `s-maxage=3600, stale-while-revalidate=3600` | `api/v1/notices.js` |
| `/api/v1/resolve` | CDN `s-maxage=300` | `dataset.md` 2.15 |
| `/api/v1/codes/search` | CDN 1시간 | `dataset.md` 2.19 |
| `/api/bus` | CDN `s-maxage` = 서버 `ttl`(≥60초) | `dataset.md` 2.14 |
| 오류 응답 | 5xx · 429는 `no-store`, 그 밖 `s-maxage=60`, 본문 `application/problem+json`(RFC 7807) | `api/v1/*.js` |

## 4. 브라우저 구성

| 파일 | 크기 | 역할 | 시험 |
|---|---|---|---|
| `index.html` | — | 뼈대, `preconnect`(V-World · AWS · OpenFreeMap), MapLibre 스크립트 `preload`, 접근성 속성(`role` `aria-*` `aria-live`) | — |
| `assets/js/app.js` | 약 1,750줄 | 지도 생성·레이어·3D 표현·클릭·팝업·사이드바·HUD·옵션·요청 시 건물 조회(`DYN`) | `ghost` `dynbuildings` `sidebar` `topbar` `glass` |
| `assets/js/region.js` | 464줄 | 번들 → 화면용 전역(`GY_BUILDINGS` `GY_PROJECTS` `GY_CONTEXT` `GY_INFRA`) 어댑터, 번들 없는 지역용 빈 번들(`emptyBundle`), 서버 API 호출 | `region` |
| `assets/js/infra.js` | 274줄 | 입주 전 점검(교육·교통·전기) 판정, 거리·년월 문구 | `infra` |
| `assets/js/facility.js` | 63줄 | 기존 건물에서 학교·병원·공공 시설 분류(이름 키워드 → 용도) | `facility` |
| `assets/js/bus.js` | 167줄 | 버스 노선·위치 순수 함수, 3D 버스 모형 정의 | `bus` |
| `assets/js/goto.js` | 302줄 | 주소 이동 입력줄(상태 4종, 후보 목록) | `goto` |
| `assets/css/app.css` | 약 41 KB | 스타일 전부(CSS 변수, 유리 효과) | — |
| `assets/vendor/maplibre-gl/5.24.0/` | — | 지도 엔진, 자체 호스팅 | — |

| 기술 | 내용 |
|---|---|
| 모듈 방식 | 순수 함수 파일은 UMD 형태(`(function(root, factory){…})`)로 브라우저 전역과 Node `require`를 모두 지원 → `node --test`로 DOM 없이 시험 |
| 상태 | 전역 변수 + 주소 매개변수(`?region` `?sgg` `?bjd` `?pnu` `?code` `?at=경도,위도,확대[,기울기,방위]` `?mode` `?priv` `?ctx` `?infra` `?zone` `?bus` `?hud` `?cards` `?ring` `?dyn` `?aa` `?selftest`) |
| 글꼴 | 웹폰트 없음. 시스템 스택 `'Noto Sans KR','Apple SD Gothic Neo','Malgun Gothic',system-ui,sans-serif`, 지도 글자는 `localIdeographFontFamily` |
| UI 효과 | CSS 변수 + `backdrop-filter` 유리 패널(밝은 3단 · 어두운 4단 투명도), `@supports not (backdrop-filter)`이면 거의 불투명으로 대체 |
| 접근성 | `role` `aria-label` · 스크린리더 안내(`#sr` 영역, `say()`) · `prefers-reduced-motion` 시 애니메이션 끔 · 상태색은 Okabe–Ito 계열 + 무늬(사선·점·격자)로 색 외에도 구분 |

## 5. 지도 엔진·배경

| 항목 | 내용 | 근거 |
|---|---|---|
| 엔진 | MapLibre GL JS **5.24.0**(자체 호스팅, WebGL) | `assets/vendor/` |
| 좌표 | WGS84 `[경도, 위도]`, 소수 6자리 | `dataset.md` 2.0 |
| 시작 카메라 | `pitch 52` · `bearing 0` · `maxPitch 80` · `minZoom 11`, 지역 `view` 또는 주소 `?at=` | `app.js` `START` |
| 안티앨리어싱 | 기본 켬(`antialias`), `?aa=0`으로 끔 | `app.js` |
| 배경(기본) | V-World WMTS `white`(래스터 256 px, 최대 확대 18) `https://api.vworld.kr/req/wmts/1.0.0/{KEY}/white/{z}/{y}/{x}.png` | `app.js` `baseStyle` |
| 배경(대체) | V-World 타일이 2번 실패하면 OpenFreeMap `positron`으로 한 번 전환 | `app.js` `map.on('error')` |
| 지명·도로명 글자 | OpenFreeMap 벡터 타일(`ofm` 소스) 6개 레이어를 스타일 JSON 내려받기 없이 코드에 내장해 얹음 | `app.js` `OFM_LABELS` |
| 지형 | `raster-dem`(terrarium, AWS Terrain Tiles, 최대 14단계) → `setTerrain({exaggeration: 1.5})` | `app.js` |
| 음영 | `hillshade`(과장 0.3, 조명 방향 315°, 지도 기준) | `app.js` `hillshade-own` |
| 하늘·안개 | `setSky`(하늘·지평선·안개 색, 혼합 비율) | `app.js` |
| 조명 | `setLight({anchor:'map', position:[1.5, 315, 38], intensity:0.3})` (북서쪽 해) | `app.js` |
| 스타일 재적용 | 스타일이 다시 올라오면(`style.load`) `setupCustom()`이 소스·레이어를 `add`(이미 있으면 건너뜀) | `app.js` |

## 6. 지도 소스·레이어

소스: `geojson`(자료 전부) · `raster-dem` 2(지형·음영) · `vector` 1(`ofm` 글자) · `raster` 1(V-World 배경). 레이어는 첫 `symbol` 레이어 앞에 쌓음.

| 묶음 | 레이어 종류 | 주요 레이어 id | 줌 | 자료 |
|---|---|---|---|---|
| 바닥(맨 아래) | `fill` · `line` | `official-flat` `official-flat-line` | 14 · 15 이상 | 정보 없는 건물 도형 |
| 지구·용지 | `fill` · `line` | `district-mask` `district-line` `other-fill` `other-line` | 13.5 이상(용지) | 지구 경계, 이름 모르는 용지 |
| 단지 블록 | `fill`(무늬·색) · `line` | `blk-sale` `blk-build` `blk-soon` `blk-move` `blk-plan` `blk-priv` `blk-line` `blk-line-plan` | — | 상태 5종 + 공공택지 민간 |
| 동 | `fill-extrusion` · `fill` · `line` | `dong-3d` `dong-ghost` `dong-shadow` `dong-line` | 선 15.6 이상 | 동 윤곽·층수(보기에 따라 높이 변화) |
| 기존 건물(입체) | `fill-extrusion` · `line` | `official-far` `official-3d` `official-roof` `official-shadow` `official-ao` | 12~14 · 14 · 14 · 14.3 · 15 이상 | `buildings.json` + 요청 시 조회 |
| 선택 | `fill-extrusion` · `line` | `sel-3d` `sel-line` `sel-line-halo` | — | 고른 건물·동 |
| 기반시설 | `fill` · `line` · `symbol` | `infra-site-fill` `infra-zone-fill` `infra-school` `infra-stop` `infra-ring-*` `infra-link-*` | 옵션 | 신설 학교·부지·통학구역·정류장 |
| 역·학교 | `circle` · `line` | `ctx-station` `ctx-school` `ctx-ring` | 옵션 | OSM |
| 버스 | `fill-extrusion` · `line` · `symbol` | `bus-3d` `bus-route-line` `bus-lbl` | 3D 13.8 이상 | 노선 `path` + `/api/bus` |
| 단지 표지 | `circle` · `symbol` | `blk-dot` `blk-badge` `blk-label-lo` `dong-label` `fac-label` | 멀리서는 점 | 세대수·이름표 |
| 코드로 연 곳 | `fill` · `line` | `resolved-fill` `resolved-line` `resolved-halo` | — | `/api/v1/resolve` 경계 |

## 7. 3D 표현 기법

| 기법 | 내용 | 근거 |
|---|---|---|
| 건물 입체 | `fill-extrusion`. 벽(`official-3d`, 높이 = `eh` − 0.8 m)과 밝은 지붕 층(`official-roof`, `ROOF_T` 0.8 m)을 따로 그림 | `app.js` |
| 높이 결정 | 공식 높이 → 지상층수 × 층고(지역에서 측정한 중앙값, 없으면 2.85 m) → 없음(`eh=3`). 출처를 `src`에 남김 | `lib/buildings.js` `buildings.py` |
| 색(장식) | 높이 5단 램프(3·12·25·45·70 m) + 용도 색조 + 연식(1990년 전 칙칙하게·2010년 후 산뜻하게) + 동마다 ±4.5% 명도 흔들림. 벽·지붕·흐림용 4색(`c` `cr` `cd` `crd`)을 속성에 미리 계산 | `app.js` `paintBuildings` |
| 멀리서 | 확대 12~14는 10 m 이상 건물만(`official-far`), 14 이상은 전부. 14.3 미만은 단지를 점(세대수만큼 크기)으로 | `app.js` |
| 그림자 | 북서 해 기준 높이 0.6배를 남동쪽으로 늘어뜨린 바닥 판을 `fill-extrusion`(높이 0.06 m)으로, 3 m 이상만, 확대 14.3 이상에서 처음 필요할 때 생성 | `app.js` `officialShadowData` |
| 접지 음영(의사 AO) | 건물 외곽선에 블러한 `line` 레이어 | `app.js` `official-ao` |
| 정보 없는 도형 | 높이·층수가 모두 없는 도형(`정보없음`)은 솟지 않는 연한 평면 + 점선, 그림자·접지 음영 제외 | `app.js` `KNOWN_H` `NO_INFO` |
| 동 3D | 지구 단지의 동을 `fill-extrusion`으로. 보기 4가지(층수 / 공정율 = 지은 만큼 채움 / 입주 시기 / 기반시설)가 `fill-extrusion-height` 식을 바꿈 | `app.js` `applyMode` |
| 3D 버스 | 12개 `fill-extrusion` 조각(차체·창·앞 유리·지붕·앞 표지·범퍼·바퀴·에어컨)을 맞춘 조립 모형 11×2.5×3.2 m. 추가 라이브러리·모델 파일 없음. 방향은 노선 경로로 어림, 새 위치로 1.2초 보간, 확대 17.5 이상에서 실제 크기·멀수록 최대 4배 | `bus.js` `app.js` |
| 상태 무늬 | 캔버스로 만든 8×8 패턴 이미지(사선 · 점 · 격자)를 `fill-pattern`으로 | `app.js` `patternImage` |
| 선택 표시 | 노랑(Okabe–Ito `#F0E442`) 입체 + 흰 후광선 + 검은 선 | `app.js` `SEL_COLOR` |
| 기본 색 | `fill-extrusion-opacity` 1, "기존 건물 흐리게" 옵션은 0.3 | `app.js` `DIM_OPACITY` |

## 8. 상호작용

| 항목 | 내용 | 근거 |
|---|---|---|
| 클릭 우선순위 | 버스 → 동 → 블록 → 점·배지 → 기반시설 → 기존 건물(`queryRenderedFeatures`) | `app.js` `map.on('click')` |
| 팝업 | `maplibregl.Popup`(폭 236 px 유리 카드), 건물 오른쪽 → 왼쪽 → 위 순으로 자리를 찾고 가로 요약·확대 묶음과 겹치면 아래로 비킴 | `app.js` `showCard` |
| HUD | 단지마다 모서리 표시선(레티클)·정보창을 `map.project()`로 화면 좌표에 고정 크기로 그림 | `app.js` HUD |
| 카메라 이동 | `flyTo` · `easeTo` · `fitBounds`, `prefers-reduced-motion`이면 즉시 | `app.js` |
| 나침반 | 지도 방위에 맞춰 바늘 회전 | `app.js` |
| 옵션 | 보일 상태 · 역·학교 · 반경 원 · 기존 건물 흐리게 · 점검 · 표시선 · 정보 카드 · 버스 | `app.js` |
| 주소 이동 | 하단 입력줄 → `/api/v1/codes/search` → `?pnu` `?bjd` `?sgg`로 다시 열기 | `goto.js` |
| 지역 선택 | `regions/index.json` 색인 + 선택기, 코드로 열면 코드가 `?region`보다 우선 | `region.js` |

## 9. 데이터 적재

| 방식 | 내용 | 근거 |
|---|---|---|
| 지역 번들 | `regions/<slug>/{region,projects,buildings,context,infra}.json`을 브라우저가 `fetch`. 계양 건물 약 6 MB가 대부분 | `region.js` |
| 건물 요청 시 조회(`DYN`) | 번들이 없거나 번들 밖: 보이는 0.01° 칸을 `/api/v1/buildings?cell=`로, 확대 14.6 이상·중심에서 가까운 12칸·동시 3개·실패 칸은 30초 뒤 재시도·최대 6만 동, 붙일 때 150 ms 묶음으로 소스 갱신 | `app.js` `DYN` |
| 인허가·기반시설·공고 | `/api/v1/permits` → `/api/v1/infra`(15초까지 대기) · `/api/v1/notices` | `region.js` |
| 버스 위치 | **버튼을 누를 때만** `/api/bus` 1회(자동 갱신 없음), 서버 `ttl` 동안 버튼 비활성 | `app.js` `bus.js` |
| GeoJSON 소스 | 건물 소스 `maxzoom 16`(그 이상은 같은 타일을 확대), 큰 번들은 첫 사용 때 그림자 소스 생성 | `app.js` |
| 폴백 | 서버 함수가 없으면(404·405·503) 해당 기능만 끄고 지도는 계속 | `app.js` `region.js` |

## 10. 서버 함수

| 경로 | 매개변수 | 원천 | 서버 캐시 | 제한 |
|---|---|---|---|---|
| `GET /api/bus` | `region` | TAGO 버스위치정보 | `ttl`초(≥60) | 노선은 번들 `infra.json`의 live 노선만, 하루 8,000건 예산 |
| `GET /api/v1/resolve` | `code` `sgg` `bjd` `pnu` `project` `geometry` | 행정표준코드 + V-World 경계·필지 + 사업 id 레지스트리 | 24시간 | 코드는 하나만, 시도 단위는 422 |
| `GET /api/v1/codes/search` | `q` `limit` `near` | V-World 장소·주소 + 행정표준코드 | 24시간 | 시간당 `SEARCH_UPSTREAM_PER_HOUR`, 표준코드 호출 110 ms 간격 |
| `GET /api/v1/notices` | `sgg` | 마이홈 HWSPR02 + LH 공고문·공급정보 | 1시간 | 키 풀 RESOLVE |
| `GET /api/v1/buildings` | `cell` | V-World `LT_C_BLDGINFO` | 24시간 | 한국 범위 칸만, 칸당 최대 5쪽, 시간당 1,200쪽 |
| `GET /api/v1/permits` | `bjd` | 건축HUB 주택인허가·건축물대장 + V-World 필지 | 24시간 | 필지 호출 시간당 2,000·대장 1,500쪽, 대장은 110 ms 간격·동시 4개 |
| `GET /api/v1/infra` | `bjd` | 교육재정알리미 · TAGO · 서울시 정류소 · OSM | 24시간 | 임의 좌표 불가(인허가 결과의 중심만), TAGO 시간당 600 |

공통: GET·HEAD만(그 밖 405), 허용 목록 밖 쿼리는 400, 오류는 RFC 7807 `problem+json`, 응답·로그에 키·원천 URL·원천 오류 문구 없음.

## 11. 서버 공통 모듈 (`lib/`)

| 모듈 | 역할 |
|---|---|
| `keys.js` | 공공데이터포털 키 풀: 용도별(`BUILD` `RESOLVE` `BUS` `DEMO`) 여러 키, 서비스별 일일 한도, 오늘 가장 적게 쓴 키 선택, 한도 오류를 받은 키는 한국시간 자정까지 건너뜀, 초당 한도(429 `…PER_SECOND…`)는 하루 소진으로 보지 않음 |
| `cache.js` | 메모리 + 파일 캐시(TTL 최대 24시간, 총량 50 MB 초과 시 오래된 것부터 삭제, 같은 키 동시 요청은 한 번만 가져옴, 키는 해시) |
| `datagokr.js` | 포털 JSON 한 쪽 조회: 5xx·빈 본문·`resultCode 99` 재시도(점점 길게), 한도 오류 구분, 16자리 이상 관리번호(`mgm…Pk`)를 문자열로 보호(JSON 정밀도 손실 방지) |
| `vworld.js` | 키·`domain` 선택(Vercel은 운영키, 로컬은 개발키), 오류 문구에서 키 가림 |
| `buildings.js` | V-World 건물 → 번들과 같은 속성(높이 규칙·좌표 정리·칸 소속) |
| `permits.js` · `projects.js` | 인허가 → 번지 단위 사업, 상태 계산, 건물대장 대조(세대수·대지면적) |
| `infra.js` · `seoul.js` | 신설 학교·정류소 변환, 서울시 정류소·OSM 보조 |
| `stan.js` · `codes.js` · `coverage.js` | 행정표준코드 조회·부분 일치, 코드 판별(5·8·10·19자리), 번들 보유 시군구 |
| `myhome.js` · `lhnotice.js` | 마이홈·LH 공고 변환, 시군구 거르기 |
| `geom.js` · `registry.js` | 경계 단순화, 사업 id 레지스트리(`registry/projects.json`) 조회 |

## 12. 운영 안전장치

| 항목 | 내용 |
|---|---|
| 열린 중계 방지 | 노선·도시·좌표를 요청이 정하지 못하게 함, 칸 번호는 한국 범위 정수만, 인스턴스별 시간당 원천 호출 상한 |
| 키 보호 | 키는 환경변수·`.env.local`에만, 로그·캐시·응답에 없음(`redact`), 브라우저에는 V-World 배경 키만 |
| 한도 대응 | 키 풀·간격 두기·재시도·24시간 캐시·CDN, 초당 한도와 일일 한도 구분 |
| 프레임 차단 | `X-Frame-Options: DENY` + `frame-ancestors 'none'` (iframe 삽입 금지 시험 있음) |
| 부분 실패 | 한쪽 원천 실패 시 나머지를 주고 `meta`에 알림, 불완전한 응답은 캐시하지 않음 |
| 미리보기 지역 | 운영 빌드는 `visibility: preview` 지역을 번들·색인에서 제외 |

## 13. 자료 규격·계약

| 항목 | 내용 | 위치 |
|---|---|---|
| 번들 스키마 | JSON Schema 2020-12 6종(`index` `region` `projects` `buildings` `context` `infra`), 버전 1.1.0 | `schemas/bundle/` |
| 번들 검증 | 스키마 + 교차 규칙(출처 id, 단지 id 중복, 기본 지역 하나, 폴더 = slug) | `tools/regiontools/check_bundle.py` |
| 서버 API 계약 | OpenAPI 3.1 정본 → 사람이 읽는 정의서 자동 생성(`--check`로 최신 여부 확인) | `schemas/api/openapi.json` `scripts/gen-api-docs.js` |
| 계약 시험 | `tests/fixtures/api/`의 운영 응답 파일(24개)을 스키마에 통과시킴 | `tests/fixtures/api/` `tests/js/contract.test.cjs` |
| 입력 규격 | 팀원이 보내는 CSV 입력 규격과 검증기 | `schemas/input.spec.json` `tools/datacheck/` |
| 사업 id | `PRJ-{시군구5}-{일련4}`를 저장소 레지스트리에 발급(서버리스에 공유 쓰기 저장소가 없어 요청 시 발급 없음) | `registry/projects.json` `scripts/issue-projects.js` |

## 14. 만들기·수집 도구 (배포 안 함)

| 도구 | 기술 | 역할 |
|---|---|---|
| `tools/regiontools/build_region.py` | Python 표준 라이브러리 | 광산구·나주 번들을 API로 자동 생성 |
| `tools/regiontools/build_infra.py` | 〃 | 계양 `infra.json` 조립(알리미·학구도·UPIS·TAGO) |
| `tools/regiontools/migrate_legacy.py` | 〃 | 옛 계양 자료 → 번들 |
| `tools/regiontools/proj.py` · `shp.py` | 직접 구현 | EPSG:5186 TM 투영 변환 · SHP/DBF(CP949) 읽기 |
| `tools/regiontools/api.py` | `urllib` | 키 로드, 재시도, 캐시, 키 가림 |
| `tools/build_docs_pdf.py` | `markdown` + 헤드리스 Chrome | 정의서 PDF 생성 (개발 전용) |
| `scripts/smoke.js` | Node | 전국 표본 59곳이 번들 없이 끝까지 열리는지 점검 |
| `scripts/capture-fixtures.js` | Node | 운영 응답을 계약 시험의 기준 파일로 저장 |

## 15. 시험

| 종류 | 도구 | 규모 | 내용 |
|---|---|---|---|
| Node | `node --test "tests/js/*.test.cjs"` | 파일 33개 | 순수 함수, 핸들러, 계약, 화면 코드 정적 점검(레이어·필터·카드 문구), 빌드·헤더 설정 |
| Python | `python -m unittest discover -s tests` | 파일 23개 | 번들 빌더, 투영, 스키마, 상태 계산, 문서·정의서 최신 여부 |
| 운영 점검 | `scripts/smoke.js` | 표본 59곳 | 해석 · 건물 · 인허가 · 기반시설 · 응답 시간 |
| 화면 확인 | 헤드리스 브라우저 | 수동 | `?selftest`로 상태 노출(`window.__mapStatus`) |

## 16. 프로덕션에 아직 반영되지 않은 것 (작업 트리, 미커밋)

| 항목 | 내용 |
|---|---|
| 철거 의심 `g` | 신도시 지구 안에서 도로명주소 건물(`LT_C_SPBD`)과 겹치지 않는 옛 건물을 평면으로 그림. `tools/regiontools/existence.py` · `flag_existence.py`, 번들 스키마 `g`, 나주 번들 1,424동 |
| 저배율 층 필터 | `official-far`에도 평면 도형 제외 필터 추가 |
| 기록 | `resource.md` · `architecture.md` |
