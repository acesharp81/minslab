# 01. 청킹 실습

Supabase의 일반 청킹 테이블과 전처리 청킹 테이블을 같은 질문으로 조회하고, 검색 결과와 LLM 답변 차이를 나란히 비교하는 포트폴리오 실습입니다.

## 현재 상태

- 홈페이지 통합: 완료
- 공개 화면: https://www.minslab.kr/portfolio?project=chunking-lab
- 별도 웹서버 또는 전용 포트: 없음
- 실행 백엔드: 루트 main.py와 chunking_compare.py
- 데이터 저장소: Supabase documents, documents_test
- 답변 모델: OpenRouter 또는 서버에 설치된 Ollama 모델

이 폴더의 vsRAG.py는 초기 설계 스케치입니다. 현재 홈페이지에서 실제 실행되는 비교 로직은 저장소 루트의 chunking_compare.py에 구현되어 있습니다.

## 비교 흐름

1. 사용자가 질문과 답변 모델을 선택합니다.
2. 백엔드가 documents와 documents_test에서 각각 최대 50건을 읽습니다.
3. 질문과 문서의 토큰 중첩을 기준으로 점수를 계산합니다.
4. 각 테이블의 상위 5건을 문맥으로 구성합니다.
5. 선택한 OpenRouter 또는 Ollama 모델이 검색 문맥에 근거한 답변을 생성합니다.
6. 총 문서 수, 상위 결과 수, 최고·평균 점수, 답변과 검색 미리보기를 좌우로 표시합니다.

현재 01 실습은 pgvector 유사도 검색이 아니라 기존 두 테이블의 키워드 중첩 점수를 비교하는 레거시 실험 화면입니다. 벡터 임베딩과 Naive/Advanced RAG 비교는 02 프로젝트에서 수행합니다.

## 화면 사용법

1. 포트폴리오에서 01. 청킹 실습을 선택합니다.
2. 비교할 질문을 입력합니다.
3. 자동 조회된 로컬 Ollama 모델 또는 OpenRouter 모델을 선택합니다.
4. 비교 실행을 누릅니다.
5. 일반 청킹과 전처리 청킹의 검색 점수, 근거 문서와 답변을 비교합니다.

## 환경변수

설정은 프로젝트별 파일이 아니라 저장소 루트의 공용 .env를 사용합니다.

필수 Supabase 설정:

~~~dotenv
SUPABASE2_URL=https://YOUR_PROJECT.supabase.co
SUPABASE2_SERVICE_ROLE_KEY=YOUR_SERVICE_ROLE_KEY
~~~

OpenRouter 모델 사용 시:

~~~dotenv
OPENROUTER_API_KEY=YOUR_OPENROUTER_API_KEY
CHUNKING_OPENROUTER_MODEL=openai/gpt-4o-mini
~~~

로컬 모델 사용 시 선택 설정:

~~~dotenv
OLLAMA_BASE_URL=http://127.0.0.1:11434
~~~

SUPABASE2_SERVICE_ROLE_KEY는 브라우저로 전달하지 않으며 Python 백엔드에서만 사용합니다.

## 홈페이지 API

- GET /api/chunking-models
- POST /api/chunking-legacy-compare

예시 요청:

~~~json
{
  "prompt": "민원 처리 절차의 핵심 내용을 알려줘",
  "model": "openrouter:openai/gpt-4o-mini"
}
~~~

## 파일 구성

~~~text
projects/01-chunking-lab/
├── README.md       # 현재 프로젝트 문서
├── project.json    # 홈페이지 메타데이터
└── vsRAG.py        # 초기 청킹 비교 인터페이스 스케치

chunking_compare.py # 실제 Supabase 조회와 LLM 비교 로직
main.py             # 홈페이지 화면과 API 라우팅
~~~

## 검증과 주의사항

- 검색 결과가 비어 있으면 Supabase의 documents, documents_test 테이블과 권한을 확인합니다.
- OpenRouter 선택 시 API 키와 네트워크 연결이 필요합니다.
- Ollama 선택 시 모델이 서버에 설치되어 있어야 합니다.
- 비교 점수는 실습용 휴리스틱이며 답변 품질의 절대 평가값이 아닙니다.
- 실제 업무 판단에는 검색 원문과 생성 답변을 사람이 다시 확인해야 합니다.
