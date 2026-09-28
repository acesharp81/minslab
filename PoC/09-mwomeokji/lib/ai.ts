import { z } from "zod";
import { parseIntent } from "./intent";
import type { MemberUpdate } from "./dialogue";
import { recordAiUsage } from "./usage-meter";
import { requestFreeStructured } from "./free-llm";
import type { conversationSnapshot } from "./conversation-context";
import { ALLERGENS, DIET_RULES, type OrderIntent } from "./types";

export type Interpretation = {
  intent: OrderIntent;
  provider: "openrouter" | "groq" | "rules";
  targetSeat?: string | null;
  globalMenuLabels?: string[];
  offerResolution?: "accept" | "decline" | "none";
  modelUnavailable?: boolean;
  modelStatus?: number;
  modelErrorCode?: string;
  retryAfterSeconds?: number;
  reference: "none" | "first" | "second" | "third" | "all" | "last" | "previous_order";
  alternative: boolean;
  memberUpdates: MemberUpdate[];
  globalAllergies: string[];
  optionNames: string[];
  clarification: string | null;
  corrections: { clearVegetarian: boolean; clearSpiceLimit: boolean; clearBudget: boolean };
  usage?: { inputTokens: number; outputTokens: number; costUsd?: number };
};

const tasteValues = ["spicy", "mild", "sweet", "soup", "rice", "kids"] as const;
const compactTurnSchema = z.object({
  action: z.enum(["recommend", "ask"]),
  targetSeat: z.string().regex(/^seat_(?:[1-9]|1[0-2])$/).nullable(),
  peopleCount: z.number().int().min(1).max(12).nullable(),
  totalBudget: z.number().int().min(0).max(1000000).nullable(),
  category: z.enum(["식사", "음료", "사이드", "디저트"]).nullable(),
  globalTastes: z.array(z.enum(tasteValues)).max(6),
  globalLabels: z.array(z.string().max(30)).max(4),
  memberUpdates: z.array(z.object({ label: z.string().trim().min(1).max(40), count: z.number().int().min(1).max(12), tastes: z.array(z.enum(tasteValues)).max(6), labels: z.array(z.string().max(30)).max(4) }).strict()).max(12),
  offerResolution: z.enum(["accept", "decline", "none"]),
  reference: z.enum(["none", "first", "second", "third", "all", "last"]),
  alternative: z.boolean(),
  clarification: z.string().max(120).nullable(),
}).strict();
const compactTurnProperties = {
  action: { type: "string", enum: ["recommend", "ask"] },
  targetSeat: { type: ["string", "null"] },
  peopleCount: { type: ["integer", "null"] },
  totalBudget: { type: ["integer", "null"] },
  category: { type: ["string", "null"], enum: ["식사", "음료", "사이드", "디저트", null] },
  globalTastes: { type: "array", items: { type: "string", enum: tasteValues } },
  globalLabels: { type: "array", items: { type: "string" } },
  memberUpdates: { type: "array", items: { type: "object", properties: {
    label: { type: "string" }, count: { type: "integer" }, tastes: { type: "array", items: { type: "string", enum: tasteValues } }, labels: { type: "array", items: { type: "string" } },
  }, required: ["label", "count", "tastes", "labels"], additionalProperties: false } },
  offerResolution: { type: "string", enum: ["accept", "decline", "none"] },
  reference: { type: "string", enum: ["none", "first", "second", "third", "all", "last"] },
  alternative: { type: "boolean" },
  clarification: { type: ["string", "null"] },
};
const compactResponseSchema = { type: "object", properties: compactTurnProperties,
  required: Object.keys(compactTurnProperties), additionalProperties: false };

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
  category: z.enum(["식사", "음료", "사이드", "디저트"]).nullable(),
  menuName: z.string().max(80).nullable(),
  quantity: z.number().int().min(1).max(30).nullable(),
  reference: z.enum(["none", "first", "second", "third", "all", "last", "previous_order"]),
  targetSeat: z.string().regex(/^seat_(?:[1-9]|1[0-2])$/).nullable().optional(),
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
    tastes: z.array(z.enum(["spicy", "mild", "sweet", "soup", "rice", "kids"])).max(5),
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
  tastes: { type: "array", items: { type: "string", enum: ["spicy", "mild", "sweet", "soup", "rice", "kids"] } },
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
  category: { type: ["string", "null"], enum: ["식사", "음료", "사이드", "디저트", null] },
  menuName: stringOrNull,
  quantity: numberOrNull,
  reference: { type: "string", enum: ["none", "first", "second", "third", "all", "last", "previous_order"] },
  targetSeat: { type: ["string", "null"] },
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
  const nonPeople = new Set(["메뉴", "음식", "재료", "알레르기", "알러지", "예산", "가격", "오늘", "식사", "주문", "추천", "덮밥", "국물", "수프", "소스", "맛"]);
  const clauses = [...message.matchAll(/(?:^|[\s,，.;:])([가-힣]{1,8})(?:꺼|것|메뉴)?(?:는|은|에게는|한테는)\s*/g)]
    .filter((match) => (match[1].length >= 2 || ["나", "저", "딸"].includes(match[1])) && !nonPeople.has(match[1]));
  return clauses.map((match, index) => {
    const following = message.slice(match.index! + match[0].length, clauses[index + 1]?.index ?? message.length);
    const nextSpeaker = following.search(/[,，.;]\s*[가-힣A-Za-z]{1,20}(?:는|은)\s*/);
    const segment = (nextSpeaker >= 0 ? following.slice(0, nextSpeaker) : following).split(/[.!?。]/, 1)[0];
    const tastes: NonNullable<MemberUpdate["tastes"]> = [];
    if (/매운|맵게|얼큰/.test(segment) && !/안\s*맵|맵지|매운.*(?:안|못)/.test(segment)) tastes.push("spicy");
    if (/안\s*맵|맵지|순한|매운.*(?:안|못)/.test(segment)) tastes.push("mild");
    if (/달달|달콤|단맛/.test(segment)) tastes.push("sweet");
    if (/국물|수프|탕|찌개/.test(segment)) tastes.push("soup");
    if (/덮밥|볶음밥|밥류/.test(segment)) tastes.push("rice");
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
    corrections: { clearVegetarian: false, clearSpiceLimit: false, clearBudget: /(?:예산|가격|금액).*(?:제한|상관)?.*(?:없어|없어요|없음|괜찮아)/.test(message) },
  };
}

export async function understand(message: string, context?: {
  snapshot: ReturnType<typeof conversationSnapshot>;
  outboundMessage: string;
  spokenLabels?: string[];
  seatLabels?: string[];
  skipModel?: boolean;
}): Promise<Interpretation> {
  const basic = fallback(message);
  if (process.env.POC09_CONVERSATION_PROVIDER === "groq") {
    // Explicit cart commands need no model call and never let a model place an order.
    if (context?.skipModel || ["add", "remove", "checkout", "help"].includes(basic.intent.action)) return basic;
    const result = await requestFreeStructured(compactResponseSchema,
      "Interpret the current Korean restaurant utterance as a STATE CHANGE using the compact previous state. Return the required JSON fields. Null means no change. A pendingOffer in state is the assistant's immediately preceding question: set offerResolution=accept for agreement such as 그래 그러게 해줘 or 그렇게 해달라고, decline for refusal, none otherwise. Do not repeat the rejected constraint when accepting a replacement. For a new party, represent EACH distinct diner group in memberUpdates with label, count, tastes, and labels. Example: 4식구, 아이 둘은 키즈, 나와 와이프는 든든, 와이프는 안 맵게 => peopleCount=4; 아이 count=2 tastes=[kids]; 나 count=1 labels=[든든]; 와이프 count=1 tastes=[mild] labels=[든든]. labels must come only from mentionedCatalogLabels in the user input. Use globalLabels only for a whole-table request, never for a taste/label assigned to some diners. A change to one diner preserves other diners. targetSeat must be an existing seat ID and grounded in the utterance or focus. Map tastes to spicy, mild, sweet, soup, rice, kids. 해장 indicates soup preference, never a health claim. Do not invent menus, diners, prices, ingredients, allergies or safety facts. The server validates all proposed state changes and menu facts.",
      { currentTurn: (context?.outboundMessage || message).slice(0, 500), mentionedCatalogLabels: context?.spokenLabels || [], state: context?.snapshot || null },
      (value) => { const parsed = compactTurnSchema.safeParse(value); return parsed.success ? parsed.data : null; },
      "order_interpretation", 900);
    if (!result.value) return { ...basic, modelUnavailable: true, modelStatus: result.httpStatus, modelErrorCode: result.errorCode, retryAfterSeconds: result.retryAfterSeconds };
    const turn = result.value;
    const intent: OrderIntent = { ...basic.intent, action: basic.intent.action === "ask" ? "ask" : turn.action };
    const explicitParty = /명|사람|일행|(?:우리|저희)\s*(?:둘|셋|넷)(?:이|이서)|와이프|아내|남편|아이|아기|딸|아들/.test(message);
    if (turn.peopleCount !== null && (!basic.intent.quantity || explicitParty)) intent.peopleCount = turn.peopleCount;
    if (turn.totalBudget !== null && /예산|이하|안에서|원/.test(message)) intent.totalBudget = turn.totalBudget;
    if (turn.category !== null && !basic.intent.category) intent.category = turn.category;
    const memberUpdates = turn.memberUpdates.map((entry): MemberUpdate => {
      const anonymousSeat = entry.label.match(/^(?:일행\s*|seat_)(\d{1,2})$/);
      const localLabel = anonymousSeat ? context?.seatLabels?.[Number(anonymousSeat[1]) - 1] : undefined;
      return {
      label: localLabel || entry.label, count: entry.count, allergies: [], dietaryRules: [],
      maxSpiceLevel: entry.tastes.includes("mild") ? 0 : null,
      removeDietaryRules: [], clearSpiceLimit: false, tastes: entry.tastes,
      menuLabels: entry.labels.filter((label) => context?.spokenLabels?.includes(label)),
      };
    });
    for (const extracted of basic.memberUpdates) {
      const existing = memberUpdates.find((entry) => entry.label === extracted.label);
      if (existing) {
        existing.tastes = [...new Set([...(existing.tastes || []), ...(extracted.tastes || [])])];
        if (existing.tastes.includes("mild")) existing.maxSpiceLevel = 0;
      } else memberUpdates.push(extracted);
    }
    const individual = memberUpdates.length > 0 || !!turn.targetSeat;
    if (!individual) {
      if (turn.globalTastes.includes("spicy") && /매운|매콤|얼큰|맵게/.test(message)) intent.minSpiceLevel = 2;
      if (turn.globalTastes.includes("mild") && /순한|맵지|안\s*매운|맵찔/.test(message)) intent.maxSpiceLevel = 0;
      if (turn.globalTastes.includes("sweet") && /달달|달콤|단맛|sweet/.test(message)) intent.wantsSweet = true;
      if (turn.globalTastes.includes("soup") && /해장|속\s*풀|국물|탕|찌개|수프/.test(message)) intent.category = "국물";
      if (turn.globalTastes.includes("kids") && /아이|애기|아기|키즈|어린이/.test(message)) intent.kidsOnly = true;
    }
    if (basic.memberUpdates.some((entry) => entry.tastes?.length)) intent.action = "recommend";
    return {
      intent, provider: "groq", targetSeat: turn.targetSeat, offerResolution: turn.offerResolution, globalMenuLabels: turn.globalLabels.filter((label) => context?.spokenLabels?.includes(label)), reference: turn.reference,
      alternative: turn.alternative, memberUpdates,
      globalAllergies: [], optionNames: [], clarification: turn.clarification,
      corrections: basic.corrections,
      usage: { inputTokens: result.inputTokens, outputTokens: result.outputTokens },
    };
  }
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
          { role: "system", content: `You interpret one Korean restaurant-ordering turn for a future voice-first service. Return only the JSON schema. Interpret only the current utterance. A separate server holds session memory and resolves any references to prior recommendations. Null means not mentioned this turn. Never invent a menu, person, price, ingredient, allergy, or safety claim. Copy any menu or option phrase only from the current utterance. You have no catalog; the server matches real names and asks if uncertain. Category is one of 식사, 음료, 사이드, 디저트 or null. Set 식사 for a clearly requested filling meal or main dish even when the word 식사 is absent; set null for a generic menu request with no clear course. This category controls which actual catalog items can be proposed. For speech-keyboard typos, preserve the likely spoken phrase without inventing a menu. For a group member mentioned by name or 'one person', put that member's dietary/allergy/spice facts in memberUpdates, not global fields. When family roles establish a party, infer their distinct count: self + spouse + one child is three; an age such as 2살 is not a headcount. For an explicit overall party count, peopleCount is the stated total. For each named person, put desired tastes in memberUpdates.tastes: spicy, mild, sweet, soup, rice, kids. When the user switches a diner's dish type (for example soup to a rice bowl), extract the new type; the server replaces the old type. Use the exact diner role as label, such as 나, 아이, 와이프. A possessive referring to one diner still identifies that diner. 얼큰한 국물 means soup and spicy. A request to make one diner's soup spicier is a recommendation refinement, not a request for party size or checkout. A child’s mild preference must not limit everyone. If a user describes who wants what and says 주문해줘, classify as recommend: first select catalog items, then obtain an explicit confirmation before ordering. checkout is only for finalizing an already chosen cart. If user says more people joined without stating a total, return null and let the server ask. For per-person budget with unknown party size, return null and let the server ask. reference denotes a numbered or pronoun-based prior recommendation, which the server resolves. Set reference to previous_order only when the user explicitly asks for a menu they previously ordered; the server checks this anonymous session's order history. Do not invent a past order. When the user corrects an earlier fact, use corrections or removeDietaryRules only for explicit negations. Never remove an allergy on your own. clarification is for genuine ambiguity, not routine recommendations. Do not assume a menu exists; the server checks catalog names. You only interpret; the server checks facts and takes actions.` },
          { role: "user", content: message.slice(0, 500) },
        ],
      }),
    });
    const raw = await response.json().catch(() => ({})) || {};
    const content = raw.choices?.[0]?.message?.content;
    let parsed: ReturnType<typeof llmSchema.safeParse> | null = null;
    try { if (typeof content === "string") parsed = llmSchema.safeParse(JSON.parse(content)); } catch { /* local fallback */ }
    const usage = raw.usage || {};
    const measuredUsage = {
      inputTokens: Number.isFinite(usage.prompt_tokens) ? usage.prompt_tokens : 0,
      outputTokens: Number.isFinite(usage.completion_tokens) ? usage.completion_tokens : 0,
      costUsd: Number.isFinite(usage.cost) ? usage.cost : undefined,
    };
    await recordAiUsage({
      model: typeof raw.model === "string" ? raw.model : model,
      status: response.ok && parsed?.success ? "COMPLETED" : "FAILED",
      httpStatus: response.status,
      ...measuredUsage,
    });
    if (!response.ok || !parsed?.success) return { ...basic, usage: measuredUsage };
    const turn = parsed.data;
    const intent: OrderIntent = { ...basic.intent, action: turn.action };
    // A drink count is a quantity, not a party size. The model cannot turn 2잔 into 2명.
    const explicitParty = /명|사람|일행|(?:우리|저희)\s*(?:둘|셋|넷)(?:이|이서)|와이프|아내|남편|아이|아기|딸|아들/.test(message);
    if (turn.peopleCount !== null && (!basic.intent.quantity || explicitParty)) intent.peopleCount = turn.peopleCount;
    if (turn.totalBudget !== null) intent.totalBudget = turn.totalBudget;
    if (turn.maxSpiceLevel !== null) intent.maxSpiceLevel = Math.min(turn.maxSpiceLevel, basic.intent.maxSpiceLevel ?? 4);
    if (turn.vegetarian !== null) intent.vegetarian = turn.vegetarian;
    if (basic.intent.vegetarian) intent.vegetarian = true;
    if (turn.wantsWarm !== null) intent.wantsWarm = turn.wantsWarm;
    if (turn.wantsCool !== null) intent.wantsCool = turn.wantsCool;
    if (turn.avoidPork !== null) intent.avoidPork = turn.avoidPork;
    if (turn.avoidBeef !== null) intent.avoidBeef = turn.avoidBeef;
    if (turn.category !== null && !basic.intent.category) intent.category = turn.category;
    if (turn.menuName !== null) intent.menuName = turn.menuName;
    if (turn.quantity !== null && /(\d+|한|두|세|네|하나|둘|셋|넷)\s*(개|잔|그릇|인분)/.test(message)) intent.quantity = turn.quantity;
    // Direct command words override any model guess that would mutate an order.
    if (basic.intent.action === "checkout" || basic.intent.action === "remove" || basic.intent.action === "add" || basic.intent.action === "help") intent.action = basic.intent.action;
    if (intent.action === "checkout" && basic.intent.action !== "checkout") intent.action = "recommend";
    if (basic.intent.action === "recommend" && basic.memberUpdates.some((entry) => entry.tastes?.length)) intent.action = "recommend";
    if (basic.intent.coffee && /추천|골라/.test(message)) intent.action = "recommend";
    if (basic.intent.action === "recommend" && /추천|골라/.test(message) && !/담아|추가|넣어/.test(message)) intent.action = "recommend";
    if (intent.action === "help" && !/직원|사장님|도움|불러/.test(message)) intent.action = "recommend";
    if (intent.action === "add" && basic.intent.action !== "add" && !/담|넣|추가|이걸|그걸|이거|그거|할게/.test(message)) intent.action = "recommend";
    if (intent.action === "remove" && !/빼|제거|삭제|취소/.test(message)) intent.action = "recommend";
    return {
      intent, provider: "openrouter", reference: turn.reference, alternative: turn.alternative,
      memberUpdates: turn.memberUpdates, globalAllergies: turn.globalAllergies,
      optionNames: turn.optionNames,
      clarification: turn.clarification,
      corrections: turn.corrections,
      usage: measuredUsage,
    };
  } catch {
    await recordAiUsage({ model, status: "FAILED", httpStatus: 0 });
    return basic;
  }
}
