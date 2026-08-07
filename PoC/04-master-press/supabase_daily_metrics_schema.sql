-- Master Press: long-term score-history read model only.
-- Run this block as-is in Supabase SQL Editor before activating the admin control.
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

-- Long-term, aggregate-only history. This intentionally excludes bodies,
-- embeddings, prompts and model responses, so it remains safe after the local
-- seven/eight-day operational retention window.
create table if not exists public.master_press_daily_operations (
  id text primary key,
  dataset text not null default 'production' check (dataset in ('production','trial')),
  metric_date date not null,
  organization_id uuid references public.master_press_organizations(id) on delete set null,
  article_count integer not null default 0,
  analyzed_count integer not null default 0,
  analysis_failed_count integer not null default 0,
  press_release_count integer not null default 0,
  related_match_count integer not null default 0,
  score_count integer not null default 0,
  sent_count integer not null default 0,
  hold_count integer not null default 0,
  low_count integer not null default 0,
  collection_run_count integer not null default 0,
  collection_failed_count integer not null default 0,
  created_at timestamptz not null,
  updated_at timestamptz not null,
  unique(dataset, metric_date, organization_id)
);
create index if not exists master_press_daily_operations_date_idx
  on public.master_press_daily_operations(dataset, metric_date desc);

create table if not exists public.master_press_daily_keyword_metrics (
  id text primary key,
  dataset text not null default 'production' check (dataset in ('production','trial')),
  metric_date date not null,
  organization_id uuid references public.master_press_organizations(id) on delete set null,
  source_kind text not null check (source_kind in ('article','press_release')),
  keyword text not null,
  document_count integer not null,
  document_total integer not null,
  coverage_pct numeric(6,2) not null,
  rank integer not null,
  extractor_version text not null,
  created_at timestamptz not null,
  updated_at timestamptz not null,
  unique(dataset, metric_date, organization_id, source_kind, keyword)
);
create index if not exists master_press_daily_keyword_trend_idx
  on public.master_press_daily_keyword_metrics(dataset, keyword, metric_date);
create index if not exists master_press_daily_keyword_org_date_idx
  on public.master_press_daily_keyword_metrics(dataset, organization_id, metric_date desc);

-- A mutable two-day transfer can leave rows from an earlier intraday snapshot.
-- This view exposes only the newest complete snapshot per day/source bucket,
-- while retaining older snapshots for audit and recovery.
create or replace view public.master_press_daily_keyword_metrics_current
with (security_invoker = true) as
select ranked.*
from (
  select metrics.*,
         max(updated_at) over (partition by dataset, metric_date, organization_id, source_kind) as snapshot_updated_at
  from public.master_press_daily_keyword_metrics metrics
) ranked
where ranked.updated_at = ranked.snapshot_updated_at;

create table if not exists public.master_press_daily_model_metrics (
  id text primary key,
  dataset text not null default 'production' check (dataset in ('production','trial')),
  metric_date date not null,
  provider text not null,
  stage text not null,
  model text not null,
  request_count integer not null default 0,
  completed_count integer not null default 0,
  failed_count integer not null default 0,
  input_tokens bigint not null default 0,
  output_tokens bigint not null default 0,
  usage_units bigint not null default 0,
  average_duration_ms numeric(12,1) not null default 0,
  created_at timestamptz not null,
  updated_at timestamptz not null,
  unique(dataset, metric_date, provider, stage, model)
);
create index if not exists master_press_daily_model_date_idx
  on public.master_press_daily_model_metrics(dataset, metric_date desc);

alter table public.master_press_daily_operations enable row level security;
alter table public.master_press_daily_keyword_metrics enable row level security;
alter table public.master_press_daily_model_metrics enable row level security;
