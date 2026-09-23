import { db, menuInclude } from "./db";
import type { PrismaClient } from "../generated/prisma/client";
import { checkSafety, priceFor } from "./safety";
import type { PreferenceProfile } from "./types";
import { readDialogue } from "./dialogue";

export async function cartSummary(
  sessionId: string,
  profile: PreferenceProfile,
  client: Pick<PrismaClient, "guestSession" | "cartItem"> = db,
) {
  const session = await client.guestSession.findUnique({
    where: { id: sessionId },
  });
  const members = readDialogue(session?.context).members;
  const cart = await client.cartItem.findMany({
    where: { sessionId },
    include: { menuItem: { include: menuInclude } },
    orderBy: { createdAt: "asc" },
  });
  const items = cart.map((entry) => {
    const item = entry.menuItem;
    const relevant = entry.assignedTo
      ? members.filter((member) => member.label === entry.assignedTo)
      : members;
    const effective: PreferenceProfile = {
      ...profile,
      allergies: [
        ...new Set([
          ...profile.allergies,
          ...relevant.flatMap((member) => member.allergies),
        ]),
      ],
      dietaryRules: [
        ...profile.dietaryRules,
        ...relevant.flatMap((member) => member.dietaryRules),
      ],
      maxSpiceLevel: relevant.reduce<number | undefined>(
        (limit, member) =>
          member.maxSpiceLevel === undefined
            ? limit
            : Math.min(limit ?? 4, member.maxSpiceLevel),
        profile.maxSpiceLevel,
      ),
    };
    const checked = checkSafety(item, effective, entry.selectedOptionIds);
    const safety =
      entry.assignedTo && relevant.length === 0
        ? {
            ...checked,
            allowed: false,
            reasons: [...checked.reasons, "일행 정보를 다시 확인해 주세요."],
          }
        : checked;
    const options = item.options
      .flatMap((group) => group.options)
      .filter((option) => entry.selectedOptionIds.includes(option.id));
    const unitPrice = priceFor(item, entry.selectedOptionIds);
    return {
      id: entry.id,
      menuItemId: item.id,
      name: item.name,
      emoji: item.emoji,
      quantity: entry.quantity,
      selectedOptionIds: entry.selectedOptionIds,
      optionNames: options.map((option) => option.name),
      assignedTo: entry.assignedTo,
      unitPrice,
      lineTotal: unitPrice * entry.quantity,
      safety,
    };
  });
  return {
    items,
    total: items.reduce((sum, item) => sum + item.lineTotal, 0),
    canOrder: items.length > 0 && items.every((item) => item.safety.allowed),
  };
}
