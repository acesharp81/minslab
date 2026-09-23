# PoC 09 — ㅁㅁㅈ(뭐먹지?)

AI 대화형 매장 주문 플랫폼의 독립 PoC입니다.

현재 단계는 **팀 공유 준비**입니다. 기술 계획과 홈페이지 적합성은 [docs/PLAN.md](docs/PLAN.md), 팀의 작업 순서와 역할은 [docs/TEAM_EXECUTION_PLAN.md](docs/TEAM_EXECUTION_PLAN.md), 열린 결정은 [docs/DECISIONS.md](docs/DECISIONS.md)에 정리했습니다. 실행 가능한 앱과 `project.json`은 주문·안전·모바일 검증을 통과한 뒤 추가합니다. `project.json`을 먼저 두면 홈페이지의 PoC 목록에 미완성 서비스가 자동 노출됩니다.

예정 경로:

- 공개 앱: `/poc/mwomeokji/`
- 데모 매장: `/poc/mwomeokji/s/demo-store?table=T07&token=...`
- 홈페이지 카드: `/poc?project=mwomeokji`

API 키는 저장소 루트 `.env`의 서버 환경변수를 사용합니다. 이 폴더에 키를 복사하거나 브라우저 공개 변수로 전달하지 않습니다. 앱별 데이터베이스, 세션, 업로드 파일은 독립적으로 둡니다.
