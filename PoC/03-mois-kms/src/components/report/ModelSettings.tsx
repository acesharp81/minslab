import { useEffect, useMemo, useState } from "react";
import { Bot, ChevronDown, SlidersHorizontal } from "lucide-react";
import { apiRequest, type AIModelOption, type AIModelResponse } from "@/lib/api";
import type { ReportAISettings } from "@/lib/report.functions";

const STORAGE_KEY = "minslab-mois-kms-ai-settings";

export function useReportAISettings() {
  const [models, setModels] = useState<AIModelOption[]>([]);
  const [providers, setProviders] = useState<AIModelResponse["providers"]>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [settings, setSettings] = useState<ReportAISettings>({
    model: "",
    temperature: 0.2,
    max_tokens: 1200,
    system_prompt: "",
  });

  useEffect(() => {
    apiRequest<AIModelResponse>("/models")
      .then((response) => {
        let saved: Partial<ReportAISettings> = {};
        try { saved = JSON.parse(localStorage.getItem(STORAGE_KEY) || "{}"); } catch { saved = {}; }
        const values = new Set(response.models.map((model) => model.value));
        setModels(response.models);
        setProviders(response.providers);
        setSettings({
          model: typeof saved.model === "string" && values.has(saved.model) ? saved.model : response.default,
          temperature: typeof saved.temperature === "number" ? saved.temperature : response.settings.temperature,
          max_tokens: typeof saved.max_tokens === "number" ? saved.max_tokens : response.settings.max_tokens,
          system_prompt: typeof saved.system_prompt === "string" ? saved.system_prompt : "",
        });
      })
      .catch((reason) => setError(reason instanceof Error ? reason.message : "모델 목록을 불러오지 못했습니다."))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    if (!settings.model) return;
    localStorage.setItem(STORAGE_KEY, JSON.stringify(settings));
  }, [settings]);

  return { settings, setSettings, models, providers, loading, error, ready: !loading && Boolean(settings.model) };
}

export function ModelSettingsPanel({
  settings,
  setSettings,
  models,
  providers,
  loading,
  error,
}: {
  settings: ReportAISettings;
  setSettings: React.Dispatch<React.SetStateAction<ReportAISettings>>;
  models: AIModelOption[];
  providers: AIModelResponse["providers"];
  loading: boolean;
  error: string | null;
}) {
  const selected = useMemo(() => models.find((model) => model.value === settings.model), [models, settings.model]);

  return (
    <section className="model-settings-card">
      <div className="model-settings-head">
        <div>
          <span className="section-kicker">AI REPORT ENGINE</span>
          <h2><Bot className="h-5 w-5" /> 보고서 생성 모델</h2>
          <p>서버 키를 브라우저에 노출하지 않고 선택한 제공자로 보고서를 생성합니다.</p>
        </div>
        <div className="provider-statuses">
          {Object.entries(providers).map(([key, provider]) => (
            <span key={key} className={provider.configured ? "is-ready" : "is-off"}>
              <i /> {provider.label}
            </span>
          ))}
        </div>
      </div>

      <div className="model-select-row">
        <label>
          모델
          <select
            value={settings.model}
            onChange={(event) => setSettings((current) => ({ ...current, model: event.target.value }))}
            disabled={loading || !models.length}
          >
            {loading && <option value="">모델 확인 중...</option>}
            {!loading && !models.length && <option value="">사용 가능한 모델 없음</option>}
            {models.map((model) => (
              <option key={model.value} value={model.value} disabled={!model.available}>
                {model.label}{model.available ? "" : " · 설정 필요"}
              </option>
            ))}
          </select>
        </label>
        <div className="selected-model-meta">
          <strong>{selected?.label ?? "모델을 선택하세요"}</strong>
          <span>{selected?.provider === "ollama" ? "서버 내부 실행" : "보호된 서버 API 호출"}</span>
        </div>
      </div>

      {error && <p className="model-error">{error}</p>}

      <details className="model-advanced">
        <summary><SlidersHorizontal className="h-4 w-4" /> 생성 옵션 <ChevronDown className="h-4 w-4" /></summary>
        <div className="model-option-grid">
          <label>
            창의성 · {settings.temperature.toFixed(1)}
            <input
              type="range"
              min="0"
              max="1.5"
              step="0.1"
              value={settings.temperature}
              onChange={(event) => setSettings((current) => ({ ...current, temperature: Number(event.target.value) }))}
            />
          </label>
          <label>
            최대 출력 토큰
            <select
              value={settings.max_tokens}
              onChange={(event) => setSettings((current) => ({ ...current, max_tokens: Number(event.target.value) }))}
            >
              <option value={512}>512 · 간결</option>
              <option value={1200}>1,200 · 권장</option>
              <option value={2048}>2,048 · 상세</option>
              <option value={4096}>4,096 · 최대</option>
            </select>
          </label>
          <label className="system-prompt-field">
            시스템 프롬프트 · 비워두면 보고서 유형별 기본값 사용
            <textarea
              rows={5}
              maxLength={8000}
              value={settings.system_prompt ?? ""}
              onChange={(event) => setSettings((current) => ({ ...current, system_prompt: event.target.value }))}
              placeholder="예: 중앙부처 개조식으로 작성하고 확인되지 않은 내용은 추측하지 마세요."
            />
          </label>
        </div>
      </details>
    </section>
  );
}
