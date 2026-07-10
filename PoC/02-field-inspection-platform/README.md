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
