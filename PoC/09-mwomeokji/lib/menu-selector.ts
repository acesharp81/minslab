import { z } from "zod";
import type { Recommendation } from "./types";
import { recordAiUsage } from "./usage-meter";

export type MenuProposal = { id: string; recommendations: Recommendation[]; total: number };
export type MenuSelection = { proposal: MenuProposal | null; provider: "openrouter" | "rules"; usage?: { inputTokens: number; outputTokens: number; costUsd?: number } };

/** The model sees only the current turn and public catalog facts; saved guest context stays local. */
export async function selectMenuProposal(currentTurn: string, proposals: MenuProposal[]): Promise<MenuSelection> {
  const fallback: MenuSelection = { proposal: proposals[0] ?? null, provider: "rules" };
  if (proposals.length < 2 || process.env.POC09_MENU_SELECTOR_PROVIDER === "rules" ||
      process.env.POC09_CONVERSATION_PROVIDER !== "openrouter" || !process.env.OPENROUTER_API_KEY) return fallback;
  const model = process.env.POC09_MENU_SELECTOR_MODEL || process.env.POC09_LLM_MODEL || "openai/gpt-4.1-mini";
  const choices = [...proposals.map((proposal) => proposal.id), "no_match"];
  const schema = z.object({ choiceId: z.enum(choices as [string, ...string[]]), confidence: z.number().min(0).max(1) }).strict();
  try {
    const response = await fetch("https://openrouter.ai/api/v1/chat/completions", {
      method: "POST", signal: AbortSignal.timeout(8000),
      headers: { Authorization: `Bearer ${process.env.OPENROUTER_API_KEY}`, "Content-Type": "application/json",
        "HTTP-Referer": "https://www.minslab.kr", "X-Title": "Mwomeokji PoC9" },
      body: JSON.stringify({
        model, temperature: 0, max_tokens: 180,
        provider: { require_parameters: true, data_collection: "deny", zdr: true },
        response_format: { type: "json_schema", json_schema: { name: "bounded_menu_choice", strict: true,
          schema: { type: "object", properties: { choiceId: { type: "string", enum: choices },
            confidence: { type: "number", minimum: 0, maximum: 1 } },
            required: ["choiceId", "confidence"], additionalProperties: false } } },
        messages: [
          { role: "system", content: "Choose the best menu option for the customer's current utterance. The server has already verified all listed options against the customer's explicit and saved hard constraints, including caffeine, allergy, quantity, and budget. Trust that verification. Prioritize the customer's expressed food and flavor preferences. For a group asking for a filling meal, choose a complete option where each diner receives a main dish; drinks or sides cannot replace a person's meal. Select no_match only when the current utterance explicitly asks for a particular food, ingredient, or flavor that none of the listed options has; never select no_match merely because the request is broad or a verified safety claim is not repeated in the description. If the current utterance gives no preference that distinguishes eligible options, prefer the more popular option. The option ID is opaque. Return only the required JSON. Never invent a menu or change price, quantity, or safety facts." },
          { role: "user", content: JSON.stringify({ currentTurn: currentTurn.slice(0, 500), options: proposals.map((proposal) => ({
            id: proposal.id, total: proposal.total, serverVerified: true,
            dishes: proposal.recommendations.map(({ item }, slot) => ({ slot: slot + 1, id: item.id,
              name: item.name, description: item.description.slice(0, 160), price: item.price,
              popularity: item.popularity, spiceLevel: item.spiceLevel,
              caffeineFree: item.tags.includes("caffeine_free"), coffee: item.tags.includes("coffee"),
              tags: item.tags.slice(0, 12) })),
          })) }) },
        ],
      }),
    });
    const data = await response.json().catch(() => ({})) || {};
    let parsed: ReturnType<typeof schema.safeParse> | null = null;
    try { if (typeof data.choices?.[0]?.message?.content === "string") parsed = schema.safeParse(JSON.parse(data.choices[0].message.content)); } catch { /* fallback */ }
    const valid = response.ok && parsed?.success && parsed.data.confidence >= (parsed.data.choiceId === "no_match" ? 0.8 : 0.55);
    const usage = {
      inputTokens: Number.isFinite(data.usage?.prompt_tokens) ? data.usage.prompt_tokens : 0,
      outputTokens: Number.isFinite(data.usage?.completion_tokens) ? data.usage.completion_tokens : 0,
      costUsd: Number.isFinite(data.usage?.cost) ? data.usage.cost : undefined,
    };
    await recordAiUsage({ workload: "order_selection", model: typeof data.model === "string" ? data.model : model,
      status: valid ? "COMPLETED" : "FAILED", httpStatus: response.status, ...usage });
    if (!valid || !parsed?.success) return fallback;
    return { proposal: parsed.data.choiceId === "no_match" ? null : proposals.find((proposal) => proposal.id === parsed.data.choiceId) ?? null,
      provider: "openrouter", usage };
  } catch {
    await recordAiUsage({ workload: "order_selection", model, status: "FAILED", httpStatus: 0 });
    return fallback;
  }
}
