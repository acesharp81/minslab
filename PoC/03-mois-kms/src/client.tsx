import "./styles.css";

type PublicConfig = {
  supabase_url: string;
  supabase_publishable_key: string;
};

declare global {
  interface Window {
    __MOIS_KMS_CONFIG__?: PublicConfig;
  }
}

async function bootstrap() {
  const container = document.getElementById("root");
  if (!container) throw new Error("통합 업무관리시스템의 root 요소를 찾지 못했습니다.");

  try {
    const response = await fetch("/api/poc/mois-kms/public-config", { cache: "no-store" });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(payload.error || "MinsLab Supabase 공개 설정을 불러오지 못했습니다.");
    window.__MOIS_KMS_CONFIG__ = payload as PublicConfig;
    const { mountApp } = await import("./app");
    mountApp(container);
  } catch (error) {
    const message = error instanceof Error ? error.message : "서비스 설정을 확인하지 못했습니다.";
    container.innerHTML = `
      <main class="app-page flex min-h-screen items-center justify-center">
        <section class="paper-card max-w-lg rounded-2xl p-8 text-center">
          <span class="section-kicker">CONFIGURATION REQUIRED</span>
          <h1 class="mt-3 text-2xl font-bold">MinsLab Supabase 연결 준비 중</h1>
          <p class="mt-3 text-sm leading-relaxed text-muted-foreground">${escapeHtml(message)}</p>
          <a class="app-primary-link mt-6" href="/poc?project=mois-kms" target="_top">PoC 목록으로</a>
        </section>
      </main>`;
  }
}

function escapeHtml(value: string) {
  return value.replace(/[&<>"']/g, (character) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  })[character] || character);
}

bootstrap();
