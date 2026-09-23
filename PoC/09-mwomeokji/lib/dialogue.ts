import { ALLERGENS, type GroupMember, type OrderIntent } from './types';

export type VisitMode = 'dine_in' | 'takeout';
export type SuggestedItem = { id: string; forMember?: string };
export type DialogueState = {
  peopleCount?: number;
  members: GroupMember[];
  preferences: OrderIntent;
  lastRecommendations: SuggestedItem[];
  pendingCheckout: boolean;
  pendingCheckoutSignature?: string;
};

const numberWords: Record<string, number> = { 한: 1, 두: 2, 세: 3, 네: 4, 하나: 1, 둘: 2, 셋: 3, 넷: 4 };
const countOf = (value: string) => Number(value) || numberWords[value] || 1;
const emptyDialogue = (): DialogueState => ({ members: [], preferences: { action: 'recommend' }, lastRecommendations: [], pendingCheckout: false });

export function readDialogue(context: unknown): DialogueState {
  if (!context || typeof context !== 'object' || Array.isArray(context) || !('dialogue' in context)) return emptyDialogue();
  const value = context.dialogue;
  if (!value || typeof value !== 'object' || Array.isArray(value)) return emptyDialogue();
  const record = value as Record<string, unknown>;
  const members = Array.isArray(record.members) ? record.members.filter((member): member is GroupMember => !!member && typeof member === 'object' && !Array.isArray(member) && typeof member.id === 'string' && typeof member.label === 'string' && Array.isArray(member.allergies) && Array.isArray(member.dietaryRules)) : [];
  const lastRecommendations = Array.isArray(record.lastRecommendations) ? record.lastRecommendations.filter((item): item is SuggestedItem => !!item && typeof item === 'object' && !Array.isArray(item) && typeof item.id === 'string') : [];
  const preferences = record.preferences && typeof record.preferences === 'object' && !Array.isArray(record.preferences) ? record.preferences as OrderIntent : { action: 'recommend' as const };
  return { peopleCount: typeof record.peopleCount === 'number' ? Math.min(12, Math.max(1, record.peopleCount)) : undefined, members: members.slice(0, 12), preferences, lastRecommendations: lastRecommendations.slice(0, 12), pendingCheckout: record.pendingCheckout === true, pendingCheckoutSignature: typeof record.pendingCheckoutSignature === "string" ? record.pendingCheckoutSignature : undefined };
}

function conditions(text: string) {
  const allergies = /알레르기|못\s*먹|빼|제외/.test(text) ? ALLERGENS.filter(([, label]) => text.includes(label)).map(([key]) => key) : [];
  const dietaryRules: GroupMember['dietaryRules'] = [];
  if (/비건|vegan/.test(text)) dietaryRules.push({ type: 'vegan', mode: 'strict' });
  else if (/채식|vegetarian/.test(text)) dietaryRules.push({ type: 'vegetarian', mode: 'strict' });
  if (/돼지고기.*(안|못|빼|제외)|no pork/.test(text)) dietaryRules.push({ type: 'no_pork', mode: 'strict' });
  if (/소고기.*(안|못|빼|제외)|no beef/.test(text)) dietaryRules.push({ type: 'no_beef', mode: 'strict' });
  if (/해산물.*(안|못|빼|제외)/.test(text)) dietaryRules.push({ type: 'no_seafood', mode: 'strict' });
  if (/유제품.*(안|못|빼|제외)/.test(text)) dietaryRules.push({ type: 'no_dairy', mode: 'strict' });
  const maxSpiceLevel = /매운.*(못|안)|맵.*(못|안)|안\s*맵|순한|맵지/.test(text) ? 0 : undefined;
  return { allergies, dietaryRules, maxSpiceLevel };
}

function describe(member: Pick<GroupMember, 'allergies' | 'dietaryRules' | 'maxSpiceLevel'>, index: number) {
  if (member.allergies.length) return `${ALLERGENS.find(([key]) => key === member.allergies[0])?.[1] || '알레르기'} 알레르기 있는 분${index > 1 ? ` ${index}` : ''}`;
  if (member.dietaryRules.some((rule) => rule.type === 'vegan')) return `비건인 분${index > 1 ? ` ${index}` : ''}`;
  if (member.dietaryRules.some((rule) => rule.type === 'vegetarian')) return `채식하는 분${index > 1 ? ` ${index}` : ''}`;
  if (member.maxSpiceLevel !== undefined) return `매운 음식 못 먹는 분${index > 1 ? ` ${index}` : ''}`;
  return `일행 ${index}`;
}

export function evolveDialogue(previous: DialogueState, message: string, parsed: OrderIntent) {
  const text = message.trim().toLowerCase();
  const clauses = [...text.matchAll(/(한|두|세|네|하나|둘|셋|넷|\d+)\s*명(?:은|만)\s*(.*?)(?=(?:한|두|세|네|하나|둘|셋|넷|\d+)\s*명(?:은|만)|[,，.;]|$)/g)];
  const specified: GroupMember[] = [];
  for (const clause of clauses) {
    const count = Math.min(12, countOf(clause[1]));
    const details = conditions(clause[2]);
    if (!details.allergies.length && !details.dietaryRules.length && details.maxSpiceLevel === undefined) continue;
    for (let index = 0; index < count; index++) specified.push({ id: `spoken-${previous.members.filter((entry) => entry.id.startsWith("spoken-")).length + specified.length + 1}`, label: describe(details, index + 1), ...details });
  }
  const children = text.match(/아이\s*(둘|셋|넷|두|세|네|\d+)\s*(?:명)?/);
  const adults = text.match(/어른\s*(둘|셋|넷|두|세|네|\d+)\s*(?:명)?/);
  const familyCount = (children ? countOf(children[1]) : 0) + (adults ? countOf(adults[1]) : 0);
  const casualCount = text.match(/(?:우리|저희)?\s*(둘|셋|넷)이(?:요|에요|에|서)?/);
  const explicitTotal = text.match(/(?:우리|저희|총|전체|모두)\s*(\d+|한|두|세|네|하나|둘|셋|넷)\s*명/);
  const leadingCount = text.slice(0, clauses[0]?.index ?? text.length).match(/(\d+|한|두|세|네|하나|둘|셋|넷)\s*명/);
  const inferredCount = explicitTotal ? countOf(explicitTotal[1]) : leadingCount ? countOf(leadingCount[1]) : specified.length ? 0 : parsed.peopleCount || 0;
  const peopleCount = Math.min(12, inferredCount || familyCount || (casualCount ? countOf(casualCount[1]) : 0) || previous.peopleCount || 0) || undefined;
  let members = previous.members;
  if (specified.length) {
    const existingSpecific = previous.members.filter((member) => !member.id.startsWith('generic-'));
    members = [...existingSpecific];
    for (const member of specified) if (!members.some((current) => current.label === member.label && JSON.stringify(current.allergies) === JSON.stringify(member.allergies) && JSON.stringify(current.dietaryRules) === JSON.stringify(member.dietaryRules))) members.push(member);
  }
  if (children && adults && !specified.length && !previous.members.length) {
    members = [
      ...Array.from({ length: countOf(children[1]) }, (_, index) => ({ id: `child-${index + 1}`, label: `아이 ${index + 1}`, allergies: [], dietaryRules: [] })),
      ...Array.from({ length: countOf(adults[1]) }, (_, index) => ({ id: `adult-${index + 1}`, label: `어른 ${index + 1}`, allergies: [], dietaryRules: [] }))
    ];
  }
  if (/아이는?\s*매운.*못|아이들은?\s*매운.*못/.test(text)) members = members.map((member) => member.id.startsWith('child-') ? { ...member, maxSpiceLevel: 0 } : member);
  if (peopleCount) {
    members = members.slice(0, peopleCount);
    while (members.length < peopleCount) members.push({ id: `generic-${members.length + 1}`, label: `일행 ${members.length + 1}`, allergies: [], dietaryRules: [] });
  }
  const preferences: OrderIntent = { ...previous.preferences, action: 'recommend' };
  for (const key of ['totalBudget','maxSpiceLevel','peopleCount','category','wantsWarm','wantsCool','wantsMild','vegetarian','avoidPork','avoidBeef'] as const) {
    const value = parsed[key];
    if (value !== undefined && value !== false) Object.assign(preferences, { [key]: value });
  }
  if (specified.length) {
    if (specified.some((member) => member.dietaryRules.some((rule) => rule.type === 'vegetarian' || rule.type === 'vegan'))) preferences.vegetarian = false;
    if (specified.some((member) => member.maxSpiceLevel !== undefined)) preferences.maxSpiceLevel = undefined;
  }
  if (peopleCount) preferences.peopleCount = peopleCount;
  const globalAllergies = specified.length ? [] : conditions(text).allergies;
  const needsPeopleCount = specified.length > 0 && !peopleCount;
  const onlyHeadcount = !!peopleCount && !specified.length && !/추천|메뉴|먹|밥|국물|따뜻|시원|매운|채식|비건|원|달|파스타|샐러드|치킨|음료/.test(text);
  return { state: { ...previous, peopleCount, members, preferences }, globalAllergies, needsPeopleCount, onlyHeadcount };
}

export function contextSummary(state: DialogueState, mode: VisitMode | null) {
  const result: string[] = [];
  if (mode) result.push(mode === 'dine_in' ? '먹고 가기' : '가져가기');
  if (state.peopleCount) result.push(`${state.peopleCount}명`);
  if (state.preferences.totalBudget) result.push(`예산 ${state.preferences.totalBudget.toLocaleString('ko-KR')}원`);
  if (state.preferences.wantsWarm) result.push('따뜻한 음식');
  if (state.preferences.maxSpiceLevel !== undefined) result.push('순한 맛');
  for (const member of state.members.filter((entry) => !entry.id.startsWith('generic-'))) result.push(member.label);
  return result.slice(0, 8);
}
