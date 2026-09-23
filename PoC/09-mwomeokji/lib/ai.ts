import { parseIntent } from "./intent";
import type { OrderIntent } from "./types";

export async function understand(
  message: string,
): Promise<{ intent: OrderIntent; provider: string }> {
  const fallback = { intent: parseIntent(message), provider: "mock" };
  if (
    process.env.POC09_AI_PROVIDER !== "openrouter" ||
    !process.env.OPENROUTER_API_KEY
  )
    return fallback;
  try {
    const response = await fetch(
      "https://openrouter.ai/api/v1/chat/completions",
      {
        method: "POST",
        signal: AbortSignal.timeout(7000),
        headers: {
          Authorization: `Bearer ${process.env.OPENROUTER_API_KEY}`,
          "Content-Type": "application/json",
          "HTTP-Referer": "https://www.minslab.kr",
          "X-Title": "Mwomeokji PoC9",
        },
        body: JSON.stringify({
          model: process.env.POC09_LLM_MODEL || "openai/gpt-4o-mini",
          temperature: 0,
          response_format: { type: "json_object" },
          messages: [
            {
              role: "system",
              content:
                "Extract only user ordering intent as JSON. Fields: action (recommend/add/remove/ask/help), peopleCount, totalBudget KRW, maxSpiceLevel 0-4, wantsWarm, wantsCool, wantsMild, vegetarian, avoidPork, avoidBeef, category, menuName, quantity. Never invent menu, price, ingredients or safety. No personal data.",
            },
            { role: "user", content: message.slice(0, 500) },
          ],
        }),
      },
    );
    if (!response.ok) return fallback;
    const result = await response.json();
    const parsed = JSON.parse(result.choices?.[0]?.message?.content || "{}");
    if (!["recommend", "add", "remove", "ask", "help"].includes(parsed.action))
      return fallback;
    return {
      intent: { ...fallback.intent, ...parsed },
      provider: "openrouter",
    };
  } catch {
    return fallback;
  }
}
