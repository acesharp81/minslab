# AI Work Hub 현재 아키텍처와 경계

> 기준선: 0.31.2 / 2026-09-04 / 표시명 `AI Work Hub`, 기술 식별자 `aiworks`

## 배포 구조

```text
Browser SPA
  -> /api/poc/aiworks
  -> main.py ASGI host
  -> backend.py application facade
  -> SQLite WAL + local artifact/package bytes
  -> optional Solar/OpenRouter/Ollama/RHWP bridge
```

현재는 단일 프로세스·단일 노드 PoC이며 Queue, Object Storage, 다중 인스턴스 쓰기, 신뢰 가능한
SSO identity를 제공하지 않는다.

## 코드 기준 인벤토리

- `backend.py`: 약 14.8K LOC, 함수 348개, SQLite 테이블 54개, 단일 `dispatch` API facade
- `web/app.js`: 약 2.3K LOC, 프로젝트·문서·승인·Builder·Store·운영 화면의 공용 상태
- `core_runtime/`: Context Assembler, Task Compiler, Capability Resolution 설명 계약의 초기 분리
- `contracts/`: Project, Document, Artifact, Evidence, Plan, Approval, Workflow, MCP, Recipe 계약
- `tests/`: 2026-09-04 기준 단위·계약·통합 145개 통과; 브라우저와 Windows RHWP는 별도 검증

## 보존 경계

1. Markdown revision은 immutable이다.
2. HWPX는 Markdown version에서 파생된 산출물이다.
3. `stale`, `diverged`, `conflict`에서 자동 우선순위를 정하지 않는다.
4. 외부 전송은 권한과 일회용 승인 없이는 실행하지 않는다.
5. MCP는 고정 package/version으로 실행한다.
6. Audit event와 과거 Artifact provenance를 개칭이나 migration으로 다시 쓰지 않는다.

## 표시명 호환성

`AI Work Hub`는 교체 가능한 표시명이다. `/poc/aiworks`, `/api/poc/aiworks`, `AIWORKS_*`,
`.aiworks.json`, schema `$id`, DB 및 감사 이벤트의 기존 `AIWorks` 표기는 기술 호환성과 과거 이력으로
유지한다. 서버 bootstrap은 `displayName`, `technicalName`, `technicalSlug`를 구분한다.

## 다음 분리 지점

Golden Workflow를 회귀 안전망으로 사용한 후 API routing, 실제 Capability 후보 선택, Project/Document
repository, Approval/Execution/Audit 순서로 Strangler 방식 분리를 진행한다. Phase 1에서는 구조를
재작성하지 않는다.
