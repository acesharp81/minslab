# Operations

## OpenRouter 공용 게이트웨이

POC7 이미지 빌드 후 API와 워커보다 게이트웨이를 먼저 배포합니다.

```bash
sudo scripts/deploy_openrouter_gateway.sh
sudo scripts/deploy_api.sh
sudo scripts/deploy_live_capture_workers.sh
sudo scripts/deploy_secure_workers.sh all
```

`http://127.0.0.1:18071/internal/status`의 `reserved`가 POC4+POC7 **무료 모델** 합산 시도이며 운영 상한은 950, 공식 상한은 1,000입니다. `breakdown`은 무료 모델 장애 분석용이고 프로젝트별 별도 quota로 사용하지 않습니다. `external_breakdown`과 `external_monthly_breakdown`은 같은 OpenRouter 키를 직접 쓰는 PoC9 주문 대화의 모델·상태·토큰 메타데이터입니다. 여기에는 주문 문장과 응답이 저장되지 않으며, 이 유료 호출을 무료 950회에 합치지 않습니다. PoC9의 `npm run ai:usage`는 OpenRouter `/api/v1/key`의 실제 공유 키 잔액까지 함께 보여 줍니다. 계량 기록 API는 `OPENROUTER_METER_TOKEN`으로 인증합니다. gateway 컨테이너만 실제 OpenRouter key를 받으며 텍스트 워커는 `gateway-local` 토큰과 내부 URL만 받습니다.

자막 운영 상태는 live API의 `active_transcript_source`, `official_caption_state`, `stt_fallback_status`로 확인합니다. 국회 공식 자막 무수신 45초 후 `AI_STT`, 재수신 90초 후 `OFFICIAL_CAPTION`이 정상 전환입니다.

공식 자막 연결 장애를 늦게 발견해 STT 전환 이전 구간이 비어 있으면 국회가 실제 제공한 Quick VOD `EVENT` 재생목록과 시작 시각을 확인한 뒤 아래 복구 도구를 사용합니다. 도구는 STT 전환 경계 이전의 완성 구간만 최대 8개씩 병렬 수집해 원래 순서로 하나의 오디오를 만들고, Mistral STT는 누락구간 전체에 1회만 호출합니다. 같은 방송에 이미 Quick VOD 복구 자막이 있으면 재호출하지 않습니다.

```bash
sudo scripts/backfill_quick_vod.sh BROADCAST_ID PLAYLIST_URL PLAYLIST_START_AT --dry-run
sudo scripts/backfill_quick_vod.sh BROADCAST_ID PLAYLIST_URL PLAYLIST_START_AT
```


## 회의 보고서 후처리

국회 회의가 `ENDED`로 전환되면 60초 주기의 다음 worker cycle에서 비공식 회의 브리프 생성을 바로 시작합니다. 같은 방송이 속개되거나 늦은 final 자막이 추가되면 변경된 자막 cursor가 기존 캐시를 무효화해 새 발언까지 다시 통합합니다. 현재 분석 버전과 자막 cursor가 모두 일치할 때만 READY이며, 공식 회의록은 별도 5분 수집 경로에서 발표 즉시 대조합니다.

최종 분석은 발언 구간 → 8개 구간 단위 중간 병합 → 회의 전체 통합의 계층형 구조입니다. 각 구간과 중간 병합은 `meeting_brief_chunk_cache`에 내용 해시로 저장하므로 429·5xx·시간초과 뒤에도 완료 구간을 재호출하지 않습니다. 실시간 군집은 직접 근거와 엄격한 결정적 일치만 최종 주제에 붙이며, 어휘 후보와 다중 후보는 최종 화면 연결에서 제외하고 계보 감사 데이터에 남깁니다.

OpenRouter가 HTTP 200과 함께 닫히지 않은 `json_schema` 본문을 반환하면 gateway 원장에는 `invalid_structured_output` 실패로 남고 같은 idempotency key를 성공 재생하지 않습니다. 회의 보고서 워커는 형식 실패에 문장을 축약하고 JSON을 닫으라는 지침을 추가하며, 형식 실패·5xx·timeout 요청만 짧은 청크·병합은 Liquid, 긴 최종 통합은 Dots 3 Note로 재시도합니다. 정상 청크와 최종 통합의 기본 모델은 Nemotron을 유지합니다. 진행률이 같은 청크에서 멈춘 경우 gateway의 `FAILED` 증가와 worker 로그의 `MalformedMeetingBriefResponse`를 함께 확인합니다.

Dots 3 Note 무료 endpoint는 OpenRouter 공지상 2026-09-30 종료 예정이므로 최종 통합 재시도에만 제한합니다. 종료일 전 현재 무료 모델 목록에서 `json_schema`와 한국어 장문 통합을 실제 fixture로 통과한 대체 모델을 선정하고 `OPENROUTER_FINAL_RETRY_MODEL` 및 gateway 허용 목록을 함께 갱신합니다.

국무회의는 LIVE 캡처 유무와 무관하게 공식자료만으로도 완료할 수 있습니다. `official-minutes-worker`는 국회 공식 API 단계에서 오류가 나더라도 국무회의 공식자료 수집을 별도로 실행하며, `NATIONAL_ASSEMBLY_API_KEY`가 없는 국무회의 전용 실행 환경에서도 해당 수집은 계속됩니다. 로그의 `executive.official.completed`와 `parser_version`을 확인하고, 운영 snapshot의 parser version이 배포 버전보다 낮아지면 구형 워커가 같은 volume을 덮어쓰는지 점검합니다.

상세 공식자료가 공개되지 않은 부처보고의 `OFFICIAL_LIMITED`는 실패나 재시도 대기가 아닙니다. 화면에는 `공식자료만 반영 · 상세내용 미공개`로 표시하고 제목·소관 부처·연결된 대통령 지시만 제공합니다. 이후 새로운 공식 부처자료가 게시되어 content hash가 바뀌면 다음 수집에서 자동으로 상세 요약 상태로 승격합니다. 이 경로는 결정적 추출만 사용하며 LLM 호출은 0회입니다.

대통령 지시는 공식 브리핑의 source span 순서를 기준으로 주제 블록을 만듭니다. 명시된 안건명·정책명·사건명 또는 새 대통령 발언이 주제 경계가 되며, `이어·다만·이에`로 계속되는 실행 지시는 같은 블록에 둡니다. 블록 안에 기존 부처보고와 일치하는 공식 span이나 보수적 제목 일치가 있으면 그 보고 카드로 이동하고, 나머지만 `그 밖의 대통령 지시`에 남깁니다. 표시 요약과 별도로 `source_paragraphs` 및 `source_span_ids`를 보존하므로 묶음 결과에서 공식 원문을 다시 확인할 수 있습니다.


## 개발 배포

```bash
cp .env.example .env
docker compose up --build -d
curl -fsS http://127.0.0.1:8070/api/health
```

배포 과정에서 `web/` 디렉터리 또는 상위 checkout 디렉터리를 교체했다면 기존 bind mount가 이전 디렉터리를 계속 참조할 수 있으므로 API 컨테이너를 재시작만 하지 말고 재생성합니다.

```bash
docker compose up --build -d --force-recreate api
curl -fsS http://127.0.0.1:8070/api/health
curl -fsS http://127.0.0.1:8070/ >/dev/null
curl -fsS http://127.0.0.1:8070/assets/app.js >/dev/null
```

상태 판정은 `/api/health`만으로 끝내지 않습니다. 진입 HTML과 핵심 정적 자산이 모두 200이어야 사용자 준비 상태로 간주합니다.

공식 일정 수집과 정규화는 다음 순서로 실행합니다.

```bash
python3 scripts/fetch_schedule.py --date YYYY-MM-DD
PYTHONPATH=backend python3 -m app.ingestion.schedule_file
PYTHONPATH=backend python3 -m app.ingestion.committee_sync --date YYYY-MM-DD
PYTHONPATH=backend python3 -m app.ingestion.bill_sync --assembly-term 제22대
```

`docker compose up`은 `live-monitor`도 함께 기동합니다. worker는 브라우저와 무관하게 국회 공식 LIVE 목록을 30초마다 확인하고, `data/processed/live_status.json`을 원자적으로 교체하며, 감지된 방송의 `LiveBroadcast` 생명주기를 PostgreSQL에 저장합니다. 일회성 점검은 다음 명령을 사용합니다.

```bash
PYTHONPATH=backend python3 -m app.ingestion.live_monitor --once
```

`caption-worker`는 READY 상태 방송을 DB lease로 선점하고 최대 네 방송의 자막을 동시에 수집합니다. 메시지는 raw 저장 후 segment revision으로 적재하며, 15초 무수신 시 lease를 갱신합니다. 연결 종료·오류는 재시도 상태로 반환하되 연결 전 handshake 실패도 방송 감지 후 45초 장애 판정에 포함하여 `AI_STT` fallback을 시작합니다.

동시 수집은 `--workers 4`와 `FOR UPDATE SKIP LOCKED` claim으로 방송별 소유권을 분리합니다. 2026-08-31 운영 DB 감사에서는 목표 위원회 두 방송이 동시에 저장된 분 단위 구간 526개와 그 구간의 revision 83,347건을 확인했습니다. 관측된 최대 동시는 2개이며 4개 동시는 worker 계약 테스트로 보장하되, 실제 대상 3개 위원회와 본회의 동시 개회일에는 아래 항목을 다시 확인합니다.

- 각 LIVE 방송의 lease owner가 서로 다르고 `capture_status`가 `CAPTURING`인지
- 방송별 최신 final revision 시각이 함께 증가하는지
- 한 방송의 `broadcast_id`가 다른 방송 snapshot/delta에 섞이지 않는지

`schedule-worker`는 검증된 국회 `ALLSCHEDULE`의 `SCH_DT` 필터로 향후 7일 위원회 일정을 10분마다 조회합니다. KTV 공식 날짜별 편성표에서는 `국무회의`이면서 `생방송` 표지가 확인된 일정만 수집합니다. 최초 구축 때 최근 35일과 향후 7일을 한 번 백필하고, 이후에는 향후 7일을 6시간 캐시해 하루 최대 28회(7일 × 4회)만 요청합니다. 원본 응답과 manifest를 먼저 저장하고 PostgreSQL 정규화 후 공개 달력에서 국무회의·위원회를 함께 제공합니다. 국회 의사중계 당일 목록에서 `예정`으로 확인된 위원회와 KTV 생방송 편성 국무회의에만 `방송예정`을 표시하며 정례일을 추정 생성하지 않습니다. 과거 KTV 생방송 편성 또는 실제 종료 저장 기록과 같은 날짜·위원회가 일치하는 위원회 일정은 `방송 완료`로 표시합니다. 테스트·시연 방송은 완료 판정에서 제외합니다.

```bash
PYTHONPATH=backend python3 -m app.ingestion.schedule_worker --once --days 7
```


```bash
PYTHONPATH=backend python3 -m app.ingestion.caption_worker --workers 4
```

## 데이터

- PostgreSQL은 named volume에 저장합니다.
- Raw/processed 파일은 프로젝트 `data/`에 저장하되 Git에서 제외합니다.
- canonical 일정은 전체 원문을 보존하며 `is_target_committee`로 행안위·예결위·법사위 scope를 구분합니다.
- 운영 전 backup, retention, restore drill을 별도로 승인합니다.
- 회의록 API의 비대상 위원회 행은 raw에 남기되 canonical 회의록·의안 적재 대상에서는 제외합니다.
- 방송 metadata와 자막 revision은 PostgreSQL에 저장하고, 원본 source 응답은 raw artifact로 별도 보존합니다. 브라우저 local state를 수집 원장으로 사용하지 않습니다.

## 관측

향후 수집 worker 로그에는 `ingestion_run_id`, source type, external ID, HTTP 결과, retry 수, payload hash, parser version과 처리 건수를 포함합니다. secret이나 원문 전체를 로그에 출력하지 않습니다.

LIVE monitor의 기본 로그는 `checked_at`, 대상 `live_count`, `caption_ready`만 출력합니다. 상세 응답은 로그가 아니라 raw artifact로 보존합니다.

caption worker는 연결 종료 시 방송 ID별 저장·중복·오류 건수만 출력하며 자막 본문을 로그에 출력하지 않습니다.

중간 입장 화면은 snapshot의 `cursor`를 받은 뒤 2초마다 delta를 조회합니다. `has_more=true`이면 대기 없이 다음 묶음을 요청합니다. 네트워크 오류 시 5초 후 같은 cursor로 재시도하므로 이미 반영한 revision을 건너뛰지 않습니다.

`review-worker`는 종료 후 60초가 지난 방송을 10초마다 확인합니다. final 자막이 없으면 `NO_CONTENT`, 성공하면 `COMPLETED`, 오류는 최대 5회 `RETRY_WAIT` 후 `FAILED`로 기록합니다. 로그에는 방송 ID와 segment·topic 건수만 출력합니다.

```bash
PYTHONPATH=backend python3 -m app.ingestion.review_worker --once
```

## LLM 발언 요약 캐시

현재 발언 요약과 회의 보고서의 기본 provider는 OpenRouter다. 회의 보고서에 한해 Mistral Small 직접 호출을 별도 플랫폼 콜드 스탠바이로 준비한다. OpenRouter 안의 Nemotron·Dots·Liquid 교체는 모델 종료나 구조화 형식 오류 보정용이며 플랫폼 장애 예비로 계산하지 않는다. 원문은 선택 provider로 전송되므로 사전에 전송 범위와 API key를 승인해야 한다. API 요청 경로에서는 외부 LLM을 호출하지 않으며, 성공 결과는 `transcript_utterance_summaries`와 `meeting_briefs`에 저장한다. 같은 방송·원문 hash·prompt version으로 저장된 결과는 반복 호출하지 않는다. 실패하거나 캐시가 없는 발언은 기존 180자 발췌로 표시한다.

실시간 운영에서는 `summary-worker`가 2초마다 공식 국회 LIVE 방송을 확인합니다. 같은 화자의 연속 자막은 먼저 하나의 완결 발언으로 합치며, source가 non-final 자막을 잠시 빈 화자나 `-1`로 보내는 구간은 직전 확정 화자에 임시 연결해 거짓 전환으로 요약하지 않습니다. 요약 대상 발언의 원문 전체와 직전 최대 4개·직후 최대 2개의 완결 발언을 하나의 대화 문맥으로 선택 provider에 보내되, 결과는 대상 발언별로 저장합니다. LIVE에서는 진행 중인 마지막 발언을 제외하므로 실제 화자가 전환되어 닫힌 발언만 처리하고, 방송이 ENDED로 전환되면 마지막 발언까지 처리합니다. 화면 API는 이 워커가 저장한 캐시만 읽으며 화자 전환 뒤 제한된 snapshot 재조회로 새 DB 캐시를 반영합니다.

OpenRouter는 게이트웨이에서 UTC 일자별 요청을 원자 예약하며 공식 1,000회 중 950회를 운영 상한으로 사용합니다. 성공 여부와 관계없이 OpenRouter 외부 요청을 시도하기 전에 1회로 계산합니다. 알람 보고서는 조회 시 새 근거가 3개 이상일 때만 요청 플래그를 저장하고, 성공한 동일 근거 ID 집합·provider·model·prompt version은 DB 캐시를 재사용합니다. 브리핑은 종합 판단과 2~4개 통합 논점으로 저장합니다.

Mistral은 일일 호출 횟수나 고정 토큰 수로 차단하지 않습니다. 성공한 각 응답의 입력·출력 토큰과 국무회의 음성 전사 시간을 고유 request ID 기준으로 한 번만 저장하고, 현재 단가로 계산한 합산 비용이 `MISTRAL_MONTHLY_CREDIT_USD=10`에 도달하면 다음 요청을 중단합니다. 입력·출력·음성 단가가 다르므로 토큰 수 하나를 월 한도로 오인하지 않습니다. Mistral Studio의 Workspace 월간 지출 한도도 USD 10 이하로 별도 설정합니다.

```bash
AI_ENRICHMENT_ENABLED=1
LLM_PROVIDER=mistral
LLM_MODEL=mistral-small-2603
MISTRAL_BASE_URL=https://api.mistral.ai/v1
MISTRAL_MONTHLY_CREDIT_USD=10
MISTRAL_API_KEY=...

PYTHONPATH=backend python3 -m app.ingestion.summary_backfill \
  --broadcast-id cfa253d9-5ada-46e2-9f95-bdf55fb54046
```

### 회의 보고서 공급자 전환

OpenRouter 장애 또는 공용 한도 소진이 확인되면 PoC 7 `.env`에서 회의 보고서 전용 provider만 전환한다. 전역 `LLM_PROVIDER`는 바꾸지 않으므로 실시간 발언 요약과 다른 워커에 전파되지 않는다.

```bash
MEETING_BRIEF_PROVIDER=mistral
MEETING_BRIEF_MISTRAL_MODEL=mistral-small-2603
sudo scripts/deploy_secure_workers.sh meeting
```

Mistral 월 비용에는 Voxtral STT가 함께 포함되므로 `/api/ai/usage`의 잔액을 먼저 확인한다. 자동 전환은 사용하지 않는다. 복구 후에는 `MEETING_BRIEF_PROVIDER=openrouter`로 되돌리고 같은 명령으로 워커만 재생성한다.

로그에는 방송 ID, 대상·캐시·저장 건수와 API 호출 횟수만 남기며 API key와 자막 원문은 출력하지 않습니다.

### 비밀값 최소 주입

루트 `.env`를 컨테이너의 `env_file`로 직접 지정하지 않습니다. 루트 파일은 Compose 변수 치환에만 읽히며, 각 서비스의 `environment` 허용목록에 선언된 값만 컨테이너에 전달합니다. Mistral을 사용하는 워커만 `MISTRAL_API_KEY`를 받습니다.

현재 운영 서버에서는 전용 배포 스크립트가 루트·프로젝트 환경파일에서 서비스별 허용 변수만 권한 `0600`의 임시파일로 추출합니다. Docker에는 임시파일 경로만 전달하며 값은 명령행이나 로그에 나타나지 않습니다. 배포가 끝나면 임시파일은 즉시 삭제됩니다.

```bash
sudo scripts/deploy_secure_workers.sh all
```

다음 운영 원칙을 지킵니다.

- `docker inspect` 전체 결과나 `Config.Env` 값을 로그·티켓·대화에 출력하지 않습니다.
- 기존 환경을 복제할 때 `docker run -e KEY=value` 문자열을 생성하지 않습니다.
- 환경변수 존재 여부는 값 대신 변수 이름과 설정 여부만 안전한 상태 검사로 확인합니다.
- 중지된 롤백 컨테이너도 환경변수 원본을 보유하므로 검증이 끝나면 삭제합니다.

## 오픈 베타 회의 브리프

### 국무회의 LIVE 음성 처리

`executive-caption-worker`는 KTV 공식 편성에서 국무회의가 `ONAIR`로 확인된 동안, 또는 국회 공식 자막이 45초 이상 중단된 동안 공식 HLS 음성을 끊김 없이 계속 받아 60초 단위 MP3 원본으로 보존합니다. 녹음 producer와 전사 consumer를 분리했으므로 Mistral 응답을 기다리는 동안에도 다음 음성이 누락되지 않습니다. 완성된 청크는 `voxtral-mini-latest`의 diarization 전사로 처리하고 확정 구간을 국회 자막과 동일한 `transcript_segments`·revision 경로에 넣습니다. 따라서 화자 전환 요약, 실시간 주제, 자동 최신 발언 포커스, 종료 후 회의 브리프는 별도 국무회의 전용 비즈니스 로직이 아니라 기존 공통 기능을 사용합니다.

Mistral 전사는 기본 분당 USD 0.003으로 계산하여 `audio_usage_events`에 기록하고 텍스트 요약 비용과 월 USD 10 한도를 공유합니다. KTV가 자막 트랙을 제공하지 않아도 영상 음성으로 기록합니다. 방송 종료가 감지되면 상태를 `POST_PROCESSING`으로 바꾸고 마지막 부분 파일과 미처리 청크를 모두 전사한 뒤 `COMPLETED`로 전환합니다. 전체 발언 정리가 끝나기 전에는 결과 브리프 워커가 먼저 실행되지 않습니다.

종료 후처리 도중 워커가 재시작되면 만료된 lease의 `POST_PROCESSING` 방송을 다시 claim하여 저장된 원본 청크부터 이어서 처리합니다. 재시도 가능한 청크가 남아 있으면 `POST_PROCESSING`을 유지하고, 최대 재시도를 소진한 청크가 있으면 `FAILED`로 남겨 부분 결과를 완료 결과로 오인하지 않습니다. 청크 길이는 `ffprobe`로 측정하며 실제 누적 길이를 자막 시작 시각과 음성 비용 계산에 사용합니다.

실전 점검에서는 `executive.audio.started` 이후 약 한 청크 주기마다 `executive.audio.progress`가 증가하는지 확인합니다. 로그에는 방송 ID, 저장 청크 수, 전사 구간 수, 실패 수만 남기며 발언 본문과 API 키는 출력하지 않습니다.

공식 정책브리핑이 발행되면 `official-minutes-worker`가 회차와 서울 날짜가 일치하는 방송만 `executive_official_matches`에 연결합니다. 같은 회차 후보가 여러 개인데 날짜가 맞지 않으면 임의 연결하지 않습니다. 화면은 LIVE 임시 결과를 별도 회의로 중복 노출하지 않고 하나의 공식 결과로 전환하되, 각 보고 카드를 `부처 보고 내용 · 대통령 지시 · 부처 추가 발표`로 분리하고 심의안건을 별도 영역에 둡니다. 부처 보고 내용은 공식 보고 제목과 담당 부처를 기준으로 LIVE 보고서의 주제를 보수적으로 연결하며, 동점이거나 근거가 약하면 공식 보고 확인 문구만 제공합니다. 이 결합은 저장 자료와 규칙만 사용해 LLM을 추가 호출하지 않습니다.

```bash
sudo scripts/deploy_live_capture_workers.sh
docker logs --tail 50 poc07-national-assembly-executive-caption-worker
```

`meeting-brief-worker`는 최근 30일 공식 종료 방송을 60초마다 확인합니다. 발언 묶음의 저장 요약과 최대 700자 원문 발췌를 32개 이하 구간으로 분석한 뒤 회의 headline·요약·주제·화자 요지·과제를 한 번 더 통합합니다. 결과의 evidence ID는 현재 방송의 Utterance ID 집합으로 검증하며 근거가 없는 항목은 저장하지 않습니다.

브리프 1.1은 화자 요지와 주제 요약이 원문 문장을 그대로 복사하거나 통용 약어가 아닌 소문자 영문을 포함하면 저장을 거부하고 한 번만 교정 재요약합니다. 공식 통합 1.5는 공백·문장부호와 이동한 동일 문장을 변경 이력에서 제외하되 숫자·부정·결정/행위의 횟수와 기관-행위 결합이 달라지면 실제 변경으로 유지합니다. 유사도 0.58 미만의 전체 재작성은 잠정 본문에 적용하지 않고 공식 대안으로만 제공합니다. 공식 발언이 연결된 근거 조회는 공식 전체 발언만 반환하며 LIVE 조각과 혼합하지 않습니다.

기존 통합본을 비교 규칙 최신 버전으로만 재계산할 때는 `python -m app.ingestion.official_integration_worker --limit 50 --deterministic-only`를 사용합니다. 같은 공식 의미 해시와 저장된 검증 변경 목록이 없는 회의는 `SKIPPED_LLM_REQUIRED`로 건너뛰며, 이 모드에서는 외부 LLM을 호출하지 않습니다.

방송이 `ENDED`로 바뀌면 worker는 외부 LLM 호출 전에 deterministic 방송 리뷰와 현재 발언 묶음으로 `자동 정리 · 잠정` 결과를 먼저 저장합니다. 따라서 Mistral 월간 토큰 한도나 재시도 유예 중에도 공개 화면은 방송 포맷으로 되돌아가지 않고 결과 포맷을 유지합니다. 이후 Mistral 결과가 저장되면 더 최신 브리프가 같은 화면에 표시됩니다.

`meeting_briefs`의 유일 키는 방송·transcript hash·provider·model·prompt version입니다. worker를 반복 실행해도 `CACHED + api_requests=0`으로 종료합니다. 각 성공 응답의 실제 토큰은 다음 구간 호출 전에 월간 공용 장부에 기록합니다. 429는 30초·60초 대기 후 재시도하며 응답이 없는 실패 시도는 토큰 사용량으로 추정하지 않습니다. 그 밖의 실패는 `meeting_brief_failures`에 기록하고 기본 6시간 동안 재시도를 유예합니다.

```bash
PYTHONPATH=backend python3 -m app.ingestion.meeting_brief_worker --once --limit 5
PYTHONPATH=backend python3 -m app.ingestion.meeting_brief_worker \
  --broadcast-id cfa253d9-5ada-46e2-9f95-bdf55fb54046 --once
```

운영 화면 API는 저장된 브리프만 읽습니다. `/api/live/broadcasts/{id}/brief/evidence`는 선택한 주제·과제·화자 요지에 연결된 발언만 반환하고 외부 LLM을 호출하지 않습니다.

`official-minutes-worker`는 최근 30일 종료 방송 중 공식본 미게시 건을 5분마다 확인합니다. API 원본을 먼저 보존한 뒤 위원회+서울 날짜 후보가 하나일 때만 연결합니다. 동일한 의미의 본문은 발언과 주석을 다시 적재하지 않습니다. 후보가 없으면 `NOT_PUBLISHED`, 둘 이상이면 `AMBIGUOUS`로 남깁니다.

같은 회차에서 회의 안건의 `BILL_ID`는 확인됐지만 `bill_versions` 상세가 없는 의안은 최신 회의 순으로 한 주기당 20건씩 자동 동기화합니다. 공식 API에 상세가 아직 없으면 6시간 뒤, 일시 오류면 15분 뒤 재시도하며 다른 의안 처리는 계속합니다. 일상 운영에서는 별도 `bill_sync` 실행이 필요하지 않고, 전체 연결 의안을 강제로 새로 수집할 때만 수동 명령을 사용합니다.

`official-integration-worker`는 수집 워커와 독립적으로 15초마다 미처리 상태 큐를 확인합니다. 완료된 동일 브리프·공식문서·통합 버전은 다시 처리하지 않고, 만료된 lease와 재시도 시각이 된 실패 작업만 다시 선점합니다. 공식 본문이 publication보다 먼저 수집돼도 정확한 `meeting_id + conference_id`가 확인되면 자동 연결합니다.

```bash
PYTHONPATH=backend python3 -m app.ingestion.official_minutes_worker --once
PYTHONPATH=backend python3 -m app.ingestion.official_integration_worker --once --limit 5
docker logs --tail 50 poc07-national-assembly-official-integration-worker
```

운영 화면은 `OFFICIAL_PUBLICATION_PENDING`, `OFFICIAL_BODY_PENDING`, `COMPARISON_QUEUED`, `COMPARISON_PROCESSING`, `COMPARISON_RETRY_WAIT`, `COMPARISON_COMPLETE`를 사용자 문구로 변환합니다. `COMPARISON_RETRY_WAIT`이면 저장된 다음 재시도 시각을 확인하고, 같은 회의만 반복 실패할 때 공식 원본·본문 parser와 LLM 응답 오류를 각각 분리해 점검합니다.

## 장애 원칙
종료 방송 상세 API는 최신 공식 publication과 문서 버전, final 자막 exact 일치 수를 함께 반환합니다. `NOT_PUBLISHED`와 `AMBIGUOUS`는 정상적인 대기·검토 상태이며 LIVE 저장본을 삭제하거나 공식본으로 승격하지 않습니다.


API 실패는 기존 공식 데이터를 삭제하지 않습니다. schema 불일치 응답은 raw로 보존하고 canonical 반영을 중단합니다. 마지막 성공 시각과 source별 지연을 UI와 운영 상태에 표시합니다.

## LIVE 저장본과 공식 자료 매칭

저장 계층에서는 LIVE 잠정 브리프와 공식 회의록을 계속 분리합니다. 사용자 화면은 별도 탭을 두지 않고, 잠정 결과 위에 공식 자료로 확인된 변경 부분만 인라인으로 합성합니다. 수정·추가·삭제 문구에는 이전 내용과 공식 근거를 확인할 수 있는 tooltip을 제공하며 나머지 잠정 본문은 그대로 유지합니다.

매칭은 다음 단계로 진행합니다.

1. 공식 일정의 회의 identity와 LIVE 방송 identity를 날짜·위원회·회차로 연결합니다.
2. 공식 회의록이 발행되면 conference_id와 publication URL을 방송에 연결합니다.
3. 공식 발언 본문을 추출한 뒤 LIVE final revision과 공식 utterance를 순서·문자 구절로 대조하고 화자 표기를 보정합니다.
4. 근거가 확인된 주제·과제 변경만 적용합니다. 공식 문서에 없다는 이유만으로 잠정 내용을 자동 삭제하지 않습니다.
5. 화면은 발행 대기, 공식본 확인 중, 공식본 연결 완료를 구분하고 연결률과 미연결 건수를 숨기지 않습니다.

`GET /api/live/broadcasts/{broadcast_id}/brief`는 통합 읽기 모델과 변경 span, 화자 보정 통계를 함께 반환합니다. 동일 브리프·공식 문서·통합 버전 결과는 DB에서 재사용하므로 상세 화면을 다시 열어도 Mistral을 호출하지 않습니다. `/brief/official`은 이전 클라이언트 호환용 경량 endpoint로만 유지합니다.

## 관심주제 후속 처리

`watch-worker`는 final 자막 감지 외에 종료 세션 digest와 공식 정본 확인을 함께 수행합니다. digest는 사용자가 선택한 규칙에만 `digest:{rule_id}:{broadcast_id}` 중복키로 한 번 생성하며 저장된 발언 수·화자 수를 사용하므로 외부 모델을 호출하지 않습니다. 공식 확인은 `READY` 통합과 `FINAL · OFFICIAL` 문서가 모두 존재할 때만 실행하고, 새 통합 또는 새 문장 대조가 생긴 경우에만 갱신합니다.

```bash
sudo scripts/deploy_secure_workers.sh watch
curl -fsS -H "X-Watch-Token: $TOKEN" http://127.0.0.1:18070/api/watch/metrics
```

무료 기본값은 `WATCH_DIGEST_ENABLED=true`, `WATCH_KAKAO_ENABLED=false`, `WATCH_LLM_ENABLED=false`입니다. 사용자별 최근 알림 50건, 활성 규칙 20개, 테스트 방송 하루 3회를 서버에서 강제합니다. 회의 보고서의 인쇄와 `/brief.md` 다운로드도 저장된 결과만 사용하며 응답 헤더 `X-LLM-Calls: 0`으로 확인할 수 있습니다.

### 선택형 Kakao·통합 요약·운영 검토

Kakao는 PoC 7 callback URI를 Kakao Developers에 먼저 등록한 뒤 `WATCH_KAKAO_ENABLED=true`로 켭니다. 사용자는 동의 화면의 **[선택] 카카오 메시지 전송**에 동의해야 합니다. 토큰은 PoC 7 전용 `WATCH_KAKAO_TOKEN_ENCRYPTION_KEY`로 암호화하고 API 응답·로그에는 원문 토큰을 내보내지 않습니다. `notification-worker`는 `PENDING/FAILED` outbox를 lease로 claim하고 429·5xx·timeout만 지수 backoff로 최대 3회 재시도합니다. 401·403은 계정을 `REAUTHORIZE`로 바꾸며 in-app 알림은 이미 독립적으로 완료된 상태를 유지합니다.

`scripts/deploy_api.sh`와 `scripts/deploy_secure_workers.sh`는 부모 저장소나 PoC 4의 `.env`를 읽지 않습니다. 단독 배포에는 PoC 7 `.env`가 필요하며 `.env.example`에 전체 키 목록이 있습니다. 기존 앱 키를 이관할 때만 `scripts/bootstrap_poc07_env.py --source ...`를 한 번 사용하며 이후 source 파일은 필요하지 않습니다.

`watch-summary-worker`는 기본 OFF입니다. 활성화해도 신규 근거 3개, 30초 debounce, 세션 12회, 월 USD 1 soft cap과 전역 Mistral USD 10 한도를 함께 적용합니다. `watch_summary_versions.evidence_set_hash`가 같은 입력은 다시 호출하지 않고 화면은 저장 결과만 읽습니다.

#### 다중 기기 세션

Kakao callback은 Kakao 사용자 ID 단위 PostgreSQL advisory transaction lock을 건 뒤 기존 subscriber를 선택합니다. 새 PC의 익명 규칙은 동일 감지문구·기관·위원회 기준으로 기존 계정에 추가하되 기존 계정이나 다른 기기의 규칙·토큰을 자동 삭제하지 않습니다. callback 성공 시 새 `WatchWebSession`을 만들고 경로 제한 Secure HttpOnly 쿠키를 설정합니다. 구형 브라우저 token은 `/api/watch/session/upgrade`에서 1회 승격합니다.

세션 원문은 DB에 저장하지 않으며, 현재 기기는 `DELETE /api/watch/session/current`, 모든 기기는 `DELETE /api/watch/session/all`로 폐기합니다. Kakao 연결 해제는 세션 로그아웃과 다른 명시적 작업입니다.

#### 주문형 주제별 보고서

`POST /api/topic-reports/search`는 구조화된 회의 주제·소관부처·도출과제를 의미구조와 keyword overlap으로 순위화하며 LLM을 호출하지 않습니다. `POST /api/topic-reports`만 PENDING 작업을 만들고 `topic-report-worker`가 OpenRouter를 1회 호출합니다. 동일 query/evidence/provider/model/prompt READY 행은 재사용합니다.

외부 호출 전에 사용자 10회/UTC 일, 주제 보고서 100회/UTC 일을 검사하고 POC4·POC7 공용 gateway가 전체 950회/UTC 일 운영선을 원자 예약합니다. 실제 OpenRouter 키는 gateway에만 있고 `topic-report-worker`에는 `gateway-local` 값만 전달합니다. 요청은 공개 근거 최대 60,000자로 제한하고 식별 가능한 이메일·전화·주민번호 패턴을 제거합니다. gateway는 공개 데이터 class만 허용한 뒤 승인된 `data_collection=allow`, 무료 모델 fallback과 strict JSON schema를 적용합니다. 응답의 모든 evidence ID를 저장 snapshot과 대조하고 근거 본문이 2개 미만이면 저장하지 않습니다.

~~~bash
sudo scripts/deploy_secure_workers.sh topic-report
PYTHONPATH=backend python3 -m app.ingestion.topic_report_worker --once
~~~

운영 검토 API는 PoC 7 전용 `WATCH_ADMIN_TOKEN`을 `X-Watch-Admin-Token`으로 검증합니다. 화면 입력값은 `sessionStorage`에만 보존합니다. 검토 decision은 자동판정 원본과 별도 행이며 원본 상태를 갱신하지 않습니다.

~~~bash
sudo scripts/deploy_secure_workers.sh notification
sudo scripts/deploy_secure_workers.sh watch-summary
PYTHONPATH=backend python3 -m app.ingestion.live_regression_audit --limit 20
~~~

실방송 audit가 `PENDING`이면 실패나 통과로 바꾸지 않습니다. 실제 final 자막 또는 종료 후 공식 통합이 아직 관측되지 않았다는 뜻입니다. `REVIEW_REQUIRED`는 final 부재나 cursor 중복처럼 운영자가 확인해야 할 조건입니다.
