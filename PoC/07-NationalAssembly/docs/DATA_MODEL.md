# Data Model

실제 schema는 `backend/migrations/`에서 순서대로 적용합니다. 공식 일정은 종류가 섞여 있으므로 모든 원본 레코드를 `ScheduleEntry`로 보존하고, 회의 식별 조건을 만족한 항목만 `Meeting`에 연결합니다.

제품의 우선 대상은 행정안전위원회, 예산결산특별위원회, 법제사법위원회입니다. `is_target_committee`는 제품 scope이며 자료 권위나 회의 매칭 상태와 별개입니다.

```text
ScheduleEntry N ─ 1 SourceDocumentVersion, N ─ 0..1 Meeting
Meeting 1 ─ N MeetingSource N ─ 1 SourceDocument
   │                                  └─ N SourceDocumentVersion
   ├─ N MeetingVersion
   ├─ N MeetingExternalId
   ├─ N CommitteeMinuteEntry
   ├─ N AgendaItem N ─ 0..1 Bill ─ N BillVersion
   ├─ N Event ─ 0..1 Statement / Question / Answer / ProceduralAction / Vote
   └─ N MeetingParticipant N ─ 1 Actor ─ 0..1 Organization

AIAnnotation N ─ N AIAnnotationEvidence ─ SourceDocumentVersion + SourceSpan

LiveBroadcast 1 ─ N LiveBroadcastSourceVersion N ─ 1 SourceDocumentVersion
   └─ N TranscriptSegment 1 ─ N TranscriptSegmentRevision
   └─ N BroadcastReview 1 ─ N BroadcastReviewTopic
                              └─ N BroadcastReviewEvidence ─ TranscriptSegmentRevision
   └─ N BroadcastOfficialPublication ─ Meeting + SourceDocumentVersion
          └─ N OfficialTranscriptDocument ─ N OfficialTranscriptUtterance
                 └─ N TranscriptOfficialReconciliation ─ TranscriptSegmentRevision
```

## 식별자

- 내부 PK는 UUID를 사용합니다.
- `meeting_uid`는 동일 회의의 일정·live·회의록·의안·표결 source를 묶는 내부 식별자입니다.
- 회의 공식 ID는 `(source_system, id_type, external_id)` unique key로 관리하며 회의록·의안의 `CONF_ID` 연결에 사용합니다.
- 원본 버전은 `(source_document_id, content_hash)`로 중복을 방지합니다.

## 상태

- `lifecycle_status`: SCHEDULED, LIVE, ENDED, CANCELED
- `authority_status`: LIVE, PROVISIONAL, OFFICIAL
- `reconciliation_status`: MATCHED, UNRESOLVED, CONFLICT

## LIVE 영구 기록

- `LiveBroadcast`는 브라우저 접속 여부와 무관하게 worker가 생성하고 `LIVE → ENDED` 생명주기를 관리합니다.
- `(source_system, external_id)`로 동일 방송의 중복 생성을 막고 관측한 모든 공식 player 버전을 `LiveBroadcastSourceVersion`으로 연결합니다.
- `TranscriptSegment`는 현재 읽기 모델이며 `TranscriptSegmentRevision`은 partial/final 변경 이력을 content hash로 중복 없이 보존합니다.
- 각 revision은 원본 WebSocket 메시지의 `SourceDocumentVersion`을 직접 참조합니다. 메시지는 구조화 전에 raw artifact로 먼저 저장합니다.
- 각 revision에는 전역 단조 증가 `event_cursor`가 부여됩니다. snapshot은 먼저 cursor를 고정한 뒤 그 cursor 이하의 최신 segment revision만 조회합니다.
- caption worker는 만료 가능한 DB lease를 획득하므로 재시작 후 수집을 이어가되 같은 방송을 동시에 중복 수집하지 않습니다.
- 자막 원문은 `LIVE` 권위 상태로 저장합니다. 종료 후 보정본과 공식 회의록은 원문을 덮어쓰지 않고 별도 버전·대조 관계로 추가합니다.
- `BroadcastReview`는 종료된 방송의 final revision만 입력으로 사용하는 `PROVISIONAL` 산출물입니다. 주제별 대표 발언은 원문을 그대로 사용하며 모든 포함 segment를 `BroadcastReviewEvidence`로 연결합니다.
- 현재 review generator는 `DETERMINISTIC_KEYWORD_RULE`이며 생성형 요약을 만들지 않습니다. 규칙 버전과 마지막 입력 cursor를 함께 저장해 재생성 결과를 덮어쓰지 않습니다.
- `BroadcastOfficialPublication`은 공식 `CONF_ID`, 회의록/PDF 링크와 source version을 보존합니다. 위원회+서울 날짜에 후보가 정확히 하나일 때만 연결하고 본문 미수집 상태는 `LINK_ONLY`, 대조 상태는 `UNRESOLVED`로 둡니다.
- `OfficialTranscriptDocument`는 회의록시스템 HTML 원본 hash별 버전입니다. 화면에 명시된 임시회의록은 `TEMPORARY + PROVISIONAL`, 정본은 `FINAL + OFFICIAL`로 분리하고 이전 버전을 덮어쓰지 않습니다.
- 공식 본문은 `Meeting`에 직접 연결되므로 과거 회의 탐색에 LIVE 방송 기록이 필수는 아닙니다. 해당 회의를 실제 수집한 LIVE 세션이 있으면 선택적인 `BroadcastOfficialPublication` 관계를 추가합니다.
- `OfficialTranscriptUtterance`는 공식 뷰어의 발언자 묶음 ID와 문장 ID(`spk_*`, `spk_sub*-*`), 안건 class, 발언자·직위, 원문을 보존합니다. `source_locator`로 해당 HTML 위치를 역추적합니다.
- `TranscriptOfficialReconciliation`은 LIVE final revision과 공식 문장의 관계입니다. 공백·문장부호만 제거한 문자열이 단 하나의 공식 문장과 포함 일치할 때만 `MATCHED`로 기록하며 짧거나 복수 후보인 문장은 `UNRESOLVED`로 남깁니다.
- `OfficialUtteranceAnnotation`은 공식 문장을 변경하지 않는 파생 레이어입니다. rule version, 분류 방법, 주제·관련 부처, 원문 hash, `PROVISIONAL`, `DRAFT/REVIEWED/APPROVED` 검토 상태를 별도 저장합니다.
- 설명 가능한 annotation v2는 `utterance_kind`(POLICY/PROCEDURAL/OTHER), 실제 일치 keyword, topic link와 `RELATED` ministry link를 함께 저장합니다. 이전 rule version은 삭제하지 않습니다.
- 통합 정책 흐름은 별도 canonical table이 아니라 각 Meeting의 최신 공식 본문과 annotation v2에서 계산하는 읽기 모델입니다. POLICY 발언만 포함하고 주제별 위원회·관련 부처 count와 가장 긴 원문 발언을 대표 evidence로 반환합니다.
- `OfficialUtteranceAgendaLink`는 공식 발언의 `itemN`과 같은 Meeting의 `N.` 의안만 연결합니다. 관계마다 reconciliation 상태, match method와 confidence를 보존하고 번호가 없거나 대응 의안이 없으면 row를 만들지 않습니다.

## Provenance 최소값

`source_type`, `source_id`, `source_url`, `retrieved_at`, `published_at`, `content_hash`, `parser_version`, `source_span`을 보존합니다. 실제 source에 없는 값은 만들어내지 않고 nullable 또는 별도 수집 metadata로 구분합니다.


위원회 회의록 API는 하나의 `CONF_ID`를 소제목별 여러 행으로 반환합니다. `Meeting`은 `CONF_ID`당 하나이며 각 행은 `CommitteeMinuteEntry`로 별도 보존합니다. 회의별 의안은 같은 `CONF_ID`로 연결하고 `BILL_ID`가 있을 때만 `Bill`을 생성합니다.
## Official과 AI

`Bill`은 외부 `BILL_ID`의 안정적인 identity만 담당합니다. 변경 가능한 의안명, 발의자, 소관위 처리결과, 본회의 결과와 처리단계는 `BillVersion`에 source version별로 누적합니다.

AIAnnotation은 canonical official table에 요약 필드로 삽입하지 않습니다. provider, model, prompt version, 생성시각, 입력 source version과 evidence span을 별도로 기록합니다.
## 국무회의 확장 모델

- ExecutiveMeeting / ExecutiveMeetingVersion: 날짜·회차·주재자와 원문 버전.
- ExecutiveAgenda: 공개된 심의안건·보고안건·협조사항.
- SpeechSegment: 발언자·발언 유형·문단 순서와 source span.
- TranscriptStream: 회의별 KTV caption 또는 STT session과 LIVE/PROVISIONAL authority.
- TranscriptSegment / TranscriptSegmentRevision: 시작·종료시각, 화자 label, 중간/확정 텍스트, confidence와 수정 이력.
- TranscriptReconciliation: LIVE/PROVISIONAL segment와 OFFICIAL source span의 MATCHED/UNRESOLVED/CONFLICT 대조.
- PolicyTopic: 검토된 주제 taxonomy.
- Ministry: 부처 표준명·약칭·유효기간.
- SegmentTopic: 발언과 주제 연결, 연결 근거와 검토상태.
- SegmentMinistry: OWNER 또는 RELATED 역할, 공식 명시 여부와 검토상태.
- CrossInstitutionLink: 국무회의 주제·발언과 국회 회의·의안 후보 연결.

공식 문서에 명시된 부처와 AI가 추론한 관련 부처를 같은 authority 상태로 저장하지 않습니다. AI 결과는 DRAFT, REVIEWED, APPROVED 검토상태와 evidence span을 가져야 합니다.
