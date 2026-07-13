# Upstream

- Repository: https://github.com/acesharp81/moiskms
- Imported commit: `d0057c9e64f8cb594a14d352de10594e7913d97f`
- Imported at: 2026-07-10

## Conversion

원본 TanStack Start·Cloudflare SSR 구조를 MinsLab Python ASGI가 제공하는 Vite 정적 SPA로 변환했습니다. 원본의 Lovable AI Gateway 고정 모델 호출은 Local Ollama, Hugging Face Router, OpenRouter 제공자 선택 방식으로 교체했습니다.

Supabase 스키마, Auth 사용자, 프로필, 부서·팀, 업무 분류, 템플릿, 업무와 RLS 정책은 원본 구조를 유지합니다.

## Shared Supabase deployment

무료 플랜의 프로젝트 수 제한을 고려해 별도 원본 Supabase 대신 기존 MinsLab `SUPABASE2_URL`에 KMS 전용 테이블을 추가합니다. 적용 SQL은 `supabase/migrations/20260710000000_minslab_kms.sql`이며 기존 청킹·문서 테이블을 수정하지 않습니다.
