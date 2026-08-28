# Operations

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

`caption-worker`는 READY 상태 방송을 DB lease로 선점하고 최대 세 위원회 자막을 동시에 수집합니다. 메시지는 raw 저장 후 segment revision으로 적재하며, 15초 무수신 시 lease를 갱신하고 연결 종료·오류 시 재시도 상태로 반환합니다.

`schedule-worker`는 검증된 국회 `ALLSCHEDULE`의 `SCH_DT` 필터로 향후 7일 일정을 10분마다 조회합니다. 원본 응답과 manifest를 먼저 저장하고 PostgreSQL 정규화 후 `data/processed/upcoming_schedule.json`을 원자 교체합니다. 공개 화면은 기본적으로 오늘·내일만 읽습니다.

```bash
PYTHONPATH=backend python3 -m app.ingestion.schedule_worker --once --days 7
```


```bash
PYTHONPATH=backend python3 -m app.ingestion.caption_worker --workers 3
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

Mistral을 기본 provider로 사용하고 OpenRouter는 폴백으로 유지합니다. 원문은 선택 provider로 전송되므로 사전에 전송 범위와 API key를 승인해야 합니다. API 요청 경로에서는 외부 LLM을 호출하지 않으며, 성공 결과는 `transcript_utterance_summaries`에 저장합니다. 같은 방송·원문 hash·prompt version으로 저장된 요약은 provider나 model이 달라도 다시 호출하지 않습니다. 실패하거나 캐시가 없는 발언은 기존 180자 발췌로 표시합니다.

실시간 운영에서는 `summary-worker`가 2초마다 공식 국회 LIVE 방송을 확인합니다. 같은 화자의 연속 자막은 먼저 하나의 완결 발언으로 합치며, source가 non-final 자막을 잠시 빈 화자나 `-1`로 보내는 구간은 직전 확정 화자에 임시 연결해 거짓 전환으로 요약하지 않습니다. 요약 대상 발언의 원문 전체와 직전 최대 4개·직후 최대 2개의 완결 발언을 하나의 대화 문맥으로 선택 provider에 보내되, 결과는 대상 발언별로 저장합니다. LIVE에서는 진행 중인 마지막 발언을 제외하므로 실제 화자가 전환되어 닫힌 발언만 처리하고, 방송이 ENDED로 전환되면 마지막 발언까지 처리합니다. 화면 API는 이 워커가 저장한 캐시만 읽으며 화자 전환 뒤 제한된 snapshot 재조회로 새 DB 캐시를 반영합니다.

OpenRouter만 `llm_provider_daily_usage`에서 UTC 일자별 요청을 원자 예약하며 하루 500회를 넘기지 않습니다. 성공 여부와 관계없이 OpenRouter 외부 요청을 시도하기 전에 1회로 계산합니다.

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

`executive-caption-worker`는 KTV 공식 편성에서 국무회의가 `ONAIR`로 확인된 동안 공식 HLS 음성을 끊김 없이 계속 받아 60초 단위 MP3 원본으로 보존합니다. 녹음 producer와 전사 consumer를 분리했으므로 Mistral 응답을 기다리는 동안에도 다음 음성이 누락되지 않습니다. 완성된 청크는 `voxtral-mini-latest`의 diarization 전사로 처리하고 확정 구간을 국회 자막과 동일한 `transcript_segments`·revision 경로에 넣습니다. 따라서 화자 전환 요약, 실시간 주제, 자동 최신 발언 포커스, 종료 후 회의 브리프는 별도 국무회의 전용 비즈니스 로직이 아니라 기존 공통 기능을 사용합니다.

Mistral 전사는 기본 분당 USD 0.003으로 계산하여 `audio_usage_events`에 기록하고 텍스트 요약 비용과 월 USD 10 한도를 공유합니다. KTV가 자막 트랙을 제공하지 않아도 영상 음성으로 기록합니다. 방송 종료가 감지되면 상태를 `POST_PROCESSING`으로 바꾸고 마지막 부분 파일과 미처리 청크를 모두 전사한 뒤 `COMPLETED`로 전환합니다. 전체 발언 정리가 끝나기 전에는 결과 브리프 워커가 먼저 실행되지 않습니다.

종료 후처리 도중 워커가 재시작되면 만료된 lease의 `POST_PROCESSING` 방송을 다시 claim하여 저장된 원본 청크부터 이어서 처리합니다. 재시도 가능한 청크가 남아 있으면 `POST_PROCESSING`을 유지하고, 최대 재시도를 소진한 청크가 있으면 `FAILED`로 남겨 부분 결과를 완료 결과로 오인하지 않습니다. 청크 길이는 `ffprobe`로 측정하며 실제 누적 길이를 자막 시작 시각과 음성 비용 계산에 사용합니다.

실전 점검에서는 `executive.audio.started` 이후 약 한 청크 주기마다 `executive.audio.progress`가 증가하는지 확인합니다. 로그에는 방송 ID, 저장 청크 수, 전사 구간 수, 실패 수만 남기며 발언 본문과 API 키는 출력하지 않습니다.

공식 정책브리핑이 발행되면 `official-minutes-worker`가 회차와 서울 날짜가 일치하는 방송만 `executive_official_matches`에 연결합니다. 같은 회차 후보가 여러 개인데 날짜가 맞지 않으면 임의 연결하지 않습니다. 화면은 LIVE 임시 결과를 별도 회의로 중복 노출하지 않고 공식 `부처보고 · 심의안건 · 대변인 브리핑` 결과로 전환합니다.

```bash
sudo scripts/deploy_secure_workers.sh executive
docker logs --tail 50 poc07-national-assembly-executive-caption-worker
```

`meeting-brief-worker`는 최근 30일 공식 종료 방송을 60초마다 확인합니다. 발언 묶음의 저장 요약과 최대 700자 원문 발췌를 32개 이하 구간으로 분석한 뒤 회의 headline·요약·주제·화자 요지·과제를 한 번 더 통합합니다. 결과의 evidence ID는 현재 방송의 Utterance ID 집합으로 검증하며 근거가 없는 항목은 저장하지 않습니다.

브리프 1.1은 화자 요지와 주제 요약이 원문 문장을 그대로 복사하거나 통용 약어가 아닌 소문자 영문을 포함하면 저장을 거부하고 한 번만 교정 재요약합니다. 공식 통합 1.2는 숫자·부정·정책 의미가 바뀌지 않은 개조식/서술식 전환을 변경 이력에서 제외합니다. 공식 발언이 연결된 근거 조회는 공식 전체 발언만 반환하며 LIVE 조각과 혼합하지 않습니다.

방송이 `ENDED`로 바뀌면 worker는 외부 LLM 호출 전에 deterministic 방송 리뷰와 현재 발언 묶음으로 `자동 정리 · 잠정` 결과를 먼저 저장합니다. 따라서 Mistral 월간 토큰 한도나 재시도 유예 중에도 공개 화면은 방송 포맷으로 되돌아가지 않고 결과 포맷을 유지합니다. 이후 Mistral 결과가 저장되면 더 최신 브리프가 같은 화면에 표시됩니다.

`meeting_briefs`의 유일 키는 방송·transcript hash·provider·model·prompt version입니다. worker를 반복 실행해도 `CACHED + api_requests=0`으로 종료합니다. 각 성공 응답의 실제 토큰은 다음 구간 호출 전에 월간 공용 장부에 기록합니다. 429는 30초·60초 대기 후 재시도하며 응답이 없는 실패 시도는 토큰 사용량으로 추정하지 않습니다. 그 밖의 실패는 `meeting_brief_failures`에 기록하고 기본 6시간 동안 재시도를 유예합니다.

```bash
PYTHONPATH=backend python3 -m app.ingestion.meeting_brief_worker --once --limit 5
PYTHONPATH=backend python3 -m app.ingestion.meeting_brief_worker \
  --broadcast-id cfa253d9-5ada-46e2-9f95-bdf55fb54046 --once
```

운영 화면 API는 저장된 브리프만 읽습니다. `/api/live/broadcasts/{id}/brief/evidence`는 선택한 주제·과제·화자 요지에 연결된 발언만 반환하고 외부 LLM을 호출하지 않습니다.

`official-minutes-worker`는 최근 30일 종료 방송 중 공식본 미게시 건을 1시간마다 확인합니다. API 원본을 먼저 보존한 뒤 위원회+서울 날짜 후보가 하나일 때만 연결합니다. 후보가 없으면 `NOT_PUBLISHED`, 둘 이상이면 `AMBIGUOUS`로 남깁니다.

```bash
PYTHONPATH=backend python3 -m app.ingestion.official_minutes_worker --once
```

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
