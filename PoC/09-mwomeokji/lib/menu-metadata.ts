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

/** Merchant supplied recommendation words. Built-in safety and course tags are not spoken menu styles. */
export const builtInMenuTags = new Set([
  "식사", "음료", "사이드", "디저트", "warm", "cool", "coffee", "decaf",
  "caffeine_free", "sweet", "sour", "spicy", "rice", "soup", "kids",
]);

export function spokenMenuLabels(items: Array<{ tags: string[] }>, message: string): { wanted: string[]; excluded: string[] } {
  const text = message.toLocaleLowerCase();
  const labels = [...new Set(items.flatMap((item) => item.tags))]
    .filter((tag) => (tag.length >= 2 || /^[가-힣]$/.test(tag)) && !builtInMenuTags.has(tag));
  const wanted: string[] = [];
  const excluded: string[] = [];
  for (const label of labels) {
    let offset = text.indexOf(label.toLocaleLowerCase());
    // A one-syllable label such as 밥 must not match the suffix in 덮밥.
    while (offset > 0 && label.length === 1 && /[가-힣]/.test(text[offset - 1]))
      offset = text.indexOf(label.toLocaleLowerCase(), offset + 1);
    if (offset < 0) continue;
    const after = text.slice(offset + label.length);
    if (/^\s*(?:말고|빼고|제외|아닌|아니고)/.test(after)) excluded.push(label);
    else wanted.push(label);
  }
  return { wanted, excluded };
}

/** Catalog-derived dish nouns: a spoken exact type must remain inside that dish family. */
export function spokenCatalogDishKinds(items: Array<{ name: string }>, utterance: string): string[] {
  const endings = [...new Set(items.map((item) => item.name.trim().split(/\s+/).at(-1) || ""))]
    .filter((ending) => ending.length >= 2);
  return endings.filter((ending) => {
    const index = utterance.indexOf(ending);
    if (index < 0) return false;
    const following = utterance.slice(index + ending.length);
    return !/^(?:은|는|이|가|도)?\s*(?:말고|빼고|제외|별로|싫|아닌)/.test(following);
  });
}

/** A clearly named product outside the published catalog must not become a popular substitute. */
export function unavailableSpokenDish(items: Array<{ name: string; tags: string[] }>, utterance: string): string | null {
  const phrase = utterance.match(/([^.!?]{2,40}?)(?:를|을)\s*(?:마시|먹)고\s*싶/);
  if (!phrase) return null;
  const noun = phrase[1].trim().split(/\s+/).at(-1) || "";
  if (!noun || /^(?:메뉴|음식|식사|밥|음료|간식|디저트)$/.test(noun)) return null;
  return items.some((item) => item.name.includes(noun) || item.tags.includes(noun)) ? null : noun;
}
