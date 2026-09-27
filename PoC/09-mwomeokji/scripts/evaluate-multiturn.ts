/** Ten sequential, synthetic HTTP conversations. Stops at the first violated contract. */
import assert from "node:assert/strict";
import { createHmac } from "node:crypto";
import { performance } from "node:perf_hooks";
import { db } from "../lib/db";
import type { DialogueState } from "../lib/dialogue";
import type { MenuItemData, OrderIntent, PreferenceProfile, Recommendation } from "../lib/types";

type Cart = { items: Array<{ id: string; name: string; quantity: number; lineTotal: number }>; total: number };
type Reply = {
  reply: string;
  intent?: OrderIntent;
  provider?: string;
  menuSelectionProvider?: string;
  dialogue?: DialogueState;
  summary?: string[];
  profile?: PreferenceProfile;
  recommendations?: Recommendation[];
  group?: { total: number };
  cart?: Cart;
};
type Turn = { message: string; verify: (reply: Reply, prior: Reply[]) => void };
type Case = { id: string; visit: "dine_in" | "takeout"; turns: Turn[] };
const recs = (reply: Reply) => reply.recommendations || [];
const first = (reply: Reply) => recs(reply)[0]?.item;
const total = (reply: Reply) => reply.group?.total ?? recs(reply).reduce((sum, entry) => sum + entry.item.price * (entry.quantity || 1), 0);
const person = (reply: Reply, label: string) => reply.dialogue?.members.find((entry) => entry.label === label);

const cases: Case[] = [
  {
    id: "01_stale_budget_new_party",
    visit: "dine_in",
    turns: [
      { message: "가상 일행 4명인데 카페인 없는 음료를 1만원 안에서 추천해줘", verify: (reply) => {
        assert.equal(reply.dialogue?.peopleCount, 4);
        assert.equal(reply.dialogue?.preferences.totalBudget, 10000);
      } },
      { message: "남자 4명인데 양이 많아서 든든히 먹을 수 있는 메뉴로 추천해줘", verify: (reply) => {
        assert.equal(reply.dialogue?.preferences.totalBudget, undefined);
        assert.equal(reply.summary?.some((entry) => entry.includes("예산")), false);
        assert.equal(recs(reply).length, 4);
        assert.ok(total(reply) > 10000);
        assert.ok(recs(reply).every((entry) => entry.item.tags.includes("식사")), "a hearty meal must not become drinks or sides");
      } },
    ],
  },
  {
    id: "02_named_party_refinement",
    visit: "dine_in",
    turns: [
      { message: "가상 일행 3명이에요. 민수는 매운 덮밥, 지수는 달콤한 키즈 메뉴, 유나는 순한 국물로 추천해줘", verify: (reply) => {
        assert.equal(reply.dialogue?.peopleCount, 3);
        assert.equal(recs(reply).length, 3);
        assert.ok(recs(reply).some((entry) => entry.forMember === "민수" && entry.item.spiceLevel >= 2));
        assert.ok(recs(reply).some((entry) => entry.forMember === "지수" && entry.item.tags.includes("kids")));
        assert.ok(recs(reply).some((entry) => entry.forMember === "유나" && entry.item.spiceLevel === 0));
      } },
      { message: "유나는 더 얼큰한 국물로 골라줘", verify: (reply) => {
        assert.equal(reply.dialogue?.focusedMemberLabel, "유나");
        assert.ok(person(reply, "유나")?.tastes?.includes("spicy"));
        assert.equal(recs(reply).length, 3);
        assert.ok(recs(reply).some((entry) => entry.forMember === "유나" && entry.item.spiceLevel >= 2 && /수프|국물|탕|찌개/.test(entry.item.name)));
      } },
      { message: "그럼 덮밥으로 추천해줘", verify: (reply) => {
        assert.equal(recs(reply).length, 3);
        assert.ok(recs(reply).some((entry) => entry.forMember === "유나" && /덮밥|볶음밥/.test(entry.item.name)));
        assert.ok(recs(reply).some((entry) => entry.forMember === "민수"));
        assert.ok(recs(reply).some((entry) => entry.forMember === "지수"));
      } },
    ],
  },
  {
    id: "03_caffeine_kind_quantity",
    visit: "takeout",
    turns: [
      { message: "카페인 없는 커피 두 잔을 만원 안에서 추천해줘", verify: (reply) => {
        assert.equal(reply.dialogue?.peopleCount, undefined);
        assert.equal(recs(reply).length, 0);
        assert.match(reply.reply, /카페인 없는 커피/);
      } },
      { message: "그럼 무카페인 음료 두 잔을 1만 원 안에서 추천해줘", verify: (reply) => {
        assert.equal(reply.dialogue?.preferences.coffee, false);
        assert.equal(reply.dialogue?.preferences.quantity, 2);
        assert.equal(recs(reply).length, 1);
        assert.ok(first(reply)?.tags.includes("caffeine_free"));
        assert.ok(total(reply) <= 10000);
      } },
      { message: "새콤한 건 빼고 달콤한 걸로 골라줘", verify: (reply) => {
        assert.equal(reply.dialogue?.preferences.quantity, 2);
        assert.equal(first(reply)?.name, "달콤 사과 주스");
        assert.equal(recs(reply)[0]?.quantity, 2);
      } },
      { message: "첫 번째 담아줘", verify: (reply) => {
        assert.equal(reply.cart?.items.length, 1);
        assert.equal(reply.cart?.items[0]?.quantity, 2);
        assert.equal(reply.cart?.total, 9000);
      } },
    ],
  },
  {
    id: "04_group_diet_and_budget",
    visit: "dine_in",
    turns: [
      { message: "가상 손님 2명인데 한 명은 채식하고 한 명은 매운 걸 못 먹어", verify: (reply) => {
        assert.equal(reply.dialogue?.peopleCount, 2);
        assert.ok(reply.dialogue?.members.some((entry) => entry.dietaryRules.some((rule) => rule.type === "vegetarian")));
        assert.ok(reply.dialogue?.members.some((entry) => entry.maxSpiceLevel === 0));
      } },
      { message: "따뜻한 식사를 총 2만원 안에서 추천해줘", verify: (reply) => {
        assert.equal(recs(reply).length, 2);
        assert.ok(total(reply) <= 20000);
        const vegetarian = reply.dialogue?.members.find((entry) => entry.dietaryRules.some((rule) => rule.type === "vegetarian"));
        assert.ok(recs(reply).some((entry) => entry.forMember === vegetarian?.label && entry.item.dietaryTags.includes("vegetarian")));
        const mild = reply.dialogue?.members.find((entry) => entry.maxSpiceLevel === 0);
        assert.ok(recs(reply).some((entry) => entry.forMember === mild?.label && entry.item.spiceLevel === 0));
      } },
      { message: "예산을 3만원으로 넓혀서 다시 추천해줘", verify: (reply) => {
        assert.equal(reply.dialogue?.preferences.totalBudget, 30000);
        assert.equal(recs(reply).length, 2);
        assert.ok(total(reply) <= 30000);
      } },
    ],
  },
  {
    id: "05_allergy_ingredient_and_cart",
    visit: "dine_in",
    turns: [
      { message: "땅콩 알레르기가 있어. 따뜻한 식사를 추천해줘", verify: (reply) => {
        assert.ok(reply.profile?.allergies.includes("peanut"));
        assert.equal(recs(reply).length, 1);
        assert.ok(first(reply)?.allergens.some((entry) => entry.allergenKey === "peanut" && entry.relation === "excludes" && entry.verificationStatus === "merchant_verified"));
      } },
      { message: "내가 추천받은 메뉴에 땅콩이 들어갔는지 확인해줘", verify: (reply, prior) => {
        assert.ok(reply.reply.includes(first(prior[0])!.name));
        assert.match(reply.reply, /땅콩/);
      } },
      { message: "첫 번째 담아줘", verify: (reply) => {
        assert.equal(reply.cart?.items.length, 1);
        assert.equal(reply.cart?.items[0]?.quantity, 1);
      } },
    ],
  },
  {
    id: "06_spicy_alternative",
    visit: "takeout",
    turns: [
      { message: "매콤한 덮밥 한 그릇 추천해줘", verify: (reply) => {
        assert.equal(recs(reply).length, 1);
        assert.ok(/덮밥|볶음밥/.test(first(reply)!.name));
        assert.ok(first(reply)!.spiceLevel >= 2);
      } },
      { message: "그 메뉴 말고 다른 매운 덮밥으로 추천해줘", verify: (reply, prior) => {
        assert.equal(recs(reply).length, 1);
        assert.notEqual(first(reply)?.id, first(prior[0])?.id);
        assert.ok(first(reply)!.spiceLevel >= 2);
        assert.ok(/덮밥|볶음밥/.test(first(reply)!.name));
      } },
      { message: "첫 번째 담아줘", verify: (reply, prior) => {
        assert.equal(reply.cart?.items.length, 1);
        assert.equal(reply.cart?.items[0]?.name, first(prior[1])?.name);
      } },
    ],
  },
  {
    id: "07_semantic_menu_and_ingredient",
    visit: "dine_in",
    turns: [
      { message: "바질 향이 진한 파스타가 먹고 싶어. 하나 추천해줘", verify: (reply) => {
        assert.equal(first(reply)?.name, "바질 토마토 파스타");
      } },
      { message: "첫 번째 메뉴에 밀 성분이 들어가 있니?", verify: (reply, prior) => {
        assert.ok(reply.reply.includes(first(prior[0])!.name));
        assert.match(reply.reply, /밀 표기를 확인/);
      } },
    ],
  },
  {
    id: "08_drink_flavor_change",
    visit: "takeout",
    turns: [
      { message: "시원한 오렌지 맛 탄산 음료 한 잔 추천해줘", verify: (reply) => {
        assert.equal(first(reply)?.name, "오렌지 에이드");
      } },
      { message: "이번에는 사과 맛 음료로 바꿔줘", verify: (reply) => {
        assert.equal(first(reply)?.name, "달콤 사과 주스");
      } },
      { message: "첫 번째 담아줘", verify: (reply) => {
        assert.equal(reply.cart?.items[0]?.name, "달콤 사과 주스");
      } },
    ],
  },
  {
    id: "09_explicit_budget_correction",
    visit: "dine_in",
    turns: [
      { message: "혼자 따뜻한 식사를 만원 이내로 추천해줘", verify: (reply) => {
        assert.equal(reply.dialogue?.preferences.totalBudget, 10000);
        assert.equal(recs(reply).length, 1);
        assert.ok(total(reply) <= 10000);
      } },
      { message: "예산 제한은 없어. 소불고기 덮밥으로 추천해줘", verify: (reply) => {
        assert.equal(reply.dialogue?.preferences.totalBudget, undefined);
        assert.equal(first(reply)?.name, "든든 소불고기 덮밥");
        assert.ok(total(reply) > 10000);
        assert.equal(reply.dialogue?.members.some((entry) => entry.label === "제한"), false, "a budget restriction is not a diner");
      } },
    ],
  },
  {
    id: "10_missing_item_then_broaden",
    visit: "takeout",
    turns: [
      { message: "블루베리 스무디를 마시고 싶어. 추천해줘", verify: (reply) => {
        assert.equal(recs(reply).length, 0);
        assert.equal(reply.profile?.allergies.length, 0, "allergies must not leak from another session");
        assert.doesNotMatch(reply.reply, /땅콩 알레르기/);
        assert.match(reply.reply, /메뉴가 없|확인된 메뉴가 없/);
      } },
      { message: "그럼 달달하고 카페인 없는 음료로 추천해줘", verify: (reply) => {
        assert.equal(first(reply)?.name, "달콤 사과 주스");
      } },
      { message: "그걸 두 잔으로, 만원 안에서 추천해줘", verify: (reply) => {
        assert.equal(reply.dialogue?.preferences.quantity, 2);
        assert.equal(reply.dialogue?.preferences.totalBudget, 10000);
        assert.equal(first(reply)?.name, "달콤 사과 주스");
        assert.equal(total(reply), 9000);
      } },
    ],
  },
];

const base = process.env.POC09_SMOKE_BASE || "http://127.0.0.1:8000/poc/mwomeokji/api";
const hashes: string[] = [];
function digest(token: string) {
  return createHmac("sha256", process.env.POC09_SESSION_SECRET || "poc09-development-only").update(token).digest("hex");
}
function commonChecks(reply: Reply, catalog: Set<string>) {
  for (const entry of recs(reply)) {
    assert.ok(catalog.has(entry.item.id), "recommendation must be in the published catalog");
    assert.equal(entry.item.isAvailable, true);
    assert.equal(entry.item.isPublished, true);
  }
  if (reply.group && recs(reply).length) {
    assert.equal(reply.group.total, recs(reply).reduce((sum, entry) => sum + entry.item.price, 0));
  }
  const budget = reply.dialogue?.preferences.totalBudget ?? reply.profile?.budget;
  if (budget && recs(reply).length) assert.ok(total(reply) <= budget, "recommendation exceeds active budget");
}
async function runCase(testCase: Case) {
  let cookie = "";
  async function request(path: string, method = "GET", value?: unknown): Promise<Reply & { menu?: MenuItemData[] }> {
    const response = await fetch(base + "/" + path, {
      method,
      signal: AbortSignal.timeout(30000),
      headers: { ...(value === undefined ? {} : { "Content-Type": "application/json" }), ...(cookie ? { Cookie: cookie } : {}) },
      body: value === undefined ? undefined : JSON.stringify(value),
    });
    const setCookie = response.headers.get("set-cookie");
    if (setCookie?.startsWith("poc09_guest=")) {
      cookie = setCookie.split(";")[0];
      hashes.push(digest(cookie.slice("poc09_guest=".length)));
    }
    const result = await response.json();
    if (!response.ok) throw new Error(testCase.id + " " + path + ": HTTP " + response.status + " " + JSON.stringify(result));
    return result;
  }
  const boot = await request("bootstrap/?slug=orange-table");
  assert.ok(cookie, "bootstrap must issue a fresh guest cookie");
  assert.equal(boot.profile?.allergies.length, 0, "new guests must not inherit another guest's allergies");
  const catalog = new Set((boot.menu || []).map((item) => item.id));
  await request("visit/", "POST", { mode: testCase.visit });
  const prior: Reply[] = [];
  for (let index = 0; index < testCase.turns.length; index++) {
    const turn = testCase.turns[index];
    const started = performance.now();
    const reply = await request("conversation/", "POST", { message: turn.message });
    console.log(JSON.stringify({
      case: testCase.id, turn: index + 1, ms: Math.round(performance.now() - started),
      interpretation: reply.provider || null, selection: reply.menuSelectionProvider || null,
      summary: reply.summary || [], menus: recs(reply).map((entry) => ({ name: entry.item.name, forMember: entry.forMember, quantity: entry.quantity })),
      total: total(reply), answer: reply.reply.slice(0, 180),
    }));
    try {
      commonChecks(reply, catalog);
      turn.verify(reply, prior);
    } catch (error) {
      throw new Error(testCase.id + " turn " + (index + 1) + " failed: " + String(error));
    }
    prior.push(reply);
  }
  console.log(JSON.stringify({ case: testCase.id, status: "PASS", turns: testCase.turns.length }));
}
try {
  for (const testCase of cases) await runCase(testCase);
  console.log(JSON.stringify({ syntheticOnly: true, passedCases: cases.length, passedTurns: cases.reduce((sum, entry) => sum + entry.turns.length, 0) }));
} finally {
  if (hashes.length) await db.guestSession.deleteMany({ where: { tokenHash: { in: hashes } } });
  await db.$disconnect();
}
