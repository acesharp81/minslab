-- MinsLab shared Supabase: MoIS KMS schema
-- Existing chunking/document tables are not modified.

DO $$ BEGIN
  CREATE TYPE public.user_position AS ENUM ('과장', '팀장', '팀원', '서무');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
  CREATE TYPE public.user_status AS ENUM ('가입신청', '승인', '탈퇴');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
  CREATE TYPE public.task_step AS ENUM ('팀원저장','팀원등록','팀장검토','팀장저장','팀장등록','팀장반려','과장승인','과장반려');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
  CREATE TYPE public.task_method AS ENUM ('온라인','오프라인');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
  CREATE TYPE public.app_role AS ENUM ('admin');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

CREATE TABLE IF NOT EXISTS public.divisions (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  name text NOT NULL UNIQUE,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.teams (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  division_id uuid NOT NULL REFERENCES public.divisions(id) ON DELETE CASCADE,
  name text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (division_id, name)
);

CREATE TABLE IF NOT EXISTS public.task_categories (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  name text NOT NULL UNIQUE,
  is_default boolean NOT NULL DEFAULT false,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.templates (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  category_id uuid NOT NULL UNIQUE REFERENCES public.task_categories(id) ON DELETE CASCADE,
  content text NOT NULL DEFAULT '',
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.profiles (
  id uuid PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
  user_no_pk bigserial UNIQUE,
  login_id text NOT NULL UNIQUE,
  name text NOT NULL,
  division_id uuid REFERENCES public.divisions(id) ON DELETE SET NULL,
  team_id uuid REFERENCES public.teams(id) ON DELETE SET NULL,
  position public.user_position NOT NULL,
  status public.user_status NOT NULL DEFAULT '가입신청',
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.user_roles (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  role public.app_role NOT NULL,
  UNIQUE (user_id, role)
);

CREATE TABLE IF NOT EXISTS public.tasks (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  task_no_pk bigserial UNIQUE,
  author_id uuid NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
  category_id uuid REFERENCES public.task_categories(id) ON DELETE SET NULL,
  title text NOT NULL,
  purpose text NOT NULL,
  content text NOT NULL,
  method public.task_method NOT NULL,
  location text,
  datetime timestamptz NOT NULL,
  attendees text NOT NULL,
  step public.task_step NOT NULL DEFAULT '팀원저장',
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_tasks_author ON public.tasks(author_id);
CREATE INDEX IF NOT EXISTS idx_tasks_datetime ON public.tasks(datetime);
CREATE INDEX IF NOT EXISTS idx_profiles_division ON public.profiles(division_id);
CREATE INDEX IF NOT EXISTS idx_profiles_team ON public.profiles(team_id);

CREATE OR REPLACE FUNCTION public.kms_has_role(_user_id uuid, _role public.app_role)
RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER
SET search_path = public
AS $$
  SELECT EXISTS (
    SELECT 1 FROM public.user_roles
    WHERE user_id = _user_id AND role = _role
  )
$$;

CREATE OR REPLACE FUNCTION public.kms_current_division_id()
RETURNS uuid
LANGUAGE sql STABLE SECURITY DEFINER
SET search_path = public
AS $$
  SELECT division_id FROM public.profiles WHERE id = auth.uid()
$$;

CREATE OR REPLACE FUNCTION public.kms_current_team_id()
RETURNS uuid
LANGUAGE sql STABLE SECURITY DEFINER
SET search_path = public
AS $$
  SELECT team_id FROM public.profiles WHERE id = auth.uid()
$$;

CREATE OR REPLACE FUNCTION public.kms_current_position()
RETURNS public.user_position
LANGUAGE sql STABLE SECURITY DEFINER
SET search_path = public
AS $$
  SELECT position FROM public.profiles WHERE id = auth.uid()
$$;

CREATE OR REPLACE FUNCTION public.kms_set_updated_at()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = public
AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END
$$;

DROP TRIGGER IF EXISTS kms_profiles_updated ON public.profiles;
CREATE TRIGGER kms_profiles_updated
BEFORE UPDATE ON public.profiles
FOR EACH ROW EXECUTE FUNCTION public.kms_set_updated_at();

DROP TRIGGER IF EXISTS kms_tasks_updated ON public.tasks;
CREATE TRIGGER kms_tasks_updated
BEFORE UPDATE ON public.tasks
FOR EACH ROW EXECUTE FUNCTION public.kms_set_updated_at();

DROP TRIGGER IF EXISTS kms_templates_updated ON public.templates;
CREATE TRIGGER kms_templates_updated
BEFORE UPDATE ON public.templates
FOR EACH ROW EXECUTE FUNCTION public.kms_set_updated_at();

ALTER TABLE public.divisions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.teams ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.task_categories ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.templates ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.user_roles ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.tasks ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS kms_meta_read_divisions ON public.divisions;
CREATE POLICY kms_meta_read_divisions ON public.divisions
FOR SELECT TO authenticated USING (true);
DROP POLICY IF EXISTS kms_meta_write_divisions ON public.divisions;
CREATE POLICY kms_meta_write_divisions ON public.divisions
FOR ALL TO authenticated
USING (public.kms_has_role(auth.uid(), 'admin'))
WITH CHECK (public.kms_has_role(auth.uid(), 'admin'));

DROP POLICY IF EXISTS kms_meta_read_teams ON public.teams;
CREATE POLICY kms_meta_read_teams ON public.teams
FOR SELECT TO authenticated USING (true);
DROP POLICY IF EXISTS kms_meta_write_teams ON public.teams;
CREATE POLICY kms_meta_write_teams ON public.teams
FOR ALL TO authenticated
USING (public.kms_has_role(auth.uid(), 'admin'))
WITH CHECK (public.kms_has_role(auth.uid(), 'admin'));

DROP POLICY IF EXISTS kms_meta_read_categories ON public.task_categories;
CREATE POLICY kms_meta_read_categories ON public.task_categories
FOR SELECT TO authenticated USING (true);
DROP POLICY IF EXISTS kms_meta_write_categories ON public.task_categories;
CREATE POLICY kms_meta_write_categories ON public.task_categories
FOR ALL TO authenticated
USING (public.kms_has_role(auth.uid(), 'admin'))
WITH CHECK (public.kms_has_role(auth.uid(), 'admin'));

DROP POLICY IF EXISTS kms_meta_read_templates ON public.templates;
CREATE POLICY kms_meta_read_templates ON public.templates
FOR SELECT TO authenticated USING (true);
DROP POLICY IF EXISTS kms_meta_write_templates ON public.templates;
CREATE POLICY kms_meta_write_templates ON public.templates
FOR ALL TO authenticated
USING (public.kms_has_role(auth.uid(), 'admin'))
WITH CHECK (public.kms_has_role(auth.uid(), 'admin'));

DROP POLICY IF EXISTS kms_profiles_read_all ON public.profiles;
CREATE POLICY kms_profiles_read_all ON public.profiles
FOR SELECT TO authenticated USING (true);
DROP POLICY IF EXISTS kms_profiles_insert_self ON public.profiles;
CREATE POLICY kms_profiles_insert_self ON public.profiles
FOR INSERT TO authenticated WITH CHECK (id = auth.uid());
DROP POLICY IF EXISTS kms_profiles_update_self_or_admin ON public.profiles;
CREATE POLICY kms_profiles_update_self_or_admin ON public.profiles
FOR UPDATE TO authenticated
USING (id = auth.uid() OR public.kms_has_role(auth.uid(), 'admin'))
WITH CHECK (id = auth.uid() OR public.kms_has_role(auth.uid(), 'admin'));
DROP POLICY IF EXISTS kms_profiles_delete_admin ON public.profiles;
CREATE POLICY kms_profiles_delete_admin ON public.profiles
FOR DELETE TO authenticated
USING (public.kms_has_role(auth.uid(), 'admin'));

DROP POLICY IF EXISTS kms_roles_read_self_or_admin ON public.user_roles;
CREATE POLICY kms_roles_read_self_or_admin ON public.user_roles
FOR SELECT TO authenticated
USING (user_id = auth.uid() OR public.kms_has_role(auth.uid(), 'admin'));
DROP POLICY IF EXISTS kms_roles_write_admin ON public.user_roles;
CREATE POLICY kms_roles_write_admin ON public.user_roles
FOR ALL TO authenticated
USING (public.kms_has_role(auth.uid(), 'admin'))
WITH CHECK (public.kms_has_role(auth.uid(), 'admin'));

DROP POLICY IF EXISTS kms_tasks_read_division ON public.tasks;
CREATE POLICY kms_tasks_read_division ON public.tasks
FOR SELECT TO authenticated
USING (
  EXISTS (
    SELECT 1 FROM public.profiles p
    WHERE p.id = tasks.author_id
      AND p.division_id = public.kms_current_division_id()
  )
  OR public.kms_has_role(auth.uid(), 'admin')
);

DROP POLICY IF EXISTS kms_tasks_insert_self ON public.tasks;
CREATE POLICY kms_tasks_insert_self ON public.tasks
FOR INSERT TO authenticated
WITH CHECK (author_id = auth.uid());

DROP POLICY IF EXISTS kms_tasks_update_scope ON public.tasks;
CREATE POLICY kms_tasks_update_scope ON public.tasks
FOR UPDATE TO authenticated
USING (
  author_id = auth.uid()
  OR (
    public.kms_current_position() = '팀장'
    AND EXISTS (
      SELECT 1 FROM public.profiles p
      WHERE p.id = tasks.author_id
        AND p.team_id = public.kms_current_team_id()
    )
  )
  OR (
    public.kms_current_position() IN ('과장', '서무')
    AND EXISTS (
      SELECT 1 FROM public.profiles p
      WHERE p.id = tasks.author_id
        AND p.division_id = public.kms_current_division_id()
    )
  )
  OR public.kms_has_role(auth.uid(), 'admin')
)
WITH CHECK (true);

DROP POLICY IF EXISTS kms_tasks_delete_self_or_admin ON public.tasks;
CREATE POLICY kms_tasks_delete_self_or_admin ON public.tasks
FOR DELETE TO authenticated
USING (author_id = auth.uid() OR public.kms_has_role(auth.uid(), 'admin'));

GRANT USAGE ON SCHEMA public TO authenticated, service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON
  public.divisions,
  public.teams,
  public.task_categories,
  public.templates,
  public.profiles,
  public.user_roles,
  public.tasks
TO authenticated;
GRANT ALL ON
  public.divisions,
  public.teams,
  public.task_categories,
  public.templates,
  public.profiles,
  public.user_roles,
  public.tasks
TO service_role;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO authenticated, service_role;
GRANT EXECUTE ON FUNCTION public.kms_has_role(uuid, public.app_role) TO authenticated, service_role;
GRANT EXECUTE ON FUNCTION public.kms_current_division_id() TO authenticated, service_role;
GRANT EXECUTE ON FUNCTION public.kms_current_team_id() TO authenticated, service_role;
GRANT EXECUTE ON FUNCTION public.kms_current_position() TO authenticated, service_role;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_publication_tables
    WHERE pubname = 'supabase_realtime'
      AND schemaname = 'public'
      AND tablename = 'tasks'
  ) THEN
    ALTER PUBLICATION supabase_realtime ADD TABLE public.tasks;
  END IF;
  IF NOT EXISTS (
    SELECT 1 FROM pg_publication_tables
    WHERE pubname = 'supabase_realtime'
      AND schemaname = 'public'
      AND tablename = 'profiles'
  ) THEN
    ALTER PUBLICATION supabase_realtime ADD TABLE public.profiles;
  END IF;
END $$;

INSERT INTO public.divisions (name)
VALUES ('기획과'), ('운영과'), ('정책과')
ON CONFLICT (name) DO NOTHING;

INSERT INTO public.teams (division_id, name)
SELECT division.id, seed.name
FROM public.divisions AS division
CROSS JOIN (VALUES ('1팀'), ('2팀'), ('3팀')) AS seed(name)
ON CONFLICT (division_id, name) DO NOTHING;

INSERT INTO public.task_categories (name, is_default)
VALUES
  ('회의', false),
  ('출장', false),
  ('보고', false),
  ('월간보고템플릿', true),
  ('주간보고템플릿', true)
ON CONFLICT (name) DO NOTHING;

INSERT INTO public.templates (category_id, content)
SELECT id, '' FROM public.task_categories
ON CONFLICT (category_id) DO NOTHING;
