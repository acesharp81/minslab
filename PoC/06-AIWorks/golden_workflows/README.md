# Golden Workflows

Phase 1의 문서 계약과 Phase 2의 비-KORDOC 왕복 편집을 한 개의 재현 가능한 시나리오로 고정한다. 첫 시나리오는
`budget_business_review`이며 외부 모델·네트워크·운영 DB를 사용하지 않는다.

```bash
python3 PoC/06-AIWorks/golden_workflows/runner.py
```

기본 실행은 임시 SQLite DB를 만들고 종료 시 제거한다. 결과를 조사해야 할 때만 운영 DB와 다른
명시적 경로를 지정한다.

```bash
python3 PoC/06-AIWorks/golden_workflows/runner.py --db /tmp/ai-work-hub-golden.sqlite3
```

검증 범위는 자료 검색, 설명 가능한 계획, 단일 사용 승인, 로컬 실행, 근거가 포함된 Markdown r1,
HWPX 구조·Render Map·계보, HWPX 사용자 수정의 `diverged` 상태, 명시적 역반영으로 생성되는
Markdown r2, 전체 감사 해시체인이다. Fixture는 익명화된 합성 자료이며 실제 기관정보나 개인정보를
포함하지 않는다.
