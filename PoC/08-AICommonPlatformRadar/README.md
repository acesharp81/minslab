# PoC 08 · 조달체크 | 범정부 AI 공통기반 edition

> 나라장터 AI 사업, 자동으로 찾고 공통기반 활용까지 체크.

나라장터 사전규격과 용역 본공고의 공개자료를 수집하고, 첨부 원문에 근거해 범정부 AI 공통기반 활용 상태를 **6개 업무 분류로 선별**하는 독립 실행형 FastAPI PoC입니다. 이 분류는 위반 여부를 확정하는 행정판단이 아닙니다.

## 현재 구현 범위

- 사전규격·본공고 목록 및 e발주 첨부정보 OpenAPI 어댑터, 페이지네이션·재시도·중복 upsert
- 허용 도메인·HTTPS·확장자·크기 제한을 적용한 다운로드와 SHA-256 중복 저장 방지
- 제안요청서·과업지시서·사업설명서·요구사항 문서 등 사업 내용 문서만 선별
- 같은 제목의 TXT/DOCX/HWPX/PDF/ZIP/HWP가 함께 있으면 현재 파서 품질이 가장 높은 한 형식만 파싱
- PDF, DOCX, TXT, HWPX, ZIP 본문 추출 및 격리된 `hwp-cli` 기반 바이너리 HWP 추출
- ZIP path traversal와 실행파일 차단, 파일 단위 실패 격리 및 재처리
- YAML 규칙 필터, OpenAI-compatible 분석기, 키 없이 동작하는 결정론적 mock 분석기
- 근거 인용 원문 일치 검증, 1~6 분류 태그, 확인 질문·사전규격 보완 안내문, 조치상태와 감사로그
- `수집 → AI 사업 검출 → 적용 가능/검토 필요 → 조치중 → 조치완료`를 보여주는 대시보드와 우선 조치 10건
- 2·3·4유형 판정오류 신고, 부적합 수동 정정, 감사로그 및 설정 화면의 누적 신고 이력
- Chrome 확장프로그램을 통한 나라장터 사전규격 검색·상세 이동·의견 자동입력과 조치중 자동 전환
- 조치완료(이용·미이용·부적합) 시 등록 주소록으로 사업·의견·회신 내용을 보내는 SMTP 알림
- 누적 분석·AI 검출·공통기반 판정·조치·기관 반응·사전규격→본공고 전환을 한눈에 보는 성과 통계 화면
- 03:10 수집, 04:40 조건부 재시도, 07:00 최종 보고서의 systemd 타이머와 프로세스 간 중복 실행 잠금
- 기존 Supabase 2 Data API 운영 저장소, PoC08 전용 SQLite 장애 캐시와 시작 시 재동기화

## 3분 실행

Docker만 있으면 이 폴더 밖의 파일이나 상위 저장소가 필요하지 않습니다.

```bash
cp .env.example .env
docker compose up --build -d
curl http://localhost:18080/health
```

`http://localhost:18080`을 열면 mock 공고 5건이 자동 적재됩니다. 종료는 `docker compose down`입니다. 데이터는 이 폴더의 `data/`에 남습니다.

기본 포트 바인딩은 `127.0.0.1:18080`이며, 독립 서버에서 외부에 직접 공개해야 할 때만 `HOST_BIND=0.0.0.0`으로 변경합니다. MinsLab 홈페이지에서는 `/poc/ai-common-platform-radar/`로 프록시되며, 서비스는 전달된 접두사를 인식해 메뉴·정적 자원·API 경로를 프레임 안에 유지합니다. 이 통합 설정이 없어도 폴더 단독 Docker Compose 실행은 그대로 동작합니다.

Linux 계정 UID/GID가 1000이 아니면 `.env`의 `LOCAL_UID`, `LOCAL_GID`를 `id -u`, `id -g` 결과로 바꾸십시오. 이는 bind mount의 SQLite·리포트 쓰기 권한을 맞추기 위한 값입니다.

로컬 Python 실행:

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python scripts/seed_sample.py
python scripts/preflight.py
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

모든 경로는 `app/config.py`의 실제 프로젝트 위치를 기준으로 해석하므로 다른 이름·위치로 폴더를 복사해도 동작합니다. 테스트 데이터 위치를 분리하려면 `DATA_DIR=/tmp/radar-data`처럼 지정할 수 있습니다.

## 실데이터 전환 준비

1. 공공데이터포털에서 아래 두 서비스의 활용신청을 완료하고 **Decoding(원본) 서비스키**를 준비합니다.
   - 조달청_나라장터 사전규격정보서비스
   - 조달청_나라장터 입찰공고정보서비스
2. `.env`에서 다음 값을 변경합니다.

```env
G2B_MODE=live
G2B_SERVICE_KEY=발급받은_원본_키
AUTO_SEED_SAMPLE=false
```

현재 공공데이터포털 Swagger에서 확인한 기본값은 다음과 같습니다.

- 사전규격: `https://apis.data.go.kr/1230000/ao/HrcspSsstndrdInfoService/getPublicPrcureThngInfoServc`
- 용역 본공고: `https://apis.data.go.kr/1230000/ad/BidPublicInfoService/getBidPblancListInfoServc`
- e발주 첨부: `getBidPblancListInfoEorderAtchFileInfo`

공공 API 명세나 게이트웨이 경로 변경에 대비해 base URL과 operation은 모두 환경변수입니다. 개발계정 기본 트래픽은 일 1,000건이므로 목록을 먼저 받고, e발주 첨부 API는 규칙상 검토할 공고에만 호출합니다. 운영 전에는 실제 키로 `--lookback-days 1 --no-analyze` 스모크 테스트를 수행하고 `pipeline_runs`의 수신 건수와 원천 JSON 필드 매핑을 확인하십시오.

```bash
python scripts/run_collector.py --lookback-days 3
python scripts/reparse_failed.py
python scripts/run_daily_report.py --date 2026-09-11
python scripts/apply_attachment_policy.py
```

### 일일 무인 운영

운영 기본 시간대는 `Asia/Seoul`입니다. 03:10에 수집·파싱·2/3차 분석을 실행하고, 실패 항목이 있거나 1차 배치가 완료되지 않았을 때만 04:40에 다시 실행합니다. 07:00 보고서는 그날의 성공한 수집 배치가 있어야 최종본으로 생성되며, 배치가 없거나 실패 중이면 조용히 빈 보고서를 발행하지 않고 service를 실패 처리합니다.

```bash
# 판단만 확인하며 외부 API는 호출하지 않음
python scripts/run_operational_batch.py --phase primary --dry-run
python scripts/run_operational_batch.py --phase retry --dry-run

# 완료 배치가 있는 날짜의 최종 보고서 생성
python scripts/run_daily_report.py --finalize --require-successful-batch

# Docker 컨테이너 이름을 기본값으로 사용하는 Linux systemd 설치
sudo bash deploy/install_systemd.sh
systemctl list-timers 'poc08-*'
```

수동 API, CLI, systemd가 동시에 수집을 요청해도 `DATA_DIR/poc08-collection.lock`이 한 실행만 허용합니다. 재시도 여부와 최근 실행 결과는 대시보드 및 `/health`의 `latest_batch`에서 확인할 수 있습니다. 독립 배포에서도 컨테이너 이름은 `poc08-ai-common-platform-radar`로 고정됩니다.

화면의 `지금 수집·판정`은 HTTP 요청을 오래 붙잡지 않고 백그라운드 작업을 접수합니다. 버튼에는 10건 단위 처리 진도와 판정 완료 수가 표시되고, `/api/collect/status`에서도 규칙 후보·판정·보류·실패 수를 확인할 수 있습니다.

대시보드의 `지금 처리해야 할 항목`은 담당자 확인, 분석 재시도, AI 명시 미분석, 3차 심층 대기, 표본·수동 검토, 문서 재처리를 중복 제외 합계와 개별 큐로 보여줍니다. `문서 오류 재처리` 버튼은 저장된 실패 문서를 백그라운드에서 다시 파싱하고 완료 통계를 표시합니다.

## LLM 분석

기본 provider 값은 `mock`이어서 키 없이도 판정 스키마와 사용자 흐름을 검증합니다. 운영 구성은 PoC 4 자동 워커와 겹치지 않는 Upstage Solar Pro4를 2차 주 공급자로 사용하고, Mistral Small은 주 공급자 장애 때만 호출하는 비상 fallback으로 둡니다. 3차 심층분석은 GPT-5.4 mini를 주 공급자로, NVIDIA Nemotron 3 Super를 fallback으로 사용합니다. 모든 결과는 로컬 Pydantic 스키마와 원문 인용 검증을 통과해야 저장됩니다.

```env
STAGE2_PROVIDER=upstage
STAGE2_MODEL=solar-pro4
UPSTAGE_API_KEY=...

STAGE2_FALLBACK_PROVIDER=mistral
STAGE2_FALLBACK_MODEL=mistral-small-latest
MISTRAL_API_KEY=...

STAGE3_PRIMARY_PROVIDER=openai
STAGE3_PRIMARY_MODEL=gpt-5.4-mini
OPENAI_API_KEY=...

STAGE3_FALLBACK_PROVIDER=nvidia
STAGE3_FALLBACK_MODEL=nvidia/nemotron-3-super-120b-a12b
NVIDIA_API_KEY=...
```

2차 입력은 기본 8,000자, 3차 입력은 100,000자로 분리합니다. 2차 주 공급자의 호출 한도·응답 오류가 발생하면 Mistral fallback으로 같은 검증을 수행하며, 두 공급자가 모두 실패한 건만 다음 배치로 보류합니다. 서버로 보내는 내용은 수집한 공개 메타데이터와 공개 첨부 추출문으로 제한됩니다. 프롬프트는 `app/prompts/`, 스키마는 `app/schemas.py`에 있습니다. 확정한 기본조건·사용 상태·전환 가능성은 의미가 맞는 원문 직접 인용이 필수이며, 단순 `AI 기반` 문구만으로 LLM/RAG 적합성이나 국가사무를 추정하지 않습니다.

키 발급 위치와 입력 방법은 [docs/API_KEYS.md](docs/API_KEYS.md)에 정리했습니다.

키 입력 후 아래 명령은 각 LLM에 작은 공개 샘플을 한 번씩 보내 연결·모델 접근·JSON 스키마를 점검합니다. 키 값은 출력하지 않습니다.

```bash
python scripts/preflight.py
python scripts/probe_llm.py --target all
```

## Supabase Data API

운영 원본은 기존 서비스와 같은 Supabase REST Data API에 저장합니다. 필요한 값은 이미 보유한 `SUPABASE2_URL`과 `SUPABASE2_SERVICE_ROLE_KEY` 두 개뿐이며 DB 비밀번호나 Pooler URI는 필요하지 않습니다. 키는 서버에서만 사용하고 브라우저에는 노출하지 않습니다.

```env
SUPABASE2_URL=https://PROJECT_REF.supabase.co
SUPABASE2_SERVICE_ROLE_KEY=...
DATABASE_URL=sqlite:///./data/supabase-cache.db
```

최초 한 번 [Supabase 마이그레이션](supabase/migrations/20260911000000_poc08_radar.sql)을 Dashboard의 SQL Editor에서 실행합니다. 모든 테이블은 `poc08_` 접두사와 RLS를 사용하며 anon/authenticated 접근은 허용하지 않습니다. 앱은 커밋 후 변경을 REST로 반영하고, 일시 장애 때는 PoC08 전용 SQLite 캐시에 보존한 뒤 다음 시작 시 원격과 재조정합니다.

## 주요 화면과 API

| 경로 | 기능 |
| --- | --- |
| `/` | 누적 업무 흐름, 미종결 우선 조치 10건, 공통기반 이용 확인 공고 |
| `/notices` | 기간·단계·기관·6개 분류·조치·분석·마감·문서상태·키워드 필터 |
| `/notices/{id}` | 분류 태그, 3대 조건·사용·전환 근거, 2·3·4번 안내문, 첨부 본문, 조치 관리 |
| `/reports/daily` | 누적 분석·AI 검출·공통기반 판정·조치·기관 반응·사전규격→본공고 전환 성과 통계 |
| `/settings` | 관리자 로그인 후 의견 자동입력 담당자·등록 비밀번호·문구 템플릿, Gmail SMTP·주소록, 판정오류 이력 관리 |
| `/extension/install` | Chrome 의견 도우미 ZIP 다운로드와 최초 1회 설치 안내 |
| `/api/statistics` | 성과 통계 원자료(JSON). 전환은 의견·연락 이후 `bfSpecRgstNo`로 직접 연결된 후속 본공고만 인정 |
| `GET/PUT /api/settings/opinion-sender` | 향후 원클릭 입력 기능에서도 재사용할 의견 발신자 설정 조회·저장 |
| `/health` | DB·수집모드·LLM·설정·스케줄·최근 배치 상태 |
| `POST /api/collect/run` | 수집·다운로드·파싱·분석 실행 |
| `POST /api/maintenance/reparse` | 실패한 저장 문서 일괄 재파싱 |
| `GET /api/maintenance/reparse/status` | 재파싱 작업 상태와 통계 |
| `POST /api/reports/daily/generate` | 선택 날짜 보고서를 현재 데이터로 강제 재생성 |
| `POST /api/notices/{id}/parse` | 해당 공고 첨부 재파싱 |
| `POST /api/notices/{id}/analyze/simple` | 간소화 검증 |
| `POST /api/notices/{id}/analyze/deep` | 심층 검증 |
| `PATCH /api/actions/{id}` | 조치상태·담당자·메모 변경 |
| `POST /api/actions/{id}/opinion-submitted` | 의견 등록 성공을 조치중 상태로 반영하고 최초 1회 주소록 알림 발송 |
| `POST /api/notices/{id}/classification-error` | 2·3·4유형 판정오류 사유를 기록하고 부적합으로 정정 |

FastAPI 자동 명세는 `/docs`에서 볼 수 있습니다.

## 환경변수

전체 목록과 안전한 기본값은 `.env.example`에 있습니다. 핵심 항목은 다음과 같습니다.

| 항목 | 설명 |
| --- | --- |
| `SUPABASE2_URL`, `SUPABASE2_SERVICE_ROLE_KEY` | 운영 Data API 주소와 서버 전용 키 |
| `DATABASE_URL`, `DATA_DIR` | 장애 복구용 로컬 캐시 및 원문·추출문·리포트 위치 |
| `G2B_MODE`, `G2B_SERVICE_KEY` | mock/live 선택 및 공공데이터포털 키 |
| `G2B_PAGE_SIZE`, `G2B_MAX_PAGES` | 호출량과 한 실행의 최대 수집 범위 |
| `STAGE2_*`, `STAGE3_*` | 단계별 provider·모델·한도·동시성 |
| `GEMINI_API_KEY`, `OPENAI_API_KEY`, `NVIDIA_API_KEY` | 서버 전용 LLM 인증정보 |
| `MAX_FILE_SIZE_MB`, `DOWNLOAD_ALLOWED_HOSTS` | 다운로드 보안 경계 |
| `ADMIN_USERNAME/PASSWORD`, `ADMIN_TOKEN` | HTTP Basic 또는 Bearer 인증 |

`APP_ENV=production`에서는 인증정보가 없으면 `/health`가 `degraded`를 반환합니다. 외부 공개 배포는 리버스 프록시 TLS와 기관 인증체계를 추가해야 합니다.

## 6개 업무 분류

3차 심층검증은 AI 기능 유무와 별도로 아래 기본조건을 모두 구조화해 원문 근거와 함께 확인합니다.

1. **망·데이터**: 행정망·업무망·내부망 또는 연계 가능한 혼합망인지, 외부망에서 완결되는 서비스인지 확인
2. **모델·기능**: 공통기반 제공 LLM·RAG로 처리 가능한지, 독자 모델·풀파인튜닝 등 별도 협의가 필요한지 확인
3. **국가사무**: 중앙·지방정부 행정사무 또는 명시적으로 위탁받은 국가사무인지, 공공기관 자체 내부업무인지 확인

검사 범위는 정보화 서비스를 구축·개발·고도화하는 사업과 그 구축을 준비하는 BPR·ISP·ISMP·연구용역입니다. 정보시스템 감리, 지표 발굴·개발, 연수·교육·훈련 운영, 단순 운영·유지관리 등 구축이 주된 산출물이 아닌 용역은 AI 문구가 있어도 5유형 `비대상·미사용`으로 규칙 확정하며 외부 LLM을 호출하지 않습니다.

중앙부처·지방정부 또는 소속기관이 발주한 내용은 발주기관 메타데이터를 근거로 국가사무로 분류합니다. 비정부 공공기관은 주관기관이 발주기관 자신이면 내부업무, NIA·KLID 등 법정 수탁 가능 기관을 포함해 주무·수탁·출연·관련·협조기관에서 중앙부처·지방정부가 확인되면 위탁 국가사무, 그 밖에 정부 관계가 없으면 비국가사무로 분류합니다. 관계가 모순되거나 법정 수탁 가능 기관의 해당 사업 위탁관계가 확인되지 않으면 담당자 확인 대상으로 유지합니다. 별도 폐쇄망은 행정망·업무망 연계 여부를, 독자모델·풀파인튜닝은 공개 파운데이션 모델·RAG 대체 가능 범위를 확인합니다. 결과에는 `criteria_version=common-platform-v7-service-construction-scope`가 기록됩니다.

2·3·4유형 의견 문안은 사람이 직접 작성한 것처럼 `검토 취지 → 현재 확인된 상태 → 변경·확인 시 활용 가능한 조건 → 회신 요청 → 법적 근거` 순서의 자연스러운 문장으로 제공합니다. 법적 근거는 「인공지능·데이터 기반 행정 활성화에 관한 법률」(약칭: 인공지능데이터행정법) 제27조제2항입니다. 나라장터의 `/link/*/single/` 주소는 내부 화면 상태 없이 직접 열면 조회 오류가 발생하므로, 확장프로그램이 정상 메뉴 순서로 사전규격을 검색해 의견등록 화면까지 이동합니다.

사전규격 의견을 나라장터에 저장하면 확장프로그램이 조치 상태를 `조치중`으로 바꿉니다. 새벽 배치가 나라장터 공개 의견 API에서 답글을 확인하며, 공고 상세의 `답변 여부 새로 확인`으로 즉시 갱신할 수도 있습니다. 회신 확인 후 사용자가 `조치완료 · 이용/미이용/부적합`을 선택하면 설정한 주소록으로 결과가 발송됩니다. 본공고 상세에서는 `담당자 연락처 보기` 버튼으로 나라장터가 공개한 담당자 이름과 전화번호를 확인할 수 있습니다.

| 분류 | 태그 | 의미 | 기본 조치 |
| --- | --- | --- | --- |
| 1 | 적합·사용 | AI 사업, 3대 조건 충족, 공통기반 사용 명시 | 현황 관리 |
| 2 | 적합·미반영 | 3대 조건 충족, 공통기반 미사용·미명시 | 사전규격 보완 안내 |
| 3 | 전환·확인검토 | 명시적 제외 근거 없이 국가사무·망·모델이 미확인되었거나 폐쇄망 연계·모델 대체 검토 필요 | 담당자 확인 및 사전규격 보완 안내 |
| 4 | 사용명시·조건확인 | 사용 명시, 기본조건 불일치 또는 미확인 | 조건 정합성 확인 및 사전규격 보완 안내 |
| 5 | 비대상·미사용 | 구축 범위 밖의 감리·지표·연수·운영·비구축 연구 또는 비국가사무·기관 내부업무·외부망 완결 AI 사업 | 제외 사유 기록 |
| 6 | 비AI 사업 | 직접적인 AI 구축·개선 근거 없음 | 자동 분류, 조치 없음 |

2·3·4번에는 본공고 전에 반영할 수 있는 안내문을 자동 생성하고 확장프로그램으로 나라장터 입력란에 채웁니다. 최종 저장은 오등록을 막기 위해 사용자가 직접 확인합니다. “활용 문구 미확인”, “미사용 명시”, “활용 여부 검토”는 서로 다른 사용 상태로 보존합니다. 자료에 없는 보안등급·망 구성·실제 구축방식은 추정하지 않습니다. 규칙상 명확한 비AI 사업은 LLM 호출 없이 6번으로 저장해 미분석 적체를 줄입니다.

## 테스트

```bash
pytest -q
```

파일명, 사업문서 allowlist, 동일 제목 형식 우선순위, 단일 파싱, 구축·BPR/ISP·구축연구 포함과 감리·지표·연수·운영 제외, 중복 upsert, SHA 중복 저장 방지, JSON 스키마와 원문 근거, 1~6 강제 분류, 사용·미사용·단순검토 구분, 사전규격 안내문, 이전 기준 최우선 재검증, 비AI 로컬 분류, ZIP traversal, 인코딩, HWP CLI 연계, 공고 단위 실패 격리, 배치 잠금, 누적 성과, 설정 로그인, 의견 등록 상태 전환과 최초 1회 이메일, 판정오류 이력 및 확장프로그램 ZIP 제공을 검증합니다.

## 백업

API 키와 `.env`를 제외하고 SQLite 장애 캐시, 공개 원문, 추출문, 생성 보고서를 하나의 검증 가능한 압축파일로 보관합니다. 수집 중에는 같은 프로세스 간 잠금을 사용하며 SQLite는 온라인 backup API로 일관된 스냅샷을 만듭니다.

```bash
python scripts/backup_data.py
# 로그까지 필요할 때
python scripts/backup_data.py --include-logs --output-dir ./backups
(cd backups && sha256sum -c poc08-backup-*.tar.gz.sha256)
```

복구할 때는 서비스를 중지하고 압축을 별도 임시 디렉터리에 푼 뒤 `manifest.json`의 SHA-256을 검증합니다. `database/cache.db`와 `data/`를 새 설치의 대응 경로로 옮기고 서비스를 시작하면 Supabase 운영 원본과 다시 조정됩니다. 백업에는 인증정보가 없으므로 새 설치의 `.env`는 별도로 준비해야 합니다.

## 운영과 데이터 보안

- `data/raw`, `data/parsed`, `data/reports`, DB와 로그는 Git에서 제외됩니다.
- 수동 업로드 기능은 없으며 공개 나라장터 URL만 다운로드합니다.
- 다운로드는 HTTPS와 허용 도메인만 사용하고 redirect, 비표준 포트, 실행·스크립트 확장자를 거부합니다.
- 공고문·내역서·계약서·사유서·서식 등은 LLM 입력에서 제외하며, 파일명이 다운로드 응답에서만 확인되는 경우에도 저장·파싱 전에 동일 정책을 다시 적용합니다.
- 수집/필터/분석/조치 변경은 `pipeline_runs`, `analysis_runs`, `audit_logs`에 기록합니다.
- Docker 빌드는 `hwp-cli` v0.17.0 Linux 바이너리의 SHA-256을 검증해 이미지에 포함합니다. 각 HWP는 별도 프로세스에서 30초·출력 10MB 한도로 처리하며, 확장자가 HWPX여도 OLE 시그니처이면 HWP CLI로 자동 전환합니다.
- 운영 원본은 Supabase의 `poc08_` 테이블이며 `data/supabase-cache.db`는 서비스별 장애 캐시입니다. `scripts/backup_data.py`가 캐시와 원문·추출문·보고서를 함께 보관합니다.

보완된 구축계획과 운영 전 게이트는 [docs/PLAN_REVIEW.md](docs/PLAN_REVIEW.md)에 정리했습니다.
