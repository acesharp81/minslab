# 2026-10-16 공식 발표 대조 근거

원문·운영 API·읽기 전용 DB의 동결 자료입니다. 공개 웹 게시 대상이 아닙니다.

- `capture.json`: API별 읽기 시작·완료시각과 응답 크기
- `official_fetch.json`: 공식 원문 URL·HTTP 상태
- `briefing_official.html`, `public_housing_official.html`: 직접 확보한 공식 원문
- `*_official.txt`: 분석에 사용한 본문 추출
- `selected_database.json.gz`: REPEATABLE READ / READ ONLY로 조회한 선택 종류·사업명 관련 원천
- `capture_database.py`: 해당 읽기 전용 DB 조회 코드. 기관 수집·관계 갱신을 호출하지 않음
- `compression.json`: 큰 JSON의 압축 전후 크기·해시. 압축은 저장 방식이며 내용은 동일

분석 재현: `python3 scripts/audit_official_comparison.py`. 동결 API 응답과 DB 조회는 각각 확보 시각이 다르므로 하나의 스냅샷으로 간주하지 않습니다. 사업명이 있다고 해당 발표의 단계·물량이 검증된 것은 아닙니다.
