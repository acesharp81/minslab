import { useEffect, useRef, useState } from "react";
import { ASSET_CATEGORIES, SIDO_LIST, store, type Asset, type AssetCategory } from "@/lib/store";
import { MapPin, Search, X } from "lucide-react";

interface DaumPostcode {
  open: () => void;
}
interface DaumPostcodeOptions {
  oncomplete: (data: { roadAddress: string; jibunAddress: string; sido: string }) => void;
}
declare global {
  interface Window {
    daum?: { Postcode: new (opts: DaumPostcodeOptions) => DaumPostcode };
  }
}

const DAUM_SRC = "https://t1.daumcdn.net/mapjsapi/bundle/postcode/prod/postcode.v2.js";
let loader: Promise<void> | null = null;
function loadDaum() {
  if (typeof window === "undefined") return Promise.resolve();
  if (window.daum?.Postcode) return Promise.resolve();
  if (loader) return loader;
  loader = new Promise<void>((res, rej) => {
    const s = document.createElement("script");
    s.src = DAUM_SRC;
    s.async = true;
    s.onload = () => res();
    s.onerror = () => rej(new Error("postcode load failed"));
    document.head.appendChild(s);
  });
  return loader;
}

interface Props {
  open: boolean;
  initial?: Partial<Asset>;
  onClose: () => void;
  onSaved: (asset: Asset) => void;
}

export function AssetFormDialog({ open, initial, onClose, onSaved }: Props) {
  const [name, setName] = useState("");
  const [category, setCategory] = useState<AssetCategory>("시설물");
  const [address, setAddress] = useState("");
  const [detail, setDetail] = useState("");
  const [sido, setSido] = useState<string>(SIDO_LIST[0]);
  const detailRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!open) return;
    setName(initial?.name ?? "");
    setCategory((initial?.category as AssetCategory) ?? "시설물");
    setAddress(initial?.address ?? "");
    setDetail(initial?.addressDetail ?? "");
    setSido(initial?.sido ?? SIDO_LIST[0]);
  }, [open, initial]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  const openPostcode = async () => {
    try {
      await loadDaum();
      new window.daum!.Postcode({
        oncomplete: (data) => {
          setAddress(data.roadAddress || data.jibunAddress);
          const matched = SIDO_LIST.find((s) => s.startsWith(data.sido) || data.sido.startsWith(s.slice(0, 2)));
          if (matched) setSido(matched);
          setTimeout(() => detailRef.current?.focus(), 0);
        },
      }).open();
    } catch {
      const manual = prompt("도로명 주소를 입력하세요");
      if (manual) setAddress(manual);
    }
  };

  const save = () => {
    if (!name.trim() || !address.trim()) return;
    if (initial?.assetId) {
      store.updateAsset(initial.assetId, { name: name.trim(), category, address: address.trim(), addressDetail: detail.trim(), sido });
      const a = store.get().assets.find((x) => x.assetId === initial.assetId)!;
      onSaved(a);
    } else {
      const a = store.addAsset({ name: name.trim(), category, address: address.trim(), addressDetail: detail.trim(), sido });
      onSaved(a);
    }
    onClose();
  };

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 grid place-items-center p-4 bg-black/50 backdrop-blur-sm">
      <div className="modal-card w-full max-w-lg">
        <div className="flex items-center justify-between mb-5">
          <div className="flex items-center gap-2">
            <div className="size-9 rounded-xl glass grid place-items-center">
              <MapPin className="size-4 text-primary" />
            </div>
            <h3 className="text-lg font-semibold">{initial?.assetId ? "물건 수정" : "물건 등록"}</h3>
          </div>
          <button onClick={onClose} className="size-8 grid place-items-center rounded-lg hover:bg-muted">
            <X className="size-4" />
          </button>
        </div>

        <div className="space-y-4">
          <Field label="이름">
            <input value={name} onChange={(e) => setName(e.target.value)} maxLength={60}
              className="w-full glass rounded-xl px-4 py-2.5 outline-none focus:ring-2 ring-primary/50"
              placeholder="물건 이름" />
          </Field>

          <Field label="분류">
            <div className="flex flex-wrap gap-2">
              {ASSET_CATEGORIES.map((c) => (
                <button key={c} type="button" onClick={() => setCategory(c)}
                  className={`px-3 py-1.5 rounded-lg text-sm border ${category === c ? "bg-primary/25 border-primary/50 text-primary" : "glass border-border hover:bg-muted"}`}>
                  {c}
                </button>
              ))}
            </div>
          </Field>

          <Field label="도로명 주소">
            <div className="flex gap-2">
              <input value={address} readOnly placeholder="주소 검색을 눌러주세요"
                className="flex-1 glass rounded-xl px-4 py-2.5 outline-none placeholder:text-muted-foreground/60" />
              <button type="button" onClick={openPostcode}
                className="app-secondary-button">
                <Search className="size-4" /> 검색
              </button>
            </div>
          </Field>

          <Field label="상세주소">
            <input ref={detailRef} value={detail} onChange={(e) => setDetail(e.target.value)} maxLength={100}
              className="w-full glass rounded-xl px-4 py-2.5 outline-none focus:ring-2 ring-primary/50"
              placeholder="동/호수, 구역 등" />
          </Field>

          <Field label="관할 시도">
            <select value={sido} onChange={(e) => setSido(e.target.value)}
              className="w-full glass rounded-xl px-4 py-2.5 outline-none focus:ring-2 ring-primary/50">
              {SIDO_LIST.map((s) => (<option key={s} value={s}>{s}</option>))}
            </select>
          </Field>
        </div>

        <div className="flex justify-end gap-2 mt-6 pt-5 border-t border-border">
          <button onClick={onClose} className="app-secondary-button">취소</button>
          <button onClick={save}
            className="app-primary-button">
            저장
          </button>
        </div>
      </div>
    </div>
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
