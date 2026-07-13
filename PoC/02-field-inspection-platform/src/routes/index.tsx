import { createFileRoute, Link } from "@tanstack/react-router";
import { Shell } from "@/components/Shell";
import { useStore, store, taskStatusCounts, type Asset, type Result, type Task } from "@/lib/store";
import { ResultForm } from "@/components/ResultForm";
import { AssetPickerDialog } from "@/components/AssetPickerDialog";
import {
  ArrowUpRight,
  Building2,
  CheckCircle2,
  ClipboardCheck,
  FileClock,
  ListChecks,
  MapPin,
  Plus,
  Search,
  X,
} from "lucide-react";
import { useState } from "react";

export const Route = createFileRoute("/")({
  head: () => ({
    meta: [
      { title: "현장점검 지원플랫폼 · MinsLab" },
      { name: "description", content: "업무, 대상, 점검 결과와 통계를 한 화면에서 관리합니다." },
    ],
  }),
  component: Index,
});

function Index() {
  const tasks = useStore((s) => s.tasks);
  const state = useStore((s) => s);
  const completed = state.results.filter((result) => result.status === "점검완료").length;

  return (
    <Shell>
      <section className="dashboard-hero">
        <div className="dashboard-hero-copy">
          <div className="app-kicker">Field operations / PoC 02</div>
          <h1>현장점검을<br />한눈에 관리합니다.</h1>
          <p>
            점검 업무와 대상을 연결하고, 현장 기록부터 완료 현황과 통계까지
            하나의 흐름으로 확인하세요.
          </p>
          <div className="dashboard-mode">
            <i />
            공개 PoC 운영 중 · 관리자 및 데이터 편집 기능 공개
          </div>
        </div>

        <div className="dashboard-summary" aria-label="현장점검 요약">
          <SummaryCard icon={<ListChecks className="size-4" />} value={tasks.length} label="등록 업무" />
          <SummaryCard icon={<Building2 className="size-4" />} value={state.assets.length} label="점검 대상" />
          <SummaryCard icon={<FileClock className="size-4" />} value={state.results.length} label="전체 기록" />
          <SummaryCard icon={<CheckCircle2 className="size-4" />} value={completed} label="점검 완료" />
        </div>
      </section>

      <UnifiedAssetInput />

      <section className="mt-12">
        <div className="section-heading">
          <div>
            <div className="section-kicker">Inspection tasks</div>
            <h2>점검 업무 목록</h2>
            <p>업무 카드를 선택하면 기록 검색, 신규 등록과 CSV 다운로드를 이용할 수 있습니다.</p>
          </div>
          <span className="section-count">{tasks.length}개 업무</span>
        </div>

        {tasks.length === 0 ? (
          <div className="empty-state">
            <ClipboardCheck className="size-7" />
            <strong>등록된 점검 업무가 없습니다.</strong>
            <span>관리자 메뉴에서 첫 업무와 입력 서식을 등록해 주세요.</span>
          </div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-4">
            {tasks.map((task) => {
              const counts = taskStatusCounts(task.taskId, state);
              const completion = counts.total
                ? Math.round((counts.점검완료 / counts.total) * 100)
                : 0;

              return (
                <Link
                  key={task.taskId}
                  to="/tasks/$taskId"
                  params={{ taskId: task.taskId }}
                  className="task-card group"
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="task-card-icon">
                      <ClipboardCheck className="size-5" />
                    </div>
                    <ArrowUpRight className="task-card-arrow size-5" />
                  </div>

                  <h3>{task.taskName}</h3>
                  <div className="task-card-meta">
                    {task.department || "담당부서 미지정"}
                    {task.manager ? ` · ${task.manager}` : ""}
                  </div>

                  <div className="task-stats">
                    <Stat label="등록" value={counts.등록} />
                    <Stat label="점검중" value={counts.점검중} tone="progress" />
                    <Stat label="완료" value={counts.점검완료} tone="complete" />
                  </div>

                  <div className="progress-track" aria-label={`완료율 ${completion}%`}>
                    <div className="progress-fill" style={{ width: `${completion}%` }} />
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

function SummaryCard({
  icon,
  value,
  label,
}: {
  icon: React.ReactNode;
  value: number;
  label: string;
}) {
  return (
    <div className="summary-card">
      <div className="summary-card-icon">{icon}</div>
      <div>
        <b>{value}</b>
        <span>{label}</span>
      </div>
    </div>
  );
}

function Stat({
  label,
  value,
  tone = "default",
}: {
  label: string;
  value: number;
  tone?: "default" | "progress" | "complete";
}) {
  return (
    <div className={`status-stat ${tone === "progress" ? "is-progress" : tone === "complete" ? "is-complete" : ""}`}>
      <b>{value}</b>
      <span>{label}</span>
    </div>
  );
}

function UnifiedAssetInput() {
  const tasks = useStore((s) => s.tasks);
  const assets = useStore((s) => s.assets);
  const results = useStore((s) => s.results);
  const [assetId, setAssetId] = useState("");
  const [pickerOpen, setPickerOpen] = useState(false);
  const [activeTab, setActiveTab] = useState<string>("");
  const [savedFlash, setSavedFlash] = useState("");

  const selected = assets.find((asset) => asset.assetId === assetId);

  return (
    <section>
      <div className="section-heading">
        <div>
          <div className="section-kicker">Quick entry</div>
          <h2>물건별 통합 입력</h2>
          <p>점검 대상을 먼저 선택하면 연결된 모든 업무 기록을 한 자리에서 입력하고 수정할 수 있습니다.</p>
        </div>
      </div>

      <div className="asset-selector">
        <div className="asset-selector-value">
          {selected ? (
            <>
              <MapPin className="size-4 shrink-0 text-primary" />
              <strong>{selected.name}</strong>
              <span className="asset-meta">
                {selected.category} · {selected.sido} · {selected.address} {selected.addressDetail}
              </span>
              <button
                onClick={() => {
                  setAssetId("");
                  setActiveTab("");
                }}
                className="ml-auto grid size-7 shrink-0 place-items-center rounded-lg hover:bg-muted"
                aria-label="선택한 점검 대상 해제"
              >
                <X className="size-3.5" />
              </button>
            </>
          ) : (
            <span className="text-sm font-semibold text-muted-foreground">
              점검할 물건을 선택해 주세요.
            </span>
          )}
        </div>

        <button onClick={() => setPickerOpen(true)} className="app-secondary-button">
          <Search className="size-4" />
          점검 대상 찾기
        </button>
      </div>

      {selected && (() => {
        const visibleTasks = tasks.filter((task) =>
          results.some((result) => result.assetId === assetId && result.taskId === task.taskId),
        );

        if (visibleTasks.length === 0) {
          return (
            <div className="empty-state mt-4">
              <ClipboardCheck className="size-7" />
              <strong>연결된 점검 업무가 없습니다.</strong>
              <span>업무별 결과 화면에서 이 물건의 첫 점검 기록을 등록해 주세요.</span>
            </div>
          );
        }

        const currentTab = activeTab || visibleTasks[0].taskId;
        const activeTask = visibleTasks.find((task) => task.taskId === currentTab) ?? visibleTasks[0];

        return (
          <div className="workspace-card mt-4">
            <div className="workspace-tabs" aria-label="점검 업무 선택">
              {visibleTasks.map((task) => {
                const count = results.filter(
                  (result) => result.assetId === assetId && result.taskId === task.taskId,
                ).length;
                const active = activeTask.taskId === task.taskId;

                return (
                  <button
                    key={task.taskId}
                    onClick={() => setActiveTab(task.taskId)}
                    className={`record-tab ${active ? "is-active" : ""}`}
                  >
                    {task.taskName}
                    <span>{count}</span>
                  </button>
                );
              })}
            </div>

            <TaskAssetPanel
              key={`${assetId}-${activeTask.taskId}`}
              task={activeTask}
              asset={selected}
              onSaved={(name) => {
                setSavedFlash(`${name} 저장 완료`);
                setTimeout(() => setSavedFlash(""), 1800);
              }}
            />
          </div>
        );
      })()}

      {savedFlash && (
        <div className="save-toast">
          <CheckCircle2 className="size-4" />
          {savedFlash}
        </div>
      )}

      <AssetPickerDialog
        open={pickerOpen}
        onClose={() => setPickerOpen(false)}
        onPick={(asset) => {
          setAssetId(asset.assetId);
          setActiveTab("");
        }}
      />
    </section>
  );
}

function TaskAssetPanel({
  task,
  asset,
  onSaved,
}: {
  task: Task;
  asset: Asset;
  onSaved: (taskName: string) => void;
}) {
  const all = useStore((s) =>
    s.results
      .filter((result) => result.assetId === asset.assetId && result.taskId === task.taskId)
      .sort((a, b) => (a.createdAt < b.createdAt ? 1 : -1)),
  );
  const [editingId, setEditingId] = useState<string | "new">(all[0]?.resultId ?? "new");
  const current: Result | undefined =
    editingId === "new" ? undefined : all.find((result) => result.resultId === editingId);

  return (
    <div className="mt-5 space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <span className="section-kicker mr-1">Records</span>
        {all.map((result) => (
          <button
            key={result.resultId}
            onClick={() => setEditingId(result.resultId)}
            className={`record-tab ${editingId === result.resultId ? "is-active" : ""}`}
          >
            {result.year} · {result.inspector || "미지정"} · {result.status}
          </button>
        ))}
        <button
          onClick={() => setEditingId("new")}
          className={`record-tab ${editingId === "new" ? "is-active" : ""}`}
        >
          <Plus className="size-3" />
          신규 입력
        </button>
      </div>

      <ResultForm
        taskId={task.taskId}
        lockedAssetId={asset.assetId}
        initial={current}
        submitLabel={current ? "수정 저장" : "등록"}
        onSubmit={(payload) => {
          const { resultId: _resultId, ...rest } = payload;
          void _resultId;
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
