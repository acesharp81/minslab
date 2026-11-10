# 실행·재현 안내

## 현재 배포

**https://www.minslab.kr/handover/**에서 접속 코드로 로그인할 수 있습니다. 프로젝트 전용 `poc13-handover` 컨테이너와 `poc13-handover-data` 볼륨을 사용합니다. 사용자 승인 후 공용 Nginx의 `/handover/` 경로만 연결했습니다. 적용·백업·HTTPS 검증 기록은 [DEPLOYMENT.md](DEPLOYMENT.md)에 있습니다.

## 실행 방법 A: Python

저장소의 `PoC/13-handover`에서 Python 3.12 가상환경을 만들고 `requirements.lock`을 설치한 뒤 `bash scripts/run.sh`를 실행합니다. Node·GPU·AIWorks 서버는 필요하지 않습니다. `http://127.0.0.1:18130/`을 열고 샘플로 시작합니다.

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.lock
bash scripts/run.sh
```

서버를 종료할 때는 실행한 터미널에서 Ctrl+C를 누릅니다. `data/`는 보존됩니다. 완료된 문서 단계가 있는 작업은 재시작 시 중단 상태로 보이며 화면의 다시 시도로 이어 갈 수 있습니다. 모델 키를 화면에서 입력했다면 메모리 설정이므로 재시작 후 다시 연결합니다.

## 실행 방법 B: Docker

Docker Compose 설치 환경:

```bash
docker compose up -d --build
docker compose ps
docker compose logs --tail=100
```

이 작업 환경에는 Compose 플러그인이 없어 아래 Docker CLI 경로로 동일한 앱 이미지의 기동·시험을 수행합니다. 최초 기동 스크립트는 같은 이름의 컨테이너가 있으면 중단합니다. 배포 교체 시에는 이 프로젝트 컨테이너만 백업·중지하고 전용 볼륨을 유지합니다.

```bash
docker build -t poc13-handover:0.4.0 .
bash scripts/docker-run.sh
docker inspect --format '{{.State.Health.Status}}' poc13-handover
docker logs --tail=100 poc13-handover
```

Docker 권한이 없는 계정이면 위 `docker` 명령에 `sudo`를 붙이고 실행 스크립트는 `sudo bash scripts/docker-run.sh`로 실행합니다. 스크립트는 같은 이름의 컨테이너가 이미 있으면 중단하며 기존 서비스를 임의로 교체하지 않습니다.

기동 포트는 `127.0.0.1:18130`으로 제한됩니다. 비루트 사용자, 읽기 전용 루트 파일시스템, 자체 영구 볼륨, 메모리 1.5GB·CPU 2개 제한을 적용합니다. `poc13-handover-data` 볼륨이 원문·DB를 보관합니다. 이미지·컨테이너만 새로 만들어도 이 볼륨을 유지하면 자료가 남습니다.

```bash
docker stop poc13-handover
docker start poc13-handover
```

다른 PoC 이름이나 볼륨을 이 명령에 넣지 않습니다. `docker system prune`, 전체 컨테이너 종료, 전체 볼륨 정리 명령은 필요하지 않습니다.

## 접속 코드와 AI 키

프로젝트 전용 `.env`를 사용합니다. 실제 값은 저장소·문서·화면 캡처에 넣지 않습니다.

- `HANDOVER_ACCESS_TOKEN`: 공유 시연 접속 코드. 비어 있으면 인증 화면이 없습니다. 원격 공개 연결에는 설정합니다.
- `HANDOVER_LLM_URL`: 서버 운영자가 지정하는 모델의 API 기본 URL.
- `HANDOVER_LLM_MODEL`: 기본 `solar-pro4`.
- `HANDOVER_LLM_KEY`: 프로젝트 전용 키. 비어 있으면 로컬 규칙 모드로 시작합니다.
- `HANDOVER_DATA_DIR`: 로컬 데이터 경로. Docker 실행 스크립트에서는 `/app/data`로 고정합니다.

화면의 AI 모델 연결은 Upstage 공식 엔드포인트와 지정 모델만 허용합니다. 다른 호환 제공자를 사용하려면 운영자가 전용 `.env`에서 설정하고 그 제공자의 계약을 검증해야 합니다. 기존 운영 서비스의 `.env` 전체를 복사하거나 심볼릭 링크로 연결하지 않습니다. 현재 배포는 사용자의 모델 연결 요청에 따라 기존 Upstage 자격 증명 중 유효한 값만 독립 `.env`에 저장했으며 재시작 후에도 연결을 유지합니다. 기존 설정은 변경하지 않았고 실행 중 의존하지 않습니다. 계정 사용 한도·과금은 공유될 수 있습니다.

## 원격 서버를 자신의 브라우저에서 보기

VS Code의 포트 전달 기능으로 18130을 전달하거나 아래 터널을 사용합니다.

```bash
ssh -L 18130:127.0.0.1:18130 사용자@서버주소
# SSH가 10022 포트를 쓰는 경우
ssh -p 10022 -L 18130:127.0.0.1:18130 사용자@서버주소
```

자신의 브라우저에서 `http://127.0.0.1:18130/`을 엽니다. 원격 서버의 루프백 주소를 단순히 링크로 열어서는 자신의 컴퓨터에서 접근할 수 없습니다.

웹 주소를 연결할 때는 `nginx-handover.conf.example`의 정확한 경로 프록시를 검토 후 HTTPS 가상 호스트에 추가합니다. 기존 앱의 `/` 경로는 유지합니다. 공유 라우팅 변경은 원래 계획서의 운영자산 변경 금지 조건에 대한 별도 확인을 받은 후 적용합니다. 임시 독립 Nginx의 `/handover/` 경로에서는 브라우저 전체 흐름을 검증했습니다.

## 검증

실제 모델 확대 평가는 `.venv/bin/python scripts/live_evaluate.py`로 실행합니다. 자체 생성한 합성 문서 12개만 전송하며 API 사용량이 발생합니다. 결과는 `test-results/solar4-v040/`에 저장됩니다.

```bash
bash scripts/verify.sh
# 브라우저를 최초 설치하는 개발 환경에서만:
.venv/bin/playwright install chromium
# 독립 합성 데이터 워크스페이스에만 실행: 샘플 사건을 새로 생성합니다.
HANDOVER_TEST_URL=http://127.0.0.1:18130/ .venv/bin/python scripts/browser_smoke.py
```

접속 코드를 설정했다면 브라우저 시험의 `HANDOVER_TEST_TOKEN` 환경변수를 사용합니다. 쉘 이력에 코드를 직접 쓰지 않도록 별도 환경 파일이나 비밀 입력 방식을 사용하세요. 현재 연결된 배포에서 브라우저 시험을 하면 합성 샘플만 Solar API로 전송하며 API 사용량이 발생합니다. 인증 키는 서버에서 제공자에게만 사용합니다. `HANDOVER_REQUIRE_LLM=1`로 실행하면 AI 사용 기록 표시도 검사합니다.

```bash
docker run --rm --network none --read-only \
  --tmpfs /tmp:mode=1777 --tmpfs /app/data:uid=10001,gid=10001 \
  --cap-drop ALL --security-opt no-new-privileges \
  poc13-handover:0.4.0 python -m pytest tests -q -p no:cacheprovider
```

시험은 임시 디렉터리에 DB를 만들며 `app.main`을 import하는 것만으로 운영 데이터나 작업 상태를 변경하지 않습니다. 모델 계약 시험의 HTTP 서버도 로컬 루프백에서만 동작합니다.

## 장애 대응

| 증상 | 조치 |
|---|---|
| 파일 추출 실패 | 자료 탭 경고 확인. 암호화·스캔·손상을 확인하고 텍스트 기반 판본 추가 |
| 부분 추출 | 빠진 도형·각주·이미지 등을 원본에서 확인하고 추가 자료 또는 전임자 입력으로 보완 |
| 업무가 0개 | 로컬 모드의 라벨 지원 범위 확인. AI 연결 후 재생성하거나 업무 직접 추가 |
| 모델 연결 실패 | 프로젝트 전용 키·현재 모델 이름·사용량·네트워크 확인. 오류는 정상 초안으로 저장하지 않음 |
| 작업 실패/서버 재시작 | 화면 다시 시도. 완료 문서 단계는 캐시에서 재사용 |
| 판본 충돌 409 | 다른 수정·자료 추가 여부 확인 후 새로 고침. 최신 판본에서 재검토 |
| 새 자료 이후 확정 불가 | 원문 목록이 변경됨. 새 초안을 생성하고 검토 |
| 컨테이너 unhealthy | 해당 컨테이너 로그와 전용 볼륨 권한·포트 확인 |

## 백업

로컬 실행은 앱 종료 후 `data/` 전체를 복사합니다. Docker 실행은 `poc13-handover`만 중지하고 `docker cp poc13-handover:/app/data ./handover-backup`으로 복사한 뒤 같은 컨테이너를 다시 시작합니다. SQLite 파일만 실행 중에 복사하면 WAL과 시점이 맞지 않을 수 있습니다. 원문 파일도 반드시 함께 보관합니다.

## 후임자 조회

확정 후 **보고서에 질문**에서 질문을 입력합니다. AI 조회는 질문·확정 필드·관련 원문 전송 동의가 필요하며, 키워드 조회는 외부 전송 없이 사용할 수 있습니다. 응답 중 확정본이 바뀌면 오래된 답을 폐기하고 다시 조회하도록 안내합니다. 질문 이력은 현재 브라우저 세션의 해당 확정본에 대해 최근 10개만 표시하고 질문 원문은 DB에 보관하지 않습니다. 사용량·판본·조회 방식만 감사 기록에 남깁니다.

**일정·연락망**은 현재 한국 날짜 기준으로 일정을 구분합니다. 보고서 자체의 확정일 기준 분류와 목적이 다릅니다. 정기 업무의 다음 날짜를 추정하거나 미기재 연락처를 생성하지 않습니다. **여러 파일 선택**과 **폴더 선택**은 100개·총 80MB 이내를 한 요청으로 검사·등록합니다. 한 파일의 검사가 실패하면 그 요청의 자료를 모두 등록하지 않습니다.

Compose와 Docker CLI는 이제 같은 명시적 볼륨 `poc13-handover-data`를 사용합니다. 이미 다른 방식으로 앱이 실행 중이라면 포트 충돌이 나므로 두 실행 방식을 동시에 기동하지 않습니다.

## v1.5 직원·그림 후처리 운영

- 직원은 시연 페르소나이며 실제 사용자 인증이 아니다. 기존 건은 직원 1→2의 이전 자료로 조회하고 보고서 표시명·확정 포인터를 변경하지 않는다.
- 그림 후처리는 초안 생성의 별도 동의 옵션이다. 본문 최신본 선택이 먼저이며 최신본이 모호하거나 본문 없는 스캔이면 전송하지 않는다.
- `HANDOVER_VISION_KEY`, `HANDOVER_VISION_URL`, `HANDOVER_USAGE_GATEWAY_URL`, `HANDOVER_USAGE_METER_TOKEN`을 이 프로젝트 환경파일에만 설정한다. 다른 PoC 환경파일을 런타임에 읽지 않는다.
- 운영 Docker 실행 스크립트는 `minslab-ai-budget` 네트워크가 있을 때 이 앱만 참여시켜 `poc07-openrouter-gateway:8071`에 접근한다. Python 직접 실행은 접근 가능한 중앙 예산 주소를 설정한다. Compose 사용 시 운영자가 같은 외부 네트워크를 연결하거나 접근 가능한 주소를 제공한다.
- 호출 전 예산 예약 실패 시 GPT를 호출하지 않는다. 호출 이후 통신 중단은 자동 재호출하지 않으며 `vision_calls`의 정산 기록을 보존한다. 미전송 정산은 다음 그림 요청에서 재전송한다. 불확실한 호출을 수동 삭제해 다시 과금하지 않는다.
- 그림 캐시는 모델·지침·이미지 해시로 재사용한다. `vision_meta` 설치 식별자와 `vision_calls`를 원본 DB와 함께 백업한다.
- 전체 자료를 다시 생성하면 최신본과 그림을 다시 평가한다. 이미 전달한 확정본은 재확정 전까지 유지된다.
- `POST /api/employee-demo`는 합성 순환함 6개를 최초 한 번만 생성하며 기존 시연함을 덮어쓰지 않는다.


## 2026-11-10 Solar 공용 한도
`HANDOVER_SOLAR_SHARED_POOL=key2`이면 운영 Solar 키를 PoC10의 `UPSTAGE_SECRET_KEY2`와 공유한다. 공용 예산 서버 주소·토큰은 기존 `HANDOVER_USAGE_GATEWAY_URL`, `HANDOVER_USAGE_METER_TOKEN`을 사용한다. 호출 전 원자적 예약이 성공해야 모델을 호출한다. 일반 응답과 스트리밍 모두 사용량을 정산하며 정산 실패는 `solar_shared_calls`에 보존하고 다음 호출을 차단한다. 상단 잔액은 PoC10·13 사용액과 진행 중 예약·미확정액을 함께 차감한 $100 내부 추정 잔액이다.
기존 같은 키의 비용 이력은 서비스 중지 후 `SharedSolar.import_history(config)`로 한 번 가져온다. 재실행은 중복 차감하지 않는다. 과거 미확인 요청은 지원하는 요청 상한(입력 200만·출력 10만 토큰)을 보수적으로 미확정액으로 잡으며, 제공사 원장 확인 전 실제 사용액으로 확정하지 않는다. 다른 키를 UI에 연결하면 이 공유 계정을 쓰지 않는다.
