# 2026-10-30 CPU·로딩 및 AI 역할 화면 개선

## 관측과 조치

- 서버: 4 vCPU, RAM 약 16GB. 초기 컨테이너 표본에서 PoC7 PostgreSQL CPU 113.7~171.94%(100%=1코어). 가용 RAM 약 9GB이며 vmstat의 현재 swap in/out은 0이었다. swap에 남아 있는 2.5GB만으로 메모리 고갈로 판정하지 않았다.
- 알림 워커가 처리 대기 없음 확인 시 109만여 자막 revision을 반복 스캔했다. `EXISTS(event_cursor > cutoff)`를 인덱스 `MAX(event_cursor)`와 워커 커서 비교로 바꾸었다. 빈 데이터·없는 워커 상태·커서 간격의 기존 결과를 7개 임시 테이블 PostgreSQL 시험으로 확인했다.
- 기존 대기 확인 EXPLAIN ANALYZE 501.972ms → 동등한 인덱스 조회 0.073ms. 다른 반복 측정에서도 기존 265~402ms, 개선 0.05~0.14ms. 모델 호출이나 업무 데이터 수정 없는 읽기 시험이다.
- 종료 방송 경계는 기존 판단을 유지하며 covering index 두 개를 CONCURRENTLY 생성했다. 대표 두 방송: 120.253/114.661ms → 17.664/13.801ms. 신규 인덱스 두 개의 indisvalid=true 확인 후 migration 0062 이력 기록.
- 처음 배포 시 워커의 실제 Python 경로가 `/app/backend/app`임을 확인하여 배포 경로를 바로잡았다. 운영 모듈에 새 함수 존재 확인 및 최종 쿼리 표본에서 기존 대기 EXISTS 전체 스캔이 없음을 확인했다.
- 수정 후 5회 컨테이너 표본의 PoC7 DB는 27.52~83.24%, 해당 표본 구간 호스트 전체 CPU busy 33.4%. 동시 요약·보고서 작업이 있어 유휴 상태는 아니며, 이 수치를 향후 부하 상한으로 해석하지 않는다.
- HOME AI_PUBLICATION_ANALYSIS/DISCOVERY 감사 이력과 ai_publication_analysis 판본만으로 정책 조회를 재생성하지 않게 했다. 원천·연결·승인 변경은 계속 즉시 무효화한다. 공통 사용량 API는 초기 측정 약 53~125ms로, 이번 지연의 주된 원인으로 확인되지 않았다.
- 정책 조회 초기/미스 관측 1.8~8초. 반영 후 warm 직접 API 측정: policy-monitor 32ms, delivery/view 81ms. 재시작 직후 cold 정책 계산은 약 2~6초 관측되어 최초 계산 비용은 남는다. Cold/warm을 같은 조건의 성능 향상 수치로 혼용하지 않는다.

## 수집 실행 상태

최신 Solar 실행 225196d5-df82-4f3f-8649-3cc5a17b2bd9: PARTIAL, 20건 처리, 1건 원문 처리 실패, 1곳 목록 탐색 실패, 53,544 토큰, 예약/미확정 0. 100%는 처리 진행률이며 전부 성공을 뜻하지 않는다.

원문 경로에 한글이 있으면 http.client 요청에서 UnicodeEncodeError가 발생했다. HTTP 전송 경로만 percent encoding하여 저장 URL·중복 식별을 유지했다. 실제 재확인에서는 인코딩 오류 없이 응답을 받았으나 본문 부족/접근 제한 상태라 해당 원문은 아직 확인이 필요하다. 국토교통부 목록 탐색 실패도 해결됐다고 처리하지 않았으며, 기존 PARTIAL 이력을 덮어쓰지 않았다. 재검증에 유료 모델 호출은 하지 않았다.

## 화면과 운영 역할

- 사용량: 잔여량/한도·잔여율 표시. CSP가 HTML 인라인 너비를 차단하던 문제를 신뢰된 스크립트의 DOM 속성 설정으로 수정. CSP 자체를 완화하지 않음.
- 실제 값 약 78.4/62.7/4.1/99.7% 및 시험용 0/50/100%·미확인의 화면 비율 확인. 진행 바도 같은 문제 수정.
- 수집 AI는 좌측, 업무 담당자 AI 설계안은 우측. 미가동 기능을 작동 중으로 표시하지 않음. 수집 예약은 사용자 요청에 따라 07:00, 기존 Solar·활성·한도 설정 유지. 업무 담당자 AI 08:00은 설계 목표이며 스케줄러 없음.
- 데스크톱 좌우 배치, 390px 모바일 세로 배치 및 가로 넘침 없음. 브라우저 JS/CSP 오류 없음.
- HTML/CSS/JS만 hot copy하여 재계산 캐시를 유지했고 정적 수정 포함 재배포 이미지도 빌드했다. 운영 중 컨테이너의 원본 image 태그와 패치 이미지 태그는 manifest로 구분했다.

## 검증

- HOME 수집·공통 예산·캐시: 50 passed.
- PoC7 대기 조회·알림·lifecycle: 52 passed, 15 기존 lifecycle DB 통합 테스트는 별도 WATCH_TEST_DATABASE_URL 미지정으로 skipped. 새 대기 조회 PostgreSQL 시험 7개는 실제 임시 테이블로 실행했다.
- API·AI worker healthy, 알림 worker running, 운영 import 경로와 함수 존재 확인.
- 데이터 승인·실적·기존 연결을 변경하지 않음. 운영 설정 변경은 수집 예약 시각만 08→07시.

원시 측정: `query-plans-before.json`, `query-plans-after.json`, `api-before.json`, `browser-before.json`, `browser-after-cold.json`, `server-after.json`, `db-load-final-summary.jsonl`, `roles-quota-browser.json`. 배포 manifest와 화면 이미지를 같은 폴더에 보관한다.
