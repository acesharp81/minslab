import { spawn } from "node:child_process";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import dotenv from "dotenv";

const rootEnv = resolve(process.cwd(), "../../.env");
let parsed = {};
try {
  parsed = dotenv.parse(readFileSync(rootEnv));
} catch {
  /* Mock mode works without root .env. */
}
const allowed = [
  "OPENROUTER_API_KEY",
  "GROQ_API_KEY",
  "POC09_DATABASE_URL",
  "POC09_MERCHANT_EMAIL",
  "POC09_MERCHANT_PASSWORD",
  "POC09_SESSION_SECRET",
  "POC09_LLM_MODEL",
  "POC09_VISION_MODEL",
  "POC09_JEV_MODEL",
  "POC09_AI_PROVIDER",
  "POC09_CONVERSATION_PROVIDER",
  "POC09_METER_TOKEN",
  "POC09_METER_URL",
  "POC09_DECISION_PROVIDER",
  "POC09_MENU_SELECTOR_PROVIDER",
  "POC09_MENU_SELECTOR_MODEL",
];
const env = { ...process.env };
for (const key of allowed) if (!env[key] && parsed[key]) env[key] = parsed[key];
env.POC09_DATABASE_URL ||=
  "postgresql://poc09:poc09_local_only@127.0.0.1:18091/poc09";
const [command, ...args] = process.argv.slice(2);
if (!command) throw new Error("A command is required");
const executable = resolve(process.cwd(), "node_modules/.bin", command);
const child = spawn(executable, args, { stdio: "inherit", env });
child.on("exit", (code, signal) => {
  if (signal) process.kill(process.pid, signal);
  else process.exit(code ?? 1);
});
