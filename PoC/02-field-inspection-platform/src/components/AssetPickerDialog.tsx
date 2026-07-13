import { useEffect, useMemo, useState } from "react";
import { useStore, type Asset } from "@/lib/store";
import { Search, X, MapPin } from "lucide-react";

interface Props {
  open: boolean;
  onClose: () => void;
  onPick: (a: Asset) => void;
}

export function AssetPickerDialog({ open, onClose, onPick }: Props) {
  const assets = useStore((s) => s.assets);
  const [q, setQ] = useState("");

  useEffect(() => {
    if (open) setQ("");
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  const filtered = useMemo(() => {
    if (!q.trim()) return assets;
    const n = q.toLowerCase();
    return assets.filter(
      (a) =>
        a.name.toLowerCase().includes(n) ||
        a.address.toLowerCase().includes(n) ||
        a.sido.toLowerCase().includes(n),
    );
  }, [assets, q]);

  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 grid place-items-center p-4 bg-black/50 backdrop-blur-sm">
      <div className="modal-card w-full max-w-xl max-h-[80vh] flex flex-col">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-lg font-semibold">점검 대상 검색</h3>
          <button onClick={onClose} className="size-8 grid place-items-center rounded-lg hover:bg-muted">
            <X className="size-4" />
          </button>
        </div>
        <div className="glass rounded-xl px-4 py-2.5 flex items-center gap-2 mb-3">
          <Search className="size-4 text-muted-foreground" />
          <input autoFocus value={q} onChange={(e) => setQ(e.target.value)}
            placeholder="이름, 주소, 관할로 검색"
            className="flex-1 bg-transparent outline-none placeholder:text-muted-foreground/60" />
        </div>
        <div className="overflow-y-auto -mx-2 px-2 space-y-2">
          {filtered.length === 0 ? (
            <div className="text-center text-muted-foreground py-10">결과가 없습니다.</div>
          ) : (
            filtered.map((a) => (
              <button key={a.assetId} onClick={() => { onPick(a); onClose(); }}
                className="w-full text-left glass rounded-xl p-3 hover:bg-muted transition-colors flex gap-3 items-start">
                <div className="size-9 rounded-lg glass-strong grid place-items-center shrink-0">
                  <MapPin className="size-4 text-primary" />
                </div>
                <div className="min-w-0 flex-1">
                  <div className="font-medium truncate">{a.name}</div>
                  <div className="text-xs text-muted-foreground mt-0.5 truncate">
                    [{a.category}] {a.address} {a.addressDetail}
                  </div>
                  <div className="text-[11px] text-primary/80 mt-0.5">{a.sido}</div>
                </div>
              </button>
            ))
          )}
        </div>
      </div>
    </div>
  );
}
