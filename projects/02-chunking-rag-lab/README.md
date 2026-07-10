# 02. 청킹실습(과제)

첨부 문서를 최대 3가지 방식으로 청킹하고, 선택한 결과만 임베딩한 뒤 Naive RAG와 Advanced RAG 답변을 비교하는 실행형 포트폴리오 프로젝트입니다.

## 현재 상태

- 홈페이지 통합: 완료
- 공개 화면: https://www.minslab.kr/portfolio?project=chunking-rag-lab
- 별도 웹서버 또는 전용 포트: 없음
- 실행 백엔드: 루트 main.py와 chunking_compare.py
- 저장소: Supabase pgvector 테이블
- 답변 모델: OpenRouter 또는 서버에 설치된 Ollama 모델
- 선택 기능: Cohere reranking

## 전체 실행 순서

1. 문서 내용을 붙여넣거나 파일을 첨부합니다.
2. 고정 길이, 문단 우선 재귀, 문장 윈도우 의미 청킹 중 1~3개를 선택합니다.
3. 1. 청킹 실행으로 방식별 청크, 설명, 장단점을 확인합니다.
4. 2. 임베딩 실행으로 선택한 청킹 결과만 Supabase에 저장합니다.
5. 질문, 모델, RAG 방식, Temperature, Top-K와 reranking 여부를 설정합니다.
6. 3. 질문 실행으로 선택 테이블의 검색 결과와 답변을 비교합니다.

## 지원 문서

화면에서 다음 텍스트 기반 파일을 첨부할 수 있습니다.

- hwpx
- txt, md, csv, json
- html, xml
- py, js, css
- log

hwpx는 ZIP 내부 Contents/section*.xml의 본문 문단만 추출합니다. 전체 입력은 최대 150,000자로 제한되고 방식별 청크는 최대 30개까지 구성됩니다.

## 청킹 전략

### 고정 길이 청킹

일정한 문자 수와 overlap으로 빠르게 분할합니다. 처리 속도와 결과 크기가 일정하지만 문장 경계를 자를 수 있습니다.

### 문단 우선 재귀 청킹

문단과 문장 경계를 우선 보존하면서 긴 단위를 다시 나눕니다. 문맥 보존에 유리하지만 청크 크기가 일정하지 않을 수 있습니다.

### 문장 윈도우 의미 청킹

인접 문장을 겹치는 윈도우로 묶습니다. 주변 의미를 보존하지만 중복 저장량이 늘어날 수 있습니다.

## 임베딩과 Supabase

선택 순서에 따라 다음 테이블을 사용합니다.

| 선택 슬롯 | Supabase 테이블 |
| --- | --- |
| 1 | chucking_test1 |
| 2 | chucking_test2 |
| 3 | chucking_test3 |

기존 오탈자 테이블 chucnkig_test1~3도 자동으로 탐색합니다.

중요: 임베딩 실행은 해당 슬롯 테이블의 기존 행을 모두 삭제한 뒤 현재 청크로 교체합니다. 공동 데이터나 운영 테이블에 연결하지 말고 실습 전용 테이블만 사용해야 합니다.

OpenRouter 임베딩의 기본 모델은 openai/text-embedding-3-small입니다. API 호출에 실패하면 동일 실행 동안 결정적 local-hash-fallback 임베딩으로 전환합니다.

## RAG 방식

### Naive RAG

- 단일 질문 임베딩
- 코사인 유사도 검색
- 선택적 Cohere reranking
- Top-K 문맥으로 답변 생성

### Advanced RAG

- 다중 질의 변형
- 확장 후보 검색
- best-effort Cohere reranking
- 문맥 압축
- 근거 인용을 포함한 답변 생성

Advanced RAG에서 Cohere 호출이 실패하면 기본 유사도 순위로 계속 실행하며 경고를 표시합니다. Naive RAG에서 reranking을 직접 켠 경우 Cohere 오류는 해당 패널 오류로 반환됩니다.

## 환경변수

루트 공용 .env를 사용합니다.

필수 Supabase 설정:

~~~dotenv
SUPABASE2_URL=https://YOUR_PROJECT.supabase.co
SUPABASE2_SERVICE_ROLE_KEY=YOUR_SERVICE_ROLE_KEY
~~~

OpenRouter 임베딩 또는 답변 모델 사용 시:

~~~dotenv
OPENROUTER_API_KEY=YOUR_OPENROUTER_API_KEY
~~~

선택:

~~~dotenv
OPENROUTER_EMBEDDING_MODEL=openai/text-embedding-3-small
OLLAMA_BASE_URL=http://127.0.0.1:11434
COHERE_API_KEY=YOUR_COHERE_API_KEY
COHERE_RERANK_MODEL=rerank-v4.0-fast
~~~

OpenRouter 답변 모델을 사용하지 않고 로컬 Ollama만 사용할 때도 OpenRouter 임베딩 키가 없으면 local-hash-fallback으로 임베딩할 수 있습니다.

## 홈페이지 API

- GET /api/chunking-models
- POST /api/hwpx-extract
- POST /api/chunking-plan
- POST /api/chunking-embed
- POST /api/chunking-compare

## 파일 구성

~~~text
projects/02-chunking-rag-lab/
├── README.md       # 현재 프로젝트 문서
├── project.json    # 홈페이지 메타데이터
└── vsRAG.py        # 공용 chunking_compare 모듈 사용 예시

chunking_compare.py # 청킹, 임베딩, Supabase, RAG 실제 구현
main.py             # 홈페이지 화면과 API 라우팅
supabase_schema.sql # 실습 테이블 참고 스키마
~~~

## 검증과 주의사항

- 임베딩 전 청킹 결과와 선택 슬롯을 반드시 확인합니다.
- 서비스 역할 키는 브라우저에 노출하지 않습니다.
- local-hash-fallback은 기능 검증용이며 상용 임베딩과 품질이 같지 않습니다.
- RAG 점수와 자동 평가 카드는 실습 보조 지표입니다.
- 답변의 사실성과 인용 근거는 원문 청크를 열어 최종 확인합니다.
