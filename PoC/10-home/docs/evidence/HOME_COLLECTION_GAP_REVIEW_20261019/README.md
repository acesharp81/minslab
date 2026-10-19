# 2026-10-19 수집 갭 재검토 근거

운영 API 읽기 전용 조회, 두 개의 DB 읽기 전용 트랜잭션, 공식 웹·PDF 조회 결과를 보존한다. 담당자 승인·수집 원장·운영 코드를 변경하지 않았다. 파일은 프로젝트 내부 검토용이며 공개 웹에 게시하지 않았다.

- `sources.json`, `coverage.json`, `jobs.json`: 현재 원천·조회 범위·최근 작업. `capture.json`에 시각과 경로 기록. 최초 서울 연간 API 요청의 URL 인코딩 오류는 `external_fetch.json`의 성공 재요청으로 보완했다.
- `annual.json`: 서울 연간 조회 화면의 원자료. 2026 인허가 미확보 상태 확인.
- `database.json`: `capture_readonly.py`의 REPEATABLE READ + READ ONLY 결과. 현재 통계 72행, 관리 원천 사업 323행, 원천별 자료 유형 건수 및 특정 사업 근거.
- `construction.json`: `capture_construction_readonly.py`의 별도 읽기 전용 결과. 두 인허가 원장의 2026년 착공일 보유 행과 두 종류의 사업 연결 여부. 이전 DB 스냅샷과 같은 시점으로 취급하지 않는다.
- `official_august.pdf`, `.txt`: e-나라지표가 게시한 국토부 2026년 8월 주택통계. `pdf_fetch.json`에 URL/시각. PDF 7~10쪽의 표를 `official_august_transcription.json`에 전사. 착공 8쪽은 렌더링 이미지로 추가 확인.
- `period_starts.json`, `period_permits.json`: 공식 API의 제공기간 직접 응답.
- `index_permits.html`, `.txt`: 공식 첨부 목록과 다운로드 경로 근거.
- `blackstone11_*`, `silim2_*`: 서울 공식 사업개요·추진경과 직접 응답. `seoul_fetch.json`에 URL/응답 크기 기록.
- `external_fetch.json`: 외부 조회 성공과 실패를 함께 기록.

재현 스크립트: `scripts/audit_collection_gap.py`. 문서의 `.manifest.json`은 각 파일과 관련 코드의 SHA-256을 보존한다. DB 캡처 스크립트는 기존 컨테이너 설정을 통해 연결하며 자격증명 값을 출력하지 않는다.
