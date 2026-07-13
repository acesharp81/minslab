import { z } from "zod";
import { supabase } from "@/integrations/supabase/client";

const monthInput = z.object({
  year: z.number().int().min(2000).max(2100),
  month: z.number().int().min(1).max(12),
});

export type TaskRow = {
  id: string;
  task_no_pk: number;
  title: string;
  purpose: string;
  content: string;
  method: "온라인" | "오프라인";
  location: string | null;
  datetime: string;
  attendees: string;
  step:
    | "팀원저장"
    | "팀원등록"
    | "팀장검토"
    | "팀장저장"
    | "팀장등록"
    | "팀장반려"
    | "과장승인"
    | "과장반려";
  category_id: string | null;
  author_id: string;
  author_name: string;
  author_position: "과장" | "팀장" | "팀원" | "서무";
  author_team_id: string | null;
  author_team_name: string | null;
  category_name: string | null;
  created_at: string;
  updated_at: string;
};

function monthRange(year: number, month: number) {
  return {
    start: new Date(Date.UTC(year, month - 1, 1)).toISOString(),
    end: new Date(Date.UTC(year, month, 1)).toISOString(),
  };
}

async function currentUserId() {
  const { data, error } = await supabase.auth.getUser();
  if (error || !data.user) throw new Error("로그인이 필요합니다.");
  return data.user.id;
}

const COMPLETED_STEPS = new Set(["과장승인"]);

export async function listTasksForMonth({ data: raw }: { data: z.infer<typeof monthInput> }) {
  const data = monthInput.parse(raw);
  const { start, end } = monthRange(data.year, data.month);
  const { data: rows, error } = await supabase
    .from("tasks")
    .select("id, task_no_pk, title, purpose, content, method, location, datetime, attendees, step, category_id, author_id, created_at, updated_at")
    .gte("datetime", start)
    .lt("datetime", end)
    .order("datetime", { ascending: true });
  if (error) throw new Error(error.message);
  if (!rows?.length) return { tasks: [] as TaskRow[] };

  const authorIds = Array.from(new Set(rows.map((row) => row.author_id)));
  const categoryIds = Array.from(new Set(rows.map((row) => row.category_id).filter((id): id is string => Boolean(id))));
  const [{ data: authors }, { data: categories }] = await Promise.all([
    supabase.from("profiles").select("id, name, position, team_id").in("id", authorIds),
    categoryIds.length
      ? supabase.from("task_categories").select("id, name").in("id", categoryIds)
      : Promise.resolve({ data: [] as { id: string; name: string }[] }),
  ]);
  const authorMap = new Map((authors ?? []).map((author) => [author.id, author]));
  const categoryMap = new Map((categories ?? []).map((category) => [category.id, category.name]));
  const teamIds = Array.from(new Set((authors ?? []).map((author) => author.team_id).filter((id): id is string => Boolean(id))));
  const { data: teams } = teamIds.length
    ? await supabase.from("teams").select("id, name").in("id", teamIds)
    : { data: [] as { id: string; name: string }[] };
  const teamMap = new Map((teams ?? []).map((team) => [team.id, team.name]));

  return {
    tasks: rows.map((row) => {
      const author = authorMap.get(row.author_id);
      const teamId = author?.team_id ?? null;
      return {
        ...row,
        author_name: author?.name ?? "(알 수 없음)",
        author_position: (author?.position ?? "팀원") as TaskRow["author_position"],
        author_team_id: teamId,
        author_team_name: teamId ? teamMap.get(teamId) ?? null : null,
        category_name: row.category_id ? categoryMap.get(row.category_id) ?? null : null,
      } as TaskRow;
    }),
  };
}

export function isTaskCompleted(step: TaskRow["step"]) {
  return COMPLETED_STEPS.has(step);
}

export const TASK_STEPS = [
  "팀원저장", "팀원등록", "팀장검토", "팀장저장",
  "팀장등록", "팀장반려", "과장승인", "과장반려",
] as const;

const taskBaseSchema = z.object({
  title: z.string().trim().min(1).max(120),
  category_id: z.string().uuid().nullable(),
  purpose: z.string().trim().min(1).max(2000),
  content: z.string().trim().min(1).max(5000),
  method: z.enum(["온라인", "오프라인"]),
  location: z.string().trim().max(200).nullable(),
  datetime: z.string().min(10),
  attendees: z.string().trim().min(1).max(500),
});
const createSchema = taskBaseSchema.extend({ intent: z.enum(["save", "submit"]) });
const updateSchema = taskBaseSchema.extend({ id: z.string().uuid(), intent: z.enum(["save", "submit"]) });

function stepForCreate(position: TaskRow["author_position"], intent: "save" | "submit"): TaskRow["step"] {
  if (intent === "save") return position === "팀원" ? "팀원저장" : "팀장저장";
  if (position === "팀원") return "팀장검토";
  if (position === "팀장") return "팀장등록";
  return "과장승인";
}

async function loadMyProfile(userId: string) {
  const { data, error } = await supabase
    .from("profiles")
    .select("id, position, team_id, division_id, status")
    .eq("id", userId)
    .maybeSingle();
  if (error || !data) throw new Error("프로필을 찾을 수 없습니다.");
  if (data.status !== "승인") throw new Error("승인된 계정만 사용할 수 있습니다.");
  return data;
}

export async function createTask({ data: raw }: { data: z.infer<typeof createSchema> }) {
  const data = createSchema.parse(raw);
  const userId = await currentUserId();
  const profile = await loadMyProfile(userId);
  const step = stepForCreate(profile.position, data.intent);
  const { error } = await supabase.from("tasks").insert({
    author_id: userId,
    title: data.title,
    category_id: data.category_id,
    purpose: data.purpose,
    content: data.content,
    method: data.method,
    location: data.method === "오프라인" ? data.location : null,
    datetime: data.datetime,
    attendees: data.attendees,
    step,
  });
  if (error) throw new Error(error.message);
  return { ok: true, step };
}

export async function updateTask({ data: raw }: { data: z.infer<typeof updateSchema> }) {
  const data = updateSchema.parse(raw);
  const userId = await currentUserId();
  const profile = await loadMyProfile(userId);
  const { data: existing, error: fetchError } = await supabase
    .from("tasks")
    .select("id, author_id, step")
    .eq("id", data.id)
    .maybeSingle();
  if (fetchError || !existing) throw new Error("업무를 찾을 수 없습니다.");
  if (existing.author_id !== userId) throw new Error("본인 업무만 수정할 수 있습니다.");
  if (COMPLETED_STEPS.has(existing.step)) throw new Error("등록 완료된 업무는 수정할 수 없습니다.");
  const step = stepForCreate(profile.position, data.intent);
  const { error } = await supabase.from("tasks").update({
    title: data.title,
    category_id: data.category_id,
    purpose: data.purpose,
    content: data.content,
    method: data.method,
    location: data.method === "오프라인" ? data.location : null,
    datetime: data.datetime,
    attendees: data.attendees,
    step,
  }).eq("id", data.id);
  if (error) throw new Error(error.message);
  return { ok: true, step };
}

export async function deleteTask({ data }: { data: { id: string } }) {
  const id = z.string().uuid().parse(data.id);
  const userId = await currentUserId();
  const { data: existing } = await supabase.from("tasks").select("author_id").eq("id", id).maybeSingle();
  if (!existing) throw new Error("업무를 찾을 수 없습니다.");
  if (existing.author_id !== userId) throw new Error("본인 업무만 삭제할 수 있습니다.");
  const { error } = await supabase.from("tasks").delete().eq("id", id);
  if (error) throw new Error(error.message);
  return { ok: true };
}

export type WorkflowAction = "보완" | "반려" | "검토완료" | "승인";
const transitionSchema = z.object({ id: z.string().uuid(), action: z.enum(["보완", "반려", "검토완료", "승인"]) });

export async function transitionTask({ data: raw }: { data: z.infer<typeof transitionSchema> }) {
  const data = transitionSchema.parse(raw);
  const userId = await currentUserId();
  const me = await loadMyProfile(userId);
  const { data: task } = await supabase.from("tasks").select("id, author_id, step").eq("id", data.id).maybeSingle();
  if (!task) throw new Error("업무를 찾을 수 없습니다.");
  const { data: author } = await supabase.from("profiles").select("team_id, division_id").eq("id", task.author_id).maybeSingle();
  if (!author) throw new Error("작성자 정보를 찾을 수 없습니다.");

  const isLeader = me.position === "팀장" && me.team_id != null && author.team_id === me.team_id;
  const isManager = (me.position === "과장" || me.position === "서무") && me.division_id != null && author.division_id === me.division_id;
  let nextStep: TaskRow["step"] | null = null;
  if (task.step === "팀장검토" && isLeader) {
    if (data.action === "검토완료") nextStep = "팀원등록";
    if (data.action === "보완") nextStep = "팀원저장";
    if (data.action === "반려") nextStep = "팀장반려";
  } else if (task.step === "팀장등록" && isManager) {
    if (data.action === "승인") nextStep = "과장승인";
    if (data.action === "반려") nextStep = "과장반려";
  }
  if (!nextStep) throw new Error("해당 단계에서 수행할 수 없는 작업입니다.");
  const { error } = await supabase.from("tasks").update({ step: nextStep }).eq("id", data.id);
  if (error) throw new Error(error.message);
  return { ok: true, step: nextStep };
}

export async function listCategories() {
  const { data, error } = await supabase.from("task_categories").select("id, name, is_default").order("name");
  if (error) throw new Error(error.message);
  const reserved = new Set(["월간보고템플릿", "주간보고템플릿"]);
  return { categories: (data ?? []).filter((category) => !reserved.has(category.name)) };
}
