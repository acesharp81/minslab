/** Report only call metadata to the shared local meter. No prompt, response or session ID. */
export async function recordAiUsage(input: {
  model: string;
  workload?: "order_interpretation" | "order_ranking" | "order_selection" | "menu_import";
  status: "COMPLETED" | "FAILED";
  httpStatus: number;
  inputTokens?: number;
  outputTokens?: number;
  costUsd?: number;
}): Promise<void> {
  const token = process.env.POC09_METER_TOKEN;
  if (!token) return;
  try {
    await fetch(process.env.POC09_METER_URL || "http://127.0.0.1:18071/internal/usage-events", {
      method: "POST",
      signal: AbortSignal.timeout(1000),
      headers: { "Content-Type": "application/json", "X-Minslab-Meter-Token": token },
      body: JSON.stringify({
        event_id: crypto.randomUUID(),
        project: "poc09",
        workload: input.workload || "order_interpretation",
        provider: "openrouter",
        model: input.model.slice(0, 180),
        status: input.status,
        http_status: input.httpStatus,
        input_tokens: input.inputTokens || 0,
        output_tokens: input.outputTokens || 0,
        cost_usd: input.costUsd ?? null,
      }),
    });
  } catch {
    // Meter outages cannot block a visitor's order; the OpenRouter key cap remains authoritative.
  }
}
