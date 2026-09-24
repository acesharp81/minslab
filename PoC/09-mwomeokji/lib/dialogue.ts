import { ALLERGENS, DIET_RULES, type GroupMember, type OrderIntent } from './types';

export type VisitMode = 'dine_in' | 'takeout';
export type SuggestedItem = { id: string; forMember?: string };
export type DialogueState = {
  peopleCount?: number;
  members: GroupMember[];
  preferences: OrderIntent;
  lastRecommendations: SuggestedItem[];
  pendingCheckout: boolean;
  pendingCheckoutSignature?: string;
  lastMemberLabel?: string;
};
export type MemberUpdate = {
  label: string;
  count: number;
  allergies: string[];
  dietaryRules: string[];
  maxSpiceLevel: number | null;
  removeDietaryRules: string[];
  clearSpiceLimit: boolean;
  tastes?: GroupMember["tastes"];
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
  return { peopleCount: typeof record.peopleCount === 'number' ? Math.min(12, Math.max(1, record.peopleCount)) : undefined, members: members.slice(0, 12), preferences, lastRecommendations: lastRecommendations.slice(0, 12), pendingCheckout: record.pendingCheckout === true, pendingCheckoutSignature: typeof record.pendingCheckoutSignature === "string" ? record.pendingCheckoutSignature : undefined, lastMemberLabel: typeof record.lastMemberLabel === "string" ? record.lastMemberLabel.slice(0, 40) : undefined };
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
  const joined = text.match(/(\d+|한|두|세|네|하나|둘|셋|넷)\s*명(?:이|은)?\s*(?:더|추가|합류|왔|늘었)/);
  const left = text.match(/(\d+|한|두|세|네|하나|둘|셋|넷)\s*명(?:이|은)?\s*(?:빠졌|갔|취소|줄었)/);
  const changedCount = previous.peopleCount && (joined || left)
    ? Math.max(1, previous.peopleCount + (joined ? countOf(joined[1]) : -countOf(left![1])))
    : undefined;
  let inferredCount = 0;
  if (explicitTotal) inferredCount = countOf(explicitTotal[1]);
  else if (changedCount !== undefined) inferredCount = changedCount;
  else if (leadingCount) inferredCount = countOf(leadingCount[1]);
  else if (!specified.length) inferredCount = parsed.peopleCount || 0;
  // Family roles can establish a party without a spoken headcount. Age ("2살") is not a count.
  const familyRoles = [/(?:^|\s)(?:나|저|제가|나는|저는)(?:랑|와|과|는|도|\s|$)/.test(text), /와이프|아내|남편|배우자|신랑/.test(text), /아이|아기|딸|아들|여아|남아|키즈/.test(text)].filter(Boolean).length;
  if (!explicitTotal && changedCount === undefined && !leadingCount && familyRoles >= 2) inferredCount = Math.max(inferredCount, familyRoles);
  const rawPeopleCount = inferredCount || familyCount || (casualCount ? countOf(casualCount[1]) : 0) || previous.peopleCount || 0;
  const peopleCount = rawPeopleCount ? Math.min(12, Math.max(1, rawPeopleCount)) : undefined;
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
  if (/말고|아니|대신/.test(text)) {
    if (parsed.wantsCool && /따뜻|뜨끈|국물/.test(text)) preferences.wantsWarm = false;
    if (parsed.wantsWarm && /시원|차가운/.test(text)) preferences.wantsCool = false;
  }
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

/** Apply only bounded, attributable member facts from the model. Rules still validate every menu and option. */
export function applyMemberUpdates(state: DialogueState, updates: MemberUpdate[], utterance: string): { state: DialogueState; applied: boolean; needsClarification: boolean } {
  const text = utterance.toLowerCase();
  const named: GroupMember[] = [...state.members];
  const allowedAllergies = new Set<string>(ALLERGENS.map(([key]) => key));
  const allowedDiets = new Set<string>(DIET_RULES.map(([key]) => key));
  const isCorrection = /아니|말고|없어|취소|정정|괜찮|잘못/.test(text);
  let applied = false;
  let needsClarification = false;
  let lastMemberLabel = state.lastMemberLabel;
  for (const update of updates.slice(0, 12)) {
    let baseLabel = update.label.replace(/님$/, '').trim();
    if (/^(그\s*친구|그\s*사람|그\s*분|그분|그녀|그)$/i.test(baseLabel)) {
      const specific = named.filter((member) => !member.id.startsWith('generic-'));
      if (specific.length === 1) baseLabel = specific[0].label.replace(/님$/, '');
      else { needsClarification = true; continue; }
    }
    if (!baseLabel || /^(한\s*명|두\s*명|세\s*명|일행|손님|사람|누군가|한\s*사람|unknown)$/.test(baseLabel)) continue;
    const previousIndex = named.findIndex((member) => member.label.replace(/님$/, '') === baseLabel);
    if (!text.includes(baseLabel.toLowerCase()) && !/그\s*친구|그\s*사람|그\s*분|그분/.test(text)) continue;
    const allergies = /알레르기|못\s*먹|빼|제외/.test(text) ? update.allergies.filter((key) => allowedAllergies.has(key)) : [];
    const diets = update.dietaryRules.filter((key) => allowedDiets.has(key));
    const count = Math.min(12, Math.max(1, update.count));
    for (let index = 0; index < count; index++) {
      const label = count === 1 ? baseLabel : `${baseLabel} ${index + 1}`;
      let targetIndex = count === 1 ? previousIndex : named.findIndex((member) => member.label === label);
      if (targetIndex < 0) targetIndex = named.findIndex((member) => member.id.startsWith('generic-'));
      const old = targetIndex >= 0 ? named[targetIndex] : { id: `llm-${named.length + 1}`, label, allergies: [], dietaryRules: [] };
      const removed = isCorrection ? new Set(update.removeDietaryRules.filter((key) => allowedDiets.has(key))) : new Set<string>();
      const updated: GroupMember = {
        ...old,
        id: old.id.startsWith('generic-') ? `named-${targetIndex + 1}` : old.id,
        label,
        allergies: [...new Set([...old.allergies, ...allergies])],
        dietaryRules: [...old.dietaryRules.filter((rule) => !removed.has(rule.type)), ...diets.filter((type) => !old.dietaryRules.some((rule) => rule.type === type && !removed.has(type))).map((type) => ({ type, mode: 'strict' as const }))],
        maxSpiceLevel: isCorrection && update.clearSpiceLimit ? undefined : update.maxSpiceLevel === null ? old.maxSpiceLevel : Math.min(old.maxSpiceLevel ?? 4, update.maxSpiceLevel),
        tastes: [...new Set([...(old.tastes || []), ...(update.tastes || []).filter((taste) => ["spicy", "mild", "sweet", "soup", "kids"].includes(taste))])],
      };
      if (targetIndex >= 0) named[targetIndex] = updated;
      else named.push(updated);
      applied = true;
      lastMemberLabel = label;
    }
  }
  if (!applied) return { state, applied: false, needsClarification };
  const members = state.peopleCount ? named.slice(0, state.peopleCount) : named.slice(0, 12);
  while (state.peopleCount && members.length < state.peopleCount) members.push({ id: `generic-${members.length + 1}`, label: `일행 ${members.length + 1}`, allergies: [], dietaryRules: [] });
  const preferences = { ...state.preferences };
  // A named person's restriction must not turn into a restriction for the whole table.
  if (updates.some((entry) => entry.dietaryRules.includes('vegetarian') || entry.dietaryRules.includes('vegan') || entry.removeDietaryRules.includes('vegetarian') || entry.removeDietaryRules.includes('vegan'))) preferences.vegetarian = false;
  if (updates.some((entry) => entry.maxSpiceLevel !== null || entry.tastes?.includes('mild'))) { preferences.maxSpiceLevel = undefined; preferences.wantsMild = false; }
  if (updates.some((entry) => entry.tastes?.includes('soup'))) preferences.wantsWarm = false;
  if (updates.some((entry) => entry.tastes?.length)) preferences.category = undefined;
  return { state: { ...state, members, preferences, lastMemberLabel }, applied: true, needsClarification };
}

export function applyExplicitCorrections(state: DialogueState, corrections: { clearVegetarian: boolean; clearSpiceLimit: boolean; clearBudget: boolean }, utterance: string): DialogueState {
  if (!/아니|말고|없어|취소|정정|괜찮|잘못/.test(utterance)) return state;
  const preferences = { ...state.preferences };
  if (corrections.clearVegetarian && /채식|비건/.test(utterance)) preferences.vegetarian = false;
  if (corrections.clearSpiceLimit && /맵|매운|순한/.test(utterance)) { preferences.maxSpiceLevel = undefined; preferences.wantsMild = false; }
  if (corrections.clearBudget && /예산|원|가격/.test(utterance)) preferences.totalBudget = undefined;
  return { ...state, preferences };
}
