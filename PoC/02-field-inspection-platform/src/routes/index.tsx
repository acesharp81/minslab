import { createFileRoute, Link } from "@tanstack/react-router";
import { Shell } from "@/components/Shell";
import { useStore, store, taskStatusCounts, type Asset, type Result, type Task } from "@/lib/store";
import { ResultForm } from "@/components/ResultForm";
import { AssetPickerDialog } from "@/components/AssetPickerDialog";
import { ArrowUpRight, ClipboardCheck, MapPin, Search, X, Plus, ShieldCheck } from "lucide-react";
import { useMemo, useState } from "react";

export const Route = createFileRoute("/")({
  head: () => ({
    meta: [
      { title: "재난안전정보시스템 - 현장점검 지원플랫폼" },
      { name: "description", content: "Powered by Minisoft — 현장점검 지원 플랫폼" },
    ],
  }),
  component: Index,
});

function Index() {
  const tasks = useStore((s) => s.tasks);
  const state = useStore((s) => s);

  return (
    <Shell>
      <section className="mb-8">
        <div className="glass-strong rounded-3xl px-6 py-5 md:px-8 md:py-6 flex items-center gap-3">
          <div className="size-10 rounded-xl glass grid place-items-center">
            <ShieldCheck className="size-5 text-primary" />
          </div>
          <div>
            <div className="text-[11px] uppercase tracking-[0.2em] text-primary/90 font-medium">현장점검 플랫폼</div>
            <h1 className="text-lg md:text-xl font-semibold leading-tight">한 곳에서 끝내는 현장점검</h1>
          </div>
        </div>
      </section>

      <UnifiedAssetInput />

      <section className="mt-10">
        <div className="flex items-end justify-between mb-5">
          <div>
            <h2 className="text-xl font-semibold">점검 업무 목록</h2>
            <p className="text-sm text-muted-foreground">업무를 선택하면 점검 결과를 관리할 수 있습니다.</p>
          </div>
          <span className="text-sm text-muted-foreground">{tasks.length} tasks</span>
        </div>

        {tasks.length === 0 ? (
          <div className="glass rounded-2xl p-12 text-center text-muted-foreground">
            등록된 점검 업무가 없습니다. 관리자 메뉴에서 추가하세요.
          </div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5">
            {tasks.map((t) => {
              const m = taskStatusCounts(t.taskId, state);
              const pct = m.total ? Math.round((m.점검완료 / m.total) * 100) : 0;
              return (
                <Link key={t.taskId} to="/tasks/$taskId" params={{ taskId: t.taskId }}
                  className="group glass rounded-2xl p-6 hover:glass-strong transition-all relative overflow-hidden">
                  <div className="absolute -top-12 -right-12 size-40 rounded-full opacity-40 blur-3xl"
                       style={{ background: "oklch(0.72 0.22 290)" }} />
                  <div className="flex items-start justify-between gap-3 relative">
                    <div className="size-11 rounded-xl glass-strong grid place-items-center">
                      <ClipboardCheck className="size-5 text-primary" />
                    </div>
                    <ArrowUpRight className="size-5 text-muted-foreground group-hover:text-foreground group-hover:-translate-y-0.5 group-hover:translate-x-0.5 transition-transform" />
                  </div>
                  <h3 className="mt-5 text-lg font-semibold leading-snug relative">{t.taskName}</h3>
                  {t.department && <div className="text-xs text-muted-foreground mt-1">{t.department} · {t.manager}</div>}

                  <div className="mt-4 grid grid-cols-3 gap-2 text-center relative">
                    <Stat label="등록" value={m.등록} tone="muted" />
                    <Stat label="점검중" value={m.점검중} tone="accent" />
                    <Stat label="완료" value={m.점검완료} tone="primary" />
                  </div>
                  <div className="mt-4 h-1.5 rounded-full bg-white/10 overflow-hidden relative">
                    <div className="h-full rounded-full transition-all"
                      style={{ width: `${pct}%`, background: "linear-gradient(90deg, oklch(0.72 0.2 290), oklch(0.78 0.18 200))" }} />
                  </div>
                </Link>
              );
            })}
          </div>
        )}
      </section>
    </Shell>
  );
}

function Stat({ label, value, tone }: { label: string; value: number; tone: "muted" | "accent" | "primary" }) {
  const color = tone === "primary" ? "text-primary" : tone === "accent" ? "text-[color:oklch(0.78_0.18_200)]" : "text-foreground";
  return (
    <div className="glass rounded-xl py-2">
      <div className={`text-lg font-semibold ${color}`}>{value}</div>
      <div className="text-[11px] text-muted-foreground">{label}</div>
    </div>
  );
}

/* ============ 물건별 통합 입력 ============ */


function UnifiedAssetInput() {
  const tasks = useStore((s) => s.tasks);
  const assets = useStore((s) => s.assets);
  const results = useStore((s) => s.results);
  const [assetId, setAssetId] = useState("");
  const [pickerOpen, setPickerOpen] = useState(false);
  const [activeTab, setActiveTab] = useState<string>("");
  const [savedFlash, setSavedFlash] = useState("");

  const selected = assets.find((a) => a.assetId === assetId);

  return (
    <section>
      <div className="flex items-end justify-between mb-4">
        <div>
          <h2 className="text-xl font-semibold">물건별 통합 입력</h2>
          <p className="text-sm text-muted-foreground">물건을 선택하면 등록된 모든 점검 업무에 대해 한 화면에서 입력/수정할 수 있습니다.</p>
        </div>
      </div>

      <div className="glass-strong rounded-2xl p-4 flex gap-2 items-center mb-4">
        <div className="flex-1 glass rounded-xl px-4 py-2.5 flex items-center gap-2 min-h-[44px]">
          {selected ? (
            <>
              <MapPin className="size-4 text-primary" />
              <span className="font-medium">{selected.name}</span>
              <span className="text-xs text-muted-foreground">· [{selected.category}] {selected.sido} · {selected.address} {selected.addressDetail}</span>
              <button onClick={() => { setAssetId(""); setActiveTab(""); }}
                className="ml-auto size-6 grid place-items-center rounded hover:bg-white/10">
                <X className="size-3.5" />
              </button>
            </>
          ) : (
            <span className="text-muted-foreground/70 text-sm">물건을 선택해주세요</span>
          )}
        </div>
        <button onClick={() => setPickerOpen(true)}
          className="glass rounded-xl px-4 py-2.5 text-sm hover:bg-white/10 flex items-center gap-1.5">
          <Search className="size-4" /> 물건 검색
        </button>
      </div>

      {selected && (
        (() => {
          const visibleTasks = tasks.filter((t) =>
            results.some((r) => r.assetId === assetId && r.taskId === t.taskId)
          );
          if (visibleTasks.length === 0) {
            return (
              <div className="glass-strong rounded-2xl p-8 text-center text-muted-foreground">
                선택한 물건에 등록된 점검 업무가 없습니다.
              </div>
            );
          }
          const currentTab = activeTab || visibleTasks[0].taskId;
          const activeTask = visibleTasks.find((t) => t.taskId === currentTab) ?? visibleTasks[0];
          return (
            <div className="glass-strong rounded-2xl p-4 md:p-5">
              <div className="flex flex-wrap gap-1.5 mb-4">
                {visibleTasks.map((t) => {
                  const count = results.filter((r) => r.assetId === assetId && r.taskId === t.taskId).length;
                  const active = activeTask.taskId === t.taskId;
                  return (
                    <button key={t.taskId} onClick={() => setActiveTab(t.taskId)}
                      className={`px-3.5 py-2 rounded-xl text-sm border flex items-center gap-2 transition-colors ${active ? "bg-primary/20 border-primary/40 text-primary" : "glass border-transparent hover:bg-white/10"}`}>
                      {t.taskName}
                      <span className={`text-[10px] px-1.5 py-0.5 rounded-full ${active ? "bg-primary/30" : "bg-white/10"}`}>{count}</span>
                    </button>
                  );
                })}
              </div>

              <TaskAssetPanel
                key={`${assetId}-${activeTask.taskId}`}
                task={activeTask}
                asset={selected}
                onSaved={(name) => { setSavedFlash(`${name} 저장됨`); setTimeout(() => setSavedFlash(""), 1800); }}
              />
            </div>
          );
        })()
      )}

      {savedFlash && (
        <div className="fixed bottom-6 left-1/2 -translate-x-1/2 glass-strong rounded-xl px-4 py-2.5 text-sm z-40">
          {savedFlash}
        </div>
      )}

      <AssetPickerDialog open={pickerOpen} onClose={() => setPickerOpen(false)}
        onPick={(a) => { setAssetId(a.assetId); setActiveTab(""); }} />
    </section>
  );
}

function TaskAssetPanel({ task, asset, onSaved }: { task: Task; asset: Asset; onSaved: (taskName: string) => void }) {
  const all = useStore((s) =>
    s.results.filter((r) => r.assetId === asset.assetId && r.taskId === task.taskId)
      .sort((a, b) => (a.createdAt < b.createdAt ? 1 : -1)),
  );
  const [editingId, setEditingId] = useState<string | "new">(all[0]?.resultId ?? "new");
  const current: Result | undefined = editingId === "new" ? undefined : all.find((r) => r.resultId === editingId);

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap gap-2 items-center">
        <span className="text-xs uppercase tracking-wider text-muted-foreground mr-1">기록</span>
        {all.map((r) => (
          <button key={r.resultId} onClick={() => setEditingId(r.resultId)}
            className={`px-3 py-1.5 rounded-lg text-xs border ${editingId === r.resultId ? "bg-primary/20 border-primary/40 text-primary" : "glass border-transparent hover:bg-white/10"}`}>
            {r.year} · {r.inspector || "—"} · {r.status}
          </button>
        ))}
        <button onClick={() => setEditingId("new")}
          className={`px-3 py-1.5 rounded-lg text-xs border flex items-center gap-1 ${editingId === "new" ? "bg-primary/20 border-primary/40 text-primary" : "glass border-transparent hover:bg-white/10"}`}>
          <Plus className="size-3" /> 신규 입력
        </button>
      </div>

      <ResultForm
        taskId={task.taskId}
        lockedAssetId={asset.assetId}
        initial={current}
        submitLabel={current ? "수정 저장" : "등록"}
        onSubmit={(p) => {
          const { resultId: _r, ...rest } = p;
          void _r;
          if (current) {
            store.updateResult(current.resultId, rest);
          } else {
            const created = store.addResult(rest);
            setEditingId(created.resultId);
          }
          onSaved(task.taskName);
        }}
        onDelete={current ? () => {
          store.deleteResult(current.resultId);
          setEditingId("new");
        } : undefined}
      />
    </div>
  );
}
