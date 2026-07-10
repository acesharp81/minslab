# 03. API 기반 멀티에이전트

하나의 사용자 요청을 여러 역할의 에이전트가 나누어 처리하고, 마지막 에이전트가 결과를 종합하는 독립 실행형 CLI 실습입니다.

## 협업 흐름

```text
사용자 요청
    │
    ▼
조정자(실행 계획)
    │
    ├──────────────┐
    ▼              ▼
분석가(API)      검토자(API)
    └──────┬───────┘
           ▼
      종합자(API)
           │
           ▼
       최종 답변
```

분석가와 검토자는 서로의 결과를 기다릴 필요가 없으므로 병렬로 호출합니다. 종합자는 실행 계획과 두 결과를 함께 받아 중복을 제거하고 실행 가능한 최종 답변을 만듭니다.

## 특징

- `urllib` 기반 OpenAI 호환 `/chat/completions` API 호출
- `ThreadPoolExecutor` 기반 독립 에이전트 병렬 실행
- 에이전트별 역할, 입력, 결과, 소요 시간 기록
- API 호출 없이 협업 구조를 확인하는 `--demo` 모드
- 기존 서비스 모듈과 패키지를 import하지 않는 단일 Python 실행 파일
- 저장소 루트의 공용 `.env`에 있는 OpenRouter 설정 재사용

## 설정

Python 3.10 이상만 필요하며 별도 패키지를 설치하지 않습니다. 설정은 이 프로젝트 폴더에 따로 만들지 않고 저장소 루트의 공용 `.env`를 읽습니다.

```bash
cd /home/ubuntu/apps/myservice
cp .env.example .env  # 공용 .env가 아직 없을 때만 실행
```

공용 `.env`의 기존 OpenRouter 설정을 그대로 사용합니다.

```dotenv
OPENROUTER_API_KEY=YOUR_OPENROUTER_API_KEY
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
```

모델은 기본값 `openai/gpt-4o-mini`를 사용합니다. 필요하면 같은 공용 `.env`에 `MULTI_AGENT_MODEL`과 `MULTI_AGENT_TIMEOUT`을 추가할 수 있습니다.

## 실행

API 없이 흐름 확인:

```bash
python3 api_multi_agent.py --demo "신규 AI 서비스 출시 계획을 작성해줘"
```

실제 API 호출:

```bash
python3 api_multi_agent.py "신규 AI 서비스 출시 계획을 작성해줘"
```

중간 에이전트 결과와 실행 메타데이터 확인:

```bash
python3 api_multi_agent.py --verbose "사내 문서 검색 챗봇의 도입 전략을 검토해줘"
```

기본 설정 경로는 저장소 루트의 `.env`입니다. 필요한 경우에만 `--env-file`로 다른 공용 설정 파일을 지정할 수 있습니다.

```bash
python3 api_multi_agent.py --env-file /safe/path/agent.env "요청 내용"
```

## 보안

- API 키는 루트 공용 `.env`에서만 관리하고 소스나 `project.json`에 기록하지 않습니다.
- 에이전트에게 전달하는 요청에는 비밀번호, 인증 토큰, 개인정보를 포함하지 않습니다.
- 실제 업무 의사결정에는 최종 답변과 근거를 사람이 다시 검토합니다.
