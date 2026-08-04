-- Master Press PoC 04: optional Supabase mirror schema.
-- SQLite remains the operational queue/cache. Supabase stores shareable metadata,
-- relevance history and case versions. No browser receives the service-role key.

create table if not exists public.master_press_organizations (
  id uuid primary key,
  name text not null,
  search_metadata jsonb not null default '{}'::jsonb,
  collection_settings jsonb not null default '{}'::jsonb,
  is_active boolean not null default true,
  next_collect_at timestamptz,
  last_collected_at timestamptz,
  archived_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);


create table if not exists public.master_press_cases (
  id uuid primary key,
  name text not null,
  organization_id uuid references public.master_press_organizations(id) on delete set null,
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
  organization_tag text not null default '',
  article_type text not null default '기타',
  classification_tags jsonb not null default '[]'::jsonb,
  reasons jsonb not null default '[]'::jsonb,
  low_score_categories jsonb not null default '[]'::jsonb,
  decision text not null check (decision in ('send','hold','low')),
  created_at timestamptz not null,
  updated_at timestamptz not null,
  unique(article_id, case_id)
);

create table if not exists public.master_press_llm_jobs (
  id text primary key,
  article_id uuid not null references public.master_press_articles(id) on delete cascade,
  case_id uuid not null references public.master_press_cases(id) on delete cascade,
  case_version integer not null,
  organization_id uuid references public.master_press_organizations(id) on delete set null,
  status text not null,
  queued_at timestamptz not null,
  started_at timestamptz,
  finished_at timestamptz,
  duration_ms integer,
  error text,
  unique(article_id, case_id, case_version)
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
alter table public.master_press_cases add column if not exists organization_id uuid references public.master_press_organizations(id) on delete set null;
alter table public.master_press_scores add column if not exists organization_tag text not null default '';
alter table public.master_press_scores add column if not exists article_type text not null default '기타';
alter table public.master_press_scores add column if not exists classification_tags jsonb not null default '[]'::jsonb;
alter table public.master_press_runs add column if not exists organization_id uuid references public.master_press_organizations(id) on delete set null;

create index if not exists master_press_articles_published_idx
  on public.master_press_articles(published_at desc);

alter table public.master_press_organizations enable row level security;
alter table public.master_press_cases enable row level security;
alter table public.master_press_articles enable row level security;
alter table public.master_press_scores enable row level security;
alter table public.master_press_llm_jobs enable row level security;
alter table public.master_press_runs enable row level security;

-- No anon/authenticated policies are created. The existing homepage Python boundary
-- reads and writes these tables with the service-role key and exposes sanitized APIs.

-- 행안부 보도자료 Markdown RAG 및 기사 양방향 연관 관계
create extension if not exists vector;

create table if not exists public.master_press_press_releases (
  id uuid primary key,
  organization_id uuid not null references public.master_press_organizations(id) on delete cascade,
  source text not null default 'mois',
  external_id text not null,
  canonical_url text not null unique,
  title text not null,
  department text not null default '',
  contact_name text not null default '',
  contact_phone text not null default '',
  published_at timestamptz,
  summary text not null default '',
  markdown text not null default '',
  content_hash text not null,
  document_fingerprint text not null,
  embedding_model text not null default '',
  created_at timestamptz not null,
  updated_at timestamptz not null
);

create table if not exists public.master_press_press_release_chunks (
  id uuid primary key,
  press_release_id uuid not null references public.master_press_press_releases(id) on delete cascade,
  chunk_index integer not null,
  content text not null,
  content_hash text not null,
  embedding_model text not null,
  dimensions integer not null default 768,
  embedding vector(768) not null,
  created_at timestamptz not null,
  updated_at timestamptz not null,
  unique(press_release_id, chunk_index)
);

create table if not exists public.master_press_article_press_matches (
  id text primary key,
  article_id uuid not null references public.master_press_articles(id) on delete cascade,
  press_release_id uuid not null references public.master_press_press_releases(id) on delete cascade,
  semantic_score numeric(5,2) not null,
  lexical_score numeric(5,2) not null,
  similarity_score numeric(5,2) not null,
  matcher_version text not null,
  matched_at timestamptz not null,
  unique(article_id, press_release_id)
);

create index if not exists master_press_release_chunks_embedding_idx
  on public.master_press_press_release_chunks using ivfflat (embedding vector_cosine_ops) with (lists = 20);
create index if not exists master_press_press_releases_org_published_idx
  on public.master_press_press_releases(organization_id, published_at desc);
create unique index if not exists master_press_press_releases_org_fingerprint_idx
  on public.master_press_press_releases(organization_id, document_fingerprint);

create or replace function public.match_master_press_release_chunks(
  query_embedding vector(768), match_count integer default 10, target_organization uuid default null
)
returns table (
  press_release_id uuid, chunk_id uuid, title text, department text,
  published_at timestamptz, content text, similarity double precision
)
language sql stable
as $$
  select pr.id, pc.id, pr.title, pr.department, pr.published_at, pc.content,
         1 - (pc.embedding <=> query_embedding) as similarity
  from public.master_press_press_release_chunks pc
  join public.master_press_press_releases pr on pr.id=pc.press_release_id
  where target_organization is null or pr.organization_id=target_organization
  order by pc.embedding <=> query_embedding
  limit greatest(1, least(match_count, 50));
$$;

-- 기사 임베딩은 관련 기사 군집의 원격 후보 검색에만 사용한다.
create table if not exists public.master_press_article_embeddings (
  analysis_id text primary key,
  article_id uuid not null references public.master_press_articles(id) on delete cascade,
  organization_id uuid references public.master_press_organizations(id) on delete set null,
  embedding_model text not null,
  dimensions integer not null default 768,
  embedding vector(768) not null,
  updated_at timestamptz not null
);
create index if not exists master_press_article_embeddings_hnsw_idx
  on public.master_press_article_embeddings using hnsw (embedding vector_cosine_ops);

alter table public.master_press_article_embeddings alter column analysis_id type text using analysis_id::text;

drop function if exists public.match_master_press_article_embeddings(vector, integer, uuid);
create function public.match_master_press_article_embeddings(
  query_embedding vector(768), match_count integer default 20, target_organization uuid default null
)
returns table (analysis_id text, article_id uuid, similarity double precision)
language sql stable
as $$
  select ae.analysis_id, ae.article_id, 1 - (ae.embedding <=> query_embedding) as similarity
  from public.master_press_article_embeddings ae
  where target_organization is null or ae.organization_id=target_organization
  order by ae.embedding <=> query_embedding
  limit greatest(1, least(match_count, 50));
$$;

alter table public.master_press_press_releases enable row level security;
alter table public.master_press_press_release_chunks enable row level security;
alter table public.master_press_article_press_matches enable row level security;
alter table public.master_press_article_embeddings enable row level security;


-- 장기 분석 이력 전용 읽기 모델: 실시간 수집·발송·LLM 원문은 포함하지 않는다.
create table if not exists public.master_press_daily_metrics (
  id text primary key,
  metric_date date not null,
  organization_id uuid not null references public.master_press_organizations(id) on delete cascade,
  case_id uuid not null references public.master_press_cases(id) on delete cascade,
  score_count integer not null default 0,
  article_count integer not null default 0,
  sent_count integer not null default 0,
  hold_count integer not null default 0,
  low_count integer not null default 0,
  average_score numeric(5,2) not null default 0,
  top_publishers jsonb not null default '[]'::jsonb,
  top_topics jsonb not null default '[]'::jsonb,
  created_at timestamptz not null,
  updated_at timestamptz not null,
  unique(metric_date, organization_id, case_id)
);

create index if not exists master_press_daily_metrics_org_date_idx
  on public.master_press_daily_metrics(organization_id, metric_date desc);
create index if not exists master_press_daily_metrics_case_date_idx
  on public.master_press_daily_metrics(case_id, metric_date desc);
alter table public.master_press_daily_metrics enable row level security;

-- Long-term aggregate-only history. It excludes bodies, embeddings, prompts
-- and model responses so it can outlive the local operational retention.
create table if not exists public.master_press_daily_operations (
  id text primary key, dataset text not null default 'production' check (dataset in ('production','trial')),
  metric_date date not null, organization_id uuid references public.master_press_organizations(id) on delete set null,
  article_count integer not null default 0, analyzed_count integer not null default 0, analysis_failed_count integer not null default 0,
  press_release_count integer not null default 0, related_match_count integer not null default 0, score_count integer not null default 0,
  sent_count integer not null default 0, hold_count integer not null default 0, low_count integer not null default 0,
  collection_run_count integer not null default 0, collection_failed_count integer not null default 0,
  created_at timestamptz not null, updated_at timestamptz not null,
  unique(dataset, metric_date, organization_id)
);
create table if not exists public.master_press_daily_keyword_metrics (
  id text primary key, dataset text not null default 'production' check (dataset in ('production','trial')),
  metric_date date not null, organization_id uuid references public.master_press_organizations(id) on delete set null,
  source_kind text not null check (source_kind in ('article','press_release')), keyword text not null,
  document_count integer not null, document_total integer not null, coverage_pct numeric(6,2) not null, rank integer not null,
  extractor_version text not null, created_at timestamptz not null, updated_at timestamptz not null,
  unique(dataset, metric_date, organization_id, source_kind, keyword)
);
create table if not exists public.master_press_daily_model_metrics (
  id text primary key, dataset text not null default 'production' check (dataset in ('production','trial')),
  metric_date date not null, provider text not null, stage text not null, model text not null,
  request_count integer not null default 0, completed_count integer not null default 0, failed_count integer not null default 0,
  input_tokens bigint not null default 0, output_tokens bigint not null default 0, usage_units bigint not null default 0,
  average_duration_ms numeric(12,1) not null default 0, created_at timestamptz not null, updated_at timestamptz not null,
  unique(dataset, metric_date, provider, stage, model)
);
create index if not exists master_press_daily_operations_date_idx on public.master_press_daily_operations(dataset, metric_date desc);
create index if not exists master_press_daily_keyword_trend_idx on public.master_press_daily_keyword_metrics(dataset, keyword, metric_date);
create index if not exists master_press_daily_keyword_org_date_idx on public.master_press_daily_keyword_metrics(dataset, organization_id, metric_date desc);
create or replace view public.master_press_daily_keyword_metrics_current
with (security_invoker = true) as
select ranked.* from (
  select metrics.*,max(updated_at) over (partition by dataset,metric_date,organization_id,source_kind) snapshot_updated_at
  from public.master_press_daily_keyword_metrics metrics
) ranked where ranked.updated_at=ranked.snapshot_updated_at;
create index if not exists master_press_daily_model_date_idx on public.master_press_daily_model_metrics(dataset, metric_date desc);
alter table public.master_press_daily_operations enable row level security;
alter table public.master_press_daily_keyword_metrics enable row level security;
alter table public.master_press_daily_model_metrics enable row level security;
