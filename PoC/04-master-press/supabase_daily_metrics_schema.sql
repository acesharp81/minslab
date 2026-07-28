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
