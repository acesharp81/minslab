import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useServerFn } from "@/lib/server-functions";
import { useNavigate } from "@tanstack/react-router";
import { toast } from "sonner";
import { format } from "date-fns";
import { FileText, Pencil, Trash2 } from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  isTaskCompleted,
  transitionTask,
  deleteTask,
  type TaskRow,
  type WorkflowAction,
} from "@/lib/tasks.functions";
import { TaskFormDialog } from "./TaskFormDialog";

type Position = "과장" | "팀장" | "팀원" | "서무";

type Props = {
  task: TaskRow | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  currentUserId: string | null;
  currentPosition: Position | null;
  currentTeamId: string | null;
};

export function TaskDetailDialog({
  task,
  open,
  onOpenChange,
  currentUserId,
  currentPosition,
  currentTeamId,
}: Props) {
  const queryClient = useQueryClient();
  const transitionFn = useServerFn(transitionTask);
  const deleteFn = useServerFn(deleteTask);
  const [editOpen, setEditOpen] = useState(false);
  const navigate = useNavigate();

  const transition = useMutation({
    mutationFn: (action: WorkflowAction) =>
      transitionFn({ data: { id: task!.id, action } }),
    onSuccess: (_d, action) => {
      toast.success(`${action} 처리되었습니다.`);
      queryClient.invalidateQueries({ queryKey: ["tasks-month"] });
      onOpenChange(false);
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const del = useMutation({
    mutationFn: () => deleteFn({ data: { id: task!.id } }),
    onSuccess: () => {
      toast.success("삭제되었습니다.");
      queryClient.invalidateQueries({ queryKey: ["tasks-month"] });
      onOpenChange(false);
    },
    onError: (e: Error) => toast.error(e.message),
  });

  if (!task) return null;
  const completed = isTaskCompleted(task.step);
  const dt = new Date(task.datetime);

  const isAuthor = currentUserId === task.author_id;
  const canEdit = isAuthor && !completed;
  const canDelete = isAuthor && !completed;

  const showLeaderActions =
    task.step === "팀장검토" &&
    currentPosition === "팀장" &&
    currentTeamId != null &&
    currentTeamId === task.author_team_id;
  const showManagerActions =
    task.step === "팀장등록" &&
    (currentPosition === "과장" || currentPosition === "서무");

  return (
    <>
      <Dialog open={open} onOpenChange={onOpenChange}>
        <DialogContent className="glass-panel max-h-[90vh] max-w-2xl overflow-y-auto border-0 sm:rounded-3xl">
          <DialogHeader>
            <div className="flex items-center gap-2">
              <Badge
                variant={completed ? "default" : "secondary"}
                className={
                  completed
                    ? "bg-[color:var(--status-done)] text-white"
                    : "bg-[color:var(--status-progress)] text-white"
                }
              >
                {completed ? "완료" : "입력 중"}
              </Badge>
              <span className="text-xs text-muted-foreground">
                #{task.task_no_pk}
              </span>
              <span className="text-xs text-muted-foreground">· {task.step}</span>
            </div>
            <DialogTitle className="text-left text-xl">{task.title}</DialogTitle>
          </DialogHeader>

          <div className="grid grid-cols-2 gap-3 text-sm">
            <Field label="작성자">
              {task.author_name} ({task.author_position})
            </Field>
            <Field label="분류">{task.category_name ?? "해당없음"}</Field>
            <Field label="일시">{format(dt, "yyyy-MM-dd HH:mm")}</Field>
            <Field label="방식">
              {task.method}
              {task.location ? ` · ${task.location}` : ""}
            </Field>
            <Field label="참석자" full>
              {task.attendees}
            </Field>
            <Field label="목적" full>
              <p className="whitespace-pre-wrap leading-relaxed">{task.purpose}</p>
            </Field>
            <Field label="내용" full>
              <p className="whitespace-pre-wrap leading-relaxed">{task.content}</p>
            </Field>
          </div>

          <DialogFooter className="flex-wrap gap-2 sm:gap-2">
            <Button
              variant="secondary"
              className="gap-1.5"
              onClick={() => {
                onOpenChange(false);
                navigate({
                  to: "/report/task/$taskId",
                  params: { taskId: task.id },
                });
              }}
            >
              <FileText className="h-4 w-4" /> 보고서 만들기
            </Button>

            {showLeaderActions && (
              <>
                <Button
                  variant="outline"
                  onClick={() => transition.mutate("보완")}
                  disabled={transition.isPending}
                >
                  보완
                </Button>
                <Button
                  variant="destructive"
                  onClick={() => transition.mutate("반려")}
                  disabled={transition.isPending}
                >
                  반려
                </Button>
                <Button
                  onClick={() => transition.mutate("검토완료")}
                  disabled={transition.isPending}
                >
                  검토완료
                </Button>
              </>
            )}

            {showManagerActions && (
              <>
                <Button
                  variant="destructive"
                  onClick={() => transition.mutate("반려")}
                  disabled={transition.isPending}
                >
                  반려
                </Button>
                <Button
                  onClick={() => transition.mutate("승인")}
                  disabled={transition.isPending}
                >
                  승인
                </Button>
              </>
            )}

            {canDelete && (
              <AlertDialog>
                <AlertDialogTrigger asChild>
                  <Button variant="outline" className="gap-1.5">
                    <Trash2 className="h-4 w-4" /> 삭제
                  </Button>
                </AlertDialogTrigger>
                <AlertDialogContent className="glass-panel border-0">
                  <AlertDialogHeader>
                    <AlertDialogTitle>이 업무를 삭제하시겠습니까?</AlertDialogTitle>
                    <AlertDialogDescription>
                      삭제된 업무는 복구할 수 없습니다. 정말 삭제하시려면 아래
                      [삭제] 버튼을 한 번 더 누르세요.
                    </AlertDialogDescription>
                  </AlertDialogHeader>
                  <AlertDialogFooter>
                    <AlertDialogCancel>취소</AlertDialogCancel>
                    <AlertDialogAction
                      className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
                      onClick={() => del.mutate()}
                    >
                      삭제
                    </AlertDialogAction>
                  </AlertDialogFooter>
                </AlertDialogContent>
              </AlertDialog>
            )}

            {canEdit && (
              <Button onClick={() => setEditOpen(true)} className="gap-1.5">
                <Pencil className="h-4 w-4" /> 수정
              </Button>
            )}
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {canEdit && currentPosition && (
        <TaskFormDialog
          open={editOpen}
          onOpenChange={setEditOpen}
          position={currentPosition}
          task={task}
        />
      )}
    </>
  );
}

function Field({
  label,
  children,
  full,
}: {
  label: string;
  children: React.ReactNode;
  full?: boolean;
}) {
  return (
    <div className={full ? "col-span-2" : ""}>
      <div className="text-xs font-medium text-muted-foreground">{label}</div>
      <div className="mt-1 text-foreground">{children}</div>
    </div>
  );
}