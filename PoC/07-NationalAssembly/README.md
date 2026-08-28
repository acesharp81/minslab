# 07 · 지금 우리 회의에선

국회와 국무회의의 **예정 일정 → 생방송 기록 → AI 잠정 정리 → 공식 자료 반영**을 한 화면에서 이어 보는 회의 정보 서비스입니다. 사용자는 회의에서 무엇을 논의했고 어떤 과제가 남았는지를 먼저 확인하고, 필요할 때만 근거 발언과 공식 원문을 펼쳐 볼 수 있습니다.

이 문서는 다음 두 독자를 위한 통합 안내서입니다.

- **서비스 사용자**: 일정, 생방송, 요약, 도출 과제, 근거 발언과 공식 수정 내용을 확인하는 방법
- **시스템 운영자**: 설치, 설정, 수집 워커, AI 비용, 모니터링, 재처리, 장애 대응과 보안 운영 방법

> 현재 단계는 실제 수집 자료를 사용하는 오픈 베타입니다. 데모 회의는 사용자 목록에 노출하지 않습니다. AI 결과는 근거 발언 ID가 있는 잠정 정보이며, 공식 자료가 발표되면 동일 회의 안에서 보완됩니다.

## 제공 기능

### 공통

- 국회와 국무회의를 같은 회의 생명주기와 결과 화면으로 처리합니다.
- 오늘의 예정 회의를 상단 전광판에서 5초간 보여 준 뒤 2초 동안 위로 전환합니다. 화살표와 키보드로 직접 이동할 수도 있습니다.
- 회의 목록은 시작 시각 기준 최근 순으로 20건을 먼저 읽고, 끝으로 이동할 때 10건씩 추가합니다.
- 생방송 여부, 기록·정리 상태, 공식 자료 확정 여부, 국회·국무회의 유형을 독립된 태그로 표시합니다.
- 가장 최근에 끝난 회의를 기본 선택하며, 공식 자료가 새로 반영된 과거 회의도 다시 노출합니다.
- PC, 노트북, 태블릿, 휴대전화 폭에 맞춰 재배치됩니다. 작은 화면에서는 근거 발언 영역이 본문 아래로 이동합니다.

### 국회

- 행정안전위원회, 예산결산특별위원회, 법제사법위원회의 공식 일정과 생방송을 집중 감시합니다.
- 국회 공식 생방송 자막을 저장하고, 같은 화자의 연속 자막 조각을 한 발언 묶음으로 합칩니다.
- 화자가 전환되면 완료된 발언 묶음 전체를 한 번 요약해 DB에 저장합니다.
- 실시간으로 파악한 주요 주제와 잠정 과제를 영상 오른쪽에 한 줄씩 누적합니다.
- 방송 종료 후 전체 발언을 다시 분석해 논의 주제, 화자별 요지, 도출 과제와 담당 부처 후보를 구성합니다.
- 공식 회의록이 발표되면 위원회와 서울 기준 일자로 매칭하고 공식 완성형 문장과 화자 정보를 반영합니다.
- 회의별 의안, 처리 결과와 본회의 표결이 명시적 순번으로 연결될 때 함께 표시합니다.

대상 확대는 구동 로직을 복제하지 않고 수집 대상 설정과 업무 분류 규칙을 추가하는 방식으로 처리합니다.

### 국무회의

- KTV 공식 일정과 HLS 생방송을 감지합니다.
- 공개 HLS에 기계 판독 가능한 자막 트랙이 없으면 60초 단위 오디오를 저장하고 Voxtral로 전사합니다.
- 국회와 같은 발언 묶음, 실시간 요약, 종료 후 브리프, 공식 자료 매칭 흐름을 사용합니다.
- 결과는 **부처보고 → 심의안건 → 대변인 브리핑** 순서로 정리합니다.
- 중복 접두어 대신 기관명만 간결하게 표시합니다.
- 대통령 지시사항은 관련 주제 안에 대상 부처와 함께 별도로 표시합니다.
- 같은 날의 명시적 관련 부처 브리핑은 제목, 핵심 요약과 원문 링크로 연결할 수 있습니다.
- 회차와 서울 기준 일자를 우선 사용해 라이브 기록과 공식 자료를 연결합니다.

KTV 화면에 사람이 읽는 자막이 포함될 수는 있지만 현재 공개 플레이어에서는 안정적으로 수집 가능한 별도 텍스트 자막 피드가 확인되지 않았습니다. 국무회의 라이브 자막은 오디오 전사 결과이며 공식 속기록과 동일한 정확도를 보장하지 않습니다.

## 사용자 안내

### 1. 상단 정보

- **예정 회의 전광판**: 오늘 예정된 회의 제목, 시각과 장소
- **생방송 중 / 방송없음**: 현재 감지된 공식 방송 유무
- **AI 사용량**: 플랫폼, 모델, 현재 사용량, 최대 한도와 다음 갱신 시각

예정 회의는 결과 카드에 섞이지 않습니다. 좌우 버튼이나 키보드 방향키로 다른 일정을 볼 수 있습니다. 모션 감소 설정을 사용하는 기기에서는 자동 전환 효과가 줄어듭니다.

### 2. 회의 카드와 태그

각 카드는 태그, 굵은 제목, 일시·장소·상세보기의 세 줄로 구성됩니다.

| 태그 | 의미 |
|---|---|
| 진행중 | 공식 생방송이 현재 진행 중 |
| 완료 | 방송 또는 회의가 종료됨 |
| 기록 중 | 자막이나 오디오를 실시간 저장 중 |
| 정리중 | 종료 후 전체 요약·근거 연결을 생성 중 |
| 비공식 정리 | AI 잠정 결과를 볼 수 있음 |
| 공식정리 | 공식 회의록 또는 브리핑이 반영됨 |
| 국회 / 국무회의 | 회의 출처 |

생명주기와 자료 권위는 별개입니다. 예를 들어 **완료 + 정리중**은 회의는 끝났지만 결과 생성이 진행 중이라는 뜻입니다.

### 3. 생방송 화면

- 영상은 16:9 비율로 표시됩니다.
- 오른쪽 **주요 주제와 과제**에는 현재까지 확인된 주제, 대상 부처와 과제 수가 짧게 쌓입니다. 영상 높이를 넘으면 이 영역만 스크롤됩니다.
- 시네마 모드를 켜면 오른쪽 패널이 숨겨지고 영상이 넓어집니다.
- 영상 아래에는 현재 화자와 바로 전 화자의 발언 묶음을 우선 표시합니다.
- 같은 화자의 새 자막은 현재 묶음 끝에 계속 누적되며 최신 내용으로 자동 이동합니다.
- **원문 전체 보기**를 열어 둔 상태는 새 자막이 들어와도 유지됩니다.
- 진행 중인 발언은 임의로 잘라 요약하지 않습니다. 화자가 바뀐 뒤 완료된 묶음만 요약합니다.

원본 자막이 0, 1 같은 채널 번호만 제공하면 실제 인물로 추정하지 않고 **화자 미확인**으로 취급합니다. 운영자가 확인한 이름을 임시 보완할 수 있고, 공식 회의록이 발표되면 공식 화자 기준으로 분리하거나 합칩니다.

### 4. 종료 회의 결과

결과 화면은 원문보다 결론을 먼저 보여 줍니다.

1. **요약된 논의 주제**와 **도출 과제**를 제목 한 줄씩 표시합니다.
2. 제목을 누르면 해당 **주요 논의 내용**으로 이동합니다.
3. 주제 아래에 화자별 주요 내용을 표시합니다.
4. 관련 과제가 있으면 같은 주제 아래에 **과제 + 내용 + 원문보기** 구조로 붙습니다.
5. 주제, 화자 요지 또는 과제를 누르면 근거 발언을 확인할 수 있습니다.

PC에서는 근거 발언 패널이 논의 내용을 스크롤해도 화면 안에 따라옵니다. 이 패널은 요약문을 중복 표시하지 않고 **화자명 + 해당 자막 묶음의 전체 문장**을 보여 줍니다. 핵심은 단어나 문장 전체가 아니라 짧은 핵심 문구로 최대 3곳만 강조합니다.

### 5. 정리 중인 회의

방송 직후에는 전체 화면을 막지 않습니다. 요약된 논의 주제와 도출 과제 영역만 흐리게 처리하고 **전체 N개 발언 중 M개 정리 완료**와 같은 진행 현황을 표시합니다. 기본 회의 정보와 저장된 자막은 계속 볼 수 있고, 처리가 끝나면 같은 화면에서 결과가 갱신됩니다.

### 6. 공식 자료와 변경 표시

임시 결과와 공식 결과를 별도 탭으로 중복 제공하지 않습니다. 공식 자료가 들어오면 같은 결과 안에서 의미 있는 변경만 반영합니다.

- 바뀐 문구는 굵기와 색으로 표시합니다.
- 마우스를 올리거나 포커스하면 이전 내용, 변경 내용, 추가 또는 삭제 이유를 확인할 수 있습니다.
- 개조식과 서술식처럼 의미가 같은 문체 변경은 가능한 한 변경으로 잡지 않습니다.
- 공식 완성형 발언이 있으면 파편화된 라이브 자막 대신 공식 문장을 근거 발언에 사용합니다.
- 공식 자료에서 화자가 여러 명으로 확인되면 묶음을 나누고, 같은 화자로 확인되면 합칩니다. 화자 분리·병합 자체는 사용자용 변경 이력으로 표시하지 않습니다.
- 원본 라이브 자막과 공식 원문은 삭제하지 않고 출처가 다른 버전으로 보존합니다.

| 권위 수준 | 뜻 |
|---|---|
| LIVE | 방송 중 수집한 원문 또는 전사 |
| PROVISIONAL | AI 또는 규칙 기반 잠정 정리 |
| OFFICIAL | 공식 회의록·브리핑·안건 원문 |
| RULE LINK | 양쪽 공식 원문에서 주제와 핵심어가 겹친 잠정 연결. 인과관계 확정이 아님 |

## 전체 처리 흐름

~~~text
공식 일정 수집
  → 생방송 감지
  → 자막/오디오 원본 보존
  → 같은 화자의 연속 자막을 발언 묶음으로 누적
  → 화자 전환 시 묶음 요약·주제·잠정 과제 저장
  → 방송 종료 후 전체 회의 브리프 생성
  → 공식 회의록/브리핑 탐색 및 안전한 매칭
  → 공식 완성형 문장·화자·안건 반영
  → 의미 있는 변경만 사용자 화면에 표시
~~~

외부 AI는 API 조회 때마다 호출되지 않습니다. 워커가 결과를 한 번 생성해 DB에 저장하며 같은 방송, 같은 본문 해시, 같은 프롬프트 버전은 캐시를 재사용합니다.

## 운영자 빠른 시작

### 요구 사항

- Docker Engine과 Docker Compose 플러그인
- 공식 데이터 수집을 위한 네트워크 연결
- 국회 API를 사용할 경우 NATIONAL_ASSEMBLY_API_KEY
- AI 요약을 사용할 경우 MISTRAL_API_KEY
- 선택적 대체 경로를 사용할 경우 OPENROUTER_API_KEY
- 국무회의 오디오 전사를 사용할 경우 Mistral/Voxtral 사용 권한

### 1. 환경 설정

~~~bash
cd PoC/07-NationalAssembly
cp .env.example .env
~~~

.env에서 DB 비밀번호와 필요한 API 키를 설정합니다. 전체 변수와 기본값은 [.env.example](.env.example)을 기준으로 합니다.

~~~dotenv
AI_ENRICHMENT_ENABLED=1
LLM_PROVIDER=mistral
LLM_MODEL=mistral-small-2603
MISTRAL_MONTHLY_CREDIT_USD=10
EXECUTIVE_TRANSCRIPTION_MODEL=voxtral-mini-latest
EXECUTIVE_AUDIO_CHUNK_SECONDS=60
OPENROUTER_DAILY_LIMIT=500
~~~

- Mistral 한도는 호출 횟수가 아니라 실제 입력·출력 토큰과 오디오 분을 USD로 환산해 월 10 USD 내에서 관리합니다.
- OPENROUTER_DAILY_LIMIT=500은 OpenRouter를 사용할 때만 적용되며 Mistral 호출에는 적용하지 않습니다.
- 공급자 가격이 바뀌면 .env.example의 입력·출력 백만 토큰당 비용과 오디오 분당 비용을 운영자가 갱신해야 합니다.
- AI를 끄려면 AI_ENRICHMENT_ENABLED=0으로 설정합니다. 원본 수집과 공식 자료 기능은 계속 동작하지만 AI 요약은 생성되지 않습니다.

### 2. 실행

Compose 네트워크가 없으면 한 번만 생성합니다.

~~~bash
docker network inspect poc07-national-assembly
docker network create poc07-national-assembly
~~~

첫 명령이 성공하면 두 번째 명령은 실행하지 않습니다.

~~~bash
docker compose up --build -d
~~~

이미지는 시작할 때 DB migration을 자동 적용합니다. 소스가 교체된 배포에서는 API 컨테이너를 재생성합니다.

~~~bash
docker compose up --build -d --force-recreate api
~~~

### 3. 기동 확인

~~~bash
docker compose ps
curl -fsS http://127.0.0.1:8070/api/health
curl -fsS http://127.0.0.1:8070/api/meta
~~~

- 독립 실행: http://127.0.0.1:8070/
- OpenAPI: http://127.0.0.1:8070/docs
- 통합 홈페이지: /poc/national-assembly/

통합 홈페이지는 부모 서비스의 NATIONAL_ASSEMBLY_UPSTREAM을 통해 이 앱으로 프록시합니다. 배포 환경에서 독립 서비스가 127.0.0.1:18070을 사용하도록 구성할 수 있지만 이 Compose의 기본 포트는 8070입니다.

### 4. 로그와 종료

~~~bash
docker compose logs --tail=200 api
docker compose logs --tail=200 live-monitor caption-worker summary-worker
docker compose down
~~~

docker compose down은 기본적으로 DB 볼륨을 삭제하지 않습니다. 운영 데이터가 있는 환경에서는 down -v를 사용하지 마십시오.

## Compose 서비스

| 서비스 | 기본 주기/병렬도 | 역할 |
|---|---:|---|
| api | 상시 | 화면, 조회 API, 저장된 근거·브리프 제공 |
| db | 상시 | PostgreSQL 영속 저장소 |
| live-monitor | 30초 | 국회와 KTV 공식 생방송 감지 |
| schedule-worker | 10분, 7일 범위 | 국회 공식 예정 일정 동기화 |
| caption-worker | 3 workers | 국회 공식 자막 WebSocket 수집·정규화 |
| executive-caption-worker | 5초 | KTV HLS 오디오 수집과 Voxtral 전사 |
| summary-worker | 2초 | 완료된 화자 발언 묶음의 요약·주제·과제 생성 |
| review-worker | 10초 | 종료 방송의 규칙 기반 잠정 리뷰 생성·복구 |
| meeting-brief-worker | 60초 | 전체 발언 기반 회의 주제·과제 브리프 생성 |
| official-minutes-worker | 1시간 | 국회 공식 회의록 수집과 라이브 결과 재조정 |

모든 워커는 같은 PostgreSQL을 사용합니다. 화면 API는 외부 AI를 직접 호출하지 않으므로 사용자가 새로고침해도 토큰이 반복 소비되지 않습니다.

## 수동 실행과 재처리

아래 명령은 프로젝트 디렉터리에서 실행합니다. Compose가 정상이라면 일상 운영에 수동 실행은 필요하지 않습니다.

### 일정과 공식 데이터

~~~bash
python3 scripts/fetch_schedule.py --date YYYY-MM-DD
PYTHONPATH=backend python3 -m app.ingestion.schedule_file
PYTHONPATH=backend python3 -m app.ingestion.committee_sync --date YYYY-MM-DD
PYTHONPATH=backend python3 -m app.ingestion.bill_sync --assembly-term 제22대
~~~

### 워커 1회 점검

~~~bash
PYTHONPATH=backend python3 -m app.ingestion.live_monitor --once
PYTHONPATH=backend python3 -m app.ingestion.schedule_worker --once
PYTHONPATH=backend python3 -m app.ingestion.review_worker --once
PYTHONPATH=backend python3 -m app.ingestion.executive_caption_worker --once
PYTHONPATH=backend python3 -m app.ingestion.summary_worker --once
PYTHONPATH=backend python3 -m app.ingestion.meeting_brief_worker --once
PYTHONPATH=backend python3 -m app.ingestion.official_minutes_worker --once
~~~

### 공식 자료 재조정

~~~bash
PYTHONPATH=backend python3 -m app.ingestion.official_integration_worker
PYTHONPATH=backend python3 -m app.ingestion.revalidate_official_integration --help
~~~

official_integration_worker는 지정된 대기 건을 한 번 처리하고 종료합니다. 특정 방송만 강제 재처리해야 할 때는 --help에서 broadcast-id와 force 옵션을 확인한 뒤 실행합니다.

운영 원칙은 삭제 후 재생성이 아니라 저장된 원본과 버전을 유지한 채 새 통합 결과를 추가하는 것입니다.

## AI 요약과 비용

### 호출 단위

- 실시간: 자막 한 조각마다 호출하지 않고 화자 전환으로 닫힌 **발언 묶음 전체**를 한 번 호출합니다.
- 문맥: 대상 발언과 함께 앞쪽 최대 4개, 뒤쪽 최대 2개 묶음을 사용할 수 있습니다.
- 진행 중인 마지막 발언: 계속 바뀌므로 닫히기 전에는 요약하지 않습니다.
- 종료 후: 저장된 발언 요약과 근거 원문을 청크로 묶어 전체 회의 브리프를 만듭니다.
- 공식 자료 반영: 잠정 결과와 공식 원문 사이에서 의미가 달라진 부분만 통합합니다.

### 중복 방지

요약은 방송 ID, 본문 해시와 프롬프트 버전을 키로 DB에 저장합니다. 같은 입력은 캐시를 사용하며 API 요청이나 화면 새로고침으로 재호출하지 않습니다. 프롬프트 버전 또는 원문이 바뀐 경우에만 새 결과를 만들 수 있습니다.

### 사용량 확인

~~~bash
curl -fsS http://127.0.0.1:8070/api/ai/usage
~~~

상단 UI와 이 API에서 공급자, 모델, 현재 사용량, 최대 한도와 갱신 시각을 확인합니다. Mistral 월 예산에는 텍스트 요약과 국무회의 오디오 전사 비용이 함께 반영됩니다. 오디오 전사 기본 추정치는 EXECUTIVE_TRANSCRIPTION_USD_PER_MINUTE=0.003입니다.

한도를 초과하거나 키가 없으면 AI 작업은 실패 상태로 남고 원본은 보존됩니다. 키를 보완하거나 한도가 갱신된 뒤 워커를 다시 실행하면 처리할 수 있습니다.

## 공식 자료 매칭 원칙

- 국회: 같은 위원회와 서울 기준 일자에 공식 회의록 후보가 하나일 때만 자동 매칭합니다.
- 국무회의: 회차와 서울 기준 일자를 우선 사용하고 동일 대표 회의 안에 부처보고·심의안건·브리핑을 묶습니다.
- 후보가 없으면 UNRESOLVED, 여러 개면 CONFLICT, 안전하게 하나로 확정되면 MATCHED로 관리합니다.
- 모호한 후보를 제목 유사도만으로 강제 연결하지 않습니다.
- 수집 API가 실패해도 이미 저장한 공식 데이터는 삭제하지 않습니다.
- 원본 응답, 자막, 오디오와 공식 문서는 provenance와 함께 보존합니다.

공식 문서가 아직 발표되지 않은 상태는 오류가 아닐 수 있습니다. 회의 종료 직후에는 정리중 또는 비공식 정리가 정상이며, 공식 회의록 발표 후 공식정리로 전환됩니다.

## 모니터링과 장애 대응

### 기본 점검 순서

1. /api/health를 확인합니다.
2. docker compose ps에서 API, DB와 워커 상태를 확인합니다.
3. 문제 서비스의 최근 로그를 확인합니다.
4. /api/live/status, /api/live/broadcasts, /api/ai/usage로 저장 상태와 한도를 확인합니다.
5. 원본이 저장됐는지 확인한 뒤 해당 워커를 --once로 재실행합니다.

| 증상 | 우선 확인 | 조치 |
|---|---|---|
| 홈페이지 Internal Server Error | api, db, migration 로그, /api/health | DB 연결과 컨테이너 상태 확인 후 API 재생성 |
| 상단은 보이나 회의 호출 실패 | 브라우저 네트워크, 프록시 upstream | NATIONAL_ASSEMBLY_UPSTREAM과 API 포트 확인 |
| 생방송 감지 실패 | live-monitor와 공식 소스 응답 | live_monitor --once 실행 |
| 국회 영상은 나오나 자막 없음 | caption-worker, WebSocket 준비 상태 | worker 재기동, 공식 자막 제공 여부 확인 |
| 국무회의 자막 없음 | executive-caption-worker, ffmpeg, 키·예산 | HLS 오디오 저장과 Voxtral 응답 확인 |
| 주제가 계속 잘게 생성됨 | 화자 전환, 발언 묶음, summary-worker | 원본을 보존한 채 worker와 프롬프트 버전 확인 |
| 종료 회의가 계속 정리중 | overview, summary/brief 로그 | AI 한도 확인 후 두 worker를 --once 실행 |
| 공식 회의록 미반영 | official worker, 매칭 상태 | 후보 유일성 확인 후 통합 worker 실행 |
| 주제 클릭 시 발언 없음 | brief/evidence와 evidence ID | 품질 게이트 로그 확인 후 브리프 재생성 |
| UI가 이전 모습 | assets/app.js, 캐시, 이미지 | API를 build·force-recreate하고 강력 새로고침 |

로그에는 API 키, Authorization 헤더 또는 .env 내용을 출력하지 마십시오. 장애 조사 시 키 존재 여부와 길이만 확인하고 값을 복사해 공유하지 않습니다.

## 보안과 백업

- .env와 실제 키는 Git에 커밋하지 않습니다.
- 운영에서는 루트 .env 전체를 컨테이너에 전달하지 말고 프로젝트에 필요한 허용 목록만 주입합니다.
- 제공된 보안 배포 스크립트를 사용할 수 있는 환경에서는 다음 명령으로 워커별 최소 비밀값만 전달합니다.

~~~bash
sudo scripts/deploy_secure_workers.sh all
~~~

- Mistral 키는 요약·국무회의 전사 워커에만, 국회 API 키는 공식 데이터 수집 워커에만 제공합니다.
- 서비스 포트 8070을 인터넷에 직접 공개하지 않습니다. 외부 사용자는 인증·권한 검사를 수행하는 부모 홈페이지나 리버스 프록시로 접속해야 합니다.
- 화자명 수정 API는 운영자 기능입니다. 부모 프록시의 관리자 세션을 거쳐야 하며 공개 클라이언트에 직접 노출하지 않습니다.
- 무료 플랜 키도 유출 위험은 같습니다. 이상 호출이나 공급자 경고가 있으면 키를 폐기하고 다시 발급합니다.
- 원본 파일에는 개인정보가 포함될 수 있으므로 서버와 백업 접근 권한을 제한합니다.

DB 볼륨과 data/raw, data/processed는 역할이 다릅니다. DB와 원본 파일을 함께 백업해야 완전한 복구가 가능합니다. 자동 백업이 별도로 구성되지 않은 환경에서는 운영 전 보존 주기, 암호화, 복구 훈련과 책임자를 정하십시오.

## 주요 API

전체 요청·응답 계약은 실행 중인 /docs에서 확인합니다.

| 구분 | 메서드와 경로 | 용도 |
|---|---|---|
| 시스템 | GET /api/health | 앱·DB 상태 |
| 시스템 | GET /api/meta | 서비스 메타데이터 |
| 시스템 | GET /api/ai/usage | 모델, 사용량, 한도, 갱신 시각 |
| 시스템 | GET /api/data-sources | 데이터 출처 |
| 일정 | GET /api/schedule/upcoming | 예정 회의 전광판 |
| 일정 | GET /api/schedule/today | 오늘 일정 |
| 회의 | GET /api/committees/meetings | 국회 회의·공식 자료 |
| 회의 | GET /api/executive/briefings | 국무회의·행정부 공식 자료 |
| 회의 | GET /api/committees/meetings/{conference_id}/transcript | 공식 국회 발언 |
| 정책 | GET /api/committees/policy-flow | 위원회 정책 흐름 |
| 정책 | GET /api/policy/cross-institution-flow | 행정부·국회 잠정 공통 신호 |
| 의안 | GET /api/bills | 회의 연결 의안과 표결 |
| 라이브 | GET /api/live/status | 현재 방송 상태 |
| 라이브 | GET /api/live/magazine | 상단 일정·결과 통합 목록 |
| 라이브 | GET /api/live/broadcasts | 방송 목록과 추가 로딩 |
| 라이브 | GET /api/live/overview | 방송 처리 단계와 진행률 |
| 자막 | GET /api/live/transcript/snapshot | 입장 시 저장 자막과 cursor |
| 자막 | GET /api/live/transcript/delta | cursor 이후 변경분 |
| 자막 | GET /api/live/transcript/recent | 최근 발언 |
| 자막 | GET /api/live/broadcasts/{broadcast_id}/transcript | 방송별 전체 발언 묶음 |
| 화자 | GET /api/live/broadcasts/{broadcast_id}/speakers | 화자 보정 조회 |
| 화자 | PUT /api/live/broadcasts/{broadcast_id}/speakers/{source_label} | 운영자 화자명 보정 |
| 화자 | DELETE /api/live/broadcasts/{broadcast_id}/speakers/{source_label} | 운영자 보정 철회 |
| 결과 | GET /api/live/broadcasts/{broadcast_id}/brief | 잠정/통합 회의 브리프 |
| 결과 | GET /api/live/broadcasts/{broadcast_id}/brief/official | 공식 반영 상태 |
| 결과 | GET /api/live/broadcasts/{broadcast_id}/brief/evidence | 선택한 주제·과제의 근거 |
| 결과 | GET /api/live/tasks | 방송에서 도출된 잠정 과제 |

GET /api/meetings/today는 이전 클라이언트 호환용 deprecated 경로입니다. 새 구현은 /api/schedule/today를 사용합니다.

## 개발과 테스트

~~~bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r backend/requirements-dev.txt
uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8070 --reload
~~~

~~~bash
python3 -m unittest discover -s backend/tests -v
ruff check backend
~~~

외부 API 호출은 기본 테스트 suite에 넣지 않습니다. fixture에는 출처, 조회일, 원본/합성 여부와 이용 조건을 기록하고 키와 개인정보를 포함하지 않습니다.

### 공식 LIVE source probe

~~~bash
python3 scripts/probe_live_sources.py
~~~

국회 대상 위원회의 공식 생중계 상태와 KTV 플레이어 계약을 확인하고 원본·manifest를 data/raw, 정규화 상태를 data/processed/live_status.json에 저장합니다.

## 디렉터리

~~~text
PoC/07-NationalAssembly/
├── project.json              # 홈페이지 PoC 등록 메타데이터
├── README.md                 # 사용자·운영자 통합 안내서
├── AGENTS.md                 # 구현과 데이터 권위 원칙
├── CHANGELOG.md              # 날짜별 변경 내역
├── .env.example              # 환경변수 예시
├── docker-compose.yml        # API·DB·수집/후처리 워커
├── backend/
│   ├── app/                  # FastAPI, 수집, 정규화, 요약
│   ├── migrations/           # PostgreSQL migration
│   └── tests/                # 단위·통합 테스트
├── web/                      # 반응형 사용자 화면
├── docs/                     # 설계·개발·운영 문서
├── prompts/                  # 버전 관리 AI 프롬프트
├── scripts/                  # 수집·배포·점검 명령
├── tests/fixtures/           # 검증된 최소 fixture
└── data/
    ├── raw/                  # 원본 응답·자막·오디오·manifest
    └── processed/            # 정규화·상태 산출물
~~~

동일 manifest와 본문은 해시로 중복 판정합니다. 원본이 바뀌면 이전 버전을 덮어쓰지 않고 새 버전과 provenance를 저장합니다.

## 알려진 제약

- 라이브 자막의 화자 번호는 신원 정보가 아니므로 공식 문서 전까지 인물명을 확정할 수 없습니다.
- 국무회의 라이브는 오디오 상태, 동시 발화, 고유명사와 방송 음량에 따라 전사 정확도가 달라집니다.
- 실시간 주제와 과제는 잠정 결과이며 종료 후 전체 분석에서 합쳐지거나 수정될 수 있습니다.
- 공식 회의록과 브리핑은 회의 종료 즉시 발표되지 않을 수 있습니다.
- 행정부와 국회의 공통 정책 신호는 동일 안건이나 직접 인과관계를 의미하지 않습니다.
- 공식 후보가 여러 개인 경우 자동 연결하지 않으므로 운영자 확인이 필요합니다.

## 운영 체크리스트

### 매일

- /api/health와 Compose 서비스 상태 확인
- 상단 일정과 실제 공식 일정의 누락 여부 확인
- 생방송 감지, 자막 증가, 최신 발언 자동 이동 확인
- AI 사용량과 다음 갱신 시각 확인
- 종료 회의가 기록 중 또는 정리중에 장시간 머무는지 확인

### 공식 자료 발표 후

- 동일 회의 카드가 공식정리로 전환됐는지 확인
- 주제별 과제와 담당 부처가 잘못 여러 주제에 묶이지 않았는지 확인
- 근거 발언이 공식 완성형 문장과 공식 화자를 반영했는지 확인
- 의미 없는 문체 변경이나 과도한 하이라이트가 없는지 확인
- 국무회의의 부처보고·심의안건·대변인 브리핑과 대통령 지시사항 확인

### 배포 후

- /, /assets/app.js, /api/health 응답 확인
- 모바일 폭과 데스크톱 sticky 근거 패널 확인
- 통합 홈페이지 프록시와 관리자 화자 수정 권한 확인
- 로그와 네트워크 응답에 비밀값이 노출되지 않았는지 확인

## 관련 문서

- [프로젝트 배경](docs/PROJECT_CONTEXT.md)
- [아키텍처](docs/ARCHITECTURE.md)
- [국무회의 × 국회 실행 플랜](docs/EXECUTION_PLAN.md)
- [데이터 모델](docs/DATA_MODEL.md)
- [데이터 출처와 신청 링크](docs/DATA_SOURCES.md)
- [개발 방법](docs/DEVELOPMENT.md)
- [상세 운영 방법](docs/OPERATIONS.md)
- [PoC 평가](docs/POC_EVALUATION.md)
- [설계 결정](docs/DECISIONS.md)
- [변경 내역](CHANGELOG.md)

새 기능은 별도 구동 경로를 복제하지 않고 **일정 → 방송 → 발언 묶음 → 브리프 → 공식 자료 통합** 공통 파이프라인을 재사용합니다. 업무 차이는 수집 어댑터, 분류 taxonomy, 공식 문서 파서와 화면 그룹 규칙에만 추가하는 것이 이 프로젝트의 운영 원칙입니다.
