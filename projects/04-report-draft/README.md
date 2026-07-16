# 04. 보고서 초안 생성

사용자 요청과 가장 관련 있는 XML 민원 사례를 선택하고, 서버의 로컬 Ollama 모델로 검토 전 행정 회신 초안을 생성하는 실행형 포트폴리오 프로젝트입니다.

## 현재 상태

- 홈페이지 통합: 완료
- 공개 화면: https://www.minslab.kr/portfolio?project=report-draft
- 별도 프로젝트 웹서버 또는 전용 포트: 없음
- 실행 백엔드: 기존 main.py ASGI 서비스
- LLM: 서버 내부 Ollama
- 문맥 데이터: civil_reply_context.xml의 민원 사례 6건

04 프로젝트를 위해 별도 Python HTTP 서버를 실행하지 않습니다. 브라우저는 기존 홈페이지 API만 호출하고, 홈페이지 백엔드가 127.0.0.1:11434의 Ollama에 연결합니다.

## 실행 구조

~~~text
브라우저
  │
  │ 기존 MinsLab HTTPS
  ▼
main.py ASGI API
  │
  ├── portfolio_service.py  모델 목록, 옵션 검증, Ollama 호출
  ├── report_core.py        XML 검색, 프롬프트 구성, 응답 정리
  └── data/*.xml            민원 사실관계와 조치계획
              │
              ▼
      Ollama 127.0.0.1:11434
~~~

- 8000: 기존 홈페이지 Uvicorn의 localhost 내부 포트
- 11434: Ollama의 localhost 내부 포트
- 04 프로젝트 전용 포트: 없음

## 처리 흐름

1. 사용자가 예시 요청을 선택하거나 최대 8,000자의 요청을 입력합니다.
2. report_core.py가 요청 토큰과 각 XML 사례의 제목·키워드·본문을 점수화합니다.
3. 가장 관련 있는 사례의 사실관계, 조치계획, 필수 문구와 작성 기준을 프롬프트로 구성합니다.
4. portfolio_service.py가 설치된 Ollama 대화 모델과 생성 옵션을 검증합니다.
5. Ollama에 JSON 형식의 초안 생성을 요청합니다.
6. 응답을 정리하고 최대 8줄로 제한합니다.
7. 자료 ID, 제목, 담당부서, 문의처와 담당자 검토 안내를 함께 표시합니다.

## 홈페이지 옵션

- 서버에 설치된 로컬 Ollama 대화 모델 선택
- Temperature: 0.0~2.0
- 최대 생성 토큰: 500~4,096
- Context 크기: 512~32,768
- 시스템 프롬프트 편집: 최대 4,000자
- 기본값 복원

생성 옵션과 시스템 프롬프트는 현재 브라우저의 localStorage에 저장되고 이 프로젝트 요청에만 적용됩니다. 시스템 프롬프트가 비어 있으면 서버 기본값을 사용합니다.

API 키, 개인정보와 비밀정보를 시스템 프롬프트에 입력하면 안 됩니다.

## 환경변수와 설정

루트 공용 .env에서 다음 선택 설정을 읽습니다.

~~~dotenv
OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_MODEL=qwen2.5:1.5b
~~~

설정하지 않으면 config/model_config.json의 값과 코드 기본값을 사용합니다. 화면의 모델 목록은 설정 파일의 권장 목록이 아니라 현재 Ollama에 실제 설치된 대화 모델을 기준으로 구성됩니다.

기본 생성 옵션은 다음 파일에서 관리합니다.

~~~text
projects/04-report-draft/config/model_config.json
~~~

## 홈페이지 API

- GET /api/portfolio/report-draft/models
- POST /api/portfolio/report-draft/generate

생성 요청 예시:

~~~json
{
  "request": "공원 야간 소음 민원 회신 초안을 작성해 주세요.",
  "model": "qwen2.5:1.5b",
  "options": {
    "temperature": 0.3,
    "num_predict": 500,
    "num_ctx": 2048,
    "system_prompt": ""
  }
}
~~~

응답에는 생성 초안, 선택 모델, 적용 옵션, 소요 시간, 선택 사례와 검토 안내가 포함됩니다. 시스템 프롬프트 원문은 응답하지 않고 기본값 수정 여부만 반환합니다.

## 파일 구성

~~~text
projects/04-report-draft/
├── README.md
├── project.json
├── report_core.py
├── portfolio_service.py
├── config/
│   └── model_config.json
├── data/
│   └── civil_reply_context.xml
├── assets/
│   └── 결과 스샷.png
└── 과제설명.txt
~~~

## 로컬 검증

홈페이지 서비스가 실행 중일 때 다음 경로를 확인합니다.

~~~bash
curl -fsS http://127.0.0.1:8000/api/portfolio/report-draft/models
~~~

Ollama 확인:

~~~bash
curl -fsS http://127.0.0.1:11434/api/tags
~~~

## 검토 원칙

- XML에 없는 주소, 법령, 수치와 확정 일정을 새로 만들지 않습니다.
- 결과는 검토 전 초안이며 자동 발송하지 않습니다.
- 담당자가 사실관계, 법령 근거, 일정과 개인정보 포함 여부를 확인합니다.
- 모델 변경이나 시스템 프롬프트 수정 후에는 출력 형식과 필수 문구를 다시 점검합니다.


## XML 문맥 스키마와 선택 방식

`data/civil_reply_context.xml`의 각 사례는 최소한 자료 ID, 제목, 키워드, 사실관계, 조치계획, 필수 포함문구, 담당부서와 문의처를 가집니다. `report_core.py`는 XML을 구조적으로 파싱하고 사용자 요청과 다음 영역을 비교합니다.

1. 제목과 키워드의 직접 일치
2. 요청 토큰과 사례 본문의 중첩
3. 사전에 정의된 주제별 가중 단어
4. 동점일 때 XML 원본 순서

선택된 사례 하나만 LLM 문맥에 넣어 관련 없는 민원 자료가 섞이는 것을 줄입니다. 검색 점수와 선택 자료 ID는 결과 metadata에 포함되므로 어떤 근거가 사용됐는지 화면에서 확인할 수 있습니다.

## 생성 옵션의 실제 적용

`config/model_config.json`의 현재 기본값:

| 항목 | 기본값 | 서버 허용 범위 |
| --- | --- | --- |
| `temperature` | 0.3 | 0.0~2.0 |
| `num_predict` | 500 | 500~4096 |
| `num_ctx` | 2048 | 512~32768 |
| `system_prompt` | 행정 회신 JSON 작성 규칙 | 최대 4000자 |

`portfolio_service.py`는 브라우저 값을 그대로 신뢰하지 않고 숫자 범위, 모델명과 시스템 프롬프트 길이를 다시 검증합니다. 설치 모델 목록에서 embedding 계열은 제외합니다. 선택 모델이 사라졌거나 설치되지 않았으면 생성 요청을 거부합니다.

Ollama 요청은 `/api/chat`, `stream=false`, `keep_alive=5m`를 사용하고, options에 temperature·num_predict·num_ctx를 전달합니다.

## 출력 정규화

모델에는 JSON 객체 출력을 요청하지만 로컬 모델이 코드 펜스나 설명 문장을 섞을 수 있어 다음 순서로 정리합니다.

```text
응답 문자열 확보
  → Markdown code fence 제거
  → JSON 객체 구간 파싱 시도
  → draft/lines 계열 필드 추출
  → 비어 있으면 일반 텍스트 fallback
  → 공백·빈 줄 정리
  → 최대 8줄 제한
  → 필수 문구 누락 시 검토 경고
```

응답에는 시스템 프롬프트 원문을 반환하지 않습니다. 대신 기본 프롬프트 사용 여부와 적용된 숫자 옵션만 돌려줘 비밀정보가 프롬프트에 잘못 들어갔을 때 노출 범위를 줄입니다.

## 실패 모드

| 증상 | 확인 항목 |
| --- | --- |
| 모델 목록 비어 있음 | Ollama 프로세스, `OLLAMA_BASE_URL`, `/api/tags` |
| XML 사례 없음 | 파일 경로, XML 문법, 필수 필드 |
| 관련 없는 사례 선택 | 요청 핵심어와 사례 keywords/title |
| JSON 파싱 실패 | 정규화 fallback 결과와 시스템 프롬프트 |
| 생성 시간 초과 | 모델 크기, num_predict, 서버 CPU·메모리 |
| 필수 문구 누락 | 담당자 검토 경고와 선택 XML 원문 |

## 모듈별 책임

- `report_core.py`: 데이터 파싱, 사례 검색, 프롬프트 작성, LLM 응답 정규화. HTTP나 Ollama 연결을 알지 못합니다.
- `portfolio_service.py`: 환경설정, 모델 조회, 입력 제한, Ollama 호출, API 응답 조립.
- `main.py`: ASGI 요청 본문을 읽고 위 서비스를 thread에서 실행한 뒤 HTTP JSON으로 반환.
- 브라우저 UI: 옵션 localStorage, 실행 상태, 결과·근거·검토 안내 표시.
