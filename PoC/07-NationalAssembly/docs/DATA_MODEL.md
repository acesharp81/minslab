# Data Model

## 공식 회의록 비교 projection

- `MeetingBrief.brief`는 LIVE/STT 기반 잠정 초안이며 공식 자료 게시 뒤에도 원본을 유지한다.
- 공식 대조가 완료된 API 응답의 `brief`와 `official_brief`는 검증된 공식 보완 projection이며 `default_brief_view=OFFICIAL`이다. `provisional_brief`는 원형 LIVE/STT 초안이다. 공식 대조 전에는 `brief`가 잠정 초안이고 `default_brief_view=PROVISIONAL`이다.
- 공식 대조본의 화자별 항목은 현재 공식 문서의 발언 ID·화자명·원문을 직접 표시한다. 연결되지 않은 LIVE/STT 화자 요지는 `draft_only_speaker_points`에 따로 두며 초안의 요지와 원본은 보존한다. 다른 공식 화자가 한 요지에 연결되면 공식 발언자별로 분리한다.
- `TranscriptOfficialReconciliation`의 V2 매칭은 양방향 문자 겹침과 발언 순서를 사용하며 모호한 후보는 저장하지 않는다.
- 공식 발언 evidence는 reconciliation의 `live_revision_id`와 `live_text`로 해당 공식 발언에 매칭된 원본 자막 조각만 비교한다. `diff_spans`는 공식 문장을 재구성하고, `change_count`는 의미 있는 교체·추가·LIVE 전용 문구만 센다. 공식본에 없는 실질적인 LIVE 문구는 `live_only_fragments`에 보존한다.

실제 schema는 `backend/migrations/`에서 순서대로 적용합니다. 공식 일정은 종류가 섞여 있으므로 모든 원본 레코드를 `ScheduleEntry`로 보존하고, 회의 식별 조건을 만족한 항목만 `Meeting`에 연결합니다.

제품의 우선 대상은 행정안전위원회, 예산결산특별위원회, 법제사법위원회입니다. `is_target_committee`는 제품 scope이며 자료 권위나 회의 매칭 상태와 별개입니다.

`assembly_reference.json`은 canonical 의원 테이블이 아니라 공식 `ALLNAMEMBER` 원본 버전에서 하루 한 번 계산하는 공개 읽기 스냅샷입니다. 현행 대수·직책 존재 규칙, 정당별 의석·선출구분·성별·위원회 수와 각 raw content hash를 보존합니다. 화면 조회는 이 스냅샷만 읽으며 외부 API나 LLM을 호출하지 않습니다. 월간 달력은 `ScheduleEntry`의 최대 42일 범위 읽기 모델이고 저장되지 않은 미래 일정을 추정하지 않습니다.

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
   └─ N TranscriptUtteranceSummary (summary + PROVISIONAL live_insight JSON)
   └─ N BroadcastReview 1 ─ N BroadcastReviewTopic
                              └─ N BroadcastReviewEvidence ─ TranscriptSegmentRevision
   └─ N MeetingBrief (PROVISIONAL JSON read model)
          └─ topic / speaker point / task evidence ─ TranscriptSegment(Utterance id)
   └─ N BroadcastOfficialPublication ─ Meeting + SourceDocumentVersion
          └─ N OfficialTranscriptDocument ─ N OfficialTranscriptUtterance
                 ├─ N TranscriptOfficialReconciliation ─ TranscriptSegmentRevision
                 └─ N TranscriptOfficialPartMatch ─ TranscriptSegmentRevision + source part index
```

관심주제 계층은 `WatchSubscriber → WatchRule → WatchRuleRevision`으로 설정 버전을 보존하고, `WatchDetectionEvent → WatchSession → WatchMatch`로 빠른 감지와 사용자 발언 묶음을 분리합니다. `WatchNotification.notification_type`은 `MATCH`와 `DIGEST`를 구분하며 dedupe key로 재시작 중복을 막습니다. `WatchMatchOfficialVerification`은 FINAL 공식 문서별로 `PENDING_OFFICIAL / OFFICIAL_CONFIRMED / OFFICIAL_CORRECTED / OFFICIAL_NOT_CONFIRMED / REVIEW_REQUIRED`를 별도 파생 상태로 보존하고 LIVE 원문을 수정하지 않습니다.

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
- `TranscriptSpeakerOverride`는 방송별 원본 화자 코드와 사람이 확인한 표시 이름만 연결합니다. 원본 segment/revision의 `speaker_label`은 수정하지 않으며 보정값 삭제 시 즉시 원본 코드 기반 표시로 돌아갑니다.
- 화면용 `Utterance`는 별도 canonical table이 아닌 읽기 모델입니다. 같은 방송에서 바로 이어지는 동일 원본 화자의 자막을 시간·길이 제한 없이 연속 병합하고 포함 segment/revision ID와 180자 자동 발췌 요약, 전체 원문을 함께 반환합니다.
- `TranscriptUtteranceSummary`는 방송·원문 해시·provider·model·prompt version 조합을 유일 키로 사용해 성공한 외부 LLM 요약을 저장합니다. `live_insight` JSON은 같은 호출에서 생성한 잠정 주제·주제 key·발언 역할·명시적 과제·담당 기관 후보를 `PROVISIONAL`로 보존합니다. 원문 근거는 `content_hash`와 읽기 모델의 포함 segment/revision ID로 역추적하며 공식 자료 필드와 혼합하지 않습니다. API 요청은 이 캐시만 읽으며 외부 LLM을 호출하지 않습니다.
- 프롬프트 버전이 바뀌어도 이미 성공한 동일 방송·원문 hash는 비용 제어를 위해 재호출하지 않습니다. 새 발언은 최신 계약으로 저장하고, 기존 행은 요약값을 유지한 채 `live_insight={}`로 남을 수 있습니다.
- 수동 화자명은 공식 발언자 확정값이 아니라 운영자 검토 표시값입니다. 공식 회의록의 `OfficialTranscriptUtterance.speaker_name` 및 reconciliation과 혼합하지 않습니다.
- `(source_system, external_id)`로 동일 방송의 중복 생성을 막고 관측한 모든 공식 player 버전을 `LiveBroadcastSourceVersion`으로 연결합니다.
- `TranscriptSegment`는 현재 읽기 모델이며 `TranscriptSegmentRevision`은 partial/final 변경 이력을 content hash로 중복 없이 보존합니다.
- 각 revision은 원본 WebSocket 메시지의 `SourceDocumentVersion`을 직접 참조합니다. 메시지는 구조화 전에 raw artifact로 먼저 저장합니다.
- 각 revision에는 전역 단조 증가 `event_cursor`가 부여됩니다. snapshot은 먼저 cursor를 고정한 뒤 그 cursor 이하의 최신 segment revision만 조회합니다.
- `LiveBroadcast.source_last_event_cursor`는 해당 방송에 저장된 revision의 최대 cursor를 같은 트랜잭션에서 함께 갱신하는 읽기 최적화 값입니다. 원본 revision은 그대로 보존하며, 회의 보고서 목록·상세 상태 확인은 전체 revision 집계 대신 이 값을 사용합니다.
- `LiveBroadcast.final_segment_count`와 `matched_segment_count`는 공식 대조 현황 조회용 집계값입니다. 현재 공식 문서에 연결된 최신 final 자막 revision만 일치 수에 포함하고, 대조 배치 완료 시 해당 방송만 다시 집계합니다. 사용자 상세 조회에서는 원본 자막·대조 테이블에 `COUNT`를 수행하지 않습니다.
- caption worker는 만료 가능한 DB lease를 획득하므로 재시작 후 수집을 이어가되 같은 방송을 동시에 중복 수집하지 않습니다.
- `LiveBroadcast.active_transcript_source`, `official_caption_state`, `stt_fallback_status`는 공식 자막과 AI STT의 활성 소스·복구 상태·별도 STT lease를 관리합니다. `TranscriptSourceSession`은 공식 자막 timeout과 STT 시작·종료 전환 사유를 감사 이력으로 보존합니다.
- 자막 원문은 `LIVE` 권위 상태로 저장합니다. 종료 후 보정본과 공식 회의록은 원문을 덮어쓰지 않고 별도 버전·대조 관계로 추가합니다.
- `BroadcastReview`는 종료된 방송의 final revision만 입력으로 사용하는 `PROVISIONAL` 산출물입니다. 주제별 대표 발언은 원문을 그대로 사용하며 모든 포함 segment를 `BroadcastReviewEvidence`로 연결합니다.
- `MeetingBrief`는 공식 원문과 분리된 오픈 베타용 `PROVISIONAL · DRAFT` 읽기 모델입니다. provider-neutral client가 발언 묶음을 구간별로 분석한 뒤 회의 전체의 headline·summary·topic·speaker point·task를 통합하며, 모든 항목의 `evidence_ids`는 해당 방송의 실제 Utterance 시작 segment ID로 검증합니다. 각 task는 공통 evidence를 우선해 하나의 canonical `topic_id`와 정식 `topic_title`에 연결하며 생성된 제목 문자열을 관계 키로 사용하지 않습니다. 최종 표시용 세부 쟁점은 최대 24개로 제한하되 나머지 LIVE cluster와 근거는 삭제하지 않고 `live_topic_lineage`의 미연결 검토 대상으로 보존합니다. `(broadcast_id, transcript_hash, provider, model, prompt_version)`을 캐시 키로 사용하고 API는 저장 결과만 읽습니다.
- `MeetingBrief.topic_groups`와 `topic_grouping`은 저장 원본을 바꾸지 않는 버전형 읽기 모델입니다. `ONTOLOGY` 그룹은 세부 주제별 `classification_evidence(topic_id, keyword, field, score)`를 포함하고, 등록 정책 밖의 보수적 묶음은 `DYNAMIC_SEMANTIC` 또는 `TITLE_FALLBACK`으로 남습니다. 정책 대상이 아닌 대화·초안 구조는 `REPORT_ARTIFACT`로 근거를 보존하며 `report_artifact_topic_count`에 별도 집계합니다. `policy_topic_count`를 온톨로지 적용률 분모로 사용하고 `unclassified_topic_count`는 정책 주제 중 분류 보류만 셉니다.
- `LlmProviderDailyUsage`는 이전 POC7 로컬 OpenRouter 장부이며, 운영 권위값은 POC4·POC7이 공유하는 gateway의 UTC 일일 장부입니다. gateway는 공식 1,000회 중 운영선 950회까지만 원자적으로 예약합니다. `LlmProviderTokenUsageEvent`는 Mistral 성공 응답을 provider·request ID로 한 번만 저장하며, `LlmProviderMonthlyTokenUsage`는 입력·출력·전체 토큰과 STT 비용을 provider·model·UTC 월 단위로 누적합니다.
- 현재 review generator는 `DETERMINISTIC_KEYWORD_RULE`이며 생성형 요약을 만들지 않습니다. 규칙 버전과 마지막 입력 cursor를 함께 저장해 재생성 결과를 덮어쓰지 않습니다.
- `BroadcastOfficialPublication`은 공식 `CONF_ID`, 회의록/PDF 링크와 source version을 보존합니다. 위원회+서울 날짜에 후보가 정확히 하나일 때만 연결하고 본문 미수집 상태는 `LINK_ONLY`, 대조 상태는 `UNRESOLVED`로 둡니다.
- `OfficialTranscriptDocument`는 회의록시스템 HTML 원본 hash별 버전입니다. 화면에 명시된 임시회의록은 `TEMPORARY + PROVISIONAL`, 정본은 `FINAL + OFFICIAL`로 분리하고 이전 버전을 덮어쓰지 않습니다.
- 공식 본문은 `Meeting`에 직접 연결되므로 과거 회의 탐색에 LIVE 방송 기록이 필수는 아닙니다. 해당 회의를 실제 수집한 LIVE 세션이 있으면 선택적인 `BroadcastOfficialPublication` 관계를 추가합니다. 여러 발행 기록이나 방송이 같은 회의·`CONF_ID`를 가리켜도 본문 완료 판정과 공식 문서 조회는 회의·`CONF_ID`를 기준으로 공유합니다.
- `OfficialTranscriptUtterance`는 공식 뷰어의 발언자 묶음 ID와 문장 ID(`spk_*`, `spk_sub*-*`), 안건 class, 발언자·직위, 원문을 보존합니다. `source_locator`로 해당 HTML 위치를 역추적합니다.
- `TranscriptOfficialReconciliation`은 LIVE final revision과 공식 문장의 관계입니다. 공백·문장부호만 제거한 문자열이 단 하나의 공식 문장과 포함 일치할 때만 `MATCHED`로 기록하며 짧거나 복수 후보인 문장은 `UNRESOLVED`로 남깁니다.
- `TranscriptOfficialPartMatch`는 한 자막 revision 안의 원천 화자 조각을 `(공식 문서 ID, revision ID, 조각 순번)`으로 식별합니다. 원문 SHA-256, 공식 발언 ID, 방법·신뢰도를 보존하고 화면에서는 현재 문서와 최신 revision의 조각 원문 해시가 모두 맞을 때만 화자명을 투영합니다. 문서가 바뀌면 예전 관계는 이력으로 남되 표시에서는 제외합니다. 매칭되지 않은 조각은 미확인으로 남깁니다.
- `OfficialSpeakerReviewDecision`은 사람이 확인한 예외를 `(브리프 ID, 공식 문서 ID, 화자 요지 ID, LIVE 원문 SHA-256)`에 묶고, 공식 발언 ID·보정 문장·검토 출처·사유·규칙 버전을 보존합니다. 공식 발언이 해당 문서에 속하고 모든 키가 일치할 때만 적용하며 기존 코드 고정 보정은 검토 출처를 `legacy_review_import`로 이관합니다.
- `OfficialUtteranceAnnotation`은 공식 문장을 변경하지 않는 파생 레이어입니다. rule version, 분류 방법, 주제·관련 부처, 원문 hash, `PROVISIONAL`, `DRAFT/REVIEWED/APPROVED` 검토 상태를 별도 저장합니다.
- 설명 가능한 annotation v2는 `utterance_kind`(POLICY/PROCEDURAL/OTHER), 실제 일치 keyword, topic link와 `RELATED` ministry link를 함께 저장합니다. 이전 rule version은 삭제하지 않습니다.
- 통합 정책 흐름은 별도 canonical table이 아니라 각 Meeting의 최신 공식 본문과 annotation v2에서 계산하는 읽기 모델입니다. POLICY 발언만 포함하고 주제별 위원회·관련 부처 count와 가장 긴 원문 발언을 대표 evidence로 반환합니다. 주제별 `meeting_count`와 날짜별 고유 회의·공식 정책 발언 수의 `timeline`도 반환하며 최근 14일 증감 표시는 이 읽기 모델에서 계산한 화면 파생값입니다.
- `OfficialUtteranceAgendaLink`는 공식 발언의 `itemN`과 같은 Meeting의 `N.` 의안만 연결합니다. 관계마다 reconciliation 상태, match method와 confidence를 보존하고 번호가 없거나 대응 의안이 없으면 row를 만들지 않습니다.
- `OfficialAnnotationProcessingState`는 문서·주석 생성 규칙 버전별 발언 수와 성공 또는 지연 재시도 상태를 저장합니다. 완료 문서는 매 주기 발언·주석 전체 표에서 누락 여부를 다시 검색하지 않습니다.
- `OfficialAgendaReconciliationState`는 문서별 마지막 처리 발언 순번과 당시 의안 수를 저장합니다. 새로운 문서 또는 뒤늦게 추가된 의안만 최대 1,000발언씩 처리하며, 완료된 정본의 원문은 변경 감시 대상으로 다시 읽지 않습니다.
- `BillOfficialDocumentFetch`는 법안 버전·PDF URL·파서 버전별 성공 또는 재시도 상태를 저장합니다. PDF 원문과 추출 문서 버전은 기존 테이블에 계속 보존하고 성공 건은 수집 대기열에서 제외합니다.
- `MeetingOfficialIntegration`은 특정 `MeetingBrief`와 특정 `OfficialTranscriptDocument` 버전의 파생 대조 결과입니다. LIVE 잠정 원본과 공식 원본은 수정하지 않고, 통합 브리프·본문 변경 span·공식 근거 ID·화자 매칭 통계·LLM 사용량만 캐시합니다. 캐시 키는 `(meeting_brief_id, official_document_id, integration_version)`입니다.
- `MeetingOfficialIntegrationJob`은 최신 브리프·공식 문서·통합 버전 조합의 PENDING/PROCESSING/RETRY_WAIT/READY 상태, lease, 시도 횟수와 다음 재시도 시각을 저장합니다. READY 통합본이 있는 조합은 큐에 다시 넣지 않으며 여러 워커는 `SKIP LOCKED`로 서로 다른 작업만 선점합니다.
- `MeetingOfficialChangeReport`는 하나의 READY `MeetingOfficialIntegration`에서 서버가 검증한 변경 snapshot과 hash, OpenRouter 설명 결과, 사용량·상태·lease·제한 재시도를 저장합니다. LLM은 제공된 change ID만 묶을 수 있고 변경 0건은 결정론 결과를 저장합니다.
- `OfficialChangeReportDailyUsage`는 공식화 변화 보고 전용 UTC 일일 요청 수를 원자적으로 제한하며 실제 호출은 공용 `LlmProviderDailyUsage` 한도도 함께 예약합니다.
- 공식 화자 매칭은 `TranscriptOfficialReconciliation`의 파생 관계를 현재 문서 기준으로 교체합니다. 화면은 이 관계를 발언 묶음 키로 사용해 공식 화자가 바뀌면 분리하고, 인접 자막이 같은 공식 화자로 확인되면 병합하지만 별도 화자 변경 이력 UI는 만들지 않습니다.

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

## 관심주제 외부 기능과 운영 이력

- `WatchKakaoAccount`: 브라우저 subscriber와 Kakao 사용자 연결 상태, 암호화 access/refresh token, 만료·scope·재동의 상태를 저장합니다.
- `WatchWebSession`: Kakao 계정과 여러 브라우저를 연결하는 만료 가능한 opaque session의 SHA-256 hash, user-agent hash, 마지막 사용·폐기 시각만 저장합니다. 원문 token은 저장하지 않습니다.
- `NotificationOutbox`: IN_APP/KAKAO provider별 전송 상태와 lease, attempt, 다음 재시도 시각을 저장합니다. provider 실패는 match와 다른 channel을 변경하지 않습니다.
- `WatchSummaryVersion`: session별 evidence match ID 집합 hash, 근거 연결 claim, provider/model/prompt, 실제 token·비용과 생성 상태를 버전으로 저장합니다.
- `WatchReviewDecision`: 공식 대조의 자동판정 상태를 복사해 보존하고 운영자 승인·보정·보류와 메모를 별도 이력으로 추가합니다.
- `LiveRegressionAudit`: 방송별 revision/final/partial/수집 공백과 공식 통합 확인 결과를 실행 시점별로 저장합니다.
- `TopicReport`: 사용자 검색 조건, 당시 선별된 공개 근거 snapshot과 hash, provider/model/prompt, 검증된 보고서 JSON, 사용량과 비동기 lease를 저장합니다. 같은 조건·근거·모델·프롬프트의 READY 결과는 재사용합니다. READY 결과는 계정과 무관한 공개 읽기 모델이며 `generated_at` 기준 최근 30일의 최신 50건만 유지합니다. 공개 응답에서는 subscriber와 upstream 사용 metadata를 제거하고, 미완료·실패 상태는 요청자에게만 반환합니다.
- `TopicReportDailyUsage`: 사용자별 UTC 일일 요청 수를, `TopicReportGlobalDailyUsage`는 주제 보고서 전용 UTC 일일 요청 수를 원자적으로 제한합니다. 실제 외부 호출 전에는 공용 `LlmProviderDailyUsage` 500회 장부도 함께 예약합니다.
