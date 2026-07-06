create extension if not exists vector;

create table if not exists public.chat_history (
  id uuid primary key,
  client_id uuid not null,
  title text not null default '새로운 대화',
  model text not null,
  messages jsonb not null default '[]'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists chat_history_client_updated_idx
  on public.chat_history (client_id, updated_at desc);

alter table public.chat_history enable row level security;

create table if not exists public.chucking_test1 (
  id int8 primary key,
  content text not null,
  metadata jsonb not null default '{}'::jsonb,
  embedding vector
);

create table if not exists public.chucking_test2 (
  id int8 primary key,
  content text not null,
  metadata jsonb not null default '{}'::jsonb,
  embedding vector
);

create table if not exists public.chucking_test3 (
  id int8 primary key,
  content text not null,
  metadata jsonb not null default '{}'::jsonb,
  embedding vector
);

-- 서비스 역할 키는 RLS를 우회하므로 백엔드에서만 사용합니다.
-- SUPABASE2_SERVICE_ROLE_KEY를 절대 브라우저 코드에 넣지 마세요.
