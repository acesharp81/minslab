# 03. 픽셀오피스

계층형 멀티에이전트가 업무를 분담하고 검수하는 과정과, 제한된 LLM 자원을 안전하게 배분하는 과정을 픽셀 오피스로 보여주는 하네스 엔지니어링 실습입니다.

## 과제 핵심

> **이번 과제의 핵심은 AI Agent가 업무를 처리하는 구조를 설계하고, 입력 → 처리 → 검증 → 출력 흐름을 실행 가능한 하네스로 표현하는 것입니다.**

### 바이브 코딩을 활용한 하네스 구조 구현

자연어로 업무 시나리오와 화면 피드백을 빠르게 구체화하고, 반복 구현한 결과를 코드·이벤트·테스트 계약으로 고정하는 방식으로 개발했습니다.

1. “현안 대응 패키지를 여러 전문 Agent가 만든다”는 업무 시나리오를 자연어로 정의했습니다.
2. Agent 역할, 계층, 공용 Agent Pool과 작업 순서를 대화형으로 세분화했습니다.
3. 아바타 이동, 대면 문서 전달, 중간 검수처럼 실행 상태가 보이도록 UI를 반복 개선했습니다.
4. 자연어 요구사항을 DAG, Quality Gate, 이벤트 타입과 산출물 스키마로 변환했습니다.
5. 테스트로 이벤트 순서, 순환 없는 DAG, 모델 슬롯, 인증과 키 격리를 검증해 재현 가능한 하네스로 완성했습니다.

구축 과정의 상세 요구사항과 단계별 계획은 [`incident_response_multi_agent_project_plan.md`](incident_response_multi_agent_project_plan.md)에서 확인할 수 있습니다.

### 하네스 주제·구성 목적·전체 구조

| 항목 | 내용 |
|---|---|
| 주제 | 계층형 멀티에이전트가 공공서비스 장애 현안 대응 패키지를 만드는 업무 하네스 |
| 구성 목적 | Agent의 역할 분담, 병렬 작업, 공용 기능 재사용, 중간 검수와 모델 자원 제약을 하나의 흐름으로 검증 |
| 입력 | 사용자 현안 요청, 에이전트별 모델 설정, 실제 실행 시 API Key 사용 방식 |
| 처리 | Mission Manager의 업무 분해 → 공용 수집·요약 → 기술·법제 분석 → 보고자료 작성 |
| 검증 | 근거·분석·초안·리스크 Quality Gate, 수정 반송과 재검수 |
| 출력 | 추적 가능한 산출물 9종, 최종 대응 패키지, 감사 이벤트 로그와 픽셀오피스 시각화 |

```text
[입력]
현안 요청 + 모델 설정
    ↓
[처리]
업무 분해 → 자료 수집 → 공용 요약 → 전문 분석 → 보고자료 작성
    ↓
[검증]
근거 검수 → 분석 검수 → 초안 검수 → 독립 리스크 검수
    ↓
[출력]
최종 대응 패키지 + 산출물 이력 + 하네스 이벤트 시각화
```

## 1. 하네스 정의

이 프로젝트의 하네스는 두 영역으로 나뉩니다.

### 업무 흐름 하네스

업무 흐름 하네스는 **무슨 일을 어떤 순서와 책임으로 처리할지** 통제합니다. 단순히 여러 에이전트에게 질문을 동시에 보내는 것이 아니라, 업무 분해부터 최종 산출물 보관까지 재현 가능한 절차로 정의했습니다.

- 계층 구조: Mission Manager 아래에 Evidence·Analysis·Document·Quality Coordinator를 둡니다.
- 작업 DAG: 선행 작업이 완료돼야 다음 작업을 시작할 수 있도록 의존성을 검증합니다.
- 공용 에이전트 풀: 자료 수집과 요약처럼 여러 팀에서 반복 사용하는 기능은 공유 풀에서 배정합니다.
- 품질 게이트: 근거, 분석, 초안, 리스크 단계마다 검수하고 실패하면 수정 작업으로 되돌립니다.
- 추적 가능한 산출물: 각 결과물에 작성자, 선행 자료, 상태, 버전과 수정 이력을 연결합니다.
- 이벤트 계약: 배정·실행·전달·검수·완료를 표준 이벤트로 기록해 화면과 실행 엔진이 같은 상태를 사용합니다.

동작 흐름은 다음과 같습니다.

```text
현안 접수 → 업무 분해 → 자료 수집·공용 요약 → 전문 분석
→ 보고자료 작성 → 독립 리스크 검수 → 최종 통합·보관
```

### 인프라 제약 하네스

인프라 제약 하네스는 **한정된 모델 자원을 어떤 조건에서 얼마나 사용할지** 통제합니다. 에이전트 수와 실제 LLM 실행 수를 분리해, 많은 에이전트가 있어도 서버와 외부 API가 감당할 수 있는 범위 안에서만 호출합니다.

- 모델 선택: 에이전트별로 Local LLM, Hugging Face, OpenRouter 모델을 할당합니다.
- Provider Lane: 공급자마다 별도 대기열과 실행 슬롯을 둡니다.
- 동시성 제한: 기본값은 Ollama 1개, Hugging Face 1개, OpenRouter 2개입니다.
- 실행 예산: 실행당 최대 모델 호출 8회, 실제 실행 동시 1개, 기본 시간당 1회로 제한합니다.
- 시간·응답 제한: 호출 타임아웃, 전체 실행시간, 호출별 최대 토큰을 상한 안에서 관리합니다.
- 실패 격리: 실제 LLM 실행 실패를 성공한 데모 결과로 바꾸지 않고 실패 상태와 이벤트를 그대로 남깁니다.
- 접근 통제: 사이트 오너 키는 암호 인증, 개인 키는 실행 시 임시 전달 방식으로 분리합니다.

즉, 업무 흐름 하네스가 **일의 정확한 진행 방식**을 보장한다면, 인프라 제약 하네스는 **실행의 안전성과 비용 상한**을 보장합니다.

## 2. 유료 LLM 비활성화 제약

실제 LLM 사용은 기본적으로 비활성화됩니다. 화면과 하네스 동작을 확인하는 데 외부 API 비용이 필요하지 않도록 데모 실행을 기본 경로로 사용합니다.

| 구분 | 데모 | 실제 LLM |
|---|---|---|
| 모델 호출 | 없음 | 선택 모델 실제 호출 |
| 비용 | 없음 | 공급자 정책에 따라 발생 가능 |
| 결과 | 미리 정의된 결정적 이벤트·산출물 | 모델 응답으로 산출물 생성 |
| 소요 시간 | 빠른 재생 | 약 1~5분 |
| 활성화 | 항상 가능 | 오너 키 암호 인증 또는 개인 키 입력 |

이 제약은 API 키 노출, 의도하지 않은 과금, 로컬 LLM 자원 고갈과 반복 클릭을 방지하기 위한 것입니다. 실제 실행은 다음 조건을 모두 만족해야 합니다.

1. 모델 설정에서 두 API Key 사용 방식 중 하나를 선택합니다.
2. 사이트 오너 키는 실행 암호 인증을 완료하고 10분 안에 사용합니다.
3. 개인 키는 OpenRouter 또는 Hugging Face 키를 입력한 뒤 바로 실행합니다.
4. 두 방식 모두 동시 실행·시간당 실행·호출 수 제한을 초과하지 않아야 합니다.

### API Key 사용 방식

- **사이트 오너 API Key 활성화**: 홈페이지 루트 `.env`의 키를 사용합니다. 실행 암호 확인 후 10분 동안 활성화되며 실제 실행을 시작하면 인증 토큰은 소모됩니다.
- **개인 Key 사용**: OpenRouter와 Hugging Face 입력칸 중 하나 이상을 사용합니다. 키는 환경변수, 실행 기록, 산출물, 브라우저 저장소에 보관하지 않고 해당 실행 객체에만 전달한 뒤 폐기합니다.

두 방식은 라디오 버튼으로 상호 배타적으로 선택됩니다. 개인 키 모드에서는 사이트 오너의 원격 API 키를 fallback으로 사용하지 않습니다. 입력되지 않은 provider의 에이전트는 사용 가능한 로컬 모델 또는 입력된 provider 모델로 fallback될 수 있습니다.

## 3. 프로젝트 설명

- 제목: **픽셀오피스**
- 목적: **멀티에이전트 및 하네스 시뮬레이션**

### 프로세스

1. Mission Manager가 현안을 접수하고 작업 DAG를 생성합니다.
2. Coordinator가 capability에 맞는 전담 또는 공용 에이전트를 배정합니다.
3. 자료 수집 에이전트가 병렬로 근거를 만들고 공용 요약 에이전트가 통합합니다.
4. 기술·법제 에이전트가 요약 근거를 바탕으로 병렬 분석합니다.
5. 보고 에이전트가 분석 결과를 보고자료로 작성합니다.
6. Risk Checker가 근거·법령·표현을 독립 검수하고 필요하면 수정 요청을 반송합니다.
7. Final Synthesizer가 검수 통과 자료를 최종 패키지로 통합해 보관합니다.

### 구현 핵심 요소

- 계층형 Coordinator와 capability 기반 공용 Agent Pool
- DAG 의존성 검증과 병렬 실행 Wave
- 에이전트별 모델 할당 및 Provider별 동시성 제어
- 데모 실행과 실제 LLM 실행의 명확한 분리
- 실행 암호, 일회용 토큰, 호출·시간·토큰 예산
- 이벤트 기반 실시간 상태·감사 로그 시각화
- 검수 과정, 대면 문서 전달, 반송과 최종 제출 애니메이션
- 산출물 본문·근거·의존성·버전 이력 열람
- HiDPI Canvas 기반 픽셀 아바타와 선명한 픽셀오피스 화면

## 사용 방법과 실행 예시

### 1. 데모 실행

1. 홈페이지 포트폴리오에서 `03 · 픽셀오피스`를 엽니다.
2. `현안 요청` 입력칸에 처리할 업무를 작성합니다.
3. `에이전트 팀 출동 / 데모`를 누릅니다.
4. 픽셀오피스, 작업 DAG, Quality Gate와 하네스 이벤트에서 처리 과정을 확인합니다.
5. `산출물 열람`에서 생성 문서의 본문, 근거, 의존성과 수정 이력을 확인합니다.

데모는 외부 LLM을 호출하지 않으며 동일한 입력에는 동일한 이벤트 흐름을 재생합니다.

### 2. 실제 LLM 실행

1. `에이전트 모델 설정`에서 Agent별 모델을 선택합니다.
2. API Key 사용 방식을 하나만 선택합니다.
   - `사이트 오너 API Key 활성화`: 실행 암호 인증 후 10분 안에 사용
   - `개인 Key 사용`: OpenRouter 또는 Hugging Face 키를 실행 시점에만 입력
3. `에이전트 팀 출동 / 실제 LLM사용`을 누릅니다.
4. 확인창에서 `LLM실행하기`를 선택합니다.
5. 약 1~5분 동안 실제 하네스 이벤트와 생성 산출물을 확인합니다.

### 입력 예시

```text
전국 공공서비스 예약시스템이 오전 9시부터 11시까지 접속 장애를 겪었다는
민원이 다수 발생했다. 언론 문의와 국회 질의 가능성에 대비해
현안 대응 패키지를 만들어줘.
```

### 실행 흐름 예시

```text
run.started
→ collect-facts + collect-public 병렬 수행
→ summarize-evidence 공용 요약
→ technical-analysis + legal-review 병렬 수행
→ executive-brief 보고자료 작성
→ risk-check 독립 검수 및 필요 시 수정 반송
→ final-package 최종 통합
→ run.completed
```

### 결과 예시

- `01_fact_timeline.md`: 장애 사실관계와 타임라인
- `evidence_summary.md`: 수집 자료를 통합한 공용 근거 요약
- `02_technical_analysis.md`, `03_legal_policy_review.md`: 기술·법제 병렬 분석
- `07_executive_brief.md`: 검수와 수정 이력이 포함된 보고자료
- `09_risk_check.md`: 사실·법령·표현 독립 검수 결과
- `10_final_package.md`: Quality Gate를 모두 통과한 최종 현안 대응 패키지

화면에서는 Agent가 회의 지점에서 산출물을 직접 전달하고, 검수 실패 문서는 빨간 문서로 반송되며, 최종 패키지는 Filing Cabinet에 보관됩니다.

## GitHub에서 이 폴더 읽는 방법

이 폴더는 별도 실행 패키지가 아니라 MinsLab 홈페이지에 연결되는 **프로젝트 소스 묶음**입니다. GitHub에서 이 서브폴더 주소만 공유해도 설계, 백엔드 흐름, UI 이벤트와 검증 방법을 순서대로 파악할 수 있도록 구성했습니다.

### 권장 분석 순서

| 순서 | 파일 | 확인할 내용 |
|---|---|---|
| 1 | `README.md` | 하네스 정의, 제약, 전체 프로세스 |
| 2 | `docs/ARCHITECTURE.md` | 컴포넌트 경계와 모델 실행 슬롯 |
| 3 | `harness_engine.py` | 에이전트 계층, 공용 풀, 데모 이벤트 계약 |
| 4 | `scheduler.py` | capability 라우팅, DAG 검증, 병렬 Wave |
| 5 | `artifact_catalog.py` | 산출물 본문, 근거, 의존성과 버전 정보 |
| 6 | `model_gateway.py` | Ollama·Hugging Face·OpenRouter 호출과 동시성 제어 |
| 7 | `live_executor.py` | 실제 LLM 기반 8개 작업 실행과 이벤트 발행 |
| 8 | `service.py` | 홈페이지가 호출하는 API 경계, 인증과 실행 상태 관리 |
| 9 | `capacity_probe.py` | 실제 호출 전 provider 용량을 보수적으로 점검하는 관리자 도구 |
| 10 | `app/` | 이벤트를 픽셀오피스 화면과 아바타 동작으로 변환하는 UI |
| 11 | `tests/` | DAG, 이벤트, 슬롯, 인증과 실제 실행 계약 검증 |

### 코드 흐름

```text
홈페이지 요청
  → service.py / dispatch
  → harness_engine.py 데모 실행 또는 live_executor.py 실제 실행
  → scheduler.py 작업 배정·DAG Wave
  → model_gateway.py provider별 제한 실행
  → artifact_catalog.py 산출물 생성·갱신
  → 하네스 이벤트 및 실행 상태 응답
  → app/app.js 픽셀오피스·검수·문서 전달 시각화
```

### 폴더 경계

프로젝트 고유의 에이전트 정의, 스케줄러, 모델 게이트웨이, 실행기, 산출물, UI, 문서와 테스트는 모두 이 폴더 안에 있습니다. 폴더 밖에 있는 다음 두 항목은 홈페이지 공통 코어이므로 의도적으로 포함하지 않습니다.

- `main.py`: 정적 앱과 `/api/portfolio/multiagent-harness` 경로를 홈페이지에 연결
- 저장소 루트 `.env`: 여러 홈페이지 프로젝트가 함께 사용하는 비밀 설정 저장

두 항목은 통합 지점일 뿐 하네스 업무 로직을 포함하지 않습니다. 따라서 GitHub에서 이 서브폴더만 분석해도 프로젝트 전체 흐름을 이해할 수 있습니다.

## 홈페이지 실행 화면

기존 홈페이지에 포함된 경우 다음 경로에서도 같은 프로젝트를 실행할 수 있습니다.

```text
https://www.minslab.kr/portfolio?project=multiagent-harness
```

전체 화면:

```text
https://www.minslab.kr/portfolio/multiagent-harness/
```

로컬 API:

```text
GET  /api/portfolio/multiagent-harness/health
GET  /api/portfolio/multiagent-harness/config
GET  /api/portfolio/multiagent-harness/models
GET  /api/portfolio/multiagent-harness/gateway/status
POST /api/portfolio/multiagent-harness/demo
POST /api/portfolio/multiagent-harness/live/authorize
POST /api/portfolio/multiagent-harness/live
GET  /api/portfolio/multiagent-harness/runs/{run_id}
```

## 구성

```text
Mission Manager
├── Evidence Coordinator
│   ├── Collector Pool × 2
│   └── Summarizer Pool × 1
├── Analysis Coordinator
│   ├── Technical Analyst
│   └── Legal Policy Reviewer
├── Document Coordinator
│   └── Briefing Writer
└── Quality Coordinator
    ├── Risk Checker
    └── Final Synthesizer
```

에이전트 수와 실제 모델 실행 슬롯은 분리됩니다. 여러 작업이 동시에 준비돼도 중앙 Model Gateway가 provider별 동시성을 통제합니다.

## 모델 설정

모델 식별자는 다음 형식을 사용합니다.

```text
ollama:qwen2.5:1.5b
huggingface:Qwen/Qwen2.5-72B-Instruct
openrouter:openai/gpt-4o-mini
```

사이트 오너 API 키는 브라우저나 에이전트 설정에 전달하지 않고 홈페이지 저장소 루트 `.env`에서만 읽습니다. 이 폴더의 [`.env.example`](.env.example)은 필요한 항목을 설명하는 공개용 참고 파일이며, 사용할 값을 홈페이지 루트 `.env`에 추가합니다. 개인 키는 `.env`에 쓰지 않고 모델 설정 입력칸에서 실행할 때만 임시 전달합니다.

```dotenv
OLLAMA_BASE_URL=http://127.0.0.1:11434
HF_BASE_URL=https://router.huggingface.co/v1
HF_API_KEY=...
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
OPENROUTER_API_KEY=...

MULTI_AGENT_HF_MODELS=Qwen/Qwen2.5-72B-Instruct
MULTI_AGENT_OPENROUTER_MODELS=openai/gpt-4o-mini,google/gemini-2.5-flash
MULTI_AGENT_DEFAULT_MODEL=ollama:qwen2.5:1.5b
MULTI_AGENT_OLLAMA_CONCURRENCY=1
MULTI_AGENT_HF_CONCURRENCY=1
MULTI_AGENT_OPENROUTER_CONCURRENCY=2

# 실제 실행은 명시적으로 활성화합니다.
# 실제 값은 저장소에 커밋하지 않고 서버 .env에만 저장합니다.
MULTI_AGENT_LIVE_ENABLED_key=충분히_긴_실행_암호
MULTI_AGENT_LIVE_RUNS_PER_HOUR=1
MULTI_AGENT_LIVE_MAX_SECONDS=300
MULTI_AGENT_LIVE_CALL_TIMEOUT=120
MULTI_AGENT_LIVE_MAX_TOKENS=600
```
브라우저는 실행 암호와 개인 키를 저장소에 저장하지 않습니다. 오너 인증 성공 시 서버가 10분 유효한 일회용 토큰을 발급하며 실제 LLM 실행을 시작할 때 즉시 소모됩니다. 암호 인증 실패는 10분 동안 5회로 제한됩니다.


## 이벤트 기반 시각화

Canvas 화면은 다음 하네스 이벤트를 소비합니다.

```text
phase.changed
task.assigned
inference.queued
inference.started
inference.completed
artifact.created
handoff.requested
meeting.requested
review.started
review.item
review.failed
review.passed
submission.requested
run.completed
```

중요 산출물은 아바타가 중앙 회의 지점에서 직접 만나 전달합니다. Risk Checker의 필수 수정은 빨간 문서로 반송되며, 최종 패키지는 Final Synthesizer가 Filing Cabinet으로 이동해 보관합니다.

## 산출물 열람

실행 중 생성된 산출물 카드를 클릭하면 읽기 전용 상세 뷰어가 열립니다.

- Markdown 본문과 요약
- 작성 에이전트, 현재 버전, 실행 ID
- 작성 완료·수정 필요·검수 통과·보관 완료 상태
- 근거 문서와 선행 산출물 간 이동
- 수정 이력과 본문 복사

## 테스트

```bash
cd projects/03-multiagent-harness
python3 -m unittest discover -s tests -v
python3 -m py_compile artifact_catalog.py harness_engine.py live_executor.py model_gateway.py scheduler.py service.py
```

테스트는 이벤트 순서, 에이전트 참조, DAG 순환 검출, 공용 풀 분산, provider 단일 슬롯과 서비스 응답을 확인합니다.

## 파일 구성

```text
projects/03-multiagent-harness/
├── .env.example
├── .gitignore
├── app/
│   ├── index.html
│   ├── styles.css
│   └── app.js
├── tests/
├── harness_engine.py
├── artifact_catalog.py
├── live_executor.py
├── scheduler.py
├── model_gateway.py
├── project_env.py
├── capacity_probe.py
├── service.py
├── project.json
├── docs/
│   ├── ARCHITECTURE.md
│   ├── CAPACITY_PROBE.md
│   └── preview.png
├── demo/
│   └── sample-task.md
├── incident_response_multi_agent_project_plan.md
└── legacy/
    ├── backend_demo_service.py
    ├── api_multi_agent.py
    └── README-api-multi-agent.md
```

`legacy/`는 최초 API 멀티에이전트 프로토타입을 비교용으로 보관한 영역이며, 현재 홈페이지 실행 경로에서는 import하지 않습니다.

## 보안과 비용

- 외부 API 키를 응답, 이벤트, 로그와 브라우저 저장소에 포함하지 않습니다.
- 실제 모델 호출 전 실행별 호출 수·토큰·비용 한도를 적용합니다.
- 429·503은 `Retry-After` 또는 제한된 지수 backoff로 재시도합니다.
- 402는 재시도하지 않습니다.
- 개인정보와 실제 내부자료는 데모 입력으로 사용하지 않습니다.
- 실제 산출물은 Risk Checker와 사람의 최종 검토 전 공식 문서로 사용하지 않습니다.


## 홈페이지 통합 API 계약

루트 ASGI는 `/api/portfolio/multiagent-harness/*` 요청을 `service.py dispatch()`로 전달합니다. 프로젝트 서비스는 프레임워크에 의존하지 않는 사전형 응답을 반환하고, 루트가 HTTP 상태와 JSON으로 변환합니다.

| Method | 경로 | 역할 |
| --- | --- | --- |
| GET | `/health` | 서비스·실행 가능 상태 |
| GET | `/config` | 에이전트, DAG, 실제 실행 한도 |
| GET | `/models` | 사용 가능 provider·모델 목록 |
| GET | `/gateway/status` | provider lane의 슬롯·대기 상태 |
| POST | `/demo` | 모델 호출 없는 결정적 실행 생성 |
| POST | `/live/authorize` | 오너 실행 암호 검증과 10분 일회용 토큰 발급 |
| POST | `/live` | 실제 LLM 실행 시작 |
| GET | `/runs/{run_id}` | 실행 상태·이벤트·산출물 폴링 |

실행 기록은 데이터베이스가 아니라 서버 프로세스 메모리의 `OrderedDict`에 최근 12개만 보관됩니다. 서비스 재시작 시 사라지므로 감사·보존이 필요한 운영 시스템에서는 영속 저장소와 사용자 소유권을 추가해야 합니다.

## 실제 실행 제한값

| 항목 | 기본값 | 강제 범위·동작 |
| --- | --- | --- |
| 실제 실행 동시성 | 1 | `BoundedSemaphore(1)` |
| 시간당 실행 | 1 | 환경변수로 1~3 범위 |
| 모델 호출 수 | 8 | 실행 설정에 고정 |
| 인증 토큰 TTL | 600초 | 실제 실행 시작 시 소비 |
| 인증 실패 제한 | 10분 내 5회 | 초과 시 429 |
| 전체 실행 시간 | 300초 | `MULTI_AGENT_LIVE_MAX_SECONDS` |
| 호출 타임아웃 | 120초 | `MULTI_AGENT_LIVE_CALL_TIMEOUT` |
| 호출 출력 | 600토큰 | `MULTI_AGENT_LIVE_MAX_TOKENS` |

개인 키 모드는 `ModelGateway(allow_environment_keys=False)`를 사용하므로 입력하지 않은 원격 provider가 서버 환경키로 조용히 fallback하지 않습니다. 키는 길이와 개행을 검사하고 실행 객체에만 유지합니다.

## 결정적 스케줄링 규칙

`HierarchicalScheduler`는 작업 ID 중복, 존재하지 않는 의존성, DAG 순환을 실행 전에 거부합니다. Capability Router는 같은 capability를 가진 에이전트 중 현재 배정 횟수가 가장 적은 에이전트를 선택하고, 동률이면 ID 순서로 결정합니다. 따라서 동일한 에이전트 목록과 작업 DAG에는 재현 가능한 배정 결과가 나옵니다.

기본 업무 DAG의 병렬 wave는 다음과 같습니다.

```text
Wave 1: collect-facts, collect-public
Wave 2: summarize-evidence
Wave 3: technical-analysis, legal-review
Wave 4: executive-brief
Wave 5: risk-check
Wave 6: final-package
```

업무 병렬성은 Agent 작업 준비 상태이고 모델 병렬성은 Model Gateway 슬롯입니다. 같은 wave에 두 작업이 있어도 provider 슬롯이 1이면 하나는 `inference.queued` 상태로 기다립니다.
