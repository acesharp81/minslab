import { Link } from "@tanstack/react-router";
import {
  ArrowUpRight,
  BarChart3,
  ClipboardList,
  LayoutDashboard,
  Settings2,
} from "lucide-react";
import { Background } from "./Background";

export function Shell({ children }: { children: React.ReactNode }) {
  const navLink = "app-nav-link";
  const active = { className: "app-nav-link is-active" };

  return (
    <div className="inspection-app">
      <Background />
      <header className="inspection-header">
        <div className="inspection-header-inner">
          <Link to="/" className="app-brand">
            <span className="app-brand-mark">MI</span>
            <span className="app-brand-copy">
              <strong>재난안전정보시스템 · 현장점검 지원플랫폼</strong>
              <small>MINSLAB / FIELD OPERATIONS POC 02</small>
            </span>
          </Link>

          <div className="app-header-actions">
            <nav className="app-nav" aria-label="현장점검 주요 메뉴">
              <Link to="/" className={navLink} activeOptions={{ exact: true }} activeProps={active}>
                <LayoutDashboard className="size-3.5" /> 업무 현황
              </Link>
              <Link to="/statistics" className={navLink} activeProps={active}>
                <BarChart3 className="size-3.5" /> 점검 통계
              </Link>
              <Link to="/admin" className={navLink} activeProps={active}>
                <Settings2 className="size-3.5" /> 관리자
              </Link>
            </nav>
            <a
              href="/poc?project=field-inspection-platform"
              target="_top"
              className="app-home-link"
            >
              <ClipboardList className="size-3.5" />
              MinsLab PoC
              <ArrowUpRight className="size-3.5" />
            </a>
          </div>
        </div>
      </header>
      <main className="app-main">{children}</main>
    </div>
  );
}
