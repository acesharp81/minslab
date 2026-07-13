import { z } from "zod";
import { supabase } from "@/integrations/supabase/client";
import { apiRequest } from "./api";

async function assertAdmin() {
  const { data: auth } = await supabase.auth.getUser();
  if (!auth.user) throw new Error("로그인이 필요합니다.");
  const { data } = await supabase
    .from("user_roles")
    .select("role")
    .eq("user_id", auth.user.id)
    .eq("role", "admin")
    .maybeSingle();
  if (!data) throw new Error("관리자 권한이 필요합니다.");
  return auth.user.id;
}

export async function adminListUsers() {
  await assertAdmin();
  const [{ data: profiles, error }, { data: divisions }, { data: teams }] = await Promise.all([
    supabase.from("profiles").select("id, user_no_pk, login_id, name, position, status, division_id, team_id, created_at").order("user_no_pk"),
    supabase.from("divisions").select("id, name").order("name"),
    supabase.from("teams").select("id, name, division_id").order("name"),
  ]);
  if (error) throw new Error(error.message);
  return { users: profiles ?? [], divisions: divisions ?? [], teams: teams ?? [] };
}

const userPatchSchema = z.object({
  user_id: z.string().uuid(),
  name: z.string().min(1).max(50).optional(),
  position: z.enum(["과장", "팀장", "팀원", "서무"]).optional(),
  division_id: z.string().uuid().nullable().optional(),
  team_id: z.string().uuid().nullable().optional(),
  status: z.enum(["가입신청", "승인", "탈퇴"]).optional(),
});

export async function adminUpdateUser({ data: raw }: { data: z.infer<typeof userPatchSchema> }) {
  await assertAdmin();
  const data = userPatchSchema.parse(raw);
  const { user_id, ...patch } = data;
  const { error } = await supabase.from("profiles").update(patch).eq("id", user_id);
  if (error) throw new Error(error.message);
  return { ok: true };
}

export async function adminDeleteUser({ data }: { data: { user_id: string } }) {
  await assertAdmin();
  return apiRequest<{ ok: boolean }>("/admin/delete-user", {
    data: { user_id: z.string().uuid().parse(data.user_id) },
    auth: true,
  });
}

const nameSchema = z.object({ name: z.string().trim().min(1).max(50) });
const idSchema = z.object({ id: z.string().uuid() });
const namedIdSchema = idSchema.extend({ name: z.string().trim().min(1).max(50) });

export async function adminCreateDivision({ data: raw }: { data: { name: string } }) {
  await assertAdmin();
  const data = nameSchema.parse(raw);
  const { error } = await supabase.from("divisions").insert({ name: data.name });
  if (error) throw new Error(error.message);
  return { ok: true };
}

export async function adminUpdateDivision({ data: raw }: { data: { id: string; name: string } }) {
  await assertAdmin();
  const data = namedIdSchema.parse(raw);
  const { error } = await supabase.from("divisions").update({ name: data.name }).eq("id", data.id);
  if (error) throw new Error(error.message);
  return { ok: true };
}

export async function adminDeleteDivision({ data: raw }: { data: { id: string } }) {
  await assertAdmin();
  const data = idSchema.parse(raw);
  await supabase.from("profiles").update({ division_id: null, team_id: null }).eq("division_id", data.id);
  await supabase.from("teams").delete().eq("division_id", data.id);
  const { error } = await supabase.from("divisions").delete().eq("id", data.id);
  if (error) throw new Error(error.message);
  return { ok: true };
}

const teamSchema = z.object({
  name: z.string().trim().min(1).max(50),
  division_id: z.string().uuid(),
});
const teamUpdateSchema = teamSchema.extend({ id: z.string().uuid() });

export async function adminCreateTeam({ data: raw }: { data: z.infer<typeof teamSchema> }) {
  await assertAdmin();
  const data = teamSchema.parse(raw);
  const { error } = await supabase.from("teams").insert(data);
  if (error) throw new Error(error.message);
  return { ok: true };
}

export async function adminUpdateTeam({ data: raw }: { data: z.infer<typeof teamUpdateSchema> }) {
  await assertAdmin();
  const data = teamUpdateSchema.parse(raw);
  const { error } = await supabase.from("teams").update({ name: data.name, division_id: data.division_id }).eq("id", data.id);
  if (error) throw new Error(error.message);
  return { ok: true };
}

export async function adminDeleteTeam({ data: raw }: { data: { id: string } }) {
  await assertAdmin();
  const data = idSchema.parse(raw);
  await supabase.from("profiles").update({ team_id: null }).eq("team_id", data.id);
  const { error } = await supabase.from("teams").delete().eq("id", data.id);
  if (error) throw new Error(error.message);
  return { ok: true };
}

export async function adminCreateCategory({ data: raw }: { data: { name: string } }) {
  await assertAdmin();
  const data = nameSchema.parse(raw);
  const { data: category, error } = await supabase.from("task_categories").insert({ name: data.name }).select("id").single();
  if (error) throw new Error(error.message);
  const { error: templateError } = await supabase.from("templates").insert({ category_id: category.id, content: "" });
  if (templateError) throw new Error(templateError.message);
  return { ok: true };
}

export async function adminUpdateCategory({ data: raw }: { data: { id: string; name: string } }) {
  await assertAdmin();
  const data = namedIdSchema.parse(raw);
  const { error } = await supabase.from("task_categories").update({ name: data.name }).eq("id", data.id);
  if (error) throw new Error(error.message);
  return { ok: true };
}

export async function adminDeleteCategory({ data: raw }: { data: { id: string } }) {
  await assertAdmin();
  const data = idSchema.parse(raw);
  await supabase.from("tasks").update({ category_id: null }).eq("category_id", data.id);
  await supabase.from("templates").delete().eq("category_id", data.id);
  const { error } = await supabase.from("task_categories").delete().eq("id", data.id);
  if (error) throw new Error(error.message);
  return { ok: true };
}

export async function adminListTemplates() {
  await assertAdmin();
  const [{ data: categories, error }, { data: templates }] = await Promise.all([
    supabase.from("task_categories").select("id, name").order("name"),
    supabase.from("templates").select("category_id, content"),
  ]);
  if (error) throw new Error(error.message);
  return { categories: categories ?? [], templates: templates ?? [] };
}

const templateSchema = z.object({ category_id: z.string().uuid(), content: z.string().max(5000) });

export async function adminSaveTemplate({ data: raw }: { data: z.infer<typeof templateSchema> }) {
  await assertAdmin();
  const data = templateSchema.parse(raw);
  const { error } = await supabase.from("templates").upsert(
    { category_id: data.category_id, content: data.content, updated_at: new Date().toISOString() },
    { onConflict: "category_id" },
  );
  if (error) throw new Error(error.message);
  return { ok: true };
}
