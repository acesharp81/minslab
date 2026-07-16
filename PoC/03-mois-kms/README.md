# 03. 통합 업무관리시스템

Lovable로 만든 `acesharp81/moiskms`를 MinsLab 홈페이지에 통합한 조직형 업무관리 PoC입니다. 별도 Supabase 프로젝트를 만들지 않고 기존 MinsLab Supabase에 KMS 테이블을 추가합니다.

## 서비스 경로

- 홈페이지 내장 화면: `https://www.minslab.kr/poc?project=mois-kms`
- 전체 화면: `https://www.minslab.kr/poc/mois-kms/`
- 별도 Node 서버 또는 전용 포트: 없음
- 기존 Python ASGI가 `dist/`와 `/api/poc/mois-kms/*`를 함께 제공

## 주요 기능

- Supabase Auth 기반 로그인과 가입 신청
- 부서·팀·직급별 프로필 및 관리자 역할
- 월별 캘린더와 업무 등록·수정·삭제
- 팀원 → 팀장 → 과장 결재 흐름
- 관리자 사용자 승인, 조직·팀·업무 분류·템플릿 관리
- 단일 업무, 부서 월간, 부서 주간 AI 보고서
- Local LLM, Hugging Face, OpenRouter 모델 선택
- Temperature, 최대 출력 토큰, 시스템 프롬프트 설정

## 디자인 시스템

MinsLab 홈페이지와 PoC 02에 맞춰 아이보리 배경, 잉크색 본문, 라임 포인트와 보라색 보조색을 사용합니다. 반투명 glass 효과를 제거하고 카드, 표, 캘린더, 모달의 경계와 정보 위계를 명확하게 구성했습니다.

## 공용 환경변수

프로젝트별 `.env`를 만들지 않고 루트 공용 `.env`를 사용합니다.

```dotenv
# 기존 MinsLab Supabase
SUPABASE2_URL=https://YOUR_MINSLAB_PROJECT.supabase.co
SUPABASE2_PUBLISHABLE_KEY=YOUR_MINSLAB_PUBLISHABLE_KEY
SUPABASE2_SERVICE_ROLE_KEY=YOUR_MINSLAB_SERVICE_ROLE_KEY

OLLAMA_BASE_URL=http://127.0.0.1:11434
HF_BASE_URL=https://router.huggingface.co/v1
HF_API_KEY=YOUR_HUGGING_FACE_TOKEN
OPENROUTER_API_KEY=YOUR_OPENROUTER_KEY
```

- `SUPABASE2_PUBLISHABLE_KEY`는 브라우저에서 사용하는 공개 키입니다.
- `SUPABASE2_SERVICE_ROLE_KEY`는 가입과 Auth 사용자 삭제에만 사용하며 Python 서버 밖으로 보내지 않습니다.
- 프런트엔드는 `/api/poc/mois-kms/public-config`에서 URL과 publishable key를 런타임에 받으므로 키 변경 시 다시 빌드할 필요가 없습니다.

## MinsLab Supabase에 테이블 추가

Supabase Dashboard에서 기존 MinsLab 프로젝트를 선택한 뒤 SQL Editor에서 다음 파일 전체를 실행합니다.

```text
supabase/migrations/20260710000000_minslab_kms.sql
```

이 마이그레이션은 기존 `documents`, `documents_test`, `chucnkig_test*` 테이블을 수정하지 않습니다.

추가되는 KMS 테이블:

- `profiles`, `user_roles`
- `divisions`, `teams`
- `task_categories`, `templates`
- `tasks`

함께 추가되는 항목:

- 사용자·업무 열거형
- 조직·직급별 RLS 정책
- updated_at 트리거
- tasks, profiles Realtime publication
- 기획과·운영과·정책과, 1~3팀, 기본 업무 분류

## 최초 관리자

마이그레이션과 공용 환경변수 설정 후 서버 터미널에서 한 번만 실행합니다.

```bash
cd /home/ubuntu/apps/myservice/PoC/03-mois-kms
python3 bootstrap_admin.py
```

비밀번호는 화면에 표시되지 않으며 코드나 `.env`에 저장되지 않습니다. 이미 관리자가 있으면 중복 초기화를 거부합니다.

## LLM 제공자

- Local LLM: Ollama `/api/tags`에서 설치된 채팅 모델을 자동 조회
- Hugging Face: `MOIS_KMS_HF_MODELS`, 기본 `Qwen/Qwen2.5-72B-Instruct`
- OpenRouter: `MOIS_KMS_OPENROUTER_MODELS`, 기본 `openai/gpt-4o-mini`, `google/gemini-2.5-flash`
- 기본 모델: `MOIS_KMS_DEFAULT_MODEL`로 선택 가능

모든 LLM 요청은 로그인 access token과 승인 상태를 서버에서 재검증합니다.

## 빌드

```bash
cd /home/ubuntu/apps/myservice/PoC/03-mois-kms
npm install
npm run build
```

빌드는 루트 `.env`를 읽지 않습니다. 운영 서버는 `dist/`만 읽으므로 `npm run dev`, `vite preview` 또는 별도 Node 프로세스를 실행하지 않습니다.

## 보안 경계

- 브라우저 데이터 접근은 로그인 JWT와 Supabase RLS 사용
- 가입·Auth 사용자 삭제는 기존 MinsLab service-role을 사용하는 Python API에서만 처리
- LLM 키와 service-role은 브라우저 응답에 포함하지 않음
- 보고서 API는 승인된 사용자 상태를 매 요청마다 확인
- 모델 이름은 서버가 제공한 허용 목록으로 제한
- 익명 역할에는 KMS 테이블 권한을 부여하지 않음

AI 보고서는 검토용 초안이며 사실관계와 기관 양식을 담당자가 확인해야 합니다.


## 사용자와 업무 상태 모델

### 사용자 상태

`가입신청 → 승인 → 탈퇴` 상태를 사용합니다. 가입 API는 Auth 사용자를 service-role로 만들고 `profiles` 행을 생성합니다. 로그인 화면은 login ID를 서버에서 합성 이메일로 해석한 뒤 Supabase Auth에 로그인하며, profile이 `승인`이 아니면 업무 화면 진입을 막습니다.

직급은 `과장/팀장/팀원/서무`입니다. 전역 관리자는 별도 `user_roles.role=admin`으로 관리하므로 직급과 관리자 권한을 혼동하지 않습니다.

### 업무 결재 단계

```text
팀원저장 → 팀원등록
              ↓
          팀장검토
          ├─ 팀장반려
          ├─ 팀장저장
          └─ 팀장등록
                 ↓
             과장승인
             └─ 과장반려
```

업무 방식은 `온라인/오프라인` 열거형입니다. task에는 작성자, 분류, 제목, 목적, 내용, 방식, 장소, 일시, 참석자와 현재 결재 단계를 저장합니다.

## 테이블과 RLS

| 테이블 | 핵심 역할 |
| --- | --- |
| `divisions` | 과 단위 조직 |
| `teams` | division 하위 팀 |
| `task_categories` | 회의·출장·보고·보고 템플릿 분류 |
| `templates` | category별 보고서 양식 |
| `profiles` | Auth 사용자와 로그인 ID·조직·직급·승인 상태 |
| `user_roles` | admin 역할 |
| `tasks` | 월간 업무와 결재 단계 |

RLS 핵심 규칙:

- 조직·팀·분류·템플릿은 인증 사용자가 읽고 admin만 변경합니다.
- profile은 인증 사용자가 읽고 본인 또는 admin이 수정합니다.
- role은 본인 또는 admin이 읽고 admin만 변경합니다.
- task는 같은 division 또는 admin이 읽습니다.
- task 생성은 `author_id=auth.uid()`인 본인 행만 가능합니다.
- 수정은 작성자, 같은 team의 팀장, 같은 division의 과장·서무, admin에게 허용됩니다.
- 삭제는 작성자 또는 admin만 가능합니다.
- 익명 역할에는 KMS 테이블 권한을 부여하지 않습니다.

`tasks`, `profiles`는 Supabase Realtime publication에 추가됩니다. `updated_at`은 DB trigger가 갱신합니다.

## Python API 경계

모든 경로의 prefix는 `/api/poc/mois-kms`입니다.

| Method | 경로 | 인증 | 기능 |
| --- | --- | --- | --- |
| GET | `/public-config` | 없음 | Supabase URL·publishable key |
| GET | `/models` | 없음 | 허용 LLM 목록과 provider 상태 |
| GET | `/auth/signup-meta` | 없음 | 가입용 조직·팀 데이터 |
| POST | `/auth/check-login-id` | 없음 | 로그인 ID 중복 확인 |
| POST | `/auth/resolve-login` | 없음 | ID를 Auth 이메일과 상태로 해석 |
| POST | `/auth/signup` | 없음 | Auth 사용자와 가입신청 profile 생성 |
| POST | `/admin/delete-user` | admin JWT | profile/Auth 사용자 삭제 |
| POST | `/report` | 승인 사용자 JWT | 선택 provider 보고서 생성 |

service-role은 가입과 관리자 Auth 삭제 경계에서만 사용합니다. 일반 업무 CRUD는 브라우저 JWT와 RLS를 사용합니다.

## 보고서 생성 흐름

프런트엔드는 보고서 종류에 따라 Supabase에서 task, 작성자, 분류, 템플릿과 기간 업무를 읽어 시스템·사용자 프롬프트를 구성합니다.

- 업무 보고서: 단일 task + 작성자 + 해당 분류 template
- 월간 보고서: 선택 월의 division 업무 + `월간보고템플릿`
- 주간 보고서: 선택 주의 division 업무 + `주간보고템플릿`

서버는 매 요청마다 access token으로 Supabase Auth 사용자를 조회하고 profile 상태가 `승인`인지 확인합니다. 모델은 서버가 광고한 목록만 허용합니다.

| 옵션 | 기본값 | 범위 |
| --- | --- | --- |
| temperature | 0.2 | 0.0~1.5 |
| max_tokens | 1200 | 128~4096 |
| system prompt | 화면 기본값 | 1~8000자 |
| user prompt | 보고서별 구성 | 1~60000자 |
| Ollama num_ctx | 8192 | 서버 고정 |
| Ollama keep_alive | 5m | 서버 고정 |

모델 설정은 브라우저 `minslab.moisKms.reportAISettings.v1` localStorage에 저장됩니다. 비밀키는 저장하지 않습니다.

## 공급자와 실패 조건

- Ollama: `/api/tags`에서 embedding 모델을 제외한 설치 모델을 찾습니다.
- Hugging Face: `MOIS_KMS_HF_MODELS` 목록과 `HF_API_KEY` 존재 여부를 결합합니다.
- OpenRouter: `MOIS_KMS_OPENROUTER_MODELS`와 `OPENROUTER_API_KEY`를 사용합니다.
- `MOIS_KMS_DEFAULT_MODEL`이 허용 목록에 있으면 기본 선택합니다.

선택 provider 키가 없거나 모델이 허용 목록에 없으면 호출 전에 거부합니다. 원격 응답에서 `content`가 비면 `reasoning_content`를 확인하고 둘 다 없으면 오류로 처리합니다.

## 프런트엔드 구조

```text
src/
├── routes/                   # login, dashboard, admin, task/weekly/monthly report
├── components/dashboard/    # calendar, task list/detail/form, profile
├── components/report/       # model settings, result viewer
├── lib/
│   ├── api.ts               # host Python API + Bearer token
│   ├── auth.functions.ts
│   ├── profile.functions.ts
│   ├── tasks.functions.ts
│   ├── admin.functions.ts
│   └── report.functions.ts
└── integrations/supabase/   # browser client and generated types
```

TanStack Router history 경로는 ASGI가 `dist/index.html`로 fallback합니다. 운영 반영은 반드시 `npm run build`로 `dist/`를 갱신한 뒤 Python 서비스를 재시작합니다.
