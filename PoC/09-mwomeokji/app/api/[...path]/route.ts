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
import {
  ALLERGENS,
  emptyProfile,
  type GroupMember,
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
          include: { table: true },
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
          context: {
            ...nextProfile,
            members:
              session.context &&
              typeof session.context === "object" &&
              !Array.isArray(session.context) &&
              "members" in session.context
                ? session.context.members
                : [],
          },
        },
      });
      return json({
        profile: nextProfile,
        cart: await cartSummary(session.id, nextProfile),
      });
    }
    if (path[0] === "conversation") {
      const input = z
        .object({
          message: z.string().trim().min(1).max(500),
          members: z
            .array(
              z.object({
                id: z.string(),
                label: z.string(),
                allergies: z.array(z.string()),
                dietaryRules: z.array(
                  z.object({
                    type: z.string(),
                    mode: z.enum(["strict", "prefer"]),
                  }),
                ),
                maxSpiceLevel: z.number().optional(),
              }),
            )
            .max(12)
            .default([]),
        })
        .parse(await body(req));
      await db.guestSession.update({
        where: { id: session.id },
        data: {
          context: { ...profile(session.context), members: input.members },
        },
      });
      const { intent, provider } = await understand(input.message);
      const items = await db.menuItem.findMany({
        where: { storeId: session.storeId, isPublished: true },
        include: menuInclude,
      });
      const currentProfile = profile(session.context);
      if (intent.action === "help") {
        const help = await db.helpRequest.create({
          data: {
            storeId: session.storeId,
            tableId: session.tableId,
            sessionId: session.id,
            note: input.message,
          },
        });
        return json({
          intent,
          provider,
          reply: "사장님께 알렸어요. 잠시만 기다려 주세요.",
          help,
        });
      }
      if (intent.action === "ask") {
        const found = items.filter(
          (item) => !intent.menuName || item.name.includes(intent.menuName),
        );
        return json({
          intent,
          provider,
          reply: found.length
            ? found
                .slice(0, 3)
                .map(
                  (item) =>
                    `${item.name} ${item.price.toLocaleString()}원 · ${item.description}`,
                )
                .join("\n")
            : "해당 메뉴를 찾지 못했어요. 메뉴 이름을 확인해 주세요.",
          recommendations: found
            .slice(0, 3)
            .map((item) => ({ item, reason: "매장 메뉴 정보", score: 0 })),
        });
      }
      if (intent.action === "add" || intent.action === "remove") {
        const found =
          items.find(
            (item) => intent.menuName && item.name.includes(intent.menuName),
          ) ||
          items.find(
            (item) => intent.menuName && intent.menuName.includes(item.name),
          );
        if (!found)
          return json({
            intent,
            provider,
            reply: "어떤 메뉴인지 찾지 못했어요. 메뉴에서 직접 골라 주세요.",
          });
        if (intent.action === "remove") {
          const cartItem = await db.cartItem.findFirst({
            where: { sessionId: session.id, menuItemId: found.id },
          });
          if (cartItem)
            await db.cartItem.delete({ where: { id: cartItem.id } });
          return json({
            intent,
            provider,
            reply: `${found.name}을 장바구니에서 뺐어요.`,
            cart: await cartSummary(session.id, currentProfile),
          });
        }
        if (found.options.some((group) => group.minSelect > 0))
          return json({
            intent,
            provider,
            reply: `${found.name}의 옵션을 골라 주세요.`,
            recommendations: [
              { item: found, reason: "옵션 선택이 필요해요", score: 0 },
            ],
          });
        const safety = checkSafety(found, currentProfile, []);
        if (!safety.allowed)
          return json({
            intent,
            provider,
            reply: `조건을 확인해 주세요: ${safety.reasons.join(", ")}`,
          });
        const created = await db.cartItem.create({
          data: {
            sessionId: session.id,
            menuItemId: found.id,
            quantity: Math.min(intent.quantity || 1, 30),
          },
        });
        const updatedCart = await cartSummary(session.id, currentProfile);
        if (
          !updatedCart.items.find((entry) => entry.id === created.id)?.safety
            .allowed
        ) {
          await db.cartItem.delete({ where: { id: created.id } });
          return json({
            intent,
            provider,
            reply:
              "함께 주문하는 손님의 조건을 확인해 주세요. 이 메뉴는 장바구니에 담지 않았어요.",
          });
        }
        return json({
          intent,
          provider,
          reply: `${found.name}을 장바구니에 담았어요.`,
          cart: updatedCart,
        });
      }
      const group =
        input.members.length > 1 || (intent.peopleCount || 1) > 1
          ? recommendGroup(
              items,
              currentProfile,
              intent,
              input.members as GroupMember[],
            )
          : null;
      const ranked = group
        ? { recommendations: group.items, provider: "rules" }
        : await rankRecommendations(
            recommend(items, currentProfile, intent),
            intent,
          );
      const recommendations = ranked.recommendations;
      const reply = recommendations.length
        ? group
          ? `${input.members.length || intent.peopleCount}명 조건에 맞춰 골랐어요. 총 ${group.total.toLocaleString()}원이에요.`
          : "이 메뉴는 어떠세요? 조건과 메뉴 정보를 확인하고 골랐어요."
        : "조건에 맞는 확인된 메뉴가 없어요. 조건을 조정하거나 사장님께 문의해 주세요.";
      return json({
        intent,
        provider,
        decisionProvider: ranked.provider,
        reply,
        recommendations,
        group,
      });
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
