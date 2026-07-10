import { Link } from "@tanstack/react-router";
import { Background } from "./Background";
import { Sparkles } from "lucide-react";

export function Shell({ children }: { children: React.ReactNode }) {
  const navLink = "px-3 py-1.5 rounded-lg hover:bg-white/10 transition-colors";
  const active = { className: "px-3 py-1.5 rounded-lg bg-white/15" };
  return (
    <div className="relative min-h-screen">
      <Background />
      <header className="sticky top-0 z-30">
        <div className="mx-auto max-w-7xl px-4 md:px-8 pt-4">
          <div className="glass rounded-2xl px-5 py-3 flex flex-col items-stretch gap-3 lg:flex-row lg:items-center lg:justify-between">
            <Link to="/" className="flex min-w-0 items-center gap-2 group cursor-pointer hover:opacity-80 transition-opacity">
              <div className="size-9 rounded-xl glass-strong grid place-items-center">
                <Sparkles className="size-4 text-primary" />
              </div>
              <div className="leading-tight">
                <div className="font-display font-semibold tracking-tight">재난안전정보시스템 - 현장점검 지원플랫폼</div>
                <div className="text-[11px] text-muted-foreground -mt-0.5">Powered by Minisoft</div>
              </div>
            </Link>
            <nav className="flex flex-wrap items-center gap-1 text-xs sm:text-sm">
              <a href="/poc?project=field-inspection-platform" target="_top" className="px-3 py-1.5 rounded-lg hover:bg-white/10 transition-colors">MinsLab PoC</a>
              <Link to="/" className={navLink} activeOptions={{ exact: true }} activeProps={active}>Dashboard</Link>
              <Link to="/statistics" className={navLink} activeProps={active}>통계</Link>
              <Link to="/admin" className="px-3 py-1.5 rounded-lg glass-strong hover:bg-white/15 transition-colors" activeProps={{ className: "px-3 py-1.5 rounded-lg glass-strong bg-white/15" }}>
                관리자 메뉴
              </Link>
            </nav>
          </div>
        </div>
      </header>
      <main className="mx-auto max-w-7xl px-4 md:px-8 py-8">{children}</main>
    </div>
  );
}
