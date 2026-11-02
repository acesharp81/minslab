# HOME 독립 재구성·재사용

이 문서의 기준 디렉터리는 이 저장소의 최상위입니다. MinsLab 전체 저장소나 공용 Docker network가 없어도 실행할 수 있습니다. Python 3.12, Docker Engine과 Compose plugin, 인터넷에서 설치하는 의존성이 필요합니다. 프런트엔드 테스트에는 Node.js가 필요합니다.

## 새 환경에서 시작

```bash
git clone https://gitlab.aigov.go.kr/acesharp/HOME.git
cd HOME
python3 scripts/init_standalone.py
docker compose --env-file .env.standalone -f compose.standalone.yml up --build -d
curl --fail http://127.0.0.1:18110/health
```

`init_standalone.py`는 무작위 DB 비밀번호 등 로컬 설정을 권한 600의 `.env.standalone`에 만들며 기존 파일을 덮어쓰지 않습니다. 파일은 Git에서 제외됩니다. DB는 전용 volume에서 시작하고 migration은 API 시작 시 적용됩니다. 기존 운영용 `docker-compose.yml`의 공용 network와 배포 컨테이너는 사용하지 않습니다.

초기 DB에는 운영에서 누적한 기록이 없습니다. 필요한 공개 원천을 수집해 내용을 채웁니다. API 키와 서비스 승인은 각 설치 환경에서 발급·설정하며 `.env.example`에 항목과 출처 안내가 있습니다. 실제 키·운영 DB·세션은 공개 저장소에 포함하지 않습니다. 운영 당시의 누적 상태까지 복원할 때는 별도로 제공받은 DB 및 원문 저장소 백업이 필요합니다.

기본 구성은 API·DB만 시작하며 자동 수집·외부 모델 호출·메시지 발송을 시작하지 않습니다. 수집과 모델·알림 기능은 각 설정·예산·원천 승인을 준비한 뒤 [README](README.md)의 해당 worker 절차를 이 독립 환경에 맞춰 적용합니다.

```bash
# 상태와 로그
docker compose --env-file .env.standalone -f compose.standalone.yml ps
docker compose --env-file .env.standalone -f compose.standalone.yml logs --tail 50 api
# DB와 원문 volume을 보존한 중지
docker compose --env-file .env.standalone -f compose.standalone.yml down
```

## 포함 자료와 공개 범위

소스, 웹 자산, 설정 예시, dependency manifest, migration, 공개 참조 데이터, 오프라인 fixture, 설계·API·수집 문서를 포함합니다. 대용량 검증 덤프·화면 캡처인 `docs/evidence/`만 게시 이력에서 제외하며 원본은 [GitHub의 해당 프로젝트](https://github.com/acesharp81/minslab/tree/main/PoC/10-home/docs/evidence)에 보관합니다. 과거 검증 문서의 이 경로 링크는 GitHub에서 확인합니다. 실행과 테스트에 필요한 원문 fixture는 `tests/fixtures/` 또는 `backend/tests/fixtures/`에 포함합니다.

## 기능을 다른 방식으로 사용

웹 화면과 API, 수집기, 정규화·파서, DB 저장 계층을 각각 재사용할 수 있습니다. 디렉터리 구조·주요 API·출처 등록·필드의 의미는 [README](README.md)를 기준으로 확인합니다. 실제 외부 API 없이 파서와 변환 규칙을 실행하는 fixture 기반 테스트부터 실행하면 기존 의미를 확인할 수 있습니다.

```bash
python -m pytest tests -q
node --test tests/js/*.test.cjs
```

테스트 의존성은 개발환경 안내에 따라 설치합니다. 수집 원문의 출처·기준일·권위 상태와 AI 파생 결과 구분을 유지합니다. 제3자 웹 라이브러리의 라이선스 파일은 자산 디렉터리에 포함돼 있습니다.

화면은 `http://127.0.0.1:18110/poc/home/`에서 열립니다. 공개 조회·수집 모듈은 부모 로그인 서버 없이 실행됩니다. 관리 API는 기존과 같이 `POC10_INTERNAL_SECRET`의 HMAC 검증을 유지합니다. 별도 인증 프록시/클라이언트를 연동할 때 `backend/app.py`의 `authenticated()` 계약(타임스탬프·HTTP 메서드·요청 경로, 60초 허용)을 사용합니다. 기존 MinsLab 로그인 UI는 이 저장소의 구성 요소가 아닙니다.

공개 원천을 선택해 수집하는 예시는 다음과 같습니다. 실제 네트워크 요청이므로 원천별 키와 수집 범위를 먼저 확인합니다.

```bash
docker compose --env-file .env.standalone -f compose.standalone.yml exec api python -m scripts.collect --help
```

## 2026-11-02 공유 준비 보완

외부 XML은 defusedxml로 읽고 요청 내 캐시는 타입과 객체 격리를 유지하는 복사 방식으로 변경했습니다. 초기 설치 migration의 동적 SQL 식별자는 Alembic의 식별자 처리로 구성하며 기존 schema·index 의미를 유지합니다. 비밀 탐지는 기본 규칙을 유지하고 검토한 정확한 체크섬·변수명·공개 식별자 줄만 `.gitleaks.toml`로 기록합니다. 빈 키 예시의 여러 줄 오탐은 빈 문자열을 명시해 해결합니다.

PDF·웹 요청 처리를 위한 의존성은 2026-11-02 공개 보안 정보를 확인해 pypdf 6.21.4, FastAPI 0.162.0, Starlette 1.10.0으로 고정했습니다. 이미지의 설치 도구도 pip 26.2.2로 고정합니다. [pypdf 보안 공지](https://github.com/py-pdf/pypdf/security/advisories), [Starlette 보안 공지](https://github.com/Kludex/starlette/security/advisories). 이 보완이 GitLab 502의 직접 원인 해결이라는 뜻은 아니며 실제 게시 결과로 별도 검증합니다.

AI 기능은 기본 실행에 포함되지 않습니다. 자신의 OpenAI·Solar 키와 로컬 사용량 한도로 독립 운영하려면 관련 provider 설정과 `POC10_SHARED_BUDGET_REQUIRED=false`를 명시적으로 선택합니다. 기존 공유 예산을 유지할 때는 `USAGE_GATEWAY_URL`·`USAGE_METER_TOKEN`을 연결하며, 게이트웨이 소스는 별도 공유된 [국정ON 저장소의 backend/app/openrouter_gateway.py](https://gitlab.aigov.go.kr/acesharp/kjon/-/blob/main/backend/app/openrouter_gateway.py)에 있습니다. 기존 MinsLab 운영 키를 복제하지 않습니다.

### HTTP 처리·실행 사용자 보완

검증용 스크립트의 HTTP 요청도 requests로 통일하고 HTTP 오류 응답을 원천 데이터로 저장하지 않도록 확인합니다. 키가 포함된 공식 통계 요청의 예외에는 키·요청 URL을 출력하지 않습니다. requests와 보안 민감 간접 의존성(anyio, certifi, idna, h11, urllib3, charset-normalizer)의 검증 버전을 명시합니다. [AnyIO](https://pypi.org/project/anyio/), [Certifi](https://pypi.org/project/certifi/), [Requests](https://pypi.org/project/requests/)의 공식 배포와 OSV 공개 정보를 확인했습니다.

API·worker 이미지는 UID/GID `1000:1000`으로 실행합니다. 독립 Compose의 새 runtime volume은 이미지의 `/app/data` 소유권을 이어받습니다. 기존 운영 데이터나 다른 bind mount를 재사용할 때는 모든 하위 디렉터리·파일에 이 UID의 읽기·쓰기 권한이 있는지 먼저 확인해야 합니다. 기존 root 소유 데이터는 worker를 중지한 유지보수 절차에서 소유권을 이관한 뒤 새 이미지를 배포합니다.

브라우저에서 유효하지만 일부 검사기가 optional chaining과 혼동하던 `조건?.6:값` 등의 조건식은 `조건 ? 0.6 : 값` 형태로 표기했습니다. 계산 의미는 같습니다.
