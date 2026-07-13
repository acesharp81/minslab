import { supabase } from "@/integrations/supabase/client";

const API_BASE = "/api/poc/mois-kms";

type ApiOptions = {
  method?: "GET" | "POST";
  data?: unknown;
  auth?: boolean;
};

export async function apiRequest<T>(path: string, options: ApiOptions = {}): Promise<T> {
  const headers: Record<string, string> = { Accept: "application/json" };
  if (options.data !== undefined) headers["Content-Type"] = "application/json";

  if (options.auth) {
    const { data } = await supabase.auth.getSession();
    const token = data.session?.access_token;
    if (!token) throw new Error("로그인이 필요합니다.");
    headers.Authorization = `Bearer ${token}`;
  }

  const response = await fetch(`${API_BASE}${path}`, {
    method: options.method ?? (options.data === undefined ? "GET" : "POST"),
    headers,
    body: options.data === undefined ? undefined : JSON.stringify(options.data),
  });
  const text = await response.text();
  let body: any = {};
  try {
    body = text ? JSON.parse(text) : {};
  } catch {
    body = { error: text || `HTTP ${response.status}` };
  }
  if (!response.ok) throw new Error(body.error || body.detail || `요청 실패 (${response.status})`);
  return body as T;
}

export type AIModelOption = {
  value: string;
  label: string;
  provider: "ollama" | "huggingface" | "openrouter";
  available: boolean;
  details?: Record<string, unknown>;
};

export type AIModelResponse = {
  models: AIModelOption[];
  default: string;
  settings: { temperature: number; max_tokens: number };
  providers: Record<string, { configured: boolean; label: string }>;
};
