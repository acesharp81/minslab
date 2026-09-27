/** Synthetic menu-choice probe. No real customer text or saved guest context is used. */
import { performance } from "node:perf_hooks";
import { selectMenuProposal, type MenuProposal } from "../lib/menu-selector";
import type { MenuItemData } from "../lib/types";

function candidate(id: string, name: string, description: string, tags: string[], popularity: number): MenuProposal {
  const item: MenuItemData = { id, storeId: "synthetic", categoryId: "synthetic", name, description, price: 4500,
    emoji: "🥤", imageUrl: null, spiceLevel: 0, isAvailable: true, isPublished: true,
    isShareable: false, popularity, tags, ingredients: [], dietaryTags: [], allergens: [], options: [] };
  return { id: `option_${id}`, recommendations: [{ item, score: popularity, reason: "" }], total: item.price * 2 };
}
const proposals = [
  candidate("orange", "오렌지 에이드", "상큼한 오렌지 음료", ["음료", "sour", "caffeine_free"], 85),
  candidate("apple", "달콤 사과 주스", "사과로 만든 달콤한 음료", ["음료", "sweet", "caffeine_free"], 68),
  candidate("water", "생수", "깨끗한 물", ["음료", "caffeine_free"], 42),
];
const live = process.argv.includes("--live");
if (live && !process.env.OPENROUTER_API_KEY) throw new Error("OPENROUTER_API_KEY is needed for --live");
process.env.POC09_CONVERSATION_PROVIDER = live ? "openrouter" : "mock";
const cases = [
  { utterance: "사과 맛 나는 음료가 당겨요", expected: "option_apple" },
  { utterance: "카페인 없는 음료 두 잔을 만 원 안에서 골라줘", expected: "option_orange" },
  { utterance: "블루베리 스무디를 마시고 싶어요", expected: null },
];
for (const testCase of cases) {
  const start = performance.now();
  const selected = await selectMenuProposal(testCase.utterance, proposals);
  const elapsedMs = Math.round(performance.now() - start);
  if (selected.proposal && !proposals.includes(selected.proposal)) throw new Error("Selector returned a fabricated proposal");
  if (live && (selected.proposal?.id ?? null) !== testCase.expected) throw new Error(`LLM missed synthetic request: expected ${testCase.expected}, got ${selected.proposal?.id ?? null}`);
  console.log(JSON.stringify({ syntheticOnly: true, mode: live ? "openrouter" : "rules", selected: selected.proposal?.id ?? null,
    provider: selected.provider, elapsedMs, usage: selected.usage || null, bounded: true }, null, 2));
}
