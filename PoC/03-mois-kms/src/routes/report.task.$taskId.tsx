import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { useEffect, useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { ArrowLeft } from "lucide-react";
import { Button } from "@/components/ui/button";
import { supabase } from "@/integrations/supabase/client";
import { generateTaskReport } from "@/lib/report.functions";
import { ReportView } from "@/components/report/ReportView";
import { ModelSettingsPanel, useReportAISettings } from "@/components/report/ModelSettings";

export const Route = createFileRoute("/report/task/$taskId")({ component: TaskReportPage });

function TaskReportPage() {
  const { taskId } = Route.useParams();
  const navigate = useNavigate();
  const [authChecked, setAuthChecked] = useState(false);
  const ai = useReportAISettings();

  useEffect(() => {
    supabase.auth.getSession().then(({ data }) => {
      if (!data.session) navigate({ to: "/login" });
      else setAuthChecked(true);
    });
  }, [navigate]);

  const mutation = useMutation({
    mutationFn: () => generateTaskReport({ data: { taskId, ...ai.settings } }),
  });

  useEffect(() => {
    if (authChecked && ai.ready) mutation.mutate();
    // 첫 모델 로딩이 끝난 시점에 한 번 자동 생성합니다.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [authChecked, ai.ready]);

  if (!authChecked) return null;

  return (
    <main className="app-page">
      <div className="mx-auto max-w-4xl space-y-4">
        <Link to="/"><Button variant="ghost" size="sm" className="gap-1.5"><ArrowLeft className="h-4 w-4" /> 업무 현황</Button></Link>
        <ModelSettingsPanel {...ai} />
        <ReportView
          title="AI 업무 보고서"
          subtitle="선택한 업무와 등록된 템플릿을 바탕으로 만든 검토용 초안입니다."
          report={mutation.data?.report ?? null}
          loading={mutation.isPending || ai.loading}
          error={mutation.error instanceof Error ? mutation.error.message : ai.error}
          onRegenerate={() => mutation.mutate()}
        />
      </div>
    </main>
  );
}
