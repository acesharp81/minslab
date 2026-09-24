import { NextRequest, NextResponse } from "next/server";
import { z } from "zod";
import { db, menuInclude } from "../../../lib/db";
import {
  currentGuest,
  currentMerchant,
  guest,
  merchantLogin,
  merchantLogout,
} from "../../../lib/auth";
import { cartSummary } from "../../../lib/cart";
import { understand } from "../../../lib/ai";
import { rankRecommendations } from "../../../lib/decision";
import { recommend, recommendGroup } from "../../../lib/recommend";
import { checkSafety } from "../../../lib/safety";
import { applyExplicitCorrections, applyFocusedTaste, applyMemberUpdates, contextSummary, evolveDialogue, readDialogue, type DialogueState, type VisitMode } from "../../../lib/dialogue";
import {
  ALLERGENS,
  emptyProfile,
  type PreferenceProfile,
} from "../../../lib/types";

export const runtime = "nodejs";
type Context = { params: Promise<{ path: string[] }> };
class ApiError extends Error {
  constructor(
    message: string,
    public status = 400,
  ) {
    super(message);
  }
}
const loginAttempts = new Map<string, { count: number; until: number }>();
const conversationWindows = new Map<string, { count: number; until: number }>();
function rateLimited(key: string, limit: number) {
  const now = Date.now();
  const previous = conversationWindows.get(key);
  const current = previous && previous.until > now ? previous : { count: 0, until: now + 60000 };
  current.count += 1;
  conversationWindows.set(key, current);
  if (conversationWindows.size > 3000) conversationWindows.clear();
  return current.count > limit;
}
const json = (data: unknown, status = 200) =>
  NextResponse.json(data, { status });
const fail = (message: string, status = 400) =>
  json({ error: message }, status);
const profileSchema = z.object({
  allergies: z
    .array(z.enum(ALLERGENS.map(([key]) => key) as [string, ...string[]]))
    .max(10),
  dietaryRules: z
    .array(
      z.object({
        type: z.string().max(40),
        mode: z.enum(["strict", "prefer"]),
      }),
    )
    .max(12),
  spicePreference: z.number().int().min(0).max(4),
  maxSpiceLevel: z.number().int().min(0).max(4).optional(),
  budget: z.number().int().min(0).max(1000000).optional(),
  largeText: z.boolean().optional(),
  locale: z.enum(["ko", "en"]).optional(),
});
const cartSchema = z.object({
  menuItemId: z.string(),
  quantity: z.number().int().min(1).max(30),
  selectedOptionIds: z.array(z.string()).max(12).default([]),
  assignedTo: z.string().max(40).optional(),
});
const optionGroupSchema = z
  .object({
    name: z.string().trim().min(1).max(60),
    minSelect: z.number().int().min(0).max(5),
    maxSelect: z.number().int().min(1).max(5),
    options: z
      .array(
        z.object({
          name: z.string().trim().min(1).max(60),
          priceDelta: z.number().int().min(0).max(100000),
          isAvailable: z.boolean().default(true),
          ingredients: z.array(z.string().max(50)).max(30).default([]),
          dietaryTags: z.array(z.string().max(40)).max(15).default([]),
          allergens: z
            .array(
              z.object({
                allergenKey: z.string(),
                relation: z.enum(["contains", "excludes", "unknown"]),
                verificationStatus: z.enum(["merchant_verified", "unknown"]),
              }),
            )
            .max(10)
            .default([]),
        }),
      )
      .min(1)
      .max(5),
  })
  .refine(
    (value) =>
      value.minSelect <= value.maxSelect &&
      value.maxSelect <= value.options.length,
    "옵션 선택 개수를 확인해 주세요.",
  );
const menuSchema = z.object({
  name: z.string().trim().min(1).max(80),
  description: z.string().max(400).default(""),
  categoryId: z.string(),
  price: z.number().int().min(0).max(1000000),
  emoji: z.string().max(8).default("🍽️"),
  spiceLevel: z.number().int().min(0).max(4).default(0),
  isAvailable: z.boolean().default(true),
  isPublished: z.boolean().default(false),
  isShareable: z.boolean().default(false),
  tags: z.array(z.string().max(30)).max(15).default([]),
  ingredients: z.array(z.string().max(50)).max(50).default([]),
  dietaryTags: z.array(z.string().max(40)).max(15).default([]),
  allergens: z
    .array(
      z.object({
        allergenKey: z.string(),
        relation: z.enum(["contains", "excludes", "unknown"]),
        verificationStatus: z.enum(["merchant_verified", "unknown"]),
      }),
    )
    .max(10)
    .default([]),
});

function sameOrigin(req: NextRequest) {
  const origin = req.headers.get("origin");
  if (!origin) return true;
  try {
    return (
      new URL(origin).host ===
      (req.headers.get("x-forwarded-host") || req.headers.get("host"))
    );
  } catch {
    return false;
  }
}
async function body(req: NextRequest) {
  return req.json().catch(() => ({}));
}
function profile(context: unknown): PreferenceProfile {
  const parsed = profileSchema.safeParse(context);
  return parsed.success ? parsed.data : emptyProfile;
}
function normalizedMenuName(value: string) {
  return value.toLowerCase().replace(/\s+/g, "");
}
function menuMatches(actual: string, spoken: string) {
  const name = normalizedMenuName(actual);
  const phrase = normalizedMenuName(spoken);
  return !!phrase && (name.includes(phrase) || phrase.includes(name));
}
function segments(context: Context) {
  return context.params.then(({ path }) => path);
}
function errorResponse(error: unknown) {
  if (error instanceof ApiError) return fail(error.message, error.status);
  if (error instanceof z.ZodError)
    return fail(error.issues.map((item) => item.message).join(", "));
  console.error("poc09 api error", error);
  return fail("요청을 처리하지 못했어요. 잠시 후 다시 시도해 주세요.", 500);
}

export async function GET(req: NextRequest, context: Context) {
  try {
    const path = await segments(context);
    if (path[0] === "health") {
      await db.$queryRaw`SELECT 1`;
      return json({ ok: true });
    }
    if (path[0] === "bootstrap") {
      const slug = req.nextUrl.searchParams.get("slug") || "orange-table";
      const store = await db.store.findUnique({
        where: { slug },
        include: {
          categories: { orderBy: { sortOrder: "asc" } },
          tables: true,
        },
      });
      if (!store || !store.isActive) return fail("매장을 찾을 수 없어요.", 404);
      const tableCode = req.nextUrl.searchParams.get("table");
      const table = store.tables.find((entry) => entry.code === tableCode);
      const session = await guest(store.id, table?.id);
      const menu = await db.menuItem.findMany({
        where: { storeId: store.id, isPublished: true },
        include: menuInclude,
        orderBy: [{ popularity: "desc" }, { name: "asc" }],
      });
      return json({
        store: {
          id: store.id,
          slug: store.slug,
          name: store.name,
          description: store.description,
        },
        categories: store.categories,
        tables: store.tables.map(({ id, code, label }) => ({
          id,
          code,
          label,
        })),
        table: table ? { code: table.code, label: table.label } : null,
        menu,
        profile: profile(session.context),
        visitMode: session.fulfillmentType,
        dialogue: readDialogue(session.context),
        cart: await cartSummary(session.id, profile(session.context)),
      });
    }
    if (path[0] === "cart") {
      const session = await currentGuest();
      return session
        ? json(await cartSummary(session.id, profile(session.context)))
        : fail("주문 세션이 없어요.", 401);
    }
    if (path[0] === "orders") {
      const session = await currentGuest();
      if (!session) return fail("주문 세션이 없어요.", 401);
      return json(
        await db.order.findMany({
          where: { sessionId: session.id },
          include: { lines: true },
          orderBy: { createdAt: "desc" },
        }),
      );
    }
    if (path[0] === "merchant" && path[1] === "dashboard") {
      if (!(await currentMerchant()))
        return fail("사장님 로그인이 필요해요.", 401);
      const store = await db.store.findUnique({
        where: { slug: "orange-table" },
        include: { categories: true, tables: true },
      });
      const [menu, orders, helpRequests] = await Promise.all([
        db.menuItem.findMany({
          where: { storeId: store!.id },
          include: menuInclude,
          orderBy: { updatedAt: "desc" },
        }),
        db.order.findMany({
          where: { storeId: store!.id },
          include: { lines: true, table: true },
          orderBy: { createdAt: "desc" },
          take: 80,
        }),
        db.helpRequest.findMany({
          where: { storeId: store!.id },
          include: { table: true, session: { select: { fulfillmentType: true } } },
          orderBy: { createdAt: "desc" },
          take: 50,
        }),
      ]);
      return json({ store, menu, orders, helpRequests });
    }
    return fail("찾을 수 없는 주소예요.", 404);
  } catch (error) {
    return errorResponse(error);
  }
}

export async function POST(req: NextRequest, context: Context) {
  try {
    if (!sameOrigin(req)) return fail("요청 출처를 확인해 주세요.", 403);
    const path = await segments(context);
    if (path[0] === "merchant" && path[1] === "login") {
      const input = z
        .object({ email: z.string().email(), password: z.string().min(1) })
        .parse(await body(req));
      const client = req.headers.get("x-forwarded-for") || "local";
      const attempts = loginAttempts.get(client);
      if (attempts && attempts.count >= 5 && attempts.until > Date.now())
        return fail("로그인 시도가 많아요. 10분 뒤 다시 시도해 주세요.", 429);
      if (await merchantLogin(input.email, input.password)) {
        loginAttempts.delete(client);
        return json({ ok: true });
      }
      loginAttempts.set(client, {
        count:
          (attempts?.until && attempts.until > Date.now()
            ? attempts.count
            : 0) + 1,
        until: Date.now() + 600000,
      });
      if (loginAttempts.size > 1000) loginAttempts.clear();
      return fail("이메일 또는 비밀번호를 확인해 주세요.", 401);
    }
    if (path[0] === "merchant" && path[1] === "logout") {
      await merchantLogout();
      return json({ ok: true });
    }
    if (path[0] === "merchant") {
      if (!(await currentMerchant()))
        return fail("사장님 로그인이 필요해요.", 401);
      if (path[1] === "menu" && !path[2]) {
        const input = menuSchema.parse(await body(req));
        const store = await db.store.findUniqueOrThrow({
          where: { slug: "orange-table" },
        });
        const category = await db.menuCategory.findFirst({
          where: { id: input.categoryId, storeId: store.id },
        });
        if (!category) return fail("올바른 카테고리를 골라 주세요.");
        if (
          input.isPublished &&
          (input.ingredients.length === 0 ||
            input.allergens.length !== ALLERGENS.length ||
            input.allergens.some(
              (entry) => entry.verificationStatus !== "merchant_verified",
            ))
        )
          return fail("공개 전 재료와 모든 알레르기 항목을 확인해 주세요.");
        const item = await db.menuItem.create({
          data: {
            ...input,
            storeId: store.id,
            allergens: {
              create: input.allergens.map((entry) => ({
                ...entry,
                verifiedAt:
                  entry.verificationStatus === "merchant_verified"
                    ? new Date()
                    : null,
              })),
            },
          },
          include: menuInclude,
        });
        return json(item, 201);
      }
      if (path[1] === "menu" && path[2] && path[3] === "options") {
        const input = optionGroupSchema.parse(await body(req));
        const item = await db.menuItem.findUnique({ where: { id: path[2] } });
        if (!item) return fail("메뉴가 없어요.", 404);
        const group = await db.menuOptionGroup.create({
          data: {
            menuItemId: item.id,
            name: input.name,
            minSelect: input.minSelect,
            maxSelect: input.maxSelect,
            options: {
              create: input.options.map((option) => ({
                ...option,
                allergens: {
                  create: option.allergens.length
                    ? option.allergens
                    : ALLERGENS.map(([allergenKey]) => ({
                        allergenKey,
                        relation: "unknown",
                        verificationStatus: "unknown",
                      })),
                },
              })),
            },
          },
          include: { options: { include: { allergens: true } } },
        });
        return json(group, 201);
      }
      if (path[1] === "import") {
        const form = await req.formData();
        const file = form.get("file");
        const text = String(form.get("text") || "").slice(0, 10000);
        const categoryId = String(form.get("categoryId") || "");
        const store = await db.store.findUniqueOrThrow({
          where: { slug: "orange-table" },
        });
        if (
          !(await db.menuCategory.findFirst({
            where: { id: categoryId, storeId: store.id },
          }))
        )
          return fail("카테고리를 선택해 주세요.");
        let extracted = text;
        if (
          file instanceof File &&
          file.size > 0 &&
          file.size <= 5_000_000 &&
          process.env.POC09_AI_PROVIDER === "openrouter" &&
          process.env.OPENROUTER_API_KEY
        ) {
          const bytes = Buffer.from(await file.arrayBuffer());
          const mime = ["image/jpeg", "image/png", "image/webp"].includes(
            file.type,
          )
            ? file.type
            : null;
          if (!mime) return fail("JPG, PNG 또는 WEBP 이미지를 올려 주세요.");
          const response = await fetch(
            "https://openrouter.ai/api/v1/chat/completions",
            {
              method: "POST",
              signal: AbortSignal.timeout(15000),
              headers: {
                Authorization: `Bearer ${process.env.OPENROUTER_API_KEY}`,
                "Content-Type": "application/json",
              },
              body: JSON.stringify({
                model: process.env.POC09_VISION_MODEL || "openai/gpt-4o-mini",
                messages: [
                  {
                    role: "user",
                    content: [
                      {
                        type: "text",
                        text: "Read this restaurant menu image. Return one menu per line as name | price KRW | description. Never infer allergens or ingredients.",
                      },
                      {
                        type: "image_url",
                        image_url: {
                          url: `data:${mime};base64,${bytes.toString("base64")}`,
                        },
                      },
                    ],
                  },
                ],
              }),
            },
          );
          if (response.ok) {
            const result = await response.json();
            extracted = result.choices?.[0]?.message?.content || "";
          }
        }
        if (!extracted.trim())
          return fail(
            "메뉴 텍스트를 입력하거나 AI 설정 후 메뉴판 이미지를 올려 주세요.",
          );
        const drafts = extracted
          .split("\n")
          .slice(0, 40)
          .map((line) => {
            const parts = line.split(/[|,\t]/).map((value) => value.trim());
            const price = Number((parts[1] || "").replace(/[^0-9]/g, ""));
            return {
              name: parts[0]?.slice(0, 80),
              price,
              description: (parts[2] || "").slice(0, 400),
            };
          })
          .filter(
            (item) => item.name && item.price > 0 && item.price <= 1000000,
          );
        if (!drafts.length)
          return fail(
            "메뉴를 읽지 못했어요. “메뉴명 | 가격 | 설명” 형식으로 입력해 주세요.",
          );
        const created = [];
        for (const draft of drafts)
          created.push(
            await db.menuItem.create({
              data: {
                storeId: store.id,
                categoryId,
                ...draft,
                isPublished: false,
                allergens: {
                  create: ALLERGENS.map(([allergenKey]) => ({
                    allergenKey,
                    relation: "unknown",
                    verificationStatus: "unknown",
                  })),
                },
              },
            }),
          );
        return json(
          {
            created,
            note: "초안으로 저장했습니다. 재료와 알레르기 정보를 점주가 확인한 후 공개하세요.",
          },
          201,
        );
      }
      return fail("찾을 수 없는 기능이에요.", 404);
    }
    const session = await currentGuest();
    if (!session) return fail("매장 화면을 새로고침해 주세요.", 401);
    if (path[0] === "profile") {
      const nextProfile = profileSchema.parse(await body(req));
      await db.guestSession.update({
        where: { id: session.id },
        data: {
          context: { ...nextProfile, dialogue: readDialogue(session.context) },
        },
      });
      return json({
        profile: nextProfile,
        cart: await cartSummary(session.id, nextProfile),
      });
    }
    if (path[0] === "visit") {
      const { mode } = z.object({ mode: z.enum(["dine_in", "takeout"]) }).parse(await body(req));
      await db.guestSession.update({
        where: { id: session.id },
        data: { fulfillmentType: mode, tableId: mode === "takeout" ? null : session.tableId },
      });
      return json({
        visitMode: mode,
        reply: mode === "dine_in"
          ? "매장에서 드시는군요! 몇 분이세요? 먹고 싶은 음식이나 피해야 할 재료도 편하게 말씀해 주세요."
          : "가져가시는군요! 몇 분이 드실 음식인가요? 취향과 피해야 할 재료도 편하게 말씀해 주세요.",
      });
    }
    if (path[0] === "conversation") {
      if (!session.fulfillmentType) return fail("먼저 먹고 가기 또는 가져가기를 골라 주세요.");
      const { message } = z.object({ message: z.string().trim().min(1).max(500) }).parse(await body(req));
      const clientIp = (req.headers.get("x-forwarded-for") || "local").split(",")[0].trim();
      if (rateLimited(`session:${session.id}`, 30) || rateLimited(`ip:${clientIp}`, 200)) return fail("잠시 뒤 다시 말씀해 주세요.", 429);
      let previous = readDialogue(session.context);
      const affirmative = /^(응|네|예|좋아|맞아|확인|주문해|결제해|진행해|그래)(요|줘|주세요|할게요?)?[.! ]*$/.test(message.trim());
      if (previous.pendingCheckout && affirmative) {
        const currentCart = await cartSummary(session.id, profile(session.context));
        const signature = JSON.stringify(currentCart.items.map((item) => [item.id, item.quantity, item.lineTotal, item.selectedOptionIds, item.assignedTo]));
        if (currentCart.canOrder && signature === previous.pendingCheckoutSignature)
          return json({ reply: "주문을 접수할게요.", nextAction: "checkout", dialogue: previous });
        const changed = { ...previous, pendingCheckout: currentCart.canOrder, pendingCheckoutSignature: currentCart.canOrder ? signature : undefined };
        await db.guestSession.update({ where: { id: session.id }, data: { context: { ...profile(session.context), dialogue: changed } } });
        return json({ dialogue: changed, cart: currentCart, nextAction: currentCart.canOrder ? "confirm_checkout" : undefined, reply: currentCart.canOrder ? `장바구니가 바뀌었어요. 새 합계는 ${currentCart.total.toLocaleString()}원이에요. 이대로 주문할까요?` : "장바구니를 다시 확인해 주세요." });
      }
      const understanding = await understand(message);
      const freshSession = await db.guestSession.findUniqueOrThrow({ where: { id: session.id } });
      previous = readDialogue(freshSession.context);
      const { intent, provider } = understanding;
      if (/^(?:이걸로|그걸로|이거|그거)(?:\s*(?:할게|줘|주세요))?$/.test(message.trim())) intent.action = "add";
      const evolved = evolveDialogue(previous, message, intent);
      const updatedMembers = applyMemberUpdates(evolved.state, understanding.memberUpdates, message);
      const focusedFollowup = applyFocusedTaste(updatedMembers.state, message);
      if (focusedFollowup.applied && intent.action === "ask" && !/가격|얼마|재료|뭐가/.test(message)) intent.action = "recommend";
      let dialogue: DialogueState = applyExplicitCorrections(focusedFollowup.state, understanding.corrections, message);
      const focusedRequest = !!dialogue.focusedMemberLabel && /얼큰|매운|맵|국물|수프|달달|달콤|순한|키즈|어린이/.test(message) && (focusedFollowup.applied || message.includes(dialogue.focusedMemberLabel));
      dialogue = { ...dialogue, pendingCheckout: false, pendingCheckoutSignature: undefined };
      const currentProfile = profile(freshSession.context);
      const freshAllergies = updatedMembers.applied ? understanding.globalAllergies : [...evolved.globalAllergies, ...understanding.globalAllergies];
      if (freshAllergies.length && /알레르기|못\s*먹|빼|제외/.test(message)) currentProfile.allergies = [...new Set([...currentProfile.allergies, ...freshAllergies])];
      const save = async () => db.guestSession.update({ where: { id: session.id }, data: { context: { ...currentProfile, dialogue } } });
      const summary = () => contextSummary(dialogue, session.fulfillmentType as VisitMode);
      if (intent.action === "checkout") {
        const cart = await cartSummary(session.id, currentProfile);
        dialogue.pendingCheckout = cart.canOrder;
        dialogue.pendingCheckoutSignature = cart.canOrder ? JSON.stringify(cart.items.map((item) => [item.id, item.quantity, item.lineTotal, item.selectedOptionIds, item.assignedTo])) : undefined;
        await save();
        return json({ intent, provider, dialogue, summary: summary(), cart,
          reply: cart.canOrder ? `장바구니 ${cart.items.length}개, 총 ${cart.total.toLocaleString()}원이에요. 모의 결제로 주문할까요? “응”이라고 답해 주세요.` : "주문할 메뉴가 없거나 확인할 조건이 있어요. 원하는 메뉴를 말씀해 주세요.",
          nextAction: cart.canOrder ? "confirm_checkout" : undefined });
      }
      const items = await db.menuItem.findMany({ where: { storeId: session.storeId, isPublished: true }, include: menuInclude });
      if (intent.action === "help") {
        const help = await db.helpRequest.create({ data: { storeId: session.storeId, tableId: session.tableId, sessionId: session.id, note: message } });
        await save();
        return json({ intent, provider, dialogue, summary: summary(), reply: "사장님께 알렸어요. 잠시만 기다려 주세요.", help });
      }
      if ((updatedMembers.needsClarification || understanding.clarification) && !focusedRequest) {
        await save();
        return json({ intent, provider, dialogue, summary: summary(), reply: updatedMembers.needsClarification ? "어느 분을 말씀하셨나요? 이름이나 특징을 알려 주세요." : understanding.clarification });
      }
      if (intent.action === "ask") {
        const found = items.filter((item) => !intent.menuName || menuMatches(item.name, intent.menuName)).slice(0, 3);
        dialogue.lastRecommendations = found.map((item) => ({ id: item.id }));
        await save();
        return json({ intent, provider, dialogue, summary: summary(), reply: found.length ? found.map((item) => `${item.name} ${item.price.toLocaleString()}원 · ${item.description}`).join("\n") : "해당 메뉴를 찾지 못했어요. 음식 이름이나 취향을 다르게 말씀해 주세요.", recommendations: found.map((item) => ({ item, reason: "매장 메뉴 정보", score: 0 })) });
      }
      if (intent.action === "add" || intent.action === "remove") {
        const allSuggested = /추천한.*(?:전부|모두|다)|(?:전부|모두|다)\s*(?:담|넣|추가|빼|제거)/.test(message);
        const ordinal = understanding.reference === "first" ? 0 : understanding.reference === "second" ? 1 : understanding.reference === "third" ? 2 : /첫\s*번째|1\s*번/.test(message) ? 0 : /두\s*번째|2\s*번/.test(message) ? 1 : /세\s*번째|3\s*번/.test(message) ? 2 : undefined;
        const refs = allSuggested ? dialogue.lastRecommendations : ordinal !== undefined ? dialogue.lastRecommendations.slice(ordinal, ordinal + 1) : understanding.reference === "last" && /마지막|끝/.test(message) ? dialogue.lastRecommendations.slice(-1) : /이걸|그걸|이거|그거|추천한/.test(message) ? dialogue.lastRecommendations.slice(0, 1) : [];
        const targets = refs.map((ref) => ({ item: items.find((entry) => entry.id === ref.id), forMember: ref.forMember })).filter((entry) => !!entry.item);
        if (!targets.length) {
          const found = items.find((item) => intent.menuName && menuMatches(item.name, intent.menuName));
          if (found) targets.push({ item: found, forMember: undefined });
        }
        if (!targets.length) {
          await save();
          return json({ intent, provider, dialogue, summary: summary(), reply: "어떤 음식인지 알려 주세요. “첫 번째 담아줘”처럼 말씀하셔도 돼요." });
        }
        if (intent.action === "remove") {
          const target = targets[0].item!;
          const cartItem = await db.cartItem.findFirst({ where: { sessionId: session.id, menuItemId: target.id } });
          if (cartItem) await db.cartItem.delete({ where: { id: cartItem.id } });
          await save();
          return json({ intent, provider, dialogue, summary: summary(), reply: `${target.name}을 장바구니에서 뺐어요.`, cart: await cartSummary(session.id, currentProfile) });
        }
        const added: string[] = [];
        const skipped: string[] = [];
        for (const target of targets) {
          const item = target.item!;
          const member = dialogue.members.find((entry) => entry.label === target.forMember);
          const effectiveProfile: PreferenceProfile = { ...currentProfile, allergies: [...new Set([...currentProfile.allergies, ...(member?.allergies || [])])], dietaryRules: [...currentProfile.dietaryRules, ...(member?.dietaryRules || [])], maxSpiceLevel: member?.maxSpiceLevel ?? currentProfile.maxSpiceLevel };
          let optionSets: string[][] = [[]];
          for (const group of item.options) {
            const available = group.options.filter((option) => option.isAvailable);
            const mentioned = available.filter((option) => message.includes(option.name));
            const choices = mentioned.length ? mentioned : available;
            const targetCount = mentioned.length ? Math.min(group.maxSelect, Math.max(group.minSelect, mentioned.length)) : group.minSelect;
            const combinations: string[][] = [];
            const collect = (offset: number, selected: string[]) => {
              if (selected.length === targetCount) { combinations.push(selected); return; }
              for (let index = offset; index < choices.length; index++) collect(index + 1, [...selected, choices[index].id]);
            };
            collect(0, []);
            optionSets = optionSets.flatMap((ids) => combinations.map((choice) => [...ids, ...choice])).slice(0, 120);
          }
          const optionIds = optionSets.find((ids) => checkSafety(item, effectiveProfile, ids).allowed);
          if (!optionIds) { skipped.push(`${item.name}: 조건에 맞는 옵션 없음`); continue; }
          const safety = checkSafety(item, effectiveProfile, optionIds);
          if (!safety.allowed) { skipped.push(`${item.name}: ${safety.reasons.join(", ")}`); continue; }
          const created = await db.cartItem.create({ data: { sessionId: session.id, menuItemId: item.id, quantity: Math.min(intent.quantity || 1, 30), selectedOptionIds: optionIds, assignedTo: target.forMember } });
          const checked = await cartSummary(session.id, currentProfile);
          if (!checked.items.find((entry) => entry.id === created.id)?.safety.allowed) { await db.cartItem.delete({ where: { id: created.id } }); skipped.push(`${item.name}: 일행 조건 확인 필요`); continue; }
          added.push(item.name);
        }
        await save();
        return json({ intent, provider, dialogue, summary: summary(), reply: [added.length ? `${added.join(", ")} 담았어요. 더 필요한 게 있나요?` : "아직 담지 못했어요.", skipped.length ? `확인 필요: ${skipped.join(" / ")}` : ""].filter(Boolean).join("\n"), cart: await cartSummary(session.id, currentProfile) });
      }
      if (evolved.needsPeopleCount || (updatedMembers.applied && !dialogue.peopleCount) || evolved.onlyHeadcount) {
        await save();
        return json({ intent, provider, dialogue, summary: summary(), reply: evolved.needsPeopleCount || (updatedMembers.applied && !dialogue.peopleCount) ? "조건을 기억했어요. 모두 몇 분이세요?" : "좋아요. 어떤 음식이 당기세요? 맵기, 예산, 알레르기도 함께 말씀해 주세요." });
      }
      const excluding = /다른\s*거|다른\s*메뉴|또\s*다른|말고|바꿔/.test(message) || (understanding.alternative && /더/.test(message));
      const candidates = excluding ? items.filter((item) => !previous.lastRecommendations.some((ref) => ref.id === item.id && (!focusedRequest || ref.forMember === dialogue.focusedMemberLabel))) : items;
      const group = (dialogue.peopleCount || 1) > 1 ? recommendGroup(candidates, currentProfile, dialogue.preferences, dialogue.members) : null;
      if (group && !group.complete && dialogue.members.some((member) => member.tastes?.includes("kids")) && !candidates.some((item) => item.isAvailable && (item.tags.includes("kids") || /키즈|어린이/.test(item.name)))) {
        dialogue.lastRecommendations = [];
        await save();
        return json({ intent, provider, dialogue, summary: summary(), recommendations: [], reply: "이 매장에는 지금 주문 가능한 키즈 메뉴가 없어요. 아이에게 순한 일반 메뉴로 다시 골라볼까요?" });
      }
      const ranked = group ? { recommendations: group.items, provider: "rules" } : await rankRecommendations(recommend(candidates, currentProfile, dialogue.preferences), dialogue.preferences);
      const recommendations = ranked.recommendations;
      dialogue.lastRecommendations = recommendations.map((entry) => ({ id: entry.item.id, forMember: entry.forMember }));
      await save();
      const focusedPick = focusedRequest ? recommendations.find((entry) => entry.forMember === dialogue.focusedMemberLabel) : undefined;
      const reply = recommendations.length
        ? focusedPick ? `${dialogue.focusedMemberLabel} 메뉴를 새로 골랐어요: ${focusedPick.item.name}. 다른 분 메뉴도 함께 확인해 주세요. 예상 합계 ${group?.total.toLocaleString()}원이에요.`
          : group ? `${dialogue.peopleCount}분의 취향을 각각 반영해 골랐어요. 예상 합계 ${group.total.toLocaleString()}원이에요. ${/2\s*살|두\s*살|만\s*2\s*세/.test(message) && dialogue.members.some((member) => member.tastes?.includes("kids")) ? "2살 아이에게 맞는 재료와 식감인지 보호자가 확인해 주세요. " : ""}“추천한 거 전부 담아줘”라고 하셔도 돼요.`
            : "이 음식은 어떠세요? 마음에 들면 “첫 번째 담아줘”라고 말씀해 주세요."
        : focusedRequest ? `${dialogue.focusedMemberLabel}의 새 조건에 맞는 확인된 메뉴가 없어요. 다른 맛으로 골라볼까요?` : "지금 조건에 맞는 확인된 메뉴가 없어요. 조건을 바꾸거나 사장님께 문의해 주세요.";
      return json({ intent, provider, decisionProvider: ranked.provider, dialogue, summary: summary(), recommendations, group, reply });
    }
    if (path[0] === "cart") {
      const input = cartSchema.parse(await body(req));
      const item = await db.menuItem.findFirst({
        where: { id: input.menuItemId, storeId: session.storeId },
        include: menuInclude,
      });
      if (!item) return fail("메뉴를 찾을 수 없어요.", 404);
      const safety = checkSafety(
        item,
        profile(session.context),
        input.selectedOptionIds,
      );
      if (!safety.allowed)
        return fail(`담을 수 없어요: ${safety.reasons.join(", ")}`);
      const created = await db.cartItem.create({
        data: { sessionId: session.id, ...input },
      });
      const updatedCart = await cartSummary(
        session.id,
        profile(session.context),
      );
      const newLine = updatedCart.items.find(
        (entry) => entry.id === created.id,
      );
      if (!newLine?.safety.allowed) {
        await db.cartItem.delete({ where: { id: created.id } });
        return fail(
          `담을 수 없어요: ${newLine?.safety.reasons.join(", ") || "일행의 조건과 맞지 않음"}`,
        );
      }
      return json(updatedCart, 201);
    }
    if (path[0] === "checkout") {
      const input = z
        .object({
          idempotencyKey: z.string().min(8).max(100),
          paymentMethod: z.enum(["mock_card", "mock_cash"]),
          note: z.string().max(300).default(""),
        })
        .parse(await body(req));
      const order = await db.$transaction(async (tx) => {
        await tx.$queryRaw`SELECT id FROM "GuestSession" WHERE id = ${session.id} FOR UPDATE`;
        const duplicate = await tx.order.findUnique({
          where: { idempotencyKey: input.idempotencyKey },
          include: { lines: true },
        });
        if (duplicate) {
          if (duplicate.sessionId !== session.id)
            throw new ApiError("중복 주문 키예요.", 409);
          return duplicate;
        }
        const freshSession = await tx.guestSession.findUniqueOrThrow({
          where: { id: session.id },
        });
        if (!freshSession.fulfillmentType) throw new ApiError("먼저 먹고 가기 또는 가져가기를 골라 주세요.");
        const snapshot = await cartSummary(
          session.id,
          profile(freshSession.context),
          tx,
        );
        if (!snapshot.canOrder)
          throw new ApiError(
            "장바구니의 메뉴와 옵션, 알레르기 정보를 확인해 주세요.",
          );
        const created = await tx.order.create({
          data: {
            code: `MMJ-${Date.now().toString(36).toUpperCase()}-${Math.random().toString(36).slice(2, 6).toUpperCase()}`,
            storeId: session.storeId,
            tableId: freshSession.tableId,
            fulfillmentType: freshSession.fulfillmentType,
            sessionId: session.id,
            idempotencyKey: input.idempotencyKey,
            paymentMethod: input.paymentMethod,
            paymentStatus: "mock_succeeded",
            total: snapshot.total,
            note: input.note,
            lines: {
              create: snapshot.items.map((item) => ({
                menuItemId: item.menuItemId,
                menuName: item.name,
                unitPrice: item.unitPrice,
                quantity: item.quantity,
                lineTotal: item.lineTotal,
                optionNames: item.optionNames,
                assignedTo: item.assignedTo,
              })),
            },
          },
          include: { lines: true },
        });
        await tx.cartItem.deleteMany({ where: { sessionId: session.id } });
        await tx.guestSession.update({ where: { id: session.id }, data: { context: { ...profile(freshSession.context), dialogue: { ...readDialogue(freshSession.context), pendingCheckout: false, pendingCheckoutSignature: undefined } } } });
        return created;
      });
      return json(order, 201);
    }
    if (path[0] === "help") {
      const input = z
        .object({ note: z.string().trim().min(1).max(300) })
        .parse(await body(req));
      return json(
        await db.helpRequest.create({
          data: {
            storeId: session.storeId,
            tableId: session.tableId,
            sessionId: session.id,
            note: input.note,
          },
        }),
        201,
      );
    }
    return fail("찾을 수 없는 기능이에요.", 404);
  } catch (error) {
    return errorResponse(error);
  }
}

export async function PATCH(req: NextRequest, context: Context) {
  try {
    if (!sameOrigin(req)) return fail("요청 출처를 확인해 주세요.", 403);
    const path = await segments(context);
    if (path[0] === "merchant") {
      if (!(await currentMerchant()))
        return fail("사장님 로그인이 필요해요.", 401);
      if (path[1] === "orders" && path[2]) {
        const input = z
          .object({
            status: z.enum([
              "placed",
              "accepted",
              "preparing",
              "ready",
              "completed",
              "cancelled",
            ]),
          })
          .parse(await body(req));
        const order = await db.order.update({
          where: { id: path[2] },
          data: { status: input.status },
        });
        return json(order);
      }
      if (path[1] === "help" && path[2]) {
        const input = z
          .object({ status: z.enum(["open", "resolved"]) })
          .parse(await body(req));
        return json(
          await db.helpRequest.update({ where: { id: path[2] }, data: input }),
        );
      }
      if (path[1] === "menu" && path[2]) {
        const item = await db.menuItem.findUnique({ where: { id: path[2] } });
        if (!item) return fail("메뉴가 없어요.", 404);
        const input = menuSchema.partial().parse(await body(req));
        if (
          input.categoryId &&
          !(await db.menuCategory.findFirst({
            where: { id: input.categoryId, storeId: item.storeId },
          }))
        )
          return fail("카테고리가 올바르지 않아요.");
        const nextAllergens =
          input.allergens ??
          (await db.menuItemAllergen.findMany({
            where: { menuItemId: item.id },
          }));
        if (
          (input.isPublished ?? item.isPublished) &&
          ((input.ingredients ?? item.ingredients).length === 0 ||
            nextAllergens.length !== ALLERGENS.length ||
            nextAllergens.some(
              (entry) => entry.verificationStatus !== "merchant_verified",
            ))
        )
          return fail("공개 전 재료와 모든 알레르기 항목을 확인해 주세요.");
        const { allergens, ...values } = input;
        const updated = await db.menuItem.update({
          where: { id: item.id },
          data: {
            ...values,
            ...(allergens
              ? {
                  allergens: {
                    deleteMany: {},
                    create: allergens.map((entry) => ({
                      ...entry,
                      verifiedAt:
                        entry.verificationStatus === "merchant_verified"
                          ? new Date()
                          : null,
                    })),
                  },
                }
              : {}),
          },
          include: menuInclude,
        });
        return json(updated);
      }
      return fail("찾을 수 없는 기능이에요.", 404);
    }
    const session = await currentGuest();
    if (!session) return fail("주문 세션이 없어요.", 401);
    if (path[0] === "cart" && path[1]) {
      const input = z
        .object({ quantity: z.number().int().min(1).max(30) })
        .parse(await body(req));
      const updated = await db.cartItem.updateMany({
        where: { id: path[1], sessionId: session.id },
        data: input,
      });
      return updated.count
        ? json(await cartSummary(session.id, profile(session.context)))
        : fail("장바구니 항목이 없어요.", 404);
    }
    return fail("찾을 수 없는 기능이에요.", 404);
  } catch (error) {
    return errorResponse(error);
  }
}

export async function DELETE(req: NextRequest, context: Context) {
  try {
    if (!sameOrigin(req)) return fail("요청 출처를 확인해 주세요.", 403);
    const path = await segments(context);
    if (
      path[0] === "merchant" &&
      path[1] === "menu" &&
      path[2] &&
      path[3] === "options" &&
      path[4]
    ) {
      if (!(await currentMerchant()))
        return fail("사장님 로그인이 필요해요.", 401);
      const group = await db.menuOptionGroup.findFirst({
        where: { id: path[4], menuItemId: path[2] },
      });
      if (!group) return fail("옵션 그룹이 없어요.", 404);
      await db.menuOptionGroup.delete({ where: { id: group.id } });
      return json({ ok: true });
    }
    if (path[0] === "merchant" && path[1] === "menu" && path[2]) {
      if (!(await currentMerchant()))
        return fail("사장님 로그인이 필요해요.", 401);
      const item = await db.menuItem.findUnique({ where: { id: path[2] } });
      if (!item) return fail("메뉴가 없어요.", 404);
      await db.menuItem.update({
        where: { id: item.id },
        data: { isPublished: false, isAvailable: false },
      });
      return json({ ok: true });
    }
    const session = await currentGuest();
    if (!session) return fail("주문 세션이 없어요.", 401);
    if (path[0] === "cart" && path[1]) {
      const deleted = await db.cartItem.deleteMany({
        where: { id: path[1], sessionId: session.id },
      });
      return deleted.count
        ? json(await cartSummary(session.id, profile(session.context)))
        : fail("장바구니 항목이 없어요.", 404);
    }
    return fail("찾을 수 없는 기능이에요.", 404);
  } catch (error) {
    return errorResponse(error);
  }
}
