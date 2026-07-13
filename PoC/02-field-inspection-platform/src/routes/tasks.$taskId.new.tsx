import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { Shell } from "@/components/Shell";
import { ResultForm } from "@/components/ResultForm";
import { store, useStore } from "@/lib/store";
import { ArrowLeft, ClipboardPlus } from "lucide-react";

export const Route = createFileRoute("/tasks/$taskId/new")({ component: NewResult });

function NewResult() {
  const { taskId } = Route.useParams();
  const navigate = useNavigate();
  const task = useStore((s) => s.tasks.find((item) => item.taskId === taskId));

  if (!task) {
    return (
      <Shell>
        <div className="empty-state">
          <ClipboardPlus className="size-7" />
          <strong>점검 업무를 찾을 수 없습니다.</strong>
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
          <div className="section-kicker">New inspection</div>
          <h1>신규 점검 등록</h1>
          <p>{task.taskName} · 현장 정보를 입력하고 상태를 저장합니다.</p>
        </div>
      </div>

      <ResultForm
        taskId={taskId}
        onCancel={() => navigate({ to: "/tasks/$taskId", params: { taskId } })}
        onSubmit={(payload) => {
          const { resultId: _resultId, ...rest } = payload;
          void _resultId;
          store.addResult(rest);
          navigate({ to: "/tasks/$taskId", params: { taskId } });
        }}
      />
    </Shell>
  );
}
