# NationalAssembly 개발 규칙

이 파일은 Codex, Continue 및 다른 개발 Agent가 `PoC/07-NationalAssembly`를 독립적으로 수정할 때 적용합니다.

## 절대 원칙

- 검증되지 않은 국회 API endpoint, 응답 필드 또는 갱신주기를 추측해 구현하지 않는다.
- 공식 자료와 AI 생성값을 같은 필드 또는 테이블에 저장하지 않는다.
- AI 생성값을 `OFFICIAL`로 표시하지 않는다.
- 사용자에게 노출되는 구조화 정보는 `SourceDocumentVersion`과 원문 위치로 추적할 수 있어야 한다.
- 원본 응답과 이전 버전을 덮어쓰지 않는다.
- 외부 API 장애 시 parser와 normalizer 테스트가 가능하도록 fixture를 유지한다.
- 부모 저장소의 모듈, `.env`, 가상환경 또는 다른 PoC를 runtime dependency로 사용하지 않는다.

## 상태 모델

다음 세 축을 혼합하지 않는다.

- 회의 생명주기: `SCHEDULED`, `LIVE`, `ENDED`, `CANCELED`
- 자료 권위 상태: `LIVE`, `PROVISIONAL`, `OFFICIAL`
- 출처 매칭 상태: `MATCHED`, `UNRESOLVED`, `CONFLICT`

## 수집 규칙

1. 응답 바이트와 수집 metadata를 먼저 저장한다.
2. SHA-256 `content_hash`로 중복을 판별한다.
3. Source Adapter가 응답을 Source DTO로 변환한다.
4. Normalizer만 canonical model을 생성한다.
5. 정규화 결과는 source version과 parser version을 기록한다.
6. 불확실한 회의 매칭은 강제하지 않는다.

## 코드와 테스트

- Python은 타입 힌트를 사용하고 외부 I/O와 순수 변환 로직을 분리한다.
- API key, token, password는 로그에 남기지 않는다.
- adapter와 normalizer는 실제 네트워크 없이 unit test가 가능해야 한다.
- API 추가 시 API 테스트, schema 변경 시 migration과 `DATA_MODEL.md`를 함께 갱신한다.
- 데이터 출처 변경 시 `DATA_SOURCES.md`, 기술 결정 시 `DECISIONS.md`, 사용자 영향 변경 시 `CHANGELOG.md`를 갱신한다.

## POC 과설계 방지

PostgreSQL, 단일 API, 단일 worker로 먼저 검증합니다. 명확한 측정 근거가 생기기 전에는 Kafka, Airflow, Kubernetes, Neo4j, OpenSearch, 별도 Vector DB 또는 microservice를 추가하지 않습니다.
