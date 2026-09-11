# 국정ON 계정 동기화·주제별 보고서 구축 기록

작성일: 2026-09-01
상태: 구현 및 단위 검증 완료

## 목표

- 알람 설정과 저장 결과를 같은 Kakao 사용자가 여러 PC에서 이어 본다.
- 사용자가 소관 부처·주제·기간을 지정한 때에만 저장 자료를 검색하고 완결형 보고서를 작성한다.
- 무료 운영, 최소 비밀 노출, 근거 추적과 기존 회의 파이프라인의 권위 원칙을 유지한다.

## 최종 구조

1. 익명 사용자는 만료 가능한 PoC7 보안 세션으로 시작한다.
2. Kakao 연결 시 Kakao 사용자 ID의 기존 subscriber를 canonical 계정으로 선택한다.
3. 새 PC에서 만든 규칙만 중복 없이 병합하고 기존 규칙·계정·토큰은 자동 삭제하지 않는다.
4. 관련 자료 미리보기는 저장된 회의 브리프와 공식 통합본을 구조화 의미·키워드로 검색한다. LLM 호출은 없다.
5. 사용자가 작성 버튼을 누르면 선별 근거 snapshot을 DB 큐에 저장한다.
6. 전용 worker가 OpenRouter를 한 번 호출하고 JSON schema와 evidence ID를 검증한다.
7. 완료 결과는 query·evidence·provider·model·prompt version으로 캐시한다. 다시 보기·다운로드·인쇄는 외부 호출을 만들지 않는다.

## 무료 운영 한도

| 경계 | 한도 | 설명 |
|---|---:|---|
| 사용자별 주제 보고서 | 10회/UTC 일 | 익명 남용과 단일 사용자 독점을 방지 |
| 주제 보고서 전체 | 100회/UTC 일 | PoC7의 다른 OpenRouter 기능에 400회 이상 여유 보존 |
| PoC7 OpenRouter 전체 | 500회/UTC 일 | 알람 요약과 주제 보고서가 공유하는 최종 상한 |
| 검색·목록·상세·다운로드·인쇄 | 0회 | PostgreSQL 저장 자료만 사용 |

무료 모델이나 공급자 조건이 바뀌면 `TOPIC_REPORT_MODEL`만 교체한다. strict schema와 data collection 거부를 만족하는 공급자가 없으면 유료 또는 비보장 경로로 우회하지 않고 실패로 남긴다.

## 보안 결정

- OpenRouter 키는 topic-report worker에만 전달한다. API와 브라우저에는 전달하지 않는다.
- Kakao access/refresh token은 PoC7 전용 Fernet 키로 암호화한다.
- 브라우저 세션 원문은 Secure HttpOnly SameSite=Lax 경로 제한 cookie에만 두고 DB에는 SHA-256 hash만 저장한다.
- 변경 API는 다른 Origin 요청을 거부한다.
- 모든 응답에 CSP, HSTS, Referrer-Policy, Permissions-Policy와 nosniff를 적용한다.
- LLM payload에는 공개 회의 근거만 넣고 Kakao ID, 브라우저 세션, API token은 넣지 않는다. 이메일·전화번호·주민번호 패턴은 전송 전에 제거한다.
- OpenRouter 요청은 공용 gateway에서 공개 회의 근거만 허용하고 PII 패턴을 제거한다. 2026-09-09 명시 승인에 따라 공개 데이터에만 data collection 허용과 승인된 무료 모델 fallback을 적용하며 ZDR은 강제하지 않는다.

## 구현 단계와 상태

- [x] 1단계 — `watch_web_sessions`, `topic_reports`, 사용자/전역 사용량 장부 migration
- [x] 2단계 — 기존 로컬 token의 cookie 승격, 현재/전체 기기 session 폐기
- [x] 3단계 — Kakao canonical 계정 선택, 트랜잭션 잠금, 비파괴 규칙 병합
- [x] 4단계 — 회의 브리프·공식 통합본의 로컬 의미구조+키워드 검색
- [x] 5단계 — OpenRouter strict JSON 생성, 개인정보 제거와 근거 ID 검증
- [x] 6단계 — 10/100/500 삼중 한도, 동일 결과 cache와 실패 재시도
- [x] 7단계 — 상위 메뉴, 검색 미리보기, 작성 진행, 내역, Markdown, 인쇄 UI
- [x] 8단계 — 전용 worker·allowlist 배포, 운영 환경 설정과 문서
- [x] 9단계 — Python·JavaScript 문법, 보안 요청 계약, 기존 알람 회귀 테스트

## 다음 운영 확인

- 실제 Kakao 계정으로 PC 두 대를 연결해 동일 규칙·알림·보고서가 보이는지 확인한다.
- 실제 수집 자료로 1건을 작성해 근거 링크, 담당 부처, 기간 흐름과 Markdown을 확인한다.
- OpenRouter dashboard와 DB 일일 장부의 요청 수가 1건 증가하고 새로고침 때 증가하지 않는지 확인한다.
- 무료 모델 변경 공지 시 모델 교체 후 strict schema·공개 데이터 경계·ZDR 가용성을 다시 확인한다. ZDR 지원 무료 endpoint가 생기면 우선 적용한다.
