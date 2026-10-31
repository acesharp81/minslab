# 주제별 보고서 모델 점검 — 2026-10-31 13:49 KST

## 확인 결과

| 모델 | 계정 모델 조회 | 현재 주제별 보고서 배정 | 적합한 역할에 대한 판단 |
|---|---|---|---|
| GPT-5.4 mini | HTTP 200 | 배정 없음 | 근거별 소규모 요약·빠진 논의 보완 후보 |
| GPT-5.4 | HTTP 200 | 첫 번째 후보 | 전체 정책 분야 종합·완결 보고서 |
| GPT-6.1 Terra | HTTP 200 | 통신/JSON 처리 실패 시 다음 후보 | 반복 실패/복잡한 종합 보완 후보 |

`/models/{model}` 조회는 계정의 모델 접근을 확인한다. 이 점검에서는 생성 호출·원문 재전송을 하지 않았으며 실제 주제별 보고서의 모델 간 품질/속도 비교를 수행한 것은 아니다.

공식 문서상 GPT-5.4 mini와 GPT-5.4는 Chat Completions/Responses 및 Structured Outputs를 지원하므로 현재 JSON 보고서 계약으로 구현 가능하다.

- [GPT-5.4 mini 공식 문서](https://developers.openai.com/api/docs/models/gpt-5.4-mini): 400K context, 최대 입력 272K, 최대 출력 128K.
- [GPT-5.4 공식 문서](https://developers.openai.com/api/docs/models/gpt-5.4): 1.05M context, 최대 출력 128K.

## 실제 운영 코드와 장부

- `MODEL_WORKLOAD_GROUPS_ENABLED=true`, `TOPIC_REPORTS_ENABLED=true`.
- `GroupedTopicReportClient` → `WorkloadBriefClient` → integration pool: `gpt-5.4`, `gpt-6.1-terra`.
- Mini는 general pool에만 있다. 현재 wrapper는 최초 작성·빠진 근거 보완·전체 요약 재작성을 모두 `topic_report`로 전달해 단계별 Mini 배정이 불가능하다.
- 조회 시 서비스 공용 장부 잔여: Mini 10,000,000 tokens, main 1,000,000 tokens, Terra 로컬 배정 잔액 $2.022042. 활성 cooldown·예약/미확정 daily token 없음. 이 수치는 연결된 서비스 장부이며 OpenAI 조직 전체의 청구 잔액 API 값이 아니다.
- 주제별 보고서 대기/처리 중 항목 없음. 최근 30일 저장 8건은 구형 Dots 경로: READY 5, 품질 검증 실패 2(근거 누락/한국어 문법), OpenRouter 한도 도달 1. GPT 경로 전환 후 주제별 보고서 생성 실적은 아직 없다.

## 발견한 보완 지점

1. **단계 이름 보존**: `gukjeongbomi_topic_report`, `topic_report_missing_discussions`, `topic_report_complete_scope_summary`를 유지해야 소규모 보완에 Mini를 배정할 수 있다.
2. **품질 실패의 대체 경로**: 현재 transport 오류/JSON 파싱 실패는 Terra로 넘기지만, 응답 이후 발생하는 근거 누락·언어·문법·출력 잘림 검증 실패에는 `on_quality_failure`가 연결되지 않는다. 단순히 5.4→Terra 후보가 있다는 이유로 모든 품질 실패가 재생성된다고 설명하면 안 된다.
3. **긴 결과의 출력 상한**: 현재 서비스는 최초 보고서 8,000 completion tokens, 입력 근거 60,000 characters 제한이다. 모델 자체 최대치와 다르다. 전체 입력을 조용히 자르지는 않고 초과 시 오류를 반환한다. 긴 보고서는 단계별 분할·보완 및 출력 예산을 실제 검증해야 한다.
4. **구형 모델 표시**: 생성 요청 API는 아직 대기 항목에 OpenRouter/Dots 모델명을 기록하고, 워커가 실제 실행할 때 OpenAI/5.4로 바꾼다. 최종 실행 모델과 생성 대기 표시를 일치시키는 보완이 필요하다.

## 권장 배정

- 근거별 보완(현재 8개씩): GPT-5.4 mini → 검증 실패 시 GPT-5.4.
- 최초 전체 작성·최종 요약/정책 시사점: GPT-5.4.
- 5.4의 반복 품질 실패나 복잡한 종합: GPT-6.1 Terra, 기존 월 배정 한도 안에서만.
- 근거 누락·수치·언어 검증, 출처 보존 및 무료 그룹/크레딧 분리는 그대로 유지한다. 모델 접근 확인과 품질 검증을 구분하고, 실제 동일 입력 비교 후 Mini 적용 범위를 결정한다.

이번 추가 요청은 점검 범위로 처리했으며, 기존 운영 모델 우선순위는 변경하지 않았다.

## 검증

모델 그룹·주제별 보고서·누락 근거 보완·완결성 관련 테스트 50개 통과. 이는 코드 경로 회귀 검증이며 실제 모델 응답 품질 평가와 구분한다.
