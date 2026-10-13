# HOME API 키 발급·연결 안내

2026-10-12 **9·7 수도권 확대**: 인천 LH 분양·임대계획 10건, 착공·공정 16건,
통계누리 320행, VWorld 시군구 경계 11개와 건축물대장 총괄표제부 1,539건을 실제 수집했습니다.
이 자료에는 추가 키가 필요하지 않았습니다. VWorld·통계누리·건축물대장 기존 HOME 키를 재사용합니다.

추가 기관 자료로 [iH 임대주택 공급대상 및 실적 조회](https://www.data.go.kr/data/15168460/openapi.do)를 안내합니다.
공공데이터포털 로그인 → **활용신청** → 개발계정 자동승인 → 마이페이지의 **일반 인증키(Decoding)**를 확인합니다.
신청 목적은 수도권 주택공급 단계·기관별 실적 검증, 서비스 URL은 `https://www.minslab.kr/poc/home/`입니다.
발급 키가 기존 포털 키와 같아도 해당 서비스 활용승인이 필요합니다.
실제 키는 `PoC/10-home/.env`의 `POC10_IH_SERVICE_KEY=`에 저장합니다. `.env.example`에는 빈 변수명만 등록했습니다.
iH 수집기는 연결했으며 전용 키가 비어 있으면 기존 HOME `POC10_LH_NOTICE_SERVICE_KEY`를 재사용합니다.
2026-10-12 신청 후 검증에서 API 서버가 **HTTP 504 / SERVICETIMEOUT_ERROR(05)**를 반환했습니다.
이는 원천 기관 연결 실패 응답이고 자료 0건·0호를 의미하지 않습니다. 데이터 검증의 배치 상태에서 재시도 여부를 확인합니다.
공식 Swagger 응답은 주택별 재고(`totalHouseholds`), 계약(`contractHouseholds`), 공가(`vacantHouseholds`)의 유형별 수량입니다.
소개 문구의 ‘공급실적’을 연간 신규 착공·모집 실적과 동일하게 해석하지 않습니다. 개별 관측일·정책 귀속 확인 전 `agency_stock` 참조자료로 별도 보관합니다.
원천 복구 후 `sudo docker exec poc10-home-api python -m scripts.collect --source ih_supply`로 다시 수집할 수 있습니다.
이 신청은 인천 LH·지역 통계 조회와 독립적입니다. iH 자료를 아직 확보하지 않은 것을 0호로 표시하지 않습니다.

> 2026-10-10 추가 확보한 [GH 사용검사·승인 PDF](https://apply.gh.or.kr/cs/sr/sr7900/selectNoticeList.do)와 [한국부동산원 단지 식별정보 CSV](https://www.data.go.kr/data/15106861/fileData.do)는 **새 API 키 없이** 수집했습니다. 기존 건축HUB·건축물대장 키로 법정동 조회도 확대했습니다. 최신 수량과 남은 핵심 공백은 [데이터 공백 판정과 운영](DATA_AVAILABILITY.md), [미입수 자료 확보 순서](DATA_ACQUISITION_PRIORITIES.md)를 참고하세요.

> 2026-10-10 신규 정비사업·LH 준공예정·건축HUB 상세 원천, 실제 건수 및 신청 상태는 [적용·검증 현황](HOME_IMPLEMENTATION_STATUS_20261010.md)과 [API 연결 안내](HOME_API_CONNECTIONS_20261010.md)를 우선 확인하세요. 아래 내용은 앞선 수집 판본의 기록입니다.


2026-10-03 점검. **최신 공식 원천 7개와 과거 정책·공사 원천 2개는 API 키 없이 수집합니다.** 청약홈·주택인허가·VWorld와 신규 건축물대장·LH 공고·통계누리까지 SH 분양계획·재개발·재건축까지 총 8개 API의 키 적용과 실제 수집을 확인했습니다. 실제 준공 근거·공공임대·SH/GH 범위 확대는 아래 추가 서비스별로 구분합니다. 다른 PoC의 키를 자동 공유하지 않습니다.

2026-10-02 소급 수집: 기존 세 키로 정책 기원 2018년부터 조회하여 **청약공고 1,110·인허가 3,870·누적 주소 조회 52개**, 총 5,032개를 보관했습니다. 이 기존 수집 범위를 유지하는 데 추가 키가 필요하지 않습니다. 이후 시군구 경계 56개도 기존 VWorld 키로 수집했습니다. 최초 검증은 [API_KEY_VERIFICATION.md](API_KEY_VERIFICATION.md), 수집 범위는 [HISTORICAL_COLLECTION.md](HISTORICAL_COLLECTION.md), 현재 연결·통계 기준은 [POLICY_PROGRESS_AND_MATCHING.md](POLICY_PROGRESS_AND_MATCHING.md)에 기록했습니다.

## 추가 연결 점검 결과

| 우선순위 | 연결할 원천 | 키 / 활용신청 | 준비 상태와 범위 |
| --- | --- | --- | --- |
| 우선 | [건축HUB 건축물대장정보 15134735](https://www.data.go.kr/data/15134735/openapi.do) | 별도 API 활용신청. 설정명 `POC10_BUILDING_REGISTER_SERVICE_KEY` | **신규 키 인증 정상·320건 적재**. 6개 법정동별 첫 100건 중 주거용 표제부. 대장 PK·주소·과거 사용승인일을 보관. 기존 재고를 포함하며 신규 공급 실적 아님 |
| 공공임대 보완 | [LH 분양임대공고문 15058530](https://www.data.go.kr/data/15058530/openapi.do) | 해당 서비스 활용신청. `POC10_LH_NOTICE_SERVICE_KEY` | **인증 정상·3,050건 적재**. 2018~2026 서울·경기 분양·임대 전체 페이지. 비주거 230건·복수지역 배분 미확인 1건은 표시 제외하고 원문 보존. 공고 목록은 세대수·실제 입주량 미제공 |
| 지역 총계 대조 | [국토교통 통계누리 공유서비스](https://stat.molit.go.kr/portal/api/info.do) | 별도 인증키와 대상 통계표 신청. `POC10_MOLIT_STAT_API_KEY` | **인증 정상·432건 적재**. 월별 착공·준공 2018.01~2026.08, 연간 인허가 2018~2025. 민간 포함 전체 통계를 개별 정책 실적에 합산하지 않음. 월별 인허가 5375 API는 개방 취소 응답으로 연간 자료 사용 |
| 서울 계획·이력 | [SH 주택분양 공급계획](https://www.data.go.kr/data/15008820/fileData.do) | **Open API 각각 활용신청**, `POC10_SH_SERVICE_KEY` | **인증 정상·20행 적재**. 2019·2020·2023·2026 공개본, 최신 4행. 공개본 간 중복 합산 금지 |
| 서울 사업·위치 | [SH 공공재개발·재건축](https://www.data.go.kr/data/15124798/fileData.do) | **Open API 각각 활용신청**, `POC10_SH_SERVICE_KEY` | **인증 정상·16개 사업 적재**. 기준일 2023-11-02. 전체 세대수·임대 부분·주소·과거 추진현황 |
| 서울 재고 보완 | [SH 주택관리현황](https://data.seoul.go.kr/dataList/OA-12027/S/1/datasetView.do) | **현재 확인 XLSX는 키 불필요** | 2026 등 연도별 공식 파일. 관리 재고·단지 자료이며 신규 공급 실적과 구분. 파일 수집기 준비 단계 |
| 경기 범위 확대 | [GH 재건축매입임대현황](https://www.data.go.kr/data/15112600/fileData.do) | **현재 확인 CSV는 키 불필요** | 매입임대 사업·물량·주소. GH 전체 신축사업 범위를 대체하지 않음. 파일 수집기 준비 단계 |

건축물대장의 사용승인일은 주택법 사용검사나 실제 입주와 같은 사건으로 단정하지 않습니다. 이번 세 키는 HOME 전용 실행 설정에 적용하고 실제 수집했습니다. `API 테스트 데이터`에서 유형·자료 연도·지역을 선택하고 상세 근거·날짜·CSV를 조회합니다. `API 연결 안내`와 `데이터 검증`은 실제 배치 성공·건수·최근 시각을 표시합니다. SH 두 Open API는 연결을 완료했습니다. 별도 SH 관리 재고·GH 파일과 지역 포털 선택 API의 준비 상태는 별도로 유지합니다. [SH 검증 기록](SH_API_VERIFICATION.md). [신규 API 검증 기록](ADDITIONAL_API_VERIFICATION.md).

### 공공데이터포털 신청 방법

1. 위 **건축물대장정보** 서비스에 로그인하여 `활용신청`을 진행합니다. 기존 **주택인허가정보 15136560** 승인과 별개입니다.
2. 목적은 `HOME 서울·경기 주택사업 진행·준공 근거 검증`, 서비스 URL은 `https://www.minslab.kr/poc/home/`로 작성합니다. 화면의 이용기간·필요 기능·호출량을 확인합니다.
3. 승인 후 마이페이지에서 **해당 서비스의 일반 인증키(Decoding)**를 확인합니다. 기존 키와 동일하면 재발급할 필요 없이 해당 서비스 승인·등록 상태를 확인합니다. 별도 값이면 HOME `.env`의 신규 설정명에 저장합니다. 실제 시험 호출에서 승인 상태를 다시 확인합니다.
4. LH 공고 보완도 위 LH 서비스에서 별도로 활용신청한 뒤 같은 절차를 진행합니다. 건축물대장의 현재 공식 안내는 개발·운영 자동승인이지만 실제 이용 상태는 마이페이지에서 확인합니다.

### SH 두 서비스의 신청·연결

공공데이터포털의 15008820과 15124798 각각에서 `Open API` 탭 → `활용신청` → 승인 상태를 확인합니다. 해당 파일 페이지가 제공하는 파일 변환 API(JSON/XML)입니다. 파일 다운로드에는 키가 필요하지 않지만 API 호출에는 승인된 포털 인증키가 필요합니다. 같은 키라도 서비스별 승인 여부가 다르므로 둘 다 실제 호출해야 합니다.

이번 저장된 키로 두 서비스 모두 HTTP 200을 확인하고 `POC10_SH_SERVICE_KEY` 전용 설정에 적용했습니다. 추가 키 발급은 필요하지 않습니다. 이전 서울 포털 설정란에 저장된 값은 SH ODcloud 호출로 검증되었으며 서울 열린데이터광장 API 승인 확인으로 해석하지 않습니다.

### 통계누리·서울·경기 선택 연결

통계누리는 공식 공유서비스에 로그인한 뒤 `서비스신청 및 내역 → 인증키신청 및 이용내역`과 `OPEN API 신청 및 신청현황`에서 필요한 주택건설 통계표·양식을 선택합니다. 키 외에 시도·단위·시계열·양식 번호를 확인해야 합니다.

서울·경기 자체 Open API는 **대상 주택 데이터셋이 API로 제공될 때만** 별도 키를 사용합니다. SH 15008820·15124798은 공공데이터포털 ODcloud API이므로 서울 열린데이터광장 키가 아닌 승인된 공공데이터포털 키를 사용합니다. 별도 SH 관리 재고·GH 파일을 다운로드하는 데 아래 지역 포털 키는 필요하지 않습니다.

- [서울 열린데이터광장 이용 안내](https://data.seoul.go.kr/together/guide/useGuide.do): 서울시 회원가입·로그인 → 인증키 신청/관리 → HOME 활용 목적·URL 등록. 추후 설정명 `POC10_SEOUL_OPEN_API_KEY`. 대상 데이터셋과 서비스명 확정 전 단계입니다.
- [경기데이터드림 Open API 이용 안내](https://data.gg.go.kr/portal/openapi/usagePage.do): 로그인 → 인증키 발급 → 활용용도·사용 URL·설명 입력 → 발급 요청. 추후 설정명 `POC10_GG_OPEN_API_KEY`. 대상 주택사업 데이터셋과 필터 확인 후 연결합니다.

| 서비스 / 발급 페이지 | HOME 환경변수 | 준비할 정보 | 활용 |
| --- | --- | --- | --- |
| [한국부동산원 청약홈 분양정보 조회](https://www.data.go.kr/data/15098547/openapi.do) | `POC10_CHEONGYAK_SERVICE_KEY` | 해당 API 활용승인, 일반 인증키 원문(Decoding), 승인된 호출량 | 모집공고·공급세대수·주택관리번호·입주예정월 |
| [국토교통부 건축HUB 주택인허가정보](https://www.data.go.kr/data/15136560/openapi.do) | `POC10_BUILDING_HUB_SERVICE_KEY` | 해당 API 활용승인, 일반 인증키 원문(Decoding), 승인된 조회 서비스·호출량 | 주택 인허가·착공·사용검사 정보를 사업과 연결 |
| [VWorld 오픈API 안내](https://www.vworld.kr/v4po_openapi_s001.do) | `POC10_VWORLD_API_KEY` | 실제 사용 URL `https://www.minslab.kr` 및 `https://minslab.kr`에 대한 도메인·서비스 이용 설정 | 주소 좌표·행정구역 경계, 지도 확장(선택) |

청약홈과 건축HUB는 공공데이터포털에서 각각 활용신청을 해야 합니다. 인증키가 있어도 개별 API의 활용승인 여부를 확인합니다. VWorld의 주소 검색·공간 API와 배경지도는 서비스별 사용조건과 허용 도메인을 확인합니다.

VWorld는 [오픈API 안내](https://www.vworld.kr/v4po_openapi_s001.do)에 접속한 뒤 **회원가입/로그인 → 오픈API → 인증키발급**으로 이동합니다. 현재 공식 메뉴의 [인증키 발급 경로](https://www.vworld.kr/dev/apiKey_i001.do)는 로그인이 필요합니다. 기존 `/dev/v4dv_api2_s001.do` 주소는 2026-10-02 확인 시 404였으므로 사용하지 않습니다.

## 설정 위치

실제 키는 `PoC/10-home/.env`에 보관합니다. 값 자체를 문서, Git, 공개 화면이나 채팅 메시지에 기록하지 않습니다.

```dotenv
POC10_CHEONGYAK_SERVICE_KEY=
POC10_BUILDING_HUB_SERVICE_KEY=
POC10_VWORLD_API_KEY=
POC10_BUILDING_REGISTER_SERVICE_KEY=
POC10_LH_NOTICE_SERVICE_KEY=
POC10_MOLIT_STAT_API_KEY=
POC10_SH_SERVICE_KEY=
```

`.env`는 Git에서 제외하고 권한 `600`으로 관리합니다. 홈페이지에는 설정 여부만 표시합니다. 기존 DB 비밀번호와 내부 인증 비밀값을 보존한 상태에서 필요한 항목만 추가합니다.

## 실제 연결 단계

8개 API connector는 Source Registry에 `implemented=True`, `collection_mode=TEST_SAMPLE`, `manual_only=True`로 등록했습니다. 기본 자동수집은 최신 원천 7개와 과거 원천 2개를 실행합니다. API는 관리자 요청 또는 `python -m scripts.collect --samples`로 호출합니다. **키 입력만으로 정책 사업·공급 실적·지도가 자동 확정되지는 않습니다.**

현재 완료: 공식 명세와 실제 endpoint 확인, 지역·기간·법정동·식별자 검증, 청약홈·LH 과거 전체 조회 페이지와 건축물대장 첫 페이지 주거용 표본, 월별 착공·준공 및 연간 인허가 총계 적재, 주소 조회, 키 제거와 hash 검증, 재수집 멱등성 및 홈페이지 조회. 청약홈 필터 집계는 `matchCount`를 사용하고 전역 `totalCount`와 구분합니다. 건축HUB의 큰 PK는 문자열로 저장합니다.

현재 단계: 본 모집공고의 LH·지구·블록 일치 검토 연결, 승인 대기 통계, 담당자 정책 조정·최종 승인·해제와 지도 표출을 구현했습니다. 인허가 PK·주소의 사업 교차검증과 SH/GH 전체 범위 확보, 실제 준공·입주 실적 연결은 추가 원천·수집기 검증이 필요합니다. 건축HUB의 `useInsptDay`·`useInsptSchedDay`는 명세 설명과 필드명 의미를 검토하기 전 준공·사용검사 실제일로 확정하지 않습니다.

건축물 사용승인은 주택법상 사업계획승인·사용검사와 동일한 사건이 아닐 수 있어 필드의 법적 의미를 구분합니다. 좌표를 확보하지 못한 사업에는 지도 위치를 임의 생성하지 않습니다.

`POC10_DB_PASSWORD`와 `POC10_INTERNAL_SECRET`은 내부 운영용으로 이미 설정했으며 외부에서 발급받는 API 키가 아닙니다.

## 2026-10-03 과거 자료 수집 연결 점검

추가 API 키 신청 없이 LH 공식 게시물 첨부와 공개 CSV를 직접 수집하도록 연결했다. `.env`와 `.env.example`의 기존 9개 키 항목에는 신청·이용 안내 링크를 주석으로 넣었다. 기존 키 값은 보존하고 `.env` 권한 0600을 유지했다. 서울 열린데이터광장·경기데이터드림 키도 설정되어 있으나, 해당 키 설정만으로 새 주택 데이터셋을 연결했다고 표시하지 않는다.

| 원천 | 수집 방식 | 추가 키 | 원본 링크 |
| --- | --- | --- | --- |
| LH 2020~2025 공공분양 공급현황 | 게시물 XLSX 첨부 자동 내려받기 | 불필요 | [LH 주택(분양)공급 현황](https://www.lh.or.kr/board.es?act=view&bid=0007&list_no=727605&mid=a10103040000) |
| LH 연간 입주계획 | 공개 HWPX·DOCX 첨부 자동 내려받기 | 불필요 | [LH 신규입주계획](https://www.lh.or.kr/board.es?act=view&bid=0007&list_no=654827&mid=a10103010000) |
| LH 단지정보 | 공공데이터포털 공개 CSV 자동 내려받기 | 불필요 | [LH 전국 아파트 단지정보](https://www.data.go.kr/data/15080989/fileData.do) |

공공데이터포털의 LH 단지정보에는 변환 Open API도 있지만, 같은 원본을 공개 CSV로 확보할 수 있어 별도 활용신청을 요구하지 않는다. 기존 LH 공고 API와 위 파일 수집은 별도 원천으로 관리한다. LH 공사진행현황 상세 이력과 2018 리츠 투자보고서는 추가 API 키 없이 크롤링 연결했다. 공개 이력이 없는 연도·블록 및 SH·GH 실제 공정률 전체는 추가 원본 확인이 필요하다.


실제 공정률 조회: [LH 블록별 공사진행현황](https://apply.lh.or.kr/lhapply/land/cwsttList.do?mi=1352) → `lh_progress`, [2018년 NHF 제6호 투자보고서](https://www.lh.or.kr/boardDownload.es?bid=0028&list_no=651950&seq=1) → `lh_reit_progress`. 두 원천은 키 신청·추가 `.env` 항목 없이 자동 수집한다. 홈페이지 **정책 흐름·과거 자료**에서 조회 및 공정률 CSV 다운로드가 가능하다. 공정률은 공급·입주 달성률과 별도 지표다.

## 2026-10-05 공급량 연도별 비교

기존 `POC10_MOLIT_STAT_API_KEY`로 [국토교통 통계누리 분양실적](https://stat.molit.go.kr/portal/cate/statMetaView.do?hRsId=488) 양식 5557/1이 조회되어 새 키 신청 없이 월별 분양승인 2018.01~2026.08 서울·경기 208행을 추가 수집했다. 기존 세 지표 432행과 합쳐 640행이다. 자세한 기간·연도별 수치는 [ANNUAL_SUPPLY.md](ANNUAL_SUPPLY.md)에 기록했다.

## 2026-10-12 보완 작업 이후

이번 전국 공급통계 확대·인천 KOSIS 이력·건축HUB 복구에는 추가 키가 필요하지 않았다. 실제 키는 계속 `.env`에만 저장한다. 전국 통계는 보관한 공식 응답을 해시 검증 후 확대 추출했으며 이후 국토부 수집 성공 시 같은 확대 경로를 실행한다.

iH 임대주택 재고·계약·공가 API는 기존 설정으로 재시도했으나 HTTP 504였다. 원천 0건 또는 새 키 필요로 판정하지 않는다. [iH 활용신청](https://www.data.go.kr/data/15168460/openapi.do)의 승인 상태와 제공기관 응답을 확인하고, 오류가 계속되면 조회시각·HTTP 504를 제공기관에 전달한다. 설정명은 `POC10_IH_SERVICE_KEY`이고 없으면 기존 `POC10_LH_NOTICE_SERVICE_KEY`를 대체 사용한다. 키가 같아도 서비스 활용승인은 별도다.

[데이터 구조·보완 결과·남은 공백 설명자료](HOME_REMEDIATION_STATUS_20261012.html)에 수집 범위, DB 매칭, 담당자 입력 및 후속 조치를 함께 정리했다.
