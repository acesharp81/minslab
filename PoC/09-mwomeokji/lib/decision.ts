import type { OrderIntent, Recommendation } from "./types";
import { recordAiUsage } from "./usage-meter";

export function applyBoundedRanking(
  candidates: Recommendation[],
  output: unknown,
  minConfidence = 0.7,
): Recommendation[] {
  if (!output || typeof output !== "object") return candidates;
  const result = output as { confidence?: unknown; orderedIds?: unknown };
  if (
    typeof result.confidence !== "number" ||
    result.confidence < minConfidence ||
    result.confidence > 1 ||
    !Array.isArray(result.orderedIds)
  )
    return candidates;
  const ids = result.orderedIds;
  const known = new Set(candidates.map((candidate) => candidate.item.id));
  if (
    ids.length !== candidates.length ||
    ids.some((id) => typeof id !== "string" || !known.has(id)) ||
    new Set(ids).size !== ids.length
  )
    return candidates;
  const byId = new Map(
    candidates.map((candidate) => [candidate.item.id, candidate]),
  );
  return ids.map((id) => byId.get(id as string)!);
}

export async function rankRecommendations(
  candidates: Recommendation[],
  intent: OrderIntent,
): Promise<{ recommendations: Recommendation[]; provider: string; usage?: { inputTokens: number; outputTokens: number; costUsd?: number } }> {
  if (
    process.env.POC09_DECISION_PROVIDER !== "jev-openrouter" ||
    !process.env.OPENROUTER_API_KEY ||
    candidates.length < 2
  ) return { recommendations: candidates, provider: "rules" };
  const model = process.env.POC09_JEV_MODEL || "typesafe/jev-1.13";
  try {
    // Jev accepts typed decisions, not chat completions. Only verified candidate metadata is sent.
    const response = await fetch("https://openrouter.ai/api/alpha/decisions", {
      method: "POST",
      signal: AbortSignal.timeout(2500),
      headers: {
        Authorization: `Bearer ${process.env.OPENROUTER_API_KEY}`,
        "Content-Type": "application/json",
        "HTTP-Referer": "https://www.minslab.kr",
        "X-Title": "Mwomeokji PoC9",
      },
      body: JSON.stringify({
        model,
        state: {
          context: {
            peopleCount: intent.peopleCount,
            wantsWarm: intent.wantsWarm,
            wantsCool: intent.wantsCool,
            wantsMild: intent.wantsMild,
            category: intent.category,
          },
        },
        questions: {
          best: {
            type: "choice",
            instructions: "Which already verified candidate best fits the context? Use the candidate descriptions and rule scores. Do not infer missing food, safety or price facts.",
            criteria: Object.fromEntries(candidates.map(({ item, score }) => [
              item.id,
              `tags: ${item.tags.join(", ")}; spice: ${item.spiceLevel}; popularity: ${item.popularity}; rule score: ${score}`,
            ])),
          },
        },
      }),
    });
    const data = await response.json().catch(() => ({})) || {};
    const tokens = data.usage || {};
    const usage = {
      inputTokens: Number.isFinite(tokens.input_tokens) ? tokens.input_tokens : 0,
      outputTokens: Number.isFinite(tokens.output_tokens) ? tokens.output_tokens : 0,
      costUsd: Number.isFinite(tokens.cost) ? tokens.cost : undefined,
    };
    const answer = data.answers?.best;
    const probabilities = answer?.probabilities;
    const ids = candidates.map((candidate) => candidate.item.id);
    const valid = answer?.type === "choice" && ids.includes(answer.choice) &&
      typeof answer.confidence === "number" && answer.confidence >= 0.7 && answer.confidence <= 1 &&
      probabilities && typeof probabilities === "object" &&
      Object.keys(probabilities).length === ids.length &&
      ids.every((id) => typeof probabilities[id] === "number" &&
        Number.isFinite(probabilities[id]) && probabilities[id] >= 0 && probabilities[id] <= 1);
    const orderedIds = valid
      ? [...ids].sort((a, b) => probabilities[b] - probabilities[a])
      : [];
    const ranked = response.ok && valid
      ? applyBoundedRanking(candidates, { confidence: answer.confidence, orderedIds })
      : candidates;
    await recordAiUsage({ workload: "order_ranking", model: typeof data.model === "string" ? data.model : model,
      status: response.ok && valid ? "COMPLETED" : "FAILED", httpStatus: response.status, ...usage });
    return { recommendations: ranked, provider: ranked === candidates ? "rules" : "jev-openrouter", usage };
  } catch {
    await recordAiUsage({ workload: "order_ranking", model, status: "FAILED", httpStatus: 0 });
    return { recommendations: candidates, provider: "rules" };
  }
}
