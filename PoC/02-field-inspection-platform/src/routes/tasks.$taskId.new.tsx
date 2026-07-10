import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { Shell } from "@/components/Shell";
import { ResultForm } from "@/components/ResultForm";
import { store, useStore } from "@/lib/store";
import { ArrowLeft } from "lucide-react";

export const Route = createFileRoute("/tasks/$taskId/new")({ component: NewResult });

function NewResult() {
  const { taskId } = Route.useParams();
  const navigate = useNavigate();
  const task = useStore((s) => s.tasks.find((t) => t.taskId === taskId));
  if (!task) return <Shell><div className="glass rounded-2xl p-10 text-center">Task not found.</div></Shell>;

  return (
    <Shell>
      <div className="mb-6 flex items-center gap-3">
        <Link to="/tasks/$taskId" params={{ taskId }} className="size-10 grid place-items-center glass rounded-xl hover:bg-white/10">
          <ArrowLeft className="size-4" />
        </Link>
        <div>
          <div className="text-xs uppercase tracking-[0.2em] text-muted-foreground">신규 등록</div>
          <h1 className="text-2xl font-semibold">{task.taskName}</h1>
        </div>
      </div>

      <ResultForm taskId={taskId}
        onCancel={() => navigate({ to: "/tasks/$taskId", params: { taskId } })}
        onSubmit={(p) => {
          const { resultId: _ignore, ...rest } = p;
          void _ignore;
          store.addResult(rest);
          navigate({ to: "/tasks/$taskId", params: { taskId } });
        }} />
    </Shell>
  );
}
