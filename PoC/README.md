# MinsLab PoC 안내

`PoC/`는 실제 사용자 흐름과 외부 데이터·인증·LLM 연동을 검증하는 실행형 개념증명 프로젝트 모음입니다. 각 하위 폴더의 `project.json`을 `portfolio_loader.py`가 자동 검색해 PoC 메뉴를 만들고, `main.py`가 프로젝트별 UI 또는 빌드된 SPA를 기존 서비스 안에서 제공합니다.

## 프로젝트 목록

| 번호 | 폴더 | 주제 | 런타임 |
| --- | --- | --- | --- |
| 01 | [01-AISafeAgent](01-AISafeAgent/README.md) | GPS·기상청·공간 방재·AI 안전비서 | Python 모듈 + 루트 UI + NDJSON |
| 02 | [02-field-inspection-platform](02-field-inspection-platform/README.md) | 점검 업무·대상·결과·통계 | React/Vite 정적 SPA + Supabase |
| 03 | [03-mois-kms](03-mois-kms/README.md) | 조직·업무·결재·AI 보고서 | React/Vite SPA + Python API + Supabase Auth |
| 04 | [04-master-press](04-master-press/README.md) | 뉴스 수집·복합 관련도·카카오 알림·CaseON 매거진 | Python 모듈 + 정적 UI + SQLite/Supabase |
| 05 | [05-north-korea-night-lights](05-north-korea-night-lights/README.md) | 북한 VIIRS 월별 야간조명 3D 격자 지도 | Earth Engine Python API + pydeck 단일 HTML |
| 06 | [06-AIWorks](06-AIWorks/README.md) | 승인 기반 AI 업무 작업공간·문서 자동화·MCP 제작/스토어 | 정적 SPA + JSON Schema 샌드박스 |

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
| `order` | PoC 메뉴 정렬 순서 |
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

/poc/mois-kms/*
  └─ PoC 03 dist/ 정적 SPA + history fallback

/poc/north-korea-night-lights/map
  └─ PoC 05 공통 deck.gl 플레이어 + 월별 gzip 데이터 API

/poc/aiworks/*
  └─ PoC 06 정적 작업공간 + SQLite 기반 승인·문서·MCP API

/api/poc/*
  └─ 서버 비밀값, 외부 API, 관리자 권한, LLM 호출 경계
```

PoC 02와 03의 React 소스는 개발·빌드 시에만 Node를 사용합니다. 운영에서는 별도 Node 프로세스나 포트를 열지 않고 루트 ASGI가 `dist/` 파일을 제공합니다.

## 공통 환경설정

공통 런타임 값은 저장소 루트 `.env`에 둡니다. 프로젝트 자체 로더가 있는 PoC는 해당 폴더의
`.env`를 우선 읽고 루트 `.env`를 fallback으로 사용할 수 있습니다. 변수 목록과 예시는
가장 가까운 프로젝트의 `.env.example`에 보관합니다.

| 영역 | 환경변수 |
| --- | --- |
| Supabase 공통 | `SUPABASE2_URL`, `SUPABASE2_PUBLISHABLE_KEY`, `SUPABASE2_SERVICE_ROLE_KEY` |
| Local LLM | `OLLAMA_BASE_URL` |
| Remote LLM | `HF_API_KEY`, `HF_BASE_URL`, `OPENROUTER_API_KEY`, `OPENROUTER_BASE_URL` |
| AI Safe Agent | `KMA_AUTH_KEY`, `SAFETYDATA_*_KEY`, `KAKAO_REST_API_KEY`, `VWORLD_API_KEY` |
| Field Inspection | `VITE_FIELD_INSPECTION_SUPABASE_URL`, `VITE_FIELD_INSPECTION_SUPABASE_PUBLISHABLE_KEY` |
| MoIS KMS | `MOIS_KMS_HF_MODELS`, `MOIS_KMS_OPENROUTER_MODELS`, `MOIS_KMS_DEFAULT_MODEL` |
| 북한 야간조명 | `GEE_PROJECT` |
| AIWorks | `AIWORKS_STORE_SIGNING_SECRET`, `AIWORKS_APPROVAL_SECRET`, `AIWORKS_OPENROUTER_LIVE`, `AIWORKS_RHWP_*` |

Vite의 `VITE_*` 값과 Supabase publishable key는 브라우저 공개값입니다. service-role과 LLM API key는 어떤 경우에도 브라우저 번들에 넣지 않습니다.

## 빌드와 배포

Python PoC 검증:

```bash
python3 -m py_compile \
  PoC/01-AISafeAgent/RiskInspection_v1.py \
  PoC/01-AISafeAgent/import.py \
  PoC/05-north-korea-night-lights/generate_map.py \
  PoC/05-north-korea-night-lights/collect_all.py \
  PoC/06-AIWorks/backend.py
python3 -m unittest discover -s PoC/06-AIWorks/tests -v
```

React PoC 검증:

```bash
cd PoC/02-field-inspection-platform
npm ci
npm run build

cd ../03-mois-kms
npm ci
npm run build
```

통합 반영:

```bash
cd /home/ubuntu/apps/myservice
sudo systemctl restart myservice
curl -fsS http://127.0.0.1:8000/health
```

## 데이터와 보안 원칙

- PoC 01의 CSV·PKL은 재생성 가능한 산출물이므로 Git에 넣지 않습니다.
- PoC 02는 익명 CRUD가 열린 공개 실험 스키마입니다. 운영 데이터와 연결하지 않습니다.
- PoC 03은 Supabase Auth, 승인 상태와 RLS를 적용하고 service-role 작업만 Python API로 격리합니다.
- PoC 05의 Earth Engine OAuth 자격증명과 생성된 월별 데이터는 저장소에 커밋하지 않습니다.
- PoC 06은 외부 전송과 문서 변경을 기본 거부하며 서명된 승인, 버전 충돌 검사와 감사 로그를 거칩니다.
- AI 출력은 공식 재난 판단, 행정 결재 또는 확정 보고서를 대체하지 않습니다.
- 프로젝트 구현을 변경할 때 `project.json`, 하위 `README.md`, 루트 `.env.example`의 설정 이름을 함께 확인합니다.
