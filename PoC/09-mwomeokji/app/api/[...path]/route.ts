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
import { anonymizeKnownNames, conversationSnapshot, resolveSeatTarget } from "../../../lib/conversation-context";
import { addsCurrentRecommendation, asksForPreviousOrder, hasExplicitNoAllergies, parseIntent } from "../../../lib/intent";
import { answerIngredientQuestion, ingredientQuestion } from "../../../lib/ingredient-answer";
import { rankRecommendations } from "../../../lib/decision";
import { selectMenuProposal } from "../../../lib/menu-selector";
import { spokenCatalogDishKinds, unavailableSpokenDish } from "../../../lib/menu-metadata";
import { recordAiUsage } from "../../../lib/usage-meter";
import { catalogTags, spokenMenuLabels, validCaffeineTags } from "../../../lib/menu-metadata";
import { matchesRequestedMenu, recommend, recommendDiverseGroupOptions, recommendGroupOptions, requestsDistinctMenus, shortlistForTurn, validateRecommendationResult } from "../../../lib/recommend";
import { checkSafety } from "../../../lib/safety";
import { applyExplicitCorrections, applyFocusedTaste, applyMemberUpdates, canStageRecommendations, contextSummary, emptyDialogue, evolveDialogue, readDialogue, resetForFullMealBrief, type DialogueState, type VisitMode } from "../../../lib/dialogue";
import {
  ALLERGENS,
  newEmptyProfile,
  type PreferenceProfile,
  type Recommendation,
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
  return parsed.success ? parsed.data : newEmptyProfile();
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
        const tags = catalogTags(input.tags, category.name);
        if (!validCaffeineTags(tags, category.name)) return fail("커피의 카페인 표시와 음료 카테고리를 확인해 주세요.");
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
            tags,
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
          const model = process.env.POC09_VISION_MODEL || "openai/gpt-4o-mini";
          try {
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
                  model,
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
            const result = await response.json().catch(() => ({}));
            const visionText = result.choices?.[0]?.message?.content;
            if (response.ok && typeof visionText === "string") extracted = visionText;
            await recordAiUsage({
              workload: "menu_import", model: typeof result.model === "string" ? result.model : model,
              status: response.ok && typeof visionText === "string" && visionText.trim() ? "COMPLETED" : "FAILED",
              httpStatus: response.status,
              inputTokens: Number.isFinite(result.usage?.prompt_tokens) ? result.usage.prompt_tokens : 0,
              outputTokens: Number.isFinite(result.usage?.completion_tokens) ? result.usage.completion_tokens : 0,
              costUsd: Number.isFinite(result.usage?.cost) ? result.usage.cost : undefined,
            });
          } catch {
            await recordAiUsage({ workload: "menu_import", model, status: "FAILED", httpStatus: 0 });
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
      if (req.headers.get("x-poc09-groq-evaluation") === "1" && process.env.POC09_CONVERSATION_PROVIDER !== "groq")
        return fail("Groq evaluation requires the free Groq provider.", 409);
      if (req.headers.get("x-poc09-rules-evaluation") === "1" && process.env.POC09_CONVERSATION_PROVIDER !== "rules")
        return fail("이 합성 평가는 외부 모델을 호출하지 않는 규칙 경로에서만 실행할 수 있어요.", 409);
      if (!session.fulfillmentType) return fail("먼저 먹고 가기 또는 가져가기를 골라 주세요.");
      if (path[1] === "reset") {
        const cart = await cartSummary(session.id, profile(session.context));
        if (cart.items.length) return json({ reset: false, dialogue: readDialogue(session.context), cart });
        const dialogue = emptyDialogue();
        await db.guestSession.update({ where: { id: session.id }, data: { context: { ...profile(session.context), dialogue } } });
        return json({ reset: true, dialogue, cart, summary: contextSummary(dialogue, session.fulfillmentType as VisitMode) });
      }
      const { message } = z.object({ message: z.string().trim().min(1).max(500) }).parse(await body(req));
      const clientIp = (req.headers.get("x-forwarded-for") || "local").split(",")[0].trim();
      if (rateLimited(`session:${session.id}`, 30) || rateLimited(`ip:${clientIp}`, 200)) return fail("잠시 뒤 다시 말씀해 주세요.", 429);
      let previous = readDialogue(session.context);
      const ingredient = ingredientQuestion(message);
      if (ingredient) {
        const [menu, cart] = await Promise.all([
          db.menuItem.findMany({ where: { storeId: session.storeId, isPublished: true }, include: menuInclude }),
          db.cartItem.findMany({ where: { sessionId: session.id }, orderBy: { createdAt: "desc" } }),
        ]);
        return json({
          dialogue: previous,
          summary: contextSummary(previous, session.fulfillmentType as VisitMode),
          reply: answerIngredientQuestion(message, ingredient, previous, menu, cart),
        });
      }
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
      const menuNames = new Map<string, string>();
      if (process.env.POC09_CONVERSATION_PROVIDER === "groq" && previous.lastRecommendations.length) {
        const suggested = await db.menuItem.findMany({
          where: { id: { in: previous.lastRecommendations.map((entry) => entry.id) }, storeId: session.storeId },
          select: { id: true, name: true },
        });
        for (const item of suggested) menuNames.set(item.id, item.name);
      }
      const mentionedCatalogLabels = process.env.POC09_CONVERSATION_PROVIDER === "groq"
        ? spokenMenuLabels(await db.menuItem.findMany({ where: { storeId: session.storeId, isPublished: true }, select: { tags: true } }), message).wanted
        : [];
      const understanding = await understand(message, process.env.POC09_CONVERSATION_PROVIDER === "groq"
        ? { snapshot: conversationSnapshot(previous, menuNames), outboundMessage: anonymizeKnownNames(message, previous), spokenLabels: mentionedCatalogLabels, seatLabels: previous.members.map((member) => member.label) }
        : undefined);
      const freshSession = await db.guestSession.findUniqueOrThrow({ where: { id: session.id } });
      previous = readDialogue(freshSession.context);
      if (understanding.modelUnavailable) return json({
        provider: "rules",
        ...(req.headers.get("x-poc09-groq-evaluation") === "1" ? { modelStatus: understanding.modelStatus, modelErrorCode: understanding.modelErrorCode } : {}),
        dialogue: previous,
        summary: contextSummary(previous, session.fulfillmentType as VisitMode),
        reply: understanding.modelStatus === 429
          ? `무료 대화 모델의 사용 한도가 잠시 가득 찼어요. ${understanding.retryAfterSeconds ? `약 ${Math.ceil(understanding.retryAfterSeconds / 60)}분 뒤 ` : "잠시 뒤 "}다시 말씀해 주세요. 이미 담은 메뉴는 그대로예요.`
          : "지금은 대화 추천을 잠시 처리할 수 없어요. 잠시 뒤 다시 말씀해 주세요. 이미 담은 메뉴는 그대로예요.",
      });
      const { intent, provider } = understanding;
      if (previous.pendingOffer && understanding.offerResolution === "accept") {
        const offered = new Set(previous.pendingOffer.memberIds);
        previous = { ...previous, pendingOffer: undefined, members: previous.members.map((member) => offered.has(member.id)
          ? { ...member, tastes: [...new Set([...(member.tastes || []).filter((taste) => taste !== "kids"), "mild" as const])], maxSpiceLevel: 0, excludedTags: [...new Set([...(member.excludedTags || []), "kids"])] }
          : member), preferences: { ...previous.preferences, kidsOnly: false } };
        intent.action = "recommend";
      } else if (previous.pendingOffer && understanding.offerResolution === "decline") {
        previous = { ...previous, pendingOffer: undefined };
        await db.guestSession.update({ where: { id: session.id }, data: { context: { ...profile(freshSession.context), dialogue: previous } } });
        return json({ intent, provider, dialogue: previous, summary: contextSummary(previous, session.fulfillmentType as VisitMode), reply: "알겠어요. 아이들 메뉴를 어떤 음식으로 바꿀까요?" });
      } else if (previous.pendingOffer) previous = { ...previous, pendingOffer: undefined };
      if (/^(?:이걸로|그걸로|이거|그거)(?:\s*(?:할게|줘|주세요))?$/.test(message.trim())) intent.action = "add";
      const beforeBrief = previous;
      previous = resetForFullMealBrief(previous, message, understanding.memberUpdates);
      const unmatchedAllergies = previous === beforeBrief ? [] : beforeBrief.members
        .filter((member) => !previous.members.some((retained) => retained.id === member.id))
        .flatMap((member) => member.allergies);
      const evolved = evolveDialogue(previous, message, intent);
      const updatedMembers = applyMemberUpdates(evolved.state, understanding.memberUpdates, message);
      const wantsAlternative = /다른|바꿔|말고|별로|대신/.test(message);
      const referencedMenus = wantsAlternative && previous.lastRecommendations.length
        ? await db.menuItem.findMany({ where: { id: { in: previous.lastRecommendations.map((entry) => entry.id) } }, select: { id: true, name: true } })
        : [];
      const mentioned = referencedMenus.filter((item) => item.name.split(/\s+/).some((word) => word.length >= 2 && message.includes(word)));
      const referencedFocus = resolveSeatTarget(message, previous, understanding.targetSeat, menuNames) ||
        (mentioned.length === 1 ? previous.lastRecommendations.find((entry) => entry.id === mentioned[0].id)?.forMember : undefined);
      const focusedFollowup = applyFocusedTaste(referencedFocus
        ? { ...updatedMembers.state, focusedMemberLabel: referencedFocus }
        : updatedMembers.state, message);
      if (focusedFollowup.applied && intent.action === "ask" && !/가격|얼마|재료|뭐가/.test(message)) intent.action = "recommend";
      if (referencedFocus && wantsAlternative) intent.action = "recommend";
      let dialogue: DialogueState = applyExplicitCorrections(focusedFollowup.state, understanding.corrections, message);
      if (referencedFocus) dialogue.preferences = {
        ...dialogue.preferences,
        category: previous.preferences.category,
        maxSpiceLevel: previous.preferences.maxSpiceLevel,
        wantsMild: previous.preferences.wantsMild,
        wantsWarm: previous.preferences.wantsWarm,
        wantsCool: previous.preferences.wantsCool,
        wantsSweet: previous.preferences.wantsSweet,
        avoidSour: previous.preferences.avoidSour,
      };
      const focusedRequest = !!(referencedFocus && wantsAlternative) ||
        (!!dialogue.focusedMemberLabel && /얼큰|매운|맵|국물|수프|덮밥|볶음밥|밥류|달달|달콤|순한|키즈|어린이/.test(message) && (focusedFollowup.applied || message.includes(dialogue.focusedMemberLabel)));
      dialogue = { ...dialogue, pendingCheckout: false, pendingCheckoutSignature: undefined };
      const currentProfile = profile(freshSession.context);
      if (unmatchedAllergies.length) currentProfile.allergies = [...new Set([...currentProfile.allergies, ...unmatchedAllergies])];
      const tableWideAllergy = /(?:우린|우리는|우리가|저흰|저희는|모두|전부|다들|전원).*(?:알레르기|알러지|못\s*먹)|(?:알레르기|알러지).*(?:모두|전부|다들|전원)/.test(message);
      const freshAllergies = tableWideAllergy || !updatedMembers.applied
        ? [...evolved.globalAllergies, ...understanding.globalAllergies]
        : understanding.globalAllergies;
      if (freshAllergies.length && /알레르기|알러지|못\s*먹|빼|제외/.test(message)) currentProfile.allergies = [...new Set([...currentProfile.allergies, ...freshAllergies])];
      // The guest explicitly corrected their own or table-wide allergy profile; named diners keep their own restrictions.
      if (hasExplicitNoAllergies(message)) currentProfile.allergies = [];
      const save = async () => db.guestSession.update({ where: { id: session.id }, data: { context: { ...currentProfile, dialogue } } });
      const summary = () => contextSummary(dialogue, session.fulfillmentType as VisitMode);
      // If the guest rejects a named dish absent from the current proposal, keep the proposal
      // and ask which existing dish to replace rather than silently rebuilding the table.
      if (!referencedFocus && wantsAlternative && previous.lastRecommendations.length &&
        /^.{2,30}?(?:은|는|이|가)\s*(?:별로|싫|마음에\s*안|좀\s*아닌)/.test(message)) {
        dialogue = previous;
        await save();
        return json({ intent, provider, dialogue, summary: summary(), reply: "직전 추천에는 말씀하신 메뉴가 없어요. 바꿀 메뉴 이름이나 번호를 알려 주세요." });
      }
      let orderFromRecommendations = false;
      if (intent.action === "checkout") {
        const cart = await cartSummary(session.id, currentProfile);
        const bareOrder = /^주문해(?:줘|주세요)?[.! ]*$/.test(message.trim());
        if (!cart.items.length && bareOrder && canStageRecommendations(dialogue)) {
          // A complete group proposal, or one unambiguous dish, can be staged for explicit confirmation.
          intent.action = "add";
          orderFromRecommendations = true;
        } else if (!cart.items.length && bareOrder && dialogue.lastRecommendations.length > 1) {
          await save();
          return json({ intent, provider, dialogue, summary: summary(), reply: "추천 메뉴가 여러 개예요. 원하는 메뉴 번호를 말씀해 주세요. 모두 담으려면 “추천한 거 전부 담아줘”라고 하시면 돼요." });
        } else {
          dialogue.pendingCheckout = cart.canOrder;
          dialogue.pendingCheckoutSignature = cart.canOrder ? JSON.stringify(cart.items.map((item) => [item.id, item.quantity, item.lineTotal, item.selectedOptionIds, item.assignedTo])) : undefined;
          await save();
          return json({ intent, provider, dialogue, summary: summary(), cart,
            reply: cart.canOrder ? `장바구니 ${cart.items.length}개, 총 ${cart.total.toLocaleString()}원이에요. 모의 결제로 주문할까요? “응”이라고 답해 주세요.` : "아직 담긴 메뉴가 없어요. 먼저 먹고 싶은 메뉴를 말씀해 주세요.",
            nextAction: cart.canOrder ? "confirm_checkout" : undefined });
        }
      }
      const items = await db.menuItem.findMany({ where: { storeId: session.storeId, isPublished: true }, include: menuInclude });
      if (intent.action === "help") {
        const help = await db.helpRequest.create({ data: { storeId: session.storeId, tableId: session.tableId, sessionId: session.id, note: message } });
        await save();
        return json({ intent, provider, dialogue, summary: summary(), reply: "사장님께 알렸어요. 잠시만 기다려 주세요.", help });
      }
      // A model paraphrase cannot interrupt an explicit recommendation request.
      const askedForRecommendation = intent.action === "recommend" &&
        (/추천|골라|주문해/.test(message) || focusedRequest || (previous.lastRecommendations.length > 0 && (wantsAlternative || /부탁해/.test(message))));
      const contextualAdd = intent.action === "add" && addsCurrentRecommendation(message) && canStageRecommendations(dialogue);
      const modelClarification = askedForRecommendation || contextualAdd ? null : understanding.clarification;
      if ((updatedMembers.needsClarification || modelClarification) && !focusedRequest && !orderFromRecommendations) {
        await save();
        return json({ intent, provider, dialogue, summary: summary(), reply: updatedMembers.needsClarification ? "어느 분을 말씀하셨나요? 이름이나 특징을 알려 주세요." : modelClarification });
      }
      if (intent.action === "ask") {
        const found = items.filter((item) => matchesRequestedMenu(item, intent) && (!intent.menuName || menuMatches(item.name, intent.menuName))).slice(0, 3);
        dialogue.lastRecommendations = found.map((item) => ({ id: item.id }));
        await save();
        return json({ intent, provider, dialogue, summary: summary(), reply: found.length ? found.map((item) => `${item.name} ${item.price.toLocaleString()}원 · ${item.description}`).join("\n") : "해당 메뉴를 찾지 못했어요. 음식 이름이나 취향을 다르게 말씀해 주세요.", recommendations: found.map((item) => ({ item, reason: "매장 메뉴 정보", score: 0 })) });
      }
      if (intent.action === "add" || intent.action === "remove") {
        const allSuggested = orderFromRecommendations || /추천한.*(?:전부|모두|다)|(?:전부|모두|다)\s*(?:담|넣|추가|빼|제거)/.test(message) ||
          contextualAdd;
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
          const created = await db.cartItem.create({ data: { sessionId: session.id, menuItemId: item.id, quantity: Math.min(intent.quantity || (!target.forMember && dialogue.lastRecommendations.length === 1 ? dialogue.preferences.quantity : undefined) || 1, 30), selectedOptionIds: optionIds, assignedTo: target.forMember } });
          const checked = await cartSummary(session.id, currentProfile);
          if (!checked.items.find((entry) => entry.id === created.id)?.safety.allowed) { await db.cartItem.delete({ where: { id: created.id } }); skipped.push(`${item.name}: 일행 조건 확인 필요`); continue; }
          added.push(item.name);
        }
        const checked = await cartSummary(session.id, currentProfile);
        if (orderFromRecommendations && added.length === targets.length && checked.canOrder) {
          dialogue.pendingCheckout = true;
          dialogue.pendingCheckoutSignature = JSON.stringify(checked.items.map((item) => [item.id, item.quantity, item.lineTotal, item.selectedOptionIds, item.assignedTo]));
          await save();
          return json({ intent, provider, dialogue, summary: summary(), cart: checked, nextAction: "confirm_checkout",
            reply: `추천 메뉴 ${added.length}개를 담았어요. 총 ${checked.total.toLocaleString()}원이에요. 이대로 모의 결제로 주문할까요? “응”이라고 답해 주세요.` });
        }
        await save();
        return json({ intent, provider, dialogue, summary: summary(), reply: [added.length ? `${added.join(", ")} 담았어요. 더 필요한 게 있나요?` : "아직 담지 못했어요.", skipped.length ? `확인 필요: ${skipped.join(" / ")}` : ""].filter(Boolean).join("\n"), cart: checked });
      }
      if (evolved.needsPeopleCount || (updatedMembers.applied && !dialogue.peopleCount) || evolved.onlyHeadcount) {
        await save();
        return json({ intent, provider, dialogue, summary: summary(), reply: evolved.needsPeopleCount || (updatedMembers.applied && !dialogue.peopleCount) ? "조건을 기억했어요. 모두 몇 분이세요?" : "좋아요. 어떤 음식이 당기세요? 맵기, 예산, 알레르기도 함께 말씀해 주세요." });
      }
      const priorOrderRequested = asksForPreviousOrder(message);
      const priorOrder = priorOrderRequested ? await db.order.findFirst({
        where: { sessionId: session.id, storeId: session.storeId },
        include: { lines: true }, orderBy: { createdAt: "desc" },
      }) : null;
      if (priorOrderRequested && !priorOrder) {
        dialogue.lastRecommendations = [];
        await save();
        return json({ intent, provider, dialogue, summary: summary(), recommendations: [], reply: "이 브라우저의 이전 주문 기록이 없어요. 먹고 싶은 메뉴를 말씀해 주세요." });
      }
      const requestedDishKinds = updatedMembers.applied && !focusedRequest ? [] : spokenCatalogDishKinds(items, message);
      const missingDish = unavailableSpokenDish(items, message);
      if (missingDish) {
        dialogue.lastRecommendations = [];
        await save();
        return json({ intent, provider, dialogue, summary: summary(), profile: currentProfile, recommendations: [], reply: `이 매장에는 ${missingDish} 메뉴가 없어요. 다른 음식으로 바꿔 추천해 드릴까요?` });
      }
      const labels = spokenMenuLabels(items, message);
      const tableLabels = provider === "groq" ? understanding.globalMenuLabels || [] : labels.wanted;
      if (tableLabels.length) dialogue.menuLabels = tableLabels;
      else if ((provider === "groq" && labels.wanted.length && updatedMembers.applied) ||
        labels.excluded.some((label) => dialogue.menuLabels.includes(label)) ||
        (intent.category && intent.category !== previous.preferences.category) ||
        (wantsAlternative && requestedDishKinds.length)) dialogue.menuLabels = [];
      const mentionedMenus = updatedMembers.applied && !focusedRequest ? [] : items.filter((item) => {
        const index = message.indexOf(item.name);
        return index >= 0 && !/^(?:은|는|이|가)?\s*(?:말고|빼고|제외|아닌|별로)/.test(message.slice(index + item.name.length));
      });
      const longestMenuName = Math.max(0, ...mentionedMenus.map((item) => item.name.length));
      const namedMenus = mentionedMenus.filter((item) => item.name.length === longestMenuName);
      if (wantsAlternative && namedMenus.length === 1 && previous.lastRecommendations.length) {
        // A fully named new dish replaces the previous dish's soft flavor/temperature cues.
        // Allergy, strict diet, caffeine restrictions and budget remain in force.
        const replacement = parseIntent(message.split(/말고|대신/).at(-1) || message);
        dialogue.preferences = { ...dialogue.preferences,
          minSpiceLevel: replacement.minSpiceLevel,
          wantsSweet: replacement.wantsSweet, avoidSour: replacement.avoidSour,
          wantsWarm: replacement.wantsWarm, wantsCool: replacement.wantsCool,
          coffee: replacement.coffee || false,
          decaf: replacement.coffee ? dialogue.preferences.decaf || replacement.decaf : false,
        };
      }
      const excluding = /다른|바꿔|말고/.test(message) || (understanding.alternative && /더/.test(message));
      const previousOrderIds = priorOrder ? new Set(priorOrder.lines.map((line) => line.menuItemId)) : null;
      const candidates = items.filter((item) => (!namedMenus.length || namedMenus.some((named) => named.id === item.id)) &&
        (namedMenus.length > 0 || !requestedDishKinds.length || requestedDishKinds.some((kind) => item.name.endsWith(kind))) &&
        (!previousOrderIds || previousOrderIds.has(item.id)) &&
        (namedMenus.length > 0 || dialogue.menuLabels.every((label) => item.tags.includes(label))) &&
        (!excluding || !previous.lastRecommendations.some((ref) => ref.id === item.id && (!focusedRequest || ref.forMember === dialogue.focusedMemberLabel))));
      const focus = dialogue.members.find((member) => member.label === dialogue.focusedMemberLabel);
      const canKeepOthers = focusedRequest && focus && canStageRecommendations(previous) &&
        previous.lastRecommendations.length === dialogue.peopleCount &&
        previous.lastRecommendations.some((entry) => entry.forMember === focus.label);
      const anchoredOptions = canKeepOthers ? recommendGroupOptions(candidates, currentProfile,
        { ...dialogue.preferences, peopleCount: 1, totalBudget: undefined }, [focus]).map((option) => {
        const replacement = option.items[0];
        const entries = previous.lastRecommendations.map((ref): Recommendation | null => {
          if (ref.forMember === focus.label) return replacement;
          const item = items.find((entry) => entry.id === ref.id);
          return item && ref.forMember ? { item, forMember: ref.forMember, reason: "앞서 고른 메뉴를 유지했어요.", score: 0 } : null;
        });
        if (entries.some((entry) => !entry)) return null;
        const recommendations = entries as Recommendation[];
        const checked = validateRecommendationResult(recommendations, currentProfile, dialogue.preferences, dialogue.members, requestsDistinctMenus(message));
        return checked.valid ? { items: recommendations, total: checked.total, complete: true as const } : null;
      }).filter((entry): entry is NonNullable<typeof entry> => !!entry) : [];
      const groupOptions = canKeepOthers ? anchoredOptions : (dialogue.peopleCount || 1) > 1
        ? recommendDiverseGroupOptions(candidates, currentProfile, dialogue.preferences, dialogue.members, message) : [];
      const group = (dialogue.peopleCount || 1) > 1 ? groupOptions[0] ?? { items: [], total: 0, complete: false } : null;
      if (group && !group.complete) {
        const children = dialogue.members.filter((member) => member.tastes?.includes("kids"));
        const relaxed = children.length ? dialogue.members.map((member) => children.some((child) => child.id === member.id)
          ? { ...member, tastes: [...new Set([...(member.tastes || []).filter((taste) => taste !== "kids"), "mild" as const])], maxSpiceLevel: 0, excludedTags: [...new Set([...(member.excludedTags || []), "kids"])] }
          : member) : [];
        const canOfferMild = relaxed.length && recommendDiverseGroupOptions(candidates, currentProfile,
          { ...dialogue.preferences, kidsOnly: false }, relaxed, message).some((option) => option.complete);
        if (canOfferMild) {
          dialogue.pendingOffer = { kind: "replace_kids_with_mild", memberIds: children.map((child) => child.id) };
          dialogue.lastRecommendations = [];
          await save();
          return json({ intent, provider, dialogue, summary: summary(), recommendations: [], reply: "아이들 조건에 맞는 키즈 메뉴로는 지금 구성을 완성할 수 없어요. 아이들에게 맵지 않은 일반 메뉴를 골라볼까요?" });
        }
      }
      const requestedCount = (dialogue.peopleCount || 1) > 1 ? 1 : Math.max(1, dialogue.preferences.quantity || 1);
      const ranked = group ? { recommendations: group.items, provider: "rules" } : await rankRecommendations(shortlistForTurn(recommend(candidates, currentProfile, dialogue.preferences, candidates.length), message), dialogue.preferences);
      const proposals = group
        ? groupOptions.map((option, index) => ({ id: `option_${index + 1}`, recommendations: option.items, total: option.total }))
        : ranked.recommendations.map((entry, index) => ({ id: `option_${index + 1}`, recommendations: [entry], total: entry.item.price * requestedCount }));
      const selection = await selectMenuProposal(message, proposals);
      const chosenGroup = group && selection.proposal ? { items: selection.proposal.recommendations, total: selection.proposal.total, complete: true } : null;
      const checked = validateRecommendationResult(selection.proposal?.recommendations ?? [], currentProfile, dialogue.preferences, dialogue.members, requestsDistinctMenus(message));
      const unit = dialogue.preferences.category === "음료" ? "잔" : "개";
      const recommendations = checked.valid ? selection.proposal!.recommendations.map((entry) => ({
        ...entry,
        reason: entry.reason === "많이 찾는 메뉴라서 골랐어요." && dialogue.menuLabels.length
          ? `${dialogue.menuLabels.join(" · ")} 요청에 맞춰 골랐어요.` : entry.reason,
        quantity: group ? 1 : requestedCount, unit,
      })) : [];
      if (recommendations.length || !focusedRequest)
        dialogue.lastRecommendations = recommendations.map((entry) => ({ id: entry.item.id, forMember: entry.forMember }));
      await save();
      const focusedPick = focusedRequest ? recommendations.find((entry) => entry.forMember === dialogue.focusedMemberLabel) : undefined;
      const savedLimits = [
        currentProfile.maxSpiceLevel !== undefined ? `맵기 ${currentProfile.maxSpiceLevel} 이하` : null,
        currentProfile.budget ? `예산 ${currentProfile.budget.toLocaleString()}원` : null,
        currentProfile.allergies.length ? `${currentProfile.allergies.map((key) => ALLERGENS.find(([code]) => code === key)?.[1] || key).join("·")} 알레르기 조건` : null,
        currentProfile.dietaryRules.some((rule) => rule.mode === "strict") ? "식사 제한" : null,
      ].filter(Boolean);
      const childReminder = /애기|아기|유아|2\s*살|두\s*살|만\s*2\s*세/.test(message) &&
        recommendations.some((entry) => entry.item.tags.includes("kids"))
        ? "아이에게 맞는 재료와 식감인지 보호자가 확인해 주세요. " : "";
      const limitHelp = savedLimits.length ? `현재 적용 중인 조건(${savedLimits.join(", ")})도 있어요. ‘내 취향 설정’에서 확인하거나 조건을 다시 말씀해 주세요.` : "조건을 바꾸거나 사장님께 문의해 주세요.";
      const noMatchReply = `지금 조건에 맞는 확인된 메뉴가 없어요. ${limitHelp}`;
      const reply = recommendations.length
        ? focusedPick ? `${dialogue.focusedMemberLabel} 메뉴를 새로 골랐어요: ${focusedPick.item.name}. 다른 분 메뉴도 함께 확인해 주세요. 예상 합계 ${chosenGroup?.total.toLocaleString()}원이에요.`
          : chosenGroup ? `${dialogue.peopleCount}분의 취향을 각각 반영해 골랐어요. 예상 합계 ${chosenGroup.total.toLocaleString()}원이에요. ${childReminder}“추천한 거 전부 담아줘”라고 하셔도 돼요.`
            : requestedCount > 1 ? `${recommendations[0].item.name} ${requestedCount}${unit}이면 예상 합계 ${checked.total.toLocaleString()}원이에요. “첫 번째 담아줘”라고 하시면 ${requestedCount}${unit}${unit === "잔" ? "을" : "를"} 담을게요.`
              : priorOrderRequested ? `이 브라우저에서 전에 주문한 ${recommendations[0].item.name}이에요. “첫 번째 담아줘”라고 말씀해 주세요.`
              : `${childReminder}이 음식은 어떠세요? 마음에 들면 “첫 번째 담아줘”라고 말씀해 주세요.`
        : focusedRequest ? `${dialogue.focusedMemberLabel}의 새 조건에 맞는 확인된 메뉴가 없어요. ${savedLimits.length ? limitHelp : "다른 맛이나 음식 종류로 골라볼까요?"}` : dialogue.preferences.coffee && dialogue.preferences.caffeineFree
          ? "이 매장에는 카페인 없는 커피로 확인된 메뉴가 없어요. 다른 음료나 음식으로 바꿔 추천하지 않았어요. 디카페인도 괜찮다면 말씀해 주세요."
          : dialogue.preferences.coffee && dialogue.preferences.decaf
            ? "이 매장에는 디카페인 커피로 확인된 메뉴가 없어요. 다른 음료로 바꿔 추천하지 않았어요."
            : priorOrderRequested ? "이전에 주문한 메뉴가 지금은 판매되지 않거나 현재 조건에 맞지 않아요. 다른 메뉴를 골라드릴까요?"
          : requestsDistinctMenus(message) ? "지금 조건에서는 모두 다른 메뉴로 고를 수 없어요. 인원이나 종류, 제한 조건을 바꿔 말씀해 주세요." : noMatchReply;
      return json({ intent, provider, decisionProvider: ranked.provider, menuSelectionProvider: selection.provider, dialogue, summary: summary(), recommendations, group: checked.valid ? chosenGroup : null, profile: currentProfile, reply });
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
        await tx.guestSession.update({ where: { id: session.id }, data: { context: { ...profile(freshSession.context), dialogue: emptyDialogue() } } });
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
        const category = await db.menuCategory.findFirst({
          where: { id: input.categoryId || item.categoryId, storeId: item.storeId },
        });
        if (!category) return fail("카테고리가 올바르지 않아요.");
        const tags = catalogTags(input.tags ?? item.tags, category.name);
        if (!validCaffeineTags(tags, category.name)) return fail("커피의 카페인 표시와 음료 카테고리를 확인해 주세요.");
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
            tags,
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
