/** One synthetic candidate-ranking check; only IDs and menu metadata reach the provider. */
import { performance } from "node:perf_hooks";
import { rankRecommendations } from "../lib/decision";
import type { MenuItemData, Recommendation } from "../lib/types";

const candidate = (id: string, tags: string[], spiceLevel: number, popularity: number, score: number): Recommendation => ({
  item: { id, storeId: "synthetic", categoryId: "synthetic", name: id, description: "", price: 10000,
    emoji: "🍽️", imageUrl: null, spiceLevel, isAvailable: true, isPublished: true,
    isShareable: false, popularity, tags, ingredients: [], dietaryTags: [], allergens: [], options: [] } satisfies MenuItemData,
  score, reason: "synthetic rule score",
});
const candidates = [
  candidate("safe-warm-rice", ["warm", "rice"], 1, 75, 90),
  candidate("safe-soup", ["warm", "soup"], 0, 65, 80),
  candidate("safe-cool-salad", ["cool", "salad"], 0, 70, 70),
];
const context = { action: "recommend" as const, peopleCount: 1, wantsWarm: true };
process.env.POC09_DECISION_PROVIDER = "rules";
const rules = await rankRecommendations(candidates, context);
const allowLive = process.argv.includes("--live");
if (allowLive && !process.env.OPENROUTER_API_KEY) throw new Error("OPENROUTER_API_KEY is needed for --live");
process.env.POC09_DECISION_PROVIDER = allowLive ? "jev-openrouter" : "rules";
const start = performance.now();
const compared = await rankRecommendations(candidates, context);
const elapsedMs = Math.round(performance.now() - start);
const original = candidates.map((entry) => entry.item.id).sort();
const output = compared.recommendations.map((entry) => entry.item.id).sort();
if (JSON.stringify(original) !== JSON.stringify(output)) throw new Error("Ranking changed the candidate set");
console.log(JSON.stringify({ syntheticOnly: true, model: allowLive ? process.env.POC09_JEV_MODEL || "typesafe/jev-1.13" : "rules",
  rulesOrder: rules.recommendations.map((entry) => entry.item.id),
  comparedOrder: compared.recommendations.map((entry) => entry.item.id),
  decisionProvider: compared.provider, elapsedMs, usage: compared.usage || null,
  guardedCandidateSet: true }, null, 2));
