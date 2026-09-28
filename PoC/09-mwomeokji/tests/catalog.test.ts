import { describe, expect, it } from "vitest";
import { scenarioRecipes } from "../prisma/scenario-recipes";
import { ALLERGENS } from "../lib/types";

const seafood = new Set(["shrimp", "crab", "clam", "fish", "salmon", "tuna"]);
const animal = new Set(["chicken", "beef", "pork", ...seafood]);

describe("expanded fictional menu", () => {
  it("adds 56 distinct dishes across every course and spice level", () => {
    expect(scenarioRecipes).toHaveLength(56);
    expect(new Set(scenarioRecipes.map((recipe) => recipe[1])).size).toBe(56);
    expect(Object.fromEntries(["식사", "국물", "사이드", "디저트", "음료"].map((category) =>
      [category, scenarioRecipes.filter((recipe) => recipe[0] === category).length]))).toEqual({
      식사: 25, 국물: 6, 사이드: 8, 디저트: 8, 음료: 9,
    });
    expect(new Set(scenarioRecipes.map((recipe) => recipe[5]))).toEqual(new Set([0, 1, 2, 3, 4]));
    expect(new Set(scenarioRecipes.flatMap((recipe) => recipe[9]))).toEqual(new Set(ALLERGENS.map(([key]) => key)));
  });

  it("keeps allergy, diet, caffeine, and course claims consistent with virtual ingredients", () => {
    for (const [category, name, , price, , spice, tags, ingredients, diets, contains] of scenarioRecipes) {
      expect(price, name).toBeGreaterThan(0);
      expect(tags, name).toContain(category === "국물" ? "식사" : category);
      expect(tags.length, name).toBeLessThanOrEqual(15);
      expect(contains.length, name).toBeGreaterThanOrEqual(0);
      if (diets.includes("vegetarian")) expect(ingredients.some((part) => animal.has(part)), name).toBe(false);
      if (diets.includes("vegan")) expect(ingredients.some((part) => animal.has(part) || ["egg", "milk", "honey"].includes(part)), name).toBe(false);
      if (diets.includes("no_dairy")) expect(ingredients, name).not.toContain("milk");
      if (diets.includes("no_pork")) expect(ingredients, name).not.toContain("pork");
      if (diets.includes("no_beef")) expect(ingredients, name).not.toContain("beef");
      if (diets.includes("no_seafood")) expect(ingredients.some((part) => seafood.has(part)), name).toBe(false);
      if (tags.includes("kids")) expect(spice, name).toBe(0);
      if (tags.includes("매콤")) expect(spice, name).toBeGreaterThanOrEqual(2);
      if (tags.includes("caffeine_free")) expect(ingredients.some((part) => ["coffee", "cocoa"].includes(part)), name).toBe(false);
      if (tags.includes("decaf")) {
        expect(tags, name).toContain("coffee");
        expect(tags, name).not.toContain("caffeine_free");
      }
    }
  });
});
