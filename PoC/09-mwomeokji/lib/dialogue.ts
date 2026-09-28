import { ALLERGENS, DIET_RULES, type GroupMember, type OrderIntent } from './types';

export type VisitMode = 'dine_in' | 'takeout';
export type SuggestedItem = { id: string; forMember?: string };
export type DialogueState = {
  peopleCount?: number;
  members: GroupMember[];
  preferences: OrderIntent;
  menuLabels: string[];
  lastRecommendations: SuggestedItem[];
  pendingCheckout: boolean;
  pendingCheckoutSignature?: string;
  pendingOffer?: { kind: "replace_kids_with_mild"; memberIds: string[] };
  lastMemberLabel?: string;
  focusedMemberLabel?: string;
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
  menuLabels?: string[];
};

const numberWords: Record<string, number> = { 한: 1, 두: 2, 세: 3, 네: 4, 다섯: 5, 하나: 1, 둘: 2, 셋: 3, 넷: 4 };
const countOf = (value: string) => Number(value) || numberWords[value] || 1;
export const emptyDialogue = (): DialogueState => ({ members: [], preferences: { action: 'recommend' }, menuLabels: [], lastRecommendations: [], pendingCheckout: false });

function mergeTastes(previous: GroupMember['tastes'], incoming: NonNullable<GroupMember['tastes']>): NonNullable<GroupMember['tastes']> {
  const replacing = new Set<NonNullable<GroupMember['tastes']>[number]>();
  if (incoming.includes('rice')) replacing.add('soup');
  if (incoming.includes('soup')) replacing.add('rice');
  if (incoming.includes('spicy')) replacing.add('mild');
  if (incoming.includes('mild')) replacing.add('spicy');
  return [...new Set([...(previous || []).filter((taste) => !replacing.has(taste)), ...incoming])];
}

export function readDialogue(context: unknown): DialogueState {
  if (!context || typeof context !== 'object' || Array.isArray(context) || !('dialogue' in context)) return emptyDialogue();
  const value = context.dialogue;
  if (!value || typeof value !== 'object' || Array.isArray(value)) return emptyDialogue();
  const record = value as Record<string, unknown>;
  const members = Array.isArray(record.members) ? record.members.filter((member): member is GroupMember => !!member && typeof member === 'object' && !Array.isArray(member) && typeof member.id === 'string' && typeof member.label === 'string' && Array.isArray(member.allergies) && Array.isArray(member.dietaryRules)) : [];
  const lastRecommendations = Array.isArray(record.lastRecommendations) ? record.lastRecommendations.filter((item): item is SuggestedItem => !!item && typeof item === 'object' && !Array.isArray(item) && typeof item.id === 'string') : [];
  const preferences = record.preferences && typeof record.preferences === 'object' && !Array.isArray(record.preferences) ? record.preferences as OrderIntent : { action: 'recommend' as const };
  return { peopleCount: typeof record.peopleCount === 'number' ? Math.min(12, Math.max(1, record.peopleCount)) : undefined, members: members.slice(0, 12), preferences, menuLabels: Array.isArray(record.menuLabels) ? record.menuLabels.filter((label): label is string => typeof label === "string" && label.length <= 30).slice(0, 3) : [], lastRecommendations: lastRecommendations.slice(0, 12), pendingCheckout: record.pendingCheckout === true, pendingCheckoutSignature: typeof record.pendingCheckoutSignature === "string" ? record.pendingCheckoutSignature : undefined, pendingOffer: record.pendingOffer && typeof record.pendingOffer === "object" && !Array.isArray(record.pendingOffer) && (record.pendingOffer as { kind?: unknown }).kind === "replace_kids_with_mild" && Array.isArray((record.pendingOffer as { memberIds?: unknown }).memberIds) ? { kind: "replace_kids_with_mild", memberIds: (record.pendingOffer as { memberIds: unknown[] }).memberIds.filter((id): id is string => typeof id === "string").slice(0, 12) } : undefined, lastMemberLabel: typeof record.lastMemberLabel === "string" ? record.lastMemberLabel.slice(0, 40) : undefined, focusedMemberLabel: typeof record.focusedMemberLabel === "string" ? record.focusedMemberLabel.slice(0, 40) : undefined };
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
  else if (!specified.length && !previous.peopleCount) inferredCount = parsed.peopleCount || 0;
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
  // Spoken groups often omit 명: “둘은 맵찔이고, 셋은 매운 걸 잘 먹어”.
  // Attribute each explicit count to separate seats before making any menu proposal.
  let groupedSpice = false;
  if (peopleCount && !specified.length) {
    const groupClauses = [...text.matchAll(/(?:^|[\s,，;])(\d+|한|두|세|네|다섯|하나|둘|셋|넷)\s*(?:명)?(?:은|는|이|가)\s*(.*?)(?=(?:[,，;]?\s*(?:\d+|한|두|세|네|다섯|하나|둘|셋|넷)\s*(?:명)?(?:은|는|이|가))|[.!?]|$)/g)];
    let seat = 0;
    for (const clause of groupClauses) {
      const detail = clause[2];
      const mild = /맵찔|매운.*(?:못|안)|맵.*(?:못|안)|안\s*맵|맵지|순한/.test(detail);
      const spicy = !mild && /매운|맵게|얼큰/.test(detail);
      if (!mild && !spicy) continue;
      groupedSpice = true;
      for (let index = 0; index < countOf(clause[1]) && seat < peopleCount; index++, seat++) {
        const member = members[seat];
        members[seat] = {
          ...member,
          maxSpiceLevel: mild ? 0 : undefined,
          tastes: mergeTastes(member.tastes, [mild ? 'mild' : 'spicy']),
        };
      }
    }
  }
  const preferences: OrderIntent = { ...previous.preferences, action: 'recommend' };
  for (const key of ['totalBudget','maxSpiceLevel','minSpiceLevel','kidsOnly','peopleCount','category','wantsWarm','wantsCool','wantsMild','vegetarian','avoidPork','avoidBeef','quantity','coffee','caffeineFree','decaf','wantsSweet','avoidSour'] as const) {
    const value = parsed[key];
    if (value !== undefined && value !== false) Object.assign(preferences, { [key]: value });
  }
  if (parsed.maxSpiceLevel !== undefined) preferences.minSpiceLevel = undefined;
  if (specified.length) {
    if (specified.some((member) => member.dietaryRules.some((rule) => rule.type === 'vegetarian' || rule.type === 'vegan'))) preferences.vegetarian = false;
    if (specified.some((member) => member.maxSpiceLevel !== undefined)) preferences.maxSpiceLevel = undefined;
  }
  if (groupedSpice) { preferences.maxSpiceLevel = undefined; preferences.minSpiceLevel = undefined; preferences.wantsMild = false; }
  if (peopleCount) preferences.peopleCount = peopleCount;
  if (parsed.category && parsed.category !== previous.preferences.category) {
    if (!parsed.coffee) preferences.coffee = false;
    if (!parsed.caffeineFree) preferences.caffeineFree = false;
    if (!parsed.decaf) preferences.decaf = false;
    if (!parsed.quantity) preferences.quantity = undefined;
    if (!parsed.wantsSweet) preferences.wantsSweet = false;
    if (!parsed.avoidSour) preferences.avoidSour = false;
  }
  // A broader drink request explicitly drops a previous coffee-only requirement.
  if (parsed.category === '음료' && /음료|마실/.test(text) && !parsed.coffee) {
    preferences.coffee = false;
    preferences.decaf = false;
  }
  if (parsed.caffeineFree && !parsed.decaf) preferences.decaf = false;
  if (parsed.decaf && !parsed.caffeineFree) preferences.caffeineFree = false;
  if (parsed.coffee && /일반\s*커피|카페인\s*있어도|카페인\s*상관/.test(text)) { preferences.caffeineFree = false; preferences.decaf = false; }
  if (/말고|아니|대신/.test(text)) {
    if (parsed.wantsCool && /따뜻|뜨끈|국물/.test(text)) preferences.wantsWarm = false;
    if (parsed.wantsWarm && /시원|차가운/.test(text)) preferences.wantsCool = false;
  }
  const globalAllergies = specified.length ? [] : conditions(text).allergies;
  const needsPeopleCount = specified.length > 0 && !peopleCount;
  // Saved party size is context, not evidence that this turn only states a headcount.
  const statedHeadcount = !!(explicitTotal || leadingCount || familyCount || casualCount || changedCount !== undefined);
  const onlyHeadcount = statedHeadcount && !/추천|골라|주문해|메뉴|음식|밥\s*먹|식사|먹을|먹고\s*싶|뭐\s*먹/.test(text);
  return { state: { ...previous, peopleCount, members, preferences }, globalAllergies, needsPeopleCount, onlyHeadcount };
}

export function canStageRecommendations(state: DialogueState): boolean {
  if (state.lastRecommendations.length === 1) return true;
  return !!state.peopleCount && state.peopleCount > 1
    && state.lastRecommendations.length === state.peopleCount
    && state.lastRecommendations.every((entry) => !!entry.forMember)
    && new Set(state.lastRecommendations.map((entry) => entry.forMember)).size === state.peopleCount;
}

export function contextSummary(state: DialogueState, mode: VisitMode | null) {
  const result: string[] = [];
  if (mode) result.push(mode === 'dine_in' ? '먹고 가기' : '가져가기');
  if (state.peopleCount) result.push(`${state.peopleCount}명`);
  if (state.preferences.totalBudget) result.push(`예산 ${state.preferences.totalBudget.toLocaleString('ko-KR')}원`);
  for (const label of state.menuLabels) result.push(label);
  if (state.preferences.wantsWarm) result.push('따뜻한 음식');
  if (state.preferences.maxSpiceLevel !== undefined) result.push('순한 맛');
  for (const member of state.members.filter((entry) => !entry.id.startsWith('generic-'))) result.push(member.label);
  return result.slice(0, 8);
}

function mentionedMember(text: string, label: string) {
  if (label === '나' || label === '저') {
    const pattern = label === '나'
      ? /(?:^|[\s,，.;])나(?=는|은|랑|와|과|도|에게|한테|꺼|것|메뉴|\s|$)/
      : /(?:^|[\s,，.;])저(?=는|은|랑|와|과|도|에게|한테|꺼|것|메뉴|\s|$)/;
    return pattern.test(text);
  }
  return text.includes(label.toLowerCase());
}

/** A complete new meal brief replaces stale menu tastes and budget from a resumed chat. */
export function resetForFullMealBrief(previous: DialogueState, utterance: string, updates: MemberUpdate[] = []): DialogueState {
  const text = utterance.toLowerCase();
  const roles = [/(?:^|\s)(?:나|저|제가|나는|저는)(?:랑|와|과|는|도|\s|$)/.test(text), /와이프|아내|남편|배우자|신랑/.test(text), /아이|아기|딸|아들|여아|남아/.test(text)].filter(Boolean).length;
  const namedPeople = new Set(updates.map((entry) => entry.label.replace(/(?:의)?(?:꺼|것|메뉴)$/, '')).filter((label) => mentionedMember(text, label))).size;
  const statedParty = /(\d+|두|세|네|둘|셋|넷)\s*(?:명|인|사람)/.test(text);
  // A newly described party and meal request starts a new choice, even without named family members.
  const newPartyBrief = statedParty && !/그럼|다른|이어서|아까|방금|기존/.test(text);
  const fullBrief = (roles >= 2 || (statedParty && namedPeople >= 2) || newPartyBrief) && /밥\s*먹|식사|한\s*끼|(?:메뉴|음식).*(?:추천|골라)|주문해|골라줘/.test(text);
  const standaloneDrink = /(?:음료|커피|디카페인|아메리카노|카페라떼)/.test(text) && /(?:\d+|한|두|세|네)\s*잔/.test(text) && /추천|골라/.test(text) && !/명|사람|일행|와이프|아내|남편|아이|딸|아들/.test(text);
  if (standaloneDrink && (previous.peopleCount || previous.members.length)) return emptyDialogue();
  if (!fullBrief || (!previous.peopleCount && !previous.members.length && !previous.lastRecommendations.length)) return previous;
  const members = previous.members.filter((member) => !member.id.startsWith('generic-') && mentionedMember(text, member.label)).map((member) => ({
    ...member,
    tastes: [],
    menuLabels: [],
    excludedTags: [],
    maxSpiceLevel: undefined,
  }));
  return { ...emptyDialogue(), members };
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
  const appliedLabels = new Set<string>();
  for (const update of updates.slice(0, 12)) {
    let baseLabel = update.label.replace(/(?:의)?(?:꺼|것|메뉴)$/, '').replace(/님$/, '').trim();
    if (/^(그\s*친구|그\s*사람|그\s*분|그분|그녀|그)$/i.test(baseLabel)) {
      const specific = named.filter((member) => !member.id.startsWith('generic-'));
      if (specific.length === 1) baseLabel = specific[0].label.replace(/님$/, '');
      else { needsClarification = true; continue; }
    }
    if (!baseLabel || /^(?:\d+|한|두|세|네|다섯|하나|둘|셋|넷)(?:\s*명)?$/.test(baseLabel) || /^(한\s*명|두\s*명|세\s*명|일행|손님|사람|누군가|한\s*사람|unknown)$/.test(baseLabel) || text.includes(`${baseLabel}명`)) continue;
    const previousIndex = named.findIndex((member) => member.label.replace(/님$/, '') === baseLabel);
    if (!mentionedMember(text, baseLabel) && !/그\s*친구|그\s*사람|그\s*분|그분/.test(text)) continue;
    const allergies = /알레르기|못\s*먹|빼|제외/.test(text) ? update.allergies.filter((key) => allowedAllergies.has(key)) : [];
    const diets = update.dietaryRules.filter((key) => allowedDiets.has(key));
    const count = Math.min(12, Math.max(1, update.count));
    for (let index = 0; index < count; index++) {
      const label = count === 1 ? baseLabel : `${baseLabel} ${index + 1}`;
      let targetIndex = count === 1 ? previousIndex : named.findIndex((member) => member.label === label);
      if (targetIndex < 0) targetIndex = named.findIndex((member) => member.id.startsWith('generic-'));
      const old = targetIndex >= 0 ? named[targetIndex] : { id: `llm-${named.length + 1}`, label, allergies: [], dietaryRules: [] };
      const removed = isCorrection ? new Set(update.removeDietaryRules.filter((key) => allowedDiets.has(key))) : new Set<string>();
      const incomingTastes = (update.tastes || []).filter((taste) => ["spicy", "mild", "sweet", "soup", "rice", "kids"].includes(taste));
      const incomingLabels = (update.menuLabels || []).filter((label) => label.length <= 30);
      const updated: GroupMember = {
        ...old,
        id: old.id.startsWith('generic-') ? `named-${targetIndex + 1}` : old.id,
        label,
        allergies: [...new Set([...old.allergies, ...allergies])],
        dietaryRules: [...old.dietaryRules.filter((rule) => !removed.has(rule.type)), ...diets.filter((type) => !old.dietaryRules.some((rule) => rule.type === type && !removed.has(type))).map((type) => ({ type, mode: 'strict' as const }))],
        maxSpiceLevel: incomingTastes.includes('spicy') && !incomingTastes.includes('mild') ? undefined : isCorrection && update.clearSpiceLimit ? undefined : update.maxSpiceLevel === null ? old.maxSpiceLevel : Math.min(old.maxSpiceLevel ?? 4, update.maxSpiceLevel),
        tastes: mergeTastes(old.tastes, incomingTastes),
        menuLabels: [...new Set([...(old.menuLabels || []), ...incomingLabels])].slice(0, 3),
        excludedTags: incomingTastes.includes("kids") ? (old.excludedTags || []).filter((tag) => tag !== "kids") : old.excludedTags,
      };
      if (targetIndex >= 0) named[targetIndex] = updated;
      else named.push(updated);
      applied = true;
      appliedLabels.add(label);
      lastMemberLabel = label;
    }
  }
  if (!applied) return { state, applied: false, needsClarification };
  const members = state.peopleCount ? named.slice(0, state.peopleCount) : named.slice(0, 12);
  while (state.peopleCount && members.length < state.peopleCount) members.push({ id: `generic-${members.length + 1}`, label: `일행 ${members.length + 1}`, allergies: [], dietaryRules: [] });
  const preferences = { ...state.preferences };
  // A named person's restriction must not turn into a restriction for the whole table.
  const tableWideDiet = /(?:우린|우리는|우리가|저흰|저희는|모두|전부|다들|전원|다\s*같이).*(?:채식|비건)|(?:채식|비건).*(?:모두|전부)/.test(text);
  if (!tableWideDiet && updates.some((entry) => entry.dietaryRules.includes('vegetarian') || entry.dietaryRules.includes('vegan') || entry.removeDietaryRules.includes('vegetarian') || entry.removeDietaryRules.includes('vegan'))) preferences.vegetarian = false;
  if (updates.some((entry) => entry.maxSpiceLevel !== null || entry.tastes?.includes('mild'))) { preferences.maxSpiceLevel = undefined; preferences.wantsMild = false; }
  if (updates.some((entry) => entry.tastes?.includes('spicy') || entry.tastes?.includes('mild'))) preferences.minSpiceLevel = undefined;
  if (updates.some((entry) => entry.tastes?.includes('kids'))) preferences.kidsOnly = false;
  if (updates.some((entry) => entry.tastes?.includes('soup'))) preferences.wantsWarm = false;
  if (updates.some((entry) => entry.tastes?.includes('sweet')) && !/모두|전부|다\s*같이/.test(text)) preferences.wantsSweet = false;
  if (updates.some((entry) => entry.tastes?.length)) preferences.category = undefined;
  const focusedMemberLabel = appliedLabels.size === 1 ? [...appliedLabels][0] : appliedLabels.size > 1 ? undefined : state.focusedMemberLabel;
  return { state: { ...state, members, preferences, lastMemberLabel, focusedMemberLabel }, applied: true, needsClarification };
}

/** Resolve a short preference follow-up only after the preceding turn focused on one diner. */
export function applyFocusedTaste(state: DialogueState, utterance: string): { state: DialogueState; applied: boolean } {
  const label = state.focusedMemberLabel;
  if (!label || !state.members.some((member) => member.label === label)) return { state, applied: false };
  const text = utterance.toLowerCase();
  if (/와이프|아내|남편|배우자|아이|아기|딸|아들|여아|남아|(?:^|\s)(?:나|저)(?:는|은|랑|도|\s)/.test(text) || /우리|모두|전부|다\s*같이/.test(text)) return { state, applied: false };
  const tastes: NonNullable<GroupMember["tastes"]> = [];
  if (/얼큰|매운|맵게/.test(text) && !/안\s*맵|맵지|매운.*(?:안|못)/.test(text)) tastes.push('spicy');
  if (/안\s*맵|맵지|순한/.test(text)) tastes.push('mild');
  if (/달달|달콤|단맛/.test(text)) tastes.push('sweet');
  if (/국물|수프|탕|찌개|해장|속\s*풀/.test(text) && !/덮밥|볶음밥|밥류/.test(text)) tastes.push('soup');
  if (/덮밥|볶음밥|밥류/.test(text)) tastes.push('rice');
  if (/키즈|어린이/.test(text)) tastes.push('kids');
  if (!tastes.length) return { state, applied: false };
  const members = state.members.map((member) => member.label === label ? {
    ...member,
    tastes: mergeTastes(member.tastes, tastes),
    maxSpiceLevel: tastes.includes('spicy') && !tastes.includes('mild') ? undefined : tastes.includes('mild') ? Math.min(member.maxSpiceLevel ?? 4, 0) : member.maxSpiceLevel,
  } : member);
  return { state: { ...state, members, preferences: { ...state.preferences, minSpiceLevel: undefined } }, applied: true };
}

export function applyExplicitCorrections(state: DialogueState, corrections: { clearVegetarian: boolean; clearSpiceLimit: boolean; clearBudget: boolean }, utterance: string): DialogueState {
  if (!/아니|말고|없어|취소|정정|괜찮|잘못/.test(utterance)) return state;
  const preferences = { ...state.preferences };
  if (corrections.clearVegetarian && /채식|비건/.test(utterance)) preferences.vegetarian = false;
  if (corrections.clearSpiceLimit && /맵|매운|순한/.test(utterance)) { preferences.maxSpiceLevel = undefined; preferences.wantsMild = false; }
  if (corrections.clearBudget && /예산|원|가격/.test(utterance)) preferences.totalBudget = undefined;
  return { ...state, preferences };
}
