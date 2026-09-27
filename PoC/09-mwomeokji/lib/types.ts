export const ALLERGENS = [
  ["peanut", "땅콩"],
  ["tree_nut", "견과류"],
  ["milk", "우유"],
  ["egg", "달걀"],
  ["soy", "대두"],
  ["wheat", "밀"],
  ["shellfish", "갑각류"],
  ["mollusk", "조개류"],
  ["fish", "생선"],
  ["sesame", "참깨"],
] as const;

export const DIET_RULES = [
  ["vegetarian", "채식"],
  ["vegan", "비건"],
  ["no_pork", "돼지고기 제외"],
  ["no_beef", "소고기 제외"],
  ["no_seafood", "해산물 제외"],
  ["no_dairy", "유제품 제외"],
] as const;

export type AllergenRecord = {
  allergenKey: string;
  relation: string;
  verificationStatus: string;
};
export type MenuOptionData = {
  id: string;
  name: string;
  priceDelta: number;
  isAvailable: boolean;
  ingredients: string[];
  dietaryTags: string[];
  allergens: AllergenRecord[];
};
export type OptionGroupData = {
  id: string;
  name: string;
  minSelect: number;
  maxSelect: number;
  options: MenuOptionData[];
};
export type MenuItemData = {
  id: string;
  storeId: string;
  categoryId: string;
  name: string;
  description: string;
  price: number;
  emoji: string;
  imageUrl: string | null;
  spiceLevel: number;
  isAvailable: boolean;
  isPublished: boolean;
  isShareable: boolean;
  popularity: number;
  tags: string[];
  ingredients: string[];
  dietaryTags: string[];
  allergens: AllergenRecord[];
  options: OptionGroupData[];
};
export type DietaryRule = { type: string; mode: "strict" | "prefer" };
export type PreferenceProfile = {
  allergies: string[];
  dietaryRules: DietaryRule[];
  spicePreference: number;
  maxSpiceLevel?: number;
  budget?: number;
  largeText?: boolean;
  locale?: "ko" | "en";
};
export type GroupMember = {
  id: string;
  label: string;
  allergies: string[];
  dietaryRules: DietaryRule[];
  maxSpiceLevel?: number;
  tastes?: Array<"spicy" | "mild" | "sweet" | "soup" | "rice" | "kids">;
};
export type OrderIntent = {
  action: "recommend" | "add" | "remove" | "ask" | "help" | "checkout";
  peopleCount?: number;
  totalBudget?: number;
  maxSpiceLevel?: number;
  wantsWarm?: boolean;
  wantsCool?: boolean;
  wantsMild?: boolean;
  vegetarian?: boolean;
  avoidPork?: boolean;
  avoidBeef?: boolean;
  category?: string;
  menuName?: string;
  quantity?: number;
  coffee?: boolean;
  caffeineFree?: boolean;
  decaf?: boolean;
  wantsSweet?: boolean;
  avoidSour?: boolean;
};
export type Recommendation = {
  item: MenuItemData;
  quantity?: number;
  unit?: "잔" | "개";
  score: number;
  reason: string;
  forMember?: string;
};
export const newEmptyProfile = (): PreferenceProfile => ({
  allergies: [],
  dietaryRules: [],
  spicePreference: 2,
  locale: "ko",
});
export const emptyProfile: PreferenceProfile = newEmptyProfile();
