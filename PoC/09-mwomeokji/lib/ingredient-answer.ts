import type { DialogueState } from "./dialogue";
import type { MenuItemData } from "./types";

type CartReference = {
  menuItemId: string;
  assignedTo: string | null;
  selectedOptionIds: string[];
};

type IngredientQuery = { label: string; names: string[]; allergenKey?: string };

const ingredients: IngredientQuery[] = [
  { label: "오이", names: ["오이", "cucumber"] },
  { label: "땅콩", names: ["땅콩", "peanut"], allergenKey: "peanut" },
  { label: "견과류", names: ["견과류", "tree_nut"], allergenKey: "tree_nut" },
  { label: "우유", names: ["우유", "milk"], allergenKey: "milk" },
  { label: "달걀", names: ["달걀", "계란", "egg"], allergenKey: "egg" },
  { label: "대두", names: ["대두", "콩", "soy"], allergenKey: "soy" },
  { label: "밀", names: ["밀", "wheat"], allergenKey: "wheat" },
  { label: "새우", names: ["새우", "shrimp"], allergenKey: "shellfish" },
  { label: "생선", names: ["생선", "fish"], allergenKey: "fish" },
  { label: "참깨", names: ["참깨", "sesame"], allergenKey: "sesame" },
  { label: "닭고기", names: ["닭고기", "chicken"] },
  { label: "돼지고기", names: ["돼지고기", "pork"] },
  { label: "소고기", names: ["소고기", "beef"] },
  { label: "감자", names: ["감자", "potato"] },
  { label: "버섯", names: ["버섯", "mushroom"] },
  { label: "두부", names: ["두부", "tofu"] },
  { label: "토마토", names: ["토마토", "tomato"] },
];

export function ingredientQuestion(message: string): IngredientQuery | null {
  const text = message.trim().toLowerCase();
  if (!/들어|들었|포함|재료|성분|있는지|있나요|있어\??/.test(text)) return null;
  const known = ingredients.find((entry) => entry.names.some((name) => text.includes(name)));
  if (known) return known;
  const spoken = text.match(/(?:^|\s)([가-힣]{2,12}?)(?:이|가)?\s*(?:들어|들었|포함)/)?.[1];
  return spoken ? { label: spoken, names: [spoken] } : null;
}

export function answerIngredientQuestion(
  message: string,
  question: IngredientQuery,
  dialogue: DialogueState,
  menu: MenuItemData[],
  cart: CartReference[],
): string {
  const lower = message.toLowerCase();
  const byId = new Map(menu.map((item) => [item.id, item]));
  const explicit = menu.filter((item) => lower.includes(item.name.toLowerCase()));
  const mine = /(?:^|\s)(?:내|제|나|저)(?:꺼|것|메뉴|음식)?(?:에|의|는|은|도|\s|$)/.test(lower);
  const ownLabels = new Set(dialogue.members.filter((member) => /^(나|저)$/.test(member.label)).map((member) => member.label));
  const choose = (references: Array<{ item: MenuItemData; selectedOptionIds?: string[] }>) => {
    if (references.length === 1) return references[0];
    if (references.length > 1) return null;
    return undefined;
  };
  const cartChoices = cart.filter((entry) => entry.assignedTo && ownLabels.has(entry.assignedTo)).map((entry) => ({ item: byId.get(entry.menuItemId), selectedOptionIds: entry.selectedOptionIds })).filter((entry): entry is { item: MenuItemData; selectedOptionIds: string[] } => !!entry.item);
  const recommendationChoices = dialogue.lastRecommendations.filter((entry) => entry.forMember && ownLabels.has(entry.forMember)).map((entry) => ({ item: byId.get(entry.id) })).filter((entry): entry is { item: MenuItemData } => !!entry.item);
  let target = choose(explicit.map((item) => ({ item })));
  const ordinal = /첫\s*번째|1\s*번/.test(lower) ? 0 : /두\s*번째|2\s*번/.test(lower) ? 1 : /세\s*번째|3\s*번/.test(lower) ? 2 : undefined;
  if (target === undefined && ordinal !== undefined) {
    const reference = dialogue.lastRecommendations[ordinal];
    target = reference && byId.has(reference.id) ? { item: byId.get(reference.id)! } : undefined;
  }
  if (target === undefined && mine) target = choose(cartChoices);
  if (target === undefined && mine) target = choose(recommendationChoices);
  if (target === undefined && (dialogue.peopleCount || 1) === 1) target = choose(cart.map((entry) => ({ item: byId.get(entry.menuItemId), selectedOptionIds: entry.selectedOptionIds })).filter((entry): entry is { item: MenuItemData; selectedOptionIds: string[] } => !!entry.item));
  if (target === undefined && (dialogue.peopleCount || 1) === 1) target = choose(dialogue.lastRecommendations.map((entry) => ({ item: byId.get(entry.id) })).filter((entry): entry is { item: MenuItemData } => !!entry.item));
  if (!target) return mine && !ownLabels.size && (dialogue.peopleCount || 1) > 1
    ? "어느 분의 메뉴가 본인 것인지 아직 모르겠어요. 메뉴 이름이나 추천 번호를 말씀해 주세요."
    : "어느 메뉴인지 알려 주세요. 메뉴 이름이나 추천 번호를 말씀해 주시면 재료를 확인할게요.";

  const selectedOptions = target.selectedOptionIds
    ? target.item.options.flatMap((group) => group.options).filter((option) => target.selectedOptionIds!.includes(option.id))
    : [];
  const listed = [...target.item.ingredients, ...selectedOptions.flatMap((option) => option.ingredients)]
    .some((ingredient) => question.names.some((name) => ingredient.toLowerCase() === name.toLowerCase()));
  const markedAllergen = question.allergenKey && [target.item, ...selectedOptions].some((source) => source.allergens.some((record) => record.allergenKey === question.allergenKey && record.relation === "contains"));
  if (listed || markedAllergen) return `${target.item.name}의 등록된 재료${selectedOptions.length ? "와 선택한 옵션" : ""}에서 ${question.label} 표기를 확인했어요.`;
  return `${target.item.name}의 등록된 재료${selectedOptions.length ? "와 선택한 옵션" : ""}에서 ${question.label} 표기를 찾지 못했어요. 실제 미포함 여부는 확인되지 않았으니 사장님께 확인해 주세요.`;
}
