# POC4·POC7 OpenRouter 통합 및 Mistral 최소화 실행 계획

- 작성 기준일: 2026-09-08, 구현 검증 갱신 2026-09-09 (Asia/Seoul)
- 범위: POC4 Master Press, POC7 National Assembly
- 상태: 2026-09-09 공개 공식자료·공개 뉴스에 대한 무료 provider 데이터 보존/학습 허용 승인을 반영해 전체 운영 전환을 완료했다. POC4 OpenRouter 보조 worker와 POC7 OpenRouter 텍스트 worker가 활성 상태이며, Mistral 자격 증명은 Voxtral STT worker에만 남아 있다.

## 1. 결론

1. POC4의 `google/gemma-4-26b-a4b-it:free`는 종료된 모델이 아니다. OpenRouter 공식 목록에는 무료 모델로 남아 있고 최근 3일 uptime도 100%로 표시된다.
2. POC4의 실제 실패 원인은 2026-09-08 기준 Google AI Studio 공유 upstream pool의 지속적인 HTTP 429이다. 모델 존속 여부와 실제 계정·시점의 공급 가능성은 별개다.
3. POC4와 POC7은 서로 다른 로컬 장부를 사용하므로 현재 구조로는 합산 1,000회를 원자적으로 보장할 수 없다. 모든 OpenRouter 전송을 하나의 공용 관문에서 승인·기록해야 한다.
4. POC4 OpenRouter는 부스터와 단건 잔여 처리만 맡기고 NVIDIA/OpenAI/Groq/Cloudflare 기본 작업의 선점·대기·동기 fallback 경로에서 제거한다.
5. POC7의 텍스트 생성은 검증된 OpenRouter 무료 모델 풀로 이전한다. Mistral은 기계 판독 가능한 공식 자막이 없거나 장애가 지속되는 구간의 STT fallback에만 사용한다.
6. 공식 자막이 회복되면 안정화·중복 대조 후 공식 자막으로 자동 복귀한다. AI STT는 `PROVISIONAL`, 공식 자막은 `LIVE/OFFICIAL` 권위를 유지하고 원본을 덮어쓰지 않는다.
7. 공식 국무회의 자막이 안정적인 기계 판독 피드로 확인되면 Mistral 사용량은 0이 될 수 있다. 그렇지 않아도 현재 Mistral 텍스트 6,139,041토큰과 454회는 제거 가능하고, 현재 기간 비용 기준 약 88.4%가 줄어든다.

## 2. 확인된 현재 상태

### POC4

- 기본 OpenRouter 모델: `google/gemma-4-26b-a4b-it:free`
- 용도: 단건 케이스 판정, 공통분석 backlog 부스터, 기본 배치 JSON 실패 시 단건 복구
- 2026-09-08 09:00 KST 이후 확인된 OpenRouter 전송: 27회
- 결과: 27회 모두 HTTP 429
- upstream 응답: `google/gemma-4-26b-a4b-it:free is temporarily rate-limited upstream`
- 제한 출처: `upstream_provider_shared_pool`, upstream provider `Google AI Studio`
- 같은 시점 OpenRouter 공식 모델 페이지에는 모델이 무료·운영 중으로 표시된다.
- 별도 문제: `openrouter_usage_today()`는 성공 호출만 `attempts`로 계산한다. 실패와 retry도 공급자 한도에 영향을 줄 수 있으므로 합산 장부로 사용할 수 없다.
- 별도 문제: OpenRouter 단건 worker가 가용으로 판단되면 NVIDIA/OpenAI worker는 일부 미지정 단건을 양보한다. 기본 모델 우선순위에 간접 영향이 있다.
- 별도 문제: NVIDIA/OpenAI 배치 JSON이 비정상이면 같은 기본 worker 실행 안에서 OpenRouter 단건 호출을 동기 수행한다. OpenRouter 지연이 기본 worker를 붙잡을 수 있다.
- 운영 로그에는 OpenRouter 오류 외에 POC4 SQLite `database is locked`도 1건 확인됐다. 공용 한도 장부를 POC4 SQLite에 추가하면 lock 경쟁이 더 커질 수 있다.

### POC7

- 텍스트 기본: Mistral `mistral-small-2603`
- 국무회의 STT: Mistral `voxtral-mini-latest`
- 선택형 OpenRouter 기본: `dots-studio/dots-3-note-preview:free`
- 현재 기간 Mistral 텍스트: 454회, 입력 4,887,490토큰, 출력 1,251,551토큰
- 현재 기간 Mistral STT: 65회, 3,879.828초, USD 0.193991
- 현재 기간 Mistral 총비용: USD 1.678046
- POC7 OpenRouter 일일 예약은 PostgreSQL 안에서는 원자적이지만 POC4 장부와 분리돼 있다.
- 현재 `/api/ai/usage`는 설정된 요약 provider 하나만 주 화면에 반환한다. Mistral과 OpenRouter를 동시에 표시하지 못한다.
- `dots-studio/dots-3-note-preview:free`는 OpenRouter 공식 페이지상 2026-09-30 종료 예정이다. 장기 기본 모델로 두면 안 된다.
- 발언 요약은 provider 교체가 가능하지만 회의 브리프와 공식 의미 교정에는 Mistral 조건·client가 하드코딩된 곳이 남아 있다.
- 국회는 공식 `xsami` WebSocket 자막을 수집하고 STT를 사용하지 않는다.
- 국무회의는 KTV HLS에 별도 VTT/subtitle group이 없다는 2026-08-25 표본을 근거로 항상 Voxtral 경로에 등록된다. 공식 자막 탐색→STT fallback→공식 복귀의 일반 상태 머신은 아직 없다.

## 3. 목표 모델 라우팅

| 업무 | 1순위 | 2순위/실패 처리 | 원칙 |
|---|---|---|---|
| POC4 공통 기본분석 | 현행 Groq/Cloudflare 기본 체인 | 기존 예비 체인 | OpenRouter가 선점하거나 기다리게 하지 않음 |
| POC4 케이스 기본판정 | NVIDIA, OpenAI 기존 순서 | 기존 결정론 fallback | OpenRouter와 독립 |
| POC4 단건 잔여판정 | OpenRouter 허용 모델 풀 | 결정론 보류/다음 주기 | 기본 worker가 처리하지 못한 aged residual만 |
| POC4 backlog 부스터 | OpenRouter 허용 모델 풀 | 즉시 반납 | 전역 사용량이 낮고 backlog 기준 충족 시만 |
| POC7 실시간 발언 요약 | OpenRouter | 캐시/규칙 기반 요약 | 여러 발언을 묶어 호출 |
| POC7 종료 회의 브리프 | OpenRouter | 저장 발언 요약+결정론 브리프 | 변경 구간만 생성 |
| POC7 공식본 의미 교정 | 결정론 diff 후 OpenRouter | 검토 필요 표시 | 의미 변경 후보가 있을 때만 |
| POC7 주문형/관심주제 보고 | OpenRouter | 저장 결과/결정론 보고 | 기존 요청형·cache 원칙 유지 |
| 국회·국무회의 실시간 자막 | 기계 판독 공식 자막 | Mistral Voxtral STT | STT는 자막 gap에만 사용 |

POC7의 Mistral 텍스트 client는 운영 경로에서 제거한다. 라이브 처리의 완결성은 특정 텍스트 provider 가용성에 의존하지 않으며, OpenRouter가 소진돼도 원문 수집·알림 규칙·검색·결정론 보고는 계속 동작해야 한다.

## 4. 공용 OpenRouter 관문

### 필요한 이유

두 프로젝트가 각각 `현재 사용량 < 1000`을 검사하면 동시에 마지막 슬롯을 사용할 수 있다. 사후 합산 화면은 초과를 보여줄 뿐 초과 자체를 막지 못한다. 요청 전에 공용 트랜잭션으로 슬롯을 예약해야 한다.

### 형태

- 독립된 경량 `openrouter-gateway` 컨테이너 1개를 운영한다.
- OpenRouter API key는 관문에만 둔다. POC4·POC7 worker에서는 제거한다.
- 관문은 짧은 트랜잭션만 수행하는 전용 SQLite WAL 장부를 사용한다. POC4의 1.5GB 업무 DB와 분리한다.
- POC4는 host loopback `127.0.0.1:18071`로 호출한다.
- POC7 worker는 전용 Docker network의 `poc07-openrouter-gateway:8071`로 호출한다. 외부 공개 포트는 열지 않는다.
- 관문 장애 시 각 프로젝트는 결정론 fallback으로 진행하고 기본 모델 worker를 중단시키지 않는다.

### 장부 규칙

- 공급자 기준일: UTC 00:00, 한국시간 09:00 초기화
- `reserved`, `inflight`, `completed`, `failed`, `canceled_before_send`를 분리한다.
- 실제 HTTP 전송을 시작한 모든 시도를 1회로 계산한다. HTTP 429·5xx와 모델 fallback 재시도도 각각 1회다.
- 전송 전에 취소된 예약만 반환한다.
- idempotency key를 `project + workload + source hash + prompt version`으로 구성해 중복 예약·재호출을 방지한다.
- OpenRouter 429의 `X-RateLimit-*`, `Retry-After`, upstream provider와 model을 저장한다.
- OpenRouter `/api/v1/key`는 credit 상태 보조 확인용으로 사용하고, 일일 요청 장부는 로컬 관문을 권위값으로 삼는다.

### 한도와 동시성

- 공식 무료 한도: 1,000회/UTC day
- 운영 허용선: 950회
- 안전 여유: 50회. 운영 외 수동 호출·계측 오차·공급자 계산 차이를 흡수한다.
- 시작 속도: 전체 18 RPM token bucket
- 최대 동시 전송: 초기 4개, 부하 시험 후 조정
- 같은 모델 upstream 429 발생 시 해당 모델만 circuit open하고 다른 허용 모델로 이동한다.
- 서로 다른 API key를 추가해 한도를 늘리는 방식은 사용하지 않는다. OpenRouter 문서도 account-global capacity임을 명시한다.

### 사용량 기반 workload 차단선

프로젝트별 고정 할당은 두지 않는다. 대신 업무 중요도와 현재 합산 사용량으로 제어한다.

| 합산 사용량 | 허용 업무 |
|---:|---|
| 0~699 | 전체 허용 |
| 700~849 | POC4 부스터 중지, 과거 대량 backfill 중지 |
| 850~949 | 라이브·종료 필수 분석과 aged 단건만 허용 |
| 950 이상 | 외부 호출 중지, cache/결정론 fallback만 사용 |

우선순위는 `POC7 라이브 신규 발언 > POC7 종료 필수 브리프 > POC4 aged 단건 잔여 > POC7 공식본/주문형 > POC4 부스터 > 모든 backfill`이다. 낮은 순위가 영구 대기하지 않도록 aging을 적용하되 상한 차단선은 넘지 않는다.

## 5. POC4 기본 모델 비간섭 보장

1. NVIDIA/OpenAI 기본 케이스 worker가 `OpenRouter available` 상태 때문에 미지정 작업을 양보하지 않게 한다.
2. 기본 worker 내부의 `_recover_case_batch_json_with_single()` OpenRouter 동기 호출을 제거한다.
3. 배치 JSON 실패 항목은 별도 residual 상태로 다시 큐잉한다. 기본 worker는 즉시 다음 기본 작업으로 이동한다.
4. OpenRouter 단건 worker는 기본 lane이 한 차례 처리했거나 일정 시간 이상 남은 residual만 claim한다.
5. 부스터 worker는 공통 큐의 oldest 항목을 바로 선점하지 않고, 기본 lane 대기시간·backlog·전역 700회 미만을 모두 만족할 때만 claim한다.
6. OpenRouter circuit·gateway 장애는 POC4 provider priority 계산에 반영하지 않는다. 보조 worker만 쉬게 한다.

수용 기준: OpenRouter를 강제로 429/timeout으로 만들어도 NVIDIA/OpenAI/Groq/Cloudflare worker의 처리량·claim 순서·평균 대기시간이 기준 대비 5% 이상 악화되지 않아야 한다.

## 6. POC7 호출량 압축과 Mistral 제거

### 텍스트

- 발언 요약 batch를 현재 최대 2개에서 품질 표본을 통과한 8~12개까지 확대한다.
- 입력 글자수·토큰 상한을 동시에 적용해 긴 발언은 안전하게 나눈다.
- 회의 브리프는 원문 전체를 매번 재요약하지 않고 저장된 발언 요약과 결정론 topic cluster를 사용한다.
- transcript hash가 바뀌면 변경된 chunk와 최종 synthesis만 갱신한다.
- 공식본 통합은 숫자·부정·정책 주체·기한의 결정론 diff를 먼저 실행하고 의미 변경 후보가 0이면 호출하지 않는다.
- 같은 evidence hash·model·prompt version은 프로젝트와 화면 재진입에 관계없이 재사용한다.
- live day에는 backfill을 중지하고 다음 저수요 UTC day로 넘긴다.

현재 454회의 Mistral 텍스트 호출 구성상 발언 요약 batching과 회의 브리프 증분화를 적용하면 현재 범위에서 약 65~75%의 호출 압축을 목표로 할 수 있다. 이후 남은 텍스트 호출만 OpenRouter로 이전한다.

### Mistral 잔존 조건

- 텍스트 생성: 0회 목표
- STT: 공식 기계 판독 자막이 없는 gap에만 허용
- 공식 자막이 전체 회의를 덮으면 Mistral 0회
- Mistral 월 budget 소진 시 원문 영상은 계속 보존하되 `TRANSCRIPT_UNAVAILABLE`을 명시하고 텍스트 생성 모델을 STT 대용으로 사용하지 않는다.

## 7. 공식 자막→STT fallback→공식 복귀

### 공식 자막 탐색 순서

1. 국회 `xsami` WebSocket
2. KTV HLS master의 `EXT-X-MEDIA:TYPE=SUBTITLES`
3. KTV media stream 내부 embedded caption/방송 자막 stream
4. 청와대·대한민국정부 공식 live player의 caption track
5. 종료 후 공식 영상 자막·브리핑·회의록

영상 픽셀에 합성된 글자만 있고 독립 텍스트 track이 없으면 기계 판독 자막 미제공으로 본다. 검증되지 않은 endpoint나 비공개 export를 추측해 사용하지 않는다.

### 상태 머신

```text
OFFICIAL_ACTIVE
  └─ 30~60초 무수신/연결 오류 → OFFICIAL_SUSPECT
       ├─ 재연결 성공 → OFFICIAL_ACTIVE
       └─ 재연결 실패 + 영상 정상 → AI_STT_FALLBACK
            └─ 공식 자막 연속 정상 수신 → RECOVERING
                 ├─ 60~120초 overlap 정렬 성공 → OFFICIAL_ACTIVE
                 └─ 정렬/수신 불안정 → AI_STT_FALLBACK
```

### gap 손실 방지

- 공식 자막 사용 중에도 외부 STT 호출 없이 최근 2~3분의 저용량 오디오 ring buffer 또는 HLS segment reference를 유지한다.
- outage 확정 시 마지막 공식 자막 시각부터 필요한 gap만 Voxtral로 전사한다.
- 복구 시점 뒤의 미전송 audio chunk는 취소하고, 이미 전송된 요청 결과만 gap 후보로 저장한다.

### 복구·중복 대조

- 공식 자막이 최소 60초 또는 연속 N개 final segment 동안 정상이고 cursor/timestamp가 전진할 때 복구로 인정한다.
- 2~5분 hysteresis/cooldown으로 source flapping을 막는다.
- 공식 자막과 STT를 시간 범위, 정규화 문장, 화자 순서로 정렬한다.
- 동일 구간의 canonical 표시는 공식 자막을 사용한다.
- STT revision은 `PROVISIONAL` provenance로 보존하고 공식 원본을 덮어쓰지 않는다.
- 요약·알림 idempotency key는 source segment가 아니라 논리 발언과 시간 범위를 기준으로 해 이중 생성·이중 발송을 막는다.
- 공식 복구 후 의미가 달라진 잠정 요약만 invalidation하고, 동일 의미 결과는 재호출하지 않는다.

필요 schema는 기존 단일 `capture_status`를 source별 상태로 분리하거나 별도 `transcript_source_sessions`를 추가해 `source`, `authority`, `started_at`, `ended_at`, `failure_reason`, `last_event_at`, `recovery_overlap`을 기록하는 방식으로 확장한다.

## 8. 무료 모델 수명주기와 대체 후보

하나의 무료 모델을 영구 하드코딩하지 않는다. 허용 모델 registry에 다음을 저장한다.

- model ID, 가격 0 여부, 종료/deprecation 표시
- text/JSON object/JSON schema 지원
- context/output 한도
- provider와 data policy
- 최근 health probe 시각과 실제 업무 schema 통과 여부
- circuit 상태와 마지막 성공 시각

현재 후보:

| 후보 | 장점 | 제약 | 계획상 용도 |
|---|---|---|---|
| `nvidia/nemotron-3-super-120b-a12b:free` | strict structured output 지원 | 단일 endpoint 과부하 가능 | 허용 풀 1순위 |
| `liquid/lfm-2.5-2.6b:free` | strict structured output 지원, fallback 실호출 성공 | 소형 모델이라 복잡한 장문 합성은 회귀 검증 필요 | 허용 풀 2순위 |
| `google/gemma-4-26b-a4b-it:free` | 기존 prompt 호환, JSON object 지원 | 2026-09-08 Google 공유 pool 429 지속, strict schema 미지원 | 회복 후 보조 후보 |
| `dots-studio/dots-3-note-preview:free` | 현재 POC7 성공 이력, JSON schema 지원 | 2026-09-30 종료 예정 | 전환 기간에만 사용, 신규 장기 기본 금지 |

`openrouter/free` 임의 router는 모델·정책·출력 재현성이 바뀌므로 판정·공식 비교의 기본값으로 사용하지 않는다. allowlist 안에서만 model fallback을 허용한다.

## 9. 화면과 운영 지표

POC4와 POC7의 OpenRouter 표시는 같은 gateway status를 사용한다.

- `합산 사용 30 / 운영 허용 950 / 공식 한도 1000`
- 완료·실패·진행 중·전송 전 취소
- 현재 RPM, in-flight, queue 길이
- UTC reset과 한국시간 표시
- 열려 있는 model circuit과 최근 upstream 오류
- 잔여 workload 단계: 전체/부스터 중지/필수만/외부 호출 중지

POC7 `/api/ai/usage`는 단일 provider 응답을 `providers[]`로 확장해 다음을 동시에 표시한다.

- Mistral: 텍스트 토큰·텍스트 비용·STT 분·STT 비용·월 예산
- OpenRouter: POC4+POC7 합산 일일 요청·운영선·공식 한도·reset

메인 화면에서는 프로젝트별 할당을 표시하지 않는다. 다만 장애 분석을 위한 관리자 drill-down에는 workload·model·status별 집계를 남긴다.

## 10. 구현 단계

### 0단계 — 기준선 고정

- 최근 14일 POC4/POC7 요청·성공·실패·latency·업무별 호출 수 snapshot
- 기존 accepted 결과를 회귀 fixture로 고정
- 국무회의 실제 live 1회와 국회 caption 장애 fixture 확보

### 1단계 — 공용 관문과 읽기 화면

- gateway ledger, idempotency, 950 hard operational cap, 18 RPM, in-flight 4
- 두 프로젝트는 우선 shadow reservation만 기록하고 기존 직접 호출과 수치를 대조
- POC4/POC7 화면을 합산 값으로 전환
- 차이가 0인지 확인 후 key를 gateway로 이동

### 2단계 — POC4 격리와 모델 교체

- 동기 OpenRouter fallback 제거
- residual/booster lane 분리
- 후보 모델 schema·한국어·판정 회귀 시험
- 통과 모델을 allowlist primary로 활성화하고 Gemma 공유 pool 429 circuit 검증

### 3단계 — POC7 텍스트 이전

- 발언 요약 batch 확대
- 회의 브리프·공식 교정 client를 provider-neutral interface로 변경
- Mistral 텍스트 credential을 관련 worker에서 제거
- 캐시 재사용·증분 처리 검증 후 OpenRouter 전환

### 4단계 — 자막 자동 fallback·복귀

- 공식 KTV/청와대 caption contract 재검증
- source health 상태와 audio ring buffer 추가
- outage gap만 Voxtral 전사
- recovery overlap·공식 우선 canonical view·중복 알림 방지

### 5단계 — 요청 범위 확대

- 기존 3개 핵심 위원회는 상시 포함하고, 정기국회·국정감사 표식이 있는 본회의/기타 위원회는 자동 포함
- 정기국회·국정감사 실제 1주간 shadow estimate
- POC7 live 호출이 집중일에도 600회/일 이하인지 확인
- 합산 850회 경고, 950회 차단과 backfill pause를 fault test한 뒤 단계 확대

## 11. 검증 시나리오와 통과 기준

### 모델 품질

- POC4 과거 단건 100건: JSON 유효 99% 이상, 필수 필드 100%, false-negative가 기준보다 1%p 이상 악화되지 않음
- POC7 발언 batch 30개·회의 브리프 10건·공식 변경 10건: evidence ID 존재율 100%, 미근거 숫자·주체 추가 0건, 한국어 완결성 99% 이상
- 모델별 timeout/429/404/malformed JSON을 fixture로 재현

### 합산 한도와 동시성

- POC4·POC7에서 동시에 100개씩 예약해도 합산 counter가 정확히 200 증가
- 949에서 두 요청이 동시에 오면 하나만 승인되고 950에서 정지
- retry와 model fallback은 각각 새 1회로 증가
- 같은 idempotency key 동시 요청은 외부 전송 1회
- 18 RPM 이상 시작하지 않으며 in-flight 4를 넘지 않음

### 기본 모델 비간섭

- gateway down, OpenRouter 429, malformed JSON 각각에서 POC4 기본 worker는 계속 처리
- OpenRouter ON/OFF 시 기본 lane 처리량·평균 대기시간 차이 5% 이내
- OpenRouter worker는 기본 lane job lease를 소유하지 않음

### 자막 전환

- 공식 자막 정상: Mistral 호출 0
- 45초 무수신: gap 시작부터 STT fallback
- 공식 자막 60초 안정 복구: overlap 정렬 후 공식 자막 복귀
- 10초 단위 반복 장애: hysteresis로 flapping 방지
- 공식/STT 중복 구간: 화면 발언·요약·알림 각각 1개
- Mistral budget 소진: 영상/공식 자막 수집은 계속되고 상태가 명확히 표시

## 12. 배포와 rollback

- feature flag: `OPENROUTER_GATEWAY_ENABLED`, `OPENROUTER_TEXT_MIGRATION_ENABLED`, `CAPTION_STT_FAILOVER_ENABLED`, `CAPTION_AUTO_RECOVERY_ENABLED`
- 1차는 관문 shadow count, 2차는 POC4 보조 호출, 3차는 POC7 주문형, 4차는 POC7 실시간 요약 순으로 확대한다.
- 각 단계에서 직접 provider 경로는 짧은 rollback 기간 동안 비활성 설정으로 보존하되 API key는 동시에 두 경로에 두지 않는다.
- rollback은 provider를 Mistral로 되돌리는 것이 아니라 해당 AI 기능을 cache/결정론 모드로 내리는 것을 기본으로 한다. STT만 자막 gap에서 Mistral로 유지한다.

## 13. 최종 수용 조건

- 두 화면의 OpenRouter 합산값과 gateway ledger가 동일하다.
- 어떤 동시 요청에서도 운영 허용선 950, 공식 한도 1,000을 넘지 않는다.
- POC4 기본 모델의 우선순위와 처리량이 OpenRouter 장애에 영향받지 않는다.
- POC7 Mistral 텍스트 호출이 0이다.
- 공식 자막 정상 구간의 Mistral STT 호출이 0이다.
- 자막 장애 구간만 STT로 채워지고 회복 후 공식 자막으로 자동 복귀한다.
- 정기국회·국정감사 집중일 예상치가 `POC7 live ≤ 600`, `합산 < 850`을 만족한다. 만족하지 않으면 대상 확대 전에 batch/caching을 추가 조정한다.

## 14. 구현·운영 검증 결과 (2026-09-09)

- 공용 gateway: UTC 일자 기준 공식 1,000회, 운영선 950회, 안전 여유 50회, 18 RPM, 최대 동시 4개를 원자적으로 적용했다.
- 활성화 검증 시 합산 장부: 94회 예약(성공 38, 실패 56), 잔여 운영 한도 856회이며 POC7 `/api/ai/usage`와 gateway 값이 일치한다. 이 중 실패 46회는 gateway 도입 전 POC4 이력 import다.
- POC4: 기본 공통·NVIDIA·OpenAI worker는 활성, OpenRouter 단건·부스터 worker는 별도이며 30초 residual 우선순위와 700회 부스터 차단선을 적용했다. 호환 체인에서도 OpenRouter를 마지막 순위로 내렸다.
- POC7: 발언 batch를 최대 8개/12,000자로 확대하고, 회의 브리프·공식 교정·관심주제·주문형 보고 client를 OpenRouter 호환으로 변경했다.
- 모니터링: 국무회의 + 기존 3개 위원회 + 정기국회 + 국정감사 필터를 반영했다. 운영 일정 worker가 2026-09-09~15 구간 대상 9건을 생성했다.
- 자막: 국회 공식 WebSocket 우선, 45초 무수신 시 Voxtral STT, 공식 자막 90초 안정 수신 시 공식 자막으로 자동 복귀하고 STT 중지를 요청한다. KTV 표본 HLS에는 독립 자막 track이 없어 현재 국무회의는 STT를 사용한다.
- Mistral 비용 표시의 STT 중복 가산을 제거했다. 현재 정확한 총비용은 USD 1.678046이며 텍스트 비용 USD 1.484055를 OpenRouter로 옮기면 현재 기준 약 88.4%가 감소한다.
- 테스트: POC4 핵심 171개와 최종 POC7 관련 86개가 통과했고, Python 구문·compose 파싱·`git diff --check`도 통과했다.
- 데이터 정책: 현재 무료 endpoint는 `data_collection=deny`/ZDR 조건에서 사용할 수 없어, 2026-09-09 명시 승인에 따라 공개 공식자료·공개 뉴스에만 `data_collection=allow`를 적용했다. gateway는 `public_official`·`public_web_news` 외 요청을 403으로 차단하고 승인된 무료 모델 fallback 정책을 덮어써서 강제한다.
- 자격 증명: 실제 OpenRouter 키는 gateway만, Mistral 키는 Voxtral STT worker만 보유한다. POC7 텍스트 worker는 `gateway-local` 식별값만 사용하고 Mistral·Gemini 키를 받지 않는다.

## 15. 작성 시점 검증 기록

- OpenRouter 공식 model catalog: Gemma 4 26B A4B free가 현재 catalog에 존재함을 확인
- OpenRouter 공식 model page: Gemma 4 무료 endpoint의 최근 3일 uptime 100%, availability 98.86% 표시 확인
- POC4 운영 DB: 2026-09-08 09:00 KST 이후 27건 모두 Google AI Studio shared upstream pool 429임을 확인
- POC7 운영 DB: 같은 UTC day OpenRouter 예약 3회 확인. 따라서 현재 실제 합산 전송/예약 관점의 관측값은 최소 30회지만, 기존 두 화면은 이를 하나의 값으로 표시하지 못함
- POC7 운영 API: Mistral 텍스트 454회·6,139,041토큰, STT 65회·3,879.828초·총 USD 1.678046 확인
- OpenRouter 공식 model page: POC7의 Dots3-Note Preview free가 2026-09-30 종료 예정임을 확인
- OpenRouter 공식 limits 문서: 한도는 API key를 늘려 우회할 수 없고 account-global로 관리되며, 429가 OpenRouter 플랫폼 또는 upstream provider 양쪽에서 발생할 수 있음을 확인
- POC4 기준선 unittest 5개 통과: 실패 호출 미차감, 성공 soft limit, 단건 claim, 배치 JSON의 동기 OpenRouter 복구, 부스터 reserve 동작
- POC7 기준선 unittest 18개 통과: 국회/KTV source 계약, 공식 자막 저장, executive STT, provider factory, POC7 내부 OpenRouter 원자 한도와 retry 예약
- 문서 검사: `git diff --check` 통과를 최종 확인 대상으로 둠

공식 참고:

- OpenRouter limits: https://openrouter.ai/docs/api_reference/limits
- Gemma 4 free: https://openrouter.ai/google/gemma-4-26b-a4b-it:free/providers
- Dots3-Note Preview free: https://openrouter.ai/dots-studio/dots-3-note-preview:free
- gpt-oss-20b free: https://openrouter.ai/openai/gpt-oss-20b:free/providers
