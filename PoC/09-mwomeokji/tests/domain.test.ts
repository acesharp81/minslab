import { describe, expect, it } from "vitest";
import { checkSafety, priceFor } from "../lib/safety";
import { parseIntent } from "../lib/intent";
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
