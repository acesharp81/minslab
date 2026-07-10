# 포트폴리오 프로젝트 안내

MinsLab 홈페이지의 포트폴리오 목록은 projects/*/project.json을 자동으로 읽어 구성합니다.

## 현재 프로젝트

| 번호 | 폴더 | 프로젝트 | 실행 방식 |
| --- | --- | --- | --- |
| 01 | 01-chunking-lab | 청킹 실습 | 홈페이지 실행형 Supabase·LLM 비교 |
| 02 | 02-chunking-rag-lab | 청킹실습(과제) | 홈페이지 실행형 청킹·임베딩·RAG |
| 03 | 03-api-multi-agent | API 기반 멀티에이전트 | 독립 Python CLI, 홈페이지 문서 표시 |
| 04 | 04-report-draft | 보고서 초안 생성 | 홈페이지 실행형 로컬 Ollama |

각 폴더의 README.md에 현재 실행 구조, 공용 환경변수, 사용법과 주의사항을 기록합니다.

## 기본 폴더 구조

~~~text
projects/
└── 05-new-project/
    ├── project.json   # 홈페이지 목록과 설명
    ├── README.md      # 실행 구조와 학습 기록
    ├── main.py        # 대표 소스 예시
    └── assets/        # 이미지와 샘플 결과물
~~~

폴더명의 두 자리 번호, project.json의 order와 display_no는 같은 번호로 맞춥니다.

## project.json 필수 기준

- id: 전체 컬렉션에서 중복되지 않는 영문 식별자
- order: 좌측 목록 정렬 순서
- display_no: 화면에 표시할 두 자리 번호
- title: 프로젝트 이름
- summary: 한 문장 요약
- description: 현재 동작 기준 설명
- entry_file: 홈페이지 코드 미리보기에 사용할 파일
- usage: 사용자 실행 순서
- note: 보안, 데이터와 검토 주의사항

entry_file이 없으면 홈페이지에는 실행 파일을 찾을 수 없다는 안내가 표시됩니다.

## 실행 방식

### 문서형 프로젝트

project.json과 entry_file만 추가하면 설명, 기능, 코드와 실행 방법이 기본 화면에 표시됩니다.

03 API 기반 멀티에이전트가 이 방식이며 실제 실행은 프로젝트 폴더의 CLI에서 수행합니다.

### 홈페이지 실행형 프로젝트

화면 상호작용이 필요한 프로젝트는 main.py에 해당 project id의 렌더 함수와 ASGI API를 연결합니다.

현재 실행형 프로젝트:

- chunking-lab
- chunking-rag-lab
- report-draft

공용 처리 로직은 프로젝트 폴더 또는 루트 모듈에 두되, 별도 웹서버와 중복 포트를 만들지 않습니다.

## 공용 환경변수

프로젝트별 비밀키 파일을 만들지 않고 저장소 루트 .env를 사용합니다.

- Supabase: SUPABASE2_URL, SUPABASE2_SERVICE_ROLE_KEY
- OpenRouter: OPENROUTER_API_KEY, OPENROUTER_BASE_URL
- Ollama: OLLAMA_BASE_URL
- Cohere: COHERE_API_KEY, COHERE_RERANK_MODEL

프로젝트별 선택 환경변수는 해당 README와 루트 .env.example에 함께 기록합니다.

## README 현행화 기준

README에는 최소한 다음 내용을 포함합니다.

1. 현재 상태와 홈페이지 경로
2. 실제 실행 흐름
3. 필요한 환경변수
4. API 또는 CLI 실행 방법
5. 파일 구성
6. 데이터 변경 동작
7. 보안과 검토 주의사항
8. 별도 포트 사용 여부

구현을 바꾸면 project.json 설명과 README를 같은 작업에서 함께 갱신합니다.

## 등록 후 검증

~~~bash
cd /home/ubuntu/apps/myservice
python3 -c "from portfolio_loader import load_projects; print([(p['no'], p['id']) for p in load_projects()])"
python3 -m py_compile main.py portfolio_loader.py
git diff --check
sudo systemctl restart myservice
curl -fsS http://127.0.0.1:8000/health
~~~

홈페이지 확인:

~~~text
https://www.minslab.kr/portfolio
~~~

## 보안 원칙

- API 키, 비밀번호와 service-role 키를 저장소에 커밋하지 않습니다.
- service-role 키는 브라우저 코드에 포함하지 않습니다.
- 외부 API 응답과 스크린샷에서 개인정보와 인증 토큰을 제거합니다.
- 생성형 AI 결과는 검토 전 결과로 취급합니다.
- 실습 테이블과 운영 데이터를 분리합니다.
