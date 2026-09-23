import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import dotenv from "dotenv";

const config = dotenv.parse(readFileSync(resolve(process.cwd(), "../../.env")));
const key = config.OPENROUTER_API_KEY;
if (!key) throw new Error("OPENROUTER_API_KEY is not configured");
const [account, meter] = await Promise.all([
  fetch("https://openrouter.ai/api/v1/key", {
    headers: { Authorization: `Bearer ${key}` }, signal: AbortSignal.timeout(8000),
  }).then(async (response) => {
    if (!response.ok) throw new Error(`OpenRouter account HTTP ${response.status}`);
    const data = (await response.json()).data || {};
    return Object.fromEntries(["is_free_tier", "limit", "limit_remaining", "limit_reset", "usage_daily", "usage_monthly"].map((name) => [name, data[name] ?? null]));
  }),
  fetch("http://127.0.0.1:18071/internal/status", { signal: AbortSignal.timeout(3000) }).then(async (response) => {
    if (!response.ok) throw new Error(`shared meter HTTP ${response.status}`);
    const data = await response.json();
    return {
      free_gateway: { utc_day: data.usage_date, reserved: data.reserved, operational_limit: data.operational_limit, remaining: data.remaining, breakdown: data.breakdown },
      direct_calls_today: data.external_breakdown || [],
      direct_calls_this_month: data.external_monthly_breakdown || [],
    };
  }),
]);
console.log(JSON.stringify({ checked_at: new Date().toISOString(), openrouter_shared_key: account, ...meter }, null, 2));
