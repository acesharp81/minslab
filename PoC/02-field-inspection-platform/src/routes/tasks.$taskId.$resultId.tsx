import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { Shell } from "@/components/Shell";
import { ResultForm } from "@/components/ResultForm";
import { ConfirmDialog } from "@/components/ConfirmDialog";
import { store, useStore } from "@/lib/store";
import { ArrowLeft } from "lucide-react";
import { useState } from "react";

export const Route = createFileRoute("/tasks/$taskId/$resultId")({ component: ResultDetail });

function ResultDetail() {
  const { taskId, resultId } = Route.useParams();
  const navigate = useNavigate();
  const task = useStore((s) => s.tasks.find((t) => t.taskId === taskId));
  const result = useStore((s) => s.results.find((r) => r.resultId === resultId));
  const [confirm, setConfirm] = useState(false);

  if (!task || !result) return <Shell><div className="glass rounded-2xl p-10 text-center">Not found.</div></Shell>;

  return (
    <Shell>
      <div className="mb-6 flex items-center gap-3">
        <Link to="/tasks/$taskId" params={{ taskId }} className="size-10 grid place-items-center glass rounded-xl hover:bg-white/10">
          <ArrowLeft className="size-4" />
        </Link>
        <div>
          <div className="text-xs uppercase tracking-[0.2em] text-muted-foreground">상세 / 수정</div>
          <h1 className="text-2xl font-semibold">{task.taskName}</h1>
        </div>
      </div>

      <ResultForm taskId={taskId} initial={result}
        onCancel={() => navigate({ to: "/tasks/$taskId", params: { taskId } })}
        onDelete={() => setConfirm(true)}
        onSubmit={(p) => {
          const { resultId: _ignore, ...rest } = p;
          void _ignore;
          store.updateResult(result.resultId, rest);
          navigate({ to: "/tasks/$taskId", params: { taskId } });
        }} />

      <ConfirmDialog open={confirm}
        title="기록을 삭제하시겠습니까?"
        message="이 작업은 되돌릴 수 없습니다."
        onConfirm={() => { store.deleteResult(result.resultId); navigate({ to: "/tasks/$taskId", params: { taskId } }); }}
        onCancel={() => setConfirm(false)} />
    </Shell>
  );
}
