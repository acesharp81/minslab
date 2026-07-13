import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useServerFn } from "@/lib/server-functions";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { toast } from "sonner";
import { format } from "date-fns";
import {
  createTask,
  updateTask,
  listCategories,
  type TaskRow,
} from "@/lib/tasks.functions";

type Position = "과장" | "팀장" | "팀원" | "서무";

type Props = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  position: Position;
  /** existing task for edit mode */
  task?: TaskRow | null;
};

type FormState = {
  title: string;
  category_id: string | null;
  purpose: string;
  content: string;
  method: "온라인" | "오프라인";
  location: string;
  datetime: string; // local datetime string yyyy-MM-ddTHH:mm
  attendees: string;
};

function emptyForm(): FormState {
  const now = new Date();
  return {
    title: "",
    category_id: null,
    purpose: "",
    content: "",
    method: "오프라인",
    location: "",
    datetime: format(now, "yyyy-MM-dd'T'HH:mm"),
    attendees: "",
  };
}

function fromTask(t: TaskRow): FormState {
  return {
    title: t.title,
    category_id: t.category_id,
    purpose: t.purpose,
    content: t.content,
    method: t.method,
    location: t.location ?? "",
    datetime: format(new Date(t.datetime), "yyyy-MM-dd'T'HH:mm"),
    attendees: t.attendees,
  };
}

export function TaskFormDialog({ open, onOpenChange, position, task }: Props) {
  const isEdit = !!task;
  const [form, setForm] = useState<FormState>(emptyForm());
  const queryClient = useQueryClient();
  const fetchCats = useServerFn(listCategories);
  const createFn = useServerFn(createTask);
  const updateFn = useServerFn(updateTask);

  useEffect(() => {
    if (open) setForm(task ? fromTask(task) : emptyForm());
  }, [open, task]);

  const catsQuery = useQuery({
    queryKey: ["task-categories"],
    queryFn: () => fetchCats(),
    enabled: open,
  });

  const submit = useMutation({
    mutationFn: async (intent: "save" | "submit") => {
      const iso = new Date(form.datetime).toISOString();
      const payload = {
        title: form.title.trim(),
        category_id: form.category_id,
        purpose: form.purpose.trim(),
        content: form.content.trim(),
        method: form.method,
        location: form.method === "오프라인" ? form.location.trim() || null : null,
        datetime: iso,
        attendees: form.attendees.trim(),
        intent,
      };
      if (!payload.title) throw new Error("제목을 입력해주세요.");
      if (!payload.purpose) throw new Error("목적을 입력해주세요.");
      if (!payload.content) throw new Error("내용을 입력해주세요.");
      if (!payload.attendees) throw new Error("참석자를 입력해주세요.");
      if (payload.method === "오프라인" && !payload.location) {
        throw new Error("오프라인은 장소를 입력해주세요.");
      }
      if (isEdit && task) {
        return updateFn({ data: { ...payload, id: task.id } });
      }
      return createFn({ data: payload });
    },
    onSuccess: (_res, intent) => {
      toast.success(
        intent === "save"
          ? "임시 저장되었습니다."
          : position === "팀원"
            ? "팀장 검토 요청되었습니다."
            : "등록되었습니다.",
      );
      queryClient.invalidateQueries({ queryKey: ["tasks-month"] });
      onOpenChange(false);
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const submitLabel = position === "팀원" ? "검토 요청" : "등록";

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="glass-panel max-h-[90vh] max-w-2xl overflow-y-auto border-0 sm:rounded-3xl">
        <DialogHeader>
          <DialogTitle>{isEdit ? "업무 수정" : "업무 추가"}</DialogTitle>
        </DialogHeader>

        <div className="grid gap-4 py-2">
          <Field label="제목" required>
            <Input
              className="glass-input"
              value={form.title}
              onChange={(e) => setForm({ ...form, title: e.target.value })}
              maxLength={120}
              placeholder="업무 제목"
            />
          </Field>

          <div className="grid grid-cols-2 gap-3">
            <Field label="분류">
              <Select
                value={form.category_id ?? "__none"}
                onValueChange={(v) =>
                  setForm({ ...form, category_id: v === "__none" ? null : v })
                }
              >
                <SelectTrigger className="glass-input">
                  <SelectValue placeholder="분류 선택" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="__none">해당없음</SelectItem>
                  {(catsQuery.data?.categories ?? []).map((c) => (
                    <SelectItem key={c.id} value={c.id}>
                      {c.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </Field>
            <Field label="일시" required>
              <Input
                type="datetime-local"
                className="glass-input"
                value={form.datetime}
                onChange={(e) => setForm({ ...form, datetime: e.target.value })}
              />
            </Field>
          </div>

          <div className="grid grid-cols-[180px_1fr] gap-3">
            <Field label="방식" required>
              <RadioGroup
                value={form.method}
                onValueChange={(v) =>
                  setForm({ ...form, method: v as "온라인" | "오프라인" })
                }
                className="flex gap-3 pt-2"
              >
                <label className="flex items-center gap-1.5 text-sm">
                  <RadioGroupItem value="오프라인" /> 오프라인
                </label>
                <label className="flex items-center gap-1.5 text-sm">
                  <RadioGroupItem value="온라인" /> 온라인
                </label>
              </RadioGroup>
            </Field>
            <Field label={form.method === "오프라인" ? "장소" : "링크/플랫폼"}>
              <Input
                className="glass-input"
                value={form.location}
                onChange={(e) => setForm({ ...form, location: e.target.value })}
                placeholder={
                  form.method === "오프라인"
                    ? "예) 본사 3층 회의실"
                    : "예) Zoom 링크"
                }
                maxLength={200}
              />
            </Field>
          </div>

          <Field label="참석자" required>
            <Input
              className="glass-input"
              value={form.attendees}
              onChange={(e) => setForm({ ...form, attendees: e.target.value })}
              placeholder="예) 김과장, 이팀장, 박팀원"
              maxLength={500}
            />
          </Field>

          <Field label="목적" required>
            <Textarea
              className="glass-input min-h-[80px] resize-y"
              value={form.purpose}
              onChange={(e) => setForm({ ...form, purpose: e.target.value })}
              maxLength={2000}
            />
          </Field>

          <Field label="내용" required>
            <Textarea
              className="glass-input min-h-[140px] resize-y"
              value={form.content}
              onChange={(e) => setForm({ ...form, content: e.target.value })}
              maxLength={5000}
            />
          </Field>
        </div>

        <DialogFooter className="gap-2 sm:gap-2">
          <Button
            variant="secondary"
            onClick={() => onOpenChange(false)}
            disabled={submit.isPending}
          >
            취소
          </Button>
          <Button
            variant="outline"
            onClick={() => submit.mutate("save")}
            disabled={submit.isPending}
          >
            저장
          </Button>
          <Button
            onClick={() => submit.mutate("submit")}
            disabled={submit.isPending}
          >
            {submitLabel}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function Field({
  label,
  required,
  children,
}: {
  label: string;
  required?: boolean;
  children: React.ReactNode;
}) {
  return (
    <div className="grid gap-1.5">
      <Label className="text-xs font-medium">
        {label}
        {required && <span className="ml-0.5 text-destructive">*</span>}
      </Label>
      {children}
    </div>
  );
}