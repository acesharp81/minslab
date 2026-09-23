import type { OrderIntent, Recommendation } from "./types";

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
): Promise<{ recommendations: Recommendation[]; provider: string }> {
  if (
    process.env.POC09_DECISION_PROVIDER !== "jev-openrouter" ||
    !process.env.OPENROUTER_API_KEY ||
    candidates.length < 2
  )
    return { recommendations: candidates, provider: "rules" };
  try {
    const response = await fetch(
      "https://openrouter.ai/api/v1/chat/completions",
      {
        method: "POST",
        signal: AbortSignal.timeout(2500),
        headers: {
          Authorization: `Bearer ${process.env.OPENROUTER_API_KEY}`,
          "Content-Type": "application/json",
          "HTTP-Referer": "https://www.minslab.kr",
          "X-Title": "Mwomeokji PoC9",
        },
        body: JSON.stringify({
          model: process.env.POC09_JEV_MODEL || "typesafe/jev-1.13",
          temperature: 0,
          response_format: { type: "json_object" },
          messages: [
            {
              role: "system",
              content:
                "You are a bounded menu ordering ranker. Return JSON {confidence: 0..1, orderedIds: string[]} using every supplied ID exactly once. Never create menu facts, alter prices or reason about allergen safety. Candidates were already checked by code.",
            },
            {
              role: "user",
              content: JSON.stringify({
                context: {
                  peopleCount: intent.peopleCount,
                  wantsWarm: intent.wantsWarm,
                  wantsCool: intent.wantsCool,
                  wantsMild: intent.wantsMild,
                  category: intent.category,
                },
                candidates: candidates.map(({ item, score }) => ({
                  id: item.id,
                  tags: item.tags,
                  spiceLevel: item.spiceLevel,
                  popularity: item.popularity,
                  score,
                })),
              }),
            },
          ],
        }),
      },
    );
    if (!response.ok) return { recommendations: candidates, provider: "rules" };
    const data = await response.json();
    const ranked = applyBoundedRanking(
      candidates,
      JSON.parse(data.choices?.[0]?.message?.content || "{}"),
    );
    return {
      recommendations: ranked,
      provider: ranked === candidates ? "rules" : "jev-openrouter",
    };
  } catch {
    return { recommendations: candidates, provider: "rules" };
  }
}
