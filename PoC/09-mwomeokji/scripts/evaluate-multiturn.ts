/** Sequential, synthetic HTTP conversations. Stops at the first violated contract. */
import assert from "node:assert/strict";
import { createHmac, randomUUID } from "node:crypto";
import { performance } from "node:perf_hooks";
import { db } from "../lib/db";
import type { DialogueState } from "../lib/dialogue";
import type { MenuItemData, OrderIntent, PreferenceProfile, Recommendation } from "../lib/types";

type Cart = { items: Array<{ id: string; name: string; quantity: number; lineTotal: number }>; total: number; canOrder?: boolean };
type Reply = {
  reply: string;
  intent?: OrderIntent;
  provider?: string;
  modelStatus?: number;
  modelErrorCode?: string;
  menuSelectionProvider?: string;
  dialogue?: DialogueState;
  summary?: string[];
  profile?: PreferenceProfile;
  recommendations?: Recommendation[];
  group?: { total: number };
  cart?: Cart;
  nextAction?: string;
  reset?: boolean;
  code?: string;
  total?: number;
  lines?: Array<{ menuName: string; quantity: number }>
};
type Turn = { message: string; path?: string; body?: unknown; verify: (reply: Reply, prior: Reply[]) => void };
type Case = { id: string; requiresGroq?: boolean; visit: "dine_in" | "takeout"; turns: Turn[]; prepare?: (request: (path: string, method?: string, value?: unknown) => Promise<Reply & { menu?: MenuItemData[] }>, boot: Reply & { menu?: MenuItemData[] }) => Promise<void> };
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
        assert.ok(recs(reply).every((entry) => entry.item.tags.includes("식사") && entry.item.tags.includes("든든")), "a hearty meal must match merchant-curated hearty dishes");
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
        assert.ok(first(reply)?.tags.includes("caffeine_free"));
        assert.ok(first(reply)?.tags.includes("sweet"));
        assert.equal(first(reply)?.tags.includes("sour"), false);
        assert.ok(total(reply) <= 10000);
        assert.equal(recs(reply)[0]?.quantity, 2);
      } },
      { message: "첫 번째 담아줘", verify: (reply, prior) => {
        assert.equal(reply.cart?.items.length, 1);
        assert.equal(reply.cart?.items[0]?.quantity, 2);
        assert.equal(reply.cart?.items[0]?.name, first(prior[2])?.name);
        assert.equal(reply.cart?.total, total(prior[2]));
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
        assert.ok(first(reply)?.tags.includes("음료"));
        assert.ok(first(reply)?.tags.includes("caffeine_free"));
        assert.ok(first(reply)?.tags.includes("sweet"));
      } },
      { message: "그걸 두 잔으로, 만원 안에서 추천해줘", verify: (reply, prior) => {
        assert.equal(reply.dialogue?.preferences.quantity, 2);
        assert.equal(reply.dialogue?.preferences.totalBudget, 10000);
        assert.equal(first(reply)?.id, first(prior[1])?.id);
        assert.ok(total(reply) <= 10000);
      } },
    ],
  },
  {
    id: "11_brunch_party",
    visit: "dine_in",
    turns: [
      { message: "가상 친구 3명이서 브런치 메뉴를 추천해줘", verify: (reply) => {
        assert.equal(reply.dialogue?.peopleCount, 3);
        assert.ok(reply.summary?.includes("브런치"));
        assert.equal(recs(reply).length, 3);
        assert.ok(recs(reply).every((entry) => entry.item.tags.includes("브런치")), "every diner needs a catalog-backed brunch dish");
        assert.ok(new Set(recs(reply).map((entry) => entry.item.id)).size >= 2, "offer at least two brunch dishes");
      } },
      { message: "추천한 거 전부 담아줘", verify: (reply, prior) => {
        assert.ok(reply.summary?.includes("브런치"));
        assert.equal(reply.cart?.items.length, 3);
        assert.equal(reply.cart?.total, total(prior[0]));
      } },
    ],
  },
  {
    id: "12_lunch_dinner_rice",
    visit: "dine_in",
    turns: [
      { message: "가상 손님이 점심으로 밥 메뉴를 추천해줘", verify: (reply) => {
        assert.equal(recs(reply).length, 1);
        assert.ok(first(reply)?.tags.includes("밥"));
        assert.ok(first(reply)?.tags.includes("식사"));
      } },
      { message: "저녁엔 다른 든든한 밥 메뉴로 골라줘", verify: (reply, prior) => {
        assert.equal(recs(reply).length, 1);
        assert.ok(first(reply)?.tags.includes("밥"));
        assert.ok(first(reply)?.tags.includes("든든"));
        assert.notEqual(first(reply)?.id, first(prior[0])?.id);
      } },
    ],
  },
  {
    id: "13_bread_to_brunch",
    visit: "takeout",
    turns: [
      { message: "빵으로 간단히 먹을 메뉴를 추천해줘", verify: (reply) => {
        assert.ok(first(reply)?.tags.includes("빵"));
        assert.ok(reply.summary?.includes("빵"));
      } },
      { message: "그럼 브런치 메뉴로 바꿔줘", verify: (reply) => {
        assert.equal(recs(reply).length, 1);
        assert.ok(first(reply)?.tags.includes("브런치"));
        assert.ok(reply.summary?.includes("브런치"));
      } },
    ],
  },
  {
    id: "14_dessert_to_drink",
    visit: "dine_in",
    turns: [
      { message: "달콤한 디저트 하나 추천해줘", verify: (reply) => {
        assert.equal(recs(reply).length, 1);
        assert.ok(first(reply)?.tags.includes("디저트"));
      } },
      { message: "그럼 카페인 없는 음료로 바꿔줘", verify: (reply) => {
        assert.equal(recs(reply).length, 1);
        assert.ok(first(reply)?.tags.includes("음료"));
        assert.ok(first(reply)?.tags.includes("caffeine_free"));
        assert.equal(reply.dialogue?.preferences.category, "음료");
      } },
    ],
  },
  {
    id: "15_spicy_to_mild_rice",
    visit: "takeout",
    turns: [
      { message: "매콤한 밥 메뉴를 추천해줘", verify: (reply) => {
        assert.equal(recs(reply).length, 1);
        assert.ok(first(reply)?.tags.includes("밥"));
        assert.ok(first(reply)!.spiceLevel >= 2);
      } },
      { message: "이번엔 맵지 않은 밥으로 골라줘", verify: (reply) => {
        assert.equal(recs(reply).length, 1);
        assert.ok(first(reply)?.tags.includes("밥"));
        assert.equal(first(reply)?.spiceLevel, 0);
      } },
    ],
  },
  {
    id: "16_signature_to_popular",
    visit: "dine_in",
    turns: [
      { message: "이 가상 매장의 대표메뉴를 추천해줘", verify: (reply) => {
        assert.equal(first(reply)?.name, "햇살 치킨 덮밥");
        assert.ok(reply.summary?.includes("대표메뉴"));
      } },
      { message: "대표메뉴 말고 추천이 많은 식사로 골라줘", verify: (reply) => {
        assert.equal(recs(reply).length, 1);
        assert.ok(first(reply)?.tags.includes("식사"));
        assert.ok(first(reply)!.popularity >= 70);
        assert.notEqual(first(reply)?.name, "햇살 치킨 덮밥");
      } },
    ],
  },
  {
    id: "17_child_meal",
    visit: "dine_in",
    turns: [
      { message: "애기용으로 맵지 않은 밥 메뉴를 추천해줘", verify: (reply) => {
        assert.equal(recs(reply).length, 1);
        assert.ok(first(reply)?.tags.includes("kids"));
        assert.equal(first(reply)?.spiceLevel, 0);
        assert.match(reply.reply, /보호자/);
      } },
      { message: "첫 번째 메뉴에 달걀이 들어가니?", verify: (reply, prior) => {
        assert.ok(reply.reply.includes(first(prior[0])!.name));
        assert.match(reply.reply, /달걀/);
      } },
    ],
  },
  {
    id: "18_date_to_coworker",
    visit: "dine_in",
    turns: [
      { message: "가상 손님 둘이 데이트하면서 먹을 식사를 추천해줘", verify: (reply) => {
        assert.equal(reply.dialogue?.peopleCount, 2);
        assert.equal(recs(reply).length, 2);
        assert.ok(recs(reply).every((entry) => entry.item.tags.includes("식사") && entry.item.tags.includes("데이트")));
      } },
      { message: "이번엔 직장동료와 2명이서 점심 먹을 메뉴로 다시 추천해줘", verify: (reply) => {
        assert.equal(reply.dialogue?.peopleCount, 2);
        assert.equal(recs(reply).length, 2);
        assert.ok(recs(reply).every((entry) => entry.item.tags.includes("식사") && entry.item.tags.includes("직장동료")));
      } },
    ],
  },
  {
    id: "19_previous_completed_order",
    visit: "takeout",
    prepare: async (request, boot) => {
      const tofu = boot.menu?.find((entry) => entry.name === "버섯 두부 덮밥");
      assert.ok(tofu);
      await request("cart/", "POST", { menuItemId: tofu.id, quantity: 1, selectedOptionIds: [] });
      await request("checkout/", "POST", { idempotencyKey: `topic-history-${randomUUID()}`, paymentMethod: "mock_card", note: "가상 평가 주문" });
    },
    turns: [
      { message: "이전에 주문했던 메뉴 다시 추천해줘", verify: (reply) => {
        assert.equal(first(reply)?.name, "버섯 두부 덮밥");
        assert.match(reply.reply, /이전에|전에/);
      } },
      { message: "첫 번째 담아줘", verify: (reply) => {
        assert.equal(reply.cart?.items[0]?.name, "버섯 두부 덮밥");
      } },
    ],
  },
  {
    id: "20_no_previous_order",
    visit: "dine_in",
    turns: [
      { message: "지난번에 주문했던 메뉴를 추천해줘", verify: (reply) => {
        assert.equal(recs(reply).length, 0);
        assert.match(reply.reply, /이전 주문 기록이 없/);
      } },
    ],
  },
  {
    id: "21_long_tail_seafood_allergy",
    visit: "dine_in",
    turns: [
      { message: "조개 맑은탕 한 그릇을 추천해줘", verify: (reply) => {
        assert.equal(first(reply)?.name, "조개 맑은탕");
        assert.ok(first(reply)?.allergens.some((entry) => entry.allergenKey === "mollusk" && entry.relation === "contains"));
      } },
      { message: "조개류 알레르기가 있어서 다른 국물로 추천해줘", verify: (reply) => {
        assert.ok(reply.profile?.allergies.includes("mollusk"));
        assert.equal(recs(reply).length, 1);
        assert.ok(/수프|국|탕|찌개/.test(first(reply)!.name));
        assert.ok(first(reply)?.allergens.some((entry) => entry.allergenKey === "mollusk" && entry.relation === "excludes" && entry.verificationStatus === "merchant_verified"));
      } },
    ],
  },
  {
    id: "22_decaf_coffee_distinction",
    visit: "takeout",
    turns: [
      { message: "디카페인 아이스 커피 한 잔을 추천해줘", verify: (reply) => {
        assert.equal(first(reply)?.name, "디카페인 아이스 아메리카노");
        assert.ok(first(reply)?.tags.includes("decaf"));
        assert.equal(first(reply)?.tags.includes("caffeine_free"), false);
      } },
      { message: "카페인이 완전히 없는 커피로 바꿔줘", verify: (reply) => {
        assert.equal(recs(reply).length, 0);
        assert.match(reply.reply, /카페인 없는 커피/);
      } },
    ],
  },
  {
    id: "23_refresh_clears_hidden_party",
    visit: "dine_in",
    turns: [
      { message: "가상 일행 4명인데 채식 식사로 추천해줘", verify: (reply) => {
        assert.equal(reply.dialogue?.peopleCount, 4);
        assert.equal(recs(reply).length, 4);
      } },
      { message: "새로고침", path: "conversation/reset/", verify: (reply) => {
        assert.equal(reply.reset, true);
        assert.equal(reply.dialogue?.peopleCount, undefined);
        assert.equal(reply.cart?.items.length, 0);
      } },
      { message: "우린 채식주의자야 채식으로 편성된 메뉴를 알려줘", verify: (reply) => {
        assert.equal(reply.dialogue?.peopleCount, undefined, "a refreshed chat must not inherit four diners");
        assert.ok(recs(reply).length > 0);
        assert.ok(recs(reply).every((entry) => entry.item.dietaryTags.includes("vegetarian")));
      } },
    ],
  },
  {
    id: "24_voice_only_group_checkout",
    visit: "dine_in",
    turns: [
      { message: "가상 일행 4명 모두 채식으로 식사 메뉴 추천해줘", verify: (reply) => {
        assert.equal(reply.dialogue?.peopleCount, 4);
        assert.equal(recs(reply).length, 4);
        assert.ok(recs(reply).every((entry) => entry.item.dietaryTags.includes("vegetarian")));
      } },
      { message: "좋아 담아줘", verify: (reply, prior) => {
        assert.equal(reply.cart?.items.length, 4);
        assert.equal(reply.cart?.total, total(prior[0]));
      } },
      { message: "음료도 추천해줘", verify: (reply) => {
        assert.equal(recs(reply).length, 4);
        assert.ok(recs(reply).every((entry) => entry.item.tags.includes("음료")));
        assert.equal(new Set(recs(reply).map((entry) => entry.item.id)).size, 4);
      } },
      { message: "겹치지 않게 추천해줘", verify: (reply) => {
        assert.equal(recs(reply).length, 4);
        assert.ok(recs(reply).every((entry) => entry.item.tags.includes("음료")));
        assert.equal(new Set(recs(reply).map((entry) => entry.item.id)).size, 4);
      } },
      { message: "좋아 담아줘", verify: (reply, prior) => {
        assert.equal(reply.cart?.items.length, 8);
        assert.equal(reply.cart?.total, (prior[1].cart?.total || 0) + total(prior[3]));
      } },
      { message: "주문할께", verify: (reply, prior) => {
        assert.equal(reply.nextAction, "confirm_checkout");
        assert.equal(recs(reply).length, 0, "checkout intent must not trigger a new recommendation");
        assert.equal(reply.cart?.items.length, 8);
        assert.equal(reply.cart?.total, prior[4].cart?.total);
      } },
      { message: "응", verify: (reply) => {
        assert.equal(reply.nextAction, "checkout");
      } },
      { message: "모의 주문 접수", path: "checkout/", body: { idempotencyKey: randomUUID(), paymentMethod: "mock_card", note: "" }, verify: (reply, prior) => {
        assert.ok(reply.code?.startsWith("MMJ-"));
        assert.equal(reply.lines?.length, 8);
        assert.equal(reply.total, prior[5].cart?.total);
      } },
    ],
  },
  {
    id: "25_whole_party_allergy",
    visit: "dine_in",
    turns: [
      { message: "우리 모두 땅콩 알레르기가 있어. 4명 식사 메뉴 추천해줘", verify: (reply) => {
        assert.equal(reply.dialogue?.peopleCount, 4);
        assert.ok(reply.profile?.allergies.includes("peanut"));
        assert.equal(recs(reply).length, 4);
        assert.ok(recs(reply).every((entry) => entry.item.allergens.some((allergen) => allergen.allergenKey === "peanut" && allergen.relation === "excludes" && allergen.verificationStatus === "merchant_verified")));
      } },
      { message: "좋아 담아줘", verify: (reply) => {
        assert.equal(reply.cart?.items.length, 4);
        assert.equal(reply.cart?.canOrder, true);
      } },
    ],
  },
  {
    id: "26_spoken_group_spice_and_soup_replacement",
    visit: "dine_in",
    turns: [
      { message: "다섯명인데 둘은 맵찔이고, 셋은 매운거 잘 먹어. 이 집 대표 메뉴로 점심먹기 좋은 걸로 추천해줘", verify: (reply) => {
        assert.equal(reply.dialogue?.peopleCount, 5);
        assert.equal(recs(reply).length, 5);
        assert.equal(recs(reply).filter((entry) => entry.item.spiceLevel === 0).length, 2);
        assert.equal(recs(reply).filter((entry) => entry.item.spiceLevel >= 2).length, 3);
        assert.ok(recs(reply).every((entry) => entry.item.tags.includes("식사")));
      } },
      { message: "샐러드는 별로인거 같아 다른 메뉴로 부탁해. 해장되는 메뉴면 좋겠어", verify: (reply, prior) => {
        assert.doesNotMatch(reply.reply, /User wants|different menu instead/);
        const salad = recs(prior[0]).find((entry) => entry.item.name.includes("샐러드"));
        if (!salad) {
          assert.match(reply.reply, /직전 추천에는.*없어요/);
          assert.equal(recs(reply).length, 0);
          assert.deepEqual(reply.dialogue?.lastRecommendations, prior[0].dialogue?.lastRecommendations);
        } else {
          assert.equal(recs(reply).length, 5);
          const replacement = recs(reply).find((entry) => entry.forMember === salad.forMember);
          assert.ok(replacement);
          assert.notEqual(replacement.item.id, salad.item.id);
          assert.match(replacement.item.name, /수프|국|탕|찌개/);
          for (const old of recs(prior[0]).filter((entry) => entry.forMember !== salad.forMember))
            assert.equal(recs(reply).find((entry) => entry.forMember === old.forMember)?.item.id, old.item.id);
        }
      } },
    ],
  },
  {
    id: "27_salad_only_replaced_with_soup",
    visit: "dine_in",
    prepare: async (_request, boot) => {
      const names = ["햇살 치킨 덮밥", "오렌지 치킨 샐러드", "매콤 제육 덮밥", "얼큰 닭고기 덮밥", "고추장 소불고기 비빔밥"];
      const selected = names.map((name) => boot.menu?.find((item) => item.name === name));
      assert.ok(selected.every(Boolean));
      const tokenHash = hashes.at(-1)!;
      const session = await db.guestSession.findUniqueOrThrow({ where: { tokenHash } });
      const dialogue: DialogueState = {
        peopleCount: 5,
        members: names.map((_, index) => ({ id: `generic-${index + 1}`, label: `일행 ${index + 1}`, allergies: [], dietaryRules: [],
          maxSpiceLevel: index < 2 ? 0 : undefined, tastes: index < 2 ? ["mild"] : ["spicy"] })),
        preferences: { action: "recommend", category: "식사", peopleCount: 5 },
        menuLabels: [],
        lastRecommendations: selected.map((item, index) => ({ id: item!.id, forMember: `일행 ${index + 1}` })),
        pendingCheckout: false,
      };
      await db.guestSession.update({ where: { id: session.id }, data: { context: { ...boot.profile, dialogue } } });
    },
    turns: [
      { message: "샐러드는 별로인거 같아 다른 메뉴로 부탁해. 해장되는 메뉴면 좋겠어", verify: (reply) => {
        assert.equal(recs(reply).length, 5);
        const changed = recs(reply).find((entry) => entry.forMember === "일행 2");
        assert.ok(changed);
        assert.doesNotMatch(changed.item.name, /샐러드/);
        assert.match(changed.item.name, /수프|국|탕|찌개/);
        assert.equal(changed.item.spiceLevel, 0);
        const fixed = ["햇살 치킨 덮밥", "매콤 제육 덮밥", "얼큰 닭고기 덮밥", "고추장 소불고기 비빔밥"];
        assert.deepEqual(recs(reply).filter((entry) => entry.forMember !== "일행 2").map((entry) => entry.item.name), fixed);
        assert.match(reply.reply, /일행 2 메뉴를 새로 골랐어요/);
      } },
    ],
  },
  {
    id: "28_family_kids_adults_followup",
    requiresGroq: true,
    visit: "dine_in",
    turns: [
      { message: "4식구 외식을 왔어. 아이 둘은 키즈 메뉴로 추천하고, 나와 와이프는 든든히 먹을 수 있는 메뉴로 부탁해. 와이프는 매운걸 잘 못먹으니 맵지않은 메뉴로 추천해줘", verify: (reply) => {
        assert.equal(reply.dialogue?.peopleCount, 4);
        assert.equal(recs(reply).length, 4, "the available kids menu and adult meals should make a complete four-person proposal");
        assert.ok(recs(reply).filter((entry) => entry.item.tags.includes("kids")).length >= 2);
        assert.ok(person(reply, "나")?.menuLabels?.includes("든든"));
        assert.ok(person(reply, "와이프")?.menuLabels?.includes("든든"));
        assert.ok(recs(reply).some((entry) => entry.forMember?.includes("와이프") && entry.item.spiceLevel === 0));
        assert.ok(recs(reply).some((entry) => entry.forMember === "나" && entry.item.tags.includes("든든")));
      } },
      { message: "좋아 담아줘", verify: (reply) => {
        assert.equal(reply.cart?.items.length, 4);
      } },
    ],
  },

  ...["그래 그러게 해줘", "그렇게 해달라고"].map((agreement, index): Case => ({
    id: `29_${index + 1}_accept_child_substitute`,
    requiresGroq: true,
    visit: "dine_in",
    prepare: async (_request, boot) => {
      const tokenHash = hashes.at(-1)!;
      const session = await db.guestSession.findUniqueOrThrow({ where: { tokenHash } });
      const dialogue: DialogueState = {
        peopleCount: 4,
        members: [
          { id: "child-1", label: "아이 1", allergies: [], dietaryRules: [], tastes: ["kids"] },
          { id: "child-2", label: "아이 2", allergies: [], dietaryRules: [], tastes: ["kids"] },
          { id: "adult-1", label: "나", allergies: [], dietaryRules: [], menuLabels: ["든든"] },
          { id: "adult-2", label: "와이프", allergies: [], dietaryRules: [], tastes: ["mild"], menuLabels: ["든든"], maxSpiceLevel: 0 },
        ],
        preferences: { action: "recommend", peopleCount: 4, category: "식사" },
        menuLabels: [], lastRecommendations: [], pendingCheckout: false,
        pendingOffer: { kind: "replace_kids_with_mild", memberIds: ["child-1", "child-2"] },
      };
      await db.guestSession.update({ where: { id: session.id }, data: { context: { ...boot.profile, dialogue } } });
    },
    turns: [
      { message: agreement, verify: (reply) => {
        assert.equal(reply.provider, "groq");
        assert.equal(reply.dialogue?.pendingOffer, undefined);
        assert.equal(recs(reply).length, 4);
        assert.ok(recs(reply).filter((entry) => entry.forMember?.startsWith("아이")).every((entry) => entry.item.spiceLevel === 0 && !entry.item.tags.includes("kids")));
        assert.ok(recs(reply).some((entry) => entry.forMember === "나" && entry.item.tags.includes("든든")));
        assert.ok(recs(reply).some((entry) => entry.forMember === "와이프" && entry.item.tags.includes("든든") && entry.item.spiceLevel === 0));
      } },
    ],
  })),

  {
    id: "30_unavailable_kids_offer_then_accept",
    requiresGroq: true,
    visit: "dine_in",
    prepare: async (_request, boot) => {
      const tokenHash = hashes.at(-1)!;
      const session = await db.guestSession.findUniqueOrThrow({ where: { tokenHash } });
      const vegan = [{ type: "vegan" as const, mode: "strict" as const }];
      const dialogue: DialogueState = {
        peopleCount: 4,
        members: [
          { id: "child-1", label: "아이 1", allergies: [], dietaryRules: vegan, tastes: ["kids"] },
          { id: "child-2", label: "아이 2", allergies: [], dietaryRules: vegan, tastes: ["kids"] },
          { id: "adult-1", label: "나", allergies: [], dietaryRules: [], menuLabels: ["든든"] },
          { id: "adult-2", label: "와이프", allergies: [], dietaryRules: [], tastes: ["mild"], menuLabels: ["든든"], maxSpiceLevel: 0 },
        ],
        preferences: { action: "recommend", peopleCount: 4, category: "식사" },
        menuLabels: [], lastRecommendations: [], pendingCheckout: false,
      };
      await db.guestSession.update({ where: { id: session.id }, data: { context: { ...boot.profile, dialogue } } });
    },
    turns: [
      { message: "추천해줘", verify: (reply) => {
        assert.equal(recs(reply).length, 0);
        assert.equal(reply.dialogue?.pendingOffer?.kind, "replace_kids_with_mild");
        assert.match(reply.reply, /아이들에게 맵지 않은 일반 메뉴/);
      } },
      { message: "그래 그러게 해줘", verify: (reply) => {
        assert.equal(reply.provider, "groq");
        assert.equal(reply.dialogue?.pendingOffer, undefined);
        assert.equal(recs(reply).length, 4);
        assert.ok(recs(reply).filter((entry) => entry.forMember?.startsWith("아이")).every((entry) => entry.item.spiceLevel === 0 && !entry.item.tags.includes("kids") && entry.item.dietaryTags.includes("vegan")));
      } },
    ],
  },

  {
    id: "31_ordinal_refines_one_diner",
    requiresGroq: true,
    visit: "dine_in",
    prepare: async (_request, boot) => {
      const first = boot.menu?.find((item) => item.name === "햇살 치킨 덮밥");
      const second = boot.menu?.find((item) => item.name === "든든 소불고기 덮밥");
      assert.ok(first && second);
      const tokenHash = hashes.at(-1)!;
      const session = await db.guestSession.findUniqueOrThrow({ where: { tokenHash } });
      const dialogue: DialogueState = {
        peopleCount: 2,
        members: [
          { id: "generic-1", label: "일행 1", allergies: [], dietaryRules: [] },
          { id: "generic-2", label: "일행 2", allergies: [], dietaryRules: [] },
        ],
        preferences: { action: "recommend", peopleCount: 2, category: "식사" },
        menuLabels: [], lastRecommendations: [{ id: first.id, forMember: "일행 1" }, { id: second.id, forMember: "일행 2" }],
        pendingCheckout: false,
      };
      await db.guestSession.update({ where: { id: session.id }, data: { context: { ...boot.profile, dialogue } } });
    },
    turns: [
      { message: "첫 번째 거 더 맵게 바꿔줘", verify: (reply) => {
        assert.equal(recs(reply).length, 2);
        assert.ok(recs(reply).some((entry) => entry.forMember === "일행 1" && entry.item.spiceLevel >= 2));
        assert.ok(recs(reply).some((entry) => entry.forMember === "일행 2" && entry.item.name === "든든 소불고기 덮밥"));
      } },
    ],
  },


  {
    id: "33_group_meal_course_survives_member_tastes_and_correction",
    requiresGroq: true,
    visit: "dine_in",
    turns: [
      { message: "조별 활동으로 4명이서 식사 할건데 여자 두분에 남자 두명이야 여자 두분은 매운거 잘 못 드시거든. 메뉴 추천해줘", verify: (reply) => {
        assert.equal(reply.provider, "groq");
        assert.equal(reply.dialogue?.peopleCount, 4);
        assert.equal(reply.dialogue?.preferences.category, "식사");
        assert.equal(recs(reply).length, 4);
        assert.ok(recs(reply).every((entry) => entry.item.tags.includes("식사")), "all four diners requested a meal, not drinks or sides");
        assert.ok(recs(reply).every((entry) => !entry.item.tags.includes("kids")), "adult diners did not request kids meals");
        assert.equal(recs(reply).filter((entry) => entry.forMember?.startsWith("여자") && entry.item.spiceLevel === 0).length, 2);
      } },
      { message: "음료나 사이드 말고 식사류로 선택해줘", verify: (reply) => {
        assert.equal(reply.provider, "groq");
        assert.equal(reply.dialogue?.preferences.category, "식사");
        assert.equal(recs(reply).length, 4);
        assert.ok(recs(reply).every((entry) => entry.item.tags.includes("식사")), "the corrected meal request excludes drinks and sides");
        assert.ok(recs(reply).every((entry) => !entry.item.tags.includes("kids")), "adult diners did not request kids meals");
        assert.equal(recs(reply).filter((entry) => entry.forMember?.startsWith("여자") && entry.item.spiceLevel === 0).length, 2);
      } },
    ],
  },
];

const base = process.env.POC09_SMOKE_BASE || "http://127.0.0.1:8000/poc/mwomeokji/api";
const hashes: string[] = [];
const liveGroq = process.argv.includes("--live-groq");
let lastLiveCall = 0;
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
    if (liveGroq && path === "conversation/" && lastLiveCall) {
      const wait = 35000 - (Date.now() - lastLiveCall);
      if (wait > 0) await new Promise((resolve) => setTimeout(resolve, wait));
    }
    if (liveGroq && path === "conversation/") lastLiveCall = Date.now();
    const response = await fetch(base + "/" + path, {
      method,
      signal: AbortSignal.timeout(30000),
      headers: { [liveGroq ? "X-PoC09-Groq-Evaluation" : "X-PoC09-Rules-Evaluation"]: "1", ...(value === undefined ? {} : { "Content-Type": "application/json" }), ...(cookie ? { Cookie: cookie } : {}) },
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
  if (testCase.prepare) await testCase.prepare(request, boot);
  const prior: Reply[] = [];
  for (let index = 0; index < testCase.turns.length; index++) {
    const turn = testCase.turns[index];
    const started = performance.now();
    const reply = turn.path
      ? await request(turn.path, "POST", turn.body)
      : await request("conversation/", "POST", { message: turn.message });
    console.log(JSON.stringify({
      case: testCase.id, turn: index + 1, ms: Math.round(performance.now() - started),
      interpretation: reply.provider || null, modelStatus: reply.modelStatus || null, modelErrorCode: reply.modelErrorCode || null, selection: reply.menuSelectionProvider || null,
      summary: reply.summary || [], ...(liveGroq ? { preferences: reply.dialogue?.preferences, members: reply.dialogue?.members?.map((member) => ({ label: member.label, tastes: member.tastes, menuLabels: member.menuLabels, maxSpiceLevel: member.maxSpiceLevel })) } : {}), menus: recs(reply).map((entry) => ({ name: entry.item.name, forMember: entry.forMember, quantity: entry.quantity })),
      total: total(reply), answer: (reply.reply || "").slice(0, 180),
    }));
    try {
      commonChecks(reply, catalog);
      if (liveGroq && !turn.path && reply.provider === "rules" && /추천|골라|바꿔|말고/.test(turn.message) && !/담아|주문할|응/.test(turn.message))
        throw new Error("Groq interpretation silently fell back to rules");
      turn.verify(reply, prior);
    } catch (error) {
      throw new Error(testCase.id + " turn " + (index + 1) + " failed: " + String(error));
    }
    prior.push(reply);
  }
  console.log(JSON.stringify({ case: testCase.id, status: "PASS", turns: testCase.turns.length }));
}
try {
  const onlyCase = process.argv.find((argument) => argument.startsWith("--case="))?.slice(7);
  const eligible = cases.filter((testCase) => liveGroq || !testCase.requiresGroq);
  const selectedCases = onlyCase ? eligible.filter((testCase) => testCase.id.startsWith(onlyCase)) : process.argv.includes("--first-ten") ? eligible.slice(0, 10) : eligible;
  if (!selectedCases.length) throw new Error(`Unknown evaluation case: ${onlyCase}`);
  for (const testCase of selectedCases) await runCase(testCase);
  console.log(JSON.stringify({ syntheticOnly: true, provider: liveGroq ? "groq" : "rules", passedCases: selectedCases.length, passedTurns: selectedCases.reduce((sum, entry) => sum + entry.turns.length, 0) }));
} finally {
  if (hashes.length) {
    await db.order.deleteMany({ where: { session: { tokenHash: { in: hashes } } } });
    await db.guestSession.deleteMany({ where: { tokenHash: { in: hashes } } });
  }
  await db.$disconnect();
}
