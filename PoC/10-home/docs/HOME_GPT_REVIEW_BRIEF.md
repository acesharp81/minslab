# HOME 데이터·서비스 개선 계획 검증용 단일 브리프

작성 기준: **2026-10-10**. 이 문서는 외부 GPT가 다른 파일을 열지 않아도 HOME PoC의 목적, 현재 구현, 데이터 저장 구조, 원천, 운영 방식, 결함과 개선 계획을 검토할 수 있도록 작성했다. 아래에서 **[구현]**은 현재 코드·DB에 있는 것, **[제안]**은 아직 구현하지 않은 설계, **[미검증]**은 원천이나 범위의 확인이 필요한 것을 뜻한다. 링크는 등록된 공식 자료의 진입점이며, 링크의 현재 응답·제공 범위를 이번 문서 작성 과정에서 새로 검증한 것은 아니다.

## 1. 검토 요청과 판단 기준

HOME(Housing Operations Monitoring & Execution, 주택정책의 실행·모니터링)은 **서울특별시·경기도**의 정부 주택공급 정책과 실제 사업을 연결해 진행 상황을 공간·시계열로 살피는 PoC 10이다. 서비스 경로는 `minslab.kr/poc/home` 및 `minslab.kr/home`이다. 핵심 질문은 “정책 발표 이후 어떤 프로그램과 실제 사업이 움직였고, 어느 지역·블록에서 계획 대비 공급이 진행·지연됐는가”이다. 지도 자체가 대시보드이며 시도/시군구 집계와 블록/단지 3D 상세, 정책·프로그램·사업 검토, 공급·인구·가구·고용 시계열을 제공한다.

검토 GPT에는 다음 판단을 요청한다. **① HOME의 정책·프로그램·계획/구역·사업·블록 식별 모델이 서로 다른 법적·집행 단위를 혼동하지 않는가, ② 현재 수집 원천으로 목표/예정/실적을 어느 범위까지 입증할 수 있는가, ③ 서울·경기로 넓힐 수집 순서와 커버리지 검증이 현실적인가, ④ 기존 DB·API·관리자 검토 이력을 안전하게 이관할 수 있는가, ⑤ 무엇을 먼저 고쳐야 지도와 시계열의 신뢰도가 가장 빨리 높아지는가.** 실제 행이나 사업별 숫자를 재계산할 필요는 없다. 근거가 불충분한 사항은 단정하지 말고 필요한 검증과 대안을 지적해 달라.

## 2. 사용자가 확정한 요구와 데이터 원칙

- 정책 → 프로그램 → 사업의 연결을 자동으로 **가장 가능성 높은 후보**로 제안하고, 정책–프로그램과 프로그램–사업을 별도로 담당자가 승인·변경·해제한다. 승인 전 `REVIEW`는 탐색용 통계에 포함하지만 확정 귀속이나 공식 성과로 취급하지 않는다.
- 정책 발표연도뿐 아니라 관련 계획·사업의 최초 시행·지정 시점부터 변경·해제·공급 일정을 보존한다. 그래프는 계획과 실제를 분리하고 과거부터 현재, 향후 1~5년을 보여준다. 원천에 없는 연도별 물량은 임의로 실제 계획치처럼 만들지 않는다.
- 지도는 넓은 화면에서 시도·시군구 총량과 누적 목표/달성률을, 확대 시 블록 단위 목표·현재 단계·향후 일정과 기존 주변 건물을 보여준다. 예상 건물의 3D 모양은 **시각적 모형**으로 생성 가능하나 공식 건물 형상·실제 준공 증거로 쓰지 않는다.
- 목표, 공고, 인허가, 착공, 준공, 입주는 다른 지표다. `미확보`, `미연계`, `일정 미정`, `0호`를 구분한다. 인구·가구원수별 가구·고용·주택 재고 및 예정 공급을 비교할 때 시점·단위·지역·집계 범위를 맞춘다.
- 조원들의 데이터셋을 HOME에 합치는 것이 목적이 아니다. `refs/`는 **HOME의 수집 누락과 구조 설계를 검증하는 비교 자료**다. 조장 플랫폼으로의 변환·반출은 HOME 데이터 정체성과 품질이 갖춰진 뒤의 별도 작업이다.

## 3. 현재 서비스와 데이터 흐름 [구현]

FastAPI 백엔드, PostgreSQL/PostGIS, Alembic 마이그레이션, 정적 웹 UI로 구성된다. 부모 서비스의 세션과 서명 헤더로 관리자 쓰기 API를 보호한다. 공개 조회에는 `/poc/home/api/overview`, `/api/map/dashboard`, `/api/projects`, `/api/policy-monitor`, `/api/annual-supply`, `/api/area-context`, `/api/validation`, `/api/sources` 등의 API가 있다. 담당자는 프로그램의 상위 정책, 사업 후보의 프로그램, 사업별 관리자 연도 목표를 수정할 수 있다. 코드상 원천 등록은 `backend/sources.py`, 수집·정규화는 `backend/collectors.py` 및 원천별 모듈, 적재/조회는 `backend/service.py`, 물리 모델은 `backend/db.py`, HTTP는 `backend/app.py`에 있다.

```text
기관 공식 문서·공개 파일·API·지도 응답
  → 등록된 원천 ID와 수집기 → 원본 응답/파일 보관 + URL·SHA-256·파서 버전 manifest
  → (kind, source_id, 원천 객체 키, 정규화 payload)
  → home_batch + home_revision의 원천 객체 판본
  → 사업 후보의 자동 정책·프로그램 REVIEW 연결 / 담당자 조정·감사
  → 지도·차트용 조회 API와 정적 UI
```

기본 자동 수집은 서비스 시작과 설정된 간격(기본 24시간)으로 수행하며 `manual_only` 원천은 제외한다. API 표본과 범위 확대는 관리 기능이나 `python -m scripts.collect --source <source_id>` 및 `--samples`, `--history`, `--expand-building --rounds N`으로 별도 수행한다. 수집 실패는 성공했던 이전 판본을 삭제하지 않으며 실패 배치를 남긴다. **성공 배치가 있다는 사실만으로 전 기간·전 지역·전 페이지를 수집했다는 뜻은 아니다.** 수집 목록과 최근 상태는 `/api/sources`, 검증·누락은 `/api/validation`에서 확인한다.

2026-10-07 공유 스냅샷에는 등록 원천 36개, 자료 유형 23개, 유효 원천 판본 약 85.9만 건, 정책 사업 **후보** 266건이 있었다. 이 숫자는 구조·규모 참고용이며 공급 물량, 완료 사업 수 또는 현재 운영 DB의 실시간 현황이 아니다. 당시 `building_register` 최신 시도는 실패했고 이전 정상 판본을 유지했다. 실제 상태는 새 배치와 원천별 기간/페이지 커버리지를 다시 확인해야 한다.

## 4. 현재 물리 DB 스키마와 키 [구현]

현재 **물리 테이블은 아래 다섯 개**다. `source_registry`는 DB 테이블이 아니라 `backend/sources.py`의 코드 등록 목록이다. `policy`, `goal`, `project`, `permit`, `register` 등은 독립 테이블이 아니라 `home_revision.kind`와 `payload`의 유형이다. 관계는 대부분 **논리적 참조**로, DB 외래 키 제약이 없다.

| 테이블 | PK와 주요 컬럼 | 의미·제약 |
|---|---|---|
| `home_revision` | `id` UUID 문자열 PK; `entity_id` varchar(80); `kind` varchar(30); `source_id` varchar(40); `revision_no` int; `previous_id` UUID 문자열; `payload` JSON; `payload_hash` SHA-256; `batch_id`; `recorded_at`, `superseded_at` UTC; 검색용 `sample_base_date`, `sample_region`, `sample_name`, `sample_source_date`, `sample_event_day` | **원천 객체 판본**. `entity_id`는 한 원천 객체 안에서만 안정적이다. `superseded_at IS NULL`인 판본만 현행이며 그 조건의 `entity_id` 유일 인덱스가 있다. 이전 판본은 삭제하지 않고 대체 시각만 기록한다. |
| `home_batch` | `id` PK; `source_id`; `started_at`, `finished_at`; `status`; `stats` JSON; `error`; `manifest` JSON | 한 원천의 한 수집 시도. manifest는 실제 요청 URL(키 제거), 원본 경로, 파일 해시, 바이트 수, 파서 버전을 기록한다. |
| `home_mapping` | `id` PK; `project_id` varchar(80) UNIQUE; 과거 호환 `policy_id`; `program_id`; `status`; `revision_no`; `basis`; `evidence_url`; `reviewed_at` | **원천별 `kind=project` 후보 → 프로그램** 검토 연결. `project_id`는 정규화된 실제 사업 ID가 아니라 `home_revision.entity_id`이다. |
| `home_program_mapping` | `id` varchar(36) PK; `name`; `seed_policy_id`; 현재 `policy_id`; `status`; `revision_no`; `basis`; `evidence_url`; `reviewed_at`; `created_at` | **프로그램 묶음 → 정책** 검토 연결. ID가 `프로그램명 + 최초 정책 제안(seed_policy_id)`에 의존해 프로그램 정체성과 초기 정책 가설이 결합돼 있다. |
| `home_audit` | `id` PK; `entity_id`; `action`; `before`, `after` JSON; `recorded_at` | 자동 제안·담당자 조정·관리자 목표 변경 등 변경 이력. `entity_id`의 대상 유형은 `action`에 따라 달라진다. |

`home_revision.entity_id = kind`의 앞 세 글자 + `SHA-256(source_id + ':' + 원천 객체 키)` 앞 24자이다. 같은 payload 해시를 재수집하면 판본을 늘리지 않고, 내용이 바뀌면 `previous_id`로 연결한다. `home_revision.id`는 각 판본의 ID로, 정책/계획/실사업의 영구 ID가 아니다. `home_batch.id ← home_revision.batch_id`, `home_revision.entity_id(kind=project) ← home_mapping.project_id`, `home_program_mapping.id ← home_mapping.program_id`가 핵심 논리 관계다. 정책 유효 연결은 `home_program_mapping.policy_id`를 따라야 하며 `home_mapping.policy_id`는 최초 직접 제안의 호환 필드다.

`REVIEW`는 자동 추천/확인 대기, `CONFIRMED`는 담당자 승인, `RELEASED`는 연결 해제다. 자동 수집이 담당자 확정·수정을 덮지 않도록 설계돼 있다. 관리자 목표는 `kind=goal`의 사업 후보별 JSON이며 공식 일정은 여러 원천 payload를 조회 시 조합한다. **별도 `home_policy`, `home_program`, `home_plan`, 정규화 `home_project`, 공식 공급 실적 원장은 현재 없다.** 특히 단일 사업에 대한 LH·SH·허가·공고·대장의 중복/동일성 판정을 물리적으로 보장하지 못한다.

`payload`는 자료 유형별 반정형 JSON이다. 원천 고유 필드와 HOME 정규화 필드를 함께 담으며, 동일 이름의 수량 필드라도 원천·단계에 따라 뜻이 다르다. 아래 목록은 **2026-10-07 추출본에서 관측한 23개 `kind`**이며, 앞으로 들어올 모든 필드를 고정한 API 계약은 아니다.

| 자료 범주 | `home_revision.kind` | 대표 payload/연결 의미 |
|---|---|---|
| 정책·사업 | `policy`, `policy_event`, `project`, `project_report`, `document` | 정책에는 `id`, `announced_at`, `target_units`, `target_scope`, `metric`; 사업 후보에는 `name`, `district`/`municipality`, `block`, `planned_units`, `program`, `evidence_url`; 보고서에는 공정 관측·기준일 등이 있을 수 있다. 모든 필드가 매행 필수는 아니다. |
| 공급계획·공고 | `sh_plan`, `sh_project`, `lh_supply`, `lh_movein_plan`, `lh_notice`, `gh_notice`, `notice` | 공급계획·공고·입주 **예정**을 서로 다른 원천 행으로 보존한다. `planned_units`, 모집 호수, 날짜/월의 의미는 해당 원천 정의로 확인한다. |
| 허가·대장·재고 | `permit`, `register`, `lh_stock`, `agency_stock`, `statistic` | 허가 관리번호·법정동·원천 날짜·세대/호수·기존 재고. `register`의 `household_count` 등은 신규 공급 실적이라는 보증이 아니다. |
| 지역 통계 | `area_stat` | `base_date`, 지역, 가구·주택 재고·취업/사업체·가구 추계 등과 정의/원천 테이블 ID. 관측값과 전망값을 같은 계열로 합치지 않는다. |
| 위치·경계 | `location`, `district`, `municipality`, `block_location`, `legal_dong` | 주소 좌표, 공식 행정 경계, 지구 용지, 블록 라벨, 법정동 코드. `geometry` 존재 여부와 `coordinate_basis`/연결 상태를 구분한다. |

`kind=project`의 `payload.id` 또는 `home_revision.entity_id`는 **출처 객체 식별자**이지 기관 간 동일 사업의 증명은 아니다. 정책 연결의 `policy_id`는 `kind=policy` 판본의 `payload.id`와 논리적으로 매칭되며 `UNASSIGNED` sentinel을 허용한다. JSON 공유본에는 자료 유형별 관측 스키마, 필드 출현/결측 카탈로그, 논리 관계 정의가 별도로 있으나 이 문서의 설계 검토에는 위의 물리 테이블·키·의미 구분이 기준이다.

시간은 최소 네 가지로 분리해야 한다: `recorded_at`(HOME 수집/인식 시각), 원천 자료의 기준일, 고시·허가·준공 등의 사건/효력일, 미래 예정일. 과거 고시를 오늘 수집해도 `recorded_at`을 과거로 되돌리지 않는다. `as_of` 조회는 “당시 HOME이 알고 있던 판본”을 재현할 뿐 역사상 그때 존재했던 모든 자료를 뜻하지 않는다. 날짜 정밀도가 연·월·일로 다르면 원천 정밀도를 보존한다.

## 5. 원천 목록과 출처 추적 [구현]

아래 **36개 등록 source ID**는 유지관리자가 어떤 출처에서 무엇을 얻는지 파악하기 위한 목록이다. `기본`은 기본 자동 수집 대상, `수동`은 `manual_only`로 별도 요청해야 하는 원천이다. 공식 진입 URL과 실제 API/파일 요청 URL은 다를 수 있다. **실제 요청 URL·응답 해시는 배치 manifest를 기준으로 검증**한다. 저장된 행의 자료연도 범위는 연속 커버리지나 공식 공급 확정률을 보장하지 않는다.

| 목적 / 등록 source ID | 원천·공식 진입점 | 방식·운영상 의미 |
|---|---|---|
| 정책 발표·정책 연혁: `policy_907`, `policy_129`, `policy_813`, `urban_930`, `policy_history` | [9·7 정책](https://d.nts.go.kr/cheonan/na/ntt/selectNttInfo.do?mi=4611&nttSn=1353601), [1·29](https://www.korea.kr/briefing/policyBriefingView.do?newsId=156742030), [8·13](https://www.korea.kr/briefing/policyBriefingView.do?newsId=156774369), [9·30 후속](https://www.korea.kr/news/policyNewsView.do?newsId=148972807), [기원 이력](https://www.korea.kr/news/policyNewsView.do?newsId=148856563) | 공식 웹문서·첨부 파싱, 기본. 정책 목표의 **수도권**은 인천을 포함할 수 있어 서울+경기 사업 합계와 직접 비교 불가. |
| LH 공고·계획: `lh_sale`, `lh_rent`, `lh_notice` | [LH청약플러스 분양](https://apply.lh.or.kr/lhapply/apply/noti/sp/list.do?sUppAisTpCd=05), [임대](https://apply.lh.or.kr/lhapply/apply/noti/sp/list.do?sUppAisTpCd=06), [공공데이터포털 공고 API](https://www.data.go.kr/data/15058530/openapi.do) | 웹 목록·상세 기본, API는 수동. 공고 수량은 총계획·준공·입주 수량과 다름. |
| LH 공정·과거 공급·재고·위치: `lh_construction`, `lh_history`, `lh_progress`, `lh_reit_progress`, `lh_supply_history`, `lh_movein_history`, `lh_stock`, `lh_block_location` | [LH 건설공사](https://www.lh.or.kr/board.es?mid=a10607030000&bid=0007&act=view&list_no=654682), [블록 공정](https://apply.lh.or.kr/lhapply/land/cwsttList.do), [과거 공급](https://www.lh.or.kr/board.es?act=view&bid=0007&list_no=727605&mid=a10103040000&nPage=1), [입주계획](https://www.lh.or.kr/board.es?act=view&bid=0007&list_no=654827&mid=a10103010000&nPage=1), [단지정보](https://www.data.go.kr/data/15080989/fileData.do), [LH 지도](https://bizmap.lh.or.kr/lhmap.do) | 웹/공개파일/PDF·DOCX/지도 응답, 기본. 공정률은 호수로 환산하지 않으며 블록 라벨 점은 공식 필지 경계가 아니다. |
| SH 계획·재개발·재고: `sh_files`, `sh_supply_plan`, `sh_redevelopment`, `sh_inventory` | [서울 열린데이터광장 OA-12027](https://data.seoul.go.kr/dataList/OA-12027/S/1/datasetView.do), [분양 공급계획](https://www.data.go.kr/data/15008820/fileData.do), [공공재개발·재건축](https://www.data.go.kr/data/15124798/fileData.do) | `sh_files`·파생 inventory는 기본, 포털 계획 2종은 수동. 공개 파일의 날짜·원천 버전 확인 필요. |
| GH 계획·공고·재고: `gh_files`, `gh_supply_plan`, `gh_notice` | [GH 파일](https://www.data.go.kr/data/15112600/fileData.do), [공급계획](https://www.gh.or.kr/gh/housing-stability-in-gyeonggi-do001.do), [공고](https://www.gh.or.kr/gh/housing.do) | 공개 파일·웹; `gh_notice` 수동, 나머지 기본. 경기도 전체 계획 고시 이력을 대체하지 않음. |
| 청약·인허가·대장: `cheongyak`, `building_hub`, `building_register` | [청약홈 API](https://www.data.go.kr/data/15098547/openapi.do), [건축HUB 주택인허가](https://www.data.go.kr/data/15136560/openapi.do), [건축HUB 건축물대장](https://www.data.go.kr/data/15134735/openapi.do) | 인증 API, 수동 확대. 현재 주택인허가는 주로 `getHpBasisOulnInfo`, 대장은 `getBrTitleInfo` 사용. 광범위한 허가·기존 재고는 정책 공급 실적이 아님. |
| 주택·인구·가구·고용: `molit_statistics`, `kosis_housing`, `kosis_household_size`, `kosis_employment`, `kosis_household_forecast`, `sgis_area` | [국토교통 통계누리](https://stat.molit.go.kr/portal/api/info.do), [KOSIS API](https://kosis.kr/openapi/devGuide/devGuide_0201List.do), [KOSIS 가구원수 표](https://kosis.kr/statisticsList/mass/mass_list.jsp?org_id=101&process=statHtml&tbl_id=DT_1JC1516&vw_cd=MT_ZTITLE), [SGIS 인구주택총조사](https://sgis.mods.go.kr/developer/html/newOpenApi/api/dataApi/census.html) | 통계 API. `molit_statistics` 수동, 나머지 기본. 조사/공표 시차, 거주지/사업장 기준, 재고/흐름, 실적/추계 구분 필요. |
| 공간 참조: `legal_dongs`, `vworld`, `vworld_district`, `vworld_municipality` | [행정표준코드](https://www.code.go.kr/stdcode/regCodeL.do), [VWorld 개발자센터](https://www.vworld.kr/v4po_openapi_s001.do) | 법정동 코드는 기본, VWorld 계열은 수동. 시군구 경계·공공주택지구 용지·주소 좌표를 구분. 런타임 기존 건물 도형 조회는 별도 화면 컨텍스트이며 공급 실적 원장이 아니다. |

원천별 인증 **환경변수 이름만** 코드와 `.env.example`에 둔다. 운영 값은 `.env` 등 비공개 설정에 있으며 이 문서와 내보내기 파일에 적지 않는다. 주요 키 이름은 `POC10_CHEONGYAK_SERVICE_KEY`, `POC10_BUILDING_HUB_SERVICE_KEY`, `POC10_BUILDING_REGISTER_SERVICE_KEY`, `POC10_LH_NOTICE_SERVICE_KEY`, `POC10_MOLIT_STAT_API_KEY`, `POC10_SH_SERVICE_KEY`, `POC10_VWORLD_API_KEY`, `POC10_KOSIS_API_KEY`, `POC10_SGIS_CONSUMER_KEY`/`POC10_SGIS_CONSUMER_SECRET`이다. 서울·경기 다른 공개 API 확장용 환경변수는 존재하더라도 **해당 자료의 실제 수집·완전성을 뜻하지 않는다**.

원천 응답은 허용된 공식 호스트만 호출하고, 수집기는 인증 query/응답 반사 키를 제거한 뒤 원본 파일을 `data/raw/<source_id>/...`에 두고 SHA-256·크기·파서 버전을 배치 manifest에 남긴다. 같은 배치의 정규화 레코드는 트랜잭션으로 저장한다. 원천이 바뀌면 새 `home_revision`을 추가하고 기존 유효 판본의 `superseded_at`을 찍는다. 수집 실패/부분 수집 여부, 원천 기준일, 마지막 성공 시점을 함께 살펴야 한다. 2026-10-07 공유본은 `data/exports/home-20261007-snapshot/`이며 `source_registry.json`, `collection_batches.json.gz`, `revisions/{kind}.json.gz`, 관계·스키마·필드 카탈로그, `verify_export.py`가 있다. **원본 응답 본문은 그 공유본에 포함되지 않아**, 바이트 수준 재현은 운영 `data/raw`가 따로 필요하다.

## 6. 현재 화면 지표의 해석 한계 [구현/미검증]

| 화면에서 보이는 항목 | 현재 얻는 근거 | 피해야 할 해석 |
|---|---|---|
| 정책 목표·프로그램·사업 후보 | 공식 발표문, 원천 사업 후보, 자동 REVIEW 연결 | 정책 전체 목표를 서울·경기 후보 합계와 바로 나눠 정책 달성률로 표시하지 않는다. 인천 포함 목표와 범위가 다를 수 있다. |
| 연도별 계획·관리자 목표 | LH/SH/GH 일정, 공고, `kind=goal` JSON, 조회 시 로드맵 조합 | 날짜 없는 사업 물량을 확정된 해당 연도 공식 목표로 균등 배분하지 않는다. 관리자 목표는 공식 계획과 별도 계열이다. |
| 실제 진행 | LH 일부 공개 공정, 공고·허가·대장 날짜 | 공정률을 완료 호수로 바꾸거나 대장 기존 재고를 새 정책 공급으로 합산하지 않는다. 전 사업의 실공정률은 확보되지 않았다. |
| 3D 지도 | VWorld 기존 건물 도형/높이, LH 블록 라벨, 공식 지구/행정 경계, 시각용 예상 건물 | 기존 주변 건물은 공급 사업의 실제 단지·동과 자동 연결되지 않는다. 예상 건물은 가상 형태로 구별해야 한다. |
| 주택 부족/여유 평가 | KOSIS/SGIS 가구·주택 재고·증가/추계와 예정 공급 | `주택 재고 + 예정 공급 - 가구 수`는 단위·공실·멸실·가구 정의·지역 간 이동을 통제하기 전에는 확정 부족량이 아니다. 시나리오/참고 지표로 표시한다. |

## 7. 조원 자료로 확인한 HOME의 구조적 누락

`refs/`의 성북구 사례는 고시 중심 **계획(P-)**, 사업 **(SB-)**, 계획–사업 N:M 링크, 다수의 출처별 사업 기록을 구분한다. 같은 이름을 가진 폐지 계획과 현재 후보 사업을 별도 객체로 두는 사례가 있다. 이 자료는 HOME에 직접 적재하거나 그 ID를 HOME 영구 키로 채택하지 않는다. 교차 비교에서 성북구 건축HUB 기본 인허가와 대장의 원천 기록은 HOME에도 상당 부분 이미 있었으나, 그것을 **동일 사업으로 식별하고 고시·계획 이력과 연결하는 원장**이 부족하다는 점이 드러났다. 즉 원천 행이 많아도 지도·연도별 사업 흐름이 빈 이유는 수집량과 사업 정체성/관계 완성도가 다르기 때문이다.

현재 HOME의 `kind=project`는 출처별 **사업 후보**다. 정책 후보, 사업 후보, 공고, 허가, 대장, 실제 준공/입주가 각각 몇 단계까지 연결됐는지를 별도로 측정해야 한다. 조원 사례의 `upisRebuild` 서울 정비구역 고시 이력, 건축HUB `getHpDongOulnInfo`(동별 공공/민간 구성), `getHpPlatPlcInfo`(필지/PNU), 건축법 `getApBasisOulnInfo`, 서울 정비사업 진행자료·마이홈 PNU는 HOME의 **추가 검증 후보**다. 웹/API의 현재 제공 상태와 이용 범위를 HOME이 직접 재검증해야 한다. 서울 정비구역 자료만으로 공공주택지구·매입임대 등 모든 계획을 덮지 못하고, 성북구 수집기를 단순 확장해 경기도 고시 이력까지 얻을 수 없다. 경기도의 동등한 계획 지정·변경·해제 원천은 **미검증**이다.

## 8. 목표 데이터 모델 [제안]

핵심 구조는 **정책 → 프로그램 → 정규화 사업 → 블록/단지**이다. 이와 별도로 법적·공간적 **계획/구역**을 사건 이력과 함께 원장화하여 사업과 **다대다**로 연결한다. 화면에서는 편의상 `정책 → 프로그램 → 관련 계획/지구 → 사업 → 블록` 트리로 펼칠 수 있지만, DB에서 모든 사업에 하나의 상위 계획을 강제하지 않는다. 계획이 없는 사업은 가상 계획을 만들지 않는다. 정책은 범정부 목표·발표 문서, 프로그램은 실행 유형/관리 묶음, 계획은 구역 지정·변경·해제의 생애주기, 사업은 실제 시행 단위다. 정책 발표 전에 시작된 계획/사업도 있을 수 있고, 폐지 계획과 신규 사업은 이름이 같더라도 별도로 둔다.

```text
home_policy ──< home_policy_program_link >── home_program
                                                 │
                                    home_program_project_link
                                                 │
                                    home_project ──< home_block
                                         │     │
                         home_plan_project_link  └──< home_project_evidence >── home_revision
                                         │
                                    home_plan ──< home_plan_event >── home_revision

home_project/home_block ──< home_milestone, home_supply_measure
모든 주요 객체 ──< home_identity_alias; 수집 범위 ──< home_coverage
```

| 새 원장/관계 | 핵심 필드·제약 제안 | 보존할 의미 |
|---|---|---|
| `home_policy` | `policy_id` 안정 PK, 공식명, 발표/시행 기간, 목표의 범위·단위·원문 근거; 발표/개정 사건은 별도 판본/이력 | 현재 `kind=policy`로만 있는 정책 정체성을 독립화한다. 정책 목표 수정도 과거 발표를 덮지 않는다. |
| `home_program` | `program_id` 안정 PK, 공식/관리명, 정의·적용 범위·기간, 상태 | ID를 최초 `seed_policy_id`에서 분리한다. 이름만 같다고 합치지 않는다. |
| `home_policy_program_link`, `home_program_project_link` | 양쪽 안정 ID, 관계 유효기간, `REVIEW/CONFIRMED/RELEASED`, 근거 원천 판본·URL, 제안 규칙/버전, 담당자·시간, 감사 이력 | 객체의 정체성과 현재 상위 연결을 분리하고 기존 두 단계 검토 UI를 유지한다. |
| `home_plan` | HOME 발급 `PLN_…` 안정 PK, 계획 유형, 관할 코드, 최초 지정·현재 법적 상태, 대표 명칭; 공식 경계는 버전 관리 | 정비구역·공공주택지구 등 **법적/공간적 계획**. 원천 코드·명칭·PNU 하나를 영구 PK로 쓰지 않는다. |
| `home_plan_event` | 사건 PK, `plan_id`, 지정/변경/해제/재지정 유형, 고시번호, 고시일·효력일·수집일 및 날짜 정밀도, `home_revision.id`/URL, 경계 판본 | 원고시·후속 고시의 순서를 보존한다. 해제 뒤 새로운 지정이 같은 법적 계획인지 별도 계획인지는 근거로 판정한다. |
| `home_project` | HOME 발급 `HPR_…` 안정 PK, 실제 시행 단위의 명칭·위치·시행자·유형·공공성 판정, 현재 단계와 근거 | 기관별 후보를 같은 실사업으로 모으되 분할 시행·단계별 물량은 별도 하위 범위로 관리한다. |
| `home_identity_alias`, `home_project_evidence` | 대상 유형·HOME ID ↔ 기관/원천·외부 키 및 유효기간; 사업 ↔ 원천 `entity_id`/판본 ID, 역할, 근거, 매칭 상태·버전 | 허가 관리번호, 대장 PK, 공식 구역코드, 사업코드, 과거 이름, PNU를 교차표로 보관한다. 충돌·거절 이력을 자동 덮어쓰지 않는다. |
| `home_plan_project_link` | 계획/사업 ID, 시행·포함·전신·참고 등 관계 유형, 유효기간, 근거 판본, 검토 상태 | N:M. 폐지된 계획과의 `참고` 관계를 현재 유효 계획이나 정책 성과로 자동 합산하지 않는다. |
| `home_block` | HOME 블록 ID, 소속 사업, 공식 블록코드/단지명, 필지·경계/대표좌표, 공간 근거·확인 상태 | A4/S1처럼 독립 블록을 보존한다. 공식 블록 경계가 없는 대표점과 가상 3D 형상을 혼동하지 않는다. |
| `home_milestone` | 대상 사업/블록, 단계(계획/승인/착공/공고/분양/준공/입주), 예정·실제·추정, 날짜/정밀도, 근거 판본 | 실제 사건과 계획 일정을 별도 시계열로 제공한다. 공개 지연·미확보와 실제 지연은 분리한다. |
| `home_supply_measure` | 대상/지표(정책 목표·계획 총호수·공고·준공·입주·기존 재고 등), 호수/단위, 공간·기간 범위, 공식/관리자/추정, 기준일, 근거 판본 | 같은 사업·단계·기간·범위의 유효 수치만 비교한다. 공정률은 호수로 환산하지 않는다. |
| `home_coverage` | `source_id × 지역 × 기간 × API/자료 유형`, 요청·성공·페이지 완료·원천 행·사업 연결 행, 실패·미조회·원천 없음 사유 | 0건·미수집·실패·지연 공개를 구분한다. 서울·경기 확대의 완료 여부를 수집 건수 아닌 커버리지로 판정한다. |

위 표는 **논리 설계**다. 컬럼 타입·인덱스·FK·유일 제약·법정 상태 코드는 구현 전 별도 마이그레이션으로 확정한다. 새 안정 키는 HOME 내부에서 한 번 발급하고, 조원 `P-`/`SB-` 및 향후 조장 플랫폼 ID는 alias/crosswalk로만 둔다. 원천의 관리번호는 강한 동일성 근거지만 복수 사업/재지정/분할 사례를 검토해야 하며 PNU나 이름만으로 자동 확정하지 않는다.

## 9. 수집·결합·지표 개선 순서 [제안]

| 순서 | 작업 | 완료 판정과 운영상 주의 |
|---|---|---|
| A. 품질 기준선 | 현 원천을 `지역 × 연도 × 자료 유형 × 페이지`로 재점검; 최근 실패·수동 원천·과거 공백을 `home_coverage`로 기록. 원천 행 → 사업 후보 → 정규화 사업 → 정책 귀속 → 확인 실적의 각 연결률을 분리 | “수집 성공”과 “전량 확보”가 다르다는 것을 화면/운영 표에서 확인 가능. 마지막 정상 판본·배치 실패를 동시에 표시. |
| B. 안정 식별·마이그레이션 | `home_project`/alias/evidence와 정책·프로그램 안정 ID를 먼저 만들고 기존 후보 ID→정규화 ID 교차표 생성. 현 `home_mapping`, `home_program_mapping`, `kind=goal`, 감사 이력은 호환 조회로 유지 | 동일 원천 재수집 시 안정 ID 불변. 한 사업으로 묶이는 두 후보의 프로그램·목표가 충돌하면 자동 선택하지 않고 검토함에 보냄. |
| C. 독립 파일럿 | **HOME 자체 원천**으로 성북구 인허가–대장 교집합과 계획 고시 이력을 재수집. 동별/필지별 허가, 건축법 소규모 주택, 서울 정비구역 지정/변경/해제, 사업 단계/필지 자료를 출처·이용조건부터 확인 | 조원 JSON을 가져오지 않고 HOME 추출과 공식 고시로 연결 정확도·중복·법적 연속성을 검증. 성북구 사례는 회귀 검토 예시일 뿐 정답 데이터는 아님. |
| D. 측정 원장·화면 | 목표·관리자 목표·공고·준공·입주·재고를 별도 measure로, 계획/실제 사건을 milestone으로 저장. 지도·정책 트리·시계열에 출처, 검토 상태, 결측, 정책 적용 범위를 표시 | 과거 최초 시행과 최신 실제 사건이 보이고 지표별 분모/분자가 명시됨. 미공개 연도에 확정 수치를 만들어내지 않음. |
| E. 범위 확장 | 서울 다른 구와 다른 계획 유형을 분리해 확대; 경기도는 GH/LH/경기도·시군의 **동등한 고시 이력** 출처를 먼저 탐색·검증 | 서울 정비구역 커버리지가 높아도 경기도/매입임대/공공주택지구를 완료로 표시하지 않음. 지역·유형별 조회 실패·원천 없음·미연계율 확인. |

자동 매칭은 **공식 ID 일치 → 기관·관리번호/필지·경계·시기·사업명 조합 → 텍스트 유사성** 순으로 신뢰도를 낮춘다. 다수 후보나 공공/민간 혼재, 폐지·재지정, 분할 시행, 공고·대장의 공급 범위가 다르면 `REVIEW`를 유지한다. 담당자의 승인·거절·수정은 규칙 버전과 함께 감사에 남기고 새 수집으로 되돌리지 않는다. 과거 정책 시행 이전의 준공을 후속 정책 성과로 소급하지 않는다. 공급 목표/계획/공고/준공/입주·기존 재고는 별도 계열로 보관해 중복 합계를 차단한다.

## 10. 유지관리·반출 관점의 최소 운영 계약

1. **원천 등록과 비밀 관리:** `backend/sources.py`에 기관·진입 URL·원천 ID·수집 모드·키 환경변수 이름을 등록한다. 키 값은 운영 비밀 설정에서만 관리하고 로그·문서·JSON 반출에서 제거한다. 신규 출처는 공식 제공 범위, 이용조건, 페이지 한도, 기준연도, 지역 단위를 먼저 검증한다.
2. **수집 가능성과 복구:** 배치마다 성공/실패, 원본 manifest, 원천 기준일, 페이지 완결성과 누락을 남긴다. 실패 시 이전 성공본 보존, 재시도/체크포인트, 원천 포맷 변경 알림이 필요하다. 현재 manifest와 판본 보존은 구현돼 있으나 지역·기간·엔드포인트별 완결성 원장은 제안 단계다.
3. **원본·정규화·파생물 구분:** `data/raw`의 응답, `home_revision`의 원천별 정규화 payload, 정책/사업/측정 원장, 화면용 집계와 3D 가상 형태를 다른 층으로 관리한다. 역추적은 화면 값 → 안정 객체/지표 → 근거 판본 → 배치 manifest → 공식 요청 URL/원본 해시 순서가 되어야 한다.
4. **품질·수정 책임:** 자동 후보는 검토 사유·근거·규칙 버전을 보여주고 담당자가 승인/해제한다. 운영자는 원천 갱신, 수집 실패, 키 만료, 형식 변경, 식별 충돌, 지역·연도 공백을 감시한다. 확정 연결이나 관리자 목표는 재수집으로 덮지 않는다.
5. **백업·외부 공유:** DB 판본/검토 이력과 원본 파일을 함께 백업해야 출처 증명이 된다. 기존 JSON 추출본의 해시·스키마·관계 파일은 재현에 유용하지만 원본 응답 본문은 별도 보관·제공해야 바이트 검증이 된다. 향후 조장 지도 플랫폼으로 내보내는 형식은 안정 객체와 단위·근거·검토 상태가 정리된 뒤 **어댑터**로 구현한다.

## 11. 검토 GPT가 특히 짚어야 할 미결정 사항

1. `정책→프로그램→사업`과 `계획/구역↔사업` N:M의 구분이 적합한가? **계획을 사업의 필수 상위 계층**으로 두어야 하는 예외가 실제로 있는가?
2. 재지정·합필·분할·사업명 변경·공공/민간 혼합에서 어떤 공식 식별자와 증거 조합을 안정 키·자동 후보 기준으로 삼아야 하는가? 현재 `seed_policy_id` 기반 프로그램 ID를 이관할 때의 충돌 처리와 관리자 결정 보존 방안은 충분한가?
3. 목표·공고·허가·공정·준공·입주·기존 재고를 현재 자료로 어디까지 확인할 수 있으며, 정책 성과의 **공식 분자/분모와 지역·기간 귀속**을 어떻게 정의해야 하는가? 특히 9·7 등 수도권 목표와 HOME 서울·경기 범위 차이를 어떻게 표시할 것인가?
4. 서울 정비구역 외 **서울 다른 계획 유형과 경기도 계획 고시**의 실제 원천/공식 ID는 무엇인지 추가 조사해야 하는가? 성북구 파일럿 후 서울·경기 확대의 API 호출량·시차·운영 비용을 어떻게 검증할 것인가?
5. 원천 행이 많아도 실제 연도별 공급 실적이 부족한 상황에서, 표본 확대와 **사업 동일성·자료 귀속 개선** 중 어느 순서가 효과적인가? 미수집·미연계·원천 미공개·실제 0건을 어떻게 서로 다른 상태로 유지할 것인가?
6. 제안 원장의 컬럼/FK/유일성·판본 방식에 빠진 제약은 무엇이며, 기존 API와 JSON 공유본을 깨지 않고 단계적으로 이전할 수 있는가? 데이터 정확성/운영 비용 기준으로 A~E의 우선순위를 수정해야 하는가?

검토 결과는 **확인된 사실 / 추론 / 추가 확인 필요**를 구분하고, 치명적 결함부터 수정안과 검증 방법을 제시해 달라. 이 문서만으로 확인되지 않는 외부 서비스의 현재 제공 상태나 공급 수치는 사실로 단정하지 말아 달라.

### 저장소 내 확인 위치

필수 열람 자료는 아니지만, 실제 구현 대조가 필요하면 `backend/db.py`, `backend/sources.py`, `backend/service.py`, `backend/collectors.py`, `backend/app.py`, `docs/DATA_SHARING_20261007.md`, `docs/REFS_INTEGRATION_REVIEW.md`, `data/exports/home-20261007-snapshot/`을 볼 수 있다. 조원 비교 자료는 `refs/architecture.md`, `refs/resource.md`, `refs/README.md`, `refs/schema.json`, `refs/seongbuk_public_housing.json`, `refs/손창미_architecture.md`, `refs/성북구 상황판 데이터 흐름.html`에 있다. 이 브리프의 검토 범위는 HOME 개선이며 조원 데이터 통합이나 플랫폼 이관 상세 설계가 아니다.
