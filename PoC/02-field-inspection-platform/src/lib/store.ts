import { useSyncExternalStore } from "react";
import { supabase } from "@/integrations/supabase/client";

export type AssetCategory = "시설물" | "산" | "하천" | "강";
export const ASSET_CATEGORIES: AssetCategory[] = ["시설물", "산", "하천", "강"];

export const SIDO_LIST = [
  "서울특별시", "부산광역시", "대구광역시", "인천광역시", "광주광역시",
  "대전광역시", "울산광역시", "세종특별자치시", "경기도", "강원특별자치도",
  "충청북도", "충청남도", "전북특별자치도", "전라남도", "경상북도",
  "경상남도", "제주특별자치도",
] as const;

export type InspectionStatus = "등록" | "점검중" | "점검완료";
export const STATUS_LIST: InspectionStatus[] = ["등록", "점검중", "점검완료"];

export type CustomFieldType = "text" | "number" | "photo";
export const CUSTOM_FIELD_TYPES: { value: CustomFieldType; label: string }[] = [
  { value: "text", label: "텍스트" },
  { value: "number", label: "숫자" },
  { value: "photo", label: "사진업로드" },
];

export interface CustomField {
  id: string;
  name: string;
  type: CustomFieldType;
  length: number;
}

export type CustomValue = string | number | string[];

export interface Asset {
  assetId: string;
  name: string;
  category: AssetCategory;
  address: string;
  addressDetail: string;
  sido: string;
}

export interface Task {
  taskId: string;
  taskName: string;
  purpose: string;
  content: string;
  department: string;
  manager: string;
  customFields: CustomField[];
}

export interface Result {
  resultId: string;
  taskId: string;
  createdAt: string;
  year: number;
  assetId: string;
  inspector: string;
  inspectedAt: string;
  status: InspectionStatus;
  confirmer: string;
  customValues: Record<string, CustomValue>;
}

interface State {
  tasks: Task[];
  assets: Asset[];
  results: Result[];
  loaded: boolean;
}

export function uid() {
  return Math.random().toString(36).slice(2, 10) + Math.random().toString(36).slice(2, 6);
}

function defaultCustomFields(): CustomField[] {
  return [
    { id: uid(), name: "점검항목", type: "text", length: 100 },
    { id: uid(), name: "점검결과", type: "text", length: 200 },
    { id: uid(), name: "점검사진", type: "photo", length: 4 },
  ];
}

// ---------- mapping helpers ----------
import type { Json } from "@/integrations/supabase/types";
type TaskRow = { task_id: string; task_name: string; purpose: string; content: string; department: string; manager: string; custom_fields: Json };
type AssetRow = { asset_id: string; name: string; category: string; address: string; address_detail: string; sido: string };
type ResultRow = { result_id: string; task_id: string; created_at: string; year: number; asset_id: string; inspector: string; inspected_at: string; status: string; confirmer: string; custom_values: Json };

const rowToTask = (r: TaskRow): Task => ({
  taskId: r.task_id, taskName: r.task_name, purpose: r.purpose, content: r.content,
  department: r.department, manager: r.manager,
  customFields: Array.isArray(r.custom_fields) ? (r.custom_fields as unknown as CustomField[]) : [],
});
const taskToRow = (t: Task): TaskRow => ({
  task_id: t.taskId, task_name: t.taskName, purpose: t.purpose, content: t.content,
  department: t.department, manager: t.manager, custom_fields: t.customFields as unknown as Json,
});
const rowToAsset = (r: AssetRow): Asset => ({
  assetId: r.asset_id, name: r.name, category: r.category as AssetCategory,
  address: r.address, addressDetail: r.address_detail, sido: r.sido,
});
const assetToRow = (a: Asset): AssetRow => ({
  asset_id: a.assetId, name: a.name, category: a.category,
  address: a.address, address_detail: a.addressDetail, sido: a.sido,
});
const rowToResult = (r: ResultRow): Result => ({
  resultId: r.result_id, taskId: r.task_id, createdAt: r.created_at, year: r.year,
  assetId: r.asset_id, inspector: r.inspector, inspectedAt: r.inspected_at,
  status: r.status as InspectionStatus, confirmer: r.confirmer,
  customValues: (r.custom_values as Record<string, CustomValue>) ?? {},
});
const resultToRow = (r: Result): ResultRow => ({
  result_id: r.resultId, task_id: r.taskId, created_at: r.createdAt, year: r.year,
  asset_id: r.assetId, inspector: r.inspector, inspected_at: r.inspectedAt,
  status: r.status, confirmer: r.confirmer, custom_values: r.customValues as unknown as Json,
});

// ---------- state ----------
let state: State = { tasks: [], assets: [], results: [], loaded: false };
const listeners = new Set<() => void>();
function emit() { listeners.forEach((l) => l()); }
function set(next: Partial<State>) { state = { ...state, ...next }; emit(); }

// ---------- seed ----------
async function seedIfEmpty() {
  const a1: Asset = { assetId: uid(), name: "강남구청사 본관", category: "시설물", address: "서울 강남구 학동로 426", addressDetail: "본관 3층", sido: "서울특별시" };
  const a2: Asset = { assetId: uid(), name: "북한산 백운대 구역", category: "산", address: "서울 강북구 우이동 산 14", addressDetail: "백운대 구간", sido: "서울특별시" };
  const a3: Asset = { assetId: uid(), name: "한강 잠수교 교각", category: "하천", address: "서울 서초구 반포동 1-1", addressDetail: "교각 12번", sido: "서울특별시" };

  const t1Fields = defaultCustomFields();
  const t2Fields = defaultCustomFields();
  const t1: Task = { taskId: uid(), taskName: "소방 시설 정기 점검", purpose: "화재 예방 및 시설 안전 확보", content: "소화전, 스프링클러, 경보 시스템 점검", department: "안전관리과", manager: "홍길동", customFields: t1Fields };
  const t2: Task = { taskId: uid(), taskName: "교량 안전 점검", purpose: "교량 구조 안전성 확인", content: "교각/난간/노면 균열 및 부식 점검", department: "시설관리과", manager: "이철수", customFields: t2Fields };

  const today = new Date().toISOString().slice(0, 10);
  const year = new Date().getFullYear();
  const mk = (taskId: string, fields: CustomField[], assetId: string, inspector: string, item: string, result: string, status: InspectionStatus, confirmer = ""): Result => ({
    resultId: uid(), taskId, createdAt: new Date().toISOString(), year, assetId, inspector,
    inspectedAt: today, status, confirmer,
    customValues: { [fields[0].id]: item, [fields[1].id]: result, [fields[2].id]: [] },
  });

  const tasks = [t1, t2];
  const assets = [a1, a2, a3];
  const results = [
    mk(t1.taskId, t1Fields, a1.assetId, "홍길동", "소화전 수압", "정상 작동 확인", "점검완료", "김감독"),
    mk(t1.taskId, t1Fields, a1.assetId, "김영희", "스프링클러", "노즐 1개 교체 필요", "점검중"),
    mk(t2.taskId, t2Fields, a3.assetId, "이철수", "교각 균열", "—", "등록"),
  ];

  await supabase.from("tasks").insert(tasks.map(taskToRow));
  await supabase.from("assets").insert(assets.map(assetToRow));
  await supabase.from("results").insert(results.map(resultToRow));
  return { tasks, assets, results };
}

// ---------- load ----------
let loadPromise: Promise<void> | null = null;
async function loadAll() {
  const [tasksRes, assetsRes, resultsRes] = await Promise.all([
    supabase.from("tasks").select("*").order("created_at"),
    supabase.from("assets").select("*").order("created_at"),
    supabase.from("results").select("*").order("created_at", { ascending: false }),
  ]);
  let tasks = (tasksRes.data ?? []).map((r) => rowToTask(r as TaskRow));
  let assets = (assetsRes.data ?? []).map((r) => rowToAsset(r as AssetRow));
  let results = (resultsRes.data ?? []).map((r) => rowToResult(r as ResultRow));

  if (tasks.length === 0 && assets.length === 0 && results.length === 0) {
    const seeded = await seedIfEmpty();
    tasks = seeded.tasks; assets = seeded.assets; results = seeded.results;
  }
  set({ tasks, assets, results, loaded: true });
}
function ensureLoaded() {
  if (typeof window === "undefined") return;
  if (!loadPromise) loadPromise = loadAll().catch((e) => { console.error("[store] load failed", e); });
}

// ---------- store ----------
function reportError(label: string, err: unknown) {
  console.error(`[store] ${label}`, err);
}

export const store = {
  get: () => state,
  subscribe(l: () => void) {
    listeners.add(l);
    ensureLoaded();
    return () => { listeners.delete(l); };
  },
  reload: () => { loadPromise = null; ensureLoaded(); },

  addTask(input: Omit<Task, "taskId">) {
    const t: Task = { ...input, taskId: uid() };
    set({ tasks: [...state.tasks, t] });
    supabase.from("tasks").insert(taskToRow(t)).then(({ error }) => error && reportError("addTask", error));
    return t;
  },
  updateTask(id: string, patch: Partial<Task>) {
    const next = state.tasks.map((t) => (t.taskId === id ? { ...t, ...patch } : t));
    set({ tasks: next });
    const t = next.find((x) => x.taskId === id);
    if (t) {
      const { task_id, ...rest } = taskToRow(t);
      supabase.from("tasks").update(rest).eq("task_id", task_id).then(({ error }) => error && reportError("updateTask", error));
    }
  },
  deleteTask(id: string) {
    set({
      tasks: state.tasks.filter((t) => t.taskId !== id),
      results: state.results.filter((r) => r.taskId !== id),
    });
    supabase.from("tasks").delete().eq("task_id", id).then(({ error }) => error && reportError("deleteTask", error));
  },

  addAsset(input: Omit<Asset, "assetId">) {
    const a: Asset = { ...input, assetId: uid() };
    set({ assets: [...state.assets, a] });
    supabase.from("assets").insert(assetToRow(a)).then(({ error }) => error && reportError("addAsset", error));
    return a;
  },
  updateAsset(id: string, patch: Partial<Asset>) {
    const next = state.assets.map((a) => (a.assetId === id ? { ...a, ...patch } : a));
    set({ assets: next });
    const a = next.find((x) => x.assetId === id);
    if (a) {
      const { asset_id, ...rest } = assetToRow(a);
      supabase.from("assets").update(rest).eq("asset_id", asset_id).then(({ error }) => error && reportError("updateAsset", error));
    }
  },
  deleteAsset(id: string) {
    set({ assets: state.assets.filter((a) => a.assetId !== id) });
    supabase.from("assets").delete().eq("asset_id", id).then(({ error }) => error && reportError("deleteAsset", error));
  },

  addResult(input: Omit<Result, "resultId" | "createdAt">) {
    const r: Result = { ...input, resultId: uid(), createdAt: new Date().toISOString() };
    set({ results: [r, ...state.results] });
    supabase.from("results").insert(resultToRow(r)).then(({ error }) => error && reportError("addResult", error));
    return r;
  },
  updateResult(id: string, patch: Partial<Result>) {
    const next = state.results.map((r) => (r.resultId === id ? { ...r, ...patch } : r));
    set({ results: next });
    const r = next.find((x) => x.resultId === id);
    if (r) {
      const { result_id, created_at, ...rest } = resultToRow(r);
      void created_at;
      supabase.from("results").update(rest).eq("result_id", result_id).then(({ error }) => error && reportError("updateResult", error));
    }
  },
  deleteResult(id: string) {
    set({ results: state.results.filter((r) => r.resultId !== id) });
    supabase.from("results").delete().eq("result_id", id).then(({ error }) => error && reportError("deleteResult", error));
  },
};

export function useStoreState(): State {
  return useSyncExternalStore(store.subscribe, store.get, store.get);
}
export function useStore<T>(selector: (s: State) => T): T {
  return selector(useStoreState());
}

export function taskStatusCounts(taskId: string, s: State = store.get()) {
  const list = s.results.filter((r) => r.taskId === taskId);
  return {
    total: list.length,
    등록: list.filter((r) => r.status === "등록").length,
    점검중: list.filter((r) => r.status === "점검중").length,
    점검완료: list.filter((r) => r.status === "점검완료").length,
  };
}

export function summarizeResult(r: Result, task?: Task): string {
  if (!task) return "";
  const f = task.customFields.find((cf) => cf.type !== "photo");
  if (!f) return "";
  const v = r.customValues?.[f.id];
  return v == null ? "" : String(v);
}

export const YEAR_OPTIONS = Array.from({ length: 51 }, (_, i) => 2000 + i);
