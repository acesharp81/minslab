import { createFileRoute, Link } from "@tanstack/react-router";
import { Shell } from "@/components/Shell";
import { SIDO_LIST, STATUS_LIST, useStore, type InspectionStatus } from "@/lib/store";
import { AssetPickerDialog } from "@/components/AssetPickerDialog";
import { useMemo, useState } from "react";
import { BarChart3, MapPin, Search, X } from "lucide-react";

export const Route = createFileRoute("/statistics")({
  component: Statistics,
  head: () => ({
    meta: [{ title: "통계 — 재난안전정보시스템" }],
  }),
});

function Statistics() {
  const [tab, setTab] = useState<"jurisdiction" | "asset">("jurisdiction");
  return (
    <Shell>
      <div className="mb-6 flex items-center gap-3">
        <div className="size-10 rounded-xl glass-strong grid place-items-center">
          <BarChart3 className="size-5 text-primary" />
        </div>
        <div>
          <div className="text-xs uppercase tracking-[0.2em] text-muted-foreground">Statistics</div>
          <h1 className="text-2xl font-semibold">통계</h1>
        </div>
      </div>

      <div className="glass-strong rounded-2xl p-1.5 inline-flex gap-1 mb-5">
        <TabBtn active={tab === "jurisdiction"} onClick={() => setTab("jurisdiction")}>업무 · 관할지별</TabBtn>
        <TabBtn active={tab === "asset"} onClick={() => setTab("asset")}>물건별</TabBtn>
      </div>

      {tab === "jurisdiction" ? <JurisdictionStats /> : <AssetStats />}
    </Shell>
  );
}

function TabBtn({ active, onClick, children }: { active: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button onClick={onClick}
      className={`px-4 py-2 rounded-xl text-sm transition-colors ${active ? "bg-white/15 text-foreground" : "text-muted-foreground hover:bg-white/5"}`}>
      {children}
    </button>
  );
}

function StatusPill({ status, value }: { status: InspectionStatus; value: number }) {
  const tone =
    status === "점검완료" ? "bg-primary/20 text-primary" :
    status === "점검중" ? "bg-[color:oklch(0.78_0.18_200/.2)] text-[color:oklch(0.85_0.15_200)]" :
    "bg-white/10 text-muted-foreground";
  return (
    <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs ${tone}`}>
      {status} <span className="font-semibold">{value}</span>
    </span>
  );
}

function JurisdictionStats() {
  const tasks = useStore((s) => s.tasks);
  const results = useStore((s) => s.results);
  const assets = useStore((s) => s.assets);
  const [taskId, setTaskId] = useState<string>(tasks[0]?.taskId ?? "");

  const assetSido = useMemo(() => Object.fromEntries(assets.map((a) => [a.assetId, a.sido])), [assets]);

  const rows = useMemo(() => {
    const filtered = results.filter((r) => r.taskId === taskId);
    return SIDO_LIST.map((sido) => {
      const list = filtered.filter((r) => assetSido[r.assetId] === sido);
      return {
        sido,
        total: list.length,
        등록: list.filter((r) => r.status === "등록").length,
        점검중: list.filter((r) => r.status === "점검중").length,
        점검완료: list.filter((r) => r.status === "점검완료").length,
      };
    }).filter((r) => r.total > 0);
  }, [results, taskId, assetSido]);

  if (tasks.length === 0) {
    return <div className="glass rounded-2xl p-10 text-center text-muted-foreground">등록된 업무가 없습니다.</div>;
  }

  return (
    <div className="space-y-5">
      <div className="glass-strong rounded-2xl p-4 flex flex-wrap gap-2 items-center">
        <span className="text-xs uppercase tracking-wider text-muted-foreground mr-2">점검 업무</span>
        {tasks.map((t) => (
          <button key={t.taskId} onClick={() => setTaskId(t.taskId)}
            className={`px-3 py-1.5 rounded-lg text-sm border ${taskId === t.taskId ? "bg-primary/25 border-primary/50 text-primary" : "glass border-transparent hover:bg-white/10"}`}>
            {t.taskName}
          </button>
        ))}
      </div>

      <div className="glass rounded-2xl overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-xs uppercase tracking-wider text-muted-foreground border-b border-white/10">
              <th className="px-4 py-3 font-medium">관할 시도</th>
              <th className="px-4 py-3 font-medium text-center">총합</th>
              <th className="px-4 py-3 font-medium text-center">등록</th>
              <th className="px-4 py-3 font-medium text-center">점검중</th>
              <th className="px-4 py-3 font-medium text-center">점검완료</th>
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 ? (
              <tr><td colSpan={5} className="px-4 py-10 text-center text-muted-foreground">해당 업무에 등록된 점검 결과가 없습니다.</td></tr>
            ) : rows.map((r) => (
              <tr key={r.sido} className="border-b border-white/5 last:border-0">
                <td className="px-4 py-3 font-medium">{r.sido}</td>
                <td className="px-4 py-3 text-center font-semibold">{r.total}</td>
                <td className="px-4 py-3 text-center">{r.등록}</td>
                <td className="px-4 py-3 text-center text-[color:oklch(0.85_0.15_200)]">{r.점검중}</td>
                <td className="px-4 py-3 text-center text-primary font-semibold">{r.점검완료}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function AssetStats() {
  const assets = useStore((s) => s.assets);
  const tasks = useStore((s) => s.tasks);
  const results = useStore((s) => s.results);
  const [assetId, setAssetId] = useState<string>("");
  const [pickerOpen, setPickerOpen] = useState(false);

  const selected = assets.find((a) => a.assetId === assetId);

  const taskRows = useMemo(() => {
    if (!assetId) return [];
    return tasks.map((t) => {
      const list = results.filter((r) => r.assetId === assetId && r.taskId === t.taskId);
      return {
        task: t,
        total: list.length,
        등록: list.filter((r) => r.status === "등록").length,
        점검중: list.filter((r) => r.status === "점검중").length,
        점검완료: list.filter((r) => r.status === "점검완료").length,
        items: list,
      };
    }).filter((r) => r.total > 0);
  }, [assetId, tasks, results]);

  return (
    <div className="space-y-5">
      <div className="glass-strong rounded-2xl p-4 flex gap-2 items-center">
        <div className="flex-1 glass rounded-xl px-4 py-2.5 flex items-center gap-2 min-h-[44px]">
          {selected ? (
            <>
              <MapPin className="size-4 text-primary" />
              <span className="font-medium">{selected.name}</span>
              <span className="text-xs text-muted-foreground">· [{selected.category}] {selected.sido}</span>
              <button onClick={() => setAssetId("")} className="ml-auto size-6 grid place-items-center rounded hover:bg-white/10">
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

      {!selected ? (
        <div className="glass rounded-2xl p-12 text-center text-muted-foreground">물건을 선택하면 점검 업무별 통계가 표시됩니다.</div>
      ) : taskRows.length === 0 ? (
        <div className="glass rounded-2xl p-12 text-center text-muted-foreground">해당 물건에 등록된 점검 결과가 없습니다.</div>
      ) : (
        <div className="space-y-4">
          {taskRows.map((row) => (
            <div key={row.task.taskId} className="glass-strong rounded-2xl p-5">
              <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
                <div>
                  <h3 className="font-semibold">{row.task.taskName}</h3>
                  <p className="text-xs text-muted-foreground mt-0.5">총 {row.total}건</p>
                </div>
                <div className="flex flex-wrap gap-2">
                  {STATUS_LIST.map((s) => (
                    <StatusPill key={s} status={s} value={row[s]} />
                  ))}
                </div>
              </div>
              <div className="glass rounded-xl overflow-hidden">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-left text-xs uppercase tracking-wider text-muted-foreground border-b border-white/10">
                      <th className="px-3 py-2 font-medium">점검연도</th>
                      <th className="px-3 py-2 font-medium">점검업무</th>
                      <th className="px-3 py-2 font-medium">점검자</th>
                      <th className="px-3 py-2 font-medium">점검일</th>
                      <th className="px-3 py-2 font-medium">상태</th>
                      <th className="px-3 py-2 font-medium text-right">상세</th>
                    </tr>
                  </thead>
                  <tbody>
                    {row.items.map((r) => (
                      <tr key={r.resultId} className="border-b border-white/5 last:border-0">
                        <td className="px-3 py-2">{r.year}</td>
                        <td className="px-3 py-2 truncate max-w-[14rem]">{row.task.taskName}</td>
                        <td className="px-3 py-2">{r.inspector || "—"}</td>
                        <td className="px-3 py-2 text-muted-foreground">{r.inspectedAt}</td>
                        <td className="px-3 py-2"><StatusPill status={r.status} value={1} /></td>
                        <td className="px-3 py-2 text-right">
                          <Link to="/tasks/$taskId/$resultId" params={{ taskId: row.task.taskId, resultId: r.resultId }}
                            className="text-xs text-primary hover:underline">상세 내용 보기</Link>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          ))}
        </div>
      )}

      <AssetPickerDialog open={pickerOpen} onClose={() => setPickerOpen(false)} onPick={(a) => setAssetId(a.assetId)} />
    </div>
  );
}
