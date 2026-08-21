# POC-07 실행 플랜 — 국무회의 × 국회

## 1. 제품 목표

POC-07은 청와대·국무회의에서 제시된 국정 주제와 국회에서 논의·의결되는 회의·의안을 공식 원문 근거로 연결한다.

핵심 질문:

- 최근 국무회의에서 어떤 주제가 논의됐고 누가 무엇을 말했는가?
- 각 주제의 소관 또는 관련 부처는 어디인가?
- 특정 부처를 선택하면 관련 발언·보고·지시만 모아볼 수 있는가?
- 같은 주제가 국회의 어느 위원회·의안·표결로 이어졌는가?
- 공식 사실, 구조화 값, AI 분류·요약을 구분해 원문까지 추적할 수 있는가?

## 2. 화면 구조

화면은 목적성이 약한 프로젝트 상태·구축 설명·달력 블록을 전면에서 제외하고 다음 네 영역만 유지한다.

1. 타이틀과 관심 부서 선택
2. 국무회의·국회 생방송과 실시간 분류; 방송이 없으면 최근 자료와 공식본 표시
3. 청와대 공식 자료의 주제·발언·소관 부처·국회 진행 시각화
4. 행안위·예결위·법사위의 회의·의안·본회의 표결 시각화

### A. 국무회의

- 상태 헤더: `LIVE 자막`, `보정 중`, `공식본 게시`를 출처·갱신시각과 함께 표시한다.
- 같은 회의에서 LIVE/PROVISIONAL/OFFICIAL 본을 탭으로 전환하고 문장별 근거를 확인한다.
- 회의 목록: 날짜 + 회차 + 주재자 + 안건 수를 한 줄로 표시한다.
- 주제 목록: 주제명 + 핵심 발언 + 관련 부처 배지를 한 줄로 표시한다.
- hover/focus 상세: 발언 요약, 발언자, 지시·보고 구분, 관련 부처, 원문 위치를 표시한다.
- 필터: 기간, 회차, 주제, 소관 부처, 관련 부처, 발언자, 지시/보고/토의.
- 부처 선택 모드: 선택 부처가 소관 또는 관련으로 연결된 주제·발언만 반환한다.

### B. 국회

- 일정: 월간 미니 달력에서 건수만 표시하고 클릭 시 상세를 연다.
- 위원회 현황: 위원회 + 회차 + 날짜 + 회의록/의안 건수를 회의별 한 줄로 표시한다.
- 의안: 제목 + 본회의 표결 결과를 의안별 한 줄로 표시한다.
- hover/focus 상세: 처리 요약, 발의자, 소관위·본회의 결과, 찬성·반대·기권 그래프, 공식 의안 링크를 표시한다.
- 필터: 위원회, 처리단계, 검색어.

### C. 연계 보기

- 주제별로 국무회의 발언·지시와 국회 회의·의안을 나란히 배치한다.
- 연결은 OFFICIAL_LINK, RULE_LINK, AI_SUGGESTED_LINK로 구분한다.
- AI가 제안한 연결은 검토 전 공식 관계로 표시하지 않는다.

## 3. 국무회의 수집 전략

국무회의는 `생중계 → 종료 후 보정 → 공식 문서`의 세 계층으로 수집한다. 뒤에 나온 자료가 앞선 자료를 덮어쓰지 않으며 같은 회의에 연결해 함께 보존한다.

### LIVE — 공식 생중계와 실시간 자막

1. KTV 국무회의 생중계 편성·콘텐츠 페이지를 주기적으로 확인해 방송 시작과 종료를 감지한다.
2. 기계가 읽을 수 있는 공식 자막 트랙이 있으면 이를 최우선 source로 사용한다.
3. 공식 자막이 영상에 합성된 화면 자막뿐이거나 별도 트랙 접근이 불가능하면, 이용조건을 확인한 뒤 방송 오디오를 스트리밍 STT로 전사한다.
4. 중간 인식 결과는 수정될 수 있으므로 segment revision을 누적하고 확정 구간만 LIVE 본문에 고정한다.
5. 화면에는 5~15초 단위로 추가된 발언을 보내되 `실시간 자동 전사·오류 가능`을 항상 표시한다.

STT MVP의 1순위 후보는 한국어 실시간 전사와 화자 분리 구성을 지원하는 Azure Speech다. Amazon Transcribe와 자체 호스팅 Whisper 계열은 비교 후보로 유지한다. 외부 회의록 서비스의 결과는 안정적인 수집 API, 재사용 조건, source timestamp를 검증한 경우에만 PROVISIONAL source로 추가한다.

### PROVISIONAL — 종료 후 보정본

- 종료된 공식 VOD를 다시 일괄 전사해 실시간 오인식, 문장 경계, 화자 구분을 보정한다.
- 인명·부처명·법안명 사전과 방송 자막을 결합하되 AI/규칙 교정 이력을 남긴다.
- 주제 요약과 부처 분류는 이 보정본을 기준으로 생성하되 공식 발언으로 오인되지 않게 표시한다.

### OFFICIAL — 게시 후 공식본

공개 공식 문서는 일정 주기로 확인해 content hash 기반으로 버전 보존한다.

1. 대한민국 청와대 president.go.kr
   - 국무회의 관련 브리핑
   - 대통령 모두발언·연설문
2. 대한민국 정책브리핑 korea.kr
   - 국무회의 결과 브리핑과 국무회의 브리핑
   - 첨부 속기자료 HWP/PDF
3. 국무조정실·국무총리비서실 opm.go.kr
   - 총리 주재 국무회의 모두말씀
   - 결과·보완 보도자료

공공데이터포털의 행정안전부_통계연보_국무회의 운영 API는 연간 개최·의안분류 통계이므로 발언·주제 분석 source로 사용하지 않는다. 정책브리핑 RSS는 2026-07-01 중단됐으므로 수집 계약에 포함하지 않는다.

공식 브리핑은 전체 회의의 축어록이 아닐 수 있다. 따라서 공식본이 게시돼도 LIVE/PROVISIONAL 전문을 삭제하거나 공식 문장으로 승격하지 않고, 시간·문장 유사도와 source span으로 대응 관계만 만든다. 일치하지 않는 내용은 `미확인`, 공식 자료와 충돌하는 내용은 `충돌`로 표시한다.

### API 신청 판단

- 공식 홈페이지·KTV 편성 및 자막 트랙 검증: 추가 API 신청 없음.
- 공식 자막 트랙을 쓸 수 있으면 STT 키도 필요 없음.
- 공식 자막 트랙을 쓸 수 없을 때: Azure Speech resource/key 또는 선택한 대체 STT credential이 필요하다. source contract 검증 전에는 신청하지 않는다.
- 국회 자료: 기존 NATIONAL_ASSEMBLY_API_KEY 계속 사용.
- 공식 사이트가 별도 콘텐츠 API를 제공하거나 수집 정책이 변경되면 contract 검증 후 신청 여부를 재결정한다.

## 4. 국무회의 데이터 모델

    ExecutiveMeeting
      ├─ N ExecutiveMeetingVersion ─ 1 SourceDocumentVersion
      ├─ N ExecutiveAgenda
      └─ N SpeechSegment
             ├─ N SegmentTopic ─ 1 PolicyTopic
             ├─ N SegmentMinistry ─ 1 Ministry
             └─ N SourceSpan

    PolicyTopic N ─ N Ministry
    ExecutiveAgenda N ─ N Ministry
    AIAnnotation N ─ N AIAnnotationEvidence
    CrossInstitutionLink
      ├─ ExecutiveMeeting / SpeechSegment / PolicyTopic
      └─ Meeting / AgendaItem / Bill

핵심 필드:

- ExecutiveMeeting: 날짜, 회차, 회의명, 주재자, 개최장소.
- SpeechSegment: 발언자, 발언 유형, 원문 텍스트, 순서, source span.
- PolicyTopic: 검토된 표준 주제명과 상·하위 주제.
- Ministry: 정부 부처 표준명, 약칭, 유효기간.
- SegmentMinistry: OWNER 또는 RELATED, 연결 근거와 확신도.
- AIAnnotation: provider, model, prompt version, 입력 source version, evidence span, 검토상태.
- CrossInstitutionLink: 연결 유형, 근거, 생성 주체, 검토상태.

공식 문서에 부처가 명시된 경우만 OFFICIAL 연결로 저장한다. 규칙·AI로 추정한 부처는 별도 annotation으로 저장하고 승인 전에는 공식 소관으로 표시하지 않는다.

## 5. 실행 단계

### Phase 0 — 목적 중심 화면 재구성

- [x] 타이틀·생방송·청와대 자료·위원회 자료의 4영역 구성
- [x] 국무회의와 국회 생방송을 나란히 배치한 LIVE 허브
- [x] 생방송 부재 시 최근 자료와 공식 정보가 같은 패널을 대체하는 구조
- [x] 청와대 자료의 주제·발언·소관·국회 진행 시각화 골격
- [x] 위원회 + 회차 한 줄과 의안 제목 + 표결 결과 한 줄 목록
- [x] 관심 분야 선택과 위원회·의안 필터 연계
- [x] hover/focus 상세 요약과 표결 그래프
- [x] 의안정보시스템 공식 PDF의 제안설명·검토 요지를 raw-first 수집해 hover 원문 발췌 보강

### Phase 1 — LIVE source contract 검증

- [x] 국회 공식 LIVE 목록과 대상 위원회 필터 계약 검증
- [x] 대상 LIVE 상세 응답과 자막 WebSocket 메시지 parser 구현
- [x] 30초 감시 worker와 화면 LIVE/OFF AIR 자동 전환
- [x] 방송 세션·source version·자막 segment·revision PostgreSQL 모델
- [x] 감시 worker의 방송 세션 idempotent 생성과 `LIVE → ENDED` 처리
- [ ] 대상 위원회 실제 방송 중 WebSocket handshake·partial/final revision 회귀 검증
- [x] 상시 caption worker의 lease·재접속·중복 방지·revision 영구 저장
- [ ] 실제 대상 위원회 방송에서 장시간 연결·재접속 검증
- [x] 중간 입장용 snapshot + 단조 증가 cursor + delta API
- [x] 국회 LIVE 화면의 저장 자막 + 2초 delta 연속 표시
- [x] 종료 60초 debounce와 DB lease 기반 review worker
- [x] final 자막의 규칙 기반 주제·대표 발언·근거 revision 저장
- [x] 실제 AUTO REVIEW 우선, 기관별 SIMULATION fallback 매거진
- [x] 종료 방송 날짜의 공식 위원회 회의록 1시간 polling
- [x] 위원회+서울 날짜 유일 후보만 공식 게시 링크로 연결
- [x] AUTO REVIEW 카드의 공식 회의록 원문 이동
- [x] 공식 회의록 HTML 본문 contract와 문장별 source span 검증
- [x] 잠정본/정본 버전 저장과 보수적 exact 문장 대조 기반 구현
- [x] LIVE·종료 방송의 명시적 OPEN 과제를 근거 revision과 함께 통합 조회
- [x] 담당 부서별 후속 과제 보드와 해당 방송의 미해결 과제 화면 이동
- [x] 종료 방송 final 자막별 공식 회의록 exact 일치·미확인 상태와 대조 공식 문장 표시
- [ ] 실제 대상 LIVE 종료 건의 final 자막과 후속 정본 간 장시간 회귀 검증
- [x] 격리된 SIMULATION 방송을 실제 DB lifecycle·snapshot/delta·review 경로로 재생하는 E2E 운영 데모
- 최근 KTV 자막 생중계와 다시보기 각 3건에서 방송 URL, 시작·종료시각, 자막 track/segment 존재 여부를 확인한다.
- 자막이 별도 기계 판독 track인지 화면에 합성된 자막인지 구분한다.
- 접근·재처리·보존 범위를 KTV 이용조건과 robots/서비스 정책에서 확인한다.
- 공식 자막을 쓸 수 없을 때 10분 표본으로 Azure Speech 실시간 전사·한국어 화자 분리 품질과 지연시간을 측정한다.

완료 기준:

- `KTV_CAPTION` 또는 `STREAMING_STT` 중 LIVE 입력 계약 하나가 확정된다.
- 방송 시작 감지부터 UI 반영까지 목표 지연과 장애 시 동작이 기록된다.
- 승인되지 않은 우회 다운로드나 출처 불명 자막을 사용하지 않는다.
- 홈페이지를 모두 닫은 상태에서도 방송 감지부터 종료까지 서버 기록이 지속된다.
- 중간 입장자는 저장된 확정 segment와 현재 생성되는 revision을 cursor 누락 없이 이어서 본다.
- 공식본 게시 후 기존 LIVE·PROVISIONAL 기록을 유지한 채 대조 상태가 추가된다.

### Phase 2 — 공식 문서 source contract 검증

- [x] 정책브리핑 국무회의 목록·상세 selector와 최근 10건 표본 검증
- [x] 공식 HTML raw-first 저장, content hash 기반 snapshot, 1시간 polling
- [x] 명시된 【소관 : ...】 안건을 화면의 주제·소관 행으로 표시
- [x] 최근 국무회의 10건의 정책브리핑 공식본을 회차별 탐색 화면에 표시한다.
- [x] 같은 회의의 청와대·정책브리핑 문서를 날짜·회차 exact match로 대조한다.
- 같은 회의의 국무조정실 문서를 추가 대조한다.
- 목록 URL, 문서 ID, 게시일, 제목, 첨부파일, 본문 selector를 검증한다.
- HTML/PDF/HWP 원본과 secret 없는 manifest를 보존한다.
- 실제 원문을 저장소 fixture로 복제하지 않고 합성 fixture를 만든다.

완료 기준:

- 같은 회의를 source 간 식별할 수 있다.
- 원문·첨부 변경을 content hash로 새 버전으로 보존한다.
- 수집 실패와 selector 변경을 감지하는 테스트가 있다.

### Phase 3 — 회의·발언 canonical model

- migration에 executive_meetings, executive_meeting_versions, transcript_segments, transcript_segment_revisions, speech_segments, ministries를 추가한다.
- 회차·날짜·주재자로 회의를 정규화하되 불확실한 매칭은 UNRESOLVED로 둔다.
- 모두발언·브리핑·부처보고를 문단/발언 단위 source span으로 분절한다.
- LIVE/PROVISIONAL/OFFICIAL 본을 authority_status로 분리하고 서로의 대조 결과를 reconciliation_status로 저장한다.
완료 기준:

- 최근 10건 회의와 모든 발언 segment가 원문 위치로 역추적된다.
- 같은 문서 재수집 시 canonical row가 중복되지 않는다.

### Phase 4 — 주제·부처 관리

- 공식 명시 부처를 먼저 규칙 기반으로 연결한다.
- 주제 분류와 암시적 관련 부처 추천은 AI annotation으로 별도 생성한다.
- DRAFT → REVIEWED → APPROVED 검토 흐름을 적용한다.
- 주제·소관 부처·관련 부처 필터 API를 제공한다.

완료 기준:

- 부처 필터 결과 100%가 evidence span을 가진다.
- 공식 명시와 AI 추론이 UI에서 시각적으로 구분된다.
- 승인되지 않은 AI 분류는 기본 검색 결과에 포함하지 않는다.

### Phase 5 — 국무회의 화면

- LIVE 자막 스트림과 마지막 갱신시각을 표시한다.
- LIVE/보정본/공식본 탭과 `일치·미확인·충돌` 대조 상태를 제공한다.
- 회의 한 줄 목록과 주제 한 줄 목록을 구현한다.
- hover/focus 상세에 발언 요약·발언자·부처·원문 링크를 표시한다.
- [x] 공식 명시 부처 선택과 안건명·공식 내용 검색 시 해당 회의·안건만 서버에서 다시 조회한다.
- 모바일에서는 hover 대신 행 선택으로 상세를 토글한다.

### Phase 6 — 국무회의와 국회 연계

- [x] 검토된 정책 주제 taxonomy를 공통 축으로 사용한다.
- [x] 동일 taxonomy와 공통 근거 단어가 양쪽에 있고 광범위 단일 단어 연결이 아닐 때만 공통 정책 신호로 대조한다.
- [x] 양쪽 공식 근거와 그 사이의 `PROVISIONAL · DRAFT` 규칙 연결을 분리해 표시한다.
- [x] 국무회의 → 관련 국회 논의 → 연결된 의안·표결 → 의안정보시스템 원문으로 이동하게 한다.
- [ ] 운영 검토 결과를 반영해 taxonomy·강한 근거 사전을 버전 업한다.

## 6. POC 성공 기준

- 국무회의 최근 10건과 대상 국회 위원회 3개의 자료가 한 화면에서 탐색된다.
- 특정 부처 선택 후 2초 이내에 관련 주제·발언 목록이 반환된다.
- 모든 노출 발언·요약·부처 마킹·기관 간 연결이 source version과 evidence span을 가진다.
- 의안 행에서 표결 유무와 찬성·반대·기권을 즉시 구분할 수 있다.
- 공식 값과 AI 생성값을 사용자가 혼동하지 않는다.

## 7. 이번 단계에서 하지 않는 것

- 비공개 국무회의 발언 추정
- 뉴스 기사로 공식 발언 보완
- 근거 없는 소관 부처 자동 확정
- 검토 전 AI 주제·기관 연결의 공식화
- 별도 검색엔진, 벡터 DB, 메시지 큐 도입
- 화면 합성 자막을 OCR로 읽는 방식을 기본 수집 경로로 사용
- 외부 회의록 서비스의 약관·API·timestamp 검증 없이 결과를 재게시
