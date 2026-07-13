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
