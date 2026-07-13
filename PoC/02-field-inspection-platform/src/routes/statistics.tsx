import { createFileRoute, Link } from "@tanstack/react-router";
import { Shell } from "@/components/Shell";
import { SIDO_LIST, STATUS_LIST, useStore, type InspectionStatus } from "@/lib/store";
import { AssetPickerDialog } from "@/components/AssetPickerDialog";
import { useMemo, useState } from "react";
import { BarChart3, MapPin, MapPinned, Search, X } from "lucide-react";

export const Route = createFileRoute("/statistics")({
  component: Statistics,
  head: () => ({
    meta: [{ title: "점검 통계 · 현장점검 지원플랫폼" }],
  }),
});

function Statistics() {
  const [tab, setTab] = useState<"jurisdiction" | "asset">("jurisdiction");

  return (
    <Shell>
      <div className="app-page-heading">
        <div className="app-page-heading-icon">
          <BarChart3 className="size-5" />
        </div>
        <div>
          <div className="section-kicker">Inspection insights</div>
          <h1>점검 통계</h1>
          <p>업무·관할지와 점검 대상 기준으로 진행 상태를 비교합니다.</p>
        </div>
      </div>

      <div className="page-tabs" role="tablist" aria-label="통계 기준">
        <TabBtn
          active={tab === "jurisdiction"}
          onClick={() => setTab("jurisdiction")}
        >
          업무 · 관할지별
        </TabBtn>
        <TabBtn active={tab === "asset"} onClick={() => setTab("asset")}>
          점검 대상별
        </TabBtn>
      </div>

      {tab === "jurisdiction" ? <JurisdictionStats /> : <AssetStats />}
    </Shell>
  );
}

function TabBtn({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      onClick={onClick}
      className={"page-tab" + (active ? " is-active" : "")}
      role="tab"
      aria-selected={active}
    >
      {children}
    </button>
  );
}

function StatusPill({ status, value }: { status: InspectionStatus; value: number }) {
  const tone =
    status === "점검완료"
      ? " is-complete"
      : status === "점검중"
        ? " is-progress"
        : "";

  return (
    <span className={"status-pill" + tone}>
      {status} <b>{value}</b>
    </span>
  );
}

function JurisdictionStats() {
  const tasks = useStore((s) => s.tasks);
  const results = useStore((s) => s.results);
  const assets = useStore((s) => s.assets);
  const [taskId, setTaskId] = useState<string>(tasks[0]?.taskId ?? "");

  const assetSido = useMemo(
    () => Object.fromEntries(assets.map((asset) => [asset.assetId, asset.sido])),
    [assets],
  );

  const rows = useMemo(() => {
    const filtered = results.filter((result) => result.taskId === taskId);
    return SIDO_LIST.map((sido) => {
      const list = filtered.filter((result) => assetSido[result.assetId] === sido);
      return {
        sido,
        total: list.length,
        등록: list.filter((result) => result.status === "등록").length,
        점검중: list.filter((result) => result.status === "점검중").length,
        점검완료: list.filter((result) => result.status === "점검완료").length,
      };
    }).filter((row) => row.total > 0);
  }, [results, taskId, assetSido]);

  if (tasks.length === 0) {
    return (
      <div className="empty-state">
        <BarChart3 className="size-7" />
        <strong>집계할 점검 업무가 없습니다.</strong>
        <span>관리자 메뉴에서 업무를 먼저 등록해 주세요.</span>
      </div>
    );
  }

  return (
    <div className="space-y-5">
      <section className="filter-panel">
        <div>
          <div className="section-kicker">Task filter</div>
          <strong>점검 업무 선택</strong>
        </div>
        <div className="flex min-w-0 flex-1 flex-wrap gap-2">
          {tasks.map((task) => (
            <button
              key={task.taskId}
              onClick={() => setTaskId(task.taskId)}
              className={"record-tab" + (taskId === task.taskId ? " is-active" : "")}
            >
              {task.taskName}
            </button>
          ))}
        </div>
      </section>

      <div className="data-table-card">
        <div className="table-title">
          <MapPinned className="size-4" />
          관할 시도별 점검 현황
          <span>{rows.reduce((sum, row) => sum + row.total, 0)}건</span>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr>
                <th className="px-4 py-3 text-left">관할 시도</th>
                <th className="px-4 py-3 text-center">전체</th>
                <th className="px-4 py-3 text-center">등록</th>
                <th className="px-4 py-3 text-center">점검중</th>
                <th className="px-4 py-3 text-center">점검완료</th>
              </tr>
            </thead>
            <tbody>
              {rows.length === 0 ? (
                <tr>
                  <td colSpan={5} className="px-4 py-12 text-center text-muted-foreground">
                    선택한 업무에 등록된 점검 결과가 없습니다.
                  </td>
                </tr>
              ) : rows.map((row) => (
                <tr key={row.sido}>
                  <td className="px-4 py-3 font-bold">{row.sido}</td>
                  <td className="px-4 py-3 text-center font-black">{row.total}</td>
                  <td className="px-4 py-3 text-center">{row.등록}</td>
                  <td className="px-4 py-3 text-center text-[#245f9f] font-semibold">{row.점검중}</td>
                  <td className="px-4 py-3 text-center text-[#237249] font-bold">{row.점검완료}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

function AssetStats() {
  const assets = useStore((s) => s.assets);
  const tasks = useStore((s) => s.tasks);
  const results = useStore((s) => s.results);
  const [assetId, setAssetId] = useState("");
  const [pickerOpen, setPickerOpen] = useState(false);

  const selected = assets.find((asset) => asset.assetId === assetId);

  const taskRows = useMemo(() => {
    if (!assetId) return [];
    return tasks.map((task) => {
      const list = results.filter(
        (result) => result.assetId === assetId && result.taskId === task.taskId,
      );
      return {
        task,
        total: list.length,
        등록: list.filter((result) => result.status === "등록").length,
        점검중: list.filter((result) => result.status === "점검중").length,
        점검완료: list.filter((result) => result.status === "점검완료").length,
        items: list,
      };
    }).filter((row) => row.total > 0);
  }, [assetId, tasks, results]);

  return (
    <div className="space-y-5">
      <div className="asset-selector">
        <div className="asset-selector-value">
          {selected ? (
            <>
              <MapPin className="size-4 shrink-0 text-primary" />
              <strong>{selected.name}</strong>
              <span className="asset-meta">{selected.category} · {selected.sido}</span>
              <button
                onClick={() => setAssetId("")}
                className="ml-auto grid size-7 shrink-0 place-items-center rounded-lg hover:bg-muted"
                aria-label="선택한 점검 대상 해제"
              >
                <X className="size-3.5" />
              </button>
            </>
          ) : (
            <span className="text-sm font-semibold text-muted-foreground">
              통계를 확인할 점검 대상을 선택해 주세요.
            </span>
          )}
        </div>
        <button onClick={() => setPickerOpen(true)} className="app-secondary-button">
          <Search className="size-4" />
          점검 대상 찾기
        </button>
      </div>

      {!selected ? (
        <div className="empty-state">
          <MapPin className="size-7" />
          <strong>점검 대상이 선택되지 않았습니다.</strong>
          <span>대상을 선택하면 업무별 점검 건수와 상태를 보여줍니다.</span>
        </div>
      ) : taskRows.length === 0 ? (
        <div className="empty-state">
          <BarChart3 className="size-7" />
          <strong>등록된 점검 결과가 없습니다.</strong>
          <span>선택한 대상에 첫 점검 기록을 등록해 주세요.</span>
        </div>
      ) : (
        <div className="space-y-4">
          {taskRows.map((row) => (
            <section key={row.task.taskId} className="stat-group-card">
              <div className="stat-group-head">
                <div>
                  <div className="section-kicker">Inspection task</div>
                  <h3>{row.task.taskName}</h3>
                  <p>총 {row.total}건의 점검 기록</p>
                </div>
                <div className="flex flex-wrap gap-2">
                  {STATUS_LIST.map((status) => (
                    <StatusPill key={status} status={status} value={row[status]} />
                  ))}
                </div>
              </div>

              <div className="data-table-card shadow-none">
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr>
                        <th className="px-3 py-3 text-left">연도</th>
                        <th className="px-3 py-3 text-left">점검업무</th>
                        <th className="px-3 py-3 text-left">점검자</th>
                        <th className="px-3 py-3 text-left">점검일</th>
                        <th className="px-3 py-3 text-left">상태</th>
                        <th className="px-3 py-3 text-right">상세</th>
                      </tr>
                    </thead>
                    <tbody>
                      {row.items.map((result) => (
                        <tr key={result.resultId}>
                          <td className="px-3 py-3">{result.year}</td>
                          <td className="px-3 py-3 truncate max-w-[14rem]">{row.task.taskName}</td>
                          <td className="px-3 py-3">{result.inspector || "—"}</td>
                          <td className="px-3 py-3 text-muted-foreground">{result.inspectedAt}</td>
                          <td className="px-3 py-3">
                            <StatusPill status={result.status} value={1} />
                          </td>
                          <td className="px-3 py-3 text-right">
                            <Link
                              to="/tasks/$taskId/$resultId"
                              params={{ taskId: row.task.taskId, resultId: result.resultId }}
                              className="font-bold text-primary hover:underline"
                            >
                              상세 보기
                            </Link>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </section>
          ))}
        </div>
      )}

      <AssetPickerDialog
        open={pickerOpen}
        onClose={() => setPickerOpen(false)}
        onPick={(asset) => setAssetId(asset.assetId)}
      />
    </div>
  );
}
