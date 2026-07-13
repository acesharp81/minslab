
-- Enums
CREATE TYPE public.user_position AS ENUM ('과장', '팀장', '팀원', '서무');
CREATE TYPE public.user_status AS ENUM ('가입신청', '승인', '탈퇴');
CREATE TYPE public.task_step AS ENUM ('팀원저장','팀원등록','팀장검토','팀장저장','팀장등록','팀장반려','과장승인','과장반려');
CREATE TYPE public.task_method AS ENUM ('온라인','오프라인');
CREATE TYPE public.app_role AS ENUM ('admin');

-- Divisions
CREATE TABLE public.divisions (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  name text NOT NULL UNIQUE,
  created_at timestamptz NOT NULL DEFAULT now()
);

-- Teams
CREATE TABLE public.teams (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  division_id uuid NOT NULL REFERENCES public.divisions(id) ON DELETE CASCADE,
  name text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (division_id, name)
);

-- Task categories
CREATE TABLE public.task_categories (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  name text NOT NULL UNIQUE,
  is_default boolean NOT NULL DEFAULT false,
  created_at timestamptz NOT NULL DEFAULT now()
);

-- Templates (one per task_category)
CREATE TABLE public.templates (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  category_id uuid NOT NULL UNIQUE REFERENCES public.task_categories(id) ON DELETE CASCADE,
  content text NOT NULL DEFAULT '',
  updated_at timestamptz NOT NULL DEFAULT now()
);

-- Profiles
CREATE TABLE public.profiles (
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

-- User roles
CREATE TABLE public.user_roles (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  role public.app_role NOT NULL,
  UNIQUE (user_id, role)
);

-- Tasks
CREATE TABLE public.tasks (
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

CREATE INDEX idx_tasks_author ON public.tasks(author_id);
CREATE INDEX idx_tasks_datetime ON public.tasks(datetime);

-- has_role function (security definer)
CREATE OR REPLACE FUNCTION public.has_role(_user_id uuid, _role public.app_role)
RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public
AS $$
  SELECT EXISTS (SELECT 1 FROM public.user_roles WHERE user_id = _user_id AND role = _role)
$$;

-- helper: get current profile's division
CREATE OR REPLACE FUNCTION public.current_division_id()
RETURNS uuid LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public
AS $$ SELECT division_id FROM public.profiles WHERE id = auth.uid() $$;

CREATE OR REPLACE FUNCTION public.current_team_id()
RETURNS uuid LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public
AS $$ SELECT team_id FROM public.profiles WHERE id = auth.uid() $$;

CREATE OR REPLACE FUNCTION public.current_position()
RETURNS public.user_position LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public
AS $$ SELECT position FROM public.profiles WHERE id = auth.uid() $$;

-- updated_at trigger
CREATE OR REPLACE FUNCTION public.set_updated_at()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN NEW.updated_at = now(); RETURN NEW; END $$;

CREATE TRIGGER trg_profiles_updated BEFORE UPDATE ON public.profiles
  FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();
CREATE TRIGGER trg_tasks_updated BEFORE UPDATE ON public.tasks
  FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();
CREATE TRIGGER trg_templates_updated BEFORE UPDATE ON public.templates
  FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

-- Enable RLS
ALTER TABLE public.divisions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.teams ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.task_categories ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.templates ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.user_roles ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.tasks ENABLE ROW LEVEL SECURITY;

-- Policies: meta (read by authenticated, write by admin)
CREATE POLICY "meta_read_div" ON public.divisions FOR SELECT TO authenticated USING (true);
CREATE POLICY "meta_write_div" ON public.divisions FOR ALL TO authenticated
  USING (public.has_role(auth.uid(), 'admin')) WITH CHECK (public.has_role(auth.uid(), 'admin'));

CREATE POLICY "meta_read_team" ON public.teams FOR SELECT TO authenticated USING (true);
CREATE POLICY "meta_write_team" ON public.teams FOR ALL TO authenticated
  USING (public.has_role(auth.uid(), 'admin')) WITH CHECK (public.has_role(auth.uid(), 'admin'));

CREATE POLICY "meta_read_cat" ON public.task_categories FOR SELECT TO authenticated USING (true);
CREATE POLICY "meta_write_cat" ON public.task_categories FOR ALL TO authenticated
  USING (public.has_role(auth.uid(), 'admin')) WITH CHECK (public.has_role(auth.uid(), 'admin'));

CREATE POLICY "meta_read_tpl" ON public.templates FOR SELECT TO authenticated USING (true);
CREATE POLICY "meta_write_tpl" ON public.templates FOR ALL TO authenticated
  USING (public.has_role(auth.uid(), 'admin')) WITH CHECK (public.has_role(auth.uid(), 'admin'));

-- Profiles
CREATE POLICY "profiles_read_all" ON public.profiles FOR SELECT TO authenticated USING (true);
CREATE POLICY "profiles_insert_self" ON public.profiles FOR INSERT TO authenticated
  WITH CHECK (id = auth.uid());
CREATE POLICY "profiles_update_self" ON public.profiles FOR UPDATE TO authenticated
  USING (id = auth.uid() OR public.has_role(auth.uid(), 'admin'))
  WITH CHECK (id = auth.uid() OR public.has_role(auth.uid(), 'admin'));
CREATE POLICY "profiles_admin_delete" ON public.profiles FOR DELETE TO authenticated
  USING (public.has_role(auth.uid(), 'admin'));

-- user_roles: only admins manage; users can read their own
CREATE POLICY "roles_read_self" ON public.user_roles FOR SELECT TO authenticated
  USING (user_id = auth.uid() OR public.has_role(auth.uid(), 'admin'));
CREATE POLICY "roles_admin_write" ON public.user_roles FOR ALL TO authenticated
  USING (public.has_role(auth.uid(), 'admin')) WITH CHECK (public.has_role(auth.uid(), 'admin'));

-- Tasks: division-scoped read, role-scoped write
CREATE POLICY "tasks_read_division" ON public.tasks FOR SELECT TO authenticated
  USING (
    EXISTS (
      SELECT 1 FROM public.profiles p
      WHERE p.id = tasks.author_id AND p.division_id = public.current_division_id()
    )
    OR public.has_role(auth.uid(), 'admin')
  );

CREATE POLICY "tasks_insert_self" ON public.tasks FOR INSERT TO authenticated
  WITH CHECK (author_id = auth.uid());

CREATE POLICY "tasks_update_scope" ON public.tasks FOR UPDATE TO authenticated
  USING (
    author_id = auth.uid()
    OR (public.current_position() = '팀장' AND EXISTS (
      SELECT 1 FROM public.profiles p WHERE p.id = tasks.author_id AND p.team_id = public.current_team_id()))
    OR (public.current_position() IN ('과장','서무') AND EXISTS (
      SELECT 1 FROM public.profiles p WHERE p.id = tasks.author_id AND p.division_id = public.current_division_id()))
    OR public.has_role(auth.uid(), 'admin')
  )
  WITH CHECK (true);

CREATE POLICY "tasks_delete_self" ON public.tasks FOR DELETE TO authenticated
  USING (author_id = auth.uid() OR public.has_role(auth.uid(), 'admin'));

-- Enable realtime
ALTER PUBLICATION supabase_realtime ADD TABLE public.tasks;
ALTER PUBLICATION supabase_realtime ADD TABLE public.profiles;

-- Seed divisions
INSERT INTO public.divisions (name) VALUES ('기획과'), ('운영과'), ('정책과');

-- Seed teams
INSERT INTO public.teams (division_id, name)
SELECT d.id, t.name FROM public.divisions d
CROSS JOIN (VALUES ('1팀'),('2팀'),('3팀')) AS t(name);

-- Seed task categories
INSERT INTO public.task_categories (name, is_default) VALUES
  ('회의', false), ('출장', false), ('보고', false),
  ('월간보고템플릿', true), ('주간보고템플릿', true);

-- Seed empty templates for every category
INSERT INTO public.templates (category_id, content)
SELECT id, '' FROM public.task_categories;
