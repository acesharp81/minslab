import { recordAiUsage } from "./usage-meter";

export type FreeProvider = "groq" | "openrouter";
export type StructuredReply<T> = {
  value: T | null;
  provider: FreeProvider | "rules";
  model?: string;
  inputTokens: number;
  outputTokens: number;
  httpStatus?: number;
  errorCode?: string;
  retryAfterSeconds?: number;
};

export async function requestFreeStructured<T>(
  schema: unknown,
  system: string,
  input: unknown,
  validate: (value: unknown) => T | null,
  workload: "order_interpretation" | "order_selection",
  maxTokens = 700,
  format: "strict" | "json" = "strict",
): Promise<StructuredReply<T>> {
  const selected = process.env.POC09_CONVERSATION_PROVIDER;
  const provider: FreeProvider | null = selected === "groq" || selected === "openrouter" ? selected : null;
  const empty: StructuredReply<T> = { value: null, provider: "rules", inputTokens: 0, outputTokens: 0 };
  if (!provider) return empty;
  const key = provider === "groq" ? process.env.GROQ_API_KEY : process.env.OPENROUTER_API_KEY;
  if (!key) return empty;
  const model = process.env.POC09_LLM_MODEL || (provider === "groq" ? "openai/gpt-oss-20b" : "");
  // An OpenRouter API key can pay for both free and paid models. Require a pinned free ID.
  if (provider === "openrouter" && !model.endsWith(":free")) return empty;
  if (provider === "groq" && !new Set(["openai/gpt-oss-20b", "openai/gpt-oss-120b"]).has(model)) return empty;
  const url = provider === "groq"
    ? "https://api.groq.com/openai/v1/chat/completions"
    : "https://openrouter.ai/api/v1/chat/completions";
  let status = 0;
  let inputTokens = 0;
  let outputTokens = 0;
  try {
    const response = await fetch(url, {
      method: "POST",
      signal: AbortSignal.timeout(12000),
      headers: {
        Authorization: `Bearer ${key}`,
        "Content-Type": "application/json",
        ...(provider === "openrouter" ? {
          "HTTP-Referer": "https://www.minslab.kr",
          "X-Title": "Mwomeokji PoC9",
        } : {}),
      },
      body: JSON.stringify({
        model, temperature: 0, max_tokens: maxTokens,
        ...(provider === "groq" ? { reasoning_effort: "low" } : {}),
        ...(provider === "openrouter" ? { provider: { require_parameters: true, data_collection: "deny", zdr: true } } : {}),
        response_format: format === "strict"
          ? { type: "json_schema", json_schema: { name: workload, strict: true, schema } }
          : { type: "json_object" },
        messages: [
          { role: "system", content: format === "json" ? `${system}\nReturn valid JSON matching this schema: ${JSON.stringify(schema)}` : system },
          { role: "user", content: typeof input === "string" ? input : JSON.stringify(input) },
        ],
      }),
    });
    status = response.status;
    const retryHeader = Number(response.headers?.get("retry-after"));
    const retryAfterSeconds = Number.isFinite(retryHeader) && retryHeader > 0 ? Math.min(3600, Math.ceil(retryHeader)) : undefined;
    const data = await response.json().catch(() => ({})) as {
      choices?: Array<{ message?: { content?: string } }>;
      usage?: { prompt_tokens?: number; completion_tokens?: number };
      error?: { code?: string; type?: string };
    };
    inputTokens = Number.isFinite(data.usage?.prompt_tokens) ? data.usage!.prompt_tokens! : 0;
    outputTokens = Number.isFinite(data.usage?.completion_tokens) ? data.usage!.completion_tokens! : 0;
    let value: T | null = null;
    try {
      const content = data.choices?.[0]?.message?.content;
      if (response.ok && typeof content === "string") value = validate(JSON.parse(content));
    } catch { /* Fail closed. */ }
    await recordAiUsage({
      provider, model, workload, status: value === null ? "FAILED" : "COMPLETED",
      httpStatus: status, inputTokens, outputTokens,
    });
    const errorCode = data.error?.code || data.error?.type;
    if (provider === "groq" && format === "strict" && status === 400 && errorCode === "json_validate_failed")
      return requestFreeStructured(schema, system, input, validate, workload, maxTokens, "json");
    return { value, provider: value === null ? "rules" : provider, model, inputTokens, outputTokens, httpStatus: status, errorCode, retryAfterSeconds };
  } catch {
    await recordAiUsage({ provider, model, workload, status: "FAILED", httpStatus: status, inputTokens, outputTokens });
    return { ...empty, httpStatus: status };
  }
}
