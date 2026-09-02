# 관심주제 실시간 알림·기존 기능 완성도 보완 구축 계획

## 문서 관리 정보

| 항목 | 값 |
|---|---|
| 프로젝트 | PoC 7 · 국정보미 |
| 문서 상태 | RELEASE A/B SOFTWARE COMPLETED · EXTERNAL KAKAO ACTIVATION PENDING |
| 확정일 | 2026-08-28 |
| 우선순위 | Release A 관심주제 알림 → Release B 기존 기능 완성도 |
| 기준 브랜치 | main |
| 기준 커밋 | a1ef014 |
| 데이터 원칙 | LIVE / PROVISIONAL / OFFICIAL 분리, 원본·provenance 보존 |
| 비용 원칙 | 감지·알림·근거는 LLM과 무관하게 동작, 전역 월 예산 초과 금지 |

이 문서는 관심주제 실시간 알림과 후속 완성도 보완 작업의 최종 구축 기준이다. 구현 중 범위, 권위 모델, 비용 한도 또는 사용자 식별 방식이 달라질 경우 코드를 먼저 바꾸지 않고 이 문서의 변경 기록과 docs/DECISIONS.md를 먼저 갱신한다.

## 0. 2026-08-28 구현 기록

Release A의 P0를 운영 화면과 실제 DB 경로까지 배포했다.

| 항목 | 상태 | 구현 내용 |
|---|---|---|
| 익명 사용자 격리 | 완료 | 256-bit opaque token의 SHA-256 hash만 DB 저장 |
| rule CRUD | 완료 | 이름·포함 문구·제외 문구·기관·위원회·알림 정책 API, 생성·수정·삭제 UI |
| deterministic matcher | 완료 | Unicode NFKC, 공백·문장부호, 한글 띄어쓰기, 영문 약어 경계, EXCLUDE 우선 |
| 빠른 감지 | 완료 | final caption revision에서 LLM 없이 감지 |
| 발언 묶음 누적 | 완료 | 감지 event를 같은 화자의 연속 자막 묶음으로 투영해 근거·화자 흐름 제공 |
| FIRST_PER_MEETING | 완료 | DB UNIQUE와 회의 단위 상태로 재시작 후에도 1회만 알림 |
| interval 정책 | 완료 | 10분 간격 선택 제공. 시간 경과만으로 발송하지 않고 새 발언 때만 판단 |
| outbox·in-app | 완료 | notification/outbox 분리, in-app SENT와 읽음 상태 제공 |
| 무료 누적 요약 | 완료 | 발언 묶음의 extractive summary를 화자별로 제공, LLM 호출 0 |
| 테스트 방송 | 완료 | 12개 자막/약 36초, 실제 revision→감지→알림→근거 경로, 일반 목록·후처리 격리 |
| 보안 배포 | 완료 | API·watch/review worker 환경변수 허용목록 및 API 롤백 스크립트 |
| 자동 검증 | 완료 | 전체 177 tests 통과, E2E 12 segments/10 utterances/알림 1/근거 5/화자 4 확인 |

현재 구현은 빠른 detection event와 사용자 표시용 utterance bundle을 분리한다. 이는 최초 작업지시의 ‘RAW 조각마다 알림 금지’ 목적을 지키면서, 최종 검토에서 확정한 낮은 지연 요구도 함께 만족하기 위한 결정이다. segment 반복은 DB event로 멱등 처리하고 사용자 match 수는 연속 화자 발언 묶음 수로 다시 계산한다.

### 0.1 알람·실시간 / 회의 보고서 이원화 구현

후속 검토에서 제품의 업무 성격을 다음 두 상위 메뉴로 확정하고 화면에 반영했다.

| 상위 메뉴 | 범위 | 데이터 상태 |
|---|---|---|
| 알람·실시간 | 알람 규칙, 알림함, 근거 흐름, 진행 중 방송, 실시간 자막, 누적 초안 보고서, 격리 테스트 방송 | LIVE_DRAFT |
| 회의 보고서 | 종료 후 정리 진행률, 비공식 보고서, 공식자료가 반영된 통합 결과와 변경 근거 | POST_PROCESSING → PROVISIONAL_READY → OFFICIAL_INTEGRATED |

구현 원칙은 다음과 같다.

1. 기존 방송 수집·자막 revision·화자 묶음·회의 브리프·공식자료 통합 파이프라인을 복제하거나 재작성하지 않는다.
2. `알람·실시간`에는 진행 중 방송, 결과 정리 중 재열람 카드, 가장 최근 완료 보고서 인계 카드만 두고, 완료된 전체 결과 목록은 `회의 보고서`에서 관리한다.
3. 알람 설정과 알림함은 별도 드로어가 아니라 실시간 화면의 상시 업무 영역이다. 알림 근거도 같은 화면에서 확인한다.
   - 사용자 설정 원본은 브라우저 localStorage에 두고 감지 워커에는 브라우저 토큰 범위의 서버 규칙을 동기화한다.
   - 최초 로컬 마이그레이션과 신규 저장에서 동일한 이름·문구·기관 범위의 중복 규칙을 제거한다.
   - 감지 기록 UI는 최신순 12건으로 제한하고 서버에는 사용자별 최근 50건까지만 자동 보존한다. 개별 삭제·읽은 기록 정리를 제공하며 삭제된 마지막 알림의 빈 세션과 고아 이벤트도 정리한다.
4. 실시간 초안은 화자 전환으로 닫힌 묶음의 기존 `transcript_utterance_summaries.live_insight`를 주제·담당부처·과제 기준으로 결정론적으로 병합한다.
   - 최종 회의 보고서와 같은 잠정 헤더, 3개 지표, 주제/과제 2열 표, 주요 논의 카드 형식을 사용한다.
   - 카드 본문에는 최근 누적 논의 3개, 전체 반영 묶음 수, 미해결 과제와 대상 부처를 표시한다.
   - 같은 주제가 다시 언급되면 새 카드를 만들지 않고 기존 카드를 갱신한 뒤 최신 위치로 이동한다.
   - `관련 발언 보기`는 해당 카드의 가장 최근 근거 발언 묶음을 열고 강조하며 별도의 요약문을 중복 생성하지 않는다.
5. 초안 렌더링, 새로고침, 필터링은 외부 LLM을 호출하지 않는다. 같은 발언 묶음의 저장된 요약을 재사용하므로 기존 화자 묶음당 최대 1회 호출 원칙과 월 USD 10 전역 한도를 그대로 지킨다.
6. 방송 종료 시 실시간 초안을 최종 결과로 승격하지 않는다. 기존 전체 회의 `meeting_brief` 후처리가 별도의 비공식 보고서를 생성하고, 공식자료가 발행되면 기존 통합·변경 표시 흐름을 사용한다.
   - 화면 배치는 `영상 | 발언 묶음`을 첫 행으로, `실시간 초안 보고서`를 그 아래 전체 폭으로 사용한다.
   - 방송 종료부터 비공식 보고서 준비 전까지 종료 회의를 `알람·실시간`의 `완료 · 정리중` 카드로 유지하고 저장된 LIVE 초안과 발언 묶음을 재열람한다.
   - 비공식 또는 공식 결과가 준비된 회의는 `회의 보고서`의 결과 카드로 관리한다. 알람·실시간에는 가장 최근 완료 회의의 인계 카드 하나만 남겨 클릭 시 해당 보고서를 직접 연다.
7. 불명확한 주제는 무리하게 새 주제를 만들기보다 기존 유사 주제에 병합하거나 분류 대기로 남긴다. 화면 조회를 이유로 재분류 LLM을 반복 호출하지 않는다.

현재 단계별 완료 상태:

- 1단계 상위 메뉴와 데이터 권위 분리: 완료
- 2단계 알람 설정·알림함 상시 배치 및 테스트 방송 연결: 완료
- 3단계 진행 중/종료 카드 분리와 각 상세 렌더러 연결: 완료
- 4단계 저장된 `live_insight` 기반 실시간 초안 보고서 표시: 완료
- 5단계 기존 종료 후 비공식 보고서·공식자료 통합 연결 유지: 완료
- 6단계 반응형 레이아웃·자동 계약 테스트·운영 문서: 완료

테스트 방송 화면 원칙도 실제 서비스 검증에 맞게 보완했다. 별도 `watch-test-stage` 데모 UI는 사용하지 않으며, 인증된 테스트 세션의 transcript만 브라우저 내부에서 공통 LIVE 렌더러로 전달한다. 따라서 테스트 데이터는 공개 LIVE API와 종료 보고서에서 계속 격리되지만 사용자는 실제 국무회의 LIVE 카드, 미디어 비율, 실시간 초안, 자막 자동 갱신을 그대로 검증한다.

무료 운영 P1/P2는 이 구조를 바꾸지 않고 추가 알림 정책, 회의 종료 digest, 공식 근거 확인, 운영 지표와 대응자료로 구현했다. Kakao는 PoC 7 독립 OAuth·암호화 토큰·outbox worker까지 구현하되 Kakao Developers에 PoC 7 redirect URI를 등록하기 전에는 기능 플래그로 비활성화한다. 관리자 검토는 기존 루트 운영자 인증 또는 전용 토큰을 사용하며 자동 판정을 덮어쓰지 않는 별도 decision 이력으로 구현했다.

2026-08-28 후속 구현 결과는 다음과 같다.

- FIRST_PER_SPEAKER 및 15/30/60분 preset: 완료
- rule revision/archive와 수정 이전 과거 무알림: 완료
- 공식 회의록 기준 watch evidence 확인 상태: 완료
- 회의 종료 digest와 운영 latency·억제·공식확인율 API: 완료
- 저장 결과 기반 인쇄/PDF·Markdown 대응자료: 완료
- 선택적 watch 전용 LLM: 무료 기본 흐름으로 대체하고 비활성 유지
- Kakao OAuth/provider: 소프트웨어 구현 완료, Kakao Developers redirect URI 등록과 사용자 동의만 운영 활성화 전제
- 관리자 review decision: 인증 경계·검토 목록·결정 이력·회귀 점검 구현 완료

## 1. 최종 검토 결론

추가 사용자 결정을 기다려야 할 핵심 쟁점은 없다. 다음 방향으로 구축을 시작할 수 있다.

1. 관심어 알림은 안정화된 자막 segment에서 빠르게 발생시킨다.
2. 최종 match 건수, 화자별 흐름, 근거와 통합 요약은 기존 화자 발언 묶음을 사용한다.
3. 빠른 감지 이벤트와 최종 발언 match를 분리해 중복 집계와 불안정한 자막 근거 문제를 막는다.
4. in-app과 Kakao는 같은 outbox를 사용하는 독립 provider로 구성한다.
5. Kakao 장애가 감지, 근거 저장, in-app 알림을 막지 않는다.
6. 추가 LLM이 없어도 관련 발언 흐름을 항상 제공한다.
7. AI 통합 요약은 선택 기능이며 별도 soft budget과 버전 캐시를 사용한다.
8. 공식자료 반영 후 CONFIRMED, CORRECTED, NOT_CONFIRMED를 구분하되 과거 알림은 취소하거나 재발송하지 않는다.
9. 정상적인 공식자료 미발표 상태를 사람 검토 항목으로 세지 않는다.
10. 첫 번째 관심주제 기능을 완료한 뒤 두 번째 기존 기능 완성도 작업을 진행한다.

## 2. 확정된 제품 목표

> 관심 주제가 처음 등장하면 가능한 한 빠르게 알려주고, 이후 반복되는 발언은 조용히 누적해 현재까지의 논의 흐름을 근거 발언과 함께 보여주며, 공식 회의록 공개 후 잠정 기록을 공식 정보 기준으로 보정한다.

완성형 사용자 흐름은 다음과 같다.

~~~text
관심주제 등록
  → 회의 화면을 계속 보지 않고 대기
  → 안정화된 자막에서 관심어 최초 감지
  → in-app / Kakao 알림
  → 관심주제 deep link 진입
  → 현재까지의 관련 발언 흐름과 근거 확인
  → 선택적 AI 통합 요약 확인
  → 회의 종료 digest 수신
  → 공식자료 발표 후 공식 화자·문장·확인 상태 반영
~~~

## 3. 변경하지 않는 기존 원칙

- 기존 일정 → 방송 → 자막/오디오 → 발언 묶음 → 브리프 → 공식자료 통합 파이프라인을 재작성하지 않는다.
- LIVE 원본, 자막 revision, 오디오와 공식 원문을 삭제하지 않는다.
- AI 결과를 공식 사실로 표현하지 않는다.
- 모든 요약·주제·과제·관심주제 결과는 evidence로 역추적할 수 있어야 한다.
- 공식 후보가 모호하면 강제 매칭하지 않는다.
- API 조회와 화면 새로고침이 외부 LLM 호출을 만들지 않는다.
- 동일 input hash와 prompt/version은 캐시를 재사용한다.
- 다른 PoC의 내부 모듈에 런타임 의존하지 않는다.
- 범용 MCP나 새로운 orchestration framework를 도입하지 않는다.

## 4. 최종 아키텍처

### 4.1 빠른 알림과 정확한 누적의 분리

~~~text
실시간 자막 revision
  ├─ 빠른 감지 경로
  │    final segment 또는 안정화된 revision
  │      → deterministic matcher
  │      → watch detection event
  │      → notification policy / dedupe
  │      → notification outbox
  │      → in-app / Kakao
  │
  └─ 기존 정확한 처리 경로
       연속 화자 발언 묶음
         → 기존 발언 요약 cache
         → watch match 확정
         → evidence 연결
         → 화자별 관련 발언 흐름
         → 선택적 통합 요약

공식자료
  → 기존 official integration
  → watch evidence 공식 화자·문장 연결
  → CONFIRMED / CORRECTED / NOT_CONFIRMED
  → 알림 재발송 없음
~~~

빠른 감지 건은 알림 latency를 위한 신호이고, watch match는 사용자에게 표시하고 집계하는 최종 발언 단위다. detection 수를 관련 발언 수로 표시하지 않는다.

### 4.2 자막 안정화 규칙

소스가 final 상태를 제공하면 final revision을 즉시 검사한다.

final 상태가 없는 경우 다음 조건을 모두 만족한 revision만 검사한다.

- 동일 source segment의 content hash가 WATCH_STABILITY_SECONDS 이상 변하지 않음
- watch-worker가 동일 hash를 두 번 이상 관찰
- 비어 있거나 지나치게 짧은 텍스트가 아님
- 이전에 같은 rule과 source segment로 감지되지 않음

초기 기본값:

~~~dotenv
WATCH_POLL_INTERVAL_SECONDS=1
WATCH_STABILITY_SECONDS=3
WATCH_STABILITY_OBSERVATIONS=2
~~~

국회 공식 자막의 final 신호를 우선한다. KTV 국무회의는 60초 오디오 청크 전사가 완료된 뒤 final segment로 들어오므로 알림 지연에 해당 청크 길이와 전사 시간이 포함된다. 국무회의에서 실제보다 빠른 latency를 표시하지 않고 국회와 별도 지표로 집계한다.

안정화 감지 후 원문이 바뀌어 관심어가 사라지면 detection을 SUPERSEDED로 표시한다. 이미 보낸 알림은 지우지 않으며 이후 공식 확인 상태에서 사용자가 변경 이유를 알 수 있게 한다.

### 4.3 deterministic matcher

P0의 기본 표현은 다음과 같다.

- match_mode: ANY
- INCLUDE term 여러 개
- EXCLUDE term 선택
- source_scope: ALL / NATIONAL_ASSEMBLY / EXECUTIVE
- committee_scope 선택

정규화 범위:

- Unicode normalization
- 앞뒤·연속 공백
- 한글 문구의 제한적인 띄어쓰기 차이
- 영문 대소문자
- 문장부호
- 영문 약어 word boundary
- 동일 normalized term 중복 제거

EXCLUDE가 INCLUDE보다 우선한다. 과도한 edit-distance나 fuzzy matching은 사용하지 않는다.

matcher 인터페이스는 향후 ANY, ALL, INCLUDE, EXCLUDE clause를 받을 수 있게 구성하지만 P0 UI에는 ANY와 EXCLUDE만 제공한다. semantic matching은 기본 OFF이며 장기 기능으로 둔다.

### 4.4 관심주제 변경 원칙

관심주제 rule은 stable ID와 revision을 갖는다. 수정 시 기존 감지·알림 이력을 덮어쓰지 않고 새 revision과 effective_at을 생성한다.

> 조회는 과거까지, 알림은 설정 이후부터

- 사용자가 요청하면 새 조건으로 현재 회의의 과거 발언을 backfill한다.
- backfill match는 notification_eligible=false다.
- rule 생성·수정 이전의 발언으로 알림을 보내지 않는다.
- 삭제는 이력 보존을 위해 기본적으로 archive/disable 처리한다.

## 5. 데이터 모델 계획

기존 migration 0029 다음 번호부터 순차적으로 추가한다.

### 5.1 0030 — subscriber와 rule

watch_subscribers:

- id
- credential_hash
- status
- created_at, last_seen_at

watch_rules:

- id, subscriber_id
- name
- source_scope
- notification_policy
- cooldown_minutes
- notification_channels
- digest_enabled
- enabled, archived_at
- current_revision
- created_at, updated_at

watch_rule_revisions:

- rule_id, revision
- effective_at
- match_mode
- configuration snapshot
- created_at

watch_rule_terms:

- rule_id, rule_revision
- term_type: INCLUDE / EXCLUDE
- original_term
- normalized_term
- clause_group

subscriber별 활성 rule 최대 수와 rule별 term 수를 DB와 API 양쪽에서 검증한다.

### 5.2 0031 — 빠른 감지와 최종 match

watch_detection_events:

- rule_id, rule_revision, broadcast_id
- source_segment_id
- first_detected_revision_id, latest_checked_revision_id
- matched_terms
- detected_at, stabilized_at
- status: DETECTED / FINALIZED / SUPERSEDED
- notification_eligible
- unique(rule_id, rule_revision, broadcast_id, source_segment_id)

watch_matches:

- rule_id, rule_revision, broadcast_id
- utterance_key
- utterance_content_hash
- source_speaker_label
- matched_terms
- matched_at
- source_authority
- notification_eligible
- unique(rule_id, broadcast_id, utterance_content_hash)

watch_match_evidence:

- match_id
- transcript_revision_id
- position

watch_scan_checkpoints:

- broadcast_id
- detector cursor
- bundle cursor
- updated_at

원본 자막 ID는 실제 FK로 보존한다. presentation용 utterance_key만으로 provenance를 대신하지 않는다.

### 5.3 0032 — session과 notification outbox

watch_topic_sessions:

- rule_id, broadcast_id
- first_matched_at, last_matched_at
- first_notified_at, last_notified_at
- latest_summary_version_id
- official_verification_status
- unique(rule_id, broadcast_id)

match_count와 distinct_speaker_count는 가능한 한 watch_matches에서 계산한다. 조회 성능 때문에 snapshot을 저장할 경우 항상 재계산 가능한 값으로 취급한다.

watch_notifications:

- id, subscriber_id, rule_id, session_id, broadcast_id
- detection_id 또는 match_id
- notification_type
- provider
- dedupe_key UNIQUE
- status: PENDING / SENDING / SENT / FAILED / CANCELED
- scheduled_at, started_at, sent_at
- attempts, next_attempt_at
- lease_owner, lease_expires_at
- provider_message_id
- last_error_type
- created_at, updated_at

watch_notification_attempts:

- notification_id
- attempt_number
- provider
- started_at, finished_at
- result_status
- response_code
- error_type

메시지 본문에 비밀값이나 전체 원문을 저장하지 않는다. last_error에는 예외 타입과 안전하게 제한된 메시지만 남긴다.

### 5.4 0033 — 누적 요약 버전

watch_topic_summary_versions:

- id, session_id
- evidence_set_hash
- source_last_match_at
- provider, model, prompt_version
- authority_status: PROVISIONAL
- summary
- evidence_match_ids
- usage_metadata
- generated_at
- unique(session_id, evidence_set_hash, provider, model, prompt_version)

이전 accumulated summary를 input의 유일한 근거로 사용하지 않는다. 최신 evidence와 저장된 발언 요약을 기준으로 생성하고 evidence ID를 검증한다.

### 5.5 0034 — 공식 확인과 검토 기록

watch_match_official_verifications:

- match_id
- official_document_id
- status
- official_utterance_ids
- verification_method
- verified_at
- unique(match_id, official_document_id)

허용 상태:

- LIVE_DETECTED
- PENDING_OFFICIAL
- OFFICIAL_CONFIRMED
- OFFICIAL_CORRECTED
- OFFICIAL_NOT_CONFIRMED
- REVIEW_REQUIRED

OFFICIAL_NOT_CONFIRMED는 다음 조건을 모두 만족할 때만 사용한다.

- FINAL 공식 문서가 존재
- LIVE evidence와 official utterance 정합이 완료
- 연결된 공식 발언 또는 충분한 공식 문맥에서 등록 term/alias를 확인하지 못함
- 후보 충돌이나 LOW_CONFIDENCE 상태가 아님

공식 문구가 정확히 같지 않다는 이유만으로 알림을 오탐으로 단정하지 않는다. 조건이 불충분하면 PENDING_OFFICIAL 또는 REVIEW_REQUIRED를 유지한다.

## 6. 사용자와 보안 경계

이번 PoC에는 device-scoped anonymous subscriber까지만 구현한다.

- 서버가 cryptographically random credential 발급
- 브라우저에는 HttpOnly, Secure, SameSite=Lax 쿠키 저장
- DB에는 credential hash만 저장
- 쿠키 path는 PoC 7 범위로 제한
- write 요청은 CSRF token 또는 동일 origin 검증
- rule CRUD와 test notification에 rate limit
- 사용자별 활성 rule 최대 20개
- rule별 INCLUDE 최대 10개, EXCLUDE 최대 10개
- term 길이와 request body 제한
- 8070 포트 외부 공개 금지

부모 프록시는 전체 쓰기 요청을 개방하지 않는다. subscriber 발급, watch rule, notification 관련 정확한 경로만 허용하고 필요한 Cookie와 Set-Cookie만 전달한다. 운영자 review endpoint는 기존 관리자 세션이 있을 때만 프록시한다.

SSO, 조직 계정, 역할 기반 권한은 이번 범위에 포함하지 않는다.

## 7. 알림 정책

### 7.1 FIRST_PER_MEETING

기본값이다.

dedupe key:

~~~text
first:{rule_id}:{broadcast_id}:{provider}
~~~

### 7.2 FIRST_PER_SPEAKER

dedupe key:

~~~text
speaker:{rule_id}:{broadcast_id}:{source_speaker_key}:{provider}
~~~

공식자료에서 화자가 분리·병합되어도 과거 알림을 재발송하지 않는다. 표시명만 공식 화자로 갱신한다.

국무회의에서는 기본 비활성으로 제공하고 화자 분리 신뢰도 안내 후에만 선택하게 한다.

### 7.3 INTERVAL

dedupe window는 rule, broadcast, provider와 실제 신규 detection을 기준으로 계산한다. cooldown 경과 자체로 알림을 생성하지 않는다.

초기 preset:

- 15분
- 30분
- 60분

### 7.4 회의 종료 digest

사용자가 digest_enabled를 선택한 session만 회의 종료 후 한 번 발송한다.

dedupe key:

~~~text
digest:{rule_id}:{broadcast_id}:{provider}
~~~

digest는 match 수, 화자 수, 기존 관련 발언 흐름과 저장된 통합 요약을 사용한다. digest 때문에 새 LLM 호출을 강제하지 않는다.

## 8. 알림 provider

NotificationProvider 인터페이스:

- send(notification)
- health()
- provider name

구현 순서:

1. InAppNotificationProvider
2. KakaoNotificationProvider

Kakao는 PoC 4의 OAuth, TokenCipher, send-to-me, lease/retry 설계를 참고하되 PoC 4 모듈을 import하지 않는다. PoC 7 설정, PostgreSQL repository와 독립 코드로 구현한다.

Kakao 원칙:

- 사용자별 talk_message 동의
- access/refresh token 암호화
- 토큰 갱신 실패 시 REAUTHORIZE
- provider 실패는 notification FAILED/RETRY로만 기록
- match와 in-app 알림에는 영향 없음
- 환경변수와 secret allowlist 별도 관리
- 외부 정책·쿼터 변경 시 Kakao만 비활성화 가능

## 9. 무료 운영 정책

### 9.1 비용이 없어야 하는 기능

- deterministic keyword detection
- notification policy와 suppression
- watch match·evidence 저장
- in-app notification
- 관련 발언 흐름
- deep link
- 공식자료 deterministic verification
- lifecycle, metrics
- HTML/Markdown 대응자료

### 9.2 선택적 AI 통합 요약

화면 문구를 명확히 구분한다.

- 관련 발언 흐름: 기존 발언 요약 조합, 추가 비용 없음
- 현재까지 논의 요약: 선택적 LLM 통합 결과

초기 운영값:

~~~dotenv
WATCH_LLM_ENABLED=0
WATCH_LLM_MONTHLY_BUDGET_USD=1.0
WATCH_LLM_DEBOUNCE_SECONDS=30
WATCH_LLM_MIN_NEW_MATCHES=3
WATCH_LLM_MAX_UPDATES_PER_SESSION=12
~~~

LLM을 활성화해도 다음 조건을 적용한다.

- 첫 3개 match 전에는 기존 관련 발언 흐름만 표시
- 신규 match가 3개 이상 추가됐을 때 갱신
- 짧은 시간의 연속 match는 30초 debounce
- 화면 진입과 새로고침은 호출 조건이 아님
- session당 최대 12회
- watch 전용 soft cap에 도달하면 해당 기능만 중단
- 전역 Mistral 월 hard cap 10 USD는 최종 방어선
- 국무회의 오디오 전사와 기존 요약 사용량을 포함한 실제 provider usage로 계산

가격은 문서에 영구 고정하지 않는다. .env 설정 단가와 실제 input/output token, audio seconds를 이용해 계산한다.

### 9.3 무료 운영 제한

- notification test는 사용자별 일 3회
- Kakao retry 최대 3회, exponential backoff
- in-app notification 기본 보존 90일
- 실패 attempt 로그 기본 보존 30일
- watch worker는 cursor 이후 신규 revision만 처리
- 비활성 rule은 matcher 대상에서 즉시 제외
- 같은 normalized rule signature의 통합 요약 재사용 가능성을 검토하되 사용자 데이터는 섞지 않음

## 10. API 계획

별도 FastAPI APIRouter를 추가하고 main.py에는 router include만 둔다.

사용자 세션:

- POST /api/watch/subscriber
- GET /api/watch/subscriber

관심주제:

- GET /api/watch/rules
- POST /api/watch/rules
- PUT /api/watch/rules/{rule_id}
- DELETE /api/watch/rules/{rule_id}

상황과 근거:

- GET /api/watch/topics
- GET /api/watch/broadcasts/{broadcast_id}/topics
- GET /api/watch/broadcasts/{broadcast_id}/topics/{rule_id}

알림:

- GET /api/watch/notifications
- POST /api/watch/notifications/{notification_id}/read
- POST /api/watch/notifications/test

운영·평가:

- GET /api/watch/metrics
- GET /api/live/broadcasts/{broadcast_id}/metrics

UI나 API handler는 LLM 또는 Kakao를 직접 호출하지 않는다.

## 11. Frontend 계획

기존 web/app.js의 책임을 더 늘리지 않고 다음 모듈을 분리한다.

- web/watch-alerts.js
- web/watch-alerts.css
- web/watch-settings.js

화면 구성:

1. 상단 알림 아이콘과 읽지 않은 알림 수
2. 관심주제 알림 설정 drawer
3. 회의 상세의 내 관심주제 영역
4. session 요약 카드
5. 관련 발언 흐름
6. 선택적 현재까지 논의 요약
7. 기존 evidence panel로 이동하는 근거 버튼
8. 공식 확인 상태

deep link는 broadcast ID와 rule ID만 URL에 사용하고 credential을 URL에 넣지 않는다.

## 12. Release A — 관심주제 기능

### A0. 최소 subscriber 보안 경계

작업:

- subscriber schema와 repository
- 안전한 credential cookie
- watch write API proxy allowlist
- CSRF, rate limit, body limit
- 운영 환경변수와 secret allowlist

수용 기준:

- 다른 subscriber의 rule을 읽거나 수정할 수 없음
- 직접 8070 공개 없이 통합 경로에서 동작
- 기존 speaker admin write 정책 유지
- 일반 POST를 포괄 허용하지 않음

### A1. 관심주제 DB와 matcher

작업:

- 0030~0031 migration
- normalization과 deterministic matcher
- rule revision과 effective_at
- 과거 backfill은 notification_eligible=false
- repository idempotency

필수 테스트:

- Unicode, 띄어쓰기, 문장부호, 영문 boundary
- INCLUDE/EXCLUDE 우선순위
- 동일 keyword 반복은 detection 1건
- worker 재처리 중복 없음
- rule 수정 전 발언 알림 없음

### A2. 저지연 감지·FIRST_PER_MEETING·outbox

작업:

- watch-worker
- final/stable revision scanner
- detection event와 bundle match reconciliation
- FIRST_PER_MEETING
- notification-worker
- in-app provider
- Compose와 운영 문서

목표 지표:

- 국회 final revision 저장 → outbox 생성 p95 5초 이내
- outbox 생성 → in-app SENT p95 5초 이내
- Kakao provider latency는 별도 표시
- KTV latency는 오디오 청크·전사 시간을 포함해 별도 표시

필수 테스트:

- 한 화자의 장시간 발언 중 final segment가 나오면 화자 전환 전 알림
- partial revision 반복으로 중복 알림 없음
- 같은 회의 10 match, 알림 1건
- 재시작 후 같은 알림 재발송 없음
- provider 실패 시 match/evidence 유지

### A3. 설정·evidence·deep link

작업:

- 설정 drawer
- 관심주제 목록과 활성화
- in-app 알림 센터
- session 카드와 관련 발언 수
- 기존 evidence panel 연결
- 모바일·키보드 접근성

수용 기준:

- 알림 클릭 시 회의와 관심주제가 자동 선택됨
- 관련 발언은 utterance 단위로 표시됨
- 감지 event 수와 관련 발언 match 수가 혼동되지 않음
- AI 장애 중에도 근거를 볼 수 있음

### A4. 외부 알림 최소 구현

작업:

- PoC 7 독립 Kakao adapter
- OAuth 동의·토큰 암호화·갱신
- Kakao provider outbox
- 연결 테스트와 재동의 상태
- deep link 메시지

수용 기준:

- 관심어 최초 감지 시 실제 화면 밖 메시지 시연
- Kakao 장애 시 in-app 알림 정상
- token과 Authorization 값 로그 미노출
- 동일 dedupe key 중복 전송 없음

### A5. 무료 흐름과 선택적 통합 요약

작업:

- 기존 utterance summary로 관련 발언 흐름 구성
- 화자별 그룹과 시각
- watch summary version/cache
- 선택적 LLM worker와 soft budget
- 생성 중/실패/한도 초과 상태

수용 기준:

- WATCH_LLM_ENABLED=0에서도 자연스러운 화면
- LLM 실패 시 notification과 evidence 정상
- 동일 evidence_set_hash 재호출 없음
- summary의 모든 주장이 evidence로 연결됨

### A6. 추가 알림 정책

작업:

- FIRST_PER_SPEAKER
- INTERVAL 15/30/60
- 국무회의 화자 정책 경고
- suppression metric

필수 테스트:

- 같은 화자 5회, 다른 화자 2명 → 화자 정책 알림 3건
- 30분 interval에서 14:00과 14:31 신규 발언만 알림
- 시간이 흐르기만 해서는 알림 없음

### A7. 공식자료 사후 검증

작업:

- watch match와 official utterance 연결
- CONFIRMED/CORRECTED/NOT_CONFIRMED/REVIEW_REQUIRED
- 공식 표시명·완성형 문장 우선
- LIVE 원문 보기 유지
- 공식 확인율 지표

필수 테스트:

- 공식 exact/normalized term 확인
- STT 오탈자와 공식 문구 수정
- FINAL 공식자료에서 미확인
- 후보 충돌은 NOT_CONFIRMED가 아니라 REVIEW_REQUIRED
- 공식자료 반영 후 알림 0건 추가

### A8. 회의 종료 digest

작업:

- 선택적 digest 설정
- 회의 종료 시 session별 1회 outbox
- 기존 흐름·저장 요약 사용

수용 기준:

- 최초 알림과 digest dedupe 분리
- digest 비활성 사용자는 발송 없음
- digest 생성 때문에 LLM 추가 호출 없음

## 13. Release B — 기존 기능 완성도

### B1. 검토 필요 항목

사용자 상태 매핑:

| 내부 상태 | 사용자 표현 | 검토 |
|---|---|---|
| PENDING/CHECKING/NOT_PUBLISHED | 공식자료 대기 | 아니요 |
| AMBIGUOUS/CONFLICT | 공식 후보 확인 필요 | 예 |
| LOW_CONFIDENCE | 문장 대응 확인 필요 | 예 |
| integration FAILED | 처리 오류 | 운영 장애 |
| READY | 공식 확인 완료 | 아니요 |

작업:

- 기존 official diff/evidence 기반 finding 집계
- 검토 drawer
- 관리자 review decision 기록
- reviewed_at, reviewed_by, decision, note
- 원본 자동판단 보존

### B2. lifecycle과 metrics

단계:

1. 회의 수집
2. AI 잠정 정리
3. 근거 확인
4. 공식자료 반영
5. 최종 정리

기존 timestamp를 재사용한다. official integration 시작·완료 시각처럼 실제로 없는 값만 migration으로 추가한다.

필수 지표:

- live detected latency
- 첫 자막 수신
- 방송 종료 → 브리프 완료
- 공식자료 발견 → 통합 완료
- 전체 utterance와 AI 요약 수
- topic/task 수
- 공식 정합 발언과 수정 수
- 검토 필요/완료 수
- 관심주제 detection/match/notification/suppression
- 감지 → 발송 latency
- 공식확인율
- 전체 match 대비 실제 알림 수

공식확인율 분모는 FINAL 공식 문서와 evidence 정합이 완료된 eligible match만 사용한다.

### B3. 회의 대응자료

우선 출력:

1. print CSS가 적용된 HTML
2. Markdown
3. 브라우저 PDF 저장

포함 내용:

- 회의 기본정보와 권위 상태
- 주요 논의 주제와 화자 요지
- 도출 과제와 담당부처 후보
- 주요 근거 발언
- 공식자료 반영과 의미 있는 수정
- 검토 필요 항목
- 생성 시각, 데이터 최신 시각, prompt/integration version

추가 LLM 호출 없이 현재 저장 결과로 생성한다.

### B4. UX와 문서 마무리

- 공식 변경 집계
- 근거 버튼 일관성
- 근거 없는 AI 결과 품질 게이트
- 대기·실패·한도·충돌 빈 상태
- 사용자용 상태 문구
- README, OPERATIONS, DATA_MODEL, DECISIONS 갱신

## 14. 구현 예상 파일

신규:

~~~text
backend/app/api/watch.py
backend/app/db/watch_repository.py
backend/app/ingestion/watch_worker.py
backend/app/ingestion/notification_worker.py
backend/app/ingestion/watch_summary_worker.py
backend/app/services/watch_matcher.py
backend/app/services/watch_sessions.py
backend/app/services/notifications/base.py
backend/app/services/notifications/in_app.py
backend/app/services/notifications/kakao.py
backend/tests/test_watch_matcher.py
backend/tests/test_watch_repository.py
backend/tests/test_watch_worker.py
backend/tests/test_watch_notifications.py
backend/tests/test_watch_official_verification.py
web/watch-alerts.js
web/watch-alerts.css
web/watch-settings.js
~~~

변경:

~~~text
main.py
PoC/07-NationalAssembly/backend/app/main.py
PoC/07-NationalAssembly/backend/app/config.py
PoC/07-NationalAssembly/backend/app/services/transcript_presentation.py
PoC/07-NationalAssembly/backend/app/ingestion/official_integration_worker.py
PoC/07-NationalAssembly/docker-compose.yml
PoC/07-NationalAssembly/web/index.html
PoC/07-NationalAssembly/web/app.js
PoC/07-NationalAssembly/.env.example
PoC/07-NationalAssembly/README.md
PoC/07-NationalAssembly/docs/DATA_MODEL.md
PoC/07-NationalAssembly/docs/OPERATIONS.md
PoC/07-NationalAssembly/docs/DECISIONS.md
PoC/07-NationalAssembly/CHANGELOG.md
~~~

실제 수정 전에 각 단계에서 최소 범위를 다시 확인한다. 관련 없는 PoC와 루트 변경은 함께 커밋하지 않는다.

## 15. 테스트와 검증 게이트

각 단계 공통:

~~~bash
PYTHONPATH=backend python3 -m unittest discover -s backend/tests -v
ruff check backend
git diff --check
~~~

추가 검증:

- migration fresh install
- 기존 데이터가 있는 DB migration
- watch worker 재시작과 lease 만료
- 동시 worker 중복 claim
- 동일 자막 revision 재처리
- LLM disabled
- Mistral watch soft cap
- global monthly hard cap
- Kakao timeout/401/429/5xx
- 모바일과 데스크톱
- 관리자와 anonymous subscriber 권한
- 기존 live/brief/official integration regression

Ruff 기존 baseline 문제가 남아 있다면 신규·변경 파일의 오류를 우선 0으로 만들고 baseline 변화량을 기록한다. 자동 포맷으로 무관한 파일을 대량 변경하지 않는다.

## 16. 배포와 rollback

단계별 feature flag:

~~~dotenv
WATCH_ALERTS_ENABLED=0
WATCH_KAKAO_ENABLED=0
WATCH_LLM_ENABLED=0
WATCH_DIGEST_ENABLED=0
~~~

배포 순서:

1. migration
2. API 읽기 경로
3. watch-worker shadow mode
4. 운영자 detection 검증
5. in-app 알림 활성
6. Kakao test subscriber
7. 제한 사용자 활성
8. 전체 오픈 베타

shadow mode에서는 detection과 metric만 저장하고 notification outbox를 만들지 않는다.

rollback:

- feature flag로 worker와 provider를 중단
- migration 테이블과 원본 데이터는 삭제하지 않음
- 신규 UI를 숨기고 기존 회의 화면 유지
- 이미 전송한 알림 history 보존
- migration downgrade보다 forward fix 우선

## 17. 기록관리 규칙

### 17.1 단계 완료 기록

각 단계가 끝날 때 아래 표를 갱신한다.

| 단계 | 상태 | 완료일 | 커밋 | 테스트 | 실제 비용/사용량 | 비고 |
|---|---|---|---|---|---|---|
| A0 | COMPLETED | 2026-08-28 | 작업트리 | 182 tests | $0 | 브라우저 토큰 격리·허용목록 |
| A1 | COMPLETED | 2026-08-28 | 작업트리 | 182 tests | $0 | rule revision·적용시각 |
| A2 | COMPLETED | 2026-08-28 | 작업트리 | E2E | $0 | final 감지·in-app outbox |
| A3 | COMPLETED | 2026-08-28 | 작업트리 | 182 tests | $0 | 근거·deep link·반응형 UI |
| A4 | COMPLETED | 2026-08-28 | 작업트리 | 186 tests·disabled E2E | $0 | 독립 OAuth·Fernet·outbox retry, 외부 redirect 등록 전 OFF |
| A5 | COMPLETED | 2026-08-28 | 작업트리 | 186 tests·disabled E2E | $0 | evidence hash 캐시·$1 soft cap·세션 12회, 기본 OFF |
| A6 | COMPLETED | 2026-08-28 | 작업트리 | E2E | $0 | 화자별·10/15/30/60분·매회 |
| A7 | COMPLETED | 2026-08-28 | 작업트리 | 182 tests | $0 | FINAL 공식 근거 상태 |
| A8 | COMPLETED | 2026-08-28 | 작업트리 | E2E | $0 | 종료 digest dedupe |
| B1 | COMPLETED | 2026-08-28 | 작업트리 | auth 401/200 E2E | $0 | 자동판정 보존형 decision·세션 한정 운영 UI |
| B2 | COMPLETED | 2026-08-28 | 작업트리 | E2E | $0 | 지연·억제·공식확인율 API |
| B3 | COMPLETED | 2026-08-28 | 작업트리 | 182 tests | $0 | print/PDF·Markdown |
| B4 | COMPLETED | 2026-08-28 | 작업트리 | 182 tests | $0 | 상태 문구·문서·빈 상태 |

최종 배포 검증(2026-08-28): 전체 186 tests 통과, API health 200, 운영자 API 비인가/인가 401/200, 외부 알림 worker `claimed=0`, 선택형 LLM worker `DISABLED`·`$0.00`을 확인했다. 최근 실방송 audit 9건은 PASS 4건, PENDING 5건이며 PENDING은 공식자료 미연결·과거 수집 공백·국무회의 final 자막 미관측 조건을 성공으로 오인하지 않고 보존한 결과다.

허용 상태:

- NOT_STARTED
- IN_PROGRESS
- BLOCKED
- COMPLETED
- DEFERRED

### 17.2 구현 기록

각 단계 완료 시 다음을 기록한다.

- 변경 목적
- 실제 변경 파일
- migration 번호
- 신규 환경변수
- API 변경
- 테스트 수와 결과
- 실제 provider 요청 수·token·audio seconds·비용
- 알려진 제약
- rollback 방법

### 17.3 문서 동기화

- 사용자 기능: README.md
- 운영·장애 대응: docs/OPERATIONS.md
- 테이블·권위·상태: docs/DATA_MODEL.md
- 설계 변경: docs/DECISIONS.md
- 날짜별 결과: CHANGELOG.md
- 이 계획의 단계 현황: 현재 문서

### 17.4 변경 통제

다음 변경은 별도 설계 결정 기록이 필요하다.

- segment 안정화 조건 변경
- 알림 dedupe 범위 변경
- OFFICIAL_NOT_CONFIRMED 판정 조건 변경
- 사용자 credential 방식 변경
- watch LLM soft budget 상향
- Kakao 외 provider 추가
- semantic matching 기본 활성화
- 데이터 보존 기간 단축

## 18. 최종 완료 조건

Release A 완료:

- 화자 전환 전 final/stable segment에서 저지연 알림 가능
- 반복 발언은 누적되지만 정책에 따라 알림 억제
- in-app과 Kakao 중 하나의 장애가 다른 provider에 영향 없음
- 관련 발언 흐름과 실제 근거를 항상 확인 가능
- AI 통합 요약은 선택적이고 evidence/version/cache를 가짐
- rule 수정 이전 발언은 알림하지 않음
- 회의 종료 digest를 선택 가능
- 공식자료 후 CONFIRMED/CORRECTED/NOT_CONFIRMED 반영
- 공식자료 때문에 과거 알림을 재발송하지 않음
- 무료 예산 초과 시 감지·알림·근거가 계속 동작

Release B 완료:

- 사용자가 확인해야 할 항목을 즉시 파악
- 정상적인 공식자료 대기와 실제 검토 필요를 구분
- 처리시간과 건수를 실제 DB timestamp로 측정
- 공식확인율과 match 대비 알림 억제 효과를 실제 데이터로 설명
- 버튼 한 번으로 권위와 근거가 포함된 대응자료 생성
- 기존 live, brief, evidence, official integration 회귀 없음

## 19. 장기 기능

이번 구축 범위 밖:

- semantic matching
- 복합 matcher UI
- DOCX / HWPX
- SSO / 조직 계정
- 조직별 공유 관심주제
- SMS, 이메일 등 추가 provider
- 범정부 확산 아키텍처

장기 기능 때문에 Release A/B의 신뢰성, 비용 제한 또는 일정이 흔들려서는 안 된다.

## 20. 문서 변경 기록

| 날짜 | 버전 | 변경 |
|---|---|---|
| 2026-08-28 | 1.0 | 최종 보완 의견을 반영해 저지연 감지, 외부 알림 우선순위, 공식 미확인 상태, 무료 운영, 단계별 수용기준과 기록관리 규칙 확정 |
| 2026-08-28 | 1.1 | 상위 메뉴를 알람·실시간/회의 보고서로 이원화하고 저장된 live_insight 기반 무추가호출 실시간 초안, 종료 후 기존 브리프·공식통합 전환과 구현 상태 기록 |
| 2026-08-28 | 1.2 | 별도 테스트 화면을 제거하고 인증된 격리 transcript를 실제 국무회의 LIVE 인터페이스의 공통 렌더러로 표시하도록 확정 |
| 2026-08-28 | 1.3 | 변경된 알람·실시간/회의 보고서 구조를 기준으로 추가 정책, 종료 digest, 공식 확인, 운영 지표, 인쇄·Markdown과 무료 운영 제한 구현 기록. 외부 OAuth·관리자 인증 항목은 명시적으로 분리 |
| 2026-08-28 | 1.4 | 독립 Kakao OAuth/provider·암호화 토큰·retry worker, 선택형 evidence 기반 Mistral 요약과 soft cap, 관리자 결정 이력, 실방송 회귀 audit까지 구현. 외부 Kakao redirect 등록과 실제 방송 관측만 운영 활성화/실증 조건으로 분리 |
| 2026-08-28 | 1.5 | 최종 186 tests·배포 health·관리자 인증·비활성 provider 무비용 동작을 검증하고, 최근 실방송 audit PASS 4/PENDING 5의 관측 상태를 기록 |
| 2026-08-31 | 1.6 | 제438회 제05차 예결위 실방송에서 자막 2,420개·발언 묶음 578개·저장 주제 힌트 140개와 계속되는 갱신을 검증. PoC 7 전용 Kakao 설정·scope 확인·부트스트랩·공개 proxy 헤더/redirect 계약을 적용하고 189 tests와 공개 E2E 통과 |
