import assert from "node:assert/strict";
import { randomUUID } from "node:crypto";
import { db } from "../lib/db";
import { ALLERGENS } from "../lib/types";

const base =
  process.env.POC09_SMOKE_BASE || "http://127.0.0.1:8000/poc/mwomeokji/api";
let guestCookie = "";
let merchantCookie = "";
let orderId = "";
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
  const profile = {
    allergies: ["peanut"],
    dietaryRules: [],
    spicePreference: 0,
    maxSpiceLevel: 0,
  };
  await request("profile/", "POST", profile);
  const conversation = await request("conversation/", "POST", {
    message: "안 맵고 따뜻한 거 만원 정도로 추천해줘",
    members: [],
  });
  assert.ok(conversation.recommendations.length > 0);
  assert.ok(
    conversation.recommendations.every(
      (entry: { item: { name: string } }) =>
        entry.item.name !== "고소 땅콩 치킨",
    ),
  );
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
  const duplicate = await request("checkout/", "POST", {
    idempotencyKey: key,
    paymentMethod: "mock_card",
  });
  assert.equal(duplicate.id, order.id);
  const email = process.env.POC09_MERCHANT_EMAIL;
  const password = process.env.POC09_MERCHANT_PASSWORD;
  assert.ok(email && password, "Set PoC9 merchant credentials in root .env");
  await request("merchant/login/", "POST", { email, password }, true);
  const dashboard = await request(
    "merchant/dashboard/",
    "GET",
    undefined,
    true,
  );
  assert.ok(
    dashboard.orders.some((entry: { id: string }) => entry.id === order.id),
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
    "PoC9 smoke passed: bootstrap, preferences, recommendation, options, cart, idempotent order, merchant, help, import review.",
  );
} finally {
  if (orderId) await db.order.deleteMany({ where: { id: orderId } });
  if (helpId) await db.helpRequest.deleteMany({ where: { id: helpId } });
  if (draftId) await db.menuItem.deleteMany({ where: { id: draftId } });
  await db.$disconnect();
}
