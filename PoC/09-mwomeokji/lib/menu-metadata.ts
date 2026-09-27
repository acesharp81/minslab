/** Normalize merchant-maintained menu labels used by the recommendation guard. */
const menuCategoryTags = new Set(["식사", "음료", "사이드", "디저트"]);

export function catalogTags(tags: string[], categoryName: string): string[] {
  return [...new Set([...tags.filter((tag) => !menuCategoryTags.has(tag)), categoryName])];
}

export function validCaffeineTags(tags: string[], categoryName: string): boolean {
  const decaf = tags.includes("decaf");
  const caffeineFree = tags.includes("caffeine_free");
  if ((decaf || caffeineFree) && categoryName !== "음료") return false;
  if (decaf && !tags.includes("coffee")) return false;
  return !(decaf && caffeineFree);
}
