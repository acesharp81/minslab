import { useMemo, useState } from "react";
import { ChevronDown, ChevronRight } from "lucide-react";
import { format } from "date-fns";
import { ko } from "date-fns/locale";
import { isTaskCompleted, type TaskRow } from "@/lib/tasks.functions";
import { cn } from "@/lib/utils";

type Props = {
  tasks: TaskRow[];
  onSelectTask: (task: TaskRow) => void;
};

export function TaskListSidebar({ tasks, onSelectTask }: Props) {
  const grouped = useMemo(() => {
    const m = new Map<string, TaskRow[]>();
    for (const t of tasks) {
      const key = format(new Date(t.datetime), "yyyy-MM-dd");
      const arr = m.get(key) ?? [];
      arr.push(t);
      m.set(key, arr);
    }
    return Array.from(m.entries()).sort(([a], [b]) => a.localeCompare(b));
  }, [tasks]);

  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const toggle = (id: string) => {
    setExpanded((prev) => {
      const n = new Set(prev);
      if (n.has(id)) n.delete(id);
      else n.add(id);
      return n;
    });
  };

  return (
    <div className="glass-panel flex h-full flex-col overflow-hidden rounded-3xl">
      <div className="border-b border-white/40 bg-white/30 px-4 py-3">
        <h3 className="text-sm font-semibold">이번 달 업무 목록</h3>
        <p className="mt-0.5 text-xs text-muted-foreground">
          총 {tasks.length}건
        </p>
      </div>
      <div className="flex-1 overflow-y-auto px-2 py-2">
        {grouped.length === 0 && (
          <div className="px-4 py-10 text-center text-xs text-muted-foreground">
            등록된 업무가 없습니다.
          </div>
        )}
        {grouped.map(([day, items]) => (
          <div key={day} className="mb-3">
            <div className="px-2 py-1 text-[11px] font-semibold text-muted-foreground">
              {format(new Date(day), "M월 d일 (E)", { locale: ko })} · {items.length}건
            </div>
            <ul className="space-y-1">
              {items.map((t) => {
                const isOpen = expanded.has(t.id);
                const done = isTaskCompleted(t.step);
                return (
                  <li key={t.id}>
                    <div className="flex items-stretch gap-1">
                      <button
                        onClick={() => toggle(t.id)}
                        className="flex w-6 items-center justify-center rounded-md text-muted-foreground hover:bg-white/40"
                        aria-label="펼치기"
                      >
                        {isOpen ? (
                          <ChevronDown className="h-3.5 w-3.5" />
                        ) : (
                          <ChevronRight className="h-3.5 w-3.5" />
                        )}
                      </button>
                      <button
                        onClick={() => onSelectTask(t)}
                        className="flex-1 rounded-lg bg-white/40 px-2.5 py-2 text-left text-xs transition hover:bg-white/60"
                      >
                        <div className="flex items-center gap-1.5">
                          <span
                            className={cn(
                              "rounded px-1 text-[10px] font-semibold",
                              done
                                ? "bg-[color:var(--status-done)]/20 text-[color:var(--status-done)]"
                                : "bg-[color:var(--status-progress)]/20 text-[color:var(--status-progress)]",
                            )}
                          >
                            {done ? "완료" : "입력 중"}
                          </span>
                          <span className="font-medium text-foreground line-clamp-1">
                            {t.title}
                          </span>
                        </div>
                        <div className="mt-0.5 text-[10px] text-muted-foreground">
                          {format(new Date(t.datetime), "HH:mm")} · {t.author_name}
                        </div>
                      </button>
                    </div>
                    {isOpen && (
                      <div className="ml-7 mt-1 rounded-lg bg-white/30 p-2 text-[11px] text-muted-foreground">
                        <p className="line-clamp-3 whitespace-pre-wrap leading-relaxed">
                          {t.content}
                        </p>
                      </div>
                    )}
                  </li>
                );
              })}
            </ul>
          </div>
        ))}
      </div>
    </div>
  );
}