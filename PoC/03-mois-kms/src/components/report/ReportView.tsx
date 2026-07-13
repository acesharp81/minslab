import { useState } from "react";
import { Copy, Loader2, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { toast } from "sonner";

type Props = {
  title: string;
  subtitle?: string;
  report: string | null;
  loading: boolean;
  error: string | null;
  onRegenerate: () => void;
};

export function ReportView({
  title,
  subtitle,
  report,
  loading,
  error,
  onRegenerate,
}: Props) {
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    if (!report) return;
    try {
      await navigator.clipboard.writeText(report);
      setCopied(true);
      toast.success("보고서가 복사되었습니다.");
      setTimeout(() => setCopied(false), 2000);
    } catch {
      toast.error("복사에 실패했습니다.");
    }
  };

  return (
    <div className="glass-panel rounded-3xl p-6">
      <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-xl font-bold">{title}</h2>
          {subtitle && (
            <p className="mt-1 text-sm text-muted-foreground">{subtitle}</p>
          )}
        </div>
        <div className="flex gap-2">
          <Button
            variant="secondary"
            size="sm"
            onClick={onRegenerate}
            disabled={loading}
            className="gap-1.5"
          >
            <RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} />
            다시 생성
          </Button>
          <Button
            size="sm"
            onClick={handleCopy}
            disabled={!report || loading}
            className="gap-1.5"
          >
            <Copy className="h-4 w-4" />
            {copied ? "복사됨" : "복사하기"}
          </Button>
        </div>
      </div>

      {loading && (
        <div className="flex items-center gap-2 rounded-2xl bg-white/40 p-8 text-sm text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" />
          AI가 보고서를 작성하는 중입니다...
        </div>
      )}

      {error && !loading && (
        <div className="rounded-2xl bg-destructive/10 p-4 text-sm text-destructive">
          {error}
        </div>
      )}

      {report && !loading && (
        <article className="prose prose-sm max-w-none whitespace-pre-wrap rounded-2xl bg-white/50 p-6 leading-relaxed text-foreground">
          {report}
        </article>
      )}
    </div>
  );
}