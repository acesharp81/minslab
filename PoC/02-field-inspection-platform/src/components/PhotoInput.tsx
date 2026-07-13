import { useRef } from "react";
import { ImagePlus, X } from "lucide-react";

export function PhotoInput({ value, onChange, max = 4 }: { value: string[]; onChange: (v: string[]) => void; max?: number }) {
  const inputRef = useRef<HTMLInputElement>(null);
  const handle = async (files: FileList | null) => {
    if (!files) return;
    const arr = Array.from(files).slice(0, max - value.length);
    const reads = await Promise.all(
      arr.map(
        (f) =>
          new Promise<string>((res) => {
            const r = new FileReader();
            r.onload = () => res(r.result as string);
            r.readAsDataURL(f);
          }),
      ),
    );
    onChange([...value, ...reads]);
  };
  return (
    <div className="flex flex-wrap gap-3">
      {value.map((src, i) => (
        <div key={i} className="relative size-24 rounded-xl overflow-hidden glass">
          <img src={src} alt="" className="size-full object-cover" />
          <button type="button" onClick={() => onChange(value.filter((_, j) => j !== i))}
            className="absolute top-1 right-1 size-6 grid place-items-center rounded-full bg-black/60 hover:bg-black/80">
            <X className="size-3.5" />
          </button>
        </div>
      ))}
      {value.length < max && (
        <button type="button" onClick={() => inputRef.current?.click()}
          className="size-24 rounded-xl glass grid place-items-center hover:bg-muted transition-colors text-muted-foreground">
          <ImagePlus className="size-6" />
          <input ref={inputRef} type="file" accept="image/*" multiple className="hidden"
            onChange={(e) => handle(e.target.files)} />
        </button>
      )}
    </div>
  );
}
