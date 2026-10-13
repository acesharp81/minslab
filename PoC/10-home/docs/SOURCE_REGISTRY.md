# HOME 첫 수집 원천과 포함 규칙

> 2026-10-10 연도별 주택멸실현황 공개본과 데이터 공백 판정은 [데이터 공백 판정과 운영](DATA_AVAILABILITY.md)을 참고하세요. 신규 정비사업·LH 준공예정·건축HUB 상세 원천, 실제 건수 및 신청 상태는 [적용·검증 현황](HOME_IMPLEMENTATION_STATUS_20261010.md)과 [API 연결 안내](HOME_API_CONNECTIONS_20261010.md)를 우선 확인하세요. 아래 내용은 앞선 수집 판본의 기록입니다.


실행 registry는 `backend/sources.py`입니다. 공개 정책자료 4개와 LH 자료 3개를 수집합니다. 정부 주택공급 정책과 서울·경기 사업의 전체 목록을 확보했다는 의미는 아닙니다.

추가로 청약홈·건축HUB·VWorld의 **수동 API 테스트 표본**을 별도 kind로 저장합니다. 정책 사업 Master와 매핑을 생성하지 않습니다. [실제 수집 검증](TEST_COLLECTION.md).

정책 기원·후속조치 `policy_history`와 과거 LH 공사 `lh_history`는 `HISTORY` 원천으로 자동 갱신합니다. 과거 정책은 `policy_event`, 기준일별 보고서는 `project_report`로 보존하여 현재 정책·사업 상태를 덮어쓰지 않습니다. 정책 기원 2018년부터의 누적 수집은 [HISTORICAL_COLLECTION.md](HISTORICAL_COLLECTION.md)에 기록합니다.

공식 지도 원천 `vworld_district`(`MAP_LAYER`, `manual_only=True`)는 VWorld `LT_C_LHBLPN`의 공동주택용지 도형을 `district` kind로 보관합니다. 30개 지구·106개 사업 후보를 검토 연결하며, 완전 일치 지구명과 실제 도형 대표점을 사용합니다. 위치 미연결 44건은 임의 좌표로 보완하지 않습니다. 기존 VWorld 키를 재사용하고 API 표본 3,268건과 분리합니다. [지도 범위와 검증](MAP_INTERFACE.md).

| 원천 ID | 공식 원천 | 첫 정상 수집 |
| --- | --- | --- |
| `policy_907` | [9·7 주택공급 확대방안 — 국세청 공식 전재](https://d.nts.go.kr/cheonan/na/ntt/selectNttInfo.do?mi=4611&nttSn=1353601) | 정책 1 |
| `policy_129` | [1·29 정책브리핑](https://www.korea.kr/briefing/policyBriefingView.do?newsId=156742030) | 정책 1 + 개별 명칭·호수 확인 사업 8 |
| `policy_813` | [8·13 정책브리핑](https://www.korea.kr/briefing/policyBriefingView.do?newsId=156774369) | 정책 1 |
| `urban_930` | [9·30 도심복합 후속조치](https://www.korea.kr/news/policyNewsView.do?newsId=148972807) | 문서 1 + 본문에서 명칭 확인 후보지 3 |
| `lh_sale` | [LH 분양 공급계획](https://apply.lh.or.kr/lhapply/apply/noti/sp/list.do?sUppAisTpCd=05) | 서울·경기 사업 후보 34 |
| `lh_rent` | [LH 임대 공급계획](https://apply.lh.or.kr/lhapply/apply/noti/sp/list.do?sUppAisTpCd=06) | 서울·경기 건설형 임대 사업 후보 18 |
| `lh_construction` | [LH 건설공사 현황](https://www.lh.or.kr/board.es?mid=a10607030000&bid=0007&act=view&list_no=654682) | 서울·경기 주택 건축공사 87 |

국토부 원문 직접 접근이 불안정한 자료는 정부 기관의 공식 전재·정책브리핑을 사용하고 출처 기관을 표시합니다. 정책 유효상태는 후속 변경 문서와 담당자 검토로 확정합니다.

## 실제 수집 규칙

- LH 공급계획은 `sUppAisTpCd`를 유지하고 `listCo=100`, `prevListCo=100`, `currPage`로 전체 페이지를 순회합니다. 전체 건수와 수집 행 수가 다르면 실패 처리합니다.
- 분양 표의 총세대수는 면적별로 반복되어도 한 번만 사용합니다. 공급호수는 면적별 행 기준입니다. 충돌·중복 행은 검증 항목 또는 수집 실패로 처리합니다.
- 소재지가 명시적으로 `서울특별시` 또는 `경기도`인 행을 포함하고 매입·전세 유형은 첫 범위에서 제외합니다.
- 건설공사는 첨부 제목의 기준일로 최신 DOCX를 선택하고 `건축` 공종·`호` 단위의 13열 표만 파싱합니다. 현재 최신 첨부는 **2026-07-01**입니다.
- 지역은 사업지구 표기를 사용합니다. 서울지역본부 관할이라고 서울 소재로 판단하지 않습니다. 위례 등 배분 미확인 지구는 제외합니다. 복수 지역을 묶은 공사 계약은 개별 공급묶음으로 추가 확인해야 합니다.
- 시작일이 원천 기준일 이하인 경우에만 원천상 착공일을 표시합니다. 준공예정일을 실제 준공일로 변환하지 않습니다. 공정률은 해당 파일 기준일 당시 수치입니다.
- 9·30 원문은 총 후보지 11곳을 발표했지만 본문에서 개별 명칭을 확인한 3곳만 생성합니다. 나머지 명칭·개별 호수를 추정하지 않습니다.
- 정책/사업 관계는 원문 근거와 함께 `REVIEW`로 생성합니다. LH 자료의 9·7 귀속은 담당자 확인이 필요한 연결 후보입니다.

## 원본과 실패 처리

웹·파일 원문은 `data/raw/{source_id}/{sha256}.{html|docx}`로, API 응답은 인증정보 제거 후 `{sha256}.json`으로 보존하고 배치 DB에 URL·bytes·SHA-256·parser version manifest를 저장합니다. API manifest에는 키 query를 제거하고 `credentials_removed=True`를 표시합니다. 공개 화면은 원문 URL과 hash를 제공하며 서버 raw 경로는 직접 다운로드 경로로 노출하지 않습니다.

원천별 전체 파싱 후 하나의 DB 트랜잭션으로 적재합니다. schema 변경·접근 실패·페이지 누락은 성공 0건으로 간주하지 않습니다. 실패 배치와 마지막 정상 배치를 분리합니다. 같은 내용은 revision을 늘리지 않고 변경되면 이전 revision을 보존합니다.

다음 원천에서 사업이 사라져도 취소·준공으로 단정하지 않습니다. `최신 원천에서 미발견` 경고와 이전 레코드를 유지합니다.

## 다음 수집 범위

현재 API 규칙은 청약공고: 정책 기원 2018년부터 서울 `100`·경기 `410` × 연도별 필터 결과를 페이지당 100개로 전체 순회, 인허가: 기존 서울·경기 6개 법정동 전체 조회 페이지(법정동별 안전 상한 10,000건), 좌표: 지역·원천 유형별 10개 고유 주소로 한 배치 최대 40개입니다. 전체 페이지 건수와 PK를 검증하고 페이지·연도 중복이나 수집 중 건수 변경 시 적재하지 않습니다. API 미제공 연도와 정책 실적 0을 구분합니다. 법정동 범위와 전체 정책 모집단은 다르며 원천 생성일은 현재 진행 상태가 아닙니다. 좌표 미발견은 NULL로 유지합니다. 현재 상세 범위는 [HISTORICAL_COLLECTION.md](HISTORICAL_COLLECTION.md)입니다.

SH·GH·서울시·경기도·시군구 사업자료, 정책 지정/변경 고시, 청약홈과 건축HUB 전수 실적·정책 사업 연결, 행정구역·사업경계를 순차 추가합니다. 먼저 동일 사업·블록·공급묶음 식별자를 정리하고 승인된 범위 기준선과 연결합니다.

## SH 공식 API (2026-10-03 연결 검증)

`sh_supply_plan`(15008820)과 `sh_redevelopment`(15124798)은 `TEST_SAMPLE`, `manual_only=True`입니다. 공식 ODcloud 메타데이터에서 날짜별 API 경로를 확인한 뒤 모든 페이지와 건수를 검증합니다. 분양계획 4개 공개본 20행, 재개발·재건축 2023-11-02 공개본 16행을 보존했습니다. 원천 날짜·예정월·추진현황·원래 필드를 제공하며 공개본·사업·주택형 식별자로 중복과 변경을 검증합니다. 세부 범위와 제한은 [SH_API_VERIFICATION.md](SH_API_VERIFICATION.md)에 기록합니다.
