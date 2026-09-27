import { afterEach, describe, expect, it, vi } from "vitest";
import { checkSafety, priceFor } from "../lib/safety";
import { hasExplicitNoAllergies, parseIntent } from "../lib/intent";
import { answerIngredientQuestion, ingredientQuestion } from "../lib/ingredient-answer";
import { applyFocusedTaste, applyMemberUpdates, canStageRecommendations, evolveDialogue, readDialogue, resetForFullMealBrief, type DialogueState } from "../lib/dialogue";
import { understand } from "../lib/ai";
import { recordAiUsage } from "../lib/usage-meter";
import { validCaffeineTags } from "../lib/menu-metadata";
import { recommend, recommendDiverseGroupOptions, recommendGroup, validateRecommendationResult } from "../lib/recommend";
import { applyBoundedRanking, rankRecommendations } from "../lib/decision";
import { selectMenuProposal } from "../lib/menu-selector";
import { ALLERGENS, emptyProfile, newEmptyProfile, type MenuItemData } from "../lib/types";

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

describe("LLM menu choice over real proposals", () => {
  const orange = { item: { ...item("오렌지 에이드", 4500), tags: ["음료", "sour"] }, score: 80, reason: "" };
  const apple = { item: { ...item("달콤 사과 주스", 4500), tags: ["음료", "sweet"] }, score: 70, reason: "" };
  const proposals = [
    { id: "option_1", recommendations: [orange], total: 4500 },
    { id: "option_2", recommendations: [apple], total: 4500 },
  ];
  it("selects a known menu ID using only current utterance and public menu facts", async () => {
    vi.stubEnv("POC09_CONVERSATION_PROVIDER", "openrouter");
    vi.stubEnv("OPENROUTER_API_KEY", "unit-test-key");
    let outbound: Record<string, unknown> = {};
    vi.stubGlobal("fetch", vi.fn(async (_url: string, options: RequestInit) => {
      outbound = JSON.parse(String(options.body));
      return { ok: true, status: 200, json: async () => ({ choices: [{ message: { content: '{"choiceId":"option_2","confidence":0.9}' } }] }) };
    }));
    const result = await selectMenuProposal("사과 맛으로 골라줘", proposals);
    expect(result.provider).toBe("openrouter");
    expect(result.proposal?.recommendations[0].item.name).toBe("달콤 사과 주스");
    const body = JSON.stringify(outbound);
    expect(body).toContain("사과 맛으로 골라줘");
    expect(body).not.toContain("allergies");
    expect(body).not.toContain("forMember");
    expect(body).not.toContain("session");
  });
  it("can abstain from an explicit menu request that no proposal matches", async () => {
    vi.stubEnv("POC09_CONVERSATION_PROVIDER", "openrouter");
    vi.stubEnv("OPENROUTER_API_KEY", "unit-test-key");
    vi.stubGlobal("fetch", vi.fn(async () => ({ ok: true, status: 200, json: async () => ({ choices: [{ message: { content: '{"choiceId":"no_match","confidence":0.95}' } }] }) })));
    const result = await selectMenuProposal("블루베리 스무디를 마시고 싶어요", proposals);
    expect(result.provider).toBe("openrouter");
    expect(result.proposal).toBeNull();
  });
  it("falls back to a verified proposal for an uncertain abstention", async () => {
    vi.stubEnv("POC09_CONVERSATION_PROVIDER", "openrouter");
    vi.stubEnv("OPENROUTER_API_KEY", "unit-test-key");
    vi.stubGlobal("fetch", vi.fn(async () => ({ ok: true, status: 200, json: async () => ({ choices: [{ message: { content: '{"choiceId":"no_match","confidence":0.6}' } }] }) })));
    const result = await selectMenuProposal("음료를 추천해줘", proposals);
    expect(result.provider).toBe("rules");
    expect(result.proposal).toBe(proposals[0]);
  });
  it("uses the rules proposal for a malformed model choice", async () => {
    vi.stubEnv("POC09_CONVERSATION_PROVIDER", "openrouter");
    vi.stubEnv("OPENROUTER_API_KEY", "unit-test-key");
    vi.stubGlobal("fetch", vi.fn(async () => ({ ok: true, status: 200, json: async () => ({ choices: [{ message: { content: '{"choiceId":"invented","confidence":0.9}' } }] }) })));
    const result = await selectMenuProposal("사과 맛으로 골라줘", proposals);
    expect(result.provider).toBe("rules");
    expect(result.proposal).toBe(proposals[0]);
  });
});

describe("diverse group proposal coverage", () => {
  it("offers a complete meal option even when drinks and sides have higher popularity", () => {
    const drink = { ...item("주스", 4500), tags: ["음료"], popularity: 95 };
    const side = { ...item("감자튀김", 4500), tags: ["사이드"], popularity: 90 };
    const meal = { ...item("든든한 덮밥", 11900), tags: ["식사"], popularity: 30 };
    const members = Array.from({ length: 4 }, (_, index) => ({
      id: String(index), label: "일행 " + (index + 1), allergies: [], dietaryRules: [],
    }));
    const options = recommendDiverseGroupOptions([drink, side, meal], emptyProfile, { action: "recommend", peopleCount: 4 }, members);
    expect(options.some((option) => option.items.length === 4 && option.items.every((entry) => entry.item.tags.includes("식사")))).toBe(true);
  });
});

describe("merchant beverage labels", () => {
  it("allows a confirmed caffeine-free non-coffee drink, but requires decaf to be coffee", () => {
    expect(validCaffeineTags(["음료", "caffeine_free"], "음료")).toBe(true);
    expect(validCaffeineTags(["음료", "decaf"], "음료")).toBe(false);
    expect(validCaffeineTags(["음료", "coffee", "decaf"], "음료")).toBe(true);
    expect(validCaffeineTags(["음료", "coffee", "decaf", "caffeine_free"], "음료")).toBe(false);
  });
});

describe("caffeine-free coffee order contract", () => {
  const request = "카페인 없는 커피 음료 2잔으로 추천해줘 만원이하로";
  const soda = { ...item("오렌지 에이드", 4500), tags: ["음료"], ingredients: ["orange"] };
  const fries = { ...item("바삭 감자튀김", 4500), tags: ["사이드"], ingredients: ["potato"] };
  const regular = { ...item("아이스 아메리카노", 3900), tags: ["음료"], ingredients: ["coffee"] };
  const decaf = { ...item("디카페인 아메리카노", 4500), tags: ["음료", "coffee", "decaf"], ingredients: ["coffee"] };
  const verified = { ...item("카페인 없는 대체 커피", 4500), tags: ["음료", "coffee", "caffeine_free"], ingredients: ["chicory"] };
  it("treats two cups as units, not two diners, and never substitutes soda or fries", async () => {
    vi.stubEnv("POC09_CONVERSATION_PROVIDER", "rules");
    const understood = await understand(request);
    const state = evolveDialogue(readDialogue({}), request, understood.intent).state;
    expect(state.peopleCount).toBeUndefined();
    expect(state.preferences.quantity).toBe(2);
    expect(state.preferences.totalBudget).toBe(10000);
    expect(state.preferences.coffee).toBe(true);
    expect(state.preferences.caffeineFree).toBe(true);
    expect(recommend([soda, fries, regular, decaf], emptyProfile, state.preferences)).toEqual([]);
    const valid = recommend([soda, fries, regular, decaf, verified], emptyProfile, state.preferences);
    expect(valid.map((entry) => entry.item.name)).toEqual([verified.name]);
    expect(validateRecommendationResult(valid, emptyProfile, state.preferences)).toEqual({ valid: true, total: 9000 });
  });
  it("broadens coffee to verified caffeine-free drinks on the next turn", () => {
    const coffee = evolveDialogue(readDialogue({}), request, parseIntent(request)).state;
    const broaderRequest = "카페인 없는 음료 2잔으로 추천해줘 만원이하로";
    const broader = evolveDialogue(coffee, broaderRequest, parseIntent(broaderRequest)).state;
    expect(broader.preferences.coffee).toBe(false);
    expect(broader.preferences.caffeineFree).toBe(true);
    expect(broader.preferences.quantity).toBe(2);
    expect(broader.preferences.totalBudget).toBe(10000);
    const caffeineFreeSoda = { ...soda, tags: ["음료", "caffeine_free"] };
    const proposals = recommend([caffeineFreeSoda, fries, regular, decaf], emptyProfile, broader.preferences, 1);
    expect(proposals.map((entry) => entry.item.name)).toEqual(["오렌지 에이드"]);
    expect(validateRecommendationResult(proposals, emptyProfile, broader.preferences)).toEqual({ valid: true, total: 9000 });
  });
  it("keeps caffeine, quantity and budget while replacing sour soda with a sweet drink", () => {
    const first = evolveDialogue(readDialogue({}), "카페인 없는 음료 2잔으로 추천해줘 만원이하로", parseIntent("카페인 없는 음료 2잔으로 추천해줘 만원이하로")).state;
    const followup = "신거 말고 달달한거로";
    expect(parseIntent("새콤한 건 빼고 달콤한 음료로 골라줘").action).toBe("recommend");
    const next = evolveDialogue(first, followup, parseIntent(followup)).state;
    expect(next.preferences.caffeineFree).toBe(true);
    expect(next.preferences.quantity).toBe(2);
    expect(next.preferences.totalBudget).toBe(10000);
    expect(next.preferences.wantsSweet).toBe(true);
    expect(next.preferences.avoidSour).toBe(true);
    const orange = { ...soda, tags: ["음료", "caffeine_free", "sour"], description: "상큼한 음료" };
    const water = { ...item("생수", 1500), tags: ["음료", "caffeine_free"] };
    const apple = { ...item("달콤 사과 주스", 4500), tags: ["음료", "caffeine_free", "sweet"], description: "달콤한 음료" };
    const proposals = recommend([orange, water, apple], emptyProfile, next.preferences, 1);
    expect(proposals.map((entry) => entry.item.name)).toEqual(["달콤 사과 주스"]);
    expect(validateRecommendationResult(proposals, emptyProfile, next.preferences)).toEqual({ valid: true, total: 9000 });
    expect(validateRecommendationResult([{ item: water, score: 99, reason: "" }], emptyProfile, next.preferences).valid).toBe(false);
    expect(proposals[0].reason).toContain("달콤한 맛");
    expect(proposals[0].reason).not.toContain("원라서");
  });
  it("starts a standalone drink brief after a group meal and relaxes only an explicit decaf correction", () => {
    const previous = { ...readDialogue({}), peopleCount: 3,
      members: Array.from({ length: 3 }, (_, index) => ({ id: String(index), label: `일행 ${index + 1}`, allergies: [], dietaryRules: [] })),
      preferences: { action: "recommend" as const, peopleCount: 3, category: "식사" } };
    const reset = resetForFullMealBrief(previous, request);
    const drink = evolveDialogue(reset, request, parseIntent(request)).state;
    expect(drink.peopleCount).toBeUndefined();
    expect(drink.preferences.quantity).toBe(2);
    const decafRequest = "그럼 디카페인 커피로 추천해줘";
    const corrected = evolveDialogue(drink, decafRequest, parseIntent(decafRequest)).state;
    expect(corrected.preferences.caffeineFree).toBe(false);
    expect(corrected.preferences.decaf).toBe(true);
    expect(corrected.preferences.quantity).toBe(2);
  });
  it("rejects a model-ranked result that violates the menu kind, caffeine claim or total budget", () => {
    const intent = parseIntent(request);
    expect(validateRecommendationResult([{ item: soda, score: 99, reason: "" }], emptyProfile, intent).valid).toBe(false);
    expect(validateRecommendationResult([{ item: decaf, score: 99, reason: "" }], emptyProfile, intent).valid).toBe(false);
    expect(validateRecommendationResult([{ item: { ...verified, price: 5100 }, score: 99, reason: "" }], emptyProfile, intent).valid).toBe(false);
  });
  it("ignores a model's invented headcount when the utterance only says two cups", async () => {
    vi.stubEnv("POC09_CONVERSATION_PROVIDER", "openrouter");
    vi.stubEnv("OPENROUTER_API_KEY", "unit-test-key");
    vi.stubGlobal("fetch", vi.fn(async () => ({ ok: true, status: 200, json: async () => ({ choices: [{ message: { content: JSON.stringify({
      action: "recommend", peopleCount: 2, totalBudget: 10000, maxSpiceLevel: null,
      vegetarian: null, wantsWarm: null, wantsCool: null, avoidPork: null, avoidBeef: null,
      category: "음료", menuName: null, quantity: 2, reference: "none", alternative: false,
      globalAllergies: [], memberUpdates: [], optionNames: [], clarification: null,
      corrections: { clearVegetarian: false, clearSpiceLimit: false, clearBudget: false },
    }) } }] }) })));
    const result = await understand(request);
    expect(result.provider).toBe("openrouter");
    expect(result.intent.peopleCount).toBeUndefined();
    expect(result.intent.quantity).toBe(2);
  });
});

describe("spoken order confirmation", () => {
  it("stages one menu per diner, but never every alternative for one diner", () => {
    const base = readDialogue({});
    expect(canStageRecommendations({ ...base, peopleCount: 2, lastRecommendations: [{ id: "a", forMember: "나" }, { id: "b", forMember: "동료" }] })).toBe(true);
    expect(canStageRecommendations({ ...base, peopleCount: 1, lastRecommendations: [{ id: "a" }, { id: "b" }] })).toBe(false);
    expect(canStageRecommendations({ ...base, peopleCount: 2, lastRecommendations: [{ id: "a", forMember: "나" }, { id: "b", forMember: "나" }] })).toBe(false);
  });
});

describe("spoken preference scope", () => {
  it("keeps named adult preferences separate when the model is unavailable", async () => {
    vi.stubEnv("POC09_CONVERSATION_PROVIDER", "rules");
    const message = "가상 성인 3명: 민수는 매운 덮밥, 지수는 달콤한 메뉴, 유나는 순한 국물로 추천해줘";
    const understood = await understand(message);
    const changed = applyMemberUpdates(evolveDialogue(readDialogue({}), message, understood.intent).state, understood.memberUpdates, message).state;
    expect(changed.peopleCount).toBe(3);
    expect(changed.members.find((entry) => entry.label === "민수")?.tastes).toEqual(["spicy", "rice"]);
    expect(changed.members.find((entry) => entry.label === "지수")?.tastes).toEqual(["sweet"]);
    expect(changed.members.find((entry) => entry.label === "유나")?.tastes).toEqual(["mild", "soup"]);
  });
  it("does not attach a coworker's tastes to the preceding self clause", async () => {
    vi.stubEnv("POC09_CONVERSATION_PROVIDER", "rules");
    const result = await understand("우리 둘이 먹을게. 나는 매운 덮밥, 동료는 순한 국물로 추천해줘");
    expect(result.memberUpdates.find((entry) => entry.label === "나")?.tastes).toEqual(["spicy", "rice"]);
    vi.unstubAllEnvs();
  });
});

describe("conversational ingredient checks", () => {
  const ownDish = { ...item("매콤 제육 덮밥", 11900), ingredients: ["pork", "rice", "soy"] };
  const otherDish = { ...item("얼큰 닭고기 덮밥", 11900), ingredients: ["chicken", "rice"] };
  const state: DialogueState = {
    ...readDialogue({}), peopleCount: 2,
    members: [
      { id: "self", label: "나", allergies: [], dietaryRules: [] },
      { id: "other", label: "동료", allergies: [], dietaryRules: [] },
    ],
    lastRecommendations: [
      { id: ownDish.id, forMember: "나" },
      { id: otherDish.id, forMember: "동료" },
    ],
  };
  it("answers a self-reference from the last recommendations without asserting unverified absence", () => {
    const question = ingredientQuestion("내꺼에 오이가 들어갔는지 확인해봐");
    expect(question).not.toBeNull();
    const reply = answerIngredientQuestion("내꺼에 오이가 들어갔는지 확인해봐", question!, state, [ownDish, otherDish], []);
    expect(reply).toContain("매콤 제육 덮밥");
    expect(reply).toContain("오이 표기를 찾지 못했어요");
    expect(reply).toContain("사장님께 확인");
    expect(reply).not.toContain("얼큰 닭고기 덮밥");
  });
  it("uses selected cart options before the earlier recommendation", () => {
    const withOption = { ...ownDish, options: [{ id: "g", name: "토핑", minSelect: 0, maxSelect: 1, options: [{ id: "o", name: "오이 추가", priceDelta: 0, isAvailable: true, ingredients: ["cucumber"], dietaryTags: [], allergens: [] }] }] };
    const reply = answerIngredientQuestion("내꺼에 오이 들어 있어?", ingredientQuestion("내꺼에 오이 들어 있어?")!, state, [withOption, otherDish], [{ menuItemId: withOption.id, assignedTo: "나", selectedOptionIds: ["o"] }]);
    expect(reply).toContain("오이 표기를 확인했어요");
    expect(reply).toContain("선택한 옵션");
  });
  it("asks which dish when the owner cannot be resolved", () => {
    const unknown = { ...state, members: [{ id: "other", label: "동료", allergies: [], dietaryRules: [] }] };
    const reply = answerIngredientQuestion("내꺼에 오이 들어가?", ingredientQuestion("내꺼에 오이 들어가?")!, unknown, [ownDish, otherDish], []);
    expect(reply).toContain("어느 분의 메뉴");
  });
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

describe("guest profile isolation", () => {
  it("never shares a mutable allergy list between new guests", () => {
    const firstGuest = newEmptyProfile();
    firstGuest.allergies.push("peanut");
    const secondGuest = newEmptyProfile();
    expect(secondGuest.allergies).toEqual([]);
    expect(firstGuest).not.toBe(secondGuest);
  });
});

describe("ingredient question boundary", () => {
  it("keeps an allergy declaration with a recommendation request in the recommendation flow", () => {
    expect(ingredientQuestion("땅콩 알레르기가 있어. 따뜻한 식사 추천해줘")).toBeNull();
    expect(ingredientQuestion("내가 추천받은 메뉴에 땅콩이 들어갔는지 확인해줘")?.label).toBe("땅콩");
  });
});

describe("multi-turn Tap Talk Together dialogue", () => {
  it("asks for a food preference after a party only states restrictions", () => {
    const message = "가상 손님 2명인데 한 명은 채식하고 한 명은 매운 걸 못 먹어";
    const result = evolveDialogue(readDialogue({}), message, parseIntent(message));
    expect(result.state.peopleCount).toBe(2);
    expect(result.onlyHeadcount).toBe(true);
  });
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
  it("clears a stale budget when a returning guest gives a complete four-person meal brief", async () => {
    vi.stubEnv("POC09_CONVERSATION_PROVIDER", "rules");
    const stale: DialogueState = {
      ...readDialogue({}), peopleCount: 4,
      preferences: { action: "recommend", peopleCount: 4, totalBudget: 10000, category: "음료", quantity: 2 },
      members: Array.from({ length: 4 }, (_, index) => ({
        id: `generic-${index + 1}`, label: `일행 ${index + 1}`, allergies: [], dietaryRules: [],
      })),
      lastRecommendations: [{ id: "old-drink" }],
    };
    const message = "남자 4명인데 양이 많아서 든든히 먹을 수 있는 메뉴로 추천해줘";
    const interpreted = await understand(message);
    const reset = resetForFullMealBrief(stale, message, interpreted.memberUpdates);
    expect(reset.preferences.totalBudget).toBeUndefined();
    expect(reset.preferences.category).toBeUndefined();
    expect(reset.preferences.quantity).toBeUndefined();
    expect(reset.lastRecommendations).toEqual([]);
    const next = evolveDialogue(reset, message, interpreted.intent).state;
    expect(next.peopleCount).toBe(4);
    expect(next.preferences.totalBudget).toBeUndefined();
    const hearty = { ...item("든든한 덮밥", 11900), tags: ["식사", "warm", "rice"] };
    expect(recommendGroup([hearty], emptyProfile, next.preferences, next.members).complete).toBe(true);
  });
  it("keeps a budget on a short refinement but accepts a new explicit budget", () => {
    const stale: DialogueState = { ...readDialogue({}), peopleCount: 4,
      preferences: { action: "recommend", peopleCount: 4, totalBudget: 10000 } };
    expect(resetForFullMealBrief(stale, "그럼 따뜻한 메뉴로 다시 추천해줘")).toBe(stale);
    const message = "우리 4명인데 따뜻한 메뉴로 5만원 안에서 추천해줘";
    const reset = resetForFullMealBrief(stale, message);
    const next = evolveDialogue(reset, message, parseIntent(message)).state;
    expect(next.preferences.totalBudget).toBe(50000);
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
  it("finds a verified non-seafood spicy soup despite a shellfish allergy", () => {
    const spicySeafood = item("얼큰 해물 수프", 10900, ["shellfish", "fish"], 3);
    const spicyChicken = item("얼큰 닭고기 수프", 9900, [], 2);
    const result = recommendGroup([spicySeafood, spicyChicken], { ...emptyProfile, allergies: ["shellfish"] }, { action: "recommend", peopleCount: 2 }, [
      { id: "a", label: "유나", allergies: [], dietaryRules: [], tastes: ["soup", "spicy"] },
      { id: "b", label: "민수", allergies: [], dietaryRules: [], tastes: ["spicy"] },
    ]);
    expect(result.complete).toBe(true);
    expect(result.items[0].item.name).toBe("얼큰 닭고기 수프");
    expect(result.items.every((entry) => entry.item.name !== "얼큰 해물 수프")).toBe(true);
  });
  it("replaces a named diner's mild limit when they explicitly ask for spicy food", () => {
    const state: DialogueState = { ...readDialogue({}), peopleCount: 2, members: [
      { id: "a", label: "민수", allergies: [], dietaryRules: [], tastes: ["spicy"] },
      { id: "b", label: "유나", allergies: [], dietaryRules: [], maxSpiceLevel: 0, tastes: ["mild", "soup"] },
    ] };
    const update = { label: "유나", count: 1, allergies: [], dietaryRules: [], maxSpiceLevel: null, removeDietaryRules: [], clearSpiceLimit: false, tastes: ["spicy" as const, "soup" as const] };
    const changed = applyMemberUpdates(state, [update], "유나는 더 얼큰한 국물로 추천해줘").state;
    const wife = changed.members.find((member) => member.label === "유나");
    expect(wife?.tastes).toEqual(["soup", "spicy"]);
    expect(wife?.maxSpiceLevel).toBeUndefined();
    const soup = item("얼큰 닭고기 수프", 9900, [], 2);
    const result = recommendGroup([soup], { ...emptyProfile, allergies: ["shellfish"] }, changed.preferences, changed.members);
    expect(result.complete).toBe(true);
    expect(result.items.find((entry) => entry.forMember === "유나")?.item.name).toBe("얼큰 닭고기 수프");
  });
  it("replaces the focused diner's soup type when they ask for a rice bowl instead", () => {
    const state: DialogueState = { ...readDialogue({}), peopleCount: 2, focusedMemberLabel: "와이프", members: [
      { id: "a", label: "나", allergies: [], dietaryRules: [], tastes: ["spicy"] },
      { id: "b", label: "와이프", allergies: [], dietaryRules: [], tastes: ["soup", "spicy"] },
    ] };
    const changed = applyFocusedTaste(state, "아니면 덮밥류로 추천해줘");
    expect(changed.applied).toBe(true);
    expect(changed.state.members[1].tastes).toEqual(["spicy", "rice"]);
    const soup = item("얼큰 닭고기 수프", 9900, [], 2);
    const bowl = item("얼큰 닭고기 덮밥", 11900, [], 2);
    const result = recommendGroup([soup, bowl], emptyProfile, changed.state.preferences, changed.state.members);
    expect(result.items.find((entry) => entry.forMember === "와이프")?.item.name).toBe("얼큰 닭고기 덮밥");
  });
  it("clears only an explicitly denied own allergy profile", () => {
    expect(hasExplicitNoAllergies("알러지는 없고 얼큰한걸로")).toBe(true);
    expect(hasExplicitNoAllergies("저는 알레르기 없어요")).toBe(true);
    expect(hasExplicitNoAllergies("와이프는 알러지 없어")).toBe(false);
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

describe("bounded ranking meter", () => {
  it("records only Jev call metadata and rejects a fabricated menu ID", async () => {
    vi.stubEnv("POC09_DECISION_PROVIDER", "jev-openrouter");
    vi.stubEnv("OPENROUTER_API_KEY", "unit-test-key");
    vi.stubEnv("POC09_METER_TOKEN", "unit-meter-token");
    const reports: Record<string, unknown>[] = [];
    vi.stubGlobal("fetch", vi.fn(async (url: string, options: RequestInit) => {
      if (url.includes("usage-events")) {
        reports.push(JSON.parse(String(options.body)));
        return { ok: true };
      }
      return { ok: true, status: 200, json: async () => ({
        model: "typesafe/jev-1.13", usage: { input_tokens: 80, output_tokens: 20, cost: 0.001 },
        answers: { best: { type: "choice", choice: "invented", confidence: 0.9, probabilities: { invented: 0.9, b: 0.1 } } },
      }) };
    }));
    const candidates = [{ item: item("a", 5000), score: 2, reason: "a" }, { item: item("b", 6000), score: 1, reason: "b" }];
    const result = await rankRecommendations(candidates, { action: "recommend" });
    expect(result.provider).toBe("rules");
    expect(result.recommendations).toBe(candidates);
    expect(result.usage?.inputTokens).toBe(80);
    expect(reports[0].workload).toBe("order_ranking");
    expect(reports[0].cost_usd).toBe(0.001);
    expect(Object.keys(reports[0]).sort()).toEqual(["cost_usd", "event_id", "http_status", "input_tokens", "model", "output_tokens", "project", "provider", "status", "workload"]);
  });

  it("uses the Decisions API and accepts only a complete known-candidate choice", async () => {
    vi.stubEnv("POC09_DECISION_PROVIDER", "jev-openrouter");
    vi.stubEnv("OPENROUTER_API_KEY", "unit-test-key");
    let outbound: Record<string, unknown> = {};
    vi.stubGlobal("fetch", vi.fn(async (url: string, options: RequestInit) => {
      expect(url).toBe("https://openrouter.ai/api/alpha/decisions");
      outbound = JSON.parse(String(options.body));
      return { ok: true, status: 200, json: async () => ({
        model: "typesafe/jev-1.13", usage: { input_tokens: 10, output_tokens: 2 },
        answers: { best: { type: "choice", choice: "b", confidence: 0.95,
          probabilities: { a: 0.15, b: 0.85 } } },
      }) };
    }));
    const candidates = [{ item: item("a", 5000), score: 2, reason: "a" }, { item: item("b", 6000), score: 1, reason: "b" }];
    const result = await rankRecommendations(candidates, { action: "recommend", wantsWarm: true });
    expect(result.provider).toBe("jev-openrouter");
    expect(result.recommendations.map((entry) => entry.item.id)).toEqual(["b", "a"]);
    expect(outbound).toHaveProperty("questions.best.type", "choice");
    expect(outbound).toHaveProperty("state.context.wantsWarm", true);
    expect(JSON.stringify(outbound)).not.toContain("utterance");
  });
});

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
