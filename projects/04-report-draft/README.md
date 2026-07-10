# 04. 보고서 초안 생성

홈페이지의 기존 `myservice` 안에서 실행되는 포트폴리오 프로젝트입니다. 04번을
위해 별도 Python 웹 서버를 실행하거나 추가 포트를 열지 않습니다.

접속 경로:

```text
http://localhost:8000/portfolio?project=report-draft
```

## 현재 실행 구조

```text
브라우저
  │
  │ 기존 홈페이지 127.0.0.1:8000
  ▼
main.py ASGI API
  │
  ├── portfolio_service.py  모델 목록·옵션 검증·Ollama 호출
  ├── report_core.py        XML 검색·프롬프트 구성·응답 정리
  └── data/*.xml            민원 사실관계·조치계획
              │
              ▼
      Ollama 127.0.0.1:11434
```

- `8000`: 홈페이지가 사용하는 기존 내부 포트
- `11434`: 로컬 LLM 호출에 필요한 Ollama 내부 포트
- 04 프로젝트 전용 포트: 없음

Ollama 포트는 브라우저에 노출하지 않습니다. 홈페이지 백엔드만 로컬로 호출합니다.

## 처리 흐름

1. 사용자가 민원 요청을 입력합니다.
2. `report_core.py`가 XML 사례의 제목·키워드·본문을 점수화합니다.
3. 가장 관련 있는 사례의 사실관계, 조치계획, 필수 문구를 프롬프트로 구성합니다.
4. `portfolio_service.py`가 선택된 로컬 모델과 생성 옵션으로 Ollama를 호출합니다.
5. 홈페이지에 8줄 이내 초안, 자료 ID, 담당부서, 문의처와 검토 안내를 표시합니다.

## 홈페이지 옵션

- 서버에 설치된 로컬 Ollama 모델 선택
- Temperature
- 최대 생성 토큰
- Context 크기
- 시스템 프롬프트 편집 및 기본값 복원

옵션은 현재 브라우저의 `localStorage`에 저장되며 보고서 생성 요청에만 적용됩니다.
시스템 프롬프트는 최대 4,000자이고, 빈 값은 서버 기본값으로 처리합니다.

## 파일 구성

```text
04-report-draft/
├── report_core.py                # 포트 없는 보고서 처리 코어
├── portfolio_service.py          # 홈페이지 API와 Ollama 연결
├── project.json                  # 포트폴리오 메타데이터
├── config/model_config.json      # 생성 옵션 기본값
├── data/civil_reply_context.xml  # 민원 사례와 작성 기준
└── assets/결과 스샷.png           # 원본 테스트 결과 기록
```

## 홈페이지 API

- `GET /api/portfolio/report-draft/models`
- `POST /api/portfolio/report-draft/generate`

## 검토 원칙

- XML에 없는 주소, 법령, 수치와 확정 일정을 새로 만들지 않습니다.
- 생성 결과는 검토 전 초안으로 취급합니다.
- 실제 회신 전 담당자가 사실관계, 법령 근거와 개인정보 포함 여부를 확인합니다.
