# AIWorks 프로젝트·문서·최종 산출물 모델

기준일: 2026-08-28
적용 버전: AIWorks 0.30.x

## 1. 도메인 경계

```text
프로젝트
├─ 프로젝트 메타정보 (1:N)
└─ 기본 문서/Markdown (1:N)
   ├─ Markdown revision (1:N)
   ├─ 형식별 편집 작업본 (0:N)
   └─ 최종 산출물 (0:N, 프로젝트 자산 아님)

양식 MCP ── 렌더링 시 참조 ──> 기본 문서 + 프로젝트 메타정보
```

프로젝트가 소유하는 업무 데이터는 프로젝트 메타정보와 여러 기본 문서다. 문서의 내용 원본은 Markdown revision이다.

HWPX 등 형식별 작업본은 MD↔HWPX 편집 동기화를 위한 문서 하위 상태다. 프로젝트 목록, 프로젝트 집계, 프로젝트 백업에는 포함하지 않는다.

최종 산출물은 특정 Markdown revision과 특정 양식을 결합한 불변 파일이다. 원본 문서를 추적하기 위해 `document_id`와 `source_version_id`를 기록하지만 프로젝트 자산으로 등록하거나 프로젝트 Artifact로 복제하지 않는다.

## 2. 저장 규칙

| 구분 | 저장소 | 갱신 방식 | 프로젝트 백업 |
| --- | --- | --- | --- |
| 프로젝트 메타정보 | `project_facts`, `project_fact_values` | 시점/상태 이력 | 포함 |
| 기본 문서 | `project_markdown_documents` | 문서 단위 | 포함 |
| 문서 내용 | `project_markdown_versions` | revision 추가 | 포함 |
| 형식별 작업본 | `project_document_artifacts` | 문서+형식별 갱신 | 제외 |
| 최종 산출물 | `document_final_outputs` | 생성할 때마다 추가, 불변 | 제외 |
| 양식 | MCP 패키지/양식 저장소 | 버전 관리 | 참조만 기록 |

## 3. 생성 흐름

1. 사용자가 프로젝트와 기본 문서를 선택한다.
2. 의도 분석 및 데이터 MCP가 프로젝트 메타정보와 필요한 외부 데이터를 조회한다.
3. 보고서 MCP가 Markdown revision을 생성하거나 갱신한다.
4. 양식 MCP가 요청한 양식 버전을 선택한다.
5. 형식 어댑터가 `Markdown revision + 양식`을 HWPX 등으로 렌더링한다.
6. RHWP에서 계속 편집할 수 있도록 형식별 작업본을 갱신한다.
7. 같은 렌더링 결과를 `document_final_outputs`에 새 최종 산출물로 추가한다.
8. 최종 산출물은 문서 작업대의 `최종 산출물` 탭에서 개별 다운로드한다.

## 4. API 경계

- `GET /projects`: 문서 수와 프로젝트 메타정보 수만 반환한다.
- `GET /projects/{projectId}/workspace`: 프로젝트, 기본 문서, 프로젝트 메타정보, 마지막 작업 상태만 반환한다.
- `GET /projects/{projectId}/backup`: 프로젝트 메타정보와 Markdown 문서/revision만 내보낸다.
- `GET /projects/{projectId}/documents/{documentId}/workbench`: 문서 편집 작업본과 해당 문서의 최종 산출물 목록을 반환한다.
- `GET /projects/{projectId}/documents/{documentId}/outputs`: 해당 문서에서 만든 최종 산출물 이력을 반환한다.
- `GET /projects/{projectId}/documents/{documentId}/outputs/{outputId}`: 불변 최종 산출물을 다운로드한다.

URL의 `projectId`는 접근 권한과 원본 문서 소속 검증을 위한 경로 문맥이다. 최종 산출물 레코드에는 `project_id`를 저장하지 않는다.

## 5. 불변 조건

- 메타정보는 반드시 한 프로젝트에 속한다.
- 기본 문서는 반드시 한 프로젝트에 속하며 한 프로젝트에는 여러 문서가 존재할 수 있다.
- 최종 산출물은 반드시 하나의 기본 문서와 하나의 Markdown revision에서 만들어진다.
- 양식은 프로젝트에 복사하지 않고 렌더링 시 양식/렌더러 버전 참조를 최종 산출물에 기록한다.
- 최종 산출물을 다시 생성해도 과거 산출물을 덮어쓰지 않는다.
- 프로젝트 목록, 집계, 작업 문맥, 백업에 최종 산출물 바이너리를 포함하지 않는다.
- HWPX 작업본 수정은 명시적 `HWPX → MD` 반영 전까지 Markdown 원본을 자동 변경하지 않는다.

## 6. 기존 데이터 호환

기존 `project_document_artifacts`는 삭제하지 않고 문서별 편집 작업본으로 재해석한다. 과거에 `source_type='project-document-artifact'`로 생성된 프로젝트 Artifact 미러는 새 렌더링부터 생성하지 않으며 프로젝트 Artifact 조회에서 제외한다.

프로젝트 백업 1.1은 프로젝트 경계만 내보낸다. 가져오기는 과거 1.0 백업도 허용하되, 새 1.1 백업에는 작업본·최종 산출물·프로젝트 Artifact를 넣지 않는다.

## 7. 다음 확장 원칙

- PDF, DOCX, 제3자 형식도 `document_final_outputs`의 format/adapter 확장으로 추가한다.
- 최종 산출물 보존기간, 잠금, 서명, 외부 반출 감사는 프로젝트 정책이 아니라 산출물 저장소 정책으로 분리한다.
- 최종 산출물에서 기본 MD로 역변환할 때는 기존 문서를 자동 덮어쓰지 않고 새 revision 후보를 만든 뒤 사용자가 반영한다.
- 양식 MCP 삭제 시에도 기존 최종 산출물 재현 정보를 유지하도록 양식 버전, 해시, 렌더러 버전의 스냅샷을 보관한다.
