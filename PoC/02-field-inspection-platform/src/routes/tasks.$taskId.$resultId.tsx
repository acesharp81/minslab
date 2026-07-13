import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { Shell } from "@/components/Shell";
import { ResultForm } from "@/components/ResultForm";
import { ConfirmDialog } from "@/components/ConfirmDialog";
import { store, useStore } from "@/lib/store";
import { ArrowLeft, ClipboardCheck } from "lucide-react";
import { useState } from "react";

export const Route = createFileRoute("/tasks/$taskId/$resultId")({ component: ResultDetail });

function ResultDetail() {
  const { taskId, resultId } = Route.useParams();
  const navigate = useNavigate();
  const task = useStore((s) => s.tasks.find((item) => item.taskId === taskId));
  const result = useStore((s) => s.results.find((item) => item.resultId === resultId));
  const [confirm, setConfirm] = useState(false);

  if (!task || !result) {
    return (
      <Shell>
        <div className="empty-state">
          <ClipboardCheck className="size-7" />
          <strong>점검 기록을 찾을 수 없습니다.</strong>
          <Link to="/" className="app-secondary-button mt-2">업무 현황으로 이동</Link>
        </div>
      </Shell>
    );
  }

  return (
    <Shell>
      <div className="app-page-heading">
        <Link
          to="/tasks/$taskId"
          params={{ taskId }}
          className="app-page-heading-icon"
          aria-label="점검 기록으로 돌아가기"
        >
          <ArrowLeft className="size-5" />
        </Link>
        <div>
          <div className="section-kicker">Inspection detail</div>
          <h1>점검 기록 상세</h1>
          <p>{task.taskName} · 내용을 수정하거나 상태를 완료 처리할 수 있습니다.</p>
        </div>
      </div>

      <ResultForm
        taskId={taskId}
        initial={result}
        onCancel={() => navigate({ to: "/tasks/$taskId", params: { taskId } })}
        onDelete={() => setConfirm(true)}
        onSubmit={(payload) => {
          const { resultId: _resultId, ...rest } = payload;
          void _resultId;
          store.updateResult(result.resultId, rest);
          navigate({ to: "/tasks/$taskId", params: { taskId } });
        }}
      />

      <ConfirmDialog
        open={confirm}
        title="점검 기록을 삭제하시겠습니까?"
        message="삭제한 기록은 되돌릴 수 없습니다."
        onConfirm={() => {
          store.deleteResult(result.resultId);
          navigate({ to: "/tasks/$taskId", params: { taskId } });
        }}
        onCancel={() => setConfirm(false)}
      />
    </Shell>
  );
}
