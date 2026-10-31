# MinsLab PoC 안내

`PoC/`는 실제 사용자 흐름과 외부 데이터·인증·LLM 연동을 검증하는 실행형 개념증명 프로젝트 모음입니다. 각 하위 폴더의 `project.json`을 `portfolio_loader.py`가 자동 검색해 `menu_group`에 따라 PoC 또는 포트폴리오 메뉴를 만들고, `main.py`가 프로젝트별 UI 또는 빌드된 SPA를 기존 서비스 안에서 제공합니다.

## 프로젝트 목록

| 번호 | 폴더 | 주제 | 런타임 |
| --- | --- | --- | --- |
| 01 | [01-AISafeAgent](01-AISafeAgent/README.md) | GPS·기상청·공간 방재·AI 안전비서 | Python 모듈 + 루트 UI + NDJSON |
| 02 | [02-field-inspection-platform](02-field-inspection-platform/README.md) | 점검 업무·대상·결과·통계 | React/Vite 정적 SPA + Supabase |
| 04 | [04-master-press](04-master-press/README.md) | 뉴스 수집·복합 관련도·카카오 알림·CaseON 매거진 | Python 모듈 + 정적 UI + SQLite/Supabase |
| 06 | [AI Work Hub](06-AIWorks/README.md) | 승인 기반 AI 업무 작업공간·문서 자동화·MCP 제작/스토어 | 정적 SPA + Python/SQLite + JSON Schema |
| 07 | [07-NationalAssembly](07-NationalAssembly/README.md) | 국무회의·국회 회의·의안·표결의 공식 원문 기반 정책 흐름 | 독립 FastAPI + PostgreSQL + 루트 reverse proxy |
| 08 | [조달췤!](08-AICommonPlatformRadar/README.md) | 조달 AI 사업 수집·선별·검토 | 독립 FastAPI + SQLite |
| 10 | [HOME](10-home/README.md) | 정부 정책과 서울·경기 사업 후보 수집·검토·현황 조회 | 독립 FastAPI + PostgreSQL/PostGIS + 루트 reverse proxy |
| 11 | [췤미!](11-image-inspection/README.md) | 이미지 검사·OCR | 독립 API + SQLite |
| 12 | [책자리](12-epub-reader/README.md) | EPUB·PDF 읽기·로컬 서재·책갈피 | 정적 HTML/JS + 브라우저 IndexedDB |


현재 1·2·4·6·11번은 PoC, 7·8·10·12번은 포트폴리오입니다. 3·5·9번은 삭제했습니다. 4번은 코드·파이프라인·테이블 구조를 보존하고 데이터·백업만 초기화한 중지 상태입니다. 8번은 수집이 비활성화되어 있습니다.

포트폴리오로 전환할 때 폴더를 옮기거나 번호를 다시 부여하지 않습니다. `menu_group`만 `portfolio`로 변경하고 기존 `display_no`, `id`, URL을 유지합니다.

## 등록 방식

각 프로젝트는 다음 메타데이터를 가집니다.

```text
PoC/NN-project/
├── project.json        # 메뉴 순서, 제목, 기능, 엔트리 파일
├── README.md           # 동작 원리, 구조, 설정, 운영 문서
├── .env.example        # 프로젝트 전용 설정이 있으면 함께 보관
├── requirements.txt    # 프로젝트 전용 Python 의존성이 있으면 함께 보관
├── web/                # 프로젝트 전용 정적 화면
├── scripts/            # 배치·마이그레이션·유지보수 실행기
├── deploy/             # 프로젝트 전용 systemd 등 배포 정의
└── tests/              # 프로젝트 단위 회귀 테스트
```

PoC는 폴더 하나만으로 기능·설정·운영·테스트를 이해하고 재현할 수 있어야 합니다. 프로젝트 간
코드 중복은 허용하며, 한 PoC의 전용 실행기나 배포 파일을 저장소 루트에 두지 않습니다. 루트에는
`main.py`의 공통 HTTP 경계, `portfolio_loader.py`의 등록 탐색, 홈페이지·관리자·공통 관측처럼
둘 이상의 프로젝트가 실제로 공유하는 기능만 둡니다.

`project.json`의 핵심 필드는 다음과 같습니다.

| 필드 | 용도 |
| --- | --- |
| `id` | URL과 전용 렌더러를 연결하는 전역 고유 식별자 |
| `order` | 메뉴 정렬 순서 |
| `menu_group` | `poc` 또는 `portfolio` 메뉴 분류 |
| `display_no` | 화면의 두 자리 번호 |
| `title`, `summary`, `description` | 목록과 상세 화면 설명 |
| `features`, `usage`, `note` | 기능, 사용자 흐름, 주의사항 |
| `entry_file` | 코드 미리보기에 포함할 대표 소스 |

새 프로젝트는 메타데이터만으로 설명형 화면에 등록할 수 있습니다. 전용 상호작용이나 API가 필요하면 `main.py`에 렌더러와 ASGI 라우트를 연결합니다.

## 공통 제공 구조

```text
/poc?project={id}
  └─ 루트 포트폴리오 셸 안에서 프로젝트 렌더링

/poc/field-inspection-platform/*
  └─ PoC 02 dist/ 정적 SPA + history fallback

/poc/aiworks/*
  └─ PoC 06 정적 작업공간 + SQLite 기반 승인·문서·MCP API

/poc/national-assembly/*
  └─ PoC 07 독립 FastAPI 서비스(기본 localhost:18070) reverse proxy

/home
  └─ /poc/home/으로 이동

/poc/home/*
  └─ PoC 10 HOME 독립 FastAPI 서비스(기본 localhost:18100) reverse proxy

/api/poc/*
  └─ 서버 비밀값, 외부 API, 관리자 권한, LLM 호출 경계
```

PoC 02의 React 소스는 개발·빌드 시에만 Node를 사용합니다. 운영에서는 별도 Node 프로세스나 포트를 열지 않고 루트 ASGI가 `dist/` 파일을 제공합니다. PoC 07은 부모 저장소와 런타임을 공유하지 않는 독립 서비스이며, 루트 ASGI는 같은 출처의 `/poc/national-assembly/` 경로로만 프록시합니다.

## 공통 환경설정

공통 런타임 값은 저장소 루트 `.env`에 둡니다. 프로젝트 자체 로더가 있는 PoC는 해당 폴더의
`.env`를 우선 읽고 루트 `.env`를 fallback으로 사용할 수 있습니다. 변수 목록과 예시는
가장 가까운 프로젝트의 `.env.example`에 보관합니다.

| 영역 | 환경변수 |
| --- | --- |
| Supabase 공통 | `SUPABASE2_URL`, `SUPABASE2_PUBLISHABLE_KEY`, `SUPABASE2_SERVICE_ROLE_KEY` |
| Local LLM | `OLLAMA_BASE_URL` |
| Remote LLM | `HF_API_KEY`, `HF_BASE_URL`, `OPENROUTER_API_KEY`, `OPENROUTER_BASE_URL`, `UPSTAGE_API_KEY` |
| AI Safe Agent | `KMA_AUTH_KEY`, `SAFETYDATA_*_KEY`, `KAKAO_REST_API_KEY`, `VWORLD_API_KEY` |
| Field Inspection | `VITE_FIELD_INSPECTION_SUPABASE_URL`, `VITE_FIELD_INSPECTION_SUPABASE_PUBLISHABLE_KEY` |
| AI Work Hub (`aiworks` 호환 식별자) | `AIWORKS_STORE_SIGNING_SECRET`, `AIWORKS_APPROVAL_SECRET`, `AIWORKS_SOLAR_LIVE`, `AIWORKS_LOCAL_MCP_LIVE`, `AIWORKS_RHWP_*` |
| 국회 PoC 프록시 | `NATIONAL_ASSEMBLY_UPSTREAM` |

Vite의 `VITE_*` 값과 Supabase publishable key는 브라우저 공개값입니다. service-role과 LLM API key는 어떤 경우에도 브라우저 번들에 넣지 않습니다.

## 빌드와 배포

Python PoC 검증:

```bash
python3 -m py_compile \
  PoC/01-AISafeAgent/RiskInspection_v1.py \
  PoC/01-AISafeAgent/import.py \
  PoC/06-AIWorks/backend.py
python3 -m unittest discover -s PoC/06-AIWorks/tests -v
python3 -m unittest discover -s PoC/07-NationalAssembly/backend/tests -v
```

React PoC 검증:

```bash
cd PoC/02-field-inspection-platform
npm ci
npm run build

```

통합 반영:

```bash
cd /home/ubuntu/apps/myservice
# 운영은 연결을 마친 뒤 검증된 인스턴스로 전환하고 공개 경로를 확인합니다.
curl -fsS http://127.0.0.1:8000/health
```

## 데이터와 보안 원칙

- PoC 01의 CSV·PKL은 재생성 가능한 산출물이므로 Git에 넣지 않습니다.
- PoC 02는 익명 CRUD가 열린 공개 실험 스키마입니다. 운영 데이터와 연결하지 않습니다.
- PoC 06은 외부 전송과 문서 변경을 기본 거부하며 서명된 승인, 버전 충돌 검사와 감사 로그를 거칩니다.
- PoC 07은 공식 자료와 자동 분류를 분리하고, raw 원본·버전·source span을 보존하며, 검증되지 않은 API 필드나 관계를 공식 사실로 표시하지 않습니다.
- AI 출력은 공식 재난 판단, 행정 결재 또는 확정 보고서를 대체하지 않습니다.
- 프로젝트 구현을 변경할 때 `project.json`, 하위 `README.md`, 루트 `.env.example`의 설정 이름을 함께 확인합니다.

## 11 · 췤미! — 체크 이미지

`11-image-inspection/`은 이미지 홍보물을 원문 25개 항목과 156개 세부 행동으로 검수하는 독립 서비스입니다. 홈페이지 PoC 11에서 선택하거나 `/imgscan`으로 접속합니다. 그림 읽기(GPT-5.4/Sol/Astra/Nemotron)와 분석(GPT-5.4/mini/Solar/Sol/Astra) 모델을 구분하며, PoC7 중앙 사용량·동일 OpenAI 크레딧 원장을 공유합니다. 실행·환경변수·공유 방법은 [전용 README](11-image-inspection/README.md)를 참고하세요. 실제 키와 업로드는 공유하지 않습니다.
