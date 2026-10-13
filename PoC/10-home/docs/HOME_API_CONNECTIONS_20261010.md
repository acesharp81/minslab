# HOME 공식 데이터 연결·API 키 신청 안내 (2026-10-10)

실제 인증값은 **`PoC/10-home/.env`**에만 저장하고, `.env.example`에는 변수 이름·설명만 둔다. `.env`의 값은 홈페이지·JSON·Git에 노출하지 않는다. 이번에 구현한 **국토부 정비사업 CSV와 LH 준공예정 CSV, GH 사용검사 PDF, 한국부동산원 단지 식별 CSV는 API 키가 필요 없으며**, 건축HUB 동별·대지위치는 기존 `POC10_BUILDING_HUB_SERVICE_KEY`를 재사용한다. 확인 시점의 `.env`에는 아래 기존 연계 키가 모두 설정돼 있다(값은 출력·복사하지 않음). 따라서 **이번 구현을 위해 새로 신청할 키는 없다.** 키가 설정됐다는 사실과 모든 대상 자료가 수집됐다는 사실은 다르다.

| 자료·용도 | 공식 신청·안내 경로 | `.env` 변수 | 지금 상태 |
|---|---|---|---|
| 건축HUB 주택인허가 기본/동별/대지위치 | [공공데이터포털 주택인허가정보](https://www.data.go.kr/data/15136560/openapi.do) → 로그인 → 활용신청 → 서비스키 확인 | `POC10_BUILDING_HUB_SERVICE_KEY` | 설정·실호출 검증. 상세는 공식 법정동 코드 기준 이어받기 수집 중; 현재 범위는 /api/coverage 확인 |
| 건축HUB 건축물대장 | [건축물대장정보](https://www.data.go.kr/data/15134735/openapi.do) → 별도 활용신청 | `POC10_BUILDING_REGISTER_SERVICE_KEY` | 설정됨; 이번 상세 수집에 사용하지 않음 |
| 서울 정비사업 현황·후속 원고시 대조 | [서울 열린데이터광장 인증키 신청](https://data.seoul.go.kr/together/mypage/actkeyMain.do) → 서울시 로그인 → 일반 인증키 신청. 대상 [정비사업 현황](https://data.seoul.go.kr/dataList/OA-20281/A/1/datasetView.do)의 서비스명·공개 조건 확인 | `POC10_SEOUL_OPEN_API_KEY` | 설정됨; 대상 안내의 HTTP `:8088` 대신 안전한 HTTPS 경로가 확인되지 않아 실제 키 호출·수집은 보류. 원고시 연결도 미구현 |
| 경기데이터드림에서 **API가 확인된 개별 자료** | [OpenAPI 사용방법](https://data.gg.go.kr/portal/openapi/usagePage.do) → 대상 데이터셋/명세 확인 → 로그인·인증키 발급 | `POC10_GG_OPEN_API_KEY` | 설정됨. 경기 정비사업 온누리의 동일 범위 API는 미확인; 이 키가 온누리 크롤링을 대체한다고 보지 않음 |
| 국토교통 통계누리 지역 주택 통계 | [통계누리 공유서비스](https://stat.molit.go.kr/portal/api/info.do) → OPEN API 신청·통계표 목록 확인 | `POC10_MOLIT_STAT_API_KEY` | 설정됨. 지역 총계는 개별 사업 실적에 배분하지 않음 |
| KOSIS 가구·주택·고용 | [KOSIS 공유서비스](https://kosis.kr/openapi/?sso=ok) → 로그인·OPEN API 인증키 신청 | `POC10_KOSIS_API_KEY` | 설정됨; 기존 지역 통계 수집기 사용 |
| SGIS 인구·가구·사업체 종사자 | [SGIS 인증키 발급절차](https://sgis.mods.go.kr/developer/html/newOpenApi/app/apply.html) → 로그인 → 서비스 ID·보안 Key 발급 | `POC10_SGIS_CONSUMER_KEY`, `POC10_SGIS_CONSUMER_SECRET` | 둘 다 설정됨; 기존 지역 통계 수집기 사용 |

서울시보 공덕1 고시 PDF와 국토부 고양창릉 고시 PDF도 공식 HTTPS 경로에서 키 없이 확보했다. 두 자료는 계획 변경 사건이며 사업 공급 실적이 아니다. 아래 공개 파일은 **이번 검증에서 키 없이 실제 다운로드**했다. [전국 도시정비사업 통합 데이터](https://www.data.go.kr/data/15160169/fileData.do), [LH 공공주택 준공예정현황](https://www.data.go.kr/data/15141761/fileData.do). 파일명 기준일과 원본 해시를 함께 저장하므로 같은 URL에서 내용이 바뀌어도 판본을 구분한다.

키를 새로 받거나 교체할 때는 [`PoC/10-home/.env.example`](../.env.example)의 변수 이름을 확인하고 **같은 폴더의 `.env`**에서 해당 한 줄의 `=` 오른쪽에 값만 입력한다. 건축HUB 상세 하루 배치 범위는 `POC10_BUILDING_DETAIL_DONGS_PER_BATCH=8`로 지정한다(1~8개 법정동). 공식 현존 코드에서 미수집 동을 자동 선택하며 이전 배치에서 이어받는다. 비밀키·DB 비밀번호는 `refs/`, 문서, JSON 스냅샷에 넣지 않는다. Docker 배포 시 `env_file: .env`가 API 컨테이너에 변수를 전달하며, 새 키 반영에는 API 컨테이너 재시작이 필요하다.

배포 후 키를 화면에 입력하지 않고 `/poc/home/api/connections`의 설정/수집 상태, `/poc/home/api/coverage`의 endpoint·지역·건수를 확인한다. 새 공식 CSV 2종은 기본 자동 수집 대상이다. 건축HUB 상세는 기동 후 및 기본 24시간 간격으로 제한된 법정동을 자동 수집한다. 필요할 때 `python -m scripts.collect --expand-building-details --rounds 5`로 이어받을 수 있다. 서울·경기 공식 고시 2건의 파일럿은 `--source seoul_plan_notice_pilot`, `--source gyeonggi_plan_notice_pilot`로 원문·SHA-256을 검증한다. 키가 인증되더라도 `home_coverage.population_status=PARTIAL_SCOPE`인 동안 서울·경기 전수 확보로 표기하지 않는다.
