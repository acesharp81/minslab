# Data Model

## 2026-10-22 — 인사이트 전체 목록 검색

두 인사이트 API(`specific-issues`, `cross-institution-flow`)는 선택 `q`(최대 200자)를 받는다. 항목별 전체 집합에서 검색한 뒤 페이지를 나누며, 검색 단어는 모두 포함해야 한다. 기관 별칭과 대소문자를 비교용 텍스트에서 정규화한다. URL·내부 ID는 검색하지 않는다. 응답의 `query`는 적용 검색어, `total_count`는 검색 결과 수, `unfiltered_total_count`는 검색 전 해당 항목 전체 수다. 저장 자료 수정 없음.

## 2026-10-22 — 인사이트 페이지 조회 및 온톨로지 어휘 확장

- `/api/policy/specific-issues`: 선택 `limit`(1~500), `offset`(0 이상), `category`(`all`/`institution`). 기존 무제한 조회도 유지한다.
- `/api/policy/cross-institution-flow`: 기존 `committee` 외 선택 `limit`(1~500), `offset`(0 이상).
- 응답의 `items`, `count`는 현재 페이지이며 `total_count`, `offset`, `has_more`, `next_offset`(마지막은 null)을 제공한다. 제도화 전체 건수는 DISCUSSION을 제외한 지원 전환 단계의 수다.
- 온톨로지 파생 `classification_evidence.method`에 `REPORT_VOCABULARY_SOURCE_AGREEMENT`를 추가한다. 기존 `supporting_spans`와 출처/위치 추적 조건을 유지한다. 그룹 `context_keywords`에 보완 어휘, `vocabulary_version`에 `report-vocabulary/2026-10-22`를 노출한다. DB 스키마·원본 수정 없음.

## 온톨로지 1.13 파생 필드 (2026-10-19)

DB 원본 변경 없이 주제 그룹의 `classification_evidence`에 `topic_title`, `method`, `supporting_spans`를 추가한다. 보완 연결 방법은 `ISSUE_AND_SOURCE_AGREEMENT` 또는 `PARENT_AND_SOURCE_AGREEMENT`이며 각 구간은 evidence ID·start/end·quote·content hash·revision IDs·상위 주제·일치 정책어를 보존한다. 기존 분류는 `TITLE_OR_SUMMARY_KEYWORD`로 구별한다.

온톨로지 API의 `metrics.context_topic_count`는 원문 문맥으로 추가 연결된 주제 수다. 분류별 `context_topic_count`, `context_keywords`, `context_examples`(최대 3건)를 제공한다. 예시는 출처 보고서 ID·주제 ID·근거 구간과 `PROVISIONAL` 권위를 포함한다. DB migration은 없으며 조회 시 계산한다.

## 실시간 누락 쟁점 복원 projection (2026-10-16)

- 저장된 `MeetingBrief.brief`는 수정하지 않는다. 잠정 보고서의 공개 읽기 모델에만 `coverage_origin=LIVE_TOPIC_SUPPLEMENT`, `summary_source=PRESERVED_LIVE_TOPIC`, `authority_status=PROVISIONAL`인 보완 topic을 추가한다. ID는 `live-issue-{cluster_id}`이며 원래 `utterance_ids`를 `evidence_ids`로 보존한다. 새 과제·화자·공식 근거를 만들지 않는다.
- 계보의 `mapping_status=SUPPLEMENTARY_EVIDENCE`는 보완 쟁점의 발언 근거를 뜻한다. `live_topic_assignment`의 기존 모델 연결 결과·요청 hash·미연결 목록은 그대로 두며, 조회 시 집계한 연결/미연결 수는 `live_topic_lineage`에 표시한다.
- `live_topic_coverage`에는 규칙 버전, 원래 미연결·단일 발언 수, 핵심/보완 주제 수, 복원한 cluster ID, 추가 호출 0회를 기록한다. 온톨로지 집계는 `core_topic_count`, `supplementary_topic_count`, `supplementary_report_count`로 분모 변경을 공개한다.
- 공식 대조본에는 복원 기능을 적용하지 않는다. 주제별 근거 endpoint는 표시된 잠정 보고서와 같은 규칙으로 보완 ID를 해석한다. DB schema 변경·migration은 없다.

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
- `MeetingBrief.topic_groups`와 `topic_grouping`은 저장 원본을 바꾸지 않는 버전형 읽기 모델입니다. `ONTOLOGY` 그룹은 세부 주제별 `classification_evidence(topic_id, keyword, field, score)`를 포함하고, 등록 정책 밖의 보수적 묶음은 `DYNAMIC_SEMANTIC` 또는 `TITLE_FALLBACK`으로 남습니다. 정책 대상이 아닌 대화·초안 구조는 `REPORT_ARTIFACT`로 근거를 보존하며 `report_artifact_topic_count`에 별도 집계합니다. `policy_topic_count`를 온톨로지 적용률 분모로 사용하고 `unclassified_topic_count`는 정책 주제 중 분류 보류만 셉니다. `follow_up_task_groups`는 회의별 자료 제출 요구를 묶은 파생 필드로 `task_ids`, `topic_ids`, 담당 기관과 LIVE·공식 근거 ID를 포함합니다. 저장된 `tasks` 행과 원본 보고서는 바꾸지 않습니다.
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
# 2026-10-19 추가: 논의 구조화 버전

- `meeting_topic_structures`: 원본 `meeting_briefs.id`, 원본 주제·과제·계보 해시, 구조화 버전으로 구분한 AI 파생 결과입니다. 원문 스냅샷에는 발언 ID, 수집 revision/segment ID, 텍스트·위치·앞뒤 맥락을 저장합니다. 공식 원문 테이블을 수정하지 않습니다.
- `meeting_topic_structure_batches`: 요청 단위의 원문·쟁점 목록, 모델 응답, 사용량, 시도 번호와 실패 사유를 추가 저장합니다. 성공한 분할 작업은 재사용하며 동일 입력·응답 형식/요청 프로필에 최대 3회 시도합니다. 입력 또는 검증 형식을 보완한 재처리도 기존 시도를 덮어쓰지 않고 추가 저장합니다. 최종 쟁점 통합은 별도 batch index로 보존합니다.
- `evidence_span`: `evidence_id`, `start`, `end`, `content_hash`, `revision_ids`, `segment_ids`, 원문 인용을 포함합니다. 위치는 해당 수집 발언 문자열의 Python 문자 오프셋이며 `end`는 제외됩니다.
- `structured_brief`: 기존 보고서와 별도로 제공하는 PROVISIONAL 파생 보기입니다. `structured-*` 식별자로 기존 근거 API를 이용하며 공식 원문 자동 추정 연결을 수행하지 않습니다. 공식 보고서는 기본 보기를 유지합니다.
- 구조화 근거 API의 `LIVE_STRUCTURE_SNAPSHOT`은 해당 분석 시점에 저장한 발언을 반환합니다. 긴 발언의 겹치는 저장 구간은 오프셋으로 복원하며, 이후 자막 수정으로 원문과 인용 위치가 달라지는 것을 방지합니다.
- `topic_structure`: 실행·근거 검증·전체 통합 상태, 원본 계보 집계, 검토 보류와 절차성 발언을 보존합니다. ‘근거 검증 통과’는 참조·구간 검증이며 발언 주장의 사실성이나 의미 분류의 정답 보증이 아닙니다.

## 온톨로지 의미 검토 감사 기록 (2026-10-19)

- 스키마 추가 없이 `meeting_topic_structure_batches.batch_index >= 200000`을 의미 검토에 할당한다. 기존 발언 구조화(`<100000`)와 최종 통합(`100002`)에서 제외된다.
- `request_snapshot`: `profile=ontology-semantic/1.3`, 분류 사전, 항목별 제목·원문 구간·fingerprint. `response`: 원본 `proposals` 및 `verification`. `usage_metadata`: 공급자·모델·각 단계 사용량. 실패 응답도 새 attempt로 추가한다.
- 읽기 투영의 `ontology_evidence_spans`는 원래 인용의 위치와 같은 발언 내 보완 구간 위치를 함께 보존한다. `ontology_semantic_review`는 fingerprint가 현재 입력과 일치하는 완료 기록만 반영한다.
- API의 `semantic_topic_count`는 `context_topic_count`의 부분집합이다. 기존 정책 주제 분모에서 미분류 주제를 제거하지 않는다. 분류 예시에는 잠정 상태, 실제 인용, 출처 위치와 검토 사유를 포함한다.

첫 단계 응답은 두 번째 호출 전에 `VERIFICATION_PENDING` 오류 코드의 감사 행으로 즉시 보존한다. 이 행은 완료 분류로 적용하거나 실패 횟수 상한에 포함하지 않는다. 같은 묶음의 완료/실패 결과는 새로운 attempt 행에 기록한다.

`semantic_reviewed_topic_count`는 현재 입력과 일치하는 저장된 AI 검토 건수이며 승인과 보류를 포함한다. `semantic_topic_count`는 실제 공통 분류에 반영된 부분집합이다.
# 실시간 논의 연결 읽기 모델 (2026-10-19)

회의 보고서 API의 `live_topic_resolution`은 저장된 공식/잠정 보고서를 수정하지 않는 파생 필드다. `source_brief_id`, 구조화 `revision_id`, `source_hash`, `authority_status=PROVISIONAL`을 포함한다. 기존 `live_topic_lineage`는 보존한다.

- `entries`: 기존 묶음 ID, 구조화 묶음 ID, 과거 상태, 현재 `LINKED/PROCEDURAL/PARTIAL/UNRESOLVED`, 연결 쟁점 ID·제목, 검토 원문 항목을 제공한다. 묶음 원문 발언 집합이 일치하고 모든 쟁점 ID가 존재해야 연결 상태를 수용한다.
- `legacy_pending_*`: 기존 요약에서 연결 확인 대상이었던 항목의 처리 결과다. `review_count`는 기존 연결 여부와 관계없이 보고서 전체의 남은 검토 묶음 수다.
- 구조화 projection 1.2의 묶음별 `review_evidence_ids`는 부분 연결 묶음 안에서 실제로 추가 확인해야 하는 원문 발언만 가리킨다. 기존 `structure_review` 근거 API로 저장 스냅샷을 조회한다.
- DB 스키마·저장 보고서·모델 응답 변경은 없다. 공식 자료 권위와 잠정 연결 권위를 합치지 않는다.

## 자료 요구 과제 투영 1.3

`topic_structure.document_requests`는 원문 요청 구간과 `related_topic_ids`, `topic_link_method`, `context_spans`를 담는다. 각 구간은 atom/evidence ID, 원문 start/end, quote, content_hash, revision_ids로 추적한다. `document_request_count`, `document_request_linked_count`는 구간 수다.

과제에 `task_kind=DOCUMENT_SUBMISSION`, `request_spans`, `topic_link_status`, `source_evidence_ids`를 부가한다. 필요한 앞 발언의 맥락은 `context_spans`에 구분하고 조회 가능한 `evidence_ids`에도 포함한다. `follow_up_task_groups`는 단일 주제 내부의 선택적 메타데이터(`scope=TOPIC`)만 제공하며 화면에서 개별 과제를 대체하지 않는다. `topic_identity_parent`는 공통 상위 분류를 복원할 때 기존 쟁점 ID를 유지하기 위한 이전 parent다. 원본 저장 스키마 변경은 없다.

## 과제 직접 언급 구간 투영 1.4

`tasks[].task_evidence_spans`는 원문 atom/evidence ID, start/end, quote, content_hash, revision_ids, topic_ids를 포함한다. `topic_link_method=DIRECT_TASK_REQUEST_OR_COMMITMENT`는 직접 요청·약속 문장 대조 결과이며, `SOURCE_SPAN_REVIEW`는 직접 구간 확인이 필요한 기존 연결이다. 과제 근거 API의 `direct_task_spans`는 반환 원문의 텍스트·위치·해시·버전 검증을 통과한 구간만 담는다. 공식 근거에 LIVE 오프셋을 적용하지 않는다. 원본 저장 스키마 변경은 없다.

### 문맥 자동 재분류 (2026-10-20)

기존 `meeting_topic_structure_batches`에 `request_snapshot.profile=discussion-context-review/3`을 가진 배치를 추가한다. 구조화 원문 배치(<100000), 통합 배치(100002), 온톨로지 분류 배치와 profile로 구분한다. 별도 migration은 없다. request의 `atoms`/`targets`는 대상 원문과 교체할 미분류 facet이며, response의 `assignments`/`reasons`는 모델 판단과 사유다. 원본은 수정하지 않는다.

투영 1.5의 `topic_structure.automatic_review`는 처리한 원문/대기 원문/실패 원문 수를 구분한다. `structure_review_items.review_state`는 `AUTO_PENDING`, `ANALYSIS_FAILED`, `SOURCE_LIMITED`, `PROCEDURAL`이다. SOURCE_LIMITED는 자동 재분석이 수행됐으나 현재 근거로 주제를 특정하지 못한 상태이며 사용자 확인 요청이 아니다. 일반 발언 근거는 기존 위치 필드를 유지하고, 문맥 근거는 `classification_context_spans`에 별도로 기록한다.

주제 미연결 자료 요구는 `discussion-request-context/1` profile로 같은 문맥 재분류 경로에 들어간다. 요구 구간의 대상이 확인되면 해당 쟁점 및 REQUEST 과제를 생성한다. `replacement_kind=DOCUMENT_REQUEST`는 기존의 일반 자료 요구/절차 facet만 교체하며 같은 발언의 다른 정책 쟁점을 보존한다. `pending_request_atom_count`와 `unresolved_request_atom_count`로 아직 처리하지 않은 요구와 재분석 후에도 연결 대상이 불명확한 요구를 구분한다.

`discussion-uncertain-check/1`은 원문이 충분한데 첫 재분류가 UNCERTAIN으로 남긴 발언에 대한 다른 모델의 추가 판단이다. 보고서별 잠금과 동일한 원문 검증을 사용하며 각 원문은 이 profile에서 한 번의 성공 결과만 채택한다. 추가 판단 대기를 완료/원문 불명확으로 조기에 표시하지 않는다. 짧게 잘린 원문은 불필요한 재호출을 하지 않는다.

주제 미연결 자료 요구도 `structure_review_items`에 `request_atom_id`와 원문·분류 사유를 제공한다. 처리 전은 AUTO_PENDING, 모델 처리가 끝났으나 대상이 불명확하면 REQUEST_SOURCE_LIMITED이며, UI에서 ‘주제 특정이 어려운 자료 요구’로 분리한다. 원문·과제는 유지하고 사람의 확인 작업으로 전환하지 않는다.


## 회의 보고서 표시 투영 (2026-10-20)

- `structured_brief.report_summary`: `status=AVAILABLE|PENDING`, `source=PRESERVED_AI_BRIEF`, `authority_status=PROVISIONAL`, `topics`. 실제 저장된 AI 서술 요약만 포함하며, 구조화 주제 수/온톨로지 분모에는 포함하지 않는다.
- 각 요약 topic은 `structured-summary-*` ID, `source_topic_id`, 원래 `title`, `summary`, `evidence_ids`, `authority_status=PROVISIONAL`을 가진다. 원 보고서를 수정하지 않고 현재 읽기 투영에서 생성한다.
- 기존 호환 필드 `speaker_points.summary`의 원문 인용은 `summary_kind=SOURCE_QUOTE`, 구조화 topic의 역할별 건수는 `summary_kind=ROLE_COUNTS`로 구별한다. 화면은 이를 서술 요약으로 취급하지 않는다.
- `/api/live/broadcasts/{id}/brief/evidence?entity_type=summary_topic&entity_id=structured-summary-*`는 요약이 참조한 구조화 스냅샷을 조회한다. 원문 hash·revision_ids와 `LIVE_STRUCTURE_SNAPSHOT`·`PROVISIONAL`을 유지한다.
- DB schema·기존 모델 응답·구조화 분류 ID 변경 없음. 최신 보고서 읽기 시 자동 적용된다.


### 요약 계층 보존 보완 (2026-10-20)

`report_summary.topic_groups`는 기존 대주제 이름과 topic 순서를 보존하며 요약 topic ID로 참조한다. 각 topic의 `speaker_points`는 저장된 AI 세부 발언 요약, `source_point_id`, `evidence_ids`를 보존한다. `summary_speaker` 근거 조회는 `structured-summary-point-*` ID로 해당 세부 발언의 구조화 스냅샷을 연다. 대주제·발언 묶음·세부 요약은 순서대로 표시하며, 평면 카드 목록으로 펼치지 않는다.


### 공통 보고서 카드 투영 (2026-10-20)

- 모든 표시용 brief(공식·잠정·구조화)에 `report_summary.presentation_version=meeting-summary/3`을 제공한다. 원 brief의 자료 권위와 기본 화면 선택은 바꾸지 않는다.
- `evidence_type`은 요약/세부 행의 기존 근거 조회 타입이다. 구조화 요약은 `summary_topic`, `summary_speaker`, 공식·잠정 요약은 `topic`, `speaker`를 사용한다. 공식 원문을 참조해도 서술 요약의 authority_status는 PROVISIONAL이다.
- 공식 원문 발췌인 speaker point는 보존된 `provisional_summary`로 요약 행을 만들고 원문은 그대로 보존한다. 공식 화자 근거가 있는 경우에만 확인된 화자명을 표시한다.
- 요약 topic의 `task_ids`는 같은 brief.tasks의 표시용 참조다. 기존 topic_id/source_topic_id 및 원래 주제 제목을 우선 사용하고, 새 과제는 근거가 하나의 요약 카드만 가리킬 때 보조 연결한다. canonical 과제 연결/원문 구간을 변경하지 않는다.
- Markdown은 이미 준비된 공통 투영의 주제·과제 연결을 재분류하지 않고 그대로 사용한다.


### 온톨로지 집계 스냅샷 응답 (2026-10-20)

`GET /api/policy/ontology?background=true[&refresh=true]`는 기존 온톨로지 응답에 `snapshot`을 추가한다. DB schema 변경은 없다.

- `status`: `LOADING`(분류 체계만 있음), `READY`(집계 완료), `REFRESHING`(이전 집계 표시·갱신 중), `STALE`(갱신 실패·이전 집계 유지), `FAILED`(최초 집계 실패).
- `generated_at`: 마지막 성공 집계 시각(UTC ISO 8601). null이면 적용 건수·연결률을 유효한 통계로 표시하지 않는다.
- `refresh_in_progress`: 서버에서 단일 집계가 수행 중인지 여부.
- `max_age_seconds`: 정상 캐시 재집계 기준, 현재 120초. `retry_after_seconds`: 재요청 간격 안내.
- 기본 조회(쿼리 없음)는 기존의 동기 전체 집계를 유지한다. 공식 자료 선택 규칙·구조화 투영·지표 산식·원문 참조는 같다.


### 주제별 보고서 전체 근거 응답·생성 감사 (2026-10-20)

DB migration 없이 기존 JSON 저장 경계와 읽기 응답을 확장한다.

- 검색 응답 `items/count/total_count/selection_limited`: 기본 조회는 전체 조건 일치 자료를 반환한다. `report_input.compatible`과 제한 시 `reason`은 모델 입력 가능 여부이며 검색 자료의 존재 여부와 다르다.
- READY 상세·Markdown은 원래 `evidence`와 모델 `report`를 변경하지 않고 `supplementary_evidence`를 별도로 붙인다. 원래 검색 조건의 현재 자료 중 저장 ID에 없는 항목이다.
- `evidence_scope`: `saved_count`, `additional_count`, `current_match_count`, `checked_at`(UTC), `basis=SAVED_SNAPSHOT_PLUS_CURRENT_SCOPE_QUERY`. 재검색 실패 시 `status=UNAVAILABLE`이며 보완 완료로 표시하지 않는다.
- `coverage`: `evidence_count`, `narrative_cited_count`, `report_cited_count`, 미인용 ID 목록, `source_task_count`, `detail_evidence_count`, `semantic_completeness_verified=false`. 상세 응답은 저장+보완 자료를 대상으로 계산한다. `evidence_scope`로 출처를 구분하며 인용 수를 의미상 완전성 지표로 사용하지 않는다.
- 프롬프트 `topic-report/1.7`: 전체 근거 ID가 sections에 포함되어야 한다. 누락은 `EVIDENCE_COVERAGE_INCOMPLETE`, 전체 입력 예산 초과는 `EVIDENCE_INPUT_TOO_LARGE`, 출력 필드 초과는 `OUTPUT_FIELD_TOO_LONG`으로 처리한다. 기존 `OUTPUT_TRUNCATED` 검증도 유지한다.
- 성공 시 비공개 `usage_metadata.generation_audit`에 입력·출력 검증 건수, 종료 사유, 원 모델 응답 `response_snapshot`을 보존한다. 공개 응답에서 usage_metadata와 소유자 정보는 제외한다. 기존 응답을 덮어쓰지 않는다.


### 주제별 보고서 1.8의 근거별 세부 요약 보완

DB migration 없이 `report.sections[].discussions[]`를 선택적으로 추가한다. 각 항목은 `heading`, `body`, `evidence_ids`를 가지며 근거 한 건을 직접 요약한다. 상위 절의 evidence_ids는 기존 본문 근거와 실제 보완 요약 근거의 합집합이다. 요약 없이 근거 ID만 덧붙이지 않는다. 기존 보고서에 이 필드가 없으면 이전처럼 표시한다.

`usage_metadata.generation_audit.response_snapshots`는 초기·보완·전체 요약 응답을 순서대로 보존한다. `coverage_repair`는 initial_missing_count, repaired_count, requests, summary_refreshed 및 실패 시 remaining_ids를 기록한다. 공개 응답에는 노출하지 않는다. 실패는 usage_metadata.failed_attempts에 오류·시각·원 응답 감사 기록을 추가하고 성공 저장 시 이전 실패 이력을 유지한다. 모든 응답의 사용량은 개별 provider request_id로 기록하여 캐시 재생과 재시도의 이중 집계를 막는다.

작업 소유권·할당량 예약을 생성 전에 커밋하고, 추가 호출마다 제공자 일일 제한과 lease_owner를 유지하며 임대를 3분 갱신한다. 사용자 작성 한도는 동일 보고서 복구에 중복 차감하지 않는다.

## 관심주제 발송 생명주기 (0054)

- `watch_topic_episodes`: 규칙·정규화 키워드별 감지 구간. `OPEN → WAITING(정회/종료 요약 대기) → CLOSED`, 규칙 변경/중지 시 `CANCELED`. 시작 cursor, 규칙 revision, 경계 및 저장 요약을 보존.
- `watch_episode_detections`: 감지와 키워드별 구간을 다대다 연결. 한 자막에 여러 키워드가 있으면 각각 최초 감지하며 다른 키워드의 열린 구간이 이를 막지 않음. `watch_detection_events.episode_id`는 누적 대상 여부를 확인하는 연결.
- `watch_meeting_boundaries`: 정회/종료 시각, cutoff cursor, 원문 revision 또는 SourceDocumentVersion 근거. 방송·종류·cursor 유일.
- `watch_broadcast_signals`: 공식 중계/명시적 선포의 최신 상태. 회의 생명주기 및 자료 권위와 별도 신호.
- `watch_dispatches`: 소유자·session·단계(1/2/3)·영구 dedupe key·순번·발송 당시 JSON. 알림함 삭제로 제거되지 않으며 규칙/계정 삭제 시 cascade. 저장 요약은 LIVE 권위이며 원문 segment/revision ID를 보존.
- `watch_notifications.dispatch_id`, `TOPIC_COMPLETE` 유형 추가. 외부 발송 대기 기록은 자동 50건 정리 대상에서 제외.
- 구형 frequency/digest/cooldown DB 컬럼은 이전 버전과의 배포 호환을 위해 보존하지만 새 API·로직에서는 사용하지 않음.
- `watch_lifecycle_rollout`: 신규 생명주기 적용 시작 시각. 과거 회의를 소급 발송하지 않음.
