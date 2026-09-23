import { createHmac, randomBytes, timingSafeEqual } from "node:crypto";
import { cookies } from "next/headers";
import { db } from "./db";

const path = "/poc/mwomeokji";
export const tokenHash = (value: string) =>
  createHmac(
    "sha256",
    process.env.POC09_SESSION_SECRET || "poc09-development-only",
  )
    .update(value)
    .digest("hex");
const newToken = () => randomBytes(32).toString("base64url");
const cookieOptions = {
  httpOnly: true,
  sameSite: "lax" as const,
  secure: process.env.NODE_ENV === "production",
  path,
  maxAge: 60 * 60 * 24,
};

export async function guest(storeId: string, tableId?: string) {
  const jar = await cookies();
  const token = jar.get("poc09_guest")?.value;
  if (token) {
    const session = await db.guestSession.findUnique({
      where: { tokenHash: tokenHash(token) },
    });
    if (
      session &&
      session.storeId === storeId &&
      session.expiresAt > new Date()
    ) {
      if (tableId && session.tableId !== tableId)
        return db.guestSession.update({
          where: { id: session.id },
          data: { tableId },
        });
      return session;
    }
  }
  const created = newToken();
  const session = await db.guestSession.create({
    data: {
      tokenHash: tokenHash(created),
      storeId,
      tableId,
      expiresAt: new Date(Date.now() + 86400000),
    },
  });
  jar.set("poc09_guest", created, cookieOptions);
  return session;
}

export async function currentGuest() {
  const token = (await cookies()).get("poc09_guest")?.value;
  if (!token) return null;
  const session = await db.guestSession.findUnique({
    where: { tokenHash: tokenHash(token) },
  });
  return session && session.expiresAt > new Date() ? session : null;
}

export async function currentMerchant() {
  const token = (await cookies()).get("poc09_merchant")?.value;
  if (!token) return null;
  const session = await db.merchantSession.findUnique({
    where: { tokenHash: tokenHash(token) },
  });
  return session && session.expiresAt > new Date() ? session : null;
}

export async function merchantLogin(email: string, password: string) {
  const ownerEmail = process.env.POC09_MERCHANT_EMAIL || "";
  const ownerPassword = process.env.POC09_MERCHANT_PASSWORD || "";
  const demoEmail = "demo@mmj.local";
  const demoPassword = "demo1234";
  const expectedPassword = email === demoEmail ? demoPassword : email === ownerEmail ? ownerPassword : "";
  if (!expectedPassword) return false;
  const a = Buffer.from(tokenHash(password));
  const b = Buffer.from(tokenHash(expectedPassword));
  if (!timingSafeEqual(a, b)) return false;
  const token = newToken();
  await db.merchantSession.create({
    data: {
      tokenHash: tokenHash(token),
      expiresAt: new Date(Date.now() + 12 * 3600000),
    },
  });
  (await cookies()).set("poc09_merchant", token, {
    ...cookieOptions,
    maxAge: 12 * 3600,
  });
  return true;
}

export async function merchantLogout() {
  const jar = await cookies();
  const token = jar.get("poc09_merchant")?.value;
  if (token)
    await db.merchantSession.deleteMany({
      where: { tokenHash: tokenHash(token) },
    });
  jar.delete("poc09_merchant");
}
