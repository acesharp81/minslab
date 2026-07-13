import { createClient } from "@supabase/supabase-js";
import type { Database } from "./types";

const config = window.__MOIS_KMS_CONFIG__;
if (!config?.supabase_url || !config.supabase_publishable_key) {
  throw new Error("MinsLab Supabase 공개 설정이 준비되지 않았습니다.");
}

export const supabase = createClient<Database>(
  config.supabase_url,
  config.supabase_publishable_key,
  {
    auth: {
      storageKey: "minslab-mois-kms-auth",
      persistSession: true,
      autoRefreshToken: true,
      detectSessionInUrl: true,
    },
  },
);
