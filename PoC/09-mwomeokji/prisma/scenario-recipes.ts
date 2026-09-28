/** Fictional recipes for conversation and safety testing. These are not real restaurant claims. */
export type DemoRecipe = readonly [
  category: string, name: string, description: string, price: number, emoji: string,
  spiceLevel: number, tags: readonly string[], ingredients: readonly string[],
  dietaryTags: readonly string[], contains: readonly string[], popularity: number,
];

type CompactRecipe = readonly [
  category: string, name: string, description: string, price: number, emoji: string,
  spiceLevel: number, tags: readonly string[], ingredients: readonly string[],
  dietaryTags: readonly string[], popularity: number,
];

const vegan = ["vegetarian", "vegan", "no_pork", "no_beef", "no_seafood", "no_dairy"] as const;
const vegetarian = ["vegetarian", "no_pork", "no_beef", "no_seafood"] as const;
const vegetarianNoDairy = ["vegetarian", "no_pork", "no_beef", "no_seafood", "no_dairy"] as const;
const poultry = ["no_pork", "no_beef", "no_seafood", "no_dairy"] as const;
const poultryWithDairy = ["no_pork", "no_beef", "no_seafood"] as const;
const beef = ["no_pork", "no_seafood", "no_dairy"] as const;
const pork = ["no_beef", "no_seafood", "no_dairy"] as const;
const seafood = ["no_pork", "no_beef", "no_dairy"] as const;
const seafoodWithDairy = ["no_pork", "no_beef"] as const;

const compactRecipes: CompactRecipe[] = [
  // Meals: rice, bread, pasta, noodles, salads, meat, fish, and plant-based choices.
  ["식사", "고추장 소불고기 비빔밥", "고추장 소스와 소고기, 채소를 비벼 먹는 밥", 13900, "🌶️", 2, ["warm", "식사", "밥", "매콤", "든든", "직장동료"], ["beef", "rice", "soy", "sesame", "chili"], beef, 59],
  ["식사", "참깨 닭가슴살 비빔밥", "구운 닭가슴살과 채소, 참깨를 곁들인 밥", 11500, "🍚", 0, ["warm", "식사", "밥", "가벼운"], ["chicken", "rice", "sesame", "lettuce"], poultry, 57],
  ["식사", "구운 연어 덮밥", "구운 연어와 간장 소스를 올린 밥", 15900, "🐟", 0, ["warm", "식사", "밥", "해산물", "데이트"], ["salmon", "rice", "soy", "sesame"], seafood, 60],
  ["식사", "매운 참치 김치 볶음밥", "참치와 김치를 볶아 만든 아주 매운 밥", 10900, "🍚", 4, ["warm", "식사", "밥", "매콤", "해산물"], ["tuna", "rice", "kimchi", "chili"], seafood, 54],
  ["식사", "채소 김밥 한 접시", "달걀과 채소를 넣은 작은 김밥", 7900, "🍙", 0, ["cool", "식사", "밥", "가벼운"], ["rice", "egg", "carrot", "cucumber", "sesame"], vegetarianNoDairy, 52],
  ["식사", "달걀 간장 주먹밥", "달걀과 간장을 곁들인 한입 주먹밥", 6500, "🍙", 0, ["warm", "식사", "밥", "kids"], ["rice", "egg", "soy", "sesame"], vegetarianNoDairy, 49],
  ["식사", "버섯 들깨 리소토", "버섯과 들깨, 우유로 만든 크리미한 리소토", 13900, "🍄", 0, ["warm", "식사", "밥", "브런치", "데이트"], ["rice", "mushroom", "perilla", "milk"], vegetarian, 56],
  ["식사", "매콤 두부 현미 덮밥", "두부와 고추로 만든 매콤한 현미밥", 10500, "🌶️", 2, ["warm", "식사", "밥", "매콤"], ["tofu", "brown_rice", "soy", "chili"], vegan, 58],
  ["식사", "순한 닭고기 야채죽", "닭고기와 당근을 푹 익힌 부드러운 죽", 8500, "🥣", 0, ["warm", "식사", "밥", "kids"], ["chicken", "rice", "carrot"], poultry, 48],
  ["식사", "치즈 소시지 오므라이스", "치즈와 돼지고기 소시지를 얹은 달걀 밥", 12500, "🍳", 0, ["warm", "식사", "밥", "든든"], ["pork", "rice", "egg", "milk"], ["no_beef", "no_seafood"], 56],
  ["식사", "구운 채소 퀴노아 볼", "구운 채소와 아몬드를 얹은 퀴노아 볼", 12900, "🥗", 0, ["cool", "식사", "가벼운"], ["quinoa", "broccoli", "tomato", "almond"], vegan, 53],
  ["식사", "병아리콩 아보카도 랩", "병아리콩과 아보카도를 밀 또띠야에 담은 랩", 10900, "🌯", 0, ["cool", "식사", "빵", "브런치"], ["chickpea", "avocado", "wheat"], vegan, 56],
  ["식사", "닭고기 시저 랩", "구운 닭고기와 달걀 소스를 밀 또띠야에 담은 랩", 11900, "🌯", 0, ["cool", "식사", "빵", "직장동료"], ["chicken", "wheat", "milk", "egg", "lettuce"], poultryWithDairy, 55],
  ["식사", "훈제연어 베이글", "훈제연어와 크림치즈를 얹은 베이글", 14900, "🥯", 0, ["cool", "식사", "빵", "브런치", "데이트", "해산물"], ["salmon", "wheat", "milk"], seafoodWithDairy, 58],
  ["식사", "딸기 프렌치토스트", "딸기와 달걀, 우유를 곁들인 달콤한 토스트", 11900, "🍓", 0, ["warm", "식사", "빵", "브런치", "sweet", "데이트"], ["wheat", "milk", "egg", "strawberry"], vegetarian, 57],
  ["식사", "토마토 모차렐라 파니니", "토마토와 모차렐라 치즈를 넣어 구운 빵", 11500, "🥪", 0, ["warm", "식사", "빵", "브런치", "데이트"], ["wheat", "milk", "tomato"], vegetarian, 55],
  ["식사", "매콤 치킨 파니니", "고추 소스와 닭고기를 넣어 구운 치즈 빵", 11900, "🥪", 2, ["warm", "식사", "빵", "매콤"], ["chicken", "wheat", "milk", "chili"], poultryWithDairy, 54],
  ["식사", "버섯 크림 파스타", "버섯과 우유 크림으로 만든 파스타", 13900, "🍝", 0, ["warm", "식사", "데이트"], ["mushroom", "wheat", "milk"], vegetarian, 60],
  ["식사", "해물 토마토 파스타", "새우와 조개를 넣은 토마토 파스타", 15900, "🍝", 1, ["warm", "식사", "해산물", "데이트"], ["shrimp", "clam", "wheat", "tomato"], seafood, 55],
  ["식사", "매운 소고기 우동", "고추와 소고기를 넣은 뜨거운 우동", 12900, "🍜", 3, ["warm", "식사", "든든", "매콤"], ["beef", "wheat", "soy", "chili"], beef, 59],
  ["식사", "시원한 채소 메밀국수", "채소와 참깨를 곁들인 차가운 메밀국수", 10500, "🍜", 0, ["cool", "식사", "가벼운"], ["buckwheat", "wheat", "soy", "sesame", "cucumber"], vegan, 50],
  ["식사", "치킨 카레 플레이트", "닭고기와 채소 카레를 올린 밥", 12900, "🍛", 1, ["warm", "식사", "밥", "든든"], ["chicken", "rice", "carrot", "potato"], poultry, 58],
  ["식사", "코코넛 채소 카레", "코코넛과 병아리콩을 넣은 채소 카레 밥", 11500, "🍛", 1, ["warm", "식사", "밥"], ["coconut", "chickpea", "rice", "tomato"], vegan, 54],
  ["식사", "돼지고기 김치 볶음밥", "돼지고기와 김치를 볶아 만든 밥", 10900, "🍚", 2, ["warm", "식사", "밥", "매콤", "직장동료"], ["pork", "rice", "kimchi", "soy", "chili"], pork, 57],
  ["식사", "소고기 채소 샐러드", "구운 소고기와 채소, 참깨 드레싱", 13900, "🥗", 0, ["cool", "식사", "가벼운"], ["beef", "lettuce", "tomato", "sesame"], beef, 52],
  // Soups and stews: mild/spicy, vegan, dairy, and seafood variants.
  ["국물", "토마토 채소 수프", "토마토와 여러 채소를 끓인 맑은 수프", 6900, "🍅", 0, ["warm", "식사", "soup", "가벼운"], ["tomato", "carrot", "potato"], vegan, 47],
  ["국물", "버섯 크림 수프", "버섯과 우유 크림으로 만든 부드러운 수프", 7900, "🍄", 0, ["warm", "식사", "soup"], ["mushroom", "milk"], vegetarian, 51],
  ["국물", "소고기 미역국", "소고기와 미역을 넣은 따뜻한 국", 8900, "🍲", 0, ["warm", "식사", "soup", "든든"], ["beef", "seaweed"], beef, 55],
  ["국물", "매운 김치 두부찌개", "젓갈 없이 담근 김치와 두부를 끓인 매운 찌개", 9900, "🌶️", 3, ["warm", "식사", "soup", "매콤"], ["tofu", "soy", "kimchi", "chili"], vegan, 53],
  ["국물", "조개 맑은탕", "조개와 무를 넣은 맑은 국물", 11900, "🐚", 0, ["warm", "식사", "soup", "해산물"], ["clam", "radish"], seafood, 48],
  ["국물", "단호박 수프", "단호박과 우유를 넣은 달콤한 수프", 7500, "🎃", 0, ["warm", "식사", "soup", "sweet"], ["pumpkin", "milk"], vegetarian, 50],
  // Sides: contrasting prices, flavors, and allergen profiles.
  ["사이드", "구운 옥수수 컵", "소금만 더해 구운 옥수수", 3900, "🌽", 0, ["warm", "사이드"], ["corn"], vegan, 50],
  ["사이드", "허니 버터 고구마", "꿀과 버터를 얹은 따뜻한 고구마", 4900, "🍠", 0, ["warm", "사이드", "sweet"], ["sweet_potato", "honey", "milk"], vegetarian, 54],
  ["사이드", "매콤 치킨 윙", "고추와 간장 소스로 양념한 치킨 윙", 7900, "🍗", 2, ["warm", "사이드", "매콤"], ["chicken", "chili", "soy"], poultry, 55],
  ["사이드", "미니 새우튀김", "새우에 밀가루 옷을 입혀 튀긴 사이드", 6900, "🦐", 0, ["warm", "사이드", "해산물"], ["shrimp", "wheat", "egg"], seafood, 52],
  ["사이드", "오이 피클", "오이와 식초로 만든 새콤한 피클", 2500, "🥒", 0, ["cool", "사이드", "sour"], ["cucumber", "vinegar"], vegan, 44],
  ["사이드", "후무스 채소스틱", "병아리콩과 참깨 딥을 곁들인 채소", 5900, "🥕", 0, ["cool", "사이드"], ["chickpea", "sesame", "carrot"], vegan, 49],
  ["사이드", "치즈 감자 그라탱", "치즈를 녹여 얹은 구운 감자", 6900, "🧀", 0, ["warm", "사이드"], ["potato", "milk"], vegetarian, 54],
  ["사이드", "견과 에너지볼", "아몬드와 땅콩을 뭉친 달콤한 한입 간식", 4500, "🥜", 0, ["cool", "사이드", "sweet"], ["almond", "peanut", "date_fruit"], vegan, 46],
  // Desserts: fruit, dairy, nuts, sesame, chocolate, and coffee-containing choices.
  ["디저트", "딸기 요거트 파르페", "딸기와 그래놀라를 얹은 요거트", 6500, "🍓", 0, ["cool", "디저트", "sweet"], ["strawberry", "milk", "wheat"], vegetarian, 54],
  ["디저트", "망고 코코넛 푸딩", "망고와 코코넛 우유로 만든 푸딩", 6200, "🥭", 0, ["cool", "디저트", "sweet"], ["mango", "coconut"], vegan, 52],
  ["디저트", "흑임자 아이스크림", "검은 참깨와 우유로 만든 아이스크림", 5900, "🍨", 0, ["cool", "디저트", "sweet"], ["sesame", "milk"], vegetarian, 51],
  ["디저트", "견과 초코 쿠키", "아몬드와 초콜릿을 넣은 쿠키", 3900, "🍪", 0, ["디저트", "sweet"], ["almond", "wheat", "egg", "milk", "cocoa"], vegetarian, 49],
  ["디저트", "레몬 셔벗", "레몬을 갈아 만든 새콤한 얼음 디저트", 4900, "🍋", 0, ["cool", "디저트", "sour"], ["lemon", "water"], vegan, 48],
  ["디저트", "바나나 오트 머핀", "바나나와 귀리로 구운 작은 머핀", 4500, "🧁", 0, ["디저트", "sweet", "빵"], ["banana", "oat", "wheat", "egg", "milk"], vegetarian, 53],
  ["디저트", "티라미수 컵", "커피와 크림을 층층이 담은 티라미수", 6900, "🍮", 0, ["cool", "디저트", "sweet"], ["coffee", "milk", "egg", "wheat"], vegetarian, 55],
  ["디저트", "복숭아 과일 젤리", "복숭아 과즙으로 만든 시원한 젤리", 4500, "🍑", 0, ["cool", "디저트", "sweet"], ["peach", "water"], vegan, 47],
  // Drinks: distinct caffeine states. Decaf is not marked caffeine-free.
  ["음료", "디카페인 아이스 아메리카노", "디카페인 원두로 만든 차가운 커피", 4500, "☕", 0, ["cool", "음료", "coffee", "decaf"], ["coffee", "water"], vegan, 53],
  ["음료", "딸기 우유", "딸기와 우유로 만든 달콤한 음료", 4900, "🥛", 0, ["cool", "음료", "caffeine_free", "sweet"], ["strawberry", "milk"], vegetarian, 56],
  ["음료", "바나나 쉐이크", "바나나와 우유를 갈아 만든 달콤한 쉐이크", 5500, "🍌", 0, ["cool", "음료", "caffeine_free", "sweet"], ["banana", "milk"], vegetarian, 52],
  ["음료", "레몬 에이드", "레몬으로 만든 새콤한 탄산 음료", 4700, "🍋", 0, ["cool", "음료", "caffeine_free", "sour"], ["lemon", "water"], vegan, 54],
  ["음료", "자몽 스파클링", "자몽 탄산으로 만든 새콤한 음료", 5200, "🍊", 0, ["cool", "음료", "caffeine_free", "sour"], ["grapefruit", "water"], vegan, 50],
  ["음료", "따뜻한 보리차", "보리를 우려낸 무카페인 차", 2500, "🍵", 0, ["warm", "음료", "caffeine_free"], ["barley", "water"], vegan, 45],
  ["음료", "민트 허브티", "민트 잎을 우려낸 카페인 없는 차", 3900, "🍵", 0, ["warm", "음료", "caffeine_free"], ["mint", "water"], vegan, 46],
  ["음료", "초코 라떼", "우유와 코코아를 섞은 달콤한 음료", 5500, "🍫", 0, ["warm", "음료", "sweet"], ["milk", "cocoa"], vegetarian, 55],
  ["음료", "아몬드 밀크", "아몬드와 물로 만든 고소한 음료", 4900, "🥛", 0, ["cool", "음료", "caffeine_free"], ["almond", "water"], vegan, 48],
];

const allergenByIngredient: Record<string, string> = {
  soy: "soy", tofu: "soy", milk: "milk", egg: "egg", wheat: "wheat",
  shrimp: "shellfish", crab: "shellfish", clam: "mollusk",
  fish: "fish", salmon: "fish", tuna: "fish",
  peanut: "peanut", almond: "tree_nut", walnut: "tree_nut", sesame: "sesame",
};

export const scenarioRecipes: DemoRecipe[] = compactRecipes.map(([
  category, name, description, price, emoji, spiceLevel, tags, ingredients, dietaryTags, popularity,
]) => [category, name, description, price, emoji, spiceLevel, tags, ingredients, dietaryTags,
  [...new Set(ingredients.map((ingredient) => allergenByIngredient[ingredient]).filter((key): key is string => !!key))], popularity]);
