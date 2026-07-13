import { z } from "zod";
import { supabase } from "@/integrations/supabase/client";

async function currentUserId() {
  const { data, error } = await supabase.auth.getUser();
  if (error || !data.user) throw new Error("로그인이 필요합니다.");
  return data.user.id;
}

export async function getMyProfile() {
  const userId = await currentUserId();
  const { data: profile, error } = await supabase
    .from("profiles")
    .select("id, login_id, name, position, status, division_id, team_id, user_no_pk")
    .eq("id", userId)
    .maybeSingle();
  if (error) throw new Error(error.message);

  const [divisionResult, teamResult, roleResult] = await Promise.all([
    profile?.division_id
      ? supabase.from("divisions").select("name").eq("id", profile.division_id).maybeSingle()
      : Promise.resolve({ data: null }),
    profile?.team_id
      ? supabase.from("teams").select("name").eq("id", profile.team_id).maybeSingle()
      : Promise.resolve({ data: null }),
    supabase.from("user_roles").select("role").eq("user_id", userId),
  ]);

  return {
    profile: profile ?? null,
    divisionName: divisionResult.data?.name ?? null,
    teamName: teamResult.data?.name ?? null,
    isAdmin: (roleResult.data ?? []).some((row) => row.role === "admin"),
  };
}

const updateMeSchema = z.object({
  name: z.string().trim().min(1).max(50),
  position: z.enum(["과장", "팀장", "팀원", "서무"]),
  division_id: z.string().uuid().nullable(),
  team_id: z.string().uuid().nullable(),
  new_password: z.string().min(6).max(72).optional().nullable(),
});

export async function updateMyProfile({ data: raw }: { data: z.infer<typeof updateMeSchema> }) {
  const data = updateMeSchema.parse(raw);
  const userId = await currentUserId();
  const { error } = await supabase.from("profiles").update({
    name: data.name,
    position: data.position,
    division_id: data.division_id,
    team_id: data.position === "과장" ? null : data.team_id,
  }).eq("id", userId);
  if (error) throw new Error(error.message);
  if (data.new_password) {
    const { error: passwordError } = await supabase.auth.updateUser({ password: data.new_password });
    if (passwordError) throw new Error(passwordError.message);
  }
  return { ok: true };
}

export async function getProfileMeta() {
  const [{ data: divisions, error }, { data: teams }] = await Promise.all([
    supabase.from("divisions").select("id, name").order("name"),
    supabase.from("teams").select("id, name, division_id").order("name"),
  ]);
  if (error) throw new Error(error.message);
  return { divisions: divisions ?? [], teams: teams ?? [] };
}
