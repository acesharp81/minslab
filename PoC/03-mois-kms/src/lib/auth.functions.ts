import { z } from "zod";
import { apiRequest } from "./api";

const LOGIN_ID_RE = /^[a-z0-9]+$/;

const signupSchema = z.object({
  login_id: z.string().min(3).max(32).regex(LOGIN_ID_RE),
  password: z.string().min(6).max(72),
  name: z.string().min(1).max(50),
  position: z.enum(["과장", "팀장", "팀원", "서무"]),
  division_id: z.string().uuid().nullable(),
  team_id: z.string().uuid().nullable(),
});

export async function checkLoginId({ data }: { data: { login_id: string } }) {
  return apiRequest<{ available: boolean; reason: "invalid" | "taken" | "ok" }>(
    "/auth/check-login-id",
    { data: { login_id: data.login_id.trim() } },
  );
}

export async function signupUser({ data }: { data: z.infer<typeof signupSchema> }) {
  return apiRequest<{ ok: boolean }>("/auth/signup", { data: signupSchema.parse(data) });
}

export async function resolveLoginEmail({ data }: { data: { login_id: string } }) {
  return apiRequest<{ email: string; status: "가입신청" | "승인" | "탈퇴" }>(
    "/auth/resolve-login",
    { data: { login_id: data.login_id.trim() } },
  );
}

export async function getSignupMeta() {
  return apiRequest<{
    divisions: { id: string; name: string }[];
    teams: { id: string; name: string; division_id: string }[];
    signup_enabled: boolean;
  }>("/auth/signup-meta");
}
