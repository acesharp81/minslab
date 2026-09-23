import type {
  AllergenRecord,
  MenuItemData,
  MenuOptionData,
  PreferenceProfile,
} from "./types";

export type SafetyResult = {
  allowed: boolean;
  reasons: string[];
  verifiedAllergens: string[];
};

function isVerifiedAbsent(records: AllergenRecord[], key: string): boolean {
  const record = records.find((entry) => entry.allergenKey === key);
  return (
    record?.verificationStatus === "merchant_verified" &&
    record.relation === "excludes"
  );
}

function dietTag(rule: string): string {
  return rule === "avoid_pork"
    ? "no_pork"
    : rule === "avoid_beef"
      ? "no_beef"
      : rule === "avoid_seafood"
        ? "no_seafood"
        : rule === "avoid_dairy"
          ? "no_dairy"
          : rule;
}

function optionPasses(
  option: MenuOptionData,
  profile: PreferenceProfile,
): boolean {
  if (!option.isAvailable) return false;
  if (profile.allergies.some((key) => !isVerifiedAbsent(option.allergens, key)))
    return false;
  return profile.dietaryRules
    .filter((rule) => rule.mode === "strict")
    .every((rule) => option.dietaryTags.includes(dietTag(rule.type)));
}

export function checkSafety(
  item: MenuItemData,
  profile: PreferenceProfile,
  selectedOptionIds?: string[],
): SafetyResult {
  const reasons: string[] = [];
  if (!item.isAvailable || !item.isPublished)
    reasons.push("품절 또는 비공개 메뉴");
  if (
    profile.maxSpiceLevel !== undefined &&
    item.spiceLevel > profile.maxSpiceLevel
  )
    reasons.push("요청한 맵기보다 매움");
  for (const key of profile.allergies)
    if (!isVerifiedAbsent(item.allergens, key))
      reasons.push(`${key} 성분 미확인 또는 포함`);
  for (const rule of profile.dietaryRules.filter(
    (entry) => entry.mode === "strict",
  )) {
    if (!item.dietaryTags.includes(dietTag(rule.type)))
      reasons.push(`${rule.type} 식이조건 미확인`);
  }
  for (const group of item.options) {
    const selected = group.options.filter((option) =>
      selectedOptionIds?.includes(option.id),
    );
    if (selectedOptionIds) {
      if (
        selected.length < group.minSelect ||
        selected.length > group.maxSelect
      )
        reasons.push(`${group.name} 옵션 선택 오류`);
      if (selected.some((option) => !optionPasses(option, profile)))
        reasons.push(`${group.name} 옵션 조건 미확인`);
    } else if (
      group.minSelect > 0 &&
      group.options.filter((option) => optionPasses(option, profile)).length <
        group.minSelect
    ) {
      reasons.push(`${group.name}에서 조건에 맞는 필수 옵션 없음`);
    }
  }
  if (selectedOptionIds) {
    const allIds = new Set(
      item.options.flatMap((group) => group.options.map((option) => option.id)),
    );
    if (selectedOptionIds.some((id) => !allIds.has(id)))
      reasons.push("존재하지 않는 옵션");
  }
  return {
    allowed: reasons.length === 0,
    reasons,
    verifiedAllergens: profile.allergies.filter((key) =>
      isVerifiedAbsent(item.allergens, key),
    ),
  };
}

export function priceFor(
  item: MenuItemData,
  selectedOptionIds: string[],
): number {
  const choices = item.options
    .flatMap((group) => group.options)
    .filter((option) => selectedOptionIds.includes(option.id));
  return (
    item.price + choices.reduce((sum, option) => sum + option.priceDelta, 0)
  );
}
