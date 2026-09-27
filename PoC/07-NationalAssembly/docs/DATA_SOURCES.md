# Data Sources

## 현재 상태

2026-09-10부터 국회 실시간 범위는 예산결산특별위원회·법제사법위원회·행정안전위원회와 본회의로 한정합니다. `정기국회`, `정기회`, `국정감사`, `국감`은 본회의의 표시 분류에만 사용하며, 이 문구만으로 국방위·교육위 등 다른 위원회까지 수집하지 않습니다.

국회 공식 WebSocket 자막은 정본 우선 소스입니다. 45초 무수신 때만 같은 공식 중계 HLS 오디오를 Mistral STT로 보완하고, 공식 자막이 90초 안정적으로 회복되면 다시 공식 자막을 선택합니다. KTV 국무회의 HLS master manifest는 2026-09-09 재검증에서도 `EXT-X-MEDIA:TYPE=SUBTITLES` 또는 VTT track을 제공하지 않아 현재는 Mistral STT가 필수입니다. 화면에 보이는 영상 내 번인 자막은 기계 판독 자막으로 간주하지 않습니다.

2026-08-12 기준으로 발급 키를 사용해 아래 8개 서비스의 현행 resource, 필수 조회인자, JSON envelope와 출력 필드를 확인했습니다. 각 서비스는 최소 1건 또는 공식 빈 결과로 인증과 응답 contract를 통과했습니다.

기존 회의록 API는 2025년 서비스 중단 안내가 있었고 본회의 회의록, 위원회 회의록, 회의별 의안목록, 본회의 표결정보 등의 대체 서비스가 안내됐습니다. 기존 의원·의사일정·의안 API도 2026년 통합 API 등으로 대체된다는 안내가 있어 과거 endpoint를 재사용하지 않습니다.

일정 화면은 `ALLSCHEDULE` 원본의 `schedule_kind`를 유지합니다. 달력 셀에는 `위원회`만 표시하고, 선택 날짜 상세에서는 위원회 일정을 먼저 표시한 뒤 `국회행사` 중 공식 `host_name`에 `의원실`이 명시된 항목을 의원실 일정으로 분리해 보여줍니다. 주최를 추정하거나 다른 국회행사를 의원실 일정으로 승격하지 않습니다.

정책 흐름 타임라인은 저장된 국무회의 공식 안건과 국회 최신 회의 보고서의 구체 주제·고유어·소관기관을 보수적으로 연결한 파생 읽기 모델입니다. 일반 단어 하나만 겹치면 연결하지 않습니다. 쟁점 변화·제도화 전환은 회의별 최신 저장 보고서 또는 공식 통합본의 구체 주제·과제와 직접 연결된 의안을 사용합니다. 과제·법안·의결 표현은 발의 확인이 아니며 직접 의안 연결과 별도 상태로 보존합니다.

국정 온톨로지 스타맵은 공개 보고서 목록과 같은 범위의 최신 저장 보고서를 입력으로 사용합니다. 격리 테스트·데모·재생 방송과 대상 3개 위원회·본회의 밖의 국회 방송은 집계에서 제외합니다. 현재 방송에 연결된 공식 회의록 문서의 `READY` 통합본이 있으면 그 본문을, 아직 없으면 보존된 LIVE/STT 초안을 선택합니다. 공식 문서 ID와 보고서 ID가 일치하지 않거나 임시 업데이트가 유예된 통합본은 공식 입력으로 사용하지 않습니다. 분류는 요청 시 로컬 규칙으로 계산하며 외부 LLM 호출이나 주기적 재합성은 없습니다. 공식·초안 입력 건수를 API에서 각각 표시합니다.

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

일정 API는 `Type=json` 요청에도 HTTP Content-Type을 XML로 반환하는 경우가 확인되어 raw 저장 시 본문 signature를 우선 판별합니다. 2026-08-24에는 `SCH_DT=YYYY-MM-DD`가 해당 날짜만 반환하는 것을 오늘·내일 응답으로 재검증했으며, `schedule-worker`는 이 필터만 사용해 향후 7일을 10분마다 raw-first 동기화합니다.

국회의원 정보 통합 API는 전체 페이지를 raw-first로 하루 한 번 수집합니다. `GTELT_ERACO`에 현행 대수가 있고 `DTY_NM`이 비어 있지 않은 행만 현역 집계에 포함하며, 정당·선출구분은 대수 배열과 같은 위치의 `PLPT_NM`·`ELECD_DIV_NM` 값을 사용합니다. 화면에는 기준 대수, 수집시각, 공식 출처와 API 표기 시차 가능성을 함께 표시하고 의원 개별 연락처는 스냅샷에 복제하지 않습니다.

## 공식 확인 출발점

위원회 회의록은 같은 `CONF_ID`가 `SUB_NAME`별 여러 행으로 반복됩니다. 회의별 의안목록은 `CONF_ID`로 연결되며 의안이 없는 회의는 공식 빈 결과를 반환합니다. 두 경우 모두 오류나 중복 회의로 해석하지 않습니다.

본회의 방송은 위원회 회의록 API가 아닌 `plenary_minutes`의 `국회본회의` 행에서 `CONF_ID`, 서울 날짜와 회차를 확인합니다. 회의록 행과 `meeting_agendas`의 별도 의안목록은 각각 raw 보존 후 같은 회의에 연결합니다. 2026-09-27 검증에서는 제439회 제5~9차 본회의 회의록이 모두 게시됐고, 제9차 `N054488`의 공식 의안목록은 73행이었습니다. 회의록 78행 중 완전히 동일한 1행은 원본에 남기고 canonical 항목 77개로 중복 제거합니다.


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
| https://www.korea.kr/briefing/policyBriefingList.do | 부처 정책 브리핑 대본 | 없음 |
| https://www.korea.kr/briefing/pressReleaseList.do | 부처 보도자료·PDF 첨부 | 없음 |
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
- 부처보고 내용은 같은 부처, 구체 정책 핵심어, 회의 당일 또는 이전 21일 조건이 모두 맞는 정책 브리핑·보도자료만 연결합니다. 회의 당일 후속조치 자료를 이전 원대책보다 우선하며 HTML 본문이 안내문뿐이면 PDF 첨부를 raw-first로 저장해 실행 문단을 추출합니다.
- LIVE 기록이 없는 회차도 `공식 부처 브리핑/보도자료 → 공식 대통령실 브리핑의 사실 설명 → 공식 결과문 상세 요약` 순으로 읽기 모델을 완성합니다. 대통령 지시·당부 문장은 보고 내용에서 제외해 별도 지시 영역에 둡니다. 어느 공식 출처에도 상세 내용이 없으면 제목을 내용처럼 재작성하지 않고 `공식자료만 반영 · 상세내용 미공개`로 확정합니다. 이는 수집 대기가 아니라 공개된 공식자료의 한계를 명시한 최종 상태입니다.

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

### LIVE source contract 검증 결과

- 국회: `https://assembly.webcast.go.kr/main/service/live_list.asp` 공개 JSON에서 대상 위원회의 `xstat`, `xcgcd`, 회의명, 썸네일, 퀵 VOD, 자막 서비스 제공 여부를 판별합니다.
- 국회 자막: LIVE 플레이어가 `live_play.asp` 응답의 `xsami`를 자막 서버로 사용함을 확인했습니다. 실제 자막 segment 계약은 대상 위원회 방송 중에만 최종 검증합니다.
- 국회 영상: 같은 `live_play.asp` 응답의 검증된 `xhls` profile 중 HTTPS `.m3u8` 주소만 LIVE 화면의 native video 입력으로 사용합니다. 브라우저 HLS 지원이나 원본 CORS 정책으로 재생에 실패할 수 있으며 이때 다른 주소를 추정하지 않습니다.
- 국회 자막 메시지: 공개 플레이어 JavaScript에서 `segment`, `transcript`, `transcripts`, `scd`, `final` 필드를 확인해 파서를 고정했습니다. 대상 위원회 방송 중 실제 WebSocket 메시지로 최종 회귀 검증하기 전까지 `READY_TO_CAPTURE`는 연결 준비 상태이지 공식 발언 확정 상태가 아닙니다.
- 감시 주기: `live-monitor` worker가 30초마다 목록을 검사하고 원본 hash·parser version·조회 시각을 보존합니다. 대상 LIVE에 한해 상세 player 계약을 추가 수집합니다.
- KTV 편성: `https://www.ktv.go.kr/onair/scheduleAjax`의 `ONAIR`, `internet_yn`, 회차명과 편성 시각으로 국무회의 시작·종료를 판정합니다.
- KTV 영상: 공식 온에어 페이지 `https://www.ktv.go.kr/onair/tv`가 사용하는 `https://hlive.ktv.go.kr/live/klive_h.stream/playlist.m3u8`만 표시합니다.
- KTV 자막: 2026-08-25 제37회 국무회의 표본의 HLS manifest와 공식 페이지에서 별도 VTT·subtitle group을 확인하지 못했습니다. `caption_contract_status=UNAVAILABLE_NO_MACHINE_CAPTIONS`로 표시하며 자막이나 화자를 추정하지 않습니다.
- 이용 제한: 국회 회의 영상은 공식 도움말에 따라 상업적 이용 대상에서 제외합니다. POC의 영상 표출은 내부 검증 범위이며 외부 배포 전 이용 범위와 재송출 조건을 다시 확인합니다.

### 위원회 공식 회의록 본문 contract 검증 결과

- 위원회 회의록 API의 `CONF_LINK_URL`은 회의정보 HTML이며 `type=view`로 전환하면 같은 공식 사이트의 본문 뷰를 반환합니다. 직접 요청은 400일 수 있어 사이트 첫 방문으로 발급된 공개 세션 쿠키와 동일 사이트 Referer가 필요합니다.
- 본문은 `#minutes`, `.speaker[id]`, `.spk_sub[id]`로 발언자 묶음과 문장 위치를 제공합니다. `data-name`, `data-pos`, `itemN` class도 함께 보존합니다.
- 2026-07-30 법제사법위원회 `CONF_ID=N054353` 표본은 55개 발언 문장으로 추출됐고 공식 화면이 `임시회의록`이라고 명시하므로 `PROVISIONAL`로 저장합니다.
- PDF 다운로드도 5면 `application/pdf`로 확인했지만 동일 발언을 더 정밀한 source span으로 제공하는 HTML을 우선 계약으로 채택했습니다. HTML 계약 변경 시 PDF/HWP fallback은 별도 품질 검증 후 활성화합니다.
- 정본이 게시될 때까지 1시간마다 같은 URL을 재수집하며 content hash가 바뀌면 새 `SourceDocumentVersion`으로 추가합니다.
