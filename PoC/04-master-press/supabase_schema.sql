-- Master Press PoC 04: optional Supabase mirror schema.
-- SQLite remains the operational queue/cache. Supabase stores shareable metadata,
-- relevance history and case versions. No browser receives the service-role key.

create table if not exists public.master_press_cases (
  id uuid primary key,
  name text not null,
  topic_description text not null default '',
  settings jsonb not null default '{}'::jsonb,
  version integer not null default 1,
  is_active boolean not null default true,
  next_collect_at timestamptz,
  last_collected_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.master_press_articles (
  id uuid primary key,
  canonical_url text not null unique,
  original_url text not null,
  title text not null,
  publisher text not null default '',
  published_at timestamptz,
  snippet text not null default '',
  source_type text not null default 'naver',
  first_seen_at timestamptz not null,
  updated_at timestamptz not null
);

create table if not exists public.master_press_scores (
  id uuid primary key,
  article_id uuid not null references public.master_press_articles(id) on delete cascade,
  case_id uuid not null references public.master_press_cases(id) on delete cascade,
  case_version integer not null,
  keyword_score numeric(5,2) not null,
  semantic_score numeric(5,2) not null,
  llm_score numeric(5,2) not null,
  final_score numeric(5,2) not null,
  summary text not null default '',
  reasons jsonb not null default '[]'::jsonb,
  low_score_categories jsonb not null default '[]'::jsonb,
  decision text not null check (decision in ('send','hold','low')),
  created_at timestamptz not null,
  updated_at timestamptz not null,
  unique(article_id, case_id)
);

create table if not exists public.master_press_runs (
  id uuid primary key,
  case_id uuid references public.master_press_cases(id) on delete set null,
  status text not null,
  counts jsonb not null default '{}'::jsonb,
  error text,
  started_at timestamptz not null,
  finished_at timestamptz
);

create index if not exists master_press_scores_case_created_idx
  on public.master_press_scores(case_id, created_at desc);
create index if not exists master_press_articles_published_idx
  on public.master_press_articles(published_at desc);

alter table public.master_press_cases enable row level security;
alter table public.master_press_articles enable row level security;
alter table public.master_press_scores enable row level security;
alter table public.master_press_runs enable row level security;

-- No anon/authenticated policies are created. The existing homepage Python boundary
-- reads and writes these tables with the service-role key and exposes sanitized APIs.
