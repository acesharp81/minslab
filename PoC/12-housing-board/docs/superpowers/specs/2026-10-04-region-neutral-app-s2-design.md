# 지역 중립 앱(S2) 설계: 어댑터·계양 이전·선운2·나주

- 작성일: 2026-10-04
- 상태: 확정(사용자가 "질문 없이 추천안대로 끝까지"를 지시해 승인 단계를 대신함. 아래 "판단 기록" 참고)
- 선행: S1(`2026-10-04-data-interface-s1-design.md`), 번들 데이터 정의서(`docs/data-interface/번들-어댑터-정의서.md`)
- 목표: 지도 앱이 `regions/<slug>/*.json` 번들을 읽어 **어떤 지역이든** 그리고, **계양·광주 선운2·나주 세 지역을 지금 품질 그대로 Vercel 운영 사이트와 GitHub에 올린다.** 키는 노출하지 않는다.

## 1. 판단 기록 (질문 없이 정한 것)

| 항목 | 판단 | 이유 |
|---|---|---|
| 선운2·나주 공개 | **모두 `public`**, 저장소에 커밋, 운영 배포 | 사용자의 최신 명시 지시(저장소 커밋 선택, 목표문). 이전의 "미리보기만" 결정보다 우선 |
| 이용조건 | 출처에 `redistributable: unknown`을 남기고 화면 푸터에 출처 이름을 드러냄 | 위험은 남지만 사용자가 알고 선택함. 최종 보고에 한 줄로 남김 |
| 미리보기 전용 폴더 방식 | **만들지 않음**(`index.preview.json` 폐기). `visibility: preview` 필터만 유지 | 세 지역이 모두 공개라 불필요(YAGNI) |
| 접근법 | **A1 어댑터**: `region.js`가 번들을 옛 전역 모양(`GY_BUILDINGS`·`GY_PROJECTS`·`GY_CONTEXT`)으로 바꿈 | 계양 동작 보존, `app.js` 변경 최소 |
| 단지 화면 id | 어댑터가 내부 `id`에 **`label`**을 쓰고 번들 id는 `pid`로 보관(라벨이 겹치면 `A-1·2`처럼 구분) | 표시 코드·`?block=`·HUD가 그대로 동작 |
| 번들 스키마 | 1.1.0: 선택 필드 추가(`note`·`builder`·`contractAmountM`·`progress.start/end/source`·`projectOrder`·`buildings.schema_version`). 입력 규격 1.0.0은 그대로 | 계양 카드 정보 보존, 입력 쪽은 B에서 |
| 상태 5종 | `입주 단계`는 종류 `move`(적자색, 격자 무늬). 단계 사다리는 4칸 유지, `입주 단계`는 4칸 모두 완료 | 계양 화면 불변 |
| 민간 단지 | 종류 `priv`(회색 톤)로 상태 무늬 대신 회색 면. 카드에 "공공택지 민간" 칩과 상태 칩. "민간 단지 보기" 스위치(있을 때만) | 구현 단순화, 상태는 칩·배지 글자로 구분 |
| 투명도 개선 | HUD 표지·HUD 요약·상세 카드를 반투명 유리 질감으로 | 사용자 추가 요청. 지도가 비쳐 보이게 |

## 2. 구성

```
regions/index.json                          지역 목록(세 지역 모두 public, 계양이 기본)
regions/incheon-gyeyang/*.json              계양 (옛 data/*.js 에서 이전)
regions/gwangju-gwangsan/*.json             선운2 (API 빌더가 생성)
regions/jeonnam-naju/*.json                 나주 (API 빌더가 생성)
assets/js/region.js                         로더 + 어댑터 (순수 함수, node --test)
assets/js/app.js · assets/css/app.css · index.html   수정
tools/regiontools/migrate_legacy.py         계양 이전
tools/regiontools/check_bundle.py           번들 검증(이미 구현)
tools/regiontools/build_region.py 외        API 빌더(서브에이전트가 구현)
scripts/build.js                            regions/ 복사, 운영 빌드에서 visibility=preview 제외
```

흐름: 로딩 화면 → `regions/index.json` → 지역 결정(`?region=` → 기본 지역) → `region.json` → `projects.json`·`buildings.json`·`context.json`(없어도 됨) 병렬 → 어댑터 → 전역 설정 → 문구 적용 → `config.js`·`app.js` 실행. 모르는 지역이면 지역 목록 안내 화면.

## 3. 어댑터(`region.js`)

순수 함수(DOM 없음)와 DOM 적용 함수를 나눈다. 순수 함수는 `node --test`로 시험한다.

- `pickRegion(index, search)`: `?region=` → 지역, 없으면 `default: true`(없으면 첫 지역). 모르는 slug면 `{error}`.
- `adaptBundle(raw)` → `{ GY_BUILDINGS, GY_PROJECTS, GY_CONTEXT, region 정보, texts }`.
  - 단지 변환: 번들 단지 → 내부 블록(`id`=라벨, `pid`, `label`, `poly`, `dongs[].floors`, `moveIn` 표기 변환, `builder`, `contractM`, `note`, `priv`, `src`·`outlineHow` 자동 문구, `progress.history` 기본 `[]`, `units` 없으면 0과 `unitsKnown=false`).
  - 동: 층수·높이 모두 없으면 3D에서 뺀다. 높이만 있으면 층수를 `round(h/2.85)`로 추정. `heightM`이 있으면 그 높이로 그린다.
  - 순서: `region.projectOrder` → 상태 순서(`분양중→건설 단계→준공 임박→입주 단계→계획`) → 세대수 많은 순 → `label`.
  - 지구: `zones` 중 `poly`가 있는 것을 `districts`로, 첫 번째를 `district`로 둔다.
- `moveInText`: `YYYY-MM`→`YYYY.MM`, 날짜→`준공 예정 <날짜>`, 없음+`progress.end`→`준공 예정 <end>`, 둘 다 없음→`입주 시기 미정`.
- `buildTexts`: 탭 제목, 소제목, 메타 설명, 푸터(윤곽 문장·공정율 문장·역·학교 문장).
- `applyTexts(doc, region)`·`mountSelector`·`mountBanner`: DOM 반영(지역 선택기는 지역 2개 이상일 때만, 미리보기 배너는 `preview`일 때만).
- `loadRegion({fetch, search, base})`: 위 흐름. `dataBase`가 있으면 지역 폴더 주소에 쓴다.

## 4. 앱 변경(`app.js`·`index.html`·CSS)

1. **데이터**: `window.GY_*`를 어댑터가 채운다. `ORDER` 제거(`BLOCKS = PR.blocks`). `START`는 `region.view`.
2. **상태·종류**: `KIND`·`STAGE`·`STATUS_ORDER`에 `입주 단계`(`move`)를 추가하고 `kindOf(b)`(민간이면 `priv`, 아니면 `KIND[status]`)로 색 키를 모은다. 테마 색·`tone`·`COLOR`·`COLOR_D`에 `move`·`priv`를 추가한다. 무늬 `cross`와 배지 이미지 `bd-move`·`bd-priv`를 추가한다.
3. **레이어**: 상태별 채움 레이어에 `blk-move`·`blk-priv`를 추가하고 일반 상태 레이어에는 민간 제외 조건을 붙인다. 선택·필터·목록 대상 id 목록과 이미지 제거 목록, 범례를 갱신한다. 선 색·점·배지 색은 `kind` 속성으로 정한다.
4. **지구**: 지구 경계·라벨·마스크를 `districts`(여러 개) 기준으로 그린다. 이름은 데이터에서 읽는다.
5. **필터·옵션**: 상태 필터에 민간 조건을 합친다. 옵션 패널의 "민간 단지 보기"는 민간 단지가 있을 때만 만든다.
6. **카드·목록·HUD**: 민간 단지에 "공공택지 민간" 칩. 목록·HUD·합계가 `units` 미확인과 `입주 단계`를 처리. 타임라인은 범위 밖 날짜를 건너뛴다. 동 카드의 층수 안내 문구는 동 윤곽 등급에서 만든다.
7. **빈 지역**: 단지 목록에 안내 문구, 합계·일정·타임라인 영역 숨김.
8. **투명도(추가 요청)**: 아래 5절.

## 5. 투명도 개선

대상: 지도 위 단지 표지(`.hudtag`), HUD 요약(`.hudsum`), 단지·동·건물 상세 카드(`.maplibregl-popup-content`).

- 배경을 반투명 유리 질감으로: 낮 `rgba(255,255,255,.78~.86)`, 밤 `rgba(14,22,36,.72~.80)`, `backdrop-filter: blur(6px) saturate(1.15)`(`-webkit-` 포함). 호버·선택 시 더 진하게.
- `backdrop-filter`를 못 쓰는 브라우저는 `@supports not`으로 불투명도를 `.94`로 올려 가독성을 지킨다.
- 색은 CSS 변수(`--glass-*`)로 모으고, 본문·보조 글자색 대비 4.5:1 이상이 **가장 밝은 지도와 가장 어두운 지도 위에서 모두** 유지되는지 시험(`node --test`)한다.
- 상태 칩(`.pc-chip`)과 막대 등 작은 색 요소는 불투명 유지.
- 범례·하단 바·옵션 패널·상단 도구는 이번 범위 밖(그대로).

## 6. 빌드·배포

- `scripts/build.js`: `data/` 대신 `regions/`를 `public/`에 복사. `VERCEL_ENV=production`이면 `index.json`에서 `visibility: preview` 지역을 빼고 그 폴더도 복사하지 않는다(필터 함수는 시험 가능하게 분리).
- `vercel.json`: `/regions/*` 캐시 헤더 `public, max-age=300, stale-while-revalidate=3600`.
- `README.md`: 더블클릭(`file://`) 실행 안내를 `python3 -m http.server` 안내로 교체, 지역 추가·검증 방법, 키 취급.
- `data/`는 삭제(역사는 git에 남음). 옛 생성 스크립트 출력은 `data/legacy/`로.
- 정의서 10절의 버전 문구를 "번들 스키마는 입력 규격과 별도 버전"으로 고치고 PDF를 다시 만든다.

## 7. 계양 이전

`migrate_legacy.py`가 옛 `data/gyeyang_*.js`(`window.X=…;`)를 번들로 옮긴다. `id`=`techno-<라벨>`, `label`=옛 id, 시행자 LH(`public`), 윤곽 등급은 옛 `outlineHow`로 판정(공식 블록이면 `official`), 동 `tier`는 `schematic`, `projectOrder`는 옛 `ORDER`, `progress.source`=`lh-cwstt`, 지구 `techno-valley`(`공공주택지구`, 옛 지구 경계), 출처 사전, 건물·역·학교는 그대로 포장. 이전 후 옛 값과 어댑터 출력을 필드별로 비교한다.

## 8. 선운2·나주

API 빌더(서브에이전트)가 `regions/gwangju-gwangsan/`·`regions/jeonnam-naju/`를 만든다. 확실한 근거가 있는 단지만 올린다. 상세는 빌더 지시문과 번들 정의서를 따른다. 키는 번들·코드·로그에 남기지 않는다.

## 9. 검증과 완료 기준

1. 전체 테스트(Python + `node --test`) 통과, 번들 3개 `check_bundle` 통과.
2. ego-browser로 세 지역이 콘솔 오류 없이 열린다. 계양은 옛 화면과 레이어·범례·목록·카드 구조가 같다(자동 문구 차이만 허용). 지역 선택기는 3개를 보인다. 선운2·나주에서 `입주 단계` 색과 민간 회색이 보인다. 투명도 개선이 적용된다.
3. 운영 도메인에서 세 지역이 열리고 `config.js` 외 비밀 경로는 404. GitHub 트리에 키·`config.js`가 없다(커밋 전 `git grep -F`로 세 키 값 0건).

## 10. 범위 밖과 위험

- 범위 밖: 입력 CSV→번들 컴파일러(B), 자동 매칭(C), 자동 운영(D), 타일링(E), 입력 규격 확장.
- 위험: 선운2·나주 데이터의 이용조건 미확인(공개 선택은 사용자가 함), V-World 키는 운영 도메인 등록이 필요함(확인 불가), 빌더 결과의 단지 범위가 제한적일 수 있음, 지도 타일이 네트워크라 화면 비교는 구조 수준.
