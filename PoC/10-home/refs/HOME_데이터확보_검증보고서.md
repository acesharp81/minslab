# HOME 공식 데이터 수집·확보 가능성 검증 보고서

> 검증 기준일: **2026-10-10**  
> 근거: `HOME_GPT_REVIEW_BRIEF.md`(현재 등록 소스/5개 물리 테이블), `PLAN.md`(목표 모델), 정부·공공기관 공식 포털의 공개 데이터셋·명세·정책 고시.  
> 범위: **2026-10-10 확인 · 기존 source_id 36개 + 신규 비교후보 19개 · V2 29 / V1 11 / V0 13 / N 2**. 여기서 55개는 **검토한 원천·후보 등록 단위**이며 55개의 실수집 성공 또는 독립 데이터셋을 뜻하지 않는다. 같은 카탈로그를 여러 source_id가 공유하고, 새 후보 가운데 기존 원천과 중복하는 것도 있다.

## 먼저 결론

1. **핵심 자료를 확보할 공식 경로는 다수 확인**되었다. 특히 건축HUB 인허가 16개 조회 기능, 국토부의 월별 인허가·착공·준공 통계, LH 블록별 준공예정 CSV, 국토부 지구 지정·변경 고시문은 실무 수집 검증의 우선 대상이다.
2. **실제 전수 확보 여부는 아직 확인되지 않았다.** 이번 검증은 공식 웹/카탈로그/API 명세 확인 수준이며 **자격증명으로 인증한 실제 API 호출, 전체 페이지 반복 다운로드, 원본 바이트 검증, 수집된 사업 수량의 독립 재계산 및 HOME 운영 DB 조회를 수행하지 않았다.** 완결성을 주장해서는 안 된다.
3. 병렬 수집하되 데이터 역할을 반드시 나눈다: `(A) 법적·정책·사업 사건 원장`, `(B) 사업·공급묶음 단계별 목표/예정/실제`, `(C) 별도 지역 공식 통계`, `(D) 참고·수요·예측`. 통계(C)로 (A)/(B)의 미확인 개별 사업 실적을 메우지 않는다.
4. 서울 정비사업 참고 원천에는 **법적 효력 부재 안내**가 있다. 제공되는 이용허락 메타데이터가 서로 다른 조회시점에 *공공누리 제4유형*과 *자유이용*으로 다르게 표기되는 것이 관측되어, 최신 원천 약관 확인 전 수집 결과의 2차 배포·재가공 가능성을 확정하지 않는다.
5. 멸실·철거의 정합한 주택 **호수** 및 사업별 병목·중단 **사유**의 전국·수도권 전수 공식 API는 확인되지 않았다. 후보로 남겨야 하며 **0이나 추정값으로 대체하지 않는다.**

## 1. 판정 기준과 한계

| 등급 | 뜻 | 어디까지 주장 가능한가 |
|---|---|---|
| **V2 — 명세·파일 확인** | 개별 공식 API 명세 또는 특정 공개파일·통계표의 제공 방식 확인 | ‘공식 제공 경로 존재’; 호출·전량 확보·현재 행은 미검증 |
| **V1 — 공식 서비스 확인** | 운영하는 공식 검색/자료 서비스 확인 | ‘출처 후보 존재’; API·대량 다운로드/기록 범위 미검증 |
| **V0 — 기존 등록 경로 미재확인** | HOME 브리프 등록 또는 공식 경로 추정은 있으나 이번 독립 확인 실패 | 운영자 재검증 전 자동 확대 금지 |
| **N — 확보 경로 불명** | 요구 항목의 구체적 공식 수집원을 이번 검증에서 특정 못함 | 가공·추측 금지, 추가 자료제공 요청/기관 수기 관리 검토 |

**검증을 완료했다고 보기 위한 4개 관문:** `G1 공식 카탈로그 → G2 인증 포함 1~3페이지 실제 응답 → G3 지역×연도×페이지 전수/결측 검사 → G4 원문 해시·레코드·지표 검증·주기적 재수집`.

**V2는 G1 판정이며, G2~G4를 만족하지 않는다.** 원천별 최신 등급·검증 일시·담당을 Codex가 운영대장으로 갱신해야 한다.

## 2. 실제 확인된 확보 경로와 중요 사실

| 원천 | 취득 경로 및 검증 결과 | HOME 적재상 주요 제약 |
|---|---|---|
| [건축HUB 주택인허가](https://www.data.go.kr/data/15136560/openapi.do) | 정부 공개 API REST JSON/XML; `getHpBasisOulnInfo`, `getHpDongOulnInfo`, `getHpPlatPlcInfo` 등 **16개 GET** 명세. 2026-07-10 수정, 월간 갱신, 카탈로그상 개발계정 신청가능 트래픽 10,000(실사용 승인값 아님) | 원천 PK 체계 변경 안내. API 내부 허가 ID는 HOME 사업 ID가 아님. 일부 허가·공종만 정책관리 대상 |
| [건축HUB 건축물대장](https://www.data.go.kr/data/15134735/openapi.do) | 대장 표제부 등 REST API 명세 | 건축물 재고/대장 기록을 정책 시행 후 신규 공급·실준공으로 자동 산정하지 않음 |
| [국토부 인허가](https://stat.molit.go.kr/portal/cate/statMetaView.do?hRsId=31) · [착공](https://stat.molit.go.kr/portal/cate/statMetaView.do?hRsId=471) · [준공](https://stat.molit.go.kr/portal/cate/statMetaView.do?hRsId=468) | 국토교통통계누리에서 월별 공식 통계표 및 연도별·월별·지역별 XLSX/ZIP 제공. 익월말 잠정치/익년 9월 확정치 | 시군구 해상도는 *실제 선택한 통계표/파일의 컬럼*으로 판정. 2014~24 재집계 설명에 최초 사용승인 시 전체 세대수 인식, 동일 허가 일부 중복 가능성 명시. HOME 개별 사업의 실적과 직접 차감 금지 |
| [LH 공공주택 준공예정현황](https://www.data.go.kr/data/15141761/fileData.do) | 2026-01-27 기준 파일 설명에 사업지구·블록·위치·공급유형·세대수·준공예정일, CSV; 포털 메타데이터 2026-09-02 수정 | 준공 예정은 실제 준공 아님. 세대수 0·공란이 ‘미확정’을 뜻할 수 있음. 공식 완료량 또는 0호로 오해 금지 |
| [LH 신규입주계획](https://www.data.go.kr/data/15084477/fileData.do) | 기관 공개 자료·첨부다운로드 경로 | 계획·예정, 실입주 검증 아님. 기존 `lh_movein_history`와 중복 원천 검사 |
| [국토부 공공주택지구 고시 사례](https://molit.go.kr/USR/I0204/m_45/dtl.jsp?gubun=4&idx=18272&lcmspage=20) | 고양창릉 지구 지정 변경 **4차**, 국토교통부고시 **제2024-372호**(2024-07-15), 이전 고시·고시문 첨부가 포함된 공식 자료 | 지구의 지정·변경 **일부 사건을 입증할 수 있음**. 모든 지구와 지정/변경/해제의 전수 아카이브나 API 이용 가능성은 별도 |
| [서울 정비사업 현황](https://data.seoul.go.kr/dataList/OA-20281/A/1/datasetView.do) | `upisRebuild` Open API 구조·결정고시관리코드 설명, 연관 결정고시 자료 | ‘법적 효력 없음’ 명시. 동일 URL의 크롤 시점별 이용허락 표기가 상충하여 최신 약관 확인이 필요하며, 원고시가 법적 근거 |
| [경기도 정비사업 온누리](https://www.gg.go.kr/onnuri/index.do) | 공식 사업장 검색, 추진현황, 고시/공고 제공 | 웹 페이지 확인만으로 정비사업 전체/공공주택지구/과거 고시 전수 수집 가능하다고 보지 않음 |
| [SH 주택분양 계획](https://www.data.go.kr/data/15008820/fileData.do) | 2026년 공개 파일 4행으로 제한된 계획 목록 | SH 전체 공급 마스터로 사용 금지 |
| [GH 재건축매입임대](https://www.data.go.kr/data/15112600/fileData.do) | 2026-06 기준 특정 유형의 10행 카탈로그 | GH 전체 신규 공급·준공의 대표 표본 아님 |
| [행안부 주민등록통계](https://jumin.mois.go.kr/) | 지역별 월별 인구·세대 다운로드 | 외국인 제외 등 가구총조사·장래가구추계와 분모 정의가 다름 |
| [SGIS 인구주택총조사](https://sgis.mods.go.kr/developer/html/newOpenApi/api/dataApi/census.html) · [KOSIS](https://kosis.kr/openapi/devGuide/devGuide_0201List.do) | 공공 통계 API 설명과 시점·지역 파라미터 | 표/기준년도·조사단위·행정코드·주거지/사업장 기준을 분리 |

## 3. 검토 대상 전체 55개 출처·수단 대장

**해석:** 기존 36개 `source_id`와 추가 조사 후보 19개를 나열한다. `✓`는 기존 HOME 코드 등록 ID, `+`는 새로운 후보. `G1 V2` 역시 실제 API 인증·데이터 취득이 완료된 것이 아니다.

### 정책 (5건)

| 분류/원천 ID | 내용·역할 | 확인 등급·수단 | 공식 진입점 | 미확인 또는 주의점 |
|---|---|---|---|---|
| ✓ `policy_907` | **9·7 주택공급 확대방안** — 정책 목표·범위 | **V2** · 국토부 보도자료·첨부 HWPX/PDF | [공식 링크](https://www.molit.go.kr/USR/NEWS/dtl.jsp?id=95091185) | 브리프 기존 국세청 URL 접속 실패; 원문 첨부 실제 바이트 다운로드 미실시 |
| ✓ `policy_129` | **1·29 도심 주택공급 확대방안** — 정책 대상 후보·총량 | **V2** · 정책브리핑 본문·첨부 PDF/HWP | [공식 링크](https://www.korea.kr/briefing/policyBriefingView.do?newsId=156742030) | 첨부 표의 후보지별 값 정합성 별도 확인 |
| ✓ `policy_813` | **8·13 관련 정책문서** — 정책 사건 | **V0** · 정책브리핑 웹/첨부 | [공식 링크](https://www.korea.kr/briefing/policyBriefingView.do?newsId=156774369) | 현시점 문서 링크 직접 조회 실패; 제목·첨부·범위 재검증 |
| ✓ `urban_930` | **9·30 관련 후속정책** — 정책 사건 | **V0** · 정책브리핑 웹/첨부 | [공식 링크](https://www.korea.kr/news/policyNewsView.do?newsId=148972807) | 현시점 페이지 직접 조회 실패; 날짜·명칭·첨부 재검증 |
| ✓ `policy_history` | **과거 정책 기원 문서** — 정책 선후 관계 | **V0** · 정책브리핑 웹/첨부 | [공식 링크](https://www.korea.kr/news/policyNewsView.do?newsId=148856563) | 자료별 소급범위·공식 효력 검증 |

### LH (13건)

| 분류/원천 ID | 내용·역할 | 확인 등급·수단 | 공식 진입점 | 미확인 또는 주의점 |
|---|---|---|---|---|
| ✓ `lh_sale` | **LH 분양 공고·목록** — 모집·공고 | **V2** · LH청약플러스 웹 목록·상세 | [공식 링크](https://apply.lh.or.kr/lhapply/apply/noti/sp/list.do?sUppAisTpCd=05) | 페이지 전량·상세 일정·정정공고 연결은 운영 환경에서 시험 |
| ✓ `lh_rent` | **LH 임대 공고·목록** — 임대 모집·공고 | **V1** · LH청약플러스 웹 목록·상세 | [공식 링크](https://apply.lh.or.kr/lhapply/apply/noti/sp/list.do?sUppAisTpCd=06) | 임대 목록 검색·페이지네이션 별도 검증 |
| ✓ `lh_notice` | **LH 분양임대공고문 API** — 공고·공고정정 | **V2** · 공공데이터포털 REST API | [공식 링크](https://www.data.go.kr/data/15058530/openapi.do) | 활용신청·인증·페이지완결성·원천형식 실호출 미검증 |
| ✓ `lh_construction` | **LH 건설공사 관련 보고** — 공정·사업 후보 | **V0** · LH 홈페이지 공개 첨부 | [공식 링크](https://www.lh.or.kr/board.es?mid=a10607030000&bid=0007&act=view&list_no=654682) | 해당 페이지 현재 도구 접근 실패; 첨부 및 기준일 별도 검증 |
| ✓ `lh_history` | **LH 과거 사업·공정 보고** — 과거 공정 | **V0** · LH 보도/자료실 첨부 | [공식 링크](https://www.lh.or.kr/board.es?mid=a10607030000&bid=0007&act=view&list_no=654682) | 2018~2024 사업별 공정의 연속 커버리지 미확보 |
| ✓ `lh_progress` | **LH 블록 공정 조회** — 사업 공정·단계 | **V1** · LH청약플러스 공식 웹 | [공식 링크](https://apply.lh.or.kr/lhapply/land/cwsttList.do) | 공정률 표본/기간/전체성 및 공정률≠준공호수 검증 |
| ✓ `lh_reit_progress` | **LH 리츠 공정** — 리츠 사업 공정 | **V0** · LH 공식 웹/첨부 | [공식 링크](https://apply.lh.or.kr/lhapply/land/cwsttList.do) | 공식 표본·리츠 범위 분리 불명 |
| ✓ `lh_supply_history` | **LH 과거 공급현황** — 과거 분양 계획 | **V0** · LH 사전정보 공표 첨부 | [공식 링크](https://www.lh.or.kr/board.es?act=view&bid=0007&list_no=727605&mid=a10103040000&nPage=1) | 원본 첨부·연속 연도 확인 필요 |
| ✓ `lh_movein_history` | **LH 입주계획 과거 자료** — 입주예정 | **V2** · LH 공표 자료·HWPX 파일 | [공식 링크](https://www.data.go.kr/data/15084477/fileData.do) | 원문 현행 첨부판본·연도별 완전성 및 실제 입주 증거는 별도 |
| ✓ `lh_stock` | **전국 LH아파트 단지정보** — 기존 재고·단지식별 | **V2** · 공공데이터포털 공개파일 | [공식 링크](https://www.data.go.kr/data/15080989/fileData.do) | 재고와 신규 공급 실적 구분, 원천 PK·갱신주기 재검증 |
| ✓ `lh_block_location` | **LH 비즈맵 블록 위치** — 블록 공간참조 | **V0** · LH GIS 웹지도 | [공식 링크](https://bizmap.lh.or.kr/lhmap.do) | 공식 다운로드/API·경계 타입·재배포 이용조건 미검증 |
| + `new_lh_completion_plan` | **LH 공공주택 준공예정현황** — 블록별 공식 준공예정 | **V2** · CSV 원문파일·자동변환 API | [공식 링크](https://www.data.go.kr/data/15141761/fileData.do) | 예정≠실제, 주소 대략적·0=미확정 가능 |
| + `new_lh_movein_registry` | **LH 신규입주계획 파일 카탈로그** — 연도별 입주예정 | **V2** · LH 기관 다운로드 링크·HWPX | [공식 링크](https://www.data.go.kr/data/15084477/fileData.do) | 브리프 기존 lh_movein_history와 중복 확인 필요 |

### SH (4건)

| 분류/원천 ID | 내용·역할 | 확인 등급·수단 | 공식 진입점 | 미확인 또는 주의점 |
|---|---|---|---|---|
| ✓ `sh_files` | **SH 주택관리현황** — 기존 임대 재고 | **V2** · 서울 열린데이터광장 XLSX | [공식 링크](https://data.seoul.go.kr/dataList/OA-12027/S/1/datasetView.do) | 단지별 공급 신규 실적 아님 |
| ✓ `sh_supply_plan` | **SH 주택분양 공급계획** — 계획·분양예정 | **V2** · 공공데이터포털 CSV/파일 자동변환 API | [공식 링크](https://www.data.go.kr/data/15008820/fileData.do) | 공공분양 계획 제한적 4행, SH 전체공급 전수 원장 아님 |
| ✓ `sh_redevelopment` | **SH 공공재개발·재건축** — 정비 사업 후보 | **V2** · 공공데이터포털 공개파일 | [공식 링크](https://www.data.go.kr/data/15124798/fileData.do) | 변경 고시 이력·현재 유효성은 별도 확인 |
| ✓ `sh_inventory` | **SH 유형별 관리재고 파생** — 재고 참조 | **V2** · 서울 열린데이터광장 XLSX | [공식 링크](https://data.seoul.go.kr/dataList/OA-12027/S/1/datasetView.do) | HOME 내 파생 테이블 최신화·호수 정의 검증 |

### GH (3건)

| 분류/원천 ID | 내용·역할 | 확인 등급·수단 | 공식 진입점 | 미확인 또는 주의점 |
|---|---|---|---|---|
| ✓ `gh_files` | **GH 재건축매입임대현황** — 재건축 매입임대 재고 | **V2** · 공공데이터포털 공개파일 | [공식 링크](https://www.data.go.kr/data/15112600/fileData.do) | 이 데이터는 GH 전체 공급계획이 아닌 특정 매입임대 현황 |
| ✓ `gh_supply_plan` | **GH 분양/임대계획 안내** — 경기 공공 공급예정 | **V1** · GH 공식 웹페이지 | [공식 링크](https://www.gh.or.kr/gh/housing-stability-in-gyeonggi-do001.do) | 기계수집/연간 파일·지역 전수 완결성 미검증 |
| ✓ `gh_notice` | **GH 분양·임대 공고** — 모집·공고 | **V0** · GH 공식 웹페이지 | [공식 링크](https://www.gh.or.kr/gh/housing.do) | 현 링크 직접 접근 오류, 대체 경로 탐색 필요 |

### 청약·인허가 (3건)

| 분류/원천 ID | 내용·역할 | 확인 등급·수단 | 공식 진입점 | 미확인 또는 주의점 |
|---|---|---|---|---|
| ✓ `cheongyak` | **청약홈 분양정보** — 모집공고 실제 사건 | **V2** · 공공데이터포털 REST API | [공식 링크](https://www.data.go.kr/data/15098547/openapi.do) | HOUSE_MANAGE_NO는 HOME 사업 ID 아님; 키·레코드 수·정정 구분 미검증 |
| ✓ `building_hub` | **건축HUB 주택인허가** — 사업 동일성·승인·착공 | **V2** · 공공데이터포털 인증 REST API | [공식 링크](https://www.data.go.kr/data/15136560/openapi.do) | 활용승인 키 실호출, 총페이지, 자연키, 업무대상/비대상 제외 필요 |
| ✓ `building_register` | **건축HUB 건축물대장** — 건축물 실물·대장·재고 증거 | **V2** · 공공데이터포털 인증 REST API | [공식 링크](https://www.data.go.kr/data/15134735/openapi.do) | 기존 재고≠준공 실적; 건축허가와 사용검사 연결 별도 검증 |

### 통계 (12건)

| 분류/원천 ID | 내용·역할 | 확인 등급·수단 | 공식 진입점 | 미확인 또는 주의점 |
|---|---|---|---|---|
| ✓ `molit_statistics` | **국토교통부 주택통계** — 인허가·착공·분양·준공 지역 공식 집계 | **V2** · 통계누리 XLSX/CSV 및 API 안내 | [공식 링크](https://stat.molit.go.kr/portal/cate/statMetaView.do?hRsId=31) | 시군구 공개 해상도는 통계표별 확인, 사업별 정책 실적으로 바로 귀속 금지 |
| ✓ `kosis_housing` | **KOSIS 주택 재고 통계** — 가구·재고 분모 | **V1** · KOSIS 등록키 API | [공식 링크](https://kosis.kr/openapi/devGuide/devGuide_0201List.do) | 사용 tblId·표의 실제 공간/기간 분류는 재검증 |
| ✓ `kosis_household_size` | **KOSIS 가구원수별 가구** — 지역 가구 구조 | **V1** · KOSIS 등록키 API | [공식 링크](https://kosis.kr/openapi/devGuide/devGuide_0201List.do) | 실제 선택된 표 DT_1JC1516 최신 항목 구조는 미확인 |
| ✓ `kosis_employment` | **KOSIS 고용 통계** — 지역 노동시장 맥락 | **V1** · KOSIS 등록키 API | [공식 링크](https://kosis.kr/openapi/devGuide/devGuide_0201List.do) | 선택 tblId의 거주지/사업장 기준 확인 필요 |
| ✓ `kosis_household_forecast` | **KOSIS 장래가구 추계** — 장기 가구 전망 | **V1** · KOSIS 등록키 API | [공식 링크](https://kosis.kr/openapi/devGuide/devGuide_0201List.do) | 추계 시나리오·범위·공표 주기 확인 필요 |
| ✓ `sgis_area` | **SGIS 인구주택총조사** — 인구·가구·주택 재고·고용 | **V2** · SGIS 액세스토큰 REST API | [공식 링크](https://sgis.mods.go.kr/developer/html/newOpenApi/api/dataApi/census.html) | 연도 상한 동적으로 변경될 수 있어 운영 재검증; 행정구역 코드 변환 |
| + `new_movein_estimate` | **한국부동산원 입주예정물량** — 입주전망 보조선 | **V2** · 공공데이터포털 CSV | [공식 링크](https://www.data.go.kr/data/15111714/fileData.do) | 정책 성과·공식 실입주 증거 아님 |
| + `new_mois_population` | **행안부 주민등록 인구·세대** — 월간 세대/인구 맥락 | **V2** · 정부 사이트 CSV/XLSX 다운로드 | [공식 링크](https://jumin.mois.go.kr/statGrapA.do) | 외국인 제외, KOSIS 가구 정의와 불일치 |
| + `new_molit_unsold` | **국토부 미분양주택현황** — 민간시장 리스크 맥락 | **V2** · 통계누리 XLSX/통계표 | [공식 링크](https://stat.molit.go.kr/portal/cate/statMetaView.do?hRsId=32) | 대상은 주로 민간 미분양; 개별 공공사업 지연사유를 증명하지 않음 |
| + `new_molit_sales_stat` | **국토부 주택건설실적(분양)** — 지역별 공급 흐름 | **V2** · 통계누리 XLSX | [공식 링크](https://stat.molit.go.kr/portal/cate/statView.do?hRsId=488) | 본청약 공고·정책 귀속과 자동 동일시 불가 |
| + `new_molit_starts_stat` | **국토부 주택건설실적(착공)** — 지역별 착공 공식 실적 | **V2** · 통계누리 XLSX/CSV | [공식 링크](https://stat.molit.go.kr/portal/cate/statMetaView.do?hRsId=471) | 사업별 정책관리 목표와 분모 불일치 주의 |
| + `new_molit_completion_stat` | **국토부 주택건설실적(준공)** — 지역별 준공 공식 실적 | **V2** · 통계누리 XLSX/CSV | [공식 링크](https://stat.molit.go.kr/portal/cate/statMetaView.do?hRsId=468) | 사업별 준공동수·사용검사 날짜와 집계시점 차이 |

### 공간 (5건)

| 분류/원천 ID | 내용·역할 | 확인 등급·수단 | 공식 진입점 | 미확인 또는 주의점 |
|---|---|---|---|---|
| ✓ `legal_dongs` | **법정동 코드 목록** — 법정동 구분·주소 표준화 | **V2** · 행정표준코드 공식 조회 | [공식 링크](https://www.code.go.kr/stdcode/regCodeL.do) | 코드 유효기간·행정구역 변동판본 수집방법 필요 |
| ✓ `vworld` | **VWorld 주소 좌표** — 좌표 지오코딩 | **V0** · 브이월드 API·인증 | [공식 링크](https://www.vworld.kr/v4po_openapi_s001.do) | 제시된 개발자 문서 페이지 접근 실패; 정확한 엔드포인트·키·약관 재검증 |
| ✓ `vworld_district` | **VWorld 용지·공공주택지구 공간** — 법적 구역 경계·대표위치 | **V0** · 브이월드 GIS/WFS | [공식 링크](https://www.vworld.kr/v4po_openapi_s001.do) | 레이어 ID·법적 지위·폴리곤 변화이력·사용권한 불명 |
| ✓ `vworld_municipality` | **VWorld 시군구 경계** — 시군구 경계 | **V0** · 브이월드 행정구역 WFS | [공식 링크](https://www.vworld.kr/v4po_openapi_s001.do) | 법정/행정 경계별 시간 버전 및 API 호출 미검증 |
| + `new_regional_gis` | **국토부 행정구역도(WMS/WFS)** — 시군구 경계 공간참조 | **V2** · 공공데이터포털 공개 OGC 서비스 | [공식 링크](https://www.data.go.kr/data/15059008/openapi.do) | 실제 피처 응답/좌표계/기준연도·갱신 범위 확인 필요 |

### 서울·경기 계획 (7건)

| 분류/원천 ID | 내용·역할 | 확인 등급·수단 | 공식 진입점 | 미확인 또는 주의점 |
|---|---|---|---|---|
| + `new_seoul_upis` | **서울 도시계획 정비사업 현황(upisRebuild)** — 계획/구역 후보·결정고시관리코드 | **V2** · 서울 열린데이터광장 API (인증키) | [공식 링크](https://data.seoul.go.kr/dataList/OA-20281/A/1/datasetView.do) | 법적 효력 없음 명시; 이용허락 표기가 크롤시점에 따라 제4유형/자유이용으로 상충: 최신 조건·원문 이용허락 재확인 후 재가공/공개 판단 |
| + `new_seoul_notice` | **서울 도시계획 결정고시 정보** — 결정고시 사건 연결 | **V1** · 서울 열린데이터광장 DB·OpenAPI 후보 | [공식 링크](https://data.seoul.go.kr/dataList/OA-20283/S/1/datasetView.do) | 데이터셋도 비법적참고·공공누리 4유형, 원고시 PDF를 법적 증거로 별도 검증 |
| + `new_seoul_urban_history` | **서울 도시계획이력 정보** — 계획 변경이력 후보 | **V1** · 서울 열린데이터광장 | [공식 링크](https://data.seoul.go.kr/dataList/OA-20282/S/1/datasetView.do) | 실제 버전·관계키·권리·연속기간 상세 미검증 |
| + `new_seoul_renewal_report` | **서울 도시정비사업 통계** — 정비사업 단계 교차검증 | **V2** · XLSX 분기 통계 | [공식 링크](https://data.seoul.go.kr/dataList/OA-22856/L/1/datasetView.do) | 고시 원본 아님, 분기 갱신/문서 내 첨부 확인 |
| + `new_gyeonggi_onnuri` | **경기도 정비사업 온누리** — 경기 정비사업 후보·진행단계 | **V1** · 공식 홈페이지 조회·고시공고 | [공식 링크](https://www.gg.go.kr/onnuri/index.do) | API/다운로드 가능 여부 및 역사 전체성 미확인, 공공택지와는 별도 |
| + `new_gosi_eum` | **토지이음 고시정보** — 공공주택지구 지정·변경·해제 검색 후보 | **V0** · 공식 고시검색 웹 | [공식 링크](https://eum.go.kr/web/gs/gv/gvGosiList.jsp) | 도구에서 페이지 인코딩 오류, 목록 검색 조건·API·저작권 미확인 |
| + `new_public_housing_gosi` | **공공주택지구 지정·변경·해제 원고시** — 계획 법적 상태 | **V2** · 국토부 및 지자체 공식 고시 원문 | [공식 링크](https://www.molit.go.kr/USR/I0204/m_45/dtl.jsp?gubun=4&idx=18272&lcmspage=20) | 이 자료는 단일 지구 고시사례; 모든 지구의 지정·변경·해제 전수·크롤링 API는 미검증 |

### 임대·추가 (3건)

| 분류/원천 ID | 내용·역할 | 확인 등급·수단 | 공식 진입점 | 미확인 또는 주의점 |
|---|---|---|---|---|
| + `new_myhome` | **마이홈포털 공공임대주택/모집** — 임대 단지·공고 교차검증 | **V1** · 공식 웹 검색 | [공식 링크](https://www.myhome.go.kr/hws/portal/main/getMgtMainPage.do) | 공개 API/일괄 파일/PNU 필드 제공은 확인되지 않음 |
| + `new_molit_demolition` | **주택 멸실·철거** — 재고 순증·멸실 | **N** · 공식 지역 통계원천 탐색 필요 | 확보 경로 미확인 | 건축물대장 말소 데이터로 멸실호수나 물량을 자동 추정 금지 |
| + `new_suspension` | **공사중단·병목원인 현황** — 사업별 지연 원인 | **N** · 기관별 관리자료·공개자료 검증 필요 | 확보 경로 미확인 | 관리자 입력/공식 보고 자료를 근거와 함께 사용 |

## 4. 보유 원천부터 추가할 구체적 필드·연결 규칙

| 수집원 / 수집 대상 | 필요한 최소 인덱스·자연키(원천값, HOME PK 아님) | 적재할 계층 | 범위 검증 |
|---|---|---|---|
| 건축HUB 기본개요/동별/대지위치 | 원천 PK, 허가번호, 법정동코드, PNU/필지, 승인/착공/사용검사 일자, 동/호수 | `source_object`→`identity_alias`→`project_evidence`→`milestone` | 월×동×endpoint×페이지 커버리지; 참조할 한 사업에 복수 동 주의 |
| LH 계획/준공예정/공정/모집 | 사업지구명, 공식 사업·블록코드, 주택유형, 호수, 단계, 예정기준일 | `home_block`, `home_supply_cohort`, `home_supply_measure`, `home_milestone` | 지구·블록 인식률, 과거 파일 버전, 동일 모집 1차·정정·잔여 구분 |
| 국토부/지자체 원고시 | 고시 발행기관·번호·일자, 문서 해시, 이전 고시, 지구·계획 코드, 지정/변경/해제, 효력일 | `home_plan` + `home_plan_event` 및 `home_plan_project_link` | 고시 최초~현재 체인, 번호 중복, 효력일/게시일 구분 |
| 서울 정비사업 API/경기 온누리 | 계획/구역 식별코드, 현황·결정고시관리코드, 원고시 URI | *참고* 계획 후보 + 근거 링크 | 접근 가능·이용허락·현행 legal-status 배제 규칙 |
| 국토교통통계누리 | 통계표ID, 지역코드, 연월, 지표, 단위, 잠정/확정, 판본, 공표일 | **별도** `home_region_stat` (Master/Fact와 별도) | 선택 통계표의 실제 시군구 컬럼, 집계정의, 이전 공표값 수정 |
| 주민등록/KOSIS/SGIS | 원천 표ID, 기준일, 지역코드/정의, 값 유형(관측/추계) | `home_area_context` 또는 별도 통계 영역 | 인구/가구 개념·외국인·재고·사업장 소재지 구분 |

### G2~G4 실증 체크리스트 (각 소스에 적용)

- [ ] 공식 제공조건, 공개등급, 2차 이용조건·출처표시 의무를 수집 승인권자가 확인했다.
- [ ] API 키는 비공개 환경변수에 두고 `requests/manifest`에서 query secret 제거를 검증했다.
- [ ] 호출 가능 endpoint·필수 파라미터·요청 URL·응답코드·pagination·실제 1페이지 응답을 저장했다.
- [ ] 지역×연도×endpoint별 전체 페이지를 끝까지 읽고 원천 `totalCount`와 정규화 행 수를 비교했다.
- [ ] 원천에 조회 0건인 경우와 오류/미조회/갱신 지연을 다른 상태로 기록했다.
- [ ] 3개 원본 fixture에 schema·파서 회귀 테스트를 통과했다.
- [ ] 출처별 고유키·`kind` 충돌과 정정·삭제 레코드의 역사처리 규칙을 통과했다.
- [ ] 기존 `home_revision`·`home_mapping`·`home_audit` 및 관리자 확정·목표를 덮어쓰지 않았다.
- [ ] 특정 날짜의 정책 목표/사업 진행을 과거 `known_at`과 사건 `effective_at` 별도로 재현했다.
- [ ] 프로젝트에 사용할 수 있는 레코드와 지역 배경 통계를 혼합·중복합산하지 않았다.

## 5. 가장 위험한 해석 오류와 차단 규칙

1. **정책 목표 착공 135만과 준공/입주 물량 비교 금지.** 정책 측정 단계와 공간범위가 같은 경우에만 달성률을 제공한다.
2. **수도권 목표의 서울+경기 배분을 임의 추정 금지.** 인천이 포함되거나 배정치가 없다면 `NON_COMPARABLE` 또는 `SCOPE_UNKNOWN`.
3. **동일 사업 여러 기관 행 → 여러 실물 사업으로 가정 금지.** 안정 `HPR_*`, 원천 alias·증거·승인 상태로 정체성 확인.
4. **지구 총량 + 블록 물량 이중합산 금지.** `home_supply_cohort` 상하위 구조, 미배정 잔여를 ‘사업’이 아닌 집계상 잔여로 관리.
5. **정책/후속대책 복수 귀속 총합 이중합산 금지.** 정책별 승인 집계와 지역 고유 물량 집계를 독립 집계 context로 처리.
6. **준공예정 ≠ 준공실적, 입주예정 ≠ 실제 입주.** 사건의 `plan/actual/estimate` 구분 필수.
7. **공정률(%)을 준공호수로 환산 금지.** 공정률의 분모는 건설공정이고 공급 호수 지표가 아님.
8. **행정통계 준공 최초 승인 시점과 사업별 단계별 실준공 시점 혼동 금지.** 정의가 일치하는 경우만 품질 비교.
9. **서울 upisRebuild 법적 효력 부여 금지.** 고시번호·공식 게시 원문을 갖춘 `plan_event`만 법적 사건으로 분류.
10. **주민등록세대·통계청 가구·주택재고·공급계획 수치 직접 가감 금지.** 모집단과 기준연도·조사 개념 차이를 별도 관리.
11. **0 / null / 미수집 / 원천 없음 / 예정일 미정 / 단계 비적용 / 검토대상 혼동 금지.** `value_status`와 `collection_status` 분리.
12. **원천 수정/삭제를 HOME 판본 삭제로 처리 금지.** bitemporal 이력과 manifest 유지.
13. **REVIEW 연결을 공식 성과로 표시 금지.** 탐색·관리자 승인 연결·공식 실적을 분리.
14. **과거 정책 시행 이전 완료를 해당 정책 성과로 소급 금지.** 전후 정책·사업 이력은 표시해도 귀속은 승인 근거 필요.
15. **법적 원천/공공 데이터셋 이용허락 메타데이터 충돌 무시 금지.** 당시 자료 출처·허락 판본, 제공처 답변 및 공개 전 검증 필수.

## 6. 추진 순서와 성공 판정

| 단계 | 작업 | 산출물 / 실패 조건 |
|---|---|---|
| 0: READ-ONLY PRECHECK | 실제 코드·마이그레이션·DB 5개 물리 테이블·36 등록 소스 확인. 별도 백업·복구 가능성 검증 | 기존 승인건/goal/audit 건수, 원천 충돌 검사, 현재 수집 커버리지. 불명확하면 스키마 이관 중단 |
| 1: G1→G2 자료 확증 | 우선 API/파일 3개(건축HUB 동별·대지위치, LH 준공예정, 국토부 월별 실적)의 실원본 소량 검증 | Raw SHA-256 + manifest + 행 카탈로그 + 실패 재현; 데이터 미제공 시 `UNVERIFIED` |
| 2: 핵심 의미 모델 | `baseline`+`cohort` 규칙, 안정 사업 ID와 계획/사건 최소 스키마, `coverage` | 중복 0, 원본 보전, 예시 10 사업·10 cohort 정합성 확인 |
| 3: 골든셋·연결 | 서울 정비형 + 경기 공공택지형 공식 근거 최소 10개 사업, 2정책/3프로그램 | 허가·고시·공급·블록의 정체성 충돌을 담당자 검토로 해결 |
| 4: 병렬 통계·지도 API | 지역별 공식 통계 계층 별도 구성, `map` 출력 contract와 단계별 실적/예정 분리 | 지역 통계 ≠ 개별 정책 성과, 지도 값 → 증거 Drill-down |
| 5: 확대 | 서울 전구·경기 유형·과거연도·고시 사건 확대 | 지역×연도×자료 유형 completeness 지표 확보 |
| 6: 운영 | 고시 갱신·스키마 변경 감지, 소스 이용조건 승인, 병목 수기 입력 | 실패 배치 이전 성공본 유지, 권한·감사·복구 확인 |

**초기 수용 테스트:** (a) 확정 정책 이행률은 정의가 맞는 경우만 숫자, (b) `REVIEW`가 공식 실적에 혼입되지 않음, (c) 지구 33,000 + 블록 20,000의 잘못된 53,000이 발생하지 않음(설명용 가상 수치), (d) 서울과 경기도 모두 포함한 10사업 골든셋, (e) 현행 공개 API 계약을 깨지 않음, (f) G2~G4 인증/원문 부재는 정확히 미검증으로 남김.

## 7. 관련 산출물·사후 운영

- `HOME_source_verification.json`: 55개 원천별 URL, 판정, 확인된 사항, 남은 테스트를 가진 기계판독용 근거 카탈로그
- `HOME_시스템아키텍처_설명.html`: 시스템 전반, ERD, 집계 규칙, 수집 상태를 설명하는 단일 HTML
- `HOME_CODEX_실행지시서.md`: Codex가 실제 저장소에서 검사 → 보완 → 단계별 데이터 수집 → 안전한 이관 → 테스트까지 수행하도록 하는 실행 지침

**보고서의 한계:** 위 공식 URL은 2026-10-10에 웹 검색/카탈로그상 존재를 확인한 사례다. 서울·경기 전 기간 수집의 법적·기술적 가용성과 인증 후 응답은 Codex 실행 단계에서 확인해야 한다. 어떤 원천에도 운영계정의 키를 만들었다거나 실제 배치 적재에 성공했다고 기재하지 않았다.
