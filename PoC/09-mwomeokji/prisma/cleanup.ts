import { db } from "../lib/db";
async function main() {
  const now = new Date();
  const expired = await db.guestSession.findMany({
    where: { expiresAt: { lt: now } },
    select: { id: true },
  });
  if (expired.length) {
    const ids = expired.map((session) => session.id);
    await db.$transaction([
      db.cartItem.deleteMany({ where: { sessionId: { in: ids } } }),
      db.guestSession.updateMany({
        where: { id: { in: ids } },
        data: { context: {} },
      }),
      db.merchantSession.deleteMany({ where: { expiresAt: { lt: now } } }),
    ]);
  } else
    await db.merchantSession.deleteMany({ where: { expiresAt: { lt: now } } });
  console.log(`Cleared expired PoC9 session profiles: ${expired.length}`);
}
main().finally(() => db.$disconnect());
