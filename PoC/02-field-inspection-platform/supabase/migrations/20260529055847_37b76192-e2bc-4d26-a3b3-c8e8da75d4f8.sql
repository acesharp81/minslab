
CREATE TABLE public.tasks (
  task_id TEXT PRIMARY KEY,
  task_name TEXT NOT NULL,
  purpose TEXT NOT NULL DEFAULT '',
  content TEXT NOT NULL DEFAULT '',
  department TEXT NOT NULL DEFAULT '',
  manager TEXT NOT NULL DEFAULT '',
  custom_fields JSONB NOT NULL DEFAULT '[]'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
GRANT SELECT, INSERT, UPDATE, DELETE ON public.tasks TO anon, authenticated;
GRANT ALL ON public.tasks TO service_role;
ALTER TABLE public.tasks ENABLE ROW LEVEL SECURITY;
CREATE POLICY "tasks_all" ON public.tasks FOR ALL TO anon, authenticated USING (true) WITH CHECK (true);

CREATE TABLE public.assets (
  asset_id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  category TEXT NOT NULL,
  address TEXT NOT NULL DEFAULT '',
  address_detail TEXT NOT NULL DEFAULT '',
  sido TEXT NOT NULL DEFAULT '',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
GRANT SELECT, INSERT, UPDATE, DELETE ON public.assets TO anon, authenticated;
GRANT ALL ON public.assets TO service_role;
ALTER TABLE public.assets ENABLE ROW LEVEL SECURITY;
CREATE POLICY "assets_all" ON public.assets FOR ALL TO anon, authenticated USING (true) WITH CHECK (true);

CREATE TABLE public.results (
  result_id TEXT PRIMARY KEY,
  task_id TEXT NOT NULL REFERENCES public.tasks(task_id) ON DELETE CASCADE,
  asset_id TEXT NOT NULL,
  year INT NOT NULL,
  inspector TEXT NOT NULL DEFAULT '',
  inspected_at TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL DEFAULT '등록',
  confirmer TEXT NOT NULL DEFAULT '',
  custom_values JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX results_task_idx ON public.results(task_id);
CREATE INDEX results_asset_idx ON public.results(asset_id);
GRANT SELECT, INSERT, UPDATE, DELETE ON public.results TO anon, authenticated;
GRANT ALL ON public.results TO service_role;
ALTER TABLE public.results ENABLE ROW LEVEL SECURITY;
CREATE POLICY "results_all" ON public.results FOR ALL TO anon, authenticated USING (true) WITH CHECK (true);
