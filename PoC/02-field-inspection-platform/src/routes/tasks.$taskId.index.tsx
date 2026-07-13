import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { Shell } from "@/components/Shell";
import { useStore, taskStatusCounts, summarizeResult, type InspectionStatus } from "@/lib/store";
import {
  ArrowLeft,
  CheckCircle2,
  ClipboardCheck,
  Download,
  Plus,
  Search,
} from "lucide-react";
import { useMemo, useState } from "react";

export const Route = createFileRoute("/tasks/$taskId/")({ component: TaskResults });

function statusClass(status: InspectionStatus) {
  return status === "점검완료"
    ? "status-pill is-complete"
    : status === "점검중"
      ? "status-pill is-progress"
      : "status-pill";
}

function TaskResults() {
  const { taskId } = Route.useParams();
  const navigate = useNavigate();
  const task = useStore((s) => s.tasks.find((item) => item.taskId === taskId));
  const results = useStore((s) => s.results.filter((result) => result.taskId === taskId));
  const assets = useStore((s) => s.assets);
  const counts = useStore((s) => taskStatusCounts(taskId, s));
  const [query, setQuery] = useState("");
  const [toast, setToast] = useState("");

  const assetMap = useMemo(
    () => Object.fromEntries(assets.map((asset) => [asset.assetId, asset])),
    [assets],
  );

  const filtered = useMemo(() => {
    if (!query.trim()) return results;
    const normalized = query.toLowerCase();
    return results.filter((result) => {
      const asset = assetMap[result.assetId];
      const summary = summarizeResult(result, task).toLowerCase();
      return (
        asset?.name.toLowerCase().includes(normalized) ||
        asset?.address.toLowerCase().includes(normalized) ||
        asset?.sido.toLowerCase().includes(normalized) ||
        result.inspector.toLowerCase().includes(normalized) ||
        summary.includes(normalized) ||
        String(result.year).includes(normalized)
      );
    });
  }, [results, query, assetMap, task]);

  if (!task) {
    return (
      <Shell>
        <div className="empty-state">
          <ClipboardCheck className="size-7" />
          <strong>점검 업무를 찾을 수 없습니다.</strong>
          <Link to="/" className="app-secondary-button mt-2">업무 현황으로 이동</Link>
        </div>
      </Shell>
    );
  }

  const exportCsv = () => {
    const header = [
      "점검연", "점검자", "점검일시", "점검대상", "분류", "주소", "관할",
      ...task.customFields.map((field) => field.name), "상태", "확인자",
    ];
    const rows = filtered.map((result) => {
      const asset = assetMap[result.assetId];
      const custom = task.customFields.map((field) => {
        const value = result.customValues?.[field.id];
        if (Array.isArray(value)) return value.length + "장";
        return value ?? "";
      });
      return [
        result.year,
        result.inspector,
        result.inspectedAt,
        asset?.name ?? "",
        asset?.category ?? "",
        ((asset?.address ?? "") + " " + (asset?.addressDetail ?? "")).trim(),
        asset?.sido ?? "",
        ...custom,
        result.status,
        result.confirmer,
      ].map((value) => '"' + String(value ?? "").replace(/"/g, '""') + '"').join(",");
    });

    const csv = [header.join(","), ...rows].join("\n");
    const blob = new Blob(["\ufeff" + csv], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = task.taskName + ".csv";
    anchor.click();
    URL.revokeObjectURL(url);
    setToast("CSV 다운로드 완료");
    setTimeout(() => setToast(""), 2000);
  };

  return (
    <Shell>
      <div className="app-page-heading">
        <Link to="/" className="app-page-heading-icon" aria-label="업무 현황으로 이동">
          <ArrowLeft className="size-5" />
        </Link>
        <div>
          <div className="section-kicker">Inspection task</div>
          <h1>{task.taskName}</h1>
          <p>
            {task.department || "담당부서 미지정"}
            {task.manager ? " · " + task.manager : ""}
          </p>
        </div>
      </div>

      <div className="metric-grid">
        <MetricCard label="전체 기록" value={counts.total} />
        <MetricCard label="등록" value={counts.등록} />
        <MetricCard label="점검중" value={counts.점검중} tone="progress" />
        <MetricCard label="점검완료" value={counts.점검완료} tone="complete" />
      </div>

      <div className="list-toolbar">
        <div className="search-field">
          <Search className="size-4" />
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="대상, 주소, 관할, 점검자와 항목 검색"
          />
        </div>
        <div className="flex gap-2">
          <button onClick={exportCsv} className="app-secondary-button">
            <Download className="size-4" />
            CSV 다운로드
          </button>
          <button
            onClick={() => navigate({ to: "/tasks/$taskId/new", params: { taskId } })}
            className="app-primary-button"
          >
            <Plus className="size-4" />
            점검 추가
          </button>
        </div>
      </div>

      <div className="data-table-card">
        <div className="table-title">
          <ClipboardCheck className="size-4" />
          점검 기록
          <span>{filtered.length}건</span>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr>
                <th className="px-4 py-3 text-left">연도</th>
                <th className="px-4 py-3 text-left">점검 대상</th>
                <th className="px-4 py-3 text-left">관할</th>
                <th className="px-4 py-3 text-left">점검자</th>
                <th className="px-4 py-3 text-left">점검일</th>
                <th className="px-4 py-3 text-left">주요 항목</th>
                <th className="px-4 py-3 text-left">상태</th>
              </tr>
            </thead>
            <tbody>
              {filtered.length === 0 ? (
                <tr>
                  <td colSpan={7} className="px-4 py-14 text-center text-muted-foreground">
                    검색 조건에 맞는 점검 기록이 없습니다.
                  </td>
                </tr>
              ) : filtered.map((result) => {
                const asset = assetMap[result.assetId];
                return (
                  <tr
                    key={result.resultId}
                    onClick={() =>
                      navigate({
                        to: "/tasks/$taskId/$resultId",
                        params: { taskId, resultId: result.resultId },
                      })
                    }
                    className="cursor-pointer transition-colors"
                  >
                    <td className="px-4 py-3">{result.year}</td>
                    <td className="px-4 py-3 max-w-[12rem] truncate font-bold">
                      {asset?.name ?? "—"}
                    </td>
                    <td className="px-4 py-3 text-muted-foreground">{asset?.sido ?? "—"}</td>
                    <td className="px-4 py-3">{result.inspector || "—"}</td>
                    <td className="px-4 py-3 text-muted-foreground">{result.inspectedAt}</td>
                    <td className="px-4 py-3 max-w-xs truncate">
                      {summarizeResult(result, task) || "—"}
                    </td>
                    <td className="px-4 py-3">
                      <span className={statusClass(result.status)}>{result.status}</span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      {toast && (
        <div className="save-toast">
          <CheckCircle2 className="size-4" />
          {toast}
        </div>
      )}
    </Shell>
  );
}

function MetricCard({
  label,
  value,
  tone = "default",
}: {
  label: string;
  value: number;
  tone?: "default" | "progress" | "complete";
}) {
  return (
    <div className={"metric-card" + (tone === "progress" ? " is-progress" : tone === "complete" ? " is-complete" : "")}>
      <span>{label}</span>
      <b>{value}</b>
    </div>
  );
}
