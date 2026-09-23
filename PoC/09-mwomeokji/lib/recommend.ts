import { checkSafety } from "./safety";
import type {
  GroupMember,
  MenuItemData,
  OrderIntent,
  PreferenceProfile,
  Recommendation,
} from "./types";

function withIntent(
  profile: PreferenceProfile,
  intent: OrderIntent,
): PreferenceProfile {
  const dietaryRules = [...profile.dietaryRules];
  if (intent.vegetarian)
    dietaryRules.push({ type: "vegetarian", mode: "strict" });
  if (intent.avoidPork) dietaryRules.push({ type: "no_pork", mode: "strict" });
  if (intent.avoidBeef) dietaryRules.push({ type: "no_beef", mode: "strict" });
  return {
    ...profile,
    dietaryRules,
    maxSpiceLevel: intent.maxSpiceLevel ?? profile.maxSpiceLevel,
  };
}

function score(
  item: MenuItemData,
  intent: OrderIntent,
  profile: PreferenceProfile,
): number {
  let value = item.popularity;
  if (intent.wantsWarm && item.tags.includes("warm")) value += 24;
  if (intent.wantsCool && item.tags.includes("cool")) value += 24;
  if (intent.wantsMild && item.spiceLevel <= 1) value += 15;
  if (intent.category && item.tags.includes(intent.category)) value += 12;
  if (item.spiceLevel === profile.spicePreference) value += 8;
  if (item.isShareable && (intent.peopleCount ?? 1) > 1) value += 8;
  if (
    intent.totalBudget &&
    item.price <= intent.totalBudget / Math.max(1, intent.peopleCount ?? 1)
  )
    value += 12;
  return value;
}

function reason(item: MenuItemData, intent: OrderIntent): string {
  const reasons: string[] = [];
  if (intent.wantsWarm && item.tags.includes("warm"))
    reasons.push("따뜻한 메뉴");
  if (intent.wantsCool && item.tags.includes("cool"))
    reasons.push("시원한 메뉴");
  if (intent.wantsMild && item.spiceLevel <= 1) reasons.push("맵기 1 이하");
  if (intent.totalBudget)
    reasons.push(`${item.price.toLocaleString("ko-KR")}원`);
  if (!reasons.length) reasons.push("많이 찾는 메뉴");
  return `${reasons.join(" · ")}라서 골랐어요.`;
}

export function recommend(
  items: MenuItemData[],
  profile: PreferenceProfile,
  intent: OrderIntent,
  limit = 5,
): Recommendation[] {
  const current = withIntent(profile, intent);
  const budget = intent.totalBudget ?? profile.budget;
  const individualBudget =
    budget && (intent.peopleCount ?? 1) > 1
      ? Math.floor(budget / (intent.peopleCount ?? 1))
      : budget;
  return items
    .filter(
      (item) =>
        checkSafety(item, current).allowed &&
        (!individualBudget || item.price <= individualBudget),
    )
    .map((item) => ({
      item,
      score: score(item, intent, current),
      reason: reason(item, intent),
    }))
    .sort((a, b) => b.score - a.score || a.item.price - b.item.price)
    .slice(0, limit);
}

export function recommendGroup(
  items: MenuItemData[],
  profile: PreferenceProfile,
  intent: OrderIntent,
  members: GroupMember[],
) {
  const people: GroupMember[] = members.length
    ? members
    : Array.from(
        { length: Math.min(12, Math.max(1, intent.peopleCount || 1)) },
        (_, index) => ({
          id: String(index),
          label: `${index + 1}번 손님`,
          allergies: [],
          dietaryRules: [],
        }),
      );
  const totalBudget = intent.totalBudget ?? profile.budget;
  type State = {
    items: Recommendation[];
    total: number;
    score: number;
    used: Set<string>;
  };
  let states: State[] = [{ items: [], total: 0, score: 0, used: new Set() }];
  for (const member of people) {
    const memberProfile: PreferenceProfile = {
      ...profile,
      allergies: [...new Set([...profile.allergies, ...member.allergies])],
      dietaryRules: [...profile.dietaryRules, ...member.dietaryRules],
      maxSpiceLevel: member.maxSpiceLevel ?? profile.maxSpiceLevel,
    };
    const choices = recommend(
      items,
      memberProfile,
      { ...intent, peopleCount: 1, totalBudget: undefined },
      10,
    );
    const next: State[] = [];
    for (const state of states)
      for (const choice of choices) {
        const total = state.total + choice.item.price;
        if (totalBudget && total > totalBudget) continue;
        next.push({
          items: [...state.items, { ...choice, forMember: member.label }],
          total,
          score:
            state.score +
            choice.score -
            (state.used.has(choice.item.id) ? 8 : 0),
          used: new Set([...state.used, choice.item.id]),
        });
      }
    if (!next.length) return { items: [], total: 0, complete: false };
    states = next
      .sort((a, b) => b.score - a.score || a.total - b.total)
      .slice(0, 32);
  }
  const best = states[0];
  return { items: best.items, total: best.total, complete: true };
}
