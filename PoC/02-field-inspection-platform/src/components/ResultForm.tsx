import { useEffect, useMemo, useState } from "react";
import {
  useStore, store, YEAR_OPTIONS, STATUS_LIST,
  type Asset, type InspectionStatus, type Result, type CustomField, type CustomValue,
} from "@/lib/store";
import { AssetPickerDialog } from "@/components/AssetPickerDialog";
import { AssetFormDialog } from "@/components/AssetFormDialog";
import { PhotoInput } from "@/components/PhotoInput";
import { Plus, Search, MapPin } from "lucide-react";

interface Props {
  taskId: string;
  initial?: Result;
  /** When provided, the asset is fixed and the picker/추가 UI is hidden */
  lockedAssetId?: string;
  onSubmit: (payload: Omit<Result, "resultId" | "createdAt"> & { resultId?: string }) => void;
  onCancel?: () => void;
  onDelete?: () => void;
  submitLabel?: string;
  /** Show the bottom action bar (default true). */
  showActions?: boolean;
}

function defaultValueFor(f: CustomField): CustomValue {
  if (f.type === "photo") return [];
  if (f.type === "number") return "";
  return "";
}

export function ResultForm({
  taskId, initial, lockedAssetId, onSubmit, onCancel, onDelete,
  submitLabel = "저장", showActions = true,
}: Props) {
  const assets = useStore((s) => s.assets);
  const task = useStore((s) => s.tasks.find((t) => t.taskId === taskId));
  const customFields = task?.customFields ?? [];

  const [year, setYear] = useState<number>(initial?.year ?? new Date().getFullYear());
  const [assetId, setAssetId] = useState<string>(initial?.assetId ?? lockedAssetId ?? "");
  const [inspector, setInspector] = useState(initial?.inspector ?? "");
  const [inspectedAt, setInspectedAt] = useState(initial?.inspectedAt ?? new Date().toISOString().slice(0, 10));
  const [status, setStatus] = useState<InspectionStatus>(initial?.status ?? "등록");
  const [confirmer, setConfirmer] = useState(initial?.confirmer ?? "");
  const [values, setValues] = useState<Record<string, CustomValue>>(() => {
    const base: Record<string, CustomValue> = {};
    for (const f of customFields) base[f.id] = initial?.customValues?.[f.id] ?? defaultValueFor(f);
    return base;
  });

  // If task's customFields change (e.g. admin edits schema) keep keys aligned
  useEffect(() => {
    setValues((prev) => {
      const next: Record<string, CustomValue> = {};
      for (const f of customFields) next[f.id] = prev[f.id] ?? initial?.customValues?.[f.id] ?? defaultValueFor(f);
      return next;
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [customFields.map((f) => f.id + f.type).join("|")]);

  useEffect(() => { if (lockedAssetId) setAssetId(lockedAssetId); }, [lockedAssetId]);

  const [pickerOpen, setPickerOpen] = useState(false);
  const [assetFormOpen, setAssetFormOpen] = useState(false);

  const selectedAsset: Asset | undefined = useMemo(
    () => assets.find((a) => a.assetId === assetId),
    [assets, assetId],
  );

  useEffect(() => { if (status !== "점검완료") setConfirmer(""); }, [status]);

  const submit = () => {
    if (!assetId) { alert("점검 대상(물건)을 선택해주세요."); return; }
    onSubmit({
      resultId: initial?.resultId,
      taskId, year, assetId,
      inspector: inspector.trim(),
      inspectedAt,
      status,
      confirmer: status === "점검완료" ? confirmer.trim() : "",
      customValues: values,
    });
  };

  return (
    <div className="form-card space-y-6">
      <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
        <Field label="점검연">
          <select value={year} onChange={(e) => setYear(Number(e.target.value))}
            className="w-full glass rounded-xl px-4 py-2.5 outline-none focus:ring-2 ring-primary/50">
            {YEAR_OPTIONS.map((y) => <option key={y} value={y}>{y}</option>)}
          </select>
        </Field>
        <Field label="점검자">
          <input value={inspector} onChange={(e) => setInspector(e.target.value)} maxLength={20}
            className="w-full glass rounded-xl px-4 py-2.5 outline-none focus:ring-2 ring-primary/50" />
        </Field>
      </div>

      <Field label="점검 대상">
        <div className="space-y-3">
          {!lockedAssetId && (
            <div className="flex gap-2">
              <div className="flex-1 glass rounded-xl px-4 py-2.5 truncate min-h-[42px] flex items-center">
                {selectedAsset ? (
                  <span className="flex items-center gap-2">
                    <MapPin className="size-4 text-primary" />
                    <span className="font-medium">{selectedAsset.name}</span>
                  </span>
                ) : (
                  <span className="text-muted-foreground/70">선택된 대상이 없습니다</span>
                )}
              </div>
              <button type="button" onClick={() => setPickerOpen(true)}
                className="app-secondary-button">
                <Search className="size-4" /> 검색
              </button>
              <button type="button" onClick={() => setAssetFormOpen(true)}
                className="app-primary-button">
                <Plus className="size-4" /> 추가
              </button>
            </div>
          )}

          {selectedAsset && (
            <div className="glass rounded-xl p-4 grid grid-cols-1 md:grid-cols-3 gap-3 text-sm">
              <ReadOnlyField label="이름" value={selectedAsset.name} />
              <ReadOnlyField label="분류" value={selectedAsset.category} />
              <ReadOnlyField label="관할" value={selectedAsset.sido} />
              <ReadOnlyField label="주소지" value={`${selectedAsset.address} ${selectedAsset.addressDetail}`.trim()} className="md:col-span-3" />
            </div>
          )}
        </div>
      </Field>

      <Field label="점검일시">
        <input type="date" value={inspectedAt} onChange={(e) => setInspectedAt(e.target.value)}
          className="w-full glass rounded-xl px-4 py-2.5 outline-none focus:ring-2 ring-primary/50" />
      </Field>

      <Field label="점검 상태">
        <div className="flex flex-wrap gap-2">
          {STATUS_LIST.map((s) => (
            <label key={s}
              className={`px-4 py-2 rounded-xl cursor-pointer text-sm border flex items-center gap-2 transition-colors ${status === s ? "bg-primary/25 border-primary/50 text-primary" : "glass border-border hover:bg-muted"}`}>
              <input type="radio" name={`status-${taskId}-${initial?.resultId ?? "new"}`} className="sr-only" checked={status === s} onChange={() => setStatus(s)} />
              <span className={`size-2 rounded-full ${status === s ? "bg-primary" : "bg-[#aeb3aa]"}`} />
              {s}
            </label>
          ))}
        </div>
      </Field>

      <Field label="확인자">
        <input value={confirmer} onChange={(e) => setConfirmer(e.target.value)} maxLength={20}
          disabled={status !== "점검완료"}
          placeholder={status === "점검완료" ? "확인자 이름" : "점검완료 시 입력 가능"}
          className="w-full glass rounded-xl px-4 py-2.5 outline-none focus:ring-2 ring-primary/50 disabled:opacity-40 disabled:cursor-not-allowed" />
      </Field>

      {customFields.length > 0 && (
        <div className="space-y-5 pt-2 border-t border-border">
          <div className="text-xs uppercase tracking-[0.2em] text-muted-foreground">점검 항목</div>
          {customFields.map((f) => (
            <Field key={f.id} label={f.name}>
              <CustomFieldInput field={f}
                value={values[f.id] ?? defaultValueFor(f)}
                onChange={(v) => setValues((s) => ({ ...s, [f.id]: v }))} />
            </Field>
          ))}
        </div>
      )}

      {showActions && (
        <div className="flex flex-col sm:flex-row justify-between gap-2 pt-5 border-t border-border">
          {onDelete ? (
            <button onClick={onDelete}
              className="danger-button">
              삭제
            </button>
          ) : <span />}
          <div className="flex gap-2 justify-end">
            {onCancel && <button onClick={onCancel} className="app-secondary-button">취소</button>}
            <button onClick={submit}
              className="app-primary-button">
              {submitLabel}
            </button>
          </div>
        </div>
      )}

      <AssetPickerDialog open={pickerOpen} onClose={() => setPickerOpen(false)} onPick={(a) => setAssetId(a.assetId)} />
      <AssetFormDialog open={assetFormOpen} onClose={() => setAssetFormOpen(false)}
        onSaved={(a) => { setAssetId(a.assetId); store.get(); }} />
    </div>
  );
}

function CustomFieldInput({
  field, value, onChange,
}: { field: CustomField; value: CustomValue; onChange: (v: CustomValue) => void }) {
  if (field.type === "photo") {
    const arr = Array.isArray(value) ? value : [];
    return <PhotoInput value={arr} onChange={onChange} max={Math.max(1, field.length || 1)} />;
  }
  if (field.type === "number") {
    return (
      <input type="number" value={value as string | number}
        onChange={(e) => {
          const raw = e.target.value;
          if (field.length > 0 && raw.replace("-", "").length > field.length) return;
          onChange(raw);
        }}
        className="w-full glass rounded-xl px-4 py-2.5 outline-none focus:ring-2 ring-primary/50" />
    );
  }
  return (
    <input value={value as string} onChange={(e) => onChange(e.target.value)}
      maxLength={field.length || 200}
      className="w-full glass rounded-xl px-4 py-2.5 outline-none focus:ring-2 ring-primary/50" />
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <label className="text-xs uppercase tracking-wider text-muted-foreground font-medium">{label}</label>
      <div className="mt-1.5">{children}</div>
    </div>
  );
}

function ReadOnlyField({ label, value, className = "" }: { label: string; value: string; className?: string }) {
  return (
    <div className={className}>
      <div className="text-[10px] uppercase tracking-wider text-muted-foreground">{label}</div>
      <div className="text-sm mt-0.5">{value || "—"}</div>
    </div>
  );
}
