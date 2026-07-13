export function AppBrand({ centered = false }: { centered?: boolean }) {
  return (
    <div className={`app-brand ${centered ? "is-centered" : ""}`}>
      <a className="app-brand-mark" href="/poc?project=mois-kms" target="_top" aria-label="MinsLab PoC로 돌아가기">
        <span>MI</span>
      </a>
      <div>
        <strong>MoIS KMS</strong>
        <small>MinsLab · 통합 업무관리시스템</small>
      </div>
    </div>
  );
}
