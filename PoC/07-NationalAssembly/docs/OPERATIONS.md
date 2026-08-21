# Operations

## 개발 배포

```bash
cp .env.example .env
docker compose up --build -d
curl -fsS http://127.0.0.1:8070/api/health
```

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

## LIVE E2E 데모

실제 방송이 없을 때도 서버 저장부터 중간 입장 snapshot, cursor delta, 종료 후 review 전환까지 같은 경로를 검증할 수 있습니다. 아래 데이터는 `poc07.demo` source system과 `SIMULATION` 표시로 공식 방송에서 격리됩니다.

```bash
PYTHONPATH=backend python3 -m app.ingestion.demo_live_replay --event-interval 3 --hold-seconds 1800
```

데모는 partial/final 자막 revision을 raw-first로 저장하고 지정 시간 동안 LIVE를 유지한 뒤 ENDED로 전환합니다. 공식 LIVE monitor는 `assembly.webcast.go.kr` 행만 종료하므로 데모 생명주기에 개입하지 않습니다.

`official-minutes-worker`는 최근 30일 종료 방송 중 공식본 미게시 건을 1시간마다 확인합니다. API 원본을 먼저 보존한 뒤 위원회+서울 날짜 후보가 하나일 때만 연결합니다. 후보가 없으면 `NOT_PUBLISHED`, 둘 이상이면 `AMBIGUOUS`로 남깁니다.

```bash
PYTHONPATH=backend python3 -m app.ingestion.official_minutes_worker --once
```

## 장애 원칙
종료 방송 상세 API는 최신 공식 publication과 문서 버전, final 자막 exact 일치 수를 함께 반환합니다. `NOT_PUBLISHED`와 `AMBIGUOUS`는 정상적인 대기·검토 상태이며 LIVE 저장본을 삭제하거나 공식본으로 승격하지 않습니다.


API 실패는 기존 공식 데이터를 삭제하지 않습니다. schema 불일치 응답은 raw로 보존하고 canonical 반영을 중단합니다. 마지막 성공 시각과 source별 지연을 UI와 운영 상태에 표시합니다.
