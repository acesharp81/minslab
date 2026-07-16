# 02. 현장점검플랫폼

Lovable로 만든 acesharp81/ndmsinsptest를 MinsLab 홈페이지의 독립 React SPA로 이관한 통합 현장점검 PoC입니다.

## 현재 상태

- 홈페이지 통합: 완료
- PoC 내장 화면: https://www.minslab.kr/poc?project=field-inspection-platform
- 전체 화면: https://www.minslab.kr/poc/field-inspection-platform/
- 별도 Node 서버 또는 전용 포트: 없음
- 프런트엔드: React 19, TanStack Router, Vite, Tailwind CSS
- 데이터: Supabase tasks, assets, results
- 운영 정책: 로그인 없는 공개 PoC, 관리자 메뉴와 전체 CRUD 공개

원본 기준 커밋은 ca46ae10cfc94f993dc44681845f31fdff3d40d7입니다.

## 제공 기능

### Dashboard

- 점검 업무별 등록·점검중·점검완료 집계
- 업무별 완료율
- 물건을 선택한 통합 점검 입력
- 기존 기록 수정과 신규 기록 추가

### 점검 결과

- 업무별 결과 목록과 검색
- 점검연도, 점검자, 점검일, 대상, 상태 관리
- 업무별 사용자 정의 입력 항목
- 사진을 base64 데이터로 결과 JSON에 저장
- CSV 다운로드

### 통계

- 업무·관할 시도별 상태 집계
- 물건별 점검 업무와 결과 집계
- 결과 상세 화면 연결

### 관리자 메뉴

- 점검 업무 등록·수정·삭제
- 업무별 사용자 정의 입력 서식 구성
- 점검 대상 물건 등록·수정·삭제
- 시설물, 산, 하천, 강 분류와 관할 시도 관리

## 디자인 시스템

MinsLab 홈페이지와 자연스럽게 이어지도록 아이보리 배경, 잉크색 본문, 라임 포인트와 보라색 보조색을 공통 토큰으로 사용합니다.

- 대시보드는 핵심 수치, 빠른 점검 등록, 업무별 진행률 순으로 구성
- 상태는 등록(회색), 점검중(파랑), 점검완료(초록)로 일관되게 표시
- 카드와 표는 반투명 효과 대신 선명한 테두리와 충분한 여백을 적용
- 모바일에서는 메뉴, 요약 카드, 입력 폼과 표가 화면 폭에 맞게 재배치
- 별도 이미지 자산이나 외부 디자인 라이브러리 없이 React와 CSS로 구현

## 통합 구조

~~~text
MinsLab PoC 화면
  │
  └── 같은 출처 iframe
        │
        ▼
/poc/field-inspection-platform/
        │
        ├── dist/index.html
        ├── dist/assets/*.js
        └── dist/assets/*.css
                  │
                  ▼
        Supabase JavaScript client
                  │
                  ▼
        tasks / assets / results
~~~

원본 TanStack Start·Cloudflare 실행 구조는 Vite 정적 SPA로 변경했습니다. TanStack Router의 base path는 /poc/field-inspection-platform이며, 기존 Python ASGI 서비스가 index와 정적 자산을 제공합니다.

중첩 경로도 ASGI가 SPA index로 fallback합니다.

- /poc/field-inspection-platform/statistics
- /poc/field-inspection-platform/admin
- /poc/field-inspection-platform/tasks/{taskId}

## 공용 환경변수

루트 공용 .env에서 다음 공개 클라이언트 설정을 빌드 시 읽습니다.

~~~dotenv
VITE_FIELD_INSPECTION_SUPABASE_URL=https://YOUR_PROJECT.supabase.co
VITE_FIELD_INSPECTION_SUPABASE_PUBLISHABLE_KEY=YOUR_PUBLISHABLE_KEY
~~~

VITE_ 값은 브라우저 번들에 포함됩니다. 반드시 Supabase publishable key만 사용하고 service-role 키를 넣으면 안 됩니다.

프로젝트 폴더에는 별도 .env를 만들지 않습니다.

## Supabase 스키마

### tasks

- task_id
- task_name
- purpose
- content
- department
- manager
- custom_fields
- created_at

### assets

- asset_id
- name
- category
- address
- address_detail
- sido
- created_at

### results

- result_id
- task_id
- asset_id
- year
- inspector
- inspected_at
- status
- confirmer
- custom_values
- created_at

참고 마이그레이션:

~~~text
supabase/migrations/20260529055847_37b76192-e2bc-4d26-a3b3-c8e8da75d4f8.sql
~~~

## 빌드

Node.js 22 환경을 권장합니다.

~~~bash
cd /home/ubuntu/apps/myservice/PoC/02-field-inspection-platform
npm ci
npm run build
~~~

npm run build는 TypeScript 검사를 먼저 실행하고 성공하면 dist/를 갱신합니다.

운영 서버는 dist만 읽으므로 npm run dev, vite preview 또는 별도 Node 프로세스를 실행하지 않습니다.

## 배포와 확인

메인 서비스 재시작:

~~~bash
sudo systemctl restart myservice
~~~

로컬 ASGI 확인:

~~~bash
curl -fsS http://127.0.0.1:8000/poc/field-inspection-platform/
~~~

공개 HTTPS 확인:

~~~bash
curl -fsSL https://minslab.kr/poc/field-inspection-platform/
~~~

## 파일 구성

~~~text
PoC/02-field-inspection-platform/
├── README.md
├── UPSTREAM.md
├── project.json
├── package.json
├── package-lock.json
├── tsconfig.json
├── vite.config.ts
├── index.html
├── src/
│   ├── client.tsx
│   ├── router.tsx
│   ├── routes/
│   ├── components/
│   ├── lib/store.ts
│   └── integrations/supabase/
├── supabase/
│   └── migrations/
└── dist/
    ├── index.html
    └── assets/
~~~

## 공개 PoC 정책

현재는 사용자 요청에 따라 원본 동작을 유지합니다.

- anon 역할에 SELECT, INSERT, UPDATE, DELETE 허용
- 모든 방문자에게 관리자 메뉴 공개
- 사용자·조직별 데이터 분리 없음
- 변경·삭제 이력과 승인 흐름 없음

실제 운영 전에는 다음 작업이 필요합니다.

1. Supabase Auth 로그인
2. 조직과 사용자 소유권 컬럼 추가
3. 관리자·점검자·조회자 역할 분리
4. 사용자·조직별 RLS 정책 적용
5. 관리자 변경 이력과 삭제 보호
6. 사진을 JSON base64가 아닌 보호된 Storage 버킷으로 이전

공개 PoC에는 실제 개인정보, 보안시설 정보와 민감한 현장 자료를 저장하지 않습니다.


## 라우트와 화면 책임

| SPA 경로 | 화면 | 주요 동작 |
| --- | --- | --- |
| `/` | 업무 현황 | 업무별 상태 집계, 완료율, 물건 중심 통합 입력 |
| `/tasks/{taskId}/` | 업무별 결과 | 검색, 결과 목록, CSV 다운로드 |
| `/tasks/{taskId}/new` | 신규 결과 | 점검 대상·연도·점검자·상태·동적 항목 입력 |
| `/tasks/{taskId}/{resultId}` | 결과 상세/수정 | 기존 값 조회와 수정 |
| `/statistics` | 통계 | 업무·시도·물건 기준 집계와 상세 이동 |
| `/admin` | 관리자 | 업무, 입력 스키마, 점검 대상 CRUD |

TanStack Router의 history 경로를 사용하므로 ASGI 정적 서버는 파일이 없는 SPA 경로를 `dist/index.html`로 fallback합니다.

## 데이터 모델

### tasks

| 열 | 형식 | 설명 |
| --- | --- | --- |
| `task_id` | text PK | 클라이언트 생성 ID |
| `task_name` | text | 업무명 |
| `purpose`, `content` | text | 목적과 점검 내용 |
| `department`, `manager` | text | 담당 조직·담당자 |
| `custom_fields` | jsonb | 동적 입력 항목 배열 |
| `created_at` | timestamptz | 생성 시각 |

`custom_fields` 항목은 `id`, `name`, `type(text/number/photo)`, `length`를 가집니다. photo의 length는 최대 사진 수, text/number는 입력 길이로 사용합니다.

### assets

`asset_id`, `name`, `category`, `address`, `address_detail`, `sido`, `created_at`을 저장합니다. category 허용값은 화면 기준 `시설물/산/하천/강`입니다.

### results

`result_id`, `task_id`, `asset_id`, `year`, `inspector`, `inspected_at`, `status`, `confirmer`, `custom_values`, `created_at`을 저장합니다. 상태는 `등록/점검중/점검완료`이며 완료 상태에서만 확인자를 유지합니다. task 삭제는 FK cascade로 결과도 삭제됩니다.

사진은 별도 Storage bucket이 아니라 브라우저에서 읽은 base64 문자열 배열로 `custom_values` JSONB에 저장됩니다. 큰 사진은 행 크기와 네트워크 비용을 급격히 늘리므로 운영형 설계에서는 Storage 업로드와 URL 참조로 교체해야 합니다.

## 클라이언트 상태 동작

`src/lib/store.ts`는 React 외부 store와 `useSyncExternalStore`를 사용합니다.

```text
첫 subscribe
  → tasks/assets/results 병렬 SELECT
  → 모두 비어 있으면 데모 seed INSERT
  → 메모리 state 갱신
  → 컴포넌트 구독자 알림
```

CRUD는 화면 상태를 먼저 바꾸고 Supabase 요청을 비동기로 보내는 optimistic 방식입니다. 실패 시 콘솔에 오류를 남기지만 자동 rollback하지 않습니다. 따라서 다중 사용자가 동시에 편집하거나 네트워크가 불안정한 운영 환경에서는 mutation pending/error 상태, rollback, 재조회와 충돌 정책이 추가로 필요합니다.

## Supabase 권한의 의미

마이그레이션은 `tasks/assets/results`에 RLS를 켜지만 `anon`, `authenticated` 모두에게 `USING (true) WITH CHECK (true)` 정책을 부여합니다. 이는 공개 데모를 위한 전체 CRUD 허용이며 사용자 격리가 아닙니다.

운영 전 필수 변경:

1. Supabase Auth 도입
2. 각 행에 사용자 또는 조직 소유권 열 추가
3. anon 쓰기 권한 제거
4. SELECT/INSERT/UPDATE/DELETE별 RLS 분리
5. 관리자 역할을 서버 또는 검증된 role claim으로 제한
6. 사진을 Storage private bucket과 signed URL로 이전

## 빌드 설정

`vite.config.ts`는 배포 base를 `/poc/field-inspection-platform/`에 맞춥니다. 브라우저 Supabase 값은 빌드 시 다음 환경변수에서 들어갑니다.

```dotenv
VITE_FIELD_INSPECTION_SUPABASE_URL=...
VITE_FIELD_INSPECTION_SUPABASE_PUBLISHABLE_KEY=...
```

`VITE_*`는 번들에서 누구나 볼 수 있으므로 publishable key만 사용합니다.

```bash
npm ci
npm run build
# 결과: dist/
```

운영 서버는 `dist/`만 읽습니다. 소스 수정 후 build하지 않으면 화면에는 이전 코드가 계속 표시됩니다.

## CSV와 입력 제한

CSV는 UTF-8 BOM을 붙여 엑셀의 한글 인식을 돕고, 기본 열과 업무별 custom field를 함께 출력합니다. 사진 배열은 파일 자체가 아니라 저장된 문자열 값을 직렬화하므로 CSV 용량과 가독성을 확인해야 합니다. CSV는 브라우저에서 생성되며 서버 파일을 만들지 않습니다.
