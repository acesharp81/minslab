/** Synthetic Korean dialogue quality check. No real customer utterance or session is loaded. */
import { performance } from "node:perf_hooks";
import { understand } from "../lib/ai";
import { applyFocusedTaste, applyMemberUpdates, evolveDialogue, readDialogue, resetForFullMealBrief, type DialogueState } from "../lib/dialogue";
import type { Interpretation } from "../lib/ai";

const scenarios: Array<{
  id: string;
  turns: Array<{
    id: string;
    message: string;
    check: (state: DialogueState, parsed: Interpretation) => Record<string, boolean>;
  }>;
}> = [
  { id: "named_adults", turns: [
    { id: "three_tastes", message: "가상 성인 일행 3명이에요. 민수는 매운 덮밥, 지수는 달콤한 메뉴, 유나는 순한 국물로 추천해줘.", check: (state) => ({
      three_people: state.peopleCount === 3,
      minsu_spicy_rice: hasTastes(state, "민수", ["spicy", "rice"]),
      jisu_sweet: hasTastes(state, "지수", ["sweet"]),
      yuna_mild_soup: hasTastes(state, "유나", ["mild", "soup"]),
    }) },
    { id: "spicier_soup", message: "유나는 더 얼큰한 국물로 추천해줘.", check: (state) => ({
      focus_yuna: state.focusedMemberLabel === "유나",
      yuna_spicy_soup: hasTastes(state, "유나", ["spicy", "soup"]) && !hasTastes(state, "유나", ["mild"]),
      others_unchanged: hasTastes(state, "민수", ["spicy", "rice"]) && hasTastes(state, "지수", ["sweet"]),
    }) },
    { id: "rice_instead", message: "그럼 덮밥으로 추천해줘.", check: (state) => ({
      yuna_spicy_rice: hasTastes(state, "유나", ["spicy", "rice"]) && !hasTastes(state, "유나", ["soup"]),
      others_unchanged: hasTastes(state, "민수", ["spicy", "rice"]) && hasTastes(state, "지수", ["sweet"]),
    }) },
  ] },
  { id: "group_restrictions", turns: [
    { id: "separate_limits", message: "가상 손님 2명인데 한 명은 채식하고 한 명은 매운 걸 못 먹어.", check: (state) => ({
      two_people: state.peopleCount === 2,
      vegetarian_member: state.members.some((member) => member.dietaryRules.some((rule) => rule.type === "vegetarian")),
      mild_member: state.members.some((member) => member.maxSpiceLevel === 0),
    }) },
  ] },
  { id: "order_words", turns: [
    { id: "add_all", message: "추천한 거 전부 담아줘", check: (_state, parsed) => ({ add_not_checkout: parsed.intent.action === "add" }) },
    { id: "confirm_order", message: "주문해줘", check: (_state, parsed) => ({ explicit_order: parsed.intent.action === "checkout" }) },
  ] },
];

function hasTastes(state: DialogueState, label: string, tastes: string[]): boolean {
  const member = state.members.find((entry) => entry.label === label);
  return !!member && tastes.every((taste) => member.tastes?.includes(taste as NonNullable<typeof member.tastes>[number]));
}

async function evaluate(mode: "rules" | "openrouter") {
  process.env.POC09_CONVERSATION_PROVIDER = mode === "rules" ? "mock" : "openrouter";
  const details = [];
  const durations: number[] = [];
  let passed = 0, total = 0, fallbackTurns = 0, inputTokens = 0, outputTokens = 0, costUsd = 0;
  for (const scenario of scenarios) {
    let state = readDialogue({});
    for (const turn of scenario.turns) {
      const start = performance.now();
      const parsed = await understand(turn.message);
      const latencyMs = Math.round(performance.now() - start);
      durations.push(latencyMs);
      if (mode === "openrouter" && parsed.provider !== "openrouter") fallbackTurns++;
      inputTokens += parsed.usage?.inputTokens || 0;
      outputTokens += parsed.usage?.outputTokens || 0;
      costUsd += parsed.usage?.costUsd || 0;
      const reset = resetForFullMealBrief(state, turn.message, parsed.memberUpdates);
      const evolved = evolveDialogue(reset, turn.message, parsed.intent);
      const members = applyMemberUpdates(evolved.state, parsed.memberUpdates, turn.message);
      state = applyFocusedTaste(members.state, turn.message).state;
      const checks = turn.check(state, parsed);
      passed += Object.values(checks).filter(Boolean).length;
      total += Object.keys(checks).length;
      details.push({ scenario: scenario.id, turn: turn.id, provider: parsed.provider, latencyMs, checks });
    }
  }
  const sorted = [...durations].sort((a, b) => a - b);
  return {
    mode, model: mode === "rules" ? "local-rules" : process.env.POC09_LLM_MODEL || "openai/gpt-4.1-mini",
    checksPassed: passed, checksTotal: total, turns: durations.length,
    averageMs: Math.round(durations.reduce((a, b) => a + b, 0) / durations.length),
    p95Ms: sorted[Math.ceil(sorted.length * 0.95) - 1], fallbackTurns,
    inputTokens, outputTokens, costUsd: Number(costUsd.toFixed(6)), details,
  };
}

const modes: Array<"rules" | "openrouter"> = process.argv.includes("--both") ? ["rules", "openrouter"] : ["rules"];
if (modes.includes("openrouter") && !process.env.OPENROUTER_API_KEY) throw new Error("OPENROUTER_API_KEY is needed for --both");
const report = [];
for (const mode of modes) report.push(await evaluate(mode));
console.log(JSON.stringify({ syntheticOnly: true, createdAt: new Date().toISOString(), report }, null, 2));
if (report.some((entry) => entry.checksPassed !== entry.checksTotal)) process.exitCode = 1;
