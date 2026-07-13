import { createFileRoute, useNavigate, Link } from "@tanstack/react-router";
import { useEffect, useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useServerFn } from "@/lib/server-functions";
import { supabase } from "@/integrations/supabase/client";
import { getMyProfile } from "@/lib/profile.functions";
import {
  adminListUsers,
  adminUpdateUser,
  adminDeleteUser,
  adminCreateDivision,
  adminUpdateDivision,
  adminDeleteDivision,
  adminCreateTeam,
  adminUpdateTeam,
  adminDeleteTeam,
  adminCreateCategory,
  adminUpdateCategory,
  adminDeleteCategory,
  adminListTemplates,
  adminSaveTemplate,
} from "@/lib/admin.functions";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Table,
  TableHeader,
  TableBody,
  TableRow,
  TableHead,
  TableCell,
} from "@/components/ui/table";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { ArrowLeft, Pencil, Trash2, Plus, Check, X } from "lucide-react";
import { toast } from "sonner";

export const Route = createFileRoute("/admin")({
  component: AdminConsole,
  head: () => ({ meta: [{ title: "관리자 콘솔 | 통합 업무 관리 시스템" }] }),
});

function AdminConsole() {
  const navigate = useNavigate();
  const [ready, setReady] = useState(false);
  const fetchProfile = useServerFn(getMyProfile);

  useEffect(() => {
    supabase.auth.getSession().then(({ data }) => {
      if (!data.session) navigate({ to: "/login" });
      else setReady(true);
    });
  }, [navigate]);

  const profileQuery = useQuery({
    queryKey: ["my-profile"],
    queryFn: () => fetchProfile(),
    enabled: ready,
  });

  useEffect(() => {
    if (profileQuery.data && !profileQuery.data.isAdmin) {
      toast.error("관리자만 접근할 수 있습니다.");
      navigate({ to: "/" });
    }
  }, [profileQuery.data, navigate]);

  if (!ready || !profileQuery.data?.isAdmin) return null;

  return (
    <main className="min-h-screen px-4 py-6 lg:px-8">
      <div className="mx-auto max-w-[1200px] space-y-4">
        <header className="glass-panel flex items-center justify-between rounded-3xl px-6 py-4">
          <div className="flex items-center gap-3">
            <Link to="/">
              <Button variant="ghost" size="icon" className="h-8 w-8">
                <ArrowLeft className="h-4 w-4" />
              </Button>
            </Link>
            <div>
              <h1 className="text-lg font-bold tracking-tight">관리자 콘솔</h1>
              <p className="text-xs text-muted-foreground">사용자 · 메타 · 템플릿 관리</p>
            </div>
          </div>
        </header>

        <Tabs defaultValue="users" className="space-y-4">
          <TabsList className="glass-panel rounded-2xl p-1">
            <TabsTrigger value="users" className="rounded-xl">사용자 관리</TabsTrigger>
            <TabsTrigger value="meta" className="rounded-xl">메타 관리</TabsTrigger>
            <TabsTrigger value="templates" className="rounded-xl">템플릿 관리</TabsTrigger>
          </TabsList>

          <TabsContent value="users"><UsersTab /></TabsContent>
          <TabsContent value="meta"><MetaTab /></TabsContent>
          <TabsContent value="templates"><TemplatesTab /></TabsContent>
        </Tabs>
      </div>
    </main>
  );
}

// ===================== USERS =====================
function UsersTab() {
  const qc = useQueryClient();
  const list = useServerFn(adminListUsers);
  const update = useServerFn(adminUpdateUser);
  const del = useServerFn(adminDeleteUser);
  const q = useQuery({ queryKey: ["admin-users"], queryFn: () => list() });

  if (q.isLoading) return <div className="glass-panel rounded-2xl p-6 text-sm">로딩 중...</div>;
  if (!q.data) return null;

  const { users, divisions, teams } = q.data;
  const divName = (id: string | null) =>
    id ? divisions.find((d) => d.id === id)?.name ?? "미분류" : "미분류";
  const teamName = (id: string | null) =>
    id ? teams.find((t) => t.id === id)?.name ?? "해당없음" : "해당없음";

  const handleStatus = async (user_id: string, status: "가입신청" | "승인" | "탈퇴") => {
    try {
      await update({ data: { user_id, status } });
      toast.success("상태가 변경되었습니다.");
      qc.invalidateQueries({ queryKey: ["admin-users"] });
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "변경 실패");
    }
  };

  const handleDelete = async (user_id: string) => {
    try {
      await del({ data: { user_id } });
      toast.success("삭제되었습니다.");
      qc.invalidateQueries({ queryKey: ["admin-users"] });
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "삭제 실패");
    }
  };

  return (
    <div className="glass-panel rounded-2xl p-4">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead className="w-12">No</TableHead>
            <TableHead>ID</TableHead>
            <TableHead>이름</TableHead>
            <TableHead>부서</TableHead>
            <TableHead>팀</TableHead>
            <TableHead>직책</TableHead>
            <TableHead>상태</TableHead>
            <TableHead className="text-right">관리</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {users.map((u) => {
            const unassigned = !u.division_id;
            return (
              <TableRow key={u.id}>
                <TableCell className="tabular-nums">{u.user_no_pk}</TableCell>
                <TableCell className="font-mono text-xs">{u.login_id}</TableCell>
                <TableCell>{u.name}</TableCell>
                <TableCell className={unassigned ? "text-destructive font-semibold" : ""}>
                  {divName(u.division_id)}
                </TableCell>
                <TableCell>{teamName(u.team_id)}</TableCell>
                <TableCell>{u.position}</TableCell>
                <TableCell>
                  <div className="flex gap-1">
                    {(["가입신청", "승인", "탈퇴"] as const).map((s) => (
                      <Button
                        key={s}
                        variant={u.status === s ? "default" : "outline"}
                        size="sm"
                        className="h-7 px-2 text-xs"
                        onClick={() => handleStatus(u.id, s)}
                      >
                        {s}
                      </Button>
                    ))}
                  </div>
                </TableCell>
                <TableCell className="text-right">
                  <AlertDialog>
                    <AlertDialogTrigger asChild>
                      <Button variant="ghost" size="icon" className="h-7 w-7 text-destructive">
                        <Trash2 className="h-3.5 w-3.5" />
                      </Button>
                    </AlertDialogTrigger>
                    <AlertDialogContent>
                      <AlertDialogHeader>
                        <AlertDialogTitle>사용자 삭제</AlertDialogTitle>
                        <AlertDialogDescription>
                          {u.name}({u.login_id})을(를) 삭제합니다. 되돌릴 수 없습니다.
                        </AlertDialogDescription>
                      </AlertDialogHeader>
                      <AlertDialogFooter>
                        <AlertDialogCancel>취소</AlertDialogCancel>
                        <AlertDialogAction onClick={() => handleDelete(u.id)}>
                          삭제
                        </AlertDialogAction>
                      </AlertDialogFooter>
                    </AlertDialogContent>
                  </AlertDialog>
                </TableCell>
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
    </div>
  );
}

// ===================== META =====================
function MetaTab() {
  return (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
      <DivisionsPanel />
      <TeamsPanel />
      <CategoriesPanel />
    </div>
  );
}

function DivisionsPanel() {
  const qc = useQueryClient();
  const list = useServerFn(adminListUsers);
  const create = useServerFn(adminCreateDivision);
  const update = useServerFn(adminUpdateDivision);
  const del = useServerFn(adminDeleteDivision);
  const q = useQuery({ queryKey: ["admin-users"], queryFn: () => list() });
  const [name, setName] = useState("");
  const [editing, setEditing] = useState<{ id: string; name: string } | null>(null);

  const refresh = () => qc.invalidateQueries({ queryKey: ["admin-users"] });

  const handleCreate = async () => {
    if (!name.trim()) return;
    try {
      await create({ data: { name: name.trim() } });
      setName("");
      toast.success("추가되었습니다.");
      refresh();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "추가 실패");
    }
  };

  return (
    <div className="glass-panel rounded-2xl p-4 space-y-3">
      <h3 className="font-semibold text-sm">부서 (Division)</h3>
      <div className="flex gap-2">
        <Input
          className="glass-input h-8 text-sm"
          placeholder="부서명"
          value={name}
          onChange={(e) => setName(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && handleCreate()}
        />
        <Button size="sm" onClick={handleCreate}><Plus className="h-3.5 w-3.5" /></Button>
      </div>
      <div className="space-y-1">
        {(q.data?.divisions ?? []).map((d) => (
          <div key={d.id} className="flex items-center gap-2 rounded-lg bg-white/40 px-2 py-1 text-sm">
            {editing?.id === d.id ? (
              <>
                <Input
                  className="glass-input h-7 text-sm"
                  value={editing.name}
                  onChange={(e) => setEditing({ ...editing, name: e.target.value })}
                />
                <Button size="icon" variant="ghost" className="h-6 w-6" onClick={async () => {
                  await update({ data: { id: editing.id, name: editing.name.trim() } });
                  setEditing(null); refresh();
                }}>
                  <Check className="h-3.5 w-3.5" />
                </Button>
                <Button size="icon" variant="ghost" className="h-6 w-6" onClick={() => setEditing(null)}>
                  <X className="h-3.5 w-3.5" />
                </Button>
              </>
            ) : (
              <>
                <span className="flex-1">{d.name}</span>
                <Button size="icon" variant="ghost" className="h-6 w-6" onClick={() => setEditing({ id: d.id, name: d.name })}>
                  <Pencil className="h-3 w-3" />
                </Button>
                <AlertDialog>
                  <AlertDialogTrigger asChild>
                    <Button size="icon" variant="ghost" className="h-6 w-6 text-destructive">
                      <Trash2 className="h-3 w-3" />
                    </Button>
                  </AlertDialogTrigger>
                  <AlertDialogContent>
                    <AlertDialogHeader>
                      <AlertDialogTitle>부서 삭제</AlertDialogTitle>
                      <AlertDialogDescription>
                        '{d.name}' 부서 및 산하 팀이 모두 삭제됩니다. 소속 사용자는 '미분류'로 변경됩니다.
                      </AlertDialogDescription>
                    </AlertDialogHeader>
                    <AlertDialogFooter>
                      <AlertDialogCancel>취소</AlertDialogCancel>
                      <AlertDialogAction onClick={async () => {
                        await del({ data: { id: d.id } });
                        toast.success("삭제됨"); refresh();
                      }}>삭제</AlertDialogAction>
                    </AlertDialogFooter>
                  </AlertDialogContent>
                </AlertDialog>
              </>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

function TeamsPanel() {
  const qc = useQueryClient();
  const list = useServerFn(adminListUsers);
  const create = useServerFn(adminCreateTeam);
  const update = useServerFn(adminUpdateTeam);
  const del = useServerFn(adminDeleteTeam);
  const q = useQuery({ queryKey: ["admin-users"], queryFn: () => list() });
  const [name, setName] = useState("");
  const [divisionId, setDivisionId] = useState<string>("");
  const [editing, setEditing] = useState<{ id: string; name: string; division_id: string } | null>(null);
  const refresh = () => qc.invalidateQueries({ queryKey: ["admin-users"] });

  const divisions = q.data?.divisions ?? [];
  const teams = q.data?.teams ?? [];

  const handleCreate = async () => {
    if (!name.trim() || !divisionId) return;
    try {
      await create({ data: { name: name.trim(), division_id: divisionId } });
      setName("");
      toast.success("추가됨"); refresh();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "추가 실패");
    }
  };

  return (
    <div className="glass-panel rounded-2xl p-4 space-y-3">
      <h3 className="font-semibold text-sm">팀 (Team)</h3>
      <div className="space-y-2">
        <Select value={divisionId} onValueChange={setDivisionId}>
          <SelectTrigger className="glass-input h-8 text-sm">
            <SelectValue placeholder="부서 선택" />
          </SelectTrigger>
          <SelectContent>
            {divisions.map((d) => (
              <SelectItem key={d.id} value={d.id}>{d.name}</SelectItem>
            ))}
          </SelectContent>
        </Select>
        <div className="flex gap-2">
          <Input
            className="glass-input h-8 text-sm"
            placeholder="팀명"
            value={name}
            onChange={(e) => setName(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleCreate()}
          />
          <Button size="sm" onClick={handleCreate}><Plus className="h-3.5 w-3.5" /></Button>
        </div>
      </div>
      <div className="space-y-1">
        {teams.map((t) => {
          const divName = divisions.find((d) => d.id === t.division_id)?.name ?? "?";
          return (
            <div key={t.id} className="flex items-center gap-2 rounded-lg bg-white/40 px-2 py-1 text-sm">
              {editing?.id === t.id ? (
                <>
                  <Input
                    className="glass-input h-7 text-sm flex-1"
                    value={editing.name}
                    onChange={(e) => setEditing({ ...editing, name: e.target.value })}
                  />
                  <Button size="icon" variant="ghost" className="h-6 w-6" onClick={async () => {
                    await update({ data: editing });
                    setEditing(null); refresh();
                  }}>
                    <Check className="h-3.5 w-3.5" />
                  </Button>
                  <Button size="icon" variant="ghost" className="h-6 w-6" onClick={() => setEditing(null)}>
                    <X className="h-3.5 w-3.5" />
                  </Button>
                </>
              ) : (
                <>
                  <span className="flex-1">
                    <span className="text-muted-foreground text-xs">{divName} ·</span> {t.name}
                  </span>
                  <Button size="icon" variant="ghost" className="h-6 w-6" onClick={() => setEditing({ id: t.id, name: t.name, division_id: t.division_id })}>
                    <Pencil className="h-3 w-3" />
                  </Button>
                  <AlertDialog>
                    <AlertDialogTrigger asChild>
                      <Button size="icon" variant="ghost" className="h-6 w-6 text-destructive">
                        <Trash2 className="h-3 w-3" />
                      </Button>
                    </AlertDialogTrigger>
                    <AlertDialogContent>
                      <AlertDialogHeader>
                        <AlertDialogTitle>팀 삭제</AlertDialogTitle>
                        <AlertDialogDescription>
                          '{t.name}' 팀을 삭제합니다. 소속 사용자는 '해당없음'으로 변경됩니다.
                        </AlertDialogDescription>
                      </AlertDialogHeader>
                      <AlertDialogFooter>
                        <AlertDialogCancel>취소</AlertDialogCancel>
                        <AlertDialogAction onClick={async () => {
                          await del({ data: { id: t.id } });
                          toast.success("삭제됨"); refresh();
                        }}>삭제</AlertDialogAction>
                      </AlertDialogFooter>
                    </AlertDialogContent>
                  </AlertDialog>
                </>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

function CategoriesPanel() {
  const qc = useQueryClient();
  const list = useServerFn(adminListTemplates);
  const create = useServerFn(adminCreateCategory);
  const update = useServerFn(adminUpdateCategory);
  const del = useServerFn(adminDeleteCategory);
  const q = useQuery({ queryKey: ["admin-templates"], queryFn: () => list() });
  const [name, setName] = useState("");
  const [editing, setEditing] = useState<{ id: string; name: string } | null>(null);
  const refresh = () => qc.invalidateQueries({ queryKey: ["admin-templates"] });

  return (
    <div className="glass-panel rounded-2xl p-4 space-y-3">
      <h3 className="font-semibold text-sm">카테고리 (Category)</h3>
      <div className="flex gap-2">
        <Input
          className="glass-input h-8 text-sm"
          placeholder="카테고리명"
          value={name}
          onChange={(e) => setName(e.target.value)}
          onKeyDown={async (e) => {
            if (e.key === "Enter" && name.trim()) {
              try { await create({ data: { name: name.trim() } }); setName(""); toast.success("추가됨"); refresh(); }
              catch (err) { toast.error(err instanceof Error ? err.message : "실패"); }
            }
          }}
        />
        <Button size="sm" onClick={async () => {
          if (!name.trim()) return;
          try { await create({ data: { name: name.trim() } }); setName(""); toast.success("추가됨"); refresh(); }
          catch (err) { toast.error(err instanceof Error ? err.message : "실패"); }
        }}><Plus className="h-3.5 w-3.5" /></Button>
      </div>
      <div className="space-y-1">
        {(q.data?.categories ?? []).map((c) => (
          <div key={c.id} className="flex items-center gap-2 rounded-lg bg-white/40 px-2 py-1 text-sm">
            {editing?.id === c.id ? (
              <>
                <Input
                  className="glass-input h-7 text-sm"
                  value={editing.name}
                  onChange={(e) => setEditing({ ...editing, name: e.target.value })}
                />
                <Button size="icon" variant="ghost" className="h-6 w-6" onClick={async () => {
                  await update({ data: { id: editing.id, name: editing.name.trim() } });
                  setEditing(null); refresh();
                }}>
                  <Check className="h-3.5 w-3.5" />
                </Button>
                <Button size="icon" variant="ghost" className="h-6 w-6" onClick={() => setEditing(null)}>
                  <X className="h-3.5 w-3.5" />
                </Button>
              </>
            ) : (
              <>
                <span className="flex-1">{c.name}</span>
                <Button size="icon" variant="ghost" className="h-6 w-6" onClick={() => setEditing({ id: c.id, name: c.name })}>
                  <Pencil className="h-3 w-3" />
                </Button>
                <AlertDialog>
                  <AlertDialogTrigger asChild>
                    <Button size="icon" variant="ghost" className="h-6 w-6 text-destructive">
                      <Trash2 className="h-3 w-3" />
                    </Button>
                  </AlertDialogTrigger>
                  <AlertDialogContent>
                    <AlertDialogHeader>
                      <AlertDialogTitle>카테고리 삭제</AlertDialogTitle>
                      <AlertDialogDescription>
                        '{c.name}' 카테고리 및 연결된 템플릿이 삭제됩니다. 사용 중인 업무는 '해당없음'으로 변경됩니다.
                      </AlertDialogDescription>
                    </AlertDialogHeader>
                    <AlertDialogFooter>
                      <AlertDialogCancel>취소</AlertDialogCancel>
                      <AlertDialogAction onClick={async () => {
                        await del({ data: { id: c.id } });
                        toast.success("삭제됨"); refresh();
                      }}>삭제</AlertDialogAction>
                    </AlertDialogFooter>
                  </AlertDialogContent>
                </AlertDialog>
              </>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

// ===================== TEMPLATES =====================
function TemplatesTab() {
  const qc = useQueryClient();
  const list = useServerFn(adminListTemplates);
  const save = useServerFn(adminSaveTemplate);
  const q = useQuery({ queryKey: ["admin-templates"], queryFn: () => list() });
  const [drafts, setDrafts] = useState<Record<string, string>>({});

  const templateMap = useMemo(() => {
    const m: Record<string, string> = {};
    (q.data?.templates ?? []).forEach((t) => { m[t.category_id] = t.content; });
    return m;
  }, [q.data]);

  const getValue = (id: string) => drafts[id] ?? templateMap[id] ?? "";

  const handleSave = async (category_id: string) => {
    try {
      await save({ data: { category_id, content: getValue(category_id) } });
      toast.success("저장되었습니다.");
      qc.invalidateQueries({ queryKey: ["admin-templates"] });
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "저장 실패");
    }
  };

  if (q.isLoading) return <div className="glass-panel rounded-2xl p-6 text-sm">로딩 중...</div>;
  const cats = q.data?.categories ?? [];
  if (cats.length === 0) {
    return <div className="glass-panel rounded-2xl p-6 text-sm text-muted-foreground">먼저 메타 관리에서 카테고리를 추가하세요.</div>;
  }

  return (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
      {cats.map((c) => {
        const v = getValue(c.id);
        return (
          <div key={c.id} className="glass-panel rounded-2xl p-4 space-y-2">
            <div className="flex items-center justify-between">
              <h4 className="font-semibold text-sm">{c.name}</h4>
              <span className="text-xs text-muted-foreground tabular-nums">{v.length}/300</span>
            </div>
            <Textarea
              className="glass-input min-h-[140px] text-sm"
              maxLength={300}
              value={v}
              onChange={(e) => setDrafts((d) => ({ ...d, [c.id]: e.target.value }))}
              placeholder="템플릿 내용을 입력하세요..."
            />
            <Button size="sm" onClick={() => handleSave(c.id)}>저장</Button>
          </div>
        );
      })}
    </div>
  );
}