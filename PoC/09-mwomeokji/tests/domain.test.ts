import { afterEach, describe, expect, it, vi } from "vitest";
import { checkSafety, priceFor } from "../lib/safety";
import { parseIntent } from "../lib/intent";
import { applyFocusedTaste, applyMemberUpdates, evolveDialogue, readDialogue, resetForFullMealBrief, type DialogueState } from "../lib/dialogue";
import { understand } from "../lib/ai";
import { recordAiUsage } from "../lib/usage-meter";
import { recommend, recommendGroup } from "../lib/recommend";
import { applyBoundedRanking } from "../lib/decision";
import { ALLERGENS, emptyProfile, type MenuItemData } from "../lib/types";

const item = (
  name: string,
  price: number,
  includes: string[] = [],
  spiceLevel = 0,
): MenuItemData => ({
  id: name,
  storeId: "demo",
  categoryId: "meal",
  name,
  description: "",
  price,
  emoji: "🍽️",
  imageUrl: null,
  spiceLevel,
  isAvailable: true,
  isPublished: true,
  isShareable: false,
  popularity: 50,
  tags: ["warm"],
  ingredients: [],
  dietaryTags: [
    "vegetarian",
    "vegan",
    "no_pork",
    "no_beef",
    "no_seafood",
    "no_dairy",
  ],
  allergens: ALLERGENS.map(([allergenKey]) => ({
    allergenKey,
    relation: includes.includes(allergenKey) ? "contains" : "excludes",
    verificationStatus: "merchant_verified",
  })),
  options: [],
});

describe("allergen and option safety", () => {
  const allergy = { ...emptyProfile, allergies: ["peanut"] };
  it("rejects included, unknown and AI inferred allergens", () => {
    expect(
      checkSafety(item("contains", 5000, ["peanut"]), allergy).allowed,
    ).toBe(false);
    const unknown = item("unknown", 5000);
    unknown.allergens[0].verificationStatus = "unknown";
    expect(checkSafety(unknown, allergy).allowed).toBe(false);
    unknown.allergens[0].verificationStatus = "ai_inferred";
    expect(checkSafety(unknown, allergy).allowed).toBe(false);
  });
  it("requires a valid and verified option for allergy sensitive orders", () => {
    const meal = item("with option", 5000);
    meal.options = [
      {
        id: "group",
        name: "토핑",
        minSelect: 1,
        maxSelect: 1,
        options: [
          {
            id: "unsafe",
            name: "땅콩",
            priceDelta: 1000,
            isAvailable: true,
            ingredients: ["peanut"],
            dietaryTags: [],
            allergens: [
              {
                allergenKey: "peanut",
                relation: "contains",
                verificationStatus: "merchant_verified",
              },
            ],
          },
          {
            id: "safe",
            name: "채소",
            priceDelta: 500,
            isAvailable: true,
            ingredients: [],
            dietaryTags: [],
            allergens: [
              {
                allergenKey: "peanut",
                relation: "excludes",
                verificationStatus: "merchant_verified",
              },
            ],
          },
        ],
      },
    ];
    expect(checkSafety(meal, allergy, []).allowed).toBe(false);
    expect(checkSafety(meal, allergy, ["unsafe"]).allowed).toBe(false);
    expect(checkSafety(meal, allergy, ["safe"]).allowed).toBe(true);
    expect(priceFor(meal, ["safe"])).toBe(5500);
  });
  it("does not silently relax strict diet, stock or spice limits", () => {
    const meal = item("meal", 5000, [], 3);
    meal.dietaryTags = [];
    expect(
      checkSafety(meal, {
        ...emptyProfile,
        dietaryRules: [{ type: "vegan", mode: "strict" }],
      }).allowed,
    ).toBe(false);
    expect(
      checkSafety(meal, { ...emptyProfile, maxSpiceLevel: 1 }).allowed,
    ).toBe(false);
    meal.isAvailable = false;
    expect(checkSafety(meal, emptyProfile).allowed).toBe(false);
  });
});

describe("conversation and recommendations", () => {
  it("extracts people, budget and mild preference from Korean text", () => {
    const result = parseIntent(
      "3명인데 안 맵고 따뜻한 거 4만원 안에서 추천해줘",
    );
    expect(result.peopleCount).toBe(3);
    expect(result.totalBudget).toBe(40000);
    expect(result.maxSpiceLevel).toBe(1);
    expect(result.wantsWarm).toBe(true);
  });
  it("understands menu quantities without leaving the count in the name", () => {
    const result = parseIntent("햇살 치킨 덮밥 2개 담아줘");
    expect(result.action).toBe("add");
    expect(result.quantity).toBe(2);
    expect(result.menuName).toBe("햇살 치킨 덮밥");
  });
  it("only recommends verified menu items within budget", () => {
    const safe = item("safe", 9000);
    const costly = item("costly", 12000);
    const unsafe = item("unsafe", 7000, ["peanut"]);
    const results = recommend(
      [safe, costly, unsafe],
      { ...emptyProfile, allergies: ["peanut"] },
      { action: "recommend", totalBudget: 10000 },
    );
    expect(results.map((entry) => entry.item.name)).toEqual(["safe"]);
  });
  it("uses the saved budget when the message omits a number", () => {
    const results = recommend(
      [item("cheap", 4500), item("expensive", 9000)],
      { ...emptyProfile, budget: 5000 },
      { action: "recommend" },
    );
    expect(results.map((entry) => entry.item.name)).toEqual(["cheap"]);
  });
  it("respects individual group allergies and total budget", () => {
    const safe = item("safe", 6000);
    const peanut = item("peanut", 7000, ["peanut"]);
    const result = recommendGroup(
      [safe, peanut],
      emptyProfile,
      { action: "recommend", totalBudget: 13000 },
      [
        { id: "a", label: "A", allergies: ["peanut"], dietaryRules: [] },
        { id: "b", label: "B", allergies: [], dietaryRules: [] },
      ],
    );
    expect(result.complete).toBe(true);
    expect(result.total).toBeLessThanOrEqual(13000);
    expect(result.items[0].item.name).toBe("safe");
  });
});

describe("multi-turn Tap Talk Together dialogue", () => {
  it("infers three people and different member constraints without a member form", () => {
    const text = "우리 3명인데 한 명은 채식하고 한 명은 매운 걸 못 먹어";
    const next = evolveDialogue(readDialogue({}), text, parseIntent(text));
    expect(next.state.peopleCount).toBe(3);
    expect(next.state.members).toHaveLength(3);
    expect(next.state.members[0].dietaryRules).toContainEqual({ type: "vegetarian", mode: "strict" });
    expect(next.state.members[1].maxSpiceLevel).toBe(0);
    expect(next.state.preferences.vegetarian).toBe(false);
  });
  it("remembers group conditions and adds a later total budget", () => {
    const first = "한 명은 땅콩 알레르기 있어";
    const a = evolveDialogue(readDialogue({}), first, parseIntent(first));
    expect(a.needsPeopleCount).toBe(true);
    const second = "우리 2명이야, 2만원 안에서 추천해줘";
    const b = evolveDialogue(a.state, second, parseIntent(second));
    expect(b.state.peopleCount).toBe(2);
    expect(b.state.members[0].allergies).toContain("peanut");
    expect(b.state.preferences.totalBudget).toBe(20000);
  });
  it("updates party size across turns when another diner joins or leaves", () => {
    const initial = evolveDialogue(readDialogue({}), "우리 세 명이야", parseIntent("우리 세 명이야")).state;
    const joined = evolveDialogue(initial, "한 명 더 왔어", parseIntent("한 명 더 왔어")).state;
    expect(joined.peopleCount).toBe(4);
    expect(joined.members).toHaveLength(4);
    const left = evolveDialogue(joined, "두 명 빠졌어", parseIntent("두 명 빠졌어")).state;
    expect(left.peopleCount).toBe(2);
    expect(left.members).toHaveLength(2);
  });
  it("treats a family meal selection request as recommendations for each diner", async () => {
    vi.stubEnv("POC09_CONVERSATION_PROVIDER", "rules");
    const message = "2살 딸이랑 와이프랑 나랑 밥 먹을게. 나는 매운걸로, 아이는 키즈 메뉴 중 달달하고 맵지 않은 걸로, 와이프는 국물 있는 걸로 주문해줘";
    const interpretation = await understand(message);
    expect(interpretation.intent.action).toBe("recommend");
    const evolved = evolveDialogue(readDialogue({}), message, interpretation.intent);
    const state = applyMemberUpdates(evolved.state, interpretation.memberUpdates, message).state;
    expect(state.peopleCount).toBe(3);
    expect(state.members.find((member) => member.label === "아이")?.tastes).toEqual(expect.arrayContaining(["kids", "sweet", "mild"]));
    expect(state.members.find((member) => member.label === "아이")?.maxSpiceLevel).toBe(0);
    expect(state.preferences.maxSpiceLevel).toBeUndefined();

    const spicy = { ...item("매콤 제육 덮밥", 11900, [], 2), popularity: 74 };
    const kids = { ...item("달콤 키즈 치킨 덮밥", 8900), tags: ["warm", "식사", "kids", "sweet"], popularity: 72 };
    const soup = { ...item("따끈 닭고기 수프", 7900), popularity: 59 };
    const group = recommendGroup([spicy, kids, soup], emptyProfile, state.preferences, state.members);
    expect(group.complete).toBe(true);
    expect(group.items.map((entry) => [entry.forMember, entry.item.name])).toEqual(expect.arrayContaining([
      ["나", "매콤 제육 덮밥"], ["아이", "달콤 키즈 치킨 덮밥"], ["와이프", "따끈 닭고기 수프"],
    ]));
  });
  it("replaces stale meal preferences on a returning guest's complete family brief", async () => {
    vi.stubEnv("POC09_CONVERSATION_PROVIDER", "rules");
    const stale: DialogueState = {
      ...readDialogue({}), peopleCount: 3,
      preferences: { action: "recommend", peopleCount: 3, vegetarian: true, totalBudget: 10000 },
      members: [
        { id: "old-child", label: "아이", allergies: ["peanut"], dietaryRules: [], tastes: ["spicy"], maxSpiceLevel: 2 },
        { id: "generic-2", label: "일행 2", allergies: [], dietaryRules: [{ type: "vegetarian", mode: "strict" }] },
        { id: "generic-3", label: "일행 3", allergies: [], dietaryRules: [], maxSpiceLevel: 0 },
      ],
      lastRecommendations: [{ id: "old-menu" }],
    };
    const message = "2살 딸이랑 와이프랑 나랑 밥 먹을게. 나는 매운걸로, 아이는 달달하고 맵지 않은 키즈 메뉴로, 와이프는 국물 있는 걸로 주문해줘";
    const interpretation = await understand(message);
    const reset = resetForFullMealBrief(stale, message);
    expect(reset.preferences.vegetarian).toBeUndefined();
    expect(reset.preferences.totalBudget).toBeUndefined();
    expect(reset.members).toHaveLength(1);
    expect(reset.members[0].allergies).toEqual(["peanut"]);
    expect(reset.members[0].tastes).toEqual([]);
    expect(reset.members[0].maxSpiceLevel).toBeUndefined();
    const state = applyMemberUpdates(evolveDialogue(reset, message, interpretation.intent).state, interpretation.memberUpdates, message).state;
    expect(state.members.map((member) => member.label)).toEqual(["아이", "나", "와이프"]);
    const spicy = item("매콤 제육 덮밥", 11900, [], 2);
    const kids = { ...item("달콤 키즈 치킨 덮밥", 8900), tags: ["warm", "식사", "kids", "sweet"] };
    const soup = item("따끈 닭고기 수프", 7900);
    const group = recommendGroup([spicy, kids, soup], emptyProfile, state.preferences, state.members);
    expect(group.complete).toBe(true);
    expect(group.items.find((entry) => entry.forMember === "아이")?.item.name).toBe("달콤 키즈 치킨 덮밥");
  });
  it("accepts a complete newly named party after a stale session", () => {
    const stale: DialogueState = { ...readDialogue({}), peopleCount: 3, preferences: { action: "recommend", vegetarian: true, peopleCount: 3 }, members: [
      { id: "generic-1", label: "일행 1", allergies: [], dietaryRules: [{ type: "vegetarian", mode: "strict" }] },
      { id: "generic-2", label: "일행 2", allergies: [], dietaryRules: [] },
      { id: "generic-3", label: "일행 3", allergies: [], dietaryRules: [] },
    ] };
    const updates = ["민수", "지수", "유나"].map((label) => ({ label, count: 1, allergies: [], dietaryRules: [], maxSpiceLevel: null, removeDietaryRules: [], clearSpiceLimit: false, tastes: [] }));
    const brief = "가상 테스트 일행은 민수, 지수, 유나 3명이야. 민수는 매운 식사, 지수는 달콤한 식사, 유나는 국물 메뉴를 골라줘";
    const reset = resetForFullMealBrief(stale, brief, updates);
    expect(reset.peopleCount).toBeUndefined();
    expect(reset.members).toEqual([]);
    expect(reset.preferences.vegetarian).toBeUndefined();
    expect(resetForFullMealBrief(stale, "유나꺼는 더 얼큰한 국물로 골라줘", updates)).toBe(stale);
  });
  it("refines the wife's soup across two short spoken turns without asking for party size", async () => {
    vi.stubEnv("POC09_CONVERSATION_PROVIDER", "rules");
    const first = "2살 딸이랑 와이프랑 나랑 밥 먹을게. 나는 매운걸로, 아이는 키즈 메뉴 중 달달하고 맵지 않은 걸로, 와이프는 국물 있는 걸로 주문해줘";
    const initial = await understand(first);
    let state = applyMemberUpdates(evolveDialogue(readDialogue({}), first, initial.intent).state, initial.memberUpdates, first).state;
    const second = "와이프꺼는 더 얼큰한걸로 보여줘";
    const refinement = await understand(second);
    expect(refinement.intent.action).toBe("recommend");
    const evolved = evolveDialogue(state, second, refinement.intent);
    expect(evolved.onlyHeadcount).toBe(false);
    state = applyMemberUpdates(evolved.state, refinement.memberUpdates, second).state;
    expect(state.peopleCount).toBe(3);
    expect(state.focusedMemberLabel).toBe("와이프");
    expect(state.members.find((member) => member.label === "와이프")?.tastes).toEqual(expect.arrayContaining(["soup", "spicy"]));

    const third = "알러지는 없고 얼큰한걸로";
    const followup = await understand(third);
    const next = evolveDialogue(state, third, followup.intent);
    expect(next.onlyHeadcount).toBe(false);
    const focused = applyFocusedTaste(applyMemberUpdates(next.state, followup.memberUpdates, third).state, third);
    expect(focused.applied).toBe(true);
    const spicy = { ...item("매콤 제육 덮밥", 11900, [], 2), popularity: 74 };
    const kids = { ...item("달콤 키즈 치킨 덮밥", 8900), tags: ["warm", "식사", "kids", "sweet"], popularity: 72 };
    const mildSoup = { ...item("따끈 닭고기 수프", 7900), popularity: 59 };
    const spicySoup = { ...item("얼큰 해물 수프", 10900, [], 3), popularity: 53 };
    const group = recommendGroup([spicy, kids, mildSoup, spicySoup], emptyProfile, focused.state.preferences, focused.state.members);
    expect(group.complete).toBe(true);
    expect(group.items.find((entry) => entry.forMember === "와이프")?.item.name).toBe("얼큰 해물 수프");
  });
  it("does not silently replace a requested kids menu with an adult menu", () => {
    const result = recommendGroup([item("일반 덮밥", 10000)], emptyProfile, { action: "recommend", peopleCount: 2 }, [
      { id: "child", label: "아이", allergies: [], dietaryRules: [], maxSpiceLevel: 0, tastes: ["kids", "mild"] },
      { id: "adult", label: "나", allergies: [], dietaryRules: [] },
    ]);
    expect(result.complete).toBe(false);
  });
  it("recognizes conversational checkout intent", () => {
    expect(parseIntent("주문할게").action).toBe("checkout");
    expect(parseIntent("주문해줘").action).toBe("checkout");
    expect(parseIntent("추천한 거 전부 주문해줘").action).toBe("add");
  });
});

describe("bounded experimental ranking", () => {
  it("rejects unknown IDs and low confidence, and only reorders known safe items", () => {
    const candidates = recommend(
      [item("a", 5000), item("b", 6000)],
      emptyProfile,
      { action: "recommend" },
    );
    expect(
      applyBoundedRanking(candidates, {
        confidence: 0.9,
        orderedIds: ["b", "invented"],
      }),
    ).toBe(candidates);
    expect(
      applyBoundedRanking(candidates, {
        confidence: 0.2,
        orderedIds: ["b", "a"],
      }),
    ).toBe(candidates);
    expect(
      applyBoundedRanking(candidates, {
        confidence: 0.9,
        orderedIds: ["b", "a"],
      }).map((entry) => entry.item.id),
    ).toEqual(["b", "a"]);
  });
});

afterEach(() => { vi.unstubAllEnvs(); vi.unstubAllGlobals(); });

describe("shared AI meter", () => {
  it("reports only call metadata without customer text or session data", async () => {
    vi.stubEnv("POC09_METER_TOKEN", "unit-meter-token");
    let outbound: Record<string, unknown> = {};
    vi.stubGlobal("fetch", vi.fn(async (_url: string, options: RequestInit) => {
      outbound = JSON.parse(String(options.body));
      return { ok: true };
    }));
    await recordAiUsage({ model: "openai/gpt-4.1-mini", status: "COMPLETED", httpStatus: 200, inputTokens: 120, outputTokens: 60 });
    expect(outbound.project).toBe("poc09");
    expect(outbound.input_tokens).toBe(120);
    expect(Object.keys(outbound).sort()).toEqual([
      "cost_usd", "event_id", "http_status", "input_tokens", "model", "output_tokens", "project", "provider", "status", "workload",
    ]);
  });
});

describe("LLM current-turn interpretation", () => {
  it("sends only the current utterance and validates the model response", async () => {
    vi.stubEnv("POC09_CONVERSATION_PROVIDER", "openrouter");
    vi.stubEnv("OPENROUTER_API_KEY", "unit-test-key");
    let outbound: Record<string, unknown> = {};
    vi.stubGlobal("fetch", vi.fn(async (_url: string, options: RequestInit) => {
      outbound = JSON.parse(String(options.body));
      return { ok: true, json: async () => ({ choices: [{ message: { content: JSON.stringify({
        action: "add", peopleCount: null, totalBudget: null, maxSpiceLevel: null,
        vegetarian: null, wantsWarm: null, wantsCool: null, avoidPork: null, avoidBeef: null,
        category: null, menuName: null, quantity: 2, reference: "second", alternative: false,
        globalAllergies: [], memberUpdates: [], optionNames: ["많이"], clarification: null,
        corrections: { clearVegetarian: false, clearSpiceLimit: false, clearBudget: false },
      }) } }] }) };
    }));
    const message = "두 번째 많이 해서 담아줘";
    const result = await understand(message);
    expect(result.provider).toBe("openrouter");
    expect(result.reference).toBe("second");
    expect(result.intent.quantity).toBeUndefined(); // ordinal is not item quantity
    expect((outbound.messages as { role: string; content: string }[]).map((entry) => entry.content).at(-1)).toBe(message);
    expect((outbound.provider as { zdr: boolean; data_collection: string }).zdr).toBe(true);
    expect((outbound.provider as { zdr: boolean; data_collection: string }).data_collection).toBe("deny");
    expect(JSON.stringify(outbound)).not.toContain("previousUtterances");
    expect((outbound.messages as { role: string; content: string }[]).filter((entry) => entry.role === "user")).toEqual([{ role: "user", content: message }]);
  });
  it("keeps a spoken request to add all prior recommendations out of checkout", async () => {
    vi.stubEnv("POC09_CONVERSATION_PROVIDER", "openrouter");
    vi.stubEnv("OPENROUTER_API_KEY", "unit-test-key");
    vi.stubGlobal("fetch", vi.fn(async () => ({ ok: true, json: async () => ({ choices: [{ message: { content: JSON.stringify({
      action: "checkout", peopleCount: null, totalBudget: null, maxSpiceLevel: null,
      vegetarian: null, wantsWarm: null, wantsCool: null, avoidPork: null, avoidBeef: null,
      category: null, menuName: null, quantity: null, reference: "all", alternative: false,
      globalAllergies: [], memberUpdates: [], optionNames: [], clarification: null,
      corrections: { clearVegetarian: false, clearSpiceLimit: false, clearBudget: false },
    }) } }] }) })));
    expect((await understand("추천한 거 전부 주문해줘")).intent.action).toBe("add");
  });
  it("falls back to local rules on invalid LLM output", async () => {
    vi.stubEnv("POC09_CONVERSATION_PROVIDER", "openrouter");
    vi.stubEnv("OPENROUTER_API_KEY", "unit-test-key");
    vi.stubGlobal("fetch", vi.fn(async () => ({ ok: true, json: async () => ({ choices: [{ message: { content: "{}" } }] }) })));
    const result = await understand("두 개 담아줘");
    expect(result.provider).toBe("rules");
    expect(result.intent.action).toBe("add");
  });
  it("does not mistake the last syllable of a name for the speaker", () => {
    const state: DialogueState = { ...readDialogue({}), peopleCount: 2, members: [
      { id: "a", label: "유나", allergies: [], dietaryRules: [], tastes: ["soup"] },
      { id: "b", label: "나", allergies: [], dietaryRules: [], tastes: ["spicy"] },
    ] };
    const update = (label: string) => ({ label, count: 1, allergies: [], dietaryRules: [], maxSpiceLevel: null, removeDietaryRules: [], clearSpiceLimit: false, tastes: ["spicy" as const] });
    const result = applyMemberUpdates(state, [update("나"), update("유나꺼")], "유나꺼는 더 얼큰한 국물로 보여줘");
    expect(result.state.focusedMemberLabel).toBe("유나");
    expect(result.state.members).toHaveLength(2);
    expect(result.state.members[0].tastes).toEqual(["soup", "spicy"]);
  });
  it("resolves an unambiguous follow-up person locally and asks when several match", () => {
    const single: DialogueState = { ...readDialogue({}), peopleCount: 2, members: [
      { id: "named-1", label: "민수", allergies: [], dietaryRules: [] },
      { id: "generic-2", label: "일행 2", allergies: [], dietaryRules: [] },
    ] };
    const update = { label: "그 친구", count: 1, allergies: ["milk"], dietaryRules: [], maxSpiceLevel: null, removeDietaryRules: [], clearSpiceLimit: false };
    const resolved = applyMemberUpdates(single, [update], "그 친구는 우유 알레르기 있어");
    expect(resolved.state.members[0].allergies).toContain("milk");
    expect(resolved.needsClarification).toBe(false);
    const many: DialogueState = { ...single, members: [...single.members, { id: "named-3", label: "영희", allergies: [], dietaryRules: [] }] };
    expect(applyMemberUpdates(many, [update], "그 친구는 우유 알레르기 있어").needsClarification).toBe(true);
  });
  it("merges named members from successive turns without imposing their diets on everyone", () => {
    const first = "민수는 채식이야. 우리 세 명이야";
    let state: DialogueState = evolveDialogue(readDialogue({}), first, { ...parseIntent(first), peopleCount: 3 }).state;
    state = applyMemberUpdates(state, [{ label: "민수", count: 1, allergies: [], dietaryRules: ["vegetarian"], maxSpiceLevel: null, removeDietaryRules: [], clearSpiceLimit: false }], first).state;
    const second = "영희는 매운 걸 못 먹어";
    state = evolveDialogue(state, second, parseIntent(second)).state;
    state = applyMemberUpdates(state, [{ label: "영희", count: 1, allergies: [], dietaryRules: [], maxSpiceLevel: 0, removeDietaryRules: [], clearSpiceLimit: false }], second).state;
    expect(state.members).toHaveLength(3);
    expect(state.members.find((member) => member.label === "민수")?.dietaryRules[0].type).toBe("vegetarian");
    expect(state.members.find((member) => member.label === "영희")?.maxSpiceLevel).toBe(0);
    expect(state.preferences.vegetarian).toBe(false);
    expect(state.preferences.maxSpiceLevel).toBeUndefined();
  });
});
