# Data Sources

## 현재 상태

2026-08-12 기준으로 발급 키를 사용해 아래 8개 서비스의 현행 resource, 필수 조회인자, JSON envelope와 출력 필드를 확인했습니다. 각 서비스는 최소 1건 또는 공식 빈 결과로 인증과 응답 contract를 통과했습니다.

기존 회의록 API는 2025년 서비스 중단 안내가 있었고 본회의 회의록, 위원회 회의록, 회의별 의안목록, 본회의 표결정보 등의 대체 서비스가 안내됐습니다. 기존 의원·의사일정·의안 API도 2026년 통합 API 등으로 대체된다는 안내가 있어 과거 endpoint를 재사용하지 않습니다.

## 조사 대상

| Official API | 사용 목적 | 상태 |
|---|---|---|
| [국회일정 통합 API](https://www.data.go.kr/data/15126132/openapi.do) | 오늘 예정·개최 회의 | `ALLSCHEDULE` 검증 완료 |
| [국회의원 정보 통합 API](https://www.data.go.kr/data/15126133/openapi.do) | 의원 식별 | `ALLNAMEMBER` 검증 완료 |
| [의안정보 통합 API](https://www.data.go.kr/data/15126134/openapi.do) | 의안 처리 흐름 | `ALLBILLV2`, `ERACO` 필수 검증 완료 |
| [본회의 회의록](https://www.data.go.kr/data/15126007/openapi.do) | 본회의 공식 원문 | `nzbyfwhwaoanttzje`, `DAE_NUM`·`CONF_DATE` 필수 검증 완료 |
| [위원회 회의록](https://www.data.go.kr/data/15126038/openapi.do) | 위원회 공식 원문 | `ncwgseseafwbuheph`, `DAE_NUM`·`CONF_DATE` 필수 검증 완료 |
| [회의별 의안목록](https://www.data.go.kr/data/15126161/openapi.do) | 회의-의안 연결 | `VCONFBILLLIST` 검증 완료 |
| [국회의원 본회의 표결정보](https://www.data.go.kr/data/15125948/openapi.do) | 공식 표결 | `nojepdqqaweusdfbi`, `AGE`·`BILL_ID` 필수 검증 완료 |
| [위원회 현황 정보](https://www.data.go.kr/data/15126037/openapi.do) | 위원회 정규화 | `nxrvzonlafugpqjuh` 검증 완료 |

## 검증 기록 형식

공공데이터포털은 개발단계 자동승인, 운영단계 심의승인으로 안내합니다. 서비스키는 프로젝트 `.env`의 `NATIONAL_ASSEMBLY_API_KEY`에만 저장하며 URL·manifest·로그에서 제거합니다.

실시간 의사중계 상태는 현재 별도의 공식 Open API 존재를 확인하지 못했습니다. 일정 API 응답으로 상태 표현 가능 여부를 먼저 검증하며, 확인 전에는 source catalog에 추가하지 않습니다.

현행 resource와 필드 계약은 `backend/app/adapters/national_assembly/contracts.py`에 기록합니다. 공식 응답은 Git에 넣지 않고 `data/raw/`에 저장합니다. repository fixture는 실제 값이 아닌 명시적인 합성 JSON/XML만 사용합니다.

일정 API는 `Type=json` 요청에도 HTTP Content-Type을 XML로 반환하는 경우가 확인되어 raw 저장 시 본문 signature를 우선 판별합니다.

## 공식 확인 출발점

위원회 회의록은 같은 `CONF_ID`가 `SUB_NAME`별 여러 행으로 반복됩니다. 회의별 의안목록은 `CONF_ID`로 연결되며 의안이 없는 회의는 공식 빈 결과를 반환합니다. 두 경우 모두 오류나 중복 회의로 해석하지 않습니다.


의안정보 통합 API의 `ERACO`는 `제22대`처럼 한글 접두·접미가 포함된 값을 요구합니다. `22`로 요청하면 인증 오류가 아니라 공식 빈 결과가 반환되므로 수집 설정에서 두 값을 혼용하지 않습니다.

`ALLBILLV2`의 `PDF_URL1`은 복수 FileGate URL을 쉼표로 제공할 수 있습니다. 첫 번째 공식 PDF를 정상 redirect로 받아 raw-first 보존하고, `pdftotext -layout`으로 제안설명·전문위원 검토 구획만 source page와 함께 추출합니다. PDF가 없거나 구획을 찾지 못하면 내용을 생성하지 않습니다.
- 국회 Open API: `https://open.assembly.go.kr/`
- 공공데이터포털 국회사무처 Open API 현황: `https://www.data.go.kr/data/15125891/openapi.do`
- 회의록 API 중단 공지: `https://www.data.go.kr/bbs/ntc/selectNotice.do?originId=NOTICE_0000000004011`
- 의원·일정·의안 API 중단 공지: `https://www.data.go.kr/bbs/ntc/selectNotice.do?originId=NOTICE_0000000004483`
## 국무회의 공식 source

| 공식 출처 | 사용 목적 | API 신청 |
|---|---|---|
| https://www.ktv.go.kr/ | 국무회의 공식 생중계·자막·다시보기 탐색 | 없음; 자막 track과 재처리 조건 검증 필요 |
| https://www.president.go.kr/briefings | 청와대 국무회의 브리핑·공개 발언 | 없음 |
| https://www.president.go.kr/speeches | 대통령 모두발언 원문 | 없음 |
| https://www.korea.kr/briefing/stateCouncilList.do | 국무회의 결과·안건 브리핑 | 없음 |
| https://www.opm.go.kr/opm/news/press-release.do | 총리 모두말씀·보완자료 | 없음 |

행정안전부 통계연보 국무회의 운영 API는 연간 횟수·의안분류 통계로, 발언·주제·부처 분석에는 사용하지 않습니다. 정책브리핑 RSS는 2026-07-01 제공이 중단됐으므로 공식 HTML과 첨부 문서를 content hash 기반으로 버전 보존합니다.

국무회의 수집기는 목록·상세 selector와 첨부 링크를 contract로 검증한 뒤에만 활성화합니다. 공개되지 않은 발언은 추정하거나 뉴스 기사로 보완하지 않습니다.

### 정책브리핑 국무회의 HTML contract 검증 결과

- 목록 https://www.korea.kr/briefing/stateCouncilList.do 의 stateCouncilView.do?newsId= 링크, 제목, 게시일을 사용합니다.
- 상세의 .article_body .view_cont를 공식 본문으로 사용하고 【소관 : ...】이 명시된 안건만 소관 부처와 함께 구조화합니다.
- 2026-08-12 표본은 제35~26회 10건, 명시 소관 안건 49건이며 제35회는 7건입니다.
- 목록과 상세 HTML을 먼저 raw 저장하고 content hash·parser version·조회시각을 snapshot에 남깁니다.
- 소관 부처에서 대상 국회 위원회로의 표시는 공식 관계가 아니라 RULE LINK로 구분합니다.
- 청와대 브리핑 공개 AJAX 목록과 .view_txt.ck-content 상세 본문을 raw-first로 저장합니다.
- 정책브리핑과 청와대 자료는 회차와 게시일이 모두 같을 때만 자동 연결합니다. 최근 10건 중 6건이 연결됐고 공식 대통령 메시지 문단 35개를 확인했습니다.

### LIVE/PROVISIONAL 후보

우선순위는 `KTV 기계 판독 공식 자막 > 검증된 스트리밍 STT > 종료 후 일괄 STT`입니다.

| 후보 | 역할 | credential | 채택 조건 |
|---|---|---|---|
| KTV 공식 자막 track | LIVE 1순위 | 없음 | 별도 track/segment 접근과 이용조건 검증 |
| Azure Speech | LIVE fallback, 종료 후 보정 | Azure Speech key | ko-KR 실시간 전사·화자 분리·지연 품질 표본 통과 |
| Amazon Transcribe | 비교 fallback | AWS credential | ko-KR streaming 및 필요한 화자 기능 표본 통과 |
| 자체 Whisper 계열 | PROVISIONAL 또는 장애 fallback | 없음 | GPU/지연·화자 분리·운영비 검증 |
| 외부 회의록 서비스 | 보조 PROVISIONAL | 서비스별 | 공식 API, 재사용 조건, timestamp, source URL 모두 검증 |

회의록 소비자 앱의 화면이나 비공개 export를 긁어오는 방식은 사용하지 않습니다. LIVE 결과는 수정 가능한 segment revision으로 저장하고, 공식 브리핑·발언문이 게시되면 동일 회의에 연결해 `MATCHED`, `UNRESOLVED`, `CONFLICT`로 대조합니다.

합성 LIVE fixture는 파이프라인·화면 검증 전용이며 공식 source catalog에 포함하지 않습니다. 결과는 항상 `SYNTHETIC_FIXTURE`, `PROVISIONAL`, `SIMULATION`으로 표시합니다.

### LIVE source contract 검증 결과

- 국회: `https://assembly.webcast.go.kr/main/service/live_list.asp` 공개 JSON에서 대상 위원회의 `xstat`, `xcgcd`, 회의명, 썸네일, 퀵 VOD, 자막 서비스 제공 여부를 판별합니다.
- 국회 자막: LIVE 플레이어가 `live_play.asp` 응답의 `xsami`를 자막 서버로 사용함을 확인했습니다. 실제 자막 segment 계약은 대상 위원회 방송 중에만 최종 검증합니다.
- 국회 영상: 같은 `live_play.asp` 응답의 검증된 `xhls` profile 중 HTTPS `.m3u8` 주소만 LIVE 화면의 native video 입력으로 사용합니다. 브라우저 HLS 지원이나 원본 CORS 정책으로 재생에 실패할 수 있으며 이때 다른 주소를 추정하지 않습니다.
- 국회 자막 메시지: 공개 플레이어 JavaScript에서 `segment`, `transcript`, `transcripts`, `scd`, `final` 필드를 확인해 파서를 고정했습니다. 대상 위원회 방송 중 실제 WebSocket 메시지로 최종 회귀 검증하기 전까지 `READY_TO_CAPTURE`는 연결 준비 상태이지 공식 발언 확정 상태가 아닙니다.
- 감시 주기: `live-monitor` worker가 30초마다 목록을 검사하고 원본 hash·parser version·조회 시각을 보존합니다. 대상 LIVE에 한해 상세 player 계약을 추가 수집합니다.
- KTV: 콘텐츠 ID, `WeNMediaPlayer`, HLS player library와 방송 본문은 확인했지만 별도 VTT/자막 URL은 공개 HTML에서 확인되지 않았습니다. `caption_contract_status=UNVERIFIED`를 유지합니다.
- 이용 제한: 국회 회의 영상은 공식 도움말에 따라 상업적 이용 대상에서 제외합니다. POC의 영상 표출은 내부 검증 범위이며 외부 배포 전 이용 범위와 재송출 조건을 다시 확인합니다.

### 위원회 공식 회의록 본문 contract 검증 결과

- 위원회 회의록 API의 `CONF_LINK_URL`은 회의정보 HTML이며 `type=view`로 전환하면 같은 공식 사이트의 본문 뷰를 반환합니다. 직접 요청은 400일 수 있어 사이트 첫 방문으로 발급된 공개 세션 쿠키와 동일 사이트 Referer가 필요합니다.
- 본문은 `#minutes`, `.speaker[id]`, `.spk_sub[id]`로 발언자 묶음과 문장 위치를 제공합니다. `data-name`, `data-pos`, `itemN` class도 함께 보존합니다.
- 2026-07-30 법제사법위원회 `CONF_ID=N054353` 표본은 55개 발언 문장으로 추출됐고 공식 화면이 `임시회의록`이라고 명시하므로 `PROVISIONAL`로 저장합니다.
- PDF 다운로드도 5면 `application/pdf`로 확인했지만 동일 발언을 더 정밀한 source span으로 제공하는 HTML을 우선 계약으로 채택했습니다. HTML 계약 변경 시 PDF/HWP fallback은 별도 품질 검증 후 활성화합니다.
- 정본이 게시될 때까지 1시간마다 같은 URL을 재수집하며 content hash가 바뀌면 새 `SourceDocumentVersion`으로 추가합니다.
