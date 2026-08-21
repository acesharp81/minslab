# Architecture

## 처리 흐름

```text
Official Source
  → Raw Collector
  → Raw Object + Ingestion Manifest
  → Source Adapter / DTO
  → Normalizer
  → Canonical PostgreSQL Model
  → Reconciliation / Versioning
  → Structured Search + Full Text Search
  → AI Enrichment
  → REST API / Web UI
```

## 현재 구현

- 독립 FastAPI 진입점
- health, metadata, 공식 오늘 일정 API
- provenance 링크가 있는 오늘 일정 화면
- 독립 Docker Compose PostgreSQL 구성
- 서로 독립적인 상태 enum과 단위 테스트
- 공식 API 8종의 검증된 contract와 일정·위원회 회의록·회의별 의안 adapter
- SHA-256 raw 원문·manifest 보존
- SourceDocument/Version, ScheduleEntry, Meeting migration과 idempotent repository
- 행안위·예결위·법사위 제품 scope 판정

- `CONF_ID` 기반 회의록·의안 연결과 공식 회의 목록 API
- `BILL_ID`별 공식 상세 버전 적재와 대상 회의 의안 검색 API
## 아직 구현하지 않음

- 의원·표결 source의 수집·정규화 adapter
- 일정과 회의록 사이의 과거 데이터 reconciliation 확대
- 구조화 검색과 Full Text Search
- LLM provider와 AI annotation
- 홈페이지 runtime 연결

## 경계

NationalAssembly는 부모 저장소에서 import하지 않습니다. 홈페이지는 향후 독립 서비스 URL을 연결할 수 있지만, 프로젝트 자체의 실행에는 필요하지 않습니다.
## 국무회의 확장 흐름

    청와대·정책브리핑·국무조정실 공식 문서
      → HTML/PDF/HWP Raw Collector
      → SourceDocumentVersion
      → ExecutiveMeeting / SpeechSegment
      → PolicyTopic / Ministry 연결
      → 검토된 AI Annotation
      → 부처·주제 필터 API
      → 국무회의 / 국회 / 연계 보기

국무회의와 국회는 같은 PostgreSQL과 worker를 사용하되 source adapter와 canonical entity를 분리합니다. 기관 간 연결은 CrossInstitutionLink에서 공식·규칙·AI 후보 상태를 구분합니다.

상세 단계와 완료 기준은 EXECUTION_PLAN.md를 따릅니다.
