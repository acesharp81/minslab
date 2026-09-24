import { z } from "zod";
import { parseIntent } from "./intent";
import type { MemberUpdate } from "./dialogue";
import { recordAiUsage } from "./usage-meter";
import { ALLERGENS, DIET_RULES, type OrderIntent } from "./types";

export type Interpretation = {
  intent: OrderIntent;
  provider: "openrouter" | "rules";
  reference: "none" | "first" | "second" | "third" | "all" | "last";
  alternative: boolean;
  memberUpdates: MemberUpdate[];
  globalAllergies: string[];
  optionNames: string[];
  clarification: string | null;
  corrections: { clearVegetarian: boolean; clearSpiceLimit: boolean; clearBudget: boolean };
};

const allergyKeys = ALLERGENS.map(([key]) => key);
const dietKeys = DIET_RULES.map(([key]) => key);
const llmSchema = z.object({
  action: z.enum(["recommend", "add", "remove", "ask", "help", "checkout"]),
  peopleCount: z.number().int().min(1).max(12).nullable(),
  totalBudget: z.number().int().min(0).max(1000000).nullable(),
  maxSpiceLevel: z.number().int().min(0).max(4).nullable(),
  vegetarian: z.boolean().nullable(),
  wantsWarm: z.boolean().nullable(),
  wantsCool: z.boolean().nullable(),
  avoidPork: z.boolean().nullable(),
  avoidBeef: z.boolean().nullable(),
  category: z.string().max(30).nullable(),
  menuName: z.string().max(80).nullable(),
  quantity: z.number().int().min(1).max(30).nullable(),
  reference: z.enum(["none", "first", "second", "third", "all", "last"]),
  alternative: z.boolean(),
  globalAllergies: z.array(z.enum(allergyKeys as [string, ...string[]])).max(10),
  memberUpdates: z.array(z.object({
    label: z.string().trim().min(1).max(40),
    count: z.number().int().min(1).max(12),
    allergies: z.array(z.enum(allergyKeys as [string, ...string[]])).max(10),
    dietaryRules: z.array(z.enum(dietKeys as [string, ...string[]])).max(6),
    maxSpiceLevel: z.number().int().min(0).max(4).nullable(),
    removeDietaryRules: z.array(z.enum(dietKeys as [string, ...string[]])).max(6),
    clearSpiceLimit: z.boolean(),
    tastes: z.array(z.enum(["spicy", "mild", "sweet", "soup", "kids"])).max(5),
  })).max(12),
  optionNames: z.array(z.string().max(60)).max(12),
  clarification: z.string().max(160).nullable(),
  corrections: z.object({
    clearVegetarian: z.boolean(),
    clearSpiceLimit: z.boolean(),
    clearBudget: z.boolean(),
  }),
}).strict();

const stringOrNull = { type: ["string", "null"] };
const booleanOrNull = { type: ["boolean", "null"] };
const numberOrNull = { type: ["integer", "null"] };
const stringList = (values?: readonly string[]) => ({ type: "array", items: values ? { type: "string", enum: values } : { type: "string" } });
const memberProperties = {
  label: { type: "string" },
  count: { type: "integer" },
  allergies: stringList(allergyKeys),
  dietaryRules: stringList(dietKeys),
  maxSpiceLevel: numberOrNull,
  removeDietaryRules: stringList(dietKeys),
  clearSpiceLimit: { type: "boolean" },
  tastes: { type: "array", items: { type: "string", enum: ["spicy", "mild", "sweet", "soup", "kids"] } },
};
const correctionProperties = { clearVegetarian: { type: "boolean" }, clearSpiceLimit: { type: "boolean" }, clearBudget: { type: "boolean" } };
const schemaProperties = {
  action: { type: "string", enum: ["recommend", "add", "remove", "ask", "help", "checkout"] },
  peopleCount: numberOrNull,
  totalBudget: numberOrNull,
  maxSpiceLevel: numberOrNull,
  vegetarian: booleanOrNull,
  wantsWarm: booleanOrNull,
  wantsCool: booleanOrNull,
  avoidPork: booleanOrNull,
  avoidBeef: booleanOrNull,
  category: stringOrNull,
  menuName: stringOrNull,
  quantity: numberOrNull,
  reference: { type: "string", enum: ["none", "first", "second", "third", "all", "last"] },
  alternative: { type: "boolean" },
  globalAllergies: stringList(allergyKeys),
  memberUpdates: { type: "array", items: { type: "object", properties: memberProperties, required: Object.keys(memberProperties), additionalProperties: false } },
  optionNames: stringList(),
  clarification: stringOrNull,
  corrections: { type: "object", properties: correctionProperties, required: Object.keys(correctionProperties), additionalProperties: false },
};
const responseFormat = {
  type: "json_schema",
  json_schema: {
    name: "restaurant_order_turn",
    strict: true,
    schema: { type: "object", properties: schemaProperties, required: Object.keys(schemaProperties), additionalProperties: false },
  },
};

function scopedTastes(message: string): MemberUpdate[] {
  const clauses = [...message.matchAll(/(나|저|아이|아기|딸|아들|여아|남아|와이프|아내|남편)(?:는|은|에게는|한테는)\s*/g)];
  return clauses.map((match, index) => {
    const segment = message.slice(match.index! + match[0].length, clauses[index + 1]?.index ?? message.length);
    const tastes: NonNullable<MemberUpdate["tastes"]> = [];
    if (/매운|맵게|얼큰/.test(segment) && !/안\s*맵|맵지|매운.*(?:안|못)/.test(segment)) tastes.push("spicy");
    if (/안\s*맵|맵지|순한|매운.*(?:안|못)/.test(segment)) tastes.push("mild");
    if (/달달|달콤|단맛/.test(segment)) tastes.push("sweet");
    if (/국물|수프|탕|찌개/.test(segment)) tastes.push("soup");
    if (/키즈|어린이/.test(segment)) tastes.push("kids");
    return {
      label: match[1], count: 1, allergies: [], dietaryRules: [],
      maxSpiceLevel: tastes.includes("mild") ? 0 : null,
      removeDietaryRules: [], clearSpiceLimit: false, tastes,
    };
  }).filter((update) => update.tastes.length > 0);
}

function fallback(message: string): Interpretation {
  return {
    intent: parseIntent(message), provider: "rules", reference: "none", alternative: false,
    memberUpdates: scopedTastes(message), globalAllergies: [], optionNames: [], clarification: null,
    corrections: { clearVegetarian: false, clearSpiceLimit: false, clearBudget: false },
  };
}

export async function understand(message: string): Promise<Interpretation> {
  const basic = fallback(message);
  if (process.env.POC09_CONVERSATION_PROVIDER !== "openrouter" || !process.env.OPENROUTER_API_KEY) return basic;
  const model = process.env.POC09_LLM_MODEL || "openai/gpt-4.1-mini";
  try {
    const response = await fetch("https://openrouter.ai/api/v1/chat/completions", {
      method: "POST",
      signal: AbortSignal.timeout(12000),
      headers: {
        Authorization: `Bearer ${process.env.OPENROUTER_API_KEY}`,
        "Content-Type": "application/json",
        "HTTP-Referer": "https://www.minslab.kr",
        "X-Title": "Mwomeokji PoC9",
      },
      body: JSON.stringify({
        model,
        temperature: 0,
        max_tokens: 900,
        provider: { require_parameters: true, data_collection: "deny", zdr: true },
        response_format: responseFormat,
        messages: [
          { role: "system", content: `You interpret one Korean restaurant-ordering turn for a future voice-first service. Return only the JSON schema. Interpret only the current utterance. A separate server holds session memory and resolves any references to prior recommendations. Null means not mentioned this turn. Never invent a menu, person, price, ingredient, allergy, or safety claim. Copy any menu or option phrase only from the current utterance. You have no catalog; the server matches real names and asks if uncertain. For speech-keyboard typos, preserve the likely spoken phrase without inventing a menu. For a group member mentioned by name or 'one person', put that member's dietary/allergy/spice facts in memberUpdates, not global fields. When family roles establish a party, infer their distinct count: self + spouse + one child is three; an age such as 2살 is not a headcount. For an explicit overall party count, peopleCount is the stated total. For each named person, put desired tastes in memberUpdates.tastes: spicy, mild, sweet, soup, kids. Use the exact role word spoken as label, such as 나, 아이, 와이프. A child’s mild preference must not limit everyone. If a user describes who wants what and says 주문해줘, classify as recommend: first select catalog items, then obtain an explicit confirmation before ordering. checkout is only for finalizing an already chosen cart. If user says more people joined without stating a total, return null and let the server ask. For per-person budget with unknown party size, return null and let the server ask. reference denotes a numbered or pronoun-based prior recommendation, which the server resolves. When the user corrects an earlier fact, use corrections or removeDietaryRules only for explicit negations. Never remove an allergy on your own. clarification is for genuine ambiguity, not routine recommendations. Do not assume a menu exists; the server checks catalog names. You only interpret; the server checks facts and takes actions.` },
          { role: "user", content: message.slice(0, 500) },
        ],
      }),
    });
    const raw = await response.json().catch(() => ({})) || {};
    const content = raw.choices?.[0]?.message?.content;
    let parsed: ReturnType<typeof llmSchema.safeParse> | null = null;
    try { if (typeof content === "string") parsed = llmSchema.safeParse(JSON.parse(content)); } catch { /* local fallback */ }
    const usage = raw.usage || {};
    await recordAiUsage({
      model: typeof raw.model === "string" ? raw.model : model,
      status: response.ok && parsed?.success ? "COMPLETED" : "FAILED",
      httpStatus: response.status,
      inputTokens: Number.isFinite(usage.prompt_tokens) ? usage.prompt_tokens : 0,
      outputTokens: Number.isFinite(usage.completion_tokens) ? usage.completion_tokens : 0,
      costUsd: Number.isFinite(usage.cost) ? usage.cost : undefined,
    });
    if (!response.ok || !parsed?.success) return basic;
    const turn = parsed.data;
    const intent: OrderIntent = { ...basic.intent, action: turn.action };
    if (turn.peopleCount !== null) intent.peopleCount = turn.peopleCount;
    if (turn.totalBudget !== null) intent.totalBudget = turn.totalBudget;
    if (turn.maxSpiceLevel !== null) intent.maxSpiceLevel = Math.min(turn.maxSpiceLevel, basic.intent.maxSpiceLevel ?? 4);
    if (turn.vegetarian !== null) intent.vegetarian = turn.vegetarian;
    if (turn.wantsWarm !== null) intent.wantsWarm = turn.wantsWarm;
    if (turn.wantsCool !== null) intent.wantsCool = turn.wantsCool;
    if (turn.avoidPork !== null) intent.avoidPork = turn.avoidPork;
    if (turn.avoidBeef !== null) intent.avoidBeef = turn.avoidBeef;
    if (turn.category !== null) intent.category = turn.category;
    if (turn.menuName !== null) intent.menuName = turn.menuName;
    if (turn.quantity !== null && /(\d+|한|두|세|네|하나|둘|셋|넷)\s*(개|잔|그릇|인분)/.test(message)) intent.quantity = turn.quantity;
    // Direct command words override any model guess that would mutate an order.
    if (basic.intent.action === "checkout" || basic.intent.action === "remove" || basic.intent.action === "add" || basic.intent.action === "help") intent.action = basic.intent.action;
    if (intent.action === "checkout" && basic.intent.action !== "checkout") intent.action = "recommend";
    if (intent.action === "help" && !/직원|사장님|도움|불러/.test(message)) intent.action = "recommend";
    if (intent.action === "add" && basic.intent.action !== "add" && !/담|넣|추가|이걸|그걸|이거|그거|할게/.test(message)) intent.action = "recommend";
    if (intent.action === "remove" && !/빼|제거|삭제|취소/.test(message)) intent.action = "recommend";
    return {
      intent, provider: "openrouter", reference: turn.reference, alternative: turn.alternative,
      memberUpdates: [...turn.memberUpdates, ...basic.memberUpdates], globalAllergies: turn.globalAllergies,
      optionNames: turn.optionNames,
      clarification: turn.clarification,
      corrections: turn.corrections,
    };
  } catch {
    await recordAiUsage({ model, status: "FAILED", httpStatus: 0 });
    return basic;
  }
}
