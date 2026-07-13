import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { useEffect, useState } from "react";
import { useServerFn } from "@/lib/server-functions";
import { useQuery } from "@tanstack/react-query";
import { toast } from "sonner";
import { supabase } from "@/integrations/supabase/client";
import {
  checkLoginId,
  getSignupMeta,
  resolveLoginEmail,
  signupUser,
} from "@/lib/auth.functions";
import { PasswordInput } from "@/components/PasswordInput";
import { getMyProfile } from "@/lib/profile.functions";
import { Button } from "@/components/ui/button";
import { AppBrand } from "@/components/AppBrand";
import { LogIn, UserPlus } from "lucide-react";

export const Route = createFileRoute("/login")({
  component: LoginPage,
  head: () => ({ meta: [{ title: "로그인 — 통합 업무 관리 시스템" }] }),
});

const LOGIN_ID_RE = /^[a-z0-9]+$/;

function LoginPage() {
  const [mode, setMode] = useState<"login" | "signup">("login");
  return (
    <main className="relative flex min-h-screen items-center justify-center px-4 py-10">
      <div className="login-shell">
        <div className="login-brand-wrap">
          <AppBrand centered />
        </div>
        <div className="glass-panel login-card rounded-3xl p-8">
          <h1 className="text-center text-2xl font-bold tracking-tight">
            통합 업무 관리 시스템
          </h1>
          <p className="mt-1 mb-6 text-center text-sm text-muted-foreground">
            {mode === "login" ? "로그인하여 시작하세요" : "신규 계정을 생성합니다"}
          </p>
          {mode === "login" ? (
            <LoginForm onSwitch={() => setMode("signup")} />
          ) : (
            <SignupForm onSwitch={() => setMode("login")} />
          )}
        </div>
      </div>
    </main>
  );
}

function LoginForm({ onSwitch }: { onSwitch: () => void }) {
  const navigate = useNavigate();
  const resolve = useServerFn(resolveLoginEmail);
  const [loginId, setLoginId] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!loginId || !password) return;
    setLoading(true);
    try {
      const { email, status } = await resolve({ data: { login_id: loginId.trim() } });
      if (status === "가입신청") {
        toast.error("관리자 승인이 필요합니다.");
        return;
      }
      if (status === "탈퇴") {
        toast.error("중지된 사용자입니다.");
        return;
      }
      const { error } = await supabase.auth.signInWithPassword({ email, password });
      if (error) {
        toast.error("ID 또는 비밀번호가 일치하지 않습니다.");
        return;
      }
      const current = await getMyProfile();
      if (!current.profile || current.profile.status !== "승인") {
        await supabase.auth.signOut();
        toast.error(current.profile?.status === "탈퇴" ? "중지된 사용자입니다." : "관리자 승인이 필요합니다.");
        return;
      }
      toast.success("환영합니다.");
      navigate({ to: "/" });
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "로그인 실패");
    } finally {
      setLoading(false);
    }
  };

  return (
    <form onSubmit={onSubmit} className="space-y-4">
      <div>
        <label className="mb-1.5 block text-xs font-medium text-muted-foreground">ID</label>
        <input
          value={loginId}
          onChange={(e) => setLoginId(e.target.value)}
          autoComplete="off"
          className="glass-input flex h-11 w-full rounded-lg px-4 text-sm"
          placeholder="아이디"
        />
      </div>
      <div>
        <label className="mb-1.5 block text-xs font-medium text-muted-foreground">
          비밀번호
        </label>
        <PasswordInput
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          placeholder="••••••••"
        />
      </div>
      <div className="flex gap-2 pt-2">
        <Button type="submit" disabled={loading} className="flex-1 gap-1.5">
          <LogIn className="h-4 w-4" /> 로그인
        </Button>
        <Button type="button" variant="secondary" onClick={onSwitch} className="flex-1 gap-1.5">
          <UserPlus className="h-4 w-4" /> 회원가입
        </Button>
      </div>
    </form>
  );
}

function SignupForm({ onSwitch }: { onSwitch: () => void }) {
  const meta = useQuery({
    queryKey: ["signup-meta"],
    queryFn: () => getSignupMeta(),
  });
  const checkId = useServerFn(checkLoginId);
  const signup = useServerFn(signupUser);

  const [loginId, setLoginId] = useState("");
  const [name, setName] = useState("");
  const [pw, setPw] = useState("");
  const [pw2, setPw2] = useState("");
  const [position, setPosition] = useState<"과장" | "팀장" | "팀원" | "서무">("팀원");
  const [divisionId, setDivisionId] = useState<string>("");
  const [teamId, setTeamId] = useState<string>("");
  const [idChecked, setIdChecked] = useState(false);
  const [idError, setIdError] = useState<string | null>(null);
  const [showIdWarning, setShowIdWarning] = useState(false);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    setIdChecked(false);
    if (!loginId) {
      setIdError(null);
    } else if (!LOGIN_ID_RE.test(loginId)) {
      setIdError("영문 소문자와 숫자만 사용 가능합니다.");
    } else {
      setIdError(null);
    }
  }, [loginId]);

  useEffect(() => {
    if (position === "과장") setTeamId("");
  }, [position]);

  const teams = (meta.data?.teams ?? []).filter((t) => t.division_id === divisionId);

  const onCheckId = async () => {
    if (!loginId || idError) return;
    const r = await checkId({ data: { login_id: loginId } });
    if (r.available) {
      setIdChecked(true);
      setShowIdWarning(false);
      toast.success("사용 가능한 ID입니다.");
    } else {
      setIdChecked(false);
      toast.error("이미 사용 중이거나 잘못된 ID입니다.");
    }
  };

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!idChecked) {
      setShowIdWarning(true);
      return;
    }
    if (!name || !pw || pw !== pw2) {
      toast.error("입력값을 확인해 주세요.");
      return;
    }
    if (pw.length < 6) {
      toast.error("비밀번호는 6자 이상이어야 합니다.");
      return;
    }
    setLoading(true);
    try {
      await signup({
        data: {
          login_id: loginId,
          password: pw,
          name,
          position,
          division_id: divisionId || null,
          team_id: position === "과장" ? null : teamId || null,
        },
      });
      toast.success("가입 신청이 접수되었습니다. 관리자 승인을 기다려 주세요.");
      onSwitch();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "회원가입 실패");
    } finally {
      setLoading(false);
    }
  };

  return (
    <form onSubmit={onSubmit} className="space-y-3.5">
      {meta.data?.signup_enabled === false && (
        <div className="rounded-xl border border-amber-300 bg-amber-50 p-3 text-xs leading-relaxed text-amber-900">
          현재 신규 가입은 준비 중입니다. 기존 승인 계정은 정상적으로 로그인할 수 있습니다.
        </div>
      )}
      <div>
        <label className="mb-1.5 block text-xs font-medium text-muted-foreground">ID</label>
        <div className="flex gap-2">
          <input
            value={loginId}
            onChange={(e) => setLoginId(e.target.value)}
            className="glass-input flex h-11 w-full rounded-lg px-4 text-sm"
            placeholder="영문소문자 + 숫자"
          />
          <Button type="button" variant="secondary" onClick={onCheckId} disabled={!!idError || !loginId || meta.data?.signup_enabled === false}>
            중복확인
          </Button>
        </div>
        {idError && <p className="mt-1 text-xs text-destructive">{idError}</p>}
        {showIdWarning && !idChecked && (
          <p className="mt-1 text-xs text-destructive">*ID 중복확인을 수행해 주세요</p>
        )}
        {idChecked && !idError && (
          <p className="mt-1 text-xs text-primary">사용 가능한 ID</p>
        )}
      </div>
      <div>
        <label className="mb-1.5 block text-xs font-medium text-muted-foreground">이름</label>
        <input
          value={name}
          onChange={(e) => setName(e.target.value)}
          className="glass-input flex h-11 w-full rounded-lg px-4 text-sm"
        />
      </div>
      <div className="grid grid-cols-2 gap-2">
        <div>
          <label className="mb-1.5 block text-xs font-medium text-muted-foreground">
            비밀번호
          </label>
          <PasswordInput value={pw} onChange={(e) => setPw(e.target.value)} />
        </div>
        <div>
          <label className="mb-1.5 block text-xs font-medium text-muted-foreground">
            비밀번호 확인
          </label>
          <PasswordInput value={pw2} onChange={(e) => setPw2(e.target.value)} />
        </div>
      </div>
      <div>
        <label className="mb-1.5 block text-xs font-medium text-muted-foreground">직책</label>
        <div className="flex flex-wrap gap-2">
          {(["과장", "팀장", "팀원", "서무"] as const).map((p) => (
            <label
              key={p}
              className={`cursor-pointer rounded-full border px-3 py-1.5 text-xs font-medium transition ${
                position === p
                  ? "border-primary bg-primary text-primary-foreground"
                  : "border-border bg-white/60"
              }`}
            >
              <input
                type="radio"
                name="pos"
                className="sr-only"
                checked={position === p}
                onChange={() => setPosition(p)}
              />
              {p}
            </label>
          ))}
        </div>
      </div>
      <div className="grid grid-cols-2 gap-2">
        <div>
          <label className="mb-1.5 block text-xs font-medium text-muted-foreground">과</label>
          <select
            value={divisionId}
            onChange={(e) => {
              setDivisionId(e.target.value);
              setTeamId("");
            }}
            className="glass-input flex h-11 w-full rounded-lg px-3 text-sm"
          >
            <option value="">선택</option>
            {(meta.data?.divisions ?? []).map((d) => (
              <option key={d.id} value={d.id}>
                {d.name}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label className="mb-1.5 block text-xs font-medium text-muted-foreground">팀</label>
          <select
            value={teamId}
            onChange={(e) => setTeamId(e.target.value)}
            disabled={position === "과장" || !divisionId}
            className="glass-input flex h-11 w-full rounded-lg px-3 text-sm disabled:opacity-50"
          >
            <option value="">선택</option>
            {teams.map((t) => (
              <option key={t.id} value={t.id}>
                {t.name}
              </option>
            ))}
          </select>
        </div>
      </div>
      <div className="flex gap-2 pt-2">
        <Button type="submit" disabled={loading || meta.data?.signup_enabled === false} className="flex-1">
          가입
        </Button>
        <Button type="button" variant="secondary" onClick={onSwitch} className="flex-1">
          로그인으로
        </Button>
      </div>
    </form>
  );
}
