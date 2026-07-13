import { createFileRoute, useNavigate, Link } from "@tanstack/react-router";
import { useEffect, useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useServerFn } from "@/lib/server-functions";
import { supabase } from "@/integrations/supabase/client";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { ChevronLeft, ChevronRight, FileText, LogOut, Plus, Shield } from "lucide-react";
import { toast } from "sonner";
import { getMyProfile } from "@/lib/profile.functions";
import { listTasksForMonth, isTaskCompleted, type TaskRow } from "@/lib/tasks.functions";
import { CalendarGrid } from "@/components/dashboard/CalendarGrid";
import { TaskListSidebar } from "@/components/dashboard/TaskListSidebar";
import { TaskDetailDialog } from "@/components/dashboard/TaskDetailDialog";
import { TaskFormDialog } from "@/components/dashboard/TaskFormDialog";
import { ProfileDialog } from "@/components/dashboard/ProfileDialog";
import { AppBrand } from "@/components/AppBrand";

export const Route = createFileRoute("/")({
  component: Dashboard,
  head: () => ({ meta: [{ title: "대시보드 | 통합 업무 관리 시스템" }] }),
});

function Dashboard() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [authChecked, setAuthChecked] = useState(false);

  useEffect(() => {
    supabase.auth.getSession().then(({ data }) => {
      if (!data.session) navigate({ to: "/login" });
      else setAuthChecked(true);
    });
  }, [navigate]);

  const now = new Date();
  const [year, setYear] = useState(now.getFullYear());
  const [month, setMonth] = useState(now.getMonth() + 1);

  const fetchProfile = useServerFn(getMyProfile);
  const fetchTasks = useServerFn(listTasksForMonth);

  const profileQuery = useQuery({
    queryKey: ["my-profile"],
    queryFn: () => fetchProfile(),
    enabled: authChecked,
  });

  const tasksQuery = useQuery({
    queryKey: ["tasks-month", year, month],
    queryFn: () => fetchTasks({ data: { year, month } }),
    enabled: authChecked,
  });

  // Realtime: invalidate on any tasks change
  useEffect(() => {
    if (!authChecked) return;
    const channel = supabase
      .channel("tasks-changes")
      .on(
        "postgres_changes",
        { event: "*", schema: "public", table: "tasks" },
        () => {
          queryClient.invalidateQueries({ queryKey: ["tasks-month"] });
        },
      )
      .subscribe();
    return () => {
      supabase.removeChannel(channel);
    };
  }, [authChecked, queryClient]);

  const [selectedTask, setSelectedTask] = useState<TaskRow | null>(null);
  const [detailOpen, setDetailOpen] = useState(false);
  const [createOpen, setCreateOpen] = useState(false);
  const [profileOpen, setProfileOpen] = useState(false);
  const onSelectTask = (t: TaskRow) => {
    setSelectedTask(t);
    setDetailOpen(true);
  };

  const profile = profileQuery.data?.profile;
  const tasks = tasksQuery.data?.tasks ?? [];

  const metrics = useMemo(() => {
    if (!profile) {
      return { scope: "", total: 0, completed: 0, progress: 0 };
    }
    // 과 단위 표기: RLS가 이미 division-scoped tasks만 반환
    const scoped = tasks;
    const scopeLabel = profileQuery.data?.isAdmin ? "전체" : "우리 부서";
    const completed = scoped.filter((t) => isTaskCompleted(t.step)).length;
    return {
      scope: scopeLabel,
      total: scoped.length,
      completed,
      progress: scoped.length - completed,
    };
  }, [tasks, profile, profileQuery.data?.isAdmin]);

  const shiftMonth = (delta: number) => {
    const d = new Date(year, month - 1 + delta, 1);
    setYear(d.getFullYear());
    setMonth(d.getMonth() + 1);
  };

  if (!authChecked) return null;

  const sessionLine = profile
    ? `${profileQuery.data?.divisionName ?? "미분류"} · ${profileQuery.data?.teamName ?? "해당없음"} · ${profile.position} · ${profile.name} (${profile.login_id})`
    : "프로필 정보를 불러오는 중...";

  return (
    <main className="min-h-screen px-4 py-6 lg:px-8">
      <div className="mx-auto max-w-[1400px] space-y-4">
        {/* Header */}
        <header className="glass-panel flex flex-col gap-4 rounded-3xl px-6 py-4 lg:flex-row lg:items-center lg:justify-between">
          <div>
            <AppBrand />
            <p className="mt-0.5 text-xs text-muted-foreground">
              {profile ? (
                <>
                  {profileQuery.data?.divisionName ?? "미분류"} ·{" "}
                  {profileQuery.data?.teamName ?? "해당없음"} · {profile.position} ·{" "}
                  <button
                    type="button"
                    onClick={() => setProfileOpen(true)}
                    className="rounded px-1 font-semibold text-foreground underline-offset-2 hover:bg-white/40 hover:underline"
                  >
                    {profile.name}
                  </button>{" "}
                  ({profile.login_id})
                </>
              ) : (
                sessionLine
              )}
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <MetricChip label={`${metrics.scope} · 총`} value={metrics.total} />
            <MetricChip
              label="완료"
              value={metrics.completed}
              tone="done"
            />
            <MetricChip
              label="입력 중"
              value={metrics.progress}
              tone="progress"
            />
            {profileQuery.data?.isAdmin && (
              <Link to="/admin">
                <Button variant="secondary" size="sm" className="gap-1.5">
                  <Shield className="h-3.5 w-3.5" /> 관리자
                </Button>
              </Link>
            )}
            {profile?.position === "서무" && (
              <>
                <Link to="/report/monthly">
                  <Button variant="secondary" size="sm" className="gap-1.5">
                    <FileText className="h-3.5 w-3.5" /> 월간보고
                  </Button>
                </Link>
                <Link to="/report/weekly">
                  <Button variant="secondary" size="sm" className="gap-1.5">
                    <FileText className="h-3.5 w-3.5" /> 주간보고
                  </Button>
                </Link>
              </>
            )}
            <Button
              variant="secondary"
              size="sm"
              className="gap-1.5"
              onClick={async () => {
                await supabase.auth.signOut();
                toast.success("로그아웃되었습니다.");
                navigate({ to: "/login" });
              }}
            >
              <LogOut className="h-3.5 w-3.5" /> 로그아웃
            </Button>
          </div>
        </header>

        {/* Body: sidebar + calendar */}
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-[320px_1fr]">
          <aside className="h-[calc(100vh-180px)] min-h-[500px]">
            <TaskListSidebar tasks={tasks} onSelectTask={onSelectTask} />
          </aside>

          <section className="space-y-3">
            <div className="glass-panel flex flex-wrap items-center justify-between gap-3 rounded-2xl px-4 py-3">
              <div className="flex items-center gap-2">
                <Button
                  variant="ghost"
                  size="icon"
                  className="h-8 w-8"
                  onClick={() => shiftMonth(-1)}
                  aria-label="이전 달"
                >
                  <ChevronLeft className="h-4 w-4" />
                </Button>
                <Select value={String(year)} onValueChange={(v) => setYear(Number(v))}>
                  <SelectTrigger className="h-8 w-[100px] glass-input">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {Array.from({ length: 7 }, (_, i) => now.getFullYear() - 3 + i).map(
                      (y) => (
                        <SelectItem key={y} value={String(y)}>
                          {y}년
                        </SelectItem>
                      ),
                    )}
                  </SelectContent>
                </Select>
                <Select value={String(month)} onValueChange={(v) => setMonth(Number(v))}>
                  <SelectTrigger className="h-8 w-[80px] glass-input">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {Array.from({ length: 12 }, (_, i) => i + 1).map((m) => (
                      <SelectItem key={m} value={String(m)}>
                        {m}월
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <Button
                  variant="ghost"
                  size="icon"
                  className="h-8 w-8"
                  onClick={() => shiftMonth(1)}
                  aria-label="다음 달"
                >
                  <ChevronRight className="h-4 w-4" />
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => {
                    const d = new Date();
                    setYear(d.getFullYear());
                    setMonth(d.getMonth() + 1);
                  }}
                >
                  오늘
                </Button>
              </div>
              <Button
                size="sm"
                className="gap-1.5"
                onClick={() => setCreateOpen(true)}
                disabled={!profile || profile.status !== "승인"}
              >
                <Plus className="h-4 w-4" /> 업무 추가
              </Button>
            </div>

            <CalendarGrid
              year={year}
              month={month}
              tasks={tasks}
              onSelectTask={onSelectTask}
            />
          </section>
        </div>
      </div>

      <TaskDetailDialog
        task={selectedTask}
        open={detailOpen}
        onOpenChange={setDetailOpen}
        currentUserId={profile?.id ?? null}
        currentPosition={profile?.position ?? null}
        currentTeamId={profile?.team_id ?? null}
      />
      {profile && (
        <TaskFormDialog
          open={createOpen}
          onOpenChange={setCreateOpen}
          position={profile.position}
        />
      )}
      {profile && (
        <ProfileDialog
          open={profileOpen}
          onOpenChange={setProfileOpen}
          profile={profile}
        />
      )}
    </main>
  );
}

function MetricChip({
  label,
  value,
  tone,
}: {
  label: string;
  value: number;
  tone?: "done" | "progress";
}) {
  const toneClass =
    tone === "done"
      ? "text-[color:var(--status-done)]"
      : tone === "progress"
        ? "text-[color:var(--status-progress)]"
        : "text-foreground";
  return (
    <div className="flex items-center gap-1.5 rounded-full bg-white/50 px-3 py-1 text-xs backdrop-blur">
      <span className="text-muted-foreground">{label}</span>
      <span className={`font-bold tabular-nums ${toneClass}`}>{value}</span>
    </div>
  );
}
