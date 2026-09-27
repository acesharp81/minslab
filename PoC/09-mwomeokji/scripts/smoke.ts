import assert from "node:assert/strict";
import { randomUUID } from "node:crypto";
import { db } from "../lib/db";
import { ALLERGENS } from "../lib/types";

const base =
  process.env.POC09_SMOKE_BASE || "http://127.0.0.1:8000/poc/mwomeokji/api";
let guestCookie = "";
let merchantCookie = "";
let orderId = "";
let groupOrderId = "";
let helpId = "";
let draftId = "";

async function request(
  path: string,
  method = "GET",
  value?: unknown,
  merchant = false,
) {
  const response = await fetch(`${base}/${path}`, {
    method,
    redirect: "manual",
    headers: {
      ...(value === undefined || value instanceof FormData
        ? {}
        : { "Content-Type": "application/json" }),
      ...(merchant
        ? merchantCookie
          ? { Cookie: merchantCookie }
          : {}
        : guestCookie
          ? { Cookie: guestCookie }
          : {}),
    },
    body:
      value instanceof FormData
        ? value
        : value === undefined
          ? undefined
          : JSON.stringify(value),
  });
  if (response.status >= 400)
    throw new Error(`${path}: ${response.status} ${await response.text()}`);
  const cookie = response.headers.get("set-cookie");
  if (cookie?.startsWith("poc09_guest=")) guestCookie = cookie.split(";")[0];
  if (cookie?.startsWith("poc09_merchant="))
    merchantCookie = cookie.split(";")[0];
  return response.json();
}

try {
  const bootstrap = await request("bootstrap/?slug=orange-table&table=A1");
  assert.equal(bootstrap.table.code, "A1");
  assert.ok(bootstrap.menu.length >= 18);
  const visit = await request("visit/", "POST", { mode: "takeout" });
  assert.equal(visit.visitMode, "takeout");
  const profile = {
    allergies: ["peanut"],
    dietaryRules: [],
    spicePreference: 0,
    maxSpiceLevel: 0,
  };
  await request("profile/", "POST", profile);
  const group = await request("conversation/", "POST", {
    message: "우리 3명인데 한 명은 채식하고 한 명은 매운 걸 못 먹어",
  });
  assert.equal(group.dialogue.peopleCount, 3);
  assert.ok(group.dialogue.members.some((member: { dietaryRules: { type: string }[] }) => member.dietaryRules.some((rule) => rule.type === "vegetarian")));
  assert.ok(group.dialogue.members.some((member: { maxSpiceLevel?: number }) => member.maxSpiceLevel === 0));
  const conversation = await request("conversation/", "POST", {
    message: "안 맵고 따뜻한 거 4만원 안에서 추천해줘",
  });
  assert.ok(conversation.recommendations.length > 0);
  assert.ok(
    conversation.recommendations.every(
      (entry: { item: { name: string } }) =>
        entry.item.name !== "고소 땅콩 치킨",
    ),
  );
  const spokenCart = await request("conversation/", "POST", { message: "추천한 거 전부 담아줘" });
  assert.equal(spokenCart.cart?.items.length, conversation.recommendations.length, spokenCart.reply);
  const confirm = await request("conversation/", "POST", { message: "주문할게" });
  assert.equal(confirm.nextAction, "confirm_checkout");
  await request(`cart/${confirm.cart.items[0].id}/`, "PATCH", { quantity: 2 });
  const changed = await request("conversation/", "POST", { message: "응" });
  assert.equal(changed.nextAction, "confirm_checkout");
  assert.match(changed.reply, /장바구니가 바뀌었어요/);
  const affirmative = await request("conversation/", "POST", { message: "응" });
  assert.equal(affirmative.nextAction, "checkout");
  const groupOrder = await request("checkout/", "POST", { idempotencyKey: `smoke-group-${randomUUID()}`, paymentMethod: "mock_card", note: "대화형 그룹 주문 자동 테스트" });
  groupOrderId = groupOrder.id;
  assert.equal(groupOrder.lines.length, conversation.recommendations.length);
  assert.equal(groupOrder.fulfillmentType, "takeout");
  guestCookie = "";
  await request("bootstrap/?slug=orange-table&table=A1");
  await request("visit/", "POST", { mode: "takeout" });
  const caffeineRequest = await request("conversation/", "POST", { message: "무카페인 커피 음료 두 잔을 1만 원 안에서 추천해줘" });
  assert.equal(caffeineRequest.dialogue.peopleCount, undefined, "cups must not become diners");
  assert.equal(caffeineRequest.recommendations?.length, 0, "unverified coffee cannot be replaced by other food");
  assert.match(caffeineRequest.reply, /카페인 없는 커피/);
  const broadenedDrink = await request("conversation/", "POST", { message: "그럼 무카페인 음료 두 잔을 1만 원 안에서 추천해줘" });
  assert.equal(broadenedDrink.dialogue.peopleCount, undefined);
  assert.equal(broadenedDrink.dialogue.preferences.coffee, false);
  assert.equal(broadenedDrink.recommendations?.length, 1);
  assert.equal(broadenedDrink.recommendations[0].item.name, "오렌지 에이드");
  assert.equal(broadenedDrink.recommendations[0].quantity, 2);
  assert.match(broadenedDrink.reply, /9,000원/);
  assert.match(broadenedDrink.reply, /2잔을 담을게요/);
  const twoDrinks = await request("conversation/", "POST", { message: "첫 번째 담아줘" });
  assert.equal(twoDrinks.cart?.items.length, 1);
  assert.equal(twoDrinks.cart?.items[0].quantity, 2);
  assert.equal(twoDrinks.cart?.total, 9000);
  await request(`cart/${twoDrinks.cart.items[0].id}/`, "DELETE");
  const sweetDrink = await request("conversation/", "POST", { message: "새콤한 건 빼고 달콤한 음료로 골라줘" });
  assert.equal(sweetDrink.dialogue.preferences.caffeineFree, true);
  assert.equal(sweetDrink.dialogue.preferences.quantity, 2);
  assert.equal(sweetDrink.recommendations?.length, 1);
  assert.equal(sweetDrink.recommendations[0].item.name, "달콤 사과 주스");
  assert.match(sweetDrink.recommendations[0].reason, /달콤한 맛/);
  assert.match(sweetDrink.reply, /9,000원/);
  const sweetCart = await request("conversation/", "POST", { message: "첫 번째 담아줘" });
  assert.equal(sweetCart.cart?.items[0].quantity, 2);
  assert.equal(sweetCart.cart?.total, 9000);
  await request(`cart/${sweetCart.cart.items[0].id}/`, "DELETE");
  await request("profile/", "POST", profile);
  const peanut = bootstrap.menu.find(
    (item: { name: string }) => item.name === "고소 땅콩 치킨",
  );
  const blocked = await fetch(`${base}/cart/`, {
    method: "POST",
    headers: { Cookie: guestCookie, "Content-Type": "application/json" },
    body: JSON.stringify({
      menuItemId: peanut.id,
      quantity: 1,
      selectedOptionIds: [],
    }),
  });
  assert.equal(blocked.status, 400);
  const menu = bootstrap.menu.find(
    (item: { name: string }) => item.name === "햇살 치킨 덮밥",
  );
  const optionId = menu.options[0].options[0].id;
  const cart = await request("cart/", "POST", {
    menuItemId: menu.id,
    quantity: 2,
    selectedOptionIds: [optionId],
  });
  assert.equal(cart.total, 21800);
  assert.equal(cart.canOrder, true);
  const key = `smoke-${randomUUID()}`;
  const order = await request("checkout/", "POST", {
    idempotencyKey: key,
    paymentMethod: "mock_card",
    note: "자동 내부 테스트",
  });
  orderId = order.id;
  assert.equal(order.total, 21800);
  assert.equal(order.fulfillmentType, "takeout");
  const duplicate = await request("checkout/", "POST", {
    idempotencyKey: key,
    paymentMethod: "mock_card",
  });
  assert.equal(duplicate.id, order.id);
  await request("merchant/login/", "POST", { email: "demo@mmj.local", password: "demo1234" }, true);
  const dashboard = await request(
    "merchant/dashboard/",
    "GET",
    undefined,
    true,
  );
  assert.ok(
    dashboard.orders.some((entry: { id: string; fulfillmentType: string }) => entry.id === order.id && entry.fulfillmentType === "takeout"),
  );
  const accepted = await request(
    `merchant/orders/${order.id}/`,
    "PATCH",
    { status: "accepted" },
    true,
  );
  assert.equal(accepted.status, "accepted");
  const help = await request("help/", "POST", { note: "물 한 잔 부탁드려요" });
  helpId = help.id;
  await request(
    `merchant/help/${help.id}/`,
    "PATCH",
    { status: "resolved" },
    true,
  );
  const form = new FormData();
  form.set("categoryId", bootstrap.categories[0].id);
  form.set(
    "text",
    `자동 테스트 ${randomUUID().slice(0, 6)} | 5500 | 가져오기 검증`,
  );
  const imported = await request("merchant/import/", "POST", form, true);
  draftId = imported.created[0].id;
  assert.equal(imported.created[0].isPublished, false);
  const premature = await fetch(`${base}/merchant/menu/${draftId}/`, {
    method: "PATCH",
    headers: { Cookie: merchantCookie, "Content-Type": "application/json" },
    body: JSON.stringify({ isPublished: true }),
  });
  assert.equal(premature.status, 400);
  await request(
    `merchant/menu/${draftId}/`,
    "PATCH",
    {
      ingredients: ["테스트 재료"],
      allergens: ALLERGENS.map(([allergenKey]) => ({
        allergenKey,
        relation: "excludes",
        verificationStatus: "merchant_verified",
      })),
      isPublished: true,
    },
    true,
  );
  await request(
    `merchant/menu/${draftId}/options/`,
    "POST",
    {
      name: "기본 선택",
      minSelect: 1,
      maxSelect: 1,
      options: [
        {
          name: "보통",
          priceDelta: 0,
          isAvailable: true,
          ingredients: ["테스트 재료"],
          dietaryTags: [],
          allergens: ALLERGENS.map(([allergenKey]) => ({
            allergenKey,
            relation: "excludes",
            verificationStatus: "merchant_verified",
          })),
        },
      ],
    },
    true,
  );
  const visible = await request("bootstrap/?slug=orange-table&table=A1");
  assert.ok(
    visible.menu.some(
      (item: { id: string; options: unknown[] }) =>
        item.id === draftId && item.options.length === 1,
    ),
  );
  console.log(
    "PoC9 smoke passed: visit mode, spoken group, caffeine-free coffee guard, broadened two-drink order, sour-to-sweet refinement, follow-up add, safety, options, takeout order, demo merchant, help, import review.",
  );
} finally {
  if (orderId) await db.order.deleteMany({ where: { id: orderId } });
  if (groupOrderId) await db.order.deleteMany({ where: { id: groupOrderId } });
  if (helpId) await db.helpRequest.deleteMany({ where: { id: helpId } });
  if (draftId) await db.menuItem.deleteMany({ where: { id: draftId } });
  await db.$disconnect();
}
