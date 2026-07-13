import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useServerFn } from "@/lib/server-functions";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { PasswordInput } from "@/components/PasswordInput";
import { toast } from "sonner";
import { supabase } from "@/integrations/supabase/client";
import { updateMyProfile, getProfileMeta } from "@/lib/profile.functions";

type Position = "과장" | "팀장" | "팀원" | "서무";

type Props = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  profile: {
    id: string;
    login_id: string;
    name: string;
    position: Position;
    division_id: string | null;
    team_id: string | null;
  };
};

export function ProfileDialog({ open, onOpenChange, profile }: Props) {
  const qc = useQueryClient();
  const fetchMeta = useServerFn(getProfileMeta);
  const updateFn = useServerFn(updateMyProfile);

  const [step, setStep] = useState<"verify" | "edit">("verify");
  const [currentPw, setCurrentPw] = useState("");
  const [verifying, setVerifying] = useState(false);

  const [name, setName] = useState(profile.name);
  const [position, setPosition] = useState<Position>(profile.position);
  const [divisionId, setDivisionId] = useState<string | null>(profile.division_id);
  const [teamId, setTeamId] = useState<string | null>(profile.team_id);
  const [newPw, setNewPw] = useState("");
  const [confirmPw, setConfirmPw] = useState("");

  useEffect(() => {
    if (open) {
      setStep("verify");
      setCurrentPw("");
      setName(profile.name);
      setPosition(profile.position);
      setDivisionId(profile.division_id);
      setTeamId(profile.team_id);
      setNewPw("");
      setConfirmPw("");
    }
  }, [open, profile]);

  const metaQuery = useQuery({
    queryKey: ["profile-meta"],
    queryFn: () => fetchMeta(),
    enabled: open && step === "edit",
  });

  const verify = async () => {
    if (!currentPw) {
      toast.error("현재 비밀번호를 입력하세요.");
      return;
    }
    setVerifying(true);
    const { error } = await supabase.auth.signInWithPassword({
      email: `${profile.login_id}@app.local`,
      password: currentPw,
    });
    setVerifying(false);
    if (error) {
      toast.error("비밀번호가 일치하지 않습니다.");
      return;
    }
    setStep("edit");
  };

  const save = useMutation({
    mutationFn: async () => {
      if (!name.trim()) throw new Error("이름을 입력하세요.");
      if (newPw || confirmPw) {
        if (newPw !== confirmPw) throw new Error("새 비밀번호가 일치하지 않습니다.");
        if (newPw.length < 6) throw new Error("비밀번호는 6자 이상이어야 합니다.");
      }
      return updateFn({
        data: {
          name: name.trim(),
          position,
          division_id: divisionId,
          team_id: position === "과장" ? null : teamId,
          new_password: newPw || null,
        },
      });
    },
    onSuccess: () => {
      toast.success("프로필이 수정되었습니다.");
      qc.invalidateQueries({ queryKey: ["my-profile"] });
      onOpenChange(false);
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const divisions = metaQuery.data?.divisions ?? [];
  const teams = (metaQuery.data?.teams ?? []).filter(
    (t) => !divisionId || t.division_id === divisionId,
  );

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="glass-panel max-w-md border-0 sm:rounded-3xl">
        <DialogHeader>
          <DialogTitle>
            {step === "verify" ? "본인 확인" : "내 정보 수정"}
          </DialogTitle>
        </DialogHeader>

        {step === "verify" ? (
          <div className="space-y-3 py-2">
            <p className="text-sm text-muted-foreground">
              계정 보호를 위해 현재 비밀번호를 입력해주세요.
            </p>
            <div className="grid gap-1.5">
              <Label className="text-xs">현재 비밀번호</Label>
              <PasswordInput
                value={currentPw}
                onChange={(e) => setCurrentPw(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && verify()}
                placeholder="비밀번호"
              />
            </div>
            <DialogFooter className="gap-2">
              <Button variant="secondary" onClick={() => onOpenChange(false)}>
                취소
              </Button>
              <Button onClick={verify} disabled={verifying}>
                확인
              </Button>
            </DialogFooter>
          </div>
        ) : (
          <div className="space-y-3 py-2">
            <div className="grid gap-1.5">
              <Label className="text-xs">ID</Label>
              <Input className="glass-input" value={profile.login_id} disabled />
            </div>
            <div className="grid gap-1.5">
              <Label className="text-xs">이름</Label>
              <Input
                className="glass-input"
                value={name}
                onChange={(e) => setName(e.target.value)}
                maxLength={50}
              />
            </div>
            <div className="grid grid-cols-2 gap-2">
              <div className="grid gap-1.5">
                <Label className="text-xs">과 (Division)</Label>
                <Select
                  value={divisionId ?? "__none"}
                  onValueChange={(v) => {
                    const newDiv = v === "__none" ? null : v;
                    setDivisionId(newDiv);
                    setTeamId(null);
                  }}
                >
                  <SelectTrigger className="glass-input">
                    <SelectValue placeholder="선택" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="__none">미분류</SelectItem>
                    {divisions.map((d) => (
                      <SelectItem key={d.id} value={d.id}>
                        {d.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="grid gap-1.5">
                <Label className="text-xs">팀 (Team)</Label>
                <Select
                  value={teamId ?? "__none"}
                  onValueChange={(v) => setTeamId(v === "__none" ? null : v)}
                  disabled={position === "과장" || !divisionId}
                >
                  <SelectTrigger className="glass-input">
                    <SelectValue placeholder="선택" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="__none">해당없음</SelectItem>
                    {teams.map((t) => (
                      <SelectItem key={t.id} value={t.id}>
                        {t.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>
            <div className="grid gap-1.5">
              <Label className="text-xs">직책</Label>
              <Select
                value={position}
                onValueChange={(v) => {
                  setPosition(v as Position);
                  if (v === "과장") setTeamId(null);
                }}
              >
                <SelectTrigger className="glass-input">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {(["과장", "팀장", "팀원", "서무"] as const).map((p) => (
                    <SelectItem key={p} value={p}>
                      {p}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="grid grid-cols-2 gap-2">
              <div className="grid gap-1.5">
                <Label className="text-xs">새 비밀번호 (선택)</Label>
                <PasswordInput
                  value={newPw}
                  onChange={(e) => setNewPw(e.target.value)}
                  placeholder="변경 시 입력"
                />
              </div>
              <div className="grid gap-1.5">
                <Label className="text-xs">새 비밀번호 확인</Label>
                <PasswordInput
                  value={confirmPw}
                  onChange={(e) => setConfirmPw(e.target.value)}
                  placeholder="다시 입력"
                />
              </div>
            </div>
            <DialogFooter className="gap-2">
              <Button variant="secondary" onClick={() => onOpenChange(false)}>
                취소
              </Button>
              <Button
                onClick={() => save.mutate()}
                disabled={save.isPending}
              >
                저장
              </Button>
            </DialogFooter>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}