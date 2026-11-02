# kjon 독립 재구성·재사용

이 문서의 기준 디렉터리는 이 저장소의 최상위입니다. MinsLab 전체 저장소나 공용 Docker network가 없어도 실행할 수 있습니다. Python 3.12, Docker Engine과 Compose plugin, 인터넷에서 설치하는 의존성이 필요합니다. 프런트엔드 테스트에는 Node.js가 필요합니다.

## 새 환경에서 시작

```bash
git clone https://gitlab.aigov.go.kr/acesharp/kjon.git
cd kjon
python3 scripts/init_standalone.py
docker compose --env-file .env.standalone -f compose.standalone.yml up --build -d
curl --fail http://127.0.0.1:18070/api/health
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

소스, 웹 자산, 설정 예시, dependency manifest, migration, 공개 참조 데이터, 오프라인 fixture, 설계·API·수집 문서를 포함합니다. 대용량 검증 덤프·화면 캡처인 `docs/evidence/`만 게시 이력에서 제외하며 원본은 [GitHub의 해당 프로젝트](https://github.com/acesharp81/minslab/tree/main/PoC/07-NationalAssembly/docs/evidence)에 보관합니다. 과거 검증 문서의 이 경로 링크는 GitHub에서 확인합니다. 실행과 테스트에 필요한 원문 fixture는 `tests/fixtures/` 또는 `backend/tests/fixtures/`에 포함합니다.

## 기능을 다른 방식으로 사용

웹 화면과 API, 수집기, 정규화·파서, DB 저장 계층을 각각 재사용할 수 있습니다. 디렉터리 구조·주요 API·출처 등록·필드의 의미는 [README](README.md)를 기준으로 확인합니다. 실제 외부 API 없이 파서와 변환 규칙을 실행하는 fixture 기반 테스트부터 실행하면 기존 의미를 확인할 수 있습니다.

```bash
cd backend
python -m pytest tests -q
```

테스트 의존성은 개발환경 안내에 따라 설치합니다. 수집 원문의 출처·기준일·권위 상태와 AI 파생 결과 구분을 유지합니다. 제3자 웹 라이브러리의 라이선스 파일은 자산 디렉터리에 포함돼 있습니다.

화면은 `http://127.0.0.1:18070/`에서 열립니다. `backend/requirements-dev.txt`로 개발 의존성을 설치합니다. API schema는 실행 중인 `/docs`에서 확인하고, 원천 계약은 `docs/DATA_SOURCES.md`와 adapter fixture를 확인합니다. DB migration은 `backend/migrations/`에 순서대로 포함돼 있습니다.
