# API 키·외부 서비스 준비

PoC 08은 기본 `mock` 모드에서 키 없이 실행된다. 실제 데이터/LLM 연결 시 아래 값만 `.env`에 넣는다. 키 값은 Git, 이슈, 채팅, 로그에 남기지 않는다.

기본 위치는 이 폴더의 `.env`다. 상위 저장소의 기존 `.env`를 Docker에서 그대로 주입하려면 아래처럼 명시한다. 폴더를 다른 곳에 공유하면 다시 로컬 `.env`만으로 실행되므로 상위 경로 의존은 생기지 않는다.

```bash
RADAR_ENV_FILE=../../.env docker compose up --build -d
```

로컬 Python 실행도 같은 변수를 명시하면 상위 파일을 읽는다. 경로를 지정하지 않으면 프로젝트 `.env`만 읽으며 상위 `.env`를 자동 탐색하지 않는다.

```bash
RADAR_ENV_FILE=../../.env python scripts/preflight.py
```

## 지금 새로 준비할 항목

### 1. 공공데이터포털 서비스 키

1. [사전규격정보서비스](https://www.data.go.kr/data/15129437/openapi.do)와 [입찰공고정보서비스](https://www.data.go.kr/data/15129394/openapi.do)에서 각각 `활용신청`을 누른다.
2. 개발계정 자동승인 후 `마이페이지 > 데이터 활용 > Open API > 활용신청 현황`을 연다.
3. 일반 인증키의 **Decoding(원본) 키**를 복사한다.
4. 프로젝트 `.env`에 다음처럼 저장한다.

```env
G2B_MODE=live
G2B_SERVICE_KEY=원본_서비스키
AUTO_SEED_SAMPLE=false
```

동일한 공공데이터포털 서비스키를 승인된 두 API 호출에 사용한다. 포털 화면에서 두 서비스 모두 승인 상태인지 확인한다.

### 2. Supabase Data API

새로 발급받을 값은 없다. 기존 세 서비스가 사용하는 2번 프로젝트의 아래 두 값을 그대로 사용한다.

```env
SUPABASE2_URL=https://PROJECT_REF.supabase.co
SUPABASE2_SERVICE_ROLE_KEY=...
```

PoC08은 Pooler나 PostgreSQL에 직접 연결하지 않는다. 따라서 DB 비밀번호, `SUPABASE2_DATABASE_URL`, publishable key도 필요하지 않다. `service_role` 키는 서버 전용이므로 프런트엔드 코드·응답·로그에 넣지 않는다.

최초 한 번만 다음 작업이 필요하다.

1. Supabase Dashboard에서 2번 프로젝트의 `SQL Editor`를 연다.
2. [20260911000000_poc08_radar.sql](../supabase/migrations/20260911000000_poc08_radar.sql)의 전체 내용을 실행한다.
3. `python scripts/preflight.py`에서 `supabase_rest: ok`를 확인한다.

마이그레이션은 기존 테이블을 건드리지 않고 `poc08_` 접두사의 테이블 7개만 만든다. RLS가 활성화되며 anon/authenticated 정책은 만들지 않는다. 공식 Data API 안내: <https://supabase.com/docs/guides/api>

## 현재 운영 LLM 키

### Cohere

[Cohere Dashboard API Keys](https://dashboard.cohere.com/api-keys)에서 평가 키를 발급한다. 현재 구성은 2차에 Command A+, 3차에 Command A를 사용하며 공식 V2 Chat API로 호출한다.

```env
COHERE_API_KEY=...
STAGE2_PROVIDER=cohere
STAGE2_MODEL=command-a-plus-05-2026
STAGE3_PRIMARY_PROVIDER=cohere
STAGE3_PRIMARY_MODEL=command-a-03-2025
```

무료 평가 키의 Chat 한도는 모델당 분당 20회, 월 1,000회다. 공식 안내: <https://docs.cohere.com/docs/rate-limits>

## 보유 키 기반 대체 경로

### Gemini

[Google AI Studio API Keys](https://aistudio.google.com/apikey)에서 `Create API key` 후 복사한다. 프로젝트는 `GEMINI_API_KEY`뿐 아니라 기존 루트 변수명 `Google_AI_STUDIO_API_KEY`도 인식한다.

```env
GEMINI_API_KEY=...
STAGE2_PROVIDER=gemini
```

공식 시작 안내: <https://ai.google.dev/gemini-api/docs/get-started>

### OpenAI

1. [OpenAI API Keys](https://platform.openai.com/api-keys)에서 프로젝트 키를 만든다.
2. [Billing](https://platform.openai.com/settings/organization/billing/overview)에서 결제수단/크레딧과 사용한도를 설정한다.
3. 프로젝트 `.env`에 저장한다. 기존 루트 변수명 `OpenAI_API_KEY`도 인식한다.

```env
OPENAI_API_KEY=...
STAGE3_PRIMARY_PROVIDER=openai
```

GPT-5.4 mini는 무료 티어에서 지원되지 않으므로 결제 활성화가 필요하다. 공식 모델 안내: <https://developers.openai.com/api/docs/models/gpt-5.4-mini>

### NVIDIA NIM

1. [NVIDIA API Keys](https://build.nvidia.com/settings/api-keys)에 로그인한다.
2. 개인 키를 만들 때 `NVIDIA Public API Endpoints` 권한을 포함한다.
3. 생성 직후 키를 복사해 `.env`에 저장한다.

```env
NVIDIA_API_KEY=...
STAGE3_FALLBACK_PROVIDER=nvidia
```

공식 키 안내: <https://docs.nvidia.com/ngc/latest/ngc-user-guide.html#generating-ngc-api-keys>

## 실호출 전환 블록

Cohere·OpenAI·G2B 키를 입력한 뒤 mock 값만 다음처럼 바꾼다.

```env
STAGE2_PROVIDER=cohere
STAGE2_MODEL=command-a-plus-05-2026
STAGE3_PRIMARY_PROVIDER=cohere
STAGE3_PRIMARY_MODEL=command-a-03-2025
STAGE3_FALLBACK_PROVIDER=openai
STAGE3_FALLBACK_MODEL=gpt-5.4-mini
```

먼저 `python scripts/preflight.py`로 키 존재 여부와 DB 연결 준비상태를 확인하고, `python scripts/probe_llm.py --target all`로 모델 접근을 한 번씩 점검한다. 두 명령은 키 값을 출력하지 않는다.
