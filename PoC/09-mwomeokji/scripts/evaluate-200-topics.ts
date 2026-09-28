/** 200 independent synthetic HTTP conversations, five turns each. Stops on first failure. */
import assert from "node:assert/strict";
import { createHmac } from "node:crypto";
import { db } from "../lib/db";

type Menu = { id: string; name: string; categoryId: string; tags: string[]; spiceLevel: number; price: number; isAvailable: boolean; isPublished: boolean };
type Pick = { item: Menu; forMember?: string };
type Reply = {
  menu?: Menu[];
  recommendations?: Pick[];
  dialogue?: { peopleCount?: number; preferences?: { totalBudget?: number } };
  profile?: { allergies: string[] };
  summary?: string[];
  reply?: string;
  cart?: { items: Array<{ name: string; quantity: number }>; total: number; canOrder: boolean };
  nextAction?: string;
  provider?: string;
  modelStatus?: number;
  modelErrorCode?: string;
};
type Topic =
  | { kind: "exact"; id: string; first: Menu }
  | { kind: "replace"; id: string; first: Menu; second: Menu }
  | { kind: "group"; id: string; theme: string; count: number };

const base = process.env.POC09_SMOKE_BASE || "http://127.0.0.1:18190/poc/mwomeokji/api";
const hashes: string[] = [];
const liveGroq = process.argv.includes("--live-groq");
let lastModelCall = 0;
let modelTurns = 0;
const secret = process.env.POC09_SESSION_SECRET || "poc09-development-only";
function digest(token: string) { return createHmac("sha256", secret).update(token).digest("hex"); }

async function runTopic(topic: Topic, catalog: Set<string>, ordinal: number) {
  let cookie = "";
  let turns = 0;
  async function request(path: string, method = "GET", value?: unknown): Promise<Reply> {
    const response = await fetch(base + "/" + path, {
      method, signal: AbortSignal.timeout(30000),
      headers: {
        "X-Forwarded-For": `192.0.2.${ordinal + 1}`,
        [liveGroq ? "X-PoC09-Groq-Evaluation" : "X-PoC09-Rules-Evaluation"]: "1",
        ...(value === undefined ? {} : { "Content-Type": "application/json" }),
        ...(cookie ? { Cookie: cookie } : {}),
      },
      body: value === undefined ? undefined : JSON.stringify(value),
    });
    const setCookie = response.headers.get("set-cookie");
    if (setCookie?.startsWith("poc09_guest=")) {
      cookie = setCookie.split(";")[0];
      hashes.push(digest(cookie.slice("poc09_guest=".length)));
    }
    const result = await response.json() as Reply;
    assert.ok(response.ok, topic.id + " HTTP " + response.status + ": " + JSON.stringify(result).slice(0, 350));
    return result;
  }
  function verify(reply: Reply) {
    for (const pick of reply.recommendations || []) {
      assert.ok(catalog.has(pick.item.id), topic.id + " invented a menu");
      assert.equal(pick.item.isAvailable, true);
      assert.equal(pick.item.isPublished, true);
    }
    const budget = reply.dialogue?.preferences?.totalBudget;
    if (budget && reply.recommendations?.length)
      assert.ok(reply.recommendations.reduce((sum, pick) => sum + pick.item.price, 0) <= budget, topic.id + " budget exceeded");
  }
  async function say(message: string): Promise<Reply> {
    const semanticTurn = liveGroq && (topic.kind === "exact" ? turns === 0 : turns < 2);
    if (semanticTurn && lastModelCall) {
      const wait = 35000 - (Date.now() - lastModelCall);
      if (wait > 0) await new Promise((resolve) => setTimeout(resolve, wait));
    }
    if (semanticTurn) lastModelCall = Date.now();
    const reply = await request("conversation/", "POST", { message });
    turns++;
    if (semanticTurn) {
      assert.equal(reply.provider, "groq", `${topic.id} must use Groq for a semantic turn: status=${reply.modelStatus ?? "none"}, code=${reply.modelErrorCode ?? "none"}, answer=${reply.reply ?? ""}`);
      modelTurns++;
    }
    verify(reply);
    return reply;
  }
  await request("bootstrap/?slug=orange-table");
  assert.ok(cookie, "fresh cookie required");
  await request("visit/", "POST", { mode: ordinal % 2 ? "takeout" : "dine_in" });
  try {
    if (topic.kind === "exact") {
      const one = await say(`${topic.first.name} 하나 추천해줘`);
      assert.equal(one.recommendations?.[0]?.item.name, topic.first.name, topic.id + " exact menu");
      const two = await say("첫 번째 메뉴에 땅콩이 들어가?");
      assert.ok(two.reply?.includes(topic.first.name), topic.id + " ingredient target");
      const three = await say("첫 번째 담아줘");
      assert.ok(three.cart?.items.some((item) => item.name === topic.first.name), topic.id + " cart target");
      const four = await say("주문할게");
      assert.equal(four.nextAction, "confirm_checkout", topic.id + " checkout gate");
      const five = await say("응");
      assert.equal(five.nextAction, "checkout", topic.id + " final confirmation");
    } else if (topic.kind === "replace") {
      const one = await say(`${topic.first.name} 하나 추천해줘`);
      assert.equal(one.recommendations?.[0]?.item.name, topic.first.name, topic.id + " first menu");
      const two = await say(`${topic.first.name} 말고 ${topic.second.name} 하나 추천해줘`);
      assert.equal(two.recommendations?.[0]?.item.name, topic.second.name, topic.id + " replacement target");
      const three = await say("그걸 담아줘");
      assert.ok(three.cart?.items.some((item) => item.name === topic.second.name), topic.id + " replacement cart");
      const four = await say("주문할게");
      assert.equal(four.nextAction, "confirm_checkout", topic.id + " checkout gate");
      const five = await say("응");
      assert.equal(five.nextAction, "checkout", topic.id + " final confirmation");
    } else {
      const one = await say(`우리 ${topic.count}명이 ${topic.theme} 메뉴를 먹고 싶어. 추천해줘`);
      assert.equal(one.dialogue?.peopleCount, topic.count, topic.id + " party count");
      assert.equal(one.recommendations?.length, topic.count, topic.id + " group assignment");
      const matchesTheme = (pick: Pick) => topic.theme === "매콤" ? pick.item.spiceLevel >= 2 : pick.item.tags.includes(topic.theme);
      if (!one.recommendations.every(matchesTheme))
        console.error(JSON.stringify({ topic: topic.id, actualMenus: one.recommendations.map((pick) => ({ name: pick.item.name, tags: pick.item.tags, spiceLevel: pick.item.spiceLevel })), dialogue: one.dialogue, reply: one.reply }));
      assert.ok(one.recommendations.every(matchesTheme), topic.id + " theme");
      const two = await say("겹치지 않게 다시 추천해줘");
      assert.equal(two.recommendations?.length, topic.count, topic.id + " distinct group assignment");
      assert.equal(new Set(two.recommendations.map((pick) => pick.item.id)).size, topic.count, topic.id + " duplicates");
      const three = await say("추천한 거 전부 담아줘");
      assert.equal(three.cart?.items.length, topic.count, topic.id + " group cart");
      const four = await say("주문할게");
      assert.equal(four.nextAction, "confirm_checkout", topic.id + " checkout gate");
      const five = await say("응");
      assert.equal(five.nextAction, "checkout", topic.id + " final confirmation");
    }
    assert.equal(turns, 5);
    console.log(JSON.stringify({ run: process.argv.find((arg) => arg.startsWith("--run="))?.slice(6) || "1", topic: topic.id, turns, status: "PASS" }));
  } catch (error) {
    console.error(JSON.stringify({ topic: topic.id, turns, status: "FAIL", error: String(error) }));
    throw error;
  }
}

try {
  const menu = await db.menuItem.findMany({ where: { isAvailable: true, isPublished: true }, select: { id: true, name: true, categoryId: true, tags: true, spiceLevel: true, price: true, isAvailable: true, isPublished: true }, orderBy: { name: "asc" } });
  assert.equal(menu.length, 84, "the 200-topic suite uses the complete 84-item virtual catalog");
  const catalog = new Set(menu.map((item) => item.id));
  const byCategory = new Map<string, Menu[]>();
  for (const item of menu) byCategory.set(item.categoryId, [...(byCategory.get(item.categoryId) || []), item]);
  const themes = ["브런치", "든든", "데이트", "직장동료", "가벼운", "해산물", "빵", "매콤"];
  const topics: Topic[] = [
    ...menu.map((first, index): Topic => ({ kind: "exact", id: `exact_${String(index + 1).padStart(2, "0")}_${first.name}`, first })),
    ...menu.map((first, index): Topic => {
      const sameCourse = byCategory.get(first.categoryId)!;
      const second = sameCourse[(sameCourse.indexOf(first) + 1) % sameCourse.length];
      assert.notEqual(first.id, second.id);
      return { kind: "replace", id: `replace_${String(index + 1).padStart(2, "0")}_${first.name}_to_${second.name}`, first, second };
    }),
    ...themes.flatMap((theme) => [2, 3, 4, 5].map((count): Topic => ({ kind: "group", id: `group_${theme}_${count}`, theme, count }))),
  ];
  assert.equal(topics.length, 200);
  assert.equal(new Set(topics.map((topic) => topic.id)).size, 200);
  const groupOnly = process.argv.includes("--group-only");
  const startAt = Number(process.argv.find((arg) => arg.startsWith("--topic-start="))?.split("=")[1] || 0);
  const limit = Number(process.argv.find((arg) => arg.startsWith("--topic-count="))?.split("=")[1] || 200);
  assert.ok(Number.isInteger(startAt) && startAt >= 0 && Number.isInteger(limit) && limit > 0, "valid topic range required");
  const indexed = topics.map((topic, index) => ({ topic, index })).filter(({ topic }) => !groupOnly || topic.kind === "group");
  const selected = indexed.slice(startAt, startAt + limit);
  assert.ok(selected.length, "no topics in the selected range");
  const start = Date.now();
  for (const { topic, index } of selected) await runTopic(topic, catalog, index);
  console.log(JSON.stringify({ run: process.argv.find((arg) => arg.startsWith("--run="))?.slice(6) || "1", provider: liveGroq ? "groq" : "rules", topics: selected.length, turns: selected.length * 5, modelTurns, groupOnly, topicStart: startAt, ms: Date.now() - start, status: "PASS" }));
} finally {
  if (hashes.length) {
    await db.order.deleteMany({ where: { session: { tokenHash: { in: hashes } } } });
    await db.guestSession.deleteMany({ where: { tokenHash: { in: hashes } } });
  }
  await db.$disconnect();
}
