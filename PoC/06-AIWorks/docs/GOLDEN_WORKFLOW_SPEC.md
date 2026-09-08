# Golden Workflow Specification

## 목적

기능의 존재가 아니라 대표 업무가 근거·승인·문서·감사 불변조건을 지키며 완료되는지를 검증한다.
첫 업무는 기존 예산 Acceptance와 프로젝트 자료 RAG를 재사용할 수 있는 예산·사업 검토 보고서다.

## 시나리오

```text
익명화 사업자료 등록
 -> 근거 검색
 -> Capability DAG 계획
 -> 일회용 승인
 -> 외부 전송 없는 보고서 실행
 -> Markdown r1
 -> HWPX + Render Map + source revision
 -> HWPX 사용자 수정
 -> diverged
 -> 명시적 HWPX -> MD 반영
 -> Markdown r2
 -> 감사 해시체인 검증
```

실행 가능한 원본은 `golden_workflows/budget_business_review/workflow.json`이고 계약은
`contracts/golden-workflow.schema.json`이다.

## Phase 1 하드 게이트

- 선택 자료의 기대 예산·집행률·개선방안·일정이 검색과 Markdown/HWPX에 보존됨
- 외부 전송 없음
- 고정 버전 Project Source·Quality·HWPX Capability가 계획에 존재함
- Task 계약과 Capability DAG가 유효함
- Markdown r1과 source revision이 연결된 HWPX `synced` 산출물이 생성됨
- HWPX 변경이 자동으로 MD를 덮지 않고 `diverged`가 됨
- 명시적 역반영 후 Markdown r2가 생성됨
- 필수 감사 이벤트와 SHA-256 해시체인이 유효함

## 알려진 범위

이 시나리오는 합성 텍스트와 내장 HWPX renderer의 의미 보존을 검증한다. 기관별 복잡한 결재표,
글상자, 머리말·꼬리말, 이미지 배경, Windows 네이티브 RHWP 레이아웃은 Phase 2 품질 세트로 확장한다.
