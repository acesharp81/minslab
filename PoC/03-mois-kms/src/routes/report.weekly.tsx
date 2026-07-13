import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { useEffect, useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { ArrowLeft } from "lucide-react";
import { Button } from "@/components/ui/button";
import { supabase } from "@/integrations/supabase/client";
import { generateWeeklyDivisionReport } from "@/lib/report.functions";
import { ReportView } from "@/components/report/ReportView";
import { ModelSettingsPanel, useReportAISettings } from "@/components/report/ModelSettings";

export const Route = createFileRoute("/report/weekly")({ component: WeeklyReportPage });

function WeeklyReportPage() {
  const navigate = useNavigate();
  const now = new Date();
  const [year, setYear] = useState(now.getFullYear());
  const [month, setMonth] = useState(now.getMonth() + 1);
  const [week, setWeek] = useState(Math.min(5, Math.ceil(now.getDate() / 7)));
  const [authChecked, setAuthChecked] = useState(false);
  const ai = useReportAISettings();

  useEffect(() => {
    supabase.auth.getSession().then(({ data }) => {
      if (!data.session) navigate({ to: "/login" });
      else setAuthChecked(true);
    });
  }, [navigate]);

  const mutation = useMutation({
    mutationFn: () => generateWeeklyDivisionReport({ data: { year, month, week, ...ai.settings } }),
  });

  useEffect(() => {
    if (authChecked && ai.ready) mutation.mutate();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [authChecked, ai.ready]);

  if (!authChecked) return null;
  const subtitle = mutation.data
    ? `${mutation.data.divisionName} · ${mutation.data.range.start} ~ ${mutation.data.range.end} · 총 ${mutation.data.taskCount}건`
    : `${year}년 ${month}월 ${week}주차`;

  return (
    <main className="app-page">
      <div className="mx-auto max-w-4xl space-y-4">
        <div className="report-page-toolbar">
          <Link to="/"><Button variant="ghost" size="sm" className="gap-1.5"><ArrowLeft className="h-4 w-4" /> 업무 현황</Button></Link>
          <div className="report-period-controls">
            <select value={year} onChange={(event) => setYear(Number(event.target.value))}>
              {Array.from({ length: 7 }, (_, index) => now.getFullYear() - 3 + index).map((value) => <option key={value} value={value}>{value}년</option>)}
            </select>
            <select value={month} onChange={(event) => setMonth(Number(event.target.value))}>
              {Array.from({ length: 12 }, (_, index) => index + 1).map((value) => <option key={value} value={value}>{value}월</option>)}
            </select>
            <select value={week} onChange={(event) => setWeek(Number(event.target.value))}>
              {[1, 2, 3, 4, 5].map((value) => <option key={value} value={value}>{value}주차</option>)}
            </select>
            <Button size="sm" onClick={() => mutation.mutate()} disabled={mutation.isPending || !ai.ready}>생성</Button>
          </div>
        </div>
        <ModelSettingsPanel {...ai} />
        <ReportView
          title="부서 주간 보고서"
          subtitle={subtitle}
          report={mutation.data?.report ?? null}
          loading={mutation.isPending || ai.loading}
          error={mutation.error instanceof Error ? mutation.error.message : ai.error}
          onRegenerate={() => mutation.mutate()}
        />
      </div>
    </main>
  );
}
