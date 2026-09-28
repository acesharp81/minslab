import { afterEach, describe, expect, it, vi } from "vitest";
import { understand } from "../lib/ai";
import { anonymizeKnownNames, conversationSnapshot, resolveSeatTarget } from "../lib/conversation-context";
import { emptyDialogue } from "../lib/dialogue";

const state = {
  ...emptyDialogue(), peopleCount: 2,
  members: [
    { id: "actual-private-id", label: "민수", allergies: ["peanut"], dietaryRules: [{ type: "vegetarian", mode: "strict" as const }], tastes: ["mild" as const] },
    { id: "second-private-id", label: "일행 2", allergies: [], dietaryRules: [], tastes: ["soup" as const] },
  ],
  preferences: { action: "recommend" as const, category: "식사", totalBudget: 30000 },
  lastRecommendations: [{ id: "menu-salad", forMember: "민수" }, { id: "menu-soup", forMember: "일행 2" }],
  focusedMemberLabel: "민수",
};
const names = new Map([["menu-salad", "오렌지 치킨 샐러드"], ["menu-soup", "얼큰 닭고기 수프"]]);

afterEach(() => { vi.unstubAllEnvs(); vi.unstubAllGlobals(); });

describe("Groq conversation boundary", () => {
  it("sends only anonymized seats and current public suggestions", () => {
    const snapshot = conversationSnapshot(state, names);
    const serialized = JSON.stringify(snapshot);
    expect(serialized).toContain("seat_1");
    expect(serialized).toContain("오렌지 치킨 샐러드");
    expect(serialized).not.toMatch(/민수|actual-private-id|peanut|vegetarian|allerg|diet|session|cart/);
    expect(anonymizeKnownNames("민수 메뉴만 바꿔줘", state)).toBe("일행 1 메뉴만 바꿔줘");
  });

  it("accepts a model seat only when the user identified the current dish or diner", () => {
    expect(resolveSeatTarget("샐러드는 별로야", state, "seat_1", names)).toBe("민수");
    expect(resolveSeatTarget("국물이 좋아", state, "seat_1", names)).toBeUndefined();
    expect(resolveSeatTarget("민수 메뉴 바꿔줘", state, "seat_1", names)).toBe("민수");
    expect(resolveSeatTarget("샐러드는 별로야", state, "seat_9", names)).toBeUndefined();
    expect(resolveSeatTarget("첫 번째 거 더 맵게 바꿔줘", state, "seat_1", names)).toBe("민수");
    expect(resolveSeatTarget("첫 번째 거 더 맵게 바꿔줘", state, "seat_2", names)).toBeUndefined();
  });

  it("retries one strict JSON failure and still validates the model response", async () => {
    vi.stubEnv("POC09_CONVERSATION_PROVIDER", "groq");
    vi.stubEnv("POC09_LLM_MODEL", "openai/gpt-oss-20b");
    vi.stubEnv("GROQ_API_KEY", "unit-test-key");
    const modes: string[] = [];
    vi.stubGlobal("fetch", vi.fn(async (_url: string, options: RequestInit) => {
      const body = JSON.parse(String(options.body));
      modes.push(body.response_format.type);
      if (modes.length === 1) return { ok: false, status: 400, json: async () => ({ error: { code: "json_validate_failed" } }) };
      return { ok: true, status: 200, json: async () => ({ choices: [{ message: { content: JSON.stringify({
        action: "recommend", targetSeat: null, peopleCount: null, totalBudget: 30000,
        category: null, globalTastes: [], globalLabels: [], memberUpdates: [], offerResolution: "none", reference: "none", alternative: false,
        clarification: null,
      }) } }], usage: { prompt_tokens: 80, completion_tokens: 30 } }) };
    }));
    const result = await understand("예산을 3만원으로 넓혀서 다시 추천해줘", {
      snapshot: conversationSnapshot(state, names), outboundMessage: "예산을 3만원으로 넓혀서 다시 추천해줘",
    });
    expect(modes).toEqual(["json_schema", "json_object"]);
    expect(result.provider).toBe("groq");
    expect(result.intent.totalBudget).toBe(30000);
  });

  it("maps an anonymized model member update back to the local diner", async () => {
    vi.stubEnv("POC09_CONVERSATION_PROVIDER", "groq");
    vi.stubEnv("POC09_LLM_MODEL", "openai/gpt-oss-20b");
    vi.stubEnv("GROQ_API_KEY", "unit-test-key");
    let sent = "";
    vi.stubGlobal("fetch", vi.fn(async (_url: string, options: RequestInit) => {
      sent = String(options.body);
      return { ok: true, status: 200, json: async () => ({ choices: [{ message: { content: JSON.stringify({
        action: "recommend", targetSeat: "seat_1", peopleCount: null, totalBudget: null,
        category: null, globalTastes: [], globalLabels: [],
        memberUpdates: [{ label: "일행 1", count: 1, tastes: ["spicy"], labels: [] }],
        offerResolution: "none", reference: "none", alternative: true, clarification: null,
      }) } }], usage: { prompt_tokens: 100, completion_tokens: 50 } }) };
    }));
    const result = await understand("민수는 더 얼큰한 걸로 바꿔줘", {
      snapshot: conversationSnapshot(state, names),
      outboundMessage: anonymizeKnownNames("민수는 더 얼큰한 걸로 바꿔줘", state),
      seatLabels: state.members.map((member) => member.label),
    });
    expect(result.provider).toBe("groq");
    expect(result.memberUpdates[0]?.label).toBe("민수");
    expect(JSON.stringify(JSON.parse(sent).messages)).not.toContain("민수");
  });

  it("uses a pinned free model with an approved compact payload", async () => {
    vi.stubEnv("POC09_CONVERSATION_PROVIDER", "groq");
    vi.stubEnv("POC09_LLM_MODEL", "openai/gpt-oss-20b");
    vi.stubEnv("GROQ_API_KEY", "unit-test-key");
    let sent = "";
    vi.stubGlobal("fetch", vi.fn(async (url: string, options: RequestInit) => {
      expect(url).toBe("https://api.groq.com/openai/v1/chat/completions");
      sent = String(options.body);
      return { ok: true, status: 200, json: async () => ({ choices: [{ message: { content: JSON.stringify({
        action: "recommend", targetSeat: "seat_1", peopleCount: null, totalBudget: null,
        category: null, globalTastes: [], globalLabels: [], memberUpdates: [], offerResolution: "none", reference: "none",
        alternative: true, clarification: null,
      }) } }], usage: { prompt_tokens: 100, completion_tokens: 50 } }) };
    }));
    const result = await understand("민수 메뉴 말고 다른 걸로 추천해줘", {
      snapshot: conversationSnapshot(state, names), outboundMessage: anonymizeKnownNames("민수 메뉴 말고 다른 걸로 추천해줘", state),
    });
    expect(result.provider).toBe("groq");
    expect(result.intent.action).toBe("recommend");
    expect(result.targetSeat).toBe("seat_1");
    const userPayload = JSON.parse((JSON.parse(sent).messages as Array<{role: string; content: string}>).find((entry) => entry.role === "user")!.content);
    expect(JSON.stringify(userPayload)).not.toMatch(/민수|peanut|vegetarian|actual-private-id|second-private-id/);
    expect(userPayload.currentTurn).toBe("일행 1 메뉴 말고 다른 걸로 추천해줘");
  });
});
