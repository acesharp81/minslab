import { useMemo } from "react";
import { isTaskCompleted, type TaskRow } from "@/lib/tasks.functions";
import { cn } from "@/lib/utils";

type Props = {
  year: number;
  month: number; // 1-12
  tasks: TaskRow[];
  onSelectTask: (task: TaskRow) => void;
};

const WEEKDAYS = ["일", "월", "화", "수", "목", "금", "토"];

export function CalendarGrid({ year, month, tasks, onSelectTask }: Props) {
  const cells = useMemo(() => {
    const first = new Date(year, month - 1, 1);
    const startDay = first.getDay(); // 0=Sun
    const daysInMonth = new Date(year, month, 0).getDate();
    const totalCells = 35; // 7x5
    const arr: Array<{ date: Date | null; inMonth: boolean }> = [];
    for (let i = 0; i < totalCells; i++) {
      const dayNum = i - startDay + 1;
      if (dayNum >= 1 && dayNum <= daysInMonth) {
        arr.push({ date: new Date(year, month - 1, dayNum), inMonth: true });
      } else {
        arr.push({ date: null, inMonth: false });
      }
    }
    return arr;
  }, [year, month]);

  const tasksByDay = useMemo(() => {
    const m = new Map<number, TaskRow[]>();
    for (const t of tasks) {
      const d = new Date(t.datetime).getDate();
      const arr = m.get(d) ?? [];
      arr.push(t);
      m.set(d, arr);
    }
    return m;
  }, [tasks]);

  const today = new Date();
  const isToday = (d: Date) =>
    d.getFullYear() === today.getFullYear() &&
    d.getMonth() === today.getMonth() &&
    d.getDate() === today.getDate();

  return (
    <div className="glass-panel overflow-hidden rounded-3xl">
      <div className="grid grid-cols-7 border-b border-white/40 bg-white/30 text-center text-xs font-medium text-muted-foreground">
        {WEEKDAYS.map((w, i) => (
          <div
            key={w}
            className={cn(
              "py-2",
              i === 0 && "text-destructive",
              i === 6 && "text-primary",
            )}
          >
            {w}
          </div>
        ))}
      </div>
      <div className="grid grid-cols-7 grid-rows-5">
        {cells.map((cell, idx) => {
          const dayTasks = cell.date ? tasksByDay.get(cell.date.getDate()) ?? [] : [];
          return (
            <div
              key={idx}
              className={cn(
                "relative flex min-h-28 flex-col gap-1 border-b border-r border-white/30 p-1.5",
                (idx + 1) % 7 === 0 && "border-r-0",
                idx >= 28 && "border-b-0",
                !cell.inMonth && "bg-white/10",
              )}
            >
              {cell.date && (
                <div
                  className={cn(
                    "flex h-5 w-5 items-center justify-center text-xs font-medium",
                    isToday(cell.date)
                      ? "rounded-full bg-primary text-primary-foreground"
                      : idx % 7 === 0
                        ? "text-destructive"
                        : idx % 7 === 6
                          ? "text-primary"
                          : "text-foreground",
                  )}
                >
                  {cell.date.getDate()}
                </div>
              )}
              <div className="flex flex-col gap-1 overflow-hidden">
                {dayTasks.slice(0, 3).map((t) => {
                  const done = isTaskCompleted(t.step);
                  const status = done ? "완료" : "입력중";
                  const teamName = t.author_team_name ?? "해당없음";
                  return (
                    <button
                      key={t.id}
                      onClick={() => onSelectTask(t)}
                      className={cn(
                        "group rounded-md px-1.5 py-1 text-left text-[11px] leading-snug transition",
                        done
                          ? "bg-[color:var(--status-done)]/15 text-[color:var(--status-done)] hover:bg-[color:var(--status-done)]/25"
                          : "bg-[color:var(--status-progress)]/15 text-[color:var(--status-progress)] hover:bg-[color:var(--status-progress)]/25",
                      )}
                      title={t.title}
                    >
                      <div className="font-semibold">
                        [{status}] {teamName}
                      </div>
                      <div className="line-clamp-1 text-foreground/80">
                        {t.title}
                      </div>
                    </button>
                  );
                })}
                {dayTasks.length > 3 && (
                  <span className="px-1 text-[10px] text-muted-foreground">
                    +{dayTasks.length - 3}건 더보기
                  </span>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}