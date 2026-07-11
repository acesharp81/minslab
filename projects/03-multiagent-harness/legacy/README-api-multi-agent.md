# 03. API 기반 멀티에이전트

하나의 요청을 조정자, 분석가, 검토자, 종합자가 역할별로 처리해 최종 답변을 만드는 독립 실행형 Python CLI 프로젝트입니다.

## 현재 상태

- 홈페이지 문서 등록: 완료
- 공개 설명 화면: https://www.minslab.kr/portfolio?project=api-multi-agent
- 실행 방식: 터미널 CLI
- 별도 웹서버 또는 포트: 없음
- 외부 패키지: 없음
- 기본 API: OpenRouter의 OpenAI 호환 Chat Completions
- 설정: 프로젝트 폴더 .env

홈페이지에서는 프로젝트 설명과 대표 코드를 보여주며 멀티에이전트 실행은 서버 터미널에서 수행합니다.

## 협업 흐름

~~~text
사용자 요청
    │
    ▼
조정자: 목표와 실행 계획 작성
    │
    ├──────────────┐
    ▼              ▼
분석가: 해결안     검토자: 위험·누락 검토
    └──────┬───────┘
           ▼
종합자: 중복 제거와 최종 답변 작성
~~~

분석가와 검토자는 ThreadPoolExecutor로 병렬 실행합니다. 종합자는 계획, 분석 결과와 검토 결과를 모두 받아 실행 가능한 최종 답변을 만듭니다.

실제 API 모드에서는 한 번의 요청 처리에 조정자 1회, 분석가·검토자 각 1회, 종합자 1회로 총 4회의 Chat Completions 호출이 발생합니다.

## 요구사항

- Python 3.10 이상
- 실제 API 모드에서는 OpenAI 호환 Chat Completions API 키
- 데모 모드에는 API 키나 네트워크가 필요하지 않음

표준 라이브러리의 urllib만 사용하므로 pip 설치가 필요하지 않습니다.

## 환경변수

기본적으로 프로젝트 폴더의 `.env`를 읽고, 이미 설정된 프로세스 환경변수는 덮어쓰지 않습니다.

~~~dotenv
OPENROUTER_API_KEY=YOUR_OPENROUTER_API_KEY
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1

# 선택
MULTI_AGENT_MODEL=openai/gpt-4o-mini
MULTI_AGENT_TIMEOUT=60
~~~

호환 별칭:

- MULTI_AGENT_API_KEY
- MULTI_AGENT_BASE_URL
- OPENROUTER_MODEL

우선순위는 멀티에이전트 전용 환경변수, 공용 OpenRouter 환경변수, 코드 기본값 순서입니다.

## 실행 방법

프로젝트 폴더로 이동합니다.

~~~bash
cd 03-multiagent-harness
~~~

API 없이 협업 흐름 확인:

~~~bash
python3 api_multi_agent.py --demo "신규 AI 서비스 출시 계획을 작성해줘"
~~~

실제 API 실행:

~~~bash
python3 api_multi_agent.py "신규 AI 서비스 출시 계획을 작성해줘"
~~~

모든 에이전트의 결과와 소요 시간 출력:

~~~bash
python3 api_multi_agent.py --verbose "사내 문서 검색 챗봇의 도입 전략을 검토해줘"
~~~

구조화된 JSON 출력:

~~~bash
python3 api_multi_agent.py --json "현장점검 플랫폼의 운영 계획을 작성해줘"
~~~

다른 환경설정 파일 사용:

~~~bash
python3 api_multi_agent.py --env-file /safe/path/agent.env "요청 내용"
~~~

## 출력 구조

일반 모드는 종합자의 최종 답변, 사용 모델과 전체 소요 시간을 출력합니다.

verbose 또는 JSON 모드에서는 각 단계의 다음 정보도 확인할 수 있습니다.

- 에이전트 이름
- 역할
- 결과 내용
- 단계별 소요 시간
- 전체 처리 시간

## 파일 구성

~~~text
projects/03-api-multi-agent/
├── README.md
├── project.json
└── api_multi_agent.py
~~~

api_multi_agent.py는 상위 서비스 모듈을 import하지 않으며 이 폴더에서 독립적으로 실행됩니다.

## 오류 처리

다음 상황은 오류 메시지와 종료 코드 1로 처리합니다.

- API 키 누락
- 0 이하이거나 숫자가 아닌 timeout
- HTTP 오류 또는 네트워크 연결 실패
- 비정상 API 응답
- 빈 에이전트 응답

Ctrl+C로 중단하면 종료 코드 130을 반환합니다.

## 보안과 비용

- API 키를 소스, project.json 또는 실행 로그에 기록하지 않습니다.
- 개인정보, 비밀번호와 인증 토큰을 에이전트 요청에 넣지 않습니다.
- 실제 API 모드는 요청당 4회 호출되므로 모델별 사용량과 비용을 확인합니다.
- 최종 답변은 여러 모델 호출의 종합 결과이므로 중요한 의사결정 전에 사람이 검토합니다.
