# AIWorks 양식 MCP 정석화 계획

> 기준일: 2026-08-19
> 문서 상태: 실행 기준 / 단계별 진행상태 갱신
> 핵심 원칙: Markdown은 내용 원본이고, 양식 MCP는 표현 구조를 소유하며, KODAK은 HWPX 직렬화만 담당한다.

## 목표 구조

```text
프로젝트 Markdown
→ ReportDocument(AST)
→ 질문·근거·초안 품질 하네스
→ 양식 MCP TemplateSchema 바인딩
→ HWPX 구조 생성
→ KODAK 직렬화·무결성 검사
→ RHWP 정적 편집 세션
```

HWPX에서 수정한 내용은 사용자가 명시적으로 `HWPX → MD 반영`할 때 새 Markdown revision으로 승격한다. MD에서 파생 문서를 갱신할 때는 `MD → HWPX 반영`을 명시적으로 실행하며, 탭 전환 자체는 재생성 조건이 아니다.

## 단계별 계획

| 단계 | 상태 | 산출물 | 완료 조건 |
|---|---|---|---|
| 1. 양식 제작 세션 분리 | 완료 | `template-authoring` RHWP 세션 | 양식 편집이 프로젝트 MD를 만들거나 변경하지 않음 |
| 2. 첨부 양식 기반 등록 샘플 | 완료 | 제목·본문 슬롯이 명시된 HWPX | 첨부 서식 보존, `{{title}}`·`{{content}}` 확인 |
| 3. RHWP 수정·초안 반영 | 완료 | Builder 전용 수정 메뉴와 commit API | RHWP 저장본이 같은 draft의 양식 원본이 됨 |
| 4. 게시 전 구조 검증 | 완료 | `template.structure` 검사 | 신뢰도 검토 필요 또는 필수 슬롯 누락 시 게시 차단 |
| 5. TemplateSchema 보정 UI | 부분 구현 | 자동 제목·본문·목록·표 추론과 RHWP 수정 | 세부 슬롯을 시각적으로 재지정하는 전용 매핑 UI는 후속 |
| 6. 구조 반복자 구현 | 완료 | section/list/table repeater | MD 블록 수에 따라 HWPX 문단·행·셀 실제 복제 |
| 7. 구조 기반 렌더러 | 완료 | ReportDocument→TemplateSchema binder | Markdown 기호 제거, 개조식 계층과 실제 표 렌더링 |
| 8. 파생 산출물 품질 하네스 | 완료 | 실렌더링→재파싱, 제목·본문 1회, 잔여 토큰·표·매핑률 검사 | 실패 양식 커밋·게시 차단 |
| 9. 양방향 의미 동기화 | 부분 구현 | 명시적 MD→HWPX/HWPX→MD와 diverged 상태 | 표 셀 단위 Render Map v2 충돌 UI는 후속 |
| 10. 템플릿 버전·호환성 | 부분 구현 | 원본 SHA·MCP SemVer·실행 Binding | TemplateSchema migration과 호환 범위 선언은 후속 |

## 이번 구현의 사용자 흐름

1. `MCP 만들기`에서 `양식 MCP`를 선택하고 초안을 만든다.
2. 완성 보고서, 빈 양식 또는 예시가 포함된 HWPX를 `양식 원본`으로 첨부한다.
3. `등록 샘플 HWPX`로 자동 변환 결과를 내려받아 확인하거나, `양식 수정 (RHWP로 편집)`을 누른다.
4. `구조 실검증`으로 테스트 ReportDocument의 제목·본문·목록·표 렌더링과 재파싱 결과를 확인한다.
5. RHWP에서 고정 문구·글꼴·문단·표·여백을 수정한다.
6. `{{title}}`과 `{{content}}` 또는 `{{body}}` 문자열은 유지한다.
7. `양식 수정 완료·초안 반영`을 눌러 RHWP 저장본을 양식 원본으로 반영한다.
8. 샌드박스 검증을 다시 실행한 뒤 게시·설치한다.

## 현재 구조 계약

현재 등록 가능한 최소 계약은 다음과 같다.

```yaml
templateSchema:
  contractVersion: "1.0"
  required:
    title: true
    body: true
    bodySlot: content
  slots:
    - slot: title
      token: "{{title}}"
    - slot: content
      token: "{{content}}"
  repeaters:
    sections: true
    lists: true  # 원본에 목록 prototype이 있을 때
    tables: true # 원본에 표 prototype이 있을 때
```

반복자 값은 원본 HWPX에서 실제 prototype을 찾은 경우에만 `true`다. 표가 없는 양식은 표 블록을 문단으로 강등하고, 표가 있는 양식은 행·셀을 실제 복제한다.

## 게시 차단 규칙

다음 상태의 양식 MCP는 게시할 수 없다.

- 양식 원본이 없거나 HWPX가 아닌 경우
- 활성 양식 원본이 둘 이상인 경우
- 자동 분석 신뢰도가 0.6 미만이거나 `reviewRequired=true`인 경우
- `{{title}}` 누락
- `{{content}}`와 `{{body}}`가 모두 누락
- 양식 원본을 게시 패키지에 포함하지 않은 경우
- 파일 SHA-256 또는 Manifest 참조가 일치하지 않는 경우

## 구조 렌더러 완료 조건

표와 개조식 보고서까지 정식 지원하려면 다음 검사를 모두 통과해야 한다.

- ReportDocument 블록 매핑률 80% 이상
- 제목과 필수 메타 슬롯 100% 매핑
- Markdown 표 구분자(`| --- |`) 잔존 0건
- 양식 예시 문구 잔존 0건
- MD 표가 있으면 HWPX에 실제 표·행·셀이 존재
- MD와 HWPX의 절 순서 및 제목 일치
- HWPX→MD 역변환 시 핵심 블록 손실 0건
- 탭 이동만으로 HWPX가 재생성되지 않음

## 책임 경계

| 구성요소 | 책임 |
|---|---|
| 프로젝트 Markdown | 내용의 단일 원본과 revision |
| ReportDocument | 제목·절·문단·목록·표의 의미 구조 |
| 양식 MCP | 슬롯, 반복 영역, 스타일 prototype, 고정 문구 |
| KODAK | HWPX 패키징·직렬화·파일 무결성 |
| RHWP | 파생 HWPX의 정적 열기와 직접 편집 |
| 품질 하네스 | 질문 일치, 근거, 구조 매핑과 잔여 토큰 검사 |
