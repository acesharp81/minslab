import type { DialogueState } from "./dialogue";

const familyRoles = new Set(["나", "저", "아이", "아기", "딸", "아들", "와이프", "아내", "남편", "배우자", "신랑"]);

/** Only the fields needed to resolve this turn leave the server. In particular,
 * allergy, diet, cart contents, session identifiers and prior utterances stay local. */
export function conversationSnapshot(state: DialogueState, menuNames: Map<string, string>) {
  const seats = state.members.map((member, index) => ({
    id: `seat_${index + 1}`,
    role: familyRoles.has(member.label) ? member.label : `일행 ${index + 1}`,
    tastes: member.tastes || [],
    menuLabels: member.menuLabels || [],
    excludedTags: member.excludedTags || [],
  }));
  const seatId = (label?: string) => {
    const index = state.members.findIndex((member) => member.label === label);
    return index < 0 ? null : `seat_${index + 1}`;
  };
  return {
    peopleCount: state.peopleCount ?? null,
    members: seats,
    suggestions: state.lastRecommendations.map((item, index) => ({
      slot: index + 1,
      menuId: item.id,
      menuName: menuNames.get(item.id) || "",
      seatId: seatId(item.forMember),
    })),
    category: state.preferences.category || null,
    totalBudget: state.preferences.totalBudget ?? null,
    focusedSeatId: seatId(state.focusedMemberLabel),
    pendingOffer: state.pendingOffer ? { kind: state.pendingOffer.kind, seatIds: state.pendingOffer.memberIds.map((id) => { const index = state.members.findIndex((member) => member.id === id); return index < 0 ? null : `seat_${index + 1}`; }).filter(Boolean) } : null,
  };
}

export function anonymizeKnownNames(message: string, state: DialogueState) {
  let result = message;
  state.members.forEach((member, index) => {
    if (familyRoles.has(member.label) || /^일행 \d+$/.test(member.label)) return;
    result = result.replaceAll(member.label, `일행 ${index + 1}`);
  });
  return result;
}

/** A model's seat target is evidence only when the user identified that diner,
 * their current dish, or the one diner already being discussed. */
export function resolveSeatTarget(message: string, state: DialogueState, seatId: string | null | undefined,
  menuNames: Map<string, string>): string | undefined {
  const seat = seatId?.match(/^seat_(\d{1,2})$/);
  if (!seat) return undefined;
  const member = state.members[Number(seat[1]) - 1];
  if (!member) return undefined;
  if (message.includes(member.label) || message.includes(`일행 ${seat[1]}`)) return member.label;
  const ordinal = message.match(/(?:첫\s*번째|1\s*번|두\s*번째|2\s*번|세\s*번째|3\s*번|네\s*번째|4\s*번|다섯\s*번째|5\s*번)/);
  if (ordinal) {
    const slot = /^(?:첫|1)/.test(ordinal[0]) ? 0 : /^(?:두|2)/.test(ordinal[0]) ? 1 : /^(?:세|3)/.test(ordinal[0]) ? 2 : /^(?:네|4)/.test(ordinal[0]) ? 3 : 4;
    if (state.lastRecommendations[slot]?.forMember === member.label) return member.label;
  }
  const matching = state.lastRecommendations.filter((entry) => {
    const name = menuNames.get(entry.id) || "";
    return name.length >= 2 && (message.includes(name) || name.split(/\s+/).some((word) => word.length >= 2 && message.includes(word)));
  });
  if (matching.length === 1 && matching[0].forMember === member.label) return member.label;
  if (state.focusedMemberLabel === member.label && /^(그럼|그러면|좀|더|다른|아니면|이번엔)/.test(message.trim())) return member.label;
  return undefined;
}
