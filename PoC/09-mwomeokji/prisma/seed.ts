import { db } from "../lib/db";
import { ALLERGENS } from "../lib/types";

const recipes = [
  [
    "식사",
    "햇살 치킨 덮밥",
    "구운 닭고기와 달콤한 간장 소스",
    10900,
    "🍗",
    0,
    ["warm", "식사"],
    ["chicken", "rice", "soy"],
    ["no_pork", "no_beef", "no_seafood", "no_dairy"],
    ["soy"],
    86,
  ],
  [
    "식사",
    "달콤 키즈 치킨 덮밥",
    "작은 한 그릇에 담은 달콤한 간장 치킨과 밥",
    8900,
    "🐣",
    0,
    ["warm", "식사", "kids", "sweet"],
    ["chicken", "rice", "soy"],
    ["no_pork", "no_beef", "no_seafood", "no_dairy"],
    ["soy"],
    72,
  ],
  [
    "식사",
    "든든 소불고기 덮밥",
    "달콤한 불고기와 갓 지은 밥",
    12900,
    "🥩",
    0,
    ["warm", "식사"],
    ["beef", "rice", "soy"],
    ["no_pork", "no_seafood", "no_dairy"],
    ["soy"],
    78,
  ],
  [
    "식사",
    "매콤 제육 덮밥",
    "불맛 가득 매콤한 돼지고기",
    11900,
    "🌶️",
    2,
    ["warm", "식사"],
    ["pork", "rice", "soy"],
    ["no_beef", "no_seafood", "no_dairy"],
    ["soy"],
    74,
  ],
  [
    "식사",
    "얼큰 닭고기 덮밥",
    "고추와 닭고기로 만든 얼큰한 밥 한 그릇",
    11900,
    "🍗",
    2,
    ["warm", "식사", "rice", "spicy"],
    ["chicken", "rice", "chili"],
    ["no_pork", "no_beef", "no_seafood", "no_dairy"],
    [],
    67,
  ],
  [
    "식사",
    "버섯 두부 덮밥",
    "버섯과 두부로 만든 담백한 한 그릇",
    9900,
    "🍄",
    0,
    ["warm", "식사"],
    ["mushroom", "tofu", "rice"],
    ["vegetarian", "vegan", "no_pork", "no_beef", "no_seafood", "no_dairy"],
    ["soy"],
    68,
  ],
  [
    "식사",
    "토마토 달걀 볶음밥",
    "상큼한 토마토와 폭신한 달걀",
    9500,
    "🍅",
    0,
    ["warm", "식사"],
    ["tomato", "egg", "rice"],
    ["vegetarian", "no_pork", "no_beef", "no_seafood", "no_dairy"],
    ["egg"],
    65,
  ],
  [
    "식사",
    "새우 크림 파스타",
    "새우와 부드러운 크림 소스",
    14900,
    "🍝",
    0,
    ["warm", "식사"],
    ["shrimp", "milk", "wheat"],
    ["no_pork", "no_beef"],
    ["shellfish", "milk", "wheat"],
    71,
  ],
  [
    "식사",
    "바질 토마토 파스타",
    "바질 향 가득한 토마토 소스",
    12900,
    "🍝",
    0,
    ["warm", "식사"],
    ["tomato", "basil", "wheat"],
    ["vegetarian", "vegan", "no_pork", "no_beef", "no_seafood", "no_dairy"],
    ["wheat"],
    70,
  ],
  [
    "식사",
    "오렌지 치킨 샐러드",
    "상큼한 오렌지와 구운 치킨",
    11900,
    "🥗",
    0,
    ["cool", "식사"],
    ["chicken", "orange", "lettuce"],
    ["no_pork", "no_beef", "no_seafood", "no_dairy"],
    [],
    76,
  ],
  [
    "식사",
    "싱그러운 두부 샐러드",
    "채소와 두부를 곁들인 가벼운 접시",
    10500,
    "🥗",
    0,
    ["cool", "식사"],
    ["tofu", "lettuce", "tomato"],
    ["vegetarian", "vegan", "no_pork", "no_beef", "no_seafood", "no_dairy"],
    ["soy"],
    64,
  ],
  [
    "국물",
    "따끈 닭고기 수프",
    "따뜻하고 순한 닭고기 수프",
    7900,
    "🍲",
    0,
    ["warm", "식사"],
    ["chicken", "potato"],
    ["no_pork", "no_beef", "no_seafood", "no_dairy"],
    [],
    59,
  ],
  [
    "국물",
    "얼큰 닭고기 수프",
    "고추와 닭고기, 감자를 넣은 얼큰한 수프",
    9900,
    "🍲",
    2,
    ["warm", "식사", "soup", "spicy"],
    ["chicken", "potato", "chili"],
    ["no_pork", "no_beef", "no_seafood", "no_dairy"],
    [],
    56,
  ],
  [
    "국물",
    "얼큰 해물 수프",
    "매콤한 해물과 채소",
    10900,
    "🦐",
    3,
    ["warm", "식사"],
    ["shrimp", "fish", "vegetable"],
    ["no_pork", "no_beef", "no_dairy"],
    ["shellfish", "fish"],
    53,
  ],
  [
    "사이드",
    "바삭 감자튀김",
    "바삭하게 튀긴 감자",
    4500,
    "🍟",
    0,
    ["warm", "사이드"],
    ["potato"],
    ["vegetarian", "vegan", "no_pork", "no_beef", "no_seafood", "no_dairy"],
    [],
    82,
  ],
  [
    "사이드",
    "오렌지 과일컵",
    "신선한 과일 한 컵",
    4900,
    "🍊",
    0,
    ["cool", "사이드"],
    ["orange", "apple"],
    ["vegetarian", "vegan", "no_pork", "no_beef", "no_seafood", "no_dairy"],
    [],
    49,
  ],
  [
    "사이드",
    "고소 땅콩 치킨",
    "땅콩 소스를 곁들인 바삭한 치킨",
    6900,
    "🥜",
    1,
    ["warm", "사이드"],
    ["chicken", "peanut", "soy"],
    ["no_pork", "no_beef", "no_seafood", "no_dairy"],
    ["peanut", "soy"],
    58,
  ],
  [
    "사이드",
    "고소 치즈볼",
    "치즈가 가득한 따뜻한 간식",
    5900,
    "🧀",
    0,
    ["warm", "사이드"],
    ["milk", "wheat"],
    ["vegetarian", "no_pork", "no_beef", "no_seafood"],
    ["milk", "wheat"],
    61,
  ],
  [
    "음료",
    "오렌지 에이드",
    "상큼한 탄산 오렌지 음료",
    4500,
    "🍊",
    0,
    ["cool", "음료"],
    ["orange"],
    ["vegetarian", "vegan", "no_pork", "no_beef", "no_seafood", "no_dairy"],
    [],
    85,
  ],
  [
    "음료",
    "아이스 아메리카노",
    "시원한 커피 한 잔",
    3900,
    "☕",
    0,
    ["cool", "음료"],
    ["coffee"],
    ["vegetarian", "vegan", "no_pork", "no_beef", "no_seafood", "no_dairy"],
    [],
    79,
  ],
  [
    "음료",
    "따뜻한 카페라떼",
    "부드러운 우유와 에스프레소",
    4900,
    "🥛",
    0,
    ["warm", "음료"],
    ["coffee", "milk"],
    ["vegetarian", "no_pork", "no_beef", "no_seafood"],
    ["milk"],
    56,
  ],
  [
    "음료",
    "생수",
    "깨끗한 생수",
    1500,
    "💧",
    0,
    ["cool", "음료"],
    ["water"],
    ["vegetarian", "vegan", "no_pork", "no_beef", "no_seafood", "no_dairy"],
    [],
    42,
  ],
] as const;

async function main() {
  const store = await db.store.upsert({
    where: { slug: "orange-table" },
    update: {},
    create: {
      slug: "orange-table",
      name: "오렌지 테이블",
      description: "오늘의 기분에 맞춰 고르는 한 끼 · 내부 테스트용 가상 매장",
      address: "서울시 테스트구 오렌지로 9",
    },
  });
  const categories = new Map<string, string>();
  for (const [index, name] of ["식사", "국물", "사이드", "음료"].entries()) {
    const existing = await db.menuCategory.findFirst({
      where: { storeId: store.id, name },
    });
    const category =
      existing ??
      (await db.menuCategory.create({
        data: { storeId: store.id, name, sortOrder: index },
      }));
    categories.set(name, category.id);
  }
  for (const code of ["A1", "A2", "B1", "B2", "포장"]) {
    await db.storeTable.upsert({
      where: { storeId_code: { storeId: store.id, code } },
      update: {},
      create: {
        storeId: store.id,
        code,
        label: code === "포장" ? "포장 주문" : `${code} 테이블`,
      },
    });
  }
  for (const [
    category,
    name,
    description,
    price,
    emoji,
    spiceLevel,
    tags,
    ingredients,
    dietaryTags,
    contains,
    popularity,
  ] of recipes) {
    const existing = await db.menuItem.findFirst({
      where: { storeId: store.id, name },
    });
    if (existing) {
      for (const [allergenKey] of ALLERGENS)
        await db.menuItemAllergen.upsert({
          where: {
            menuItemId_allergenKey: { menuItemId: existing.id, allergenKey },
          },
          update: {},
          create: {
            menuItemId: existing.id,
            allergenKey,
            relation: (contains as readonly string[]).includes(allergenKey)
              ? "contains"
              : "excludes",
            verificationStatus: "merchant_verified",
            verifiedAt: new Date(),
          },
        });
      continue;
    }
    await db.menuItem.create({
      data: {
        storeId: store.id,
        categoryId: categories.get(category)!,
        name,
        description,
        price,
        emoji,
        spiceLevel,
        tags: [...tags],
        ingredients: [...ingredients],
        dietaryTags: [...dietaryTags],
        popularity,
        isShareable: category === "사이드",
        allergens: {
          create: ALLERGENS.map(([key]) => ({
            allergenKey: key,
            relation: (contains as readonly string[]).includes(key)
              ? "contains"
              : "excludes",
            verificationStatus: "merchant_verified",
            verifiedAt: new Date(),
          })),
        },
      },
    });
  }
  const chicken = await db.menuItem.findFirstOrThrow({
    where: { storeId: store.id, name: "햇살 치킨 덮밥" },
  });
  if (
    !(await db.menuOptionGroup.findFirst({ where: { menuItemId: chicken.id } }))
  ) {
    await db.menuOptionGroup.create({
      data: {
        menuItemId: chicken.id,
        name: "밥 양",
        minSelect: 1,
        maxSelect: 1,
        options: {
          create: [
            {
              name: "보통",
              priceDelta: 0,
              dietaryTags: ["no_pork", "no_beef", "no_seafood", "no_dairy"],
              ingredients: ["rice"],
              allergens: {
                create: ALLERGENS.map(([key]) => ({
                  allergenKey: key,
                  relation: "excludes",
                  verificationStatus: "merchant_verified",
                })),
              },
            },
            {
              name: "많이",
              priceDelta: 1500,
              dietaryTags: ["no_pork", "no_beef", "no_seafood", "no_dairy"],
              ingredients: ["rice"],
              allergens: {
                create: ALLERGENS.map(([key]) => ({
                  allergenKey: key,
                  relation: "excludes",
                  verificationStatus: "merchant_verified",
                })),
              },
            },
          ],
        },
      },
    });
  }
  for (const group of await db.menuOptionGroup.findMany({
    where: { menuItemId: chicken.id },
    include: { options: true },
  })) {
    for (const option of group.options)
      for (const [allergenKey] of ALLERGENS)
        await db.menuOptionAllergen.upsert({
          where: { optionId_allergenKey: { optionId: option.id, allergenKey } },
          update: {},
          create: {
            optionId: option.id,
            allergenKey,
            relation: "excludes",
            verificationStatus: "merchant_verified",
          },
        });
  }
  console.log(
    `Seeded demo store ${store.slug}, ${recipes.length} menu items, 5 tables.`,
  );
}
main().finally(() => db.$disconnect());
