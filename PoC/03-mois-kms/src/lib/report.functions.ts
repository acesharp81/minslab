import { z } from "zod";
import { supabase } from "@/integrations/supabase/client";
import { apiRequest } from "./api";

export type ReportAISettings = {
  model: string;
  temperature: number;
  max_tokens: number;
  system_prompt?: string;
};

const aiSettingsSchema = z.object({
  model: z.string().max(200).default(""),
  temperature: z.number().min(0).max(1.5).default(0.2),
  max_tokens: z.number().int().min(128).max(4096).default(1200),
  system_prompt: z.string().max(8000).optional().default(""),
});

const SINGLE_SYSTEM =
  "당신은 한국 공공기관과 기업의 업무 보고서를 작성하는 전문 비서입니다. 주어진 업무 메타데이터와 템플릿을 바탕으로 1장짜리 중앙부처 개조식 보고서를 자연스러운 한국어로 작성합니다.";
const MONTHLY_SYSTEM =
  "당신은 부서 단위 월간 업무 보고서를 작성하는 전문 비서입니다. 주어진 업무별 메타데이터와 월간계획 템플릿을 바탕으로 업무별 월간계획 보고서를 한국어로 작성합니다.";
const WEEKLY_SYSTEM =
  "당신은 부서 단위 주간 업무 보고서를 작성하는 전문 비서입니다. 주어진 업무별 메타데이터와 주간계획 템플릿을 바탕으로 업무별 주간계획 보고서를 한국어로 작성합니다.";

async function currentUserId() {
  const { data, error } = await supabase.auth.getUser();
  if (error || !data.user) throw new Error("로그인이 필요합니다.");
  return data.user.id;
}

async function callSelectedAI(system: string, prompt: string, rawSettings: ReportAISettings) {
  const settings = aiSettingsSchema.parse(rawSettings);
  return apiRequest<{ report: string; model: string; provider: string; elapsed_seconds: number }>("/report", {
    data: {
      ...settings,
      system: settings.system_prompt.trim() || system,
      prompt,
    },
    auth: true,
  });
}

export async function generateTaskReport({ data: raw }: { data: { taskId: string } & ReportAISettings }) {
  const taskId = z.string().uuid().parse(raw.taskId);
  const { data: task, error } = await supabase
    .from("tasks")
    .select("id, title, purpose, content, method, location, datetime, attendees, category_id, author_id")
    .eq("id", taskId)
    .maybeSingle();
  if (error || !task) throw new Error("업무를 찾을 수 없습니다.");

  const [authorResult, categoryResult, templateResult] = await Promise.all([
    supabase.from("profiles").select("name, position").eq("id", task.author_id).maybeSingle(),
    task.category_id
      ? supabase.from("task_categories").select("name").eq("id", task.category_id).maybeSingle()
      : Promise.resolve({ data: null }),
    task.category_id
      ? supabase.from("templates").select("content").eq("category_id", task.category_id).maybeSingle()
      : Promise.resolve({ data: null }),
  ]);
  const date = new Date(task.datetime);
  const dateText = `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")} ${String(date.getHours()).padStart(2, "0")}:${String(date.getMinutes()).padStart(2, "0")}`;
  const prompt = [
    `작성자: ${authorResult.data?.name ?? ""} (${authorResult.data?.position ?? ""})`,
    `분류: ${categoryResult.data?.name ?? "해당없음"}`,
    "",
    `Prompt.Meta: #제목=${task.title}, #목적=${task.purpose}, #내용=${task.content}, #방식=${task.method}, #장소=${task.location ?? "해당없음"}, #일시=${dateText}, #참석자=${task.attendees}`,
    "",
    templateResult.data?.content
      ? `업무 템플릿:\n${templateResult.data.content}`
      : "업무 템플릿: 지정된 템플릿 없음 — 중앙부처 개조식 1장 표준 양식 사용",
    "",
    "템플릿 양식에 업무 메타데이터를 충실히 반영해 검토 가능한 보고서 초안을 작성하세요.",
  ].join("\n");
  return callSelectedAI(SINGLE_SYSTEM, prompt, raw);
}

function weekRange(year: number, month: number, week: number) {
  const monthStart = new Date(year, month - 1, 1);
  const monthEnd = new Date(year, month, 0);
  const start = new Date(year, month - 1, (week - 1) * 7 + 1);
  let end = new Date(year, month - 1, week * 7);
  if (end > monthEnd) end = monthEnd;
  if (start > monthEnd) return { start: monthStart, end: monthEnd };
  return { start, end };
}

async function loadDivisionTasks(userId: string, startISO: string, endExclusiveISO: string) {
  const { data: me } = await supabase.from("profiles").select("position, division_id").eq("id", userId).maybeSingle();
  if (!me) throw new Error("프로필을 찾을 수 없습니다.");
  if (me.position !== "서무") throw new Error("부서 보고서는 서무만 생성할 수 있습니다.");
  if (!me.division_id) throw new Error("부서가 지정되어 있지 않습니다.");

  const { data: rows, error } = await supabase
    .from("tasks")
    .select("id, title, purpose, content, method, location, datetime, attendees, step, author_id, category_id")
    .gte("datetime", startISO)
    .lt("datetime", endExclusiveISO)
    .order("datetime", { ascending: true });
  if (error) throw new Error(error.message);
  const tasks = rows ?? [];
  if (!tasks.length) return { tasks: [] as any[], divisionName: "" };

  const authorIds = Array.from(new Set(tasks.map((task) => task.author_id)));
  const { data: authors } = await supabase.from("profiles").select("id, name, position, division_id, team_id").in("id", authorIds);
  const authorMap = new Map((authors ?? []).map((author) => [author.id, author]));
  const teamIds = Array.from(new Set((authors ?? []).map((author) => author.team_id).filter((id): id is string => Boolean(id))));
  const { data: teams } = teamIds.length
    ? await supabase.from("teams").select("id, name").in("id", teamIds)
    : { data: [] as { id: string; name: string }[] };
  const teamMap = new Map((teams ?? []).map((team) => [team.id, team.name]));
  const { data: division } = await supabase.from("divisions").select("name").eq("id", me.division_id).maybeSingle();
  const filtered = tasks.filter((task) => authorMap.get(task.author_id)?.division_id === me.division_id);
  return {
    tasks: filtered.map((task) => {
      const author = authorMap.get(task.author_id);
      return {
        ...task,
        author_name: author?.name ?? "",
        author_position: author?.position ?? "",
        team_name: author?.team_id ? teamMap.get(author.team_id) ?? "해당없음" : "해당없음",
      };
    }),
    divisionName: division?.name ?? "",
  };
}

function formatTasksAsPromptMeta(tasks: any[]) {
  return tasks.map((task, index) => {
    const date = new Date(task.datetime);
    const dateText = `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")} ${String(date.getHours()).padStart(2, "0")}:${String(date.getMinutes()).padStart(2, "0")}`;
    return `[업무 ${index + 1}] Prompt.Meta: #제목=${task.title}, #목적=${task.purpose}, #내용=${task.content}, #방식=${task.method}, #장소=${task.location ?? "해당없음"}, #일시=${dateText}, #참석자=${task.attendees}`;
  }).join("\n\n");
}

export async function generateMonthlyDivisionReport({ data: raw }: { data: { year: number; month: number } & ReportAISettings }) {
  const input = z.object({ year: z.number().int().min(2000).max(2100), month: z.number().int().min(1).max(12) }).parse(raw);
  const userId = await currentUserId();
  const startISO = new Date(Date.UTC(input.year, input.month - 1, 1)).toISOString();
  const endISO = new Date(Date.UTC(input.year, input.month, 1)).toISOString();
  const { tasks, divisionName } = await loadDivisionTasks(userId, startISO, endISO);
  if (!tasks.length) throw new Error("해당 월에 보고할 업무가 없습니다.");
  const { data: template } = await supabase.from("templates").select("content, task_categories!inner(name)").eq("task_categories.name", "월간보고템플릿").maybeSingle();
  const prompt = [
    "# 보고 대상",
    `- 부서: ${divisionName}`,
    `- 기간: ${input.year}년 ${input.month}월`,
    `- 업무 수: ${tasks.length}건`,
    "",
    formatTasksAsPromptMeta(tasks),
    "",
    template?.content ? `월간계획 템플릿:\n${template.content}` : "월간계획 템플릿: 지정된 템플릿 없음 — 표준 월간보고 양식 사용",
    "",
    "월간계획 템플릿에 맞춰 업무별 보고서 초안을 작성하세요.",
  ].join("\n");
  const result = await callSelectedAI(MONTHLY_SYSTEM, prompt, raw);
  return { ...result, divisionName, taskCount: tasks.length };
}

export async function generateWeeklyDivisionReport({ data: raw }: { data: { year: number; month: number; week: number } & ReportAISettings }) {
  const input = z.object({
    year: z.number().int().min(2000).max(2100),
    month: z.number().int().min(1).max(12),
    week: z.number().int().min(1).max(5),
  }).parse(raw);
  const userId = await currentUserId();
  const { start, end } = weekRange(input.year, input.month, input.week);
  const endExclusive = new Date(end);
  endExclusive.setDate(endExclusive.getDate() + 1);
  const { tasks, divisionName } = await loadDivisionTasks(userId, start.toISOString(), endExclusive.toISOString());
  if (!tasks.length) throw new Error("해당 주에 보고할 업무가 없습니다.");
  const { data: template } = await supabase.from("templates").select("content, task_categories!inner(name)").eq("task_categories.name", "주간보고템플릿").maybeSingle();
  const fmt = (date: Date) => `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
  const prompt = [
    "# 보고 대상",
    `- 부서: ${divisionName}`,
    `- 기간: ${fmt(start)} ~ ${fmt(end)} (${input.month}월 ${input.week}주차)`,
    `- 업무 수: ${tasks.length}건`,
    "",
    formatTasksAsPromptMeta(tasks),
    "",
    template?.content ? `주간계획 템플릿:\n${template.content}` : "주간계획 템플릿: 지정된 템플릿 없음 — 표준 주간보고 양식 사용",
    "",
    "주간계획 템플릿에 맞춰 업무별 보고서 초안을 작성하세요.",
  ].join("\n");
  const result = await callSelectedAI(WEEKLY_SYSTEM, prompt, raw);
  return {
    ...result,
    divisionName,
    taskCount: tasks.length,
    range: { start: fmt(start), end: fmt(end) },
  };
}
