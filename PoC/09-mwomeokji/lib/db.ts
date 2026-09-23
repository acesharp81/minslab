import { PrismaClient } from "../generated/prisma/client";
import { PrismaPg } from "@prisma/adapter-pg";

const globalDb = globalThis as unknown as { poc09Db?: PrismaClient };
export const db =
  globalDb.poc09Db ??
  new PrismaClient({
    adapter: new PrismaPg({
      connectionString: process.env.POC09_DATABASE_URL!,
    }),
  });
if (process.env.NODE_ENV !== "production") globalDb.poc09Db = db;

export const menuInclude = {
  allergens: true,
  options: { include: { options: { include: { allergens: true } } } },
} as const;
