import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { Shell } from "@/components/Shell";
import { useStore, taskStatusCounts, summarizeResult, type InspectionStatus } from "@/lib/store";
import { ArrowLeft, Download, Plus, Search } from "lucide-react";
import { useMemo, useState } from "react";

export const Route = createFileRoute("/tasks/$taskId/")({ component: TaskResults });

const STATUS_TONE: Record<InspectionStatus, string> = {
  "등록": "bg-white/10 text-muted-foreground",
  "점검중": "bg-[color:oklch(0.78_0.18_200/.2)] text-[color:oklch(0.85_0.15_200)]",
  "점검완료": "bg-primary/20 text-primary",
};

function TaskResults() {
  const { taskId } = Route.useParams();
  const navigate = useNavigate();
  const task = useStore((s) => s.tasks.find((t) => t.taskId === taskId));
  const results = useStore((s) => s.results.filter((r) => r.taskId === taskId));
  const assets = useStore((s) => s.assets);
  const counts = useStore((s) => taskStatusCounts(taskId, s));
  const [q, setQ] = useState("");
  const [toast, setToast] = useState("");

  const assetMap = useMemo(() => Object.fromEntries(assets.map((a) => [a.assetId, a])), [assets]);

  const filtered = useMemo(() => {
    if (!q.trim()) return results;
    const n = q.toLowerCase();
    return results.filter((r) => {
      const a = assetMap[r.assetId];
      const summary = summarizeResult(r, task).toLowerCase();
      return (
        a?.name.toLowerCase().includes(n) ||
        a?.address.toLowerCase().includes(n) ||
        a?.sido.toLowerCase().includes(n) ||
        r.inspector.toLowerCase().includes(n) ||
        summary.includes(n) ||
        String(r.year).includes(n)
      );
    });
  }, [results, q, assetMap, task]);

  if (!task) {
    return (
      <Shell>
        <div className="glass rounded-2xl p-10 text-center">
          <p className="text-muted-foreground">Task not found.</p>
          <Link to="/" className="text-primary mt-3 inline-block">← Dashboard</Link>
        </div>
      </Shell>
    );
  }

  const exportCsv = () => {
    const fields = task.customFields;
    const header = ["점검연", "점검자", "점검일시", "점검대상", "분류", "주소", "관할", ...fields.map((f) => f.name), "상태", "확인자"];
    const rows = filtered.map((r) => {
      const a = assetMap[r.assetId];
      const custom = fields.map((f) => {
        const v = r.customValues?.[f.id];
        if (Array.isArray(v)) return `${v.length}장`;
        return v ?? "";
      });
      return [r.year, r.inspector, r.inspectedAt, a?.name ?? "", a?.category ?? "", `${a?.address ?? ""} ${a?.addressDetail ?? ""}`.trim(), a?.sido ?? "", ...custom, r.status, r.confirmer]
        .map((v) => `"${String(v ?? "").replace(/"/g, '""')}"`).join(",");
    });
    const csv = [header.join(","), ...rows].join("\n");
    const blob = new Blob(["\ufeff" + csv], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url; a.download = `${task.taskName}.csv`; a.click();
    URL.revokeObjectURL(url);
    setToast("Exported to CSV");
    setTimeout(() => setToast(""), 2000);
  };

  return (
    <Shell>
      <div className="mb-6 flex items-center gap-3">
        <Link to="/" className="size-10 grid place-items-center glass rounded-xl hover:bg-white/10">
          <ArrowLeft className="size-4" />
        </Link>
        <div className="flex-1">
          <div className="text-xs uppercase tracking-[0.2em] text-muted-foreground">Task</div>
          <h1 className="text-2xl md:text-3xl font-semibold">{task.taskName}</h1>
          {(task.department || task.manager) && (
            <p className="text-xs text-muted-foreground mt-1">{task.department}{task.manager ? ` · ${task.manager}` : ""}</p>
          )}
        </div>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-5">
        <Card label="총 등록" value={counts.total} />
        <Card label="등록" value={counts.등록} />
        <Card label="점검중" value={counts.점검중} tone="accent" />
        <Card label="점검완료" value={counts.점검완료} tone="primary" />
      </div>

      <div className="glass-strong rounded-2xl p-4 md:p-5 flex flex-col md:flex-row gap-3 mb-5">
        <div className="flex-1 flex items-center gap-2 glass rounded-xl px-4 py-2.5">
          <Search className="size-4 text-muted-foreground" />
          <input value={q} onChange={(e) => setQ(e.target.value)}
            placeholder="결과 검색 (이름, 주소, 관할, 항목...)"
            className="flex-1 bg-transparent outline-none placeholder:text-muted-foreground/60" />
        </div>
        <div className="flex gap-2">
          <button onClick={exportCsv}
            className="glass rounded-xl px-4 py-2.5 flex items-center gap-2 hover:bg-white/10 text-sm">
            <Download className="size-4" />
            Excel 다운로드
          </button>
          <button onClick={() => navigate({ to: "/tasks/$taskId/new", params: { taskId } })}
            className="rounded-xl px-4 py-2.5 flex items-center gap-2 text-sm font-medium text-primary-foreground"
            style={{ background: "linear-gradient(135deg, oklch(0.72 0.2 290), oklch(0.78 0.18 200))" }}>
            <Plus className="size-4" /> 추가
          </button>
        </div>
      </div>

      <div className="glass rounded-2xl overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-xs uppercase tracking-wider text-muted-foreground border-b border-white/10">
                <th className="px-4 py-3 font-medium">연도</th>
                <th className="px-4 py-3 font-medium">점검 대상</th>
                <th className="px-4 py-3 font-medium">관할</th>
                <th className="px-4 py-3 font-medium">점검자</th>
                <th className="px-4 py-3 font-medium">점검일</th>
                <th className="px-4 py-3 font-medium">항목</th>
                <th className="px-4 py-3 font-medium">상태</th>
              </tr>
            </thead>
            <tbody>
              {filtered.length === 0 ? (
                <tr><td colSpan={7} className="px-4 py-12 text-center text-muted-foreground">결과가 없습니다.</td></tr>
              ) : filtered.map((r) => {
                const a = assetMap[r.assetId];
                return (
                  <tr key={r.resultId}
                    onClick={() => navigate({ to: "/tasks/$taskId/$resultId", params: { taskId, resultId: r.resultId } })}
                    className="border-b border-white/5 last:border-0 hover:bg-white/5 cursor-pointer transition-colors">
                    <td className="px-4 py-3">{r.year}</td>
                    <td className="px-4 py-3 truncate max-w-[12rem]">{a?.name ?? "—"}</td>
                    <td className="px-4 py-3 text-muted-foreground">{a?.sido ?? "—"}</td>
                    <td className="px-4 py-3">{r.inspector || "—"}</td>
                    <td className="px-4 py-3 text-muted-foreground">{r.inspectedAt}</td>
                    <td className="px-4 py-3 truncate max-w-xs">{summarizeResult(r, task) || "—"}</td>
                    <td className="px-4 py-3">
                      <span className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-xs ${STATUS_TONE[r.status]}`}>
                        <span className="size-1.5 rounded-full bg-current" />
                        {r.status}
                      </span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      {toast && (
        <div className="fixed bottom-6 left-1/2 -translate-x-1/2 glass-strong rounded-xl px-4 py-2.5 text-sm">
          {toast}
        </div>
      )}
    </Shell>
  );
}

function Card({ label, value, tone }: { label: string; value: number; tone?: "primary" | "accent" }) {
  const color = tone === "primary" ? "text-primary" : tone === "accent" ? "text-[color:oklch(0.85_0.15_200)]" : "text-foreground";
  return (
    <div className="glass rounded-xl p-4">
      <div className="text-xs uppercase tracking-wider text-muted-foreground">{label}</div>
      <div className={`text-2xl font-semibold mt-1 ${color}`}>{value}</div>
    </div>
  );
}
