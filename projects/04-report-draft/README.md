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
