import { useEffect, useState, type ReactNode } from "react";
import {
  store, useStore,
  CUSTOM_FIELD_TYPES, uid,
  type Asset, type Task, type CustomField, type CustomFieldType,
} from "@/lib/store";
import { createFileRoute } from "@tanstack/react-router";
import { Shell } from "@/components/Shell";
import { ConfirmDialog } from "@/components/ConfirmDialog";
import { AssetFormDialog } from "@/components/AssetFormDialog";
import {
  ShieldCheck, Plus, Trash2, Pencil, ClipboardList, MapPin,
  X as XIcon, ArrowUp, ArrowDown,
} from "lucide-react";

export const Route = createFileRoute("/admin")({ component: Admin });

function Admin() {
  const [tab, setTab] = useState<"tasks" | "assets">("tasks");
  return (
    <Shell>
      <div className="mb-6 flex items-center gap-3">
        <div className="size-10 rounded-xl glass-strong grid place-items-center">
          <ShieldCheck className="size-5 text-primary" />
        </div>
        <div>
          <div className="text-xs uppercase tracking-[0.2em] text-muted-foreground">Admin</div>
          <h1 className="text-2xl font-semibold">관리자 메뉴</h1>
        </div>
      </div>

      <div className="glass-strong rounded-2xl p-1.5 inline-flex gap-1 mb-5">
        <TabBtn active={tab === "tasks"} onClick={() => setTab("tasks")} icon={<ClipboardList className="size-4" />}>점검 업무</TabBtn>
        <TabBtn active={tab === "assets"} onClick={() => setTab("assets")} icon={<MapPin className="size-4" />}>물건</TabBtn>
      </div>

      {tab === "tasks" ? <TaskAdmin /> : <AssetAdmin />}
    </Shell>
  );
}

function TabBtn({ active, onClick, icon, children }: { active: boolean; onClick: () => void; icon: ReactNode; children: ReactNode }) {
  return (
    <button onClick={onClick}
      className={`px-4 py-2 rounded-xl text-sm flex items-center gap-2 transition-colors ${active ? "bg-white/15 text-foreground" : "text-muted-foreground hover:bg-white/5"}`}>
      {icon}{children}
    </button>
  );
}

/* ============== TASKS ============== */

function TaskAdmin() {
  const tasks = useStore((s) => s.tasks);
  const [editing, setEditing] = useState<Task | null>(null);
  const [creating, setCreating] = useState(false);
  const [delId, setDelId] = useState<string | null>(null);

  return (
    <section className="glass-strong rounded-2xl p-5 md:p-6">
      <div className="flex items-center justify-between mb-4">
        <h2 className="font-semibold">점검 업무 목록</h2>
        <button onClick={() => setCreating(true)}
          className="rounded-xl px-4 py-2 text-sm font-medium text-primary-foreground flex items-center gap-1.5"
          style={{ background: "linear-gradient(135deg, oklch(0.72 0.2 290), oklch(0.78 0.18 200))" }}>
          <Plus className="size-4" /> 업무 추가
        </button>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-xs uppercase tracking-wider text-muted-foreground border-b border-white/10">
              <th className="px-3 py-3">이름</th>
              <th className="px-3 py-3">목적</th>
              <th className="px-3 py-3">주관부서</th>
              <th className="px-3 py-3">담당자</th>
              <th className="px-3 py-3">입력 서식</th>
              <th className="px-3 py-3 text-right">관리</th>
            </tr>
          </thead>
          <tbody>
            {tasks.length === 0 ? (
              <tr><td colSpan={6} className="px-3 py-10 text-center text-muted-foreground">등록된 업무가 없습니다.</td></tr>
            ) : tasks.map((t) => (
              <tr key={t.taskId} className="border-b border-white/5 last:border-0 hover:bg-white/5">
                <td className="px-3 py-3 font-medium">{t.taskName}</td>
                <td className="px-3 py-3 text-muted-foreground truncate max-w-xs">{t.purpose || "—"}</td>
                <td className="px-3 py-3">{t.department || "—"}</td>
                <td className="px-3 py-3">{t.manager || "—"}</td>
                <td className="px-3 py-3 text-xs text-muted-foreground">{t.customFields.length}개 항목</td>
                <td className="px-3 py-3 text-right">
                  <button onClick={() => setEditing(t)} className="size-8 inline-grid place-items-center rounded-lg hover:bg-white/10"><Pencil className="size-4" /></button>
                  <button onClick={() => setDelId(t.taskId)} className="size-8 inline-grid place-items-center rounded-lg hover:bg-destructive/20 text-destructive"><Trash2 className="size-4" /></button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {creating && <TaskEditorDialog initial={null} onClose={() => setCreating(false)} />}
      {editing && <TaskEditorDialog initial={editing} onClose={() => setEditing(null)} />}

      <ConfirmDialog open={!!delId}
        title="업무를 삭제하시겠습니까?"
        message="해당 업무의 모든 점검 결과도 함께 삭제됩니다."
        onConfirm={() => { if (delId) store.deleteTask(delId); setDelId(null); }}
        onCancel={() => setDelId(null)} />
    </section>
  );
}

function TaskEditorDialog({ initial, onClose }: { initial: Task | null; onClose: () => void }) {
  const [taskName, setTaskName] = useState(initial?.taskName ?? "");
  const [purpose, setPurpose] = useState(initial?.purpose ?? "");
  const [content, setContent] = useState(initial?.content ?? "");
  const [department, setDepartment] = useState(initial?.department ?? "");
  const [manager, setManager] = useState(initial?.manager ?? "");
  const [showSchema, setShowSchema] = useState(false);
  const [customFields, setCustomFields] = useState<CustomField[]>(
    initial?.customFields ?? [
      { id: uid(), name: "점검항목", type: "text", length: 100 },
      { id: uid(), name: "점검결과", type: "text", length: 200 },
      { id: uid(), name: "점검사진", type: "photo", length: 4 },
    ],
  );

  const updateField = (id: string, patch: Partial<CustomField>) =>
    setCustomFields((arr) => arr.map((f) => (f.id === id ? { ...f, ...patch } : f)));
  const removeField = (id: string) => setCustomFields((arr) => arr.filter((f) => f.id !== id));
  const addField = () => setCustomFields((arr) => [...arr, { id: uid(), name: "", type: "text", length: 100 }]);
  const move = (id: string, dir: -1 | 1) => setCustomFields((arr) => {
    const i = arr.findIndex((f) => f.id === id);
    if (i < 0) return arr;
    const j = i + dir;
    if (j < 0 || j >= arr.length) return arr;
    const next = arr.slice();
    [next[i], next[j]] = [next[j], next[i]];
    return next;
  });

  const submit = () => {
    if (!taskName.trim()) return;
    const cleaned = customFields
      .map((f) => ({ ...f, name: f.name.trim() }))
      .filter((f) => f.name.length > 0);
    const payload = {
      taskName: taskName.trim(),
      purpose, content, department, manager,
      customFields: cleaned,
    };
    if (initial) store.updateTask(initial.taskId, payload);
    else store.addTask(payload);
    onClose();
  };

  return (
    <DialogFrame title={initial ? "업무 수정" : "업무 추가"} onClose={onClose} onSubmit={submit} wide>
      <Labeled label="이름">
        <input value={taskName} onChange={(e) => setTaskName(e.target.value)} maxLength={60}
          className="w-full glass rounded-xl px-4 py-2.5 outline-none focus:ring-2 ring-primary/50" placeholder="업무 이름" />
      </Labeled>
      <Labeled label="목적">
        <input value={purpose} onChange={(e) => setPurpose(e.target.value)} maxLength={100}
          className="w-full glass rounded-xl px-4 py-2.5 outline-none focus:ring-2 ring-primary/50" />
      </Labeled>
      <Labeled label="내용">
        <textarea value={content} onChange={(e) => setContent(e.target.value)} rows={3} maxLength={500}
          className="w-full glass rounded-xl px-4 py-2.5 outline-none focus:ring-2 ring-primary/50 resize-none" />
      </Labeled>
      <div className="grid grid-cols-2 gap-3">
        <Labeled label="주관부서">
          <input value={department} onChange={(e) => setDepartment(e.target.value)} maxLength={40}
            className="w-full glass rounded-xl px-4 py-2.5 outline-none focus:ring-2 ring-primary/50" />
        </Labeled>
        <Labeled label="담당자">
          <input value={manager} onChange={(e) => setManager(e.target.value)} maxLength={20}
            className="w-full glass rounded-xl px-4 py-2.5 outline-none focus:ring-2 ring-primary/50" />
        </Labeled>
      </div>

      <div className="pt-2">
        <button type="button" onClick={() => setShowSchema((s) => !s)}
          className="w-full glass rounded-xl px-4 py-2.5 text-sm hover:bg-white/10 flex items-center justify-between">
          <span><span className="text-primary font-medium">입력 서식 수정</span> · 점검 결과 입력 폼에 노출됩니다</span>
          <span className="text-xs text-muted-foreground">{customFields.length}개 항목 {showSchema ? "▲" : "▼"}</span>
        </button>

        {showSchema && (
          <div className="mt-3 space-y-3">
            <div className="text-[11px] text-muted-foreground leading-relaxed">
              기본 항목(점검연도 · 점검자 · 점검대상 · 점검일시 · 점검상태 · 확인자)은 자동 포함되며 삭제할 수 없습니다.
              아래에서 추가 점검 항목을 자유롭게 구성하세요.
            </div>
            <div className="space-y-2">
              {customFields.map((f, idx) => (
                <div key={f.id} className="glass rounded-xl p-3 flex flex-wrap gap-2 items-center">
                  <input value={f.name} onChange={(e) => updateField(f.id, { name: e.target.value })}
                    placeholder="항목 이름 (예: 점검항목)"
                    className="flex-1 min-w-[140px] glass rounded-lg px-3 py-2 text-sm outline-none focus:ring-2 ring-primary/50" />
                  <select value={f.type}
                    onChange={(e) => updateField(f.id, { type: e.target.value as CustomFieldType })}
                    className="glass rounded-lg px-3 py-2 text-sm outline-none focus:ring-2 ring-primary/50">
                    {CUSTOM_FIELD_TYPES.map((t) => <option key={t.value} value={t.value}>{t.label}</option>)}
                  </select>
                  <div className="flex items-center gap-1 glass rounded-lg px-3 py-1.5">
                    <span className="text-[11px] text-muted-foreground">
                      {f.type === "photo" ? "최대 장수" : "최대 길이"}
                    </span>
                    <input type="number" min={1} max={f.type === "photo" ? 20 : 500}
                      value={f.length}
                      onChange={(e) => updateField(f.id, { length: Math.max(1, Number(e.target.value) || 1) })}
                      className="w-16 bg-transparent text-sm outline-none text-right" />
                  </div>
                  <div className="flex gap-1">
                    <button type="button" onClick={() => move(f.id, -1)} disabled={idx === 0}
                      className="size-8 grid place-items-center rounded-lg hover:bg-white/10 disabled:opacity-30"><ArrowUp className="size-3.5" /></button>
                    <button type="button" onClick={() => move(f.id, 1)} disabled={idx === customFields.length - 1}
                      className="size-8 grid place-items-center rounded-lg hover:bg-white/10 disabled:opacity-30"><ArrowDown className="size-3.5" /></button>
                    <button type="button" onClick={() => removeField(f.id)}
                      className="size-8 grid place-items-center rounded-lg hover:bg-destructive/20 text-destructive"><Trash2 className="size-3.5" /></button>
                  </div>
                </div>
              ))}
            </div>
            <button type="button" onClick={addField}
              className="w-full glass rounded-xl py-2.5 text-sm hover:bg-white/10 flex items-center justify-center gap-1.5 text-primary">
              <Plus className="size-4" /> 항목 추가
            </button>
          </div>
        )}
      </div>
    </DialogFrame>
  );
}

/* ============== ASSETS ============== */

function AssetAdmin() {
  const assets = useStore((s) => s.assets);
  const [editing, setEditing] = useState<Asset | null>(null);
  const [creating, setCreating] = useState(false);
  const [delId, setDelId] = useState<string | null>(null);

  return (
    <section className="glass-strong rounded-2xl p-5 md:p-6">
      <div className="flex items-center justify-between mb-4">
        <h2 className="font-semibold">물건 목록</h2>
        <button onClick={() => setCreating(true)}
          className="rounded-xl px-4 py-2 text-sm font-medium text-primary-foreground flex items-center gap-1.5"
          style={{ background: "linear-gradient(135deg, oklch(0.72 0.2 290), oklch(0.78 0.18 200))" }}>
          <Plus className="size-4" /> 물건 등록
        </button>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-xs uppercase tracking-wider text-muted-foreground border-b border-white/10">
              <th className="px-3 py-3">이름</th>
              <th className="px-3 py-3">분류</th>
              <th className="px-3 py-3">주소</th>
              <th className="px-3 py-3">관할</th>
              <th className="px-3 py-3 text-right">관리</th>
            </tr>
          </thead>
          <tbody>
            {assets.length === 0 ? (
              <tr><td colSpan={5} className="px-3 py-10 text-center text-muted-foreground">등록된 물건이 없습니다.</td></tr>
            ) : assets.map((a) => (
              <tr key={a.assetId} className="border-b border-white/5 last:border-0 hover:bg-white/5">
                <td className="px-3 py-3 font-medium">{a.name}</td>
                <td className="px-3 py-3"><span className="text-xs px-2 py-0.5 rounded-full bg-primary/15 text-primary">{a.category}</span></td>
                <td className="px-3 py-3 text-muted-foreground truncate max-w-xs">{a.address} {a.addressDetail}</td>
                <td className="px-3 py-3">{a.sido}</td>
                <td className="px-3 py-3 text-right">
                  <button onClick={() => setEditing(a)} className="size-8 inline-grid place-items-center rounded-lg hover:bg-white/10"><Pencil className="size-4" /></button>
                  <button onClick={() => setDelId(a.assetId)} className="size-8 inline-grid place-items-center rounded-lg hover:bg-destructive/20 text-destructive"><Trash2 className="size-4" /></button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <AssetFormDialog open={creating} onClose={() => setCreating(false)} onSaved={() => {}} />
      <AssetFormDialog open={!!editing} initial={editing ?? undefined} onClose={() => setEditing(null)} onSaved={() => {}} />

      <ConfirmDialog open={!!delId}
        title="물건을 삭제하시겠습니까?"
        message="삭제된 물건은 복구할 수 없습니다."
        onConfirm={() => { if (delId) store.deleteAsset(delId); setDelId(null); }}
        onCancel={() => setDelId(null)} />
    </section>
  );
}

/* ============== shared ============== */

function DialogFrame({
  title, onClose, onSubmit, children, wide = false,
}: { title: string; onClose: () => void; onSubmit: () => void; children: ReactNode; wide?: boolean }) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);
  return (
    <div className="fixed inset-0 z-50 grid place-items-center p-4 bg-black/50 backdrop-blur-sm">
      <div className={`glass-strong rounded-2xl p-6 w-full ${wide ? "max-w-2xl" : "max-w-lg"} max-h-[90vh] overflow-y-auto`}>
        <div className="flex items-center justify-between mb-5">
          <h3 className="text-lg font-semibold">{title}</h3>
          <button onClick={onClose} className="size-8 grid place-items-center rounded-lg hover:bg-white/10"><XIcon className="size-4" /></button>
        </div>
        <div className="space-y-4">{children}</div>
        <div className="flex justify-end gap-2 mt-6 pt-5 border-t border-white/10">
          <button onClick={onClose} className="glass rounded-xl px-4 py-2 text-sm hover:bg-white/10">취소</button>
          <button onClick={onSubmit} className="rounded-xl px-5 py-2 text-sm font-medium text-primary-foreground"
            style={{ background: "linear-gradient(135deg, oklch(0.72 0.2 290), oklch(0.78 0.18 200))" }}>
            저장
          </button>
        </div>
      </div>
    </div>
  );
}

function Labeled({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div>
      <label className="text-xs uppercase tracking-wider text-muted-foreground font-medium">{label}</label>
      <div className="mt-1.5">{children}</div>
    </div>
  );
}
