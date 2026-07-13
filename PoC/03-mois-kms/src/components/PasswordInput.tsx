import { useState, forwardRef } from "react";
import { Eye, EyeOff } from "lucide-react";
import { cn } from "@/lib/utils";

type Props = React.InputHTMLAttributes<HTMLInputElement>;

export const PasswordInput = forwardRef<HTMLInputElement, Props>(
  ({ className, ...props }, ref) => {
    const [visible, setVisible] = useState(false);
    const block = (e: React.SyntheticEvent) => e.preventDefault();
    return (
      <div className="relative">
        <input
          ref={ref}
          {...props}
          type={visible ? "text" : "password"}
          autoComplete="new-password"
          autoCorrect="off"
          spellCheck={false}
          onCopy={block}
          onPaste={block}
          onCut={block}
          onContextMenu={block}
          onDrop={block}
          className={cn(
            "glass-input flex h-11 w-full rounded-lg px-4 pr-11 text-sm placeholder:text-muted-foreground",
            className,
          )}
        />
        <button
          type="button"
          tabIndex={-1}
          onClick={() => setVisible((v) => !v)}
          className="absolute right-2.5 top-1/2 -translate-y-1/2 rounded-md p-1.5 text-muted-foreground hover:bg-foreground/5 hover:text-foreground"
          aria-label={visible ? "비밀번호 숨기기" : "비밀번호 보기"}
        >
          {visible ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
        </button>
      </div>
    );
  },
);
PasswordInput.displayName = "PasswordInput";